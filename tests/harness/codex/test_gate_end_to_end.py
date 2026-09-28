"""The Codex gate as a consumer gets it: `/flow-init`'s copy, the registered command string, and
the runner behind the wrapper, with no Claude Code environment."""

import json
import os
import subprocess
from pathlib import Path

import pytest

import scripts.flow_init_setup as fis
from scripts.harness.codex import install
from tests.flow_init._helpers import PLUGIN
from tests.invalidate_gate_markers._helpers import BASH

pytestmark = pytest.mark.skipif(BASH is None, reason="a repo-visible bash is required")


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def test_the_registered_command_denies_an_unclassified_commit(tmp_path):
    host = tmp_path / "host"
    host.mkdir()
    _git(host, "init", "-q")
    _git(host, "checkout", "-q", "-b", "feature/e2e")
    fis.copy_artifacts(PLUGIN, host, ["claude", "codex"])
    install.register(host)
    registered = json.loads((host / ".codex/hooks.json").read_text(encoding="utf-8"))
    hook = registered["hooks"]["PreToolUse"][-1]["hooks"][0]
    assert hook == install.GATE_HOOK
    sub = host / "src"
    sub.mkdir()
    payload = {
        "cwd": str(sub),
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_input": {"command": "git commit -m x"},
    }
    env = {k: v for k, v in os.environ.items() if not k.startswith("CLAUDE_")}
    run = subprocess.run(
        [BASH, "-c", hook["command"]],
        cwd=sub,
        input=json.dumps(payload).encode(),
        capture_output=True,
        env=env,
        timeout=120,
    )
    assert run.returncode == 0, run.stderr.decode(errors="replace")
    decision = json.loads(run.stdout.decode("utf-8").strip())
    output = decision["hookSpecificOutput"]
    assert output["permissionDecision"] == "deny", decision
    # `permissionDecision == "deny"` alone would also pass for a wrapper that denies every
    # commit, or one that hit Exception 1 (missing python3/PyYAML) — pin the actual reason
    # instead: the Exception 2 unclassified-commit text flow_gate_check.py's main() prints,
    # `flow 미진입: 분류되지 않은 커밋입니다. ...` (see scripts/flow_gate_check.py), normalized
    # for CRLF in case the host's own line-ending handling ever touches this string in transit.
    reason = output["permissionDecisionReason"].replace("\r\n", "\n").replace("\r", "\n")
    assert "분류되지 않은 커밋" in reason, reason
