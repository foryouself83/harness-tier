#!/usr/bin/env bash
# Claude Code PreToolUse hook — git commit/merge gate (harness-tier).
#
# Inspects the commit in two stages, emitting deny JSON on stdout only when blocking:
#   1) flow gate + wiki runtime gate — flow_gate_check.py (plugin) verifies the required gate
#      evidence for the declared tier / lifecycle branch, then runs the wiki graph verification
#      in the same process when flow-config.wiki is enabled (spawn 2→1; --wiki-check remains a
#      compat alias). If either is unmet: exit 2 + reason → deny.
#   2) module pre-check — every-commit module checks for changed modules (+ promotion checks
#      for all modules on promotion), routed by each check's `when` in flow-config. Config parse
#      failure / no command is FAIL-OPEN (skip); if any fails, deny.
# `git merge` is inspected separately (--merge-check) before both stages above and before the
# `git status` early-exit, since a merge runs on a clean tree by definition. A command that both
# merges and commits (`git merge --squash X && git commit -m …`) gets BOTH checks, in that order.
#
# Path conventions (the plugin is installed outside the host):
#   - host repo root  → CLAUDE_PROJECT_DIR (falls back to git toplevel)
#   - plugin scripts  → CLAUDE_PLUGIN_ROOT/scripts (falls back to this script's location)
#
# Blocking convention: PreToolUse blocking is done via exit 2 + stderr reason (this build
# ignores permissionDecision JSON + exit 0). JSON is emitted too for forward compatibility.
# No changes / checks pass: exit 0 → commit allowed. Transitive internal errors are handled
# as FAIL-OPEN (skip checks, allow commit) so a broken gate does not permanently block commits.
# Absence of required tools like python3/PyYAML is FAIL-CLOSED (block) — to prevent
# the gate from being silently disabled on non-Python teams (re-commit after installing).
#
# Debug: with HARNESS_PRECOMMIT_DRYRUN=1, only prints the test commands that would run, without executing them.
set -uo pipefail

# The Windows hook environment uses a cp1252/cp949 locale, so Python's default I/O is not UTF-8.
# To keep Korean-reason print() / UTF-8 config-file open() from encoding-erroring into FAIL-OPEN,
# force UTF-8 mode on every child python process (inherited).
export PYTHONUTF8=1

