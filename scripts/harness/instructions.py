"""A host's project instructions as a harness-neutral model, read from its Claude Code files.

The Claude artifacts (root CLAUDE.md, `.claude/rules/**/*.md`, per-directory CLAUDE.md) are the
only source: this reads them and never writes them. A renderer per harness turns the model into
whatever that harness loads. Runs in the host, so it keeps to the gate's Python floor (3.8).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

try:
    import yaml
except ImportError:  # `sources` lists files without parsing any; `collect` needs it
    yaml = None

MAX_IMPORT_DEPTH = 5
SKIP_DIRS = frozenset({".git", "node_modules", ".venv", ".claude"})
_IMPORT_RE = re.compile(r"@(\S+)")
_FENCE_RE = re.compile(r"\s{0,3}(```|~~~)")
_FRONTMATTER_RE = re.compile(r"---\n(?:(.*?)\n)?---[ \t]*(?:\n|\Z)", re.DOTALL)
ROOT_FILES = ("CLAUDE.md", ".claude/CLAUDE.md")


@dataclass(frozen=True)
class InstructionDoc:
    kind: str  # "root" | "rule" | "module"
    source: str  # repo-relative POSIX path of the Claude artifact
    scope_dir: str  # "" for the repo root, else the repo-relative directory
    paths: tuple[str, ...]  # a rule's `paths:` globs; () = always applies
    body: str  # text after the frontmatter, @imports expanded, LF line endings


def _read(path: Path) -> str:
    text = path.read_bytes().decode("utf-8").replace("\r\n", "\n")
    return text[1:] if text.startswith("\ufeff") else text


def _split_frontmatter(text: str) -> tuple[dict, str]:
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, text
    try:
        meta = yaml.safe_load(m.group(1) or "")
    except yaml.YAMLError:
        meta = None
    return (meta if isinstance(meta, dict) else {}), text[m.end() :]


def _split_globs(value: str) -> list[str]:
    """A comma-separated `paths:` string, where a comma inside `{…}` belongs to the glob."""
    out, depth, cur = [], 0, ""
    for ch in value:
        depth += (ch == "{") - (ch == "}")
        if ch == "," and depth == 0:
            out.append(cur)
            cur = ""
        else:
            cur += ch
    out.append(cur)
    return [g.strip() for g in out if g.strip()]


def _paths(meta: dict) -> tuple[str, ...]:
    raw = meta.get("paths")
    if isinstance(raw, str):
        return tuple(_split_globs(raw))
    if isinstance(raw, list):
        return tuple(str(g).strip() for g in raw if str(g).strip())
    return ()


def _import_target(line: str, base: Path, host: Path) -> Path | None:
    m = _IMPORT_RE.fullmatch(line.strip())
    if not m or m.group(1).startswith("~"):
        return None
    target = (base / m.group(1)).resolve()
    if not target.is_file() or host not in target.parents:
        return None
    return target


def _expand(text: str, file: Path, host: Path, chain: tuple[Path, ...], keep) -> str:
    out: list[str] = []
    fence = None
    for line in text.split("\n"):
        m = _FENCE_RE.match(line)
        if m:
            fence = None if fence == m.group(1) else (fence or m.group(1))
        target = None if fence else _import_target(line, file.parent, host)
        if target is None or target in chain or target in keep or len(chain) > MAX_IMPORT_DEPTH:
            out.append(line)
            continue
        body = _split_frontmatter(_read(target))[1]
        expanded = _expand(body, target, host, (*chain, target), keep)
        out.append(expanded[:-1] if expanded.endswith("\n") else expanded)
    return "\n".join(out)


def _doc(kind: str, path: Path, host: Path, keep) -> InstructionDoc:
    meta, body = _split_frontmatter(_read(path))
    rel = path.relative_to(host).as_posix()
    scope = path.parent.relative_to(host).as_posix() if kind == "module" else ""
    return InstructionDoc(
        kind=kind,
        source=rel,
        scope_dir="" if scope == "." else scope,
        paths=_paths(meta) if kind == "rule" else (),
        body=_expand(body, path, host, (path.resolve(),), keep),
    )


def _git_ignored(host: Path, rels: list[str]) -> set[str]:
    if not rels or not shutil.which("git"):
        return set()
    try:
        out = subprocess.run(
            ["git", "check-ignore", "--stdin", "-z"],
            cwd=host,
            input="\0".join(rels) + "\0",
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return set()
    return set(filter(None, out.stdout.split("\0"))) if out.returncode == 0 else set()


def _modules(host: Path) -> list[Path]:
    found = []
    for dirpath, dirnames, filenames in os.walk(host):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        path = Path(dirpath) / "CLAUDE.md"
        # `is_file()` drops a dangling symlink, as `collect` drops a dangling rule.
        if "CLAUDE.md" in filenames and Path(dirpath) != host and path.is_file():
            found.append(path)
    rels = [p.relative_to(host).as_posix() for p in found]
    ignored = _git_ignored(host, rels)
    return [p for p, rel in zip(found, rels) if rel not in ignored]


def collect(host: Path, keep_imports=frozenset()) -> list[InstructionDoc]:
    """ROOT_FILES in order, then rules, then modules, each group sorted by path.

    `keep_imports` names files whose `@import` lines stay literal — a renderer passes its own
    target, so a CLAUDE.md that imports it does not pull the rendered output back in.
    """
    if yaml is None:
        raise ModuleNotFoundError("No module named 'yaml'", name="yaml")
    host = host.resolve()
    keep = {Path(p).resolve() for p in keep_imports}
    return [_doc(kind, path, host, keep) for kind, path in sources(host)]


# The plugin's own rules, copied in by /flow-init (RULES_DEST in flow_init_setup.py). Codex gets
# them from the SessionStart hook instead, so rendering them too would spend the AGENTS.md
# budget on a duplicate and could push the host's own rule bodies out of it.
PLUGIN_RULES_DIR = ".claude/rules/harness-tier"


def sources(host: Path) -> list[tuple[str, Path]]:
    """(kind, path) of every file `collect` reads, in its order, found without reading any."""
    host = host.resolve()
    out = [("root", host / rel) for rel in ROOT_FILES if (host / rel).is_file()]
    rules_dir = host / ".claude" / "rules"
    plugin_rules = host / PLUGIN_RULES_DIR
    rules = sorted(
        (p for p in rules_dir.rglob("*.md") if plugin_rules not in p.parents),
        key=lambda p: p.relative_to(host).as_posix(),
    )
    out.extend(("rule", p) for p in rules if p.is_file())
    modules = sorted(_modules(host), key=lambda p: p.relative_to(host).as_posix())
    out.extend(("module", p) for p in modules)
    return out
