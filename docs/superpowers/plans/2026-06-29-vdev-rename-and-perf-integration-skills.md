# vdev 재명명 + performance/integration 스킬 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** vway-kit의 `flow` 패밀리를 `vdev`로 클린 교체하고, performance·integration을 게이트에서 분리해 사전 리서치 SSOT에 근거한 독립 스킬로 신설한다.

**Architecture:** 5단계 — (1) 재명명+티어정책, (2) performance 스킬, (3) integration 스킬, (4) harness-researcher 확장, (5) 사용자 문서+마이그레이션. 각 단계는 독립 검증 가능한 산출물을 낸다. 재명명은 게이트 무결성을 우선해 먼저 한다.

**Tech Stack:** Python(uv·pytest·ruff), Bash(ShellCheck), YAML 정책, Markdown 컴포넌트(SKILL.md/agent.md), Claude Code 플러그인 규약.

**근거 스펙:** [2026-06-29-vdev-rename-and-perf-integration-skills-design.md](../specs/2026-06-29-vdev-rename-and-perf-integration-skills-design.md) — §10 SSOT 부록을 신규 스킬 references의 출처로 사용.

## Global Constraints

- **클린 교체** — 구 `flow`/`fast`/`standard` 이름은 완전 제거(하위호환 읽기 없음).
- **blanket 치환 금지** — `flow`는 `workflow`의 부분문자열, `fast`/`standard`는 흔한 영단어. 카테고리별 타깃 치환 후 `rg`로 잔존 검증.
- **이력 문서 보존** — `docs/superpowers/specs/`·`docs/superpowers/plans/`의 과거 `flow` 언급은 갱신하지 않는다(이 계획·스펙 파일 제외).
- **CLAUDE.md Invariants 절대 보존** — ①FAIL-OPEN+의존성/미분류 fail-CLOSED ②Windows 인코딩(`PYTHONUTF8=1`·`force_utf8_io()`·`encoding="utf-8"`) ③차단=exit 2+stderr ④settings.json 훅에 `if` 금지 ⑤`/vdev-init` 멱등 ⑥Teamer 자격증명 keyring.
- **경로 규약** — `${CLAUDE_PLUGIN_ROOT}`=읽기, `${CLAUDE_PROJECT_DIR}`=쓰기. 플러그인 디렉터리에 쓰지 않는다.
- **커맨드 미생성** — 신규 산출물은 skill/agent/문서만. `.claude/commands/` 금지.
- **무료·상용가능 OSS만** — 유료/SaaS 제외. 라이선스 불명확은 "확인 필요".
- **검증 명령** — `uv run pytest` · `uv run ruff check && uv run ruff format --check` · `*.sh`는 ShellCheck · `uv run pre-commit run --all-files`.
- **출력 언어 한글** — 모든 .md 컴포넌트 본문은 한글(고유명/식별자/URL은 원형).

---

## Phase 1 — 재명명 + 티어 정책

### Task 1: 디렉터리·파일 git mv (스킬/스크립트/설정/테스트)

**Files:**
- Rename: `skills/flow/` → `skills/vdev/`
- Rename: `skills/flow-init/` → `skills/vdev-init/`
- Rename: `skills/flow-uninstall/` → `skills/vdev-uninstall/`
- Rename: `flow-tiers.yaml` → `vdev-tiers.yaml`
- Rename: `flow-config.example.yaml` → `vdev-config.example.yaml`
- Rename: `scripts/flow_gate_check.py` → `scripts/vdev_gate_check.py`
- Rename: `scripts/flow_init_setup.py` → `scripts/vdev_init_setup.py`
- Rename: `tests/test_flow_gate_check.py` → `tests/test_vdev_gate_check.py`
- Rename: `tests/test_flow_init_setup.py` → `tests/test_vdev_init_setup.py`

- [ ] **Step 1: git mv (내용 보존, 히스토리 추적)**

