#!/usr/bin/env bash
# pre-push hook (pre-commit framework, pre-push stage). If a branch being pushed is a
# registered team-shared channel, sends a Teams alert to that channel (otherwise skip). Alert failures are ignored.
#
# The target branches are not hardcoded; they are read dynamically via
# teams_alert.py --list-push-channels (= the team-shared channel keys registered in
# teams-webhooks.json). Adding/removing a channel changes the target branches without code changes.
#
# Since the plugin is installed outside the host, teams_alert.py is found via this script's
# sibling path, while the git context (branch/commit) is read relative to the host repo.
#
# Whether pre-commit passes the hook the git pre-push stdin or environment variables can vary
# by environment, so both are handled (observed: arrives via stdin). stdin takes precedence,
# and if empty it falls back to PRE_COMMIT_REMOTE_BRANCH. Being remote-ref based, even
# `git push origin dev` from another branch matches only dev exactly.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ALERT="$SCRIPT_DIR/teams_alert.py"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
# Explicitly pass this so teams_alert.py finds the webhook file (.claude/harness-tier/config/)
# relative to the host root, because CLAUDE_PROJECT_DIR is not auto-injected into pre-push hooks.
export CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$ROOT}"

# List of alert target branches (space-separated). If empty, there are no channels to alert, so exit quietly.
targets="$(python3 "$ALERT" --list-push-channels 2>/dev/null)"
[ -n "$targets" ] || exit 0

is_target() {  # $1=branch → 0 if it is a target
  local b
  for b in $targets; do [ "$1" = "$b" ] && return 0; done
  return 1
}

notify() {  # $1=branch  $2=sha
  local subject
  subject="$(git -C "$ROOT" log -1 --pretty=%s "${2:-HEAD}" 2>/dev/null)"
  python3 "$ALERT" \
    --channel "$1" --title "Push: $1" --text "$subject" || true
}

matched=""
# 1) git native pre-push stdin: <local_ref> <local_sha> <remote_ref> <remote_sha>
while read -r _local_ref local_sha remote_ref _remote_sha; do
  branch="${remote_ref#refs/heads/}"
  if is_target "$branch"; then notify "$branch" "$local_sha"; matched=1; fi
done

# 2) if stdin was empty (framework passes only env), fall back to environment variables
if [ -z "$matched" ]; then
  branch="${PRE_COMMIT_REMOTE_BRANCH:-}"  # set -u safe: empty string if unset
  branch="${branch#refs/heads/}"
  if is_target "$branch"; then notify "$branch" "${PRE_COMMIT_TO_REF:-HEAD}"; fi
fi

exit 0
