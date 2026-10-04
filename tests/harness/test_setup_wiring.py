"""The `harnesses` config key, and how /flow-init's setup/uninstall wire it through."""

import json
import os
from pathlib import Path

import pytest

import scripts.flow_init_setup as fis
from tests.flow_init._helpers import PLUGIN

CFG = Path(".claude/harness-tier/config/flow-config.yaml")


def _cfg(host: Path, text: str) -> None:
    (host / CFG).parent.mkdir(parents=True, exist_ok=True)
    (host / CFG).write_text(text, encoding="utf-8")


@pytest.fixture(autouse=True)
def _hermetic_codex_home(tmp_path, monkeypatch):
    """`trust_notes` reads the real machine's ~/.codex/config.toml by default — point CODEX_HOME
    at an empty temp directory so these tests never depend on this machine's Codex trust state."""
    home = tmp_path / "codexhome"
    home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(home))


def test_absent_key_means_claude_only(tmp_path):
    assert fis.load_harnesses(tmp_path)[0] == ["claude"]


def test_absent_key_reports_no_lines(tmp_path):
    assert fis.load_harnesses(tmp_path)[1] == []


def test_the_example_harnesses_slot_is_claude_only_and_surfaces_to_backfill(tmp_path):
    """The example's `harnesses` value is live, so the slot report offers it to every host
    whose config predates the key; inserted verbatim, it must read exactly as the absent key."""
    import yaml

    example = yaml.safe_load((PLUGIN / fis.EXAMPLE_CONFIG).read_text(encoding="utf-8"))
    assert "harnesses" in example, "Step 2.5 backfill only offers keys the example sets"
    _cfg(tmp_path, "branches:\n  integration: dev\n")
    assert "harnesses" in [s["label"] for s in fis.missing_config_slots(tmp_path, PLUGIN)]
    _cfg(tmp_path, f"harnesses: {json.dumps(example['harnesses'])}\n")
    assert fis.load_harnesses(tmp_path) == fis.load_harnesses(tmp_path / "absent")
    assert fis.load_harnesses(tmp_path) == (["claude"], [], True)


def test_claude_is_always_first_and_unknowns_are_reported(tmp_path):
    _cfg(tmp_path, "harnesses: [codex, gemini, antigravity]\n")
    names, lines, reliable = fis.load_harnesses(tmp_path)
    assert names == ["claude", "codex"]
    assert any("gemini" in line for line in lines)
    assert any("antigravity" in line for line in lines)
    # An unrecognized entry in an otherwise well-formed list leaves the rest of `names`
    # trustworthy — this is a fact about `gemini`, not about the list itself.
    assert reliable is True


def test_a_repeated_or_explicit_claude_name_is_not_duplicated(tmp_path):
    _cfg(tmp_path, "harnesses: [claude, codex, codex]\n")
    names, _lines, _reliable = fis.load_harnesses(tmp_path)
    assert names == ["claude", "codex"]


def test_a_non_list_harnesses_value_is_reported_and_stays_claude_only(tmp_path):
    _cfg(tmp_path, "harnesses: codex\n")
    names, lines, reliable = fis.load_harnesses(tmp_path)
    assert names == ["claude"]
    assert any("[!]" in line and "harnesses" in line for line in lines), lines
    assert reliable is False


def test_claude_only_setup_writes_nothing_for_codex(tmp_path):
    assert fis.run_setup(tmp_path, PLUGIN)
    assert not (tmp_path / ".codex").exists()
    assert not (tmp_path / ".claude/harness-tier/scripts/harness").exists()


def test_codex_setup_registers_both(tmp_path):
    _cfg(tmp_path, "harnesses: [claude, codex]\n")
    assert fis.run_setup(tmp_path, PLUGIN)
    assert (tmp_path / ".codex/hooks.json").is_file()
    settings = json.loads((tmp_path / ".claude/settings.json").read_text(encoding="utf-8"))
    assert settings["hooks"]["PreToolUse"]


def test_codex_setup_relays_trust_notes(tmp_path, capsys):
    _cfg(tmp_path, "harnesses: [claude, codex]\n")
    fis.run_setup(tmp_path, PLUGIN)
    out = capsys.readouterr().out
    assert "trusted" in out or "/hooks" in out


def test_uninstall_clears_codex_even_when_config_dropped_it(tmp_path):
    _cfg(tmp_path, "harnesses: [claude, codex]\n")
    fis.run_setup(tmp_path, PLUGIN)
    _cfg(tmp_path, "harnesses: [claude]\n")
    assert fis.run_uninstall(tmp_path)
    assert not (tmp_path / ".codex/hooks.json").exists()


