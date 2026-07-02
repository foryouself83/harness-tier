# harness-init 운영 컨벤션 생성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** harness-init 이 감지한 스택에서 운영 cross-cutting 관심사(에러·로깅·시크릿·관측성 등)를 누락 없이 검토해, directive 는 룰로·표준 상세는 출처와 함께 문서로 생성하게 한다.

**Architecture:** 새 마커블록·새 강제 메커니즘을 만들지 않는다. 기존 `<framework>-conventions.md`(룰)에 `<!-- ops-conventions -->` 앵커 절을 추가하고, 살은 기존 `docs/code-style/<stack>.md`에 "운영 관심사" 섹션으로 넣는다. SSOT(`rules/harness-rules.md`)에 운영 관심사 체크리스트·emit 규율을 신규 명시하고, 리서치/작성/비판 에이전트가 이를 defer 한다. 유일한 코드 변경은 `harness_scaffold.py validate` 의 운영 directive 라인 수 가드(결정적·FAIL-OPEN).

**Tech Stack:** Markdown 컴포넌트(.md), Python 3.8+ (`harness_scaffold.py`), pytest, ruff, `uv`.

## Global Constraints

- **수정 대상은 플러그인 SOURCE 만** — `c:\Work\llm_ai\vway-kit` 의 `rules/`·`skills/`·`agents/`·`scripts/`. 호스트 사본(`<host>/.claude/vway-kit/`)은 건드리지 않는다.
- **Windows cp949 인코딩 방어** — 새/수정 Python 은 파일 I/O 에 `encoding="utf-8"`. `harness_scaffold.py` 는 이미 `force_utf8_io()` 적용됨(추가 정의 금지).
- **FAIL-OPEN** — `validate` 는 게이트가 아니다. 운영 라인 수 위반은 `issues` 에 `severity: high` 로 기록하되 종료코드는 항상 0 유지(기존 `main()` 의 `return 0` 보존).
- **새 마커블록 금지** — CLAUDE.md 본문에 `harness:policies` 류 블록을 추가하지 않는다. 운영 directive 는 `<framework>-conventions.md` 의 `<!-- ops-conventions -->` 앵커 절에만.
- **표준 단정 금지** — greenfield 룰엔 카테고리 directive 만. 구체 표준(RFC-9457 등)은 `docs/code-style/<stack>.md` 에 "권장(변경 가능) + 출처 + 대안"으로.
- **커맨드 미생성** — 어떤 산출물도 `.claude/commands/` 에 만들지 않는다.
- **출처 필수** — 모든 표준에 출처 URL. 없으면 "출처 미확인".
- **gitlint** — 커밋 제목 ≤ 50자, 본문 1줄 이상 필수(빈 줄로 구분). 한글 본문 OK.
- **검증 명령** — `uv run pytest` · `uv run ruff check && uv run ruff format --check`.
- **앵커 상수(전 태스크 공유)** — 운영 directive 절 앵커는 정확히 `<!-- ops-conventions -->` (소문자, 하이픈). 모든 태스크가 이 문자열을 쓴다.

---

### Task 1: harness-rules.md 에 운영 컨벤션 SSOT 신규 명시

**Files:**
- Modify: `rules/harness-rules.md` (현재 50줄, "## 산출물" 절 끝과 "## 다중 에이전트" 사이에 신규 절 삽입)

**Interfaces:**
- Produces: 운영 관심사 체크리스트(축 목록), emit 규율(커버리지 필수/증거 기반/불확실 시 질문), directive=룰/표준=문서 분리 규율, 표준 자동채택 규율, `<!-- ops-conventions -->` 앵커 컨벤션. Task 2~6 이 이 절 번호를 defer 대상으로 가리킨다.

- [ ] **Step 1: 신규 절 추가**

`rules/harness-rules.md` 의 `9. **커맨드 미생성**...` 줄(파일의 "## 산출물" 절 마지막 항목) 바로 다음 줄에, 아래 절 전체를 삽입한다(기존 "## 다중 에이전트 / 비판" 헤딩 앞):

