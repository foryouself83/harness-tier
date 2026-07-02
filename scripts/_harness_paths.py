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
# - precommit: precommit-runner.sh runs it directly (changed-module
#   lint/static/import_lint/test, every commit).
# - security-scan: precommit-runner.sh runs it directly (full-module security on
#   staging/release promotion).
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
