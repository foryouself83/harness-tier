import json
import sys
from pathlib import Path

import pytest

import evals.outcome as outcome
import evals.run as run
import evals.scores as scores
import scripts.skill_sandbox as sandbox

_DOC_SYNC = sandbox.BY_NAME["doc-sync-drift"]


def test_outcome_check_warns_when_unmeasured():
    assert outcome.outcome_check("doc-sync", None, "abc", _DOC_SYNC).level == "warn"


def test_outcome_check_fails_on_a_stale_fingerprint():
    entry = {"outcome_hits": 3, "outcome_n": 3, "outcome_sha": "old", "model": scores.MODEL}
    v = outcome.outcome_check("doc-sync", entry, "new", _DOC_SYNC)
    assert v.level == "fail"
    assert "re-measure" in v.message


def test_stale_fingerprint_names_the_inputs_that_could_have_moved():
    # "skill body, fixture or golden" are three nouns nobody can act on. A copied gate script
    # is an input to a skill the editor may not have been thinking about at all — the message
    # has to name the files, or the only way to find out is to run the measurement.
    s = sandbox.BY_NAME["wiki-init-migration"]
    entry = {"outcome_hits": 3, "outcome_n": 3, "outcome_sha": "old", "model": scores.MODEL}
    v = outcome.outcome_check("wiki-init", entry, "new", s)
    assert v.level == "fail"
    # `uv run`, because the command is meant to be pasted and evals imports PyYAML.
    assert "uv run python -m evals.outcome --skill wiki-init" in v.message
    assert "skills/wiki-init/SKILL.md" in v.message
    # The scenario is named by its file. prompt, files, dirs, git and the golden feed the
    # fingerprint too and all live there, so a bare scenario name would leave five inputs
    # under a label that claims to list them.
    assert "scripts/skill_sandbox.py" in v.message
    assert s.name in v.message
    for src in s.copy_from_repo.values():
        assert src in v.message, src


def test_stale_verdict_survives_a_repo_that_does_not_prefix_the_module(monkeypatch):
    # REPO is resolved and a module's __file__ is not, so a checkout reached through a symlink,
    # a junction or a subst drive makes the two disagree textually. The branch that would raise
    # is the one whose whole job is to say "re-measure", so a Verdict has to come back either
    # way — the same reason _copied_file_sha refuses to raise.
    s = sandbox.BY_NAME["wiki-init-migration"]
    entry = {"outcome_hits": 3, "outcome_n": 3, "outcome_sha": "old", "model": scores.MODEL}
    monkeypatch.setattr(outcome, "REPO", Path(__file__).resolve().parent.parent / "no-such-root")
    v = outcome.outcome_check("wiki-init", entry, "new", s)
    assert v.level == "fail"
    assert "re-measure" in v.message


def test_outcome_check_fails_on_a_model_mismatch():
    entry = {"outcome_hits": 3, "outcome_n": 3, "outcome_sha": "s", "model": "claude-sonnet-5"}
    assert outcome.outcome_check("doc-sync", entry, "s", _DOC_SYNC).level == "fail"


def test_outcome_check_fails_an_all_zero_baseline():
    entry = {"outcome_hits": 0, "outcome_n": 3, "outcome_sha": "s", "model": scores.MODEL}
    assert outcome.outcome_check("doc-sync", entry, "s", _DOC_SYNC).level == "fail"


def test_outcome_check_passes_a_fresh_nonzero_entry():
    entry = {"outcome_hits": 3, "outcome_n": 3, "outcome_sha": "s", "model": scores.MODEL}
    assert outcome.outcome_check("doc-sync", entry, "s", _DOC_SYNC).level == "ok"


def _fake_doc_sync_session(writes_9090: bool, fires: bool):
    """Stands in for run._claude_stream: edits the built fixture like a doc-sync run would,
    then returns a stream carrying an init event (so obs.available is populated) and,
    optionally, a doc-sync Skill firing (for the fired diagnostic)."""

    def fake(prompt, fixture, workdir, config_dir, **kw):
        port = "9090" if writes_9090 else "8080"
        (workdir / "README.md").write_text(f"port {port}\n", encoding="utf-8")
        (workdir / "docs/api.md").write_text(f"http://localhost:{port}\n", encoding="utf-8")
        # app/server.py already ships 9090 from sandbox.build()
        events = [json.dumps({"subtype": "init", "skills": ["harness-tier:doc-sync"]})]
        if fires:
            events.append(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_use",
                                    "name": "Skill",
                                    "input": {"skill": "harness-tier:doc-sync"},
                                }
                            ]
                        },
                    }
                )
            )
        events.append(json.dumps({"type": "result", "subtype": "success", "is_error": False}))
        return "\n".join(events), ""

    return fake


