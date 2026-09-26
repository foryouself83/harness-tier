"""Behavior spec for the shared finalize-guard shell block every release workflow carries.

Pins two things: the block is byte-identical (indentation aside) across all six workflows, and
the block itself — run against a real git repo, not a mock — blocks a stable release whose
tag already exists or that sits below the latest stable tag, and passes one above it.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent.parent
BASH = shutil.which("bash")

BEGIN = "# >>> finalize-guard"
END = "# <<< finalize-guard"

_WORKFLOWS = [
    "github/release.python-semantic-release.workflow.example.yml",
    "github/release.semantic-release.workflow.example.yml",
    "github/release.gitversion.workflow.example.yml",
    "github/release.jreleaser.workflow.example.yml",
    "github/release.cargo-release.workflow.example.yml",
    ".github/workflows/release.yml",
]


def _block(path: Path) -> list[str]:
    """Return the block's lines (`# >>> finalize-guard` through `# <<< finalize-guard`,
    inclusive), CRLF-normalized and each line stripped — a plain indentation difference is not
    a divergence."""
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
        assert block == first, f"{rel} carries a different finalize-guard block"


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def _seed_repo(tmp_path: Path, tags: list[str]) -> Path:
    """A real repo: one commit carrying every tag the fixture lists."""
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "-q")
    (repo / "f.txt").write_text("1\n", encoding="utf-8")
    _git(repo, "add", "f.txt")
    _git(repo, "-c", "user.email=t@t", "-c", "user.name=T", "commit", "-qm", "chore: seed")
    for tag in tags:
        _git(repo, "tag", tag)
    return repo


_CASES = [
    # tags present, whether the guard lets STABLE=1.1.1 through, what the error names
    pytest.param(["v1.1.0", "v1.1.1"], False, "already exists", id="tag-exists-blocks"),
    pytest.param(["v1.1.0", "v1.2.0"], False, "below the latest", id="higher-stable-blocks"),
    pytest.param(["v1.1.10"], False, "below the latest", id="higher-stable-sorts-by-version"),
    pytest.param(["v1.1.0", "v1.1.1-rc.3", "v1.2.0-rc.1"], True, None, id="above-latest-passes"),
    pytest.param([], True, None, id="no-tag-passes"),
]


@pytest.mark.skipif(
    sys.platform == "win32" or not BASH,
    reason="needs a real bash + git; CI (ubuntu) and WSL are the authority, not Windows",
)
@pytest.mark.parametrize("tags, expect_ok, reason", _CASES)
def test_block_runs_against_a_real_repo(tmp_path, tags, expect_ok, reason):
    repo = _seed_repo(tmp_path, tags)
    block = "\n".join(_block(ROOT / ".github/workflows/release.yml"))
    script = 'STABLE="1.1.1"\n' + block + '\necho "GUARD_PASSED=1"\n'
    result = subprocess.run(
        [BASH, "-c", script], cwd=repo, env=os.environ.copy(), capture_output=True, text=True
    )
    if expect_ok:
        assert result.returncode == 0, result.stderr
        assert "GUARD_PASSED=1" in result.stdout, result.stdout
    else:
        assert result.returncode != 0, result.stdout
        assert "::error::" in result.stderr, result.stderr
        assert "v1.1.1" in result.stderr, result.stderr
        assert reason in result.stderr, result.stderr
        assert "Re-promote staging" in result.stderr, result.stderr
