import json
import os
import struct
import sys
from pathlib import Path

import pytest

from tests.flow_init._helpers import (
    ACCESS_ENTRIES,
    PLUGIN,
    _gate_commands,
    _gate_hook,
    _is_gate,
    _planted,
)


def test_uninstall_leaves_a_hook_of_the_hosts_that_shares_the_script_name(tmp_path: Path):
    """The install side stopped claiming it; the removal side takes hooks by the same
    predicate, and a host hook deleted by an uninstall is gone for good."""
    import scripts.flow_init_setup as fis

    theirs = {"type": "command", "command": "bash ./tools/precommit-runner.sh --their-flags"}
    settings = _planted(tmp_path, [{"matcher": "Bash", "hooks": [dict(theirs), _gate_hook()]}])
    assert "해제" in fis.unregister_gate(tmp_path)
    cmds = _gate_commands(settings)
    assert cmds == [theirs["command"]], cmds


def test_the_mode_the_host_gave_settings_json_survives_a_write(tmp_path: Path):
    """A rename carries the temporary file's mode, and mkstemp makes one only its owner can
    read. On a build machine where another uid reads .claude/settings.json that is the config
    gone, and git tracks no mode but the exec bit, so nothing shows it."""
    import stat

    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash"]}}), encoding="utf-8")
    settings.chmod(0o644)
    before = stat.S_IMODE(settings.stat().st_mode)
    if before != 0o644:  # a host whose filesystem does not carry the bits
        pytest.skip(f"mode not honoured here: {before:o}")
    assert "등록" in fis.register_gate(tmp_path)
    assert stat.S_IMODE(settings.stat().st_mode) == before


def test_a_settings_file_the_host_locked_is_not_replaced(tmp_path: Path):
    """A rename asks the DIRECTORY for permission, not the file, so read-only stopped meaning
    anything the moment the write went through a temporary file."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash"]}}), encoding="utf-8")
    before = settings.read_text(encoding="utf-8")
    settings.chmod(0o444)
    try:
        if os.access(settings, os.W_OK):  # a host where the bit does not deny the owner
            pytest.skip("read-only is not enforced here")
        assert fis.register_gate(tmp_path).startswith("  [!]")
        assert settings.read_text(encoding="utf-8") == before
    finally:
        settings.chmod(0o644)


def test_the_temporary_file_is_made_beside_the_file_it_replaces(tmp_path: Path, monkeypatch):
    """A rename cannot cross a filesystem. Made anywhere but next to the target, the write
    fails on exactly the hosts that keep their project on another volume."""
    import scripts.flow_init_setup as fis

    seen = []
    real = fis.tempfile.mkstemp

    def spy(*args, **kwargs):
        seen.append(kwargs.get("dir"))
        return real(*args, **kwargs)

    monkeypatch.setattr(fis.tempfile, "mkstemp", spy)
    fis.register_gate(tmp_path)
    assert seen == [tmp_path / ".claude"], seen


@pytest.mark.parametrize(
    "failure",
    [
        PermissionError(13, "Permission denied"),
        OSError(28, "No space left on device"),
        OSError(122, "Disk quota exceeded"),
    ],
    ids=["no permission", "full disk", "over quota"],
)
def test_a_write_that_cannot_make_a_temporary_file_leaves_the_host_alone(
    tmp_path: Path, monkeypatch, failure
):
    """Writing in place instead would be the truncation the temporary file exists to prevent,
    and `mkstemp` fails for more than a directory it may not write — a full disk and exhausted
    inodes reach the same call, with the host's own file perfectly writable."""
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": "Read", "hooks": []}])
    before = settings.read_bytes()

    def refuse(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(fis.tempfile, "mkstemp", refuse)
    assert fis.register_gate(tmp_path).startswith("  [!]")
    assert settings.read_bytes() == before
    assert not list((tmp_path / ".claude").glob("settings.json.*"))


def test_hooks_turned_off_wholesale_is_not_a_finished_setup(tmp_path: Path, monkeypatch, capsys):
    """It is the one input that says outright the gate will never fire, and it was the one
    that ended `기계적 셋업 완료.` with exit 0."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps({"disableAllHooks": True}), encoding="utf-8"
    )
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN))
    monkeypatch.setattr(sys, "argv", ["flow_init_setup.py"])
    with pytest.raises(SystemExit) as raised:
        fis.main()
    assert raised.value.code == 1
    out = capsys.readouterr().out
    assert "기계적 셋업 완료" not in out
    assert "disableAllHooks" in out


def test_an_uninstall_that_leaves_the_hook_behind_says_so(tmp_path: Path, monkeypatch, capsys):
    """The scripts the hook names are deleted by the same run, so a settings.json it could not
    write leaves every Bash command in that host running a file that is not there."""
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": "Bash", "hooks": [_gate_hook()]}])
    settings.chmod(0o444)
    try:
        if os.access(settings, os.W_OK):  # a host where the bit does not deny the owner
            pytest.skip("read-only is not enforced here")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN))
        monkeypatch.setattr(sys, "argv", ["flow_init_setup.py", "--uninstall"])
        with pytest.raises(SystemExit) as raised:
            fis.main()
        assert raised.value.code == 1
        out = capsys.readouterr().out
        assert "정리 완료" not in out
        assert "남았습니다" in out
        assert any(_is_gate(c) for c in _gate_commands(settings))
    finally:
        settings.chmod(0o644)


def test_the_access_entries_and_owner_are_carried_over(tmp_path: Path, monkeypatch):
    """Neither survives a rename, and neither shows up in a diff — `st_mode` reports the ACL
    MASK in its group bits, so putting that back as a plain mode is what gave group write to a
    file whose owner had granted one named user, and the new inode is the writer's own. The
    host running Windows has no way to observe either, so what is held here is that the calls
    are made with the values that were read."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash"]}}), encoding="utf-8")
    entries = b"entries the host set"
    chowned, xattred = [], []
    monkeypatch.setattr(fis, "_access_entries", lambda _p: entries)
    monkeypatch.setattr(
        fis.os, "setxattr", lambda p, name, value: xattred.append((name, value)), raising=False
    )
    monkeypatch.setattr(fis.os, "getuid", lambda: 4242, raising=False)
    monkeypatch.setattr(fis.os, "getgid", lambda: 4242, raising=False)
    monkeypatch.setattr(
        fis.os, "chown", lambda p, uid, gid: chowned.append((uid, gid)), raising=False
    )
    before = settings.stat()
    assert "등록" in fis.register_gate(tmp_path)
    assert xattred == [(fis._ACCESS_ENTRIES, entries)], xattred
    assert chowned == [(before.st_uid, before.st_gid)], chowned


