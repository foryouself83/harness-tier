"""flow-config-based gate check helpers.

The host repository path is accessed only via the CLAUDE_PROJECT_DIR environment
variable, and internal errors do not block the gate (fail-open).
"""

from __future__ import annotations

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
        RELEASE_TIER,
        RUNTIME_GATES,
        STAGING_TIER,
        TIERS_FILENAME,
        config_path,
        flow_dir,
        force_utf8_io,
        host_root,
        working_root,
    )
except ImportError:
    from scripts._harness_paths import (
        _PATH_TOKEN,
        BLOCK_EXIT_CODE,
        CONFIG_DIR,
        RELEASE_TIER,
        RUNTIME_GATES,
        STAGING_TIER,
        TIERS_FILENAME,
        config_path,
        flow_dir,
        force_utf8_io,
        host_root,
        working_root,
    )


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


# `merge` as a whole word — keeps `git merge-base` / `git merge-file` from false-positiving.
# Mirrors the _commit_re convention in precommit-runner.sh.
_MERGE_SPLIT_RE = re.compile(r"(?:^|\s)merge(?=$|[^\w-])")

# Flags that consume the next token as their argument. If not skipped, `-m "msg"` would leak
# the message into the source-branch slot.
# `-S`/`--gpg-sign` are deliberately ABSENT: git takes their keyid *attached* (`-Skeyid`,
# `--gpg-sign=keyid`), never as a separate token, so listing them here would swallow the source
# branch of `git merge -S feature/x` and silently disable the check for signed merges.
_MERGE_FLAGS_WITH_ARG = frozenset(
    {
        "-m",
        "--message",
        "-F",
        "--file",
        "-s",
        "--strategy",
        "-X",
        "--strategy-option",
    }
)

# A `git switch` / `git checkout` INVOCATION that precedes the merge in the SAME command.
# risk-tiers' "Merging feature/* → integration" prescribes a three-step block
# (`git switch <integration>` → `git pull --ff-only` → `git merge --squash feature/<name>`) that
# Claude Code sends as ONE Bash call, so at hook time HEAD is still the SOURCE branch and no rule
# would match — the very idiom the policy documents would bypass the gate.
# The operands are deliberately NOT part of this pattern: the invocation must be *seen* even when
# its operands are unreadable, because an unreadable one voids the whole chain
# (see :func:`_target_from_command`). `git\s+` also anchors the global-options region, so a
# `checkout`-looking word elsewhere in the command cannot start a match.
_MERGE_SWITCH_RE = re.compile(
    r"(?:^|[\s;&|])git\s+(?:-\S+\s+(?:\S+\s+)?)*(?:switch|checkout)(?=$|\s)"
)

# Where one command in a chain ends and the next begins — used to cut a switch/checkout's operand
# region so the next command's words are not read as its operands.
# A NEWLINE separates two commands exactly as `&&` does, and omitting it is not a narrow miss: the
# operand region then runs past the end of the line and swallows the next command's words, so
# `_switch_operand`'s "exactly one operand" test fails, one unclear switch voids the whole chain,
# and every newline-separated merge falls back to HEAD — i.e. walks through the gate. risk-tiers'
# own "Merging feature/* → integration" block is three newline-separated lines, so the shape the
# policy documents is precisely the shape that would bypass it. `\r` covers CRLF.
_SHELL_SEP_RE = re.compile(r"[;&|\n\r]")

# `git -C <dir>` in the global-options region before the `merge` subcommand. `-C` is a directory
# only as git's OWN global option: unanchored, any unrelated `-C` (`grep -C 3`, `gcc -C`, …)
# earlier in the chain resolves to a foreign directory and switches the entire merge gate off.
# Reuses the path-token spec from _harness_paths (quoted or bare) — no second definition of the
# same grammar.
_MERGE_DASH_C_RE = re.compile(rf"(?:^|[\s;&|])git\s+(?:-\S+\s+(?:\S+\s+)?)*-C\s+(?:{_PATH_TOKEN})")

# A leading `cd <dir>` before the merge — the merge path's own separator variant of
# _harness_paths._CD_PREFIX_RE, which recognises `&&` only. `cd <wt>` followed by a NEWLINE (the
# shape a multi-line Bash call actually has) then reads as no cd at all, the merge is judged
# against THIS root, and a flow that is not happening is named in a false block.
# Deliberately NOT fixed by widening the shared regex: the two paths have opposite risk polarity.
# Here a match only ever FAILs OPEN (Invariant #1 — `_points_elsewhere` → exit 0). There the same
# match re-points ROOT to another worktree for status/diff/tier-marker/module-lint, which
# Invariant #6 requires to stay conservative ("any uncertainty → main; never newly block").
# One grammar cannot carry both polarities, so the merge path states its own separators.
_MERGE_CD_PREFIX_RE = re.compile(rf"\s*cd\s+(?:{_PATH_TOKEN})\s*(?:&&|[;\n\r])")