def test_uninstall_reports_codex_skip_line_on_a_claude_only_host(tmp_path, capsys):
    fis.run_uninstall(tmp_path)
    out = capsys.readouterr().out
    assert "[Codex 게이트 해제]" in out
    assert "Codex 게이트 훅 없음" in out


def test_gate_problems_reports_a_missing_codex_registration(tmp_path):
    _cfg(tmp_path, "harnesses: [claude, codex]\n")
    fis.run_setup(tmp_path, PLUGIN)
    (tmp_path / ".codex" / "hooks.json").unlink()
    problems = fis._gate_problems(tmp_path, PLUGIN, ["claude", "codex"])
    assert any(".codex/hooks.json" in p for p in problems), problems
    # The gate scripts themselves are still on disk (only the registration was removed) —
    # this must be the codex.problems() branch firing, not the missing-files one.
    assert not any("gate.sh" in p or "gate.cmd" in p for p in problems), problems


def _plant_claude_gate(tmp_path: Path) -> Path:
    """A host with a live, firing Claude gate hook in settings.json."""
    claude_dir = tmp_path / ".claude"
    claude_dir.mkdir(parents=True, exist_ok=True)
    settings = claude_dir / "settings.json"
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [fis.GATE_ENTRY]}}), encoding="utf-8")
    return settings


def _corrupt_codex_hooks(tmp_path: Path) -> None:
    """A shape `_load` refuses (an extra top-level key) beside the registered gate —
    `codex.unregister` reports it and leaves the file exactly as it was, so the hook is still
    there afterwards."""
    path = tmp_path / ".codex" / "hooks.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    data["extra"] = 1
    path.write_text(json.dumps(data), encoding="utf-8")


def test_uninstall_verdict_keeps_todays_exact_message_when_only_claude_is_left(tmp_path, capsys):
    settings = _plant_claude_gate(tmp_path)
    settings.chmod(0o444)
    try:
        if os.access(settings, os.W_OK):  # a host where the bit does not deny the owner
            pytest.skip("read-only is not enforced here")
        assert fis.run_uninstall(tmp_path) is False
        out = capsys.readouterr().out
        assert (
            "커밋 게이트 훅이 settings.json 에 남았습니다 — 방금 삭제된 스크립트를"
            " 가리키므로 직접 지우세요." in out
        )
        assert "Codex 커밋 게이트 훅이" not in out
    finally:
        settings.chmod(0o644)


def test_uninstall_verdict_names_codex_when_only_codex_is_left(tmp_path, capsys):
    _cfg(tmp_path, "harnesses: [claude, codex]\n")
    fis.run_setup(tmp_path, PLUGIN)
    _corrupt_codex_hooks(tmp_path)
    assert fis.run_uninstall(tmp_path) is False
    out = capsys.readouterr().out
    assert "Codex 커밋 게이트 훅이 .codex/hooks.json 에 남았습니다" in out
    assert "커밋 게이트 훅이 settings.json 에 남았습니다" not in out