deny() {  # $1=reason → block commit (exit 2 is the actual blocking mechanism; JSON is for forward compat)
  # The reason is interpolated into a JSON string, so it must be escaped first. Reasons carry
  # the failing command verbatim, and a module command is arbitrary host text — the wiki gate's
  # own command contains double quotes and, on Windows, backslashes. Unescaped, the `"` closes
  # the JSON string early and `\r`/`\P` are invalid escapes, so the payload is malformed exactly
  # when the gate blocks. Pure bash substitution: python3 is not available on every deny path
  # (the first denies below fire *because* python3 is missing). Order matters — backslash first,
  # else the escapes added afterwards get escaped again; the control-character sweep comes last,
  # so the three characters that have a short escape keep it.
  _deny_json=${1//\\/\\\\}
  _deny_json=${_deny_json//\"/\\\"}
  _deny_json=${_deny_json//$'\n'/\\n}
  _deny_json=${_deny_json//$'\r'/\\r}
  _deny_json=${_deny_json//$'\t'/\\t}
  # JSON forbids every raw character below U+0020, not only those three. The wiki gate quotes a
  # git subject line back into its reason, and a subject is whatever was pasted into it — one
  # stray ESC would malform the payload the same way an unescaped quote does.
  _deny_json=${_deny_json//[[:cntrl:]]/ }
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$_deny_json"
  printf 'harness-tier 게이트 차단: %s\n' "$1" >&2
  exit 2
}

# Read PreToolUse stdin (tool_input JSON) and gate only `git commit`. Rather than relying on the
# settings.json `if` field, the script self-filters directly (avoids per-build `if` behavior differences).
_hook_input="$(timeout 5 cat 2>/dev/null || true)"

# Determine whether this is a commit. If python3 is present, extract tool_input.command exactly. If
# extraction is empty (python3 broken) or python3 itself is absent, fall back to a coarse raw-stdin
# match — to prevent "python3 problem → commit detection fails → gate self-disables" (absence/breakage
# is blocked fail-closed by the dependency check below).
_hook_cmd=""
if command -v python3 >/dev/null 2>&1; then
  _hook_cmd="$(printf '%s' "$_hook_input" | python3 -c "import sys, json
try:
    print((json.load(sys.stdin).get('tool_input') or {}).get('command', ''))
except Exception:
    print('')" 2>/dev/null || true)"
fi
# Coarse pre-filter. The ONLY thing decided here is whether to spawn the gate at all — what the
# command IS gets decided once, in flow_gate_check.py --classify below.
# It must never be narrower than that grammar, which requires the literal `git` and the
# word `commit`/`merge`: a command holding neither cannot be an invocation,
# and everything else is passed on to be judged. So it states no opinion about quoting —
# a second grammar has to agree with the first, and the spellings only one of them accepts
# are the gate off in silence rather than a narrower gate. Over-matching costs one python
# spawn and no verdict; under-matching costs the whole gate.
case "${_hook_cmd:-$_hook_input}" in
  *git*) ;;
  *) exit 0 ;;
esac
# The word is not required to follow a BLANK. The grammar reads a command an interpreter
# runs with its quoting rubbed out, where a quote becomes the separator — so `eval 'git'commit`
# is an invocation to the gate while a blank-anchored filter drops it, and a filter narrower
# than the grammar is the gate off in silence.
_word_re='(commit|merge)($|[^[:alnum:]_-])'
[[ "${_hook_cmd:-$_hook_input}" =~ $_word_re ]] || exit 0

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$ROOT" ] || exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_SCRIPTS="${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/scripts}"
PLUGIN_SCRIPTS="${PLUGIN_SCRIPTS:-$SCRIPT_DIR}"

# The gate's own verdict on the command: whether it commits, whether it merges, and which
# worktree the commit runs in. One spawn, one grammar, one authority — see --classify. A verdict
# that says neither means the coarse filter over-matched and there is nothing to gate. Silence
# (an unreadable payload, a python that died) says the same, which is FAIL-OPEN: this stage may
# never be the thing that newly blocks a command (Invariant #1).
_verdict=''
if command -v python3 >/dev/null 2>&1; then
  _verdict="$(printf '%s' "$_hook_input" | CLAUDE_PROJECT_DIR="$ROOT" \
    python3 "$PLUGIN_SCRIPTS/flow_gate_check.py" --classify 2>/dev/null || true)"
fi
_is_commit=0
_is_merge=0
_answered=0
_wt=""
while IFS= read -r _line; do
  # Python's print() emits CRLF on the Windows hook host and the command substitution eats
  # only the trailing newline, so every line arrives with its CR. A `case` arm compares
  # strings, so one written without it matches nothing at all (Invariant #2).
  _line="${_line%$'\r'}"
  case "$_line" in
    ok=1) _answered=1 ;;
    commit=1) _is_commit=1 ;;
    merge=1) _is_merge=1 ;;
    worktree=?*) _wt="${_line#worktree=}" ;;
  esac
done <<< "$_verdict"
# A verdict of neither ends it here — the pre-filter over-matched and there is nothing to
# gate. This is the ONLY place that decision can be made, and it must come before the
# dependency deny below, or a read-only command that merely says the word is denied on a
# host that has not installed the gate's dependencies yet.
{ [ "$_answered" -eq 1 ] && [ "$_is_commit" -eq 0 ] && [ "$_is_merge" -eq 0 ]; } && exit 0

