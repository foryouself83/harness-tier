import re
from fnmatch import fnmatchcase

import yaml

from tests.skills._helpers import REPO, bash_rule_matches


def test_the_skill_editing_rule_still_fires_on_skills():
    """`.claude/rules/skill-frontmatter.md` is path-scoped, which is the whole reason it
    costs nothing — and also how it dies silently. A glob that stops matching takes the
    rule out of context without failing anything, which is the same shape of quiet
    nothing this file exists to catch. Frontmatter is `paths`-only per authoring-spec.md.
    """
    rule = REPO / ".claude/rules/skill-frontmatter.md"
    assert rule.exists(), "the skill-editing rule is gone; CLAUDE.md still links it"
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", rule.read_text(encoding="utf-8"), re.DOTALL)
    assert m, "rule has no frontmatter, so it loads unconditionally into every session"
    data = yaml.safe_load(m.group(1))
    assert set(data) == {"paths"}, f"a rule takes only `paths`; got {sorted(data)}"
    targets = [p.relative_to(REPO).as_posix() for p in REPO.glob("skills/**/*.md")]
    for pattern in data["paths"]:
        assert any(fnmatchcase(t, pattern) for t in targets), (
            f"glob {pattern!r} matches no skill file — the rule would never load"
        )


def test_bash_rule_matcher_agrees_with_the_documented_examples():
    """This matcher is the yardstick the next test measures rules against, so it is only
    worth anything if it reproduces the examples in permissions.md verbatim."""
    for rule, command, expected in [
        ("Bash(ls *)", "ls -la", True),
        ("Bash(ls *)", "ls", True),  # word boundary is "space OR end-of-string" (permissions.md)
        ("Bash(ls *)", "lsof", False),
        ("Bash(ls:*)", "ls", True),  # :* is equivalent, so it too matches the bare command
        ("Bash(ls*)", "lsof", True),
        ("Bash(ls:*)", "ls -la", True),
        ("Bash(npm run build)", "npm run build", True),
        ("Bash(npm run build)", "npm run test", False),
        ("Bash(git add *)", "git add -A", True),
        ("Bash(* --version)", "python3 --version", True),
    ]:
        assert bash_rule_matches(rule, command) is expected, f"{rule} vs {command}"