```markdown
## 운영 컨벤션 (operational conventions)

9-1. **운영 관심사 체크리스트(누락 금지·열린 목록)**: 감지된 스택에 대해 researcher/
   code-analyzer 는 다음 *관심사 축*을 **전수 검토**한다(언어/프레임워크 무관). 닫힌 floor 가
   아니라 **흔한 출발 축** — researcher 가 스택 특성상 더 추가한다.
   에러/예외 처리 · 로깅(디버깅 지향: 레벨 규칙·디버깅 컨텍스트·구조적/검색가능·시크릿/PII 금지) ·
   설정·시크릿·env · 관측성(메트릭/트레이싱) · 헬스체크/레디니스 · 그레이스풀 셧다운 ·
   입력 검증 · 인증·인가 · 재시도/타임아웃·서킷브레이커 · 데이터 마이그레이션/스키마 진화 ·
   rate limiting.
9-2. **emit 은 증거 기반**: 커버리지는 필수이되, 각 축은 그 스택에 **관심사가 실재할 때만 emit**
   한다(정적 사이트에 헬스체크/셧다운 강제 금지). 적용성 **불확실** 시 지어내지 말고 Step 6
   미리보기에서 사용자에게 묻는다(과생성 방지 — FAIL-OPEN 은 "스킵+질문" 방향).
9-3. **directive 는 룰, 살은 문서**: 운영 directive(1~3줄 지시)는 `.claude/rules/
   <framework>-conventions.md` 의 `<!-- ops-conventions -->` 앵커 절에, 표준 상세·매핑·안티패턴·
   예제·**출처 URL(SSOT)**·대안은 `docs/code-style/<stack>.md` "운영 관심사" 섹션에 둔다.
   룰은 문서를 링크하고 같은 사실을 복제하지 않는다(한 사실 한 곳).
9-4. **표준 선택(단정 회피)**: brownfield 는 code-analyzer 가 코드에서 쓰는 표준을 감지해 명시.
   greenfield/미확정은 researcher 가 **현재 권장 최신 표준을 자동 채택(묻지 않음)** 하되, 구체
   표준명은 **문서에** "권장(변경 가능)+출처+대안"으로만 두고 룰엔 카테고리 directive 만 둔다.
9-5. **보안성 축 승격 경로**: 시크릿·인증/인가·입력 검증처럼 강제력이 필요한 축은 directive 한
   줄로 끝내지 말고, harness-init Step 1 의 **실설정 opt-in**(secret scanner·linter)을 제안한다
   (동의 시에만). "정책" 강제 착시 금지 — 진짜 강제는 탐지 도구로.
```

- [ ] **Step 2: 검증 (구조·정합성 리뷰)**

확인 항목(체크리스트):
- 삽입 위치가 "## 산출물" 절 끝 ↔ "## 다중 에이전트 / 비판" 헤딩 사이인가.
- 절 번호(9-1~9-5)가 기존 번호(1~14)와 충돌하지 않는가(9 다음, 10 앞).
- `<!-- ops-conventions -->` 문자열이 Global Constraints 와 정확히 일치하는가.

Run: `uv run pytest -q`
Expected: PASS (이 태스크는 .md 만 — 기존 테스트 무회귀 확인용).

- [ ] **Step 3: Commit**

```bash
git add rules/harness-rules.md
git commit -F - <<'EOF'
docs(harness): ops conventions SSOT rules

운영 관심사 체크리스트·emit 규율·directive/문서 분리·표준
자동채택·보안축 승격을 harness-rules SSOT 에 신규 명시.
EOF
```

---

### Task 2: harness-init SKILL.md — 언어/계층 게이트 + 운영 단계 통합

**Files:**
- Modify: `skills/harness-init/SKILL.md` (Step 1 인터뷰·Step 2 리서치·Step 3 사유·Step 5 비판·Step 6 미리보기)

