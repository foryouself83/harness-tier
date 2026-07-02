# 설계 — vway-kit 계약 테스트 CI 계층 (Schemathesis)

- **날짜**: 2026-06-23
- **상태**: 승인 대기 (brainstorming 산출물)
- **범위**: REST API 계약 테스트를 vway-kit에 추가 — pre-commit이 아니라 **CI(GitHub Actions)** 계층으로, 협업/promotion 브랜치에만 적용.

## 1. 배경과 목표

vway-kit의 검증은 현재 **2레이어**다(CLAUDE.md):

- 레이어 1 — **정적 분석**: 호스트 `.pre-commit-config.yaml` (git-native, 모든 커밋)
- 레이어 2 — **flow 게이트**: `precommit-runner.sh` (PreToolUse, `git commit` self-filter, 티어별)

여기에 **레이어 3 — 계약 테스트(CI)** 를 추가한다. REST API를 가진 호스트 repo가 **OpenAPI 스펙 하나로 구현 언어와 무관하게** 계약을 검증하도록 한다. 무거운 검증이므로 **협업/promotion 브랜치(dev/stage/main 등)에만** 걸고, `feature/*`에는 걸지 않는다 — vway-kit의 위험도 티어 철학("가장 무거운 프로세스를 모든 작업에 적용하지 말 것")과 일치한다.

### 비목표 (YAGNI)

- pre-commit/로컬 커밋 게이트에 계약 테스트를 넣지 않는다(서버 기동이 필요해 커밋 순간엔 부담 + 결정성 저하).
- GitHub Actions 외 CI 플랫폼(GitLab CI 등) 템플릿은 이번 범위 밖.
- 언어별 도구 매트릭스를 만들지 않는다 — OpenAPI **단일 도구**로 구현 언어 무관을 달성한다.
- 매 CI 실행마다 도구를 동적 선택하지 않는다(재현성·오프라인·공급망 리스크).

## 2. 핵심 결정 (확정)

| 항목 | 결정 | 근거 |
|---|---|---|
| 검증 위치 | **CI (GitHub Actions)** — 레이어 3 신설 | pre-commit은 서버 기동 가정 불가 |
| 트리거 브랜치 | `contract_test.branches` **독립 목록** (기본 dev/stage/main 제안) | git-flow 게이트 키와 관심사 분리 → 확장성(`release/**` 등) |
| feature 브랜치 | **제외** (목록에 미포함 → push·PR 모두 트리거 안 함) | 무거운 검증은 promotion 경로만 |
| 도구 | **Schemathesis**, 공식 `schemathesis/action@v3` (Docker 기반) | 가장 활발한 유지보수(v4.x, 2026-06)·property-based fuzzing·구현 언어 무관·CI 표준 통합 |
| "언어 무관"의 의미 | OpenAPI 스펙 1개로 모든 구현 언어 API 검증 (단일 도구) | schemathesis는 Python 설치지만 대상 API 언어 무관 |
| 서버 기동 | **docker compose** (flow-config `server` 슬롯) | 호스트 앱마다 다른 환경값 → 정책 아님 |
| 도구 최신성 | **flow-init 셋업 시 1회** 웹 리서치 → flow-config에 **pin** → CI는 고정값으로 결정적 | 정체 도구 회피 + CI 재현성 양립 |
| enable | 셋업 시 "REST API 있음?" 질문으로 결정, 없으면 워크플로우 **미설치** | REST API 없는 repo 다수 |
| 워크플로우 설치 | **없으면 렌더링 생성, 있으면 자동 병합 X·보고만** | 기존 `.pre-commit-config.yaml` 패턴과 일관 |
| 도구 리서치 위치 | **flow-init 에만** (flow-upgrade 제외) | upgrade는 "비대화형·config 무손상" 원칙 유지 |

## 3. 아키텍처

```text
레이어 1  정적 분석 (pre-commit)        모든 커밋, 로컬, 빠름
레이어 2  flow 게이트 (PreToolUse)      git commit, 로컬, 티어별
레이어 3  계약 테스트 (GitHub Actions)   contract_test.branches push·PR 만   ← 신설
```

### 이중 경로 (적용 흐름)

