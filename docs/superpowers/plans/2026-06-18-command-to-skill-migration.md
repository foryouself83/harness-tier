# Command-to-Skill Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** vway-kit 진입점 5개를 `commands/`에서 `skills/<name>/SKILL.md`로 일원화해 모델 자동발동·정상 위임을 활성화한다.

**Architecture:** 커맨드/스킬 통합 모델을 이용해 5개 진입점을 `skills/`로 `git mv`하고, 위임 대상(task-import·task-sync)은 자동발동을 허용하도록 frontmatter를 신설, 셋업(flow-init·harness-init)은 `disable-model-invocation: true`로 잠근다. flow는 진입점 description으로 보강하고 내부 위임을 "invoke the skill"로 명시화한다. 파일 이동으로 깨지는 상대 링크를 전부 재계산해 고친다.

**Tech Stack:** Markdown(SKILL.md frontmatter, YAML), git, pre-commit(ruff·gitlint), `uv run pytest`.

## Global Constraints

- **위임 대상에 `disable-model-invocation`을 켜지 않는다** — task-import·task-sync는 자동발동 허용이어야 flow가 `Skill` 도구로 발동 가능(끄면 흉내내기 회귀).
- **셋업은 `disable-model-invocation: true`** — flow-init·harness-init.
- **`git mv` 사용** — 파일 이력 보존.
- **상대 링크 재계산** — `commands/X.md`(깊이1) → `skills/X/SKILL.md`(깊이2): `](../foo)` → `](../../foo)`, 형제 `](task-import.md)` → `](../task-import/SKILL.md)`.
- **매니페스트 무수정** — `plugin.json`·`marketplace.json`은 컴포넌트 경로 미선언(자동 발견).
- **슬래시 호출명 표기(`/task-import` 등)는 이번 범위에서 유지** — 단축 호출명 동작은 적용 후 실측 대상(spec 5절). 디렉토리 구조 설명·링크 경로만 갱신한다.
- **frontmatter는 skills.md 스펙 준수** — 필드: `description`·`allowed-tools`·`argument-hint`·`disable-model-invocation`.
- **커밋 메시지 50/72 + 본문 필수**(gitlint).

---

### Task 1: task-import·task-sync를 skills/로 이전 + frontmatter 신설

위임 대상 2개. 상대 링크가 없어 이동+frontmatter만으로 끝난다(흉내내기 진앙).

**Files:**
- Move: `commands/task-import.md` → `skills/task-import/SKILL.md`
- Move: `commands/task-sync.md` → `skills/task-sync/SKILL.md`

**Interfaces:**
- Produces: `/task-import`·`/task-sync` 스킬 — 자동발동 허용, `argument-hint: [task_id]`. flow(Task 3)가 `../task-import/SKILL.md`·`../task-sync/SKILL.md`로 링크.

- [ ] **Step 1: task-import 이동**

```bash
git mv commands/task-import.md skills/task-import/SKILL.md
```

- [ ] **Step 2: task-import에 frontmatter 추가**

`skills/task-import/SKILL.md` 맨 위(기존 `# /task-import - ...` 헤더 앞)에 삽입:

```yaml
---
description: Import a Teamer item's context and scaffold the task-doc skeleton (Content filled; Codebase Analysis / Implementation Sequence / Plan left as placeholders). The Teamer-import sub-step /flow invokes for an ALM task-id entry — not usually invoked directly.
allowed-tools: Bash, Read, Write, Edit, Task
argument-hint: [task_id]
---
```

- [ ] **Step 3: task-sync 이동**

```bash
git mv commands/task-sync.md skills/task-sync/SKILL.md
```

- [ ] **Step 4: task-sync에 frontmatter 추가**

`skills/task-sync/SKILL.md` 맨 위에 삽입:

```yaml
---
description: Summarize the task doc and sync it to the Teamer item via PUT (item_content appended). The final sub-step /flow invokes after an ALM task-id entry completes — not usually invoked directly.
allowed-tools: Bash, Read, Glob, Task, AskUserQuestion
argument-hint: [task_id]
---
```

- [ ] **Step 5: frontmatter·이동 검증**

