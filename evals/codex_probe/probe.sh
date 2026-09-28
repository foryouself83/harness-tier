#!/usr/bin/env bash
LOG="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/log"
in="$(cat)"
printf '%s' "$in" > "$LOG/wrap-$(date +%s%N).json"
case "$in" in
  *PROBE_BLOCK_WRAP*)
    printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"probe deny (wrap)"}}\n'
    echo "probe deny wrap" >&2
    exit 2 ;;
esac
exit 0
