"""Shared constants and path helpers for harness-tier gates/scripts (magic-value SSOT).

The single source that applies this repo's [rule-dry-constants] discipline (magic
numbers/strings are defined in one place) to the gate scripts themselves. Path
segments, filenames, the blocking exit code, runtime gate keys, and lifecycle tier
labels are defined only here; other scripts import them.

**Why a module (import compatibility)**: plugin scripts are copied to the host
*one file at a time* and run there (there is no sibling to do
`from flow_init_setup import ...`), so this module is included in flow_init_setup's
COPY_FILES and copied alongside the gate scripts. Then imports resolve in both
execution modes:
  - Direct execution (`python3 .../scripts/flow_gate_check.py`): sys.path[0]=scripts/ →
    sibling `import _harness_paths` resolves.
  - Package import (pytest's `from scripts.flow_gate_check import ...`):
    `from scripts._harness_paths import ...` resolves.
Callers reconcile the two with the idiom below (bootstrap code, so it can't be abstracted):

    try:
        from _harness_paths import host_root, force_utf8_io  # direct execution (sibling)
    except ImportError:
        from scripts._harness_paths import host_root, force_utf8_io  # package (test/dev)

**External contract values are not kept here**: hook event names
(PreToolUse/SessionStart) and env-var keys (CLAUDE_PROJECT_DIR etc.) are enforced by
the Claude Code runtime/SDK, so the key strings themselves are immutable and cannot be
cross-shared with JSON/shell. But the *fallback helpers that read those keys*
(host_root/plugin_root) tend to diverge into variants, so they are consolidated here.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

# ── Path segments under the host write root (root-relative path strings) ──────────
# CLAUDE.md: all host writes are collected under .claude/harness-tier/. flow_init_setup
# joins them with the host root (e.g. `host / SCRIPTS_DIR`), so they are exposed as
# relative path strings.
HARNESS_DIR = ".claude/harness-tier"  # root of host-side artifacts
SCRIPTS_DIR = f"{HARNESS_DIR}/scripts"  # copied gate scripts (plugin-owned·git-tracked)
CONFIG_DIR = f"{HARNESS_DIR}/config"  # flow-config·flow-tiers(policy)·webhooks
FLOW_DIR = f"{HARNESS_DIR}/.flow"  # gate evidence (gitignored)

# ── Filenames under the config directory ────────────────────────────────────────
# Both live in config/ but ownership differs: flow-config holds host environment values
# (human-edited), flow-tiers is plugin policy (tier→gates, immutable·SSOT — lives in config/
# but must not be edited).
CONFIG_FILENAME = "flow-config.yaml"  # host environment values (branches·modules)
TIERS_FILENAME = "flow-tiers.yaml"  # plugin policy (tier→gates, immutable·SSOT)

# ── Gate contract constants ─────────────────────────────────────────────────────
# Invariant #3: for PreToolUse blocking, exit 2 is the actual blocking mechanism. The producer
# (flow_gate_check) blocks with this constant; the consumer (precommit-runner.sh)·tests
# byte-match the same value.
BLOCK_EXIT_CODE = 2
# The set of runtime gates the hook runs directly without a marker — excluded from
# flow_gate_check's .done check. Must exactly match the same keys in the flow-tiers.yaml gates
# list (on desync, missing_gates wrongly reports the gate as unmet — sync required on rename).
# The gates list is the real switch: module_commands decides whether to run based on membership
# in this key rather than a hardcoded tier branch — removing it from gates turns that check off.
# The two gates are timing buckets over the module checks (flow-config modules[].checks); each
# check routes to one by its `when` (every-commit | promotion), string values defaulting by key
# name (`security` → promotion, else every-commit). See flow_gate_check._parse_check.
# - precommit: precommit-runner.sh runs it directly — the every-commit checks of the CHANGED
#   modules (lint/static/import_lint/test + custom `when: every-commit`), on every commit.
# - security-scan: precommit-runner.sh runs it directly — the promotion checks of ALL modules
#   (`security` + custom `when: promotion`), on staging/release promotion.
RUNTIME_GATES = ("precommit", "security-scan")
# Lifecycle branch → tier label. Must byte-match the flow-tiers.yaml tiers: keys for the gate to be
# enforced (on desync, required_gates returns None → gate silently skipped via FAIL-OPEN).
STAGING_TIER = "staging"
RELEASE_TIER = "release"


# ── Absolute path (Path) helpers relative to the host root ──────────────────────
def harness_dir(root: Path) -> Path:
    """Absolute path of .claude/harness-tier/ under host_root."""
    return root / ".claude" / "harness-tier"


def config_dir(root: Path) -> Path:
    """.claude/harness-tier/config/ — host-owned settings (flow-config·webhooks)."""
    return harness_dir(root) / "config"


def flow_dir(root: Path) -> Path:
    """.claude/harness-tier/.flow/ — gate evidence (<gate>.done·tier marker)."""
    return harness_dir(root) / ".flow"


def config_path(root: Path) -> Path:
    """.claude/harness-tier/config/flow-config.yaml — host environment-value config file."""
    return config_dir(root) / CONFIG_FILENAME


# ── Env-var fallback helpers (keys are external contracts·immutable; only fallback logic unified)
def host_root() -> Path:
    """Host repo root. CLAUDE_PROJECT_DIR → git toplevel → .claude marker back-derivation → cwd.

    The most robust fallback is made the standard (formerly teams_alert._host_root).
    CLAUDE_PROJECT_DIR is auto-injected only during hook execution and may be empty for
    pre-push·manual calls, so it falls back to git toplevel, and if git also fails it
    back-derives the parent of `.claude` from the host copy location
    (.claude/harness-tier/scripts/) (marker search instead of a fixed index — independent
    of install depth). If no marker is found (SOURCE/standalone) it falls back to cwd.
    """
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            timeout=3,
        )
        top = out.stdout.strip()
        if top:
            return Path(top)
    except Exception:
        pass
    here = Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == ".claude":
            return parent.parent
    return Path.cwd()


def plugin_root() -> Path:
    """Plugin root. CLAUDE_PLUGIN_ROOT first, else this script's parent (scripts/..)."""
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return Path(env) if env else Path(__file__).resolve().parent.parent


