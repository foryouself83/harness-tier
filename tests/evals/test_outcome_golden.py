import os
import subprocess
import sys
from pathlib import Path

import pytest

import evals.outcome as outcome
import scripts.skill_sandbox as sandbox
import scripts.wiki_graph as wiki_graph
from tests.evals._helpers import REPO

# ── outcome arm ──────────────────────────────────────────────────────────────────────────
# A second arm, separate from the scored invocation arm above. It asks whether a skill, run
# for real in a golden fixture, reaches the right end-state — scored by deterministic file
# assertions (SWE-bench style), not by whether it fired. Everything here is model-free: the
# pure gate (outcome_sha/outcome_check) needs only disk, and the runner is exercised by
# patching run._claude_stream, so no session is spawned.


def test_doc_sync_drift_declares_a_machine_checkable_outcome():
    s = sandbox.BY_NAME["doc-sync-drift"]
    assert s.outcome, "doc-sync-drift must declare a golden end-state"
    assert set(s.outcome) == {"README.md", "docs/api.md", "app/server.py"}


def test_check_outcome_passes_the_golden_end_state(tmp_path):
    s = sandbox.BY_NAME["doc-sync-drift"]
    built = sandbox.build(s, tmp_path)
    (built / "README.md").write_text(
        "# Sandbox\n\nThe server listens on port 9090.\n", encoding="utf-8"
    )
    (built / "docs/api.md").write_text(
        "# API\n\nBase URL: `http://localhost:9090`\n", encoding="utf-8"
    )
    passed, failures = sandbox.check_outcome(s, built)
    assert passed, failures


def test_check_outcome_fails_on_the_original_drift(tmp_path):
    s = sandbox.BY_NAME["doc-sync-drift"]
    built = sandbox.build(s, tmp_path)  # ships 8080 / 3000 — unsynced drift
    passed, failures = sandbox.check_outcome(s, built)
    assert not passed
    assert any("8080" in f for f in failures)


def test_check_outcome_treats_a_missing_file_as_failure(tmp_path):
    s = sandbox.BY_NAME["doc-sync-drift"]
    built = sandbox.build(s, tmp_path)
    (built / "README.md").unlink()
    passed, failures = sandbox.check_outcome(s, built)
    assert not passed
    assert any("README.md: missing" in f for f in failures)


def test_wiki_init_migration_declares_a_machine_checkable_outcome():
    s = sandbox.BY_NAME["wiki-init-migration"]
    assert s.outcome, "wiki-init-migration must declare a golden end-state"
    assert set(s.outcome) == {
        "docs/backend.md",
        "docs/deploy.md",
        "docs/index.md",
        "docs/graph/graph.yaml",
        ".claude/harness-tier/config/flow-config.yaml",
    }


def _migrated_wiki(built: Path, *, split: bool = True) -> None:
    """Write the end-state a correct /wiki-init run leaves behind.

    `split=False` is the tempting wrong answer: front matter stamped onto the two-concept
    document without splitting it, which every structural check still passes."""
    # Step 7 edits the wiki key in place; the rest of the host's config survives, so the
    # helper flips the one value rather than rewriting the file.
    cfg = built / ".claude/harness-tier/config/flow-config.yaml"
    cfg.write_text(
        cfg.read_text(encoding="utf-8").replace("enable: false", "enable: true"),
        encoding="utf-8",
    )
    kept = "See [JWT authentication](auth.md).\n" if split else sandbox.WIKI_JWT_CLAIM
    (built / "docs/backend.md").write_text(
        "---\nwiki_id: backend\ntitle: Backend\nrelated: [auth]\n---\n\n"
        f"## JWT authentication\n\n{kept}",
        encoding="utf-8",
    )
    (built / "docs/auth.md").write_text(
        f"---\nwiki_id: auth\ntitle: JWT authentication\n---\n\n{sandbox.WIKI_JWT_CLAIM}",
        encoding="utf-8",
    )
    # Step 8: a document joins the wiki by being in the index. Left untracked it is not a
    # node, and every `related: [auth]` above becomes a dangling reference that blocks.
    subprocess.run(["git", "add", "docs/auth.md"], cwd=built, check=True, capture_output=True)
    (built / "docs/deploy.md").write_text(
        "---\nwiki_id: deploy\ntitle: Deploy\n---\n\nShip it.\n", encoding="utf-8"
    )
    (built / "docs/index.md").write_text(
        "---\nwiki_id: index\ntitle: Index\nrelated: [backend, auth, deploy]\n---\n\n"
        "- [Backend](backend.md)\n",
        encoding="utf-8",
    )
    graph = built / "docs/graph/graph.yaml"
    graph.parent.mkdir(parents=True, exist_ok=True)
    graph.write_text(
        wiki_graph.GRAPH_HEADER + "nodes:\n  auth: {}\n  backend: {}\n  deploy: {}\n  index: {}\n",
        encoding="utf-8",
    )