# Dependency FAIL-CLOSED — the harness requires python3 + PyYAML (regardless of project language).
# If they are missing and we silently pass (fail-open), the gate is disabled on non-Python teams, so
# "absence of required tools" — unlike transitive internal errors — blocks the commit (re-commit after install).
# It runs AFTER the verdict, so a command the gate has already called a non-invocation is
# never denied for a dependency it does not need. Only python3's own absence reaches it
# ahead of a verdict — nothing can classify without it, and on that host every real commit
# is blocked anyway.
#
# DRY exception (intentional duplication): the floor(3, 8) / PyYAML install command in the bootstrap
# check below are the same values as check-deps.sh, yet the code cannot be shared — (1) it directly
# verifies the bare python3 the gate invokes, so moving it into a python helper (_harness_paths) would be
# circular, and (2) this script being self-contained is an Invariant (an external source failure would
# FAIL-OPEN and disable the gate), so it cannot even be shared across shells. So the value SSOT lives in
# check-deps.sh and the floor / install command here are kept in sync with it (changing only one side
# makes the pre-check and the blocking criteria diverge).
if ! command -v python3 >/dev/null 2>&1; then
  deny "게이트에 python3 가 필요합니다. 설치 후 다시 커밋하세요(불가하면 settings.json 의 게이트 훅을 제거)."
fi
# floor = python 3.8 (SSOT: check-deps.sh — sync both sides when changing)
if ! python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" >/dev/null 2>&1; then
  deny "게이트에 python 3.8+ 가 필요합니다(현재 버전 미만). 업그레이드 후 다시 커밋하세요."
fi
# PyYAML install command = kept as the same string as check-deps.sh
if ! python3 -c "import yaml" >/dev/null 2>&1; then
  deny "게이트에 PyYAML 이 필요합니다. python3 -m pip install pyyaml 후 다시 커밋하세요(점검: .claude/harness-tier/scripts/check-deps.sh)."
fi

# No verdict at all — python3 is present and its dependencies are installed, so the gate
# script itself failed to answer. Gate the command rather than drop it: an unreadable hook
# payload is the one case the raw-stdin filter above still has to carry, and the stages
# below each fail open on their own if the script is genuinely broken.
if [ "$_answered" -ne 1 ]; then
  _is_commit=1
  # The merge check is entered too: it is reached only through `_is_merge`, and a
  # merge-strategy violation is one of the three things this gate may never fail open
  # on. It is guarded on the script EXISTING because, alone among the stages, it
  # reads stderr for its reason — and `python3 <missing file>` writes the
  # interpreter's own complaint there and exits 2, which a half-copied host would
  # then serve as a merge verdict on every commit.
  [ -f "$PLUGIN_SCRIPTS/flow_gate_check.py" ] && _is_merge=1
fi

# merge gate — a merge runs on a clean tree, so it must be inspected before the `git status`
# early-exit below, and before the worktree re-designation (Invariant #6: the merge path is
# resolved against CLAUDE_PROJECT_DIR only). Uses neither .done markers nor module checks (the
# commit gate already vetted the content being moved).
# The merge check is NOT exclusive with the commit check: `git merge X && git commit -m …` is the
# canonical squash-merge idiom, and gating it as "a commit" alone would skip the merge verdict
# entirely (and then early-exit on the clean tree). So a merge is always inspected FIRST, and a
# command that also commits falls through to the commit path below — both checks apply.
if [ "$_is_merge" -eq 1 ]; then
  merge_reason="$(printf '%s' "$_hook_input" | CLAUDE_PROJECT_DIR="$ROOT" \
    python3 "$PLUGIN_SCRIPTS/flow_gate_check.py" --merge-check 2>&1 >/dev/null)"
  merge_rc=$?
  if [ "$merge_rc" -eq 2 ] && [ -n "$merge_reason" ]; then
    deny "$merge_reason"
  fi
  # A warning is what a check that RAN has to say. Anything on this channel after a
  # non-zero exit is the interpreter's, not the gate's, and reads as a verdict.
  [ "$merge_rc" -eq 0 ] && [ -n "$merge_reason" ] && printf '%s\n' "$merge_reason" >&2
  [ "$_is_commit" -eq 1 ] || exit 0
fi

