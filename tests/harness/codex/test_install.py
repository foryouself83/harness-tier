"""Register the commit gate in a host's .codex/hooks.json and read (never write) Codex project
trust from the user's config.toml."""

import json
import os
import sys
from pathlib import Path

import pytest

from scripts.harness.codex import install

HOOKS = Path(".codex/hooks.json")

PINNED_COMMAND = (
    'bash "$(git rev-parse --show-toplevel)/.claude/harness-tier/scripts/harness/codex/gate.sh"'  # noqa: E501
)
PINNED_WINDOWS = (
    '& "$(git rev-parse --show-toplevel)/.claude/harness-tier/scripts/harness/codex/gate.cmd"'  # noqa: E501
)


def _stored_key(host: Path) -> str:
    """The project key as Codex writes it: lowercased on Windows only, where paths ignore case."""
    key = str(host.resolve())
    return key.lower() if os.name == "nt" else key


def _read(host: Path) -> dict:
    return json.loads((host / HOOKS).read_text(encoding="utf-8"))


def test_command_strings_are_pinned():
    # Changing these makes every consumer re-approve the hook in /hooks.
    assert install.GATE_HOOK == {
        "type": "command",
        "command": PINNED_COMMAND,
        "commandWindows": PINNED_WINDOWS,
        "timeout": 600,
        "statusMessage": "harness-tier: flow 게이트 + 테스트 검사 중…",
    }
    assert install.GATE_ENTRY == {"matcher": "Bash", "hooks": [install.GATE_HOOK]}


def test_register_creates_and_is_idempotent(tmp_path):
    assert "등록" in install.register(tmp_path)
    assert "이미" in install.register(tmp_path)
    data = _read(tmp_path)
    assert data == {"hooks": {"PreToolUse": [install.GATE_ENTRY]}}


def test_register_keeps_user_hooks_and_their_positions(tmp_path):
    (tmp_path / ".codex").mkdir()
    user = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo mine"}]}
    (tmp_path / HOOKS).write_text(
        json.dumps({"description": "d", "hooks": {"PreToolUse": [user]}}), encoding="utf-8"
    )
    install.register(tmp_path)
    data = _read(tmp_path)
    assert data["description"] == "d"
    assert data["hooks"]["PreToolUse"][0] == user
    assert data["hooks"]["PreToolUse"][1] == install.GATE_ENTRY


def test_register_keeps_other_events_untouched(tmp_path):
    (tmp_path / ".codex").mkdir()
    start_hook = {"type": "command", "command": "echo hi"}
    other = {"hooks": {"SessionStart": [{"matcher": "startup", "hooks": [start_hook]}]}}
    (tmp_path / HOOKS).write_text(json.dumps(other), encoding="utf-8")
    install.register(tmp_path)
    data = _read(tmp_path)
    assert data["hooks"]["SessionStart"] == other["hooks"]["SessionStart"]
    assert data["hooks"]["PreToolUse"] == [install.GATE_ENTRY]


def test_register_repairs_a_stale_gate_hook_in_place(tmp_path):
    (tmp_path / ".codex").mkdir()
    stale_command = 'bash "old/harness-tier/scripts/harness/codex/gate.sh"'
    stale = {"matcher": "Bash", "hooks": [{"type": "command", "command": stale_command}]}
    (tmp_path / HOOKS).write_text(json.dumps({"hooks": {"PreToolUse": [stale]}}), encoding="utf-8")
    assert "보정" in install.register(tmp_path)
    assert _read(tmp_path)["hooks"]["PreToolUse"] == [install.GATE_ENTRY]


@pytest.mark.parametrize("bad", ['{"hooks": {}, "extra": 1}', "[]", "{not json"])
def test_register_refuses_files_codex_would_not_load(tmp_path, bad):
    (tmp_path / ".codex").mkdir()
    (tmp_path / HOOKS).write_text(bad, encoding="utf-8")
    assert "[!]" in install.register(tmp_path)
    assert (tmp_path / HOOKS).read_text(encoding="utf-8") == bad


def test_unregister_removes_only_the_gate_and_empty_file(tmp_path):
    install.register(tmp_path)
    assert "해제" in install.unregister(tmp_path)
    assert not (tmp_path / HOOKS).exists()
    assert "없음" in install.unregister(tmp_path)


def test_unregister_keeps_a_file_with_user_hooks(tmp_path):
    (tmp_path / ".codex").mkdir()
    user = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo mine"}]}
    (tmp_path / HOOKS).write_text(json.dumps({"hooks": {"PreToolUse": [user]}}), encoding="utf-8")
    install.register(tmp_path)
    install.unregister(tmp_path)
    assert _read(tmp_path) == {"hooks": {"PreToolUse": [user]}}


def test_problems_names_a_missing_registration(tmp_path):
    assert any(".codex/hooks.json" in p for p in install.problems(tmp_path))
    install.register(tmp_path)
    assert install.problems(tmp_path) == []


def test_problems_treats_a_non_firing_matcher_as_not_registered(tmp_path):
    (tmp_path / ".codex").mkdir()
    entry = {"matcher": "Read", "hooks": [install.GATE_HOOK]}
    (tmp_path / HOOKS).write_text(json.dumps({"hooks": {"PreToolUse": [entry]}}), encoding="utf-8")
    assert any(".codex/hooks.json" in p for p in install.problems(tmp_path))


def test_problems_treats_an_exact_name_list_naming_bash_as_registered(tmp_path):
    (tmp_path / ".codex").mkdir()
    entry = {"matcher": "Read|Bash", "hooks": [install.GATE_HOOK]}
    (tmp_path / HOOKS).write_text(json.dumps({"hooks": {"PreToolUse": [entry]}}), encoding="utf-8")
    assert install.problems(tmp_path) == []


