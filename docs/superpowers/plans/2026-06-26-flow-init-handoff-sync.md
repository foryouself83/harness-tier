# flow-init handoff 종류 동기화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** example 에만 있는 handoff 종류를 감지해 flow-upgrade 는 안내하고 flow-init 은 동의 후 호스트 config 에 삽입하게 한다.

**Architecture:** 비교는 `flow_init_setup.py` 의 순수 함수(읽기 전용)로 두고 `run_setup` 보고에 노출한다. flow-upgrade 는 그 보고를 relay(안내만), flow-init 은 보고를 보고 AskUserQuestion 후 Claude 가 example 블록을 Edit 삽입한다. 삽입은 enable:false·주석 보존.

**Tech Stack:** Python 3.8+ (stdlib + PyYAML), pytest, uv. 스킬 문서는 Markdown.

## Global Constraints

- **읽기 전용 비교**: `missing_handoff_kinds` 는 example·host config 를 PyYAML 로 **읽기만** 한다(쓰기 아님 — 주석 파괴 무관). 파싱 실패·파일 부재는 빈 결과(FAIL-OPEN — 점검이 설치를 막지 않는다).
- **config 무접촉(flow-upgrade)**: flow-upgrade 는 호스트 config 를 쓰지 않는다 — 감지·안내만. critical rule 유지.
- **주석/포맷 보존**: 호스트 flow-config.yaml 삽입은 PyYAML 재작성이 아니라 flow-init 의 Claude 가 Edit 로(example 블록 텍스트 그대로, 주석·`enable:false` 포함). `check_precommit`·`render_workflow` 와 동일 원칙.
- **자동 활성화 금지**: 삽입은 항상 `enable:false`. 사용자가 검토 후 켠다.
- **Windows 인코딩 방어**: 파일 읽기는 `encoding="utf-8"`. 스크립트는 `force_utf8_io()` 적용(기존 main 유지).
- **커밋 규율(gitlint)**: 제목 ≤50자, 본문 1줄 이상. `git commit -m "<제목>" -m "<본문>"`.

## File Structure

- `scripts/flow_init_setup.py` (수정) — `EXAMPLE_CONFIG` 상수, `missing_handoff_kinds`·`report_missing_handoff` 함수, `run_setup` 보고 통합
- `tests/test_flow_init_setup.py` (수정) — 비교 함수·보고·run_setup 통합 테스트
- `skills/flow-init/SKILL.md` (수정) — Step 2 직후 삽입 단계
- `skills/flow-upgrade/SKILL.md` (수정) — 보고 relay 항목 한 줄

---

### Task 1: `missing_handoff_kinds` 비교 함수

**Files:**
- Modify: `scripts/flow_init_setup.py` (상수 추가 + 함수 추가; `load_contract_config` 근처 521-533 영역에 함께 둔다)
- Test: `tests/test_flow_init_setup.py`

**Interfaces:**
- Consumes: 기존 `config_path(host)` (이미 import 됨, 라인 47)
- Produces: `missing_handoff_kinds(host: Path, plugin: Path) -> list[str]` — example 의 handoff 종류 키 중 호스트 config 에 없는 것을 example 등장 순으로 반환. 파싱 실패·부재는 안전 처리. (인자 순서 `(host, plugin)` — `run_setup`·`render_workflow` 와 통일.)

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_flow_init_setup.py` 상단 import 에 `missing_handoff_kinds` 를 추가하고(기존 import 블록 끝에 한 줄), 파일 끝에 테스트 추가. (테스트는 tmp plugin/host 를 직접 구성해 실제 example 파일에 의존하지 않는다.)

```python
def _mk_example(plugin: Path, handoff_yaml: str) -> None:
    """tmp 플러그인에 flow-config.example.yaml 을 쓴다(handoff 섹션만)."""
    (plugin / "flow-config.example.yaml").write_text(handoff_yaml, encoding="utf-8")


def _mk_host_config(host: Path, text: str) -> None:
    """tmp 호스트의 config_path 위치에 flow-config.yaml 을 쓴다."""
    from scripts.flow_init_setup import config_path

    cfg = config_path(host)
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(text, encoding="utf-8")


