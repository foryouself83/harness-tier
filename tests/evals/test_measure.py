import sys
import threading
from pathlib import Path

import pytest

import evals.run as run
import evals.scores as scores
import evals.stream as stream
from tests.evals._helpers import EXPECT, N_SKILLS, OK


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
    the check must not live in the aggregation loop, which runs only after all 35 futures have
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
