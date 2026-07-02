# flow-upgrade → flow-init 통합 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/flow-upgrade` 를 삭제하고 `/flow-init` 을 유일한 멱등 진입점으로 만든다 — 재실행 시 재동기화(자동) + 슬롯 보충 + opt-in 재설정.

**Architecture:** 순수 문서/스킬 변경. `flow_init_setup.py`(기계적 셋업)는 이미 init·upgrade 가 공유하고 재동기화를 수행하므로 **로직은 건드리지 않는다**(docstring 만 정리). flow-init SKILL 에 "config 존재 = 재실행" 분기를 명시하고, 살아있는 운영 문서의 `/flow-upgrade` 참조를 init 으로 정리한다.

**Tech Stack:** Markdown(SKILL/docs) · Python docstring · pytest(회귀 가드) · uv.

## Global Constraints

- `flow_init_setup.py` **로직 무변경** — docstring 텍스트만 수정. 기존 `tests/test_flow_init_setup.py` 가 그대로 통과해야 한다(회귀 가드).
- 새 별칭 스킬 생성 금지(YAGNI) — `/flow-upgrade` 마이그레이션은 문서 한 줄 안내로.
- 재실행 시 **재동기화(스크립트 재복사·경로 보정)는 항상 비대화로 먼저** — 대화 단계에 가려지면 안 됨.
- "빠짐/재설정" 은 기존 값·주석 보존(verbatim Edit) — 이미 구현된 slot backfill 재사용.
- 과거 `docs/superpowers/specs|plans/*` 의 historical `/flow-upgrade` 언급은 **건드리지 않는다**.
- 커밋 Conventional Commits 50/72. master 직접 금지(현재 브랜치 `feat/merge-upgrade-into-init`).

---

### Task 1: flow-upgrade 삭제 + flow-init SKILL 개정

`/flow-upgrade` 스킬을 제거하고, flow-init SKILL 에 재실행(config 존재) 분기를 명시한다. flow-init 이 이미 Step 2 에서 `flow_init_setup.py`(재동기화)와 Step 2.5(슬롯 보충)를 수행하므로, 추가하는 것은 **재실행 라우팅 문구**다.

**Files:**
- Delete: `skills/flow-upgrade/SKILL.md`
- Modify: `skills/flow-init/SKILL.md` (frontmatter `description`; `## Execution` 도입부에 실행 모드 분기 추가)

**Interfaces:** 없음(문서). 본문은 기존 단계 구조(Step 0 deps / Step 1 config / Step 2 mechanical setup / Step 2.5 slot backfill / Step 3 webhook+teams / Step 4 teamer)를 참조한다.

- [ ] **Step 1: flow-upgrade 스킬 삭제**

```bash
git rm skills/flow-upgrade/SKILL.md
```

- [ ] **Step 2: flow-init frontmatter description 갱신**

`skills/flow-init/SKILL.md` 의 frontmatter `description:` 한 줄을 교체한다. 현재:
```
description: One-time, idempotent setup wizard — detect & consent-install deps, gather config, run the mechanical setup script, and wire Teams/Teamer credentials into the host repo
```
교체 후:
```
description: Idempotent setup & update wizard for a host repo — first run installs deps and gathers config; re-runs re-sync the host gate scripts, backfill new config slots, and optionally reconfigure values/webhooks/credentials (absorbs the former /flow-upgrade)
```

- [ ] **Step 3: `## Execution` 도입부에 실행 모드 분기 추가**

`skills/flow-init/SKILL.md` 에서 `## Execution` 헤더 바로 다음(첫 `### Step 0` 앞)에 아래 블록을 삽입한다. (먼저 Read 로 `## Execution` 위치를 확인하고 그 직후에 삽입.)

````markdown
### Execution modes — first run vs re-run

`/flow-init` is the single idempotent entry point (it absorbs the former
`/flow-upgrade`). Branch on whether the host config already exists
(`${ROOT}/.claude/vway-kit/config/flow-config.yaml`):

- **First run (config absent)** — run Step 0 → Step 4 in order, gathering
  everything (the full wizard below).
- **Re-run (config present)** — the goal is *update without clobbering*:
  1. **Re-sync (always, non-interactive):** run Step 2's
     `flow_init_setup.py`. This re-copies the gate scripts/policy, repairs
     the `settings.json` gate path, migrates any legacy layout, and prints
     the `[config 슬롯 점검]` block. This must happen before any prompt, so a
     user who only wants fresh scripts is never blocked by questions.
  2. **Slot backfill (if any):** if the report lists missing slots, do Step
     2.5 (offer to insert them verbatim).
  3. **Reconfigure (opt-in):** `AskUserQuestion` — "재설정할 항목을 고르세요"
     (multi-select; default: nothing). Options map to the existing steps,
     and you run **only the selected** ones against current values:
     - `flow-config.yaml` 값 → Step 1's slot prompts (existing values shown as defaults)
     - Teams webhook URL → Step 3's webhook prompts
     - CLAUDE.md teams 블록 → Step 3's managed-block step
     - Teamer 자격증명 → Step 4's guidance
     If the user selects nothing, stop after re-sync + backfill — this is
     exactly the old `/flow-upgrade` behavior.

  Re-run never re-gathers everything and never overwrites host-owned config
  without the user selecting that section.
