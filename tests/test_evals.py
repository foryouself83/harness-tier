"""The model-free half of the eval harness.

Measuring spends hours of rate-limit budget; checking spends nothing. Keeping the check
here means `uv run pytest` and `unit-test.yml` both enforce it with no new wiring.
"""

import json
import re
import subprocess
import sys
import threading
import warnings
from pathlib import Path

import pytest
import yaml

import evals.run as run
import evals.scores as scores
import evals.stream as stream
import scripts.skill_sandbox as sandbox

REPO = Path(__file__).resolve().parent.parent
CASES = yaml.safe_load((REPO / "evals/cases.yaml").read_text(encoding="utf-8"))
SKILLS = sorted(CASES["skills"])

HAPPY_CASES = 5
NEGATIVE_CASES = 5


class _NoRealSessions:
    """Stands in for the `subprocess` module inside `evals.run`, refusing the two spawn
    entry points (`Popen` carries the sessions since the tree-kill change; `run` is the
    taskkill helper and the historical spawn path — refusing both keeps the guard ahead
    of refactors between them).

    Everything else — DEVNULL, TimeoutExpired — is delegated, because `run_session`
    references those too and a bare object would fail with an AttributeError that says
    nothing about why."""

    @staticmethod
    def run(*_args, **_kwargs):
        raise AssertionError(
            "this test tried to spawn a real `claude` session. Every test here must be "
            "model-free: monkeypatch `evals.run._one` to return (stream.Observation(...), "
            "stderr) instead of letting it reach run_session. If a real session is genuinely "
            "what you want, it belongs in `evals/run.py`, not in the suite."
        )

    Popen = run

    def __getattr__(self, attr):
        return getattr(subprocess, attr)


@pytest.fixture(autouse=True)
def no_real_sessions(monkeypatch):
    """Make the model-free guarantee structural rather than a convention.

    Every test below monkeypatches `run._one`, which is the only reason none of them spends
    a session — a guarantee that rests on each future test author remembering the same thing.
    A test that called `run_session` (or `_one` unpatched) would spawn real `claude`
    processes against a rate limit, in CI, silently and slowly. Patching the module object's
    `subprocess` reference rather than `subprocess.run` itself keeps the block scoped to
    `evals.run`, so the rest of the suite can still shell out."""
    monkeypatch.setattr(run, "subprocess", _NoRealSessions())


@pytest.fixture(autouse=True)
def reset_capture_state():
    """Capture state is module-level, so it leaks between tests without this — `CAPTURED` makes
    the second write skip and the failure reads as a broken implementation.

    Calls the production reset rather than listing the globals again. The earlier version
    listed them, and that is how the bug got in: this fixture reset three while the runner
    reset two, so the suite stayed green over a leak a real second run would hit."""
    run._reset_capture_state()
    yield
    run._reset_capture_state()


def frontmatter(name: str) -> dict:
    path = REPO / f"skills/{name}/SKILL.md"
    text = path.read_text(encoding="utf-8")
    block = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    # A skill with no parseable frontmatter would otherwise surface as `NoneType has no
    # attribute 'group'` somewhere downstream, naming neither the skill nor the problem.
    assert block, f"{path} has no YAML frontmatter block"
    return yaml.safe_load(block.group(1))


def test_cases_cover_every_model_invoked_skill_and_nothing_else():
    """A skill with `disable-model-invocation` never puts its description in front of the
    model, so it cannot fail to be invoked — a case for it would report coverage that does
    not exist. The reverse gap is worse: a model-invoked skill with no cases is unmeasured
    while the suite is green."""
    invocable = {
        p.parent.name
        for p in REPO.glob("skills/*/SKILL.md")
        if not frontmatter(p.parent.name).get("disable-model-invocation")
    }
    assert set(SKILLS) == invocable, (
        f"cases.yaml covers {sorted(SKILLS)} but the model-invoked skills are {sorted(invocable)}"
    )


@pytest.mark.parametrize("name", SKILLS)
def test_each_skill_has_the_full_case_set(name: str):
    entry = CASES["skills"][name]
    assert len(entry["happy"]) == HAPPY_CASES, f"{name}: expected {HAPPY_CASES} happy cases"
    assert len(entry["negative"]) == NEGATIVE_CASES, (
        f"{name}: expected {NEGATIVE_CASES} negative cases"
    )


@pytest.mark.parametrize("name", SKILLS)
def test_case_fixtures_name_a_real_sandbox_scenario(name: str):
    """A typo'd fixture name would silently fall back to an empty directory and the run
    would still produce a number — a wrong one, indistinguishable from a real score."""
    entry = CASES["skills"][name]
    fixtures = {entry.get("fixture")}
    for case in entry["happy"] + entry["negative"]:
        if isinstance(case, dict):
            fixtures.add(case.get("fixture"))
    for f in fixtures - {None}:
        assert f in sandbox.BY_NAME, f"{name}: unknown fixture {f!r}"


# Real captured `claude -p --output-format stream-json` transcripts, not hand-written JSON —
# which is the point of them, and the reason they are reduced by dropping whole events rather
# than by editing any event's contents. `stream.observe` reads exactly four kinds (`init`,
# `assistant`, `rate_limit_event`, `result`); the captures also carried `hook_response`,
# `hook_started`, `hook_progress`, `thinking_tokens`, `task_*` and `user` events, 83% of the
# 332KB, none of it ever parsed. Those are gone; every surviving event is byte-identical to
# what the CLI emitted.
#
# What survives that reduction is the `init` event, kept whole: it is the source of `available`
# and cannot be trimmed without rewriting a captured event into fiction. These two were captured
# under the isolated config dir `evals.run.isolated_config_dir` builds, so `init` lists
# `harness-tier@inline` as its only plugin — the earlier captures carried the whole machine
# instead (18 plugins with absolute paths, one of them private, plus the home directory), and
# that is gone. What the isolation cannot strip stays: the account-level claude.ai MCP connectors
# still appear by name (no tokens — `apiKeySource` is `none`), because they are scoped to the
# account, not the config dir.
# Both were captured at the current `MAX_TURNS` = 6, so there is no capture-date ambiguity to
# reason around: `stream-invoked` is a real turn-cap firing (`error_max_turns`, num_turns 7) and
# `stream-quiet` a clean `success` (num_turns 9). The pair is read for tool calls per turn, which
# is what `test_a_spent_turn_cap_cannot_be_ambiguous_at_this_budget` uses it for.
FIXTURES = REPO / "evals/fixtures"


def test_observe_sees_a_skill_that_fired():
    obs = stream.observe((FIXTURES / "stream-invoked.jsonl").read_text(encoding="utf-8"))
    assert "integration" in obs.fired
    assert "integration" in obs.available


def test_observe_separates_available_from_fired():
    """Both a broken --plugin-dir and a description that stopped working score 0.0. Only
    the availability list tells them apart, and confusing the two would have the harness
    report a regression every time the path was wrong."""
    obs = stream.observe((FIXTURES / "stream-quiet.jsonl").read_text(encoding="utf-8"))
    assert obs.fired == []
    assert "integration" in obs.available


def test_observe_survives_a_truncated_final_line():
    text = (FIXTURES / "stream-invoked.jsonl").read_text(encoding="utf-8")
    obs = stream.observe(text + '{"type":"assis')
    assert "integration" in obs.fired


def test_observe_tells_an_outright_failure_from_a_turn_cap():
    """Both report is_error. Only the subtype separates them, and conflating the two would
    either abort every capped run or silently score an unauthenticated session as a miss."""
    capped = (FIXTURES / "stream-invoked.jsonl").read_text(encoding="utf-8")
    assert stream.observe(capped).turns_exhausted
    assert not stream.observe(capped).errored
    failed = json.dumps({"type": "result", "subtype": "success", "is_error": True})
    assert stream.observe(failed).errored


