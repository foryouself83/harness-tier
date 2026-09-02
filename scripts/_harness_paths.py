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
from functools import lru_cache
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

    One grammar for every subcommand the gate reads, so none of them can drift from the others.
    Match it against :func:`mask_literals` output, never the raw command, or a word inside a
    message is read as an invocation.

    The program token is spelled the way a host spells it — a directory prefix, and the `.exe`
    that is the native name on Windows — while `mygit` stays rejected: the prefix has to end in
    a separator, so a different program name never reaches the word. The word itself must end
    at a token boundary, or `git -c commit.gpgsign=false log` reads as a commit and a read-only
    command is denied.
    """
    return re.compile(
        rf"(?:^|[\s;&|(`])(?:[^\s;&|()'\"]*[/\\])?"
        rf"git(?:\.exe)?((?:\s+-\S+(?:\s+(?!-)\S+)?)*)\s+{word}(?=$|[\s;&|)`<>])"
    )


_GIT_COMMIT_RE = git_subcommand_re("commit")
# Programs that take TEXT and run it as code. The gate reads the PROGRAMS rather than the
# channels that carry text to them — a `-c` argument, a here-string, a heredoc, a pipeline,
# a substitution: the channels are unbounded, the programs are a list, and a channel left
# unnamed is a real commit the gate exits 0 on. Longest first, so `python3` is not read as
# `python` with a digit after it.
_RUNS_TEXT = (
    "powershell",
    "python3",
    "python2",
    "busybox",
    "python",
    "source",
    "perl",
    "pwsh",
    "ruby",
    "node",
    "bash",
    "dash",
    "eval",
    "zsh",
    "ksh",
    "ash",
    "cmd",
    "sh",
)
# Programs that only read. An element is exempt from the second reading when every
# program it runs is one of these — the inverse of listing what executes text, because
# a name missing from THIS list costs a false deny, which the user can see and work
# around, while a name missing from that one turned the gate off in silence.
# A name earns its place by having no documented way to run a command written in its own
# arguments. `awk` (`system`, a piped command, `getline`), `sed` (GNU `e`), `find`
# (`-exec`, whose program and subcommand may be quoted), and the two searchers whose
# `--pager` goes through a shell (`ack`, `ag`) all do, which is why the tools a developer
# reaches for beside them are here and they are not. The ones that stay run a program by
# PATH rather than a shell string — `sort --compress-program`, `rg --pre` — where nothing
# the command spells becomes a command.
_READS_ONLY = frozenset(
    (
        "cat",
        "cut",
        "diff",
        "dirname",
        "du",
        "echo",
        "egrep",
        "false",
        "fgrep",
        "file",
        "grep",
        "head",
        "less",
        "ls",
        "more",
        "printf",
        "pwd",
        "rg",
        "shellcheck",
        "sort",
        "stat",
        "tail",
        "tr",
        "tree",
        "true",
        "type",
        "uniq",
        "wc",
        "whereis",
        "which",
    )
)
# A program token at a command position, with the name captured.
# Shell syntax standing where a program would. The list is the shell's own and therefore
# closed, unlike a list of programs, and both readings need it: a command may start after one
# of these words, and the word itself is not the program that starts there.
_RESERVED_WORDS = frozenset(
    (
        "case",
        "do",
        "done",
        "elif",
        "else",
        "esac",
        "fi",
        "for",
        "function",
        "if",
        "in",
        "select",
        "then",
        "time",
        "until",
        "while",
    )
)
# Where a command may start. One fragment for everything that has to find one, since each
# place that spelled its own ended up narrower than the shell somewhere.
_COMMAND_START = r"(?:^|[;&|(){}`\n]|\b(?:" + "|".join(sorted(_RESERVED_WORDS)) + r")\b)"
_PROGRAM_RE = re.compile(_COMMAND_START + r"[ \t]*(?:[^\s;&|()'\"]*[/\\])?([A-Za-z0-9_.+-]+)")
# A command position holding a substitution: the element runs what that prints.
_RUNS_ITS_OUTPUT_RE = re.compile(_COMMAND_START + r"[ \t]*(?:\$\(|`)")


def _programs(element: str) -> list[str]:
    """The names in command position in `element`, spelled without a host's `.exe`.

    A reserved word is both a token and the start of the command after it, and one pass cannot
    be both: matched as the name, the scan resumes past it and the program it introduces is
    never seen — which left a `grep` inside a `do` looking like a command with no program at
    all, and every quoted mention in a loop body was denied.
    """
    names: list[str] = []
    at, guard = 0, -1
    while True:
        m = _PROGRAM_RE.search(element, at)
        if m is None:
            return names
        name = m.group(1)
        names.append(name[:-4] if name.lower().endswith(".exe") else name)
        if name in _RESERVED_WORDS and m.start(1) > guard:
            at, guard = m.start(1), m.start(1)
        else:
            at = m.end()


def _reads_only(element: str) -> bool:
    """Whether every program `element` runs only reads — measured on the MASK.

    An element with no program at all is NOT exempt: a bare assignment holds a script
    something later runs, and exemption has to be earned by a name, not by the absence
    of one. Neither is an element whose command position is a substitution: `$(echo "git
    commit -m x")` runs the OUTPUT of the reader written in it, and reading the reader's own
    name as the program it runs is how that spelling passed.

    A shell reserved word is not a program, so the reader inside a loop or a conditional is
    still the only program there — read as one, `for f in *; do grep … done` had a program
    that is on no list and every quoted mention in it was denied.
    """
    if _RUNS_ITS_OUTPUT_RE.search(element):
        return False
    names = [n for n in _programs(element) if n not in _RESERVED_WORDS]
    return bool(names) and all(n in _READS_ONLY for n in names)


# One of those named anywhere in the element, as a whole token on the mask. It decides one
# thing only — whether a heredoc body in that element is a script or a message — and asking
# where the interpreter sits was the same mistake as the old trigger list: a reserved word, a
# prefix command, an assignment or a redirection in front of it all made `bash <<EOF` stop
# looking like an interpreter, and the body carrying a real commit went unread. Named rather
# than positioned, the cost is an element that runs something else and quotes an interpreter's
# name in a heredoc, which over-gates. `ssh` keeps its `s`: the token has to begin where the
# name does.
_INTERPRETER_RE = re.compile(
    r"(?:^|[^\w/\\.-])(?:[^\s;&|()'\"]*[/\\])?"
    r"(?:" + "|".join(_RUNS_TEXT) + r")(?:\.exe)?(?=$|[\s;&|)<>`])"
)
# Quoting, and the backslash that escapes a quote. A backslash escaping anything else is left
# alone: on the host this gate runs on it is a path separator, and rubbing it out turns
# `bash C:\\git\\commit\\run.sh` into an invocation.
_QUOTING_RE = re.compile(r"\\?[\"'`]")
# Where one element of a command list ends. The net reads ONE element: an interpreter in
# another element does not make this one's quoted text a script, and reading the whole
# string instead denies every read-only command that runs beside a python or a bash.
# A pipe is NOT a boundary — `printf '…' | bash` puts the script in the element before its
# interpreter.
_LIST_SEPARATOR_RE = re.compile(r"&&|\|\||[;\n]")
# A heredoc introducer. The delimiter is ONE WORD — quoted and unquoted pieces concatenated,
# ending at a blank or a metacharacter, exactly as the shell reads it — and group 2 is that word
# before quote removal. Read as a single bare token instead, three spellings go unrecognised and
# each leaves the body unmasked, which hands a commit the message merely quotes to the parser as
# a real invocation: `<<\EOF` (a backslash quotes the word as single quotes do), `<<'EO'F`
# (pieces joined), and — the one the commit skill's own template produces — a CRLF line, whose CR
# is an ordinary word character and so belongs to the delimiter the terminator line must match.
# A `<<<` here-string is excluded by the lookarounds, which also refuse to start mid-run of `<`.
# Group 1 is the `-` of `<<-`, which alone strips tabs from the terminator.
_HEREDOC_RE = re.compile(
    r"(?<!<)<<(-?)(?!<)[ \t]*((?:'[^']*'|\"[^\"]*\"|\\.|[^ \t\n;&|<>()'\"\\])+)"
)
# The token a `-C` value occupies, measured on the MASK: every literal region is a NUL run there,
# so a quoted span or a backslash-escaped blank is part of one whitespace-free token and this
# pattern states no opinion about quoting.
_MASK_TOKEN_RE = re.compile(r"\S+")
# Characters the scanners name rather than spell: the first three are what a heredoc
# delimiter must carry for its body to be literal text rather than code.
SQ_CH, DQ_CH, BS_CH, BT_CH, DOLLAR_CH = chr(39), chr(34), chr(92), chr(96), chr(36)
# What a backslash quotes: a blank, either quote, itself, and a newline (which joins two
# lines rather than quoting a character). Everything it precedes outside that set stays an
# ordinary pair, so a path written with backslash separators keeps them.
_QUOTED_BY_BACKSLASH = frozenset(" \t\"'\\\n;&|()<>")
# What runs the quoted argument that follows it. Two shapes: a word that takes a command
# (`eval`, `trap`), and an interpreter's script flag — which has to be preceded by the
# interpreter, or the same `-c` claims git's own global option and every tool's count
# flag. `-C` stays outside either: git's directory option takes a path, not a command.
_EXECUTES_NEXT_RE = re.compile(
    r"(?:^|[\s;&|(`])(?:"
    r"(?:eval|trap|source|exec|foreach)"
    r"|(?:[^\s;&|()'\"]*[/\\])?"
    r"(?:" + "|".join(_RUNS_TEXT) + r""
    r")(?:\.exe)?(?:\s+-[^\s-]\S*)*\s+-[a-z]*c(?:\s+--)?"
    r"|--run|-Command|/[cCkK]"
    r")[ \t]+$"
)
# What the two anchored predicates above can reach back over: the longest word either
# names, plus the blanks after it. Bounding the scan keeps them O(1) per quote.
_EXECUTES_NEXT_WINDOW = 128
# Where `(( … ))` may open: anywhere a command may start. Judged more widely than a quoted
# span's command position, because reading it as two subshells turns its left shift into a
# heredoc introducer.
_ARITH_START_RE = re.compile(_COMMAND_START + r"[ \t]*$")
_AT_COMMAND_START_RE = re.compile(r"(?:^|(?<!\\)[;&|({}\n])[ \t]*$")
# Kinds the mask turns into blanks rather than NUL: they separate tokens, they are not
# literal text sitting inside one.
_BLANKED = frozenset({"continuation", "delimiter"})
# `-C` as an option rather than a substring of a value. Located on the mask, then the value is
# read from the raw string at that offset — a `-C` inside a quoted option value is not an option,
# and its path must not be the answer.
_DASH_C_RE = re.compile(r"(?:^|\s)-C\s+")
# Where one simple command in a chain ends and the next begins. A NEWLINE separates two
# commands exactly as `&&` does, and the block risk-tiers documents for a squash merge is
# three newline-separated lines, so omitting it lets the shape the policy prescribes read as
# one command. CR covers CRLF.
_SEPARATOR_RE = re.compile(r"[;&|)\n\r]")


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


def _matching(command: str, at: int, opener: str, closer: str, depth: int = 1) -> int:
    """Index just past the `closer` that balances `depth` open `opener`s, starting at `at`.

    The closer is tested first because a backtick is its own closer: counted as another
    opening one the pair never balances, and the scan then swallows the rest of the
    command — every invocation after it included.
    """
    n = len(command)
    while at < n and depth:
        c = command[at]
        if c == "\\":
            at += 2
            continue
        if c == closer:
            depth -= 1
        elif c == opener:
            depth += 1
        at += 1
    return at


def _arith_end(command: str, at: int) -> int:
    """Index just past the `))` closing the arithmetic whose body starts at `at`.

    Arithmetic is scanned rather than masked because it is neither literal text nor a place a
    command can live — but its `<<` is a left shift, and read as a heredoc introducer it masks
    everything that follows, which is the rest of the command line the gate exists to read.
    """
    return _matching(command, at, "(", ")", depth=2)


def _nested(command: str, a: int, b: int) -> list[tuple[int, int, str]]:
    """Regions of the sub-command `command[a:b]`, in the coordinates of the whole string.

    An executed span is scanned as what it is — a command — so its own quoting is read the same
    way everywhere, and a `git … commit` inside it is an invocation while a `grep 'git commit'`
    inside it still is not.
    """
    return [(a + x, a + y, kind) for x, y, kind in _shell_regions(command[a:b])]


def _delimiter_word(raw: str) -> str:
    """A heredoc delimiter with its quoting removed — what the terminator line must equal.

    Quote removal only: the pieces are already one word, and every quoting form turns off
    expansion inside the body identically, so which one was used does not survive here.
    """
    out: list[str] = []
    i, n = 0, len(raw)
    while i < n:
        c = raw[i]
        if c == "\\" and i + 1 < n:
            out.append(raw[i + 1])
            i += 2
        elif c in "\"'":
            j = raw.find(c, i + 1)
            j = n if j == -1 else j
            out.append(raw[i + 1 : j])
            i = j + 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


def _heredoc_bodies(
    command: str, at: int, pending: list[tuple[bool, str, bool]]
) -> tuple[int, list[tuple[int, int, str]]]:
    """Consume the bodies of the heredocs opened on one line, in the order the shell reads them.

    Each body runs to its own terminator line and the next begins after it, so a second `<<` on
    the line is not a limitation to note but a body left unmasked — and unmasked text is handed
    to the parser as syntax.
    """
    regions = []
    n = len(command)
    for dash, word, literal in pending:
        end = _heredoc_body(command, at, word, dash)
        # Only a quoted or backslashed delimiter turns expansion off. With it on, a
        # substitution in the body is a command the shell runs, and masking the body
        # whole loses it.
        regions.extend(
            [(at, end, "heredoc")]
            if literal
            else _expanding(command, at, min(end, n), "heredoc")[1]
        )
        eol = command.find("\n", end)
        at = n if eol == -1 else eol + 1
    return at, regions


def _expanding(
    command: str, a: int, b: int, kind: str, stop: str | None = None
) -> tuple[int, list[tuple[int, int, str]]]:
    """Regions for `command[a:b]`, whose text is literal except where the shell expands.

    A double-quoted span and an unquoted heredoc body are the same shape: the runs between
    substitutions are text, and each substitution is the command it is. Masking the span
    whole loses a commit the shell really runs — `"$(git commit)"` runs one — and scanning it
    whole hands the parser a message as syntax. `stop` ends the run at the first unescaped
    occurrence of that character instead of at `b`, which is the only thing a quoted span does
    differently: it closes where the shell closes it, never at a quote inside a substitution
    the scan steps over on the way. Returns where the run ended and the regions in it.
    """
    regions: list[tuple[int, int, str]] = []
    j = lit = a
    while j < b and command[j] != stop:
        if command[j] == BS_CH:
            j += 2
            continue
        if command[j] == BT_CH or (command[j] == DOLLAR_CH and command[j + 1 : j + 2] == "("):
            if j > lit:
                regions.append((lit, j, kind))
            opened = j + 1 if command[j] == BT_CH else j + 2
            end = (
                _matching(command, opened, BT_CH, BT_CH)
                if command[j] == BT_CH
                else _matching(command, opened, "(", ")")
            )
            regions.extend(_nested(command, opened, min(end, b) - 1))
            j = lit = min(end, b)
            continue
        j += 1
    end = min(j, b)
    if end > lit:
        regions.append((lit, end, kind))
    return end, regions


def _double_quoted(command: str, i: int) -> tuple[int, list[tuple[int, int, str]]]:
    """Scan the `"…"` span opening at `i`; returns where it ends and the regions inside it."""
    n = len(command)
    end, regions = _expanding(command, i + 1, n, "quote", DQ_CH)
    return min(end + 1, n), regions


def _code_span(command: str, a: int, b: int) -> list[tuple[int, int, str]]:
    """Regions for a quoted span whose contents are code: `command[a:b]` is the interior.

    The delimiters become BLANKS rather than staying quote characters, so the token grammar
    sees a word boundary where the shell has one and needs no opinion about quoting; the
    interior is scanned as the command it is.
    """
    return [(a - 1, a, "delimiter"), (b, b + 1, "delimiter"), *_nested(command, a, b)]


def _executed_span(command: str, quote_at: int) -> bool:
    """Whether the quoted span opening at `quote_at` is an argument something RUNS.

    `bash -c '…'` and `eval "…"` hand their argument to a shell, so the text inside is a command
    however it is quoted. The set is small and named rather than inferred — a gate that tried to
    follow every way a string can become code would be a shell, and a determined bypass has
    unbounded spellings anyway (a terminal commit already skips every layer). What it must not
    do is be narrower than the substring match it replaced on the spellings agents actually
    write.
    """
    # Both patterns end at `$`, so only the characters immediately before the span can
    # match. Scanning from 0 re-reads the command once per quote, which is seconds of
    # hook latency on a quote-dense argument and, past the timeout, no verdict at all.
    start = max(0, quote_at - _EXECUTES_NEXT_WINDOW)
    return bool(
        _EXECUTES_NEXT_RE.search(command, start, quote_at)
        # A quoted span at a command position is the PROGRAM's name, not data: `'git'
        # commit` runs a commit, and reading the quotes as literal loses it entirely.
        or _AT_COMMAND_START_RE.search(command, start, quote_at)
    )


@lru_cache(maxsize=16)
def _shell_regions(command: str) -> tuple[tuple[int, int, str], ...]:
    """Index ranges of `command` the mask rewrites, each tagged with what it is.

    Memoised because one command is scanned by every reader in turn — the invocation grammar,
    the `-C` value, the merge operands, each switch's operands — and the scan is the expensive
    half of all of them. Pure over its one argument, so the cache can only save work.

    One state machine rather than a parity count per quote character: a `"` inside a `'…'` region
    is literal text, and `python3 -c '… "x" …'` is exactly the shape the commit skill issues, so
    counting the two independently would read everything after it as quoted. Outside `'…'` a
    backslash quotes the next character, so the `'\\''` idiom — the only way to put an apostrophe
    inside a single-quoted string, and what a commit subject holding one produces — does not leave
    the tally one quote short and shift every later pairing.

    The kinds differ in what the mask does with them, and in whether a command's operands end
    there (:func:`operand_end`):
      - `quote`/`heredoc`/`escape` — literal text, blanked to NUL. A heredoc body is literal to
        the shell without being a quoted span, and it is where this repo's commit messages live:
        a body that says `git -C <wt> commit` is the message talking about a commit, not making
        one, and reading its directory re-points ROOT at a tree the commit does not run in
        (Invariant #6). An `escape` covers only the character the backslash quotes, so the token
        it sits in stays one whitespace-free run on the mask while the backslash itself still
        shows in the raw string — which is how a Windows path keeps its separators.
      - `comment` — literal too, but it also ENDS the command, so it is tagged apart.
      - `continuation` — a backslash-newline joins two lines. Blanked to BLANKS, not NUL, so the
        grammar sees the whitespace the shell effectively leaves behind rather than a token
        boundary that splits a continued invocation into two words.
    Command substitutions, arithmetic and an interpreter's `-c` argument are none of these: they
    are code, and are scanned as such rather than masked.
    """
    regions: list[tuple[int, int, str]] = []
    # heredocs opened on this line, in the order bash reads them
    pending: list[tuple[bool, str, bool]] = []
    body_at: int | None = None  # where the first of their bodies starts
    i, n = 0, len(command)
    while i < n:
        if body_at is not None and i >= body_at:
            i, bodies = _heredoc_bodies(command, body_at, pending)
            regions.extend(bodies)
            pending, body_at = [], None
            continue
        ch = command[i]
        if ch == "\\" and command[i + 1 : i + 3] == "\r\n":
            regions.append((i, i + 3, "continuation"))  # a CRLF-authored line join
            i += 3
            continue
        if ch == "\\" and command[i + 1 : i + 2] in _QUOTED_BY_BACKSLASH:
            # A backslash quotes only what needs quoting here. Taken as quoting ANY next
            # character it destroys the one shape this option carries on the host the gate
            # runs on: C:\\Git\\bin\\git would lose the `git` the grammar has to see, and
            # a program the mask cannot spell is a gate that never runs.
            regions.append(
                (i, i + 2, "continuation") if command[i + 1] == "\n" else (i + 1, i + 2, "escape")
            )
            i += 2
            continue
        if ch == "#" and (i == 0 or command[i - 1] in " \t\n;&|("):
            eol = command.find("\n", i)
            end = n if eol == -1 else eol
            regions.append((i, end, "comment"))  # a `-C` in a comment is not an option either
            i = end
            continue
        if ch == "$" and command[i + 1 : i + 2] == "[":  # the older arithmetic spelling
            i = _matching(command, i + 2, "[", "]")
            continue
        if (
            ch == "("
            and command[i + 1 : i + 2] == "("
            and _ARITH_START_RE.search(command, max(0, i - _EXECUTES_NEXT_WINDOW), i)
        ):
            i = _arith_end(command, i + 2)  # `(( … ))` as a command, not two subshells
            continue
        if ch == "$" and command[i + 1 : i + 2] == "(":  # a command, wherever it appears
            end = _matching(command, i + 2, "(", ")")
            regions.extend(_nested(command, i + 2, min(end, n) - 1))
            i = end
            continue
        if ch == "`":
            i += 1  # its contents are a command; only the delimiters are not
            continue
        if ch == "$" and command[i + 1 : i + 2] == "'":  # ANSI-C quoting — backslashes inside
            j = i + 2
            while j < n and command[j] != "'":
                j += 2 if command[j] == "\\" else 1
            regions.append((i + 2, min(j, n), "quote"))
            i = j + 1
            continue
        if ch == '"':
            end, inner = _double_quoted(command, i)
            code = _executed_span(command, i) and end - 1 <= n
            regions.extend(_code_span(command, i + 1, end - 1) if code else inner)
            i = end
            continue
        if ch == "'":
            j = command.find("'", i + 1)
            j = n if j == -1 else j
            code = _executed_span(command, i) and j < n
            regions.extend(_code_span(command, i + 1, j) if code else [(i + 1, j, "quote")])
            i = j + 1
            continue
        m = _HEREDOC_RE.match(command, i)
        if m:
            eol = command.find("\n", m.end())
            if eol != -1:  # no newline → no body at all, and the rest of the line is still syntax
                if body_at is None:
                    body_at = eol + 1
                raw = m.group(2)
                literal = any(q in raw for q in (SQ_CH, DQ_CH, BS_CH))
                pending.append((bool(m.group(1)), _delimiter_word(raw), literal))
            i = m.end()
            continue
        i += 1
    if body_at is not None:  # the introducer line was the whole scan
        regions.extend(_heredoc_bodies(command, body_at, pending)[1])
    return tuple(regions)


def mask_literals(command: str) -> str:
    """`command` with every literal region blanked, same length and same delimiters.

    A quoted argument stays one whitespace-free token, so the option grammar can be written
    without respelling the quoting rules, and offsets still index back into the original.
    A line continuation becomes blanks instead — it separates nothing, so a token must not end
    there.
    """
    out = list(command)
    for a, b, kind in _shell_regions(command):
        out[a:b] = (" " if kind in _BLANKED else "\x00") * (b - a)
    return "".join(out)


def _unquoted_view(command: str, *, keep_heredoc: bool = False) -> str:
    """`command` with its quoting rubbed out rather than its quoted text erased.

    What the net reads. The point is to see the script an interpreter was handed, which a mask
    that blanks it cannot show. Comments go the other way and are blanked: a `#` run is the one
    literal region no interpreter can ever be handed. Same length throughout, so the two
    readings describe the same string.
    """
    out = list(command)
    for a, b, kind in _shell_regions(command):
        if kind == "comment" or (kind == "heredoc" and not keep_heredoc):
            out[a:b] = " " * (b - a)
    return _QUOTING_RE.sub(lambda m: " " * len(m.group()), "".join(out))


def _list_elements(command: str, masked: str) -> list[tuple[int, int]]:
    """Index ranges of `command`, one per element of its command list.

    Split on the mask, so a separator inside a message or a comment ends nothing. A newline
    that opens a heredoc body is not a boundary either: the body is that command's input, and
    cut away from it the interpreter and the script it is handed land in different elements.
    """
    bodies = {a for a, _b, kind in _shell_regions(command) if kind == "heredoc"}
    spans, start = [], 0
    for m in _LIST_SEPARATOR_RE.finditer(masked):
        if m.group() == chr(10) and m.end() in bodies:
            continue
        spans.append((start, m.start()))
        start = m.end()
    spans.append((start, len(command)))
    return spans


def is_invocation(command: str, word: str) -> bool:
    """Whether `command` runs `git <word>` — the gate's single authority on that question.

    Two readings, in order. The precise one asks the grammar about the mask, where quoted text
    is data: that is what keeps a read-only `git -c commit.gpgsign=false log` from being denied
    as an unclassified commit. Behind it sits a net for the case the mask is wrong about — the
    element of the command list runs something other than a reader, so its quoted text
    may be a script rather than data. The same grammar is then tried over that element
    with its quoting rubbed out.

    The exemption is the list, not the gating: a program nobody listed as read-only
    over-gates, which the user sees and can work around, where a channel nobody listed
    as executing turned the gate off with nothing reported.

    The net cannot fire on a command that starts no interpreter, so it adds nothing to the
    read-only side. What it costs is a command that both starts one and says something
    commit-shaped: that one is gated rather than missed, which is the direction this gate is
    allowed to be wrong in.

    Detection only. A merge's FLAGS are still read off the mask, so a merge the net alone
    finds has no strategy verdict and fails open — uncertain, therefore allowed.
    """
    pattern = git_subcommand_re(word)
    masked = mask_literals(command)
    if pattern.search(masked):
        return True
    plain = _unquoted_view(command)
    scripted = _unquoted_view(command, keep_heredoc=True)
    for a, b in _list_elements(command, masked):
        if _reads_only(masked[a:b]):
            continue
        view = scripted if _INTERPRETER_RE.search(masked[a:b]) else plain
        if pattern.search(view[a:b]):
            return True
    return False


def operand_words(command: str, masked: str, start: int, end: int) -> list[str]:
    """The words `command[start:end]` holds, read the way the shell splits them.

    Taken from the unquoted view rather than the raw string: extents are measured on the
    mask, so a raw slice can carry the closing delimiter of a span the mask blanked, and
    shlex then raises on it — which reads as `no merge here` and drops a fail-CLOSED
    verdict. Continuations go too: a `\\` before a newline is not a word.
    """
    import shlex

    text = list(command[start:end])
    for a, b, kind in _shell_regions(command):
        if kind in _BLANKED:
            for i in range(max(a, start), min(b, end)):
                text[i - start] = " "
    try:
        return shlex.split("".join(text))
    except ValueError:
        return []


def operand_end(command: str, masked: str, start: int, end: int | None = None) -> int:
    """Where the simple command whose operands begin at `start` stops taking them.

    A command's words end at the separator that starts the next one, or at a comment. Read to
    end of input instead, a later command's flags join this one's and a `--squash` written in a
    trailing comment satisfies the policy row that requires it. Separators are located on the
    MASK, so one inside a message or a heredoc body ends nothing.
    """
    stop = len(command) if end is None else end
    for a, _b, kind in _shell_regions(command):
        if kind == "comment" and start <= a < stop:
            stop = a
    m = _SEPARATOR_RE.search(masked, start, stop)
    return m.start() if m else stop


def _unquote(command: str, masked: str, a: int, b: int) -> str:
    """The value of the token `command[a:b]`, whose extent was measured on `masked`.

    Quote and escape removal, with ONE deliberate departure from the shell: a backslash is
    dropped only when it quotes a blank, a quote or another backslash. The shell drops every one,
    which would turn a `-C C:\\work\\wt` — the shape this option actually carries on the host the
    gate runs on — into a path that resolves to nothing, and an unresolvable directory sends the
    whole read back to main.
    """
    out: list[str] = []
    i = a
    while i < b:
        c = command[i]
        if masked[i] == "\x00":  # inside a literal region — the character stands as written
            out.append(c)
        elif c in "\"'":  # a delimiter of a quoted span, not content
            pass
        elif c == "\\" and i + 1 < b and command[i + 1] in " \t\"'\\":
            pass  # the backslash quotes what follows; that character is the next step
        else:
            out.append(c)
        i += 1
    return "".join(out)


def dash_c_value(command: str, masked: str, start: int, end: int) -> str | None:
    """The `-C <dir>` of the options region `command[start:end]`, or None.

    Both halves read the MASK: the option, so a `-C` inside a quoted value is not one, and the
    token's extent, so a quoted span or a backslash-escaped blank does not end it early. Only the
    value itself is then taken from the raw string, through :func:`_unquote`.
    """
    d = _DASH_C_RE.search(masked, start, end)
    if not d:
        return None
    m = _MASK_TOKEN_RE.match(masked, d.end(), end)
    return _unquote(command, masked, m.start(), m.end()) if m else None


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