def parse_merge_command(command: str) -> tuple[set[str], str | None]:
    """Extract (flags, source branch) from a `git merge` invocation.

    Only the region *after* the `merge` subcommand is parsed, so `git -C <dir> merge X` never
    mistakes the -C argument for the source (and Windows backslash paths never reach shlex).
    Returns (set(), None) when this is not a merge, when there is no source operand, or on any
    parse failure (FAIL-OPEN — Invariant #1).
    """
    if not command:
        return set(), None
    parts = _MERGE_SPLIT_RE.split(command, maxsplit=1)
    if len(parts) < 2:
        return set(), None
    import shlex

    try:
        tokens = shlex.split(parts[1])
    except ValueError:  # unbalanced quotes → FAIL-OPEN
        return set(), None
    flags: set[str] = set()
    source: str | None = None
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if tok.startswith("-"):
            if tok in _MERGE_FLAGS_WITH_ARG:
                skip_next = True
                continue
            flags.add(tok.split("=", 1)[0])
            continue
        if source is None:
            source = tok
    return flags, source


def _merge_region_head(command: str) -> str:
    """The part of the command *before* the `merge` subcommand (the whole string if not a merge)."""
    return _MERGE_SPLIT_RE.split(command, maxsplit=1)[0]


def _switch_operand(operands: str) -> str | None:
    """The branch a `git switch`/`git checkout` operand region lands HEAD on, else None (unclear).

    Clear means exactly one operand and no flag at all. Every other shape moves HEAD somewhere
    this parser cannot name, so it is unclear rather than "the first bare word":
      - `checkout dev -- a/b.py` restores a FILE from dev; HEAD does not move at all.
      - `switch -c feature/y` / `checkout -b` create and land on a DIFFERENT branch.
      - `checkout origin/dev` lands on a detached HEAD — yet :func:`_branch_matches` strips
        `origin/`, so adopting it would match the integration rules it never entered.
      - `switch -`, `checkout --detach`, unbalanced quotes: unnameable.
    """
    import shlex

    try:
        tokens = shlex.split(operands)
    except ValueError:  # unbalanced quotes → unclear
        return None
    if len(tokens) != 1:
        return None
    branch = tokens[0]
    if branch.startswith("-") or branch.startswith("origin/"):
        return None
    return branch


def _target_from_command(command: str) -> str | None:
    """Branch a preceding `git switch`/`git checkout` moves onto — the merge's real target.

    `git switch dev && git merge feature/x` merges INTO dev, but at hook time HEAD is still
    feature/x. The command states the target explicitly, so it wins over the hook-time branch.

    The rule is "EVERY switch/checkout before the merge must be clear, and then the last one
    wins" — not "the last one that happens to parse". A single unclear invocation anywhere in the
    chain returns None, because it may be the one that actually decides HEAD: in
    `git switch dev && git switch -c feature/y && git merge feature/x` HEAD ends on feature/y,
    which no rule covers, yet picking the last *parseable* switch adopts the stale `dev` and
    blocks a merge the policy never governs. None → the caller falls back to the hook-time branch
    (FAIL-OPEN, Invariant #1 — this direction can only ever block less).
    """
    if not command:
        return None
    head = _merge_region_head(command)
    target: str | None = None
    for m in _MERGE_SWITCH_RE.finditer(head):
        rest = head[m.end() :]
        sep = _SHELL_SEP_RE.search(rest)
        branch = _switch_operand(rest[: sep.start()] if sep else rest)
        if branch is None:  # one unclear switch voids the whole chain
            return None
        target = branch
    return target


def _points_elsewhere(command: str, root: Path) -> bool:
    """Whether the command runs the merge in a directory other than ``root``.

    Two shell forms name an execution directory, and both must be recognised: `git -C <dir> merge
    X` (git's own global option) and a leading `cd <dir> && … git merge X`. Either way the source
    comes from the command while the target would be read from THIS root — a mismatch that has
    produced false blocks naming a flow that has no rule at all. The merge path must not
    re-designate the worktree (Invariant #6), so a foreign directory simply FAILs OPEN
    (Invariant #1). A directory that resolves to ``root`` itself is not foreign and stays
    enforced. Unresolvable path → treated as foreign.

    Relative directories resolve against ``root``, never the process cwd: the merge check runs
    before precommit-runner.sh's `cd "$ROOT"`, so the interpreter's cwd is the hook cwd and
    reading `git -C .` there would call root itself foreign and skip the gate.
    """
    m = _MERGE_DASH_C_RE.search(_merge_region_head(command)) or _MERGE_CD_PREFIX_RE.match(command)
    if not m:
        return False
    cdir = next((g for g in m.groups() if g is not None), None)
    if not cdir:
        return False
    try:
        return Path(root, cdir).resolve() != Path(root).resolve()
    except Exception:
        return True


