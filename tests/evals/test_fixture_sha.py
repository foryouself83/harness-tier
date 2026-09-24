"""`fixture_sha`: the invocation score's freshness key for the fixtures its cases run in.

A fixture-backed skill's rate depends on the directory each prompt meets as much as on its
description, so a fixture edit must stale the score the way a description edit does.
"""

from dataclasses import replace

import yaml

import evals.scores as scores
import scripts.skill_sandbox as sandbox
from tests.evals._helpers import EXPECT, N_SKILLS, OK


def test_a_skill_without_fixtures_has_no_fixture_sha():
    assert scores.fixtures_for("commit") == []
    assert scores.fixture_sha("commit") is None


def test_fixtures_for_reads_the_skill_level_and_every_case_override():
    # flow has no skill-level fixture and one case that names its own; doc-sync has a
    # skill-level fixture and a negative case that overrides it.
    assert scores.fixtures_for("flow") == ["flow-pending-commit"]
    assert scores.fixtures_for("doc-sync") == ["doc-sync-drift", "prose-review-comments"]


def test_fixture_sha_moves_with_fixture_content_and_not_with_its_prose(monkeypatch):
    base = scores.fixture_sha("flow")
    s = sandbox.BY_NAME["flow-pending-commit"]
    reworded = replace(s, why="different prose", expect=["x"], reject=["y"])
    monkeypatch.setitem(sandbox.BY_NAME, "flow-pending-commit", reworded)
    assert scores.fixture_sha("flow") == base
    emptied = replace(s, uncommitted={})
    monkeypatch.setitem(sandbox.BY_NAME, "flow-pending-commit", emptied)
    assert scores.fixture_sha("flow") != base


def test_a_changed_fixture_fails_the_gate():
    entry = {**OK, "fixture_sha": "old"}
    v = scores.check("integration", entry, "x", EXPECT, N_SKILLS, fixture="new")
    assert v.level == "fail" and "fixture changed" in v.message


def test_a_matching_fixture_passes():
    entry = {**OK, "fixture_sha": "same"}
    assert scores.check("integration", entry, "x", EXPECT, N_SKILLS, fixture="same").level == "ok"


def test_an_unfingerprinted_entry_warns_rather_than_going_stale():
    """Recorded before the key existed: the gate cannot tell whether its fixture moved, so it
    says so and lets the next measurement record the key — failing it would demand a
    re-measure that proves nothing about a fixture that did not change."""
    v = scores.check("integration", dict(OK), "x", EXPECT, N_SKILLS, fixture="now")
    assert v.level == "warn" and "fixture_sha" in v.message


def test_a_skill_that_gained_or_lost_fixtures_is_stale():
    # run.py records None for a fixture-less run, so a null key is a claim, not an absence:
    # the score was measured in no fixture. Either direction of change fails.
    gained = {**OK, "fixture_sha": None}
    assert scores.check("integration", gained, "x", EXPECT, N_SKILLS, fixture="now").level == (
        "fail"
    )
    lost = {**OK, "fixture_sha": "then"}
    assert scores.check("integration", lost, "x", EXPECT, N_SKILLS).level == "fail"


def test_a_fixture_less_skill_with_a_null_key_passes():
    entry = {**OK, "fixture_sha": None}
    assert scores.check("integration", entry, "x", EXPECT, N_SKILLS).level == "ok"


def test_the_ratchet_re_baselines_across_a_moved_fixture():
    """A drop measured in a different fixture is a different case, not a description
    regression — the same boundary the model pin draws."""
    old = {**OK, "invoke_hits": 15, "invoke_n": 15, "fixture_sha": "then"}
    low = {**OK, "invoke_hits": 3, "invoke_n": 15}
    moved = scores.may_write("integration", {**low, "fixture_sha": "now"}, old, False, n_skills=7)
    assert moved.level == "ok"
    same = scores.may_write("integration", {**low, "fixture_sha": "then"}, old, False, n_skills=7)
    assert same.level != "ok"
    # A recorded null is a run in no fixture: gaining one crosses the same boundary.
    gained = scores.may_write(
        "integration",
        {**low, "fixture_sha": "now"},
        {**old, "fixture_sha": None},
        False,
        n_skills=7,
    )
    assert gained.level == "ok"
    # An entry that predates the key keeps the ratchet.
    legacy = {k: v for k, v in old.items() if k != "fixture_sha"}
    kept = scores.may_write("integration", {**low, "fixture_sha": "now"}, legacy, False, n_skills=7)
    assert kept.level != "ok"


def test_an_unknown_fixture_name_does_not_stop_the_fingerprint(monkeypatch):
    monkeypatch.setattr(scores, "fixtures_for", lambda name: ["no-such-scenario"])
    assert scores.fixture_sha("anything")


def test_fixtures_for_agrees_with_the_runner_for_every_skill():
    """run.cases_for decides which fixture each session builds; fixtures_for restates that rule
    because run imports scores. Held here to one answer over the real cases file."""
    import evals.run as run

    data = yaml.safe_load(run.CASES.read_text(encoding="utf-8"))
    for name, entry in data["skills"].items():
        from_runner = {f for arm in ("happy", "negative") for _, f in run.cases_for(entry, arm)}
        assert scores.fixtures_for(name) == sorted(f for f in from_runner if f), name


def test_a_fixture_less_skill_ignores_the_key():
    assert scores.check("integration", dict(OK), "x", EXPECT, N_SKILLS).level == "ok"


def test_the_incremental_run_targets_a_moved_fixture_and_nothing_else(monkeypatch):
    import evals.run as run

    monkeypatch.setattr(scores, "fixture_sha", lambda name: "now")
    monkeypatch.setattr(scores, "description_sha", lambda name: "desc")
    assert not run.is_stale("x", {"description_sha": "desc", "fixture_sha": "now"})
    assert run.is_stale("x", {"description_sha": "desc", "fixture_sha": "then"})
    assert not run.is_stale("x", {"description_sha": "desc"})  # predates the key
    assert run.is_stale("x", {"description_sha": "old"})


def test_every_recorded_fixture_sha_is_current():
    """The committed file, gated: a fixture edit without a re-measure is the failure this key
    exists for."""
    recorded = scores.load()["skills"]
    for name, entry in recorded.items():
        if "fixture_sha" in entry:
            assert entry["fixture_sha"] == scores.fixture_sha(name), (
                f"{name}: fixture changed since the score — re-measure"
            )
