#!/usr/bin/env python3
"""Update marketplace.json's harness-tier source.sha to the commit SHA passed as an argument.

To preserve formatting/comments, only the existing sha string is substituted instead of a
JSON round-trip (reformat). If it is already identical or there is no sha field, it does
nothing — whether an actual change occurred is decided by the caller via git diff.
(release.yml calls this only on main release commits.)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = "foryouself83/harness-tier"
MANIFEST = Path(".claude-plugin/marketplace.json")


def main() -> None:
    sha = sys.argv[1]
    txt = MANIFEST.read_text(encoding="utf-8")
    old = None
    for plugin in json.loads(txt).get("plugins", []):
        src = plugin.get("source")
        if isinstance(src, dict) and src.get("repo") == REPO:
            old = src.get("sha")
    if old and old != sha:
        # A 40-char SHA is effectively unique, so string substitution is safe (preserves format).
        MANIFEST.write_text(txt.replace(old, sha), encoding="utf-8")


if __name__ == "__main__":
    main()