# worktree-aware ROOT re-designation (FAIL-OPEN, commit-only — Invariant #6: the merge path must
# not re-designate, which is why the merge gate above ran first, against CLAUDE_PROJECT_DIR).
# CLAUDE_PROJECT_DIR is fixed at session start, so a commit run in a git worktree created inside
# that session (e.g. `git -C <wt> commit`) would otherwise be gated against main (staged diff
# invisible · branch-bound tier marker mismatch · relative module-lint misses worktree files).
# --classify above detected it by branch-key; an empty answer keeps ROOT on main.
if [ -n "$_wt" ] && [ -d "$_wt" ]; then
  ROOT="$_wt"
fi

cd "$ROOT" || exit 0

status="$(git status --porcelain 2>/dev/null)" || exit 0
[ -z "$status" ] && exit 0

# 1) flow gate + the runtime gates (wiki, doc-style) — ONE process. flow_gate_check.py reads
#    the host root from CLAUDE_PROJECT_DIR and FAIL-OPENs (exit 0) on internal error; after
#    the flow verdict it runs those gates in the same interpreter (tier resolved once, spawn
#    2→1 — --wiki-check survives as a compat alias only). exit 2 + stdout reason → deny, any
#    gate. They stay OUT of the module commands below: that channel reads any nonzero exit as
#    "the check failed", while a runtime gate must fail OPEN on anything that is not a real
#    verdict (Invariant #1 — neither is one of the three fail-closed exceptions). stdout-only
#    is load-bearing: `python3 <missing file>` ALSO exits 2, with its complaint on stderr, so
#    reading stderr here would turn a half-copied install into a repo-wide block. At exit 0 a
#    non-empty stdout is their combined systemMessage JSON — ONE object, held until the commit
#    is allowed (a hook's stdout and stderr both go to the debug log at exit 0 —
#    systemMessage is the documented field for a warning the user does see).
#    HARNESS_PRECOMMIT_DRYRUN is consumed inside the script (the notice stages skip).
flow_reason="$(CLAUDE_PROJECT_DIR="$ROOT" python3 "$PLUGIN_SCRIPTS/flow_gate_check.py" 2>/dev/null)"
flow_rc=$?
if [ "$flow_rc" -eq 2 ] && [ -n "$flow_reason" ]; then
  deny "$flow_reason"
fi
[ "$flow_rc" -eq 0 ] && gate_note="$flow_reason"

allow() {  # emit any held non-blocking notice, then let the commit through
  [ -n "${gate_note:-}" ] && printf '%s\n' "$gate_note"
  exit 0
}

# 2) module pre-check. Per tier, runs the every-commit checks of the changed modules
#    (+ all-module promotion checks on promotion). Commands arrive on stdout, the uncovered report
#    on stderr (uncaptured — but note that a hook's stderr only reaches the user when the hook
#    exits non-zero, so this report is visible only alongside a deny). On config parse failure /
#    no command: FAIL-OPEN (skip). If any one fails, deny.
mod_cmds="$(CLAUDE_PROJECT_DIR="$ROOT" python3 "$PLUGIN_SCRIPTS/flow_gate_check.py" --module-commands)"
[ -n "$mod_cmds" ] || allow

if [ "${HARNESS_PRECOMMIT_DRYRUN:-0}" = "1" ]; then
  echo "DRYRUN: 모듈 사전검사 명령 →" 1>&2
  printf '%s\n' "$mod_cmds" 1>&2
  allow
fi

LOG_DIR="${TMPDIR:-/tmp}"
mod_log="$LOG_DIR/harness-tier-precommit-module.log"
while IFS= read -r mod_cmd; do
  [ -n "$mod_cmd" ] || continue
  echo "▶ 모듈 사전검사 실행: $mod_cmd …" 1>&2
  if ! bash -c "$mod_cmd" > "$mod_log" 2>&1; then
    cat "$mod_log" 1>&2
    deny "모듈 사전검사 실패: $mod_cmd. 위 출력을 확인해 수정한 뒤 다시 커밋하세요."
  fi
done <<< "$mod_cmds"

allow