```bash
cd "$(git rev-parse --show-toplevel)"
git mv skills/flow skills/vdev
git mv skills/flow-init skills/vdev-init
git mv skills/flow-uninstall skills/vdev-uninstall
git mv flow-tiers.yaml vdev-tiers.yaml
git mv flow-config.example.yaml vdev-config.example.yaml
git mv scripts/flow_gate_check.py scripts/vdev_gate_check.py
git mv scripts/flow_init_setup.py scripts/vdev_init_setup.py
git mv tests/test_flow_gate_check.py tests/test_vdev_gate_check.py
git mv tests/test_flow_init_setup.py tests/test_vdev_init_setup.py
```

- [ ] **Step 2: 이동 확인**

Run: `git status --short && ls skills`
Expected: 위 파일들이 R(renamed)로 표시, `skills/`에 `vdev`·`vdev-init`·`vdev-uninstall` 존재, `flow*` 없음.

> 커밋은 Task 9(게이트 통과)에서. 여기서는 커밋하지 않는다(dev 티어 게이트 미충족).

---

### Task 2: 티어 정책 `vdev-tiers.yaml` 재작성

**Files:**
- Modify: `vdev-tiers.yaml` (전체)

**Interfaces:**
- Produces: 티어 키 `docs`·`dev`·`staging`·`release`. `vdev_gate_check.py`(Task 5)와 `risk-tiers.md`(Task 6)가 이 키에 defer.

- [ ] **Step 1: 파일 내용 교체**

```yaml
# vdev 위험도 티어 정책 (불변, 플러그인 소유)
# Risk-tiered workflow tier definitions for vway-kit plugin

tiers:
  docs:
    description: "코드 없는 변경 (문서, 주석, 설정값만)"
    superpowers: false
    gates:
      - doc-sync

  dev:
    description: "코드 포함 변경 (feature/fix 브랜치, 통합 머지 전)"
    superpowers: true
    gates:
      - precommit
      - review
      - doc-sync

  staging:
    description: "QA/RC 승격 (dev → stage)"
    superpowers: true
    gates:
      - precommit
      - review

  release:
    description: "프로덕션 배포 (stage → main 또는 오프라인 배포)"
    superpowers: true
    gates:
      - precommit
      - review
      - security
```

- [ ] **Step 2: YAML 파싱 검증**

Run: `uv run python -c "import yaml,io; print(list(yaml.safe_load(open('vdev-tiers.yaml'))['tiers']))"`
Expected: `['docs', 'dev', 'staging', 'release']`

---

### Task 3: 설정 템플릿 `vdev-config.example.yaml` 헤더 갱신

**Files:**
- Modify: `vdev-config.example.yaml:1-4` (주석 헤더의 경로명)

- [ ] **Step 1: 헤더 경로명 치환**

`flow-config.yaml` → `vdev-config.yaml` 로 헤더 주석을 수정한다. 1-2행을 다음으로:

```yaml
# vdev 위험도 티어 환경 설정 템플릿
# 프로젝트 팀이 호스트의 .claude/vway-kit/config/vdev-config.yaml 로 복사하여 값을 채운다.
```

> `test.command`의 `-m 'not integration'`(pytest 마커)은 **건드리지 않는다** — 신규 integration 스킬과 무관.

- [ ] **Step 2: 잔존 확인**

Run: `rg -n "flow-config" vdev-config.example.yaml`
Expected: 매치 없음.

---

### Task 4: `scripts/vdev_gate_check.py` 내부 갱신 (티어 값·경로·식별자)

**Files:**
- Modify: `scripts/vdev_gate_check.py`
- Test: `tests/test_vdev_gate_check.py`

**Interfaces:**
- Consumes: `vdev-tiers.yaml`(Task 2) 티어 키, `.claude/vway-kit/.vdev/tier` 마커.
- Produces: 허용 마커 값 `docs|dev`(staging/release는 브랜치 구동). 미분류=fail-CLOSED 유지.

- [ ] **Step 1: 실패 테스트 갱신/작성 (TDD)**

`tests/test_vdev_gate_check.py`에서 구 `fast`/`standard` 마커를 쓰는 케이스를 `docs`/`dev`로 갱신하고, 신규 케이스 추가:

