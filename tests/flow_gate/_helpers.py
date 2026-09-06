import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

# ── the command verdict, and the worktree it names (--classify) ──────────────────
# One authority for what the hook's command is: the runner's own filter decides only whether
# to spawn this, and every question with an answer — commits? merges? which worktree? — is
# answered here. The gate also assumes working tree = CLAUDE_PROJECT_DIR (fixed at session
# start), so a commit run in a git worktree is detected by branch-key and ROOT re-pointed to
# it. These pin both halves end-to-end.


def _git_ok() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


requires_git = pytest.mark.skipif(not _git_ok(), reason="git not available")


def _rg(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _rg(["init", "-b", "main"], path)
    _rg(["config", "user.email", "t@e.st"], path)
    _rg(["config", "user.name", "Test"], path)
    (path / "README.md").write_text("x", encoding="utf-8")
    _rg(["add", "-A"], path)
    _rg(["commit", "-m", "init"], path)


def _repo_bash() -> str | None:
    """A bash that can see the repo path (Git Bash on Windows / native bash on POSIX).

    Windows PATH often resolves ``bash`` to WSL, which cannot access ``C:/…`` paths, so probe the
    candidate and fall back to known Git Bash locations. None → no usable bash (skip)."""
    repo = Path(__file__).resolve().parent.parent.parent
    probe = f"{repo.as_posix()}/scripts/precommit-runner.sh"
    which = shutil.which("bash")
    candidates = [
        which,
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ]
    for bash in candidates:
        if not bash or not (bash == which or Path(bash).exists()):
            continue
        try:
            r = subprocess.run([bash, "-c", f'test -f "{probe}"'], capture_output=True, timeout=10)
            if r.returncode == 0:
                return bash
        except Exception:
            continue
    return None


_REPO_BASH = _repo_bash()
requires_bash_git = pytest.mark.skipif(
    not (_REPO_BASH and _git_ok()), reason="a repo-visible bash + git required"
)


def _classify_worktree_module(wt: Path) -> None:
    """Give a worktree a dev tier marker + evidence and one module covering a staged file."""
    flow = wt / ".claude" / "harness-tier" / ".flow"
    flow.mkdir(parents=True)
    (flow / "tier").write_text("dev:feature/x", encoding="utf-8")
    (flow / "review.done").touch()
    (flow / "doc-sync.done").touch()
    cfg = wt / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-config.yaml").write_text(
        "modules:\n  - name: api\n    path: services/api/\n"
        '    checks:\n      lint: "echo LINT_RAN"\n',
        encoding="utf-8",
    )
    (wt / "services" / "api").mkdir(parents=True)
    (wt / "services" / "api" / "a.py").write_text("x = 1\n", encoding="utf-8")
    _rg(["add", "services/api/a.py"], wt)


def _run_runner(
    main: Path, command: str, dryrun: bool = True, plugin_root: Path | None = None
) -> subprocess.CompletedProcess[str]:
    repo = Path(__file__).resolve().parent.parent.parent
    env = {
        **os.environ,
        "CLAUDE_PROJECT_DIR": str(main),
        "CLAUDE_PLUGIN_ROOT": (plugin_root or repo).as_posix(),
        "HARNESS_PRECOMMIT_DRYRUN": "1" if dryrun else "0",
        "PYTHONIOENCODING": "utf-8",
    }
    hook = json.dumps({"cwd": str(main), "tool_input": {"command": command}})
    # bash eats backslashes in an argv path (C:\a\b → C:ab), so pass a forward-slash path.
    return subprocess.run(
        [_REPO_BASH, f"{repo.as_posix()}/scripts/precommit-runner.sh"],
        input=hook,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


# ── wiki runtime gate (its own --wiki-check step, NOT a module command) ───────────
def _wiki_host(tmp_path: Path) -> Path:
    cfgdir = tmp_path / ".claude" / "harness-tier" / "config"
    cfgdir.mkdir(parents=True)
    (cfgdir / "flow-config.yaml").write_text(
        "wiki:\n  enable: true\n  root: docs/\n", encoding="utf-8"
    )
    (tmp_path / "docs").mkdir()
    return tmp_path


def _doc_style_host(tmp_path: Path, prose: str, config: str = "") -> Path:
    """A repo whose pending commit changes one document carrying `prose`."""
    _init_repo(tmp_path)
    cfgdir = tmp_path / ".claude" / "harness-tier" / "config"
    cfgdir.mkdir(parents=True)
    (cfgdir / "flow-config.yaml").write_text(
        config or "doc_style:\n  enable: true\n", encoding="utf-8"
    )
    (tmp_path / "doc.md").write_text(prose, encoding="utf-8")
    _rg(["add", "doc.md"], tmp_path)
    return tmp_path
