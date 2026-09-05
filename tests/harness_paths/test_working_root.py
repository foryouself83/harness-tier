import subprocess
from pathlib import Path

import pytest

import scripts._harness_paths as vp


def _has_git() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


requires_git = pytest.mark.skipif(not _has_git(), reason="git not available")


def test_git_survives_non_utf8_output(tmp_path: Path):
    # A single non-UTF-8 byte anywhere in git's output makes the decode raise and the whole
    # call return None — the gate then fails open silently for that entire repository.
    # errors="replace" keeps the value: a path carrying a replacement character fails
    # to match, so only that one entry falls open, which is far narrower.
    if not _has_git():
        pytest.skip("git not available")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    sha = (
        subprocess.run(
            ["git", "hash-object", "-w", "--stdin"],
            cwd=tmp_path,
            input=b"caf\xe9 latin-1\n",
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .strip()
    )
    out = vp._git(["cat-file", "blob", sha], tmp_path)
    assert out is not None and "caf" in out


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _run_git(["init", "-b", "main"], path)
    _run_git(["config", "user.email", "t@e.st"], path)
    _run_git(["config", "user.name", "Test"], path)
    (path / "README.md").write_text("x", encoding="utf-8")
    _run_git(["add", "-A"], path)
    _run_git(["commit", "-m", "init"], path)


def _add_worktree(main: Path, wt: Path, branch: str) -> None:
    _run_git(["worktree", "add", "-b", branch, str(wt)], main)


@requires_git
def test_working_root_signal1_git_dash_c(tmp_path: Path):
    # ① `git -C <wt> commit` → W = that worktree's toplevel.
    main = tmp_path / "repo"
    _init_repo(main)
    wt = tmp_path / "repo-wt"
    _add_worktree(main, wt, "feature/x")
    got = vp.working_root(project_dir=main, hook_cwd=None, command=f'git -C {wt} commit -m "m"')
    assert got == wt.resolve()


@requires_git
def test_working_root_signal2_cd_prefix(tmp_path: Path):
    # ② `cd <wt> && git commit` → W = that worktree.
    main = tmp_path / "repo"
    _init_repo(main)
    wt = tmp_path / "repo-wt"
    _add_worktree(main, wt, "feature/x")
    got = vp.working_root(project_dir=main, hook_cwd=None, command=f"cd {wt} && git commit -m m")
    assert got == wt.resolve()


@requires_git
def test_working_root_signal3_cwd_bijection(tmp_path: Path):
    # ③ only hook cwd → learn branch B → the unique `git worktree list` entry with B.
    main = tmp_path / "repo"
    _init_repo(main)
    wt = tmp_path / "repo-wt"
    _add_worktree(main, wt, "feature/x")
    got = vp.working_root(project_dir=main, hook_cwd=str(wt), command=None)
    assert got == wt.resolve()


@requires_git
def test_working_root_signal4_fallback_main(tmp_path: Path):
    # ④ no directional signal → project_dir (current behavior).
    main = tmp_path / "repo"
    _init_repo(main)
    got = vp.working_root(project_dir=main, hook_cwd=None, command="git commit -m m")
    assert got == main.resolve()


@requires_git
def test_working_root_detached_returns_main(tmp_path: Path):
    # a detached-HEAD worktree has no branch → bijection fails → FAIL-OPEN to main.
    main = tmp_path / "repo"
    _init_repo(main)
    wt = tmp_path / "repo-wt"
    _add_worktree(main, wt, "feature/x")
    _run_git(["-C", str(wt), "checkout", "--detach"], main)
    got = vp.working_root(project_dir=main, hook_cwd=str(wt), command=None)
    assert got == main.resolve()


@requires_git
def test_working_root_different_repo_returns_main(tmp_path: Path):
    # `git -C <other-repo>` where other is a *different* repo → common-dir differs → main.
    main = tmp_path / "repo"
    _init_repo(main)
    other = tmp_path / "other"
    _init_repo(other)
    got = vp.working_root(project_dir=main, hook_cwd=None, command=f"git -C {other} commit -m m")
    assert got == main.resolve()


@requires_git
def test_working_root_sibling_prefix_same_repo(tmp_path: Path):
    # prefix trap: `…/kit` vs `…/kit-feature` (sibling, path prefix overlap) — a naive
    # startswith would (mis)judge, but common-dir equality correctly keeps same-repo.
    main = tmp_path / "kit"
    _init_repo(main)
    wt = tmp_path / "kit-feature"
    _add_worktree(main, wt, "feature/y")
    got = vp.working_root(project_dir=main, hook_cwd=None, command=f"git -C {wt} commit -m m")
    assert got == wt.resolve()


@requires_git
def test_working_root_sibling_prefix_different_repo(tmp_path: Path):
    # prefix trap, negative: `…/kit` vs `…/kit-other` share a prefix but are different repos —
    # common-dir equality correctly rejects (naive startswith would falsely accept).
    main = tmp_path / "kit"
    _init_repo(main)
    other = tmp_path / "kit-other"
    _init_repo(other)
    got = vp.working_root(project_dir=main, hook_cwd=None, command=f"git -C {other} commit -m m")
    assert got == main.resolve()
