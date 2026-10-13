"""Read and rewrite CHANGELOG.md release sections by their version heading.

A section is a `# ` or `## ` heading that opens with a version, and everything up to the next
one: PSR's `## v1.2.0 (date)`, and Node's `# [1.2.0](compare-url) (date)` for a minor or major
release beside `## [1.2.1](…)` for a patch. A heading with no version, the file's title
included, is not a section. `vX.Y.Z-<token>.N` is a prerelease; any other suffix is neither.

`pending` prints `since: v<last stable tag>` and then the rc sections a stable release folds
in: every rc section whose base sits above the last stable tag. `fold` replaces exactly those
with one `## vX.Y.Z (date)` section holding the body it is given, at the top of the release
list where PSR inserts new releases, so PSR keeps updating the file afterwards. `extract`
prints a stable section's body — the release workflows' stable release notes — and exits 1
when there is none. Tags come from `git tag --list` unless `--tags` names them.
"""

from __future__ import annotations

import argparse
import datetime
import re
import sys
from pathlib import Path

try:
    from bump_version import git_tags, last_stable
except ImportError:
    from scripts.bump_version import git_tags, last_stable

_HEADING = re.compile(r"^#{1,2} \[?v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z]+)\.(\d+))?(?![-.\w])")
_OPENS = re.compile(r"(?m)^(?=#{1,2} \[?v?\d+\.\d+\.\d+)")
_ANY_HEADING = re.compile(r"(?m)^#{1,2} ")
_NEW_FILE = "# CHANGELOG\n\n<!-- version list -->\n\n"


def _split(text: str) -> tuple[str, list[str]]:
    """Split `text` into its preamble and its version sections, each kept verbatim."""
    parts = _OPENS.split(text)
    if parts and not _HEADING.match(parts[0]):
        return parts[0], parts[1:]
    return "", parts


def _version(section: str) -> tuple[tuple[int, int, int], str | None] | None:
    m = _HEADING.match(section)
    if not m:
        return None
    return tuple(int(x) for x in m.group(1, 2, 3)), m.group(4)


def _is_pending(section: str, top: tuple[int, int, int], token: str) -> bool:
    v = _version(section)
    return bool(v) and v[1] == token and v[0] > top


def _top(tags: list[str]) -> tuple[int, int, int]:
    return tuple(int(x) for x in last_stable(tags).split("."))


def pending_sections(text: str, tags: list[str], token: str = "rc") -> list[str]:
    """Return the `token` sections whose base sits above the last stable tag, in file order."""
    top = _top(tags)
    return [s for s in _split(text)[1] if _is_pending(s, top, token)]


def _stable_section(text: str, version: str) -> str | None:
    core = tuple(int(x) for x in version.split("."))
    for section in _split(text)[1]:
        if _version(section) == (core, None):
            return section
    return None


def extract(text: str, version: str) -> str | None:
    """Return the body of the stable `version` section, or None when it is absent or empty."""
    section = _stable_section(text, version)
    if section is None:
        return None
    body = section.split("\n", 1)[1].strip() if "\n" in section else ""
    return body or None


def fold(text: str, version: str, body: str, tags: list[str], date: str, token: str = "rc") -> str:
    """Replace the pending `token` sections with one stable `version` section holding `body`."""
    if not body.strip():
        raise ValueError("the release notes body is empty")
    if _ANY_HEADING.search(body):
        raise ValueError("the body carries a `#` or `##` heading, which would end the section")
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError(f"--version {version!r} is not a bare X.Y.Z")
    if tuple(int(x) for x in version.split(".")) <= _top(tags):
        raise ValueError(f"v{version} is not above the last stable tag v{last_stable(tags)}")
    if _stable_section(text, version) is not None:
        raise ValueError(f"CHANGELOG already has a v{version} section")
    top = _top(tags)
    preamble, sections = _split(text or _NEW_FILE)
    kept = [s for s in sections if not _is_pending(s, top, token)]
    new = f"## v{version} ({date})\n\n{body.strip()}\n"
    if kept:
        new += "\n\n"
    return preamble + new + "".join(kept)


def _tags(arg: str | None) -> list[str]:
    return arg.splitlines() if arg is not None else git_tags()


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="changelog_section")
    parser.add_argument("--file", default="CHANGELOG.md")
    sub = parser.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("extract")
    e.add_argument("--version", required=True)
    p = sub.add_parser("pending")
    p.add_argument("--tags", default=None)
    f = sub.add_parser("fold")
    f.add_argument("--version", required=True)
    f.add_argument("--body-file", required=True)
    f.add_argument("--tags", default=None)
    f.add_argument("--date", default=None)
    args = parser.parse_args(argv)

    # CRITICAL TRAP: a non-ASCII changelog line crashes print() under a cp949 or cp1252 stdout
    # Trigger: a Windows host without PYTHONUTF8 runs pending or extract
    # Symptom: UnicodeEncodeError traceback where the section text should be
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    path = Path(args.file)
    try:
        raw = path.read_bytes().decode("utf-8") if path.exists() else ""
    except (OSError, UnicodeDecodeError) as e:
        if args.cmd == "extract":
            return 1
        print(f"changelog_section: {e}", file=sys.stderr)
        return 2
    crlf = "\r\n" in raw
    text = raw.replace("\r\n", "\n")

    if args.cmd == "extract":
        body = extract(text, args.version)
        if body is None:
            return 1
        print(body)
        return 0

    try:
        tags = _tags(args.tags)
        if args.cmd == "pending":
            print(f"since: v{last_stable(tags)}")
            for section in pending_sections(text, tags):
                print(section.rstrip("\n") + "\n")
            return 0
        body = Path(args.body_file).read_bytes().decode("utf-8").replace("\r\n", "\n")
        date = args.date or datetime.date.today().isoformat()
        out = fold(text, args.version, body, tags, date)
    except (OSError, ValueError) as e:
        print(f"changelog_section: {e}", file=sys.stderr)
        return 2
    if crlf:
        out = out.replace("\n", "\r\n")
    path.write_bytes(out.encode("utf-8"))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
