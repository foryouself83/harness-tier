import json
import os
import subprocess
import sys
from pathlib import Path

from scripts.wiki_graph import cmd_build
from tests.flow_gate._helpers import (
    _classify_worktree_module,
    _init_repo,
    _rg,
    _run_runner,
    _wiki_host,
    requires_bash_git,
    requires_git,
)


def _classify_docs(root: Path) -> None:
    """docs tier marker (branch-bound to the current branch) + its doc-sync evidence."""
    flow = root / ".claude" / "harness-tier" / ".flow"
    flow.mkdir(parents=True, exist_ok=True)
    branch = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    (flow / "tier").write_text(f"docs:{branch}", encoding="utf-8")
    (flow / "doc-sync.done").touch()


def _main_gate(root: Path, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    repo = Path(__file__).resolve().parent.parent.parent
    env = {
        **os.environ,
        "CLAUDE_PROJECT_DIR": str(root),
        "CLAUDE_PLUGIN_ROOT": str(repo),
        "PYTHONIOENCODING": "utf-8",
        **(env_extra or {}),
    }
    return subprocess.run(
        [sys.executable, str(repo / "scripts" / "flow_gate_check.py")],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


@requires_git
def test_main_runs_wiki_gate_in_process_and_blocks(tmp_path: Path):
    # spawn 2→1: the flow gate's own invocation must carry the wiki verdict — exit 2 with the
    # reason on stdout (the runner's stage-1 channel), no separate --wiki-check call needed.
    _init_repo(tmp_path)
    _wiki_host(tmp_path)
    (tmp_path / "docs" / "index.md").write_text(
        "---\nwiki_id: index\ntitle: Index\n---\nbody\n", encoding="utf-8"
    )
    _rg(["add", "docs/index.md"], tmp_path)  # a node enters the wiki by being staged
    _classify_docs(tmp_path)  # graph never built → drift
    r = _main_gate(tmp_path)
    assert r.returncode == 2, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    assert "wiki graph 검증 실패" in r.stdout


@requires_git
def test_main_emits_system_message_on_passing_wiki_warnings(tmp_path: Path):
    _init_repo(tmp_path)
    _wiki_host(tmp_path)
    (tmp_path / "docs" / "index.md").write_text(
        "---\nwiki_id: index\ntitle: Index\n---\nbody\n", encoding="utf-8"
    )
    (tmp_path / "docs" / "lonely.md").write_text(
        "---\nwiki_id: lonely\ntitle: Lonely\n---\nbody\n", encoding="utf-8"
    )  # orphan → warn only
    _rg(["add", "docs"], tmp_path)
    assert cmd_build(tmp_path) == 0
    _classify_docs(tmp_path)
    r = _main_gate(tmp_path)
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    payload = json.loads(r.stdout.strip())
    assert "orphan" in payload["systemMessage"]


@requires_git
def test_main_skips_wiki_under_dryrun(tmp_path: Path):
    _init_repo(tmp_path)
    _wiki_host(tmp_path)
    (tmp_path / "docs" / "index.md").write_text(
        "---\nwiki_id: index\ntitle: Index\n---\nbody\n", encoding="utf-8"
    )
    _rg(["add", "docs/index.md"], tmp_path)
    _classify_docs(tmp_path)  # drift — but DRYRUN must not pay (or fire) the wiki gate
    r = _main_gate(tmp_path, {"HARNESS_PRECOMMIT_DRYRUN": "1"})
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    assert r.stdout == ""


@requires_git
def test_wiki_check_alias_keeps_the_old_contract(tmp_path: Path):
    # A half-copied host can hold a runner still calling --wiki-check — the alias must answer
    # with the exact old contract (exit 2 + stdout reason).
    _init_repo(tmp_path)
    _wiki_host(tmp_path)
    (tmp_path / "docs" / "index.md").write_text(
        "---\nwiki_id: index\ntitle: Index\n---\nbody\n", encoding="utf-8"
    )
    _rg(["add", "docs/index.md"], tmp_path)
    _classify_docs(tmp_path)
    repo = Path(__file__).resolve().parent.parent.parent
    r = subprocess.run(
        [sys.executable, str(repo / "scripts" / "flow_gate_check.py"), "--wiki-check"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env={
            **os.environ,
            "CLAUDE_PROJECT_DIR": str(tmp_path),
            "CLAUDE_PLUGIN_ROOT": str(repo),
            "PYTHONIOENCODING": "utf-8",
        },
    )
    assert r.returncode == 2, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    assert "wiki graph 검증 실패" in r.stdout


@requires_bash_git
def test_runner_wiki_step_fails_open_when_the_gate_script_is_missing(tmp_path: Path):
    # `python3 <missing file>` exits 2 with its complaint on stderr — indistinguishable from a
    # block if the step read stderr. A host whose script copy half-failed would then have every
    # commit denied with an interpreter error as the reason, which is the one thing Invariant #1
    # forbids for this gate. Reading stdout only (which the interpreter never writes) is the fix.
    main = tmp_path / "main"
    _init_repo(main)
    _classify_worktree_module(main)  # dirty tree, so the runner reaches the wiki step
    empty_plugin = tmp_path / "no-scripts"
    (empty_plugin / "scripts").mkdir(parents=True)  # exists, but holds no gate scripts
    r = _run_runner(main, "git commit -m x", dryrun=False, plugin_root=empty_plugin)
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"


@requires_bash_git
def test_runner_wiki_step_reads_the_committing_worktree(tmp_path: Path):
    # CLAUDE_PROJECT_DIR is fixed at session start = main. A worktree commit must be verified
    # against the WORKTREE's graph (Invariant #6), so point main at a drifted wiki and give the
    # worktree a clean one: if the step read main, this would newly block.

    main = tmp_path / "main"
    _init_repo(main)
    _wiki_host(main)  # wiki enabled, graph.yaml never built → guaranteed drift if ever read
    (main / "docs" / "index.md").write_text(
        "---\nwiki_id: index\ntitle: Index\n---\nbody\n", encoding="utf-8"
    )
    wt = tmp_path / "wt"
    _rg(["worktree", "add", "-b", "feature/x", str(wt)], main)
    _classify_worktree_module(wt)
    (wt / ".claude" / "harness-tier" / "config" / "flow-config.yaml").write_text(
        "wiki:\n  enable: true\n  root: docs/\n", encoding="utf-8"
    )
    (wt / "docs").mkdir()
    (wt / "docs" / "index.md").write_text(
        "---\nwiki_id: index\ntitle: Index\n---\nbody\n", encoding="utf-8"
    )
    _rg(["add", "docs"], wt)
    assert cmd_build(wt) == 0
    _rg(["add", "docs/graph/graph.yaml"], wt)
    r = _run_runner(main, f"git -C {wt} commit -m x", dryrun=False)
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
