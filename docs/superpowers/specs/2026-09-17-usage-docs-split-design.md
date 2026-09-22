# USAGE 분할 + README/USAGE 현행화 설계

## 목표

- `USAGE.md`(845줄)·`USAGE.ko.md` 를 `docs/usage/` 아래 주제별 문서로 분할함.
- README·USAGE 의 누락·상충·중복을 현재 코드 기준으로 정리함.
- 감사에서 드러난 소스 결함 4건을 함께 수정함.

## 결정 사항

- 루트 `USAGE.md`(.ko) 는 짧은 색인으로 유지 — 외부 링크·`release.yml` 메시지·README 앵커 보존.
- 분류는 주제별 12개, 각 파일에 `.ko.md` twin.
- 누락 보강은 소비자 계약만 — 언제 부르나·인자·선행조건·무엇을 쓰나·생략 시 깨지는 것. 내부 절차는 SKILL.md 몫.
- 소스 결함은 같은 브랜치에서 수정.

## 1. 구조

| 파일 | 답하는 질문 | 흡수하는 현재 절 |
|------|-------------|------------------|
| `getting-started.md` | 설치 후 호스트에 무엇이 생기나, 어떤 순서로 쓰나 | §1 (+ 예외 목록 통합) |
| `configuration.md` | `flow-config.yaml` 각 키, `flow-tiers.yaml` 편집 금지 | §2.1, §2.2 도입 |
| `tiers-and-gates.md` | 등급별 게이트, 검증 계층, merge_strategy, evidence | §2.2 표·범위, §2.3 |
| `daily-work.md` | `/flow` · `/commit` · `/doc-sync` · `/prose-review` | §3.1, §3.5, §3.11 |
| `promotion-and-release.md` | `/release-commit`, PR 모드·ruleset, 릴리스 토큰 | §3.10, §2.1 merge_workflow, §2.2 PR 문단, 토큰 절 |
| `deployments.md` | `/harness-deployments` | §3.8 |
| `ci-workflows.md` | 렌더되는 워크플로 목록과 켜는 스위치, E2E | §2.1 선택 섹션, §3.7 E2E |
| `project-harness.md` | `/harness-init`(언어표) · `/wiki-init` · `/harness-insight` | §3.4, §3.6, §3.9 |
| `manual-verification.md` | `/integration` · `/performance` · `/playwright-scaffold` | §3.7 |
| `teams.md` | Teams 알림 | §4 |
| `troubleshooting.md` | 차단·무반응 원인과 해결 | §6 |
| `update-and-removal.md` | 갱신, `/flow-init` 재실행, `/flow-uninstall`, 수동 정리 | §3.2 재실행, §3.3, §7 |

`/flow-init` 첫 실행 설명은 `getting-started.md`, `/flow-uninstall` 은 `update-and-removal.md` 가 소유.

### 사실별 원본 위치

| 사실 | 원본 |
|------|------|
| 설치 절차·의존성 | README |
| 호스트 레이아웃(예외 포함) | getting-started |
| 검증 계층 정의("Claude 세션 커밋·머지만 게이트가 봄") | tiers-and-gates |
| evidence 마커·무효화 | tiers-and-gates |
| `checks` 의 `when` 시점 | configuration |
| PR 모드·ruleset·백머지 | promotion-and-release |
| 렌더 워크플로 카탈로그 | ci-workflows |
| 재실행·uninstall·수동 정리 | update-and-removal |
| 미분류 커밋 차단 | troubleshooting |
| 무손실 재작성 증명(`--verify-git`) | daily-work (`/prose-review`) |

나머지 위치는 한 줄 링크로 대체.

### 저장소 메타

- `CLAUDE.md` 첫 문단과 Folder structure 의 `docs/` 줄에 `docs/usage/` 를 반영.
- `.github/workflows/release.yml` 메시지, `flow-config.example.yaml` 의 E2E 주석을 새 경로로 갱신.

## 2. 내용 수정

모든 서술은 작성 시점에 소스로 재확인함. 감사 보고서는 출발점일 뿐 근거가 아님.

### README

- Hooks 행: 플러그인 훅(SessionStart · PostToolUse · Notification)과 `/flow-init` 이 호스트 `settings.json` 에 등록하는 PreToolUse 게이트를 분리.
- Rules 행: `gate-mechanics` · `merge-strategy` · `promotion` · `harness-rules` 추가, `risk-tiers` 만 세션마다 주입됨을 명시.
- `harness-authoring` 행 추가(`/harness-init` 의 생성 엔진, 직접 호출하지 않음).
- 스킬 표기 `/name` 으로 통일.
- "A typo fix commits instantly" — Docs 등급도 `doc-sync` · `wiki` · `doc-style` 게이트를 거치므로 정정.
- CI 목록에 `e2e.yml` · `srs-verify.yml` 반영, contract test 는 모듈 check 가 아닌 별도 CI.
- Requirements: `gh`(PR 모드 ruleset 점검) 추가, coreutils 목록을 `check-deps.sh` 기준으로.
- 레이아웃 문장에 `.claude/harness-tier/` 밖 예외 반영.

### docs/usage — 상충 정정

