#!/usr/bin/env bash
# pre-push hook(pre-commit framework, pre-push stage). push 대상 브랜치가
# 등록된 팀 공용 채널이면 해당 채널로 Teams 알림을 보낸다(그 외 skip). 알림 실패는 무시.
#
# 대상 브랜치는 하드코딩하지 않고 teams_alert.py --list-push-channels 로
# 동적으로 읽는다(= teams-webhooks.json 에 등록된 팀 공용 채널 키). 채널을
# 추가/삭제하면 코드 수정 없이 대상 브랜치가 바뀐다.
#
# 플러그인은 호스트 밖에 설치되므로 teams_alert.py 는 이 스크립트의 형제 경로로
# 찾고, git 컨텍스트(브랜치/커밋)는 호스트 저장소 기준으로 읽는다.
#
# pre-commit 이 hook 에 git pre-push stdin 을 주는지 환경변수를 주는지 환경마다
# 다를 수 있어 둘 다 처리한다(실측: stdin 방식으로 도착 확인). stdin 우선,
# 비어 있으면 PRE_COMMIT_REMOTE_BRANCH 로 폴백. remote ref 기준이라 다른
# 브랜치에서 `git push origin dev` 해도 dev 만 정확히 잡는다.
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ALERT="$SCRIPT_DIR/teams_alert.py"
ROOT="$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
# teams_alert.py 가 웹훅 파일(.claude/vway-kit/config/)을 호스트 루트 기준으로 찾도록
# 명시 전달한다. pre-push 훅엔 CLAUDE_PROJECT_DIR 이 자동 주입되지 않기 때문.
export CLAUDE_PROJECT_DIR="${CLAUDE_PROJECT_DIR:-$ROOT}"

# 알림 대상 브랜치 목록(공백 구분). 없으면 알릴 채널이 없으므로 조용히 종료.
targets="$(python3 "$ALERT" --list-push-channels 2>/dev/null)"
[ -n "$targets" ] || exit 0

is_target() {  # $1=branch → 대상이면 0
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

# 2) stdin 이 비었으면(framework 가 env 만 주는 경우) 환경변수로 폴백
if [ -z "$matched" ]; then
  branch="${PRE_COMMIT_REMOTE_BRANCH:-}"  # set -u 안전: 미설정이면 빈 문자열
  branch="${branch#refs/heads/}"
  if is_target "$branch"; then notify "$branch" "${PRE_COMMIT_TO_REF:-HEAD}"; fi
fi

exit 0