def test_run_outcome_scores_the_end_state_and_records_fired(monkeypatch):
    monkeypatch.setattr(run, "_claude_stream", _fake_doc_sync_session(writes_9090=True, fires=True))
    s = sandbox.BY_NAME["doc-sync-drift"]
    result = outcome.run_outcome("doc-sync", s, reps=2, config_dir=Path("."))
    assert result["outcome_hits"] == 2
    assert result["outcome_pass_rate"] == 1.0
    assert result["fired_rate"] == 1.0
    assert result["model"] == scores.MODEL
    assert result["outcome_sha"] == outcome.outcome_sha("doc-sync", s)


def test_run_outcome_records_a_miss_when_the_end_state_is_wrong(monkeypatch):
    monkeypatch.setattr(
        run, "_claude_stream", _fake_doc_sync_session(writes_9090=False, fires=True)
    )
    s = sandbox.BY_NAME["doc-sync-drift"]
    result = outcome.run_outcome("doc-sync", s, reps=2, config_dir=Path("."))
    assert result["outcome_hits"] == 0
    assert result["outcome_pass_rate"] == 0.0


def test_run_outcome_aborts_on_an_errored_session(monkeypatch):
    def fake(prompt, fixture, workdir, config_dir, **kw):
        events = [
            json.dumps({"subtype": "init", "skills": ["harness-tier:doc-sync"]}),
            json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True}),
        ]
        return "\n".join(events), "boom\n"

    monkeypatch.setattr(run, "_claude_stream", fake)
    s = sandbox.BY_NAME["doc-sync-drift"]
    with pytest.raises(SystemExit):
        outcome.run_outcome("doc-sync", s, reps=1, config_dir=Path("."))


def test_run_outcome_aborts_when_the_target_skill_is_not_offered(monkeypatch):
    """Parity with run.measure: the plugin loaded but doc-sync was not among its skills (a
    broken frontmatter). A recorded 0 there is about the missing skill, not the end-state, so
    it must abort rather than fabricate a miss."""

    def fake(prompt, fixture, workdir, config_dir, **kw):
        # init lists a *different* skill — doc-sync loaded nothing, but `available` is non-empty
        events = [
            json.dumps({"subtype": "init", "skills": ["harness-tier:integration"]}),
            json.dumps({"type": "result", "subtype": "success", "is_error": False}),
        ]
        return "\n".join(events), ""

    monkeypatch.setattr(run, "_claude_stream", fake)
    s = sandbox.BY_NAME["doc-sync-drift"]
    with pytest.raises(SystemExit, match="not among its skills"):
        outcome.run_outcome("doc-sync", s, reps=1, config_dir=Path("."))


def test_outcome_main_returns_nonzero_on_rate_limit(monkeypatch):
    """A rate-limited run is not a success. The skill that hit the limit records nothing (its
    partial reps are lost by design), so main must return non-zero rather than fall through to
    the success message. The real outcome_scores.json is untouched: run_outcome raises before
    any write."""
    import contextlib

    @contextlib.contextmanager
    def fake_config():
        yield Path(".")

    def fake(prompt, fixture, workdir, config_dir, **kw):
        events = [
            json.dumps({"subtype": "init", "skills": ["harness-tier:doc-sync"]}),
            json.dumps({"type": "rate_limit_event", "rate_limit_info": {"status": "rejected"}}),
            json.dumps({"type": "result", "subtype": "success", "is_error": False}),
        ]
        return "\n".join(events), ""

    monkeypatch.setattr(run, "isolated_config_dir", fake_config)
    monkeypatch.setattr(run, "_claude_stream", fake)
    monkeypatch.setattr(sys, "argv", ["evals.outcome", "--reps", "1"])
    assert outcome.main() == 1


def test_outcome_dry_run_spawns_no_session(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["evals.outcome", "--dry-run"])
    assert outcome.main() == 0
    assert "outcome sessions" in capsys.readouterr().out


def test_outcome_reps_zero_is_rejected(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["evals.outcome", "--reps", "0", "--dry-run"])
    with pytest.raises(SystemExit) as e:
        outcome.main()
    assert e.value.code == 2


def test_committed_outcome_baseline_is_never_stale_or_zero():
    """The outcome mirror of test_a_stale_measurement_fails: whatever is committed in
    outcome_scores.json must be fresh (ok) or absent (warn) — never a stale or all-zero lie
    that would let a broken outcome ride a green suite. After seeding it is ok; before seeding
    it is warn, keeping the suite green until the first live measure.

    Every target, not a named one: with the arm holding more than one skill, a hardcoded
    name leaves the rest outside the freshness gate — their SKILL.md, fixture or golden
    could change and only the unchecked `outcome_sha` would disagree, silently."""
    baseline: dict = {}
    if outcome.OUTCOME_SCORES.exists():
        baseline = json.loads(outcome.OUTCOME_SCORES.read_text(encoding="utf-8"))
    for skill, scenario in outcome._outcome_targets():
        v = outcome.outcome_check(
            skill, baseline.get(skill), outcome.outcome_sha(skill, scenario), scenario
        )
        assert v.level in ("ok", "warn"), v.message
