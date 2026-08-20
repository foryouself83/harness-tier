# wiki_id 파생 실행화 구현 플랜

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** wiki_id 파생 규칙을 `derive_wiki_id()` + `--derive-id` 로 실행화해, 산문·구현·플랜 어느 쪽이 어긋나도 pytest 또는 validate_plan 이 지목하게 한다.

**Architecture:** 파생 코어는 `scripts/wiki_graph.py` (SSOT — 호스트 복사는 `COPY_FILES` 로 자동). 산문(wiki-init §5)은 근거 + 패리티-테스트되는 예제 표로 축소, doc-sync·validate_plan 이 코드를 호출/대조한다. 스펙: [2026-08-12-wiki-derive-id-design.md](../specs/2026-08-12-wiki-derive-id-design.md).

**Tech Stack:** Python 3.8+ · PyYAML · pytest · uv

## Global Constraints

- **소스만 수정**: `scripts/` 가 SSOT — 호스트 복사(`.claude/harness-tier/scripts/`)는 절대 건드리지 않는다.
- **게이트 명령의 FAIL-OPEN 유지**: `--build/--verify/--stale/--neighbors` 의 기존 동작·예외 처리 불변. `--derive-id` 만 fail-closed (게이트 명령이 아님).
- **인코딩 방어 유지**: `force_utf8_io()` 경로 불변, 모든 `read_text`/`write_text` 는 `encoding="utf-8"`.
- **repo 언어**: 스킬 본문·코드 주석·docstring 영어, 사용자-facing CLI 출력 한국어 (wiki_graph.py 기존 관례).
- **`allowed-tools` 는 수정하지 않는다** — `--derive-id` 는 인자가 값이라 덮는 규칙이 `*` 로 끝나는 footgun (skill-frontmatter 규율). 주석으로 부재 사유만 남긴다.
- **커밋은 마지막에 한 번** (feat) + evals 재측정분 별도 chore 커밋. 중간 커밋 금지 — vdev dev tier 게이트(review·doc-sync 마커)가 아직 없어 막히고, 과제당 커밋 하나 선호.
- **mutation 복원은 git checkout 금지** — 작업 트리가 미커밋 상태라 `git checkout --` 은 구현 자체를 지운다. Python 역치환으로 복원 (`assert` 로 양방향 적용 단언).
- 검증 명령: `uv run pytest` · `uv run ruff check` · `uv run ruff format --check`.

---

### Task 1: `derive_wiki_id()` + `_wiki_root_hint()` (TDD)

**Files:**
- Modify: `scripts/wiki_graph.py` (`WIKI_ID_RE` 정의 직후, ~L348; `_wiki_root_hint` 는 `load_wiki_config` 바로 뒤 ~L85)
- Test: `tests/test_wiki_graph.py`

**Interfaces:**
- Produces: `derive_wiki_id(path: str, root: str = "docs") -> str` (실패 시 `ValueError`, 한국어 사유) · `_wiki_root_hint(root: Path) -> str` (fail-soft `"docs"`). Task 2·5 가 이 둘을 그대로 쓴다.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_wiki_graph.py` 상단 import 에 `re`·`pytest` 추가 (기존: json·subprocess·Path·scripts), 파일 말미에:

```python
# ---------------------------------------------------------------- derive_wiki_id


def test_derive_wiki_id_examples():
    # wiki-init §5 표와 같은 쌍 — 표 자체는 패리티 테스트가 SKILL.md 에서 긁어 대조한다.
    cases = {
        "docs/code-style/python.md": "code-style.python",
        "docs/a.b.md": "a-b",
        "docs/a/b.md": "a.b",
        "docs/api_spec.md": "api-spec",
        "docs/sds/README.md": "sds.readme",
        "docs/onboarding/README.md": "onboarding.readme",
    }
    for path, expected in cases.items():
        assert wiki_graph.derive_wiki_id(path) == expected, path


def test_derive_wiki_id_root_prefix_is_optional():
    # `--derive-id docs/a.md` 와 `--derive-id a.md --root docs/` 는 같은 호출이다.
    assert wiki_graph.derive_wiki_id("a.b.md", "docs") == "a-b"
    assert wiki_graph.derive_wiki_id("docs/a.b.md", "docs/") == "a-b"


