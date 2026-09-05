import re

import yaml

from tests.skills._helpers import REPO, body


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
    doc = (REPO / "skills/flow-init/SKILL.md").read_text(encoding="utf-8")
    bullet = re.search(r"^- \*\*Copies\*\*.*?(?=^- \*\*)", doc, re.M | re.DOTALL)
    assert bullet, "flow-init/SKILL.md: the **Copies** bullet is gone — did the report change?"
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