```python
def test_docs_tier_requires_only_doc_sync(tmp_flow):
    write_marker(tmp_flow, "docs:feature/x")
    write_policy_tier("docs", gates=["doc-sync"])
    # doc-sync.done 없으면 차단
    assert run_gate(tmp_flow, files=["README.md"]).exit_code == 2

def test_dev_tier_requires_review_and_doc_sync(tmp_flow):
    write_marker(tmp_flow, "dev:feature/x")
    write_policy_tier("dev", gates=["precommit", "review", "doc-sync"])
    touch(tmp_flow, "review.done"); touch(tmp_flow, "doc-sync.done")
    assert run_gate(tmp_flow, files=["src/a.py"]).exit_code == 0

def test_unclassified_commit_blocks(tmp_flow):
    # tier 마커 없음 + 정책/설정 파싱 성공 → fail-CLOSED
    assert run_gate(tmp_flow, files=["src/a.py"]).exit_code == 2
```

(헬퍼 이름은 기존 테스트 파일의 실제 픽스처에 맞춘다 — 읽고 따른다.)

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_vdev_gate_check.py -v`
Expected: 신규/갱신 테스트 FAIL(스크립트가 아직 `docs|dev` 미인식).

- [ ] **Step 3: 스크립트 내부 식별자·값 치환**

`scripts/vdev_gate_check.py`에서 다음을 타깃 치환(읽고 정확히):
- 증거 경로 `.claude/vway-kit/.flow` → `.claude/vway-kit/.vdev`
- 정책 파일 참조 `flow-tiers.yaml` → `vdev-tiers.yaml`
- 설정 파일 참조 `flow-config.yaml` → `vdev-config.yaml`
- 허용 티어 마커 값 집합 `{"fast","standard"}` → `{"docs","dev"}` (구 값 제거)
- 주석/메시지의 `/flow` → `/vdev`
- Invariant 보존: `force_utf8_io()`·`PYTHONUTF8`·`encoding="utf-8"`·exit 2·fail-OPEN/fail-CLOSED 로직 그대로.

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_vdev_gate_check.py -v`
Expected: PASS.

---

### Task 5: `scripts/vdev_init_setup.py` + 나머지 스크립트 내부 갱신

**Files:**
- Modify: `scripts/vdev_init_setup.py`
- Modify: `scripts/precommit-runner.sh`, `scripts/check-deps.sh`, `scripts/_vway_paths.py`
- Modify: `hooks/inject-risk-tiers.sh`, `hooks/hooks.json`(해당 시)
- Test: `tests/test_vdev_init_setup.py`, `tests/test_vway_paths.py`

**Interfaces:**
- Consumes: settings.json 훅 등록 시 `vdev_gate_check.py` 경로, 복사 소스 `vdev-tiers.yaml`.
- Produces: 호스트 `.claude/vway-kit/scripts/` 사본, `.vdev/` 증거 경로, 멱등 등록.

- [ ] **Step 1: 실패 테스트 갱신**

