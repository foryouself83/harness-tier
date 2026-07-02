# /task-sync handoff 기능 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `/task-sync` 가 config로 토글되는 "인수인계(handoff)" 내용을 지정된 Teamer 필드에 전달하고, 기존 AI 요약도 handoff의 한 종류로 일반화한다.

**Architecture:** 결정론적 로직(출처 4조합·write_mode·템플릿 경로 fallback)은 순수 함수 `scripts/handoff_resolve.py`로 빼서 TDD하고, 커맨드/에이전트(`task-sync.md`·`task-import.md`·`teamer-item-updater.md`)는 그 JSON 결과를 소비한다. 내용 생성(AI 대필·AskUserQuestion·PUT)은 비결정적이므로 마크다운 지침 + 수동 검증으로 둔다.

**Tech Stack:** Python 3.8+ (uv·pytest·ruff), PyYAML, 마크다운 커맨드/에이전트 지침, HTML 템플릿.

## Global Constraints

- **언어/도구:** Python ≥3.8, PyYAML. `uv run pytest` / `uv run ruff check && uv run ruff format --check`.
- **Windows 인코딩 (Invariant #2):** 모든 신규 Python에 `force_utf8_io()` + 파일 I/O `encoding="utf-8"` + JSON `ensure_ascii=False`. cp949 로캘에서 한글 print/open이 깨지면 안 됨.
- **게이트 아님:** `handoff_resolve.py`는 커밋 게이트가 아니다. `/task-sync`가 직접 호출하며, 오류/파싱 실패 시 **빈 결과**를 반환해 기존 동작으로 떨어진다(예외를 밖으로 던지지 않음).
- **이중 경로:** `${CLAUDE_PLUGIN_ROOT}`=읽기(템플릿·스크립트), `${CLAUDE_PROJECT_DIR}`=호스트(`flow-config.yaml`). 플러그인 디렉터리에 쓰지 않는다.
- **정책 vs 환경값:** `handoff`는 `flow-config.yaml`(환경값·gitignored)에 산다. `flow-tiers.yaml`(정책·불변) 아님.
- **Invariant #6:** PUT 시 GET의 colXX non-null 전부 보존. multipart/form-data·UTF-8(Node `https`). handoff colXX는 보존값 위에 replace.
- **하위호환:** `handoff` 또는 `handoff.summary` 미정의 시 기존 요약 동작(item_content append) 유지. summary 암묵 ON, 신규 종류는 명시해야 ON.
- **커밋 메시지:** gitlint 게이트 — `type(scope): subject` 컨벤션 준수.

## File Structure

| 파일 | 책임 |
|------|------|
| `scripts/handoff_resolve.py` (신규) | handoff 종류별 결정 순수 함수 + JSON CLI |
| `tests/test_handoff_resolve.py` (신규) | 위 단위 테스트 |
| `templates/handoff/summary.html` (신규) | 기존 3섹션 요약 구조/규칙 추출 |
| `agents/teamer-item-updater.md` (수정) | `col_overrides` 파라미터 추가 |
| `commands/task-sync.md` (수정) | handoff 순회·스크립트 호출·col_overrides 전달 |
| `commands/task-import.md` (수정) | human_doc 종류 섹션 스캐폴드 |
| `flow-config.example.yaml` (수정) | `handoff` 트리 주석 템플릿 |

---

### Task 1: handoff_resolve.py 결정 순수 함수 (load · source_mode · write_mode)

**Files:**
- Create: `scripts/handoff_resolve.py`
- Test: `tests/test_handoff_resolve.py`

**Interfaces:**
- Consumes: 없음 (PyYAML만).
- Produces:
  - `load_handoff_config(config_path: Path) -> dict` — handoff 트리 또는 `{}`
  - `is_ai_author(author: str) -> bool` — author가 `ai`/`llm`/`agent`(소문자) 중 하나
  - `resolve_source_mode(spec: dict) -> str` — `"ai_guided"|"ai_auto"|"human_ask"|"human_doc"`
  - `resolve_write_mode(field: str) -> str` — `"append"`(item_content) | `"replace"`(그 외)

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_handoff_resolve.py`:

```python
from pathlib import Path

from scripts.handoff_resolve import (
    is_ai_author,
    load_handoff_config,
    resolve_source_mode,
    resolve_write_mode,
)


def test_is_ai_author_variants():
    assert is_ai_author("AI")
    assert is_ai_author("llm")
    assert is_ai_author("Agent")
    assert not is_ai_author("bsyu")
    assert not is_ai_author("")


def test_resolve_source_mode_ai_guided():
    assert resolve_source_mode({"author": "AI", "AskUserQuestion": True}) == "ai_guided"


def test_resolve_source_mode_ai_auto():
    assert resolve_source_mode({"author": "AI", "AskUserQuestion": False}) == "ai_auto"


def test_resolve_source_mode_human_ask():
    assert resolve_source_mode({"author": "bsyu", "AskUserQuestion": True}) == "human_ask"


def test_resolve_source_mode_human_doc():
    assert resolve_source_mode({"author": "bsyu", "AskUserQuestion": False}) == "human_doc"


def test_resolve_source_mode_ask_defaults_false():
    # AskUserQuestion 미지정 → false 취급
    assert resolve_source_mode({"author": "AI"}) == "ai_auto"


def test_resolve_write_mode():
    assert resolve_write_mode("item_content") == "append"
    assert resolve_write_mode("col22") == "replace"


def test_load_handoff_config_missing(tmp_path: Path):
    assert load_handoff_config(tmp_path / "absent.yaml") == {}


def test_load_handoff_config_reads_tree(tmp_path: Path):
    cfg = tmp_path / "flow-config.yaml"
    cfg.write_text(
        "handoff:\n  qa:\n    enable: true\n    field: col22\n", encoding="utf-8"
    )
    assert load_handoff_config(cfg) == {"qa": {"enable": True, "field": "col22"}}


def test_load_handoff_config_no_handoff_key(tmp_path: Path):
    cfg = tmp_path / "flow-config.yaml"
    cfg.write_text("branches:\n  staging: stage\n", encoding="utf-8")
    assert load_handoff_config(cfg) == {}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_handoff_resolve.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.handoff_resolve'`

- [ ] **Step 3: 최소 구현 작성**

`scripts/handoff_resolve.py`:

```python
"""handoff 종류별 결정 로직 — 순수 함수. /task-sync · /task-import 가 호출해
각 종류의 (source_mode, write_mode, template_path, ...) 를 JSON 으로 받아 소비한다.

커밋 게이트가 아니므로 강제 차단과 무관하다. 결정 로직만 담고 실제 내용 생성(AI
대필, AskUserQuestion, Teamer PUT)은 호출자(커맨드/에이전트)가 한다. 파싱/입력
오류 시 빈 결과를 돌려 호출자가 기존 동작으로 떨어지게 한다.

각 함수는 인자로 받은 값만으로 결과를 반환하므로 단위 테스트가 가능하다.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

AI_AUTHORS = {"ai", "llm", "agent"}


def force_utf8_io() -> None:
    """stdout/stderr 를 UTF-8 로 재구성(Windows cp949 에서 한글 print 오류 방지)."""
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):
                pass


def load_handoff_config(config_path: Path) -> dict:
    """flow-config.yaml 의 handoff 트리(dict). 파일/키 없음·파싱 실패 시 {}."""
    import yaml

    if not config_path.is_file():
        return {}
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    handoff = data.get("handoff")
    return handoff if isinstance(handoff, dict) else {}


def is_ai_author(author: str) -> bool:
    """author 가 AI 주체(ai/llm/agent, 대소문자 무시)면 True."""
    return str(author).strip().lower() in AI_AUTHORS


def resolve_source_mode(spec: dict) -> str:
    """종류 spec → source_mode. AskUserQuestion 최우선 토글, author 로 AI/사람 구분."""
    ai = is_ai_author(spec.get("author", ""))
    ask = spec.get("AskUserQuestion") is True
    if ai:
        return "ai_guided" if ask else "ai_auto"
    return "human_ask" if ask else "human_doc"


def resolve_write_mode(field: str) -> str:
    """item_content → append, 그 외(colXX) → replace."""
    return "append" if field == "item_content" else "replace"
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_handoff_resolve.py -v`
Expected: PASS (10 passed)

- [ ] **Step 5: 린트 + 커밋**

```bash
uv run ruff check scripts/handoff_resolve.py tests/test_handoff_resolve.py
uv run ruff format scripts/handoff_resolve.py tests/test_handoff_resolve.py
git add scripts/handoff_resolve.py tests/test_handoff_resolve.py
git commit -m "feat(handoff): 출처·write_mode 결정 순수 함수 추가"
```

---

### Task 2: 템플릿 경로 해석 (resolve_template_path)

**Files:**
- Modify: `scripts/handoff_resolve.py`
- Test: `tests/test_handoff_resolve.py`

**Interfaces:**
- Consumes: Task 1의 모듈.
- Produces: `resolve_template_path(spec: dict, kind: str, plugin: Path, host: Path) -> str | None`
  - `rel = spec.get("template") or f"handoff/{kind}.html"`; `templates/<rel>` 를 host 우선·plugin fallback 으로 탐색. 없으면 `None`.

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_handoff_resolve.py` 에 import 와 테스트 추가:

```python
from scripts.handoff_resolve import resolve_template_path


def _mk(p: Path, text: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_resolve_template_path_host_overrides_plugin(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    _mk(plugin / "templates" / "handoff" / "summary.html", "P")
    _mk(host / "templates" / "handoff" / "summary.html", "H")
    assert resolve_template_path({}, "summary", plugin, host) == str(
        host / "templates" / "handoff" / "summary.html"
    )


def test_resolve_template_path_plugin_fallback(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    _mk(plugin / "templates" / "handoff" / "summary.html", "P")
    assert resolve_template_path({}, "summary", plugin, host) == str(
        plugin / "templates" / "handoff" / "summary.html"
    )


def test_resolve_template_path_implicit_kind_lookup(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    _mk(plugin / "templates" / "handoff" / "qa.html", "Q")
    assert resolve_template_path({}, "qa", plugin, host) == str(
        plugin / "templates" / "handoff" / "qa.html"
    )


def test_resolve_template_path_explicit_value(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    _mk(plugin / "templates" / "custom" / "x.html", "X")
    assert resolve_template_path(
        {"template": "custom/x.html"}, "qa", plugin, host
    ) == str(plugin / "templates" / "custom" / "x.html")


def test_resolve_template_path_missing_returns_none(tmp_path: Path):
    assert resolve_template_path({}, "qa", tmp_path / "p", tmp_path / "h") is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_handoff_resolve.py -k template -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_template_path'`

- [ ] **Step 3: 구현 추가**

`scripts/handoff_resolve.py` 의 `resolve_write_mode` 아래에 추가:

```python
def resolve_template_path(
    spec: dict, kind: str, plugin: Path, host: Path
) -> str | None:
    """template 파일 해석. rel = spec.template 또는 handoff/<kind>.html.
    templates/<rel> 을 host 우선·plugin fallback 으로 탐색. 없으면 None."""
    rel = spec.get("template") or f"handoff/{kind}.html"
    for root in (host, plugin):
        cand = root / "templates" / rel
        if cand.is_file():
            return str(cand)
    return None
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_handoff_resolve.py -v`
Expected: PASS (15 passed)

- [ ] **Step 5: 린트 + 커밋**

```bash
uv run ruff check scripts/handoff_resolve.py tests/test_handoff_resolve.py
uv run ruff format scripts/handoff_resolve.py tests/test_handoff_resolve.py
git add scripts/handoff_resolve.py tests/test_handoff_resolve.py
git commit -m "feat(handoff): 템플릿 경로 해석(host 우선·plugin fallback) 추가"
```

---

### Task 3: resolve_handoff 통합 + JSON CLI

**Files:**
- Modify: `scripts/handoff_resolve.py`
- Test: `tests/test_handoff_resolve.py`

**Interfaces:**
- Consumes: Task 1·2의 함수.
- Produces:
  - `resolve_handoff(config_path: Path, plugin: Path, host: Path) -> list[dict]` — enable:true 종류만 `{kind, author, field, source_mode, write_mode, template_path, instruction}` 리스트
  - `plugin_root()`/`host_root()` — env 기반 경로 (flow_init_setup 패턴)
  - `main()` — `argv[1]`(없으면 host/flow-config.yaml) → JSON stdout

- [ ] **Step 1: 실패 테스트 추가**

```python
from scripts.handoff_resolve import resolve_handoff


def test_resolve_handoff_filters_disabled(tmp_path: Path):
    cfg = tmp_path / "flow-config.yaml"
    cfg.write_text(
        "handoff:\n"
        "  summary:\n    enable: false\n    author: AI\n    field: item_content\n"
        "  qa:\n    enable: true\n    author: AI\n"
        "    AskUserQuestion: true\n    field: col22\n"
        '    instruction: "QA 인수인계"\n',
        encoding="utf-8",
    )
    result = resolve_handoff(cfg, tmp_path / "p", tmp_path / "h")
    assert [r["kind"] for r in result] == ["qa"]
    assert result[0]["source_mode"] == "ai_guided"
    assert result[0]["write_mode"] == "replace"
    assert result[0]["template_path"] is None
    assert result[0]["instruction"] == "QA 인수인계"


def test_resolve_handoff_skips_non_dict_and_missing_enable(tmp_path: Path):
    cfg = tmp_path / "flow-config.yaml"
    cfg.write_text(
        "handoff:\n"
        "  bad: 123\n"
        "  qa:\n    author: AI\n    field: col22\n",  # enable 없음 → skip
        encoding="utf-8",
    )
    assert resolve_handoff(cfg, tmp_path / "p", tmp_path / "h") == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_handoff_resolve.py -k resolve_handoff -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_handoff'`

- [ ] **Step 3: 구현 추가**

`scripts/handoff_resolve.py` 의 `force_utf8_io` 아래에 경로 헬퍼 추가:

```python
def plugin_root() -> Path:
    """플러그인 루트. CLAUDE_PLUGIN_ROOT 우선, 없으면 이 스크립트의 상위."""
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return Path(env) if env else Path(__file__).resolve().parent.parent


def host_root() -> Path:
    """호스트 루트. CLAUDE_PROJECT_DIR 우선, 없으면 cwd."""
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    return Path(env) if env else Path.cwd()
```

파일 끝(`resolve_template_path` 아래)에 통합 함수와 CLI 추가:

```python
def resolve_handoff(config_path: Path, plugin: Path, host: Path) -> list[dict]:
    """enable:true 종류만 결정 결과 리스트로. 입력 이상은 건너뛴다."""
    handoff = load_handoff_config(config_path)
    result: list[dict] = []
    for kind, spec in handoff.items():
        if not isinstance(spec, dict) or spec.get("enable") is not True:
            continue
        field = str(spec.get("field", ""))
        result.append(
            {
                "kind": kind,
                "author": spec.get("author", ""),
                "field": field,
                "source_mode": resolve_source_mode(spec),
                "write_mode": resolve_write_mode(field),
                "template_path": resolve_template_path(spec, kind, plugin, host),
                "instruction": spec.get("instruction", ""),
            }
        )
    return result


def main() -> None:
    force_utf8_io()
    config = (
        Path(sys.argv[1]) if len(sys.argv) > 1 else host_root() / "flow-config.yaml"
    )
    result = resolve_handoff(config, plugin_root(), host_root())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: 테스트 통과 + CLI 스모크 확인**

Run: `uv run pytest tests/test_handoff_resolve.py -v`
Expected: PASS (17 passed)

Run: `uv run python scripts/handoff_resolve.py tests/fixtures/nonexistent.yaml`
Expected: `[]` (파일 없음 → 빈 결과, 예외 없음)

- [ ] **Step 5: 린트 + 커밋**

```bash
uv run ruff check scripts/handoff_resolve.py tests/test_handoff_resolve.py
uv run ruff format scripts/handoff_resolve.py tests/test_handoff_resolve.py
git add scripts/handoff_resolve.py tests/test_handoff_resolve.py
git commit -m "feat(handoff): resolve_handoff 통합 + JSON CLI 추가"
```

---

### Task 4: summary 템플릿 추출 (templates/handoff/summary.html)

**Files:**
- Create: `templates/handoff/summary.html`

**Interfaces:**
- Consumes: 없음 (AI가 읽는 형식 가이드).
- Produces: `templates/handoff/summary.html` — resolve_template_path가 summary 종류에 매핑하는 파일.

기존 `commands/task-sync.md` 의 "Summary HTML Template" 구조·규칙을 그대로 담는다(회귀 0 목표). HTML 주석으로 규칙을 표기한다.

- [ ] **Step 1: 템플릿 파일 작성**

`templates/handoff/summary.html`:

```html
<!--
  handoff: summary 템플릿. /task-sync 의 AI 요약(field: item_content, append).
  AI 는 task 문서를 읽고 아래 3섹션 구조로 요약 HTML 을 생성한다.

  규칙:
  - 최상위 ordered list. 섹션 고정 순서: Implementation, Verification, Notes.
  - 섹션 라벨은 항상 영어. 본문은 task 문서 언어를 따른다(한글 task → 한글 본문).
  - Implementation: area 를 <ol>, 구체 변경을 nested <ul>.
  - Verification: method 를 <ol>, 결과를 nested <ol>(번호 증거).
  - Notes: caveat 의 flat <ol>. 없으면 섹션 통째로 생략.
  - atomic <li>: 한 <li> = 한 사실. ':' '→' '/' ',' ';' '+' 로 여러 사실을 묶지 말 것.
  - self-contained <li>: 앞 <li> 없이도 읽히게. '이/그/이를/따라서' 로 시작 금지.
  - area/method/Notes 라인은 이름만. 설명·수치·before/after 는 별도 <li> 로.
  - 개발 과정(TDD 반복·디버깅 이력·dev-server 왕복) 서술 금지 — 최종 형태만.
  - 최상위 task 제목 포함 금지(Teamer 가 제목을 별도 렌더).
-->
<ol>
<li>Implementation
  <ol>
    <li>[Area name — bare noun phrase, no colon, no detail]
      <ul>
        <li>[One atomic change]</li>
        <li>[Another atomic change]</li>
      </ul>
    </li>
  </ol>
</li>
<li>Verification
  <ol>
    <li>[Verification method name]
      <ol>
        <li>[One atomic observed result]</li>
      </ol>
    </li>
  </ol>
</li>
<li>Notes
  <ol>
    <li>[One atomic caveat]</li>
  </ol>
</li>
</ol>
```

- [ ] **Step 2: 기존 template과 동등성 확인**

`commands/task-sync.md` 의 "Summary HTML Template" 및 structural rules 와 위 파일을 대조한다. 3섹션·atomic·self-contained·area-name-only·개발과정 배제 규칙이 모두 반영됐는지 확인(누락 시 추가).

Expected: 기존 규칙 전부 포함, 구조 동일.

- [ ] **Step 3: 커밋**

```bash
git add templates/handoff/summary.html
git commit -m "feat(handoff): summary 템플릿 파일 추출"
```

---

### Task 5: teamer-item-updater 에 col_overrides 추가

**Files:**
- Modify: `agents/teamer-item-updater.md`

**Interfaces:**
- Consumes: `/task-sync` 가 넘기는 `col_overrides` 맵.
- Produces: PUT 시 GET 보존값 위에 명시 colXX 를 새 값으로 replace 하는 에이전트 동작.

- [ ] **Step 1: Required Parameters 에 col_overrides 추가**

`agents/teamer-item-updater.md` 의 `## Required Parameters` → `**Optional**:` 목록에 추가:

```markdown
- `col_overrides`: Map of colXX field → new value (e.g., `{col22: "<html>"}`). **Replaces** the GET-preserved value for those specific fields. All other non-null colXX from GET are still preserved (Invariant #6).
```

- [ ] **Step 2: Execution Step 4 의 fields 주석에 반영**

`### 4. Update Item via Node.js` 의 `fields` 객체에서 colXX 설명 줄을 다음으로 교체:

```javascript
  // Include only non-null colXX fields from GET (skip null cols).
  // For fields present in col_overrides, use the override value instead of GET.
  'itemVO.col07': '<value from GET, or col_overrides[col07] if provided>',
  'itemVO.col22': '<col_overrides[col22] if provided, else GET value if non-null>',
```

- [ ] **Step 3: Field Rules 에 규칙 추가**

`## Field Rules` 목록 끝에 추가:

```markdown
- **`col_overrides` replace**: For each colXX in `col_overrides`, send the override value (not the GET value). Fields not in `col_overrides` keep their GET value. Never drop a non-null colXX that lacks an override.
```

- [ ] **Step 4: 일관성 확인 + 커밋**

`item_content` append 규칙·Invariant #6(non-null 보존)·UTF-8 multipart 가 그대로 유지됐는지 확인.

```bash
git add agents/teamer-item-updater.md
git commit -m "feat(handoff): updater 에 col_overrides(replace) 파라미터 추가"
```

---

### Task 6: task-sync 에 handoff 통합

**Files:**
- Modify: `commands/task-sync.md`

**Interfaces:**
- Consumes: `scripts/handoff_resolve.py` JSON, `templates/handoff/*.html`, `teamer-item-updater` 의 `col_overrides`.
- Produces: handoff 순회 → field 별 분류 → updater 호출.

- [ ] **Step 1: Execution 3단계(요약 생성)를 handoff 일반화로 교체**

`## Execution` 의 `3. **Read and summarize task document**` 를 다음 구조로 교체한다. 기존 요약 생성 상세 규칙은 `templates/handoff/summary.html` 로 이전됐으므로, summary 종류는 그 템플릿을 따른다고 참조한다:

```markdown
3. **Resolve handoff kinds**
   - Run `python "${CLAUDE_PLUGIN_ROOT}/scripts/handoff_resolve.py" "${CLAUDE_PROJECT_DIR}/flow-config.yaml"`
   - Result is a JSON array; each element: `{kind, author, field, source_mode, write_mode, template_path, instruction}`
   - **Backward compat**: if the array is empty (no `handoff` config), fall back to legacy behavior — generate the AI summary using the structure in `templates/handoff/summary.html` and append to `item_content` (same as before).

4. **Generate content per handoff kind**
   For each resolved kind, produce HTML content by `source_mode`:
   - `ai_auto`: AI generates content from the task document. If `template_path` is set, read that file and follow its structure; otherwise apply `instruction`. (summary kind lands here — uses summary.html.)
   - `ai_guided`: use AskUserQuestion to ask the user for guidance (what to emphasize), then AI generates following `template_path`/`instruction` + the guidance.
   - `human_ask`: use AskUserQuestion to collect the content text directly; use it verbatim.
   - `human_doc`: read the `## Handoff (<Kind>)` section's **Content** from the task document; use it verbatim. If the section is missing, warn and skip this kind.
   - Wrap every generated content in the AI/author marker `<div>` block with date:
     ```html
     <div style="border-left:3px solid #6c63ff;padding-left:10px;margin:10px 0;">
     <p style="color:#888;font-size:0.85em;">Author: {author} ({YYYY-MM-DD})</p>
     <!-- content here -->
     </div>
     ```
   - Show a preview of all kinds to the user and ask for confirmation.

5. **Classify by field/write_mode**
   - `field == item_content` (write_mode append): queue for `item_content` append.
   - else (write_mode replace): add to `col_overrides` map as `{<field>: <html>}`.
```

- [ ] **Step 2: 이후 단계 번호 재정렬 + updater 호출에 col_overrides 추가**

기존 `4. Search Teamer item...` 이후 단계를 6·7·8 로 재번호하고, `teamer-item-updater` 호출 인자에 추가:

```markdown
   - `col_overrides` : map from step 5 (e.g., `{col22: "<qa html>"}`). The updater replaces these colXX over GET-preserved values; all other non-null colXX from GET are still preserved.
   - `item_content` : existing content + appended summary/handoff content from the item_content queue
```

- [ ] **Step 3: 일관성 확인**

- `source_mode` 4값이 Task 1의 `resolve_source_mode` 출력과 정확히 일치(`ai_auto`/`ai_guided`/`human_ask`/`human_doc`)하는지.
- `col_overrides` 키 이름이 Task 5의 updater 파라미터와 일치하는지.
- summary 회귀: handoff 미설정 시 기존 요약+append 경로가 보존되는지(Step 1 backward compat).

- [ ] **Step 4: 커밋**

```bash
git add commands/task-sync.md
git commit -m "feat(handoff): task-sync 에 handoff 순회·col_overrides 통합"
```

---

### Task 7: task-import 에 handoff 섹션 스캐폴드

**Files:**
- Modify: `commands/task-import.md`

**Interfaces:**
- Consumes: `scripts/handoff_resolve.py` JSON (human_doc 필터).
- Produces: task 문서 템플릿에 사람-작성 종류 섹션 추가.

- [ ] **Step 1: Execution 에 handoff 스캐폴드 단계 추가**

`## Execution` 의 task 파일 생성 단계(5)에 하위 항목 추가:

```markdown
  - **Handoff sections**: run `python "${CLAUDE_PLUGIN_ROOT}/scripts/handoff_resolve.py" "${CLAUDE_PROJECT_DIR}/flow-config.yaml"`. For each kind with `source_mode == "human_doc"`, append a section to the task file:
    ```markdown
    ## Handoff ({Kind})
    **Author:** [작성 주체]
    **Content:**
    <!-- {instruction if present} -->
    ```
    Skip kinds whose `source_mode` is not `human_doc` (AI/AskUserQuestion kinds need no document section).
```

- [ ] **Step 2: Task File Template 에 예시 섹션 추가**

`## Task File Template` 의 마크다운 블록에서 `## Notes` 앞에 주석 예시를 넣어, human_doc 종류가 있을 때 들어가는 위치를 보인다:

```markdown
<!-- ## Handoff (QA)  ← human_doc 종류가 config 에 있으면 task-import 가 삽입 -->

## Notes
[Additional observations]
```

- [ ] **Step 3: 일관성 확인 + 커밋**

`source_mode == "human_doc"` 가 Task 1 출력과 일치, 섹션 제목 `## Handoff (<Kind>)` 가 Task 6의 human_doc 읽기 경로와 동일한지 확인.

```bash
git add commands/task-import.md
git commit -m "feat(handoff): task-import 가 human_doc 종류 섹션 스캐폴드"
```

---

### Task 8: flow-config.example.yaml 에 handoff 템플릿

**Files:**
- Modify: `flow-config.example.yaml`

**Interfaces:**
- Consumes: 없음.
- Produces: 호스트가 복사해 채우는 handoff 설정 슬롯.

- [ ] **Step 1: handoff 블록 추가**

`flow-config.example.yaml` 의 `# Teamer.live 연동` 블록 뒤(또는 `doc_sync` 앞)에 추가:

```yaml
# 인수인계(handoff) — task-sync 가 종류별 내용을 Teamer 필드에 전달
# 종류 키는 확장 지점(qa 외 ops/security 등 동일 패턴). 미설정 시 summary 기존 동작 유지.
handoff:
  summary:                          # 기존 AI 요약 = handoff 의 한 종류
    enable: true
    author: AI                      # AI|LLM|Agent → AI 대필 / 그 외 → 사람 이름
    AskUserQuestion: false          # true 면 실행 시 AskUserQuestion 으로 입력/지침
    field: item_content             # item_content → append
    template: handoff/summary.html  # templates/ 기준 상대경로 (host 우선·plugin fallback)
  qa:                               # 신규 종류 예시 (필요 없으면 삭제/enable:false)
    enable: false
    author: AI
    AskUserQuestion: true
    field: col22                    # colXX → replace (전용 필드)
    instruction: "QA 인수인계 — 테스트 범위, 재현 절차, 리스크 포인트"
    # template: handoff/qa.html     # 선택 — 생략 시 일반 HTML div 래핑
```

- [ ] **Step 2: YAML 유효성 확인**

Run: `uv run python -c "import yaml; yaml.safe_load(open('flow-config.example.yaml', encoding='utf-8'))"`
Expected: 오류 없음(exit 0)

- [ ] **Step 3: 커밋**

```bash
git add flow-config.example.yaml
git commit -m "feat(handoff): flow-config.example 에 handoff 템플릿 추가"
```

---

### Task 9: 최종 검증 (전체 테스트·린트 + 수동 통합 확인)

**Files:** 없음 (검증만).

- [ ] **Step 1: 전체 테스트 + 린트 + 정적분석**

```bash
uv run pytest
uv run ruff check && uv run ruff format --check
uv run pre-commit run --all-files
```
Expected: 전부 PASS.

- [ ] **Step 2: handoff_resolve CLI 실배치 스모크**

루트에 임시 `flow-config.yaml`(handoff.summary enable:true + qa enable:true)을 두고:

Run: `uv run python scripts/handoff_resolve.py flow-config.yaml`
Expected: summary(append, template_path = templates/handoff/summary.html 해석) + qa(replace, source_mode=ai_guided) 가 JSON 으로 출력.

- [ ] **Step 3: 수동 통합 검증 (실 Teamer item — 자격증명 필요, 자동화 불가)**

다음을 사람이 확인한다(스펙 §11):
1. **summary 회귀**: handoff 미설정(또는 summary만 enable) 상태에서 `/task-sync <id>` → 기존과 동일한 요약이 item_content 에 append 되는지.
2. **qa replace**: `handoff.qa.enable: true`, `field: colXX` 로 두고 → 해당 colXX 가 인수인계 HTML 로 채워지고, **다른 colXX 와 item_title 이 GET 원본대로 보존**되는지(Invariant #6).
3. **colXX HTML 렌더링**: Teamer UI 에서 colXX 가 HTML 로 렌더되는지 확인. plain text 로만 보이면 `templates/handoff/*.html` 를 plain 포맷으로 조정(후속 작업).

- [ ] **Step 4: 브랜치 마무리**

`superpowers:finishing-a-development-branch` 스킬로 머지/PR 여부 결정.

---

## Self-Review

**1. Spec coverage:**
- §2 config 스키마 → Task 8 (example) + Task 1·3 (로드/파싱). ✓
- §3 출처 4조합 → Task 1 (resolve_source_mode) + Task 6 (소비). ✓
- §3 instruction/template 역할 → Task 1·2·3 (전달) + Task 6·7 (소비). ✓
- §4 템플릿 경로 해석 → Task 2 (resolve_template_path). ✓
- §5 데이터 흐름 → Task 6 (task-sync). ✓
- §6 updater col_overrides → Task 5. ✓
- §7 task-import 섹션 → Task 7. ✓
- §8 하위호환 → Task 6 Step 1 (backward compat) + Task 8 (summary 암묵 ON 주석). ✓
- §9 검증 → Task 9. ✓
- §11 미해결(경로 해석/스크립트화/AskUserQuestion 문구/colXX HTML/수동검증) → Task 2·1·6·9 에 반영. ✓

**2. Placeholder scan:** 코드 step 은 전부 실제 코드. 마크다운 step 은 삽입할 실제 텍스트 제공. `[Area name]` 등은 템플릿 *내용물*(의도된 플레이스홀더 예시)이지 plan 미완성이 아님. ✓

**3. Type consistency:**
- `source_mode` 값 `ai_auto/ai_guided/human_ask/human_doc` — Task 1 정의 = Task 6·7 소비 일치. ✓
- `resolve_template_path(spec, kind, plugin, host)` 시그니처 — Task 2 정의 = Task 3 호출 일치. ✓
- `col_overrides` 명칭 — Task 5 (updater) = Task 6 (task-sync) 일치. ✓
- `resolve_handoff` 출력 키 = Task 6 JSON 소비 키 일치. ✓
