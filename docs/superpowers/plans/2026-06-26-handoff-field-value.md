# handoff 필드 값 채우기 (`value`/`append`) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** handoff 각 종류에 `value`(고정값/자동 날짜)와 `append`(누적/교체) 키를 추가해, 특정 Teamer 필드에 원하는 값을 원하는 방식으로 채우게 한다.

**Architecture:** 결정 로직은 순수 함수(`handoff_resolve.py`)에 두고, 값 치환·래핑은 task-sync 커맨드가, 필드별 append/replace 적용과 PUT 은 `teamer_api.py` 가 한다. 기존 `append_item_content` 를 colXX 누적에 재사용한다.

**Tech Stack:** Python 3.8+ (stdlib + PyYAML + keyring), pytest, uv.

## Global Constraints

- **순수 함수 유지**: `handoff_resolve.py`·`teamer_api.py` 의 결정/파싱 로직은 keyring·HTTP·날짜에 무의존이어야 단위 테스트가 된다. 날짜 치환은 task-sync 단계 책임.
- **Windows 인코딩 방어**: 훅/스크립트 Python 은 cp949 로캘 — `force_utf8_io()` 와 `encoding="utf-8"` 를 빠뜨리지 않는다(기존 코드에 이미 적용됨, 신규 코드도 동일).
- **하위호환**: `resolve_handoff` 결과 dict 의 기존 키(`source_mode`·`write_mode`) 의미 불변, `value` 키만 추가. 기존 `--col-override col=path`(replace) 호출 형태 유지.
- **reuse-before-build**: colXX 누적은 신규 로직을 짜지 않고 기존 `append_item_content(existing, new)` 를 재사용한다.
- **날짜 토큰**: `${today}` → 실행일 `YYYY-MM-DD`. 그 외 토큰은 리터럴 그대로(관대 처리).
- **커밋 규율(gitlint)**: 제목 ≤50자, 본문 1줄 이상 필수. 모든 커밋은 `-m "<제목>" -m "<본문>"` 형태로.

## File Structure

- `scripts/handoff_resolve.py` (수정) — `resolve_source_mode`(value→literal), `resolve_write_mode`(append 인자), `resolve_handoff`(value 키 추가)
- `scripts/teamer_api.py` (수정) — `_build_put_fields`(col_appends 인자), `main`(--col-append 인자)
- `tests/test_handoff_resolve.py` (수정) — value/append/literal 테스트
- `tests/test_teamer_api.py` (수정) — colXX append 테스트
- `skills/task-sync/SKILL.md` (수정) — literal 분기, ${today} 치환, append 인자 전달
- `flow-config.example.yaml` (수정) — value/append 예시

---

### Task 1: `resolve_write_mode` 에 `append` 플래그 반영

**Files:**
- Modify: `scripts/handoff_resolve.py:58-60`
- Test: `tests/test_handoff_resolve.py`

**Interfaces:**
- Consumes: 없음 (순수 함수)
- Produces: `resolve_write_mode(field: str, append: object = None) -> str` — append 가 불리언이면 우선(`True→"append"`, `False→"replace"`), 아니면 field 기반 폴백.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_handoff_resolve.py` 의 기존 `test_resolve_write_mode` 아래에 추가:

```python
def test_resolve_write_mode_append_flag_overrides():
    # 불리언 플래그가 field 기반 기본을 덮어쓴다
    assert resolve_write_mode("col22", True) == "append"
    assert resolve_write_mode("item_content", False) == "replace"


def test_resolve_write_mode_falls_back_when_no_flag():
    # 플래그 미지정(None) → field 기반 폴백
    assert resolve_write_mode("item_content", None) == "append"
    assert resolve_write_mode("col22", None) == "replace"


