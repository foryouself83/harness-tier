# flow-config 슬롯 보충 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/flow-init` 재설정 시 flow-config.yaml 을 전체 재구성하지 않고, example 과 재귀 비교해 호스트에 빠진 슬롯만 verbatim 삽입한다(기존 handoff 동기화를 일반 메커니즘으로 흡수).

**Architecture:** 스크립트(`flow_init_setup.py`)는 빠진 슬롯을 **식별만** 하고(PyYAML 읽기 전용 재귀 비교), 실제 삽입은 flow-init 의 대화형 단계에서 Claude 가 example 블록을 verbatim Edit 한다. 이 repo 의 확립된 패턴(스크립트=기계적 판정, Claude=verbatim Edit)과 일치한다.

**Tech Stack:** Python 3.8+ / PyYAML(읽기 비교만, 새 의존성 없음) / pytest / uv.

## Global Constraints

- 새 런타임 의존성 추가 금지 — PyYAML 은 읽기 비교에만 사용(덤프 금지 — 주석 파괴).
- "빠짐" 판단 = **키 부재만**. 값이 비어도(`key: ""`/`null`) 키가 있으면 제외(의도적 빈 값 보존).
- 매직값은 `_vway_paths` / 기존 상수 재사용(rule-dry-constants). `EXAMPLE_CONFIG` 상수 이미 존재.
- host config 부재·빈 config·YAML 파싱 실패 → example 최상위 전부 반환(신규 설치 동등); example 부재 → 빈 목록 — `_load_yaml_safe` 재사용.
- 함수는 경로를 인자로 받아 결과를 반환(단위 테스트 가능) — 기존 파일 관례 준수.
- 커밋은 Conventional Commits 50/72. master 직접 금지(현재 브랜치 `feat/flow-config-slot-backfill`).

---

### Task 1: `missing_config_slots` 재귀 식별 + handoff 흡수

기존 `missing_handoff_kinds`(반환 `list[str]`)·`report_missing_handoff` 를 일반 함수 `missing_config_slots`(반환 `list[dict]`)·`report_missing_config_slots` 로 대체하고, `run_setup` 의 보고 블록 라벨을 `[handoff 종류 점검]` → `[config 슬롯 점검]` 으로 바꾼다. handoff 는 `parent == ["handoff"]` 인 일반 슬롯의 특수 케이스로 자연 흡수된다.

**Files:**
- Modify: `scripts/flow_init_setup.py` (함수 `missing_handoff_kinds`/`report_missing_handoff` 위치 ~536-556, `run_setup` ~643-645)
- Test: `tests/test_flow_init_setup.py` (기존 handoff 테스트 ~458-557 전환 + 신규)

**Interfaces:**
- Produces:
  - `missing_config_slots(host: Path, plugin: Path) -> list[dict]` — 각 항목 `{"path": list[str], "parent": list[str], "label": str}`. example 등장 순서 보존.
  - `report_missing_config_slots(host: Path, plugin: Path) -> list[str]` — 사람이 읽을 보고 줄(없으면 `["  [=] config 슬롯 최신 (skip)"]`).
  - 내부 헬퍼 `_diff_missing(ex: dict, cur: dict, prefix: list[str]) -> list[dict]`.
- Consumes: 기존 `_load_yaml_safe`, `config_path`, `EXAMPLE_CONFIG`.

- [ ] **Step 1: 신규 식별 함수 테스트 작성**

`tests/test_flow_init_setup.py` 의 기존 handoff 테스트 블록(`_mk_example` 정의부터 `test_run_setup_reports_missing_handoff` 까지, 약 458-557행)을 아래로 **교체**한다. import 도 갱신한다(`missing_handoff_kinds`, `report_missing_handoff` → `missing_config_slots`, `report_missing_config_slots`).