- 호스트 쓰기 예외: `.claude/settings.json` · `.pre-commit-config.yaml` · `.gitignore` 두 줄 · `CLAUDE.md` teams 블록 · `.github/workflows/`.
- `flow-tiers.yaml` 은 `/flow-init` 실행마다 덮어씀. 소비자가 지속적으로 바꿀 방법은 없음, 게이트 제거는 `/flow-uninstall`.
- `merge_workflow.promotion` 에 `hotfix/*` → production 포함.
- `versioning`: release.yml 은 지원 `release_tool` 일 때만, branch-naming·entropy 는 각자 `enable`. `/flow-init` 이 묻지 않는 섹션(`versioning` · `e2e`) 구분. CHANGELOG release body 는 python-semantic-release 템플릿 한정.
- doc-style 커밋 단계는 error 코드만 보고, `LONG` · `CLAIM` 경고는 `--lint`/CI 에서만.
- 릴리스 토큰 점검은 `/release-commit` 이 수행(경고만), 렌더된 릴리스 워크플로에는 preflight 없음.
- 모듈 check 명령별 timeout 은 없고 게이트 훅 전체가 600초 제한.
- `.gitignore` 는 managed block 이 아니라 두 줄.
- `/doc-sync preview` — 인자가 정확히 `preview` 일 때만 계획 모드.
- `/integration` 판정은 web · Electron · non-web 셋.
- `/harness-init` 은 `.md` 외에 gitignore 된 `.claude/harness-tier/.harness/` 근거 파일을 남기고, 정리 단계는 근거 메타데이터를 보존.
- `/release-commit` 의 `Release-Level:` 트레일러는 조건부(강제 가능한 호스트의 첫 staging 승격만).
- `/flow` 는 코드 변경만이 아니라 모든 작업·커밋의 첫 단계. 승격은 tier 마커가 없을 뿐 게이트 마커는 필요.

### docs/usage — 누락 보강(소비자 계약)

- `/commit` 절 신설: 인자, `--no-verify` 금지, 파일 단위 스테이징, 분류하지 않음.
- `disable-model-invocation` 스킬 5개(`/flow-init` · `/flow-uninstall` · `/harness-init` · `/harness-deployments` · `/wiki-init`)는 직접 입력해야 함.
- `flow-config` 슬롯 설명: `wiki` · `doc_style` · `deploy` · `versioning` 하위 · `modules[].path` 일치 규칙 · `gate_evidence`.
- `/wiki-init` 선행조건(`flow-config.yaml`), `wiki.enable` 을 켜고 `--verify` 실패 시 되돌림.
- troubleshooting: evidence 누락 차단, merge_strategy 위반, 모듈 사전검사 실패, wiki 구조 위반·stamp-only 차단, `/flow-init` 판정 실패, 게이트 무반응의 추가 원인.
- 갱신: `/flow-init` 재실행은 기존 워크플로를 갱신하지 않음(create-if-absent) — 템플릿 변경을 받으려면 파일 삭제 후 재실행.
- 제거: uninstall 후 남는 것(워크플로 · `.pre-commit-config.yaml` · git 훅), 삭제분 커밋 필요, `teams-notify-push` pre-push 훅, 수동 정리에 branch-naming · entropy-check · deploy 워크플로 추가.
- Teams 브랜치 채널은 pre-push 훅에서 브랜치명이 키와 일치할 때 발송.
- 번호 체계: 파일 분할로 절 번호(§) 폐기, 교차 참조는 파일·앵커 링크.

## 3. 소스 결함 수정

| 결함 | 수정 |
|------|------|
| `branches.feature_prefix` 를 읽는 코드 없음(merge_strategy · branch-naming · risk-tiers 모두 `feature/` 고정) | `flow-config.example.yaml` 과 flow-init Step 1 질문에서 삭제. 테스트 fixture 는 유지 — 키가 남은 호스트도 로드됨 |
| `check-deps.sh` 가 superpowers 마켓을 `anthropics/claude-code` 로 안내, 옛 등급명 `Standard+` · `Dev+` | `anthropics/claude-plugins-official`, `Dev` 로 정정. WSL ShellCheck |
| flow-uninstall SKILL.md Step 3 에 `srs-verify.yml` 누락(스크립트는 출력) | 추가 |
| flow-init `references/setup-script-actions.md` 에 versioning 렌더 항목 누락 | 추가 |

flow-init · flow-uninstall 은 eval 측정 대상이 아님 — 본문 수정에 재측정 비용 없음.

## 4. 테스트

- `tests/docs/test_tier_table_parity.py`: `TWINS` → `docs/usage/tiers-and-gates.md` · `.ko.md`.
- `tests/skills/test_shipped_contracts.py`
  - 스킬 등록 검사: README.md · README.ko.md · `docs/usage/*.md`(ko 제외) 합본 · `docs/usage/*.ko.md` 합본.
  - review_checklist 검사: `docs/usage/configuration.md` · `.ko.md`.
- 신규 `tests/docs/test_usage_docs.py`
  - `docs/usage` 의 모든 문서에 twin 존재.
  - 루트 `USAGE.md` · `USAGE.ko.md` 가 각 언어의 모든 문서를 링크.
  - README · USAGE · `docs/usage` 의 상대 링크 대상 파일 존재, 앵커는 `scripts/_md_anchors.py` 의 `_has_anchor` 로 해석.
- 신규 가드 mutation 확인: twin 삭제, 앵커 오타, 색인 링크 제거 각각이 실패하는지.
- `doc_style_check.py --lint` 를 바뀐 모든 `.md` 에.

## 5. 커밋

소비자 대상 `.md` 와 스킬 본문 변경 → `fix`. 브랜치 하나에 amend 된 커밋 하나.