```text
flow-config.example.yaml (SOURCE·플러그인 소유 — 슬롯 정의)
   │  /flow-init 이 읽어 사용자에게 질문
   ▼
<host>/.claude/vway-kit/config/flow-config.yaml (호스트 소유 — 실제 값)
   │  flow_init_setup.py 가 contract_test 값을 렌더링
   ▼
<host>/.github/workflows/api-contract.yml (렌더된 워크플로우)
   │  GitHub 이 contract_test.branches push/PR 시 실행
   ▼
schemathesis/action@v3 (Docker) — 계약 테스트
```

### `.github/workflows/` 위치 예외

CLAUDE.md의 "호스트 쓰기는 `${CLAUDE_PROJECT_DIR}/.claude/vway-kit/` 아래" 원칙에 **새 예외**를 추가한다. `.gitignore`(git)·`.pre-commit-config.yaml`(pre-commit)·`.claude/settings.json`(Claude Code)과 동일하게 **GitHub이 위치를 강제**하기 때문이다. CLAUDE.md Architecture 항목에 명시한다.

## 4. 컴포넌트 설계

### 4.1 `flow-config.example.yaml` — `contract_test` 섹션 (신규 슬롯)

```yaml
# REST API 계약 테스트 (CI 전용 — GitHub Actions). REST API 없으면 enable:false.
contract_test:
  enable: true
  # 이 워크플로우가 동작할 브랜치 (push/PR 모두). 직접 나열 — 확장 자유.
  # GitHub Actions 브랜치 필터 문법 그대로 사용 가능 (예: 'release/**').
  # 보통 협업/promotion 브랜치. feature/* 는 넣지 않는다(무거운 검증 제외).
  branches: [dev, stage, main]
  # 셋업 시 웹 확인으로 pin (정체 도구 회피). CI는 이 고정값으로 결정적 실행.
  tool: schemathesis
  action_ref: "schemathesis/action@v3"   # 메이저 핀
  # OpenAPI 스펙 위치 (서버 URL 경로 또는 레포 내 파일 경로)
  schema: "http://localhost:8000/openapi.json"
  base_url: "http://localhost:8000"
  # 서버 기동 = docker compose
  server:
    compose_file: "docker-compose.yml"
    health_url: "http://localhost:8000/health"
    health_timeout: 60                    # 초
```

- `branches` 초기값은 `/flow-init`이 `flow-config.branches`(integration/staging/production)에서 가져와 제안하되, 이후 **독립 편집** 가능.
- `tool`/`action_ref`는 셋업 시 pin되며 CI는 변경 없이 사용.

### 4.2 워크플로우 SOURCE 템플릿 — `github/api-contract.workflow.example.yml` (신규)

플러그인 소유 SOURCE. 플레이스홀더를 `flow_init_setup.py`가 flow-config 값으로 치환한다(GitHub Actions YAML은 변수 보간 불가 → 셋업 시 렌더링 필요).

```yaml
# vway-kit 계약 테스트 — /flow-init 이 flow-config.contract_test 로 렌더링.
# 직접 수정 시 /flow-upgrade 는 덮어쓰지 않고 "수동 확인" 보고만 한다.
name: api-contract

on:
  push:
    branches: [dev, stage, main]          # ← contract_test.branches 렌더
  pull_request:
    branches: [dev, stage, main]          # ← contract_test.branches 렌더
  # feature/* 는 목록에 없으므로 자동 제외

jobs:
  api-contract:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Start API server (docker compose)
        run: docker compose -f docker-compose.yml up -d   # ← server.compose_file
      - name: Wait for health
        run: |                                            # ← server.health_url / timeout
          timeout 60 sh -c 'until curl -sf "http://localhost:8000/health"; do sleep 2; done'
      - name: Contract test (schemathesis)
        uses: schemathesis/action@v3                      # ← action_ref
        with:
          schema: "http://localhost:8000/openapi.json"    # ← schema
          base-url: "http://localhost:8000"               # ← base_url
      - name: Teardown
        if: always()
        run: docker compose -f docker-compose.yml down
```

### 4.3 `scripts/flow_init_setup.py` — 워크플로우 렌더+설치

- flow-config의 `contract_test`를 읽는다. `enable:false`거나 섹션 부재면 **아무것도 하지 않음**(미설치).
- `enable:true`면 SOURCE 템플릿을 읽어 `branches`/`schema`/`base_url`/`action_ref`/`server.*`를 치환해 `<host>/.github/workflows/api-contract.yml`로 쓴다.
- **멱등/비파괴**: 대상 파일이 **없으면 생성, 이미 있으면 자동 병합하지 않고 "존재함 — 수동 확인" 보고만**(`.pre-commit-config.yaml`과 동일 패턴). 팀이 커스터마이즈한 워크플로우를 덮지 않는다.
- 보고 라인을 setup 리포트에 추가(생성/스킵-존재/미설치-disable).
- FAIL-OPEN 불변 보존: 렌더링 내부 오류가 커밋·셋업을 막지 않게 한다.