def test_derive_wiki_id_root_prefix_matches_segment_boundary():
    # docs-old/ 는 root docs 의 접두가 아니다 (불변식 6 의 path-prefix footgun 과 동형).
    assert wiki_graph.derive_wiki_id("docs-old/a.md", "docs") == "docs-old.a"


def test_derive_wiki_id_windows_separators():
    assert wiki_graph.derive_wiki_id("docs\\sds\\README.md", "docs") == "sds.readme"


def test_derive_wiki_id_rejects_degenerate_segment():
    # 한글만인 이름은 정규화 후 남는 글자가 없다 — 방출하면 한글 문서 둘부터
    # duplicate-id 로 커밋이 막히므로 (이 기능이 없애려는 증상) 원천 거부.
    with pytest.raises(ValueError, match="영문"):
        wiki_graph.derive_wiki_id("docs/온보딩.md", "docs")


def test_derive_wiki_id_rejects_root_itself_and_empty():
    with pytest.raises(ValueError):
        wiki_graph.derive_wiki_id("docs", "docs")
    with pytest.raises(ValueError):
        wiki_graph.derive_wiki_id("", "docs")


def test_wiki_root_hint_ignores_the_enable_gate(tmp_path: Path):
    # enable: false 여도 root 는 존중 — /harness-init 은 /wiki-init 전에 돌 수 있다
    # (harness-rules 8-2). load_wiki_config 를 거치면 None 이라 조용히 docs 로 파생한다.
    _write_config(tmp_path, "wiki:\n  enable: false\n  root: documentation/\n")
    assert wiki_graph._wiki_root_hint(tmp_path) == "documentation"


def test_wiki_root_hint_fails_soft_to_docs(tmp_path: Path):
    assert wiki_graph._wiki_root_hint(tmp_path) == "docs"  # config 없음
    _write_config(tmp_path, "wiki: [broken\n")
    assert wiki_graph._wiki_root_hint(tmp_path) == "docs"  # 파싱 불가
```

- [ ] **Step 2: RED 확인**

Run: `uv run pytest tests/test_wiki_graph.py -q -k "derive_wiki_id or wiki_root_hint"`
Expected: FAIL — `AttributeError: ... has no attribute 'derive_wiki_id'`

- [ ] **Step 3: 구현** — `scripts/wiki_graph.py` 의 `WIKI_ID_RE` 정의 직후에:

```python
def derive_wiki_id(path: str, root: str = "docs") -> str:
    """Derive a wiki node id from a document path — the executable SSOT for the id rule.

    Each segment is sanitized BEFORE the segments are joined with ".": sanitizing after
    joining would fold the just-created "." separators into "-", collapsing
    docs/a.b.md (a-b) and docs/a/b.md (a.b) onto one id. wiki-init Step 5's example
    table is parity-tested against this function (tests/test_wiki_graph.py).

    Raises ValueError (Korean reason) for a path that cannot produce an id. Unlike the
    gate commands this must not fail open: a silent empty success sends the caller
    back to hand-deriving — the failure mode this function exists to remove.
    """
    text = str(path).replace("\\", "/").strip()
    parts = [seg for seg in PurePosixPath(text).parts if seg not in (".", "/")]
    if not parts:
        raise ValueError("빈 경로에서는 wiki_id 를 만들 수 없습니다")
    root_norm = _norm_rel(root) if root else ""
    root_parts = [seg for seg in PurePosixPath(root_norm).parts if seg != "."]
    # Segment-boundary prefix only — "docs-old/a.md" is not under root "docs" (the same
    # footgun as Invariant #6's path-prefix identity).
    if root_parts and parts[: len(root_parts)] == root_parts:
        parts = parts[len(root_parts) :]
    if not parts:
        raise ValueError(f"경로가 wiki root 자체입니다 — 문서 경로가 필요합니다: {path}")
    segs = parts[:-1] + [PurePosixPath(parts[-1]).stem]
    out = []
    for seg in segs:
        cleaned = re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "-", seg.lower()))
        if not re.search(r"[a-z0-9]", cleaned):
            raise ValueError(
                f"세그먼트 '{seg}' 는 정규화 후 [a-z0-9] 가 남지 않습니다 — "
                f"파일/폴더명을 영문으로 바꿔주세요: {path}"
            )
        out.append(cleaned)
    return ".".join(out)
