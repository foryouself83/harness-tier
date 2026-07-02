"""Behavior spec for the shared helper _harness_paths — path SSOT, fallback helpers,
encoding defenses.

If this module breaks, path resolution in every gate script breaks along with it, so the
consolidated behavior is pinned here in one place (previously each script carried its own
host_root/force_utf8_io and tested it separately).
"""

from pathlib import Path

import scripts._harness_paths as vp


def test_path_segment_constants():
    # the host write root and its subcategories are all gathered under
    # .claude/harness-tier/ (CLAUDE.md).
    assert vp.HARNESS_DIR == ".claude/harness-tier"
    assert vp.SCRIPTS_DIR == ".claude/harness-tier/scripts"
    assert vp.CONFIG_DIR == ".claude/harness-tier/config"
    assert vp.FLOW_DIR == ".claude/harness-tier/.flow"


def test_filename_constants():
    assert vp.CONFIG_FILENAME == "flow-config.yaml"
    assert vp.TIERS_FILENAME == "flow-tiers.yaml"


def test_gate_contract_constants():
    # Invariant #3: block = exit 2. Runtime gates and tier labels are byte-match targets
    # against yaml keys.
    assert vp.BLOCK_EXIT_CODE == 2
    assert "security-scan" in vp.RUNTIME_GATES
    assert vp.STAGING_TIER == "staging"
    assert vp.RELEASE_TIER == "release"


def test_path_helpers_compose_from_root(tmp_path: Path):
    assert vp.harness_dir(tmp_path) == tmp_path / ".claude" / "harness-tier"
    assert vp.config_dir(tmp_path) == tmp_path / ".claude" / "harness-tier" / "config"
    assert vp.flow_dir(tmp_path) == tmp_path / ".claude" / "harness-tier" / ".flow"
    assert vp.config_path(tmp_path) == (
        tmp_path / ".claude" / "harness-tier" / "config" / "flow-config.yaml"
    )


def test_host_root_prefers_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert vp.host_root() == tmp_path.resolve()


def test_host_root_fallback_no_crash(monkeypatch, tmp_path: Path):
    # env unset + git failure → cwd fallback when the marker (.claude) lookup fails
    # (no IndexError/crash).
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)

    def boom(*_a, **_k):
        raise OSError("no git")

    monkeypatch.setattr(vp.subprocess, "run", boom)
    result = vp.host_root()
    assert isinstance(result, Path)  # path without marker → cwd fallback (no crash)


def test_plugin_root_prefers_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    assert vp.plugin_root() == tmp_path


def test_plugin_root_fallback_is_scripts_parent(monkeypatch):
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    # _harness_paths.py lives in scripts/, so the fallback is its parent (the plugin root).
    assert vp.plugin_root() == Path(vp.__file__).resolve().parent.parent


def test_force_utf8_io_sets_pythonutf8(monkeypatch):
    # set PYTHONUTF8 so child python processes inherit the encoding (reinforces Invariant #2).
    monkeypatch.delenv("PYTHONUTF8", raising=False)
    vp.force_utf8_io()
    assert vp.os.environ.get("PYTHONUTF8") == "1"
