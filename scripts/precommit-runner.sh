#!/usr/bin/env bash
# Claude Code PreToolUse hook — git commit/merge gate (harness-tier).
#
# Inspects the commit in two stages, emitting deny JSON on stdout only when blocking:
#   1) flow gate — flow_gate_check.py (plugin) verifies the required gate evidence for
#      the declared tier / lifecycle branch. If unmet: exit 2 + reason → deny.
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
# However, absence of required tools like python3/PyYAML is FAIL-CLOSED (block) — to prevent
# the gate from being silently disabled on non-Python teams (re-commit after installing).
#
# Debug: with HARNESS_PRECOMMIT_DRYRUN=1, only prints the test commands that would run, without executing them.
set -uo pipefail

# The Windows hook environment uses a cp1252/cp949 locale, so Python's default I/O is not UTF-8.
# To keep Korean-reason print() / UTF-8 config-file open() from encoding-erroring into FAIL-OPEN,
# force UTF-8 mode on every child python process (inherited).
export PYTHONUTF8=1

deny() {  # $1=reason → block commit (exit 2 is the actual blocking mechanism; JSON is for forward compat)
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$1"
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
# Detect a `git commit` invocation, allowing git global options between `git` and the `commit`
# subcommand — critically `git -C <worktree> commit` (the /flow worktree-commit convention, the
# deterministic worktree-detection signal) and `git -c k=v commit`. A plain `*"git commit"*`
# substring MISSES `git -C <wt> commit`, so the worktree commit would slip past the filter as
# "not a commit" and bypass the gate entirely (silent neutralization — Invariant #1). `commit` is
# matched as a whole word so `git commit-graph`/`git commit-tree` etc. do not false-positive. When
# python extraction is empty (python3 broken/absent) the same regex scans the raw JSON. The
# terminator allows any non-alnum/non-`-` char after `commit` (space, `;`, `&`, …) so `git commit;`
# is caught too, while `-`/alnum keep `commit-graph`/`commitfoo` excluded.
_commit_re='git([[:space:]]+-[^[:space:]]+([[:space:]]+[^[:space:]]+)?)*[[:space:]]+commit($|[^[:alnum:]-])'

# Detect `git merge` with the same convention as _commit_re: git global options (notably
# `git -C <worktree>`) may sit between `git` and the subcommand, and `merge` is matched as a
# whole word so `git merge-base` / `git merge-file` do not false-positive.
_merge_re='git([[:space:]]+-[^[:space:]]+([[:space:]]+[^[:space:]]+)?)*[[:space:]]+merge($|[^[:alnum:]-])'

_is_commit=0
_is_merge=0
[[ "${_hook_cmd:-$_hook_input}" =~ $_commit_re ]] && _is_commit=1
[[ "${_hook_cmd:-$_hook_input}" =~ $_merge_re ]] && _is_merge=1
[ "$_is_commit" -eq 1 ] || [ "$_is_merge" -eq 1 ] || exit 0

# Dependency FAIL-CLOSED — the harness requires python3 + PyYAML (regardless of project language).
# If they are missing and we silently pass (fail-open), the gate is disabled on non-Python teams, so
# "absence of required tools" — unlike transitive internal errors — blocks the commit (re-commit after install).
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

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$ROOT" ] || exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_SCRIPTS="${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/scripts}"
PLUGIN_SCRIPTS="${PLUGIN_SCRIPTS:-$SCRIPT_DIR}"

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
  [ -n "$merge_reason" ] && printf '%s\n' "$merge_reason" >&2   # warning passthrough
  [ "$_is_commit" -eq 1 ] || exit 0
fi

# worktree-aware ROOT re-designation (FAIL-OPEN, commit-only — Invariant #6: the merge path must
# not re-designate). CLAUDE_PROJECT_DIR is fixed at session start, so a commit run in a git
# worktree created inside that session (e.g. `git -C <wt> commit`) would otherwise be gated
# against main (staged diff invisible · branch-bound tier marker mismatch · relative module-lint
# misses worktree files). flow_gate_check.py --resolve-worktree detects the actual commit
# worktree W by branch-key (from the same hook JSON) and echoes its path; if valid, ROOT=W so the
# cd / CLAUDE_PROJECT_DIR=ROOT / module-command steps below all read W. Detection failure → empty
# → ROOT stays main (current behavior). python3 is guaranteed (dependency check above).
if [ "$_is_commit" -eq 1 ]; then
  _wt="$(printf '%s' "$_hook_input" | CLAUDE_PROJECT_DIR="$ROOT" python3 "$PLUGIN_SCRIPTS/flow_gate_check.py" --resolve-worktree 2>/dev/null || true)"
  if [ -n "$_wt" ] && [ -d "$_wt" ]; then
    ROOT="$_wt"
  fi
fi

cd "$ROOT" || exit 0

status="$(git status --porcelain 2>/dev/null)" || exit 0
[ -z "$status" ] && exit 0

# 1) flow gate. flow_gate_check.py reads the host root from CLAUDE_PROJECT_DIR and
#    FAIL-OPENs (exit 0) on internal error. It emits exit 2 + reason only when the gate is unmet.
flow_reason="$(CLAUDE_PROJECT_DIR="$ROOT" python3 "$PLUGIN_SCRIPTS/flow_gate_check.py" 2>/dev/null)"
flow_rc=$?
if [ "$flow_rc" -eq 2 ] && [ -n "$flow_reason" ]; then
  deny "$flow_reason"
fi

# 2) module pre-check. Per tier, runs the every-commit checks of the changed modules
#    (+ all-module promotion checks on promotion). Commands arrive on stdout, the uncovered report on
#    stderr (stderr is not captured and is shown to the user as-is). On config parse failure /
#    no command: FAIL-OPEN (skip). If any one fails, deny.
mod_cmds="$(CLAUDE_PROJECT_DIR="$ROOT" python3 "$PLUGIN_SCRIPTS/flow_gate_check.py" --module-commands)"
[ -n "$mod_cmds" ] || exit 0

if [ "${HARNESS_PRECOMMIT_DRYRUN:-0}" = "1" ]; then
  echo "DRYRUN: 모듈 사전검사 명령 →" 1>&2
  printf '%s\n' "$mod_cmds" 1>&2
  exit 0
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
done <<EOF
$mod_cmds
EOF

exit 0