```

`load_wiki_config` 바로 뒤에:

```python
def _wiki_root_hint(root: Path) -> str:
    """flow-config wiki.root read WITHOUT the enable gate, fail-soft to "docs".

    load_wiki_config() returns None on enable:false, but derivation must work before
    /wiki-init ever runs (harness-rules 8-2 removed that ordering dependency) — going
    through it would silently derive against the default root in a repo whose wiki is
    configured but not yet enabled.
    """
    try:
        import yaml

        data = yaml.safe_load(config_path(root).read_text(encoding="utf-8")) or {}
        return _norm_rel((data.get("wiki") or {}).get("root") or "docs") or "docs"
    except Exception:
        return "docs"
```

- [ ] **Step 4: GREEN 확인**

Run: `uv run pytest tests/test_wiki_graph.py -q -k "derive_wiki_id or wiki_root_hint"`
Expected: PASS (전부)

### Task 2: `--derive-id` CLI + `main()` 재구성 (TDD)

**Files:**
- Modify: `scripts/wiki_graph.py` (`cmd_derive_id` 는 `cmd_stale` 뒤; `main()` 재구성 ~L1059)
- Test: `tests/test_wiki_graph.py`

**Interfaces:**
- Consumes: Task 1 의 `derive_wiki_id` · `_wiki_root_hint`.
- Produces: `wiki_graph.py --derive-id PATH… [--root DIR]` — stdout `경로<TAB>id` 줄, 부분 실패 시 stderr 경로+사유 & exit 1. Task 3·4 의 스킬 문구가 이 계약을 서술한다.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_wiki_graph.py` 말미에:

```python
def test_derive_id_cli_prints_tab_pairs(capsys):
    # 위치 zip 이 아니라 경로<TAB>id 쌍 — 부분 실패 시 줄 밀림으로 조용히 어긋나지 않게.
    rc = wiki_graph.main(["--derive-id", "docs/a/b.md", "docs/a.b.md", "--root", "docs"])
    assert rc == 0
    assert capsys.readouterr().out.splitlines() == ["docs/a/b.md\ta.b", "docs/a.b.md\ta-b"]


def test_derive_id_cli_partial_failure_names_the_path(capsys):
    rc = wiki_graph.main(["--derive-id", "docs/ok.md", "docs/온보딩.md", "--root", "docs"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "docs/ok.md\tok" in captured.out  # 성공분은 그대로 나간다
    assert "온보딩" in captured.err  # 실패분은 경로를 지목한다


def test_derive_id_cli_reads_config_root(tmp_path: Path, monkeypatch, capsys):
    _write_config(tmp_path, "wiki:\n  enable: false\n  root: documentation/\n")
    monkeypatch.setattr(wiki_graph, "host_root", lambda: tmp_path)
    rc = wiki_graph.main(["--derive-id", "documentation/api_spec.md"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "documentation/api_spec.md\tapi-spec"


def test_derive_id_is_not_swallowed_by_fail_open(monkeypatch):
    # --derive-id 는 게이트 명령이 아니다 — 내부 예외가 fail-open 으로 exit 0 이 되면
    # "출력 없는 성공"이고, 호출자는 손 파생으로 회귀한다 (이 명령이 없애려는 실패 모드).
    def _boom(paths, root_arg):
        raise RuntimeError("boom")

    monkeypatch.setattr(wiki_graph, "cmd_derive_id", _boom)
    with pytest.raises(RuntimeError):
        wiki_graph.main(["--derive-id", "docs/a.md"])
```

- [ ] **Step 2: RED 확인**

Run: `uv run pytest tests/test_wiki_graph.py -q -k derive_id_cli`
Expected: FAIL — argparse `SystemExit 2` (unrecognized `--derive-id`)

- [ ] **Step 3: 구현** — `cmd_stale` 뒤에:

```python
def cmd_derive_id(paths: list[str], root_arg: str | None) -> int:
    """--derive-id: one `path<TAB>id` stdout line per success.

    Successes still print when a sibling path fails; each failure names its path and
    reason on stderr and the call exits 1 — the caller fixes only what is named and
    re-runs. TAB pairs, not positional zip: a partial failure must not silently shift
    the path→id mapping.
    """
    root = _norm_rel(root_arg) if root_arg else _wiki_root_hint(host_root())
    failed = False
    for p in paths:
        try:
            print(f"{p}\t{derive_wiki_id(p, root)}")
        except ValueError as exc:
            print(f"{p}: {exc}", file=sys.stderr)
            failed = True
    return 1 if failed else 0
```

