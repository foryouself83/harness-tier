"""Codex needs its own manifest, marketplace entry and hooks file — a root plugin.json or a
hooks path without "./" makes Codex fall back to auto-registering hooks/hooks.json (the Claude
one), silently disabling every hook this plugin ships for Codex."""

import json
import re
import sys
from pathlib import Path

import pytest

from tests.invalidate_gate_markers._helpers import BASH  # a repo-visible bash (Git Bash on Windows)

REPO = Path(__file__).resolve().parents[3]
CODEX = json.loads((REPO / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
CLAUDE = json.loads((REPO / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
HOOKS = json.loads((REPO / "hooks/codex/hooks.json").read_text(encoding="utf-8"))


def test_versions_and_names_match():
    assert CODEX["name"] == CLAUDE["name"] and CODEX["version"] == CLAUDE["version"]


def test_hooks_field_points_at_the_codex_file():
    # Absent, "[]", or a path without "./" makes Codex auto-register the Claude hooks/hooks.json.
    assert CODEX["hooks"] == "./hooks/codex/hooks.json"
    assert CODEX["skills"] == "./skills/"


def test_no_root_plugin_json():
    # A root plugin.json switches Codex to the Agent Plugins loader, silently disabling every hook.
    assert not (REPO / "plugin.json").exists()


def test_marketplace_lists_the_plugin():
    mk = json.loads((REPO / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
    (entry,) = mk["plugins"]
    assert entry["name"] == CODEX["name"] and entry["source"] == {"source": "url", "url": "./"}


def test_codex_hooks_file_shape_is_pinned():
    assert set(HOOKS) <= {"description", "hooks"}
    (start,) = HOOKS["hooks"]["SessionStart"]
    (post,) = HOOKS["hooks"]["PostToolUse"]
    assert start["hooks"][0]["additionalContextLimit"] == 0
    assert post["matcher"] == "apply_patch|Bash"
    for h in (start["hooks"][0], post["hooks"][0]):
        assert h["command"].startswith('bash "${PLUGIN_ROOT}/hooks/')
        assert h["command"].endswith("--harness codex")
        assert h["commandWindows"].startswith('& "${PLUGIN_ROOT}/hooks/codex/run-hook.cmd" ')


def test_cmd_files_have_no_labels():
    for p in (REPO / "hooks/codex/run-hook.cmd", REPO / "scripts/harness/codex/gate.cmd"):
        text = p.read_text(encoding="utf-8")
        assert not re.search(r"^\s*:[A-Za-z]", text, re.M) and "goto" not in text.lower(), p


@pytest.mark.skipif(sys.platform != "win32", reason="run-hook.cmd is a Windows-only wrapper")
@pytest.mark.skipif(BASH is None, reason="a repo-visible bash is required")
def test_run_hook_cmd_runs_a_real_hook_script_through_cmd_exe():
    # End-to-end through the real cmd.exe (not a text/shape check on the .cmd file):
    # run-hook.cmd must locate Git Bash and execute inject-risk-tiers.sh with the
    # --harness codex pair, producing the same SessionStart JSON the direct bash invocation
    # would, with no CLAUDE_PLUGIN_ROOT env var set (Codex substitutes ${PLUGIN_ROOT} into the
    # command string itself, so the wrapper is never handed one).
    import subprocess

    run_hook = REPO / "hooks" / "codex" / "run-hook.cmd"
    result = subprocess.run(
        ["cmd", "/d", "/c", str(run_hook), "inject-risk-tiers.sh", "--harness", "codex"],
        capture_output=True,
    )
    assert result.returncode == 0, result.stderr
    out = json.loads(result.stdout.decode("utf-8"))
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "additionalContext" in out["hookSpecificOutput"]