`tests/test_vdev_init_setup.py`·`tests/test_vway_paths.py`에서 `flow_gate_check`·`flow-tiers.yaml`·`.flow/`·`flow-config` 참조를 `vdev_*`·`.vdev/`·`vdev-config`로 갱신.

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_vdev_init_setup.py tests/test_vway_paths.py -v`
Expected: FAIL.

- [ ] **Step 3: 스크립트 타깃 치환**

각 파일에서:
- `flow_gate_check.py` → `vdev_gate_check.py`, `flow_init_setup.py` → `vdev_init_setup.py`
- `flow-tiers.yaml` → `vdev-tiers.yaml`, `flow-config.yaml` → `vdev-config.yaml`, `flow-config.example.yaml` → `vdev-config.example.yaml`
- `.claude/vway-kit/.flow` → `.claude/vway-kit/.vdev`
- `_vway_paths.py`의 `.flow` 경로 상수 → `.vdev`
- `inject-risk-tiers.sh`의 `/flow` 안내·`risk-tiers.md` 주입은 텍스트만 `/vdev`로
- 멱등 가드(match-then-skip)·exit code·ShellCheck 청결 보존

- [ ] **Step 4: 테스트 + ShellCheck 통과**

Run: `uv run pytest tests/test_vdev_init_setup.py tests/test_vway_paths.py -v`
Expected: PASS.
Run: `bash -c 'command -v shellcheck && shellcheck scripts/precommit-runner.sh scripts/check-deps.sh hooks/inject-risk-tiers.sh'`
Expected: 경고 없음(설치 시).

---

### Task 6: 룰·매니페스트·CI 소스의 `flow`→`vdev`·티어명 갱신

**Files:**
- Modify: `rules/risk-tiers.md`, `rules/harness-rules.md`
- Modify: `skills/vdev/SKILL.md`, `skills/vdev-init/SKILL.md`, `skills/vdev-uninstall/SKILL.md`, `skills/doc-sync/SKILL.md`, `skills/task-import/SKILL.md`, `skills/task-sync/SKILL.md`, `skills/harness-init/SKILL.md`, `skills/harness-authoring/SKILL.md`
- Modify: `.gitignore`, `pre-commit-hooks.example.yaml`, `github/api-contract.workflow.example.yml`, `.claude-plugin/marketplace.json`(필요 시)

**Interfaces:**
- Produces: 모든 활성 컴포넌트가 `/vdev`·`vdev-*`·`docs`/`dev` 티어명으로 일관.

- [ ] **Step 1: 카테고리별 타깃 치환 (파일별로 읽고 정확히)**

문자열 치환 카테고리:
- `/flow-init` → `/vdev-init`, `/flow-uninstall` → `/vdev-uninstall`, `/flow` → `/vdev` (긴 것 먼저)
- 상대경로 링크 `../flow/SKILL.md` → `../vdev/SKILL.md`, `../skills/flow/` → `../skills/vdev/`, `flow-init`/`flow-uninstall` 디렉터리 링크 동일
- `flow-tiers.yaml`→`vdev-tiers.yaml`, `flow-config.yaml`→`vdev-config.yaml`, `flow_gate_check.py`→`vdev_gate_check.py`, `.claude/vway-kit/.flow`→`.claude/vway-kit/.vdev`
- 산문 "flow 스킬"/"the flow command"/"flow 게이트" → "vdev …" (단 **workflow는 보존** — 단어경계 확인)
- `.gitignore`: `.claude/vway-kit/.flow/` → `.claude/vway-kit/.vdev/`

티어명 치환(`risk-tiers.md` 중심, 문맥 확인하며):
- 티어로 쓰인 `Fast`/`Fast tier` → `Docs`, `Standard`/`Standard tier` → `Dev` (일반 영단어 "fast"/"standard"가 아닌 **티어 명칭**만)
- `flow-tiers.yaml`·`risk-tiers.md` 표/예시의 `fast`/`standard` 코드값 → `docs`/`dev`

- [ ] **Step 2: performance/integration 게이트 분리 문서화**

`rules/risk-tiers.md`의 staging/release 절에서 performance·integration을 **게이트 목록에서 제거**하고, 다음 취지의 문단을 추가:

> 성능·통합 검증은 게이트(강제)가 아니라 **독립 스킬**(`/performance`, `/integration`)로 비강제 수행한다. 승격 전 권장하되 커밋을 차단하지 않는다.

- [ ] **Step 3: 잔존 검증 (핵심 게이트)**

Run: `rg -n --glob '!docs/superpowers/**' '\bflow\b|/flow|flow-tiers|flow-config|flow_gate|flow_init|\.flow/|flow-init|flow-uninstall' .`
Expected: 매치 없음(있으면 누락 — 수정). `workflow`는 매치되면 안 됨(단어경계 `\bflow\b`라 제외됨).

Run: `rg -n --glob '!docs/superpowers/**' -e '\bFast tier\b' -e '\bStandard tier\b' rules/ skills/`
Expected: 매치 없음.

---

### Task 7: 플러그인 매니페스트 정합성 확인

**Files:**
- Read/verify: `.claude-plugin/plugin.json`, `.claude-plugin/marketplace.json`

- [ ] **Step 1: 매니페스트 경로 미선언 확인**

Run: `rg -n "skills|agents|hooks|flow" .claude-plugin/plugin.json .claude-plugin/marketplace.json`
Expected: skills/agents/hooks 경로 미선언(자동 발견)·`flow` 잔존 없음. `flow`가 있으면 Task 6 누락.

> 디렉터리명이 자동 발견되므로 `skills/vdev/` 이동만으로 `/vdev` 호출명이 생긴다(매니페스트 수정 불필요).

---

### Task 8: Phase 1 전체 검증

- [ ] **Step 1: 전체 테스트·린트**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check`
Expected: 전부 PASS.

