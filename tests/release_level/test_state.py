"""`bump_version.py state`: the release-state probe /release-commit runs with no arguments.

The skill pre-approves it as one exact `allowed-tools` rule, which a `$(git tag --list)`
argument cannot be — so the probe reads the tag list itself.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import bump_version
from scripts.bump_version import main

PENDING = "v1.0.0\nv1.1.0-rc.1\nv1.1.0-rc.2"
RELEASED = PENDING + "\nv1.1.0"


def test_state_names_the_pending_rc_and_every_level(capsys):
    assert main(["state", "--tags", PENDING]) == 0
    assert capsys.readouterr().out.splitlines() == [
        "pending: v1.1.0-rc.2",
        "continue: 1.1.0-rc.3",
        "patch: 1.1.1-rc.1",
        "minor: 1.2.0-rc.1",
        "major: 2.0.0-rc.1",
    ]


def test_state_without_a_pending_rc_reports_continue_as_failing(capsys):
    assert main(["state", "--tags", RELEASED]) == 0
    out = capsys.readouterr().out.splitlines()
    assert out[0] == "pending: none"
    assert out[1].startswith("continue: fails — ") and "no pending rc" in out[1]
    assert out[2:] == ["patch: 1.1.1-rc.1", "minor: 1.2.0-rc.1", "major: 2.0.0-rc.1"]


def test_state_reads_the_tag_list_from_git_when_none_is_given(monkeypatch, capsys):
    monkeypatch.setattr(bump_version, "_git_tags", lambda: PENDING.splitlines())
    assert main(["state"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "pending: v1.1.0-rc.2"


def test_state_fails_when_git_cannot_list_tags(monkeypatch, capsys):
    def broken():
        raise OSError("git: not found")

    monkeypatch.setattr(bump_version, "_git_tags", broken)
    assert main(["state"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "bump_version: cannot list tags" in captured.err


@pytest.mark.skipif(shutil.which("git") is None, reason="needs git")
def test_git_tags_reads_a_real_repository(tmp_path, monkeypatch):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)

    git("init", "-q")
    git("-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "c")
    git("tag", "v1.0.0")
    git("tag", "v1.1.0-rc.1")
    monkeypatch.chdir(tmp_path)
    assert sorted(bump_version._git_tags()) == ["v1.0.0", "v1.1.0-rc.1"]


def test_git_tags_raises_outside_a_repository(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path.parent))
    with pytest.raises(OSError):
        bump_version._git_tags()


def test_state_survives_a_non_utf8_stdout():
    # The Windows host this runs on may carry a cp949 stdout with PYTHONUTF8 unset; the
    # `fails — …` line is on every first promotion's output.
    env = {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "cp949"}
    script = Path(__file__).resolve().parents[2] / "scripts" / "bump_version.py"
    r = subprocess.run(
        [sys.executable, str(script), "state", "--tags", "v1.0.0"],
        capture_output=True,
        env=env,
    )
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    out = r.stdout.decode("utf-8").splitlines()
    assert out[0] == "pending: none" and out[1].startswith("continue: fails — ")
