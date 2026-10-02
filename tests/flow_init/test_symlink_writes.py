"""A repo is untrusted input to /flow-init: a symlink it commits where the installer writes must
never carry that write outside the host. A write replaces a link standing at its own path; a
directory link that leaves the host refuses the write."""

from pathlib import Path

import pytest
import yaml

from scripts.flow_init_setup import (
    RULES_DEST,
    _render_one,
    check_precommit,
    copy_artifacts,
    copy_rules,
    render_deploy_workflows,
    render_unit_test_workflow,
    render_workflow,
    seed_design_templates,
)
from tests.flow_init._helpers import PLUGIN

VICTIM_TEXT = "victim\n"


def _link(link: Path, target: Path) -> None:
    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        link.symlink_to(target, target_is_directory=target.is_dir())
    except (OSError, NotImplementedError):
        pytest.skip("symlinks cannot be created here")


def _layout(tmp_path: Path) -> tuple[Path, Path]:
    host, outside = tmp_path / "host", tmp_path / "outside"
    host.mkdir()
    outside.mkdir()
    return host, outside


def _victim(outside: Path) -> Path:
    victim = outside / "victim"
    victim.write_text(VICTIM_TEXT, encoding="utf-8")
    return victim


def test_copy_rules_replaces_a_symlinked_rule(tmp_path):
    host, outside = _layout(tmp_path)
    victim = _victim(outside)
    dest = host / RULES_DEST / "doc-style.md"
    _link(dest, victim)
    copy_rules(PLUGIN, host)
    assert victim.read_text(encoding="utf-8") == VICTIM_TEXT
    assert not dest.is_symlink()
    assert dest.read_bytes() == (PLUGIN / "rules/doc-style.md").read_bytes()


def test_copy_rules_refuses_a_rules_dir_linked_outside(tmp_path):
    host, outside = _layout(tmp_path)
    _link(host / RULES_DEST, outside)
    report = copy_rules(PLUGIN, host)
    assert not (outside / "doc-style.md").exists()
    assert any("[!]" in ln for ln in report)


def test_copy_artifacts_replaces_symlinked_script_and_policy(tmp_path):
    host, outside = _layout(tmp_path)
    victim = _victim(outside)
    script = host / ".claude/harness-tier/scripts/_harness_paths.py"
    policy = host / ".claude/harness-tier/config/flow-tiers.yaml"
    _link(script, victim)
    _link(policy, victim)
    copy_artifacts(PLUGIN, host)
    assert victim.read_text(encoding="utf-8") == VICTIM_TEXT
    assert not script.is_symlink() and not policy.is_symlink()
    assert policy.read_bytes() == (PLUGIN / "flow-tiers.yaml").read_bytes()


def test_copy_artifacts_refuses_a_scripts_dir_linked_outside(tmp_path):
    host, outside = _layout(tmp_path)
    _link(host / ".claude/harness-tier/scripts", outside)
    copy_artifacts(PLUGIN, host)
    assert list(outside.iterdir()) == []


def test_copy_artifacts_makes_no_directory_outside(tmp_path):
    host, outside = _layout(tmp_path)
    _link(host / ".claude/harness-tier", outside)
    report = copy_artifacts(PLUGIN, host)
    assert list(outside.iterdir()) == []
    assert any("[!]" in ln for ln in report)


def test_seed_never_lands_through_a_dangling_link(tmp_path):
    host, outside = _layout(tmp_path)
    target = outside / "created"
    _link(host / ".claude/harness-tier/templates/design-docs/erd.template.md", target)
    seed_design_templates(PLUGIN, host)
    assert not target.exists()


def test_seed_refuses_a_templates_dir_linked_outside(tmp_path):
    host, outside = _layout(tmp_path)
    _link(host / ".claude/harness-tier/templates", outside)
    report = seed_design_templates(PLUGIN, host)
    assert list(outside.iterdir()) == []
    assert any("[!]" in ln for ln in report)


def test_precommit_example_never_lands_through_a_dangling_link(tmp_path):
    host, outside = _layout(tmp_path)
    target = outside / "created"
    _link(host / ".pre-commit-config.yaml", target)
    check_precommit(PLUGIN, host)
    assert not target.exists()


def test_render_never_lands_through_a_dangling_link(tmp_path):
    host, outside = _layout(tmp_path)
    target = outside / "created"
    dest = host / ".github/workflows/e2e.yml"
    _link(dest, target)
    _render_one(host, PLUGIN / "github/e2e.workflow.example.yml", dest, {})
    assert not target.exists()


def test_render_refuses_a_workflows_dir_linked_outside(tmp_path):
    host, outside = _layout(tmp_path)
    _link(host / ".github/workflows", outside)
    report = _render_one(
        host, PLUGIN / "github/e2e.workflow.example.yml", host / ".github/workflows/e2e.yml", {}
    )
    assert list(outside.iterdir()) == []
    assert any("[!]" in ln for ln in report)


def test_deploy_orchestrator_replaces_a_symlinked_file(tmp_path):
    host, outside = _layout(tmp_path)
    victim = _victim(outside)
    cfg = host / ".claude/harness-tier/config/flow-config.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text(
        "deploy:\n  enable: true\n  targets:\n    - name: pypi\n      target: pypi\n",
        encoding="utf-8",
    )
    orch = host / ".github/workflows/deploy.yml"
    _link(orch, victim)
    render_deploy_workflows(host, PLUGIN)
    assert victim.read_text(encoding="utf-8") == VICTIM_TEXT
    assert not orch.is_symlink() and orch.is_file()


def _config(host: Path, block: dict) -> None:
    cfg = host / ".claude/harness-tier/config/flow-config.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(yaml.safe_dump(block), encoding="utf-8")


@pytest.mark.parametrize(
    ("render", "block"),
    [
        (render_workflow, {"contract_test": {"enable": True}}),
        (
            render_unit_test_workflow,
            {"unit_test": {"enable": True, "jobs": [{"name": "py", "test": "pytest"}]}},
        ),
    ],
)
def test_config_renders_refuse_a_workflows_dir_linked_outside(tmp_path, render, block):
    host, outside = _layout(tmp_path)
    _config(host, block)
    _link(host / ".github/workflows", outside)
    report = render(host, PLUGIN)
    assert list(outside.iterdir()) == []
    assert any("[!]" in ln for ln in report)
