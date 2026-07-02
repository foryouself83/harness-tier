#!/usr/bin/env bash
# Claude Code PreToolUse hook — git commit 게이트 (vway-kit).
#
# 두 단계로 커밋을 검사하고, 차단할 때만 stdout 으로 deny JSON 을 낸다:
#   1) vdev 게이트 — vdev_gate_check.py(플러그인) 가 선언된 티어/라이프사이클
#      브랜치의 필수 게이트 증거를 확인. 미충족 시 exit 2 + 사유 → deny.
#   2) 모듈 사전검사 — 변경 모듈의 lint/static/import_lint/test(+승격 시 전체 security)
#      를 실행. config 파싱 실패/명령 없음은 FAIL-OPEN(skip), 하나라도 실패하면 deny.
#
# 경로 규약(플러그인은 호스트 밖에 설치됨):
#   - 호스트 저장소 루트 → CLAUDE_PROJECT_DIR (없으면 git toplevel)
#   - 플러그인 스크립트  → CLAUDE_PLUGIN_ROOT/scripts (없으면 이 스크립트 위치)
#
# 차단 규약: PreToolUse 차단은 exit 2 + stderr 사유로 한다(이 빌드는
# permissionDecision JSON+exit0 을 무시함). 신버전 호환을 위해 JSON 도 함께 낸다.
# 변경 없음 / 검사 통과 시: exit 0 → 커밋 허용. 전이적 내부 오류는
# FAIL-OPEN(검사 skip, 커밋 허용)으로 처리해 깨진 게이트가 커밋을 막지 않게 한다.
# 단, python3/PyYAML 같은 필수 도구 부재는 FAIL-CLOSED(차단)다 — 비-Python 팀에서
# 게이트가 조용히 무력화되는 것을 막기 위함(설치 후 재커밋).
#
# 디버그: VWAY_PRECOMMIT_DRYRUN=1 이면 실행할 테스트 명령만 출력하고 실행하지 않음.
set -uo pipefail

# Windows 훅 환경은 cp1252/cp949 로캘이라 Python 기본 I/O 가 UTF-8 이 아니다.
# 한글 사유 print() / UTF-8 설정파일 open() 이 인코딩 오류로 FAIL-OPEN 되는 것을
# 막기 위해 모든 자식 python 에 UTF-8 모드를 강제한다(상속됨).
export PYTHONUTF8=1

deny() {  # $1=사유 → 커밋 차단 (exit 2 가 실제 차단 수단, JSON 은 신버전 호환용)
  printf '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"%s"}}\n' "$1"
  printf 'vway-kit 게이트 차단: %s\n' "$1" >&2
  exit 2
}

# PreToolUse stdin(tool_input JSON)을 읽어 `git commit` 만 게이트한다. settings.json
# `if` 필드에 의존하지 않고 스크립트가 직접 self-filter 한다(빌드별 `if` 동작 차이 회피).
_hook_input="$(timeout 5 cat 2>/dev/null || true)"

# 커밋 여부 판별. python3 가 있으면 tool_input.command 를 정확히 추출한다. 추출이
# 비거나(python3 손상) python3 자체가 없으면 raw stdin 으로 거칠게 폴백한다 —
# "python3 문제 → 커밋 탐지 실패 → 게이트 자가무력화"를 막기 위함(부재/손상은
# 아래 의존성 검사에서 fail-closed 로 막힌다).
_hook_cmd=""
if command -v python3 >/dev/null 2>&1; then
  _hook_cmd="$(printf '%s' "$_hook_input" | python3 -c "import sys, json
try:
    print((json.load(sys.stdin).get('tool_input') or {}).get('command', ''))
except Exception:
    print('')" 2>/dev/null || true)"
fi
case "${_hook_cmd:-$_hook_input}" in *"git commit"*) : ;; *) exit 0 ;; esac

