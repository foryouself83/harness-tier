"""Write and read the JSON files an installer touches in a host, without ever leaving a half-written one."""  # noqa: E501

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

ACCESS_ENTRIES = "system.posix_acl_access"


def why(exc: BaseException) -> str:
    """What to put in a report line. An OSError raised without an errno has no `strerror`."""
    return getattr(exc, "strerror", None) or str(exc) or type(exc).__name__


def confine(host: Path, path: Path) -> Path:
    """`path`, refused when it resolves outside the host, every symlink on the way followed."""
    root = os.path.normcase(os.path.realpath(host))
    real = os.path.normcase(os.path.realpath(path))
    try:
        inside = os.path.commonpath([root, real]) == root
    except ValueError:  # another drive
        inside = False
    if not inside:
        raise OSError(f"호스트 밖을 가리킴: {path}")
    return path


def access_entries(path: Path) -> bytes | None:
    """The file's POSIX access entries, where the host has any. Read before the rename,
    because after it the inode they belong to is gone."""
    try:
        return os.getxattr(path, ACCESS_ENTRIES)
    except (AttributeError, OSError):
        return None


def _default_mode(tmp: Path) -> None:
    """What a file this CREATES should be. `mkstemp` makes one only its owner can read,
    and a rename carries that: on a build machine where the session runs as another uid,
    a settings.json installed at 0600 is a gate that never loads."""
    try:
        mask = os.umask(0)
        os.umask(mask)
        os.chmod(tmp, 0o666 & ~mask)
    except OSError:
        pass


def _carry_over(before: os.stat_result, acl: bytes | None, tmp: Path) -> None:
    """Put back on `tmp` what a rename does not carry. Best effort: a host whose filesystem
    holds none of this, or a process not allowed to give a file away, keeps what it had."""
    try:
        os.chmod(tmp, stat.S_IMODE(before.st_mode))
    except OSError:
        pass
    if acl is not None:
        try:
            os.setxattr(tmp, ACCESS_ENTRIES, acl)
        except (AttributeError, OSError):
            pass
    try:
        if before.st_uid != os.getuid() or before.st_gid != os.getgid():
            os.chown(tmp, before.st_uid, before.st_gid)
    except (AttributeError, OSError):
        pass


def write_json(path: Path, data: dict, host: Path) -> str | None:
    """Write, or return the line to report instead.

    A path resolving outside `host` is refused: the repo is untrusted input, and a committed
    `.claude/settings.json` linked to `~/.claude/settings.json` would carry the gate into every
    project its user opens.

    Through a temporary file and one rename, because opening for writing truncates first: a
    full disk, a dropped share or a lone surrogate in the host's own data would otherwise
    leave their settings a fragment that no longer parses — and this runs partway through a
    setup whose remaining steps are unguarded. Every way the write can fail is caught, not
    the ones that have been seen: the encode raises ValueError, the rest raise OSError.

    A rename replaces the NAME, so a settings.json a host keeps as a symlink to another file in
    the repo came back a plain file while the linked copy kept the old content. The rename
    lands on what the link points AT for that reason; a link leaving the host is refused
    above, a dotfiles link included. The temporary file is unique because a fixed name beside
    it was a file of the host's own that this silently consumed.

    What a rename does not carry is the file it replaces. Its mode, its owner and its access
    entries all come from the temporary file, which is the writer's alone: a `sudo /flow-init`
    left the host's settings owned by root, and `st_mode` reports the ACL MASK in its group
    bits, so putting that back as a plain mode gave group write to a file whose owner had
    granted one named user. All three come across, the entries before the mode would reset
    their mask. A file the host locked read-only is refused — except to root, whom the write
    bit does not stop. What a new inode cannot keep is kept by nobody: a second hard link,
    the timestamps, a `user.*` attribute, and the setuid bit where the owner has to be given
    back. A symlink inside the host survives.
    """
    try:
        confine(host, path)
    except OSError as exc:
        return f"  [!] {path.name} 쓰기 거부({why(exc)}) — 수동 확인 필요"
    target = Path(os.path.realpath(path)) if path.is_symlink() else path
    if target.is_file() and not os.access(target, os.W_OK):
        return f"  [!] {path.name} 이 쓰기 금지 상태입니다 — 수동 확인 필요"
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    try:
        before = target.stat() if target.is_file() else None
    except OSError:  # gone between the question and the answer
        before = None
    acl = access_entries(target) if before is not None else None
    tmp = None
    try:
        fd, name = tempfile.mkstemp(dir=target.parent, prefix=target.name + ".", suffix=".new")
        tmp = Path(name)  # named before the descriptor closes: the cleanup reads `tmp`
        os.close(fd)
        tmp.write_text(payload, encoding="utf-8")
        if before is not None:
            _carry_over(before, acl, tmp)
        else:
            _default_mode(tmp)
        os.replace(tmp, target)
        tmp = None
    except (OSError, ValueError) as exc:
        return f"  [!] {path.name} 을 쓰지 못했습니다({why(exc)}) — 수동 확인 필요"
    finally:
        # Not only the two the write raises: an interrupt through here leaves the file
        # in the host's `.claude/`, which is ground they track.
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass
    return None


def load_json_object(path: Path, label: str) -> tuple[dict | None, str | None]:
    """Parse `path` as a JSON object. Absent → ({}, None). Unreadable or not an object →
    (None, the line to report). `label` names the file in that line."""
    try:
        exists = path.is_file()
    except OSError as exc:
        return None, f"  [!] {label} 을 읽지 못했습니다({why(exc)}) — 수동 확인 필요"
    if not exists:
        return {}, None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError:
        return None, f"  [!] {label} 이 UTF-8 이 아닙니다 — 수동 확인 필요"
    except (json.JSONDecodeError, RecursionError):
        return None, f"  [!] {label} 파싱 실패 — 수동 확인 필요"
    except OSError as exc:
        return None, f"  [!] {label} 을 읽지 못했습니다({why(exc)}) — 수동 확인 필요"
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return None, f"  [!] {label} 이 객체가 아닙니다 — 수동 확인 필요"
    return data, None
