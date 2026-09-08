from pathlib import Path

import yaml as _yaml

from scripts.flow_init_setup import (
    load_e2e_config,
    missing_config_slots,
    render_e2e_workflow,
)
from tests.flow_init._helpers import PLUGIN

TEMPLATE = PLUGIN / "github" / "e2e.workflow.example.yml"


def _template_text() -> str:
    return TEMPLATE.read_text(encoding="utf-8")


def test_e2e_template_carries_no_render_tokens():
    # D6: the delivery path is a token-free copy, so a token here would be shipped verbatim
    # into the consumer's workflow and never substituted.
    assert "__HARNESS_" not in _template_text()


def test_e2e_template_has_no_pull_request_trigger():
    # D12: a fork PR gets no secrets, so a credentialed suite red-lights every outside
    # contribution. The consumer opts in after reading the required-check checklist.
    data = _yaml.safe_load(_template_text())
    on = data.get(True) or data.get("on")  # PyYAML reads a bare `on:` key as the boolean True
    assert "pull_request" not in on
    assert "push" in on and "workflow_dispatch" in on


def test_e2e_template_guards_on_a_playwright_config():
    # D14: the run command is a Playwright literal, which is what lets the template know the
    # config file's naming convention and therefore no-op green like wiki-verify does.
    text = _template_text()
    assert "playwright.config." in text
    assert "steps.detect.outputs.found" in text


def test_e2e_template_guards_every_step_after_detect():
    # The whole "enabled but no suite is green, not permanently red" promise lives in each
    # step's own `if:` — a string match anywhere in the file (the assertion this replaced)
    # stays green even if a guard is deleted, as long as the words survive elsewhere (the
    # detect step's own echo, or Teardown's guard). Parse the YAML and check every step
    # instead, so dropping any one guard fails this test.
    data = _yaml.safe_load(_template_text())
    steps = data["jobs"]["e2e"]["steps"]
    detect_index = next(i for i, step in enumerate(steps) if step.get("id") == "detect")
    assert detect_index >= 0
    for step in steps[detect_index + 1 :]:
        condition = step.get("if", "")
        assert "steps.detect.outputs.found" in condition, (
            f"step {step.get('name')!r} runs after detect without gating on its output"
        )


def test_e2e_template_job_carries_a_timeout():
    data = _yaml.safe_load(_template_text())
    assert data["jobs"]["e2e"]["timeout-minutes"] > 0


def _write_flow_config(host: Path, e2e: dict | None) -> None:
    cfg_dir = host / ".claude" / "harness-tier" / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    body = {} if e2e is None else {"e2e": e2e}
    (cfg_dir / "flow-config.yaml").write_text(
        _yaml.safe_dump(body, allow_unicode=True), encoding="utf-8"
    )


def test_render_e2e_creates_when_enabled(tmp_path: Path):
    _write_flow_config(tmp_path, {"enable": True})
    out = render_e2e_workflow(tmp_path, PLUGIN)
    assert any("생성" in line for line in out)
    dest = tmp_path / ".github" / "workflows" / "e2e.yml"
    assert dest.is_file()
    assert dest.read_text(encoding="utf-8") == _template_text()  # a copy, not a render


def test_render_e2e_skips_when_disabled(tmp_path: Path):
    _write_flow_config(tmp_path, {"enable": False})
    out = render_e2e_workflow(tmp_path, PLUGIN)
    assert any("enable=false" in line for line in out)
    assert not (tmp_path / ".github" / "workflows" / "e2e.yml").exists()


def test_render_e2e_skips_when_section_absent(tmp_path: Path):
    _write_flow_config(tmp_path, None)
    out = render_e2e_workflow(tmp_path, PLUGIN)
    assert any("미설정" in line for line in out)
    assert not (tmp_path / ".github" / "workflows" / "e2e.yml").exists()


def test_render_e2e_is_non_destructive(tmp_path: Path):
    _write_flow_config(tmp_path, {"enable": True})
    dest = tmp_path / ".github" / "workflows" / "e2e.yml"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text("# the consumer's own edits\n", encoding="utf-8")
    out = render_e2e_workflow(tmp_path, PLUGIN)
    assert dest.read_text(encoding="utf-8") == "# the consumer's own edits\n"
    assert any("이미 있어" in line for line in out)


def test_render_e2e_points_at_the_scaffold_when_no_config_exists(tmp_path: Path):
    # D8=C makes delivery a human trigger: the boolean can render the workflow while no
    # projects[] exists anywhere. The /flow-init report is where that gets closed.
    _write_flow_config(tmp_path, {"enable": True})
    out = render_e2e_workflow(tmp_path, PLUGIN)
    assert any("playwright-scaffold" in line for line in out)


def test_render_e2e_stays_quiet_when_a_config_exists(tmp_path: Path):
    _write_flow_config(tmp_path, {"enable": True})
    (tmp_path / "playwright.config.ts").write_text("export default {};\n", encoding="utf-8")
    out = render_e2e_workflow(tmp_path, PLUGIN)
    assert not any("playwright-scaffold" in line for line in out)


def test_render_e2e_stays_quiet_when_a_nested_config_exists(tmp_path: Path):
    # Root plus two levels down, matching the workflow's own `find -maxdepth 3` and EDIT 4's
    # own example path — a monorepo config here must not still trip the scaffold pointer.
    _write_flow_config(tmp_path, {"enable": True})
    nested = tmp_path / "apps" / "web"
    nested.mkdir(parents=True)
    (nested / "playwright.config.ts").write_text("export default {};\n", encoding="utf-8")
    out = render_e2e_workflow(tmp_path, PLUGIN)
    assert not any("playwright-scaffold" in line for line in out)


def test_load_e2e_config_fails_open_on_a_broken_file(tmp_path: Path):
    cfg_dir = tmp_path / ".claude" / "harness-tier" / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "flow-config.yaml").write_text("e2e: [broken\n", encoding="utf-8")
    assert load_e2e_config(tmp_path) is None


def test_e2e_slot_ships_disabled_in_the_example():
    # Spec 5: the slot must exist in the example (that is the only channel telling an
    # EXISTING consumer the feature arrived) and must ship false, like wiki/doc_style/deploy.
    example = _yaml.safe_load((PLUGIN / "flow-config.example.yaml").read_text(encoding="utf-8"))
    assert example["e2e"]["enable"] is False


def test_e2e_slot_is_reported_as_missing(tmp_path: Path):
    _write_flow_config(tmp_path, None)
    labels = [s["label"] for s in missing_config_slots(tmp_path, PLUGIN)]
    assert "e2e" in labels
