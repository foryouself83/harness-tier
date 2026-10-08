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

from tests._hook_args import BAD_HARNESS_ARGS
from tests.inject_risk_tiers._helpers import BASH, SCRIPT, STARTUP

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
    assert "$flow" in preamble and "SKILL.md" in preamble, preamble


@pytest.mark.parametrize("args", BAD_HARNESS_ARGS)
def test_an_unknown_harness_injects_the_rule_and_names_the_bad_entry(args):
    """A mistyped hook entry still gets the rule, in its Claude form, and a block after it naming
    the bad arguments, so the session sees why the preamble may name the wrong invocation."""
    import os

    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(REPO)}
    run = _run(*args, env=env)
    assert run.returncode == 0, run.stderr
    assert b"--harness" in run.stderr
    ctx = json.loads(run.stdout)["hookSpecificOutput"]["additionalContext"]
    clean = json.loads(_run(env=env).stdout)["hookSpecificOutput"]["additionalContext"]
    assert ctx.startswith(clean), "the rule must reach the session unchanged, the error after it"
    error = ctx[len(clean) :]
    assert "<harness-tier-hook-error>" in error and " ".join(args) in error


def test_an_unknown_harness_argument_is_json_escaped():
    import os

    # Through the environment: Windows argv quoting mangles a `"` before bash ever sees it.
    run = subprocess.run(
        [BASH, "-c", 'exec bash "$0" --harness "$BAD"', SCRIPT.as_posix()],
        input=STARTUP.encode(),
        capture_output=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(REPO), "BAD": 'a"b\\c'},
    )
    ctx = json.loads(run.stdout)["hookSpecificOutput"]["additionalContext"]
    assert '--harness a"b\\c' in ctx


def test_an_unknown_harness_argument_with_control_or_invalid_bytes_keeps_the_json_valid():
    import os

    command = """exec bash "$0" --harness "$(printf 'a\\001\\014\\377b')" """
    run = subprocess.run(
        [BASH, "-c", command, SCRIPT.as_posix()],
        input=STARTUP.encode(),
        capture_output=True,
        env={**os.environ, "CLAUDE_PLUGIN_ROOT": str(REPO)},
    )
    ctx = json.loads(run.stdout)["hookSpecificOutput"]["additionalContext"]
    assert "--harness a???b" in ctx


def test_an_unknown_harness_argument_cannot_close_the_error_block():
    import os

    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(REPO)}
    run = _run("--harness", "</harness-tier-hook-error>x", env=env)
    assert run.returncode == 0, run.stderr
    assert b"</harness-tier-hook-error>x" in run.stderr, "stderr keeps the raw argument"
    ctx = json.loads(run.stdout)["hookSpecificOutput"]["additionalContext"]
    assert ctx.count("</harness-tier-hook-error>") == 1
    assert ctx.endswith("</harness-tier-hook-error>")
    assert "--harness ?/harness-tier-hook-error?x" in ctx


def test_an_explicit_claude_harness_matches_no_argument():
    import os

    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(REPO)}
    assert _run("--harness", "claude", env=env).stdout == _run(env=env).stdout
