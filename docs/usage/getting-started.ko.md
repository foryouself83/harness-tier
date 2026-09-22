# 시작하기

[English](getting-started.md) · **한국어** · [사용 설명서](../../USAGE.ko.md)

의존성과 플러그인 설치는 [README](../../README.ko.md#설치) 참고. 이 페이지는 그 뒤 순서와
호스트에 남는 것을 다룸.

## 설치 순서

1. **`/harness-init`** — `CLAUDE.md`·`.claude/rules/`·기술 문서 생성
   ([프로젝트 하네스](project-harness.ko.md#harness-init--프로젝트-하네스-생성)). 새 프로젝트라면
   먼저 실행 — `/flow-init` 이 그 문서에서 `modules[].checks` 초안을 뽑음.
2. **`/flow-init`** — `flow-config.yaml` 작성, 커밋 게이트 등록, CI 렌더.
3. **`pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push`**
   — 없으면 커밋 메시지 검사·파일 점검·Teams push 알림이 전혀 돌지 않음.
4. **`/flow <작업>`** — 이후 모든 작업([일상 작업](daily-work.ko.md)).

`/flow-init`·`/flow-uninstall`·`/harness-init`·`/harness-deployments`·`/wiki-init` 다섯 개는
`disable-model-invocation` 스킬임. Claude 가 평문 요청으로 먼저 시작하지 않으므로 슬래시
명령으로 직접 입력함.

## `/flow-init` 첫 실행이 묻는 것

`/flow-init` 은 인자를 받지 않고 재실행해도 안전함
([재실행](update-and-removal.ko.md#flow-init-재실행--플러그인-갱신-후-동기화)). `flow-config.yaml`
이 아직 없는 첫 실행은:

- 의존성을 점검하고 부족분 설치를 제안 — 필수 항목이 끝내 없으면 중단;
- `flow-config.yaml` 슬롯을 하나씩 질문 — 브랜치, 어느 흐름을 PR 로 보낼지, 리뷰 체크리스트,
  doc-sync 대상, API 계약 테스트·유닛 테스트 CI·문체 검사 활성화 여부;
- 하네스 문서에서 `modules[].checks` 초안을 뽑아 편집하도록 남김;
- 흐름 하나라도 PR 로 가면 `gh` 로 GitHub 브랜치 룰셋을 읽어 간극을 보고
  ([PR 워크플로](promotion-and-release.ko.md#pr-워크플로와-브랜치-룰셋));
- `docs/srs/` 가 있으면 `srs-verify.yml` 을 제안;
- 커밋 게이트와 마켓 자동 업데이트를 등록하고, pre-commit 을 점검하고, 설정이 켠 CI 워크플로를
  렌더링하고, Teams 를 연결.

`versioning` 과 `e2e` 는 묻지 않고 설정값 그대로 렌더링됨. 예시 파일은
`versioning.enable: true` 와 `python-semantic-release` 를 담고 있으므로, 값을 바꾸지 않으면 첫
실행에서 그 릴리스 워크플로가 렌더링됨([CI 워크플로](ci-workflows.ko.md)).

## 저장소에 남는 것

하네스 파일은 `.claude/harness-tier/` 아래에 모임. 다른 도구가 위치를 정하는 파일은 그 도구가
찾는 자리에 있음.

| 경로 | 소유 | git | 내용 |
|------|------|-----|------|
| `.claude/harness-tier/config/flow-config.yaml` | 사용자 | 추적 | 팀 공유 설정([설정](configuration.ko.md)) |
| `.claude/harness-tier/config/flow-tiers.yaml` | 플러그인 | 추적 | 등급→게이트 정책, `/flow-init` 실행마다 덮어씀 |
| `.claude/harness-tier/config/teams-webhooks.json` | 사용자 | 추적 | 팀 Teams 채널([Teams](teams.ko.md)) |
| `.claude/harness-tier/config/.teams-webhooks.local.json` | 사용자 | gitignore | 개인 Teams 웹훅 |
| `.claude/harness-tier/scripts/` | 플러그인 | 추적 | 게이트 스크립트, 렌더링된 CI 워크플로도 호출 |
| `.claude/harness-tier/.flow/` | 런타임 | gitignore | 게이트 증거: `tier` 마커와 `<gate>.done` 파일 |
| `.claude/settings.json` | 공유 | 추적 | `PreToolUse` 커밋 게이트와 `harness-tier` 마켓 항목 |
| `.pre-commit-config.yaml` | 사용자 | 추적 | 없으면 예시에서 생성, 있으면 점검만 |
| `.gitignore` | 사용자 | 추적 | 두 줄: `.teams-webhooks.local.json` 과 `.claude/harness-tier/.flow/` |
| `CLAUDE.md` | 사용자 | 추적 | Teams 채널 설정 시 `harness-tier:teams` 블록 |
| `.github/workflows/` | 사용자 | 추적 | 설정이 켠 워크플로([CI 워크플로](ci-workflows.ko.md)) |

`scripts/` 는 커밋 상태로 유지. `wiki-verify.yml`·`doc-style.yml`·`srs-verify.yml` 은 스크립트가
체크아웃에 없으면 건너뛰어 아무것도 검증하지 못하고, `gitversion`·`jreleaser` 릴리스 워크플로는
가드 없이 `bump_version.py` 를 불러 실패함.

`tier` 마커는 작성된 브랜치에 묶임. `<gate>.done` 파일은 그렇지 않음 —
[게이트 증거](tiers-and-gates.ko.md#게이트-증거) 참고.