@pytest.mark.parametrize("subtype", ["success", "error_during_execution", "some_future_subtype"])
def test_every_failing_subtype_but_the_turn_cap_is_an_error(subtype: str):
    """The flag is a blacklist of one — only `error_max_turns` is a legitimate observation
    despite is_error. A whitelist admitting `success` alone left `error_during_execution`
    with errored=False, turns_exhausted=False and completed=True: a session that failed
    outright, tallied as a clean "the skill did not fire", with nothing printed. An unknown
    future subtype has to land on the loud side of that line, not the silent one."""
    failed = json.dumps({"type": "result", "subtype": subtype, "is_error": True})
    obs = stream.observe(failed)
    assert obs.errored, subtype
    assert not obs.turns_exhausted, subtype


def test_observe_reports_a_rate_limited_session():
    """A full run outlasts the five-hour window and `overageStatus` is `rejected`, so
    sessions will start failing mid-measurement. A refused session that gets recorded as
    "the skill did not fire" writes a fabricated score into the baseline."""
    healthy = (FIXTURES / "stream-invoked.jsonl").read_text(encoding="utf-8")
    assert not stream.observe(healthy).rate_limited
    blocked = healthy + json.dumps(
        {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected"}}
    )
    assert stream.observe(blocked).rate_limited


def test_a_rate_limit_warning_is_not_a_stop_signal():
    """A warning-level status rides on a session whose request succeeded — stopping on it
    made every run started late in the window abort on its first session, and every re-run
    abort the same way until the window reset. Only "rejected" (the request actually failed)
    stops the plan."""
    warned = json.dumps(
        {"type": "rate_limit_event", "rate_limit_info": {"status": "allowed_warning"}}
    )
    assert not stream.observe(warned).rate_limited


def test_a_null_skill_input_is_skipped_not_fatal():
    """An aborted Skill call serializes as {"skill": null}; .get's default only covers a
    missing key, so None reached _local() and an AttributeError killed observe() for the
    whole stream — the session died with a traceback instead of being scored."""
    line = json.dumps(
        {
            "type": "assistant",
            "message": {
                "content": [{"type": "tool_use", "name": "Skill", "input": {"skill": None}}]
            },
        }
    )
    obs = stream.observe(line)
    assert obs.fired == []
    assert obs.tool_calls == 1


def test_observe_counts_every_tool_call_not_just_skill():
    """The counter exists to tell a genuinely ambiguous cut from a decided miss, which only
    works if it counts every tool call the session made — Bash, Read, whatever — not just the
    Skill call itself. A counter placed after the Skill test would only ever see Skill calls."""

    def independent_tool_use_count(path: Path) -> int:
        count = 0
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("type") == "assistant":
                count += sum(
                    1
                    for block in event.get("message", {}).get("content", [])
                    if block.get("type") == "tool_use"
                )
        return count

    for fixture in ("stream-invoked.jsonl", "stream-quiet.jsonl"):
        path = FIXTURES / fixture
        obs = stream.observe(path.read_text(encoding="utf-8"))
        assert obs.tool_calls == independent_tool_use_count(path), fixture
        # Neither fixture is all-Skill, so a count equal to the independent parse and greater
        # than zero rules out the counter having silently narrowed back to Skill-only.
        assert obs.tool_calls > 0, fixture


def test_the_narrowed_rule_only_counts_a_cut_that_never_had_its_chance(monkeypatch):
    """(a) cut at 1 tool call and (c) a turn cap spent on almost nothing are both genuinely
    ambiguous — the session either never got far enough to decide or used its budget without
    deciding. Note (c) and (d) are **synthetic**: at MAX_TURNS=6 a spent cap cannot sit below
    FIRE_BY_TOOL_CALL=3, so the runner never produces them (see
    `test_a_spent_turn_cap_cannot_be_ambiguous_at_this_budget`). They fix the rule's shape for
    the day the budget changes; they are not evidence that the branch fires today.
    (b) cut after 5 tool calls had already passed FIRE_BY_TOOL_CALL=3 without
    firing, so it is a decided miss and must not inflate `truncated` the way the old
    completed-only rule did. (d) is the same judgement applied to a turn cap: a capped
    session that made 5 tool calls also had its chance, and counting every cap as ambiguous
    regardless of tool calls is what put a truncation warning on the skill nearest the floor
    for sessions that were not truncated in any meaningful sense."""
    name = "integration"
    entry = {"happy": ["p"], "negative": ["n"]}
    fallback = stream.Observation(available=[name], completed=True)
    scenarios = {
        "a: not completed, 1 tool call": (
            stream.Observation(available=[name], completed=False, tool_calls=1),
            1.0,
        ),
        "b: not completed, 5 tool calls": (
            stream.Observation(available=[name], completed=False, tool_calls=5),
            0.0,
        ),
        "c: completed, turn-capped, 0 tool calls": (
            stream.Observation(available=[name], completed=True, turns_exhausted=True),
            1.0,
        ),
        "d: completed, turn-capped, 5 tool calls": (
            stream.Observation(
                available=[name], completed=True, turns_exhausted=True, tool_calls=5
            ),
            0.0,
        ),
    }
    for label, (happy_obs, expected_truncated) in scenarios.items():

        def fake_one(prompt, fixture, config_dir, restricted, _obs=happy_obs):
            return (_obs if prompt == "p" else fallback), ""

        monkeypatch.setattr(run, "_one", fake_one)
        result = run.measure(name, entry, reps=1, config_dir=Path("."), jobs=1)
        assert result["truncated"] == expected_truncated, label


def _injected_session_text() -> str:
    """Everything the SessionStart hook puts into a session, not just the rule file.

    `hooks/inject-risk-tiers.sh` wraps `rules/risk-tiers.md` in a hardcoded preamble, and that
    preamble is the *strongest* form the help takes — it says outright that the agent's action
    MUST be to invoke /flow. Reading only the rule file would miss it, and would also report
    "the help is gone" if someone rewrote the rule file's slash forms into prose while the
    preamble kept naming the skill.

    None of it reaches a session unless `hooks.json` still registers the script for `startup`.
    Narrowing that matcher would end the help while both files still named the skills, so this
    returns "" in that case — the reverse check then reports the caveat as stale, which is what
    it would be."""
    hooks = json.loads((REPO / "hooks/hooks.json").read_text(encoding="utf-8"))
    registered = any(
        "startup" in (entry.get("matcher") or "")
        and any("inject-risk-tiers" in h.get("command", "") for h in entry.get("hooks") or [])
        for entry in hooks.get("hooks", {}).get("SessionStart") or []
    )
    if not registered:
        return ""
    return "\n".join(
        (REPO / p).read_text(encoding="utf-8")
        for p in ("hooks/inject-risk-tiers.sh", "rules/risk-tiers.md")
    )


def _skills_named_as_commands(text: str) -> set[str]:
    """Measured skills the injected text tells the agent to run, by their `/name` form.

    Intersected with the measured set rather than returned raw: a bare `/([a-z-]+)` matches
    `and/or`, `lint/static/import_lint/test` and `integration/staging/production` — 37 tokens
    in the current rule file, most of which are not invocations. Left unrestricted, reordering
    one branch-role list to `staging/integration` would force a false `hook_assisted` onto the
    `integration` skill, which the same file explicitly calls a branch role and not a skill.

    The boundary has to exclude a following hyphen, not just a following word character: `\\b`
    matches between `w` and `-`, so `/flow` would be found inside `/flow-init`,
    `/flow-uninstall` and the link `](../flow-tiers.yaml)` — leaving `flow` permanently in the
    named set and disabling the reverse stale check for it."""
    return {name for name in CASES["skills"] if re.search(rf"/{re.escape(name)}(?![\w-])", text)}


def test_the_hook_scan_does_not_match_a_longer_name_or_a_path():
    """`/flow` must not be found inside `/flow-init`, `/flow-uninstall`, or the markdown link
    `](../flow-tiers.yaml)` that the rule file already contains.

    A `\\b` boundary matches immediately before a hyphen, so it read all three as invocations —
    which would keep `flow` in the named set from a relative link alone and make the reverse
    "the help is gone" branch unable to fire for the skill it matters most for. The broader
    `/([a-z][a-z0-9-]*)` form this replaced did not have that failure (it tokenised
    `flow-tiers`); the fix has to beat both."""
    assert _skills_named_as_commands("see [flow-tiers.yaml](../flow-tiers.yaml)") == set()
    assert _skills_named_as_commands("run /flow-uninstall to remove the gate") == set()
    assert _skills_named_as_commands("`/flow-init` copies the scripts") == set()
    # …while still finding the real ones, punctuation and all.
    assert _skills_named_as_commands("enter `/flow` first") == {"flow"}
    assert _skills_named_as_commands("2. Run /doc-sync to harmonize.") == {"doc-sync"}


def test_every_skill_the_injected_rule_names_declares_hook_assisted():
    """The SessionStart hook injects its text into EVERY session, so a skill it tells the agent
    to run is measured with help that no consumer-free reading would give it. That is deliberate
    — consumers get the hook too — but it has two consequences per affected skill: its rate is
    not comparable to the others, and its ratchet is partly blind to its own description, since
    the hook can hold the number up while the description rots.

    This is checked rather than commented because the comment was wrong twice over. It sat only
    on `flow` and read "flow is the one skill measured with outside help" while the same rule
    names `/doc-sync` as a step in both the Docs and Dev workflows; the replacement note then
    put a hand-counted number on that and got it wrong too. No count is written down here — the
    check reads the text."""
    named = _skills_named_as_commands(_injected_session_text())
    measured = set(CASES["skills"])
    for name in sorted(named & measured):
        assert CASES["skills"][name].get("hook_assisted") is True, (
            f"{name}: the injected session text names /{name}, and it reaches every eval "
            f"session — declare `hook_assisted: true` in cases.yaml and say in the entry what "
            f"the hook does for it."
        )
    for name in sorted(measured):
        if CASES["skills"][name].get("hook_assisted") and name not in named:
            raise AssertionError(
                f"{name}: declares hook_assisted but nothing the SessionStart hook injects "
                f"names /{name} any more — the help is gone, so the caveat is stale and the "
                f"rate is now comparable to the unassisted skills."
            )


def test_a_spent_turn_cap_cannot_be_ambiguous_at_this_budget():
    """`cut_early` has two halves — killed-early and turn-capped — and the turn-capped one is
    unreachable at this budget: spending six turns costs at least five tool calls, so
    `tool_calls < FIRE_BY_TOOL_CALL` cannot hold alongside `turns_exhausted`. That left the
    scenario table above asserting on a state the runner cannot produce — a branch that reads
    as live because a test exercises it.

    Keeping the branch is right: the *rule* ("stopped before it could decide") is what should
    hold, and lowering MAX_TURNS to 2 would make the branch fire for real. What was missing is
    this: the emptiness now fails loudly if the two constants ever cross, instead of being a
    claim in prose that nothing rechecks."""
    assert run.MAX_TURNS > run.FIRE_BY_TOOL_CALL, (
        "MAX_TURNS dropped to or below FIRE_BY_TOOL_CALL — cut_early's turn-cap branch is now "
        "reachable, so scenarios (c)/(d) in the table above describe real sessions and the "
        "docstring calling them synthetic is stale."
    )
    # The load-bearing half: turns cost tool calls. Asserting it against `cut_early` would only
    # restate its own inequality, so it is measured on real captures instead. `stream-quiet`
    # shows the relationship is NOT one-for-one — 4 turns, 3 tool calls, because the closing
    # turn is text-only — so the honest bound is `tool_calls >= num_turns - 1`. At MAX_TURNS=6
    # that still lands on 5, comfortably past FIRE_BY_TOOL_CALL=3.
    for fixture in ("stream-invoked.jsonl", "stream-quiet.jsonl"):
        text = (FIXTURES / fixture).read_text(encoding="utf-8")
        obs = stream.observe(text)
        num_turns = 0
        for line in text.splitlines():
            if not line.strip():
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue  # a killed process ends mid-line; stream.observe tolerates it too
            if event.get("type") == "result":
                num_turns = max(num_turns, event.get("num_turns") or 0)
        assert num_turns, f"{fixture}: no result event carrying num_turns — nothing to check"
        assert obs.tool_calls >= num_turns - 1, (
            f"{fixture}: {obs.tool_calls} tool calls over {num_turns} turns breaks the bound "
            f"the empty-branch argument rests on — a session can now spend its whole budget "
            f"without reaching FIRE_BY_TOOL_CALL, so the turn-cap branch is live."
        )


def test_both_arms_apply_the_same_ambiguity_rule(monkeypatch):
    """`truncated` and `truncated_quiet` answer the same question about opposite arms, so a
    session that is ambiguous on one must be ambiguous on the other. They diverged once —
    the happy arm counted every turn cap, the negative arm counted none — which made the two
    diagnostics incomparable and inflated exactly one of them."""
    name = "integration"
    entry = {"happy": ["h"], "negative": ["n"]}
    capped_busy = stream.Observation(
        available=[name], completed=True, turns_exhausted=True, tool_calls=5
    )

    def fake_one(prompt, fixture, config_dir, restricted):
        return capped_busy, ""

    monkeypatch.setattr(run, "_one", fake_one)
    result = run.measure(name, entry, reps=1, config_dir=Path("."), jobs=1)
    assert result["truncated"] == result["truncated_quiet"] == 0.0


def test_the_narrowed_rule_lowers_truncated_below_the_old_constant(monkeypatch):
    """Under the old rule every cut-short happy miss counted regardless of how far the
    session got, which is what pinned `truncated` at a constant 0.80 across a 3-turn cap, a
    30s timeout and a 45s timeout while `invoke_rate` sat at 0.20 the whole time — a warning
    that always fires is not a signal. This mirrors that observed run: 2 of 10 happy samples
    fired, 8 were cut with varying tool-call counts.

    Counting every cut would make it 8/8 of the misses. Only the 3 below FIRE_BY_TOOL_CALL=3
    count, so 3/8. (The 0.80 above was that same run over the old all-samples denominator —
    8/10 — which is why the historical number and this assertion differ.)"""
    name = "integration"
    prompts = [f"p{i}" for i in range(10)]
    entry = {"happy": prompts, "negative": ["n"]}

    fired_obs = stream.Observation(available=[name], completed=True, fired=[name])
    obs_by_prompt = {prompts[0]: fired_obs, prompts[1]: fired_obs}
    for i, tool_calls in enumerate([0, 1, 2, 3, 4, 5, 6, 7]):
        obs_by_prompt[prompts[2 + i]] = stream.Observation(
            available=[name], completed=False, tool_calls=tool_calls
        )
    fallback = stream.Observation(available=[name], completed=True)

    def fake_one(prompt, fixture, config_dir, restricted):
        return obs_by_prompt.get(prompt, fallback), ""

    monkeypatch.setattr(run, "_one", fake_one)
    result = run.measure(name, entry, reps=1, config_dir=Path("."), jobs=1)

    # Counting every cut session would read 8/8 = 1.00 — the constant this rule replaced.
    assert result["invoke_rate"] == 0.2  # matches the observed 2/10
    assert result["truncated"] < 1.0
    assert result["truncated"] == 0.38  # 3/8 — only tool_calls 0, 1, 2 are below FIRE_BY_TOOL_CALL


def test_truncated_quiet_counts_the_negative_arm_not_the_happy_arm(monkeypatch):
    """The same early cut moves the two scored metrics in opposite directions: a happy sample
    cut before it could fire depresses `invoke_rate` via `truncated`, while a negative sample
    cut before it could over-fire flatters `false_fire` via `truncated_quiet`. If the two ever
    moved together on inputs built to separate them, the arms would be crossed."""
    name = "integration"
    entry = {"happy": ["h0", "h1"], "negative": ["n0", "n1"]}

    completed_quiet = stream.Observation(completed=True, tool_calls=5, available=[name])
    cut_early = stream.Observation(completed=False, tool_calls=1, available=[name])

    def fake_one(prompt, fixture, config_dir, restricted):
        return (cut_early if prompt in ("n0", "n1") else completed_quiet), ""

    monkeypatch.setattr(run, "_one", fake_one)
    result = run.measure(name, entry, reps=1, config_dir=Path("."), jobs=1)

    assert result["truncated"] == 0.0
    assert result["truncated_quiet"] == 1.0


def test_truncated_counts_the_happy_arm_not_the_negative_arm(monkeypatch):
    """The mirror image of the test above: happy cut early, negative completes cleanly. If
    `truncated_quiet` were reading the happy arm (or vice versa) this would come out the same
    as the previous test instead of flipping."""
    name = "integration"
    entry = {"happy": ["h0", "h1"], "negative": ["n0", "n1"]}

    completed_quiet = stream.Observation(completed=True, tool_calls=5, available=[name])
    cut_early = stream.Observation(completed=False, tool_calls=1, available=[name])

    def fake_one(prompt, fixture, config_dir, restricted):
        return (cut_early if prompt in ("h0", "h1") else completed_quiet), ""

    monkeypatch.setattr(run, "_one", fake_one)
    result = run.measure(name, entry, reps=1, config_dir=Path("."), jobs=1)

    assert result["truncated"] == 1.0


def test_truncated_is_a_share_of_the_misses_not_of_every_sample(monkeypatch):
    """`truncated` exists to say how much of a verdict rests on a session being cut short, and
    only a miss can rest on it — a session that fired already decided.

    Dividing by every sample instead capped the value at `1 - invoke_rate`, which made the same
    0.20 warning threshold mean a different thing per skill: unreachable for a skill measuring
    1.00 (ceiling 0.00, so a warning is arithmetically impossible however many sessions were
    cut) and easy to trip for one near the floor. Two of the seven baseline skills sit at 1.00."""
    name = "integration"
    entry = {"happy": ["h0", "h1", "h2", "h3"], "negative": ["n"]}

    fired = stream.Observation(completed=True, fired=[name], available=[name])
    cut = stream.Observation(completed=False, tool_calls=0, available=[name])
    by_prompt = {"h0": fired, "h1": fired, "h2": cut, "h3": cut}
    fallback = stream.Observation(completed=True, tool_calls=5, available=[name])

    def fake_one(prompt, fixture, config_dir, restricted):
        return by_prompt.get(prompt, fallback), ""

    monkeypatch.setattr(run, "_one", fake_one)
    result = run.measure(name, entry, reps=1, config_dir=Path("."), jobs=1)

    assert result["invoke_rate"] == 0.5
    # Both misses were cut before they could decide, so the whole miss column is unexplained.
    # Over every sample this reads 0.50 and looks like a coin flip.
    assert result["truncated"] == 1.0


def test_the_truncation_warning_measures_distortion_not_the_miss_column(monkeypatch, capsys):
    """The recorded metric and the warning divide by different things on purpose.

    A skill at 14/15 whose single miss timed out has a fully unexplained miss column —
    `truncated` 1.00, correctly — but its score moved by at most 1/15 = 0.067. Warning there
    would say "invoke_rate is reporting SESSION_TIMEOUT rather than the description" about a
    0.067 distortion, which is the always-on warning this threshold already survived once.

    Moving the recorded denominator to misses and leaving the warning on it would have
    inverted the very defect that motivated the change: unreachable at the top before, certain
    at the top after."""
    name = "integration"
    prompts = [f"h{i}" for i in range(15)]
    entry = {"happy": prompts, "negative": ["n"]}

    fired = stream.Observation(completed=True, fired=[name], available=[name])
    cut = stream.Observation(completed=False, tool_calls=0, available=[name])
    by_prompt = {p: fired for p in prompts[:14]} | {prompts[14]: cut}
    fallback = stream.Observation(completed=True, tool_calls=5, available=[name])

    def fake_one(prompt, fixture, config_dir, restricted):
        return by_prompt.get(prompt, fallback), ""

    monkeypatch.setattr(run, "_one", fake_one)
    result = run.measure(name, entry, reps=1, config_dir=Path("."), jobs=1)

    assert result["invoke_rate"] == 0.93
    assert result["truncated"] == 1.0  # the miss column really is entirely unexplained
    assert "cut short" not in capsys.readouterr().out


def test_truncated_reports_zero_when_there_was_nothing_to_miss(monkeypatch):
    """A denominator of misses is 0 exactly when every sample fired. There is no truncation to
    report then — not an undefined ratio and not a division error."""
    name = "integration"
    entry = {"happy": ["h0", "h1"], "negative": ["n0"]}

    fired = stream.Observation(completed=True, fired=[name], available=[name])

    def fake_one(prompt, fixture, config_dir, restricted):
        return fired, ""

    monkeypatch.setattr(run, "_one", fake_one)
    result = run.measure(name, entry, reps=1, config_dir=Path("."), jobs=1)

    assert result["invoke_rate"] == 1.0
    assert result["truncated"] == 0.0
    # The negative arm's mirror: every negative sample fired too, so `quiet` is 0.
    assert result["false_fire"] == 1.0
    assert result["truncated_quiet"] == 0.0


def test_measure_writes_an_entry_the_gate_accepts(monkeypatch):
    """The write side of the gate's contract, pinned model-free: measure() must stamp every
    field check() reads — the sha AND the model. The model stamp went missing once; every
    future entry would then fail the model gate ("re-measure" cannot fix what re-measuring
    reproduces), while may_write read the missing key as a model change and never ratcheted
    again. This is the seam the unit tests around check() cannot see, because their entries
    are built by hand rather than by measure()."""
    name = "integration"
    entry = {"happy": ["h0", "h1"], "negative": ["n0", "n1"]}
    fired = stream.Observation(completed=True, tool_calls=1, available=[name], fired=[name])
    quiet = stream.Observation(completed=True, tool_calls=5, available=[name])

    def fake_one(prompt, fixture, config_dir, restricted):
        return (fired if prompt in ("h0", "h1") else quiet), ""

    monkeypatch.setattr(run, "_one", fake_one)
    result = run.measure(name, entry, reps=1, config_dir=Path("."), jobs=1)

    v = scores.check(name, result, scores.description_sha(name), 0.70, N_SKILLS)
    assert v.level == "ok", v.message
    assert result["model"] == scores.MODEL  # the ratchet needs a same-model baseline


def test_truncation_warnings_fire_independently_per_metric(monkeypatch, capsys):
    """A single `if` covering only the happy arm would leave `false_fire` silently
    uninspected. Each metric must raise its own named warning, and only when its own share is
    over the line — not the other one's."""
    name = "integration"
    entry = {"happy": ["h0", "h1"], "negative": ["n0", "n1"]}
    completed_ok = stream.Observation(completed=True, tool_calls=5, available=[name])
    cut = stream.Observation(completed=False, tool_calls=1, available=[name])

    def make_fake_one(happy_obs, negative_obs):
        def fake_one(prompt, fixture, config_dir, restricted):
            return (negative_obs if prompt in ("n0", "n1") else happy_obs), ""

        return fake_one

    # Only invoke_rate is compromised: happy cut early, negative completes cleanly.
    monkeypatch.setattr(run, "_one", make_fake_one(cut, completed_ok))
    run.measure(name, entry, reps=1, config_dir=Path("."), jobs=1)
    out = capsys.readouterr().out
    assert "invoke_rate is" in out
    assert "false_fire is" not in out

    # Only false_fire is compromised: happy completes cleanly, negative cut early.
    monkeypatch.setattr(run, "_one", make_fake_one(completed_ok, cut))
    run.measure(name, entry, reps=1, config_dir=Path("."), jobs=1)
    out = capsys.readouterr().out
    assert "false_fire is" in out
    assert "invoke_rate is" not in out

    # Both are compromised: both arms cut early.
    monkeypatch.setattr(run, "_one", make_fake_one(cut, cut))
    run.measure(name, entry, reps=1, config_dir=Path("."), jobs=1)
    out = capsys.readouterr().out
    assert "invoke_rate is" in out
    assert "false_fire is" in out


def test_a_miss_records_which_skill_fired_instead(monkeypatch):
    """A bare `invoke_rate` says a description is losing without saying what to. The whole
    point of measuring seven descriptions against each other is that a miss usually means a
    neighbour won, and the winner's name is already in `obs.fired` — it was being tested with
    `name in obs.fired` and thrown away. A miss where a sibling fired must read as a loss to
    that sibling, not as an undifferentiated zero."""
    name = "integration"
    entry = {"happy": ["h0", "h1"], "negative": ["n0"]}
    lost = stream.Observation(
        available=[name], completed=True, tool_calls=5, fired=["playwright-scaffold"]
    )
    won = stream.Observation(available=[name], completed=True, tool_calls=5, fired=[name])
    quiet = stream.Observation(available=[name], completed=True, tool_calls=5)

    def fake_one(prompt, fixture, config_dir, restricted):
        if prompt == "n0":
            return quiet, ""
        # h0 loses to a neighbour twice (reps=2); h1 fires correctly.
        return (lost if prompt == "h0" else won), ""

    monkeypatch.setattr(run, "_one", fake_one)
    result = run.measure(name, entry, reps=2, config_dir=Path("."), jobs=1)

    assert result["invoke_rate"] == 0.5
    assert result["lost_to"] == {"playwright-scaffold": 2}
    # A skill that fired is not a loss, and the negative arm is a different question entirely.
    assert name not in result["lost_to"]


def test_lost_to_stays_out_of_the_gate():
    """Diagnostic, not gated. If `check` ever started reading it, a description that began
    losing to a neighbour would fail the suite on a number with no threshold behind it — and
    the metric would stop being safe to record honestly."""
    entry = {**OK, "lost_to": {"playwright-scaffold": 12}}
    assert scores.check("integration", entry, "x", EXPECT, N_SKILLS).level == "ok"


def test_a_rate_limit_stops_the_plan_instead_of_finishing_it(monkeypatch):
    """The window is exhausted, so every queued session would be refused the same way. The
    check used to live in the aggregation loop, which ran only after all 35 futures had
    resolved — hitting the cap on session 1 still spent the other 34 producing nothing.

    Every session but the first blocks until the assertion is done, which is what a real ~58s
    session does to the queue and what makes the count deterministic: with jobs=1 exactly one
    worker exists, so once it is parked in a fake session it cannot drain the plan behind the
    runner's back. An instant fake cannot test this at all — the worker finishes all 30 before
    the main thread is scheduled to look at the first result."""
    name = "integration"
    prompts = [f"h{i}" for i in range(10)]
    entry = {"happy": prompts, "negative": [f"n{i}" for i in range(10)]}
    calls = []
    release = threading.Event()
    limited = stream.Observation(available=[name], completed=True, rate_limited=True)
    healthy = stream.Observation(available=[name], completed=True, tool_calls=5, fired=[name])

    def fake_one(prompt, fixture, config_dir, restricted):
        calls.append(prompt)
        if prompt == "h0":
            return limited, ""
        release.wait(timeout=30)  # the timeout is a hang guard; the finally below releases it
        return healthy, ""

    monkeypatch.setattr(run, "_one", fake_one)
    try:
        with pytest.raises(run.RateLimited):
            run.measure(name, entry, reps=1, config_dir=Path("."), jobs=1)
        # 10 happy + 10 negative + 10 restricted = 30 planned. The first is rate-limited and
        # at most one more can already have been picked up, so anything above 2 means the
        # remaining sessions were spent against an exhausted window.
        assert len(calls) <= 2, calls
        assert calls[0] == "h0"
    finally:
        release.set()


def test_the_suite_cannot_spawn_a_real_session():
    """The guard itself. `no_real_sessions` is autouse, so this asserts the thing every other
    test in the file silently depends on: reaching `run_session` raises instead of spending a
    session against the rate limit."""
    with pytest.raises(AssertionError, match="model-free"):
        run.run_session("p", None, Path("."), Path("."))


def test_session_env_strips_provider_variables(monkeypatch):
    """Isolation is not only the config dir — one exported ANTHROPIC_BASE_URL reroutes
    every session through a proxy and the committed baseline becomes a fact about one
    developer's shell, the exact contamination isolated_config_dir() exists to prevent."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-leak")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://proxy.example")
    monkeypatch.setenv("CLAUDE_CODE_EXTRA", "x")
    env = run.session_env(Path("cfg"))
    assert "ANTHROPIC_API_KEY" not in env
    assert "ANTHROPIC_BASE_URL" not in env
    assert "CLAUDE_CODE_EXTRA" not in env
    assert env["CLAUDE_CONFIG_DIR"] == str(Path("cfg"))
    assert "PATH" in env  # system variables survive, or the CLI cannot even start


def test_reps_zero_is_rejected(monkeypatch):
    """--reps 0 built a plan of 5 restricted sessions, spent them, then crashed on a
    ZeroDivisionError in the rate arithmetic — real budget for no number."""
    monkeypatch.setattr(sys, "argv", ["evals.run", "--reps", "0", "--dry-run", "--all"])
    with pytest.raises(SystemExit) as e:
        run.main()
    assert e.value.code == 2  # argparse error, before any session


MANIFESTS = [".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"]


@pytest.mark.parametrize("manifest", MANIFESTS)
def test_the_eval_harness_is_never_distributed_to_consumers(manifest: str):
    """`evals/` is dev tooling — cases, a baseline, and a runner that spends this developer's
    rate-limit budget. This plugin installs from a GitHub source, so anything a manifest names
    ships to every consumer. It was the one Global Constraint in the plan with nothing
    enforcing it, which is the kind that holds right up until someone adds a `files` key."""
    text = (REPO / manifest).read_text(encoding="utf-8")
    assert "evals" not in text, f"{manifest} references evals/ — it must not ship to consumers"

    # The raw scan above is the real assertion and it is total. This walks the parsed shape
    # as well so the test keeps meaning something if a manifest ever grows nested component
    # paths: today neither file has a path list at all (plugin.json is four metadata keys,
    # marketplace.json adds a `source` pointing at the repo), and both rely on components
    # being auto-discovered from their default locations — which is precisely why `evals/`
    # is safe today and why nothing was stopping someone from listing it tomorrow.
    def strings(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from strings(value)
        elif isinstance(node, list):
            for item in node:
                yield from strings(item)
        elif isinstance(node, str):
            yield node

    named = [s for s in strings(json.loads(text)) if "evals" in s]
    assert not named, f"{manifest} names {named} — the eval harness must not ship"


def test_a_session_that_never_reached_init_is_unusable_not_a_miss(monkeypatch):
    """An empty Observation — a dead spawn, or a process that never produced a stream — has
    completed=False and tool_calls=0, so scoring it reads as a miss *and* as truncated. The
    old guard only asked whether *any* session in the run saw the plugin, so 14 of 15 dead
    sessions still produced a published number. The judgement has to be per session, and it
    has to abort rather than warn: there is no rate to record."""
    name = "integration"
    entry = {"happy": ["h0", "h1"], "negative": ["n0"]}
    healthy = stream.Observation(available=[name], completed=True, tool_calls=5)
    dead = stream.Observation()  # what observe("") returns

    def fake_one(prompt, fixture, config_dir, restricted):
        return (dead, "claude: command not found\n") if prompt == "h1" else (healthy, "")

    monkeypatch.setattr(run, "_one", fake_one)
    with pytest.raises(SystemExit) as e:
        run.measure(name, entry, reps=1, config_dir=Path("."), jobs=1)
    assert "never reached the init event" in str(e.value)
    # The cause is the only thing that makes the abort actionable, and it lives in stderr.
    # Capturing stderr and never reading it is how the reason for a dead session got lost.
    assert "command not found" in str(e.value)


def test_stderr_reaches_the_failure_message_without_reaching_observe(monkeypatch):
    """`stream.observe` answers questions about the transcript; stderr is a fact about the
    process. The tail belongs in the runner's error path only — if it ever became an
    Observation field, the parser would be reading something it cannot see."""
    assert "stderr" not in stream.Observation().__dict__
    assert run._tail("a\nb\nc\nd\ne\nf\ng\n", lines=2).splitlines()[-1].strip() == "g"
    assert run._tail("   \n  \n") == ""


OK = {
    "description_sha": "x",
    "model": scores.MODEL,
    "invoke_rate": 0.93,
    "invoke_hits": 14,
    "invoke_n": 15,
    "false_fire": 0.0,
    "false_hits": 0,
    "false_n": 15,
}


def _entry(**overrides) -> dict:
    """A gate-passing entry with per-test overrides — the check() fixtures grew one key at a
    time (model, the count pairs) and inline dicts made every addition a sweep."""
    return {**OK, **overrides}


# The declared expectation and family size `check` is exercised with. It takes both explicitly
# rather than reading cases.yaml, so a unit test can vary them without a fixture. 0.80 against
# OK's 14/15 clears the significance bar; 7 is the shipped skill-family size.
EXPECT = 0.80
N_SKILLS = 7


def test_alpha_single_is_a_family_bound_split_across_the_confirmation_re_measure():
    """Sidak over the 7-skill family gives a per-skill alpha; the square root splits it across
    the two consecutive trips a fail requires, so two independent trips at sqrt(a) compound
    back to the family a. Both fixed points were recomputed this session."""
    assert scores.alpha_single(7) == pytest.approx(0.08544, abs=1e-5)
    # Squaring undoes the sqrt, landing on the per-skill Sidak alpha the family bound implies.
    assert scores.alpha_single(7) ** 2 == pytest.approx(0.00730, abs=1e-5)


def test_binom_cdf_is_the_lower_tail():
    assert scores.binom_cdf(15, 15, 0.8) == pytest.approx(1.0)
    assert scores.binom_cdf(0, 15, 0.5) == pytest.approx(0.5**15)
    cdfs = [scores.binom_cdf(k, 15, 0.6) for k in range(16)]
    assert cdfs == sorted(cdfs), "binom_cdf must be non-decreasing in k"


@pytest.mark.parametrize(
    "k_base,trips_at_or_below,first_clear",
    [
        (10, 6, 7),
        (9, 5, 6),
        (8, 4, 5),
        # The Jeffreys boundary and the regression guard for the retracted claim: a perfect
        # baseline tolerates 14/15 and only trips at 13 — the recorded rate is itself noisy,
        # and treating 1.00 as exact would make any single miss infinitely significant.
        (15, 13, 14),
        (2, 0, 1),
    ],
)
def test_ratchet_trip_table(k_base: int, trips_at_or_below: int, first_clear: int):
    """Every boundary recomputed this session against the shipped binomial at n=15 and
    alpha=alpha_single(7). binom_cdf is monotone in k, so a trip at the boundary implies a
    trip at everything below it; the row asserts both the last trip and the first clear."""
    alpha = scores.alpha_single(7)
    for k_new in range(trips_at_or_below + 1):
        assert scores.ratchet_trips(k_new, 15, k_base, 15, alpha), (k_base, k_new)
    assert not scores.ratchet_trips(first_clear, 15, k_base, 15, alpha), (k_base, first_clear)


def test_a_rise_never_trips_the_low_tail_ratchet():
    """The test is one-sided: a measurement at or above the reference is never a regression."""
    alpha = scores.alpha_single(7)
    assert not scores.ratchet_trips(12, 15, 4, 15, alpha)
    assert not scores.ratchet_trips(15, 15, 10, 15, alpha)


def test_the_gate_ignores_per_skill_provenance_keys():
    """`measured_at`/`reps` moved onto each entry so an incremental run cannot claim its own
    sample size for six skills it never measured. The gate must stay indifferent to them —
    if `check` ever grew strict about the key set, moving provenance would break it."""
    assert scores.check(
        "integration", {**OK, "measured_at": "2026-07-19", "reps": 3}, "x", EXPECT, N_SKILLS
    ).level == ("ok")


def test_unmeasured_skill_warns_rather_than_failing():
    """Failing here would paint `uv run pytest` red from the day the harness lands, and a
    suite that is red by default stops being read as a signal at all. The same holds for
    every newly added skill."""
    assert scores.check("integration", None, "x", EXPECT, N_SKILLS).level == "warn"


def test_the_gate_surfaces_a_warning_rather_than_passing_in_silence():
    """A warn that prints nothing is a pass, and an unmeasured skill would look measured."""
    with pytest.warns(UserWarning, match="not measured"):
        gate("integration", None, "x", EXPECT, N_SKILLS)


def test_a_healthy_measurement_passes():
    assert scores.check("integration", OK, "x", EXPECT, N_SKILLS).level == "ok"


def test_a_stale_measurement_fails():
    """Without this the harness is decorative: edit the description, keep the old green
    number, merge. The score would no longer describe the skill it is attached to."""
    v = scores.check("integration", OK, "different-sha", EXPECT, N_SKILLS)
    assert v.level == "fail"
    assert "re-measure" in v.message


def test_an_all_zero_baseline_always_fails():
    """The one data-independent floor. A committed 0/15 must never be green: if the true rate
    is merely low, a re-measure will produce a nonzero and this failure forces exactly that
    re-measure. It bites with the declaration present and without it."""
    zero = {**OK, "invoke_rate": 0.0, "invoke_hits": 0, "invoke_n": 15}
    assert scores.check("integration", zero, "x", EXPECT, N_SKILLS).level == "fail"
    assert scores.check("integration", zero, "x", None, N_SKILLS).level == "fail"


def test_an_undeclared_skill_fails_rather_than_defaulting():
    """The gate refuses to operate on a skill with no `expect_invoke` rather than substituting
    a global constant — the declaration is the forcing function that replaced the floor."""
    v = scores.check("integration", OK, "x", None, N_SKILLS)
    assert v.level == "fail"
    assert "expect_invoke" in v.message


def test_a_measurement_far_below_its_declaration_warns_not_fails():
    """n=15 cannot support hard-failing an aspiration, and a suite red by default stops being
    read — so the declaration gap is a warn (information), not a fail. The ratchet is the
    enforcement. 4/15 against 0.70 is far enough below to warn; 8/15 clears it."""
    low = {**OK, "invoke_rate": 0.27, "invoke_hits": 4, "invoke_n": 15}
    assert scores.check("integration", low, "x", 0.70, N_SKILLS).level == "warn"
    ok = {**OK, "invoke_rate": 0.53, "invoke_hits": 8, "invoke_n": 15}
    assert scores.check("integration", ok, "x", 0.70, N_SKILLS).level == "ok"


@pytest.mark.parametrize("name", SKILLS)
def test_a_programmatic_reach_claim_names_a_real_caller(name: str):
    """`reached_programmatically` now grounds a low `expect_invoke` (harness-authoring's 0.10)
    rather than a floor exemption: the autonomous rate is only a liveness check because the
    primary path is another skill invoking it. If cases.yaml claims that path, some other
    shipped skill has to actually invoke it — otherwise the claim is stale."""
    if not CASES["skills"][name].get("reached_programmatically"):
        return
    callers = [
        p.parent.name
        for p in REPO.glob("skills/*/SKILL.md")
        if p.parent.name != name and f"Skill: {name}" in p.read_text(encoding="utf-8")
    ]
    assert callers, (
        f"{name}: cases.yaml declares reached_programmatically, but no shipped skill "
        f"invokes it. Either the claim is stale or the caller was removed."
    )


def test_the_false_fire_ceiling_fails():
    over = _entry(false_hits=4, false_n=15, false_fire=0.27)
    v = scores.check("integration", over, "x", EXPECT, N_SKILLS)
    assert v.level == "fail"
    assert "false_fire" in v.message


def test_false_fire_ceiling_reads_the_raw_counts_not_the_rounded_rate():
    """The derived two-decimal field can drift from the counts under a hand edit — the very
    threat the lowered_from check documents — and at a reps-raised n a true rate in
    (0.20, 0.205] rounds down to a passing 0.20."""
    lying = _entry(false_hits=5, false_n=15, false_fire=0.0)  # derived field says clean
    v = scores.check("integration", lying, "x", EXPECT, N_SKILLS)
    assert v.level == "fail"
    assert "false_fire" in v.message


def test_check_order_fails_an_undeclared_skill_even_when_unmeasured():
    """Spec §6: an undeclared skill makes the gate refuse to judge and FAIL — measured or
    not. Returning the not-measured warn first quietly bypassed the forcing function."""
    v = scores.check("ghost", None, "whatever", None, n_skills=N_SKILLS)
    assert v.level == "fail"
    assert "expect_invoke" in v.message


def test_check_fails_a_missing_count_key_with_a_verdict_not_a_keyerror():
    """The module's stated threat model is a hand-edited scores.json — a bare KeyError names
    neither the skill nor the fix."""
    trimmed = {"description_sha": "x", "invoke_rate": 0.5}
    v = scores.check("integration", trimmed, "x", EXPECT, N_SKILLS)
    assert v.level == "fail"
    assert "invoke_hits" in v.message


def test_a_model_mismatch_fails_like_a_stale_sha():
    """The baseline is a fact about one model (0/4 vs 4/4 on the same case, measured). A
    mismatched fingerprint is as stale as an old sha and forces the same re-measure."""
    v = scores.check("integration", _entry(model="claude-sonnet-5"), "x", EXPECT, N_SKILLS)
    assert v.level == "fail"
    assert "model" in v.message


def test_may_write_skips_the_ratchet_across_a_model_change():
    """Ratcheting a new model's k/n against an old model's attributes model drift to the
    description. MODEL is a reviewed code constant, so crossing it re-baselines instead —
    not an escape hatch."""
    new = _entry(invoke_hits=0, invoke_n=15, invoke_rate=0.0)
    old = _entry(invoke_hits=15, invoke_n=15, invoke_rate=1.0, model="claude-sonnet-5")
    v = scores.may_write("integration", new, old, accepted=False, n_skills=N_SKILLS)
    assert v.level == "ok"


def test_an_accepted_drop_needs_a_recorded_reason():
    entry = {**OK, "lowered_from": 0.95}
    assert scores.check("integration", entry, "x", EXPECT, N_SKILLS).level == "fail"
    entry["lowered_reason"] = "traded for a lower false_fire"
    assert scores.check("integration", entry, "x", EXPECT, N_SKILLS).level == "ok"


# Base 10/15 (invoke_rate 0.67). By the trip table this trips at k_new <= 6 and clears at 7.
RATCHET_OLD = {"invoke_rate": 0.67, "invoke_hits": 10, "invoke_n": 15, "false_fire": 0.0}
RATCHET_TRIP = {"invoke_rate": 0.40, "invoke_hits": 6, "invoke_n": 15, "false_fire": 0.0}


def test_a_first_drop_asks_for_confirmation_rather_than_failing():
    """A single reading cannot separate a real regression from binomial noise at n=15, so the
    first trip asks for a re-measure rather than failing. alpha_single already carries the
    sqrt that makes the two consecutive trips a fail requires compound to the family bound."""
    assert (
        scores.may_write("integration", RATCHET_TRIP, RATCHET_OLD, accepted=False, n_skills=7).level
        == "confirm"
    )


def test_a_confirmed_drop_fails_and_acceptance_overrides_it():
    assert (
        scores.may_write(
            "integration", RATCHET_TRIP, RATCHET_OLD, accepted=False, confirmed=True, n_skills=7
        ).level
        == "fail"
    )
    assert (
        scores.may_write("integration", RATCHET_TRIP, RATCHET_OLD, accepted=True, n_skills=7).level
        == "ok"
    )


def test_the_ratchet_tolerates_noise_and_welcomes_a_rise():
    """A drop that does not clear the significance bar is written without a fuss (7/15 from a
    10/15 base clears the trip), and a rise is never a regression."""
    within = {"invoke_rate": 0.47, "invoke_hits": 7, "invoke_n": 15, "false_fire": 0.0}
    higher = {"invoke_rate": 1.0, "invoke_hits": 15, "invoke_n": 15, "false_fire": 0.0}
    assert scores.may_write("integration", within, RATCHET_OLD, False, n_skills=7).level == "ok"
    assert scores.may_write("integration", higher, RATCHET_OLD, False, n_skills=7).level == "ok"


def gate(name: str, entry: dict | None, sha: str, expect: float | None, n_skills: int) -> None:
    """Apply a verdict: fail loudly, warn visibly, pass quietly."""
    v = scores.check(name, entry, sha, expect, n_skills)
    if v.level == "fail":
        pytest.fail(v.message)
    if v.level == "warn":
        warnings.warn(v.message, stacklevel=2)


def test_every_skill_declares_its_expectation():
    """The declarations are the gate's forcing function — a skill with no `expect_invoke`
    fails the gate rather than falling back to a global constant, and `expect_why` is the
    design-intent prose that must accompany it."""
    for name in SKILLS:
        entry = CASES["skills"][name]
        expect = entry.get("expect_invoke")
        assert isinstance(expect, int | float) and 0 < expect <= 1, f"{name}: expect_invoke"
        assert isinstance(entry.get("expect_why"), str) and entry["expect_why"].strip(), (
            f"{name}: expect_why"
        )


def test_the_committed_baseline_passes_the_gate():
    """The gate itself, applied to the file that is actually committed. Fail is the only hard
    state; warns surface through pytest's warning summary (integration and flow warn today —
    both measured significantly below their declared expectation). The warn set is
    deliberately NOT pinned: a ratchet-approved dip adds a warn, an improvement removes one,
    an --accept'ed drop still warns — and a suite that turns red on any of those teaches
    people to edit the test instead of reading the warning. Warn is information; the ratchet
    is the enforcement (spec §6)."""
    baseline = scores.load()
    for name in SKILLS:
        gate(
            name,
            baseline.get("skills", {}).get(name),
            scores.description_sha(name),
            CASES["skills"][name].get("expect_invoke"),
            len(SKILLS),
        )


# ── fixture capture ──────────────────────────────────────────────────────────────────────
# The committed fixtures were re-captured under the isolated config dir, so their `init` event
# lists `harness-tier@inline` as its only plugin — earlier captures carried the whole machine
# inventory (18 plugins with absolute paths, 146 slash commands, the home directory), half of
# each file, which a reduction cannot trim without rewriting a captured event into fiction. The
# account-level claude.ai MCP connectors survive by name (config isolation is scoped to plugins,
# not the account); no tokens ride along. The re-capture costs real sessions, so it rides along
# with a measurement run instead of being its own errand.


def test_reduce_capture_keeps_only_the_events_observe_reads():
    """`stream.observe` reads four kinds. The rest — hook_*, thinking_tokens, task_*, user —
    were 83% of the original 332KB and are never parsed, so they are dropped whole rather than
    summarised."""
    kept_init = '{"type":"system","subtype":"init","skills":["harness-tier:integration"]}'
    kept_assistant = '{"type":"assistant","message":{"content":[]}}'
    kept_rate = '{"type":"rate_limit_event","rate_limit_info":{"status":"allowed"}}'
    kept_result = '{"type":"result","subtype":"success","num_turns":2}'
    dropped = [
        '{"type":"hook_started","name":"x"}',
        '{"type":"user","message":{}}',
        '{"type":"thinking_tokens","n":11}',
        '{"type":"task_progress"}',
    ]
    text = "\n".join(
        [
            kept_init,
            dropped[0],
            kept_assistant,
            dropped[1],
            kept_rate,
            dropped[2],
            kept_result,
            dropped[3],
        ]
    )
    assert run.reduce_capture(text).splitlines() == [
        kept_init,
        kept_assistant,
        kept_rate,
        kept_result,
    ]


def test_reduce_capture_does_not_rewrite_a_surviving_event():
    """The fixtures are worth having because they are real CLI bytes. Re-serialising would
    normalise key order, spacing and escapes — turning a capture into a rendering of one, and
    quietly ending its ability to catch a parser assumption."""
    odd_spacing = '{"type":"result","subtype":"success",  "num_turns":2,"who":"caf\u00e9"}'
    assert run.reduce_capture(odd_spacing).splitlines() == [odd_spacing]


def test_reduce_capture_drops_a_line_that_is_not_json():
    """A killed process ends mid-line. `stream.observe` tolerates that; a fixture should not
    carry it, because the truncation test appends its own."""
    good = '{"type":"result","subtype":"success"}'
    assert run.reduce_capture(f'{{"type":"assis\n{good}').splitlines() == [good]


def test_fixture_role_names_the_committed_fixture_a_capture_could_replace():
    invoked = stream.Observation(
        fired=["integration"],
        available=["integration"],
        turns_exhausted=True,
        completed=True,
        tool_calls=4,
    )
    assert run.fixture_role(invoked, "integration") == "stream-invoked"
    quiet = stream.Observation(
        fired=[],
        available=["integration"],
        completed=True,
        tool_calls=3,
    )
    assert run.fixture_role(quiet, "integration") == "stream-quiet"


def test_fixture_role_refuses_a_session_that_would_teach_the_parser_nothing():
    """Each rejection maps to an assertion the committed fixtures already satisfy — a candidate
    that fails one would replace a working fixture with a broken one."""
    errored = stream.Observation(
        fired=["x"],
        available=["x"],
        turns_exhausted=True,
        errored=True,
        tool_calls=4,
    )
    assert run.fixture_role(errored, "x") is None, "an outright failure is not a clean observation"
    no_calls = stream.Observation(fired=[], available=["x"], completed=True, tool_calls=0)
    assert run.fixture_role(no_calls, "x") is None, (
        "test_observe_counts_every_tool_call_not_just_skill asserts tool_calls > 0"
    )
    never_loaded = stream.Observation(fired=[], available=[], completed=True, tool_calls=3)
    assert run.fixture_role(never_loaded, "x") is None, (
        "empty `available` means the plugin never loaded"
    )


def test_capture_writes_beside_the_committed_fixture_never_over_it(tmp_path, monkeypatch):
    """`fixture_role` checks the conditions it knows about; the committed fixtures satisfy
    seven assertions. A candidate that clears the former has not been checked against the
    latter, so replacing is a human step and this only ever writes `.new`."""
    monkeypatch.setattr(run, "CAPTURE_FOR", "x")
    committed = tmp_path / "stream-quiet.jsonl"
    committed.write_text("ORIGINAL", encoding="utf-8")
    obs = stream.Observation(fired=[], available=["x"], completed=True, tool_calls=3)

    run.maybe_capture(obs, '{"type":"result","subtype":"success"}\n{"type":"user"}', tmp_path)

    assert committed.read_text(encoding="utf-8") == "ORIGINAL"
    written = (tmp_path / "stream-quiet.jsonl.new").read_text(encoding="utf-8")
    assert written.strip() == '{"type":"result","subtype":"success"}'


def test_capture_is_off_unless_asked_and_keeps_the_first_of_each_role(tmp_path, monkeypatch):
    """Off by default because a normal measurement run must not touch the fixtures. First-wins
    because later sessions are not better candidates, and rewriting on every match would make
    the file depend on which of 35 sessions happened to finish last."""
    obs = stream.Observation(fired=[], available=["x"], completed=True, tool_calls=3)
    dest = tmp_path / "stream-quiet.jsonl.new"

    monkeypatch.setattr(run, "CAPTURE_FOR", None)
    run.maybe_capture(obs, '{"type":"result","subtype":"success"}', tmp_path)
    assert not dest.exists()

    monkeypatch.setattr(run, "CAPTURE_FOR", "x")
    run.maybe_capture(obs, '{"type":"result","subtype":"success"}', tmp_path)
    run.maybe_capture(obs, '{"type":"result","subtype":"LATER"}', tmp_path)
    assert "LATER" not in dest.read_text(encoding="utf-8")


def test_fixture_role_keeps_the_two_fixtures_covering_different_endings():
    """`stream-invoked` is a turn cap, `stream-quiet` is a clean `success` — that difference is
    what `test_observe_tells_an_outright_failure_from_a_turn_cap` reads. A capped session that
    happened not to fire satisfies every other quiet condition, so without this the pair could
    drift into two turn caps and the success path would stop being covered at all."""
    capped_but_quiet = stream.Observation(
        fired=[], available=["x"], completed=True, turns_exhausted=True, tool_calls=5
    )
    assert run.fixture_role(capped_but_quiet, "x") is None


def test_fixture_role_requires_the_measured_skill_to_be_the_one_that_fired():
    """`test_observe_sees_a_skill_that_fired` asserts `"integration" in obs.fired`, so a
    candidate taken from another skill's session would replace a working fixture with one the
    suite rejects.

    That is not hypothetical: the incremental default mode walks skills alphabetically, so
    `doc-sync` runs first and first-wins would hand it `stream-invoked`. The role has to know
    which skill is being measured — `measure` does, so it is not new information."""
    other = stream.Observation(
        fired=["doc-sync"],
        available=["doc-sync"],
        turns_exhausted=True,
        completed=True,
        tool_calls=4,
    )
    assert run.fixture_role(other, "integration") is None
    target = stream.Observation(
        fired=["integration"],
        available=["integration"],
        turns_exhausted=True,
        completed=True,
        tool_calls=4,
    )
    assert run.fixture_role(target, "integration") == "stream-invoked"
    # The quiet fixture is skill-bound through `available`, which lists every plugin skill —
    # so it only has to confirm the measured one was on offer.
    quiet = stream.Observation(
        fired=[],
        available=["doc-sync", "integration"],
        completed=True,
        tool_calls=3,
    )
    assert run.fixture_role(quiet, "integration") == "stream-quiet"
    assert run.fixture_role(quiet, "performance") is None


def test_capture_preserves_the_trailing_newline_the_fixtures_depend_on():
    """`test_observe_reports_a_rate_limited_session` and the turn-cap test both append an event
    to the file's text. Without a trailing newline the appended JSON joins the last `result`
    line and both are dropped as unparseable — so the newline is load-bearing, and asserting on
    a `.strip()`ed value (as the write test does, deliberately, for content) cannot see it."""
    assert run.reduce_capture('{"type":"result","subtype":"success"}').endswith("}")
    for name in ("stream-invoked.jsonl", "stream-quiet.jsonl"):
        assert (FIXTURES / name).read_text(encoding="utf-8").endswith("\n"), name


def test_capture_writes_a_file_ending_in_a_newline(tmp_path, monkeypatch):
    monkeypatch.setattr(run, "CAPTURE_FOR", "x")
    obs = stream.Observation(fired=[], available=["x"], completed=True, tool_calls=3)
    run.maybe_capture(obs, '{"type":"result","subtype":"success"}', tmp_path)
    assert (tmp_path / "stream-quiet.jsonl.new").read_text(encoding="utf-8").endswith("\n")


def test_git_tracks_exactly_the_two_committed_fixtures():
    """`.jsonl.new` candidates are deliberately not gitignored so they surface in `git status`
    for a human to inspect — which means one blanket `git add -A` commits an unverified second
    copy that no test would otherwise look at (nothing globs this directory).

    Tracked files, not directory contents: an untracked candidate sitting there mid-review is
    the expected state and must not turn the suite red — that pressure pushes a developer to
    delete the candidate instead of inspecting it. What must be impossible is *committing* one,
    and that is exactly what `git ls-files` sees."""
    tracked = subprocess.run(
        ["git", "ls-files", "evals/fixtures"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.split()
    assert sorted(tracked) == [
        "evals/fixtures/stream-invoked.jsonl",
        "evals/fixtures/stream-quiet.jsonl",
    ], (
        "unexpected tracked file under evals/fixtures — a captured `.jsonl.new` candidate is "
        "meant to be reviewed and renamed over the committed fixture, never committed beside it"
    )
