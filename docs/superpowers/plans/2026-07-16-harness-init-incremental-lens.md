# harness-init 증분 렌즈 업데이트 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기존 `docs/code-style/<stack>.md`에 빠진 품질 렌즈 BP를 렌즈별 관리 블록으로 안전하게 채우는 harness-init 증분 경로를 구현한다.

**Architecture:** `scripts/harness_scaffold.py`에 순수 문자열 함수(문서 스캔·3분류, 렌즈 블록 order-preserving upsert, flat 섹션 통째 교체)를 추가하고 `apply_plan`에 신규 `lens_upsert` 액션으로 연결한다. 저작 `.md`(template·harness-init SKILL·tech-doc-guide)는 렌즈 관리 블록 형태와 스캔→스코핑→dispatch→apply 흐름을 반영한다. 편집 감지는 없다 — git diff + preview/confirm이 안전망.

**Tech Stack:** Python 3.8+ (stdlib `re`, `pathlib`), pytest, `uv`.

## Global Constraints

- **설계 SSOT**: [docs/superpowers/specs/2026-07-16-harness-init-incremental-lens-design.md](../specs/2026-07-16-harness-init-incremental-lens-design.md). 이 계획은 스펙을 구현한다.
- **렌즈 정규 순서(9-7)**: `correctness · ux · a11y · performance · security · maintainability · cross-cutting · i18n` — 마커 segment key이자 삽입 순서.
- **마커 형식**: 기존 `_marker_begin`/`_marker_end` 재사용, `marker_id = code-style:lens:<stack>:<lens>`. 마커 문구 "managed by /harness-init — edits inside are overwritten" 유지.
- **편집 감지 없음**: manifest/sha 도입 금지. 안전망은 git diff + harness-init preview→confirm.
- **No overwrite 정합**(harness-rules rule 2): 문서 자체는 안 덮고 관리 블록만 upsert. flat 마이그레이션은 `## Best Practices` **섹션 한정** 교체.
- **인코딩**: 모든 파일 IO `encoding="utf-8"` (cp949 호스트 방어).
- **테스트 스타일**: `import scripts.harness_scaffold as hs`, pytest 함수 + `tmp_path`.
- **검증 커맨드**: `uv run pytest`, `uv run ruff check && uv run ruff format --check`.
- **커밋 타입**: 코드/consumer 동작 변경이므로 `feat`(전파). 스펙/플랜 문서만은 `docs`.

---

### Task 1: 렌즈 상수·마커 id·관리 블록 빌더 (DRY 리팩터)

**Files:**
- Modify: `scripts/harness_scaffold.py` (상수 + 헬퍼 추가; `upsert_marker_block` 내부를 헬퍼로 정리)
- Test: `tests/test_harness_scaffold.py`

**Interfaces:**
- Produces: `hs.LENS_ORDER: tuple[str,...]`, `hs.lens_marker_id(stack: str, lens: str) -> str`, `hs._managed_block(marker_id: str, body: str) -> str`

- [ ] **Step 1: Write the failing test**

```python
def test_lens_marker_id_format():
    assert hs.lens_marker_id("typescript-react", "ux") == "code-style:lens:typescript-react:ux"


def test_lens_order_canonical():
    assert hs.LENS_ORDER == (
        "correctness", "ux", "a11y", "performance",
        "security", "maintainability", "cross-cutting", "i18n",
    )


def test_managed_block_wraps_body_with_markers():
    block = hs._managed_block("code-style:lens:go:performance", "### Performance\n- x")
    assert block.startswith("<!-- code-style:lens:go:performance BEGIN")
    assert block.rstrip().endswith("<!-- code-style:lens:go:performance END -->")
    assert "### Performance\n- x" in block
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_harness_scaffold.py::test_lens_marker_id_format -v`
Expected: FAIL (`AttributeError: module 'scripts.harness_scaffold' has no attribute 'lens_marker_id'`)

- [ ] **Step 3: Write minimal implementation**

`scripts/harness_scaffold.py`에서 `_marker_begin`/`_marker_end` 정의 **아래**에 추가:

