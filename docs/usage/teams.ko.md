# Teams 알림

[English](teams.md) · **한국어** · [사용 설명서](../../USAGE.ko.md)

Claude 가 입력을 기다릴 때, 지켜보는 브랜치가 push 될 때, 또는 직접 부를 때 Microsoft
Teams 채널에 알림을 보냄.

## 웹훅 URL

채널마다 Power Automate 워크플로로 Teams **incoming webhook URL** 을 만듦 — URL 에
`sig=` 토큰이 들어감. personal 채널부터 시작하고 브랜치 채널은 나중에 추가함.

| 파일 | git | 채널 |
|------|-----|------|
| `.claude/harness-tier/config/.teams-webhooks.local.json` | gitignore | `personal` — 개인용 |
| `.claude/harness-tier/config/teams-webhooks.json` | 추적 | 브랜치명 하나당 키 하나, 팀 공유 |

```bash
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
# 채널 URL 등록 — personal 은 로컬 파일로, 다른 이름은 추적 파일로
python3 "${ROOT}/.claude/harness-tier/scripts/teams_alert.py" --set personal https://...
# 수동 알림
python3 "${ROOT}/.claude/harness-tier/scripts/teams_alert.py" --channel personal --title "..." --text "..."
```

## 채널별 발송 시점

- **`personal`** — 플러그인의 `Notification` 훅이, Claude 가 권한이나 입력을 기다리는
  매 순간 발송함. `AskUserQuestion` 은 이 이벤트를 만들지 않으므로, Teams 채널을 설정하면
  `/flow-init` 이 물어보기 직전에 직접 발송하라는 `harness-tier:teams` 블록을
  `CLAUDE.md` 에 추가함.
- **브랜치 채널** — `teams-notify-push` pre-push 훅이 push 된 브랜치명이
  `teams-webhooks.json` 의 키와 같을 때 그 커밋 제목을 발송함.
  `pre-commit install --hook-type pre-push` 가 필요함; 키를 추가하면 지켜보는 브랜치가
  늘어남.

URL 이 없는 채널은 조용히 건너뜀 — 단 `personal` 은 등록 방법을 출력함. 발송 실패는
훅이나 push 를 절대 막지 않음.

## 보안

추적되는 Power Automate URL 은 incoming webhook 이라 최악의 경우도 그 채널에 메시지가
주입되는 것뿐 — 데이터 유출이나 권한 상승은 없음. 시크릿 스캐너의 예외로 표시함.
