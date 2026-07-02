# vway-kit 사용 설명서

[README](README.md)가 "무엇을 해 주나 + 설치"라면, 이 문서는 **실제 사용법 · 설정 · 문제 해결**을
다룹니다. (플러그인이 내부적으로 *어떻게* 동작하는지의 원리는 개발자용 [CLAUDE.md](CLAUDE.md)와
[docs/plugins/](docs/plugins/marketplace-auto-update.md)에 있습니다.)

---

## 1. 무엇을, 왜

vway-kit의 핵심 생각은 하나입니다:

> **모든 작업에 똑같이 무거운 절차를 강요하지 않는다 — 위험도에 비례해 절차를 조절한다.**

작업이 어느 등급으로 분류되느냐가 **어떤 검증을 통과해야 커밋되는지**를 결정합니다.
문서 한 줄 수정(Docs)은 가볍게, 비즈니스 로직 변경(Dev)은 무겁게 갑니다.

브랜치명·테스트 명령·Teamer 번호 같은 저장소별 값은 모두 `vdev-config.yaml`로 빠져 있어,
새 저장소에는 `/vdev-init` 한 번으로 그대로 옮겨집니다. 여기에 Teamer 연동과 Teams 알림이 함께 옵니다.

---

## 2. 시작하기

**1) 저장소 접근 준비 (SSH)**

vway-kit은 비공개 저장소라, 설치 전에 이 저장소를 SSH로 받을 수 있는 상태여야 합니다
(조직 저장소면 먼저 조직 관리자에게 **멤버 초대 + 저장소 Read 권한**을 요청 — 권한이
없으면 키를 등록해도 거부됩니다). 새 PC 기준 순서:

1. SSH 키 생성(없을 때) — `ssh-keygen -t ed25519 -C "you@example.com"`
2. 공개키(`~/.ssh/id_ed25519.pub`)를 GitHub Settings → SSH and GPG keys 에 등록
3. 호스트 키 등록 + 확인 — `ssh -T git@github.com` → fingerprint 확인 후 `yes`.
   `Hi <아이디>! You've successfully authenticated` 가 나오면 OK.

새 PC에서 `marketplace add` 가 `Host key verification failed` / `Permission denied` 로
실패하는 건 거의 이 단계 누락입니다(§10). Claude Code의 `add` 는 비대화형이라 호스트 키
프롬프트를 못 띄우므로, 터미널에서 위 `ssh -T` 로 먼저 신뢰를 등록해야 합니다.

> 평소 `insteadOf` 로 github.com 을 HTTPS로 치환해 뒀다면 SSH 키가 무력화될 수 있습니다.
> 그 경우 SSH URL 대신 토큰(HTTPS) 경로를 쓰거나 해당 치환을 풀어야 합니다.

**2) 플러그인 설치**

```
/plugin marketplace add git@github.com:Developments-3/vway-kit.git
/plugin install vway-kit@vway
```

> 비공개 저장소의 **자동 업데이트**를 받으려면 GitHub 토큰(PAT) 설정이 한 번 더 필요합니다
> (SSH와 별개) — [README의 "자동 업데이트 설정"](README.md#자동-업데이트-설정-비공개-저장소)을 따르세요.

**3) `/harness-init` — 프로젝트 하네스 생성**

프로젝트에 맞는 `CLAUDE.md`·규칙·기술 문서를 만듭니다(§6). **아무것도 없는 새 프로젝트는
여기서부터** 시작하세요. 이미 `CLAUDE.md`가 잘 갖춰진 기존 프로젝트라면 건너뛰어도 됩니다.

**4) 준비물 작성 — harness-init 다음, vdev-init 전**

Teamer나 Teams를 쓸 거라면 계정·웹훅을 이때 만듭니다. **이 시점엔 아직 `.claude/vway-kit/config/`
폴더가 없으므로 프로젝트 루트에 두면 됩니다** — 다음 단계의 `/vdev-init`이 자동으로 `config/`로
옮겨 줍니다(또는 `/vdev-init`이 대화형으로 물어볼 때 입력해도 됩니다).

