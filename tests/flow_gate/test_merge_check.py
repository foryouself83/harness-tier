import json
import sys
from pathlib import Path

import pytest

import scripts.flow_gate_check as fgc


def _write_policy(tmp_path: Path) -> Path:
    """Host layout: .claude/harness-tier/config/{flow-tiers,flow-config}.yaml"""
    cfg_dir = tmp_path / ".claude" / "harness-tier" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "flow-tiers.yaml").write_text(
        "tiers:\n  dev:\n    gates: [review]\n"
        "merge_strategy:\n"
        '  - source: "feature/*"\n'
        "    target: integration\n"
        '    require: "--squash"\n'
        "    warn_unless_rebased: true\n"
        "  - source: staging\n"
        "    target: production\n"
        '    require: "--no-ff"\n',
        encoding="utf-8",
    )
    (cfg_dir / "flow-config.yaml").write_text(
        "branches:\n  integration: dev\n  staging: stage\n  production: main\n"
        '  feature_prefix: "feature/"\n',
        encoding="utf-8",
    )
    return tmp_path


def _run_merge_check(monkeypatch, tmp_path: Path, command: str, branch: str):
    """Invoke merge_check_output with stdin/branch stubbed; return the SystemExit code."""
    import io

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(fgc, "_current_branch", lambda root: branch)
    monkeypatch.setattr(fgc, "_is_rebased", lambda root, source, target: True)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"command": command}})))
    with pytest.raises(SystemExit) as exc:
        fgc.merge_check_output()
    return exc.value.code


def test_merge_check_blocks_missing_squash(monkeypatch, tmp_path: Path, capsys):
    _write_policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, "git merge feature/x", "dev")
    assert code == fgc.BLOCK_EXIT_CODE
    assert "--squash" in capsys.readouterr().err


def test_merge_check_allows_squash(monkeypatch, tmp_path: Path):
    _write_policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, "git merge --squash feature/x", "dev")
    assert code == 0


def test_merge_check_blocks_missing_no_ff(monkeypatch, tmp_path: Path):
    _write_policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, "git merge origin/stage", "main")
    assert code == fgc.BLOCK_EXIT_CODE


def test_merge_check_allows_no_ff(monkeypatch, tmp_path: Path):
    _write_policy(tmp_path)
    code = _run_merge_check(
        monkeypatch, tmp_path, 'git merge --no-ff -m "Merge stage: x" origin/stage', "main"
    )
    assert code == 0


def test_merge_check_blocks_switch_then_merge(monkeypatch, tmp_path: Path, capsys):
    # HEAD is still the SOURCE branch (feature/x) — the target must come from the command.
    _write_policy(tmp_path)
    code = _run_merge_check(
        monkeypatch, tmp_path, "git switch dev && git merge feature/x", "feature/x"
    )
    assert code == fgc.BLOCK_EXIT_CODE
    assert "--squash" in capsys.readouterr().err


def test_merge_check_allows_switch_then_squash_merge(monkeypatch, tmp_path: Path):
    _write_policy(tmp_path)
    code = _run_merge_check(
        monkeypatch, tmp_path, "git switch dev && git merge --squash feature/x", "feature/x"
    )
    assert code == 0


def test_merge_check_other_worktree_fails_open(monkeypatch, tmp_path: Path):
    # `git -C <wt> merge feature/x` while the worktree sits on `stage`: the source is read from
    # the command but the target would be read from THIS root (dev), inventing a feature/* → dev
    # violation for a flow (feature/* → stage) that has no rule at all. That is the one place the
    # FAIL-OPEN invariant broke in the BLOCKING direction, so an unrelated -C dir must exit 0.
    _write_policy(tmp_path)
    code = _run_merge_check(
        monkeypatch, tmp_path, f"git -C {tmp_path / 'other-wt'} merge feature/x", "dev"
    )
    assert code == 0


def test_merge_check_dash_c_on_this_root_still_enforced(monkeypatch, tmp_path: Path):
    # …but `-C` pointing at the gated root itself names no other worktree — the branch read here
    # IS the merge target, so enforcement must not be given away wholesale.
    _write_policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, f"git -C {tmp_path} merge feature/x", "dev")
    assert code == fgc.BLOCK_EXIT_CODE


def test_merge_check_no_rule_fails_open(monkeypatch, tmp_path: Path):
    # dev → stage has no rule
    _write_policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, "git merge dev", "stage")
    assert code == 0


def test_merge_check_absent_policy_fails_open(monkeypatch, tmp_path: Path):
    cfg_dir = tmp_path / ".claude" / "harness-tier" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "flow-tiers.yaml").write_text("tiers:\n  dev:\n    gates: []\n", encoding="utf-8")
    code = _run_merge_check(monkeypatch, tmp_path, "git merge feature/x", "dev")
    assert code == 0


def test_merge_check_detached_head_fails_open(monkeypatch, tmp_path: Path):
    _write_policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, "git merge feature/x", None)
    assert code == 0


def test_merge_check_not_a_merge_fails_open(monkeypatch, tmp_path: Path):
    _write_policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, "git merge-base --is-ancestor a b", "dev")
    assert code == 0


def test_merge_check_warns_when_not_rebased(monkeypatch, tmp_path: Path, capsys):
    import io

    _write_policy(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(fgc, "_current_branch", lambda root: "dev")
    monkeypatch.setattr(fgc, "_is_rebased", lambda root, source, target: False)
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps({"tool_input": {"command": "git merge --squash feature/x"}})),
    )
    with pytest.raises(SystemExit) as exc:
        fgc.merge_check_output()
    assert exc.value.code == 0  # warning never blocks
    assert "rebase" in capsys.readouterr().err
