import json
import sys
from pathlib import Path

import pytest

from tests.flow_init._helpers import (
    MALFORMED,
    PLUGIN,
    _gate_commands,
    _gate_hook,
    _gate_is_in,
    _is_gate,
    _planted,
)


def test_uninstall_leaves_a_host_hook_that_shares_the_gate_entry(tmp_path: Path):
    """The gate hook stays inside a host entry whenever that entry already fires on Bash, so
    removing the entry on the way out takes hooks the host wrote."""
    import scripts.flow_init_setup as fis

    fis.register_gate(tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    data = json.loads(settings.read_text(encoding="utf-8"))
    theirs = {"type": "command", "command": "my-audit.sh"}
    data["hooks"]["PreToolUse"][0]["hooks"].append(theirs)
    settings.write_text(json.dumps(data), encoding="utf-8")

    assert "skip" in fis.register_gate(tmp_path)
    fis.unregister_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    hooks = [h for e in pre for h in e.get("hooks") or []]
    assert theirs in hooks, pre
    assert not [h for h in hooks if fis._is_gate_hook(h)], pre


def test_uninstall_keeps_a_host_entry_it_only_emptied(tmp_path: Path):
    import scripts.flow_init_setup as fis

    settings = _planted(
        tmp_path, [{"matcher": "Read", "team_note": "ours", "hooks": [_gate_hook()]}]
    )
    fis.register_gate(tmp_path)
    fis.unregister_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert {"matcher": "Read", "team_note": "ours", "hooks": []} in pre, pre


def test_uninstall_drops_the_entry_it_wrote_itself(tmp_path: Path):
    import scripts.flow_init_setup as fis

    fis.register_gate(tmp_path)
    fis.unregister_gate(tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    assert json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"] == []


def test_a_gate_that_runs_more_than_once_says_so(tmp_path: Path):
    """Two gate hooks the host can reach are two gate runs per commit. Removing one would take
    a hook this plugin may not have written; not saying so reports a gate state that is not the
    one the host has."""
    import scripts.flow_init_setup as fis

    _planted(tmp_path, [{"matcher": "Bash", "hooks": [_gate_hook(), _gate_hook()]}])
    assert "2개" in fis.register_gate(tmp_path)


def test_moving_a_hook_is_written_even_when_the_gate_is_already_there(tmp_path: Path):
    """A move with nothing else to do still changes the file, so reporting it as a skip leaves
    the host with a gate hook under a matcher that does not fire and no record of it."""
    import scripts.flow_init_setup as fis

    settings = _planted(
        tmp_path,
        [
            {"matcher": "Bash", "hooks": [_gate_hook()]},
            {"matcher": "Read", "hooks": [_gate_hook()]},
        ],
    )
    out = fis.register_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert "skip" not in out and "1건" in out, out
    assert pre[1]["hooks"] == [], pre


def test_the_repair_count_covers_the_hooks_it_moved(tmp_path: Path):
    import scripts.flow_init_setup as fis

    # The path a release before the scripts/ subdirectory installed to. It still says
    # harness-tier, which is what separates this from a hook the host wrote.
    stale = dict(
        _gate_hook(),
        command='bash "${CLAUDE_PROJECT_DIR:-.}/.claude/harness-tier/precommit-runner.sh"',
    )
    _planted(
        tmp_path,
        [
            {"matcher": "Bash", "hooks": [stale]},
            {"matcher": "Read", "hooks": [_gate_hook()]},
        ],
    )
    assert "2건" in fis.register_gate(tmp_path)


def test_uninstall_keeps_the_keys_the_host_put_beside_the_gate(tmp_path: Path):
    """The entry carries the gate's own matcher, so only its key set says whether the host
    wrote anything into it."""
    import scripts.flow_init_setup as fis

    settings = _planted(
        tmp_path, [{"matcher": "Bash", "team_note": "ours", "hooks": [_gate_hook()]}]
    )
    fis.unregister_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert pre == [{"matcher": "Bash", "team_note": "ours", "hooks": []}], pre


def test_uninstall_keeps_a_host_entry_that_only_looks_like_the_gates(tmp_path: Path):
    """Same keys, same emptiness — the matcher is the only thing left that says whose entry it
    is, and dropping it here takes an entry the host wrote."""
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": "Read", "hooks": [_gate_hook()]}])
    fis.register_gate(tmp_path)
    fis.unregister_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert pre == [{"matcher": "Read", "hooks": []}], pre


def test_uninstall_with_no_gate_present_writes_nothing(tmp_path: Path):
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": "Bash", "hooks": [{"command": "theirs.sh"}]}])
    before = settings.read_text(encoding="utf-8")
    assert "skip" in fis.unregister_gate(tmp_path)
    assert settings.read_text(encoding="utf-8") == before


@pytest.mark.parametrize("label,payload", MALFORMED, ids=[label for label, _ in MALFORMED])
def test_setup_finishes_its_other_steps_on_a_settings_shape_it_cannot_use(
    tmp_path: Path, label: str, payload, monkeypatch, capsys
):
    """/flow-init prints each step's result unguarded, so one raise takes the marketplace
    registration, the pre-commit check, the .gitignore lines and every rendered workflow down
    with the gate — and a guard in the gate alone only moves the raise to the next step.

    Finishing is not succeeding, though: a gate that did not register is the install's whole
    point missing, and its one `[!]` scrolls past among forty other lines. So the last line and
    the exit code have to agree with the gate, whichever way it went."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN))
    monkeypatch.setattr(sys, "argv", ["flow_init_setup.py"])
    code = 0
    try:
        fis.main()
    except SystemExit as exc:
        code = exc.code
    out = capsys.readouterr().out
    # Asked of the output, the question answers itself: a build that never prints the
    # line agrees with itself about there being nothing wrong. The host's file knows.
    registered = _gate_is_in(tmp_path / ".claude" / "settings.json")
    assert (code == 0) is registered, (label, code, out)
    assert ("기계적 셋업 완료" in out) is registered, (label, out)
    assert (tmp_path / ".gitignore").is_file()
    assert (tmp_path / ".claude" / "harness-tier" / "scripts" / "precommit-runner.sh").is_file()


def test_a_settings_file_that_is_not_utf8_is_reported(tmp_path: Path):
    """The host this gate was written for runs a cp949 console, so a settings.json with a
    Korean comment in the local code page is an ordinary file there, not a corrupt one."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_bytes('{"note": "한글"}'.encode("cp949"))
    assert "UTF-8" in fis.register_gate(tmp_path)
    assert "UTF-8" in fis.unregister_gate(tmp_path)


def test_a_settings_path_that_cannot_be_written_is_reported(tmp_path: Path):
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude" / "settings.json").mkdir(parents=True)
    out = fis.register_gate(tmp_path)
    assert out.startswith("  [!]"), out


def test_a_document_that_is_not_an_object_is_left_alone(tmp_path: Path):
    """Reported, not overwritten. The guard is only worth having if the file survives it."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text('["the host\'s own array-shaped config", {"keep": "me"}]', encoding="utf-8")
    before = settings.read_text(encoding="utf-8")
    assert fis.register_gate(tmp_path).startswith("  [!]")
    assert settings.read_text(encoding="utf-8") == before


def test_the_move_count_is_hooks_not_entries(tmp_path: Path):
    """One entry can hold several gate hooks, and the number the host reads has to be the
    number that moved."""
    import scripts.flow_init_setup as fis

    _planted(
        tmp_path,
        [{"matcher": "Read", "hooks": [_gate_hook(), _gate_hook(), _gate_hook()]}],
    )
    assert "3건" in fis.register_gate(tmp_path)


def test_a_stale_hook_under_an_undecidable_matcher_is_still_brought_forward(tmp_path: Path):
    """The entry stays as the host wrote it; the gate's own hook inside it does not, because
    a path this plugin no longer installs to is a hook that runs nothing."""
    import scripts.flow_init_setup as fis

    # The path a release before the scripts/ subdirectory installed to. It still says
    # harness-tier, which is what separates this from a hook the host wrote.
    stale = dict(
        _gate_hook(),
        command='bash "${CLAUDE_PROJECT_DIR:-.}/.claude/harness-tier/precommit-runner.sh"',
    )
    settings = _planted(tmp_path, [{"matcher": "^Bash$", "hooks": [stale]}])
    fis.register_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert pre[0]["matcher"] == "^Bash$", pre
    assert pre[0]["hooks"][0]["command"] == fis.GATE_COMMAND, pre


def test_a_hook_under_an_undecidable_matcher_is_reported_as_a_maybe(tmp_path: Path):
    """It may fire and it may not — saying it does is the same false statement about the
    host's configuration that reading the matcher wrongly makes."""
    import scripts.flow_init_setup as fis

    out = fis.register_gate(
        _host_with(tmp_path, [{"matcher": "^Notebook", "hooks": [_gate_hook()]}])
    )
    assert "판정할 수 없는" in out and "1개" in out, out
    assert "발화하는 게이트 훅" not in out, out


def _host_with(tmp_path: Path, entries: list) -> Path:
    _planted(tmp_path, entries)
    return tmp_path


def test_a_settings_file_that_cannot_be_read_is_reported(tmp_path: Path, monkeypatch):
    """The file exists and the read still fails — a lock, a permission, a device. Every other
    step of the setup runs after this one."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
    real = Path.read_text

    def refuse(self, *a, **kw):
        if self.name == "settings.json":
            raise OSError(13, "Permission denied")
        return real(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", refuse)
    assert "읽지 못했습니다" in fis.register_gate(tmp_path)
    assert "읽지 못했습니다" in fis.unregister_gate(tmp_path)


def test_a_settings_file_holding_null_is_an_empty_one(tmp_path: Path):
    """`null` parses, and it is not an object; read as one the gate refuses a file that says
    nothing at all rather than registering into it."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text("null", encoding="utf-8")
    assert "등록" in fis.register_gate(tmp_path)


def test_one_gate_hook_is_not_reported_as_several(tmp_path: Path):
    import scripts.flow_init_setup as fis

    assert "게이트 훅" not in fis.register_gate(tmp_path)
    assert "게이트 훅" not in fis.register_gate(tmp_path)


def test_the_undecided_note_counts_hooks_not_entries(tmp_path: Path):
    import scripts.flow_init_setup as fis

    _planted(tmp_path, [{"matcher": "^Bash$", "hooks": [_gate_hook(), _gate_hook()]}])
    out = fis.register_gate(tmp_path)
    assert "판정할 수 없는" in out and "2개" in out, out


def test_a_write_that_fails_leaves_the_host_file_as_it_was(tmp_path: Path):
    """Opening for writing truncates before it writes, so a failure partway through is the
    host's settings gone — and the report line would call that "could not write"."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash"]}}), encoding="utf-8")
    before = settings.read_text(encoding="utf-8")
    # A lone surrogate parses as JSON and encodes as nothing.
    settings.write_text(
        json.dumps({"permissions": {"allow": ["Bash"]}, "n": "\ud800"}), encoding="utf-8"
    )
    poisoned = settings.read_text(encoding="utf-8")
    out = fis.register_gate(tmp_path)
    assert out.startswith("  [!]"), out
    assert settings.read_text(encoding="utf-8") == poisoned
    assert before != poisoned
    assert not list((tmp_path / ".claude").glob("settings.json.*")), "the temporary file stayed"


def test_a_claude_directory_that_is_a_file_is_reported(tmp_path: Path):
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").write_text("not a directory", encoding="utf-8")
    assert fis.register_gate(tmp_path).startswith("  [!]")
    assert fis.unregister_gate(tmp_path).startswith("  [!]")
    assert fis.register_marketplace(tmp_path).startswith("  [!]")


def test_a_settings_file_too_deep_to_parse_is_reported(tmp_path: Path):
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text(
        "[" * 100000 + "]" * 100000, encoding="utf-8"
    )
    assert "파싱 실패" in fis.register_gate(tmp_path)


def test_the_undecided_note_counts_only_the_gates_own_hooks(tmp_path: Path):
    """The host's hooks under an undecidable matcher are the host's, and counting them as gate
    runs tells them their commit does something it does not."""
    import scripts.flow_init_setup as fis

    _planted(
        tmp_path,
        [{"matcher": "^Bash$", "hooks": [{"command": "my-audit.sh"}, {"command": "lint.sh"}]}],
    )
    out = fis.register_gate(tmp_path)
    assert "게이트 훅" not in out, out


def test_a_settings_file_the_host_keeps_as_a_link_is_written_through(tmp_path: Path):
    """A rename replaces the name, so the link became a plain file and the dotfiles copy the
    host manages kept the old content — which their next sync puts back, gate and
    all."""
    import scripts.flow_init_setup as fis

    managed = tmp_path / "dotfiles-settings.json"
    managed.write_text(json.dumps({"permissions": {"allow": ["Bash"]}}), encoding="utf-8")
    (tmp_path / ".claude").mkdir()
    link = tmp_path / ".claude" / "settings.json"
    try:
        link.symlink_to(managed)
    except OSError as exc:  # a host without the privilege to make one
        pytest.skip(str(exc))
    assert "등록" in fis.register_gate(tmp_path)
    assert link.is_symlink()
    assert _is_gate(_gate_commands(managed)[0])


def test_a_temporary_file_does_not_consume_one_the_host_already_had(tmp_path: Path):
    """The name beside settings.json was fixed, and whatever the host had there went with the
    rename."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    victim = tmp_path / ".claude" / "settings.json.harness-new"
    victim.write_text("the host wrote this", encoding="utf-8")
    fis.register_gate(tmp_path)
    assert victim.read_text(encoding="utf-8") == "the host wrote this"


@pytest.mark.parametrize("field", [{"if": "Bash(rm *)"}, {"async": True}, {"type": "prompt"}])
def test_a_gate_hook_the_host_switched_off_is_not_the_gate(tmp_path: Path, field: dict):
    """Each of these leaves the hook registered and firing on nothing: `if` suppresses it per
    build (Invariant 4), `async` puts it where it cannot deny, and another `type` runs
    something else. Reported as already registered, the commit gate is off in silence."""
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": "Bash", "hooks": [dict(_gate_hook(), **field)]}])
    assert "보정" in fis.register_gate(tmp_path)
    hook = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"][0]["hooks"][0]
    assert hook == fis.GATE_ENTRY["hooks"][0], hook


def test_a_hook_of_the_hosts_that_merely_shares_the_script_name_is_left_alone(tmp_path: Path):
    """`precommit-runner.sh` is a name a host writes for itself. Claimed as this gate's, theirs
    was rewritten to this path under a firing matcher and deleted under one that does not
    fire."""
    import scripts.flow_init_setup as fis

    theirs = {"type": "command", "command": "bash ./tools/precommit-runner.sh --their-flags"}
    for matcher in ("Bash", "Edit"):
        host = tmp_path / matcher
        settings = _planted(host, [{"matcher": matcher, "hooks": [dict(theirs)]}])
        fis.register_gate(host)
        cmds = _gate_commands(settings)
        assert theirs["command"] in cmds, (matcher, cmds)
        assert any(_is_gate(c) for c in cmds), (matcher, cmds)


@pytest.mark.parametrize("document", ["false", "0", '""', "[]", "0.0"])
def test_a_falsy_document_is_data_not_an_empty_one(tmp_path: Path, document: str):
    """`json.loads(...) or {}` ran before the shape check, so every falsy value reached the
    writer as an empty object and was overwritten under a clean registration line. `null`
    alone is the host's own spelling for nothing set yet."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text(document, encoding="utf-8")
    assert fis.register_gate(tmp_path).startswith("  [!]")
    assert settings.read_text(encoding="utf-8") == document


def test_a_settings_file_holding_only_null_still_takes_the_gate(tmp_path: Path):
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text("null", encoding="utf-8")
    assert "등록" in fis.register_gate(tmp_path)
    assert any(_is_gate(c) for c in _gate_commands(settings))


def test_hooks_turned_off_wholesale_is_said_out_loud(tmp_path: Path):
    """Registering into a settings.json that disables every hook reported a clean install of a
    gate that cannot run."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps({"disableAllHooks": True}), encoding="utf-8"
    )
    assert "disableAllHooks" in fis.register_gate(tmp_path)


def test_a_reason_survives_an_error_that_carries_no_strerror():
    import scripts.flow_init_setup as fis

    assert fis._why(OSError()) == "OSError"
    assert fis._why(ValueError("surrogates not allowed")) == "surrogates not allowed"
    assert fis._why(OSError(2, "no such file")) == "no such file"
