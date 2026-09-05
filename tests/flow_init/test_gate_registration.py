import json
import sys
from pathlib import Path

from scripts.flow_init_setup import (
    GATE_COMMAND,
    GITIGNORE_LINES,
    append_gitignore,
    check_precommit,
    main,
    register_gate,
)
from tests.flow_init._helpers import PLUGIN, _gate_commands, _is_gate


def test_register_gate_creates(tmp_path: Path):
    msg = register_gate(tmp_path)
    assert "등록" in msg
    cmds = _gate_commands(tmp_path / ".claude" / "settings.json")
    assert any(_is_gate(c) for c in cmds)


def test_register_gate_idempotent(tmp_path: Path):
    register_gate(tmp_path)
    msg = register_gate(tmp_path)
    assert "이미" in msg
    # not registered twice
    cmds = _gate_commands(tmp_path / ".claude" / "settings.json")
    assert sum(_is_gate(c) for c in cmds) == 1


def test_register_gate_preserves_existing(tmp_path: Path):
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    other = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo other"}]}
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [other]}}), encoding="utf-8")
    register_gate(tmp_path)
    cmds = _gate_commands(settings)
    assert "echo other" in cmds
    assert any(_is_gate(c) for c in cmds)


def test_append_gitignore_creates_and_idempotent(tmp_path: Path):
    first = append_gitignore(tmp_path)
    assert any("+=" in line for line in first)
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    for line in GITIGNORE_LINES:
        assert line in content
    second = append_gitignore(tmp_path)
    assert any("이미 최신" in line for line in second)
    # flow-config.yaml is team-shared, so it is excluded from the ignore list — not added.
    assert "flow-config.yaml" not in content
    assert content.count(".claude/harness-tier/.flow/") == 1


def test_append_gitignore_preserves_existing(tmp_path: Path):
    gi = tmp_path / ".gitignore"
    gi.write_text("node_modules/\n", encoding="utf-8")
    append_gitignore(tmp_path)
    content = gi.read_text(encoding="utf-8")
    assert "node_modules/" in content
    assert ".claude/harness-tier/.flow/" in content


def test_register_gate_refreshes_stale_status_message(tmp_path: Path):
    # when command is current but only statusMessage differs, repair it (not skip)
    from scripts.flow_init_setup import GATE_COMMAND, GATE_STATUS

    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    old = {
        "matcher": "Bash",
        "hooks": [
            {
                "type": "command",
                "command": GATE_COMMAND,
                "statusMessage": "harness-tier: flow 게이트 검사 중…",
            }
        ],
    }
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [old]}}), encoding="utf-8")
    msg = register_gate(tmp_path)
    assert "보정" in msg
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["hooks"]["PreToolUse"][0]["hooks"][0]["statusMessage"] == GATE_STATUS


def test_register_gate_repairs_stale_command(tmp_path: Path):
    # when a plugin update changed command, repair the registered stale command to the current path
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    # path different from current
    old_cmd = 'bash ".../.claude/harness-tier/other-path/precommit-runner.sh"'
    stale = {"matcher": "Bash", "hooks": [{"type": "command", "command": old_cmd}]}
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [stale]}}), encoding="utf-8")
    msg = register_gate(tmp_path)
    assert "보정" in msg
    cmds = _gate_commands(settings)
    # the single entry is repaired to the current path (no duplicate added)
    assert cmds == [GATE_COMMAND]


def test_register_gate_repairs_all_stale_entries(tmp_path: Path):
    # repair all duplicated stale gate entries to the current path
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    # path different from current
    old = 'bash ".../.claude/harness-tier/other-path/precommit-runner.sh"'
    dup = [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": old}]},
        {"matcher": "Bash", "hooks": [{"type": "command", "command": old}]},
    ]
    settings.write_text(json.dumps({"hooks": {"PreToolUse": dup}}), encoding="utf-8")
    msg = register_gate(tmp_path)
    assert "보정" in msg
    cmds = _gate_commands(settings)
    assert cmds == [GATE_COMMAND, GATE_COMMAND]  # both repaired (not only the first)


def test_check_precommit_reports_stale_owned_entry(tmp_path: Path):
    # report drift when the entry of a harness-tier-owned hook (teams-notify-push)
    # differs from the current path
    dest = tmp_path / ".pre-commit-config.yaml"
    dest.write_text(
        "repos:\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: teams-notify-push\n"
        "        name: x\n"
        "        entry: scripts/notify-push.sh\n"  # path different from current
        "        language: script\n",
        encoding="utf-8",
    )
    report = check_precommit(PLUGIN, tmp_path)
    assert any("entry 가 현재 경로와 다릅니다" in line for line in report)


def test_main_setup_then_uninstall_dispatch(tmp_path: Path, monkeypatch):
    # argparse dispatch + run_setup order (copy→register) end-to-end
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN))
    monkeypatch.setattr(sys, "argv", ["flow_init_setup.py"])
    main()
    vd = tmp_path / ".claude" / "harness-tier"
    settings = tmp_path / ".claude" / "settings.json"
    assert (vd / "scripts" / "precommit-runner.sh").is_file()
    assert (vd / "config" / "flow-tiers.yaml").is_file()
    assert any(_is_gate(c) for c in _gate_commands(settings))
    # --uninstall dispatch → inverse operation
    monkeypatch.setattr(sys, "argv", ["flow_init_setup.py", "--uninstall"])
    main()
    assert not vd.exists()
    assert not any(_is_gate(c) for c in _gate_commands(settings))
