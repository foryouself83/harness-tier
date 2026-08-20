# Wiki 노드 마커 분리 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** wiki 노드 마커를 Front Matter의 `id`에서 전용 키 `wiki_id`로 분리하고, `c2a0d3f`의
게이트 오탐 2건·무음 1건·오지목 1건을 제거한다.

**Architecture:** `scripts/wiki_graph.py` 한 파일이 노드 판별·검증·출력을 모두 들고 있고,
소비자 문서(스킬 · 규칙 · 템플릿)가 그 규칙을 사람에게 설명한다. 코드 쪽 변경은 판별 함수
(`collect_nodes`) · 검증 함수(`validate_structure`) · 출력 함수(`cmd_verify`) 셋으로 국한되고,
서로 다른 결함이 서로 다른 함수에 떨어지므로 태스크가 함수 경계와 일치한다. 문서 쪽은 코드가
통과한 뒤 한 번에 맞춘다.

**Tech Stack:** Python 3.8+ (게이트 하한) · PyYAML(유일한 런타임 의존성) · pytest · ruff · uv

## Global Constraints

- 게이트 하한은 **Python 3.8**이다. 3.9+ 전용 **런타임** 문법·API(`dict |` 병합 연산자,
  `Path.write_text(newline=)`)를 쓰지 않는다. 반면 `X | None` · `list[str]` 같은 **타입
  어노테이션**은 안전하다 — `wiki_graph.py:14`의 `from __future__ import annotations`가
  어노테이션을 문자열로 만들어 런타임 평가를 막는다.
- **Invariant #1 (FAIL-OPEN)**: 내부 오류는 통과시킨다. 이번에 새로 차단하는 것은 단 하나 —
  "원문에 `wiki_id:` 줄이 있는데 Front Matter가 파싱되지 않는다"이며, 판정 근거는 저장소 상태가
  아니라 문서 원문 하나뿐이다.
- **Invariant #2 (Windows 인코딩)**: 새 문자열을 `print`할 때 `PYTHONUTF8=1` · `force_utf8_io()` ·
  `encoding="utf-8"` 방어를 우회하지 않는다. `main()`(`wiki_graph.py:946`)과
  `wiki_check_output()`(`flow_gate_check.py:819`)이 이미 `force_utf8_io()`를 부르므로 추가 작업은 없다.
- **노드 dict의 내부 키 `"id"`는 바꾸지 않는다.** 바뀌는 것은 **Front Matter의 키 이름**뿐이다.
  `node["id"]` · `graph["nodes"][nid]` · `graph.yaml`의 노드 매핑 키는 전부 그대로다.
- `ID_RE`의 **패턴**(`^[a-z0-9-]+(\.[a-z0-9-]+)*$`)과 `DEFECT_PREFIX = "defect."`,
  `--neighbors <id>` CLI 인자는 그대로다. 상수명만 `WIKI_ID_RE`로 바꾼다.
- 커밋 타입: `scripts/`·`skills/`·`rules/`는 소비자에게 전파되므로 `fix(wiki):`를 쓴다
  (`docs:`는 릴리스를 만들지 못한다). `evals/`와 `scripts/skill_sandbox.py`는 배포되지 않으므로
  `test(evals):`를 쓴다. 제목 50자, 본문 72자 줄바꿈.
- 검증 명령: `uv run pytest` · `uv run ruff check && uv run ruff format --check`.
- 브랜치 `feature/wiki-init-outcome-eval`을 유지한다. 새 브랜치를 만들지 않는다.
- 설계 근거는 [2026-08-11 설계문서](../specs/2026-08-11-wiki-node-marker-design.md)에 있다.
  판단이 갈리면 그 문서가 SSOT다.

## File Structure

| 파일 | 이 계획에서의 책임 |
|---|---|
| `scripts/wiki_graph.py` | 노드 판별 · 구조 검증 · 검증 출력. 결함 4건 전부가 여기 있다 (Task 1–5) |
| `tests/test_wiki_graph.py` | 위 판정 로직의 회귀 방어. Front Matter 픽스처의 키를 함께 옮긴다 |
| `skills/wiki-init/SKILL.md` | 마법사가 사람에게 설명하는 규칙 + 8절 롤백 지시 (Task 6) |
| `skills/wiki-init/references/defect-template.md` | defect 노드 템플릿의 Front Matter |
| `skills/doc-sync/SKILL.md` | Mode W 2·4단계 |
| `rules/harness-rules.md` | 8-2 (생성 문서는 wiki 노드다) |
| `skills/harness-authoring/templates/{sds,srs,code-style}.template.md` | 생성 문서의 Front Matter 블록 |
| `docs/superpowers/specs/2026-08-06-llm-wiki-design.md` | 원 설계 2·3절 제자리 갱신 (코드가 `design §N`으로 인용한다) |
| `scripts/skill_sandbox.py` | outcome 골든 (Task 7) |
| `evals/outcome_scores.json` | outcome 베이스라인 재측정 결과 (Task 7) |

`docs/superpowers/plans/2026-08-06-llm-wiki.md`는 **건드리지 않는다** — 실행 완료된 기록이고
인용하는 코드도 없다.

---

### Task 1: 노드 마커를 `wiki_id`로 분리

