from pathlib import Path

import pytest
import yaml

from tests.flow_init._helpers import PLUGIN


def _release_tools():
    from scripts.flow_init_setup import _RELEASE_TEMPLATES

    return sorted(_RELEASE_TEMPLATES)


# The one release template whose tool cannot be handed a level: Node semantic-release derives
# the bump from commit types and reads no trailer. Listed rather than detected — a new
# auto-only template has to be a decision, and an unlisted one fails the test below.
_AUTO_ONLY_TOOLS = {"semantic-release"}


def _reads_the_trailer(body: str) -> bool:
    """The mechanism, not the mention: a run step that pulls the level out of the commit
    message with a `sed -nE` anchored on `^Release-Level:`. Every trailer-reading template also
    NAMES the trailer in a header comment, so a bare `"Release-Level" in body` is satisfied by
    that comment alone and stays green when the extraction line itself is deleted."""
    return any(
        not line.lstrip().startswith("#")
        and "git log" in line
        and "sed" in line
        and "^Release-Level:" in line
        for line in body.splitlines()
    )


def test_render_versioning_python(tmp_path):
    from scripts import flow_init_setup as m

    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    # place the SOURCE template
    (plugin / "github").mkdir(parents=True)
    (plugin / "github" / "release.python-semantic-release.workflow.example.yml").write_text(
        "on:\n  push:\n    branches: [__HARNESS_STABLE__, __HARNESS_PRERELEASE__]\n",
        encoding="utf-8",
    )
    (plugin / "github" / "branch-naming.workflow.example.yml").write_text(
        "name: branch-naming\n", encoding="utf-8"
    )
    ent_tmpl = (
        'on:\n  schedule:\n    - cron: "__HARNESS_ENTROPY_SCHEDULE__"\n'
        "paths: __HARNESS_ENTROPY_PATHS__\n"
    )
    (plugin / "github" / "entropy-check.workflow.example.yml").write_text(
        ent_tmpl, encoding="utf-8"
    )
    (host / ".claude" / "harness-tier" / "config").mkdir(parents=True)
    (host / ".claude" / "harness-tier" / "config" / "flow-config.yaml").write_text(
        "versioning:\n  enable: true\n  release_tool: python-semantic-release\n"
        "  branches: {stable: main, prerelease: stage}\n"
        "  branch_naming: {enable: true}\n"
        '  entropy: {enable: true, schedule: "0 0 * * 5", paths: ["src/"]}\n',
        encoding="utf-8",
    )
    m.render_versioning_workflows(host, plugin)
    rel = (host / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "[main, stage]" in rel and "__HARNESS_" not in rel
    assert (host / ".github" / "workflows" / "branch-naming.yml").exists()
    ent = (host / ".github" / "workflows" / "entropy-check.yml").read_text(encoding="utf-8")
    assert "0 0 * * 5" in ent and "src/" in ent


def test_render_versioning_disabled(tmp_path):
    from scripts import flow_init_setup as m

    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    (host / ".claude" / "harness-tier" / "config").mkdir(parents=True)
    (host / ".claude" / "harness-tier" / "config" / "flow-config.yaml").write_text(
        "versioning:\n  enable: false\n", encoding="utf-8"
    )
    m.render_versioning_workflows(host, plugin)
    assert not (host / ".github" / "workflows" / "release.yml").exists()


def test_release_templates_source_files_exist():
    from scripts.flow_init_setup import _RELEASE_TEMPLATES

    for tool, rel_path in _RELEASE_TEMPLATES.items():
        assert (PLUGIN / rel_path).is_file(), f"{tool}: missing template {rel_path}"


def _write_fake_release_template(plugin: Path, rel_path: str) -> None:
    dest = plugin / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        "on:\n  push:\n    branches: [__HARNESS_STABLE__, __HARNESS_PRERELEASE__]\n",
        encoding="utf-8",
    )