`main()` 을 다음으로 교체 (docstring 포함 — 게이트/비게이트 경계가 이 함수의 계약):

```python
def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Gate commands fail open; --derive-id does not.

    For --build/--verify/--stale/--neighbors the exit code is the gate's verdict, and
    wiki is none of Invariant #1's three fail-closed exceptions — they stay inside the
    blanket except. --derive-id never runs in the commit hook, so it dispatches BEFORE
    the try: swallowing its failure into a silent exit 0 would hand the caller back
    the hand-derivation it exists to remove. An argparse usage error is a `SystemExit`
    either way — the gate builds its own commands, so a mistyped flag cannot happen at
    runtime.
    """
    force_utf8_io()
    parser = argparse.ArgumentParser(prog="wiki_graph.py", description="LLM Wiki graph tool")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--build", action="store_true", help="graph.yaml 생성 (doc-sync 전용)")
    group.add_argument("--verify", action="store_true", help="읽기 전용 검증 (flow gate 전용)")
    group.add_argument("--stale", action="store_true", help="코드 stale 목록 (JSON)")
    group.add_argument("--neighbors", metavar="ID", help="예산 내 이웃 문서 경로")
    group.add_argument(
        "--derive-id", nargs="+", metavar="PATH", help="경로별 wiki_id 파생 (경로<TAB>id 출력)"
    )
    parser.add_argument("--budget", type=int, default=None, help="줄 예산 (기본값: config)")
    parser.add_argument(
        "--root", default=None, help="--derive-id 의 wiki root (기본: flow-config wiki.root 또는 docs)"
    )
    args = parser.parse_args(argv)
    if args.derive_id:
        return cmd_derive_id(args.derive_id, args.root)
    try:
        root = host_root()
        if args.build:
            return cmd_build(root)
        if args.stale:
            return cmd_stale(root)
        # `is not None` — an empty string is still a --neighbors request. Branching on
        # truthiness let `--neighbors ""` fall silently through to cmd_verify: the caller
        # read an empty lookup result while a graph verification was actually running,
        # returning 1 on drift.
        if args.neighbors is not None:
            return cmd_neighbors(root, args.neighbors, args.budget)
        return cmd_verify(root)
    except Exception as exc:  # FAIL-OPEN: a broken wiki_graph.py never holds the repo hostage
        print(f"wiki graph 확인 중 내부 오류, 통과 처리합니다: {exc}", file=sys.stderr)
        return 0
```

- [ ] **Step 4: GREEN + 기존 CLI 회귀 확인**

Run: `uv run pytest tests/test_wiki_graph.py -q`
Expected: PASS (특히 `test_main_fails_open_on_internal_exception` · `test_main_argparse_error_still_exits_nonzero` · `test_main_routes_an_empty_neighbors_id_to_the_lookup` 불변)

### Task 3: wiki-init §5 재작성 + 패리티 테스트

**Files:**
- Modify: `skills/wiki-init/SKILL.md` (§5 도입 두 문단, L69–81)
- Test: `tests/test_wiki_graph.py`

**Interfaces:**
- Consumes: `derive_wiki_id`. 패리티 정규식이 §5 표 형식(`| \`경로\` | \`id\` |`)과 템플릿 주석 화살표(`docs/….md -> id`)를 파싱한다 — 형식을 바꾸면 테스트도 함께 바꿔야 한다.

- [ ] **Step 1: §5 의 L69–81 (도입 두 문단, "`related` · `depends_on`" 문단 직전까지) 를 다음으로 교체** — 이후 문단(related/sources/YAML quoting/defect)은 그대로:

```markdown
`wiki_id` is derived mechanically from the path **relative to the wiki root** — never
pick one by hand, and never derive it by hand either: run
[`wiki_graph.py`](../../scripts/wiki_graph.py) `--derive-id`, one call for all the
selected documents, substituting their real paths (e.g. `python3
.claude/harness-tier/scripts/wiki_graph.py --derive-id docs/code-style/python.md
docs/api_spec.md`). Each stdout line is `path<TAB>id`. A path that cannot produce an
id — a segment with no `[a-z0-9]` left after sanitizing, e.g. a Korean-only
filename — is named on stderr with the reason: rename that file and re-run.
`derive_wiki_id` owns the mechanics; this table is parity-tested against it
(`tests/test_wiki_graph.py`), so adding a row here adds a test case:

| path (root `docs/`) | wiki_id |
|---|---|
| `docs/code-style/python.md` | `code-style.python` |
| `docs/a.b.md` | `a-b` |
| `docs/a/b.md` | `a.b` |
| `docs/api_spec.md` | `api-spec` |
| `docs/sds/README.md` | `sds.readme` |
| `docs/onboarding/README.md` | `onboarding.readme` |

The order inside the rule is what makes it collision-free — each segment is sanitized
**before** the segments are joined with `.`, which keeps `docs/a.b.md` (→ `a-b`)
distinct from `docs/a/b.md` (→ `a.b`). An id derived by hand in the wrong order still
satisfies the shape regex and fails later as a duplicate — `--verify` then blocks
every commit until it is fixed.
```

- [ ] **Step 2: 패리티 테스트 작성** — `tests/test_wiki_graph.py` 말미에:

```python
_REPO = Path(__file__).resolve().parents[1]
_TABLE_ROW_RE = re.compile(r"^\s*\|\s*`([^`]+\.md)`\s*\|\s*`([^`]+)`\s*\|", re.MULTILINE)
_ARROW_EXAMPLE_RE = re.compile(r"\b(docs/[^\s`]+?\.md)\s*->\s*([a-z0-9.-]+)")


def test_wiki_init_step5_table_is_parity_tested():
    # 표가 곧 테스트 케이스다 — 산문 예제가 구현과 어긋나면 여기서 그 행이 지목된다.
    # 행 수 하한: 표가 사라지면 0쌍 매치로 공허하게 초록이 되는 걸 막는다.
    text = (_REPO / "skills" / "wiki-init" / "SKILL.md").read_text(encoding="utf-8")
    pairs = _TABLE_ROW_RE.findall(text)
    assert len(pairs) >= 5, "wiki-init §5 예제 표가 사라졌거나 줄었다"
    for path, expected in pairs:
        assert wiki_graph.derive_wiki_id(path, "docs") == expected, path


def test_template_comment_examples_are_parity_tested():
    # harness-authoring 템플릿 YAML 주석의 워크드 예제 (docs/x.md -> id 꼴)도 같은 규칙.
    tpl_dir = _REPO / "skills" / "harness-authoring" / "templates"
    found = 0
    for tpl in sorted(tpl_dir.glob("*.template.md")):
        for path, expected in _ARROW_EXAMPLE_RE.findall(tpl.read_text(encoding="utf-8")):
            assert wiki_graph.derive_wiki_id(path, "docs") == expected, tpl.name
            found += 1
    assert found >= 2, "템플릿 주석의 워크드 예제가 사라졌다"
```

- [ ] **Step 3: GREEN 확인**

Run: `uv run pytest tests/test_wiki_graph.py -q -k parity`
Expected: PASS (2건)

- [ ] **Step 4: 스킬 파일 정합성 확인**

Run: `uv run pytest tests/test_skills.py -q`
Expected: PASS (링크·frontmatter 검사)

### Task 4: doc-sync Mode W 재배선

**Files:**
- Modify: `skills/doc-sync/SKILL.md` (frontmatter 주석 L6–9 · Mode W step 4 L157–163)

**Interfaces:**
- Consumes: Task 2 의 CLI 계약 (`경로<TAB>id` · stderr 지목).

- [ ] **Step 1: Mode W step 4 첫 문장 교체** — 기존:

```markdown
4. **Give any new `.md` under the wiki root its front matter** — `wiki_id` (mechanics owned
   by [wiki-init](../wiki-init/SKILL.md) Step 5: derived from the path **relative to
   the wiki root**), `title`, and the `sources` it documents.