### 4.4 `skills/flow-init/SKILL.md`

- **Step 1**(flow-config 생성)에 `contract_test` 수집 추가:
  - "이 repo에 REST API가 있습니까?"(AskUserQuestion) — 아니오면 `enable:false`로 쓰고 이하 스킵.
  - 예면 `branches`(기본 = flow-config.branches 값 제안), `schema`, `base_url`, `server.*` 수집.
  - **도구 리서치(셋업 1회)**: `harness-researcher` 에이전트로 OpenAPI 계약 테스트 도구 후보의 최신 유지보수 상태 확인 → 추천(기본 schemathesis) → 선택을 `tool`/`action_ref`에 pin.
- **Step 2**(mechanical setup) 보고에 워크플로우 설치 결과 포함.
- Completion report에 "계약 테스트 워크플로우 생성/스킵/미설치" 한 줄 추가.

### 4.5 `skills/flow-upgrade/SKILL.md`

- 도구 리서치는 **넣지 않는다**(비대화형·config 무손상 원칙).
- `flow_init_setup.py` 재실행 시 워크플로우 경로/존재만 **보고**(자동 병합·덮어쓰기 없음). 호스트가 수정한 워크플로우는 보존.

### 4.6 `CLAUDE.md`

- Architecture에 `.github/workflows/` 위치 예외 + 레이어 3(계약 테스트 CI) 명시.

### 4.7 `pre-commit-hooks.example.yaml` (선택)

- "계약 테스트는 pre-commit이 아니라 CI 레이어(레이어 3) 참조" 주석 한 줄.

## 5. 테스트 (`tests/test_flow_init_setup.py`)

- `enable:true` + 워크플로우 부재 → 렌더링 생성, 플레이스홀더가 flow-config 값으로 치환됐는지 검증.
- `branches: [dev, stage, main]` → `on.push.branches`/`on.pull_request.branches`에 정확히 반영.
- 대상 파일 **이미 존재** → 덮어쓰지 않고 보고만(멱등).
- `enable:false` 또는 섹션 부재 → 워크플로우 미생성.
- `server.compose_file`/`health_url`/`schema`/`action_ref` 치환 정확성.
- 렌더링 내부 오류 시 FAIL-OPEN(셋업 중단 없음).

## 6. 리스크와 완화

| 리스크 | 완화 |
|---|---|
| CI에서 서버 기동 실패(헬스 타임아웃) | `health_timeout` 슬롯 + `if: always()` teardown으로 컨테이너 정리 |
| 매 CI 동적 도구 선택의 비결정성 | 도구를 셋업 시 pin, CI는 고정 `action_ref` 사용 |
| 호스트가 워크플로우 커스터마이즈 후 upgrade가 덮어씀 | 있으면 보고만(자동 병합 X) |
| `.github/workflows/` 위치가 원칙 위반처럼 보임 | CLAUDE.md에 명시적 예외로 문서화 |
| schemathesis fuzzing 실행 시간 김 | promotion 브랜치에만 적용 — feature 개발 속도에 영향 없음 |

## 7. 변경 파일 요약

| 파일 | 변경 |
|---|---|
| `github/api-contract.workflow.example.yml` | **신규** SOURCE 템플릿 |
| `flow-config.example.yaml` | `contract_test` 섹션 추가 |
| `scripts/flow_init_setup.py` | 워크플로우 렌더+설치(없으면 생성/있으면 보고), enable 분기 |
| `skills/flow-init/SKILL.md` | Step 1에 contract_test 수집 + 도구 리서치, Step 2 보고, 완료 리포트 |
| `skills/flow-upgrade/SKILL.md` | 워크플로우 경로 보수·보고만 (리서치 없음) |
| `tests/test_flow_init_setup.py` | 렌더링·멱등·있으면-보고·disable 테스트 |
| `CLAUDE.md` | `.github/workflows/` 예외 + 레이어 3 명시 |
| `pre-commit-hooks.example.yaml` | (선택) CI 레이어 참조 주석 |