**Files:**
- Modify: `scripts/wiki_graph.py` (`ID_RE` 274 · `_TEXT_FIELDS` 276-284 · `collect_nodes` 185 · `validate_structure` 391-412)
- Test: `tests/test_wiki_graph.py`

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces: `WIKI_ID_RE`(`re.Pattern`) — Task 5가 메시지에서 참조한다.
  `collect_nodes(root, wiki, paths=None) -> list[dict]`의 노드 dict 모양은 그대로
  (`{"id": str|None, "path": str, "line_count": int, "front": dict}`) — Task 2가 여기에 키를 더한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_wiki_graph.py`의 `test_front_matter_without_id_is_not_a_node_and_never_blocks`
(297행)를 아래 두 테스트로 **교체**한다.

```python
def test_foreign_id_front_matter_is_not_a_node_and_never_blocks(tmp_path: Path):
    # Docusaurus 의 `id:` 는 문서화된 1급 front matter 필드이고, wiki.root 기본값과
    # Docusaurus 기본 문서 경로는 둘 다 docs/ 다. 이것을 노드로 보면 형식 위반으로 판정되어
    # 저장소의 모든 커밋이 영구히 막힌다 — wiki 게이트는 docs 티어에도 걸려 있다.
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/getting-started.md", "id: Getting_Started\nsidebar_position: 1\n")
    nodes = collect_nodes(tmp_path, load_wiki_config(tmp_path))
    assert [n["id"] for n in nodes] == [None]
    assert _check(tmp_path, nodes) == []


def test_non_string_wiki_id_blocks(tmp_path: Path):
    # YAML 1.1 은 전용 키라도 문다: `wiki_id: 0123456` 은 octal 이라 정수 42798 이 되고,
    # 그 문자열화 "42798" 은 WIKI_ID_RE 를 통과해 아무도 쓰지 않은 유효해 보이는 id 가 된다.
    node = {
        "id": "42798",
        "path": "docs/a.md",
        "line_count": 3,
        "front": {"wiki_id": 42798, "title": "T"},
    }
    assert any("wiki_id" in p and "문자열" in p for p in _check(tmp_path, [node]))
```

그리고 293행의 기존 테스트 이름과 본문을 바꾼다.

```python
def test_bad_wiki_id_format_blocks(tmp_path: Path):
    # 전용 키를 썼다는 건 노드로 의도했다는 뜻이므로 더 이상 모호하지 않다 — 차단이 옳다.
    assert any("형식" in p and "wiki_id" in p for p in _check(tmp_path, [_mk("Auth.JWT")]))
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/test_wiki_graph.py -k "foreign_id or non_string_wiki_id or bad_wiki_id" -v`
Expected: FAIL — `test_foreign_id_...`는 `[n["id"] for n in nodes] == ["Getting_Started"]`로
어긋나고, 나머지 둘은 `wiki_id` 문자열이 메시지에 없어 어긋난다.

- [ ] **Step 3: `wiki_graph.py`를 고친다**

`ID_RE`(274행)를 개명한다. 패턴은 그대로다.

```python
WIKI_ID_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)*$")
```

`_TEXT_FIELDS`(276-284행)의 주석 마지막 문단과 튜플을 바꾼다.

```python
# `wiki_id` is in the list because it decides whether the file is a node at all:
# `wiki_id: no` → False → the document drops out of the graph and is reported as having no
# marker, and `wiki_id: 0123456` → 42798 becomes a valid-looking id for a node nobody wrote.
_TEXT_FIELDS = ("wiki_id", "title", "commit", "regression_test", "promoted_to_rule")
```

`collect_nodes`(185행)의 마커 읽기를 바꾼다.

```python
        raw_id = front.get("wiki_id")
```

`validate_structure`의 docstring 3번째 문단(391-396행)을 아래로 바꾼다.

```python
    A dedicated `wiki_id` is what marks a wiki node. `id` is NOT used: it is a documented
    first-class front-matter field in Docusaurus and Jekyll, and a wiki root is very often
    the same `docs/` tree they own — reading it as a node id made someone else's
    `id: Getting_Started` a format violation that blocked every commit in the repository,
    with no remedy `--build` or doc-sync could apply. A document with no `wiki_id` is not a
    node and is skipped; collect_warnings surfaces the ones that look like they meant to be.
```

같은 함수의 마커 검사 3곳(403 · 407 · 411-412행)을 바꾼다.

```python
        raw_id = front.get("wiki_id")
        if raw_id is not None and not isinstance(raw_id, str):
            # Checked before the not-a-node skip below: `wiki_id: no` resolves to False, which
            # makes nid None, so the document would otherwise be reported as having no marker.
            problems.append(_wrong_type(path, "wiki_id", raw_id))
            continue
        if not nid:
            continue
        if not WIKI_ID_RE.match(nid):
            problems.append(f"{path}: wiki_id '{nid}' 형식 위반 (허용: {WIKI_ID_RE.pattern})")
```

- [ ] **Step 4: 테스트 픽스처의 Front Matter 키를 옮긴다**

`tests/test_wiki_graph.py`에서 **Front Matter 문자열 안의** `id: `를 `wiki_id: `로 바꾼다.
대상은 `_node(...)`의 세 번째 인자로 넘어가는 문자열 리터럴과 `_mk` 헬퍼다. `n["id"]` ·
`node["id"]` · `graph["nodes"]` 같은 **dict 접근은 건드리지 않는다.**

`_mk`(260-262행):

```python
def _mk(nid, front=None, path="docs/a.md"):
    front = {"wiki_id": nid, "title": "T", **(front or {})}
    return {"id": nid, "path": path, "line_count": 3, "front": front}
