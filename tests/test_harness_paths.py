"""Behavior spec for the shared helper _harness_paths — path SSOT, fallback helpers,
encoding defenses.

If this module breaks, path resolution in every gate script breaks along with it, so the
consolidated behavior is pinned here in one place (previously each script carried its own
host_root/force_utf8_io and tested it separately).
"""

import subprocess
from pathlib import Path

import pytest

import scripts._harness_paths as vp


def test_path_segment_constants():
    # the host write root and its subcategories are all gathered under
    # .claude/harness-tier/ (CLAUDE.md).
    assert vp.HARNESS_DIR == ".claude/harness-tier"
    assert vp.SCRIPTS_DIR == ".claude/harness-tier/scripts"
    assert vp.CONFIG_DIR == ".claude/harness-tier/config"
    assert vp.FLOW_DIR == ".claude/harness-tier/.flow"


def test_filename_constants():
    assert vp.CONFIG_FILENAME == "flow-config.yaml"
    assert vp.TIERS_FILENAME == "flow-tiers.yaml"


def test_gate_contract_constants():
    # Invariant #3: block = exit 2. Runtime gates and tier labels are byte-match targets
    # against yaml keys.
    assert vp.BLOCK_EXIT_CODE == 2
    assert "security-scan" in vp.RUNTIME_GATES
    assert vp.STAGING_TIER == "staging"
    assert vp.RELEASE_TIER == "release"


def test_path_helpers_compose_from_root(tmp_path: Path):
    assert vp.harness_dir(tmp_path) == tmp_path / ".claude" / "harness-tier"
    assert vp.config_dir(tmp_path) == tmp_path / ".claude" / "harness-tier" / "config"
    assert vp.flow_dir(tmp_path) == tmp_path / ".claude" / "harness-tier" / ".flow"
    assert vp.config_path(tmp_path) == (
        tmp_path / ".claude" / "harness-tier" / "config" / "flow-config.yaml"
    )


def test_host_root_prefers_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert vp.host_root() == tmp_path.resolve()


def test_host_root_fallback_no_crash(monkeypatch, tmp_path: Path):
    # env unset + git failure → cwd fallback when the marker (.claude) lookup fails
    # (no IndexError/crash).
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)

    def boom(*_a, **_k):
        raise OSError("no git")

    monkeypatch.setattr(vp.subprocess, "run", boom)
    result = vp.host_root()
    assert isinstance(result, Path)  # path without marker → cwd fallback (no crash)


def test_plugin_root_prefers_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    assert vp.plugin_root() == tmp_path


def test_plugin_root_fallback_is_scripts_parent(monkeypatch):
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    # _harness_paths.py lives in scripts/, so the fallback is its parent (the plugin root).
    assert vp.plugin_root() == Path(vp.__file__).resolve().parent.parent


def test_force_utf8_io_sets_pythonutf8(monkeypatch):
    # set PYTHONUTF8 so child python processes inherit the encoding (reinforces Invariant #2).
    monkeypatch.delenv("PYTHONUTF8", raising=False)
    vp.force_utf8_io()
    assert vp.os.environ.get("PYTHONUTF8") == "1"


# ── working_root: worktree-aware detection (branch-key ladder) ────────────────────
# The gate assumes "working tree = one CLAUDE_PROJECT_DIR". working_root detects the
# worktree where the commit actually runs, so git status/diff/tier-marker/module-lint
# all read that worktree. Non-worktree / uncertain → project_dir (FAIL-OPEN, Invariant #1).


def test_dir_from_command_dash_c():
    # ① `git -C <dir>` — the deterministic top-of-ladder signal (git overrides cwd).
    assert vp._dir_from_command('git -C /a/b commit -m "x"') == "/a/b"


def test_dir_from_command_dash_c_quoted():
    # a path with spaces is preserved via quote handling (conservative shell-lite parse).
    assert vp._dir_from_command('git -C "/a b/c" commit -m "x"') == "/a b/c"


def test_dir_from_command_cd_prefix():
    # ② leading `cd <dir> && … git commit`.
    assert vp._dir_from_command("cd /a/b && git commit -m 'x'") == "/a/b"


def test_dir_from_command_none_without_signal():
    assert vp._dir_from_command("git commit -m 'x'") is None
    assert vp._dir_from_command(None) is None


def test_dir_from_command_ignores_dash_c_inside_message():
    # `-C` inside the commit message (after the `commit` subcommand) must not be picked up
    # as a directory — only the global-options region before `commit` is scanned.
    assert vp._dir_from_command('git commit -m "use -C /wrong"') is None


def test_parse_worktree_list_blocks_and_detached():
    text = (
        "worktree /main\nHEAD abc\nbranch refs/heads/main\n\n"
        "worktree /wt-feat\nHEAD def\nbranch refs/heads/feature/x\n\n"
        "worktree /wt-detached\nHEAD 123\ndetached\n"
    )
    entries = vp._parse_worktree_list(text)
    assert ("/main", "main") in entries
    assert ("/wt-feat", "feature/x") in entries
    assert ("/wt-detached", None) in entries  # detached → no branch


def _has_git() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


requires_git = pytest.mark.skipif(not _has_git(), reason="git not available")


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