def test_resolve_write_mode_ignores_non_bool_flag():
    # 불리언이 아닌 값(문자열 등)은 미지정 취급 → field 폴백
    assert resolve_write_mode("col22", "yes") == "replace"
    assert resolve_write_mode("item_content", "no") == "append"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_handoff_resolve.py::test_resolve_write_mode_append_flag_overrides -v`
Expected: FAIL — `TypeError: resolve_write_mode() takes 1 positional argument but 2 were given`

- [ ] **Step 3: 최소 구현** — `scripts/handoff_resolve.py` 의 `resolve_write_mode` 를 교체:

```python
def resolve_write_mode(field: str, append: object = None) -> str:
    """append 가 불리언이면 우선(True→append, False→replace).
    아니면 field 기반 폴백(item_content → append, 그 외 colXX → replace)."""
    if isinstance(append, bool):
        return "append" if append else "replace"
    return "append" if field == "item_content" else "replace"
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_handoff_resolve.py -k write_mode -v`
Expected: PASS (기존 `test_resolve_write_mode` 포함 전부)

- [ ] **Step 5: 커밋**

```bash
git add scripts/handoff_resolve.py tests/test_handoff_resolve.py
git commit -m "feat(handoff): append flag overrides write_mode" -m "handoff spec 의 append 불리언이 field 기반 기본 write_mode 를 덮어쓴다. 미지정/비불리언이면 기존 폴백 유지(하위호환)."
```

---

### Task 2: `value` → `literal` source_mode + `resolve_handoff` 에 value 키

**Files:**
- Modify: `scripts/handoff_resolve.py:49-55` (`resolve_source_mode`), `scripts/handoff_resolve.py:74-93` (`resolve_handoff`)
- Test: `tests/test_handoff_resolve.py`

**Interfaces:**
- Consumes: `resolve_write_mode(field, append)` (Task 1)
- Produces:
  - `resolve_source_mode(spec: dict) -> str` — spec 에 `value` 가 not-None 이면 `"literal"` 을 최우선 반환.
  - `resolve_handoff(...)` 결과 dict 에 `"value": spec.get("value")` 키 추가, `write_mode` 는 `resolve_write_mode(field, spec.get("append"))` 로 결정.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_handoff_resolve.py` 에 추가:

```python
def test_resolve_source_mode_value_is_literal():
    # value 가 있으면 author/AskUserQuestion 보다 우선해 literal
    assert resolve_source_mode({"value": "완료", "author": "AI"}) == "literal"
    assert resolve_source_mode({"value": "${today}", "AskUserQuestion": True}) == "literal"


def test_resolve_source_mode_no_value_unchanged():
    # value 없으면 기존 결정 그대로(회귀)
    assert resolve_source_mode({"author": "AI"}) == "ai_auto"
    assert resolve_source_mode({"author": "bsyu", "AskUserQuestion": True}) == "human_ask"


def test_resolve_handoff_includes_value_and_append(tmp_path):
    cfg = tmp_path / "flow-config.yaml"
    cfg.write_text(
        "handoff:\n"
        "  done_date:\n    enable: true\n    field: col30\n"
        '    value: "${today}"\n    append: false\n'
        "  progress_log:\n    enable: true\n    field: col33\n    append: true\n",
        encoding="utf-8",
    )
    result = resolve_handoff(cfg, tmp_path / "p", tmp_path / "h")
    by_kind = {r["kind"]: r for r in result}
    assert by_kind["done_date"]["value"] == "${today}"
    assert by_kind["done_date"]["source_mode"] == "literal"
    assert by_kind["done_date"]["write_mode"] == "replace"
    assert by_kind["progress_log"]["value"] is None
    assert by_kind["progress_log"]["write_mode"] == "append"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_handoff_resolve.py::test_resolve_source_mode_value_is_literal -v`
Expected: FAIL — `assert 'ai_auto' == 'literal'`

- [ ] **Step 3: 최소 구현**

`scripts/handoff_resolve.py` 의 `resolve_source_mode` 첫머리에 value 분기 추가:

```python
def resolve_source_mode(spec: dict) -> str:
    """종류 spec → source_mode. value 최우선(literal), 다음 AskUserQuestion 토글·author."""
    if spec.get("value") is not None:
        return "literal"
    ai = is_ai_author(spec.get("author", ""))
    ask = spec.get("AskUserQuestion") is True
    if ai:
        return "ai_guided" if ask else "ai_auto"
    return "human_ask" if ask else "human_doc"
```

같은 파일 `resolve_handoff` 의 result.append 블록을 교체(field 계산 직후 append 읽기, value 키 추가):

```python
        field = str(spec.get("field", ""))
        result.append(
            {
                "kind": kind,
                "author": spec.get("author", ""),
                "field": field,
                "value": spec.get("value"),
                "source_mode": resolve_source_mode(spec),
                "write_mode": resolve_write_mode(field, spec.get("append")),
                "template_path": resolve_template_path(spec, kind, plugin, host),
                "instruction": spec.get("instruction", ""),
            }
        )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_handoff_resolve.py -v`
Expected: PASS (전체 — 기존 테스트 포함 회귀 없음)

- [ ] **Step 5: 커밋**

```bash
git add scripts/handoff_resolve.py tests/test_handoff_resolve.py
git commit -m "feat(handoff): value source resolves to literal" -m "spec 에 value 가 있으면 source_mode literal 로 결정하고, resolve_handoff 결과에 value 키를 추가한다. value 없으면 기존 동작 불변."
```

---

### Task 3: `teamer_api` colXX append 지원 (`--col-append`)