```python
# Canonical quality-lens order (harness-rules 9-7). Each key is the marker segment
# id and the deterministic insertion order within a code-style Best Practices section.
LENS_ORDER = (
    "correctness", "ux", "a11y", "performance",
    "security", "maintainability", "cross-cutting", "i18n",
)


def lens_marker_id(stack: str, lens: str) -> str:
    return f"code-style:lens:{stack}:{lens}"


def _managed_block(marker_id: str, body: str) -> str:
    return f"{_marker_begin(marker_id)}\n{body.rstrip()}\n{_marker_end(marker_id)}\n"
```

그리고 `upsert_marker_block`의 `block = f"{begin}\n{body.rstrip()}\n{end}\n"` 줄을 다음으로 교체(DRY):

```python
    block = _managed_block(marker_id, body)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_harness_scaffold.py -v`
Expected: PASS (신규 3개 + 기존 upsert 회귀 전부 그린)

- [ ] **Step 5: Commit**

```bash
git add scripts/harness_scaffold.py tests/test_harness_scaffold.py
git commit -m "feat(scaffold): lens marker id + managed-block helper"
```

---

### Task 2: Best Practices 섹션 로케이터 + 문서 3분류 스캔 (순수)

**Files:**
- Modify: `scripts/harness_scaffold.py`
- Test: `tests/test_harness_scaffold.py`

**Interfaces:**
- Consumes: `LENS_ORDER`, `lens_marker_id` (Task 1)
- Produces: `hs.find_bp_section(text: str) -> tuple[int,int] | None`, `hs.scan_code_style(text: str, stack: str) -> dict` (키: `has_bp: bool`, `state: "flat"|"lens"|None`, `present: list[str]`)

- [ ] **Step 1: Write the failing test**

```python
_FLAT = "# React Code Style\n\n## Best Practices\n- keep components small\n\n## Toolchain\n- vite\n"

def _lens_doc(stack):
    return (
        "# X\n\n## Best Practices (by quality lens)\n"
        + hs._managed_block(hs.lens_marker_id(stack, "ux"), "### UX\n- guard")
        + "\n## Toolchain\n- x\n"
    )


def test_find_bp_section_spans_heading_to_next_h2():
    s, e = hs.find_bp_section(_FLAT)
    assert _FLAT[s:e].startswith("## Best Practices")
    assert "## Toolchain" not in _FLAT[s:e]


def test_find_bp_section_none_when_absent():
    assert hs.find_bp_section("# X\n\n## Toolchain\n- x\n") is None


def test_scan_flat_doc():
    r = hs.scan_code_style(_FLAT, "typescript-react")
    assert r == {"has_bp": True, "state": "flat", "present": []}


def test_scan_lens_doc_reports_present():
    r = hs.scan_code_style(_lens_doc("go"), "go")
    assert r["state"] == "lens"
    assert r["present"] == ["ux"]


def test_scan_no_bp_heading_is_none_state():
    r = hs.scan_code_style("# X\n\n## Toolchain\n- x\n", "go")
    assert r == {"has_bp": False, "state": None, "present": []}


def test_scan_recognizes_by_quality_lens_suffix_heading():
    # heading variant must still be found
    assert hs.find_bp_section(_lens_doc("go")) is not None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_harness_scaffold.py::test_scan_flat_doc -v`
Expected: FAIL (`AttributeError: ... 'scan_code_style'`)

- [ ] **Step 3: Write minimal implementation**

`scripts/harness_scaffold.py`에 추가(Task 1 헬퍼 아래):

