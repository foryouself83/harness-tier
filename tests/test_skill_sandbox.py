import subprocess
import sys
from pathlib import Path

import scripts.skill_sandbox as sandbox
from tests._non_utf8 import cp949_stdio_env

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "skill_sandbox.py"


def test_prints_a_scenario_in_utf8_on_a_cp949_host(tmp_path: Path):
    # Invariant #2. Scenario prose carries em dashes, which cp949 cannot encode, and the
    # printed prompt is read through a pipe, where stdout takes the locale codec. `why` is
    # prose free to reword without a re-measure, so the case reads it rather than a copy.
    why = sandbox.BY_NAME["custom-testdir"].why
    assert not why.isascii(), "the case needs a character outside ASCII to print"
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "custom-testdir", "--out-dir", str(tmp_path)],
        env=cp949_stdio_env(),
        capture_output=True,
    )
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert why.encode() in r.stdout


def _git(cwd: Path, *args: str) -> str:
    r = subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True, encoding="utf-8"
    )
    return r.stdout


def test_uncommitted_files_land_after_the_seed_commit(tmp_path: Path):
    """A scenario measuring `commit these changes` needs changes to commit: `git` alone
    commits everything it wrote, leaving a clean tree the prompt cannot be answered from."""
    scenario = sandbox.Scenario(
        name="dirty",
        skill="flow",
        why="w",
        prompt="p",
        expect=[],
        reject=[],
        files={"a.txt": "one\n"},
        git=True,
        uncommitted={"a.txt": "two\n", "b.txt": "new\n"},
    )
    built = sandbox.build(scenario, tmp_path)
    assert _git(built, "show", "HEAD:a.txt") == "one\n"
    # Bytes, not read_text: the write goes through newline="" so the fixture carries LF on
    # Windows too. Read back as text, a CRLF write would normalize away and read as a pass,
    # while git on a host without autocrlf would see the whole file rewritten.
    assert (built / "a.txt").read_bytes() == b"two\n"
    status = _git(built, "status", "--porcelain")
    assert " M a.txt" in status and "?? b.txt" in status


def test_uncommitted_without_git_still_writes_the_files(tmp_path: Path):
    scenario = sandbox.Scenario(
        name="nogit",
        skill="flow",
        why="w",
        prompt="p",
        expect=[],
        reject=[],
        uncommitted={"a.txt": "only\n"},
    )
    built = sandbox.build(scenario, tmp_path)
    assert (built / "a.txt").read_text(encoding="utf-8") == "only\n"