- **Teamer를 쓸 경우** — 최초 1회 `python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" setup` 실행 (자세한 설정은 §7)
- **Teams 알림을 쓸 경우** — 두 채널의 웹훅 URL (발급·등록법은 §8):
  - **개인 채널**(`personal`) — 나에게만 오는 입력 대기 알림
  - **브랜치 채널**(dev/stage/main 등) — 팀 공용 알림

**5) `/vdev-init` — 거버넌스 배선**

그 위에 커밋 게이트·Teamer·Teams를 배선합니다. 대화형 마법사가 다음을 자동으로 하며,
**여러 번 실행해도 안전**합니다:

- 루트에 둔 준비물을 `.claude/vway-kit/config/`로 이전
- 설정 파일 `vdev-config.yaml` 생성
- 커밋 게이트 등록 + pre-commit 훅 점검·생성
- 자동 업데이트 등록 · Teams/Teamer 연동 배선

**6) 마무리**

- `uv run pre-commit install --hook-type commit-msg --hook-type pre-push`
- `pre-commit-hooks.example.yaml`의 언어별 검사 도구(ruff/bandit 등)를 팀 스택에 맞게 교체

설치가 끝나면 `/vdev <작업 설명 또는 Teamer 작업 번호>`로 시작합니다.

> 설치 후 호스트 저장소에 생기는 것은 모두 **`.claude/vway-kit/`** 한곳에 모입니다 —
> `config/`(내 설정·계정·웹훅), `scripts/`(실행 스크립트), `.vdev/`(게이트 진행 기록).

---

## 3. 무엇이 들어 있나

| 종류 | 항목 | 역할 |
|------|------|------|
| 커맨드 | `/vdev` | 위험도 분류 → 등급별 워크플로 실행 → 게이트 기록 |
| 커맨드 | `/vdev-init` | 설치/갱신 마법사 — 최초 설정 + 재실행 시 재동기화·슬롯 보충·재설정 (설정값 보존) |
| 커맨드 | `/vdev-uninstall` | 호스트에 설치된 vway-kit 배선 제거 |
| 커맨드 | `/harness-init` | 프레임워크 감지 + 리서치·검증으로 하네스 생성 |
| 커맨드 | `/task-import` · `/task-sync` | Teamer 작업 가져오기 / 결과 동기화 |
| 에이전트 | `harness-researcher` · `harness-code-analyzer` · `harness-critic` | 하네스 리서치 / 코드 분석 / 생성물 검증 |
| 룰 | `risk-tiers` | 위험도 분류 + 커밋 규율의 기준 |
| 스킬 | `doc-sync` | 코드 ↔ 문서 동기화 + 문서 일관성 |
| 스킬 | `harness-insight` | 지정 기간 Claude Code 활동 집계 + 인사이트 리포트 + 메모리 정리 |
| 스킬 | `playwright-scaffold` · `integration` · `performance` | E2E 스캐폴드 / 통합·성능 검증(비강제 수동 스킬) |
| 훅 | SessionStart · Notification · PreToolUse(commit) | 규칙 주입 · Teams 알림 · 커밋 게이트 |

---

## 4. 설정 — `vdev-config.yaml`

`/vdev-init`이 만든 `.claude/vway-kit/config/vdev-config.yaml`을 팀 환경에 맞게 채웁니다.
(이 파일은 git 추적 — 같은 저장소를 공유하는 모든 개발자가 동일한 설정을 사용합니다. 자격증명은 keyring 이라 여기 없습니다.)