**Interfaces:**
- Consumes: Task 1 의 harness-rules 9-1~9-5.
- Produces: Step 1 에서 확정되는 **계층별 언어/스택 맵**(researcher/authoring 입력), Step 2 의 체크리스트 주입 지시, Step 6 의 "적용 불확실 축" 질문 분기.

- [ ] **Step 1: Step 1 인터뷰에 언어/계층 게이트 추가**

`skills/harness-init/SKILL.md` 의 Step 1 블록에서 `1. 감지 프레임워크/버전 확인...` 항목 바로 위에 새 항목을 넣어 1번으로 만들고 기존 항목 번호를 1칸씩 밀어, Step 1 을 다음으로 교체한다:

```markdown
## Step 1 — 인터뷰 (AskUserQuestion, 최소)
1. **주 개발 언어 확정(hard gate, harness-rules 참고)**: `AskUserQuestion` 으로 주 개발 언어를
   반드시 확정한다(감지값 무관 항상 질문). 감지 언어가 있으면 첫 옵션(권장), 멀티/미감지면 후보
   나열. 감지값과 사용자 선택이 다르면 **사용자 선택 우선**. **주 언어 ≠ 전 계층 동일 언어** —
   프로젝트를 계층(프런트/백/기타)으로 나누고, 각 계층에서 **더 프로덕션 레디·표준에 가까운
   스택을 권장 1순위**로 제시(가능 시 research 근거), **"전 계층 동일 vs 계층별 분리"를
   `AskUserQuestion` 으로 확인**한다. 결과 = **계층별 언어/스택 맵**(downstream 단일 출처).
2. 감지 프레임워크/버전 확인(틀리면 정정, 미감지면 입력 요청).
3. 생성 산출물 선택: CLAUDE.md / 룰(baseline 5종 + 프레임워크 컨벤션) / skills / agents /
   기술문서(PRD greenfield·architecture·스택별 code-style·research·onboarding, 분류별 폴더). **커맨드 선택지 없음.**
4. **실설정 opt-in**: 보안 스캐너 설치·CI 추가·실폴더 스캐폴딩·실제 버전핀 — 각각 물어봄.
   시크릿·인증/인가·입력검증 운영 축은 directive 만으로 끝내지 말고 스캐너 opt-in 을 함께 제안(9-5).
5. 브라운필드 충돌(existing) 항목별: 스킵 / 사용자선택.
```

- [ ] **Step 2: Step 2 리서치에 체크리스트 주입 지시 추가**

`## Step 2 — 리서치` 블록의 첫 문단(표준 설명) 끝(`...리더가 \`Read\` 로 팬인해 종합한다.` 줄 다음)에 한 줄 추가:

```markdown
- **운영 관심사 주입**: 리서치 디스패치 시 harness-rules 9-1 체크리스트와 **계층별 언어/스택 맵**을
  전달해, 각 (계층,스택)에서 운영 축별 최신 표준·출처·대안·적용성을 조사하게 한다(9-2~9-4).
```

- [ ] **Step 3: Step 3 사유에 운영 표준 기록 추가**

`## Step 3 — 사유 작성 (rationale)` 의 문장에서 `채택 패턴, BP/안티패턴 요약,` 다음에 삽입:

```markdown
**운영 축별 채택 표준+출처+적용성(emit/스킵 사유 포함)**,
```

- [ ] **Step 4: Step 6 미리보기에 불확실 축 질문 분기 추가**

`## Step 6 — 미리보기·확정` 의 문장 끝에 한 문장 추가:

```markdown
적용성이 **불확실한 운영 축**은 여기서 `AskUserQuestion` 으로 "포함할지" 확인하고(9-2), greenfield
자동채택 표준은 "권장 기본(변경 가능)"으로 노출해 확정받는다.
```

- [ ] **Step 5: 검증 + Commit**

확인: Step 1 번호가 1~5 로 재정렬됐는가 / 기존 문구(커맨드 선택지 없음 등) 보존됐는가 / 9-x 참조가 Task 1 절 번호와 일치하는가.

Run: `uv run pytest -q`  · Expected: PASS