```

`_wiki_repo`(623-628행):

```python
def _wiki_repo(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/index.md", "wiki_id: index\ntitle: Index\nrelated: [auth.jwt]\n")
    _node(tmp_path, "docs/auth/jwt.md", "wiki_id: auth.jwt\ntitle: JWT\nrelated: [index]\n")
    return tmp_path
```

나머지 `_node(...)` 호출도 같은 방식으로 옮긴다. 아래 명령의 결과가 비어야 완료다 — 남은
`id: `를 전부 보여주되 이미 옮긴 `wiki_id: `는 뺀다.

```bash
grep -n "id: " tests/test_wiki_graph.py | grep -v "wiki_id: "
```

단, 남의 Front Matter를 일부러 쓰는 새 테스트(`test_foreign_id_...`)의 `id: Getting_Started`는
**남아야 한다.** 그 한 줄을 빼고 결과가 비면 된다.

`test_collect_nodes_keeps_document_missing_id`(159행)는 이름을
`test_collect_nodes_keeps_document_missing_marker`로 바꾸고, 픽스처를 `title: 제목만\n`
그대로 둔다(마커가 없다는 사실이 요점이므로 내용 변경 없음).

- [ ] **Step 5: 전체 테스트를 돌린다**

Run: `uv run pytest tests/test_wiki_graph.py -v`
Expected: PASS (전부)

- [ ] **Step 6: 린트**

Run: `uv run ruff check && uv run ruff format --check`
Expected: 통과. 실패하면 `uv run ruff format`으로 고치고 다시 돌린다.

- [ ] **Step 7: 커밋**

```bash
git add scripts/wiki_graph.py tests/test_wiki_graph.py
git commit -F - <<'MSG'
fix(wiki): mark nodes with wiki_id, not id

`id` is a documented first-class front-matter field in Docusaurus and
Jekyll, and a wiki root is very often the same docs/ tree they own. A
doc site's own `id: Getting_Started` was read as a node id, failed the
format rule, and blocked every commit in the repository with no remedy
--build or doc-sync could apply. A dedicated key removes the collision
at its source; a format-violating wiki_id still blocks, because writing
the dedicated key is unambiguous intent.
MSG
```

---

### Task 2: 깨진 Front Matter를 표면화한다 (차단/경고 분리)

**Files:**
- Modify: `scripts/wiki_graph.py` (`parse_front_matter` 90-108 아래에 헬퍼 추가 · `collect_nodes` 182-193 · `validate_structure` 400 · `collect_warnings` 560-571)
- Test: `tests/test_wiki_graph.py`

**Interfaces:**
- Consumes: Task 1의 `wiki_id` 마커 규칙
- Produces: 노드 dict에 두 키가 **추가로** 붙을 수 있다 —
  `"broken": str`(파싱 실패 사유, 없으면 키 자체가 없음) · `"marker_seen": bool`.
  깨진 노드는 `"id": None` · `"front": {}`이므로 기존 소비자(`build_graph` ·
  `cmd_stale` · `neighbors`)는 이미 있는 `if not node["id"]: continue`로 걸러낸다.
  Task 3이 `node.get("broken")`을 읽는다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_wiki_graph.py` 끝에 추가한다.

```python
def test_broken_front_matter_with_marker_blocks_and_names_the_file(tmp_path: Path):
    # 따옴표 하나 빠지면 YAML 이 죽는다. 이 문서는 wiki_id 를 썼으니 노드로 의도한 것이
    # 명백하다 — 조용히 사라지면 --verify 가 exit 0 을 보고하고, /wiki-init 8절의
    # "verify 통과 = wiki 강제됨" 이 거짓이 된다.
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/broken.md", "wiki_id: broken\ntitle: New: Doc\n")
    nodes = collect_nodes(tmp_path, load_wiki_config(tmp_path))
    problems = _check(tmp_path, nodes)
    assert any("docs/broken.md" in p and "읽지 못했습니다" in p for p in problems)


def test_broken_front_matter_without_marker_warns_but_never_blocks(tmp_path: Path):
    # 파싱이 죽었으니 wiki_id 가 있었는지 YAML 로는 알 수 없다. 원문에 마커 줄이 없으면
    # 남의 문서일 수 있으므로 차단하지 않는다 — Task 1 과 같은 원칙이다.
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/theirs.md", "title: New: Doc\nsidebar_position: 1\n")
    wiki = load_wiki_config(tmp_path)
    nodes = collect_nodes(tmp_path, wiki)
    assert _check(tmp_path, nodes) == []
    warns = collect_warnings(wiki, nodes, build_graph(nodes), tmp_path)
    assert any("docs/theirs.md" in w and "읽지 못해" in w for w in warns)


def test_plain_markdown_is_not_reported_as_broken(tmp_path: Path):
    # 여는 `---` 가 없거나 닫는 `---` 가 없는 파일은 front matter 가 아니다. 문서 첫 줄의
    # 수평선·setext 밑줄이 흔하고, 이것까지 깨진 것으로 세면 경고가 노이즈가 된다.
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    (tmp_path / "docs" / "plain.md").write_text("# 제목\n\n본문\n", encoding="utf-8")
    (tmp_path / "docs" / "rule.md").write_text("---\n\n본문만 있고 닫히지 않음\n", encoding="utf-8")
    wiki = load_wiki_config(tmp_path)
    nodes = collect_nodes(tmp_path, wiki)
    assert nodes == []
    assert collect_warnings(wiki, nodes, build_graph(nodes), tmp_path) == []


def test_verify_no_longer_passes_silently_on_a_broken_node(tmp_path: Path):
    # 재현된 시나리오: --build 가 깨진 문서를 뺀 그래프를 먼저 쓰면 drift 탐지도 무력화되어
    # --verify 가 exit 0 을 낸다. 그 무음을 없앤 것이 이 테스트의 대상이다.
    _wiki_repo(tmp_path)
    _node(tmp_path, "docs/broken.md", "wiki_id: broken\ntitle: New: Doc\n")
    assert cmd_build(tmp_path) == 0
    assert cmd_verify(tmp_path) == 1
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/test_wiki_graph.py -k "broken or plain_markdown or silently" -v`
Expected: FAIL — `_check`가 빈 리스트를 돌려주고 `cmd_verify`가 0을 돌려준다.

- [ ] **Step 3: 구분자 탐색을 공통 헬퍼로 뽑는다**

`parse_front_matter`(90행) **바로 위**에 넣는다.

```python
def _front_matter_block(text: str) -> str | None:
    """The text between the opening `---` and the closing one, or None when there is no block.

    Both readers below share this so the delimiter rule — including the `end + 1` boundary —
    lives in one place. A copy would let one of them drift.
    """
    if not text.startswith(_FM_DELIM):
        return None
    end = text.find(f"\n{_FM_DELIM}", len(_FM_DELIM))
    if end < 0:
        return None
    return text[len(_FM_DELIM) : end + 1]
```

그리고 `parse_front_matter`의 본문(97-108행)을 헬퍼 위로 얹는다. **docstring과 시그니처는
그대로 둔다** — 직접 호출하는 기존 테스트 3건이 있다.

```python
    block = _front_matter_block(text)
    if block is None:
        return None
    try:
        import yaml

        front = yaml.safe_load(block)
    except Exception:
        return None
    return front if isinstance(front, dict) else None
```

- [ ] **Step 4: 깨진 Front Matter 판별 헬퍼를 추가한다**

`parse_front_matter` 바로 아래에 넣는다.

```python
# Read from the RAW front-matter text, because a block that failed to parse has no YAML to
# ask. Whether the author wrote a `wiki_id:` line is still visible, and that is what separates
# "an intended node that broke" (block) from "someone else's metadata that broke" (warn).
_MARKER_LINE_RE = re.compile(r"^wiki_id\s*:", re.MULTILINE)


def _broken_front_matter(text: str) -> tuple[str, bool] | None:
    """(reason, marker_seen) when a `---` block exists but does not parse as a map, else None.

    `parse_front_matter` returns None for three different situations and only one of them is a
    broken document, so its return value cannot drive a warning:

    - no leading `---` at all — an ordinary markdown file, silent
    - a leading `---` with no closing one — not front matter either. A horizontal rule or a
      setext underline on the first line is common, and counting those as broken turns the
      warning into noise
    - an opened AND closed block that raises or yields a non-map — the broken document

    Re-parsing costs one extra parse per broken file, which is rarer than changing
    parse_front_matter's signature is disruptive (three tests call it directly).
    """
    block = _front_matter_block(text)
    if block is None:
        return None
    try:
        import yaml

        front = yaml.safe_load(block)
    except Exception as exc:
        # One line: this rides a hook deny message, and PyYAML's mark spans three.
        reason = " ".join(str(exc).split())
    else:
        # `front is None` covers an EMPTY block (`---
---`), which Jekyll writes by
        # convention and which is not broken — it is simply not a node. Reporting it would
        # put the warning back on ordinary documentation, which is what this task avoids.
        if front is None or isinstance(front, dict):
            return None
        reason = f"front matter 가 map 이 아닙니다 (YAML 이 {type(front).__name__} 로 읽었습니다)"
    return reason, bool(_MARKER_LINE_RE.search(block))
```

- [ ] **Step 6: `collect_nodes`가 깨진 문서를 담게 한다**

`collect_nodes`의 182-184행(`front = parse_front_matter(text)` / `if front is None: continue`)을
바꾼다.

```python
        front = parse_front_matter(text)
        if front is None:
            broken = _broken_front_matter(text)
            if broken is None:
                continue  # no front matter at all — an ordinary markdown file
            reason, marker_seen = broken
            # `front` stays an EMPTY DICT, never None: every consumer already skips on a falsy
            # id, and a None here would turn each `node["front"].get(...)` into a crash.
            nodes.append(
                {
                    "id": None,
                    "path": path.relative_to(root).as_posix(),
                    "line_count": len(text.splitlines()),
                    "front": {},
                    "broken": reason,
                    "marker_seen": marker_seen,
                }
            )
            continue
```

- [ ] **Step 7: `validate_structure`가 마커 있는 깨진 문서를 차단하게 한다**

`validate_structure`의 노드 루프 맨 앞(400행 `for node in nodes:` 바로 다음)에 넣는다.

```python
    for node in nodes:
        if node.get("broken"):
            if node.get("marker_seen"):
                problems.append(
                    f"{node['path']}: wiki_id 가 있는데 front matter 를 읽지 못했습니다 — "
                    f"{node['broken']}"
                )
            continue
        nid, path = node["id"], node["path"]
```

- [ ] **Step 8: `collect_warnings`가 마커 없는 깨진 문서를 경고하게 한다**

`collect_warnings`의 560-571행 블록 **앞**에 새 블록을 넣고, 기존 블록의 조건에 가드를 더한다.

```python
    _capped(
        warns,
        [
            f"{node['path']}: front matter 를 읽지 못해 wiki 노드로 보지 않습니다 — "
            f"{node['broken']}"
            for node in nodes
            if node.get("broken") and not node.get("marker_seen")
        ],
        "읽지 못한 front matter",
    )
    # Front matter without a marker. (Task 3 narrows this list.)
    _capped(
        warns,
        [
            f"{node['path']}: front matter 에 wiki_id 가 없어 wiki 노드로 보지 않습니다"
            for node in nodes
            if not node["id"] and not node.get("broken")
        ],
        "wiki_id 없는 front matter",
    )
```

- [ ] **Step 9: 테스트를 돌린다**

Run: `uv run pytest tests/test_wiki_graph.py -v`
Expected: PASS (전부)

- [ ] **Step 10: 린트 후 커밋**

```bash
uv run ruff check && uv run ruff format --check
git add scripts/wiki_graph.py tests/test_wiki_graph.py
git commit -F - <<'MSG'
fix(wiki): surface unparseable front matter

A missing quote (`title: New: Doc`) made parse_front_matter return None
and the document vanished from the graph without a word, so --verify
reported exit 0 on a wiki that was not being enforced. Front matter that
opens, closes, and still fails to parse is now carried as a marked node:
it blocks when the raw text holds a wiki_id line, and warns when it does
not, matching the rule that only unambiguous wiki members block.
MSG
```

---

### Task 3: 마커 누락 경고를 wiki 전용 필드가 있을 때로 좁힌다

**Files:**
- Modify: `scripts/wiki_graph.py` (Task 2가 남긴 두 번째 `_capped` 블록 · `WIKI_ONLY_FIELDS` 상수 추가)
- Test: `tests/test_wiki_graph.py`

**Interfaces:**
- Consumes: Task 2의 `node.get("broken")` 가드
- Produces: `WIKI_ONLY_FIELDS: tuple[str, ...]` · `_wiki_fields_present(front: dict) -> list[str]`

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_missing_marker_warns_only_when_wiki_fields_are_present(tmp_path: Path):
    # 전용 키로 바꾸면 "front matter 는 있는데 노드가 아니다" 가 정상 상태다. Docusaurus
    # 저장소에서 전수 경고는 매 커밋 영구 노이즈가 된다. related 를 손으로 썼다는 것만이
    # 노드로 쓰려던 의도의 증거다.
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/theirs.md", "id: Getting_Started\nsidebar_position: 1\ntags: [x]\n")
    _node(tmp_path, "docs/meant-it.md", "title: Auth\nrelated: [index]\n")
    wiki = load_wiki_config(tmp_path)
    nodes = collect_nodes(tmp_path, wiki)
    warns = collect_warnings(wiki, nodes, build_graph(nodes), tmp_path)
    assert any("docs/meant-it.md" in w and "wiki_id" in w for w in warns)
    assert not any("docs/theirs.md" in w for w in warns)
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/test_wiki_graph.py -k missing_marker_warns -v`
Expected: FAIL — `docs/theirs.md`도 경고에 잡힌다 (`assert not any(...)`가 깨진다).

- [ ] **Step 3: 상수와 헬퍼를 추가한다**

`WARN_CAP = 3`(509행) 바로 위에 넣는다.

```python
# Fields only a wiki node carries. `tags` is deliberately NOT here: Jekyll and Docusaurus use
# it too, so it cannot tell "meant to be a node" from "someone else's metadata".
WIKI_ONLY_FIELDS = ("related", "depends_on", "affects", "sources")


def _wiki_fields_present(front: dict) -> list[str]:
    """Wiki-only fields this document carries. Non-empty means the author meant it as a node."""
    return [f for f in WIKI_ONLY_FIELDS if front.get(f) is not None]
```

- [ ] **Step 4: 경고 블록을 좁힌다**

Task 2가 남긴 두 번째 `_capped` 블록을 통째로 바꾼다.

```python
    # A missing marker is the NORMAL state once the key is dedicated — a Docusaurus tree under
    # the wiki root has hundreds of such files, and warning on all of them is permanent noise
    # on every commit. Wiki-only fields are the one signal that separates a forgotten marker
    # from someone else's metadata.
    _capped(
        warns,
        [
            f"{node['path']}: {', '.join(_wiki_fields_present(node['front']))} 가 있는데 "
            f"wiki_id 가 없어 wiki 노드로 보지 않습니다"
            for node in nodes
            if not node["id"] and not node.get("broken") and _wiki_fields_present(node["front"])
        ],
        "wiki_id 없는 wiki 필드",
    )
```

- [ ] **Step 5: 테스트를 돌린다**

Run: `uv run pytest tests/test_wiki_graph.py -v`
Expected: PASS. `test_collect_nodes_keeps_document_missing_marker`처럼 마커 없는 문서를 쓰는
기존 테스트가 경고 문구를 검사한다면 새 문구에 맞춘다.

- [ ] **Step 6: 린트 후 커밋**

```bash
uv run ruff check && uv run ruff format --check
git add scripts/wiki_graph.py tests/test_wiki_graph.py
git commit -F - <<'MSG'
fix(wiki): narrow the missing-marker warning

With a dedicated key, front matter that is not a wiki node is the normal
state, and a repository whose docs/ tree belongs to Docusaurus would
carry that warning on every commit forever. A wiki-only field —
related, depends_on, affects, sources — is the one signal that the
author meant this document to be a node, so the warning follows it.
MSG
```

---

### Task 4: 구조 위반 출력에 개수 캡을 건다

**Files:**
- Modify: `scripts/wiki_graph.py` (`PROBLEM_CAP` 상수 추가 · `cmd_verify` 854-857)
- Test: `tests/test_wiki_graph.py`

**Interfaces:**
- Consumes: Task 1–3
- Produces: `PROBLEM_CAP = 10`. `validate_structure`의 반환값은 **캡되지 않는다**.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_structural_problem_output_is_capped(tmp_path: Path, capsys):
    # 이 출력이 그대로 precommit deny 사유가 된다 (flow_gate_check.wiki_check_output).
    # 캡이 없으면 문서 300 개가 위반일 때 deny 사유가 300 줄이다.
    _wiki_repo(tmp_path)
    for i in range(12):
        _node(tmp_path, f"docs/bad{i}.md", f"wiki_id: Bad_{i}\ntitle: T\n")
    assert cmd_build(tmp_path) == 0
    assert cmd_verify(tmp_path) == 1
    err = capsys.readouterr().err
    assert err.count("형식 위반") == 10
    assert "... 외 2건 (구조 위반)" in err


def test_validate_structure_itself_stays_uncapped(tmp_path: Path):
    # 캡은 출력 단계의 것이다. 순수 함수는 전수를 돌려줘야 테스트가 전수를 확인할 수 있다.
    nodes = [_mk(f"Bad_{i}", path=f"docs/bad{i}.md") for i in range(12)]
    assert len([p for p in _check(tmp_path, nodes) if "형식 위반" in p]) == 12


def test_drift_reason_survives_a_full_structural_cap(tmp_path: Path, capsys):
    # 합쳐진 리스트에 캡을 걸면 구조 위반 10 건이 drift 사유를 밀어내고, 저자는 두 해소
    # 경로(front matter 수정 / --build) 중 하나를 보지 못한다.
    _wiki_repo(tmp_path)
    assert cmd_build(tmp_path) == 0
    for i in range(12):
        _node(tmp_path, f"docs/bad{i}.md", f"wiki_id: Bad_{i}\ntitle: T\n")
    assert cmd_verify(tmp_path) == 1
    err = capsys.readouterr().err
    assert "graph.yaml 이 front matter 와 어긋납니다" in err
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/test_wiki_graph.py -k "capped or uncapped or drift_reason_survives" -v`
Expected: FAIL — `err.count("형식 위반")`이 12다.

- [ ] **Step 3: 상수를 추가한다**

`WARN_CAP = 3` 바로 아래에 넣는다.

```python
# Warnings are a sample; structural problems are a work list. Capping them at WARN_CAP would
# make an author with 20 violations run --verify seven times to see them all, while ten lines
# still read as a deny message.
PROBLEM_CAP = 10
```

- [ ] **Step 4: `cmd_verify`의 출력 루프를 고친다**

854-857행의 `if problems:` 블록 앞부분을 바꾼다.

```python
    if problems:
        print("wiki graph 검증 실패:", file=sys.stderr)
        # Cap the STRUCTURAL section only. The drift reasons appended after it carry the other
        # remedy, and letting ten structural violations push them off the message would leave
        # half the failures with no way out. `structural` already marks that boundary.
        for line in problems[:structural][:PROBLEM_CAP]:
            print(f"  - {line}", file=sys.stderr)
        if structural > PROBLEM_CAP:
            print(f"  - ... 외 {structural - PROBLEM_CAP}건 (구조 위반)", file=sys.stderr)
        for line in problems[structural:]:
            print(f"  - {line}", file=sys.stderr)
```

- [ ] **Step 5: 테스트를 돌린다**

Run: `uv run pytest tests/test_wiki_graph.py -v`
Expected: PASS (전부)

- [ ] **Step 6: 린트 후 커밋**

```bash
uv run ruff check && uv run ruff format --check
git add scripts/wiki_graph.py tests/test_wiki_graph.py
git commit -F - <<'MSG'
fix(wiki): cap structural violations in output

cmd_verify's output is handed to the commit hook verbatim as the deny
reason, and the structural section was the only list with no cap — 300
violating documents produced 300 lines nobody can read. The cap covers
that section alone, so the drift reason after it, which carries the
other remedy, is never pushed off the message.
MSG
```

---

### Task 5: dangling edge 메시지가 양쪽을 지목하게 한다

**Files:**
- Modify: `scripts/wiki_graph.py` (`validate_structure` 449-454)
- Test: `tests/test_wiki_graph.py`

**Interfaces:**
- Consumes: Task 1의 `wiki_id` 용어
- Produces: 없음 (메시지 문구만)

- [ ] **Step 1: 실패하는 테스트를 쓴다**

```python
def test_dangling_edge_names_both_sides(tmp_path: Path):
    # 기존 문구는 참조자만 지목해서, 저자가 멀쩡한 index.md 를 들여다보게 만들었다.
    problems = _check(tmp_path, [_mk("index", {"related": ["ghost"]}, path="docs/index.md")])
    (msg,) = [p for p in problems if "ghost" in p]
    assert "docs/index.md" in msg
    assert "wiki_id" in msg
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/test_wiki_graph.py -k dangling_edge_names_both -v`
Expected: FAIL — 메시지에 `wiki_id`가 없다.

- [ ] **Step 3: 메시지를 고친다**

449-454행의 `problems.append(...)`를 바꾼다.

```python
                    problems.append(
                        f"{src_path}: {kind} 가 가리키는 id '{target}' 인 노드가 없습니다 "
                        f"— 대상 문서의 wiki_id 를 확인하거나 이 항목을 고치세요"
                    )
```

- [ ] **Step 4: 테스트를 돌린다**

Run: `uv run pytest tests/test_wiki_graph.py -v`
Expected: PASS. 기존 테스트가 `"가리킵니다"`를 검사한다면 새 문구에 맞춘다 —
`grep -n '가리킵니다' tests/test_wiki_graph.py`로 확인한다.

- [ ] **Step 5: 린트 후 커밋**

```bash
uv run ruff check && uv run ruff format --check
git add scripts/wiki_graph.py tests/test_wiki_graph.py
git commit -F - <<'MSG'
fix(wiki): name both sides of a dangling edge

The message pointed only at the referring document, so an author whose
index.md listed an id no node carried went looking for the fault in
index.md. Naming the target and the remedy on the other side sends them
to the document that actually needs the marker.
MSG
```

---

### Task 6: 소비자 문서를 마커 변경에 맞춘다

**Files:**
- Modify: `skills/wiki-init/SKILL.md` (2·3·5·6·8절)
- Modify: `skills/wiki-init/references/defect-template.md`
- Modify: `skills/doc-sync/SKILL.md` (Mode W 2·4단계)
- Modify: `rules/harness-rules.md` (8-2, 51-60행)
- Modify: `skills/harness-authoring/templates/sds.template.md` · `srs.template.md` · `code-style.template.md`
- Modify: `docs/superpowers/specs/2026-08-06-llm-wiki-design.md` (2·3절)
- Test: `uv run pytest tests/test_skills.py`

**Interfaces:**
- Consumes: Task 1–5의 최종 동작
- Produces: 없음 (문서)

- [ ] **Step 1: 남은 곳을 전수 조사한다**

```bash
grep -rn "front matter\|Front Matter" skills/ rules/ docs/superpowers/specs/2026-08-06-llm-wiki-design.md | grep -in "id"
```

- [ ] **Step 2: `wiki-init/SKILL.md`를 고친다**

- 2절(28-37행): "whether the front matter carries an `id`" → `wiki_id`. 33-37행의 문단을 아래로 바꾼다.

```markdown
**`wiki_id` is the node marker — not the `---` block, and not `id`.** A doc site's own
metadata (MkDocs · Docusaurus · Jekyll: `id`, `sidebar_position`, `slug`, `layout`, …) is
front matter too, and `id` in particular is a documented first-class field in several of
them — which is why the wiki does not use it. Those files are *not* nodes; validation
ignores them. They are ordinary migration candidates: merge the wiki fields into the
existing block rather than adding a second one, and leave their `id` alone.
```

- 3절(41-45행): "documents **without an `id`**" → "documents **without a `wiki_id`**",
  "already has one" → "already has one" 그대로.
- 5절(68-80행): "`id` is derived mechanically" → "`wiki_id` is derived mechanically",
  "an id must match" 문장의 정규식은 그대로.
- 6절(99-107행): "its own `id` (conventionally `index`)" → "its own `wiki_id`".
- 8절(146-149행): "structure violation (`id` format or duplicate …)" → "`wiki_id` format or
  duplicate … · front matter that does not parse while carrying a `wiki_id`".

- [ ] **Step 3: `wiki-init/SKILL.md` 8절에 롤백 지시를 넣는다**

156행("`--verify` reads the **working tree** …") 문단 **앞**에 넣는다.

```markdown
If you cannot make `--verify` pass within this session, set Step 7's `enable` back to
`false` before you finish and report the violations you left behind. `--build` requires
`enable: true`, so the gate is necessarily on from Step 7 onward — finishing with it on and
the graph invalid blocks every commit in the repository until someone fixes it by hand.
```

- [ ] **Step 4: 나머지 문서를 고친다**

- `defect-template.md`: Front Matter 블록의 `id: defect.<slug>` → `wiki_id: defect.<slug>`.
- `doc-sync/SKILL.md` Mode W 2단계(130-135행): "substituting that node's own `id` from step
  1's JSON" → "substituting that node's own id from step 1's JSON (the `id` key of the JSON
  entry — the graph's node id, which is what the document's `wiki_id` becomes)". `--stale`이
  내보내는 JSON 키는 `"id"` 그대로이므로 **바꾸지 않는다**; 이 문장은 Front Matter 키와
  헷갈리지 않게만 만든다.
  4단계(147-148행): "front matter — `id` (mechanics owned by …)" → "`wiki_id`".
