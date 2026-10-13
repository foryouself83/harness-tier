#!/usr/bin/env python3
"""The plugin-only tree this repo publishes, and the marketplace pin that points at it.

  build <out> [--codex-zip PATH]  copy the shipped files into <out>; optionally zip the Codex
                                  directory package from it
  pin <sha>                       point both marketplaces at <sha> on the `plugin` branch

The repo root holds tests, CI and eval tooling no consumer runs; the directories' validators
read every file a plugin source names, so consumers install from the `plugin` branch, whose
root is this tree.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = "foryouself83/harness-tier"
GIT_URL = f"https://github.com/{REPO}.git"
BRANCH = "plugin"
CLAUDE_MARKET = Path(".claude-plugin/marketplace.json")
CODEX_MARKET = Path(".agents/plugins/marketplace.json")

# Everything a consumer's session, /flow-init or a reader of the README reaches.
SHIP = (
    ".gitattributes",
    ".claude-plugin",
    ".codex-plugin",
    ".agents/plugins/marketplace.json",
    "LICENSE",
    "THIRD_PARTY_NOTICES.md",
    "README.md",
    "README.ko.md",
    "USAGE.md",
    "USAGE.ko.md",
    "docs/usage",
    "agents",
    "assets",
    "github",
    "hooks",
    "rules",
    "scripts",
    "skills",
    "templates",
    "flow-config.example.yaml",
    "flow-tiers.yaml",
    "pre-commit-hooks.example.yaml",
)
# Inside a shipped directory, yet run only by evals/.
SKIP = {"scripts/skill_sandbox.py"}
# Left out of the Codex directory package: OpenAI refuses a package with lifecycle hooks, and
# the Claude manifest declares some.
CODEX_ZIP_SKIP = (".claude-plugin/", ".agents/", "hooks/claude/")


def shipped_files(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-z", "--", *SHIP],
        check=True,
        capture_output=True,
    ).stdout.decode("utf-8")
    return sorted(rel for rel in out.split("\0") if rel and rel not in SKIP)


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def _set_source(path: Path, source: object) -> None:
    data = json.loads(path.read_text(encoding="utf-8"))
    (entry,) = data["plugins"]
    entry["source"] = source
    _write_json(path, data)


def build(root: Path, out: Path) -> list[str]:
    if out.exists():
        shutil.rmtree(out)
    files = shipped_files(root)
    for rel in files:
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(root / rel, dest)
    # On the branch the plugin is the marketplace root itself. Codex reads a `url` source as a
    # git remote, so a root that is not a clone needs `local`.
    _set_source(out / CLAUDE_MARKET, "./")
    _set_source(out / CODEX_MARKET, {"source": "local", "path": "./"})
    return files


def codex_zip(dist: Path, zip_path: Path) -> list[str]:
    names = sorted(
        p.relative_to(dist).as_posix()
        for p in dist.rglob("*")
        if p.is_file() and not p.relative_to(dist).as_posix().startswith(CODEX_ZIP_SKIP)
    )
    zip_path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for name in names:
            zf.write(dist / name, name)
    return names


def pin(root: Path, sha: str) -> None:
    if len(sha) != 40 or any(c not in "0123456789abcdef" for c in sha):
        raise SystemExit(f"not a full lowercase commit sha: {sha!r}")
    _set_source(root / CLAUDE_MARKET, {"source": "github", "repo": REPO, "ref": BRANCH, "sha": sha})
    _set_source(root / CODEX_MARKET, {"source": "url", "url": GIT_URL, "ref": BRANCH, "sha": sha})


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build")
    b.add_argument("out", type=Path)
    b.add_argument("--codex-zip", type=Path)
    p = sub.add_parser("pin")
    p.add_argument("sha")
    args = parser.parse_args(argv)
    root = Path.cwd()
    if args.cmd == "build":
        files = build(root, args.out)
        print(f"{len(files)} files -> {args.out}")
        if args.codex_zip:
            print(f"{len(codex_zip(args.out, args.codex_zip))} files -> {args.codex_zip}")
    else:
        pin(root, args.sha)
    return 0


if __name__ == "__main__":
    sys.exit(main())