```python
_BP_HEADING_RE = re.compile(r"^##[ \t]+Best Practices\b.*$", re.MULTILINE)
_H2_RE = re.compile(r"^##[ \t]+", re.MULTILINE)


def find_bp_section(text: str):
    """(start, end) char offsets of the '## Best Practices...' section — heading
    line through just before the next top-level '## ' heading (or EOF). None if
    there is no Best Practices heading. '###' sub-headings do not terminate it."""
    m = _BP_HEADING_RE.search(text)
    if not m:
        return None
    nxt = _H2_RE.search(text, m.end())
    return (m.start(), nxt.start() if nxt else len(text))


def scan_code_style(text: str, stack: str) -> dict:
    """Classify a code-style doc's Best Practices section.
    state: 'lens' (has lens markers) | 'flat' (BP heading, no markers) |
    None (no BP heading — non-standard, caller skips)."""
    span = find_bp_section(text)
    if span is None:
        return {"has_bp": False, "state": None, "present": []}
    section = text[span[0]:span[1]]
    present = [
        lens for lens in LENS_ORDER
        if f"{lens_marker_id(stack, lens)} BEGIN" in section
    ]
    return {"has_bp": True, "state": "lens" if present else "flat", "present": present}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_harness_scaffold.py -v`
Expected: PASS (신규 6개 + 기존 전부 그린)

- [ ] **Step 5: Commit**

```bash
git add scripts/harness_scaffold.py tests/test_harness_scaffold.py
git commit -m "feat(scaffold): scan + classify code-style Best Practices section"
```

---

### Task 3: 렌즈 블록 order-preserving upsert + flat 섹션 통째 교체 (순수)

**Files:**
- Modify: `scripts/harness_scaffold.py`
- Test: `tests/test_harness_scaffold.py`

**Interfaces:**
- Consumes: `find_bp_section`, `_managed_block`, `lens_marker_id`, `_marker_begin`, `_marker_end`, `LENS_ORDER`
- Produces: `hs.upsert_lens_block(text: str, stack: str, lens: str, body: str) -> str`, `hs.build_bp_section(stack: str, lenses: list[tuple[str,str]]) -> str`, `hs.replace_bp_section(text: str, stack: str, lenses: list[tuple[str,str]]) -> str`

- [ ] **Step 1: Write the failing test**

```python
def test_upsert_lens_block_inserts_in_canonical_order():
    # doc already has 'ux'; inserting 'correctness' (earlier) must land BEFORE ux
    doc = _lens_doc("go")
    out = hs.upsert_lens_block(doc, "go", "correctness", "### Correctness\n- c")
    i_corr = out.index("code-style:lens:go:correctness BEGIN")
    i_ux = out.index("code-style:lens:go:ux BEGIN")
    assert i_corr < i_ux
    assert "## Toolchain" in out  # sibling section preserved


def test_upsert_lens_block_replaces_existing():
    doc = _lens_doc("go")
    out = hs.upsert_lens_block(doc, "go", "ux", "### UX\n- NEW")
    assert "- NEW" in out
    assert out.count("code-style:lens:go:ux BEGIN") == 1  # not duplicated


def test_upsert_lens_block_requires_bp_section():
    with pytest.raises(ValueError):
        hs.upsert_lens_block("# X\n\n## Toolchain\n- x\n", "go", "ux", "b")


def test_build_bp_section_orders_by_lens_order():
    section = hs.build_bp_section("go", [("ux", "### UX"), ("correctness", "### C")])
    assert section.startswith("## Best Practices (by quality lens)")
    assert section.index("correctness BEGIN") < section.index("ux BEGIN")


def test_replace_bp_section_swaps_flat_and_keeps_siblings():
    out = hs.replace_bp_section(_FLAT, "typescript-react", [("ux", "### UX\n- g")])
    assert "keep components small" not in out          # flat prose replaced
    assert "code-style:lens:typescript-react:ux BEGIN" in out
    assert "## Toolchain" in out and "- vite" in out    # sibling preserved
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_harness_scaffold.py::test_replace_bp_section_swaps_flat_and_keeps_siblings -v`
Expected: FAIL (`AttributeError: ... 'replace_bp_section'`)

- [ ] **Step 3: Write minimal implementation**

`scripts/harness_scaffold.py`에 추가:

