# Teams 알림

[English](teams.md) · **한국어** · [사용 설명서](../../USAGE.ko.md)

Claude 가 입력을 기다릴 때, 지켜보는 브랜치가 push 될 때, 또는 직접 부를 때 Microsoft
Teams 채널에 알림을 보냄.

## 웹훅 URL

채널마다 Power Automate 워크플로로 Teams **incoming webhook URL** 을 만듦 — URL 에
`sig=` 토큰이 들어감. personal 채널부터 시작하고 브랜치 채널은 나중에 추가함.

| 파일 | git | 채널 |
|------|-----|------|
| `.claude/harness-tier/config/.teams-webhooks.local.json` | gitignore | `personal`, 그리고 기본값으로 브랜치 채널 자신의 URL |
| `.claude/harness-tier/config/teams-webhooks.json` | 추적 | 지켜보는 브랜치명들 (URL 은 `--shared` 로 등록했을 때만) |

```bash
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
# 채널 URL 등록 — personal·브랜치 URL 모두 기본은 로컬 파일로; 브랜치 등록은
# 그 키(URL 없이)를 추적 파일에도 더해 모든 클론이 그 브랜치를 지켜보게 됨
python3 "${ROOT}/.claude/harness-tier/scripts/teams_alert.py" --set personal https://...
python3 "${ROOT}/.claude/harness-tier/scripts/teams_alert.py" --set dev https://...
# 브랜치 URL 자체를 팀 전체를 위해 추적 파일에 커밋
python3 "${ROOT}/.claude/harness-tier/scripts/teams_alert.py" --set dev https://... --shared
# 수동 알림
python3 "${ROOT}/.claude/harness-tier/scripts/teams_alert.py" --channel personal --title "..." --text "..."
```

## 채널별 발송 시점

- **`personal`** — 플러그인의 `Notification` 훅이, Claude 가 권한이나 입력을 기다리는
  매 순간 발송함. `AskUserQuestion` 은 이 이벤트를 만들지 않으므로, Teams 채널을 설정하면
  `/flow-init` 이 물어보기 직전에 직접 발송하라는 `harness-tier:teams` 블록을
  `CLAUDE.md` 에 추가함.
- **브랜치 채널** — `teams-notify-push` pre-push 훅이 push 된 브랜치명이
  `teams-webhooks.json` 또는 로컬 웹훅 파일 어느 쪽의 키와도 같을 때 그 커밋 제목을
  발송함. `pre-commit install --hook-type pre-push` 가 필요함; 브랜치를 등록하면 URL
  공유 여부와 무관하게 모든 클론이 그 브랜치를 지켜봄.

URL 이 없는 채널은 조용히 건너뜀 — 단 `personal` 은 등록 방법을 출력함. 발송 실패는
훅이나 push 를 절대 막지 않음.

## 보안

Power Automate URL 의 `sig=` 토큰이 그 채널에 발송하는 자격 증명임. 기본값은 gitignore 된
로컬 파일에 남으므로 공개되는 건 브랜치명뿐. 팀 전체가 그 채널로 발송하길 원할 때만
`--shared` 로 등록함 — 그러면 저장소를 읽을 수 있는 누구나 그 채널에도 발송 가능함
(메시지 주입뿐, 데이터 유출이나 권한 상승은 없음); 그렇게 하기로 했다면 시크릿
스캐너의 예외로 표시함.
