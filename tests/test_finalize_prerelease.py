import json
import subprocess
import sys
from pathlib import Path

from scripts.finalize_prerelease import finalize, print_only, set_version

ROOT = Path(__file__).resolve().parent.parent


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


def test_set_version_writes_pyproject_and_plugin_json(tmp_path: Path):
    _seed(tmp_path, "1.0.0")
    set_version(tmp_path, "1.2.0-rc.1")
    pyproject_text = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "1.2.0-rc.1"' in pyproject_text
    plugin_data = json.loads(
        (tmp_path / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    )
    assert plugin_data["version"] == "1.2.0-rc.1"


def test_set_version_without_plugin_json_does_not_crash(tmp_path: Path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\nname = "x"\nversion = "1.0.0"\n'
        '[tool.semantic_release]\nversion_toml = ["pyproject.toml:project.version"]\n',
        encoding="utf-8",
    )
    set_version(tmp_path, "1.2.0-rc.1")  # must not raise even though plugin.json is absent
    pyproject_text = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "1.2.0-rc.1"' in pyproject_text
    assert not (tmp_path / ".claude-plugin").exists()


def test_print_only_writes_nothing(tmp_path: Path):
    _seed(tmp_path, "0.2.0-rc.1")
    before_pyproject = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    before_plugin = (tmp_path / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8")
    assert print_only(tmp_path) == "0.2.0"
    assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == before_pyproject
    assert (tmp_path / ".claude-plugin" / "plugin.json").read_text(
        encoding="utf-8"
    ) == before_plugin


def test_print_only_noop_on_stable(tmp_path: Path):
    _seed(tmp_path, "0.2.0")
    assert print_only(tmp_path) is None


def test_cli_print_only_prints_and_exits_zero(tmp_path: Path):
    _seed(tmp_path, "1.2.3-rc.4")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "finalize_prerelease.py"), "--print-only"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1.2.3"
    # writes nothing
    assert 'version = "1.2.3-rc.4"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")


def test_cli_print_only_exits_one_on_stable(tmp_path: Path):
    _seed(tmp_path, "1.2.3")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "finalize_prerelease.py"), "--print-only"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1
    assert result.stdout.strip() == ""


def test_cli_print_only_rejects_extra_args(tmp_path: Path):
    _seed(tmp_path, "1.2.3-rc.4")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "finalize_prerelease.py"), "--print-only", "x"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2


def test_cli_set_writes_and_prints_version(tmp_path: Path):
    _seed(tmp_path, "1.0.0")
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "finalize_prerelease.py"), "--set", "1.2.0-rc.1"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "1.2.0-rc.1"
    assert 'version = "1.2.0-rc.1"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
