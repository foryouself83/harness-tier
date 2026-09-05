import re
from pathlib import Path

import pytest

from tests.skills._helpers import SKILL_IDS, SKILLS, body, frontmatter

# Every field the official SKILL.md frontmatter reference defines. Anything else is
# either a typo or a command-era leftover that silently does nothing.
SPEC_FIELDS = {
    "name",
    "description",
    "when_to_use",
    "argument-hint",
    "arguments",
    "disable-model-invocation",
    "user-invocable",
    "allowed-tools",
    "disallowed-tools",
    "model",
    "effort",
    "context",
    "agent",
    "hooks",
    "paths",
    "shell",
}
# Conservative budget for `description` + `when_to_use` in the skill listing. The official
# docs put the listing truncation at 1,536 chars; 1024 leaves headroom rather than tracking
# the platform constant exactly (a previous comment presented 1024 as the platform value —
# exactly the un-re-derived model knowledge the CLAUDE.md preamble warns about).
DESCRIPTION_CAP = 1024
# --------------------------------------------------------------------------- structural


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_frontmatter_parses_and_only_uses_spec_fields(skill: Path):
    """A non-spec field is dead weight: Claude Code ignores it, so it reads as a
    working declaration while doing nothing. `allowed-tools`/`argument-hint` survived
    the command→skill migration exactly this way."""
    data = frontmatter(skill)
    unknown = set(data) - SPEC_FIELDS
    assert not unknown, f"{skill.parent.name}: fields absent from the official spec: {unknown}"


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_name_and_description_are_present_and_named_for_the_directory(skill: Path):
    data = frontmatter(skill)
    assert isinstance(data.get("description"), str) and data["description"].strip()
    assert data.get("name") == skill.parent.name, (
        f"name={data.get('name')!r} but the directory (and therefore the /command) "
        f"is {skill.parent.name!r}"
    )


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_description_fits_the_listing_cap(skill: Path):
    data = frontmatter(skill)
    combined = len(data["description"]) + len(str(data.get("when_to_use", "")))
    assert combined <= DESCRIPTION_CAP, f"{skill.parent.name}: {combined} chars > {DESCRIPTION_CAP}"


# A skill that outgrows this stops being read and starts being skimmed — including by the
# agent running it. 500 is the practical ceiling; the longest here is flow-init at 349.
SKILL_LINE_CAP = 500


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_skill_stays_short_enough_to_be_read(skill: Path):
    lines = len(skill.read_text(encoding="utf-8").splitlines())
    assert lines <= SKILL_LINE_CAP, (
        f"{skill.parent.name}: {lines} lines exceeds {SKILL_LINE_CAP}. Disclose reference "
        f"material into references/ and link it rather than growing SKILL.md"
    )


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_model_invocable_descriptions_state_when_to_use(skill: Path):
    """A model-invocable description is the only thing in context deciding whether the
    skill fires, so it must lead with triggering conditions. `disable-model-invocation`
    skills are exempt: their description never reaches the model, and serves the
    human reading the `/` menu."""
    data = frontmatter(skill)
    if data.get("disable-model-invocation") is True:
        return
    desc = data["description"]
    # "Use for requests like <quoted phrases>" is the same job done with literal user
    # wording; "MANDATORY ... invoke BEFORE" is the discipline form.
    assert re.search(r"\bUse (when|for)\b", desc) or desc.startswith("MANDATORY"), (
        f"{skill.parent.name}: description says what the skill does but not when to "
        f"use it — agents cannot decide to load it. Got: {desc[:80]!r}"
    )


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_argument_hint_is_only_on_skills_that_read_arguments(skill: Path):
    """`argument-hint` is "Hint shown during autocomplete to indicate expected
    arguments" — a skill that never reads `$ARGUMENTS` has no hint to show, and `(none)`
    puts the literal string "(none)" in the menu."""
    hint = frontmatter(skill).get("argument-hint")
    if hint is None:
        return
    assert hint != "(none)", f"{skill.parent.name}: drop argument-hint instead of '(none)'"
    assert "$ARGUMENTS" in body(skill), (
        f"{skill.parent.name}: argument-hint promises arguments the body never reads"
    )


# Tools that never prompt, so pre-approving them grants nothing. Read-only tools are
# auto-allowed (permissions.md: "Read-only | File reads, Grep | Approval required: No"),
# and the rest never reach a permission check.
NEVER_PROMPTS = {"Read", "Grep", "Glob", "Skill", "Agent", "Task", "SendMessage", "AskUserQuestion"}
# Bare tool names that grant the whole tool. `Bash` is `Bash(*)`: every command.
BLANKET = {"Bash", "Write", "Edit", "WebFetch", "WebSearch", "NotebookEdit"}


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_allowed_tools_entries_are_scoped_and_do_something(skill: Path):
    """`allowed-tools` reads like a restriction and is the opposite: "It does not restrict
    which tools are available: every tool remains callable." Two ways to get it wrong, and
    this repo shipped both at once for nine skills — `Bash, Read, Grep, Glob, Write, Edit,
    AskUserQuestion, Agent`:

    * an entry for a tool that never prompts grants nothing and only implies a limit;
    * a bare `Bash` grants every command, the opposite of the documented
      `Bash(git add *)` form, and the docs warn that "a skill can grant itself broad
      tool access".
    """
    entries = frontmatter(skill).get("allowed-tools")
    if entries is None:
        return
    if isinstance(entries, str):
        entries = re.findall(r"\w+\([^)]*\)|[\w-]+", entries)
    for e in entries:
        assert e not in NEVER_PROMPTS, (
            f"{skill.parent.name}: '{e}' never asks for permission, so pre-approving it "
            f"changes nothing — it only makes the list read like a restriction"
        )
        assert e not in BLANKET, (
            f"{skill.parent.name}: bare '{e}' grants the whole tool. Scope it, e.g. "
            f"Bash(git add *), or drop it"
        )
