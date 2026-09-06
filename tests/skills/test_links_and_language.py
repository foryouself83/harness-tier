import re
from pathlib import Path

import pytest

from tests.skills._helpers import (
    KOREAN,
    KOREAN_DATA_LITERAL_ALLOWLIST,
    REPO,
    SKILL_IDS,
    SKILLS,
    bash_blocks,
    body,
)


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_relative_links_resolve(skill: Path):
    for link in re.findall(r"\]\(([^)]+)\)", body(skill)):
        if link.startswith(("http://", "https://", "#")):
            continue
        target = (skill.parent / link.split("#")[0]).resolve()
        assert target.exists(), f"{skill.parent.name}: dead link → {link}"


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_intra_file_section_references_resolve(skill: Path):
    """`§3.1` pointing at a section that was renumbered away sends the agent nowhere.

    A `§` belonging to another file is that file's business, so a reference is only
    checked when neither its own line nor the one above names a `.md` — cross-file
    citations routinely wrap, putting the filename one line up from the `§`.
    """
    text = body(skill)
    headings = {h.rstrip(".") for h in re.findall(r"^#+\s+([\d.]+)", text, re.M)}
    if not headings:
        return
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if ".md" in line or (i and ".md" in lines[i - 1]):
            continue
        for ref in re.findall(r"§(\d+(?:\.\d+)?)", line):
            assert ref in headings, (
                f"{skill.parent.name}: §{ref} has no matching heading. Sections: {sorted(headings)}"
            )


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_cross_file_section_references_resolve(skill: Path):
    """`web-playwright.md (§10.7)` when that file stops at §6 sends the agent hunting.
    A citation is attributed to the single `.md` linked on its line or the one above —
    these wrap constantly, putting the filename a line up from the `§`."""
    lines = body(skill).splitlines()
    for i, line in enumerate(lines):
        window = (lines[i - 1] + "\n" + line) if i else line
        targets = {t for t in re.findall(r"\]\(([^)]+\.md)[^)]*\)", window)}
        refs = re.findall(r"§(\d+(?:\.\d+)?)", line)
        if len(targets) != 1 or not refs:
            continue
        target = (skill.parent / targets.pop()).resolve()
        if not target.exists():
            continue  # test_relative_links_resolve owns that failure
        headings = {
            h.rstrip(".")
            for h in re.findall(r"^#+\s+([\d.]+)", target.read_text(encoding="utf-8"), re.M)
        }
        for ref in refs:
            assert ref in headings, (
                f"{skill.parent.name}: cites {target.name} §{ref}, which has {sorted(headings)}"
            )


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_shipped_commands_have_no_unrunnable_placeholders(skill: Path):
    """A `<placeholder>` in command position is worse than a wrong default: run
    verbatim it fails into an empty result rather than an error, so the agent reads a
    silent zero as a real answer. Placeholders belong in assignments and paths that
    the surrounding prose tells the agent to fill."""
    for block in bash_blocks(body(skill)):
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            m = re.match(r"(find|cat|ls|grep\s+-\w+)\s+[\"']?(<[^>]+>)", stripped)
            assert not m, f"{skill.parent.name}: command reads a placeholder literally → {stripped}"


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_korean_only_survives_as_data_literals(skill: Path):
    """The skills ship in English. The exceptions are data, not prose: translating them
    would desync a doc from real script output, or drop Korean input support."""
    rel = skill.relative_to(REPO).as_posix()
    allowed = KOREAN_DATA_LITERAL_ALLOWLIST.get(rel, [])
    for i, line in enumerate(skill.read_text(encoding="utf-8").splitlines(), 1):
        if not KOREAN.search(line):
            continue
        assert any(a in line for a in allowed), (
            f"{rel}:{i}: untranslated Korean prose → {line.strip()}"
        )


def test_references_are_english():
    """Reference files load into the same context as the skill that points at them."""
    for ref in sorted(REPO.glob("skills/*/references/**/*.md")):
        offenders = [
            line for line in ref.read_text(encoding="utf-8").splitlines() if KOREAN.search(line)
        ]
        assert not offenders, f"{ref.relative_to(REPO)}: Korean prose → {offenders[0].strip()}"