def test_check_outcome_passes_a_correct_wiki_migration(tmp_path):
    s = sandbox.BY_NAME["wiki-init-migration"]
    built = sandbox.build(s, tmp_path)
    _migrated_wiki(built)
    passed, failures = sandbox.check_outcome(s, built)
    assert passed, failures


def test_check_outcome_fails_when_the_two_concept_document_was_not_split(tmp_path):
    """The failure this scenario exists to catch. Stamping front matter on a document that
    holds two concepts satisfies every structural rule --verify has — the id is valid, the
    title is there, nothing dangles — so a graph built from it is *valid* and *useless*:
    --neighbors hands the model a blob covering both subjects. Only the golden sees it."""
    s = sandbox.BY_NAME["wiki-init-migration"]
    built = sandbox.build(s, tmp_path)
    _migrated_wiki(built, split=False)
    passed, failures = sandbox.check_outcome(s, built)
    assert not passed
    assert any("docs/backend.md" in f for f in failures)


def test_check_outcome_fails_when_the_section_was_dropped_instead_of_split(tmp_path):
    # The mirror of the test above, and the reason `related:` is in the golden: deleting the
    # JWT section outright also removes the claim, so a must_not_contain alone reads a
    # destructive run as a correct split. Step 4 keeps the original as a node pointing at
    # what came out of it, so the absence of `related:` is what tells the two apart.
    s = sandbox.BY_NAME["wiki-init-migration"]
    built = sandbox.build(s, tmp_path)
    _migrated_wiki(built)
    (built / "docs/auth.md").unlink()
    (built / "docs/backend.md").write_text(
        "---\nwiki_id: backend\ntitle: Backend\n---\n\n## Postgres schema\n\nSee the code.\n",
        encoding="utf-8",
    )
    passed, failures = sandbox.check_outcome(s, built)
    assert not passed
    assert any("related:" in f for f in failures)


def test_check_outcome_fails_on_a_hand_written_graph(tmp_path):
    # --build is the only thing that writes the generated header, so a stub someone typed to
    # satisfy the golden fails. Without that needle a run that never executed Step 8 — and
    # therefore never had its front matter validated — would score as a pass.
    s = sandbox.BY_NAME["wiki-init-migration"]
    built = sandbox.build(s, tmp_path)
    _migrated_wiki(built)
    (built / "docs/graph/graph.yaml").write_text(
        "nodes:\n  auth: {}\n  backend: {}\n  deploy: {}\n  index: {}\n", encoding="utf-8"
    )
    passed, failures = sandbox.check_outcome(s, built)
    assert not passed
    assert any("GENERATED by wiki_graph.py" in f for f in failures)


def test_check_outcome_fails_when_a_generated_edge_was_written_by_hand(tmp_path):
    # `used_by` is derived from every other node's `depends_on`; writing it by hand blocks
    # validation outright, so a run that does it has not reached the end-state.
    s = sandbox.BY_NAME["wiki-init-migration"]
    built = sandbox.build(s, tmp_path)
    _migrated_wiki(built)
    front = "---\nwiki_id: deploy\ntitle: Deploy\nused_by: [backend]\n---\n\nShip it.\n"
    (built / "docs/deploy.md").write_text(front, encoding="utf-8")
    passed, failures = sandbox.check_outcome(s, built)
    assert not passed
    assert any("used_by" in f for f in failures)


