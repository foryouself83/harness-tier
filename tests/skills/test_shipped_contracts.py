import re
from pathlib import Path

import pytest
import yaml

from scripts.doc_style_check import markdown_prose
from tests.skills._helpers import REPO, body

# The documents a consumer reads to find out what they got: each README, and the usage guide
# in each language read as one text, since a skill documented in any topic file is documented.
# Both languages are listed: a row added to one and not the other is the drift `doc-sync`
# exists to catch.
CONSUMER_DOCS = ("README.md", "README.ko.md", "docs/usage (en)", "docs/usage (ko)")
USAGE_DIR = REPO / "docs" / "usage"
# The one skill a consumer never reaches for. `/harness-init` invokes it as its generation
# engine and its own description says not to call it directly, so it has no consumer-facing
# timing, arguments or behaviour to write down.
UNLISTED_SKILLS = frozenset({"harness-authoring"})


def _consumer_text(doc: str) -> str:
    if doc == "docs/usage (en)":
        files = [p for p in sorted(USAGE_DIR.glob("*.md")) if not p.name.endswith(".ko.md")]
    elif doc == "docs/usage (ko)":
        files = sorted(USAGE_DIR.glob("*.ko.md"))
    else:
        files = [REPO / doc]
    return chr(10).join(p.read_text(encoding="utf-8") for p in files)


@pytest.mark.parametrize("doc", CONSUMER_DOCS)
def test_every_consumer_facing_skill_is_registered(doc: str):
    """Adding a skill directory is not adding a skill a consumer can find. `prose-review`
    shipped in none of the four, and nothing failed: the component tables and the USAGE
    sections are hand-maintained, and the `doc-sync` gate that reconciles them never runs in
    a repo with no `flow-config.yaml`."""
    text = _consumer_text(doc)
    missing = sorted(
        p.parent.name
        for p in REPO.glob("skills/*/SKILL.md")
        if p.parent.name not in UNLISTED_SKILLS
        and f"`{p.parent.name}`" not in text
        and f"`/{p.parent.name}`" not in text
    )
    assert not missing, f"{doc} names no {missing} — a consumer cannot find what it does"


def copy_files() -> list[str]:
    setup = (REPO / "scripts/flow_init_setup.py").read_text(encoding="utf-8")
    block = setup[setup.index("COPY_FILES") : setup.index("]", setup.index("COPY_FILES"))]
    return re.findall(r'"scripts/([\w.\-]+)"', block)


def test_scaffold_treats_a_ts_playwright_config_as_a_typescript_signal():
    """`@playwright/test` ships its own TypeScript, so a TS Playwright project routinely
    has no `tsconfig.json` and no `typescript` dependency — keying the language only on
    those two writes a `.js` spec into a `.ts` suite. Surfaced by the `empty-web`
    sandbox scenario, whose fixture is exactly that shape."""
    step = re.search(
        r"^## Step 2 — Detect testDir and Language$(.*?)^---$",
        body(REPO / "skills/playwright-scaffold/SKILL.md"),
        re.M | re.DOTALL,
    )
    assert step, "playwright-scaffold: the language-detection step was renamed"
    assert "playwright.config.ts" in step.group(1), (
        "playwright-scaffold decides .ts vs .js without counting playwright.config.ts as "
        "a TypeScript signal, so a TS project with no tsconfig gets a .js spec"
    )


def test_flow_init_does_not_enumerate_the_copy_list():
    """`COPY_FILES` is the only list that is true by construction. flow-init once
    enumerated five scripts while COPY_FILES held nine — and told the agent to relay
    that stale list to the user. Naming a script elsewhere (what depends on it, where
    the host copy lives) is fine; re-listing what gets copied is what drifts."""
    # The bullet lives wherever flow-init's shipped guidance keeps it — SKILL.md or a
    # references/ file it loads. Both reach the same agent, so both carry the same rule;
    # pinning the search to one file turns a move into a green test over unread text.
    shipped = [
        REPO / "skills/flow-init/SKILL.md",
        *sorted((REPO / "skills/flow-init").glob("references/*.md")),
    ]
    doc = chr(10).join(f.read_text(encoding="utf-8") for f in shipped)
    bullet = re.search(r"^- \*\*Copies\*\*.*?(?=^- \*\*)", doc, re.M | re.DOTALL)
    assert bullet, "flow-init: the **Copies** bullet is gone — did the report change?"
    listed = [name for name in copy_files() if name in bullet.group(0)]
    assert not listed, (
        f"the Copies bullet enumerates {listed}; that list drifts the moment a script is "
        f"added to COPY_FILES. Relay the script's own printed report instead."
    )


def test_flow_init_setup_actually_reports_what_it_copied():
    """flow-init tells the agent to relay the script's report. That instruction is only
    real if the script prints one — otherwise the agent has nothing to relay and the
    delegation is a no-op dressed as a fix."""
    setup = (REPO / "scripts/flow_init_setup.py").read_text(encoding="utf-8")
    copy_fn = setup[setup.index("COPY_FILES") :]
    assert "report.append" in copy_fn and "Path(rel).name" in copy_fn, (
        "flow_init_setup.py no longer reports each copied file by name; flow-init's "
        "'relay the script's report' instruction now has nothing to relay."
    )


