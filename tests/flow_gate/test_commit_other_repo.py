"""A commit the command runs in a repository other than the gated one."""

import io
import json
import sys
from pathlib import Path

import pytest

import scripts.flow_gate_check as fgc
from tests.flow_gate._helpers import _init_repo, _rg, _run_runner, requires_bash_git, requires_git


def _classify(monkeypatch, capsys, root: Path, command: str, cwd: Path | None = None):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(root))
    monkeypatch.chdir(root)
    payload = {"cwd": str(cwd or root), "tool_input": {"command": command}}
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps(payload)))
    fgc.classify_output()
    return capsys.readouterr().out.split()


@pytest.fixture
def repos(tmp_path):
    main, other = tmp_path / "main", tmp_path / "other"
    _init_repo(main)
    _init_repo(other)
    _rg(["branch", "dev"], main)
    _rg(["worktree", "add", str(tmp_path / "wt"), "dev"], main)
    return main, other, tmp_path / "wt"


@requires_git
@pytest.mark.parametrize(
    "command",
    ["git -C {other} commit -m x", "cd {other} && git commit -m x"],
)
def test_a_commit_in_another_repo_is_not_ours(monkeypatch, capsys, repos, command):
    main, other, _wt = repos
    out = _classify(monkeypatch, capsys, main, command.format(other=other.as_posix()))
    assert "ok=1" in out and "commit=1" not in out


@requires_git
@pytest.mark.parametrize(
    "command",
    [
        "git -C {wt} commit -m x",  # a worktree of the gated repo
        "git -C {missing} commit -m x",  # a tree this cannot read
        "git -C {other} commit -m x && git commit -m y",  # one commit runs here
        "cd {other} && git commit -m x; cd {main} && git commit -m y",  # a hop back to main
        "git commit -m x",
        # git stacks -C, and --git-dir / GIT_DIR send the commit back to main
        "git -C {other} -C {main} commit -m x",
        "git -C {other} --git-dir={main}/.git commit -m x",
        "git --git-dir={main}/.git -C {other} commit -m x",
        "GIT_DIR={main}/.git git -C {other} commit -m x",
        "export GIT_DIR={main}/.git; git -C {other} commit -m x",
        "cd {other} && GIT_DIR={main}/.git git commit -m x",
        "cd {other} && git --git-dir={main}/.git --work-tree={main} commit -m x",
        'git -C {other} commit -m "$(git -C {main} commit -m y)"',
        "git -C {other} commit -m x --git-dir={main}/.git",
        "git -C {other} commit -m x\ngit commit -am y",  # bash splits at the newline
        "cd {other} && git commit -m x\ngit commit -am y",
        "git -C {other} commit\ngit commit -am y",
    ],
)
def test_a_commit_not_proven_elsewhere_stays_gated(monkeypatch, capsys, repos, command):
    main, other, wt = repos
    spelled = command.format(
        other=other.as_posix(),
        wt=wt.as_posix(),
        missing=(main.parent / "none").as_posix(),
        main=main.as_posix(),
    )
    assert "commit=1" in _classify(monkeypatch, capsys, main, spelled)


@requires_git
@pytest.mark.parametrize("name", ["~+", "~-", "~", "~root", "[o]", "{o,p}", "-", "--", "-P"])
@pytest.mark.parametrize("command", ["git -C {d} commit -am x", "cd {d} && git commit -am x"])
def test_a_directory_bash_expands_stays_gated(monkeypatch, capsys, repos, name, command):
    """`~+` is $PWD to bash and a literal sub-repo to Python; `[o]` globs to a plain `o`;
    `cd -` is $OLDPWD and `cd --` or `cd -P` alone is $HOME."""
    main, _other, _wt = repos
    _init_repo(main / name)
    (main / "o").mkdir()
    assert "commit=1" in _classify(monkeypatch, capsys, main, command.format(d=name))


@requires_git
def test_a_relative_directory_is_read_from_the_shells_cwd(monkeypatch, capsys, repos):
    """The shell stands in the parent, where `other` is the other repo; from main it is none."""
    main, _other, _wt = repos
    out = _classify(monkeypatch, capsys, main, "git -C other commit -m x", cwd=main.parent)
    assert "commit=1" not in out


@requires_bash_git
def test_the_runner_leaves_another_repos_commit_alone(repos):
    """Main carries no tier marker, so a commit judged as main's would be blocked unclassified."""
    main, other, _wt = repos
    cfg = main / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-tiers.yaml").write_text("tiers:\n  dev:\n    gates: [review]\n", encoding="utf-8")
    (cfg / "flow-config.yaml").write_text(
        "branches:\n  integration: dev\n  staging: stage\n  production: prod\n", encoding="utf-8"
    )
    assert _run_runner(main, "git commit -m x").returncode == 2  # main's own commit is blocked
    (other / "f.txt").write_text("x", encoding="utf-8")
    _rg(["add", "f.txt"], other)
    r = _run_runner(main, f"git -C {other.as_posix()} commit -m x")
    assert r.returncode == 0, r.stderr
