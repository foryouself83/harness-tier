import re
from fnmatch import fnmatchcase
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent.parent
SKILLS = sorted(REPO.glob("skills/*/SKILL.md"))
SKILL_IDS = [p.parent.name for p in SKILLS]
# rules/ ships to consumers and the SessionStart hook injects it, so its commands run too.
SHIPPED_RULES = sorted(REPO.glob("rules/*.md"))
# Korean is allowed only where it is *data* rather than prose: a verbatim quote of a
# script's real stdout, and the input tokens harness-insight parses. Translating either
# would desync the doc from the code or drop Korean input support.
KOREAN = re.compile(r"[가-힣]")
KOREAN_DATA_LITERAL_ALLOWLIST = {
    "skills/flow-init/SKILL.md": ["config 슬롯 점검"],
    "skills/harness-insight/SKILL.md": ["N일", "N주", "N개월", "오늘"],
}


def frontmatter(path: Path) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", path.read_text(encoding="utf-8"), re.DOTALL)
    assert m, f"{path.relative_to(REPO)}: no frontmatter block — the skill will not load"
    data = yaml.safe_load(m.group(1))
    assert isinstance(data, dict), f"{path.relative_to(REPO)}: frontmatter is not a mapping"
    return data


def body(path: Path) -> str:
    return re.sub(r"^---\s*\n.*?\n---\s*\n", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)


def bash_blocks(text: str) -> list[str]:
    return re.findall(r"```bash\n(.*?)```", text, re.DOTALL)


def bash_rule_matches(rule: str, command: str) -> bool:
    """Claude Code's Bash rule semantics, per permissions.md.

    Patterns are globs over the command string. A trailing ` *` (or the equivalent `:*`)
    "enforces a word boundary, requiring the prefix to be followed by a space **or
    end-of-string**" — so `Bash(ls *)` matches `ls -la` *and* the bare `ls`, but not
    `lsof`. Without the space, `Bash(ls*)` matches `lsof` too. No wildcard means an
    exact match.
    """
    pattern = rule[len("Bash(") : -1]
    if pattern.endswith(":*"):
        pattern = pattern[:-2] + " *"
    if pattern.endswith(" *"):
        prefix = pattern[:-2]
        # followed by a space (has arguments) or end-of-string (bare command)
        return command == prefix or fnmatchcase(command, prefix + " *")
    return fnmatchcase(command, pattern) or command == pattern