- `rules/harness-rules.md` 8-2(53행): "mandatory YAML front matter (`id`, `title`; …)" →
  "(`wiki_id`, `title`; …)".
- `harness-authoring/templates/` 3종: 주석의 `# id: derive mechanically …` → `# wiki_id: …`,
  그리고 `id: {{ID}}` → `wiki_id: {{ID}}`. 세 파일 모두 같은 자리다.
- `specs/2026-08-06-llm-wiki-design.md` 2절(59-63행)을 아래로 바꾼다.

```markdown
wiki root 안의 `.md` 중 **`wiki_id`를 가진 파일만** wiki 노드다. Front Matter 자체는 판별자가
아니고, `id`도 아니다 — 정적 사이트 생성기(MkDocs · Docusaurus · Jekyll)의 메타데이터도 Front
Matter이며 그중 `id`는 여럿에서 문서화된 1급 필드다. 전용 키를 쓰는 이유가 그것이다
([2026-08-11 마커 분리 설계](2026-08-11-wiki-node-marker-design.md)). `wiki_id`가 없는 `.md`
(예: `docs/README.md`)는 wiki 밖이며 검증 대상이 아니다. 예외는 `wiki.index`가 가리키는 파일 —
이것은 반드시 노드여야 한다.
```

같은 파일 65-75행 예시 블록의 `id: auth.jwt` → `wiki_id: auth.jwt`, 3절에서 `id` 판별을
설명하는 문장도 같은 기준으로 고친다.

