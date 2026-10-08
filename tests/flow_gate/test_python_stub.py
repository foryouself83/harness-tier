"""A python3 that is the Microsoft Store's app execution alias, seen by the gate and check-deps."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.flow_gate._helpers import _REPO_BASH, _init_repo, _run_runner, requires_bash_git

REPO = Path(__file__).resolve().parent.parent.parent
posix_only = pytest.mark.skipif(sys.platform == "win32", reason="a fake python3 on a POSIX PATH")


def _stub_path(tmp_path: Path) -> str:
    """PATH with a python3 that runs no python, in a directory named like the Store's."""
    stub = tmp_path / "WindowsApps"
    stub.mkdir()
    (stub / "python3").write_text("#!/bin/sh\nexit 9009\n", encoding="utf-8")
    (stub / "python3").chmod(0o755)
    return f"{stub}{os.pathsep}{os.environ['PATH']}"


@posix_only
@requires_bash_git
def test_the_gate_names_the_store_alias(tmp_path, monkeypatch):
    main = tmp_path / "main"
    main.mkdir()
    _init_repo(main)
    monkeypatch.setenv("PATH", _stub_path(tmp_path))
    r = _run_runner(main, "git commit -m x")
    assert r.returncode == 2
    assert "Microsoft Store" in r.stderr


@posix_only
def test_check_deps_names_the_store_alias(tmp_path):
    env = {**os.environ, "PATH": _stub_path(tmp_path)}
    r = subprocess.run(
        [_REPO_BASH or "bash", str(REPO / "scripts" / "check-deps.sh")],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert r.returncode == 1
    assert "Microsoft Store" in r.stdout + r.stderr