def test_the_commit_guide_slot_is_the_one_the_commit_skill_reads():
    """One fact in two files: the config key `/flow-init` backfills into every host, and the
    key the `commit` skill looks up to find the host's own guide. A rename on either side
    fails silently — the lookup returns nothing, the skill falls back to risk-tiers alone,
    and the host guide it was supposed to prefer is never read."""
    example = yaml.safe_load((REPO / "flow-config.example.yaml").read_text(encoding="utf-8"))
    assert "commit_guide" in example, (
        "flow-config.example lost its `commit_guide` slot — /flow-init's Step 2.5 backfill "
        "only offers slots the example advertises, so existing hosts stop receiving it"
    )
    skill = body(REPO / "skills/commit/SKILL.md")
    assert "'commit_guide'" in skill, "the commit skill no longer reads the commit_guide key"
    # The example's default value has to be the path harness-authoring generates,
    # otherwise the slot ships pointing at a file that never exists.
    assert example["commit_guide"] == "docs/operations/commit-versioning-guide.md"
    guide = (REPO / "skills/harness-authoring/references/tech-doc-guide.md").read_text(
        encoding="utf-8"
    )
    assert example["commit_guide"] in guide, (
        "tech-doc-guide no longer generates the doc the commit_guide default points at"
    )


def _checklist_in(doc: Path) -> list[str]:
    """The items of the `review_checklist:` block in a doc's config example.

    Read as a block rather than as substrings: an item quoted in the surrounding prose says
    nothing about whether the example a reader copies still carries it.
    """
    out: list[str] = []
    seen = False
    for line in doc.read_text(encoding="utf-8").splitlines():
        if line.startswith("review_checklist:"):
            seen = True
            continue
        if not seen:
            continue
        stripped = line.strip()
        if stripped.startswith("- "):
            out.append(yaml.safe_load(stripped[2:]))
        elif stripped.startswith("#") or not stripped.split("#")[0].strip():
            continue
        else:
            break
    return out


# A nested step is indented, and the shape is no less broken one level down. Case-insensitive
# for the same reason. Fenced blocks are dropped before this runs — a sample of the broken
# shape inside one is an illustration, not a step.
_SUBSTEP_MARKER = re.compile(r"^[ \t]*\d+[a-z]+[.)]\s", re.IGNORECASE)


@pytest.mark.parametrize("skill", sorted(d.name for d in (REPO / "skills").iterdir() if d.is_dir()))
def test_no_skill_numbers_a_step_in_a_shape_commonmark_rejects(skill: str):
    """CommonMark takes digits then `.` or `)` and nothing else, so a step numbered `1b.`
    is not a list item — it is absorbed as a lazy continuation of the step above it, taking
    its own continuation lines with it. The page still reads, which is why this survived:
    only the structure is gone."""
    text = (REPO / "skills" / skill / "SKILL.md").read_text(encoding="utf-8")
    hits = [line for _, line in markdown_prose(text) if _SUBSTEP_MARKER.match(line)]
    assert not hits, (
        f"{skill}/SKILL.md numbers a step {hits} — renumber the list; CommonMark reads that "
        "as a paragraph, not a list item"
    )


def test_the_review_checklist_is_one_list_in_three_files():
    """The template a host copies and the two configuration guides that quote it. They drifted once
    already: an English pass rewrote the Korean half of each `term / meaning` line into the
    term again, leaving `regression / regression tests pass` in the template while USAGE had
    deduped two of the four. A reader then cannot tell which file is the example."""
    example = yaml.safe_load((REPO / "flow-config.example.yaml").read_text(encoding="utf-8"))
    items = example["review_checklist"]
    assert items, "flow-config.example lost its review_checklist"
    for item in items:
        head, sep, tail = item.partition(" / ")
        # The leftover shape is the term restated on the far side of the separator, not
        # always verbatim: `DB transaction / migration / DB transaction & migration safety`
        # buries it one segment further in. Containment catches every form it took.
        assert not (sep and head in tail), f"{item!r} restates itself across the separator"
    for doc in ("docs/usage/configuration.md", "docs/usage/configuration.ko.md"):
        quoted = _checklist_in(REPO / doc)
        assert quoted == items, (
            f"{doc}'s review_checklist example is {quoted}, not the template's {items} — the "
            "doc and the file a host copies have to show one list"
        )
    # The categories the review gate judges against live in the tier SSOT; the
    # template is the copy a host edits, so a category added there has to reach it.
    tiers = (REPO / "rules" / "risk-tiers.md").read_text(encoding="utf-8")
    assert len(items) == 5, f"expected the five risk-tiers categories, got {len(items)}"
    for word in ("queue routing", "API error conventions"):
        assert word in tiers, f"risk-tiers no longer names {word!r}"