```yaml
branches:
  integration: dev          # feature 가 머지되는 통합 브랜치
  staging: stage            # QA/RC 승격 브랜치
  production: main          # 프로덕션 릴리스 브랜치
  feature_prefix: "feature/"

modules:                    # 모노레포 모듈 단위 사전검사 (모듈별 언어·도구가 다를 때)
  - name: api               # lint/static/import_lint/test → vdev 게이트(변경 모듈, 모든 커밋)
    path: services/api/     # security → staging·release 승격(전체 모듈)
    checks:                 # 초안은 /vdev-init 이 harness SSOT 참고해 작성, 사람이 수정
      lint: "ruff check services/api"
      test: "uv run pytest services/api"
      security: "uv run bandit -r services/api"

review_checklist:           # Dev 등급에서 점검할 항목
  - "regression / 회귀 테스트 통과"
  - "cross-service contract / 서비스 간 계약 유효성"
  - "DB transaction / migration 안전성"
  - "async task idempotency / 비동기 작업 멱등성"

teamer:                     # Teamer 연동 (task-import/sync) — 쓸 경우 필수
  project_no: "996"
  workitem_no: "188180"
  workflow_no: "164489"     # 상태 전이 시 사용

handoff:                    # 인수인계 — task-sync 가 Teamer 필드에 쓸 내용 (§7)
  summary:                  # 기본 AI 요약
    enable: true
    author: AI              # AI/LLM/Agent → AI 대필 / 그 외 → 사람 이름
    AskUserQuestion: false  # true 면 실행 시 입력/지침을 물음
    field: item_content     # item_content → 뒤에 추가(append)
    template: handoff/summary.html
  qa:                       # 신규 종류 예시
    enable: false
    author: AI
    AskUserQuestion: true
    field: col22            # colXX → 해당 필드만 덮어쓰기(replace)
    instruction: "QA 인수인계 — 테스트 범위, 재현 절차, 리스크 포인트"

doc_sync:                   # doc-sync 대상
  index: CLAUDE.md
  dirs:
    - "docs/"
    - ".claude/rules/"
  service_docs: "services/*/CLAUDE.md"
```

### 위험도 등급과 게이트

| 등급 | 언제 | 필수 게이트 |
|------|------|------------|
| `docs` | 코드 없는 변경(문서·주석·설정값) | doc-sync |
| `dev` | 코드 포함 변경(feature/fix) | 정적 분석 · 도메인 리뷰 · doc-sync |
| `staging` | QA/RC 승격(integration→staging) | 정적 분석 · 도메인 리뷰 · 전체 모듈 보안 스캔(security-scan) |
| `release` | 프로덕션 배포(staging→production) | staging 게이트 전부 + 보안 리뷰(security) |

> 위험도 분류 기준은 룰 `risk-tiers`가 단일 기준이며, 세션마다 자동으로 주입됩니다.

> 성능·통합 검증은 게이트에서 분리되어 **수동 스킬** `/performance`·`/integration` 으로
> 제공됩니다(비강제 — 승격 전 권장).

---

## 5. 일상 작업 — `/vdev`

```text
/vdev <자유 텍스트 요청 | Teamer 작업 번호(예: DEV-0952)>
```

`/vdev`를 치면 다음 순서로 진행됩니다:

1. **입력 해석** — `DEV-0952` 같은 작업 번호면 먼저 `/task-import`로 Teamer 컨텍스트를
   가져오고, 끝날 때 `/task-sync`로 결과를 올립니다. 그 외에는 요청 텍스트로 처리합니다.
2. **위험도 분류** — 실제 변경이 **코드냐 아니냐**로 Docs/Dev를 나눕니다.
   - 문서·주석·설정값만 → **Docs**
   - `.py`/`.js`/`.ts`… 코드, 신규 기능, DB 스키마, 의존성 변경 등 → **Dev**
3. **등급 확인** — 분류 결과를 묻고(오버라이드 가능), 확정 후 작업을 시작합니다.
   불확실하면 한 단계 위로 잡습니다.
4. **실행** — 등급별 절차와 게이트를 수행합니다.
   - **Docs**: 직접 편집 → `/doc-sync`로 문서 정합화 → 커밋
   - **Dev**: `superpowers` 파이프라인(설계→계획→구현→검증→리뷰) → 도메인 리뷰
     (`review_checklist` 점검) → `/doc-sync` → 커밋. 필수 게이트를 통과하지 않으면 커밋이
     막힙니다.
5. **마무리** — 작업 번호였다면 `/task-sync`로 결과를 동기화합니다.

> **승격(Staging/Release)**: integration→staging, staging→production 머지는 **타깃 브랜치**가
> 등급을 결정합니다(별도 표시 불필요). 각 등급의 필수 게이트(§4 표)를 통과해야 커밋됩니다.

> **Dev에는 `superpowers` 플러그인이 필요**합니다. 미설치면 `/vdev`가 중단하고 설치를
> 안내합니다 — 수동 구현으로 건너뛰지 마세요.

