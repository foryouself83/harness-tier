import json
from pathlib import Path

import evals.run as run
import evals.stream as stream
from tests.evals._helpers import FIXTURES


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
    assert result["truncated"] == 1.0  # the miss column is entirely unexplained
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
