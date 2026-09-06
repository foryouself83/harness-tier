from pathlib import Path

from tests.flow_init._helpers import PLUGIN


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