> **`/vdev`는 건너뛸 수 없습니다.** `/vdev`를 거치지 않고 커밋하면 등급 마커가 없어
> **미분류 커밋**으로 커밋 게이트가 막습니다(`/vdev`로 분류하면 풀립니다). 강제가
> 불필요한 저장소라면 `/vdev-uninstall`로 게이트 자체를 제거하세요.

---

## 6. `/harness-init` — 프로젝트 하네스 생성

```text
/harness-init        # 인자 없음 — 대화형 마법사
```

프로젝트에 맞는 `CLAUDE.md`·규칙·기술 문서를 만들어 줍니다. `/vdev-init`(거버넌스 배선)과는
**독립적인 별개 커맨드**입니다. 진행 순서:

1. **프레임워크 감지** — 의존성 파일(`package.json`·`pyproject.toml`·`go.mod` 등)과 디렉터리를
   분석해 언어·프레임워크를 판별합니다.
2. **리서치** — 최신 컨벤션·베스트 프랙티스·무료 기성 솔루션을 웹에서 조사하고, 기존 코드가
   있으면 그 코드의 실제 컨벤션도 함께 분석합니다. 버전은 *각 구성요소의 최신*을 따로 고르지 않고
   **함께 기동되는 호환 집합**으로 고릅니다 — 상위 프레임워크 메이저를 아직 지원하지 않는 엔진/스타터가
   있으면 본체 버전을 그 천장에 맞춰 내려 권고하고, 근거를 호환성 매트릭스로 남깁니다.
3. **생성** — `CLAUDE.md`·규칙·기술 문서(요구사항(SRS)·설계(SDS)·코드 스타일·온보딩 등)를 분류별
   폴더로 만듭니다. 기본은 **`.md` 파일만** 만들고, 실제 설정 파일은 건드리지 않습니다.
   에러 처리·로깅·시크릿 관리 등 운영 cross-cutting 컨벤션도 표준·출처와 함께 생성됩니다(언어/계층별 게이트 포함, directive=룰/표준=문서로 분리).
4. **검증** — 생성물의 품질·일관성·버전 호환성을 점검하고 필요 시 다듬습니다. 버전 호환성은 설정
   작성 정합뿐 아니라 **런타임 조합 호환**(구성요소가 함께 기동되는가, 스톡 이미지가 가정한 확장·실행
   모드를 실제로 제공하는가)까지 봅니다 — "빌드는 되는데 기동이 깨지는" 조합을 미리보기에서 드러냅니다.
   일관성 점검도 문서 간 정합을 넘어 **다중 컴포넌트의 런타임 통합 정합**(컴포넌트 간 통신이 실제로
   배선되는가 — issuer 도달성·보안 헤더/CSP 연속성·교차 오리진·자격증명 프로비저닝)까지 봅니다.
5. **미리보기 후 확정** — 무엇을 만들지 먼저 보여주고, **확정해야 비로소 파일을 씁니다.**
6. **정리(cleanup)** — 파일을 쓴 뒤, 작업 중 만든 임시 리서치 사본 등을 정리합니다. 최종 문서는
   남고, 나중에 헷갈릴 중간 산출물만 제거합니다.

- **덮어쓰기 없음** — 기존 파일은 관리 블록 단위로만 갱신하고, 충돌은 보고합니다.
- 보안 스캐너·CI·실제 폴더 생성·버전 고정 같은 **실제 설정**은 인터뷰에서 **항목별로 동의할
  때만** 적용합니다.
- 슬래시 커맨드는 생성하지 않습니다.

| | `/vdev-init` | `/harness-init` |
|---|---|---|
| 목적 | 거버넌스 배선 (게이트·Teamer·Teams) | 프로젝트 하네스(`CLAUDE.md`·문서) 생성 |
| 언제 | 저장소 설정 시 1회 | 신규·기존 저장소 언제든 |

---

## 7. Teamer 연동

### 계정 — OS 키체인(keyring)

최초 1회 터미널에서 `python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" setup` 을 실행한다.
기존 `teamer_account.md` 가 있으면 자동 이전 후 삭제하고, 없으면 getpass 로 입력받는다.
자격증명은 키체인에 저장되어 세션·재부팅과 무관하게 유지된다(재입력 불필요). 비밀은 평문 파일·
대화에 남지 않는다. `keyring` 미설치 시 `python3 -m pip install keyring`.

### `/task-import <작업 번호>`

