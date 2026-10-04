"""A repo is untrusted input to /flow-init: a symlink it commits where the installer writes must
never carry that write outside the host. A write replaces a link standing at its own path; a
directory link that leaves the host refuses the write."""

import json
from pathlib import Path

import pytest
import yaml

from scripts.flow_init_setup import (
    GATE_ENTRY,
    RULES_DEST,
    _render_one,
    append_gitignore,
    check_precommit,
    copy_artifacts,
    integrate_release_deploy,
    register_gate,
    register_marketplace,
    remove_claude_md_block,
    remove_gitignore_lines,
    remove_rules,
    render_deploy_workflows,
    render_unit_test_workflow,
    render_workflow,
    seed_design_templates,
    unregister_gate,
)
from scripts.harness.codex import install as codex_install
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


def test_rule_cleanup_unlinks_a_rules_dir_linked_outside(tmp_path):
    host, outside = _layout(tmp_path)
    victim = _victim(outside)
    _link(host / RULES_DEST, outside)
    remove_rules(host)
    assert victim.read_text(encoding="utf-8") == VICTIM_TEXT
    assert not (host / RULES_DEST).exists()
    assert not (host / RULES_DEST).is_symlink()


def test_rule_cleanup_refuses_a_rules_parent_linked_outside(tmp_path):
    """Setup runs this on every re-sync, so a committed `.claude/rules` link must not turn
    the cleanup into an rmtree of whatever `harness-tier` directory sits at its target."""
    host, outside = _layout(tmp_path)
    victim = outside / "harness-tier" / "victim"
    victim.parent.mkdir()
    victim.write_text(VICTIM_TEXT, encoding="utf-8")
    _link(host / ".claude" / "rules", outside)
    report = remove_rules(host)
    assert victim.read_text(encoding="utf-8") == VICTIM_TEXT
    assert "[!]" in report


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


# ── in-place edits: a host file this rewrites must not be a link leaving the host ──

BARE_SETTINGS = '{"permissions": {"allow": []}}\n'
GATED_SETTINGS = json.dumps({"hooks": {"PreToolUse": [GATE_ENTRY]}}) + "\n"


@pytest.mark.parametrize(
    ("step", "body"),
    [
        (register_gate, BARE_SETTINGS),
        (register_marketplace, BARE_SETTINGS),
        (unregister_gate, GATED_SETTINGS),
    ],
)
def test_settings_steps_refuse_a_settings_file_linked_outside(tmp_path, step, body):
    """A committed `.claude/settings.json` pointing at `~/.claude/settings.json` would put the
    gate into every project of that user."""
    host, outside = _layout(tmp_path)
    victim = outside / "settings.json"
    victim.write_text(body, encoding="utf-8")
    _link(host / ".claude" / "settings.json", victim)
    report = step(host)
    assert victim.read_text(encoding="utf-8") == body
    assert (host / ".claude" / "settings.json").is_symlink()
    assert "[!]" in report


def test_unregister_empties_a_linked_settings_file_instead_of_unlinking_it(tmp_path):
    """Deleting the link would leave its target, still read through other paths, holding the
    gate that names the scripts the uninstall deletes."""
    host, _outside = _layout(tmp_path)
    shared = host / "shared" / "settings.json"
    shared.parent.mkdir()
    shared.write_text(GATED_SETTINGS, encoding="utf-8")
    _link(host / ".claude" / "settings.json", shared)
    assert "[-]" in unregister_gate(host)
    assert (host / ".claude" / "settings.json").is_symlink()
    assert json.loads(shared.read_text(encoding="utf-8")) == {}


def test_unregister_never_deletes_a_settings_file_through_a_claude_dir_linked_outside(tmp_path):
    host, outside = _layout(tmp_path)
    victim = outside / "settings.json"
    victim.write_text(GATED_SETTINGS, encoding="utf-8")
    _link(host / ".claude", outside)
    assert "[!]" in unregister_gate(host)
    assert victim.read_text(encoding="utf-8") == GATED_SETTINGS


def test_register_gate_refuses_a_claude_dir_linked_outside(tmp_path):
    """Copying refuses this directory, so registering into it left a hook naming no script."""
    host, outside = _layout(tmp_path)
    _link(host / ".claude", outside)
    report = register_gate(host)
    assert list(outside.iterdir()) == []
    assert "[!]" in report


def test_codex_register_refuses_a_hooks_file_linked_outside(tmp_path):
    host, outside = _layout(tmp_path)
    victim = outside / "hooks.json"
    victim.write_text("{}\n", encoding="utf-8")
    _link(host / ".codex" / "hooks.json", victim)
    report = codex_install.register(host)
    assert victim.read_text(encoding="utf-8") == "{}\n"
    assert "[!]" in report


def test_codex_unregister_never_deletes_through_a_dir_linked_outside(tmp_path):
    host, outside = _layout(tmp_path)
    victim = outside / "hooks.json"
    victim.write_text(
        json.dumps({"hooks": {"PreToolUse": [codex_install.GATE_ENTRY]}}) + "\n", encoding="utf-8"
    )
    _link(host / ".codex", outside)
    report = codex_install.unregister(host)
    assert victim.exists()
    assert "[!]" in report


def _report(out) -> str:
    return "\n".join(out) if isinstance(out, list) else out


@pytest.mark.parametrize(
    ("name", "edit", "body"),
    [
        (".gitignore", append_gitignore, VICTIM_TEXT),
        (".gitignore", remove_gitignore_lines, ".claude/harness-tier/.flow/\n"),
        (
            "CLAUDE.md",
            remove_claude_md_block,
            "<!-- harness-tier:teams BEGIN -->\nx\n<!-- harness-tier:teams END -->\n",
        ),
    ],
)
def test_in_place_edits_refuse_a_file_linked_outside(tmp_path, name, edit, body):
    host, outside = _layout(tmp_path)
    victim = outside / name
    victim.write_text(body, encoding="utf-8")
    _link(host / name, victim)
    report = _report(edit(host))
    assert victim.read_text(encoding="utf-8") == body
    assert "[!]" in report


def test_release_deploy_wiring_refuses_a_release_file_linked_outside(tmp_path):
    host, outside = _layout(tmp_path)
    _config(host, {"deploy": {"enable": True, "targets": [{"name": "p", "target": "pypi"}]}})
    body = "jobs:\n  # __HARNESS_DEPLOY_BEGIN__\n  # __HARNESS_DEPLOY_END__\n"
    victim = outside / "release.yml"
    victim.write_text(body, encoding="utf-8")
    _link(host / ".github/workflows/release.yml", victim)
    report = _report(integrate_release_deploy(host, PLUGIN))
    assert victim.read_text(encoding="utf-8") == body
    assert "[!]" in report
