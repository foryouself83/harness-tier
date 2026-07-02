"""Harness insight extractor for Claude Code session logs.

Project-agnostic. Reads the CURRENT project's Claude Code transcript JSONL
files (under ``~/.claude/projects/<slug>``) and emits two text files that
feed the `/harness-insight` report prompt:

  - ``prompts.txt``  : user prompts only (intent text)          -> input 1
  - ``activity.txt`` : tool_use aggregates (commands, hotspots) -> input 2

Both outputs are temporary scratch files: `/harness-insight` reads them,
produces the conversation report, then deletes them. No report file is
written and no transcript data leaves the machine.

Unlike a per-project extractor, command grouping and directory hotspots are
DERIVED from the data (no hardcoded command list or path regex), so the same
script works in any repository.

Usage::

    python3 harness_insight.py --days 7 --out-dir <tmp-dir>
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import re
from collections import Counter
from datetime import UTC, datetime, timedelta

BS = chr(92)  # backslash, kept out of regex/string literals for clarity

# Tools whose first sub-token is meaningful (``git commit``, ``uv run``,
# ``docker compose``). For these we keep two tokens; everything else groups by
# the executable basename. This is a small generic hint list, not a per-project
# command inventory — unknown tools still group correctly by basename.
SUBCOMMAND_TOOLS = {
    "git",
    "docker",
    "uv",
    "uvx",
    "npm",
    "pnpm",
    "yarn",
    "npx",
    "cargo",
    "go",
    "kubectl",
    "pip",
    "pip3",
    "poetry",
    "make",
    "gh",
    "dotnet",
    "bun",
    "deno",
}

# Pure shell builtins that are navigation/setup noise, not a "command run".
# Dropped from the command hotspot so compound chains like ``cd x && git commit``
# count the meaningful segment, not ``cd``.
SHELL_BUILTINS = {"cd", "export", "set", "unset", "pushd", "popd", "source", "."}

# Chain operators that separate independent commands on one line.
CHAIN_RE = re.compile(r"&&|\|\||;")
ENV_ASSIGN_RE = re.compile(r"^\w+=")

# Leading markers of harness-injected text that is not a real user prompt.
NOISE_PREFIXES = (
    "<ide_",
    "<system-reminder",
    "<command",
    "<local-command",
    "<task-",
    "<user-",
    "[Request interrupted",
    "Caveat:",
)


def project_dirs_from_cwd() -> list[str]:
    """Collect the cwd's Claude Code project dir plus any git-worktree siblings.

    A git worktree lives at a different filesystem path, so Claude Code stores
    its transcripts under a separate ``<slug>`` directory. Those worktree slugs
    all share the main repo's slug as a prefix, so a prefix glob reunites them.

    Caveat: a sibling project whose path also starts with this slug (e.g.
    ``myapp-v2`` vs ``myapp``) would match too — slugs alone can't distinguish
    it from a worktree. ``main`` prints the collected dirs so the match stays
    visible.
    """
    slug = re.sub(r"[^a-zA-Z0-9]", "-", os.getcwd())
    base = os.path.join(os.path.expanduser("~/.claude/projects"), slug)
    return sorted(d for d in glob.glob(base + "*") if os.path.isdir(d))


def parse_ts(ts: str) -> datetime | None:
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def normalize_cmd(seg: str) -> str:
    """Group ONE command segment for frequency counting (project-agnostic).

    Strips leading ``VAR=value`` env assignments, reduces the executable to its
    basename (``/usr/bin/python3`` -> ``python3``), and for a known
    subcommand-style tool keeps the first non-flag sub-token (``git commit``).
    """
    parts = seg.strip().split()
    # Skip leading env assignments (FOO=bar python ...).
    i = 0
    while i < len(parts) and ENV_ASSIGN_RE.match(parts[i]):
        i += 1
    if i >= len(parts):
        return "?"
    base = os.path.basename(parts[i].replace(BS, "/"))
    if base in SUBCOMMAND_TOOLS and i + 1 < len(parts):
        nxt = parts[i + 1]
        if nxt and not nxt.startswith("-"):
            return f"{base} {nxt}"
    return base or "?"


def normalize_cmds(cmd: str) -> list[str]:
    """Split a compound command line into countable command groups.

    Sequential chains (``cd x && git commit``, ``a; b``) are split on
    ``&&``/``||``/``;`` and each segment normalized, so the hotspot reflects
    every command actually run — not just the first. Pure shell builtins
    (``cd``/``export``/…) and empty segments are dropped as navigation noise.
    """
    first = cmd.strip().split("\n", 1)[0]
    out: list[str] = []
    for seg in CHAIN_RE.split(first):
        norm = normalize_cmd(seg)
        if norm == "?" or norm in SHELL_BUILTINS:
            continue
        out.append(norm)
    return out


def hotspot_dir(file_path: str) -> str:
    """Derive a directory hotspot from an edited file path (project-agnostic).

    Uses the last two directory segments of the parent dir so a hotspot emerges
    without knowing the project root. Drive prefixes (``c:``) are dropped.
    """
    d = os.path.dirname(file_path.replace(BS, "/"))
    segs = [s for s in d.split("/") if s and ":" not in s]
    return "/".join(segs[-2:]) if segs else ""


def iter_records(files: list[str]):
    for path in files:
        # errors="replace": a single corrupt UTF-8 byte would otherwise raise
        # UnicodeDecodeError at `for line in fh` and abort the whole run.
        # (Transcripts are arbitrary logs: interrupted, partial, binary-mixed.)
        with open(path, encoding="utf-8", errors="replace") as fh:
            for line in fh:
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def user_text(content: object) -> str:
    """Extract the real user prompt text, dropping harness-injected blocks."""
    if isinstance(content, str):
        text = content.strip()
        return "" if text.startswith(NOISE_PREFIXES) else text
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if not isinstance(block, dict) or block.get("type") != "text":
                continue
            tx = (block.get("text") or "").strip()
            if tx and not tx.startswith(NOISE_PREFIXES):
                parts.append(tx)
        return "\n".join(parts)
    return ""


def extract(project_dirs: list[str], days: int):
    cutoff = datetime.now(UTC) - timedelta(days=days)
    cutoff_ts = cutoff.timestamp()
    # mtime pre-filter: files last modified before the cutoff are excluded early
    # to avoid re-reading the entire accumulated history every run. New records
    # bump mtime, so this errs safe; the per-record ts filter re-checks the edge.
    files = sorted(
        f
        for pd in project_dirs
        for f in glob.glob(os.path.join(pd, "*.jsonl"))
        if os.path.getmtime(f) >= cutoff_ts
    )

    prompts: list[tuple[str, str]] = []
    tools: Counter[str] = Counter()
    cmds: Counter[str] = Counter()
    edits: Counter[str] = Counter()
    dirs: Counter[str] = Counter()
    sessions: set[str] = set()

    for rec in iter_records(files):
        ts = parse_ts(rec.get("timestamp", ""))
        # Unknown date (missing/unparseable timestamp) is conservatively dropped
        # so undated records can't slip past the window and inflate the counts.
        if ts is None or ts < cutoff:
            continue
        rtype = rec.get("type")
        msg = rec.get("message", {}) or {}
        content = msg.get("content")

        if rtype == "user":
            text = user_text(content)
            if not text:
                continue
            sessions.add(rec.get("sessionId", ""))
            prompts.append((rec.get("timestamp", "")[:19], text))
            continue

        if rtype == "assistant" and isinstance(content, list):
            for block in content:
                if not isinstance(block, dict) or block.get("type") != "tool_use":
                    continue
                name = block.get("name", "?")
                inp = block.get("input", {}) or {}
                tools[name] += 1
                fp = (inp.get("file_path") or "").replace(BS, "/")
                if name in ("Edit", "Write", "NotebookEdit") and fp:
                    edits[os.path.basename(fp)] += 1
                    hot = hotspot_dir(fp)
                    if hot:
                        dirs[hot] += 1
                elif name in ("Bash", "PowerShell"):
                    for c in normalize_cmds(inp.get("command", "")):
                        cmds[c] += 1

    return prompts, tools, cmds, edits, dirs, sessions


def write_prompts(path: str, prompts: list[tuple[str, str]], days: int) -> None:
    lines = [f"# User prompts (last {days}d) - {len(prompts)} prompts", ""]
    for ts, text in prompts:
        lines.append(f"## {ts}")
        lines.append(text)
        lines.append("")
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


def write_activity(
    path: str,
    tools: Counter[str],
    cmds: Counter[str],
    edits: Counter[str],
    dirs: Counter[str],
    sessions: set[str],
    prompt_count: int,
    days: int,
) -> None:
    out = [f"# Activity stats (last {days}d)", ""]
    out.append(f"sessions: {len([s for s in sessions if s])}")
    out.append(f"prompts: {prompt_count}")
    out.append("")
    out.append("## tool_use distribution")
    out += [f"  {v:5} {k}" for k, v in tools.most_common()]
    out.append("")
    out.append("## top commands")
    out += [f"  {v:5} {k}" for k, v in cmds.most_common(12)]
    out.append("")
    out.append("## most-edited directories")
    out += [f"  {v:5} {k}" for k, v in dirs.most_common(10)]
    out.append("")
    out.append("## most-edited files")
    out += [f"  {v:5} {k}" for k, v in edits.most_common(10)]
    with open(path, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out))


def main() -> None:
    ap = argparse.ArgumentParser(description="Harness insight extractor (project-agnostic)")
    ap.add_argument("--days", type=int, default=7, help="lookback window in days")
    ap.add_argument(
        "--project-dir",
        default=None,
        help="explicit Claude project dir (overrides cwd slug + worktree scan)",
    )
    ap.add_argument("--out-dir", default=".", help="output directory for the temp txt files")
    args = ap.parse_args()

    project_dirs = [args.project_dir] if args.project_dir else project_dirs_from_cwd()
    project_dirs = [d for d in project_dirs if os.path.isdir(d)]
    if not project_dirs:
        raise SystemExit("no project dir found (cwd slug + worktree siblings)")
    for d in project_dirs:
        print(f"scanning {d}")
    os.makedirs(args.out_dir, exist_ok=True)

    prompts, tools, cmds, edits, dirs, sessions = extract(project_dirs, args.days)

    prompts_path = os.path.join(args.out_dir, "prompts.txt")
    activity_path = os.path.join(args.out_dir, "activity.txt")
    write_prompts(prompts_path, prompts, args.days)
    write_activity(activity_path, tools, cmds, edits, dirs, sessions, len(prompts), args.days)
    print(f"wrote {prompts_path} ({len(prompts)} prompts)")
    print(f"wrote {activity_path} ({len([s for s in sessions if s])} sessions)")


if __name__ == "__main__":
    main()
