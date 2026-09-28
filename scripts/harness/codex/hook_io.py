"""What a Codex hook payload edited. Codex reports every file edit as `apply_patch` — or as a Bash
command when the model runs apply_patch through the shell — with the patch text as the command and
the paths in its headers, relative to the session cwd.

`edited-paths` answers by exit status as well as output, because "no path" means two things the
invalidation hook must tell apart: 0 — the paths are printed, or the payload is not an edit;
3 — it is an edit, but no path could be placed; 4 — the payload cannot be read well enough to say.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path, PureWindowsPath

EDIT_UNPLACED = 3
UNDECIDABLE = 4

_HEADER = re.compile(r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (.+?)\s*$", re.M)
# The envelope's own lines. A `*** Begin Patch` opens one only at a line start or right after
# the quote of an `apply_patch '…'` argument, with nothing after it on the line — so a grep or an
# echo that quotes the marker mid-command is not a patch.
_BEGIN = re.compile(r"(?:^|['\"])\*\*\* Begin Patch[ \t]*\r?$", re.M)
_END = re.compile(r"^\*\*\* End Patch[ \t]*['\"]?[ \t]*\r?$", re.M)
_TOOL_NAME = re.compile(r'"tool_name"\s*:\s*"([^"\\]*)"')
_COMMAND_KEY = re.compile(r'"command"\s*:\s*"')
_STRING_BODY = re.compile(r'(?:[^"\\]|\\.)*')

# A leading `cd <dir>` (bare, or quoted for a name with spaces) joined to what follows by `&&`
# or `;` — the only shell shape simple enough to resolve without a real shell. The bare-word
# class excludes `~`, `$`, backtick, parens and pipe/redirect characters so `cd ~/x`, `cd $X` and
# `cd $(x)` never match here at all, which is what makes them fall through to the plain cwd below
# (no cd seen at position 0 == nothing to resolve).
_CD = re.compile(r'^cd\s+(?:"([^"]*)"|\'([^\']*)\'|([^\s"\'$`~();&|<>]+))\s*(?:&&|;)\s*')


def _bash_effective_dir(command: str, cwd: str) -> str:
    """Follow a leading chain of simple `cd` segments and return where they land.

    Only a prefix of `cd <dir> (&&|;)` segments is understood — a `pushd`, a subshell, a `cd`
    after some other command, or a quoted argument that still resolves to `~`/a variable/a
    substitution is not "simple" and stops the whole attempt, returning the untouched `cwd`
    rather than a guess built from part of the chain."""
    base = cwd
    text = command.lstrip()
    while True:
        m = _CD.match(text)
        if not m:
            break
        arg = next((g for g in m.groups() if g is not None), None)
        if not arg or any(ch in arg for ch in "~$`"):
            return cwd  # a cd IS here, but not one of the simple shapes — trust nothing parsed
        if arg.startswith("/") or PureWindowsPath(arg).is_absolute():
            base = arg
        else:
            base = base.rstrip("/\\") + "/" + arg if base else arg
        text = text[m.end() :]
    return base


_ANSI_C = re.compile(r"\$'((?:[^'\\]|\\.)*)'", re.S)
_ANSI_C_ESCAPE = re.compile(r"\\(.)", re.S)
_ANSI_C_ESCAPES = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", "'": "'", '"': '"'}
_TAB_INDENT = re.compile(r"^\t+", re.M)


def _as_the_shell_reads_it(command: str) -> str:
    """The patch text a shell hands apply_patch: a `$'…'` string decoded to a plain quoted one,
    and the leading tabs a `<<-` heredoc strips removed from every line."""

    def decode(m: re.Match) -> str:
        body = _ANSI_C_ESCAPE.sub(lambda e: _ANSI_C_ESCAPES.get(e.group(1), e.group(0)), m.group(1))
        return "'" + body + "'"

    return _TAB_INDENT.sub("", _ANSI_C.sub(decode, command))


def has_envelope(command: str) -> bool:
    """A `*** Begin Patch` line followed by a `*** End Patch` line: a patch, not a mention."""
    command = _as_the_shell_reads_it(command)
    begin = _BEGIN.search(command)
    return bool(begin and _END.search(command, begin.end()))


def classify(payload: dict) -> tuple[bool, list[str]]:
    """(is an edit, the paths it edited). Only `tool_input.command` is read, never
    `tool_response`: a Bash command's output can quote a whole patch without having applied it.
    """
    if not isinstance(payload, dict):
        return False, []
    tool = payload.get("tool_name")
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if tool == "apply_patch":
        if not isinstance(command, str):
            return True, []
    elif tool == "Bash":
        if not isinstance(command, str) or not has_envelope(command):
            return False, []
        command = _as_the_shell_reads_it(command)
    else:
        return False, []
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else ""
    base = cwd.rstrip("/\\")
    if tool == "Bash" and base:
        base = _bash_effective_dir(command, base)
    out = []
    for rel in _HEADER.findall(command):
        is_abs = rel.startswith("/") or PureWindowsPath(rel).is_absolute()
        out.append(rel if is_abs or not base else base + "/" + rel)
    return True, out


def edited_paths(payload: dict) -> list[str]:
    return classify(payload)[1]


def _undecoded_command(text: str) -> str | None:
    """`tool_input.command` read out of JSON that does not parse — a payload cut at the
    invalidation hook's read cap. The string may itself be cut: what survives is decoded, a torn
    escape dropped."""
    at = text.find('"tool_input"')
    key = _COMMAND_KEY.search(text, at) if at >= 0 else None
    if key is None:
        return None
    body = _STRING_BODY.match(text, key.end()).group(0)
    for cut in range(0, 7):
        try:
            return json.loads('"' + body[: len(body) - cut] + '"')
        except ValueError:
            continue
    return None


def verdict_for_unparsed(text: str) -> int:
    """The exit status for a payload that is not valid JSON. apply_patch is an edit wherever its
    text was cut; a Bash command counts only when its surviving text still holds a whole envelope,
    since a command cut mid-patch cannot be told from one that quotes the marker."""
    name = _TOOL_NAME.search(text)
    if name is None:
        return UNDECIDABLE
    if name.group(1) == "apply_patch":
        return EDIT_UNPLACED
    if name.group(1) != "Bash":
        return 0
    command = _undecoded_command(text)
    return EDIT_UNPLACED if command is not None and has_envelope(command) else 0


def main(argv: list[str]) -> int:
    try:
        from _harness_paths import force_utf8_io  # direct execution: sibling on sys.path
    except ImportError:
        from scripts._harness_paths import force_utf8_io  # package import: scripts/ already on it
    force_utf8_io()
    if argv != ["edited-paths"]:
        return 2
    raw = sys.stdin.buffer.read()
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return verdict_for_unparsed(raw.decode("utf-8", "replace"))
    is_edit, paths = classify(payload)
    for p in paths:
        print(p)
    return EDIT_UNPLACED if is_edit and not paths else 0


if __name__ == "__main__":
    # sys.path[0] here is this file's own directory (`scripts/harness/codex`), not `scripts/` —
    # add it only in this branch, never at import time: a plain `import
    # scripts.harness.codex.hook_io` (every test) must never touch sys.path, or a later bare
    # `import _harness_paths` elsewhere resolves to a SECOND module object distinct from
    # `scripts._harness_paths`, and an `is` identity check between the two breaks silently.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(main(sys.argv[1:]))