Run: `git status --short` → `R  commands/task-import.md -> skills/task-import/SKILL.md`, `R  commands/task-sync.md -> skills/task-sync/SKILL.md` 확인.
두 SKILL.md의 첫 줄이 `---`인지, frontmatter 본문(`description`/`allowed-tools`/`argument-hint`) 3필드가 있고 `disable-model-invocation`이 **없는지** 육안 확인.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m @'
refactor(skills): task-import·task-sync 를 skills 로 이전

frontmatter(description/allowed-tools/argument-hint) 신설.
flow 가 Skill 도구로 발동하도록 자동발동 허용(disable 미설정).
'@
```

---

### Task 2: flow-init·harness-init를 skills/로 이전 + 자동발동 잠금

셋업 2개. `disable-model-invocation: true` 추가 + 상대 링크 1개씩 수정.

**Files:**
- Move: `commands/flow-init.md` → `skills/flow-init/SKILL.md`
- Move: `commands/harness-init.md` → `skills/harness-init/SKILL.md`

- [ ] **Step 1: flow-init 이동**

```bash
git mv commands/flow-init.md skills/flow-init/SKILL.md
```

- [ ] **Step 2: flow-init frontmatter에 잠금 추가**

`skills/flow-init/SKILL.md` frontmatter의 `argument-hint: (none)` 아래 줄에 추가:

```yaml
disable-model-invocation: true
```

- [ ] **Step 3: flow-init 상대 링크 수정**

`skills/flow-init/SKILL.md`에서 `](../docs/plugins/marketplace-auto-update.md)` → `](../../docs/plugins/marketplace-auto-update.md)` (1곳).

- [ ] **Step 4: harness-init 이동**

```bash
git mv commands/harness-init.md skills/harness-init/SKILL.md
```

- [ ] **Step 5: harness-init frontmatter에 잠금 추가**

`skills/harness-init/SKILL.md` frontmatter의 `argument-hint: (none)` 아래 줄에 추가:

```yaml
disable-model-invocation: true
```

- [ ] **Step 6: harness-init 상대 링크 수정**

`skills/harness-init/SKILL.md`에서 `](../rules/harness-rules.md)` → `](../../rules/harness-rules.md)` (1곳).

- [ ] **Step 7: 검증**

Run: `uv run python -c "import pathlib,re,sys; [print('BROKEN',p,m) for p in [pathlib.Path('skills/flow-init/SKILL.md'),pathlib.Path('skills/harness-init/SKILL.md')] for m in re.findall(r'\]\((\.\./[^)]+)\)', p.read_text(encoding='utf-8')) if not (p.parent/m).resolve().exists()]"`
Expected: 출력 없음(깨진 상대 링크 0건).
두 SKILL.md frontmatter에 `disable-model-invocation: true`가 있는지 육안 확인.

- [ ] **Step 8: Commit**

```bash
git add -A
git commit -m @'
refactor(skills): flow-init·harness-init 를 skills 로 이전