def force_utf8_io() -> None:
    """Reconfigure stdout/stderr to UTF-8 (Invariant #2).

    In the Windows hook environment (cp1252/cp949), if a Korean reason print() breaks with
    UnicodeEncodeError it fails open and the gate is disabled. Also sets PYTHONUTF8 so child
    python processes inherit UTF-8 too (for standalone calls).
    """
    os.environ.setdefault("PYTHONUTF8", "1")
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):  # already closed or cannot reconfigure → ignore
                pass


# ── worktree-aware working root (branch-key detection) ───────────────────────────
# The gate is built on "working tree = one CLAUDE_PROJECT_DIR", fixed at session start and
# unchanged by cd. When a consumer commits from a `git worktree` created inside that session
# (case B), the commit runs in the worktree but the gate still inspects main: git diff/status
# miss the worktree's staged changes, the branch-bound tier marker mismatches (→ "unclassified"
# fail-closed), and relative module-lint commands miss the worktree's files.
#
# working_root() detects the worktree where the commit actually runs and returns it so the whole
# gate reads that worktree. Identification key = the *branch* (git enforces one-branch↔one-worktree,
# a bijection; the tier marker is already branch-bound). Everything is read git-natively (no path or
# session-id stored in the team-shared config). Any uncertainty → project_dir (= main = current
# behavior), preserving Invariant #1 (FAIL-OPEN).
_WORKTREE_PREFIX = "worktree "
_BRANCH_PREFIX = "branch "
_HEADS_PREFIX = "refs/heads/"
# path token: "double-quoted" | 'single-quoted' | bare (up to whitespace)
_PATH_TOKEN = r'"([^"]*)"|\'([^\']*)\'|(\S+)'
# A leading `cd <dir> &&` — the execution directory a chained command moves into before running
# git. Anchored at the start, so a match is necessarily *before* any later subcommand.
# `&&` only, deliberately: a match here re-points ROOT to another worktree for
# status/diff/tier-marker/module-lint, and Invariant #6 requires that path to stay conservative
# ("any uncertainty → main; never newly block"), so widening the separators is a live behaviour
# change, not a clean-up. flow_gate_check's merge path — where the same match only FAILs OPEN —
# states its own separators in _MERGE_CD_PREFIX_RE.
_CD_PREFIX_RE = re.compile(rf"\s*cd\s+(?:{_PATH_TOKEN})\s*&&")


def _git(args: list[str], cwd: str | Path) -> str | None:
    """Run a git command with cwd, returning stripped stdout, or None on any failure."""
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
        )
    except Exception:
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip()