```bash
git add skills/harness-init/SKILL.md
git commit -F - <<'EOF'
feat(harness): primary-language + ops gates

Step1 주 언어/계층 스택 확정 게이트, Step2 운영 체크리스트
주입, Step3 사유·Step6 불확실 축 질문 분기 추가.
EOF
```

---

### Task 3: 리서치/분석 에이전트에 운영 축 조사 추가

**Files:**
- Modify: `agents/harness-researcher.md` (입력 concerns·절차·출력 형식)
- Modify: `agents/harness-code-analyzer.md` (핵심 역할·출력)

**Interfaces:**
- Consumes: harness-rules 9-1 체크리스트(Task 1), Step 2 주입(Task 2).
- Produces: research 산출물에 "운영 축별 표준/출처/대안/적용성" 섹션 — Task 4(authoring)·Task 5(critic) 가 소비.

- [ ] **Step 1: researcher 입력에 운영 축 추가**

`agents/harness-researcher.md` 의 `## 입력` 항목을 교체:

```markdown
## 입력
- `framework`, `version`, `concerns`(folder/schema/best-practices/anti-patterns/security/reuse)
- `ops_axes`(운영 관심사 체크리스트, harness-rules 9-1) + `stack_map`(계층별 언어/스택)
```

- [ ] **Step 2: researcher 절차에 운영 축 조사 단계 추가**

`## 절차` 의 마지막 항목(`7. **자율 확장**...`) 다음에 새 항목 추가:

```markdown
8. **운영 축 조사(9-1~9-4)**: 전달된 `ops_axes` 를 (계층,스택)별로 **전수 검토**한다. 각 축마다
   현재 권장 **최신 표준**과 출처·대안·**적용성**(이 스택에 실재하는가)을 조사한다. 미확정이면
   최신 표준을 권장 기본으로 채택하되 **대안과 출처를 함께** 남긴다(단정 금지). 적용성 불확실은
   "확인 필요"로 표기(지어내지 않는다).
```

- [ ] **Step 3: researcher 출력 형식에 운영 섹션 추가**

`## 출력 (이 형식 그대로)` 의 코드블록 안에서 `### 안티패턴 (피한다)` 섹션 다음에 삽입:

````markdown
### 운영 축 (9-1, (계층,스택)별)
- <축>: 채택 표준 <name> (권장 기본/감지됨) / 적용성: <실재|확인 필요|해당없음> / 대안: <...> (출처: URL)
````

- [ ] **Step 4: code-analyzer 에 운영 축 감지 역할 추가**

`agents/harness-code-analyzer.md` 의 `## 핵심 역할` 에서 `4. **손수 구현...` 다음에 항목 추가:

```markdown
5. **운영 축 실사용 표준(9-1, 9-4)**: 에러/예외 처리·로깅·설정/시크릿·관측성 등 운영 축에서
   코드가 **실제 사용하는 표준/관행**을 출처(파일:라인)와 함께 보고한다. 부재하면 "부재"로 명시
   (greenfield 수준 표본 부족이면 "표본 부족"). 채택 여부 판단은 리더에 위임.
```

- [ ] **Step 5: 검증 + Commit**