- [ ] **Step 5: 스킬 파일 검사를 돌린다**

Run: `uv run pytest tests/test_skills.py -v`
Expected: PASS. 이 테스트는 프론트매터·링크·참조를 검사하므로, 상대 링크를 새로 추가한
2026-08-06 spec의 링크가 실제 파일을 가리키는지도 여기서 걸린다.

- [ ] **Step 6: 커밋**

```bash
git add skills/ rules/ docs/superpowers/specs/2026-08-06-llm-wiki-design.md
git commit -F - <<'MSG'
fix(wiki): move skills and rules to wiki_id

The wizard, doc-sync Mode W, harness-rules 8-2 and the three authoring
templates all told the author to write `id`, which is the field a doc
site owns. They now write `wiki_id`, and wiki-init Step 8 carries the
rollback the ordering needs: --build requires enable:true, so a session
that cannot make --verify pass must turn the gate back off.
MSG
```

---

### Task 7: outcome 골든을 조이고 베이스라인을 다시 잰다

**Files:**
- Modify: `scripts/skill_sandbox.py` (`wiki-init-migration` 시나리오 443-513행)
- Modify: `evals/outcome_scores.json` (재측정 결과)
- Test: `uv run pytest tests/test_evals.py`

**Interfaces:**
- Consumes: Task 6의 최종 SKILL.md 본문
- Produces: 없음 (마지막 태스크)

