# Codex 지원

[English](codex.md) · **한국어** · [사용 설명서](../../USAGE.ko.md)

harness-tier 의 플러그인 훅과 커밋 게이트는 Claude Code 뿐 아니라 Codex CLI 에도 설치됨. 이
페이지는 [기본 설치](../../README.ko.md#설치) 이후 Codex 호스트에 추가로 필요한 것과, 동작이
다른 지점을 다룸.

## 플러그인 설치

```
codex plugin marketplace add foryouself83/harness-tier
codex plugin add harness-tier@harness-tier
```

둘 다 헤드리스 — TUI 없이 스크립트나 CI 에서 실행됨. Codex TUI 에서 `/plugins` 를 실행해
`harness-tier` 를 설치하는 것도 같은 동작을 대화형으로 함.

## 프로젝트 신뢰

프로젝트 신뢰는 `.codex/hooks.json` 의 커밋 게이트를 포함해 `.codex/` 아래 전부를 좌우함:
신뢰하지 않는 프로젝트는 그 디렉터리 전체를 경고 없이 무시함. 플러그인 자체 훅은 프로젝트
신뢰 밖에 있어, 신뢰하지 않는 프로젝트에도 세션 시작 규칙은 주입되지만 커밋 게이트는 꺼진 채임 —
세션은 커밋이 막힌다고 읽지만 실제로는 막히지 않음. Codex TUI 에서 폴더를
신뢰하거나, `config.toml` 의 `[projects]` 아래 그 경로에 `trust_level = "trusted"` 를
설정함. 신뢰는 훅 승인과는 별개 관문 — 플러그인 자체 훅이든 프로젝트 훅이든 비관리 훅은
`/hooks` 에서 승인해야만 실행되고, 바뀐 훅은 재승인이 필요함.

## `/hooks` 에서 훅 승인

Codex 가 승인하지 않은 훅은 없는 것처럼 동작함: 세션 시작 시 risk-tiers 주입, 편집마다의
마커 무효화, 커밋 게이트 자체가 모두 막는 대신 조용히 넘어감. `/hooks` 를 열어
`harness-tier` 의 항목을 승인한 뒤에야 기댈 수 있음. 승인은 훅의 내용 — 명령 문자열·이벤트·
matcher·플랫폼 변형 — 과 파일 안의 위치에 매여 있어, 플러그인 갱신이 그중 하나를 바꾸면
재승인이 필요하고, `.codex/hooks.json` 의 항목을 옮기거나 순서를 바꿔도 마찬가지임: 게이트
앞에 끼워 넣은 자체 항목은 재승인 전까지 게이트를 침묵시킴. 무관한 플러그인 변경은 필요 없음.

## `/flow-init` 으로 커밋 게이트 활성화

Codex 안에서 실행한 `/flow-init` 은 묻지 않고 게이트를 Codex 에도 설치함 — 매 실행에서,
Claude Code 에서 처음 설정한 호스트의 재실행도 포함함. Claude Code 에서 실행하면 첫 실행은
`.codex/` 디렉터리를 찾거나 사용자가 Codex 를 언급할 때 묻고, 이후 실행은 재설정 메뉴에서
"flow-config.yaml values" 를 고를 때만 Codex 를 추가함. 어느 쪽이든 `flow-config.yaml` 의
`harnesses` 에 `codex` 가 들어가고, 호스트의 `.codex/hooks.json` 에 `Bash` `PreToolUse`
훅으로 게이트를 등록함 — `.claude/settings.json` 의 Claude 쪽 등록과는 별개임.
**Windows 도 Git for Windows 가 필요**: 게이트의 Windows 래퍼는 `git.exe` 옆이나
`%ProgramFiles%\Git` 아래에서 Git 이 번들한 `bash.exe` 를 찾고, 없으면 조용히 통과시키는 대신 **모든 커밋과 머지를 막음**.

등록된 명령은 Codex 가 훅을 실행하는 셸이 펼치는 `$(git rev-parse --show-toplevel)` 로
게이트를 찾음; `$(…)` 를 펼치지 않는 셸(3.4 미만 fish, tcsh)에서는 게이트가 전혀 돌지 않음.
Codex 가 열어 둔 셸 세션에 입력한 명령(`write_stdin`)은 `PreToolUse` 를 발생시키지 않으므로,
터미널 커밋과 마찬가지로 CI 가 최후 방어선임. Linux·macOS 의 훅 동작은 Codex 소스로
확인했을 뿐 실측하지 않음; Windows 는 실측함.

## Claude Code 와 다른 점

- **질문**은 구조화된 선택지 대신 채팅의 번호 선택지로 옴 — Plan 모드에서만 예외로
  `request_user_input` 이 대신 뜸.
- **스킬은 `/이름` 대신 `$이름` 으로 실행** — `$flow <작업>` 이 일상 작업 라우터를 시작함.
- **Teams 알림과 `harness-insight` 는 Claude 전용.** Codex 에는 발송할 `Notification` 훅
  이벤트가 없고, `harness-insight` 가 모을 Claude Code 트랜스크립트도 없음.
- **프로젝트 지침은 `AGENTS.md` 로 렌더됨.** Codex 는 `CLAUDE.md` 나 `.claude/rules/` 를
  직접 읽지 않음 — 세션 디렉터리와 그 상위만, 디렉터리마다 지침 파일 하나만 읽음.
  `/flow-init`·`/doc-sync`·`/harness-init` 은 사용자의 `CLAUDE.md`·`.claude/rules/`(이전
  `/flow-init` 이 남겼을 수 있는 플러그인 자체 규칙 `.claude/rules/harness-tier/` 는 제외 —
  그 내용은 SessionStart 훅 주입으로 이미 받음)·
  모듈별 `CLAUDE.md` 로부터 루트 `AGENTS.md` 안의 관리 블록 하나를 유지함; 편집은 그 원본에서
  하고 블록 자체는 건드리지 않음 — 다음 렌더가 덮어씀. 렌더된 파일은 32 KiB 로 한도가
  있고, 넘으면 규칙 전문 대신 어디를 읽을지 가리키는 색인 항목으로 바뀜.

## 제거

[`/flow-uninstall`](update-and-removal.ko.md#flow-uninstall--호스트-배선-제거) 을 먼저
실행함 — Claude 쪽 정리와 같은 실행에서 `.codex/hooks.json` 의 Codex 게이트와 `AGENTS.md`
의 관리 블록을 지움, `harnesses` 에 `codex` 가 아직 남아있는지와 무관함. `harnesses` 에서
`codex` 를 빼기만 해서는 아무것도 지워지지 않음 — `/flow-init` 이 남은 항목을 알려 줌. 그
다음 플러그인 자체를 헤드리스로 또는 TUI 에서 지움:

```
codex plugin remove harness-tier@harness-tier
codex plugin marketplace remove harness-tier
```