- [ ] **Step 2: 전역 잔존 스캔**

Run: `rg -n --glob '!docs/superpowers/**' '\bflow\b' . | rg -v 'workflow'`
Expected: 매치 없음.

---

### Task 9: Phase 1 게이트 통과 + 커밋

> 이 커밋이 dev 티어 게이트를 통과해야 한다 — review·doc-sync 마커 필요.

- [ ] **Step 1: doc-sync 게이트**

`doc-sync` 스킬을 호출해 README/USAGE/CLAUDE.md 등 문서가 코드 변경(재명명)과 정합한지 확인(실제 갱신은 Phase 5에서 마무리하되, 여기서는 재명명 정합성 확인). 통과 시:

```bash
mkdir -p .claude/vway-kit/.vdev && touch .claude/vway-kit/.vdev/doc-sync.done
```

- [ ] **Step 2: review 게이트**

독립 `general-purpose` 리뷰 에이전트로 재명명 diff를 `vdev-config.example.yaml`의 review_checklist + Invariants 보존 관점에서 검토. 통과 시 `touch .claude/vway-kit/.vdev/review.done`.

- [ ] **Step 3: 커밋**

```bash
git add -A
git commit -m "refactor(vdev): rename flow family to vdev, tiers fast/standard to docs/dev"
```
Expected: 커밋 hook(`vdev_gate_check`) 통과(마커 존재). 차단되면 누락 마커 점검.

---

## Phase 2 — `performance` 스킬

### Task 10: `performance` 스킬 골격 작성

**Files:**
- Create: `skills/performance/SKILL.md`
- Create: `skills/performance/references/static-checks.md` (스택별 안티패턴 SSOT)
- Create: `skills/performance/references/api-load.md` (OpenAPI 발견 + openapi-to-k6/k6 + 리포트 표준)

**Interfaces:**
- Produces: `/performance` (정식 `/vway-kit:performance`), 완전 수동.
- Consumes: 호스트 `docs/performance.md`(Phase 4, 있으면 우선), 없으면 references 폴백.

- [ ] **Step 1: SKILL.md frontmatter + 본문 작성**

frontmatter(공식 스펙 준수 — description은 핵심 유스케이스 앞, 1,536자 캡 내):

```markdown
---
name: performance
description: 코드베이스의 언어별 성능 안티패턴(N+1·쿼리플랜·재귀/복잡도·프론트 리렌더)을 정적으로 플래깅하고, 백엔드가 있으면 OpenAPI에서 API를 추출해 openapi-to-k6+k6로 각 API를 100회 부하 측정해 p50/p95/p99·throughput·에러율을 SLO 대비 보고한다. 게이트가 아닌 수동 스킬 — 성능 점검이 필요할 때 호출.
allowed-tools: Bash, Read, Grep, Glob, WebFetch
---
```

본문 구조(스펙 §5.2 그대로, 한글):
1. 스택 감지 → 호스트 `docs/performance.md` 우선, 없으면 `references/` 폴백.
2. 언어별 정적 플래깅 — `references/static-checks.md`로 defer. **포지셔닝 명시**: 확정 탐지 아님, "의심 플래깅 → 런타임 검증", false positive는 "검토 요망".
3. 백엔드 시 API 부하 — `references/api-load.md`로 defer.
4. 리포트 표준(평균 단독 금지, p50/p95/p99(+p99.9)·throughput·VU·에러율·SLO PASS/FAIL, 측정 메타 기록).

