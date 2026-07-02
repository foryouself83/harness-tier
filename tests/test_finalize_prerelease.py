import json
from pathlib import Path

from scripts.finalize_prerelease import finalize


def _seed(tmp_path: Path, version: str) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "x"\nversion = "{version}"\n'
        '[tool.semantic_release]\nversion_toml = ["pyproject.toml:project.version"]\n',
        encoding="utf-8",
    )
    pc = tmp_path / ".claude-plugin"
    pc.mkdir()
    plugin_text = json.dumps({"name": "x", "version": version}) + "\n"
    (pc / "plugin.json").write_text(plugin_text, encoding="utf-8")
    return tmp_path


def test_strips_prerelease(tmp_path: Path):
    _seed(tmp_path, "0.2.0-rc.1")
    assert finalize(tmp_path) == "0.2.0"
    pyproject_text = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "0.2.0"' in pyproject_text
    plugin_path = tmp_path / ".claude-plugin" / "plugin.json"
    plugin_data = json.loads(plugin_path.read_text(encoding="utf-8"))
    assert plugin_data["version"] == "0.2.0"


def test_noop_on_stable(tmp_path: Path):
    _seed(tmp_path, "0.2.0")
    before_plugin = (tmp_path / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    assert finalize(tmp_path) is None
    assert 'version = "0.2.0"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert (tmp_path / ".claude-plugin" / "plugin.json").read_text(
        encoding="utf-8"
    ) == before_plugin


def test_targets_project_version_not_sr_lines(tmp_path: Path):
    # version_toml/version_variables lines must be untouched
    # (regex targets the bare project version)
    _seed(tmp_path, "1.2.3-rc.4")
    finalize(tmp_path)
    text = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "1.2.3"' in text
    assert 'version_toml = ["pyproject.toml:project.version"]' in text


def test_preserves_plugin_json_formatting(tmp_path: Path):
    # only the version string changes; an unrelated inline-nested field keeps its formatting
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "0.2.0-rc.1"\n', encoding="utf-8"
    )
    pc = tmp_path / ".claude-plugin"
    pc.mkdir()
    original = '{\n  "name": "x",\n  "version": "0.2.0-rc.1",\n  "author": { "name": "a" }\n}\n'
    (pc / "plugin.json").write_text(original, encoding="utf-8")
    finalize(tmp_path)
    after = (pc / "plugin.json").read_text(encoding="utf-8")
    assert '"version": "0.2.0"' in after
    assert '"author": { "name": "a" }' in after  # inline nested field NOT reformatted
