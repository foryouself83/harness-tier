"""Deterministically finalize or apply a prerelease version, bypassing PSR's own algorithm.

Used by the release workflows on both the prerelease and stable branches. python-semantic-
release does NOT drop the rc token when a forced bump level was applied on stage — it
recomputes the level from commits and loses the override (verified 2026-07-03). Nor can it
be handed an explicit target version to apply — its `version` command only ever computes
one. So both branches bypass PSR's version algorithm: the prerelease branch writes a version
computed by `bump_version.py next` (`--set`), and the stable branch strips the prerelease
suffix deterministically (`finalize`).

`--set X` writes X to pyproject.toml:project.version and, when present,
.claude-plugin/plugin.json:version, then prints X (exit 0) — used when the shared
next-version block resolves a forced level (`$NEXT` is not `auto`).

With no arguments: if pyproject's project.version is a prerelease (X.Y.Z-<token>.N), write
the stable X.Y.Z to pyproject.toml:project.version and .claude-plugin/plugin.json:version and
print it (exit 0). Otherwise (e.g. a hotfix straight to production with no rc) write
nothing and exit 1 so the caller falls back to plain `semantic-release version`.

`--print-only` computes and prints the same stable X.Y.Z without writing anything — same exit
contract as the no-arg mode (0 with the version on stdout, 1 with nothing written or printed).
The stable release step calls it first to get `STABLE` for a tag-existence guard, and only
calls the writing (no-arg) form once that guard has passed — so a rerun-because-the-tag-exists
never leaves a half-written pyproject/plugin.json behind.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# X.Y.Z-<anything> → capture X.Y.Z. Anchored to the bare `version = "..."` (the [project]
# version), so `version_toml`/`version_variables` lines never match.
_PROJECT_VERSION = re.compile(r'(?m)^version\s*=\s*"(?P<v>[^"]+)"')
_PRERELEASE = re.compile(r"^(?P<core>\d+\.\d+\.\d+)-[0-9A-Za-z.]+$")


def _prerelease_match(root: Path) -> tuple[Path, str, re.Match[str], str] | None:
    """Locate pyproject.toml's project.version line and its prerelease core, if any.

    Returns (path, full text, the version match, core X.Y.Z) so a writing caller can replace
    the match's span, or None when there is no [project] version line or it is already stable.
    Shared by print_only() and finalize() so both read the same line the same way and cannot
    desync.
    """
    pyproject = root / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    m = _PROJECT_VERSION.search(text)
    if not m:
        return None
    pm = _PRERELEASE.match(m.group("v"))
    if not pm:
        return None
    return pyproject, text, m, pm.group("core")


def print_only(root: Path) -> str | None:
    """Compute the stable core if pyproject's project.version is a prerelease, writing nothing."""
    found = _prerelease_match(root)
    return found[3] if found else None


def finalize(root: Path) -> str | None:
    found = _prerelease_match(root)
    if found is None:
        return None  # no [project] version, or already stable (hotfix path) → caller falls back
    pyproject, text, m, core = found
    pyproject.write_text(text[: m.start("v")] + core + text[m.end("v") :], encoding="utf-8")
    plugin = root / ".claude-plugin" / "plugin.json"
    ptext = plugin.read_text(encoding="utf-8")
    ptext = re.subn(r'("version"\s*:\s*)"[^"]*"', r'\g<1>"' + core + '"', ptext, count=1)[0]
    plugin.write_text(ptext, encoding="utf-8")
    return core


def set_version(root: Path, version: str) -> None:
    """Write an explicit `version` to pyproject.toml, and to plugin.json when it exists.

    A consumer host rendered from the PSR template has no .claude-plugin/plugin.json — that
    file is this repo's own release-gating artifact, not a PSR concept — so writing it is
    conditional, unlike `finalize()`'s unconditional write for this repo's own release.
    """
    pyproject = root / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    m = _PROJECT_VERSION.search(text)
    if not m:
        raise ValueError(f"no [project] version found in {pyproject}")
    pyproject.write_text(text[: m.start("v")] + version + text[m.end("v") :], encoding="utf-8")
    plugin = root / ".claude-plugin" / "plugin.json"
    if not plugin.exists():
        return
    ptext = plugin.read_text(encoding="utf-8")
    ptext = re.subn(r'("version"\s*:\s*)"[^"]*"', r'\g<1>"' + version + '"', ptext, count=1)[0]
    plugin.write_text(ptext, encoding="utf-8")


def main(argv: list[str]) -> None:
    if argv and argv[0] == "--set":
        if len(argv) != 2:
            print("finalize_prerelease: --set requires exactly one version argument", file=sys.stderr)
            sys.exit(2)
        set_version(Path.cwd(), argv[1])
        print(argv[1])
        return
    if argv and argv[0] == "--print-only":
        if len(argv) != 1:
            print("finalize_prerelease: --print-only takes no arguments", file=sys.stderr)
            sys.exit(2)
        core = print_only(Path.cwd())
        if core is None:
            sys.exit(1)
        print(core)
        return
    core = finalize(Path.cwd())
    if core is None:
        sys.exit(1)
    print(core)


if __name__ == "__main__":
    main(sys.argv[1:])