확인: 출력 코드블록 펜스(```)가 깨지지 않았는가 / 9-x 참조 일치 / description frontmatter 무수정.

Run: `uv run pytest -q`  · Expected: PASS

```bash
git add agents/harness-researcher.md agents/harness-code-analyzer.md
git commit -F - <<'EOF'
feat(harness): ops axes in research agents

researcher 에 운영 축 조사 단계·출력 섹션, code-analyzer 에
실사용 표준 감지 역할 추가(9-1~9-4 defer).
EOF
```

---

### Task 4: 작성 규율 — directive(룰)/표준(문서) 분리 + ops 앵커

**Files:**
- Modify: `skills/harness-authoring/references/tech-doc-guide.md` (code-style 섹션에 "운영 관심사" 규율)
- Modify: `skills/harness-authoring/SKILL.md` (산출물·생성 절차에 운영 directive/문서 분리)

**Interfaces:**
- Consumes: Task 3 research 의 운영 축 섹션, harness-rules 9-3·9-4.
- Produces: authoring 이 `<framework>-conventions.md` 에 `<!-- ops-conventions -->` 앵커 절을 쓰고 `docs/code-style/<stack>.md` 에 "운영 관심사" 섹션을 쓰는 규율 — Task 5(critic)·Task 6(validate) 가 이 앵커를 검사.

- [ ] **Step 1: tech-doc-guide 에 운영 관심사 섹션 규율 추가**

`skills/harness-authoring/references/tech-doc-guide.md` 의 `## code-style — code-style/README.md + <stack>.md` 절에서 마지막 불릿(`- \`code-style/README.md\` 는 ...`) 다음에 추가:

```markdown
- **운영 관심사 섹션**(9-1~9-4): 각 `<stack>.md` 에 운영 축별 소섹션(`## error-handling` 등)을 둔다.
  소섹션엔 **채택 표준(권장 기본/감지됨)·매핑·안티패턴·예제·대안**과 **출처 URL(SSOT)**. greenfield
  미확정 표준은 "권장(변경 가능)"으로 표기. 구조적 지시(룰)는 여기 복제하지 않고 룰이 이 섹션을
  앵커(`#error-handling`)로 링크한다. emit 은 그 스택에 실재하는 축만(9-2).
```

- [ ] **Step 2: authoring SKILL 산출물에 운영 directive 명시**

`skills/harness-authoring/SKILL.md` 의 `## 산출물` 에서 `- \`CLAUDE.md\`(...) · 룰(baseline 5종 + \`<framework>-conventions.md\`)` 줄을 교체:

```markdown
- `CLAUDE.md`(baseline 마커블록 + 프레임워크 컨벤션 요약) · 룰(baseline 5종 +
  `<framework>-conventions.md` — 그 안에 `<!-- ops-conventions -->` 앵커 절로 운영 directive 1~3줄씩,
  살은 docs/code-style 링크. **새 마커블록 만들지 않는다**)
```

- [ ] **Step 3: authoring 생성 절차에 운영 분리 단계 추가**

`## 생성 절차` 의 4번 항목(기술문서) 다음에 새 5번을 넣고 기존 5번을 6번으로 민다:

```markdown
5. **운영 directive/표준 분리(9-3·9-4)**: research 운영 축 섹션을 받아, 룰
   `<framework>-conventions.md` 에 `<!-- ops-conventions -->` 앵커를 두고 그 아래 축별 directive 를
   **항목당 ≤ 3줄**(카테고리 지시 + `docs/code-style/<stack>.md#<axis>` 링크)로 쓴다. 구체 표준명·
   상세·출처·대안은 룰이 아니라 docs/code-style 운영 관심사 섹션에. greenfield 는 룰엔 카테고리만.
```

- [ ] **Step 4: 검증 + Commit**

확인: 앵커 문자열 일치 / "≤ 3줄" 명시 / 기존 절차 번호 재정렬 정확 / SSOT 분리 문구가 9-3 과 모순 없음.

Run: `uv run pytest -q`  · Expected: PASS

```bash
git add skills/harness-authoring/references/tech-doc-guide.md skills/harness-authoring/SKILL.md
git commit -F - <<'EOF'
feat(harness): authoring rules for ops split

directive 는 conventions 룰의 ops-conventions 앵커 절(≤3줄),
표준 상세는 code-style 운영 관심사 섹션(출처 SSOT)으로.
EOF
```

---

### Task 5: harness-critic + critique-guide 에 운영 검증 추가

**Files:**
- Modify: `agents/harness-critic.md` (검토 영역)
- Modify: `skills/harness-authoring/references/critique-guide.md` (체크리스트)

**Interfaces:**
- Consumes: Task 1(9-1~9-5)·Task 4(앵커 절·운영 섹션).
- Produces: critic 이 커버리지 누락·출처 부재·룰↔문서 중복·보안축 opt-in 누락을 `coherence`/`quality`/`reuse` kind 로 보고(기존 critic 스키마 재사용 — 새 kind 추가 안 함).

- [ ] **Step 1: critic 검토 영역에 운영 항목 추가**

`agents/harness-critic.md` 의 `## 검토 영역` 에서 `2. **경계면 정합성**(\`coherence\`)` 항목 끝(`...오케스트레이션과 맞물리는지.`)에 문장 추가:

```markdown
   **운영 컨벤션(9-1~9-5)**: 체크리스트 축이 누락 없이 검토됐는가(emit/스킵 사유 rationale 에 있는가),
   운영 표준에 **출처**가 있는가, directive(룰)와 표준 상세(문서)가 **중복**되지 않는가, 보안성 축이
   directive 한 줄로만 끝나지 않고 스캐너 opt-in 으로 연결됐는가.
```

- [ ] **Step 2: critique-guide 에 운영 체크 항목 추가**

`skills/harness-authoring/references/critique-guide.md` 의 `## 2. 경계면 정합성 (\`kind: coherence\`)` 절의 마지막 불릿 다음에 추가:

```markdown
- **운영 컨벤션(9-1~9-5)**: (a) 체크리스트 축 전수 검토 — 누락 시 rationale 에 emit/스킵 사유가
  있는가, (b) 운영 표준에 출처 URL 이 있는가(없으면 "출처 미확인"인가), (c) directive(룰)↔표준
  상세(문서)가 같은 사실을 중복하지 않는가, (d) 보안성 축(시크릿·인증·입력검증)이 directive 만으로
  끝나지 않고 스캐너 opt-in 으로 연결됐는가. 위반은 `high`.
```

- [ ] **Step 3: 검증 + Commit**

확인: 새 kind 를 만들지 않고 기존 `coherence` 로 분류했는가 / 9-x 참조 일치.

Run: `uv run pytest -q`  · Expected: PASS

```bash
git add agents/harness-critic.md skills/harness-authoring/references/critique-guide.md
git commit -F - <<'EOF'
feat(harness): critic checks ops conventions

커버리지 누락·출처 부재·룰↔문서 중복·보안축 opt-in 누락을
coherence kind 로 검증(critique-guide 동기화).
EOF
```

---

### Task 6: validate 운영 directive 라인 수 가드 (TDD)

**Files:**
- Modify: `scripts/harness_scaffold.py` (상수·헬퍼·`validate_plan` 루프)
- Test: `tests/test_harness_scaffold.py`

**Interfaces:**
- Consumes: `<!-- ops-conventions -->` 앵커(Task 4 가 생성).
- Produces: `validate_plan` 이 앵커 절의 각 directive 블록이 3줄 초과면 `{"severity":"high","kind":"ops-line-limit","path":<rel>,"detail":...}` 를 `issues` 에 추가. 종료코드는 0 유지(FAIL-OPEN).

- [ ] **Step 1: 헬퍼 단위 테스트(실패) 작성**

`tests/test_harness_scaffold.py` 맨 끝에 추가:

```python
def test_ops_blocks_none_without_anchor():
    assert hs._ops_directive_blocks("- a\n- b\n") == []


def test_ops_blocks_splits_top_level_items():
    body = "<!-- ops-conventions -->\n- 에러: RFC-9457 → docs#err\n- 로깅: 레벨 규칙 → docs#log\n"
    blocks = hs._ops_directive_blocks(body)
    assert len(blocks) == 2
    assert blocks[0][0].startswith("- 에러")


def test_ops_blocks_collects_wrapped_continuation():
    body = "<!-- ops-conventions -->\n- 에러: 1\n  cont2\n  cont3\n  cont4\n\n- 로깅: ok\n"
    blocks = hs._ops_directive_blocks(body)
    assert len(blocks[0]) == 4  # `- 에러` + 3 continuation
    assert len(blocks[1]) == 1
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_harness_scaffold.py::test_ops_blocks_splits_top_level_items -v`
Expected: FAIL — `AttributeError: module ... has no attribute '_ops_directive_blocks'`

- [ ] **Step 3: 상수 + 헬퍼 구현**

`scripts/harness_scaffold.py` 의 `_INLINE_CODE_RE = ...` 줄(286번 부근) 다음에 추가:

```python
OPS_ANCHOR_RE = re.compile(r"<!--\s*ops-conventions\s*-->")
OPS_MAX_LINES = 3


def _ops_directive_blocks(body: str) -> list[list[str]]:
    """`<!-- ops-conventions -->` 앵커 뒤의 최상위 리스트 항목(`- ...`)을 블록으로 나눈다.

    각 블록 = `- ` 줄 + 빈 줄/다음 `- `/헤딩/다음 앵커 전까지의 연속 줄. 헤딩이나 다음
    앵커를 만나면 절이 끝난 것으로 본다(운영 directive 라인 수 가드의 입력).
    """
    m = OPS_ANCHOR_RE.search(body)
    if not m:
        return []
    blocks: list[list[str]] = []
    cur: list[str] | None = None
    for line in body[m.end() :].splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or OPS_ANCHOR_RE.search(line):
            break
        if line.startswith("- "):
            if cur is not None:
                blocks.append(cur)
            cur = [line]
        elif cur is not None:
            if stripped == "":
                blocks.append(cur)
                cur = None
            else:
                cur.append(line)
    if cur is not None:
        blocks.append(cur)
    return blocks
```

- [ ] **Step 4: 헬퍼 테스트 통과 확인**

Run: `uv run pytest tests/test_harness_scaffold.py -k ops_blocks -v`
Expected: 3 passed

- [ ] **Step 5: validate 통합 테스트(실패) 작성**

`tests/test_harness_scaffold.py` 의 헬퍼 테스트 다음에 추가(`_baseline_entry` 는 기존 헬퍼 재사용):

```python
def _conv_entry(content):
    return {"path": ".claude/rules/next.js-conventions.md", "action": "create", "content": content}


def test_validate_ops_line_limit_ok(tmp_path):
    body = "<!-- ops-conventions -->\n- 에러: RFC-9457 → docs/code-style/x.md#err\n- 로깅: 레벨 → docs/code-style/x.md#log\n"
    rep = hs.validate_plan(tmp_path, {"files": [_baseline_entry(), _conv_entry(body)]})
    assert not [i for i in rep["issues"] if i["kind"] == "ops-line-limit"]


def test_validate_ops_line_limit_violation(tmp_path):
    body = "<!-- ops-conventions -->\n- 에러: 1\n  2\n  3\n  4\n"
    rep = hs.validate_plan(tmp_path, {"files": [_baseline_entry(), _conv_entry(body)]})
    hits = [i for i in rep["issues"] if i["kind"] == "ops-line-limit"]
    assert len(hits) == 1 and hits[0]["severity"] == "high"
    assert not rep["ok"]
```

- [ ] **Step 6: 테스트 실패 확인**

Run: `uv run pytest tests/test_harness_scaffold.py::test_validate_ops_line_limit_violation -v`
Expected: FAIL (아직 validate 가 ops-line-limit 을 내지 않음 → hits 비어 assert 실패)

- [ ] **Step 7: validate_plan 에 가드 추가**

`scripts/harness_scaffold.py` 의 `validate_plan` 안, per-file 루프에서 `if e.get("action") == "marker_upsert":` 블록 **직전**(dead-link 스캔 다음)에 삽입:

```python
        for blk in _ops_directive_blocks(content):
            non_empty = [ln for ln in blk if ln.strip()]
            if len(non_empty) > OPS_MAX_LINES:
                issues.append(
                    {
                        "severity": "high",
                        "kind": "ops-line-limit",
                        "path": rel,
                        "detail": f"운영 directive 가 {len(non_empty)}줄 — 항목당 ≤{OPS_MAX_LINES}줄 (살은 docs/code-style 로)",
                    }
                )
```

- [ ] **Step 8: 전체 테스트 통과 확인**

Run: `uv run pytest tests/test_harness_scaffold.py -v`
Expected: 모두 PASS (신규 5 + 기존 무회귀)

- [ ] **Step 9: 린트/포맷 확인**

Run: `uv run ruff check && uv run ruff format --check`
Expected: 통과(실패 시 `uv run ruff format` 후 재확인)

- [ ] **Step 10: Commit**

```bash
git add scripts/harness_scaffold.py tests/test_harness_scaffold.py
git commit -F - <<'EOF'
feat(harness): validate ops directive line guard

ops-conventions 앵커 절의 directive 가 항목당 3줄 초과 시
high(ops-line-limit). FAIL-OPEN(종료코드 0 유지).
EOF
```

---

### Task 7: 문서 동기화 (USAGE/README 운영 컨벤션 언급)

**Files:**
- Modify: `README.md` 또는 `USAGE.md` 중 harness-init 설명이 있는 곳(grep 으로 확인)

**Interfaces:**
- Consumes: Task 1~6 의 동작.

- [ ] **Step 1: harness-init 설명 위치 확인**

Run: `git grep -n "harness-init" README.md USAGE.md`
Expected: harness-init 산출물을 설명하는 줄 식별.

- [ ] **Step 2: 운영 컨벤션 한 줄 추가**

식별된 harness-init 산출물 설명에 운영 컨벤션 생성(주 언어/계층 게이트 + 운영 축 directive=룰/표준=문서)을 **한 줄**로 덧붙인다(장황 금지 — 상세는 spec/룰이 SSOT). 정확한 문구는 기존 문장 톤에 맞춰 작성하되, "운영 cross-cutting 컨벤션(에러·로깅·시크릿 등)을 표준·출처와 함께 생성" 의미를 담는다.

- [ ] **Step 3: 검증 + Commit**

Run: `uv run pytest -q && uv run ruff check`  · Expected: PASS

```bash
git add README.md USAGE.md
git commit -F - <<'EOF'
docs(harness): mention ops conventions output

harness-init 산출물 설명에 운영 컨벤션 생성(언어/계층 게이트,
directive=룰/표준=문서)을 한 줄 추가.
EOF
```

---

## Self-Review

**1. Spec coverage (spec 절 → 태스크):**
- §3.1 directive=룰/표준=문서 → Task 1(9-3)·Task 4
- §3.2 운영 관심사 체크리스트 → Task 1(9-1)·Task 3
- §3.3 emit 증거 기반 → Task 1(9-2)·Task 2(Step6)·Task 5
- §3.4 표준 선택(단정 회피) → Task 1(9-4)·Task 3·Task 4
- §3.5 보안축 opt-in 승격 → Task 1(9-5)·Task 2(Step1.4)·Task 5
- §3.6 결정적 라인 수 가드 → Task 6
- §3.7 주 언어/계층 게이트 → Task 2(Step1)
- §4 영향 파일 1~8 → Task 1(harness-rules)·2(harness-init)·3(researcher+code-analyzer)·4(tech-doc-guide+authoring)·5(critic+critique-guide)·6(scaffold+test). README/USAGE 는 Task 7.
- §6 성공 기준 → 각 태스크 검증 단계 + Task 6 테스트.

**2. Placeholder scan:** Task 7 Step 2 는 기존 문서 톤에 맞춘 한 줄이라 정확 문구를 실행 시 확정(파일 내용 의존) — 이는 "위치+의미"를 명시했으므로 placeholder 가 아니라 컨텍스트 의존 편집. 나머지 코드 스텝은 전부 실제 코드 포함.

**3. Type consistency:** `_ops_directive_blocks`(반환 `list[list[str]]`)·`OPS_ANCHOR_RE`·`OPS_MAX_LINES`·issue kind `"ops-line-limit"`·앵커 `<!-- ops-conventions -->` 가 Task 4·5·6 전반에서 동일 철자로 사용됨. harness-rules 절 번호 9-1~9-5 가 Task 2·3·4·5 의 defer 참조와 일치.

## Execution Handoff

(계획 저장 후 실행 방식 선택 — 아래 메시지 참조)