- [ ] **Step 1: 골든을 조인다**

`"id:"`는 `wiki_id:`의 부분문자열이라 키를 바꿔도 우연히 통과한다. 490-495행을 바꾼다.

```python
            "docs/backend.md": {
                "must_contain": ["wiki_id:", "related:"],
                "must_not_contain": [WIKI_JWT_CLAIM, "used_by:"],
            },
            # The zero-H2 branch: still a node, still not split, still no generated edge.
            "docs/deploy.md": {"must_contain": ["wiki_id:"], "must_not_contain": ["used_by:"]},
```

447행의 `expect` 항목도 바꾼다.

```python
            "derives each wiki_id from the path relative to docs/, and never writes used_by",
```

- [ ] **Step 2: 모델 없는 절반을 돌린다**

Run: `uv run pytest tests/test_evals.py -v`
Expected: PASS. `outcome_sha`가 바뀌었다는 이유로 실패한다면 그것이 정상이며 Step 4가 해소한다.

- [ ] **Step 3: 골든 변경을 커밋한다**

```bash
git add scripts/skill_sandbox.py
git commit -F - <<'MSG'
test(evals): assert wiki_id, not the substring id

must_contain "id:" also matches "wiki_id:", so the golden would have
passed the marker change without ever checking it.
MSG
```

