"""Compute the next SemVer version for release tools that cannot derive it themselves.

python-semantic-release/semantic-release read Conventional Commits and pick patch/minor/major
on their own. JReleaser/GitVersion/cargo-release/sbt-release do not (verified via each tool's
docs — see docs/operations/commit-versioning-guide.md), so their release workflows fall back to
the same explicit-level mechanism the `/flow` staging-bump step already uses: a
`Release-Level: major|minor|patch` commit trailer. This script does the arithmetic those smart
tools would otherwise do internally, and optionally rewrites a version file in place (mirrors
finalize_prerelease.py's approach, generalized to an arbitrary regex capture group).
"""

from __future__ import annotations

import argparse
import re
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

    args = parser.parse_args(argv)

    if args.cmd == "bump":
        next_version = bump(args.current, args.level, args.prerelease)
    else:
        next_version = finalize(args.current)
        if next_version is None:
            return 1  # not a prerelease — caller falls back to a fresh bump

    if args.file and args.pattern:
        rewrite_file(Path(args.file), args.pattern, next_version)
    print(next_version)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