1. 계정과 `vdev-config.teamer` 번호로 Teamer 항목을 검색합니다.
2. 작업 브랜치를 만들고 체크아웃합니다(`feature/{번호}-{english-title}`, **영문 제목**).
3. `docs/tasks/{사용자}/{번호}_{제목}.md` 문서를 만듭니다(`## Content`만 채우고 나머지는 빈 틀).

### `/task-sync <작업 번호>`

1. 작업 문서를 찾아 요약/인수인계 내용을 만들고, **미리보기로 확인**받습니다.
2. Teamer 항목을 검색해 **기존 내용을 보존**한 채 업데이트합니다.
3. 상태를 전이합니다("진행" → "검토" 등).

### 인수인계(handoff) — 종류별로 Teamer 필드에 전달

`/task-sync`는 "인수인계"를 **종류별로** 정의해 각각 다른 Teamer 필드에 쓸 수 있습니다(기본
AI 요약도 `summary`라는 한 종류입니다). 설정은 `vdev-config.yaml`의 `handoff` 트리(§4)입니다.

**내용 출처** — `author`가 AI인지 × `AskUserQuestion` 토글의 조합으로 결정됩니다:

| author | AskUserQuestion | 내용 출처 |
|--------|:---------------:|-----------|
| AI | false | AI가 작업 문서를 보고 **자동 생성** (기본 동작) |
| AI | true | 입력한 **작성 지침**대로 AI가 대필 |
| 사람 | true | 실행 시 **즉석 입력**을 그대로 |
| 사람 | false | 작업 문서의 `## Handoff (<종류>)` **내용을 그대로** |

**쓰기 모드** — `field`가 `item_content`면 **뒤에 추가**, `colXX`면 **그 필드만 덮어쓰기**.

> `handoff` 설정이 아예 없으면 기존처럼 AI 요약이 동작합니다(무중단). `qa` 같은 새 종류는
> `enable: true`라야 켜집니다.

---

## 8. Teams 알림

입력을 기다릴 때나 원하는 시점에 Teams 채널로 알립니다.

### 준비 — 채널별 웹훅 URL 발급

쓸 채널(개인·브랜치)마다 Teams의 **incoming webhook URL**을 발급받습니다(Power Automate
workflow로 만든 URL — `sig=` 토큰 포함). 발급한 URL을 아래 파일에 등록하면 됩니다. 채널은
점진적으로 켤 수 있어, 처음엔 개인 채널만 두고 나중에 브랜치 채널을 더해도 됩니다.

### 웹훅 설정 — 2개 파일

| 파일 | 추적 | 채널 |
|------|------|------|
| `.claude/vway-kit/config/teams-webhooks.json` | git 추적 | 팀 공용 채널(dev/stage/main 등) |
| `.claude/vway-kit/config/.teams-webhooks.local.json` | gitignored | 개인 채널(`personal`) |

```bash
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
# 채널 URL 등록
python3 "${ROOT}/.claude/vway-kit/scripts/teams_alert.py" --set personal https://...
# 수동 알림
python3 "${ROOT}/.claude/vway-kit/scripts/teams_alert.py" --channel personal --title "..." --text "..."
```

채널 URL이 비어 있으면 **조용히 건너뜁니다**(점진적으로 켤 수 있음). 알림 실패는 작업을 막지
않습니다.

- **자동** — 권한/입력 대기 시 `personal` 채널로 알림이 갑니다.
- **수동(옵션 제시 직전)** — `AskUserQuestion`은 자동 알림을 띄우지 않으므로, 입력을 기다리기
  직전 위 명령으로 직접 알립니다.

> Teams 채널을 설정하면 `/vdev-init`이 호스트 `CLAUDE.md`에 알림 안내 블록을 자동으로 넣어,
> 저장소의 Claude가 입력 대기 시 스스로 알리게 합니다(호스트 문서 언어에 맞춰 번역).

---

## 9. `doc-sync` 스킬

코드와 문서 변경을 분석해 관련 문서를 갱신하고 문서 집합을 일관되게 맞춥니다.

- **코드 → 문서**: 바뀐 코드의 키워드(클래스/필드/타입/route/함수)로 관련 문서를 찾아 해당
  부분을 갱신합니다.