def _dir_from_command(command: str | None) -> str | None:
    """Extract the commit's execution directory from the command string (deterministic signals).

    ① ``git -C <dir>`` (git's own -C overrides cwd) — scanned only in the global-options region
       before the ``commit`` subcommand, so a ``-C`` inside the commit message is not mistaken
       for a directory. ② a leading ``cd <dir> && … git commit`` prefix. Conservative shell-lite
       parse (quoted or bare paths); if nothing matches, None → the caller drops to the next rung.
    """
    if not command:
        return None
    head = command.split(" commit", 1)[0]  # ① global-options region only
    m = re.search(rf"(?:^|\s)-C\s+(?:{_PATH_TOKEN})", head)
    if not m:  # ② leading `cd <dir> &&`
        m = _CD_PREFIX_RE.match(command)
    if not m:
        return None
    return next(g for g in m.groups() if g is not None)


def _parse_worktree_list(porcelain: str) -> list[tuple[str, str | None]]:
    """Parse ``git worktree list --porcelain`` into ``[(path, branch|None), …]``.

    A record ends at a blank line (or EOF); a detached worktree has no ``branch`` line → None.
    """
    entries: list[tuple[str, str | None]] = []
    path: str | None = None
    branch: str | None = None
    for line in porcelain.splitlines():
        if line.startswith(_WORKTREE_PREFIX):
            path, branch = line[len(_WORKTREE_PREFIX) :], None
        elif line.startswith(_BRANCH_PREFIX):
            ref = line[len(_BRANCH_PREFIX) :]
            branch = ref[len(_HEADS_PREFIX) :] if ref.startswith(_HEADS_PREFIX) else ref
        elif not line.strip():
            if path is not None:
                entries.append((path, branch))
            path, branch = None, None
    if path is not None:
        entries.append((path, branch))
    return entries


def _common_dir(d: str | Path) -> Path | None:
    """Resolved ``--git-common-dir`` for a dir — the shared .git all worktrees of a repo point at.

    Same-repo identity uses this (never a path prefix): sibling worktrees like ``…/kit`` vs
    ``…/kit-feature`` overlap by prefix yet share the common dir, while a different repo at a
    prefix-overlapping path does not. Relative output is resolved against ``d`` (git's relative
    paths are cwd-relative and we run with cwd=d).
    """
    out = _git(["rev-parse", "--git-common-dir"], d)
    if out is None:
        return None
    p = Path(out)
    if not p.is_absolute():
        p = Path(d) / p
    try:
        return p.resolve()
    except Exception:
        return None


def working_root(
    *, project_dir: Path, hook_cwd: str | None = None, command: str | None = None
) -> Path:
    """Resolve the worktree where this commit actually runs (branch-key ladder). FAIL-OPEN.

    Reads the execution location deterministic-first and confirms same-repo via common-dir
    equality (Invariant #1: any uncertainty → ``project_dir`` = main = current behavior):
      ①② a dir named in the command (``git -C``/``cd &&``) → its toplevel, if same repo.
      ③   the hook cwd → learn its branch B → the unique ``git worktree list`` entry on B.
      ④   otherwise ``project_dir``.
    detached HEAD / a different repo / no worktree / any exception all fall to ④.
    """
    try:
        project_dir = Path(project_dir).resolve()
        main_common = _common_dir(project_dir)
        if main_common is None:  # main is not a git repo → nothing to resolve
            return project_dir
        # ①② directory named directly in the command (deterministic)
        cmd_dir = _dir_from_command(command)
        if cmd_dir and _common_dir(cmd_dir) == main_common:
            top = _git(["rev-parse", "--show-toplevel"], cmd_dir)
            if top:
                return Path(top).resolve()
        # ③ hook cwd → branch B → bijection over the worktree list
        if hook_cwd and _common_dir(hook_cwd) == main_common:
            branch = _git(["rev-parse", "--abbrev-ref", "HEAD"], hook_cwd)
            if branch and branch != "HEAD":  # not detached
                listing = _git(["worktree", "list", "--porcelain"], project_dir)
                if listing is not None:
                    matches = [p for p, b in _parse_worktree_list(listing) if b == branch]
                    if len(matches) == 1:
                        return Path(matches[0]).resolve()
        # ④ fallback → main (current behavior)
        return project_dir
    except Exception:
        return project_dir