```python
def _mk_example(plugin: Path, body: str) -> None:
    """tmp 플러그인에 flow-config.example.yaml 을 쓴다(임의 본문)."""
    (plugin / "flow-config.example.yaml").write_text(body, encoding="utf-8")


def test_missing_config_slots_top_level_section(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "branches:\n  integration: dev\ncontract_test:\n  enable: true\n")
    _mk_host_config(host, "branches:\n  integration: dev\n")
    assert missing_config_slots(host, plugin) == [
        {"path": ["contract_test"], "parent": [], "label": "contract_test"}
    ]


def test_missing_config_slots_nested_key(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "test:\n  command: x\n  coverage_threshold: 80\n")
    _mk_host_config(host, "test:\n  command: x\n")
    assert missing_config_slots(host, plugin) == [
        {
            "path": ["test", "coverage_threshold"],
            "parent": ["test"],
            "label": "test.coverage_threshold",
        }
    ]


def test_missing_config_slots_empty_value_preserved(tmp_path: Path):
    # host 에 키가 있고 값이 비어도(빈 문자열/null) 빠짐으로 보지 않는다.
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "doc_sync:\n  service_docs: services/*/CLAUDE.md\n")
    _mk_host_config(host, 'doc_sync:\n  service_docs: ""\n')
    assert missing_config_slots(host, plugin) == []


def test_missing_config_slots_all_present(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "test:\n  command: x\n")
    _mk_host_config(host, "test:\n  command: x\n  extra: y\n")
    assert missing_config_slots(host, plugin) == []


def test_missing_config_slots_handoff_kind_nested(tmp_path: Path):
    # handoff 흡수: 섹션은 있고 종류만 빠지면 parent=["handoff"] 슬롯.
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(
        plugin,
        "handoff:\n  summary:\n    enable: true\n  done_flag:\n    enable: false\n",
    )
    _mk_host_config(host, "handoff:\n  summary:\n    enable: true\n")
    assert missing_config_slots(host, plugin) == [
        {"path": ["handoff", "done_flag"], "parent": ["handoff"], "label": "handoff.done_flag"}
    ]


def test_missing_config_slots_section_absent_inserts_whole(tmp_path: Path):
    # host 에 handoff 섹션 자체가 없으면 섹션 통째가 삽입 단위.
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "handoff:\n  summary:\n    enable: true\n")
    _mk_host_config(host, "branches:\n  integration: dev\n")
    assert missing_config_slots(host, plugin) == [
        {"path": ["handoff"], "parent": [], "label": "handoff"}
    ]


def test_missing_config_slots_order_preserved(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "a: 1\nb: 2\nc: 3\n")
    _mk_host_config(host, "b: 2\n")
    assert [s["label"] for s in missing_config_slots(host, plugin)] == ["a", "c"]


def test_missing_config_slots_host_absent(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "branches:\n  integration: dev\nhandoff:\n  summary:\n    enable: true\n")
    # host config 파일 없음 → example 최상위 전부
    assert [s["label"] for s in missing_config_slots(host, plugin)] == ["branches", "handoff"]


def test_missing_config_slots_example_absent(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_host_config(host, "branches:\n  integration: dev\n")
    assert missing_config_slots(host, plugin) == []


def test_report_missing_config_slots_lists_new(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "test:\n  command: x\ncontract_test:\n  enable: true\n")
    _mk_host_config(host, "test:\n  command: x\n")
    out = report_missing_config_slots(host, plugin)
    assert any("contract_test" in line for line in out)


def test_report_missing_config_slots_skip_when_current(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "test:\n  command: x\n")
    _mk_host_config(host, "test:\n  command: x\n")
    assert report_missing_config_slots(host, plugin) == ["  [=] config 슬롯 최신 (skip)"]


def test_run_setup_reports_config_slots(tmp_path: Path, capsys):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "test:\n  command: x\ncontract_test:\n  enable: true\n")
    _mk_host_config(host, "test:\n  command: x\n")
    run_setup(host, plugin)
    captured = capsys.readouterr().out
    assert "[config 슬롯 점검]" in captured
```

> 참고: `_mk_host_config` 헬퍼는 파일에 이미 존재한다(handoff 테스트가 쓰던 것). 위치를 옮기지 말고 그대로 쓴다. 혹시 `_mk_host_config` 가 기존 handoff 블록 안에 정의돼 있었다면, 교체 시 정의를 보존한다.

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_flow_init_setup.py -k "config_slots or report_missing_config or run_setup_reports_config" -q`
Expected: FAIL — `ImportError: cannot import name 'missing_config_slots'` (함수 미정의).

- [ ] **Step 3: 식별 함수 구현**

`scripts/flow_init_setup.py` 에서 기존 `missing_handoff_kinds`·`report_missing_handoff` 두 함수(약 536-556행)를 아래로 **교체**한다:

```python
def _diff_missing(ex: dict, cur: dict, prefix: list[str]) -> list[dict]:
    """example 에 있고 host(cur)에 없는 키를 삽입 단위로 재귀 수집(example 순서).

    - cur 에 키가 없으면 그 지점을 삽입 단위로 기록(하위로 더 내려가지 않음 —
      부모 블록째 verbatim 삽입되므로).
    - 양쪽 dict 면 더 내려간다. cur 쪽이 dict 가 아니면(스칼라/리스트/빈값) 멈춘다.
    """
    out: list[dict] = []
    for key, ex_val in ex.items():
        if key not in cur:
            path = prefix + [key]
            out.append({"path": path, "parent": list(prefix), "label": ".".join(path)})
        elif isinstance(ex_val, dict) and isinstance(cur.get(key), dict):
            out.extend(_diff_missing(ex_val, cur[key], prefix + [key]))
    return out