```python
BP_HEADING = "## Best Practices (by quality lens)"


def upsert_lens_block(text: str, stack: str, lens: str, body: str) -> str:
    """Insert or replace one lens block inside the Best Practices section, keeping
    LENS_ORDER. Requires a Best Practices section to exist (ValueError otherwise)."""
    span = find_bp_section(text)
    if span is None:
        raise ValueError("no '## Best Practices' section for a lens block")
    marker_id = lens_marker_id(stack, lens)
    begin, end = _marker_begin(marker_id), _marker_end(marker_id)
    block = _managed_block(marker_id, body)
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", re.DOTALL)
    if pattern.search(text):
        return pattern.sub(block, text, count=1)
    # insert before the first later-ordered lens already present; else end of section
    insert_at = span[1]
    for later in LENS_ORDER[LENS_ORDER.index(lens) + 1:]:
        idx = text.find(_marker_begin(lens_marker_id(stack, later)), span[0], span[1])
        if idx != -1:
            insert_at = idx
            break
    prefix, suffix = text[:insert_at], text[insert_at:]
    sep = "" if prefix.endswith("\n") else "\n"
    return prefix + sep + block + suffix


def build_bp_section(stack: str, lenses) -> str:
    """Fresh Best Practices section: canonical heading + lens blocks in LENS_ORDER.
    `lenses` = iterable of (lens, body)."""
    by_key = {lens: body for lens, body in lenses}
    blocks = [
        _managed_block(lens_marker_id(stack, lens), by_key[lens])
        for lens in LENS_ORDER if lens in by_key
    ]
    return BP_HEADING + "\n" + "".join(blocks)


def replace_bp_section(text: str, stack: str, lenses) -> str:
    """Replace the whole '## Best Practices' section (flat migration) with a fresh
    lens-block section, preserving surrounding sections."""
    span = find_bp_section(text)
    if span is None:
        raise ValueError("no '## Best Practices' section to replace")
    new_section = build_bp_section(stack, lenses).rstrip() + "\n"
    tail = text[span[1]:]
    if tail:
        new_section += "\n"  # blank line before the next section
    return text[:span[0]] + new_section + tail
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_harness_scaffold.py -v`
Expected: PASS (신규 5개 + 기존 전부 그린)

- [ ] **Step 5: Commit**

```bash
git add scripts/harness_scaffold.py tests/test_harness_scaffold.py
git commit -m "feat(scaffold): lens-block upsert + flat section replace"
```

---

### Task 4: apply_plan `lens_upsert` 액션 통합

**Files:**
- Modify: `scripts/harness_scaffold.py` (`apply_plan` 분기 추가; 필요 시 `validate_plan`이 액션을 통과시키는지 확인)
- Test: `tests/test_harness_scaffold.py`

**Interfaces:**
- Consumes: `build_bp_section`, `replace_bp_section`, `upsert_lens_block` (Task 3)
- Produces: `apply_plan` 이 `{"action":"lens_upsert","path":<rel>,"stack":<s>,"lenses":[{"lens":..,"body":..}],"migrate":bool}` 엔트리를 처리(파일 부재→create, `migrate`→섹션 교체, 아니면 렌즈별 additive upsert)

- [ ] **Step 1: Write the failing test**

```python
def _plan(entry):
    return {"root": ".", "files": [entry]}


def test_apply_lens_upsert_creates_when_absent(tmp_path):
    entry = {"action": "lens_upsert", "path": "docs/code-style/go.md",
             "stack": "go", "lenses": [{"lens": "performance", "body": "### Performance\n- p"}]}
    rep = hs.apply_plan(tmp_path, _plan(entry))
    out = (tmp_path / "docs/code-style/go.md").read_text(encoding="utf-8")
    assert "docs/code-style/go.md" in rep["created"]
    assert "code-style:lens:go:performance BEGIN" in out


def test_apply_lens_upsert_additive_on_lens_doc(tmp_path):
    p = tmp_path / "docs/code-style/go.md"
    p.parent.mkdir(parents=True)
    p.write_text(_lens_doc("go"), encoding="utf-8")
    entry = {"action": "lens_upsert", "path": "docs/code-style/go.md", "stack": "go",
             "lenses": [{"lens": "performance", "body": "### Performance\n- p"}]}
    hs.apply_plan(tmp_path, _plan(entry))
    out = p.read_text(encoding="utf-8")
    assert "code-style:lens:go:ux BEGIN" in out          # existing kept
    assert "code-style:lens:go:performance BEGIN" in out  # new added


def test_apply_lens_upsert_migrate_replaces_flat(tmp_path):
    p = tmp_path / "docs/code-style/react.md"
    p.parent.mkdir(parents=True)
    p.write_text(_FLAT, encoding="utf-8")
    entry = {"action": "lens_upsert", "path": "docs/code-style/react.md",
             "stack": "typescript-react", "migrate": True,
             "lenses": [{"lens": "ux", "body": "### UX\n- g"}]}
    hs.apply_plan(tmp_path, _plan(entry))
    out = p.read_text(encoding="utf-8")
    assert "keep components small" not in out
    assert "code-style:lens:typescript-react:ux BEGIN" in out
```