- [ ] **Step 2: `references/static-checks.md` 작성 (스펙 §10.1~§10.4 SSOT)**

스택별 표(Python/Node/React/Java/Ruby/.NET/Go/DB) — 각 행에 탐지할 정적 패턴 + 올바른 형태 권고 + SSOT URL/라이선스. React Compiler v1.0 활성 시 메모룰 완화 분기 명시. 순환복잡도≠Big-O 단서.

- [ ] **Step 3: `references/api-load.md` 작성 (스펙 §10.5~§10.6 SSOT)**

OpenAPI 자동 발견 후보 경로, `$ref` dereference, example override 규칙, **openapi-to-k6→k6 100회(iterations)** 1순위 + oha/autocannon MIT 폴백, 리포트 템플릿(Four Golden Signals·warm-up 제외·CO 보정·백분위 비가산성), 라이선스 표(AGPL 내부사용 무해 주석).

- [ ] **Step 4: frontmatter·링크 검증**

Run: `uv run python -c "import yaml; d=open('skills/performance/SKILL.md').read().split('---')[1]; print(yaml.safe_load(d)['name'])"`
Expected: `performance`.
Run: `rg -n "references/" skills/performance/SKILL.md`
Expected: static-checks.md·api-load.md 링크 존재(파일 실재).

- [ ] **Step 5: 커밋 (게이트)** — Phase 5와 함께 또는 단독. 신규 .md만이라 doc-sync 마커 후 커밋(아래 공통 커밋 절차 Task 17 참조).

---

## Phase 3 — `integration` 스킬

### Task 11: `integration` 스킬 골격 작성

**Files:**
- Create: `skills/integration/SKILL.md`
- Create: `skills/integration/references/web-playwright.md`
- Create: `skills/integration/references/non-web.md`

**Interfaces:**
- Produces: `/integration`, 완전 수동.
- Consumes: 호스트 `docs/integration.md`(Phase 4, 우선), 없으면 references 폴백.

- [ ] **Step 1: SKILL.md frontmatter + 본문**

```markdown
---
name: integration
description: 프로젝트가 웹 프론트면 기존 Playwright 케이스를 결정적으로 실행(--reporter=json)해 통합 검증 결과를 PASS/FAIL로 보고하고, 케이스가 없거나 웹이 아니면 사람에게 시나리오·통과 기준을 묻는다(human-in-the-loop). 게이트가 아닌 수동 스킬 — 통합 검증이 필요할 때 호출.
allowed-tools: Bash, Read, Grep, Glob, AskUserQuestion
---
```

본문(스펙 §6.1 그대로): 웹 감지(휴리스틱) → 웹이면 `playwright.config.*` 파싱·testDir/testMatch로 케이스 발견·`npx playwright test --reporter=json` 실행·결과 파싱. 케이스 0개면 임의 생성 금지→사람. 비웹이면 human-in-the-loop. playwright MCP는 보조 경로.

- [ ] **Step 2: `references/web-playwright.md` (스펙 §10.7)**

웹 감지 신호 화이트리스트, testDir/testMatch 기본값, `--reporter=json`(+junit) 실행·결과 JSON 파싱, best-practices, SSOT URL. "휴리스틱이라 단정 SSOT 아님" 단서.

- [ ] **Step 3: `references/non-web.md`**

비웹 타입 신호(CLI/RN/Flutter/Electron 예외), human-in-the-loop 절차(AskUserQuestion), 참고 OSS(Newman/Maestro/Appium, Apache-2.0) — 자동 강제 안 함.

- [ ] **Step 4: 검증**

Run: `uv run python -c "import yaml; print(yaml.safe_load(open('skills/integration/SKILL.md').read().split('---')[1])['name'])"`
Expected: `integration`.

---

