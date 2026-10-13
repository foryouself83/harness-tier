"""Codex needs its own manifest and marketplace entry, and its package carries no lifecycle hook:
OpenAI's plugin directory refuses one that does, so the session hooks are the host's
(`scripts/harness/codex/install.py`). Codex discovers `hooks/hooks.json` on its own, so the
Claude hooks file sits elsewhere."""

import json
import re
import sys
from pathlib import Path

import pytest

from tests.invalidate_gate_markers._helpers import BASH  # a repo-visible bash (Git Bash on Windows)

REPO = Path(__file__).resolve().parents[3]
CODEX = json.loads((REPO / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
CLAUDE = json.loads((REPO / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))


def test_versions_and_names_match():
    assert CODEX["name"] == CLAUDE["name"] and CODEX["version"] == CLAUDE["version"]


def test_codex_package_declares_and_discovers_no_hooks():
    assert "hooks" not in CODEX
    assert not (REPO / "hooks/hooks.json").exists(), "Codex would register the Claude hooks"
    assert CLAUDE["hooks"] == "./hooks/claude/hooks.json"
    assert CODEX["skills"] == "./skills/"


def test_codex_listing_fields_fit_the_directory_limits():
    ui = CODEX["interface"]
    assert len(ui["displayName"]) <= 30 and len(ui["shortDescription"]) <= 30
    assert 0 < len(ui["longDescription"]) <= 4000 and len(ui["developerName"]) <= 80
    assert len(ui["defaultPrompt"]) <= 3 and all(len(p) <= 128 for p in ui["defaultPrompt"])
    for key in ("logo", "composerIcon"):
        assert ui[key].startswith("./") and (REPO / ui[key]).is_file(), key
    assert CLAUDE["icon"] == ui["logo"]


def test_no_root_plugin_json():
    # A root plugin.json switches Codex to the Agent Plugins loader, silently disabling every hook.
    assert not (REPO / "plugin.json").exists()


def test_marketplace_lists_the_plugin():
    mk = json.loads((REPO / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
    (entry,) = mk["plugins"]
    assert entry["name"] == CODEX["name"]
    assert entry["policy"] == {"installation": "AVAILABLE", "authentication": "ON_INSTALL"}


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


def test_flow_stops_a_codex_host_without_the_session_hooks():
    """A Codex host set up while the plugin carried the hooks loses them on update; the router
    every task enters is the one place that still runs, so it names the check and the remedy."""
    text = (REPO / "skills/flow/SKILL.md").read_text(encoding="utf-8")
    assert "harness-tier/hooks/invalidate-gate-markers.sh" in text and "$flow-init" in text
