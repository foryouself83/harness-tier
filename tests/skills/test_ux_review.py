import re

from tests.skills._helpers import REPO, body, frontmatter

AGENT = REPO / "agents/ux-outsider.md"


def test_outsider_reads_only_and_runs_on_sonnet():
    """The outsider's value is that it sees nothing but the capture: a write or shell tool
    lets it wander into the source and lose the first-time-user view."""
    fm = frontmatter(AGENT)
    assert fm["tools"] == "Read"
    assert fm["model"] == "sonnet"


def test_outsider_defines_both_personas_and_refuses_context():
    text = body(AGENT)
    assert "persona: customer" in text and "persona: auditor" in text
    assert "only the files" in text, "the agent must refuse to read beyond the paths it is given"


def test_egm_metaphor_only_in_its_attribution_line():
    """The skill speaks of owner, customer and auditor. The source pattern is credited once,
    on the line carrying its URL, and nowhere else."""
    files = [*REPO.glob("skills/ux-review/**/*.md"), AGENT]
    for f in files:
        for line in f.read_text(encoding="utf-8").splitlines():
            if re.search(r"(?i)elephant|goldfish", line):
                assert "github.com/google/elephant-goldfish-model" in line, f"{f.name}: {line}"


SKILL = REPO / "skills/ux-review/SKILL.md"


def test_no_install_is_preapproved():
    """Installing writes into the host's dependencies; the user's yes/no is the mechanism."""
    allowed = str(frontmatter(SKILL).get("allowed-tools", ""))
    assert not re.search(r"\b(npm|npx|pnpm|yarn)\b", allowed)


def test_capture_template_pins_spec_values():
    """`createRequire` from the cwd is what lets a monorepo's app directory resolve its own
    playwright when the run directory sits at the repository root."""
    text = body(SKILL)
    for v in ("1280", "800", "390", "844", "fullPage: false", "ariaSnapshot",
              "wcag22aa", "createRequire", "process.cwd()"):
        assert v in text, v


def test_run_dir_ignores_itself():
    assert "printf '*\\n' > \"$root/.claude/harness-tier/ux-review/.gitignore\"" in body(SKILL)


def test_degraded_paths_are_spelled_out():
    text = body(SKILL)
    for v in ("customer: not run (static mode)", "outsiders: skipped", "storageState",
              "no UI file", "commit them through `/flow`", "capture without axe",
              "Never role-play an outsider"):
        assert v in text, v


def test_run_dir_is_anchored_at_the_repository_root():
    """Commands run from the app directory; a relative run path lands the run inside a
    monorepo's app, where the capture step's root-anchored lookup never finds it."""
    text = body(SKILL)
    assert "mkdir -p .claude/harness-tier/ux-review" not in text
    assert 'root=$(git rev-parse --show-toplevel)' in text
    assert 'cd "$root"' not in text, "a persistent cd leaves the next capture running from the root"


def test_diff_mode_sees_uncommitted_ui_changes():
    """The skill leaves its own fixes uncommitted, so the work under review usually is too."""
    text = body(SKILL)
    assert "diff --name-only HEAD" in text
    assert "ls-files --others --exclude-standard" in text


def test_steps_can_be_limited_to_one_viewport():
    """A control hidden on mobile (a link inside a closed menu) times out the whole capture
    unless a step can say which viewport it belongs to."""
    assert "st.viewport && st.viewport !== vp" in body(SKILL)


def test_merged_findings_get_unique_ids():
    """`--full` runs several auditors whose `<screen>-<n>` ids collide; fixes are chosen by id."""
    assert "Renumber the merged findings" in body(SKILL)


def test_recheck_never_overwrites_the_original_capture():
    assert "a new run directory" in body(SKILL)


def test_dispatch_names_the_action_not_a_host_tool():
    """rules/harness-tools/vocabulary.md: each harness maps `Dispatch subagent <role>`."""
    text = body(SKILL)
    assert "Dispatch subagent `ux-outsider`" in text
    assert "fork_turns" not in text and "spawn_agent" not in text


def test_recheck_replays_whole_flows():
    """Steps carry over within a flow: a later screen starts from the state the earlier ones
    left, so copying only the touched screen starts it from a blank page."""
    text = body(SKILL)
    assert "every screen of each flow a fix touched" in text
    assert "only the screens a fix touched" not in text


def test_playwright_version_floor_is_checked():
    """`ariaSnapshot` lands in Playwright 1.49; older installs fail the capture with a TypeError
    that reads as a broken flow, not an old dependency."""
    text = body(SKILL)
    assert "require('playwright/package.json').version" in text
    assert "1.49" in text


def test_unresolved_base_url_falls_back_to_static_mode():
    assert "No base URL resolves" in body(SKILL)


def test_uncertain_route_mapping_is_asked_not_guessed():
    assert "mapping is uncertain" in body(SKILL)


def test_untracked_files_are_listed_from_the_repository_root():
    """`ls-files --others` lists only the cwd's subtree; the `:/` pathspec widens it."""
    assert "ls-files --others --exclude-standard --full-name :/" in body(SKILL)


def test_codex_inline_fallback_yields_to_the_skill():
    """The codex rule's inline fallback would have the owner play the outsider, which the
    skill forbids: the rule defers to a skill that names its own fallback."""
    text = (REPO / "rules/harness-tools/codex.md").read_text(encoding="utf-8")
    assert "do the work inline unless the skill names its own fallback" in text


def test_flow_config_is_read_from_the_repository_root():
    """Diff mode runs from a monorepo's app directory, where a cwd-relative config path misses
    the integration branch and silently diffs against `origin/HEAD`."""
    text = body(SKILL)
    assert "pathlib.Path('.claude/harness-tier/config/flow-config.yaml')" not in text
    assert "Path(sys.argv[1], '.claude/harness-tier/config/flow-config.yaml')" in text
    assert '"$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null)' in text


def test_playwright_upgrade_also_fetches_its_browser():
    """A newer Playwright pins a newer chromium; without it the first capture fails."""
    assert "playwright@latest` and `npx playwright install chromium`" in body(SKILL)