셋업 마법사라 disable-model-invocation:true 로 자동발동 잠금.
상대 링크를 skills 깊이에 맞춰 ../../ 로 보정.
'@
```

---

### Task 3: flow를 skills/로 이전 + 진입점 보강 + 위임 명시화

진입점. description 보강, 상대 링크 전부 보정, task-import/task-sync 링크를 새 경로로, 위임 표현을 "invoke the skill"로.

**Files:**
- Move: `commands/flow.md` → `skills/flow/SKILL.md`

**Interfaces:**
- Consumes: `../task-import/SKILL.md`·`../task-sync/SKILL.md`(Task 1 산출).

- [ ] **Step 1: flow 이동**

```bash
git mv commands/flow.md skills/flow/SKILL.md
```

- [ ] **Step 2: description을 진입점으로 보강**

`skills/flow/SKILL.md` frontmatter `description:`을 아래로 교체(task-id 자동 진입을 위해 진입점임을 명시):

```yaml
description: Risk-tiered workflow router and entry point for ALM task-id work — when given an ALM task-id (e.g. SDAL-0091) or a free-text request, classify as Fast/Standard, run the matching workflow, and record gate evidence the commit hook enforces (Staging/Release apply at integration→staging / staging→production).
```

`allowed-tools`·`argument-hint`는 유지하고 `disable-model-invocation`은 **추가하지 않는다**(자동발동 허용).

- [ ] **Step 3: task-import/task-sync 링크를 새 경로로 + 위임 명시화**

`skills/flow/SKILL.md`에서 아래 4곳 교체:
- `[`/task-import`](task-import.md)` (2곳: 본문 Phase 0, Phase 3) → `[`task-import` skill](../task-import/SKILL.md)`
- `[`/task-sync`](task-sync.md)` (2곳: Phase 0 주석, Phase 4) → `[`task-sync` skill](../task-sync/SKILL.md)`

그리고 위임 동사를 발동으로 명시(의미 보존, 표현만):
- Phase 0: `run [`task-import` skill](../task-import/SKILL.md) `$ARGUMENTS` first` → `invoke the [`task-import` skill](../task-import/SKILL.md) (via the Skill tool) with `$ARGUMENTS` first`
- Phase 4: `run [`task-sync` skill](../task-sync/SKILL.md) `<task-id>`` → `invoke the [`task-sync` skill](../task-sync/SKILL.md) (via the Skill tool) with `<task-id>``
- Fast Step 2 / Standard Step 2의 `Run `/doc-sync`` → `invoke the `doc-sync` skill` (2곳, 의미 보존).

- [ ] **Step 4: 나머지 상대 링크 보정 (`../` → `../../`)**

`skills/flow/SKILL.md`에서 아래를 일괄 치환(9곳):
- `](../rules/risk-tiers.md)` → `](../../rules/risk-tiers.md)` (6곳: L13,58,111,156,162 등)
- `](../flow-tiers.yaml)` → `](../../flow-tiers.yaml)` (3곳: L14,60,163)
- `](../scripts/flow_gate_check.py)` → `](../../scripts/flow_gate_check.py)` (1곳: L135)

- [ ] **Step 5: 링크 무결성 검증**

Run: `uv run python -c "import pathlib,re; p=pathlib.Path('skills/flow/SKILL.md'); [print('BROKEN',m) for m in re.findall(r'\]\((\.\./[^)]+)\)', p.read_text(encoding='utf-8')) if not (p.parent/m).resolve().exists()]"`
Expected: 출력 없음(모든 `../` 링크가 실재 파일로 해석됨 — task-import/task-sync SKILL.md, rules, flow-tiers, scripts 포함).

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m @'
refactor(skills): flow 를 skills 로 이전 + 진입점 보강

description 에 ALM task-id 진입점 명시(자동발동 허용).
내부 위임을 invoke the skill 로 명시화, 상대 링크 ../../ 보정,
task-import/task-sync 링크를 skills 경로로 갱신.
'@
```

---

### Task 4: 외부 참조 갱신 + commands/ 제거 확인

문서들의 디렉토리 구조 설명·구조 트리를 `skills/` 기준으로 갱신. 슬래시 호출명 표기는 유지(Global Constraints).

**Files:**
- Modify: `CLAUDE.md:31`
- Modify: `README.md:112`
- Modify: `USAGE.md:439`

- [ ] **Step 1: CLAUDE.md 폴더 구조 갱신**

`CLAUDE.md`의 폴더 구조 블록에서 `commands/` 줄을 제거하고 5개를 `skills/` 줄로 합친다.

Before:
```text
commands/   flow · flow-init · task-import · task-sync · harness-init   (/슬래시 커맨드)
agents/     teamer-api-searcher · teamer-item-updater · harness-researcher   (Teamer.live API / 하네스 리서치)
hooks/      hooks.json (SessionStart 룰주입 + Notification) · inject-risk-tiers.sh
skills/     doc-sync/SKILL.md · harness-authoring/SKILL.md
```
After:
```text
agents/     teamer-api-searcher · teamer-item-updater · harness-researcher   (Teamer.live API / 하네스 리서치)
hooks/      hooks.json (SessionStart 룰주입 + Notification) · inject-risk-tiers.sh
skills/     flow · flow-init · task-import · task-sync · harness-init · doc-sync · harness-authoring   (/슬래시 = 스킬)
```
같은 파일에 `commands/`·`skills/`를 "자동 발견"으로 설명하는 다른 문장이 있으면 `commands/` 언급을 `skills/`로 일치시킨다.

- [ ] **Step 2: README.md 구조 트리 갱신**