```

를 다음으로 (문단 나머지 — `Never write used_by …` 이하 — 는 그대로):

```markdown
4. **Give any new `.md` under the wiki root its front matter** — get `wiki_id` from one
   derivation call for all the new documents, substituting their real paths (e.g.
   `python3 .claude/harness-tier/scripts/wiki_graph.py --derive-id docs/auth/jwt.md
   docs/auth/session.md`; each stdout line is `path<TAB>id`, a failure names its path
   on stderr — fix that path and re-run; rationale in
   [wiki-init](../wiki-init/SKILL.md) Step 5), then `title`, and the `sources` it
   documents.
```

- [ ] **Step 2: frontmatter 주석에 부재 사유 한 줄 추가** — 주석 마지막 문장 `The per-node prompt is the cost of not granting that.` 뒤에 이어서:

```text
`--derive-id <paths>` is absent for the same reason — path arguments force a trailing `*`.
```

- [ ] **Step 3: 확인**

Run: `uv run pytest tests/test_skills.py -q`
Expected: PASS

### Task 5: `validate_plan` wiki-id 대조 (TDD)

**Files:**
- Modify: `scripts/harness_scaffold.py` (import ~L22 · `validate_plan` 루프 내 컴포넌트 블록 뒤 ~L832)
- Test: `tests/test_harness_scaffold.py`

**Interfaces:**
- Consumes: `derive_wiki_id` · `_wiki_root_hint` (try/except 이중 경로 import — `_harness_paths` 와 동일 패턴).
- Produces: issue `{"severity": "high", "kind": "wiki-id", "path", "detail"}`.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_harness_scaffold.py` 말미에:

```python
# ---------------------------------------------------------------- wiki-id parity


def _wiki_plan(path: str, content: str) -> dict:
    return {"files": [{"path": path, "action": "create", "content": content}]}


def test_validate_plan_flags_hand_derived_wiki_id(tmp_path):
    # 손 파생이 기계 파생과 어긋나면 나중에 duplicate/format 으로 --verify 가 모든 커밋을
    # 막는다 — plan 시점에 잡는 유일한 강제점.
    content = "---\nwiki_id: code-style-python\ntitle: t\n---\n본문\n"
    res = hs.validate_plan(tmp_path, _wiki_plan("docs/code-style/python.md", content))
    hits = [i for i in res["issues"] if i["kind"] == "wiki-id"]
    assert hits and "code-style.python" in hits[0]["detail"]


def test_validate_plan_accepts_the_derived_wiki_id(tmp_path):
    content = "---\nwiki_id: code-style.python\ntitle: t\n---\n본문\n"
    res = hs.validate_plan(tmp_path, _wiki_plan("docs/code-style/python.md", content))
    assert not any(i["kind"] == "wiki-id" for i in res["issues"])


def test_validate_plan_flags_unfilled_id_placeholder(tmp_path):
    # {{ID}} 를 안 채운 템플릿 복제도 같은 검사에 걸린다.
    content = "---\nwiki_id: '{{ID}}'\ntitle: t\n---\n본문\n"
    res = hs.validate_plan(tmp_path, _wiki_plan("docs/sds/README.md", content))
    assert any(i["kind"] == "wiki-id" for i in res["issues"])


def test_validate_plan_ignores_md_outside_wiki_root(tmp_path):
    content = "---\nwiki_id: totally-wrong\ntitle: t\n---\n본문\n"
    res = hs.validate_plan(tmp_path, _wiki_plan(".claude/rules/x-conventions.md", content))
    assert not any(i["kind"] == "wiki-id" for i in res["issues"])


def test_validate_plan_ignores_docs_without_wiki_id(tmp_path):
    res = hs.validate_plan(tmp_path, _wiki_plan("docs/guide.md", "본문만\n"))
    assert not any(i["kind"] == "wiki-id" for i in res["issues"])


def test_validate_plan_skips_front_matter_not_at_byte_zero(tmp_path):
    # 선행 HTML 주석 = "위키 밖" 마커 (wiki_graph 와 같은 의미론) — 노드가 아니므로 스킵.
    content = "<!-- note -->\n---\nwiki_id: wrong\ntitle: t\n---\n본문\n"
    res = hs.validate_plan(tmp_path, _wiki_plan("docs/guide.md", content))
    assert not any(i["kind"] == "wiki-id" for i in res["issues"])


def test_validate_plan_flags_underivable_path(tmp_path):
    content = "---\nwiki_id: onboarding\ntitle: t\n---\n본문\n"
    res = hs.validate_plan(tmp_path, _wiki_plan("docs/온보딩.md", content))
    assert any(i["kind"] == "wiki-id" for i in res["issues"])
```