**Files:**
- Modify: `scripts/teamer_api.py:231-247` (`_build_put_fields`), `scripts/teamer_api.py:311-319` (update 파서), `scripts/teamer_api.py:365-373` (update 호출)
- Test: `tests/test_teamer_api.py`

**Interfaces:**
- Consumes: 기존 `append_item_content(existing, new)`, `merge_preserve_fields(item)`, `_parse_col_overrides(pairs)`
- Produces: `_build_put_fields(item, project_no, workitem_no, item_no, new_content, col_overrides, status_no, col_appends=None) -> dict` — `col_appends` 의 각 colXX 는 GET 보존 기존값 뒤에 `append_item_content` 로 누적.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_teamer_api.py` 에 추가(상단 import 에 `_build_put_fields` 포함):

```python
from scripts.teamer_api import _build_put_fields  # noqa: E402


def test_build_put_fields_col_append_concats_existing():
    item = {"item_content": None, "col33": "<p>old</p>"}
    fields = _build_put_fields(
        item, "996", "188180", "1", "", {}, None, col_appends={"col33": "<p>new</p>"}
    )
    assert fields["itemVO.col33"] == "<p>old</p><p>new</p>"


def test_build_put_fields_col_append_when_existing_null():
    item = {"item_content": None, "col33": None}
    fields = _build_put_fields(
        item, "996", "188180", "1", "", {}, None, col_appends={"col33": "<p>new</p>"}
    )
    assert fields["itemVO.col33"] == "<p>new</p>"


def test_build_put_fields_col_override_still_replaces():
    item = {"item_content": None, "col33": "<p>old</p>"}
    fields = _build_put_fields(
        item, "996", "188180", "1", "", {"col33": "REPLACED"}, None
    )
    assert fields["itemVO.col33"] == "REPLACED"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_teamer_api.py::test_build_put_fields_col_append_concats_existing -v`
Expected: FAIL — `TypeError: _build_put_fields() got an unexpected keyword argument 'col_appends'`

- [ ] **Step 3: 최소 구현**

`scripts/teamer_api.py` 의 `_build_put_fields` 시그니처와 본문 교체:

```python
def _build_put_fields(
    item, project_no, workitem_no, item_no, new_content, col_overrides, status_no, col_appends=None
):
    """GET 보존 필드 + itemContent(append) + overrides(replace) + appends(누적) + status + 정적."""
    fields = merge_preserve_fields(item)
    fields.update(_STATIC_PUT_FIELDS)
    fields["itemVO.itemNo"] = str(item_no)
    fields["itemVO.projectNo"] = str(project_no)
    fields["itemVO.workitemNo"] = str(workitem_no)
    fields["itemVO.itemContent"] = append_item_content(item.get("item_content"), new_content)
    for col, val in (col_overrides or {}).items():
        fields[f"itemVO.{col}"] = val
    for col, val in (col_appends or {}).items():
        fields[f"itemVO.{col}"] = append_item_content(item.get(col), val)
    if status_no is not None:
        fields["itemVO.itemWorkflowStatusNo"] = str(status_no)
    elif item.get("item_workflow_status_no") is not None:
        fields["itemVO.itemWorkflowStatusNo"] = str(item["item_workflow_status_no"])
    return fields
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_teamer_api.py -k "col_append or col_override" -v`
Expected: PASS

- [ ] **Step 5: update CLI 에 `--col-append` 배선**

`scripts/teamer_api.py` 의 update 서브파서(`pu.add_argument("--col-override", ...)` 다음 줄)에 추가:

```python
    pu.add_argument("--col-append", action="append", default=[])
```

같은 파일 update 분기의 `_build_put_fields(...)` 호출에 `col_appends` 인자 추가:

```python
            fields = _build_put_fields(
                match,
                args.project_no,
                args.workitem_no,
                args.item_no,
                _read_file(args.content_file),
                _parse_col_overrides(args.col_override),
                status_no,
                col_appends=_parse_col_overrides(args.col_append),
            )
