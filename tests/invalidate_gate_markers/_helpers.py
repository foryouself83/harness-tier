"""Shared fixtures-free helpers: the bash probe, payload builders, and repo scaffolding."""

import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent.parent  # tests/<pkg>/_helpers.py

SCRIPT = REPO / "hooks" / "invalidate-gate-markers.sh"

GIT_BASH = (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe")


def _repo_bash() -> str | None:
    """A bash that can see the repo path (Git Bash on Windows / native bash on POSIX).

    PATH order is the shell's, so on Windows a bare `bash` is usually the System32 WSL stub,
    which cannot open a C:/… path — probe the candidate against a file that must exist and fall
    back to the known Git Bash locations. None → no usable bash, and these tests skip rather
    than report a green they never earned."""
    probe = f"{REPO.as_posix()}/hooks/invalidate-gate-markers.sh"
    which = shutil.which("bash")
    for bash in (which, *GIT_BASH):
        if not bash or not (bash == which or Path(bash).exists()):
            continue
        try:
            probe_run = subprocess.run(
                [bash, "-c", f'test -f "{probe}"'], capture_output=True, timeout=10
            )
            if probe_run.returncode == 0:  # captured: a WSL stub's complaint is not test output
                return bash
        except Exception:
            continue
    return None


BASH = _repo_bash()

pytestmark = pytest.mark.skipif(BASH is None, reason="a repo-visible bash is required")

NL = chr(10)

MARKERS = ("review.done", "doc-sync.done")

KEPT = ("bump.done", "security.done")


def payload(file_path: str | None, key: str = "file_path") -> str:
    body: dict[str, object] = {"hook_event_name": "PostToolUse", "tool_name": "Edit"}
    if file_path is not None:
        body["tool_input"] = {key: file_path}
    return json.dumps(body)


def repo(root: Path, *, evidence: bool = True) -> Path:
    """A tree the gate would judge: a repo root, and the evidence a gate run left in it. `.git`
    is what bounds the hook's walk, so a fixture without one is not a tree at all — and
    `evidence=False` means no evidence dir at all, not an empty one: an empty one stops a walk
    that is looking for evidence dirs, which is the very thing some of these tests must see."""
    (root / ".git").mkdir(parents=True, exist_ok=True)
    if evidence:
        flow(root).mkdir(parents=True, exist_ok=True)
        for name in MARKERS:
            (flow(root) / name).touch()
    return root


def worktree_of(main: Path, root: Path, *, gitdir: str | None = None, eol: str = chr(10)) -> Path:
    """A linked worktree: its `.git` is a FILE pointing into the main repo's common dir. That
    pointer is the only thing separating two views of one repo from two repos, and the hook has
    to void both views — the gate cannot always tell which one a commit belongs to.

    `gitdir` overrides the pointer's spelling (git writes a relative one under
    `worktree.useRelativePaths`), and `eol` its ending — a file that stops without one is still
    a file git wrote through."""
    root.mkdir(parents=True, exist_ok=True)
    target = gitdir or f"{main.as_posix()}/.git/worktrees/{root.name}"
    (root / ".git").write_text(f"gitdir: {target}{eol}", encoding="utf-8")
    flow(root).mkdir(parents=True, exist_ok=True)
    for name in MARKERS:
        (flow(root) / name).touch()
    return root


def run(project: Path | None, stdin: str) -> subprocess.CompletedProcess[str]:
    # The real environment minus the one variable under test: a hand-built env drops what bash
    # itself needs on Windows (SYSTEMROOT, TEMP), and the hook would fail for a reason no
    # assertion here is about.
    env = dict(os.environ)
    env.pop("CLAUDE_PROJECT_DIR", None)
    if project is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project)
    return subprocess.run(
        [BASH, str(SCRIPT)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def flow(project: Path) -> Path:
    return project / ".claude" / "harness-tier" / ".flow"
