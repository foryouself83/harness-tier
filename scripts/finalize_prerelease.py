"""Deterministically finalize a prerelease version to its stable form.

Used by release.yml on the production branch. python-semantic-release does NOT drop
the rc token when a forced bump level was applied on stage — it recomputes the level
from commits and loses the override (verified 2026-07-03). So main strips the
prerelease suffix deterministically instead of re-running the version algorithm.

If pyproject's project.version is a prerelease (X.Y.Z-<token>.N), write the stable
X.Y.Z to pyproject.toml:project.version and .claude-plugin/plugin.json:version and
print it (exit 0). Otherwise (e.g. a hotfix straight to production with no rc) write
nothing and exit 1 so the caller falls back to plain `semantic-release version`.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

# X.Y.Z-<anything> → capture X.Y.Z. Anchored to the bare `version = "..."` (the [project]
# version), so `version_toml`/`version_variables` lines never match.
_PROJECT_VERSION = re.compile(r'(?m)^version\s*=\s*"(?P<v>[^"]+)"')
_PRERELEASE = re.compile(r"^(?P<core>\d+\.\d+\.\d+)-[0-9A-Za-z.]+$")


def finalize(root: Path) -> str | None:
    pyproject = root / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    m = _PROJECT_VERSION.search(text)
    if not m:
        return None
    pm = _PRERELEASE.match(m.group("v"))
    if not pm:
        return None  # already stable (hotfix path) → caller falls back
    core = pm.group("core")
    pyproject.write_text(text[: m.start("v")] + core + text[m.end("v") :], encoding="utf-8")
    plugin = root / ".claude-plugin" / "plugin.json"
    ptext = plugin.read_text(encoding="utf-8")
    ptext = re.subn(r'("version"\s*:\s*)"[^"]*"', r'\g<1>"' + core + '"', ptext, count=1)[0]
    plugin.write_text(ptext, encoding="utf-8")
    return core


def main() -> None:
    core = finalize(Path.cwd())
    if core is None:
        sys.exit(1)
    print(core)


if __name__ == "__main__":
    main()