# 의존성 FAIL-CLOSED — 하니스는 python3 + PyYAML 을 요구한다(프로젝트 언어 무관).
# 누락 시 조용히 통과(fail-open)하면 비-Python 팀에서 게이트가 무력화되므로, "필수
# 도구 부재"는 전이적 내부 오류와 달리 커밋을 차단한다(설치 후 재커밋).
#
# DRY 예외(의도된 중복): 아래 부트스트랩 체크의 floor(3, 8)·PyYAML 설치 명령은
# check-deps.sh 와 동일 값이지만 코드 공유가 불가하다 — (1) 게이트가 부르는 bare
# python3 를 직접 검증하므로 파이썬 헬퍼(_vway_paths)로 옮기면 순환이고, (2) 이 스크립트는
# self-contained 가 Invariant(외부 source 실패 시 FAIL-OPEN 으로 게이트 무력화)라 셸끼리도
# 공유 못 한다. 그래서 값 SSOT 는 check-deps.sh 로 두고 여기 floor·설치 명령을 그것과
# 동기화한다(한쪽만 바꾸면 사전점검과 차단 기준이 어긋난다).
if ! command -v python3 >/dev/null 2>&1; then
  deny "게이트에 python3 가 필요합니다. 설치 후 다시 커밋하세요(불가하면 settings.json 의 게이트 훅을 제거)."
fi
# floor = python 3.8 (SSOT: check-deps.sh — 변경 시 양쪽 동기화)
if ! python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" >/dev/null 2>&1; then
  deny "게이트에 python 3.8+ 가 필요합니다(현재 버전 미만). 업그레이드 후 다시 커밋하세요."
fi
# PyYAML 설치 명령 = check-deps.sh 와 동일 문자열로 유지
if ! python3 -c "import yaml" >/dev/null 2>&1; then
  deny "게이트에 PyYAML 이 필요합니다. python3 -m pip install pyyaml 후 다시 커밋하세요(점검: .claude/vway-kit/scripts/check-deps.sh)."
fi

ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel 2>/dev/null)}"
[ -n "$ROOT" ] || exit 0
cd "$ROOT" || exit 0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PLUGIN_SCRIPTS="${CLAUDE_PLUGIN_ROOT:+$CLAUDE_PLUGIN_ROOT/scripts}"
PLUGIN_SCRIPTS="${PLUGIN_SCRIPTS:-$SCRIPT_DIR}"

status="$(git status --porcelain 2>/dev/null)" || exit 0
[ -z "$status" ] && exit 0

# 1) vdev 게이트. vdev_gate_check.py 는 CLAUDE_PROJECT_DIR 로 호스트 루트를 읽고
#    내부 오류 시 FAIL-OPEN(exit 0). 게이트 미충족일 때만 exit 2 + 사유를 낸다.
flow_reason="$(CLAUDE_PROJECT_DIR="$ROOT" python3 "$PLUGIN_SCRIPTS/vdev_gate_check.py" 2>/dev/null)"
flow_rc=$?
if [ "$flow_rc" -eq 2 ] && [ -n "$flow_reason" ]; then
  deny "$flow_reason"
fi

# 2) 모듈 사전검사. tier 별로 변경 모듈의 lint/static/import_lint/test(+승격 시 전체
#    모듈 security)를 실행한다. 명령은 stdout, 미커버 리포트는 stderr 로 분리돼 온다
#    (stderr 는 캡처하지 않고 그대로 사용자에게 노출). config 파싱 실패/명령 없음 시
#    FAIL-OPEN(skip). 하나라도 실패하면 deny.
mod_cmds="$(CLAUDE_PROJECT_DIR="$ROOT" python3 "$PLUGIN_SCRIPTS/vdev_gate_check.py" --module-commands)"
[ -n "$mod_cmds" ] || exit 0

if [ "${VWAY_PRECOMMIT_DRYRUN:-0}" = "1" ]; then
  echo "DRYRUN: 모듈 사전검사 명령 →" 1>&2
  printf '%s\n' "$mod_cmds" 1>&2
  exit 0
fi

LOG_DIR="${TMPDIR:-/tmp}"
mod_log="$LOG_DIR/vway-precommit-module.log"
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