- **문서 → 문서**: `vdev-config.doc_sync` 대상(index/dirs/service_docs)의 상호 참조·사실
  일관성·인덱스 동기화를 점검합니다. `service_docs`에 매칭되는 모듈에 로컬 `CLAUDE.md`가
  없으면 베스트 프랙티스 템플릿으로 새로 생성하고, 있으면 품질 기준(명령 정확성·구조 설명·
  게치 기록·간결성·최신성)에 맞춰 부족한 부분만 보완합니다(기존 내용은 보존).

`/vdev`가 자동으로 호출합니다. 계획만 보려면 "doc-sync preview"라고 하세요.

---

## 10. 문제 해결

### 커밋이 막혀요 — "python3 / PyYAML 필요"

게이트는 `python3`(3.8+)와 `PyYAML`을 씁니다(프로젝트 언어와 무관). 없으면 **일부러 커밋을
막습니다**(조용히 검사가 빠지는 것을 방지). 해결:

```bash
python3 -m pip install pyyaml        # 훅이 부르는 python3 환경에 설치
bash .claude/vway-kit/scripts/check-deps.sh   # 무엇이 빠졌는지 점검
```

> `uv add`는 가상환경에만 들어가 훅이 못 볼 수 있으니, 위처럼 `python3 -m pip`로 설치하세요.

### Dev 작업인데 절차가 안 돌아요

`superpowers@claude-plugins-official` 플러그인이 설치돼야 합니다. 미설치면 `/vdev`가 중단하고
안내합니다 — 수동 구현으로 건너뛰지 마세요.

### 새 PC에서 `marketplace add` 가 실패해요 — Host key / Permission denied

비공개 저장소를 SSH로 받기 위한 §2 1) 준비가 빠진 경우입니다. 증상별로:

- **`Host key verification failed` / `No ED25519 host key is known`** — 그 PC의
  `known_hosts` 에 github.com 이 없습니다. 터미널에서 `ssh -T git@github.com` 을 한 번
  실행해 fingerprint(`SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU`) 확인 후 `yes`.
  Claude Code 의 `add` 는 비대화형이라 이 프롬프트를 못 띄웁니다.
- **`Permission denied (publickey)`** — host key 는 등록됐지만 이 PC의 SSH 키가 GitHub
  계정에 없거나(§2 1-2), 계정이 저장소 접근 권한이 없습니다(조직 초대·Read 권한 확인).
- **둘 다 정상인데 HTTPS로 새는 경우** — 전역 `insteadOf` 가 github.com 을 HTTPS로
  치환하면 SSH 키가 무력화됩니다. 그 경우 토큰(HTTPS) 경로를 쓰거나 치환을 푸세요.

> `git config user.name`(커밋 author)이 GitHub 계정에 로그인돼 있다고 SSH 접근이 되는 게
> 아닙니다 — SSH 는 그 PC의 `known_hosts` + 키 쌍을 봅니다(별개 메커니즘).

### 자동 업데이트가 안 돼요