- [ ] **Step 2: RED 확인**

Run: `uv run pytest tests/test_harness_scaffold.py -q -k wiki_id`
Expected: FAIL (`wiki-id` kind 미존재 — flags/underivable/placeholder 3건)

- [ ] **Step 3: 구현** — `scripts/harness_scaffold.py` 의 `force_utf8_io` import 블록 뒤에:

```python
try:
    from wiki_graph import _wiki_root_hint, derive_wiki_id
except ImportError:
    from scripts.wiki_graph import _wiki_root_hint, derive_wiki_id
```

`validate_plan` 에서 `plan_paths` 계산 직후에 `wiki_root = _wiki_root_hint(root)` 한 줄, 그리고 파일 루프 안 컴포넌트(name/dedup) 블록 뒤 · 링크 스캔 앞에:

```python
        # Wiki-node id parity: a hand-derived wiki_id that disagrees with the mechanical
        # derivation surfaces later as a duplicate/format --verify block on every commit —
        # catch it at plan time instead. Only .md under the wiki root whose front matter
        # starts at byte 0 and carries wiki_id are nodes (same marker semantics as
        # wiki_graph; _parse_frontmatter already returns {} otherwise).
        if rel.endswith(".md") and rel.startswith(f"{wiki_root}/"):
            wid = _parse_frontmatter(content).get("wiki_id")
            if isinstance(wid, str) and wid:
                try:
                    expected = derive_wiki_id(rel, wiki_root)
                    if wid != expected:
                        issues.append(
                            {
                                "severity": "high",
                                "kind": "wiki-id",
                                "path": rel,
                                "detail": (
                                    f"wiki_id '{wid}' ≠ 경로 파생값 '{expected}' — "
                                    "--derive-id 로 얻으세요"
                                ),
                            }
                        )
                except ValueError as exc:
                    issues.append(
                        {"severity": "high", "kind": "wiki-id", "path": rel, "detail": str(exc)}
                    )
```

- [ ] **Step 4: GREEN 확인**

Run: `uv run pytest tests/test_harness_scaffold.py -q`
Expected: PASS (전부 — 기존 검사 회귀 포함)

### Task 6: mutation test + 전체 검증

**Files:**
- Modify (일시): `scripts/wiki_graph.py` — Python 역치환으로 복원

- [ ] **Step 1: 순서 뒤집기 mutation 적용** (join 후 정규화 = 원래 버그 재현; `assert` 로 적용 단언):

```bash
uv run python - <<'EOF'
from pathlib import Path

p = Path("scripts/wiki_graph.py")
text = p.read_text(encoding="utf-8")
old = '        out.append(cleaned)\n    return ".".join(out)\n'
new = (
    '        out.append(cleaned)\n'
    '    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "-", ".".join(out)))\n'
)
assert old in text, "mutation target not found"
p.write_text(text.replace(old, new, 1), encoding="utf-8")
print("mutated")
EOF
```

- [ ] **Step 2: 스위트가 RED 인지 확인** (mutation 이 안 잡히면 테스트가 순서를 안 보는 것)

Run: `uv run pytest tests/test_wiki_graph.py tests/test_harness_scaffold.py -q`
Expected: FAIL — `test_derive_wiki_id_examples` · 패리티 2건 · scaffold 대조 다수

- [ ] **Step 3: Python 역치환으로 복원 + GREEN 재확인** (트리가 미커밋이라 `git checkout --` 은 구현을 지운다 — 금지):

```bash
uv run python - <<'EOF'
from pathlib import Path

p = Path("scripts/wiki_graph.py")
text = p.read_text(encoding="utf-8")
new = (
    '        out.append(cleaned)\n'
    '    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9-]", "-", ".".join(out)))\n'
)
old = '        out.append(cleaned)\n    return ".".join(out)\n'
assert new in text, "mutated line not found — nothing to restore"
p.write_text(text.replace(new, old, 1), encoding="utf-8")
print("restored")
EOF
uv run pytest tests/test_wiki_graph.py tests/test_harness_scaffold.py -q
```

