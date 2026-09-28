"""A file copied into the host lands at its path under scripts/, so two harnesses may ship the same basename."""  # noqa: E501

from pathlib import Path

import scripts.flow_init_setup as fis
from tests.flow_init._helpers import PLUGIN

DEST = Path(".claude/harness-tier/scripts")


def test_flat_files_keep_their_destination(tmp_path: Path):
    fis.copy_artifacts(PLUGIN, tmp_path)
    for rel in fis.COPY_FILES:
        assert (tmp_path / DEST / Path(rel).name).is_file(), rel


def test_claude_only_host_gets_no_harness_tree(tmp_path: Path):
    fis.copy_artifacts(PLUGIN, tmp_path)
    assert not (tmp_path / DEST / "harness").exists()


def test_codex_files_keep_their_subpath(tmp_path: Path):
    fis.copy_artifacts(PLUGIN, tmp_path, harnesses=("claude", "codex"))
    assert (tmp_path / DEST / "harness" / "codex" / "gate.sh").is_file()
    assert (tmp_path / DEST / "harness" / "codex" / "gate.cmd").is_file()


def test_gate_files_include_codex_wrappers_only_when_enabled():
    claude_only = {rel for rel, _ in fis.gate_files(("claude",))}
    both = {rel for rel, _ in fis.gate_files(("claude", "codex"))}
    assert not any("harness/codex" in r for r in claude_only)
    codex_dest = f"{DEST.as_posix()}/harness/codex"
    assert {f"{codex_dest}/gate.sh", f"{codex_dest}/gate.cmd"} <= both


def test_missing_codex_wrapper_withholds_policy_when_codex_enabled(tmp_path: Path, monkeypatch):
    """The Codex hook runs gate.sh/gate.cmd directly (not through settings.json), so a copy
    that drops one must withhold the policy exactly like a missing Claude gate script — but
    only while codex is one of the enabled harnesses."""
    import shutil

    real = shutil.copyfile

    def refuse_codex_gate_sh(src, dst, *args, **kwargs):
        if Path(src).name == "gate.sh" and Path(src).parent.name == "codex":
            raise OSError(13, "held open by the host")
        return real(src, dst, *args, **kwargs)

    monkeypatch.setattr(shutil, "copyfile", refuse_codex_gate_sh)
    report = fis.copy_artifacts(PLUGIN, tmp_path, harnesses=("claude", "codex"))
    harness = tmp_path / ".claude" / "harness-tier"
    assert not (harness / "config" / "flow-tiers.yaml").exists()
    assert any("보류" in line for line in report)


def test_missing_codex_wrapper_does_not_withhold_when_codex_disabled(tmp_path: Path, monkeypatch):
    """The same broken copy of an unrelated harness's file must not touch a claude-only host --
    codex.gate.sh is never even attempted there."""
    import shutil

    real = shutil.copyfile

    def refuse_codex_gate_sh(src, dst, *args, **kwargs):
        if Path(src).name == "gate.sh" and Path(src).parent.name == "codex":
            raise OSError(13, "held open by the host")
        return real(src, dst, *args, **kwargs)

    monkeypatch.setattr(shutil, "copyfile", refuse_codex_gate_sh)
    report = fis.copy_artifacts(PLUGIN, tmp_path)
    harness = tmp_path / ".claude" / "harness-tier"
    assert (harness / "config" / "flow-tiers.yaml").is_file()
    assert not any("보류" in line for line in report)
