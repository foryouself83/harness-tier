"""`inject-risk-tiers.sh --harness codex` carries the same risk-tiers rule and prose block as the
Claude path, wrapped in a Codex-shaped preamble and an extra `<harness-tier-codex-tools>` block —
`rules/harness-tools/codex.md` verbatim. The no-argument output must stay byte-identical: it is
the Claude host's own hook, so a regression here breaks every existing Claude session, not only a
future Codex one.
"""

import json
import subprocess
from pathlib import Path

import pytest

from tests.test_inject_risk_tiers import BASH, SCRIPT, STARTUP

REPO = Path(__file__).resolve().parents[3]


def _run(*args, env=None):
    return subprocess.run(
        [BASH, SCRIPT.as_posix(), *args], input=STARTUP.encode(), capture_output=True, env=env
    )


def _lf(text: str) -> str:
    """`Path.read_text()` normalizes CRLF/CR to LF; the hook's `cat`-then-escape path does not, so
    a byte comparison between the two needs the same normalization on both sides — this repo
    checks tracked files out as CRLF on Windows (`core.autocrlf=true`, no `.gitattributes`)."""
    return text.replace("\r\n", "\n").replace("\r", "\n")


def test_claude_output_unchanged_without_argument():
    import os

    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(REPO)}
    a = _run(env=env).stdout
    ctx = json.loads(a)["hookSpecificOutput"]["additionalContext"]
    assert "(via the Skill tool)" in ctx
    assert "<harness-tier-codex-tools>" not in ctx


def test_codex_output_names_codex_invocation_and_carries_mapping():
    import os

    env = {**os.environ, "PLUGIN_ROOT": str(REPO), "CLAUDE_PLUGIN_ROOT": str(REPO)}
    out = json.loads(_run("--harness", "codex", env=env).stdout)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "Skill tool" not in ctx.split("<harness-tier-risk-tiers>")[1].split("\n\n")[0]
    assert "$flow" in ctx
    needle = (REPO / "rules/harness-tools/codex.md").read_text(encoding="utf-8").strip()[:80]
    assert needle in _lf(ctx)
    assert "<harness-tier-stale-build>" not in ctx


def test_codex_mapping_covers_the_hard_cases():
    text = (REPO / "rules/harness-tools/codex.md").read_text(encoding="utf-8")
    for needle in (
        "request_user_input",
        "numbered",
        "end your turn",
        "SKILL.md",
        "8,000",
        "spawn_agent",
        "fork_turns",
        "update_plan",
        "allowed-tools",
        "context: fork",
        "no multi-select option",
        "$ARGUMENTS",
    ):
        assert needle in text, needle


def test_codex_preamble_spells_the_skill_the_codex_way():
    import os

    env = {**os.environ, "PLUGIN_ROOT": str(REPO), "CLAUDE_PLUGIN_ROOT": str(REPO)}
    ctx = json.loads(_run("--harness", "codex", env=env).stdout)["hookSpecificOutput"][
        "additionalContext"
    ]
    preamble = ctx.split("<harness-tier-risk-tiers>")[1].split("\n\n")[0]
    assert "/flow" not in preamble, preamble
    assert preamble.count("$flow") == 4, preamble


@pytest.mark.parametrize(
    "args",
    [("--harness", "Codex"), ("--harness", "cdx"), ("--harness",), ("--harness", "codex", "extra")],
)
def test_an_unknown_harness_fails_loudly_instead_of_taking_the_claude_path(args):
    """A mistyped hook entry otherwise injects Claude-shaped context into a Codex session and no
    one sees why the preamble names the wrong invocation."""
    import os

    run = _run(*args, env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(REPO)})
    assert run.returncode == 1, run.stdout
    assert run.stdout == b""
    assert b"--harness" in run.stderr


def test_an_explicit_claude_harness_matches_no_argument():
    import os

    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(REPO)}
    assert _run("--harness", "claude", env=env).stdout == _run(env=env).stdout
