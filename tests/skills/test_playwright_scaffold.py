from pathlib import Path

SKILL = Path(__file__).resolve().parents[2] / "skills" / "playwright-scaffold" / "SKILL.md"


def test_scaffolded_config_reads_the_base_url_from_the_environment():
    # The plugin's own guidance (skills/integration/references/web-playwright.md:193)
    # prescribes process.env.BASE_URL. The scaffold wrote a bare literal, so two of the
    # plugin's artifacts disagreed and the CI stack could not publish a different port.
    text = SKILL.read_text(encoding="utf-8")
    assert "process.env.BASE_URL" in text
    # Pins the scaffolded block's exact baseURL line: read through the env var, with the
    # literal only as the `??` fallback. A weaker "bare literal not in text" check would
    # stay green even if the bare-literal line survived untouched elsewhere in the file.
    assert "baseURL: process.env.BASE_URL ?? 'http://localhost:3000'," in text


def test_scaffolded_config_declares_a_trace_policy():
    # A trace carries request/response bodies and session tokens, so whether the workflow's
    # artifact upload is safe is decided here, not there.
    text = SKILL.read_text(encoding="utf-8")
    assert "retain-on-failure" in text
    assert "video:" in text


def test_scaffold_reports_projects_when_a_config_already_exists():
    # D7 delegates multi-app fan-out to Playwright's own projects[]; D8 = C makes this skill
    # the delivery path, which means it must say something in the case it does not write.
    # A bare "projects" in text is satisfied by unrelated pre-existing prose ("empty
    # projects", Step 3) even without this change, so both loci this edit added
    # are pinned: the projects[] shape in the scaffolded config, and the Step 5 report
    # bullet's own wording — either one reverted fails this test.
    text = SKILL.read_text(encoding="utf-8")
    assert "projects: [" in text
    assert "Report the `projects[]` shape a" in text
