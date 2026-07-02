#!/usr/bin/env bash
# SessionStart hook — risk-tiers 룰을 세션 컨텍스트에 주입한다.
#
# 플러그인 rules/ 는 자동 로드되지 않으므로(ras_llm 의 .claude/rules 자동 로드와
# 달리), 이 hook 이 always-on rule 역할을 대신해 매 세션 risk-tiers.md 를 주입한다.
# 파일 부재·읽기 실패 시 빈 주입으로 조용히 통과한다(FAIL-OPEN).
#
# 출력 규약(superpowers session-start 패턴):
#   - Cursor      : additional_context (snake_case, top-level)
#   - Claude Code : hookSpecificOutput.additionalContext (nested)
#   - 그 외(SDK)  : additionalContext (top-level)
# heredoc 은 bash 5.3+ 에서 hang 이슈가 있어 printf 로 출력한다.

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_ROOT="${CLAUDE_PLUGIN_ROOT:-$(cd "${SCRIPT_DIR}/.." && pwd)}"
RULE_FILE="${PLUGIN_ROOT}/rules/risk-tiers.md"

# 룰 파일이 없으면 주입할 것이 없으므로 조용히 종료(FAIL-OPEN).
[ -f "$RULE_FILE" ] || exit 0
rule_content="$(cat "$RULE_FILE" 2>/dev/null)" || exit 0

# bash 파라미터 치환으로 JSON 문자열 escape (문자 단위 루프보다 빠름).
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
session_context="<vway-kit-risk-tiers>\nThis project enforces the vway-kit risk-tiered workflow AT COMMIT TIME. The commit gate is fail-closed: it blocks any commit whose task was not classified by /vdev. So before starting ANY code change, feature, fix, or dev request — and at the latest before you commit — your action MUST be to invoke the /vdev skill (via the Skill tool). /vdev is what classifies the task, confirms the tier, runs the matching gates, and records the marker the commit gate requires. Do NOT judge the tier yourself and skip the skill; without /vdev's marker the commit is rejected.\n\n${rule_escaped}\n</vway-kit-risk-tiers>"

if [ -n "${CURSOR_PLUGIN_ROOT:-}" ]; then
  printf '{\n  "additional_context": "%s"\n}\n' "$session_context"
elif [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -z "${COPILOT_CLI:-}" ]; then
  printf '{\n  "hookSpecificOutput": {\n    "hookEventName": "SessionStart",\n    "additionalContext": "%s"\n  }\n}\n' "$session_context"
else
  printf '{\n  "additionalContext": "%s"\n}\n' "$session_context"
fi

exit 0
