#!/usr/bin/env bash
# Codex's hook for the commit gate. Codex honours the runner's deny JSON, but on Windows the
# PowerShell that runs hooks turns exit 2 into 1, which Codex reads as a failed hook and lets the
# command through — so the runner's 2 becomes 0 here and the JSON alone blocks.
# The runner is shared with Claude Code and names its skills `/flow…` and its gate settings.json;
# the reason is reworded to Codex's `$flow…` and .codex/hooks.json on the way out. A rewording
# that fails prints the runner's own text: the JSON is the block, so it must never go missing.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
out="$(bash "$here/../../precommit-runner.sh")"
rc=$?
if [ -n "$out" ]; then
  reworded="$(printf '%s\n' "$out" | sed -E -e 's#(^|[ (])/(flow[a-z-]*)#\1$\2#g' \
    -e 's#settings\.json 의 게이트 훅#.codex/hooks.json 의 게이트 훅#g')" && [ -n "$reworded" ] \
    || reworded="$out"
  printf '%s\n' "$reworded"
fi
[ "$rc" -eq 2 ] && exit 0
exit "$rc"