```

- [ ] **Step 6: 전체 teamer 테스트 통과 확인**

Run: `uv run pytest tests/test_teamer_api.py -v`
Expected: PASS (회귀 없음)

- [ ] **Step 7: 커밋**

```bash
git add scripts/teamer_api.py tests/test_teamer_api.py
git commit -m "feat(teamer): colXX append via --col-append" -m "col_appends 는 GET 보존 기존값 뒤에 append_item_content 로 누적한다. 기존 --col-override(replace) 와 경로 파싱은 불변(하위호환)."
```

---

### Task 4: task-sync 절차 + config 예시 갱신 (문서)

**Files:**
- Modify: `skills/task-sync/SKILL.md:42-60`
- Modify: `flow-config.example.yaml:54-67`

**Interfaces:**
- Consumes: Task 2 의 `source_mode == "literal"`·`value` 키, Task 3 의 `--col-append`
- Produces: 없음 (문서 — 커맨드 실행 절차)

- [ ] **Step 1: SKILL.md 4단계에 literal 분기 추가** — `skills/task-sync/SKILL.md` 4단계 source_mode 목록(`human_doc` 항목 뒤, "Wrap every generated content" 앞)에 추가:

```markdown
   - `literal`: skip AI/AskUserQuestion/template entirely. Use the resolved `value` verbatim. Replace the token `${today}` with the execution date in `YYYY-MM-DD` format; leave any other text as-is. **Do NOT wrap in the Author marker div** — literal values (dates, flags) must be the raw value so Teamer field types are not broken by markup.
```

- [ ] **Step 2: SKILL.md 5단계에 col-append 분류 추가** — 5단계를 교체:

```markdown
5. **Classify by field/write_mode**
   - `field == item_content`: queue for `item_content` (the update script always appends item_content; for an `item_content` replace use the col path is N/A — item_content is append-only at the API layer).
   - else with `write_mode == replace`: write the html/value to a temp file and add `--col-override <field>=<tmpfile>`.
   - else with `write_mode == append`: write the html/value to a temp file and add `--col-append <field>=<tmpfile>`.
```

- [ ] **Step 3: SKILL.md 8단계 호출 예시 갱신** — 8단계 코드블록의 update 호출에 col-append 줄을 추가:

```bash
     python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" update \
       --project-no <project_no> --workitem-no <workitem_no> \
       --item-no <item_no> --searchtext {task_id} \
       --content-file <tmp_content.html> \
       [--col-override col22=<tmp_col22.html> ...] \
       [--col-append col33=<tmp_col33.html> ...] \
       [--target-status-name 검토 --workflow-no <teamer.workflow_no>]
```

- [ ] **Step 4: flow-config.example.yaml 에 value/append 예시 추가** — handoff 블록의 `qa` 종류 뒤에 추가:

```yaml
  done_flag:                        # 신규 종류 — 특정 필드에 고정값
    enable: false
    field: col31                    # colXX → replace 기본
    value: "완료"                   # value 있으면 template/AI/래핑 생략, 값 그대로
    append: false                   # 누적(true)/교체(false) 명시 — 미지정 시 field 기본
  done_date:                        # 신규 종류 — 특정 필드에 자동 날짜
    enable: false
    field: col30
    value: "${today}"               # 실행일(YYYY-MM-DD)로 치환
    append: false
```

- [ ] **Step 5: 정적 분석 통과 확인**

Run: `uv run pre-commit run --all-files`
Expected: PASS (yaml/마크다운 검사 통과 — 예시 config 가 유효 YAML)

- [ ] **Step 6: 커밋**

```bash
git add skills/task-sync/SKILL.md flow-config.example.yaml
git commit -m "docs(task-sync): literal value + col-append flow" -m "task-sync 가 literal source 를 ${today} 치환·래핑 없이 처리하고, write_mode append 면 --col-append 로 넘긴다. config 예시에 value/append 종류 추가."
```

---

### Task 5: 전체 회귀 + 린트 최종 확인

**Files:**
- 없음 (검증만)

- [ ] **Step 1: 전체 테스트**

Run: `uv run pytest`
Expected: PASS (전체)

- [ ] **Step 2: 린트·포맷**

Run: `uv run ruff check && uv run ruff format --check`
Expected: 통과 (오류 없음)

- [ ] **Step 3: 정적 분석 전체**

Run: `uv run pre-commit run --all-files`
Expected: 전부 Passed

---

## Self-Review (작성자 점검 결과)

- **Spec 커버리지**: value→literal(Task 2) · append→write_mode(Task 1) · colXX append(Task 3) · literal 래핑 생략·${today} 치환·인자 전달(Task 4) · config 예시(Task 4) · 하위호환 회귀(Task 1·2·3 회귀 테스트) — spec 의 모든 요구가 task 에 매핑됨.
- **Placeholder**: 모든 코드 스텝에 실제 코드·명령·기대출력 포함. TODO 없음.
- **Type 일관성**: `resolve_write_mode(field, append)` · `resolve_source_mode(spec)` · `_build_put_fields(..., col_appends=None)` 시그니처가 정의 task 와 소비 task 에서 동일.
- **비고**: `item_content` 의 replace 는 API 계층상 append 전용이라 비목표(SKILL 5단계에 명시). 워크플로 상태 전이 통합은 spec 비목표(이번 plan 제외).