> **Note:** `apply_plan(root, plan)`의 plan/entry 구조는 기존 코드가 쓰는 키에 맞춘다. 위 `_plan` 헬퍼의 `root`/`files` 키가 기존과 다르면 Step 3에서 기존 `apply_plan` 시그니처(순회 방식)에 맞춰 테스트를 교정한다(구현 전 기존 `apply_plan` 본문 확인 필수).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_harness_scaffold.py::test_apply_lens_upsert_creates_when_absent -v`
Expected: FAIL (액션 미처리 → 파일 미생성, `KeyError`/`assert` 실패)

- [ ] **Step 3: Write minimal implementation**

`apply_plan` 의 액션 분기(기존 `create`/`marker_upsert`/`else` 옆)에 추가:

```python
        elif action == "lens_upsert":
            stack = entry["stack"]
            lenses = [(x["lens"], x["body"]) for x in entry.get("lenses", [])]
            if not target.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(build_bp_section(stack, lenses).rstrip() + "\n",
                                  encoding="utf-8")
                report["created"].append(rel)
            else:
                text = target.read_text(encoding="utf-8")
                if entry.get("migrate"):
                    new = replace_bp_section(text, stack, lenses)
                else:
                    new = text
                    for lens, body in lenses:
                        new = upsert_lens_block(new, stack, lens, body)
                if new != text:
                    target.write_text(new, encoding="utf-8")
                report["updated"].append(rel)
```

`validate_plan`이 알 수 없는 `action`을 오류로 표시하면(구현 전 확인), `lens_upsert`를 marker 계열과 함께 허용 목록에 추가하고 최소 필드(`path`·`stack`·`lenses`) 존재만 확인한다.

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_harness_scaffold.py -v`
Expected: PASS (신규 3개 + 기존 전부 그린)

- [ ] **Step 5: Commit**

```bash
git add scripts/harness_scaffold.py tests/test_harness_scaffold.py
git commit -m "feat(scaffold): apply lens_upsert action (create/migrate/additive)"
```

---

### Task 5: 저작 `.md` 반영 (template · harness-init SKILL · tech-doc-guide)

**Files:**
- Modify: `skills/harness-authoring/templates/code-style.template.md`
- Modify: `skills/harness-init/SKILL.md`
- Modify: `skills/harness-authoring/references/tech-doc-guide.md`
- (검증) `tests/test_harness_scaffold.py` — 신규 테스트 없음, 전량 그린 유지

**Interfaces:**
- Consumes: 없음(런타임 코드 아님). scaffold의 마커 형식(`code-style:lens:<stack>:<lens>`)·9-7 순서와 **문구 일치**해야 함.

- [ ] **Step 1: 템플릿을 렌즈 관리 블록으로 교체**

`code-style.template.md`의 `## Best Practices (by quality lens)` 블록(현재 자유산문 + 주석 shape)을 다음으로 교체 — 각 렌즈가 관리 마커 블록임을 명시:

```markdown
## Best Practices (by quality lens)
<!-- 각 렌즈 = 관리 블록 <!-- code-style:lens:<stack>:<lens> BEGIN … END -->. 적용되는 렌즈만 emit
     (harness-rules 9-7·9-8, 9-2 evidence-based). 순서 = correctness·ux·a11y·performance·security·
     maintainability·cross-cutting·i18n. 코딩 가이드만; 소유 SSOT는 링크(중복 금지). 재실행 시 harness-init이
     빠진 렌즈 블록을 이 자리에 additive upsert 한다. -->
{{BEST_PRACTICES_LENS_BLOCKS}}
```

