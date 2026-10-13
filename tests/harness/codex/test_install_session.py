"""Register the SessionStart and PostToolUse hooks in a host's .codex/hooks.json: the Codex
plugin ships no lifecycle hooks, since OpenAI's plugin directory refuses a package that does."""

import json
from pathlib import Path

import pytest

from scripts.harness.codex import install

HOOKS = Path(".codex/hooks.json")
TOP = "$(git rev-parse --show-toplevel)/.claude/harness-tier/hooks"


def _read(host: Path) -> dict:
    return json.loads((host / HOOKS).read_text(encoding="utf-8"))


def test_session_hook_strings_are_pinned():
    # Changing these makes every consumer re-approve the hooks in /hooks.
    start = install.SESSION_ENTRIES["SessionStart"]
    post = install.SESSION_ENTRIES["PostToolUse"]
    assert start["matcher"] == "startup|resume|clear|compact|fork"
    assert post["matcher"] == "apply_patch|Bash"
    assert start["hooks"] == [
        {
            "type": "command",
            "command": f'bash "{TOP}/inject-risk-tiers.sh" --harness codex',
            "commandWindows": f'& "{TOP}/codex/run-hook.cmd" inject-risk-tiers.sh --harness codex',
            "timeout": 30,
            "additionalContextLimit": 0,
        }
    ]
    assert post["hooks"] == [
        {
            "type": "command",
            "command": f'bash "{TOP}/invalidate-gate-markers.sh" --harness codex',
            "commandWindows": (
                f'& "{TOP}/codex/run-hook.cmd" invalidate-gate-markers.sh --harness codex'
            ),
            "timeout": 10,
        }
    ]


def test_register_session_creates_and_is_idempotent(tmp_path):
    assert "등록" in install.register_session(tmp_path)
    assert "이미" in install.register_session(tmp_path)
    assert _read(tmp_path) == {
        "hooks": {event: [entry] for event, entry in install.SESSION_ENTRIES.items()}
    }


def test_register_session_beside_the_gate_keeps_both(tmp_path):
    install.register(tmp_path)
    install.register_session(tmp_path)
    data = _read(tmp_path)["hooks"]
    assert data["PreToolUse"] == [install.GATE_ENTRY]
    assert data["SessionStart"] == [install.SESSION_ENTRIES["SessionStart"]]
    assert install.problems(tmp_path) == []


def test_register_session_keeps_user_hooks(tmp_path):
    (tmp_path / ".codex").mkdir()
    user = {"matcher": "startup", "hooks": [{"type": "command", "command": "echo mine"}]}
    (tmp_path / HOOKS).write_text(json.dumps({"hooks": {"SessionStart": [user]}}), encoding="utf-8")
    install.register_session(tmp_path)
    assert _read(tmp_path)["hooks"]["SessionStart"] == [
        user,
        install.SESSION_ENTRIES["SessionStart"],
    ]


def test_register_session_repairs_a_stale_hook_in_place(tmp_path):
    (tmp_path / ".codex").mkdir()
    stale = {
        "matcher": "startup",
        "hooks": [
            {"type": "command", "command": 'bash "x/harness-tier/hooks/inject-risk-tiers.sh"'}
        ],
    }
    (tmp_path / HOOKS).write_text(
        json.dumps({"hooks": {"SessionStart": [stale]}}), encoding="utf-8"
    )
    assert "[+]" in install.register_session(tmp_path)
    (entry,) = _read(tmp_path)["hooks"]["SessionStart"]
    assert entry["hooks"] == install.SESSION_ENTRIES["SessionStart"]["hooks"]


@pytest.mark.parametrize("bad", ['{"hooks": {}, "extra": 1}', "[]", "{not json"])
def test_register_session_refuses_files_codex_would_not_load(tmp_path, bad):
    (tmp_path / ".codex").mkdir()
    (tmp_path / HOOKS).write_text(bad, encoding="utf-8")
    assert "[!]" in install.register_session(tmp_path)
    assert (tmp_path / HOOKS).read_text(encoding="utf-8") == bad


def test_unregister_session_then_gate_removes_the_file(tmp_path):
    install.register(tmp_path)
    install.register_session(tmp_path)
    assert "해제" in install.unregister_session(tmp_path)
    assert _read(tmp_path) == {"hooks": {"PreToolUse": [install.GATE_ENTRY]}}
    install.unregister(tmp_path)
    assert not (tmp_path / HOOKS).exists()
    assert "없음" in install.unregister_session(tmp_path)


def test_unregister_session_alone_removes_the_file(tmp_path):
    install.register_session(tmp_path)
    install.unregister_session(tmp_path)
    assert not (tmp_path / HOOKS).exists()


def test_problems_names_a_missing_session_hook(tmp_path):
    install.register(tmp_path)
    assert any("SessionStart" in p for p in install.problems(tmp_path))


def test_session_hooks_remain_reports_a_leftover(tmp_path):
    assert not install.session_hooks_remain(tmp_path)
    install.register_session(tmp_path)
    assert install.session_hooks_remain(tmp_path)