## Phase 4 — `harness-researcher` 확장 + harness-init 연계

### Task 12: harness-researcher에 perf/integration 리서치 차원 추가

**Files:**
- Modify: `agents/harness-researcher.md`

**Interfaces:**
- Consumes: harness-init이 전달하는 확정 `stack_map`(Step 2.5 reconcile 후).
- Produces: 출력에 `### 성능 SSOT (스택별)`·`### 통합 검증 SSOT` 절.

- [ ] **Step 1: 절차·출력 형식에 차원 추가**

`## 절차`에 항목 추가: "확정된 (계층,스택)별로 **성능 SSOT**(N+1 탐지·프로파일러·정적 복잡도·DB 쿼리플랜·API 부하 openapi-to-k6+k6 또는 MIT 폴백)와 **통합 검증 SSOT**(웹=Playwright / 비웹=human-in-the-loop + 참고 OSS)를 출처·라이선스와 함께 조사한다."
`## 출력`에 두 절 추가(기존 형식 톤 유지, 항목당 1~2줄, 출처 필수, 유료 제외).

- [ ] **Step 2: 잔존·정합 확인**

Run: `rg -n "성능 SSOT|통합 검증 SSOT" agents/harness-researcher.md`
Expected: 두 절 존재.

---

### Task 13: harness-init/authoring이 docs/performance.md·docs/integration.md 생성

**Files:**
- Modify: `skills/harness-init/SKILL.md` (Step 2·Step 4 — 리서치 차원 주입 + 산출물 추가)
- Modify: `skills/harness-authoring/SKILL.md` 및 `references/tech-doc-guide.md` (신규 문서 종류)
- Modify: `rules/harness-rules.md` (산출물 목록에 perf/integration 문서)

- [ ] **Step 1: harness-init 산출물에 추가**

Step 1.3 산출물 선택지·Step 2 리서치 디스패치·Step 4 authoring에 "성능/통합 SSOT 문서(`docs/performance.md`·`docs/integration.md`, 확정 스택만)"를 추가. 빈 스택 절 생성 금지. 출처는 `docs/research/`로 링크.

- [ ] **Step 2: authoring 가이드 반영**

`tech-doc-guide.md`에 두 문서의 목적·구조(스택별 절 + 공통 API/E2E 절)를 추가.

- [ ] **Step 3: 검증**

Run: `rg -n "performance.md|integration.md" skills/harness-init/SKILL.md skills/harness-authoring/references/tech-doc-guide.md`
Expected: 참조 존재.

---

## Phase 5 — SRS/SDS 재명명 + 사용자 문서 + 마이그레이션

### Task 14: PRD→SRS, architecture→SDS 재명명

**Files:**
- Rename: `skills/harness-authoring/templates/prd.template.md` → `srs.template.md`
- Rename: `skills/harness-authoring/templates/architecture.template.md` → `sds.template.md`
- Modify: `skills/harness-authoring/SKILL.md`, `skills/harness-authoring/references/tech-doc-guide.md`, `skills/harness-init/SKILL.md`, `rules/harness-rules.md`, `skills/harness-authoring/templates/onboarding.template.md`, `claude-md.template.md`

- [ ] **Step 1: git mv**

```bash
git mv skills/harness-authoring/templates/prd.template.md skills/harness-authoring/templates/srs.template.md
git mv skills/harness-authoring/templates/architecture.template.md skills/harness-authoring/templates/sds.template.md
```

- [ ] **Step 2: 참조 치환**

`PRD`/`prd.template.md`/`prd` → `SRS`/`srs.template.md`/`srs`, `architecture.template.md`/"architecture 문서"/"아키텍처 문서" → `sds.template.md`/`SDS`. (문맥상 SDS는 "Software Design Specification". 산문에서 일반 단어 "architecture diagram" 같은 기술 표현은 보존하되, **산출물 명칭**만 SDS로.)

- [ ] **Step 3: 잔존 검증**

Run: `rg -n --glob '!docs/superpowers/**' '\bPRD\b|prd\.template|prd\b' .`
Expected: 매치 없음.
Run: `rg -n "architecture.template" . --glob '!docs/superpowers/**'`
Expected: 매치 없음.

