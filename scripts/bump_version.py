"""Compute the next SemVer version for release tools that cannot derive it themselves.

python-semantic-release/semantic-release read Conventional Commits and pick patch/minor/major
on their own. JReleaser/GitVersion/cargo-release/sbt-release do not (verified via each tool's
docs — see docs/operations/commit-versioning-guide.md), so their release workflows fall back to
the same explicit-level mechanism the `/release-commit` staging-bump step already uses: a
`Release-Level: major|minor|patch` commit trailer. This script does the arithmetic those smart
tools would otherwise do internally, and optionally rewrites a version file in place (mirrors
finalize_prerelease.py's approach, generalized to an arbitrary regex capture group).

`next` reads the trailer plus the tag list and picks the promotion's next `X.Y.Z-rc.N`: it
continues a pending rc's series, starts a fresh one off the last stable tag, or reports `auto`
for a caller with its own commit-message-derived level. `--auto-level` supplies that fallback
level for a caller that cannot pick one itself, collapsing `auto` into `continue` when an rc is
already pending, or into the given level otherwise. `finalize-tag` prints the pending rc's
base (with `--rc`, the rc's own `v`-prefixed tag) for a release that finalizes it by tag alone,
and exits 1 when none is pending. `state` prints the pending rc and the version each level
would cut, reading `git tag --list` itself when `--tags` is absent — the no-argument form
`/release-commit` pre-approves, which a `$(git tag --list)` argument cannot be.
"""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path

_SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z.]+))?$")
_PRERELEASE = re.compile(r"^(\d+\.\d+\.\d+)-[0-9A-Za-z.]+$")


def bump(current: str, level: str, prerelease: str | None = None) -> str:
    """Bump `current` (a stable or prerelease SemVer) by `level`, tag it `prerelease` if given.

    If `current` is already a prerelease of the same train (e.g. `1.2.4-rc.1`) and `prerelease`
    is given again, the base is held and only the prerelease token advances — otherwise every
    push to the prerelease branch would re-bump major/minor/patch on top of the previous rc's
    already-bumped base, inflating the eventual stable version each time.
    """
    m = _SEMVER.match(current.strip())
    if not m:
        raise ValueError(f"not a semver: {current!r}")
    major, minor, patch = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if prerelease and m.group(4):
        return f"{major}.{minor}.{patch}-{prerelease}"
    if level == "major":
        major, minor, patch = major + 1, 0, 0
    elif level == "minor":
        minor, patch = minor + 1, 0
    elif level == "patch":
        patch += 1
    else:
        raise ValueError(f"unknown level: {level!r}")
    core = f"{major}.{minor}.{patch}"
    return f"{core}-{prerelease}" if prerelease else core


def finalize(current: str) -> str | None:
    """Strip a prerelease suffix (`X.Y.Z-rc.N` → `X.Y.Z`); None if `current` is already stable."""
    m = _PRERELEASE.match(current.strip())
    return m.group(1) if m else None


def rewrite_file(path: Path, pattern: str, new_version: str) -> None:
    """Replace capture group 1 of the first `pattern` match in `path` with `new_version`."""
    text = path.read_text(encoding="utf-8")
    m = re.search(pattern, text, re.MULTILINE)
    if not m:
        raise ValueError(f"version pattern not found in {path}")
    path.write_text(text[: m.start(1)] + new_version + text[m.end(1) :], encoding="utf-8")


LEVELS = ("auto", "continue", "patch", "minor", "major")
_TRAILER = re.compile(r"^Release-Level\s*:(.*)$", re.MULTILINE)
_TAG = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z]+)\.(\d+))?$")


def parse_level(message: str) -> str:
    """Read the commit message's `Release-Level:` trailer, defaulting to `"auto"`.

    Raise ValueError when the trailer's value is not in LEVELS, is empty, or two trailers
    disagree — a promotion commit must name exactly one level or none.
    """
    values = {v.strip() for v in _TRAILER.findall(message)}
    if not values:
        return "auto"
    if len(values) > 1:
        raise ValueError(f"conflicting Release-Level trailers: {sorted(values)}")
    (value,) = values
    if value not in LEVELS:
        raise ValueError(f"Release-Level {value!r} is not one of {', '.join(LEVELS)}")
    return value


def _parse_tags(tags: list[str], token: str) -> tuple[set[tuple[int, int, int]], list[tuple]]:
    """Split `tags` into stable SemVer cores and `(core, N)` prereleases tagged `token`."""
    stable: set[tuple[int, int, int]] = set()
    rcs: list[tuple] = []
    for t in tags:
        m = _TAG.match(t.strip())
        if not m:
            continue
        core = tuple(int(x) for x in m.group(1, 2, 3))
        if m.group(4) is None:
            stable.add(core)
        elif m.group(4) == token:
            rcs.append((core, int(m.group(5))))
    return stable, rcs


def _fmt(core: tuple[int, int, int]) -> str:
    return ".".join(str(x) for x in core)


def pending_rc(tags: list[str], token: str = "rc") -> tuple[str, int] | None:
    """Return the highest `(base, N)` prerelease whose core has no stable tag and sits above
    the highest stable tag.

    None when every prerelease's base already shipped or fell behind a later stable release —
    a released or superseded series is not pending, even when its tag is the newest one on the
    branch that cut it (a skipped back-merge), and finishing it would be a downgrade.
    """
    stable, rcs = _parse_tags(tags, token)
    top = max(stable, default=(-1, -1, -1))
    open_rcs = [rc for rc in rcs if rc[0] not in stable and rc[0] > top]
    if not open_rcs:
        return None
    core, n = max(open_rcs)
    return _fmt(core), n


