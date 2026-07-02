# harness-tier 사용 설명서

[English](USAGE.md) · **한국어**

[README](README.ko.md) 가 "핵심 생각 + 설치"라면, 이 문서는 **각 스킬의 자세한 설명 ·
설정 상세 · 사용법 · 문제 해결 · 갱신/제거**를 다룹니다. (플러그인이 내부적으로 *어떻게*
동작하는지의 원리는 개발자용 [CLAUDE.md](CLAUDE.md) 에 있습니다.)

## 목차

1. [설치 흐름 요약](#1-설치-흐름-요약)
2. [설정 상세](#2-설정-상세)
3. [스킬 상세](#3-스킬-상세)
4. [Teams 알림](#4-teams-알림)
5. [릴리스 토큰 쓰기 권한](#릴리스-토큰-쓰기-권한)
6. [문제 해결](#6-문제-해결)
7. [갱신·제거](#7-갱신제거)

---

## 1. 설치 흐름 요약

의존성 설치를 포함한 전체 설치 절차는 [README](README.ko.md#설치) 에 있습니다. 요약하면:

1. **의존성** — Python ≥ 3.8 + PyYAML(+ pre-commit), `superpowers` 플러그인.
2. **플러그인 설치** — `/plugin marketplace add foryouself83/harness-tier` →
   `/plugin install harness-tier@harness-tier`.
3. **`/harness-init`** — 프로젝트 하네스(`CLAUDE.md`·문서) 생성(신규 프로젝트는 여기서 시작).
4. **`/flow-init`** — 커밋 게이트·Teams 등 거버넌스 배선(대화형·멱등).
5. **마무리** — `pre-commit install --hook-type commit-msg --hook-type pre-push`.

설치 후 호스트 저장소에 생기는 것은 모두 **`.claude/harness-tier/`** 한곳에 모입니다:

| 경로 | 소유 | git | 내용 |
|------|------|-----|------|
| `.claude/harness-tier/config/` | 호스트/플러그인 | 추적 | `flow-config.yaml`(팀 공유 설정) · `flow-tiers.yaml`(정책) · `teams-webhooks.json` |
| `.claude/harness-tier/config/.teams-webhooks.local.json` | 사용자 | gitignored | 개인 Teams 웹훅 |
| `.claude/harness-tier/scripts/` | 플러그인 | 추적 | 복사된 게이트 스크립트 |
| `.claude/harness-tier/.flow/` | 런타임 | gitignored | 게이트 진행 기록(증거) |

---

## 2. 설정 상세

### 2.1 `flow-config.yaml` — 저장소별 값(팀 공유)

`/flow-init` 이 `.claude/harness-tier/config/flow-config.yaml` 을 만듭니다. **git 으로
추적**되어 같은 저장소를 공유하는 모든 개발자가 동일 설정을 씁니다. 사람이 편집합니다.

```yaml
branches:
  integration: dev          # feature 가 머지되는 통합 브랜치
  staging: stage            # QA/RC 승격 브랜치
  production: main           # 프로덕션 릴리스 브랜치
  feature_prefix: "feature/" # 일상 작업 브랜치 접두사

modules:                     # 모노레포 모듈 단위 사전검사 (모듈별 언어·도구가 다를 때)
  - name: api
    path: services/api/      # 이 경로 아래가 바뀌면 checks 실행
    checks:                  # 있는 것만 — 초안은 /flow-init 이 하네스 SSOT 로 작성, 사람이 수정
      lint:        "ruff check services/api"
      static:      "uv run pyright services/api"
      import_lint: "uv run lint-imports --config services/api/.importlinter"
      test:        "uv run pytest services/api"
      security:    "uv run bandit -r services/api"

review_checklist:            # Dev 등급 도메인 리뷰에서 점검할 항목
  - "regression / 회귀 테스트 통과"
  - "cross-service contract / 서비스 간 계약 유효성"
  - "DB transaction / migration 안전성"
  - "async task idempotency / 비동기 작업 멱등성"

doc_sync:                    # doc-sync 대상
  index: CLAUDE.md
  dirs:
    - "docs/"
    - ".claude/rules/"
  service_docs: "services/*/CLAUDE.md"
```

**`checks` 키의 실행 시점** (모듈 사전검사):

| 키 | 시점 |
|----|------|
| `lint` · `static` · `import_lint` · `test` | 변경 모듈 대상, **모든 커밋**(Dev 게이트) |
| `security` | 전체 모듈 대상, **staging·release 승격 시**(security-scan 게이트) |

**선택 섹션**(REST API·릴리스 자동화가 필요할 때만; `/flow-init` 이 물어보고 렌더링):

- **`contract_test`** — REST API 계약 테스트(schemathesis). `enable: true` 이면
  `/flow-init` 이 `.github/workflows/api-contract.yml` 을 생성합니다. 슬롯: `branches` ·
  `schema`(OpenAPI URL/경로) · `base_url` · `server`(compose_file/health_url/health_timeout) ·
  `tool`/`action_ref`(셋업 시 1회 pin).
- **`versioning`** — python-semantic-release 등 릴리스 자동화. `enable: true` 이면
  release / branch-naming / entropy-check 워크플로우를 렌더링합니다. **GitHub Release
  본문**은 `CHANGELOG.md` 의 최신 섹션(semantic-release 산출물 — type별 그룹핑, 배관
  커밋 필터)을 사용하며, changelog 가 없거나 비어 있으면 GitHub 자동 생성 노트로 폴백합니다.

### 2.2 `flow-tiers.yaml` — 등급→게이트 정책(편집 금지)

같은 `config/` 폴더에 있지만 **플러그인 소유**입니다. 매 설치 때 덮어써지므로 **직접
편집하지 마세요**(고칠 일이 있으면 플러그인 SOURCE 를 고치고 `/flow-init` 재실행). 이
파일이 각 등급에서 어떤 게이트가 필수인지 정합니다.

### 2.3 위험도 등급과 게이트

작업은 네 등급으로 분류되며(두 축), 등급이 **어떤 게이트를 통과해야 커밋되는지**를
결정합니다.

| 등급 | 언제 | superpowers | 필수 게이트 |
|------|------|:---:|------------|
| `docs` | 코드 없는 변경(문서·주석·설정값) | ✗ | `doc-sync` |
| `dev` | 코드 포함 변경(feature/fix) | ✓ | `precommit`(변경 모듈 lint/static/import_lint/test) · `review`(도메인 리뷰) · `doc-sync` |
| `staging` | QA/RC 승격(integration→staging) | ✓ | `precommit` · `review` · `security-scan`(전체 모듈 보안) |
| `release` | 프로덕션 배포(staging→production) | ✓ | `precommit` · `review` · `security-scan` · `security`(보안 리뷰) |

- **`precommit` · `security-scan`** 은 커밋 훅이 직접 실행합니다(별도 마커 없음). 해당
  등급의 `gates` 목록에서 빼면 그 검사만 꺼집니다.
- **`review` · `doc-sync` · `security`** 는 `/flow` 가 게이트를 통과시킨 뒤 증거 마커를
  남기고, 커밋 훅은 그 마커가 있어야 통과시킵니다.
- 위험도 분류의 단일 기준은 룰 `risk-tiers` 이며, 세션마다 자동으로 주입됩니다.

> 성능·통합 검증은 게이트에서 분리되어 **수동 스킬** `/performance` · `/integration` 으로
> 제공됩니다(비강제 — 승격 전 권장).

---

## 3. 스킬 상세

슬래시 커맨드는 모두 스킬입니다. 사용 시점·인자·동작을 정리합니다.

### 3.1 `/flow` — 일상 작업 라우터

```text
/flow <자유 텍스트 요청>
```

**모든 코드 변경의 필수 첫 단계**입니다. 순서:

1. **입력 해석** — 요청 텍스트를 그대로 작업으로 삼습니다.
2. **위험도 분류** — 실제 변경이 **코드냐 아니냐**로 Docs/Dev 를 나눕니다.
   - 문서·주석·설정값만 → **Docs**
   - `.py`/`.js`/`.ts`… 코드, 신규 기능, DB 스키마, 의존성 변경 등 → **Dev**
3. **등급 확인** — 분류 결과를 묻고(오버라이드 가능), 확정 후 작업 브랜치로 전환합니다.
   불확실하면 한 단계 위로 잡습니다.
4. **실행** — 등급별 절차와 게이트를 수행합니다.
   - **Docs**: 직접 편집 → `doc-sync` 로 문서 정합화 → 커밋
   - **Dev**: `superpowers` 파이프라인(설계→계획→구현→검증→리뷰) → 도메인 리뷰
     (`review_checklist` 점검) → `doc-sync` → 커밋

> **승격(Staging/Release)**: integration→staging, staging→production 머지는 **타깃
> 브랜치**가 등급을 결정합니다(별도 표시 불필요). 각 등급의 필수 게이트(§2.3)를 통과해야
> 커밋됩니다.

> **`/flow` 는 건너뛸 수 없습니다.** 거치지 않고 커밋하면 등급 마커가 없어 **미분류
> 커밋**으로 게이트가 막습니다. 강제가 불필요한 저장소라면 `/flow-uninstall` 로 게이트를
> 제거하세요.

### 3.2 `/flow-init` — 설치/갱신 마법사

```text
/flow-init        # 인자 없음 — 대화형
```

커밋 게이트·Teams 등 **거버넌스 배선**을 담당합니다. **여러 번 실행해도 안전**합니다.

- **첫 실행**(config 없음) — 의존성 점검·설치 동의, `flow-config.yaml` 생성, 커밋 게이트
  등록, pre-commit 점검·생성, 자동 업데이트 등록, Teams 배선.
- **재실행**(config 있음) — 먼저 **재동기화**(게이트 스크립트·정책 재복사, 게이트 경로
  보정)를 비대화로 실행하고, 빠진 config 슬롯이 있으면 보충을 제안한 뒤, 무엇을 재설정할지
  물어봅니다(아무것도 안 고르면 재동기화만).

호스트에 쓰는 것은 `${CLAUDE_PROJECT_DIR}/.claude/harness-tier/` 아래에만 모입니다
(외부 도구가 강제하는 `.gitignore`·`.pre-commit-config.yaml`·`.claude/settings.json`·
`.github/workflows/` 제외).

### 3.3 `/flow-uninstall` — 호스트 배선 제거

```text
/flow-uninstall   # 인자 없음 — 대화형(확인 후 제거)
```

`/flow-init` 의 **역연산**입니다. 커밋 게이트·마켓 등록 해제, `.gitignore`/`CLAUDE.md`
관리 블록 제거, `.claude/harness-tier/` 삭제. pre-commit·git 훅은 파괴 위험이 커
**보고만** 하고 수동 제거를 안내합니다.

> ⚠️ **`/plugin uninstall` 전에 먼저 실행하세요** — 정리 도구가 플러그인 안에 있어,
> 플러그인을 먼저 지우면 이 스킬을 쓸 수 없습니다(수동 정리는 §7).

### 3.4 `/harness-init` — 프로젝트 하네스 생성

```text
/harness-init     # 인자 없음 — 대화형 마법사
```

프로젝트에 맞는 `CLAUDE.md`·규칙·기술 문서를 만들어 줍니다. `/flow-init`(거버넌스
배선)과는 **독립적인 별개 커맨드**입니다. 진행 순서:

1. **프레임워크 감지** — 의존성 파일(`package.json`·`pyproject.toml`·`go.mod` 등)과
   디렉터리로 언어·프레임워크를 판별.
2. **리서치** — 다중 서브에이전트(`harness-researcher`)로 최신 컨벤션·베스트 프랙티스·
   무료 기성 솔루션을 웹 조사하고, 기존 코드가 있으면 `harness-code-analyzer` 로 실제
   컨벤션도 분석. 버전은 *각각의 최신*이 아니라 **함께 기동되는 호환 집합**으로 고름.
3. **생성** — `CLAUDE.md`·규칙·기술 문서(SRS·SDS·코드 스타일·온보딩 등)를 분류별 폴더로.
   기본은 **`.md` 파일만** 만들고 실제 설정 파일은 건드리지 않음.
4. **비판·검증** — `harness-critic` 이 생성물의 품질·일관성·버전 호환성(설정 정합 +
   런타임 조합 호환)을 점검하고 다듬음.
5. **미리보기 후 확정** — 무엇을 만들지 먼저 보여주고, **확정해야 비로소 파일을 씀**.
6. **정리** — 작업 중 만든 임시 리서치 사본을 제거(최종 문서만 남김).

- **덮어쓰기 없음** — 기존 파일은 관리 블록 단위로만 갱신, 충돌은 보고.
- 보안 스캐너·CI·폴더 생성·버전 고정 같은 **실제 설정**은 인터뷰에서 **항목별 동의 시에만**.
- **슬래시 커맨드는 생성하지 않습니다.**

| | `/flow-init` | `/harness-init` |
|---|---|---|
| 목적 | 거버넌스 배선(게이트·Teams) | 프로젝트 하네스(`CLAUDE.md`·문서) 생성 |
| 언제 | 저장소 설정 시 1회 | 신규·기존 저장소 언제든 |

### 3.5 `doc-sync` 스킬

코드와 문서 변경을 `git diff` 로 분석해 관련 문서를 갱신하고 문서 집합을 일관되게 맞춥니다.

- **코드 → 문서**: 바뀐 코드의 키워드(클래스/필드/타입/route/함수)로 관련 문서를 찾아 갱신.
- **문서 → 문서**: `flow-config.doc_sync` 대상(index/dirs/service_docs)의 상호 참조·사실
  일관성·인덱스 동기화를 점검. `service_docs` 에 매칭되는 모듈에 로컬 `CLAUDE.md` 가 없으면
  베스트 프랙티스 템플릿으로 새로 만들고, 있으면 부족한 부분만 보완(기존 내용 보존).

`/flow` 가 자동 호출합니다. 계획만 보려면 "doc-sync preview" 라고 하세요.

### 3.6 `harness-insight` 스킬

```text
/harness-insight [기간]   # 예: 7일 · 2주 · 30일 (기본 7일)
```

지정 기간의 Claude Code 트랜스크립트(보낸 프롬프트·tool_use)를 집계해 **4섹션 인사이트
리포트를 대화로 출력**하고, 이어서 누적된 **프로젝트 메모리를 검토·정리**합니다.

- 한 일 분포·반복 지시(하네스 후보)·활동 핫스팟·다음 액션을 도출.
- 메모리 정리: 무효/중복은 삭제, 지속 지식은 `.claude/rules` 또는 `docs/` 로 승격(삭제·이관은
  **사용자 승인 후**).
- **리포트 파일(.md)은 만들지 않습니다**(중간 txt 는 출력 후 삭제).

### 3.7 수동 검증 스킬 — `/integration` · `/performance` · `playwright-scaffold`

게이트가 아닌 **수동 스킬**입니다(필요할 때 직접 호출, 승격 전 권장).

- **`/integration`** — 웹 프론트면 기존 Playwright 케이스를 결정적으로 실행(`--reporter=json`)해
  PASS/FAIL 보고. 웹인데 케이스가 0개면 `playwright-scaffold` 로 메인화면 smoke 를 만들어
  바로 실행하고, 웹이 아니면 시나리오·통과 기준을 사람에게 묻습니다(human-in-the-loop).
- **`/performance`** — 언어별 성능 안티패턴(N+1·쿼리플랜·복잡도·프론트 리렌더)을 정적
  플래깅하고, 백엔드가 있으면 OpenAPI 에서 API 를 추출해 k6 로 각 API 를 부하 측정 →
  p50/p95/p99·throughput·에러율을 SLO 대비 보고.
- **`playwright-scaffold`** — 웹 프로젝트에 결정적 "메인화면 smoke" 케이스를 멱등 생성.
  baseURL 을 설정/코드베이스에서 찾아 확인받고 `goto('/')`+응답 OK+비어있지 않은 title 을
  생성. 보통 `/integration` 이 케이스 0개일 때 호출합니다.

---

## 4. Teams 알림

입력을 기다릴 때나 원하는 시점에 Microsoft Teams 채널로 알립니다.

### 준비 — 채널별 웹훅 URL

쓸 채널(개인·브랜치)마다 Teams **incoming webhook URL** 을 발급받습니다(Power Automate
workflow 로 만든 URL — `sig=` 토큰 포함). 채널은 점진적으로 켤 수 있어, 처음엔 개인 채널만
두고 나중에 브랜치 채널을 더해도 됩니다.

### 웹훅 설정 — 2개 파일

| 파일 | git | 채널 |
|------|-----|------|
| `.claude/harness-tier/config/teams-webhooks.json` | 추적 | 팀 공용 채널(dev/stage/main 등) |
| `.claude/harness-tier/config/.teams-webhooks.local.json` | gitignored | 개인 채널(`personal`) |

```bash
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
# 채널 URL 등록
python3 "${ROOT}/.claude/harness-tier/scripts/teams_alert.py" --set personal https://...
# 수동 알림
python3 "${ROOT}/.claude/harness-tier/scripts/teams_alert.py" --channel personal --title "..." --text "..."
```

- 채널 URL 이 비어 있으면 **조용히 건너뜁니다**. 알림 실패는 작업을 막지 않습니다.
- **자동** — 권한/입력 대기 시 `personal` 채널로 알림이 갑니다(Notification 훅).
- **수동(옵션 제시 직전)** — `AskUserQuestion` 은 자동 알림을 띄우지 않으므로, 입력을
  기다리기 직전 위 명령으로 직접 알립니다.

> Teams 채널을 설정하면 `/flow-init` 이 호스트 `CLAUDE.md` 에 알림 안내 블록을 자동으로
> 넣어(호스트 문서 언어에 맞춰 번역), 저장소의 Claude 가 입력 대기 시 스스로 알리게 합니다.
> **보안 예외** — 추적되는 Power Automate URL 은 incoming webhook 이라 최악도 채널 메시지
> 주입 수준(데이터 유출·권한 상승 없음)이므로 시크릿 스캐너 예외로 취급합니다.

---

## 릴리스 토큰 쓰기 권한

릴리스 워크플로우는 버전 범프와 태그를 푸시하므로 그 토큰에 **쓰기 권한**이 필요합니다.

1. **기본 방법** — Settings → Actions → General → **Workflow permissions** → **Read and
   write permissions** → Save.
2. **조직 정책 재정의** — 조직이 Actions 권한을 읽기 전용으로 제한하면 조직 관리자가
   풀어주어야 합니다(또는 리포지토리별 구성 허용).
3. **보호 브랜치 / 규칙** — 릴리스 브랜치가 푸시를 제한하면 Actions 봇/토큰을 우회 목록에
   추가하거나 우회할 수 있는 토큰을 씁니다.
4. **PAT / `RELEASE_TOKEN` (승격)** — `GITHUB_TOKEN` 으로 부족할 때(보호 우회, 후속 워크플로우
   트리거): 세분화 PAT 을 만들되 `Contents: Read and write` 를 포함시키고(릴리스가 워크플로우
   파일을 건드리면 `Workflows: Read and write` 추가), 리포 시크릿 `RELEASE_TOKEN` 으로 저장한 후
   `actions/checkout` 의 `token:` 과 릴리스 스텝의 `GH_TOKEN` 에서 참조합니다.

릴리스 사전검사(`check-token-write.sh`)는 토큰이 읽기 전용이면 이 안내를 띄우며 빠르게 중단합니다.

---

## 6. 문제 해결

### 커밋이 막혀요 — "python3 / PyYAML 필요"

게이트는 `python3`(3.8+)와 `PyYAML` 을 씁니다(프로젝트 언어와 무관). 없으면 **일부러
커밋을 막습니다**(조용히 검사가 빠지는 것을 방지). 해결:

```bash
python3 -m pip install pyyaml                       # 훅이 부르는 python3 환경에 설치
bash .claude/harness-tier/scripts/check-deps.sh    # 무엇이 빠졌는지 점검
```

> `uv add` 는 가상환경에만 들어가 훅이 못 볼 수 있으니, 위처럼 `python3 -m pip` 로 설치하세요.

### 미분류 커밋으로 막혀요

`/flow` 를 거치지 않고 커밋하면 등급 마커가 없어 게이트가 막습니다. `/flow` 로 작업을
분류하면 풀립니다. 강제가 불필요한 저장소라면 `/flow-uninstall` 로 게이트를 제거하세요.

### Dev 작업인데 절차가 안 돌아요

`superpowers@claude-plugins-official` 플러그인이 설치돼야 합니다. 미설치면 `/flow` 가
중단하고 안내합니다 — 수동 구현으로 건너뛰지 마세요.

### `git commit` 을 언급만 했는데 차단돼요

커밋 게이트는 명령에 `git commit` 문자열이 있으면 매칭합니다. 그 문자열을 단순히 언급하는
명령(`grep "git commit"` 등)도 막힐 수 있습니다 — 정상 동작입니다.

### 게이트가 아무 반응이 없어요(무력화 의심)

게이트 점검기 자신이 bash 라 `bash`/coreutils 부재는 스스로 감지하지 못합니다(FAIL-OPEN).
Windows 는 Git Bash 가 있는지 확인하세요.

> 게이트가 *왜* 그렇게 동작하는지(검증 레이어·Windows 인코딩·파일 전파 등 내부 원리)는
> 개발자용 [CLAUDE.md](CLAUDE.md) 에 정리돼 있습니다.

---

## 7. 갱신·제거

### `/flow-init` 재실행 — 플러그인 갱신 후 동기화

플러그인이 업데이트돼도 호스트의 스크립트 사본은 자동으로 바뀌지 않습니다(복사본이라서).
`/flow-init` 을 다시 실행하면 스크립트·정책 파일을 다시 복사하고 게이트 경로를 보정합니다
(재동기화는 비대화로 항상 먼저 실행). 빠진 config 슬롯이 있으면 보충을 제안하고, 그 외에는
무엇을 재설정할지 물어봅니다(아무것도 안 고르면 재동기화만; 설정값·웹훅은 보존).

### `/flow-uninstall` — 호스트 배선 제거

`/plugin uninstall` 은 캐시만 지우고, `/flow-init` 이 호스트에 쓴 것은 남습니다.
`/flow-uninstall` 이 그걸 정리합니다(확인 후): 커밋 게이트·마켓 등록 해제,
`.gitignore`/`CLAUDE.md` 관리 블록 제거, `.claude/harness-tier/` 삭제.

> ⚠️ **순서가 중요합니다.** 정리 도구가 플러그인 안에 있으므로 **`/plugin uninstall` 전에
> `/flow-uninstall` 을 먼저** 실행하세요.

### 수동 정리 (이미 플러그인을 지운 경우)

`/flow-uninstall` 을 못 쓰게 됐다면 직접 제거합니다:

1. `.claude/harness-tier/` 디렉터리 삭제.
2. `.claude/settings.json` 에서 커밋 게이트 훅(`hooks.PreToolUse`)과 마켓 등록
   (`extraKnownMarketplaces.harness-tier`) 제거.
3. `.gitignore` 에서 harness-tier 라인 제거.
4. `CLAUDE.md` 의 `harness-tier:teams` 관리 블록 제거.
5. (선택) `pre-commit uninstall --hook-type pre-commit --hook-type commit-msg --hook-type pre-push`.

---

## 라이선스

Apache License 2.0 — [LICENSE](LICENSE) 참고.