def test_build_can_seed_a_committed_git_repo(tmp_path):
    """wiki-init builds the graph from git's index, so the fixture has to be a repository
    with its documents already tracked.

    Without one the run exercises the filesystem fallback instead of the documented path,
    and it invites a false failure: an agent that meets `fatal: not a git repository`,
    runs `git init` and then follows Step 8 literally — `git add` the documents it
    *created* — leaves an index holding only those, so the rebuilt graph drops every
    pre-existing node and a correct migration scores as a miss."""
    s = sandbox.BY_NAME["wiki-init-migration"]
    built = sandbox.build(s, tmp_path)
    tracked = subprocess.run(
        ["git", "ls-files", "--cached"], cwd=built, capture_output=True, text=True, check=True
    ).stdout.split()
    assert "docs/backend.md" in tracked
    assert "docs/deploy.md" in tracked
    assert "docs/index.md" in tracked


def test_building_a_git_fixture_twice_into_the_same_dir_works(tmp_path):
    # git writes its object files read-only, so a plain rmtree over the previous build dies
    # on Windows with PermissionError — `skill_sandbox.py --all --out-dir <dir>` would work
    # once and fail every run after.
    s = sandbox.BY_NAME["wiki-init-migration"]
    sandbox.build(s, tmp_path)
    built = sandbox.build(s, tmp_path)
    assert (built / ".git").exists()


def test_build_materializes_the_host_copy_of_a_script(tmp_path):
    """wiki-init Step 8 runs `.claude/harness-tier/scripts/wiki_graph.py` by that literal
    path — the host copy /flow-init makes. A fixture without it fails that command every
    run, and what gets measured is how well the agent improvises a path, not the skill."""
    s = sandbox.BY_NAME["wiki-init-migration"]
    built = sandbox.build(s, tmp_path)
    copied = built / ".claude/harness-tier/scripts/wiki_graph.py"
    assert copied.is_file()
    assert copied.read_text(encoding="utf-8") == (REPO / "scripts/wiki_graph.py").read_text(
        encoding="utf-8"
    )


def test_the_wiki_golden_is_reachable_by_the_real_build(tmp_path):
    """A golden no correct run can satisfy scores 0 and reads as a broken skill.

    So this performs the migration wiki-init describes and then runs the *real*
    `wiki_graph.py --build`/`--verify` over it, rather than hand-writing a graph the way
    the scoring tests above do — the generated header, the derived ids and the structural
    rules all have to line up for the golden to pass."""
    s = sandbox.BY_NAME["wiki-init-migration"]
    built = sandbox.build(s, tmp_path)
    _migrated_wiki(built)
    (built / "docs/graph/graph.yaml").unlink()
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(built), "PYTHONUTF8": "1"}
    for flag in ("--build", "--verify"):
        r = subprocess.run(
            [sys.executable, str(REPO / "scripts/wiki_graph.py"), flag],
            capture_output=True,
            text=True,
            env=env,
            cwd=built,
        )
        assert r.returncode == 0, f"{flag}: {r.stdout} {r.stderr}"
    passed, failures = sandbox.check_outcome(s, built)
    assert passed, failures


def test_outcome_targets_can_be_narrowed_to_one_skill():
    # Parity with run.py's --skill. Without it, adding a second scenario makes every
    # measurement re-run every skill, so re-measuring one costs the others' sessions and
    # overwrites baselines nobody meant to touch.
    assert [s for s, _ in outcome._outcome_targets(only="wiki-init")] == ["wiki-init"]
    assert len(outcome._outcome_targets()) > 1


def test_outcome_targets_rejects_a_skill_with_no_scenario():
    # A typo must not silently measure nothing and then report a completed run.
    with pytest.raises(SystemExit):
        outcome._outcome_targets(only="wiki-inti")


def test_check_outcome_fails_when_the_wiki_was_never_enabled(tmp_path):
    # --build no-ops on a disabled wiki, so a run that skipped Step 7 leaves no graph at all.
    s = sandbox.BY_NAME["wiki-init-migration"]
    built = sandbox.build(s, tmp_path)
    _migrated_wiki(built)
    cfg = built / ".claude/harness-tier/config/flow-config.yaml"
    cfg.write_text(
        cfg.read_text(encoding="utf-8").replace("enable: true", "enable: false"),
        encoding="utf-8",
    )
    passed, failures = sandbox.check_outcome(s, built)
    assert not passed
    assert any("enable: true" in f for f in failures)