````

- [ ] **Step 4: Step 1 도입부를 재실행과 정합되게 조정**

`skills/flow-init/SKILL.md` 의 `### Step 1 — Generate flow-config.yaml` 첫 항목(현재 "If ... already exists, do **slot backfill** ..." 또는 reconfigure 분기 문구)을 Read 로 확인한 뒤, 그 항목을 아래로 교체해 "재실행 라우팅은 위 Execution modes 가 관장하고, Step 1 의 값 수집은 (a) 최초이거나 (b) 재실행에서 'config 값' 섹션을 골랐을 때만 수행"임을 명확히 한다:

```markdown
1. **When this step runs:** on a first run (config absent), build the file from
   scratch via items 2-4 below. On a re-run, this step runs **only if the user
   selected "flow-config.yaml 값"** in the reconfigure menu (see Execution modes)
   — then edit only the specific values the user wants, showing current values as
   defaults; never a full re-entry, never a blind rewrite. (Missing-slot backfill
   is handled separately in Step 2.5.)
```

이후 항목 2-4(new-file 전용 build)는 그대로 둔다(이미 "If the file is absent ..." 로 스코핑됨).

- [ ] **Step 5: 스킬 내부 일관성 검증**

```bash
grep -rn "flow-upgrade" skills/
```
Expected: 출력 없음(flow-init 본문이 옛 스킬명을 안 가리킴 — "absorbs the former /flow-upgrade" 문구는 description 에만, 본문엔 두지 않음). 만약 본문에 남으면 제거.

Read 로 flow-init SKILL 의 Execution modes ↔ Step 1 ↔ Step 2.5 가 모순 없는지 확인(재동기화 항상 먼저, 재설정 opt-in, 슬롯 보충 위치).

- [ ] **Step 6: 회귀 테스트**

```bash
uv run pytest -q
```
Expected: 기존 전체 통과(로직 무변경이므로 영향 없음).

- [ ] **Step 7: 커밋**

```bash
git add skills/flow-init/SKILL.md
git commit -m "feat(flow-init): absorb flow-upgrade into re-run"
```
(`git rm` 한 flow-upgrade 삭제도 이 커밋에 포함된다 — `git add -A skills/` 로 삭제 스테이징 확인.)

---

### Task 2: 운영 문서의 flow-upgrade 참조 정리

살아있는 문서에서 `/flow-upgrade` 를 제거하고 `/flow-init` 재실행으로 안내한다. 과거 spec/plan 은 건드리지 않는다.

**Files:**
- Modify: `README.md` (L167-168 표, L179-180 갱신 안내)
- Modify: `USAGE.md` (L78-79 표, L342-344 source 갱신 안내, L373-378 `### /flow-upgrade` 섹션)
- Modify: `CLAUDE.md` (L33 skills 목록, L37 스크립트 설명, L50 동기화 서술)
- Modify: `scripts/flow_init_setup.py` (L2 docstring, L98 주석)
- Modify: `github/api-contract.workflow.example.yml` (L2 주석)

**Interfaces:** 없음(문서/주석). 본문은 Task 1 의 결정(init 단일 진입점, 재실행 동기화)과 일치해야 한다.

- [ ] **Step 1: README.md**

(a) 표 행 삭제 — 현재 L168:
```
| 커맨드 | `/flow-upgrade` | 플러그인 갱신 후 호스트 사본 동기화 (설정값은 보존) |
```
이 줄을 삭제하고, 바로 위 `/flow-init` 행을 아래로 교체(재실행 동기화 의미 포함):
```
| 커맨드 | `/flow-init` | 설치/갱신 마법사 — 최초 설정 + 재실행 시 재동기화·슬롯 보충·재설정 (설정값 보존) |
```

(b) 갱신 안내 — 현재 L179-180:
```
- **갱신** — 플러그인이 업데이트돼도 호스트의 스크립트 사본은 자동으로 바뀌지 않습니다.
  `/flow-upgrade`로 동기화하세요(설정값·계정·웹훅은 보존).
```
교체:
```
- **갱신** — 플러그인이 업데이트돼도 호스트의 스크립트 사본은 자동으로 바뀌지 않습니다.
  `/flow-init`을 다시 실행하면 재동기화됩니다(설정값·계정·웹훅은 보존). 예전
  `/flow-upgrade`는 `/flow-init`에 통합되었습니다.
```

- [ ] **Step 2: USAGE.md**

(a) 표 행 삭제 — 현재 L79:
```
| 커맨드 | `/flow-upgrade` | 플러그인 갱신 후 호스트 사본 동기화 (설정값 보존) |
```
삭제하고 위 `/flow-init` 행을 README 와 동일 문구로 교체:
```
| 커맨드 | `/flow-init` | 설치/갱신 마법사 — 최초 설정 + 재실행 시 재동기화·슬롯 보충·재설정 (설정값 보존) |
```

