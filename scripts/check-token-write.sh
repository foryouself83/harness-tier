#!/usr/bin/env bash
# Verify a token has WRITE (push) permission on the repo, via the GitHub API field
# .permissions.push (admin-free — a live check confirmed actions/permissions/workflow
# needs Administration:read and 403s otherwise).
#
# Usage: check-token-write.sh [--decode]
#   default : fetch GET /repos/<repo> and decode .permissions.push
#   --decode: read repo JSON from stdin (unit-testable, no network)
# Env: HARNESS_REPO (else GITHUB_REPOSITORY), HARNESS_TOKEN (else GITHUB_TOKEN)
# Exit: 0 has-write | 10 read-only | 20 undetermined (no token/tool/parse).
set -u

decode() {  # reads JSON on stdin → exit 0 (write) / 10 (read-only) / 20 (undetermined)
  local json rc
  json="$(cat)"
  if command -v python3 >/dev/null 2>&1; then
    rc=0
    printf '%s' "$json" | python3 -c 'import json,sys
try:
    push = (json.load(sys.stdin).get("permissions") or {}).get("push")
except Exception:
    sys.exit(20)
sys.exit(0 if push is True else 10 if push is False else 20)' || rc=$?
  else
    # no python3: line-based scan of the top-level permissions.push (GitHub places it before
    # any nested repo permissions, so the first match is the token's own push right).
    case "$(printf '%s' "$json" | grep -oE '"push"[[:space:]]*:[[:space:]]*(true|false)' | head -1)" in
      *true)  rc=0 ;;
      *false) rc=10 ;;
      *)      rc=20 ;;
    esac
  fi
  case "$rc" in
    10) echo "token lacks write (push) permission on the repo" >&2 ;;
    20) echo "could not determine write permission" >&2 ;;
  esac
  return "$rc"
}

if [ "${1:-}" = "--decode" ]; then
  decode
  exit $?
fi

repo="${HARNESS_REPO:-${GITHUB_REPOSITORY:-}}"
token="${HARNESS_TOKEN:-${GITHUB_TOKEN:-}}"
if [ -z "$repo" ] || [ -z "$token" ] || ! command -v curl >/dev/null 2>&1; then
  echo "token/repo/curl unavailable — skipping write-permission check" >&2
  exit 20
fi
curl -fsS --connect-timeout 5 --max-time 10 -H "Authorization: Bearer $token" -H "X-GitHub-Api-Version: 2022-11-28" \
  "https://api.github.com/repos/$repo" 2>/dev/null | decode
exit $?
