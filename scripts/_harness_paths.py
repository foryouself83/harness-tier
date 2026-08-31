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
# precommit and security-scan are timing buckets over the module checks
# (flow-config modules[].checks); each check routes to one by its `when` (every-commit |
# promotion), string values defaulting by key name (`security` → promotion, else every-commit).
# See flow_gate_check._parse_check. wiki is unrelated to modules[] — see below.
# - precommit: precommit-runner.sh runs it directly — the every-commit checks of the CHANGED
#   modules (lint/static/import_lint/test + custom `when: every-commit`), on every commit.
# - security-scan: precommit-runner.sh runs it directly — the promotion checks of ALL modules
#   (`security` + custom `when: promotion`), on staging/release promotion.
# - wiki: flow_gate_check.py main() runs it as its in-process final stage (`--wiki-check`
#   remains a compat alias), never through the module-command channel above. Only when
#   flow-config.wiki is alive; then it checks graph drift/structure violations on every tier.
#   No wiki → nothing runs. It stays out of the module channel because the two have opposite
#   error contracts: down there any nonzero exit means "the check failed", while a runtime
#   gate must fail OPEN on anything that is not a real verdict (Invariant #1). Riding main()
#   also lets the graph's quality warnings reach the user on a passing commit — the module
#   channel buffers output into a log printed only on failure.
RUNTIME_GATES = ("precommit", "security-scan", "wiki")
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
    """Run a git command with cwd, returning stripped stdout, or None on any failure.

    errors="replace": one non-UTF-8 byte in the output otherwise kills the whole call — the
    decode error fires in subprocess's reader thread, so run() returns stdout=None and the
    .strip() below raises out of this function instead of failing soft. A replacement char in
    a path merely mismatches that one entry (its own fail-open), which is strictly narrower.
    """
    try:
        out = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=5,
        )
    except Exception:
        return None
    if out.returncode != 0 or out.stdout is None:
        return None
    return out.stdout.strip()


# The global-options region of a `git … commit`, matched from the `git` itself rather than found
# by splitting on the first " commit" in the string. A commit message reaches the command line
# ahead of the invocation whenever it is built in a heredoc and piped, and it says "commit" often;
# splitting there ends the region inside the body and drops the `-C` the skill was told to write.
# Read against the MASK below, where every literal region is one quote-delimited NUL run, so a
# token is plain `\S+` and this pattern states no opinion about quoting — `_shell_regions` is the
# one place that decides what a quote means. `(?!-)` on the optional argument keeps a `-` token a
# flag rather than the previous flag's argument. The leading separator is what stops `mygit`.


def git_subcommand_re(word: str) -> re.Pattern[str]:
    """A real ``git … <word>`` invocation, with its global-options region as group 1.

    One grammar for both subcommands the gate cares about: the merge path had its own split and
    kept the bug the commit path was fixed for. Match it against :func:`mask_literals` output,
    never the raw command, or a word inside a message is read as an invocation.
    """
    return re.compile(rf"(?:^|[\s;&|(])git((?:\s+-\S+(?:\s+(?!-)\S+)?)*)\s+{word}(?![\w-])")


_GIT_COMMIT_RE = git_subcommand_re("commit")
# A heredoc introducer, whose body is literal text however it is quoted. A `<<<` here-string is
# already excluded by the word grammar (`<` starts no word); the lookarounds add what a longer
# run of `<` would otherwise reach, by refusing to start mid-run. The word may itself be quoted,
# which is what turns off expansion inside. Group 1 is the `-` of `<<-`, which alone strips the
# terminator.
_HEREDOC_RE = re.compile(r"(?<!<)<<(-?)(?!<)\s*(?:'([^']*)'|\"([^\"]*)\"|([\w.-]+))")
# `-C` as an option rather than a substring of a value. Located on the mask, then the value is
# read from the raw string at that offset — a `-C` inside a quoted option value is not an option,
# and its path must not be the answer.
_DASH_C_RE = re.compile(r"(?:^|\s)-C\s+")
_PATH_TOKEN_RE = re.compile(_PATH_TOKEN)


def _heredoc_body(command: str, start: int, word: str, dash: bool) -> int:
    """End of the heredoc body opened at `start` (index of its first line).

    An unterminated body runs to end of input, exactly as the shell consumes it — returning
    "no body" instead would hand a message to the parser as syntax. `<<-` strips leading TABS
    from the terminator and nothing else, so a plain `<<` needs the line to match exactly; a
    looser test ends the region early on an indented look-alike and the rest of the body is
    read as commands.
    """
    at = start
    while at < len(command):
        eol = command.find("\n", at)
        line = command[at : len(command) if eol == -1 else eol]
        if (line.lstrip("\t") if dash else line) == word:
            return at
        if eol == -1:
            break
        at = eol + 1
    return len(command)


