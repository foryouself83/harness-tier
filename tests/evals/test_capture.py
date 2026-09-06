import subprocess

import evals.run as run
import evals.stream as stream
from tests.evals._helpers import FIXTURES, REPO

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