def test_uninstall_verdict_names_both_when_both_are_left(tmp_path, capsys):
    _cfg(tmp_path, "harnesses: [claude, codex]\n")
    fis.run_setup(tmp_path, PLUGIN)
    _corrupt_codex_hooks(tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    settings.chmod(0o444)
    try:
        if os.access(settings, os.W_OK):
            pytest.skip("read-only is not enforced here")
        assert fis.run_uninstall(tmp_path) is False
        out = capsys.readouterr().out
        assert "커밋 게이트 훅이 settings.json 에 남았습니다" in out
        assert "Codex 커밋 게이트 훅이 .codex/hooks.json 에 남았습니다" in out
    finally:
        settings.chmod(0o644)


def test_a_codex_module_that_cannot_be_resolved_does_not_abort_the_whole_uninstall(
    tmp_path, monkeypatch, capsys
):
    """A Codex packaging failure must cost only the Codex step — every other host's Claude
    gate removal has to still run, not die on an uncaught exception before it starts."""
    settings = _plant_claude_gate(tmp_path)

    def _raise(_name):
        raise ImportError("codex install module cannot be imported")

    monkeypatch.setattr(fis.harness, "installer", _raise)
    # The gate did clear — the answer is True — but the Codex step itself could not
    # finish, so it is not a silent "정리 완료." either.
    assert fis.run_uninstall(tmp_path) is True
    out = capsys.readouterr().out
    assert "이 단계를 끝내지 못했습니다" in out  # the Codex step reported its own trouble
    assert "[-] 커밋 게이트 해제 (settings.json)" in out  # ...and did not stop the rest running
    assert "끝내지 못한 단계가 있습니다" in out
    assert not settings.exists()  # the Claude gate was removed, and with it all the file held


def test_a_codex_module_that_cannot_be_resolved_and_has_a_hooks_file_reports_it_may_remain(
    tmp_path, monkeypatch, capsys
):
    """FAIL-OPEN toward "may remain", not toward "gone" — a check that could not run is not
    proof of anything, and a `.codex/hooks.json` sitting right there says it might still hold
    the hook."""
    (tmp_path / ".codex").mkdir(parents=True)
    (tmp_path / ".codex" / "hooks.json").write_text("{}", encoding="utf-8")

    def _raise(_name):
        raise ImportError("codex install module cannot be imported")

    monkeypatch.setattr(fis.harness, "installer", _raise)
    assert fis.run_uninstall(tmp_path) is False
    out = capsys.readouterr().out
    assert "Codex 커밋 게이트 훅이 지워졌는지 확인하지 못했습니다" in out
    assert "Codex 커밋 게이트 훅이 .codex/hooks.json 에 남았습니다" not in out


@pytest.mark.parametrize(
    "body",
    [
        b"{broken",
        b"\xff\xfe{}",
        b"[]",
        b'{"hooks": "x"}',
        b'{"hooks": {"PreToolUse": "x"}}',
        b'{"hooks": {"PreToolUse": {}}}',
    ],
)
def test_a_claude_only_hosts_own_unreadable_codex_hooks_file_does_not_fail_uninstall(
    tmp_path, capsys, body
):
    """A `.codex/hooks.json` harness-tier never wrote to: no gate marker in its raw bytes."""
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex/hooks.json").write_bytes(body)
    assert fis.run_uninstall(tmp_path) is True
    out = capsys.readouterr().out
    assert "Codex 커밋 게이트 훅이" not in out, out
    assert "[i] .codex/hooks.json 을 해석하지 못했지만" in out, out
    assert (tmp_path / ".codex/hooks.json").read_bytes() == body


def test_an_unreadable_codex_hooks_file_carrying_the_gate_marker_fails_unconfirmed(
    tmp_path, capsys
):
    from scripts.harness.codex import install as codex_install

    (tmp_path / ".codex").mkdir()
    body = json.dumps({"hooks": {"PreToolUse": [codex_install.GATE_ENTRY]}})[:-1]
    (tmp_path / ".codex/hooks.json").write_text(body, encoding="utf-8")
    assert fis.run_uninstall(tmp_path) is False
    out = capsys.readouterr().out
    assert "Codex 커밋 게이트 훅이 지워졌는지 확인하지 못했습니다" in out, out
    assert "Codex 커밋 게이트 훅이 .codex/hooks.json 에 남았습니다" not in out, out


def test_a_codex_module_that_cannot_be_resolved_with_no_hooks_file_is_not_treated_as_a_leftover(
    tmp_path, monkeypatch, capsys
):
    """The other half of the same FAIL-OPEN rule: nothing ever created `.codex/hooks.json`,
    so there is nothing a resolution failure could be hiding — a claude-only host must not be
    told the Codex hook may remain."""

    def _raise(_name):
        raise ImportError("codex install module cannot be imported")

    monkeypatch.setattr(fis.harness, "installer", _raise)
    assert fis.run_uninstall(tmp_path) is True
    out = capsys.readouterr().out
    assert "Codex 커밋 게이트 훅이" not in out
    assert "커밋 게이트 훅이 settings.json 에 남았습니다" not in out
    assert "끝내지 못한 단계가 있습니다" in out


def test_a_harnesses_read_that_raises_costs_only_its_line(tmp_path, monkeypatch, capsys):
    def closed(_host):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(fis, "load_harnesses", closed)
    assert fis.run_setup(tmp_path, PLUGIN) is True
    out = capsys.readouterr().out
    assert "[!] harnesses 를 읽지 못했습니다(Permission denied)" in out, out
    assert "기계적 셋업 완료" in out, out
    assert not (tmp_path / ".codex").exists()


def test_dropping_codex_reports_what_it_left_and_removes_nothing(tmp_path, capsys):
    _cfg(tmp_path, "harnesses: [claude, codex]\n")
    (tmp_path / "CLAUDE.md").write_text("root rule\n", encoding="utf-8")
    fis.run_setup(tmp_path, PLUGIN)
    hooks = (tmp_path / ".codex/hooks.json").read_bytes()
    agents = (tmp_path / "AGENTS.md").read_bytes()
    _cfg(tmp_path, "harnesses: [claude]\n")
    capsys.readouterr()
    fis.run_setup(tmp_path, PLUGIN)
    out = capsys.readouterr().out
    notes = [line for line in out.splitlines() if "harnesses 에 codex 가 없지만" in line]
    assert len(notes) == 1, out
    assert ".codex/hooks.json" in notes[0] and "AGENTS.md" in notes[0], notes
    assert "/flow-uninstall" in notes[0], notes
    assert (tmp_path / ".codex/hooks.json").read_bytes() == hooks
    assert (tmp_path / "AGENTS.md").read_bytes() == agents


def test_a_claude_only_host_gets_no_leftover_note(tmp_path, capsys):
    (tmp_path / "AGENTS.md").write_text("the user's own file\n", encoding="utf-8")
    (tmp_path / ".codex").mkdir()
    (tmp_path / ".codex/hooks.json").write_text("{ their own, broken", encoding="utf-8")
    fis.run_setup(tmp_path, PLUGIN)
    assert "harnesses 에 codex 가 없지만" not in capsys.readouterr().out


def test_leftover_note_is_suppressed_when_harnesses_read_raises(tmp_path, monkeypatch, capsys):
    """The `run_setup` fallback (`load_harnesses` itself raises) answers `names == ["claude"]`
    without having read the real config, which may still list codex — the leftover note must
    not tell this host codex is unconfigured when that is unknown."""
    _cfg(tmp_path, "harnesses: [claude, codex]\n")
    fis.run_setup(tmp_path, PLUGIN)
    hooks = (tmp_path / ".codex/hooks.json").read_bytes()
    capsys.readouterr()

    def closed(_host):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(fis, "load_harnesses", closed)
    assert fis.run_setup(tmp_path, PLUGIN) is True
    out = capsys.readouterr().out
    assert "harnesses 를 읽지 못했습니다" in out, out
    assert "harnesses 에 codex 가 없지만" not in out, out
    assert (tmp_path / ".codex/hooks.json").read_bytes() == hooks


def test_leftover_note_is_suppressed_for_a_malformed_harnesses_value(tmp_path, capsys):
    """`load_harnesses` answers `["claude"]` for a non-list `harnesses:` value too, with its own
    `[!]` line — a host with codex leftovers and a typo'd config must not be told to uninstall
    a gate the real (malformed) config may still name."""
    _cfg(tmp_path, "harnesses: [claude, codex]\n")
    fis.run_setup(tmp_path, PLUGIN)
    hooks = (tmp_path / ".codex/hooks.json").read_bytes()
    _cfg(tmp_path, "harnesses: codex\n")
    capsys.readouterr()
    fis.run_setup(tmp_path, PLUGIN)
    out = capsys.readouterr().out
    assert "목록이어야 합니다" in out, out
    assert "harnesses 에 codex 가 없지만" not in out, out
    assert (tmp_path / ".codex/hooks.json").read_bytes() == hooks


def test_leftover_note_still_shows_beside_an_unrelated_unknown_name(tmp_path, capsys):
    """A `[!]` line is not by itself a sign the list is unreliable — `load_harnesses` also
    prints one for a single unrecognized entry in an otherwise well-formed list, and `names`
    stays trustworthy there. A host that genuinely dropped codex (in favor of a typo) must
    still be told about its leftover, not have the note swallowed by that unrelated `[!]`."""
    _cfg(tmp_path, "harnesses: [claude, codex]\n")
    fis.run_setup(tmp_path, PLUGIN)
    hooks = (tmp_path / ".codex/hooks.json").read_bytes()
    _cfg(tmp_path, "harnesses: [claude, some-typo]\n")
    capsys.readouterr()
    fis.run_setup(tmp_path, PLUGIN)
    out = capsys.readouterr().out
    assert "알 수 없는 이름 'some-typo'" in out, out
    assert "harnesses 에 codex 가 없지만" in out, out
    assert (tmp_path / ".codex/hooks.json").read_bytes() == hooks


def test_uninstall_does_not_report_a_gate_an_extra_key_file_never_held(tmp_path, capsys):
    (tmp_path / ".codex").mkdir()
    own = {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": []}]}, "x-team": True}
    (tmp_path / ".codex/hooks.json").write_text(json.dumps(own), encoding="utf-8")
    assert fis.run_uninstall(tmp_path) is True
    assert "Codex 커밋 게이트 훅이" not in capsys.readouterr().out