def test_render_versioning_new_tools_case_insensitive(tmp_path):
    from scripts import flow_init_setup as m
    from scripts.flow_init_setup import _RELEASE_TEMPLATES

    for tool in ("jreleaser", "gitversion", "cargo-release"):
        plugin = tmp_path / tool / "plugin"
        host = tmp_path / tool / "host"
        _write_fake_release_template(plugin, _RELEASE_TEMPLATES[tool])
        (host / ".claude" / "harness-tier" / "config").mkdir(parents=True)
        # Proper-noun casing (as a researcher might propose it) must still resolve.
        (host / ".claude" / "harness-tier" / "config" / "flow-config.yaml").write_text(
            f"versioning:\n  enable: true\n  release_tool: {tool.upper()}\n"
            "  branches: {stable: main, prerelease: stage}\n",
            encoding="utf-8",
        )
        m.render_versioning_workflows(host, plugin)
        rel = host / ".github" / "workflows" / "release.yml"
        assert rel.is_file(), f"{tool}: release.yml not rendered"
        assert "__HARNESS_" not in rel.read_text(encoding="utf-8")


def test_render_versioning_unknown_tool_skips(tmp_path):
    from scripts import flow_init_setup as m

    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    (host / ".claude" / "harness-tier" / "config").mkdir(parents=True)
    (host / ".claude" / "harness-tier" / "config" / "flow-config.yaml").write_text(
        "versioning:\n  enable: true\n  release_tool: some-made-up-tool\n"
        "  branches: {stable: main, prerelease: stage}\n",
        encoding="utf-8",
    )
    out = m.render_versioning_workflows(host, plugin)
    assert not (host / ".github" / "workflows" / "release.yml").exists()
    assert any("알 수 없는 release_tool" in line for line in out)


@pytest.mark.parametrize("tool", _release_tools())
def test_a_release_template_either_reads_the_trailer_or_is_declared_auto_only(tool: str):
    """0.3.1 shipped no release candidate because the promotion followed a sister plugin's
    `workflow_dispatch` level model while this repo's workflow reads a `Release-Level:` commit
    trailer. The two agree on `auto`, so six releases passed before a forced level broke it.

    `release-commit` greps the rendered workflow for the trailer and treats a miss as "the
    level cannot be forced". That reading is only safe while every template is one of the two
    known kinds, which is what this pins."""
    from scripts.flow_init_setup import _RELEASE_TEMPLATES

    body = (PLUGIN / _RELEASE_TEMPLATES[tool]).read_text(encoding="utf-8")
    if tool in _AUTO_ONLY_TOOLS:
        # The skill greps the whole file, comments included, so an auto-only template may not
        # name the trailer anywhere: a mention alone already answers "the level can be forced".
        assert "Release-Level" not in body, (
            f"{tool}: declared auto-only but the template now names the Release-Level trailer "
            f"— release-commit greps this file and would tell users the level can be forced "
            f"here. Drop it from _AUTO_ONLY_TOOLS if the tool now reads the trailer for real."
        )
    else:
        assert _reads_the_trailer(body), (
            f"{tool}: no run step extracts the Release-Level trailer (a header comment naming "
            f"it is not one) and the tool is not in _AUTO_ONLY_TOOLS. release-commit's grep "
            f"would still report the level as forcible while nothing reads it. Restore the "
            f"`git log -1 --pretty=%B | sed -nE 's/^Release-Level:...'` line, or list the tool "
            f"as auto-only."
        )


@pytest.mark.parametrize("tool", _release_tools())
def test_no_release_template_takes_the_bump_level_from_a_workflow_dispatch(tool: str):
    """The sister plugin vway-kit forces the level through `workflow_dispatch: inputs: level`.
    No template here does, and `release-commit` says so outright — a template that grew one
    would make that statement false while every existing test stayed green."""
    from scripts.flow_init_setup import _RELEASE_TEMPLATES

    body = (PLUGIN / _RELEASE_TEMPLATES[tool]).read_text(encoding="utf-8")
    # YAML 1.1 reads a bare `on` key as the boolean True, so ask for both spellings.
    doc = yaml.safe_load(body) or {}
    on = doc.get("on", doc.get(True)) or {}
    dispatch = (on.get("workflow_dispatch") or {}) if isinstance(on, dict) else {}
    inputs = (dispatch.get("inputs") or {}) if isinstance(dispatch, dict) else {}
    assert "level" not in inputs, (
        f"{tool}: takes a bump level from workflow_dispatch. release-commit states that no "
        f"template here does and never triggers one — update the skill before adding this."
    )