def missing_config_slots(host: Path, plugin: Path) -> list[dict]:
    """example 에 있고 host config 에 없는 슬롯을 삽입 단위로 반환(example 등장 순).

    각 항목 {"path", "parent", "label"}. '빠짐' 은 키 부재만(값이 비어도 키 있으면
    제외 — 의도적 빈 값 보존). host config 부재·빈 config·파싱 실패 시에는 example
    최상위 슬롯 전부를 반환한다(신규 설치와 동등). 이 함수는 flow-init 이 host config
    존재 시에만 호출한다(신규 설치는 별도 전체 생성 경로). example 부재 → [].
    flow-init 이 이 목록으로 example 블록을 verbatim 삽입한다(주석 보존).
    """
    ex = _load_yaml_safe(plugin / EXAMPLE_CONFIG)
    if not ex:
        return []
    cur = _load_yaml_safe(config_path(host))
    return _diff_missing(ex, cur, [])


def report_missing_config_slots(host: Path, plugin: Path) -> list[str]:
    """run_setup 보고용: 빠진 config 슬롯을 사람이 읽을 줄로. 없으면 skip 한 줄."""
    slots = missing_config_slots(host, plugin)
    if not slots:
        return ["  [=] config 슬롯 최신 (skip)"]
    labels = ", ".join(s["label"] for s in slots)
    return [
        f"  [i] example 에 새 config 슬롯 {len(slots)}개: {labels}",
        "      → /flow-init 으로 호스트 config 에 추가를 검토하세요.",
    ]
```

> `_load_yaml_safe` 는 비-dict 입력에 `{}` 를 반환하므로 `cur` 는 항상 dict 다(별도 isinstance 가드 불필요). `ex` 도 동일하나, 빈 example 은 조기 반환한다.

- [ ] **Step 4: `run_setup` 보고 호출 갱신**

`scripts/flow_init_setup.py` 의 `run_setup` 에서 handoff 보고 블록(약 643-645행)을 교체한다:

```python
    print("[config 슬롯 점검]")
    for line in report_missing_config_slots(host, plugin):
        print(line)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/test_flow_init_setup.py -q`
Expected: PASS (전체). 실패 시 `missing_handoff_kinds` 잔존 import/호출이 없는지 확인.

- [ ] **Step 6: 린트·전체 테스트**

Run: `uv run ruff check && uv run ruff format --check && uv run pytest -q`
Expected: All checks passed / 전체 PASS.

- [ ] **Step 7: 커밋**

```bash
git add scripts/flow_init_setup.py tests/test_flow_init_setup.py
git commit -m "feat(flow-init): detect missing config slots recursively"
```

---

### Task 2: flow-init / flow-upgrade SKILL 문서 개정

스크립트가 식별한 빠진 슬롯을 Claude 가 verbatim Edit 으로 삽입하는 절차를 문서화한다. flow-init Step 1 은 keep/reconfigure 이분법을 유지하고, 슬롯 보충은 Step 2.5(Step 2 스크립트 실행 후)에서 처리한다. flow-upgrade 는 보고 라벨만 일반화(동작 무변경).

**Files:**
- Modify: `skills/flow-init/SKILL.md` (Step 1 ~91-115, Step 2 보고 항목 ~167-185 의 handoff 블록)
- Modify: `skills/flow-upgrade/SKILL.md` (handoff 보고 설명 ~61-64, Critical rule ~76)

**Interfaces:** 없음(문서). 본문은 Task 1 의 함수/출력 라벨(`[config 슬롯 점검]`, `report_missing_config_slots`)과 일치해야 한다.

- [ ] **Step 1: flow-init Step 1 — keep/reconfigure 이분법 복구**

`skills/flow-init/SKILL.md` 의 Step 1 첫 항목을 아래로 교체한다(기존 파일이 있으면
keep/skip 혹은 reconfigure-only, 전체 재입력 없음):

```markdown
1. If `${ROOT}/.claude/vway-kit/config/flow-config.yaml` already exists, **ask**
   whether to reconfigure existing values (default: keep). If keeping, skip to Step 2
   — do **not** rewrite the file. If reconfiguring, edit only the specific values the
   user wants to change (never a full re-entry). Either way, **missing-slot backfill
   happens in Step 2.5** (it adds new slots from the example while preserving existing
   values/comments).