Expected: `restored` 후 PASS

- [ ] **Step 4: 전체 정적 검사 + 스위트**

Run: `uv run ruff check && uv run ruff format --check && uv run pytest -q`
Expected: ruff 통과. pytest 는 **`test_committed_outcome_baseline_is_never_stale_or_zero` 1건만 FAIL** — wiki-init·doc-sync SKILL.md 본문 수정이 `outcome_sha` 를 바꿔 커밋된 outcome 베이스라인이 stale (Task 7 이 해소). 그 외 FAIL 은 이 태스크에서 고친다.

### Task 7: outcome 베이스라인 재측정 (evals)

**Files:**
- Modify (자동): `evals/outcome_scores.json`

- [ ] **Step 1: 본문이 바뀐 두 스킬만 재측정** (모델 호출 발생 — reps 3, 다른 스킬 베이스라인은 유지). doc-sync 골든은 wiki_id 파생 결과를 직접 검사하므로, 이 재측정이 재배선된 스킬의 실제 실행까지 검증한다:

```bash
uv run python -m evals.outcome --skill wiki-init
uv run python -m evals.outcome --skill doc-sync
```

Expected: 각 스킬 `outcome_hits`/`outcome_n` 갱신 + 새 `outcome_sha`. hits 가 크게 떨어지면 스킬 문구 회귀 — Step 2 전에 원인 수정.

- [ ] **Step 2: 전체 스위트 GREEN 확인**

Run: `uv run pytest -q`
Expected: PASS (전부)

### Task 8: 게이트 + 커밋

- [ ] **Step 1: 독립 review 에이전트** — `general-purpose` 에이전트(별도 컨텍스트)에 변경 파일 전체(git 목록·개수 보고)를 리스크-티어 체크리스트(회귀·계약·파생 규칙 경계·부분 실패 처리·fail-open 경계)로 검토시킨다. 통과 시:

```bash
touch .claude/vway-kit/.vdev/review.done
```

- [ ] **Step 2: doc-sync 스킬 실행** — 인덱스·번역 쌍(README/USAGE `.ko`) 정합 확인 (wiki_graph CLI 플래그는 소비자 문서에 미기재 — 신규 기재 의무 없음, doc-sync 가 판단). 통과 시:

```bash
touch .claude/vway-kit/.vdev/doc-sync.done
```

- [ ] **Step 3: 커밋 2건** (feat = 소비자-facing 전파분, chore = evals 비출하분 — risk-tiers "카테고리당 1커밋"):

```bash
git add scripts/wiki_graph.py scripts/harness_scaffold.py tests/test_wiki_graph.py \
  tests/test_harness_scaffold.py skills/wiki-init/SKILL.md skills/doc-sync/SKILL.md \
  skills/harness-authoring/references/authoring-spec.md \
  docs/superpowers/specs/2026-08-12-wiki-derive-id-design.md \
  docs/superpowers/plans/2026-08-12-wiki-derive-id.md
git commit -m "feat(wiki): make wiki_id derivation executable

- derive_wiki_id + --derive-id own the id rule; prose keeps only the
  why and a parity-tested example table (wiki-init Step 5).
- validate_plan flags a hand-derived wiki_id before it is written.
- authoring-spec drops its (mis-ordered) restatement for a link."
git add evals/outcome_scores.json
git commit -m "chore(evals): refresh outcome baseline for reworded skills"
```

- [ ] **Step 4: 상태 보고** — 남은 것: dev 브랜치 머지(리베이스→스쿼시, 별도 확인), vway-kit 이식(별도 작업), `feature/authoring-terseness-rules` 머지 대기 중.

---

## Self-Review 결과

- 스펙 A~G ↔ Task 1~5 전부 대응, 실패 계약·root 우선순위·퇴화 거부 테스트로 고정.
- outcome_sha 연쇄(스펙 밖 발견)는 Task 7 로 흡수 — 스펙 "검증" 절의 `uv run pytest` 통과 요건이 요구.
- 시그니처 일관: `derive_wiki_id(path, root)` · `_wiki_root_hint(root)` · `cmd_derive_id(paths, root_arg)` 전 태스크 동일.
- mutation 복원이 git checkout 을 못 쓰는 이유(미커밋 트리)를 Global Constraints 와 Task 6 에 명시.