(b) source 갱신 안내 — 현재 L342-344 의 "`/flow-upgrade`·`/flow-init`은 ..." 문장에서 `/flow-upgrade`· 제거:
```
조용히 스킵됩니다. `/flow-init`은 **기존 등록의 source를 보존**하므로 이걸로는
안 바뀝니다 — 직접 갱신하세요:
```

(c) `### /flow-upgrade` 섹션(L373-378) 전체를 init 재실행 설명으로 교체:
```markdown
### `/flow-init` 재실행 — 플러그인 갱신 후 동기화

플러그인이 업데이트돼도 호스트의 스크립트 사본은 자동으로 바뀌지 않습니다(복사본이라서).
`/flow-init`을 다시 실행하면 스크립트·정책 파일을 다시 복사하고 게이트 경로를 보정합니다
(재동기화는 비대화로 항상 먼저 실행). 빠진 config 슬롯이 있으면 보충을 제안하고, 그 외에는
무엇을 재설정할지 물어봅니다(아무것도 안 고르면 재동기화만). 예전 `/flow-upgrade`는 여기에
통합되었습니다.
```

- [ ] **Step 3: CLAUDE.md**

(a) L33 skills 목록에서 `flow-upgrade ·` 제거:
```
skills/     flow · flow-init · flow-uninstall · task-import · task-sync · harness-init · doc-sync · harness-authoring   (/슬래시 = 스킬)
```

(b) L37 스크립트 설명:
```
            check-deps.sh(의존성 점검·안내) · flow_init_setup.py(flow-init 셋업/재실행 + --uninstall 정리)
```

(c) L50 동기화 서술 — "플러그인 갱신 후 호스트 사본 동기화는 `/flow-upgrade`(config 무손상)" 를 교체:
```
- **스크립트 전파는 단방향**: `scripts/`(SOURCE·SSOT) → 캐시(재설치) → `<host>/.claude/vway-kit/scripts/`(실행 사본). 고칠 땐 SOURCE만, 호스트 사본 직접 수정 금지(재설치 시 덮어써짐). 플러그인 갱신 후 호스트 사본 동기화는 `/flow-init` 재실행(config 무손상), 호스트 정리는 `/flow-uninstall`.
```

- [ ] **Step 4: scripts/flow_init_setup.py docstring/주석**

(a) L2 docstring:
```
(대화형 부분은 /flow-init 커맨드의 Claude 담당)
```
(b) L98 주석 — "flow-init·flow-upgrade 재실행 시" → "flow-init 재실행 시":
```
# 구버전(루트 분산) → 신버전(분류) config/증거 이전 대상. flow-init 재실행
```

- [ ] **Step 5: github/api-contract.workflow.example.yml 주석**

L2:
```
# 직접 수정해도 /flow-init 재실행은 덮어쓰지 않고 "수동 확인"으로 보고만 한다.
```

- [ ] **Step 6: 살아있는 문서 검증**

```bash
grep -rn "flow-upgrade" --include=*.md --include=*.py --include=*.yml . | grep -v "docs/superpowers/"
```
Expected: 출력 없음(운영 문서·코드에 `flow-upgrade` 없음; 과거 spec/plan 의 historical 언급만 `docs/superpowers/` 아래 남음).

- [ ] **Step 7: 린트·회귀**

```bash
uv run ruff check && uv run ruff format --check && uv run pytest -q
```
Expected: All checks passed / 전체 PASS(로직 무변경).

- [ ] **Step 8: 커밋**

```bash
git add README.md USAGE.md CLAUDE.md scripts/flow_init_setup.py github/api-contract.workflow.example.yml
git commit -m "docs: retire flow-upgrade, point to flow-init re-run"
```

---

## Self-Review

**1. Spec coverage:**
- flow-upgrade 삭제 → Task 1 Step 1. ✅
- init 단일 진입점 + 재실행 분기(재동기화 자동 → 슬롯 보충 → opt-in 재설정) → Task 1 Step 3-4. ✅
- description 갱신 → Task 1 Step 2. ✅
- 참조 정리(README/USAGE/CLAUDE.md/flow_init_setup.py/workflow) → Task 2. ✅
- 마이그레이션 안내(별칭 없이 문서) → Task 2 Step 1-2. ✅
- flow_init_setup.py 로직 무변경 → Global Constraints + Task 2 는 docstring 만. ✅
- historical 제외 → Task 2 Step 6 grep 이 docs/superpowers 제외. ✅

**2. Placeholder scan:** 모든 step 에 정확한 before/after 텍스트·명령 포함. "적절히" 류 없음. ✅

**3. Type consistency:** 코드 시그니처 변경 없음(문서 작업). 라벨 `[config 슬롯 점검]` 은 기존 Task(slot backfill)에서 확정된 값과 일치. 재설정 섹션 명칭(config 값/webhook/teams 블록/teamer)이 Task 1 Execution modes ↔ Task 2 문서에서 일관. ✅