def test_missing_handoff_kinds_returns_example_only(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(
        plugin,
        "handoff:\n  summary:\n    enable: true\n  qa:\n    enable: false\n"
        "  done_flag:\n    enable: false\n",
    )
    _mk_host_config(host, "handoff:\n  summary:\n    enable: true\n  qa:\n    enable: false\n")
    assert missing_handoff_kinds(host, plugin) == ["done_flag"]


def test_missing_handoff_kinds_no_host_section(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "handoff:\n  summary:\n    enable: true\n  qa:\n    enable: false\n")
    _mk_host_config(host, "branches:\n  integration: dev\n")  # handoff 섹션 없음
    assert missing_handoff_kinds(host, plugin) == ["summary", "qa"]


def test_missing_handoff_kinds_all_present(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "handoff:\n  summary:\n    enable: true\n")
    _mk_host_config(host, "handoff:\n  summary:\n    enable: true\n  extra:\n    enable: true\n")
    assert missing_handoff_kinds(host, plugin) == []


def test_missing_handoff_kinds_host_absent(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "handoff:\n  summary:\n    enable: true\n")
    # 호스트 config 파일 자체가 없음 → 전부 missing
    assert missing_handoff_kinds(host, plugin) == ["summary"]


def test_missing_handoff_kinds_example_absent(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    # example 파일 없음 → []
    assert missing_handoff_kinds(host, plugin) == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_flow_init_setup.py::test_missing_handoff_kinds_returns_example_only -v`
Expected: FAIL — `ImportError: cannot import name 'missing_handoff_kinds'`

- [ ] **Step 3: 최소 구현** — `scripts/flow_init_setup.py` 의 `WORKFLOW_TEMPLATE` 상수 근처(65행 부근)에 상수를 추가:

```python
EXAMPLE_CONFIG = "flow-config.example.yaml"  # 플러그인 SOURCE(handoff 종류 SSOT)
```

그리고 `load_contract_config`(521-533) 바로 위 또는 아래에 함수 추가:

```python
def _load_yaml_safe(path: Path) -> dict:
    """YAML 파일을 dict 로 읽는다. 부재·파싱 실패·비dict 는 {}(FAIL-OPEN)."""
    import yaml

    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def missing_handoff_kinds(host: Path, plugin: Path) -> list[str]:
    """example 에 있고 호스트 config 에 없는 handoff 종류 키(example 등장 순).
    호스트에 handoff 섹션이 없으면 example 종류 전부. 파싱 실패·부재는 안전 처리."""
    ex = _load_yaml_safe(plugin / EXAMPLE_CONFIG)
    cur = _load_yaml_safe(config_path(host))
    ex_h = ex.get("handoff") if isinstance(ex.get("handoff"), dict) else {}
    cur_h = cur.get("handoff") if isinstance(cur.get("handoff"), dict) else {}
    return [k for k in ex_h if k not in cur_h]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_flow_init_setup.py -k missing_handoff -v`
Expected: PASS (5개 전부)

- [ ] **Step 5: 커밋**

```bash
git add scripts/flow_init_setup.py tests/test_flow_init_setup.py
git commit -m "feat(flow-init): detect missing handoff kinds" -m "example 에만 있는 handoff 종류를 읽기 전용으로 비교하는 순수 함수. 파싱 실패·부재는 FAIL-OPEN 으로 빈 목록."
```

---

### Task 2: `report_missing_handoff` + `run_setup` 통합

**Files:**
- Modify: `scripts/flow_init_setup.py` (`report_missing_handoff` 함수 추가; `run_setup` 579-608 에 보고 블록 추가)
- Test: `tests/test_flow_init_setup.py`

**Interfaces:**
- Consumes: `missing_handoff_kinds(host, plugin)` (Task 1)
- Produces: `report_missing_handoff(host: Path, plugin: Path) -> list[str]` — 빠진 종류가 없으면 `["  [=] handoff 종류 최신 (skip)"]`, 있으면 `[i]` 안내 2줄.

- [ ] **Step 1: 실패하는 테스트 작성** — import 에 `report_missing_handoff` 추가, 파일 끝에 테스트 추가:

```python
def test_report_missing_handoff_lists_new(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(
        plugin,
        "handoff:\n  summary:\n    enable: true\n  done_flag:\n    enable: false\n",
    )
    _mk_host_config(host, "handoff:\n  summary:\n    enable: true\n")
    out = report_missing_handoff(host, plugin)
    assert any("done_flag" in line for line in out)
    assert any("/flow-init" in line for line in out)


def test_report_missing_handoff_skip_when_current(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "handoff:\n  summary:\n    enable: true\n")
    _mk_host_config(host, "handoff:\n  summary:\n    enable: true\n")
    out = report_missing_handoff(host, plugin)
    assert out == ["  [=] handoff 종류 최신 (skip)"]


def test_run_setup_reports_missing_handoff(tmp_path: Path, capsys):
    from scripts.flow_init_setup import run_setup

    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(
        plugin,
        "handoff:\n  summary:\n    enable: true\n  done_flag:\n    enable: false\n",
    )
    _mk_host_config(host, "handoff:\n  summary:\n    enable: true\n")
    run_setup(host, plugin)
    captured = capsys.readouterr().out
    assert "[handoff 종류 점검]" in captured
    assert "done_flag" in captured
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_flow_init_setup.py::test_report_missing_handoff_lists_new -v`
Expected: FAIL — `ImportError: cannot import name 'report_missing_handoff'`

- [ ] **Step 3: 최소 구현** — `scripts/flow_init_setup.py` 의 `missing_handoff_kinds` 바로 아래에 추가:

```python
def report_missing_handoff(host: Path, plugin: Path) -> list[str]:
    """run_setup 보고용: 빠진 handoff 종류를 사람이 읽을 줄로. 없으면 skip 한 줄."""
    kinds = missing_handoff_kinds(host, plugin)
    if not kinds:
        return ["  [=] handoff 종류 최신 (skip)"]
    return [
        f"  [i] example 에 새 handoff 종류 {len(kinds)}개: {', '.join(kinds)}",
        "      → /flow-init 으로 호스트 config 에 추가를 검토하세요.",
    ]
```

그리고 `run_setup` 의 `render_workflow` 출력 블록과 `detect_autoupdate_auth` 블록 **사이**에 삽입:

```python
    print("[handoff 종류 점검]")
    for line in report_missing_handoff(host, plugin):
        print(line)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_flow_init_setup.py -k "report_missing or run_setup_reports" -v`
Expected: PASS (3개)

- [ ] **Step 5: 회귀 확인 + 커밋**

Run: `uv run pytest tests/test_flow_init_setup.py -q`
Expected: PASS (기존 포함 전부)

```bash
git add scripts/flow_init_setup.py tests/test_flow_init_setup.py
git commit -m "feat(flow-init): report missing handoff in setup" -m "run_setup 가 [handoff 종류 점검] 블록을 출력해 flow-init·flow-upgrade 둘 다 새 종류를 안내받는다."
```

---

### Task 3: flow-init·flow-upgrade SKILL 문서 갱신

**Files:**
- Modify: `skills/flow-init/SKILL.md` (Step 2 직후 새 하위 단계)
- Modify: `skills/flow-upgrade/SKILL.md` (보고 relay 항목 + critical rule 보강)

**Interfaces:**
- Consumes: Task 2 의 `[handoff 종류 점검]` 보고
- Produces: 없음 (문서)

- [ ] **Step 1: flow-init SKILL 에 삽입 단계 추가** — `skills/flow-init/SKILL.md` 의 Step 2 끝("swap the language-specific `local` hooks for their stack." 단락 뒤)에 새 단계를 추가:

````markdown
### Step 2.5 — Sync new handoff kinds (interactive — Claude, skippable)

The Step 2 script prints a `[handoff 종류 점검]` block. If it lists new handoff
kinds present in `${PLUGIN}/flow-config.example.yaml` but absent from the host
`flow-config.yaml`:

1. `AskUserQuestion`: "example 에 새 handoff 종류 N개(<목록>)가 있습니다. 호스트
   config 에 추가할까요?" — allow selecting all or a subset (default: all).
2. For each accepted kind, read its block from
   `${PLUGIN}/flow-config.example.yaml` and **insert it verbatim** (comments and
   `enable: false` intact) into the host
   `${ROOT}/.claude/vway-kit/config/flow-config.yaml` `handoff:` section using
   **Edit** — never a PyYAML round-trip (preserves the user's comments/format).
   If the host has no `handoff:` section, add the section.
3. Tell the user to adjust `field`/`value` for their environment and flip
   `enable: true` when ready. Inserted kinds stay `enable: false` so nothing
   writes to Teamer until the user opts in.

Skip entirely when the report lists no new kinds.
````

- [ ] **Step 2: flow-upgrade SKILL 에 안내 항목 추가** — `skills/flow-upgrade/SKILL.md` 의 Execution 2번 항목 목록(`- **Renders** ...` 항목 뒤)에 한 줄 추가:

```markdown
   - **Checks** new handoff kinds: prints a `[handoff 종류 점검]` block listing
     kinds present in the plugin's `flow-config.example.yaml` but absent from the
     host `flow-config.yaml`. Upgrade only **reports** them (config is never
     touched) — run `/flow-init` to review and add them interactively.
```

- [ ] **Step 3: flow-upgrade critical rule 보강** — `skills/flow-upgrade/SKILL.md` 의 critical rule 1 ("Non-destructive to host config" 항목) 끝에 한 문장 추가(괄호 안 또는 문장 끝):

```markdown
1. **Non-destructive to host config** — never regenerate `flow-config.yaml`, prompt
   for webhooks, write credentials, or rewrite the `CLAUDE.md` teams block. Those are
   `/flow-init`'s interactive job. (The contract-test workflow is also
   never overwritten if present. New handoff kinds are **detected and reported
   only** — adding them to `flow-config.yaml` is `/flow-init`'s job.)
```

- [ ] **Step 4: 문서 정적 검사 통과 확인**

Run: `uv run pre-commit run --all-files`
Expected: PASS (마크다운/trailing-whitespace/end-of-file 통과)

- [ ] **Step 5: 커밋**

```bash
git add skills/flow-init/SKILL.md skills/flow-upgrade/SKILL.md
git commit -m "docs(flow): wire handoff kind sync into skills" -m "flow-init Step 2.5 가 새 종류를 동의 후 Edit 삽입(enable:false), flow-upgrade 는 감지·안내만(config 무접촉)."
```

---

### Task 4: 전체 회귀 + 린트 최종 확인

**Files:**
- 없음 (검증만)

- [ ] **Step 1: 전체 테스트**

Run: `uv run pytest`
Expected: PASS (전체)

- [ ] **Step 2: 린트·포맷**

Run: `uv run ruff check && uv run ruff format --check`
Expected: 통과

- [ ] **Step 3: 정적 분석 전체**

Run: `uv run pre-commit run --all-files`
Expected: 전부 Passed

---

## Self-Review (작성자 점검 결과)

- **Spec 커버리지**: missing_handoff_kinds(Task 1) · run_setup 보고(Task 2) · flow-upgrade 안내(Task 3 Step 2-3) · flow-init 동의 후 삽입(Task 3 Step 1) · FAIL-OPEN·주석 보존·enable:false(Global Constraints + Task 코드) — spec 의 모든 요구가 task 에 매핑됨.
- **Placeholder**: 모든 코드 스텝에 실제 코드·명령·기대출력 포함. TODO 없음.
- **Type 일관성**: `missing_handoff_kinds(host, plugin) -> list[str]` · `report_missing_handoff(host, plugin) -> list[str]` — 두 함수 모두 `(host, plugin)` 순서로 통일(run_setup·render_workflow 패턴과 일치, 호출 혼동 제거).
- **비고**: 삽입(flow-init Edit)은 문서 절차라 자동 테스트 없음 — Task 3 는 pre-commit 정적 검사로만 검증. 실제 삽입 동작은 수동/실사용 검증.