def test_a_marketplace_write_that_fails_is_reported(tmp_path: Path, monkeypatch):
    """Every step that writes settings.json has to say so — the setup's verdict reads the
    file, but the step's own line is what names the failing write."""
    import scripts.flow_init_setup as fis

    _planted(tmp_path, [{"matcher": "Bash", "hooks": [_gate_hook()]}])

    def refuse(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(fis.tempfile, "mkstemp", refuse)
    assert fis.register_marketplace(tmp_path).startswith("  [!]")


def test_a_gate_that_is_there_and_firing_is_a_finished_setup(tmp_path: Path, monkeypatch, capsys):
    """The registration line said something was wrong — a gate hook it wanted to move out of a
    non-firing entry, and a settings.json it could not write to do it. The gate itself was
    registered and firing the whole time, and the setup's verdict is about the gate."""
    import scripts.flow_init_setup as fis

    settings = _planted(
        tmp_path,
        [
            {"matcher": "Bash", "hooks": [_gate_hook()]},
            {"matcher": "Read", "hooks": [_gate_hook()]},
        ],
    )
    settings.chmod(0o444)
    try:
        if os.access(settings, os.W_OK):  # a host where the bit does not deny the owner
            pytest.skip("read-only is not enforced here")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN))
        monkeypatch.setattr(sys, "argv", ["flow_init_setup.py"])
        fis.main()
        out = capsys.readouterr().out
        assert "기계적 셋업 완료" in out
        assert "커밋 게이트가 settings.json 에 없습니다" not in out
    finally:
        settings.chmod(0o644)


