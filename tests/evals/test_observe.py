import json
from pathlib import Path

import pytest

import evals.run as run
import evals.stream as stream
from tests.evals._helpers import FIXTURES


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
    abort the same way until the window reset. Only "rejected" (the request failed)
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
    works if it counts every tool call the session made — Bash, Read, whatever — not only the
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
