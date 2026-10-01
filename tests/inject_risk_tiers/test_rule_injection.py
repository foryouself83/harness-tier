"""The rule and the prose summary reach the session, in the block layout the evals measure."""

import os
import subprocess

import pytest

from tests.inject_risk_tiers._helpers import (
    BASH,
    SCRIPT,
    STARTUP,
    _context,
    _plugins_root,
    _run,
)


def test_rule_body_is_injected(tmp_path):
    """Regression: assert the rule FILE reaches the context, not the wrapper tag that names it —
    the tag is a constant and would pass with the rule content gone."""
    assert "the body the hook must actually read" in _context(
        _run(_plugins_root(tmp_path, published=None))
    )


def test_rule_body_with_json_specials_survives(tmp_path):
    """The rule is interpolated into a JSON string by hand, so its escaping has to hold."""
    plugin = _plugins_root(tmp_path, published=None)
    tricky = 'a "quote", a \\backslash, a\ttab\nand a second line\n'
    (plugin / "rules" / "risk-tiers.md").write_text(tricky, encoding="utf-8", newline="")
    context = _context(_run(plugin))  # would raise on malformed JSON
    assert 'a "quote", a \\backslash, a\ttab\nand a second line' in context


def _prose_block(tmp_path) -> str:
    plugin = _plugins_root(tmp_path, published=None)
    context = _context(_run(plugin, extra_env={"CLAUDE_PROJECT_DIR": str(tmp_path)}))
    assert "<harness-tier-prose>" in context, "the prose summary never reached the session"
    return context.split("<harness-tier-prose>", 1)[1].split("</harness-tier-prose>", 1)[0]


def test_the_prose_block_follows_the_risk_tiers_block(tmp_path):
    """Text beside the mandate moves measured invocation rates, so the summary lives in its
    own block after the closing tag, never inside it."""
    context = _context(_run(_plugins_root(tmp_path, published=None)))
    assert context.index("</harness-tier-risk-tiers>") < context.index("<harness-tier-prose>")


@pytest.mark.parametrize("name", ["flow", "commit", "doc-sync", "release-commit", "prose-review"])
def test_the_prose_block_names_no_skill(tmp_path, name):
    """A skill named here would be forced to declare hook_assisted, folding this hook into its
    description_sha — see tests/evals/test_injected_rule.py. The path `/doc-style.md` in the
    block is why this asks about skill names rather than about any slash-word."""
    assert f"/{name}" not in _prose_block(tmp_path)


def test_the_prose_block_asks_for_the_users_language(tmp_path):
    assert "user's language" in _prose_block(tmp_path)


def test_the_prose_block_keeps_the_box_keys_untranslated(tmp_path):
    """The three keys are what the TRAP rule parses; a localized key is that rule switched
    off for that language."""
    block = _prose_block(tmp_path)
    for key in ("CRITICAL TRAP:", "Trigger:", "Symptom:"):
        assert key in block


def _host(tmp_path, with_rule: bool) -> dict:
    host = tmp_path / "host"
    if with_rule:
        rules = host / ".claude" / "rules" / "harness-tier"
        rules.mkdir(parents=True)
        (rules / "doc-style.md").write_text("# copied rule\n", encoding="utf-8")
    host.mkdir(exist_ok=True)
    return {"CLAUDE_PROJECT_DIR": str(host)}


@pytest.mark.parametrize("harness", [[], ["--harness", "codex"]])
def test_the_prose_block_is_dropped_only_where_claude_loads_the_copied_rule(tmp_path, harness):
    """/flow-init copies doc-style.md into .claude/rules/harness-tier/, which Claude Code loads
    itself; injecting the summary beside it is the same rule twice. Codex reads no .claude/rules/,
    so it keeps the block — as does a host that has not re-run /flow-init since the upgrade."""
    plugin = _plugins_root(tmp_path, published=None)
    env = _host(tmp_path, with_rule=True)
    result = subprocess.run(
        [BASH, str(SCRIPT), *harness], input=STARTUP, text=True, capture_output=True,
        env={"PATH": os.environ.get("PATH", ""), "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
             "CLAUDE_PLUGIN_ROOT": str(plugin), **env},
        timeout=30,
    )
    context = _context(result)
    assert ("<harness-tier-prose>" in context) is bool(harness)
    assert "the body the hook must actually read" in context


def test_the_prose_block_stays_where_the_host_has_no_copied_rule(tmp_path):
    plugin = _plugins_root(tmp_path, published=None)
    context = _context(_run(plugin, extra_env=_host(tmp_path, with_rule=False)))
    assert "<harness-tier-prose>" in context