`README.md:112`의 `│   ├── flow.md · task-import.md · task-sync.md`를 `skills/` 디렉토리 구조로 수정(인접 줄의 `commands/` 트리 항목 포함해 일관되게).

- [ ] **Step 3: USAGE.md 구조 설명 갱신**

`USAGE.md:439`의 `├── commands/      flow · flow-init · harness-init · task-import · task-sync`를 `skills/` 기준으로 수정.

- [ ] **Step 4: commands/ 디렉토리 비었는지 확인**

Run: `ls commands/ 2>/dev/null; git status --short`
Expected: `commands/`에 파일 없음(5개 모두 이동됨). git에 잔여 추적 파일 없음.

- [ ] **Step 5: 잔존 깨진 참조 grep**

Run: `git grep -nE '\]\((\.\./)?(commands/)?(task-import|task-sync|flow|flow-init|harness-init)\.md\)' -- '*.md' ':!docs/superpowers/**'`
Expected: 출력 없음(구 `commands/` 경로나 `X.md` 형 형제 링크로 남은 것 0건). 남으면 해당 줄을 `skills/<name>/SKILL.md` 경로로 고친다.

- [ ] **Step 6: Commit**

```bash
git add -A
git commit -m @'
docs: 진입점 skills 이전에 맞춰 구조 설명 갱신

CLAUDE.md·README·USAGE 의 디렉토리 트리를 skills 기준으로 수정.
슬래시 호출명 표기는 적용 후 실측까지 유지.
'@
```

---

### Task 5: 호스트(ras_llm) task-plan.md 제거

별 저장소. 옛 진입점 잔재 1파일 제거(혼선 요인).

**Files:**
- Delete: `c:\Work\llm_ai\ras_llm\.claude\commands\task-plan.md`

- [ ] **Step 1: 대상 존재 확인**

Run: `ls "c:/Work/llm_ai/ras_llm/.claude/commands/task-plan.md"`
Expected: 파일 존재.

- [ ] **Step 2: ras_llm git 추적 여부 확인 후 제거**

```bash
cd /c/Work/llm_ai/ras_llm
git ls-files --error-unmatch .claude/commands/task-plan.md && git rm .claude/commands/task-plan.md || rm .claude/commands/task-plan.md
```

- [ ] **Step 3: 커밋(추적 파일이었던 경우)**

ras_llm에서 추적 파일이었다면:

```bash
cd /c/Work/llm_ai/ras_llm
git commit -m @'
chore: 옛 task-plan 진입점 커맨드 제거

진입점이 vway-kit task-import 로 이관되어 잔재 제거.
task-id 진입 오인 혼선 요인 정리.
'@
```

추적 파일이 아니었다면(로컬 사본) 커밋 불필요 — 제거로 끝.

---

### Task 6: 회귀 검증

vway-kit 저장소 전체 회귀 — 스크립트 무변경이라 테스트·린트는 그대로 통과해야 한다.

**Files:** (없음 — 검증만)

- [ ] **Step 1: 잔존 참조 전수 확인**

```bash
cd /c/Work/llm_ai/vway-kit
git grep -nE '(commands/)(flow|flow-init|task-import|task-sync|harness-init)\.md' -- ':!docs/superpowers/**'
```
Expected: 출력 없음(구 commands/ 경로 참조 0건).

- [ ] **Step 2: 테스트**

Run: `uv run pytest`
Expected: 기존과 동일하게 전부 PASS(스크립트·게이트 미변경).

- [ ] **Step 3: 린트·포맷**

Run: `uv run ruff check && uv run ruff format --check`
Expected: PASS(파이썬 미변경).

- [ ] **Step 4: 최종 구조 확인**

Run: `ls skills/`
Expected: `doc-sync  flow  flow-init  harness-init  harness-authoring  task-import  task-sync` (7개 스킬). `commands/` 디렉토리 없음.

---

## 적용 후(이 계획 범위 밖, 수동) 후속

- 호스트(vway-kit 설치 환경)에서 task-id 입력 시 `flow` 발동, `flow` → `task-import` 발동 **실측**.
- 단축 호출명(`/flow` 등) 동작 실측 → 결과를 `README`·`USAGE`의 호출명 표기에 반영.