- [ ] **Step 4: outcome 베이스라인을 다시 잰다**

**모델을 호출한다 (reps 3). 사용자에게 먼저 확인받고 실행한다.**

Run: `uv run python -m evals.outcome --skill wiki-init`
Expected: `wiki-init` 점수가 갱신되고 `evals/outcome_scores.json`이 새 `outcome_sha`로 다시 쓰인다.
점수가 이전 베이스라인보다 떨어졌다면 커밋하지 말고 원인을 보고한다 — SKILL.md 문구가 마법사를
혼동시켰다는 신호다.

- [ ] **Step 5: 베이스라인을 커밋한다**

```bash
git add evals/outcome_scores.json
git commit -F - <<'MSG'
test(evals): rebaseline wiki-init outcome

The SKILL.md body, the fixture and the golden all feed outcome_sha, so
the previous baseline no longer applies to this arm.
MSG
```

---

## 완료 확인

- [ ] `uv run pytest` 전체 통과
- [ ] `uv run ruff check && uv run ruff format --check` 통과
- [ ] `grep -rn "front matter 에 id\|id: {{ID}}\|carries an \`id\`" skills/ rules/` 결과 없음
- [ ] 4건의 재현 시나리오가 모두 해소됨:
  - `id: Getting_Started` 문서가 있어도 `--verify`가 0
  - 위반 12건일 때 deny 사유가 10줄 + 카운트
  - `title: New: Doc` + `wiki_id`가 있으면 `--verify`가 1이고 그 파일을 지목
  - dangling edge 메시지가 대상 id와 참조자를 모두 담음