새 버전이 자동으로 안 받아지면 GitHub 토큰 설정이 빠졌거나 SSH 치환과 충돌한 경우가 대부분입니다.
[README의 "자동 업데이트 설정"](README.md#자동-업데이트-설정-비공개-저장소)의 확인 명령으로 점검하세요.
급하면 수동으로: `/plugin marketplace update vway`.

### 저장소가 조직/다른 owner로 옮겨졌어요 (기존 설치자)

플러그인 저장소의 owner·경로가 바뀌면(예: 조직 `Developments-3`로 이전), **이미 설치한
사용자**의 `settings.json`에 박힌 마켓 source repo는 **자동으로 갱신되지 않습니다**(설치
시점 값으로 고정). 그 상태로 두면 자동 업데이트가 옛 경로를 향해 (특히 비공개+토큰 인증에서)
조용히 스킵됩니다. `/vdev-init`은 **기존 등록의 source를 보존**하므로 이걸로는
안 바뀝니다 — 직접 갱신하세요:

1. **`extraKnownMarketplaces`가 있는 settings.json 직접 수정** — 등록 위치는 **설치 방식에 따라
   다릅니다**. **프로젝트부터 확인하고, 없으면 유저 글로벌**을 보세요(둘 다 있으면 프로젝트가 우선):
   - **프로젝트** `${CLAUDE_PROJECT_DIR}/.claude/settings.json` — `/vdev-init`이 등록하는 경우
   - **유저 글로벌** `~/.claude/settings.json` (Windows `C:\Users\<사용자>\.claude\settings.json`)
     — `/plugin marketplace add`로 **사용자 단위** 설치한 경우

   `extraKnownMarketplaces`가 들어 있는 쪽에서 `vway.source.repo`를 새 경로로:
   ```json
   "vway": { "source": { "source": "github", "repo": "Developments-3/vway-kit" }, "autoUpdate": true }
   ```
2. **마켓 제거 후 재등록** — `/plugin marketplace remove vway` → `/plugin marketplace add <새 경로>`
   (등록 위치를 Claude Code가 알아서 처리하므로, 위 프로젝트/글로벌 위치를 신경 쓰기 싫으면 이쪽)

이후 토큰 권한·`insteadOf` 예외도 새 경로 기준으로 맞추고 호스트를 완전히 재시작하세요
([README의 "자동 업데이트 설정"](README.md#자동-업데이트-설정-비공개-저장소)).

### `git commit`을 언급만 했는데 차단돼요

커밋 게이트는 명령에 `git commit` 문자열이 있으면 매칭합니다. 그 문자열을 단순히 언급하는
명령(`grep "git commit"` 등)도 막힐 수 있습니다 — 정상 동작입니다.

> 게이트가 *왜* 그렇게 동작하는지(검증 2레이어·Windows 인코딩·파일 전파 등 내부 원리)는
> 개발자용 [CLAUDE.md](CLAUDE.md)에 정리돼 있습니다.

---

## 11. 갱신·제거

### flow → vdev 업그레이드 (기존 설치자)

`flow`가 `vdev`로 재명명되었습니다. 플러그인 업데이트 후 기존 호스트는 **`/vdev-init`을 재실행**하세요 —
settings.json 게이트 훅의 스크립트 경로(`vdev_gate_check.py`)·증거 디렉터리(`.vdev/`)·설정 파일
(`vdev-config.yaml`)을 재복사·보정합니다(멱등). 구 `flow-config.yaml`(팀 설정)·`.flow/`(증거)는
vdev-init이 자동으로 `vdev-config.yaml`·`.vdev/`로 **무손실 이전**하고, 옛 스크립트 사본
(`flow_gate_check.py` 등)도 정리합니다. 진행 중이던 작업에 구 등급 마커(`fast`/`standard`)가 남아 있어도
게이트에서 **무시(fail-open)** 되어 작업을 막지 않지만, 정확한 분류를 위해 `/vdev`로 다시 분류하세요(`docs`/`dev`).

### `/vdev-init` 재실행 — 플러그인 갱신 후 동기화

플러그인이 업데이트돼도 호스트의 스크립트 사본은 자동으로 바뀌지 않습니다(복사본이라서).
`/vdev-init`을 다시 실행하면 스크립트·정책 파일을 다시 복사하고 게이트 경로를 보정합니다
(재동기화는 비대화로 항상 먼저 실행). 빠진 config 슬롯이 있으면 보충을 제안하고, 그 외에는
무엇을 재설정할지 물어봅니다(아무것도 안 고르면 재동기화만). 예전 `/vdev-upgrade`는 여기에
통합되었습니다.

### `/vdev-uninstall` — 호스트 배선 제거

`/plugin uninstall`은 캐시만 지우고, `/vdev-init`이 호스트에 쓴 것은 남습니다.
`/vdev-uninstall`이 그걸 정리합니다(확인 후): 커밋 게이트·마켓 등록 해제, `.gitignore`/`CLAUDE.md`
관리 블록 제거, `.claude/vway-kit/` 삭제.

> ⚠️ **순서가 중요합니다.** 정리 도구가 플러그인 안에 있으므로 **`/plugin uninstall` 전에
> `/vdev-uninstall`을 먼저** 실행하세요. 이미 플러그인을 지웠다면 수동 정리: `rm -rf
> .claude/vway-kit/` + 등록 4곳(settings.json 게이트·마켓, `.gitignore`, `CLAUDE.md` 블록) 제거.

---

## 라이선스

VWAY Corporation Proprietary (사내 전용).