def _shell_regions(command: str) -> list[tuple[int, int]]:
    """Index ranges of the literal text in `command` — quoted-span interiors and heredoc bodies.

    One state machine rather than a parity count per quote character: a `"` inside a `'…'` region
    is literal text, and `python3 -c '… "x" …'` is exactly the shape the commit skill issues, so
    counting the two independently would read everything after it as quoted. Outside `'…'` a
    backslash escapes the next character, so the `'\\''` idiom — the only way to put an apostrophe
    inside a single-quoted string, and what a commit subject holding one produces — does not leave
    the tally one quote short and shift every later pairing.

    A heredoc body is literal to the shell without being a quoted span, and it is where this
    repo's commit messages live: a body that says `git -C <wt> commit` is the message talking
    about a commit, not making one, and reading its directory re-points ROOT at a tree the commit
    does not run in (Invariant #6).
    """
    regions: list[tuple[int, int]] = []
    body: tuple[int, int] | None = None  # a heredoc body, entered once the introducer line ends
    i, n = 0, len(command)
    while i < n:
        if body and i >= body[0]:
            regions.append(body)
            i, body = body[1], None
            continue
        ch = command[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "#" and (i == 0 or command[i - 1] in " \t\n;&|("):
            eol = command.find("\n", i)
            end = n if eol == -1 else eol
            regions.append((i, end))  # a `-C` in a comment is not an option either
            i = end
            continue
        if ch == "$" and command[i + 1 : i + 2] == "'":  # $'…' — backslash escapes inside
            j = i + 2
            while j < n and command[j] != "'":
                j += 2 if command[j] == "\\" else 1
            regions.append((i + 2, min(j, n)))
            i = j + 1
            continue
        if ch in "\"'":
            j = i + 1
            while j < n and command[j] != ch:
                j += 2 if ch == '"' and command[j] == "\\" else 1
            regions.append((i + 1, min(j, n)))
            i = j + 1
            continue
        m = _HEREDOC_RE.match(command, i)
        if m and body is None:  # one body per line; a second `<<` on it keeps the first
            eol = command.find("\n", m.end())
            if eol != -1:  # no newline → no body at all, and the rest of the line is still syntax
                word = next(g for g in m.groups()[1:] if g is not None)
                body = (eol + 1, _heredoc_body(command, eol + 1, word, bool(m.group(1))))
            i = m.end()
            continue
        i += 1
    if body:  # the introducer line was the whole scan
        regions.append(body)
    return regions


def mask_literals(command: str) -> str:
    """`command` with every literal region blanked to NUL, same length and same delimiters.

    A quoted argument stays one whitespace-free token, so the option grammar can be written
    without respelling the quoting rules, and offsets still index back into the original.
    """
    out = list(command)
    for a, b in _shell_regions(command):
        out[a:b] = "\x00" * (b - a)
    return "".join(out)


def dash_c_value(command: str, masked: str, start: int, end: int) -> str | None:
    """The `-C <dir>` of the options region `command[start:end]`, or None.

    The option is located on the MASK so a `-C` inside a quoted value is not one, and the path is
    then read from the raw string at that offset so the value itself survives its quotes.
    """
    d = _DASH_C_RE.search(masked, start, end)
    if not d:
        return None
    m = _PATH_TOKEN_RE.match(command, d.end())
    return next((g for g in m.groups() if g is not None), None) if m else None


def _dir_from_command(command: str | None) -> str | None:
    """Extract the commit's execution directory from the command string (deterministic signals).

    ① ``git -C <dir>`` (git's own -C overrides cwd), read from the global-options region of every
       real ``git … commit`` in the command — a quoted or heredoc'd one is the message talking
       about a commit, not making one. Invocations that name ONE directory answer with it, which
       is what commit-then-amend produces; invocations that disagree answer with nothing, because
       Invariant #6 requires ambiguity to end the read rather than guess a third tree.
       ② a leading ``cd <dir> && … git commit`` prefix, reached only when no invocation carried a
       `-C` at all. Conservative shell-lite parse (quoted or bare paths); if nothing matches,
       None → the caller drops to the next rung.
    """
    if not command:
        return None
    masked = mask_literals(command)
    answers = {
        dash_c_value(command, masked, m.start(1), m.end(1)) for m in _GIT_COMMIT_RE.finditer(masked)
    }
    if len(answers) == 1:  # ① one answer, however many invocations gave it
        if (only := answers.pop()) is not None:
            return only
    elif answers:  # invocations that disagree — never guess (Invariant #6). One that names no
        return None  # directory disagrees with one that does: they run in different trees.
    m = _CD_PREFIX_RE.match(command)  # ② leading `cd <dir> &&`
    return next(g for g in m.groups() if g is not None) if m else None


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