@pytest.mark.parametrize(
    "matcher,want",
    [
        ("Bash,Read", None),  # comma is outside Codex's exact-list alphabet -> a regex, undecided
        ("Bash|Read", True),  # `|` is Codex's own list separator -> exact match
        ("^Bash$", None),  # outside the alphabet -> a regex this does not evaluate
    ],
)
def test_fires_on_bash_uses_codexs_own_exact_list_alphabet(matcher, want):
    assert install._fires_on_bash(matcher) is want


def test_register_moves_a_gate_hook_out_of_a_non_firing_matcher(tmp_path):
    (tmp_path / ".codex").mkdir()
    entry = {"matcher": "Read", "hooks": [install.GATE_HOOK]}
    (tmp_path / HOOKS).write_text(json.dumps({"hooks": {"PreToolUse": [entry]}}), encoding="utf-8")
    report = install.register(tmp_path)
    assert "이동" in report
    data = _read(tmp_path)
    entries = data["hooks"]["PreToolUse"]
    assert {"matcher": "Read", "hooks": []} in entries
    assert install.GATE_ENTRY in entries
    assert install.problems(tmp_path) == []


def test_register_leaves_an_undecided_matcher_alone_and_appends_its_own(tmp_path):
    (tmp_path / ".codex").mkdir()
    undecided = {"matcher": "^Bash$", "hooks": [install.GATE_HOOK]}
    payload = json.dumps({"hooks": {"PreToolUse": [undecided]}})
    (tmp_path / HOOKS).write_text(payload, encoding="utf-8")
    install.register(tmp_path)
    data = _read(tmp_path)
    entries = data["hooks"]["PreToolUse"]
    assert undecided in entries  # the user's entry, byte-for-byte, still there
    assert install.GATE_ENTRY in entries
    assert len(entries) == 2


def test_hook_remains_true_after_register_false_after_unregister(tmp_path):
    assert install.hook_remains(tmp_path) is False
    install.register(tmp_path)
    assert install.hook_remains(tmp_path) is True
    install.unregister(tmp_path)
    assert install.hook_remains(tmp_path) is False


def test_trust_notes_read_the_user_config_without_writing(tmp_path):
    home = tmp_path / "codexhome"
    home.mkdir()
    host = tmp_path / "Host"
    host.mkdir()
    notes = install.trust_notes(host, home)
    assert any("trusted" in n for n in notes)  # not trusted yet -> says how
    key = _stored_key(host)
    config = home / "config.toml"
    config.write_text(f"[projects.'{key}']\ntrust_level = \"trusted\"\n", encoding="utf-8")
    before = config.read_bytes()
    notes = install.trust_notes(host, home)
    assert not any("trust_level" in n for n in notes)
    assert any("/hooks" in n for n in notes)  # hook approval is always a reminder
    assert (home / "config.toml").read_bytes() == before


def test_trust_notes_accepts_double_quoted_keys(tmp_path):
    home = tmp_path / "codexhome"
    home.mkdir()
    host = tmp_path / "Host2"
    host.mkdir()
    key = _stored_key(host)
    (home / "config.toml").write_text(
        f'[projects."{key}"]\ntrust_level = "trusted"\n', encoding="utf-8"
    )
    notes = install.trust_notes(host, home)
    assert not any("trusted" in n and "[!]" in n for n in notes)


@pytest.mark.skipif(sys.platform != "win32", reason="case-insensitive path matching is nt-only")
def test_trust_notes_matches_windows_path_case_insensitively(tmp_path):
    home = tmp_path / "codexhome"
    home.mkdir()
    host = tmp_path / "MixedCaseHost"
    host.mkdir()
    key = str(host.resolve()).upper()
    (home / "config.toml").write_text(
        f"[projects.'{key}']\ntrust_level = \"trusted\"\n", encoding="utf-8"
    )
    notes = install.trust_notes(host, home)
    assert not any("trusted" in n and "[!]" in n for n in notes)


def test_trust_notes_unescapes_basic_string_keys(tmp_path):
    home = tmp_path / "codexhome"
    home.mkdir()
    host = tmp_path / "Host4"
    host.mkdir()
    escaped = _stored_key(host).replace("\\", "\\\\")
    (home / "config.toml").write_text(
        f'[projects."{escaped}"]\ntrust_level = "trusted"\n', encoding="utf-8"
    )
    notes = install.trust_notes(host, home)
    assert not any("trusted" in n and "[!]" in n for n in notes), notes


def test_hook_remains_ignores_an_extra_top_level_key_without_a_gate(tmp_path):
    (tmp_path / ".codex").mkdir()
    other = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo hi"}]}
    payload = {"hooks": {"PreToolUse": [other]}, "x-team": 1}
    (tmp_path / HOOKS).write_text(json.dumps(payload), encoding="utf-8")
    assert install.hook_remains(tmp_path) is False
    payload["hooks"]["PreToolUse"].append(install.GATE_ENTRY)
    (tmp_path / HOOKS).write_text(json.dumps(payload), encoding="utf-8")
    assert install.hook_remains(tmp_path) is True


def test_trust_notes_never_raises_on_odd_config(tmp_path):
    home = tmp_path / "codexhome"
    home.mkdir()
    host = tmp_path / "Host3"
    host.mkdir()
    (home / "config.toml").write_bytes(b"\xff\xfe not valid utf-8 at all [[[")
    notes = install.trust_notes(host, home)
    assert any("trusted" in n for n in notes)