```

items 2-4(템플릿 읽기 / 슬롯 질문 / 파일 쓰기)는 **파일 부재(신규 설치)** 경로임을
명시하는 lead-in("If the file is **absent** (first-time setup), build it:")을 추가해
명확히 한다.

- [ ] **Step 2: Step 2.5 — 실제 슬롯 보충 절차 작성**

`skills/flow-init/SKILL.md` 의 "### Step 2.5" 섹션을 실제 보충 절차로 교체한다
(슬롯 보충은 Step 2 스크립트가 빠진 슬롯을 식별한 뒤 Step 2.5 에서 처리):

```markdown
### Step 2.5 — Backfill missing config slots (interactive — Claude, skippable)

The Step 2 script prints a `[config 슬롯 점검]` block listing slots present in
`${PLUGIN}/flow-config.example.yaml` but absent from the host config (key-absence
only; handoff kinds appear as `handoff.<kind>`).

- If it lists missing slots, `AskUserQuestion` ("example 에 새 config 슬롯 N개
  (<목록>)가 있습니다. 호스트 config 에 추가할까요?", allow all or a subset, default all).
- For each accepted slot, read its block from `${PLUGIN}/flow-config.example.yaml` and
  **insert it verbatim** (comments and example defaults intact) into the host config at
  the parent anchor (end of the parent section; top-level slots append a new section)
  using **Edit** — never a PyYAML round-trip (preserves comments/format).
- Tell the user to adjust values for their environment; `enable`-style flags stay as in
  the example (handoff kinds stay `enable: false` until opted in).
- Skip entirely when the report lists no missing slots.
```

- [ ] **Step 3: Step 2 스크립트 보고 항목 라벨 갱신**

`skills/flow-init/SKILL.md` 의 Step 2 본문에서 handoff 보고를 설명하는 문장(있다면 "prints a `[handoff 종류 점검]` block")을 `[config 슬롯 점검]` 으로 바꾸고, "handoff kinds present in ... but absent" 설명을 "config slots present in the example but absent from the host config (handoff kinds included)" 로 일반화한다.

- [ ] **Step 4: flow-upgrade SKILL 라벨 일반화**

`skills/flow-upgrade/SKILL.md` 의 handoff 점검 항목(약 61-64행)을 아래로 교체한다:

```markdown
   - **Checks** missing config slots: prints a `[config 슬롯 점검]` block listing
     slots present in the plugin's `flow-config.example.yaml` but absent from the host
     `flow-config.yaml` (handoff kinds included, as `handoff.<kind>`). Upgrade only
     **reports** them (config is never touched) — run `/flow-init` to review and add
     them interactively.
```

그리고 Critical rule 1(약 76행)의 괄호 문구 "New handoff kinds are **detected and reported only**" 를 "New config slots are **detected and reported only**" 로 바꾼다.

- [ ] **Step 5: 문서 정합성 검토**

Read 로 두 SKILL.md 를 다시 읽고 확인: (a) `[config 슬롯 점검]` 라벨이 Task 1 의 `run_setup` 출력과 정확히 일치, (b) `missing_handoff_kinds`/`[handoff 종류 점검]` 잔존 언급 없음(Grep), (c) Step 1 ↔ Step 2.5 모순 없음.

Run: `grep -rn "handoff 종류 점검\|missing_handoff" skills/`
Expected: 출력 없음(모두 일반화됨).

- [ ] **Step 6: 커밋**

```bash
git add skills/flow-init/SKILL.md skills/flow-upgrade/SKILL.md
git commit -m "docs(flow-init): wire slot backfill into skills"
```

---

## Self-Review

**1. Spec coverage:**
- 핵심 동작 재정의(키 부재 판단, 슬롯 보충) → Task 1 Step 3 함수 + Task 2 Step 1 SKILL. ✅
- `missing_config_slots` 재귀·삽입 단위 → Task 1 Step 3 `_diff_missing`. ✅
- handoff 흡수 → Task 1(함수 교체) + Task 2 Step 2(Step 2.5 통합). ✅
- flow-init verbatim Edit 흐름 → Task 2 Step 1. ✅
- flow-upgrade 보고만 유지 → Task 2 Step 4. ✅
- 테스트(최상위/하위키/빈값/일치/중첩/순서/부재) → Task 1 Step 1. ✅

**2. Placeholder scan:** 모든 step 에 실제 코드/명령 포함. "적절히 처리" 류 없음. ✅

**3. Type consistency:** `missing_config_slots` 반환 `list[dict]` (`path`/`parent`/`label`) — Task 1 정의와 Task 2 본문 참조 일치. `report_missing_config_slots` 반환 `list[str]`, skip 줄 `"  [=] config 슬롯 최신 (skip)"` — 테스트(Task 1 Step 1)와 구현(Step 3) 일치. 출력 라벨 `[config 슬롯 점검]` — run_setup(Task 1 Step 4)·테스트·SKILL(Task 2) 일치. ✅
