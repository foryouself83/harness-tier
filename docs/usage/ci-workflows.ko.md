# CI 워크플로

[English](ci-workflows.md) · **한국어** · [사용 설명서](../../USAGE.ko.md)

`/flow-init` 은 `flow-config.yaml` 로부터 GitHub Actions 워크플로를 렌더링함. 각각 없을
때만 생성됨 — 새 플러그인의 템플릿 수정은 이미 있는 워크플로에 닿지 않음; 파일을 지우고
`/flow-init` 을 다시 돌리면 새 템플릿을 받음.

| 워크플로 | 스위치 | push/PR 을 막나? |
|----------|--------|-------------------|
| `api-contract.yml` | `contract_test.enable` | 아니요 — 보고만 |
| `unit-test.yml` | `unit_test.enable` | 아니요 — 보고만 |
| `e2e.yml` | `e2e.enable` | 아니요 — 보고만; [E2E](#e2e-안전망) 참고 |
| `doc-style.yml` | `doc_style.enable` | 아니요 — 보고만 |
| `wiki-verify.yml` | `/flow-init` 이 아니라 `/wiki-init` 이 제안 | 아니요 — 보고만 |
| `srs-verify.yml` | `docs/srs/` 가 생기면 `/flow-init` 이 제안 | 아니요 — 보고만 |
| `release.yml` | `versioning.enable` + 지원하는 `release_tool` | — 태그를 만듦 |
| `branch-naming.yml` | `versioning.branch_naming.enable` | 예 — 잘못된 브랜치명 |
| `entropy-check.yml` | `versioning.entropy.enable` | 아니요 — 주간 보고 |
| `deploy.yml` + `deploy-<name>.yml` | `deploy.enable` | — 릴리스 시 배포 |

위 검증 워크플로 중 그 자체로 push/PR 을 **막는** 것은 없음; 각각은
[2층이 보지 못하는](tiers-and-gates.ko.md#게이트가-보는-것) 커밋 — 승격 브랜치의 터미널·
직접·CI 커밋 — 을 위한 가시성 안전망임. 어느 것이든 필수 상태 검사로 만드는 것은 별도
결정이며, 아래 [E2E](#e2e-안전망) 절의 전제조건이 그대로 적용됨.

## `contract_test` — REST API 계약 테스트

`enable: true` 는 지정한 브랜치 — 보통 협업·승격 브랜치, `feature/*` 는 아님 — 에서
`api-contract.yml`(schemathesis) 을 렌더링함. `tool`·`action_ref` 는 설정 시점에 한 번
고정해 낡은 도구가 CI 에 몰래 들어오는 것을 막음. `schema`·`base_url`·`server`
(`compose_file`/`health_url`/`health_timeout`) 가 API 를 가리킴.

## `unit_test` — CI 안전망

로컬 flow 게이트는 Claude 세션 커밋에서만 유닛 테스트를 돌림; `enable: true` 는
`unit-test.yml` 을 렌더링해 CI 에서도 돌게 함. `jobs[]` 는 `modules[]` 와 독립적으로
선언됨 — 로컬 게이트와 CI 는 다른 실행 맥락이기 때문 — 언어/모듈마다 하나씩
(`name`/`language`/`version`/`setup`/`test`), `strategy.matrix.include` 로 렌더링됨.
`language` 가 python/node/java/go/rust 면 그 언어의 공식 setup 액션을 씀; 그 외는 직접
`setup` 명령에 맡김. 대소문자를 구분하므로 대문자 `Python` 은 setup 액션을 조용히
건너뜀. `timeout_minutes` 가 모든 매트릭스 잡을 캡함, 기본 10.

## E2E 안전망

Playwright 스위트 전용 — 브라우저 프론트엔드가 없으면 렌더할 것도 없음. `enable: true`
는 `.github/workflows/e2e.yml` 을 **그대로** 복사함; 저장소 루트나 두 단계 아래까지
`playwright.config.*` 가 없으면 `/flow-init` 이
[`playwright-scaffold`](manual-verification.ko.md#playwright-scaffold) 를 안내함. 그 설정이
생기기 전까지는 워크플로 자신의 감지 단계가 실패 대신 이후 단계를 건너뜀 — 플래그는
파일을 렌더링할 뿐, 스위트가 있어야 의미가 생김.

이 플래그는 **렌더 스위치이지 실행 스위치가 아님**: `false` 로 되돌려도 이미 렌더링된
`e2e.yml` 은 계속 돌아감 — 멈추려면 파일을 지워야 함. Windows 데스크톱 UI(WPF,
WinForms, MAUI) 는 범위 밖 — 브라우저 드라이버가 닿지 못함; 그런 호스트도
`unit-test.yml` 은 받고, REST API 가 있으면 `api-contract.yml` 도 받음.

`github/e2e.workflow.example.yml` 은 채워야 할 `EDIT` 마커 네 개를 담음: 트리거
브랜치, 언어 setup 단계, 스택 시작/대기/정리 단계(Playwright 설정이 `webServer` 로
자체 기동하면 셋 다 삭제), 테스트 패키지 디렉터리(두 단계에서 서로 맞춰 설정).

**필수 상태 검사로 승격하려면** 아래 넷을 모두 갖추거나 전혀 갖추지 않아야 함:

1. `pull_request:` 트리거 추가 — 검사가 전혀 보고하지 않으면 PR 이 "Waiting for status
   to be reported" 에서 멈추고, 직접 push 에 필수로 걸면 교착 상태가 됨;
2. `workflow_dispatch:` 유지 — 장애 상황에서 빈 커밋 없이 누락된 검사를 만들어냄;
3. 브랜치 룰셋에 바이패스 액터를 두거나, 무관한 이유로 스위트가 깨졌을 때 누가
   룰셋을 고칠지 합의;
4. fork PR 은 시크릿을 받지 못하므로, 인증이 필요한 스위트는 외부 기여를 전부
   빨간불로 만듦.

플러그인은 이것을 배선하지 않으며, 해야 하는지에 대해서도 입장을 취하지 않음.

**실제로 승격을 막고 싶다면** 대신 자신의 설정에서 `modules[].checks` 아래
`when: promotion` 인 검사를 추가함 — 그 시점은 Staging·Release 에서 이미 필수인
`security-scan` 묶음으로 들어감. 여기엔 비용 네 가지가 따름: 커밋 훅 안에서 동기적으로
돌아 스위트가 걸리는 만큼 커밋이 멈춤; 모듈 채널은 실패할 때만 출력을 보여줌;
`security-scan` 은 변경 내용과 무관하게 모든 모듈을 돌림; 모듈 검사 명령에는 자체
timeout 이 없음 — 멈춘 브라우저 스위트는 무기한 멈춘 커밋이 됨.

## `doc-style.yml`, `wiki-verify.yml`, `srs-verify.yml`

각각 체크아웃에 자신의 스크립트가 있는지를 가드로 삼고(`.claude/` 를 gitignore 한
저장소는 없음), 실패 대신 exit 0 — 옵트인하지 않은 저장소는 검증할 것 없이 그대로
초록임. `doc-style.yml` 은 `doc_style_check.py --lint-config` 로 `doc_style.paths`
범위를 린트함; `flow-config.yaml` 이 파싱되지 않으면 "꺼짐"이 아니라 잡이 실패함.
`wiki-verify.yml` 은 `wiki_graph.py --verify` 를 돌려 flow 게이트가 보지 못하는
커밋의 그래프 드리프트를 잡음. `srs-verify.yml` 은 `srs_check.py --verify` 를 돌려
서로 다른 브랜치가 각각 만든 죽은 요구사항 앵커나 중복 번호를 잡음 — flow 게이트는
SRS 를 아예 읽지 않기 때문.

## `versioning` — 릴리스, 브랜치명, entropy

`enable: true` 는 최대 세 개의 독립된 워크플로를 렌더링함:

- **`release.yml`** — `release_tool`(대소문자 무시)에 매칭되는 템플릿:
  `python-semantic-release`, `semantic-release`(Node), `jreleaser`, `gitversion`,
  `cargo-release`. 인식되지 않는 값은 보고만 되고 `release.yml` 은 렌더링되지 않음.
  모든 템플릿은 `${{ secrets.RELEASE_TOKEN || secrets.GITHUB_TOKEN }}` 로 인증함
  ([릴리스 토큰](promotion-and-release.ko.md#릴리스-토큰-쓰기-권한)). stable 브랜치에서는
  모든 템플릿이 공유 단계를 돌려 GitHub Release 의 notes 를 그 태그에 대한
  `CHANGELOG.md` 의 `## vX.Y.Z` 절로 바꿔 씀
  ([정식 changelog 절](promotion-and-release.ko.md#정식-changelog-절)) — 그 절이
  없으면 릴리스 도구가 이미 만든 notes 를 그대로 두는 fail-open. `python-semantic-release`
  템플릿은 여기에 더해 최초 release notes 자체도 `CHANGELOG.md` 에서 끌어오고, 다른
  템플릿은 `--generate-notes` 로 만든 뒤 이 공유 단계로만 그 파일을 반영함.
- **`branch-naming.yml`** — 자신의 `branch_naming.enable` 아래, 모든 push 에서.
  고정된 패턴 집합에 안 맞는 브랜치의 push 를 실패시킴: `feature/*`, `fix/*`,
  `docs/*`, `hotfix/X.Y.Z`, `release/X.Y.Z`, 리터럴 `dev`, 그리고
  `versioning.branches.stable`/`.prerelease`. 템플릿은 `flow-config.branches.integration`
  값과 무관하게 `dev` 를 고정 문자열로 박아 넣음 — integration 브랜치명이 정확히
  `dev` 가 아닌 저장소는 그 브랜치로의 모든 push 가 실패함.
- **`entropy-check.yml`** — 자신의 `entropy.enable` 아래, `entropy.paths` 에 대해
  `schedule` cron(기본 주간)으로.

`version_files` 는 릴리스 도구에 버전을 담을 file:field 를 알려줌; 다른 어떤 것도 이
슬롯을 읽지 않음.

## `deploy` — 배포 계층

별도 페이지: [배포](deployments.ko.md).
