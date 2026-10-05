"""flow-config-based gate check helpers.

The host repository path is accessed only via the CLAUDE_PROJECT_DIR environment
variable, and internal errors do not block the gate (fail-open).
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path

# Host-root resolution, encoding defenses, and gate contract constants (blocking exit
# code·runtime gate keys·tier labels) come from the shared SSOT (_harness_paths)
# (no duplicate definitions — rule-dry-constants).
# flow_gate_check is copied to the host and run directly (sibling import) or imported as a package
# in tests — see the compatibility idiom in the _harness_paths module docstring.
try:
    from _harness_paths import (
        _PATH_TOKEN,
        BLOCK_EXIT_CODE,
        CONFIG_DIR,
        OPAQUE_CH,
        RELEASE_TIER,
        RUNTIME_GATES,
        STAGING_TIER,
        TIERS_FILENAME,
        commit_tree_unresolved,
        config_path,
        flow_dir,
        force_utf8_io,
        git_subcommand_re,
        host_root,
        invocation_words,
        is_invocation,
        live_invocations,
        mask_literals,
        operand_end,
        working_root,
    )
except ImportError:
    from scripts._harness_paths import (
        _PATH_TOKEN,
        BLOCK_EXIT_CODE,
        CONFIG_DIR,
        OPAQUE_CH,
        RELEASE_TIER,
        RUNTIME_GATES,
        STAGING_TIER,
        TIERS_FILENAME,
        commit_tree_unresolved,
        config_path,
        flow_dir,
        force_utf8_io,
        git_subcommand_re,
        host_root,
        invocation_words,
        is_invocation,
        live_invocations,
        mask_literals,
        operand_end,
        working_root,
    )

# The wiki runtime gate, same sibling-vs-package idiom — but with a third branch, because this
# sibling is genuinely optional. Plugin scripts are copied to the host ONE FILE AT A TIME (see
# _harness_paths' header), so a host can hold flow_gate_check.py without wiki_graph.py. An
# unguarded import would make this whole file unimportable there, taking the tier/marker gate
# down with it and switching enforcement off silently. None → wiki_gate opens, nothing else
# changes. Not a cycle: wiki_graph imports _harness_paths, never this module.
try:
    from wiki_graph import cmd_verify  # direct execution (sibling)
except ImportError:
    try:
        from scripts.wiki_graph import cmd_verify  # package (test/dev)
    except ImportError:
        cmd_verify = None

# The doc-style runtime gate, optional for the same reason: a half-copied host can hold this
# file without doc_style_check.py. None means the gate reports nothing.
# `except Exception`, not `except ImportError`: a sibling that raises anything at import —
# a syntax the host's python is too old for, a bad module-level expression — would
# otherwise abort THIS module too, and a flow_gate_check.py that never runs is the gate
# off in silence, including its fail-closed block on an unclassified commit.
try:
    from doc_style_check import in_scope, lint_paths  # direct execution (sibling)
except Exception:
    try:
        from scripts.doc_style_check import in_scope, lint_paths  # package (test/dev)
    except Exception:
        in_scope = lint_paths = None


def load_lifecycle_branches(config_path: Path) -> dict[str, str]:
    """Read the branches section of flow-config.yaml and return a {branch name: tier} mapping.

    - staging key → "staging" tier
    - production key → "release" tier
    - Returns {} if the file is missing or on parse error (fail-open)
    """
    if not config_path.is_file():
        return {}
    try:
        import yaml

        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    branches = data.get("branches") or {}
    out: dict[str, str] = {}
    if staging := branches.get("staging"):
        out[str(staging)] = STAGING_TIER
    if production := branches.get("production"):
        out[str(production)] = RELEASE_TIER
    return out


def required_gates(tiers_path: Path, tier: str) -> list[str] | None:
    """Return the gates list for a given tier from flow-tiers.yaml.

    - Returns None if the tier does not exist
    - Returns None if the file is missing or on parse error (fail-open)
    """
    if not tiers_path.is_file():
        return None
    try:
        import yaml

        data = yaml.safe_load(tiers_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    node = (data.get("tiers") or {}).get(tier)
    return list(node.get("gates", [])) if node else None


def load_merge_strategy(tiers_path: Path) -> list[dict]:
    """Return the merge_strategy rule list from flow-tiers.yaml.

    - Returns [] if the file is missing, fails to parse, has no merge_strategy key, or the
      key is not a list (FAIL-OPEN — Invariant #1). Removing the key disables the check.
    """
    if not tiers_path.is_file():
        return []
    try:
        import yaml

        data = yaml.safe_load(tiers_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    rules = data.get("merge_strategy")
    if not isinstance(rules, list):
        return []
    return [r for r in rules if isinstance(r, dict)]


# The `git … merge` invocation itself, not the first ` merge` in the string. Sharing the commit
# path's grammar is the point: a word inside a quoted argument or a heredoc body is text, and
# splitting there starts the operand region mid-string (shlex then raises and the strategy verdict
# never runs) or truncates the head before the `-C` that names another worktree.
_MERGE_RE = git_subcommand_re("merge")


# Short options that consume the next token as their argument when nothing is attached. If not
# skipped, `-m "msg"` — or `-qm "msg"`, the same option in a bundle — would leak the message into
# the source-branch slot.
# `-S` is deliberately ABSENT: git takes its keyid *attached* (`-Skeyid`), never as a separate
# token, so listing it here would swallow the source branch of `git merge -S feature/x` and
# silently disable the check for signed merges. It owns the rest of its bundle instead.
_MERGE_SHORT_WITH_ARG = "mFsX"


def _short_takes_next(tok: str, with_arg: str, owns_rest: str) -> bool:
    """Whether a short-option word such as `-qm` hands the next word to one of its options.

    git reads a bundle letter by letter: the first option in `with_arg` takes the attached rest
    as its value, or the next word when nothing is attached; one in `owns_rest` takes the rest
    and never the next word."""
    for i, letter in enumerate(tok[1:], 1):
        if letter in with_arg:
            return i == len(tok) - 1
        if letter in owns_rest:
            return False
    return False


def _merge_dirs(command: str) -> list[str | None]:
    """Where each `git … merge` in the command runs, ``None`` for one that names no directory.

    Every merge, and the ``None``s kept: a merge with no `-C` runs wherever the shell stands,
    which is the root the gate is already judging unless a `cd` moved it — so it is what says
    the command merges HERE, and the caller reads it that way.
    Dropping it — or reading only the first merge — lets `git merge feature/x && git -C /tmp
    merge y` claim the whole command belongs to another worktree, which is one appended token
    away from turning merge-strategy enforcement off.
    """
    invocations = [*invocation_words(command, "merge"), *invocation_words(command, "pull")]
    return [d for _start, d, _g, _o in sorted(invocations, key=lambda inv: inv[0])]


# A leading `cd <dir>` before the merge — the merge path's own separator variant of
# _harness_paths._CD_PREFIX_RE. Two differences: this one also reads a bare carriage return as
# a separator, and it keeps _PATH_TOKEN, whose bare-path branch runs to the next whitespace
# instead of stopping at `;`/`&`/`|`.
# Deliberately NOT folded into the shared regex: the two paths have opposite risk polarity.
# Here a match only ever FAILs OPEN (Invariant #1 — `_points_elsewhere` → exit 0). There the same
# match re-points ROOT to another worktree for status/diff/tier-marker/module-lint, which
# Invariant #6 requires to stay conservative ("any uncertainty → main; never newly block").
# One grammar cannot carry both polarities, so the merge path states its own separators.
# Anchored in the pattern too, for the reason _CD_PREFIX_RE carries: under `search` the leading
# `\s*` retries at every start position.
_MERGE_CD_PREFIX_RE = re.compile(rf"\A\s*cd\s+(?:{_PATH_TOKEN})\s*(?:&&|[;\n\r])")


def parse_merge_command(command: str) -> tuple[set[str], str | None]:
    """Extract (flags, source branch) from a `git merge` invocation.

    Only the region *after* the `merge` subcommand is parsed, so `git -C <dir> merge X` never
    mistakes the -C argument for the source (and Windows backslash paths never reach shlex).
    Returns (set(), None) when this is not a merge, when there is no source operand, or on any
    parse failure (FAIL-OPEN — Invariant #1).
    """
    if not command:
        return set(), None
    merges = parse_merge_commands(command)
    return merges[0] if merges else (set(), None)


def parse_merge_commands(command: str) -> list[tuple[set[str], str]]:
    """Every `git merge` the command runs that names a source, in order.

    All of them, because a merge that names no source (`--abort`, `--continue`) or one
    the policy accepts sitting in front of another left everything after it unjudged —
    and the strategy verdict is one of the three this gate may never fail open on.
    """
    return [(flags, source) for _start, flags, source in _merges(command)]


def _merges(command: str) -> list[tuple[int, set[str], str]]:
    """(where it starts, flags, source) of every `git merge` naming a source."""
    out = []
    for start, _dir, global_opts, operands in invocation_words(command or "", "merge"):
        flags, source = _merge_operands(operands, global_opts)
        if source:
            out.append((start, flags, source))
    return out


# The options a strategy row can name, as their own pairs: the last of a pair wins in git.
_SQUASH_FLAGS = ("--squash", "--no-squash")
_FF_FLAGS = ("--ff", "--no-ff", "--ff-only")
# Long options that take the next word, abbreviable like any other.
_LONG_WITH_ARG = (
    "--message",
    "--file",
    "--strategy",
    "--strategy-option",
    "--into-name",
    "--cleanup",
)


def _resolve(name: str, choices: tuple[str, ...]) -> str | None:
    """The one of `choices` a long option `name` spells, exactly or as an abbreviation.

    git takes any unambiguous prefix of a long option. A prefix of one of these that git
    accepts can only mean that one, since a second option sharing the prefix would make git
    refuse it; a prefix git refuses runs no merge, so reading it either way blocks nothing
    that would have merged."""
    if name in choices:
        return name
    if len(name) <= 2 or not name.startswith("--"):
        return None
    hits = [c for c in choices if c.startswith(name)]
    return hits[0] if len(hits) == 1 else None


_FALSE_WORDS = ("false", "no", "off", "")
_TRUE_WORDS = ("true", "yes", "on")


def _config_bool(val: str | None) -> bool | None:
    """A config value read as git reads a boolean — untrimmed, case-folded, an integer by its
    value — or None for anything git would not take as one. No value at all (`-c key`) is
    true; an empty one (`-c key=`) is false."""
    if val is None:
        return True
    if val in _FALSE_WORDS:
        return False
    if val in _TRUE_WORDS:
        return True
    if re.fullmatch(r"[+-]?\d+", val):
        return int(val) != 0
    return None


def _config_values(global_opts: list[str], key: str) -> list[str | None]:
    """Every value a `-c <key>=<value>` among git's global options sets, in order, case-folded
    and untrimmed as git leaves it; None for a bare `-c <key>`."""
    values: list[str | None] = []
    for flag, value in zip(global_opts, global_opts[1:]):
        if flag != "-c":
            continue
        name, eq, val = value.partition("=")
        if name.lower() == key:
            values.append(val.lower() if eq else None)
    return values


def _config_ff(global_opts: list[str], keys: tuple[str, ...] = ("merge.ff",)) -> str | None:
    """The fast-forward mode `-c <key>=…` sets, as the flag it stands in for. A later key in
    `keys` outranks an earlier one, as `pull.ff` outranks `merge.ff` for a pull."""
    mode = None
    for key in keys:
        for val in _config_values(global_opts, key):
            setting = _config_bool(val)
            if val == "only":
                mode = "--ff-only"
            elif setting is not None:
                mode = "--ff" if setting else "--no-ff"
    return mode


def _merge_operands(
    tokens: list[str],
    global_opts: list[str] | None = None,
    ff_keys: tuple[str, ...] = ("merge.ff",),
    takes_values: bool = True,
) -> tuple[set[str], str | None]:
    """(flags, source) from the words after one `merge` — the flags as git reads them: an
    abbreviation is the option it spells, the last of `--squash`/`--no-squash` and of the
    fast-forward modes wins, and a `-c merge.ff` stands in for a mode no flag sets.
    `takes_values=False` reads flag words whose values a caller already removed."""
    flags: set[str] = set()
    source: str | None = None
    squash = False
    ff = _config_ff(global_opts or [], ff_keys)
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if tok.startswith("-"):
            name = tok.split("=", 1)[0]
            if takes_values and (
                ("=" not in tok and _resolve(name, _LONG_WITH_ARG))
                if tok.startswith("--")
                else _short_takes_next(tok, _MERGE_SHORT_WITH_ARG, "S")
            ):
                skip_next = True
                continue
            if resolved := _resolve(name, _SQUASH_FLAGS):
                squash = resolved == "--squash"
            elif resolved := _resolve(name, _FF_FLAGS):
                ff = resolved
            else:
                flags.add(name)
            continue
        if source is None:
            source = tok
    if squash:
        flags.add("--squash")
    if ff:
        flags.add(ff)
    return flags, source


# Options of `git pull` that take the next word (its fetch half included); `-j`/`--jobs` take
# theirs attached only. Short ones open a bundle whose rest is their value.
_PULL_SHORT_WITH_ARG = "sXo"
_PULL_LONG_WITH_ARG = (
    "--strategy",
    "--strategy-option",
    "--server-option",
    "--depth",
    "--deepen",
    "--shallow-since",
    "--shallow-exclude",
    "--upload-pack",
    "--negotiation-tip",
    "--refmap",
    "--cleanup",
)
_PULL_RE = git_subcommand_re("pull")


def _rebase_setting(tok: str) -> bool | None:
    """Whether a `git pull` option turns rebasing on (True) or off (False); None for any other.
    A short bundle is read letter by letter: `-r` anywhere in it rebases, its attached rest
    being the mode, unless an option taking a value comes first and owns the rest."""
    if not tok.startswith("--"):
        for i, letter in enumerate(tok[1:], 1):
            # `-S` and `-j` take an optional value attached, so they own the rest as well
            if letter in _PULL_SHORT_WITH_ARG or letter in "Sj":
                return None
            if letter == "r":  # nothing attached is no value, not an empty one
                return _config_bool(tok[i + 1 :].lower() or None) is not False
        return None
    name, eq, val = tok.partition("=")
    resolved = _resolve(name, ("--rebase", "--no-rebase"))
    if resolved == "--rebase":
        return not eq or _config_bool(val.lower()) is not False
    if resolved == "--no-rebase":
        return False
    return None


def _takes_pull_value(tok: str) -> bool:
    """Whether this `git pull` option word is followed by its value as the next word."""
    if tok.startswith("--"):
        return "=" not in tok and _resolve(tok, _PULL_LONG_WITH_ARG) is not None
    return _short_takes_next(tok, _PULL_SHORT_WITH_ARG, "Sjr")


def _pull_merges(command: str) -> list[tuple[int, set[str], str]]:
    """(where it starts, flags, source) for every branch a `git pull` merges by name."""
    out = []
    for start, _dir, global_opts, operands in invocation_words(command or "", "pull"):
        rebase = False
        for val in _config_values(global_opts, "pull.rebase"):
            rebase = _config_bool(val) is not False
        flag_words: list[str] = []
        positional: list[str] = []
        skip_next = False
        for tok in operands:
            if skip_next:
                skip_next = False
                continue
            if tok.startswith("-"):
                if _takes_pull_value(tok):
                    skip_next = True
                elif (setting := _rebase_setting(tok)) is not None:
                    rebase = setting
                else:
                    flag_words.append(tok)
                continue
            positional.append(tok)
        if rebase:
            continue
        flags, _ = _merge_operands(
            flag_words, global_opts, ff_keys=("merge.ff", "pull.ff"), takes_values=False
        )
        for spec in positional[1:]:
            source = spec.lstrip("+").split(":", 1)[0]
            if source:
                out.append((start, flags, source))
    return out


def parse_pull_commands(command: str) -> list[tuple[set[str], str]]:
    """(flags, source) for every branch a `git pull` merges by name.

    A pull that names no branch merges an upstream the command does not spell, and one that
    rebases merges nothing: neither is judged. A `pull.rebase` or `pull.ff` set in the
    repository is not read either (Exception 3 decides from the command alone), so a pull that
    config turns into a rebase is judged as the merge it spells."""
    return [(flags, source) for _start, flags, source in _pull_merges(command)]


def _switch_operand_words(words: list[str]) -> str | None:
    """The branch a `git switch`/`git checkout` with these operand words lands HEAD on, else
    None (unclear).

    Clear means exactly one operand and no flag at all. Every other shape moves HEAD somewhere
    this parser cannot name, so it is unclear rather than "the first bare word":
      - `checkout dev -- a/b.py` restores a FILE from dev; HEAD does not move at all.
      - `switch -c feature/y` / `checkout -b` create and land on a DIFFERENT branch.
      - `checkout origin/dev` lands on a detached HEAD — yet :func:`_branch_matches` strips
        `origin/`, so adopting it would match the integration rules it never entered.
      - `switch -`, `checkout --detach`, unbalanced quotes (no words at all), a branch a
        substitution prints: unnameable.
    """
    if len(words) != 1 or words[0].startswith(("-", "origin/")) or OPAQUE_CH in words[0]:
        return None
    return words[0]


def _target_from_command(command: str, head_end: int | None = None) -> str | None:
    """Branch a `git switch`/`git checkout` before `head_end` moves onto — the real target of
    the merge starting there (the first merge's, when no position is given).

    `git switch dev && git merge feature/x` merges INTO dev, but at hook time HEAD is still
    feature/x. The command states the target explicitly, so it wins over the hook-time branch.

    The rule is "EVERY switch/checkout before the merge must be clear, and then the last one
    wins" — not "the last one that happens to parse". A single unclear invocation anywhere in the
    chain returns None, because it may be the one that decides HEAD: in
    `git switch dev && git switch -c feature/y && git merge feature/x` HEAD ends on feature/y,
    which no rule covers, yet picking the last *parseable* switch adopts the stale `dev` and
    blocks a merge the policy never governs. None → the caller falls back to the hook-time branch
    (FAIL-OPEN, Invariant #1 — this direction can only ever block less).
    """
    if not command:
        return None
    if head_end is None:
        merge = _MERGE_RE.search(mask_literals(command))
        head_end = merge.end(1) if merge else len(command)
    return _merge_targets(command, [head_end])[0]


def _merge_targets(command: str, head_ends: list[int]) -> list[str | None]:
    """:func:`_target_from_command` for every merge position at once.

    One pass over the command for all of them: read once per merge, a chain of merges cost the
    square of its length, and a hook that times out lets the merge through."""
    if not command or not head_ends:
        return [None] * len(head_ends)
    # merge-strategy's feature/* → integration block (`git switch <integration>` → `git pull
    # --ff-only` → `git merge --squash feature/<name>`) arrives as ONE Bash call, so at hook time
    # HEAD is still the source branch: without the switch, the very idiom the policy documents
    # would match no rule.
    # Read off the merge path's own invocations, a `git switch` the mask cannot see — `git
    # sw''itch dev` — included: it moves HEAD all the same. A switch written in a comment, quoted
    # in a message, or sitting in a heredoc body is text and is not among them, and adopting its
    # branch would judge the merge against a flow nobody ran.
    # (start, where its operands end, branch); a split switch's operands end where its stage does
    masked = mask_literals(command)
    moves = []
    for start, word, _dir, _globals, operands, end in live_invocations(command):
        if word not in ("switch", "checkout"):
            continue
        if end is None:
            end = operand_end(command, masked, _STAGE_LEAD_RE.match(masked, start).end())
        moves.append((start, end, _switch_operand_words(operands)))
    # A switch counts for a merge once its operands end before the merge starts. One whose
    # operands hold the merge — `git switch $(git merge x)` — runs after it, since the shell
    # expands an argument before running the command it feeds.
    moves.sort(key=lambda move: move[1])
    out: list[str | None] = [None] * len(head_ends)
    i, void, latest = 0, False, None
    for idx in sorted(range(len(head_ends)), key=head_ends.__getitem__):
        while i < len(moves) and moves[i][1] <= head_ends[idx]:
            start, _end, branch = moves[i]
            void = void or branch is None  # one unclear switch voids the whole chain
            if latest is None or start > latest[0]:
                latest = (start, branch)
            i += 1
        out[idx] = None if void or latest is None else latest[1]
    return out


# The separators and blanks a split switch's stage can open with, before its first word.
_STAGE_LEAD_RE = re.compile(r"[\s;&|]*")


def _points_elsewhere(command: str, root: Path) -> bool:
    """Whether the command runs the merge in a directory other than ``root``.

    Two shell forms name an execution directory, and both must be recognised: `git -C <dir> merge
    X` (git's own global option) and a leading `cd <dir> && … git merge X`. Either way the source
    comes from the command while the target would be read from THIS root — a mismatch that has
    produced false blocks naming a flow that has no rule at all. The merge path must not
    re-designate the worktree (Invariant #6), so a foreign directory FAILs OPEN
    (Invariant #1). A directory that resolves to ``root`` itself is not foreign and stays
    enforced. Unresolvable path → treated as foreign.

    Relative directories resolve against ``root``, never the process cwd: the merge check runs
    before precommit-runner.sh's `cd "$ROOT"`, so the interpreter's cwd is the hook cwd and
    reading `git -C .` there would call root itself foreign and skip the gate.
    """
    dirs = _merge_dirs(command)
    if not any(d for d in dirs):
        m = _MERGE_CD_PREFIX_RE.match(command)
        cdir = next((g for g in m.groups() if g is not None), None) if m else None
        if cdir:
            dirs = [cdir]
    if not dirs:
        return False
    try:
        here = Path(root).resolve()
        # ALL of them, so one merge that runs here keeps the whole command judged. `any` would
        # read a command as foreign on the strength of its foreign HALF, and the half that runs
        # here would merge unjudged — the direction Exception 3 is fail-closed to prevent.
        # A `None` counts as here even behind a `cd` that moved the shell: the prefix above is
        # read only when NO merge named a directory, so a mixed chain behind a `cd` is judged
        # against a root none of it runs in. An over-block, and the side to err on for a rule
        # that exists to keep a local merge judged.
        return all(d is not None and Path(root, d).resolve() != here for d in dirs)
    except Exception:
        return True


# What a branch name can carry in front of it and still name that branch: its full ref, a
# remote-tracking ref (the remote is the segment after `remotes/`), or `origin/`. A `-` or a sha
# names no branch the command spells, so it matches no rule.
_REF_PREFIX_RE = re.compile(r"^(?:refs/heads/|heads/|(?:refs/)?remotes/[^/]+/|origin/)")


def _branch_matches(pattern: str, branch: str, branches: dict) -> bool:
    """Whether a branch matches a merge_strategy source/target pattern.

    A pattern containing `/` is a branch-prefix glob (`feature/*` → startswith `feature/`);
    otherwise it is a flow-config.branches key compared against that key's value. A ref
    prefix (`_REF_PREFIX_RE`) is stripped from the branch first, so `git merge origin/stage`
    and `refs/heads/stage` match the `staging` key. An unknown key never matches (FAIL-OPEN
    — no rule applies).
    """
    if not pattern or not branch:
        return False
    name = _REF_PREFIX_RE.sub("", branch)
    if "/" in pattern:
        return name.startswith(pattern.rstrip("*"))
    configured = branches.get(pattern)
    return bool(configured) and name == str(configured)


# A revision suffix: `stage^0`, `stage~2`, `stage@{1}` and `stage^{commit}` merge stage's own
# history, and no branch name can hold `^`, `~` or `@{`.
_REV_SUFFIX_RE = re.compile(r"(?:[\^~]|@\{).*\Z", re.DOTALL)


def match_merge_rule(rules: list[dict], source: str, target: str, branches: dict) -> dict | None:
    """Return the first rule whose source and target both match, else None (FAIL-OPEN).

    The source is judged as the branch its revision suffix starts from. The target is not: a
    switch to `main^0` detaches HEAD, and the merge lands on no branch."""
    source = _REV_SUFFIX_RE.sub("", source)
    for rule in rules:
        if _branch_matches(str(rule.get("source", "")), source, branches) and _branch_matches(
            str(rule.get("target", "")), target, branches
        ):
            return rule
    return None


def _is_rebased(root: Path, source: str, target: str) -> bool:
    """Whether target is an ancestor of source (i.e. source was rebased onto target).

    Used only for the warning path — a False here never blocks. Any git failure returns True
    (treated as "no complaint") so a stale/absent ref cannot produce a spurious warning.
    """
    try:
        rc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", target, source],
            cwd=str(root),
            capture_output=True,
            timeout=5,
        ).returncode
    except Exception:
        return True
    return rc == 0


def merge_check_output() -> None:
    """Check a `git merge` invocation against the merge_strategy policy.

    Blocks (BLOCK_EXIT_CODE) only on two purely syntactic verdicts — a missing `require` flag or
    a present `forbid` flag. Everything else (not a merge, no source, no policy, no matching
    rule, detached HEAD, a merge run in another worktree, any exception) exits 0 (FAIL-OPEN —
    Invariant #1). The rebase check only warns. Invariant #2: force_utf8_io before any output.

    The target branch is read from the command when it says so (`git switch dev && git merge …`)
    and only otherwise from HEAD — see :func:`_target_from_command`.
    """
    force_utf8_io()
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)
    command = (payload.get("tool_input") or {}).get("command") or ""
    merges = sorted(_merges(command) + _pull_merges(command), key=lambda m: m[0])
    if not merges:
        sys.exit(0)

    root = host_root()
    # Each merge's target is the switch before IT: a switch after a merge moves nothing that
    # merge lands in, and one between a pull and a later merge decides only the later one.
    targets = _merge_targets(command, [start for start, _f, _s in merges])
    if not all(targets):
        if _points_elsewhere(command, root):  # target unknowable from here → FAIL-OPEN
            sys.exit(0)
        head = _current_branch(root)
        targets = [t or head for t in targets]

    try:
        import yaml

        data = yaml.safe_load(config_path(root).read_text(encoding="utf-8")) or {}
        branches = data.get("branches") or {}
    except Exception:
        branches = {}

    strategy = load_merge_strategy(tiers_path(root))
    # Every merge the command runs, not only the first: one the policy accepts in front
    # of another left the rest unjudged, and this verdict may not fail open.
    for (_start, flags, source), target in zip(merges, targets):
        if not target:  # detached HEAD → FAIL-OPEN
            continue
        rule = match_merge_rule(strategy, source, target, branches)
        if rule is None:
            continue

        required = rule.get("require")
        if required and required not in flags:
            print(
                f"머지 전략 위반 — '{rule.get('source')}' → '{target}' 는 "
                f"{required} 가 필요합니다. "
                f"절차는 harness-tier rules/merge-strategy.md 를 따르세요.",
                file=sys.stderr,
            )
            sys.exit(BLOCK_EXIT_CODE)

        forbidden = rule.get("forbid")
        if forbidden and forbidden in flags:
            print(
                f"머지 전략 위반 — '{rule.get('source')}' → '{target}' 에는 "
                f"{forbidden} 를 쓰지 않습니다. "
                f"절차는 harness-tier rules/merge-strategy.md 를 따르세요.",
                file=sys.stderr,
            )
            sys.exit(BLOCK_EXIT_CODE)

        if rule.get("warn_unless_rebased") and not _is_rebased(root, source, target):
            print(
                f"[경고] 머지 전략: '{rule.get('source')}' → '{target}' 는 "
                f"rebase 선행이 요구됩니다. "
                f"'{source}' 가 '{target}' 위에 rebase되어 있지 않은 것으로 보입니다"
                f"(origin ref 가 낡았다면 무시하세요).",
                file=sys.stderr,
            )

    sys.exit(0)


def policy_parseable(tiers_path: Path) -> bool:
    """Whether flow-tiers.yaml loads correctly and has a tiers section (policy reliability).

    The unclassified fail-closed block must be applied only when the gate is *working normally*
    (Invariant #1: a broken/absent policy must not permanently block commits). A missing file·parse
    failure·empty tiers are all treated as "unreliable" → False — falling back to FAIL-OPEN
    instead of blocking.
    """
    if not tiers_path.is_file():
        return False
    try:
        import yaml

        data = yaml.safe_load(tiers_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return False
    return bool(data.get("tiers"))


def config_intact(config_path: Path) -> bool:
    """Whether flow-config.yaml is absent (normal) or loads correctly.

    Absence is normal (config may not exist during feature work·before flow-init) → True.
    If it exists but fails to parse, that is an internal error → False: since lifecycle
    (staging/release) determination is disabled, blocking is withheld so promotion commits
    are not wrongly blocked as "unclassified".
    """
    if not config_path.is_file():
        return True
    try:
        import yaml

        yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return True


def missing_gates(flow_dir: Path, gates: list[str]) -> list[str]:
    """Gates without a <gate>.done file, excluding RUNTIME_GATES (gates the hook runs directly)."""
    return [g for g in gates if g not in RUNTIME_GATES and not (flow_dir / f"{g}.done").is_file()]


def _current_branch(root: Path) -> str | None:
    """Return the current git branch name. None on failure."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return None


def _resolve_context_tier(root: Path, flow: Path, current: str | None) -> tuple[str | None, bool]:
    """Resolve the tier label to apply from the current branch/.flow tier marker.

    Returns ``(tier, is_lifecycle)``:
    - A lifecycle branch (stage/main) → that tier and ``True``.
    - A ``.flow/tier`` marker present and applicable to the current branch → that tier, ``False``.
    - Unclassified (no marker)·a marker for a different branch → ``(None, False)``.

    The single tier-resolution point shared by the stage-1 evidence check (main) and the
    stage-2 module pre-check (module_commands) (no duplicate definitions — rule-dry-constants).
    """
    lifecycle = load_lifecycle_branches(config_path(root)).get(current or "")
    if lifecycle:
        return lifecycle, True
    tier_file = flow / "tier"
    if not tier_file.is_file():
        return None, False
    tier, _, branch = tier_file.read_text(encoding="utf-8").strip().partition(":")
    tier, branch = tier.strip().lower(), branch.strip()
    if branch and current is not None and current != branch:
        return None, False
    return tier, False


def tiers_path(root: Path) -> Path:
    """Resolve the location of flow-tiers.yaml (the plugin policy).

    The policy file is deployed to the host alongside the gate scripts, so it is searched in order:
    1. ``CLAUDE_PLUGIN_ROOT/flow-tiers.yaml`` — when run directly as a plugin hook.
    2. ``flow-tiers.yaml`` in the config directory — when copied to
       ``.claude/harness-tier/config/`` (the gate script is in the sibling ``scripts/``,
       so it points at that sibling directory's config/ relative to __file__ — unaffected
       by host_root() instability).
    3. ``flow-tiers.yaml`` under ``root``'s ``.claude/harness-tier/config/`` — same host
       layout as step 2, resolved via ``root`` instead of ``__file__`` (covers callers where
       the module is imported rather than executed in place, e.g. tests).
    4. ``flow-tiers.yaml`` at the host root — fallback (development/testing).
    """
    plugin = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin and (p := Path(plugin) / TIERS_FILENAME).is_file():
        return p
    config_copy = Path(__file__).resolve().parent.parent / Path(CONFIG_DIR).name / TIERS_FILENAME
    if config_copy.is_file():
        return config_copy
    host_config_copy = config_path(root).parent / TIERS_FILENAME
    if host_config_copy.is_file():
        return host_config_copy
    return root / TIERS_FILENAME


def _changed_files(root: Path) -> list[str]:
    """List of changed files to be committed. staged (--cached) first, and if empty falls back to
    the working tree (HEAD diff) (the `git commit -a` case). git failure/no changes → []
    (FAIL-OPEN)."""
    for args in (["diff", "--cached", "--name-only"], ["diff", "HEAD", "--name-only"]):
        try:
            out = subprocess.run(
                ["git", *args],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
        except Exception:
            continue
        files = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
        if files:
            return files
    return []


def _match_modules(changed: list[str], modules: list[dict]) -> tuple[list[dict], list[str]]:
    """Prefix-match changed files against modules[].path.

    Returns ``(matched modules (order preserved·deduped), uncovered files)``. An empty path("")
    matches everything (single-stack single-module). A file is attributed to the first matching
    module; if it matches no path it is uncovered.
    """
    matched: list[dict] = []
    seen: set[str] = set()
    uncovered: list[str] = []
    for f in changed:
        hit: dict | None = None
        for mod in modules:
            path = str(mod.get("path") or "")
            if path == "" or f.startswith(path):
                hit = mod
                break
        if hit is None:
            uncovered.append(f)
            continue
        key = str(hit.get("name") or hit.get("path") or "")
        if key not in seen:
            seen.add(key)
            matched.append(hit)
    return matched, uncovered


_TIMINGS = ("every-commit", "promotion")


def _default_timing(key: str) -> str:
    """Timing for a check that does not declare `when`.

    Back-compat: the reserved key ``security`` keeps its historical promotion timing; every
    other key defaults to every-commit (the historical non-security path).
    """
    return "promotion" if key == "security" else "every-commit"


def _parse_check(key: str, val: object) -> tuple[str | None, str, str | None]:
    """Parse one ``checks`` entry → ``(command|None, timing, warning|None)``. Pure (no I/O).

    A value is either a plain string (command) or an extended dict ``{run, when}``:
      - string/scalar → key-name default timing.
      - dict → ``when`` if it is a known timing, else FAIL-SAFE ``every-commit`` (bias to safety:
        run MORE often, never silently less) plus a warning surfaced on stderr. ``run`` missing
        or empty → command None (skipped). Runtime stays FAIL-OPEN (Invariant #1); strict
        validation of ``when`` is /flow-init's job.

    Field name is ``when`` (not ``on``): YAML 1.1 parses a bare ``on`` key as the boolean
    ``True``, so ``on:`` would never be read back as expected.
    """
    if isinstance(val, dict):
        run = val.get("run")
        cmd = str(run) if run else None
        when = val.get("when")
        if when in _TIMINGS:
            return cmd, str(when), None
        if when is None:
            return cmd, _default_timing(key), None
        return (
            cmd,
            "every-commit",
            f"checks['{key}'].when='{when}' 알 수 없음 → every-commit 로 처리 "
            f"(허용값: {', '.join(_TIMINGS)})",
        )
    return (str(val) if val else None, _default_timing(key), None)


def _check_cmds(mod: dict, *, promotion: bool) -> tuple[list[str], list[str]]:
    """Module checks for the given timing → ``(commands, warnings)``.

    ``promotion=False`` → every-commit checks (changed modules); ``True`` → promotion checks
    (all modules). Each entry is a plain string or an extended ``{run, when}`` dict (see
    :func:`_parse_check`). Config authoring order preserved; empty commands skipped. Warnings are
    prefixed with the module name so the same typo in two modules stays two distinct lines.
    """
    checks = mod.get("checks") or {}
    name = str(mod.get("name") or mod.get("path") or "?")
    want = "promotion" if promotion else "every-commit"
    cmds: list[str] = []
    warns: list[str] = []
    for key, val in checks.items():
        cmd, timing, warn = _parse_check(key, val)
        if warn:
            warns.append(f"[{name}] {warn}")
        if cmd and timing == want:
            cmds.append(cmd)
    return cmds, warns


def wiki_gate(root: Path, gates: list[str] | None) -> bool:
    """Run the wiki runtime gate in-process. True = block, False = allow.

    Deliberately NOT routed through module_commands. That channel's contract is "any nonzero
    exit means the check failed", which a runtime gate cannot honour: a lost script, a broken
    interpreter or an OOM kill would then block every commit in the repo, and the wiki gate is
    none of Invariant #1's three fail-closed exceptions. Here only cmd_verify's own verdict
    blocks; everything else — no wiki, wiki not in this tier's gates, wiki_graph.py absent from
    a half-copied install (cmd_verify is None), any exception — allows.

    Running it in-process rather than as an emitted command string also removes the whole class
    of quoting/interpreter bugs that came with `bash -c`: no sys.executable frozen into a string
    whose interpreter may be gone by the time the shell runs it, and no shell tokenization of
    Windows paths.
    """
    if not gates or "wiki" not in gates or cmd_verify is None:
        return False
    try:
        # No load_wiki_config guard here: cmd_verify already returns 0 when there is no wiki,
        # and pre-checking would parse flow-config.yaml a second time on every commit.
        return cmd_verify(root) != 0
    except Exception:
        return False  # FAIL-OPEN — Invariant #1


def _rel(root: Path, path: Path) -> str:
    """Root-relative posix path. A basename cannot say WHICH SKILL.md."""
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except (ValueError, OSError):
        return path.name


def doc_style_gate(root: Path, gates: list[str] | None) -> str | None:
    """Lint the prose of the files this commit changes. Report text, or None when clean.

    Warns, never blocks. The verdict belongs to CI (`doc-style.yml`), which sees the whole
    tree; here a rule tightening would otherwise deny commits nobody could predict. Anything
    uncertain — gate off, config off, doc_style_check.py absent, any exception — reports
    nothing (Invariant #1).

    Scope comes from ``doc_style_check.in_scope``, the same reader CI's ``--lint-config``
    uses, so the ``paths``/``exclude`` a consumer wrote governs both arms.
    """
    if not gates or "doc-style" not in gates or lint_paths is None:
        return None
    try:
        paths = [root / f for f in _changed_files(root)]
        items = lint_paths(in_scope(root, [path for path in paths if path.is_file()]))
    except Exception:
        return None
    lines = [
        f"{_rel(root, path)}:{lineno}: {code}: {message}"
        for path, findings in items
        for severity, lineno, code, message in findings
        if severity == "error"
    ]
    if not lines:
        return None
    head = "\n".join(lines[:20])
    more = f"\n... {len(lines) - 20} more" if len(lines) > 20 else ""
    return f"문체 규율 위반 (harness-tier rules/doc-style.md)\n{head}{more}"


def module_commands(
    root: Path, tier: str | None, gates: list[str] | None
) -> tuple[list[str], list[str]]:
    """Build module pre-check commands only for the items enabled in the gates list (tiers.yaml
    gates is the SSOT — not hardcoded by tier label. Removing it from gates turns that check off).

    - docs/None tier, or empty gates → ([], []) — no module pre-check applies.
    - "precommit" in gates → the changed modules' every-commit checks (+ uncovered report)
    - "security-scan" in gates → all modules' promotion checks (on promotion)
    The "wiki" and "doc-style" gates are NOT here: they are runtime gates with a different
    error contract, run in main()'s own process by :func:`_runtime_notices`. This channel
    reads any nonzero exit as "the check failed", which would turn their internal errors
    into blocked commits.
    Each check is a plain command string or an extended ``{run, when}`` dict routed by timing
    (see :func:`_parse_check`); unknown ``when`` warnings ride the report (deduped).
    config parse failure·absent modules → ([], []) (FAIL-OPEN — Invariant #1)."""
    if tier is None or tier == "docs" or not gates:
        return [], []
    cfg = config_path(root)
    if not cfg.is_file():
        return [], []
    try:
        import yaml

        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except Exception:
        return [], []
    modules = data.get("modules") or []
    if not modules:
        return [], []
    cmds: list[str] = []
    report: list[str] = []
    warns: list[str] = []
    if "precommit" in gates:
        matched, uncovered = _match_modules(_changed_files(root), modules)
        for mod in matched:
            c, w = _check_cmds(mod, promotion=False)
            cmds += c
            warns += w
        if uncovered:
            report.append(
                "다음 파일은 모듈 미커버라 사전검사 생략 — 새 모듈이면 "
                "flow-config.modules[] 에 등록하세요:"
            )
            report += [f"  - {f}" for f in uncovered]
    if "security-scan" in gates:
        for mod in modules:
            c, w = _check_cmds(mod, promotion=True)
            cmds += c
            warns += w
    # de-dup warnings (a module can appear in both passes), order-preserving; warnings lead so
    # they are visible above the uncovered report on stderr.
    seen: set[str] = set()
    deduped = [w for w in warns if not (w in seen or seen.add(w))]
    return cmds, deduped + report


def main() -> None:
    """flow gate check entry point. exit(BLOCK_EXIT_CODE) if a gate is unmet, exit(0) if passed."""
    force_utf8_io()
    root = host_root()
    # All host-side harness-tier artifacts are collected under .claude/harness-tier/
    # (config·evidence·copied scripts). Path assembly is unified via shared helpers.
    flow = flow_dir(root)
    tiers = tiers_path(root)
    current = _current_branch(root)

    tier, is_lifecycle = _resolve_context_tier(root, flow, current)
    if tier is None:
        # Split unresolved tier into two causes (the same None is interpreted oppositely):
        #  - Policy (flow-tiers.yaml)·config (flow-config.yaml) working normally + the tier marker
        #    file itself absent = flow not entered (unclassified) → FAIL-CLOSED block. Prevents a
        #    commit that bypassed flow from skipping the gate entirely. If enforcement is
        #    unnecessary the user can remove the gate itself with /flow-uninstall (we don't put an
        #    escape hatch in the code — if we did, the model could use that bypass on its own).
        #  - Policy absent/parse failure, config parse failure (uncertain
        #    install/environment·internal error), or a marker for a different branch (branch-bound
        #    stale) → FAIL-OPEN. Preserves Invariant #1 (a broken/absent gate must not permanently
        #    block commits)·branch-bound (a stale marker must not block unrelated branch work). The
        #    criterion is "works reliably", not "file exists".
        if (
            policy_parseable(tiers)
            and config_intact(config_path(root))
            and not (flow / "tier").is_file()
        ):
            print(
                "flow 미진입: 분류되지 않은 커밋입니다. /flow 로 작업을 분류한 뒤 "
                "커밋하세요(강제가 불필요하면 /flow-uninstall)."
            )
            sys.exit(BLOCK_EXIT_CODE)
        sys.exit(0)
    gates = required_gates(tiers, tier)
    if gates is None:  # unknown tier → FAIL-OPEN
        sys.exit(0)
    miss = missing_gates(flow, gates)
    if miss:
        if is_lifecycle:
            print(f"{tier} 게이트 (브랜치 '{current}'): {miss} 증거가 필요합니다.")
        else:
            print(f"flow 게이트: '{tier}' 티어는 {miss} 증거가 필요합니다.")
        sys.exit(BLOCK_EXIT_CODE)
    # Runtime gates ride this process: the tier is resolved once, and a second spawn
    # would resolve it again.
    _runtime_notices(root, gates)
    sys.exit(0)


def module_commands_output() -> None:
    """Emit the module pre-check commands enabled by the current tier's gates to stdout
    (line by line), and the uncovered report to stderr.

    If gates has precommit → changed modules' every-commit checks; if security-scan → + all
    modules' promotion checks (the tiers.yaml gates list is the SSOT — removing it turns that
    bucket off).
    Determination failure → empty output (FAIL-OPEN). precommit-runner.sh runs the stdout commands
    and exposes the stderr report to the user as-is."""
    force_utf8_io()
    root = host_root()
    try:
        tier, _ = _resolve_context_tier(root, flow_dir(root), _current_branch(root))
        gates = required_gates(tiers_path(root), tier) if tier else None
    except Exception:
        return  # FAIL-OPEN
    cmds, report = module_commands(root, tier, gates)
    for line in report:
        print(line, file=sys.stderr)
    for cmd in cmds:
        print(cmd)


def _wiki_stage(root: Path, gates: list[str] | None) -> str | None:
    """The wiki gate as main()'s final stage. Everything it has to say goes to STDOUT.

    Two reasons stdout rather than stderr, both from the hooks contract:

    - ``python3 <missing file>`` exits 2 with its complaint on stderr, exactly the shape of a
      block. A host whose flow_gate_check.py copy is missing would then deny every commit with
      an interpreter error as the reason. precommit-runner.sh therefore reads stdout only,
      which the interpreter never writes to, so that collision cannot fail closed.
    - At exit 0 a hook's stdout AND stderr both go to the debug log only, so the graph's
      quality warnings would never reach a human. They come back here as a ``systemMessage``
      JSON payload — the documented field for "warning shown to the user" — which the runner
      emits verbatim when it allows the commit.

    ``HARNESS_PRECOMMIT_DRYRUN=1`` skips entirely — the runner's old stage-2 guard, kept
    behind the env var so a dry run never pays (or fires) the graph walk.
    """
    if os.environ.get("HARNESS_PRECOMMIT_DRYRUN") == "1":
        return None
    captured = io.StringIO()
    with contextlib.redirect_stderr(captured):
        blocked = wiki_gate(root, gates)
    text = captured.getvalue().strip()
    if blocked:
        if text:
            print(text)  # the deny reason precommit-runner.sh hands to deny()
        sys.exit(BLOCK_EXIT_CODE)
    return f"wiki graph 경고\n{text}" if text else None


def _runtime_notices(root: Path, gates: list[str] | None) -> None:
    """Run the runtime gates that ride main(), then emit their notices as ONE payload.

    precommit-runner.sh echoes this stdout verbatim on a passing commit, and a second JSON
    object on the same stream would not parse.

    ``HARNESS_PRECOMMIT_DRYRUN=1`` skips every stage here, not only the wiki one: a dry run
    prints the commands it would issue and writes nothing else to stdout.
    """
    if os.environ.get("HARNESS_PRECOMMIT_DRYRUN") == "1":
        return
    notes = [note for note in (_wiki_stage(root, gates), doc_style_gate(root, gates)) if note]
    if notes:
        print(json.dumps({"systemMessage": "\n\n".join(notes)}, ensure_ascii=False))


def wiki_check_output() -> None:
    """Compat alias for the absorbed wiki stage (`--wiki-check`), old contract intact.

    The runner no longer calls this — main() runs the wiki gate in-process — but a
    half-copied host can hold an older precommit-runner.sh that still does, and answering
    it here costs one dispatch branch.
    """
    force_utf8_io()
    root = host_root()
    try:
        tier, _ = _resolve_context_tier(root, flow_dir(root), _current_branch(root))
        gates = required_gates(tiers_path(root), tier) if tier else None
    except Exception:
        return  # FAIL-OPEN
    note = _wiki_stage(root, gates)
    if note:
        print(json.dumps({"systemMessage": note}, ensure_ascii=False))


def classify_output() -> None:
    """Print what the hook's command IS — the gate's single authority on that question.

    precommit-runner.sh decides only whether to spawn this at all, and its filter is coarse so
    that it cannot be narrower. The grammar lives in one place — the same functions that read
    the command for every other purpose — so nothing can disagree with it about what a `git`
    invocation is.

    ``ok=1`` comes first and says the command was READ. Without it the runner cannot tell
    a verdict of `neither` from no verdict at all, and a python too old to run this would
    turn the gate off instead of tripping the dependency deny below it.
    The rest are printed only when true, so an older runner sees nothing it must not act on:
      ``commit=1`` / ``merge=1`` — the command holds that invocation.
      ``worktree=<path>`` — the commit runs in a git worktree other than main, detected by
      branch-key (:func:`working_root`), which re-points ROOT.
      ``unresolved=1`` — the command commits in a tree this cannot name, so main's cleanliness
      says nothing about it and the runner must not read a clean main as nothing to gate.
    Any failure prints less, never more: an unreadable command is not an invocation this can
    gate, and an undetectable worktree leaves ROOT on main (Invariant #1 · #6, FAIL-OPEN).
    Invariant #2: force_utf8_io before any print.
    """
    force_utf8_io()
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        return  # FAIL-OPEN → neither, and the runner stops
    tool_input = payload.get("tool_input")
    command = tool_input.get("command") if isinstance(tool_input, dict) else None
    if not isinstance(command, str):
        # No command to read, so there is no verdict to give. Answering `ok=1` here would say
        # "read it, not a commit", and the runner takes that as leave — dropping the raw-stdin
        # backstop that is all it has left when the payload is not the shape the tool sends.
        return
    try:
        is_commit = is_invocation(command, "commit")
        is_merge = is_invocation(command, "merge") or bool(parse_pull_commands(command))
    except Exception:
        return  # FAIL-OPEN
    print("ok=1")
    if is_commit:
        print("commit=1")
    if is_merge:
        print("merge=1")
    if not is_commit:  # only the commit path re-designates the worktree (Invariant #6)
        return
    # Said whether or not a worktree line follows. `working_root` can still reach one from the
    # hook's own cwd after the command itself gave no answer, and that tree is a guess about
    # where the commit lands, not a reading of it — so the runner needs this either way: the
    # tree it ends up on may be clean while the commit runs somewhere else entirely.
    if commit_tree_unresolved(command):
        print("unresolved=1")
    root = host_root()
    try:
        w = working_root(
            project_dir=root, hook_cwd=payload.get("cwd") or None, command=command or None
        )
    except Exception:
        return  # FAIL-OPEN → no re-designation
    if w and w.resolve() != root.resolve():
        print(f"worktree={w}")


if __name__ == "__main__":
    try:
        if "--module-commands" in sys.argv:
            module_commands_output()
        elif "--classify" in sys.argv:
            classify_output()
        elif "--resolve-worktree" in sys.argv:
            pass  # the name --classify replaced; a host mid-sync must get a no-op, not main()
        elif "--wiki-check" in sys.argv:
            wiki_check_output()
        elif "--merge-check" in sys.argv:
            merge_check_output()
        else:
            main()
    except SystemExit:
        raise
    except Exception as exc:  # FAIL-OPEN
        print(f"[flow-gate] unexpected error, allowing: {exc}", file=sys.stderr)
        sys.exit(0)
