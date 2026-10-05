"""A merge run from a session whose shell sits in another worktree of the gated repo."""

import io
import json
import sys
from pathlib import Path

import pytest

import scripts.flow_gate_check as fgc
from tests.flow_gate._helpers import _init_repo, _rg, requires_git
from tests.flow_gate.test_merge_check import _write_policy


def _host(tmp_path: Path, main_branch: str, wt_branch: str) -> tuple[Path, Path]:
    main = tmp_path / "main"
    _init_repo(main)
    _write_policy(main)
    for b in {"dev", "stage", "feature/a", main_branch, wt_branch} - {"main"}:
        _rg(["branch", b], main)
    _rg(["switch", main_branch], main)
    wt = tmp_path / "wt"
    _rg(["worktree", "add", str(wt), wt_branch], main)
    return main, wt


def _check(monkeypatch, main: Path, cwd: Path, command: str):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(main))
    monkeypatch.chdir(cwd)
    monkeypatch.setattr(fgc, "_is_rebased", lambda root, source, target: True)
    payload = {"cwd": str(cwd), "tool_input": {"command": command}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    with pytest.raises(SystemExit) as exc:
        fgc.merge_check_output()
    return exc.value.code


@requires_git
def test_a_merge_lands_on_the_worktree_the_shell_is_in(tmp_path, monkeypatch, capsys):
    """Read from root, the target was feature/a, which has no rule, and the unsquashed merge into
    the worktree's dev went through."""
    main, wt = _host(tmp_path, "feature/a", "dev")
    assert _check(monkeypatch, main, wt, "git merge feature/x") == fgc.BLOCK_EXIT_CODE
    assert "--squash" in capsys.readouterr().err


@requires_git
def test_root_on_dev_does_not_judge_a_worktree_on_a_feature_branch(tmp_path, monkeypatch):
    """The reverse: a feature → feature merge in the worktree was judged as one into root's dev."""
    main, wt = _host(tmp_path, "dev", "feature/a")
    assert _check(monkeypatch, main, wt, "git merge feature/x") == 0


@requires_git
def test_a_shell_in_root_still_reads_root(tmp_path, monkeypatch):
    main, _wt = _host(tmp_path, "dev", "feature/a")
    assert _check(monkeypatch, main, main, "git merge feature/x") == fgc.BLOCK_EXIT_CODE


@requires_git
def test_a_shell_in_another_repo_reads_root(tmp_path, monkeypatch):
    """No same-repo proof, so the target stays root's, as before."""
    main, _wt = _host(tmp_path, "dev", "feature/a")
    other = tmp_path / "other"
    _init_repo(other)
    assert _check(monkeypatch, main, other, "git merge feature/x") == fgc.BLOCK_EXIT_CODE


@requires_git
@pytest.mark.parametrize(
    "command",
    [
        "git -C {main} merge stage",
        "git fetch -q; cd {main} && git merge stage",
        "pushd {main} && git merge stage",
        "(cd {main} && git merge stage)",
        "env -C {main} git merge stage",
        "git --git-dir={main}/.git merge stage",
        "GIT_DIR={main}/.git git merge stage",
    ],
)
def test_a_merge_the_command_moves_to_root_is_judged_as_roots(tmp_path, monkeypatch, command):
    """The shell stands in the worktree, yet each of these merges stage into root's main."""
    main, wt = _host(tmp_path, "main", "feature/a")
    spelled = command.format(main=main.as_posix())
    assert _check(monkeypatch, main, wt, spelled) == fgc.BLOCK_EXIT_CODE


@requires_git
def test_a_commits_directory_does_not_move_the_merge(tmp_path, monkeypatch):
    """`-C` on the commit says nothing about where the merge after it lands."""
    main, wt = _host(tmp_path, "main", "feature/a")
    command = f"git -C {wt.as_posix()} commit -m x && git merge stage"
    assert _check(monkeypatch, main, main, command) == fgc.BLOCK_EXIT_CODE


@requires_git
def test_dash_c_dot_is_the_shells_tree(tmp_path, monkeypatch):
    """`-C .` names the directory the shell stands in, which is the worktree."""
    main, wt = _host(tmp_path, "dev", "feature/a")
    assert _check(monkeypatch, main, wt, "git -C . merge feature/x") == 0