- [ ] **Step 2: harness-init SKILL에 증분 흐름 추가**

`skills/harness-init/SKILL.md`의 연구/생성 절차에 code-style 재실행 경로를 추가(스펙 §5 요약). 삽입 지점은 research dispatch 서술 근처. 넣을 문단:

```markdown
- **code-style 증분(렌즈 갭) 경로 — 통합 갭 모델**: `docs/code-style/<stack>.md`를 로컬 스캔(`harness_scaffold`
  scan)해 상태를 3분류(없음/flat 레거시/렌즈 문서)하고 present 렌즈를 집계한다. `갭 = 적용 렌즈 − present`
  (적용 렌즈는 스택 성격 기반 경량 판단 — research 아님). **research 전에** AskUserQuestion으로 무엇을 채울지
  확정: flat 레거시는 **스택 단위**(적용 렌즈 전부 마이그레이션), 렌즈 문서는 **렌즈 단위**(빠진 것 add). 확정된
  `(stack, lens)`만 research dispatch → `lens_upsert` 액션(flat=`migrate:true` 섹션 교체 / 렌즈문서=additive)
  으로 적용. 교체·마이그레이션 안전망은 **git diff + preview→confirm**(편집 감지·manifest 없음).
```

- [ ] **Step 3: tech-doc-guide에 블록 형태 반영**

`skills/harness-authoring/references/tech-doc-guide.md`의 code-style "Best Practices by quality lens" 항목에 한 줄 추가:

```markdown
  각 렌즈는 관리 마커 블록(`<!-- code-style:lens:<stack>:<lens> BEGIN … END -->`)으로 emit하여 harness-init
  재실행이 빠진 렌즈만 additive upsert 할 수 있게 한다(스펙: 증분 렌즈 업데이트).
```

- [ ] **Step 4: 전체 검증**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check`
Expected: PASS (291+신규 테스트 그린, ruff 클린). `.md`는 테스트 대상 아니나 회귀 없음 확인.

- [ ] **Step 5: Commit**

```bash
git add skills/harness-authoring/templates/code-style.template.md \
        skills/harness-init/SKILL.md \
        skills/harness-authoring/references/tech-doc-guide.md
git commit -m "feat(authoring): emit lens best practices as managed blocks"
```

---

## Self-Review

**Spec coverage:**
- §4 데이터 모델(렌즈 관리 블록) → Task 1(마커/블록) + Task 5(템플릿).
- §5-1 스캔 3분류 → Task 2. §5-5 위치 인식 insert + flat 섹션 교체 → Task 3. apply 연결 → Task 4.
- §5-2 적용렌즈 판정(경량) / §5-3 스코핑 질문 / §5-4 스코프드 dispatch → Task 5(harness-init SKILL, 서술).
- §5-6 안전망(git diff) / §7 manifest 무변경 → Global Constraints + 전 태스크에 편집감지 없음.
- §6 엣지: no-BP 스킵(Task 2 state None), 순서 유지(Task 3), 마커 손상은 기존 upsert `ValueError` 경로 재사용.

**Placeholder scan:** `{{BEST_PRACTICES_LENS_BLOCKS}}`는 템플릿 플레이스홀더(모델이 채움) — 코드 placeholder 아님. Task 4의 `apply_plan` 구조 확인 Note는 "구현 전 기존 본문 확인"의 정당한 지시(가짜 코드 아님).

**Type consistency:** `lens_marker_id(stack, lens)` · `find_bp_section`(튜플|None) · `scan_code_style`(dict) · `upsert_lens_block`/`build_bp_section`/`replace_bp_section`(str) · `lenses`=`list[(lens,body)]` — Task 1→4 전반 일치. apply 엔트리 `lenses`는 `[{"lens","body"}]`(dict) → apply_plan에서 `(lens,body)` 튜플로 변환(Task 4 Step 3)해 순수 함수에 전달. 일관.

## Execution Handoff

계획을 저장했습니다. 실행 방식 선택은 상위 세션(vdev Dev 오버레이)에서 안내합니다.
