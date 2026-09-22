"""Behavior spec for the shared next-version shell block every release workflow carries.

Pins two things: the block is byte-identical (indentation aside) across all six workflows, and
the block itself — run against a real git repo, not a mock — resolves the same cases
scripts/bump_version.py's own unit tests cover for `next`.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
BASH = shutil.which("bash")

BEGIN = "# >>> next-version"
END = "# <<< next-version"

_WORKFLOWS = [
    "github/release.python-semantic-release.workflow.example.yml",
    "github/release.semantic-release.workflow.example.yml",
    "github/release.gitversion.workflow.example.yml",
    "github/release.jreleaser.workflow.example.yml",
    "github/release.cargo-release.workflow.example.yml",
    ".github/workflows/release.yml",
]


def _block(path: Path) -> list[str]:
    """Return the block's lines (`# >>> next-version` through `# <<< next-version`, inclusive),
    CRLF-normalized and each line stripped — a plain indentation difference is not a divergence."""
    text = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    lines = text.split("\n")
    start = next(i for i, line in enumerate(lines) if line.strip().startswith(BEGIN))
    end = next(i for i, line in enumerate(lines) if line.strip().startswith(END))
    return [line.strip() for line in lines[start : end + 1]]


def test_every_release_workflow_carries_the_same_block():
    blocks = {rel: _block(ROOT / rel) for rel in _WORKFLOWS}
    first = blocks[_WORKFLOWS[0]]
    assert first, "the block must not be empty"
    for rel, block in blocks.items():
        assert block == first, f"{rel} carries a different next-version block"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _seed_repo(tmp_path: Path, tags: list[str], message: str) -> Path:
    """A real repo: one commit tagged as the fixture wants, then a second commit carrying
    `message` — the one the block's `git log -1 --pretty=%B` reads."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "f.txt").write_text("1\n", encoding="utf-8")
    _git(repo, "add", "f.txt")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=T", "commit", "-qm", "chore: seed")
    for tag in tags:
        _git(repo, "tag", tag)
    (repo / "f.txt").write_text("2\n", encoding="utf-8")
    _git(repo, "add", "f.txt")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=T", "commit", "-qm", message)
    return repo


_PENDING = ["v1.0.0", "v1.1.0-rc.1"]
_RELEASED = ["v1.0.0", "v1.1.0-rc.1", "v1.1.0"]
# An rc series later stable releases left behind: finishing it would be a downgrade.
_ORPHAN = ["v0.2.3-rc.5", "v0.3.0", "v0.4.0"]

_CASES = [
    # tags, trailer level (None = no trailer), whether the block exits 0, expected $NEXT
    pytest.param(_PENDING, "continue", True, "1.1.0-rc.2", id="continue-pending-rc"),
    pytest.param(_PENDING, "patch", True, "1.1.1-rc.1", id="patch"),
    pytest.param(_PENDING, "minor", True, "1.2.0-rc.1", id="minor"),
    pytest.param(_PENDING, "major", True, "2.0.0-rc.1", id="major"),
    pytest.param(_RELEASED, "continue", False, None, id="continue-without-pending-rc-fails"),
    pytest.param(_PENDING, "pach", False, None, id="invalid-level-fails"),
    pytest.param(_PENDING, None, True, "auto", id="no-trailer-is-auto"),
    pytest.param(_ORPHAN, "continue", False, None, id="continue-superseded-rc-fails"),
    pytest.param(_ORPHAN, "patch", True, "0.4.1-rc.1", id="patch-past-superseded-rc"),
]


@pytest.mark.skipif(
    sys.platform == "win32" or not BASH,
    reason="needs a real bash + python3; CI (ubuntu) and WSL are the authority, not Windows",
)
@pytest.mark.parametrize("tags, level, expect_ok, expected", _CASES)
def test_block_runs_against_a_real_repo(tmp_path, tags, level, expect_ok, expected):
    message = "feat: something\n" if level is None else f"feat: something\n\nRelease-Level: {level}\n"
    repo = _seed_repo(tmp_path, tags, message)
    block = "\n".join(_block(ROOT / ".github/workflows/release.yml"))
    script = block + '\necho "NEXT=$NEXT"\n'
    env = {**os.environ, "HARNESS_SCRIPTS": str(ROOT / "scripts"), "AUTO_LEVEL": ""}
    result = subprocess.run(
        [BASH, "-c", script], cwd=repo, env=env, capture_output=True, text=True
    )
    if expect_ok:
        assert result.returncode == 0, result.stderr
        assert f"NEXT={expected}" in result.stdout, result.stdout
    else:
        assert result.returncode != 0, result.stdout