@pytest.mark.parametrize(
    "raw",
    ['{"a": 1,,}', "settings".encode("cp949").decode("latin-1"), '["a host array"]'],
    ids=["unparseable", "not utf-8", "not an object"],
)
def test_an_uninstall_that_cannot_read_settings_says_the_hook_may_remain(
    tmp_path: Path, monkeypatch, capsys, raw: str
):
    """A file it cannot read is one it cannot clear, and the same run has already deleted the
    scripts the hook names. `정리 완료.` over that is the lie this verdict exists to stop, and
    the cp949 spelling is the host this gate was written for (Invariant 2)."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text(raw, encoding="latin-1")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN))
    monkeypatch.setattr(sys, "argv", ["flow_init_setup.py", "--uninstall"])
    with pytest.raises(SystemExit) as raised:
        fis.main()
    assert raised.value.code == 1
    out = capsys.readouterr().out
    assert "남았습니다" in out
    assert "정리 완료" not in out


def test_an_uninstall_prints_the_follow_ups_it_is_quoted_for(tmp_path: Path, capsys):
    """`/flow-uninstall` sends the user to "the manual follow-ups the script prints", and the
    only instruction for turning off a git hook that now names a deleted script is in them."""
    import scripts.flow_init_setup as fis

    _planted(tmp_path, [{"matcher": "Bash", "hooks": [_gate_hook()]}])
    assert fis.run_uninstall(tmp_path) is True
    out = capsys.readouterr().out
    assert "pre-commit uninstall" in out
    assert "정리 완료." in out


def test_a_gate_hook_under_a_matcher_that_does_not_fire_is_not_a_gate(
    tmp_path: Path, monkeypatch, capsys
):
    """The hook is in the file, so asking only whether one is there says the setup finished.
    It fires on `Read`, and a commit arrives through Bash — and the settings.json this would
    normally move it out of cannot be written."""
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": "Read", "hooks": [_gate_hook()]}])
    settings.chmod(0o444)
    try:
        if os.access(settings, os.W_OK):  # a host where the bit does not deny the owner
            pytest.skip("read-only is not enforced here")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN))
        monkeypatch.setattr(sys, "argv", ["flow_init_setup.py"])
        with pytest.raises(SystemExit) as raised:
            fis.main()
        assert raised.value.code == 1
        out = capsys.readouterr().out
        assert "커밋 게이트가 settings.json 에 없습니다" in out
        assert "기계적 셋업 완료" not in out
        assert any(_is_gate(c) for c in _gate_commands(settings)), "the hook is still there"
    finally:
        settings.chmod(0o644)


@pytest.mark.parametrize(
    "field", [{"if": "Bash(git commit:*)"}, {"async": True}, {"type": "prompt"}]
)
def test_a_gate_hook_the_repair_could_not_reach_is_not_a_finished_setup(
    tmp_path: Path, monkeypatch, capsys, field: dict
):
    """The repair that takes an `if` back off the gate hook lands only when the write lands.
    Asked whether A gate hook is under a firing matcher, a settings.json that could not be
    written reports a finished setup over a hook that fires on nothing (Invariant 4)."""
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": "Bash", "hooks": [dict(_gate_hook(), **field)]}])
    settings.chmod(0o444)
    try:
        if os.access(settings, os.W_OK):  # a host where the bit does not deny the owner
            pytest.skip("read-only is not enforced here")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN))
        monkeypatch.setattr(sys, "argv", ["flow_init_setup.py"])
        with pytest.raises(SystemExit) as raised:
            fis.main()
        assert raised.value.code == 1
        assert "기계적 셋업 완료" not in capsys.readouterr().out
    finally:
        settings.chmod(0o644)


def test_a_matcher_this_cannot_decide_is_not_a_missing_gate(tmp_path: Path, monkeypatch, capsys):
    """`^Bash$` fires. Read as a matcher that does not, a host who anchored it on purpose is
    told the gate is missing and sent to fix what is not broken."""
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": "^Bash$", "hooks": [_gate_hook()]}])
    settings.chmod(0o444)
    try:
        if os.access(settings, os.W_OK):
            pytest.skip("read-only is not enforced here")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN))
        monkeypatch.setattr(sys, "argv", ["flow_init_setup.py"])
        fis.main()
        assert "기계적 셋업 완료" in capsys.readouterr().out
    finally:
        settings.chmod(0o644)


def test_a_settings_file_this_creates_is_as_open_as_the_umask_allows(tmp_path: Path):
    """`mkstemp` makes a file only its owner can read and a rename carries that, so the
    commonest path of all — a first install — left a settings.json the session's own uid may
    not be able to read. It is the failure this writer's docstring names."""
    import stat

    import scripts.flow_init_setup as fis

    assert "등록" in fis.register_gate(tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    mode = stat.S_IMODE(settings.stat().st_mode)
    mask = os.umask(0)
    os.umask(mask)
    if 0o666 & ~mask == 0o666:  # a host whose filesystem does not carry the bits
        pytest.skip(f"mode not honoured here: {mode:o}")
    assert mode == 0o666 & ~mask, oct(mode)


def test_a_claude_directory_that_cannot_be_entered_is_reported(tmp_path: Path):
    """`Path.is_file()` does not swallow a permission error, so the line after the guarded
    mkdir takes the script down where the guard was added — and the copy that runs
    first did the same, taking the workflows and the .gitignore with it."""
    import scripts.flow_init_setup as fis

    closed = tmp_path / ".claude"
    closed.mkdir()
    closed.chmod(0o000)
    try:
        if os.access(closed, os.R_OK):  # a host where the bits do not deny the owner
            pytest.skip("a closed directory is not enforced here")
        assert fis.register_gate(tmp_path).startswith("  [!]")
        assert fis.copy_artifacts(PLUGIN, tmp_path)[0].startswith("  [!]")
    finally:
        closed.chmod(0o755)


def _acl_blob(uid: int) -> bytes:
    """One POSIX access list, in the layout the kernel stores: a version word, then a tag,
    permission bits and an id per entry, ordered by tag. It has to be a real one — the blob
    a mode this test sets must not be refused as malformed, which would skip the test on
    Linux and leave
    the reader it exists to hold unheld on Windows too."""
    undefined = 0xFFFFFFFF
    out = struct.pack("<I", 2)
    for tag, perm, ident in (
        (0x01, 6, undefined),  # the owner
        (0x02, 6, uid),  # one named user — what a plain mode cannot carry
        (0x04, 4, undefined),  # the owning group
        (0x10, 6, undefined),  # the mask `st_mode` reports as group bits
        (0x20, 0, undefined),  # everyone else
    ):
        out += struct.pack("<HHI", tag, perm, ident)
    return out


def _set_acl(path: Path) -> bytes:
    """Put one on the file, or say why this host cannot hold the test."""
    if not hasattr(os, "setxattr"):
        pytest.skip("no extended attributes here")
    acl = _acl_blob(65534)  # nobody
    try:
        os.setxattr(path, ACCESS_ENTRIES, acl)
    except OSError as exc:  # a filesystem that will not take one
        pytest.skip(str(exc))
    return acl


def test_the_access_entries_are_read_from_the_file_itself(tmp_path: Path):
    """The carry-over test replaces this function, so nothing ran it — an xattr name spelled
    wrong, or a reader that always answers None, left the suite green."""
    import scripts.flow_init_setup as fis

    assert fis._ACCESS_ENTRIES == ACCESS_ENTRIES
    plain = tmp_path / "plain.json"
    plain.write_text("{}", encoding="utf-8")
    assert fis._access_entries(plain) is None  # nothing set, and nothing raised
    acl = _set_acl(plain)
    assert fis._access_entries(plain) == acl


def test_a_named_user_entry_survives_the_write(tmp_path: Path):
    """What the carry-over is for, asked of the file rather than of the calls: a rename
    lands a new inode, and the entry granting one named user is the part no mode can put
    back. The host running Windows skips this; the CI running Linux does not."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    acl = _set_acl(settings)
    assert "등록" in fis.register_gate(tmp_path)
    assert os.getxattr(settings, ACCESS_ENTRIES) == acl


def test_an_uninstall_write_that_fails_is_reported(tmp_path: Path, monkeypatch):
    """Every step that writes settings.json says so. The removal side dropped its result while
    the two beside it kept theirs."""
    import scripts.flow_init_setup as fis

    _planted(tmp_path, [{"matcher": "Bash", "hooks": [_gate_hook()]}])

    def refuse(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(fis.tempfile, "mkstemp", refuse)
    assert fis.unregister_gate(tmp_path).startswith("  [!]")