---

### Task 15: 사용자 문서 갱신 (README/USAGE/CLAUDE.md)

**Files:**
- Modify: `README.md`, `USAGE.md`, `CLAUDE.md`(루트)

- [ ] **Step 1: 명령·티어·문서명 갱신**

`/flow`·`/flow-init`·`/flow-uninstall` → `/vdev`·`/vdev-init`·`/vdev-uninstall`, `Fast`/`Standard` 티어 → `Docs`/`Dev`, `flow-tiers.yaml`/`flow-config.yaml` → `vdev-*`, `.flow/` → `.vdev/`, PRD→SRS·architecture→SDS. CLAUDE.md의 Folder structure·Architecture·Invariants 절의 경로/이름 갱신.

- [ ] **Step 2: 신규 스킬·게이트 분리 반영**

`/performance`·`/integration` 스킬 설명 추가, staging/release 게이트에서 두 항목 제거를 README/USAGE에 반영.

---

### Task 16: 마이그레이션 노트 추가

**Files:**
- Modify: `USAGE.md` (마이그레이션 절 신설)

- [ ] **Step 1: 노트 작성**

> **flow→vdev 업그레이드**: 기존 호스트는 `/vdev-init` 재실행 — settings.json 게이트 훅의 스크립트 경로(`vdev_gate_check.py`)·증거 디렉터리(`.vdev/`)·설정(`vdev-config.yaml`)을 재복사/이전(멱등, config 무손상). 구 `.flow/`·`flow-config.yaml`은 `/vdev-uninstall` 후 제거. 진행 중 `flow` 마커가 남아 있으면 `docs`/`dev`로 재분류(`/vdev`).

---

### Task 17: 최종 전체 검증 + 게이트 커밋

- [ ] **Step 1: 전수 검증**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check && uv run pre-commit run --all-files`
Expected: 전부 PASS.
Run: `rg -n --glob '!docs/superpowers/**' '\bflow\b|\bPRD\b|fast tier|standard tier' . | rg -v 'workflow'`
Expected: 매치 없음.

- [ ] **Step 2: 신규 스킬 발견 확인**

Run: `ls skills`
Expected: `vdev vdev-init vdev-uninstall performance integration doc-sync task-import task-sync harness-init harness-authoring`.

- [ ] **Step 3: doc-sync + review 게이트 → 커밋**

`doc-sync` 스킬 통과 → `touch .claude/vway-kit/.vdev/doc-sync.done`. 독립 review 에이전트 통과 → `touch .claude/vway-kit/.vdev/review.done`.

```bash
git add -A
git commit -m "feat(perf,integration): add manual performance and integration skills with researched SSOTs"
```

- [ ] **Step 4: flow state 정리**

```bash
rm -rf .claude/vway-kit/.vdev
```

---

## Self-Review (작성자 체크)

**Spec coverage:** §3 재명명→Task 1·4·5·6·7, §4 티어→Task 2, §5 performance→Task 10, §6 integration→Task 11, §7 researcher→Task 12·13, §3.3 마이그레이션→Task 16, SRS/SDS(§3.1)→Task 14, 검증(§8)→Task 8·17. 전 항목 커버됨.

**Placeholder scan:** 구체 명령·치환 카테고리·검증 grep 제시. 대규모 리네임은 "카테고리별 타깃 치환 + grep 검증"으로 구체화(60개 파일 리터럴 덤프는 비현실적이라 검증 게이트로 대체).

**Type consistency:** 티어 키 `docs`/`dev` 일관, 마커 경로 `.claude/vway-kit/.vdev/`, 스크립트명 `vdev_gate_check.py`/`vdev_init_setup.py` 전 Task 일치.

**주의:** 산문 치환 시 `workflow`(부분문자열)·일반 영단어 `fast`/`standard`/`architecture` 오치환 금지 — 단어경계·문맥 확인. 이력 문서(`docs/superpowers/**`)는 제외.
