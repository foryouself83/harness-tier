#!/usr/bin/env bash
# SessionStart hook — injects the risk-tiers rule into the session context.
#
# Since the plugin's rules/ is not auto-loaded (unlike ras_llm's .claude/rules auto-load),
# this hook stands in for an always-on rule and injects risk-tiers.md every session.
# On missing file / read failure, it passes quietly with an empty injection (FAIL-OPEN).
#
# Output convention (superpowers session-start pattern):
#   - Cursor      : additional_context (snake_case, top-level)
#   - Claude Code : hookSpecificOutput.additionalContext (nested)
#   - others (SDK): additionalContext (top-level)
# heredoc has a hang issue on bash 5.3+, so we output via printf.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
RULE_FILE="${PLUGIN_ROOT}/rules/risk-tiers.md"

# If the rule file is absent there is nothing to inject, so exit quietly (FAIL-OPEN).
[ -f "$RULE_FILE" ] || exit 0
rule_content="$(cat "$RULE_FILE" 2>/dev/null)" || exit 0

# Escape the JSON string via bash parameter substitution (faster than a per-character loop).
escape_for_json() {
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  s="${s//$'\t'/\\t}"
  printf '%s' "$s"
}

rule_escaped="$(escape_for_json "$rule_content")"
session_context="<harness-tier-risk-tiers>\nThis project enforces the harness-tier risk-tiered workflow AT COMMIT TIME. The commit gate is fail-closed: it blocks any commit whose task was not classified by /flow. So before starting ANY code change, feature, fix, or dev request — and at the latest before you commit — your action MUST be to invoke the /flow skill (via the Skill tool). /flow is what classifies the task, confirms the tier, runs the matching gates, and records the marker the commit gate requires. Do NOT judge the tier yourself and skip the skill; without /flow's marker the commit is rejected.\n\n${rule_escaped}\n</harness-tier-risk-tiers>"

if [ -n "${CURSOR_PLUGIN_ROOT:-}" ]; then
  printf '{\n  "additional_context": "%s"\n}\n' "$session_context"
elif [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -z "${COPILOT_CLI:-}" ]; then
  printf '{\n  "hookSpecificOutput": {\n    "hookEventName": "SessionStart",\n    "additionalContext": "%s"\n  }\n}\n' "$session_context"
else
  printf '{\n  "additionalContext": "%s"\n}\n' "$session_context"
fi

exit 0
