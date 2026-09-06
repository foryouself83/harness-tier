import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import scripts.flow_gate_check as fgc
from scripts import wiki_graph
from scripts._harness_paths import RUNTIME_GATES
from scripts.flow_gate_check import missing_gates, module_commands
from scripts.wiki_graph import cmd_build
from tests.flow_gate._helpers import (
    _classify_worktree_module,
    _init_repo,
    _rg,
    _run_runner,
    _wiki_host,
    requires_bash_git,
)


def test_wiki_is_a_runtime_gate_needing_no_marker(tmp_path: Path):
    assert "wiki" in RUNTIME_GATES
    flow = tmp_path / ".flow"
    flow.mkdir()
    assert "wiki" not in missing_gates(flow, ["wiki", "doc-sync"])


def test_wiki_gate_blocks_a_drifted_graph_on_the_docs_tier(tmp_path: Path):
    # the docs tier is where module_commands short-circuits early, so the wiki gate deliberately
    # does not live there. A graph drift IS a documentation commit — it must still block.
    _wiki_host(tmp_path)
    (tmp_path / "docs" / "index.md").write_text(
        "---\nwiki_id: index\ntitle: Index\n---\nbody\n", encoding="utf-8"
    )  # graph.yaml never built → drift
    assert fgc.wiki_gate(tmp_path, ["doc-sync", "wiki"]) is True


def test_wiki_gate_passes_a_built_graph(tmp_path: Path):
    _wiki_host(tmp_path)
    (tmp_path / "docs" / "index.md").write_text(
        "---\nwiki_id: index\ntitle: Index\n---\nbody\n", encoding="utf-8"
    )
    assert cmd_build(tmp_path) == 0
    assert fgc.wiki_gate(tmp_path, ["precommit", "wiki"]) is False


def test_wiki_gate_is_not_a_module_command(tmp_path: Path):
    # It must NOT ride the module pre-check channel: down there any nonzero exit is read as
    # "the check failed", so an internal error would block every commit (Invariant #1). The
    # module result must be bit-for-bit what it was before the wiki gate existed.
    _wiki_host(tmp_path)
    assert module_commands(tmp_path, "docs", ["doc-sync", "wiki"]) == ([], [])
    assert module_commands(tmp_path, "dev", ["precommit", "wiki"]) == ([], [])


def test_no_wiki_gate_when_wiki_absent(tmp_path: Path):
    cfgdir = tmp_path / ".claude" / "harness-tier" / "config"
    cfgdir.mkdir(parents=True)
    (cfgdir / "flow-config.yaml").write_text("branches:\n  integration: dev\n", encoding="utf-8")
    assert fgc.wiki_gate(tmp_path, ["precommit", "wiki"]) is False


def test_no_wiki_gate_when_gate_not_listed(tmp_path: Path):
    # a drifted wiki that the tier's gates list does not name must not block — flow-tiers.yaml
    # is the on/off switch.
    _wiki_host(tmp_path)
    (tmp_path / "docs" / "index.md").write_text(
        "---\nwiki_id: index\ntitle: Index\n---\nbody\n", encoding="utf-8"
    )
    assert fgc.wiki_gate(tmp_path, ["precommit"]) is False
    assert fgc.wiki_gate(tmp_path, None) is False


def test_wiki_gate_internal_failure_is_fail_open(tmp_path: Path, monkeypatch):
    # The whole reason this gate left the module channel: an internal failure must ALLOW. Here
    # cmd_verify itself raises, which on the old channel would have surfaced as a nonzero exit
    # from the emitted command and denied every commit in the repo.
    _wiki_host(tmp_path)
    monkeypatch.setattr(fgc, "cmd_verify", lambda root: 1 / 0)
    assert fgc.wiki_gate(tmp_path, ["wiki"]) is False


def test_gate_script_runs_without_the_wiki_sibling(tmp_path: Path):
    # flow_gate_check imports wiki_graph at module scope, and plugin scripts are copied to the
    # host ONE FILE AT A TIME — so a host can legitimately hold this file without that sibling.
    # Unguarded, the ImportError would make the whole gate script unrunnable: the runner reads
    # that as an internal error and FAIL-OPENs, taking the tier and marker gates down with the
    # wiki one and switching enforcement off in silence. Copy the two files it needs.
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    repo = Path(__file__).resolve().parent.parent.parent
    for name in ("flow_gate_check.py", "_harness_paths.py"):
        shutil.copy(repo / "scripts" / name, scripts_dir / name)
    assert not (scripts_dir / "wiki_graph.py").exists()
    host = tmp_path / "host"
    host.mkdir()
    r = subprocess.run(
        [sys.executable, str(scripts_dir / "flow_gate_check.py"), "--wiki-check"],
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(host), "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"


def test_wiki_gate_lookup_failure_is_fail_open(tmp_path: Path, monkeypatch):
    def _boom(_root):
        raise RuntimeError("broken flow-config.wiki")

    _wiki_host(tmp_path)
    monkeypatch.setattr(wiki_graph, "load_wiki_config", _boom)
    assert fgc.wiki_gate(tmp_path, ["wiki"]) is False


@requires_bash_git
def test_runner_wiki_step_denies_and_carries_the_report(tmp_path: Path):
    # End to end through the real hook: a drifted graph must exit 2, and the deny reason must be
    # cmd_verify's own report rather than the module channel's "모듈 사전검사 실패: <command>".
    main = tmp_path / "main"
    _init_repo(main)
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
    _rg(["add", "docs/index.md"], wt)  # a node enters the wiki by being staged
    r = _run_runner(main, f"git -C {wt} commit -m x", dryrun=False)  # graph never built → drift
    assert r.returncode == 2
    payload = json.loads(r.stdout.strip())
    reason = payload["hookSpecificOutput"]["permissionDecisionReason"]
    assert "wiki graph 검증 실패" in reason
    assert "모듈 사전검사" not in reason


@requires_bash_git
def test_runner_wiki_step_shows_warnings_on_a_passing_commit(tmp_path: Path):
    # Warnings (orphan / max_lines / defect→rule) are the gate's quality signal, and at exit 0 a
    # hook's stdout AND stderr both go to the debug log only — systemMessage is the one field
    # documented as "shown to the user", so that is what a passing commit has to emit.

    main = tmp_path / "main"
    _init_repo(main)
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
    (wt / "docs" / "lonely.md").write_text(
        "---\nwiki_id: lonely\ntitle: Lonely\n---\nbody\n", encoding="utf-8"
    )  # unreachable from index → orphan warning, but NOT a block
    _rg(["add", "docs"], wt)
    assert cmd_build(wt) == 0
    _rg(["add", "docs/graph/graph.yaml"], wt)
    r = _run_runner(main, f"git -C {wt} commit -m x", dryrun=False)
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    payload = json.loads(r.stdout.strip())
    assert "orphan" in payload["systemMessage"]
