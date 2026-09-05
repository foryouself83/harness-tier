"""How much of the payload the hook reads, and what it does past that."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.invalidate_gate_markers._helpers import (
    BASH,
    MARKERS,
    SCRIPT,
    flow,
    payload,
    repo,
)

pytestmark = pytest.mark.skipif(BASH is None, reason="a repo-visible bash is required")


def test_the_payload_is_read_without_the_pipeline(project: Path, tmp_path: Path):
    """This runs on every edit, and on Windows a spawned process costs more than the work it
    does - a repo that never installed the harness paid a whole `cat | grep | head | sed`
    pipeline to learn it had nothing to delete. Four of those five are gone; `head` stays,
    because bash's own bounded read is 4.1-and-later and macOS ships 3.2.

    The edit lands in ANOTHER repo, which is what makes the assertion discriminating: a hook
    that could not read the path gives up and voids THIS project (the safe direction), so a
    test watching only the edited repo would pass either way."""
    other = repo(tmp_path / "other")
    stubs = tmp_path / "stubs"
    stubs.mkdir()
    for name in ("grep", "sed", "tr", "cat", "awk", "cut"):
        stub = stubs / name
        stub.write_text(
            "#!/bin/sh" + chr(10) + "exit 7" + chr(10), encoding="utf-8", newline=chr(10)
        )
        stub.chmod(0o755)
    env = dict(os.environ)
    env["CLAUDE_PROJECT_DIR"] = str(project)
    env["PATH"] = str(stubs) + os.pathsep + env.get("PATH", "")
    edited = other / "src" / "a.py"
    edited.parent.mkdir(parents=True, exist_ok=True)
    edited.write_text("x", encoding="utf-8")
    proc = subprocess.run(
        [BASH, str(SCRIPT)],
        input=payload(str(edited)),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )
    assert proc.returncode == 0, (proc.returncode, proc.stdout, proc.stderr)
    for marker in MARKERS:
        assert not (flow(other) / marker).exists(), f"{marker}: the edited repo kept it"
        assert (flow(project) / marker).exists(), (
            f"{marker}: this project was voided, so the path was never read"
        )


def _padded_payload(edited: Path, pad: int) -> str:
    """A real PostToolUse payload with `pad` bytes of filler ahead of `tool_input`."""
    return json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "padding": "x" * pad,
            "tool_input": {"file_path": str(edited), "content": "y"},
        }
    )


def test_a_path_past_the_read_cap_is_a_payload_with_no_path(project: Path, tmp_path: Path):
    """The cap is only a cap if something notices when it moves. Raising it changes exactly one
    observable thing — whether a path sitting beyond it is found — so that is what is asserted
    here, rather than a wall-clock budget an unbounded read also meets.

    The edit lands in ANOTHER repo, so the two halves separate: unread, the hook cannot place
    the edit and voids the session's project instead, leaving the edited repo's markers
    standing. That is the unsafe half of the truncation, and it is why the cap sits three orders
    of magnitude past where any real payload puts the path."""
    other = repo(tmp_path / "other")
    edited = other / "src" / "a.py"
    edited.parent.mkdir(parents=True, exist_ok=True)
    edited.write_text("x", encoding="utf-8")

    proc = subprocess.run(
        [BASH, str(SCRIPT)],
        input=_padded_payload(edited, 70000),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
        timeout=30,
    )
    assert proc.returncode == 0, (proc.returncode, proc.stderr)
    for name in MARKERS:
        assert not (flow(project) / name).exists(), f"{name}: the path was read past the cap"
        assert (flow(other) / name).exists(), f"{name}: the edited repo was reached anyway"


def test_a_path_inside_the_read_cap_is_still_found(project: Path, tmp_path: Path):
    """The other side of the same boundary, so the test above cannot be satisfied by a hook that
    reads no payload at all."""
    other = repo(tmp_path / "other")
    edited = other / "src" / "a.py"
    edited.parent.mkdir(parents=True, exist_ok=True)
    edited.write_text("x", encoding="utf-8")

    proc = subprocess.run(
        [BASH, str(SCRIPT)],
        input=_padded_payload(edited, 30000),
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
        timeout=30,
    )
    assert proc.returncode == 0, (proc.returncode, proc.stderr)
    for name in MARKERS:
        assert not (flow(other) / name).exists(), f"{name}: the edited repo kept it"
        assert (flow(project) / name).exists(), f"{name}: the project was voided instead"


def test_a_huge_payload_still_finishes_inside_the_hook_s_budget(project: Path):
    """Separate from the cap: whatever the hook does per edit has to fit the 10s hooks.json
    gives it, because a killed hook leaves the markers standing. The timeout below is that
    budget. This does not pin the cap - the test above does - it pins the cost."""
    edited = project / "src" / "a.py"
    body = json.dumps(
        {
            "hook_event_name": "PostToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": str(edited), "content": "x" * (16 * 1024 * 1024)},
        }
    )
    proc = subprocess.run(
        [BASH, str(SCRIPT)],
        input=body,
        capture_output=True,
        text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(project)},
        timeout=10,
    )
    assert proc.returncode == 0, (proc.returncode, proc.stderr)
    for name in MARKERS:
        assert not (flow(project) / name).exists(), name
