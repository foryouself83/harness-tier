"""Skills name actions; the harness maps them (rules/harness-tools/).

A tool name in a body is a skill only one harness can run.
"""

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
BANNED = re.compile(
    r"\bAskUserQuestion\b|\bSkill tool\b|\bAgent tool\b|\bsubagent_type\b|\bTeamCreate\b|"
    r"\bSendMessage\b|\bTaskCreate\b|\bTodoWrite\b|\(`Task` alias\)|"
    r"\bSkill: *`?[a-z]"  # `Skill: <name>`, Claude Code's invocation notation
)
SCOPE = [*REPO.glob("skills/**/*.md"), *REPO.glob("agents/*.md"), *REPO.glob("rules/*.md")]
ASKS = re.compile(r"(?i)\bask the user \((?:structured choice|multi-select)\)")
BARE_SCRIPT = re.compile(
    r"(?<![\w/.\"'-])(?:\./|\$\{CLAUDE_PLUGIN_ROOT\}/|\.claude/harness-tier/)"
    r"scripts/[\w./-]+\.(?:sh|py)\b"
)
HIDDEN = {"policy": {"allow_implicit_invocation": False}}


def _body(p: Path) -> str:
    text = p.read_text(encoding="utf-8")
    body = text.split("---", 2)[2] if text.startswith("---") else text
    if p == REPO / "rules" / "risk-tiers.md":
        # `## Principle` is eval-position sensitive (CLAUDE.md) and names the Claude Code tool
        # on purpose; the Codex SessionStart hook rewrites that line instead.
        body = re.sub(r"(?ms)^## Principle\n.*?(?=^## )", "", body.replace("\r\n", "\n"))
    return body


def _flat(text: str) -> str:
    return " ".join(text.split())


def _rel(p: Path) -> str:
    return p.relative_to(REPO).as_posix()


def _interaction_sentence() -> str:
    vocabulary = REPO / "rules/harness-tools/vocabulary.md"
    lines = vocabulary.read_text(encoding="utf-8").splitlines()
    after = lines[lines.index("## Interaction rule") + 1 :]
    return _flat(next(line for line in after if line.strip()))


def test_no_harness_tool_names_in_shipped_prose():
    hits = [f"{_rel(p)}: {m.group(0)}" for p in SCOPE for m in BANNED.finditer(_body(p))]
    assert hits == [], "name the action from rules/harness-tools/vocabulary.md instead"


def test_the_principle_exclusion_still_removes_only_that_section():
    body = _body(REPO / "rules" / "risk-tiers.md")
    assert "## Principle" not in body
    assert "## Gates (glossary)" in body


def test_every_manual_only_skill_hides_from_codex_catalog():
    for skill in REPO.glob("skills/*/SKILL.md"):
        fm = yaml.safe_load(skill.read_text(encoding="utf-8").split("---", 2)[1])
        meta = skill.parent / "agents" / "openai.yaml"
        if fm.get("disable-model-invocation") is True:
            assert yaml.safe_load(meta.read_text(encoding="utf-8")) == HIDDEN, _rel(skill)
        else:
            assert not meta.exists(), f"{_rel(skill)} is model-invocable; Codex must list it"


def test_every_skill_that_asks_carries_the_interaction_rule_once():
    sentence = _interaction_sentence()
    assert sentence.startswith("Wherever this skill asks the user something")
    for skill in REPO.glob("skills/*/SKILL.md"):
        refs = list(skill.parent.glob("references/**/*.md"))
        asks = any(ASKS.search(_flat(_body(p))) for p in [skill, *refs])
        count = _flat(_body(skill)).count(sentence)
        assert count == (1 if asks else 0), f"{_rel(skill)}: asks={asks}, sentence x{count}"
        for ref in refs:
            assert sentence not in _flat(_body(ref)), f"{_rel(ref)} repeats the interaction rule"


def test_every_agent_that_asks_carries_the_interaction_rule_once():
    sentence = _interaction_sentence()
    for agent in REPO.glob("agents/*.md"):
        body = _body(agent)
        count = _flat(body).count(sentence)
        assert count == (1 if ASKS.search(_flat(body)) else 0), f"{_rel(agent)}: sentence x{count}"


def _fenced_lines(body: str) -> list[str]:
    lines, fenced = [], False
    for line in body.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
        elif fenced:
            lines.append(line)
    return lines


def test_bundled_scripts_are_called_through_an_interpreter():
    """Fenced lines only: prose naming a script's path is a mention, not a call."""
    hits = []
    for p in SCOPE:
        for line in _fenced_lines(_body(p)):
            for m in BARE_SCRIPT.finditer(line):
                before = line[: m.start()].rstrip().rstrip('"').rstrip()
                if not before.endswith(("bash", "python3", "python", "sh")):
                    hits.append(f"{_rel(p)}: {line.strip()[:120]}")
    assert hits == [], "call a bundled script through its interpreter: `bash x.sh`, `python3 x.py`"