def last_stable(tags: list[str]) -> str:
    """Return the highest stable `X.Y.Z` tag in `tags`, or `"0.0.0"` when none exist."""
    stable, _ = _parse_tags(tags, "rc")
    return _fmt(max(stable)) if stable else "0.0.0"


def next_version(
    message: str,
    tags: list[str],
    token: str = "rc",
    auto_level: str | None = None,
) -> str:
    """Compute the next rc version, or `"auto"` when the level is left to the caller.

    `continue` advances the pending rc's prerelease counter; any other level starts a fresh
    `X.Y.Z-token.1` off the pending rc's base (if one is pending) or the last stable tag.
    `continue` with no pending rc raises ValueError, as does a result whose tag already exists
    in `tags`. When `auto_level` is given, a message with no trailer (or an explicit
    `Release-Level: auto`) resolves to `continue` if an rc is already pending, else to
    `auto_level` — for a caller that cannot derive its own level.
    """
    level = parse_level(message)
    pending = pending_rc(tags, token)
    if level == "auto":
        if auto_level is None:
            return "auto"
        level = "continue" if pending else auto_level
    if level == "continue":
        if pending is None:
            raise ValueError("Release-Level: continue, but there is no pending rc to continue")
        base, n = pending
        version = f"{base}-{token}.{n + 1}"
    else:
        base = pending[0] if pending else last_stable(tags)
        version = bump(base, level, prerelease=f"{token}.1")
    _, rcs = _parse_tags(tags, token)
    m = _TAG.match(version)
    if (tuple(int(x) for x in m.group(1, 2, 3)), int(m.group(5))) in rcs:
        raise ValueError(f"v{version} already exists — refusing to cut a duplicate tag")
    return version


def _git_tags() -> list[str]:
    """Return `git tag --list` of the working directory; OSError when git cannot answer."""
    try:
        r = subprocess.run(
            ["git", "tag", "--list"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except OSError as e:
        raise OSError(f"git tag --list: {e}") from e
    if r.returncode != 0:
        raise OSError(f"git tag --list: {r.stderr.strip() or f'exit {r.returncode}'}")
    return r.stdout.splitlines()


def state(tags: list[str], token: str = "rc") -> list[str]:
    """Describe the release state: the pending rc, then the version each forced level cuts."""
    pending = pending_rc(tags, token)
    lines = [f"pending: v{pending[0]}-{token}.{pending[1]}" if pending else "pending: none"]
    for level in ("continue", "patch", "minor", "major"):
        try:
            lines.append(f"{level}: {next_version(f'Release-Level: {level}', tags, token)}")
        except ValueError as e:
            lines.append(f"{level}: fails — {e}")
    return lines


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(prog="bump_version")
    sub = parser.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("bump")
    b.add_argument("--current", required=True)
    b.add_argument("--level", required=True, choices=["major", "minor", "patch"])
    b.add_argument("--prerelease", default=None)
    b.add_argument("--file")
    b.add_argument("--pattern")

    f = sub.add_parser("finalize")
    f.add_argument("--current", required=True)
    f.add_argument("--file")
    f.add_argument("--pattern")

    n = sub.add_parser("next")
    n.add_argument("--message", required=True)
    n.add_argument("--tags", required=True)
    n.add_argument("--token", default="rc")
    n.add_argument("--auto-level", choices=["", "patch", "minor", "major"], default=None)

    ft = sub.add_parser("finalize-tag")
    ft.add_argument("--tags", required=True)
    ft.add_argument("--token", default="rc")
    ft.add_argument("--rc", action="store_true", help="print the pending rc tag, not its base")

    st = sub.add_parser("state")
    st.add_argument("--tags", default=None, help="newline-separated tags; default: git tag --list")
    st.add_argument("--token", default="rc")

    args = parser.parse_args(argv)

    if args.cmd == "state":
        # CRITICAL TRAP: a `fails — …` line crashes print() under a cp949 or cp1252 stdout
        # Trigger: /release-commit runs this on a Windows host without PYTHONUTF8
        # Symptom: UnicodeEncodeError traceback and no `pending:` line at all
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        try:
            tags = args.tags.splitlines() if args.tags is not None else _git_tags()
        except OSError as e:
            print(f"bump_version: cannot list tags — {e}", file=sys.stderr)
            return 2
        print("\n".join(state(tags, args.token)))
        return 0

    if args.cmd == "finalize-tag":
        pending = pending_rc(args.tags.splitlines(), args.token)
        if pending is None:
            return 1  # nothing to finalize — caller falls back to its own release
        base, n = pending
        print(f"v{base}-{args.token}.{n}" if args.rc else base)
        return 0

    if args.cmd == "next":
        try:
            version = next_version(
                args.message, args.tags.splitlines(), args.token, args.auto_level or None
            )
        except ValueError as e:
            print(f"bump_version: {e}", file=sys.stderr)
            return 2
        print(version)
        return 0

    if args.cmd == "bump":
        result = bump(args.current, args.level, args.prerelease)
    else:
        result = finalize(args.current)
        if result is None:
            return 1  # not a prerelease — caller falls back to a fresh bump

    if args.file and args.pattern:
        rewrite_file(Path(args.file), args.pattern, result)
    print(result)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