def _branch_matches(pattern: str, branch: str, branches: dict) -> bool:
    """Whether a branch matches a merge_strategy source/target pattern.

    A pattern containing `/` is a branch-prefix glob (`feature/*` → startswith `feature/`);
    otherwise it is a flow-config.branches key compared against that key's value. The
    `origin/` prefix is stripped from the branch first, so `git merge origin/stage` matches
    the `staging` key. An unknown key never matches (FAIL-OPEN — no rule applies).
    """
    if not pattern or not branch:
        return False
    name = branch[len("origin/") :] if branch.startswith("origin/") else branch
    if "/" in pattern:
        return name.startswith(pattern.rstrip("*"))
    configured = branches.get(pattern)
    return bool(configured) and name == str(configured)


def match_merge_rule(rules: list[dict], source: str, target: str, branches: dict) -> dict | None:
    """Return the first rule whose source and target both match, else None (FAIL-OPEN)."""
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
    flags, source = parse_merge_command(command)
    if not source:
        sys.exit(0)

    root = host_root()
    target = _target_from_command(command)
    if not target:
        if _points_elsewhere(command, root):  # target unknowable from here → FAIL-OPEN
            sys.exit(0)
        target = _current_branch(root)
    if not target:  # detached HEAD → FAIL-OPEN
        sys.exit(0)

    try:
        import yaml

        data = yaml.safe_load(config_path(root).read_text(encoding="utf-8")) or {}
        branches = data.get("branches") or {}
    except Exception:
        branches = {}

    rule = match_merge_rule(load_merge_strategy(tiers_path(root)), source, target, branches)
    if rule is None:
        sys.exit(0)

    required = rule.get("require")
    if required and required not in flags:
        print(
            f"머지 전략 위반 — '{rule.get('source')}' → '{target}' 는 {required} 가 필요합니다. "
            f"절차는 risk-tiers 규칙의 Merge strategy 절을 따르세요.",
            file=sys.stderr,
        )
        sys.exit(BLOCK_EXIT_CODE)

    forbidden = rule.get("forbid")
    if forbidden and forbidden in flags:
        print(
            f"머지 전략 위반 — '{rule.get('source')}' → '{target}' 에는 "
            f"{forbidden} 를 쓰지 않습니다. "
            f"절차는 risk-tiers 규칙의 Merge strategy 절을 따르세요.",
            file=sys.stderr,
        )
        sys.exit(BLOCK_EXIT_CODE)

    if rule.get("warn_unless_rebased") and not _is_rebased(root, source, target):
        print(
            f"[경고] 머지 전략: '{rule.get('source')}' → '{target}' 는 rebase 선행이 요구됩니다. "
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


def module_commands(
    root: Path, tier: str | None, gates: list[str] | None
) -> tuple[list[str], list[str]]:
    """Build module pre-check commands only for the items enabled in the gates list (tiers.yaml
    gates is the SSOT — not hardcoded by tier label. Removing it from gates turns that check off).

    - docs/None tier, or empty gates → ([], [])
    - "precommit" in gates → the changed modules' every-commit checks (+ uncovered report)
    - "security-scan" in gates → all modules' promotion checks (on promotion)
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


def resolve_worktree_output() -> None:
    """Detect the commit's actual worktree from the hook payload and print its path (branch-key).

    Reads the PreToolUse hook JSON on stdin, feeds ``cwd`` and ``tool_input.command`` to
    working_root (against CLAUDE_PROJECT_DIR = main), and prints the detected worktree's absolute
    path to stdout when it differs from main. Empty output otherwise (no worktree / detection
    failure) → precommit-runner.sh keeps ROOT=main (FAIL-OPEN, no re-designation). Invariant #2:
    force_utf8_io before any print."""
    force_utf8_io()
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        payload = {}
    hook_cwd = payload.get("cwd") or None
    command = (payload.get("tool_input") or {}).get("command") or None
    root = host_root()
    try:
        w = working_root(project_dir=root, hook_cwd=hook_cwd, command=command)
    except Exception:
        return  # FAIL-OPEN → empty output
    if w and w.resolve() != root.resolve():
        print(str(w))


if __name__ == "__main__":
    try:
        if "--module-commands" in sys.argv:
            module_commands_output()
        elif "--resolve-worktree" in sys.argv:
            resolve_worktree_output()
        elif "--merge-check" in sys.argv:
            merge_check_output()
        else:
            main()
    except SystemExit:
        raise
    except Exception as exc:  # FAIL-OPEN
        print(f"[flow-gate] unexpected error, allowing: {exc}", file=sys.stderr)
        sys.exit(0)
