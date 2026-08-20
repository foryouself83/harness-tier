# LLM Wiki 보강 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** LLM Wiki에 읽기 경로를 열고, stale 판정을 blob hash로 바꾸고, sha 도장을 기계 검증하고, 게이트를 1-spawn으로 통합하고, CI 검증과 문서 규율을 보강한다.

**Architecture:** 모든 로직 변경은 `scripts/wiki_graph.py`·`scripts/flow_gate_check.py`·`scripts/precommit-runner.sh`(SOURCE)에만 — 호스트 복사본은 건드리지 않는다. CI는 `github/` 템플릿 신설 + `flow_init_setup.py` 렌더 + 자체 `.github/` 도그푸드. 스킬 계약 변경은 wiki-init·doc-sync·flow SKILL.md.

**Tech Stack:** Python 3.8+ (PyYAML만), bash (ShellCheck), pytest, GitHub Actions.

**Spec:** [docs/superpowers/specs/2026-08-13-wiki-hardening-design.md](../specs/2026-08-13-wiki-hardening-design.md)

## Global Constraints

- 게이트 스크립트 floor = python 3.8, 의존 = PyYAML뿐 (`check-deps.sh`와 동기).
- Invariant #1: wiki 게이트는 fail-open — 판정이 아닌 모든 실패는 통과. `--derive-id`만 예외.
- Invariant #2: `force_utf8_io()`·`encoding="utf-8"` 유지. 사용자 대면 출력 한국어, 주석/독스트링 영어.
- Invariant #3: block = exit 2 + stdout 사유 (runner는 stdout만 읽는다 — `2>/dev/null` 유지).
- 워크플로 저작 규칙: 모든 job에 `timeout-minutes`, `run:` 블록에 `${{ }}` 금지 (test_flow_init_setup이 강제).
- SOURCE만 수정 (`scripts/`·`github/`·`flow-tiers.yaml`), 호스트 복사본 금지.
- 커밋은 마지막에 **단일 `feat` 커밋** (spec §11 — 중간 커밋은 dev 티어 게이트 마커가 없어 막힌다). 각 태스크의 "Commit" 스텝 없음이 의도다.

---

### Task 1: front matter 파서 경계 수정 + 중복 `wiki_id` 경고

**Files:**
- Modify: `scripts/wiki_graph.py` (`_front_matter_block` · `collect_nodes` · `collect_warnings`)
- Test: `tests/test_wiki_graph.py`

**Interfaces:**
- Produces: `_FM_OPEN_RE`·`_FM_CLOSE_RE` (Task 3의 `_split_body`가 재사용), node dict의 `dup_marker: bool` 키.
- `_front_matter_block` 반환 계약(블록 텍스트/None)·기존 두 소비자 시그니처 불변.

- [ ] **Step 1: 실패 테스트 작성** — `tests/test_wiki_graph.py`의 parse_front_matter 테스트군 옆에 추가:

```python
def test_front_matter_ruler_first_line_is_not_a_block():
    # `----` 는 여는 구분자가 아니다 — find("\n---") 시절 hr 로 시작하는 문서가
    # "깨진 front matter" 경고로 잡히던 케이스.
    assert wiki_graph._front_matter_block("----\n제목\n----\n본문\n") is None


def test_front_matter_crlf_closing_line():
    text = "---\r\nwiki_id: a\r\ntitle: T\r\n---\r\n\r\n본문\r\n"
    assert parse_front_matter(text) == {"wiki_id": "a", "title": "T"}


def test_front_matter_body_dashes_line_does_not_close_early():
    # 블록 안 열 0 의 `--- note` 줄은 닫는 구분자가 아니다. 조기 종결은 wiki_id 를
    # 조용히 블록 밖으로 밀어내 노드가 소리 없이 사라지게 했다.
    text = "---\ntitle: T\n--- note\nwiki_id: a\n---\n본문\n"
    block = wiki_graph._front_matter_block(text)
    assert block is not None and "wiki_id: a" in block


def test_duplicate_wiki_id_lines_warn(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/index.md", "wiki_id: index\ntitle: Index\n")
    _node(tmp_path, "docs/a.md", "wiki_id: old\nwiki_id: a\ntitle: A\n")
    wiki = load_wiki_config(tmp_path)
    nodes = collect_nodes(tmp_path, wiki)
    warns = collect_warnings(wiki, nodes, build_graph(nodes))
    assert any("wiki_id" in w and "여러 개" in w for w in warns)
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_wiki_graph.py -k "front_matter_ruler or crlf_closing or dashes_line or duplicate_wiki_id" -v`
Expected: 4 FAIL (`----` 가 블록으로 읽힘 · CRLF 닫는 줄 불일치 · 조기 종결 · 경고 부재)

- [ ] **Step 3: `_front_matter_block` 재구현** — `_FM_DELIM` 상수와 기존 함수를 교체:

```python
_FM_DELIM = "---"
# Opening: the first line is exactly `---` (trailing blanks tolerated). Closing: a LINE that is
# `---` — the old `find("\n---")` also matched a `----` ruler and a column-0 `--- note` body
# line, silently truncating the block there (a wiki_id below the false close vanished without
# a word). CRLF: `\r?` keeps both delimiters recognizable in files with Windows line endings.
_FM_OPEN_RE = re.compile(r"^---[ \t]*\r?\n")
_FM_CLOSE_RE = re.compile(r"^---[ \t]*\r?$", re.MULTILINE)


def _front_matter_block(text: str) -> str | None:
    """The text between the opening `---` line and the closing one, or None when there is no
    block. Both readers below share this so the delimiter rule lives in one place."""
    m_open = _FM_OPEN_RE.match(text)
    if m_open is None:
        return None
    m_close = _FM_CLOSE_RE.search(text, m_open.end())
    if m_close is None:
        return None
    return text[m_open.end() : m_close.start()]
```

`_FM_DELIM` 참조가 남으면 (`startswith(_FM_DELIM)` 등) 함께 정리 — grep으로 확인. 상수 자체는 남는 소비자가 없으면 삭제.

- [ ] **Step 4: 중복 마커 수집** — `collect_nodes`의 정상 분기(front 파싱 성공)에서 node dict에 두 키 추가:

```python
        block = _front_matter_block(text)
        nodes.append(
            {
                "id": str(raw_id) if raw_id else None,
                "path": path.relative_to(root).as_posix(),
                "line_count": len(text.splitlines()),
                "front": front,
                "text": text,  # Task 3 (stamp check) reads the body from here
                "dup_marker": bool(block) and len(_MARKER_LINE_RE.findall(block)) > 1,
            }
        )
```

`collect_warnings`에 (기존 `_capped` 패턴대로, "wiki_id 없는 wiki 필드" 블록 뒤) 추가:

```python
    _capped(
        warns,
        [
            f"{node['path']}: wiki_id: 줄이 여러 개입니다 — YAML 은 마지막 값을 채택합니다. "
            f"하나만 남기세요"
            for node in nodes
            if node.get("dup_marker")
        ],
        "wiki_id 중복 선언",
    )
```

- [ ] **Step 5: 통과 확인 + 회귀**

Run: `uv run pytest tests/test_wiki_graph.py -v`
Expected: 신규 4개 PASS, 기존 전부 PASS (특히 `_broken_front_matter`·Jekyll 빈 블록·BOM 테스트)

---

### Task 2: stale 판정 blob-hash 전환 + 마이그레이션 값

**Files:**
- Modify: `scripts/wiki_graph.py` (`cmd_stale` 재작성, `_blob_hashes` 신설)
- Test: `tests/test_wiki_graph.py`

**Interfaces:**
- Produces: `_blob_hashes(root: Path, paths: list[str]) -> dict[str, str]`.
- `--stale` JSON 항목: 기존 키(`id`·`path`·`source`·`recorded`·`current`·`missing`) 의미 변경 — `recorded`/`current`는 이제 **blob hash**. 기록 값이 커밋 객체면 `"migrated": <str|None>` 키 추가.
- Consumes: Task 1과 독립 (병행 가능).

- [ ] **Step 1: 실패 테스트 작성** — 기존 cmd_stale 테스트군이 쓰는 git-repo 헬퍼를 재사용한다 (`tests/test_wiki_graph.py`에서 `git init` grep — 기존 stale 테스트가 커밋을 만드는 방식 그대로). 신규:

```python
def test_stale_blob_recorded_fresh_and_stale(tmp_path: Path):
    # 준비: git repo + src/a.py 커밋 + 노드가 working tree blob 을 기록 → 항목 없음(fresh).
    # 그 뒤 src/a.py 를 수정(커밋 불필요 — working tree 기준) → recorded/current 가 다른
    # blob hash 로 항목 등장, migrated 키 없음.
    root = _stale_repo(tmp_path)          # 기존 헬퍼/픽스처 재사용
    blob = subprocess.run(
        ["git", "hash-object", "--", "src/a.py"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout.strip()
    _node(root, "docs/a.md", f"wiki_id: a\ntitle: A\nsources:\n  src/a.py: '{blob}'\n")
    assert _stale_entries(root) == []     # 기존 JSON-파싱 헬퍼 재사용
    (root / "src/a.py").write_text("changed = True\n", encoding="utf-8")
    entries = _stale_entries(root)
    assert len(entries) == 1
    e = entries[0]
    assert e["recorded"] == blob and e["current"] != blob
    assert "migrated" not in e


def test_stale_commit_recorded_offers_migration(tmp_path: Path):
    # 구형 기록(커밋 sha) → migrated == `git rev-parse <커밋>:<경로>` (그 시점 blob).
    # 내용 무변경이어도 항목이 나온다 — doc-sync 가 마커만 재작성해 수렴하도록.
    root = _stale_repo(tmp_path)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()
    want = subprocess.run(
        ["git", "rev-parse", f"{head}:src/a.py"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout.strip()
    _node(root, "docs/a.md", f"wiki_id: a\ntitle: A\nsources:\n  src/a.py: '{head}'\n")
    entries = _stale_entries(root)
    assert len(entries) == 1
    assert entries[0]["migrated"] == want


def test_stale_vanished_commit_migrates_to_null(tmp_path: Path):
    # 존재하지 않는 40-hex 기록(GC 된 커밋) → 타입 조회 실패 → migrated: null 일반 stale.
    root = _stale_repo(tmp_path)
    _node(root, "docs/a.md", "wiki_id: a\ntitle: A\nsources:\n  src/a.py: 'f' * 40 자리\n")
    # 실제 코드: front 에 "f"*40 문자열을 넣는다
    entries = _stale_entries(root)
    assert len(entries) == 1 and entries[0]["migrated"] is None


def test_stale_batches_hash_object(tmp_path: Path, monkeypatch):
    # Windows spawn 비용 — 경로가 몇 개든 hash-object 호출은 1회.
    root = _stale_repo(tmp_path, extra_sources=3)
    calls: list[str] = []
    real = wiki_graph._git
    def spy(args, cwd):
        calls.append(args[0])
        return real(args, cwd)
    monkeypatch.setattr(wiki_graph, "_git", spy)
    cmd_stale(root)
    assert calls.count("hash-object") <= 1
```

(`_stale_repo`/`_stale_entries`가 없으면 기존 stale 테스트의 준비 코드를 추출해 이 이름들로 헬퍼화 — 기존 테스트도 그걸 쓰도록 정리. `'f' * 40` 은 실제 코드에서 파이썬으로 조립.)

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_wiki_graph.py -k "stale" -v`
Expected: 신규 4 FAIL (기존 git-log 의미론), 기존 stale 테스트 일부도 FAIL 가능 — 의미 전환이므로 기존 stale 테스트는 Step 3에서 blob 의미로 **재작성**한다 (커밋-sha 기대를 남기지 않는다).

- [ ] **Step 3: 구현** — `_last_commit` 위쪽에 헬퍼 추가, `cmd_stale` 본문 교체:

```python
def _blob_hashes(root: Path, paths: list[str]) -> dict[str, str]:
    """Working-tree blob hash per file path, one spawn for the whole set.

    Directories and unreadable paths are absent from the result (a directory has no working-tree
    blob; its staleness is simply not checked — `sources` names files). A failed git call →
    {} (FAIL-OPEN: absence of an answer is never staleness)."""
    existing = [p for p in paths if (root / p).is_file()]
    if not existing:
        return {}
    out = _git(["hash-object", "--", *existing], root)
    if out is None:
        return {}
    hashes = out.splitlines()
    if len(hashes) != len(existing):
        return {}
    return dict(zip(existing, hashes))
```

```python
def cmd_stale(root: Path) -> int:
    """Compare each recorded `sources` blob hash against the working tree, as JSON. Always 0.

    The recorded value means "the blob of this file as doc-sync READ it at sync time"
    (`git hash-object`), so history rewrites (squash/rebase promotions) cannot fake staleness —
    same content, same hash. A legacy value that names a COMMIT (the pre-blob semantics) gets a
    `migrated` field: `git rev-parse <recorded>:<path>` — the meaning-preserving rewrite
    doc-sync stamps without re-reading. `migrated: null` = the commit is gone (GC) — treat as
    plainly stale. A lookup, so it never blocks — the gate does not call it; doc-sync consumes it.
    """
    wiki = load_wiki_config(root)
    if wiki is None:
        print(json.dumps([], ensure_ascii=False))
        return 0
    triples: list[tuple[dict, str, str | None]] = []  # (node, src, recorded)
    for node in collect_nodes(root, wiki):
        if not node["id"]:
            continue
        sources = node["front"].get("sources")
        if not isinstance(sources, dict):
            continue
        for key in sorted(sources, key=str):
            raw = sources[key]
            recorded = raw if isinstance(raw, str) and raw else None
            triples.append((node, str(key), recorded))
    current_by_path = _blob_hashes(root, sorted({src for _, src, _ in triples}))
    type_cache: dict[str, str | None] = {}  # recorded sha → git object type (None = unknown)
    out: list[dict] = []
    for node, src, recorded in triples:
        if not (root / src).exists():
            out.append(
                {
                    "id": node["id"], "path": node["path"], "source": src,
                    "recorded": recorded, "current": None, "missing": True,
                }
            )
            continue
        current = current_by_path.get(src)
        if not current:
            continue  # no answer (directory / failed git) is not staleness (FAIL-OPEN)
        if recorded is not None and current.startswith(recorded):
            continue  # fresh under blob semantics
        entry = {
            "id": node["id"], "path": node["path"], "source": src,
            "recorded": recorded, "current": current, "missing": False,
        }
        if recorded is not None and _SHA_RE.match(recorded):
            if recorded not in type_cache:
                type_cache[recorded] = _git(["cat-file", "-t", recorded], root)
            obj_type = type_cache[recorded]
            if obj_type == "commit":
                entry["migrated"] = _git(["rev-parse", f"{recorded}:{src}"], root)
            elif obj_type is None:
                entry["migrated"] = None  # legacy commit sha, object gone — plainly stale
            # obj_type == "blob": an ordinary blob drift, no migration involved
        out.append(entry)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0
```

기존 `head_cache`/`git log` 로직·주석은 삭제된다. 기존 stale 테스트를 blob 의미로 손본다 (예: "sha 미기록 → 항목", "`missing: true`", "빈 문자열 sha 는 미기록" 케이스는 의미 유지 — 준비만 blob 값으로).

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_wiki_graph.py -k "stale" -v`
Expected: 전부 PASS

---

### Task 3: sha 도장 정직성 검증 (`--verify` block)

**Files:**
- Modify: `scripts/wiki_graph.py` (`validate_stamps`·`_split_body` 신설, `cmd_verify` 한 줄)
- Test: `tests/test_wiki_graph.py`

**Interfaces:**
- Consumes: Task 1의 `_FM_OPEN_RE`/`_FM_CLOSE_RE`, `collect_nodes`의 `text` 키. Task 2의 blob 의미론 (마이그레이션 허용 조건이 `rev-parse <old>:<path>`).
- Produces: `validate_stamps(root: Path, wiki: dict, nodes: list[dict]) -> list[str]` — cmd_verify가 structural 문제 목록에 이어붙인다.

- [ ] **Step 1: 실패 테스트 작성** — git repo에서 HEAD 대비 working tree 비교이므로 준비는 "노드 파일 커밋 → working tree 수정":

```python
def _stamp_repo(tmp_path: Path) -> Path:
    """repo + 커밋된 노드 1개(sources sha 기록) + 매칭 graph.yaml. 반환: root."""
    root = tmp_path
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=root, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=root, check=True)
    (root / "src").mkdir()
    (root / "src/a.py").write_text("x = 1\n", encoding="utf-8")
    (root / "docs").mkdir()
    _write_config(root, "wiki:\n  enable: true\n  root: docs/\n")
    blob = subprocess.run(
        ["git", "hash-object", "--", "src/a.py"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout.strip()
    _node(root, "docs/index.md", "wiki_id: index\ntitle: Index\nrelated: [a]\n")
    _node(root, "docs/a.md", f"wiki_id: a\ntitle: A\nsources:\n  src/a.py: '{blob}'\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=root, check=True)
    return root


def test_stamp_only_change_blocks(tmp_path: Path, capsys):
    root = _stamp_repo(tmp_path)
    doc = root / "docs/a.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(
            _recorded_sha(doc), "b" * 40  # sources sha 만 교체, 본문 그대로
        ),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0            # graph 는 일치시켜 도장 위반만 남긴다
    assert cmd_verify(root) == 1
    assert "본문 변경이 없습니다" in capsys.readouterr().err


def test_stamp_with_body_edit_passes(tmp_path: Path):
    root = _stamp_repo(tmp_path)
    doc = root / "docs/a.md"
    text = doc.read_text(encoding="utf-8").replace(_recorded_sha(doc), "b" * 40)
    doc.write_text(text + "\n갱신된 설명.\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    assert cmd_verify(root) == 0


def test_stamp_migration_rewrite_passes(tmp_path: Path):
    # old 가 커밋 sha, new == rev-parse <old>:<src> → 의미보존 재작성 허용.
    root = _stamp_repo(tmp_path)
    head = _head_sha(root)
    doc = root / "docs/a.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(_recorded_sha(doc), head), encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    subprocess.run(["git", "commit", "-qm", "legacy commit-sha marker"], cwd=root, check=True)
    blob_at_head = subprocess.run(
        ["git", "rev-parse", f"{head}:src/a.py"],
        cwd=root, capture_output=True, text=True, check=True,
    ).stdout.strip()
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(head, blob_at_head), encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    assert cmd_verify(root) == 0


def test_stamp_new_file_passes(tmp_path: Path):
    # HEAD 에 없는 새 문서의 최초 도장은 자유 (저작 자체가 동기화).
    root = _stamp_repo(tmp_path)
    _node(root, "docs/b.md", "wiki_id: b\ntitle: B\nrelated: [index]\nsources:\n  src/a.py: 'c' * 40 자리\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    assert cmd_verify(root) == 0
```

(`_recorded_sha`/`_head_sha`는 파일에서 sha 문자열을 읽는 3줄 헬퍼로 함께 작성. `'c' * 40` 은 실제 코드에서 조립. `docs/b.md`는 index 쪽 `related` 갱신 대신 자기 쪽 `related: [index]`로 도달 — orphan 은 warn 이라 verify 결과에 영향 없지만 노이즈를 줄인다.)

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_wiki_graph.py -k "stamp" -v`
Expected: `test_stamp_only_change_blocks`만 FAIL (verify 가 0 반환 — 검사 부재), 나머지는 PASS일 수 있음 (검사가 없으니 전부 통과) — block 케이스의 FAIL 이 레드다.

- [ ] **Step 3: 구현** — `validate_defects` 아래 추가, `cmd_verify` 연결:

```python
def _split_body(text: str) -> str:
    """The document body — everything after the front-matter block, stripped. The whole text
    when there is no block."""
    m_open = _FM_OPEN_RE.match(text)
    if m_open is None:
        return text.strip()
    m_close = _FM_CLOSE_RE.search(text, m_open.end())
    if m_close is None:
        return text.strip()
    return text[m_close.end() :].strip()


def _sources_only_swaps(head_front: dict, cur_front: dict) -> list[tuple[str, str, str]]:
    """Same-key non-null `sources` value replacements, IFF that is the only front-matter change.

    [] in every other situation: any other field differing, an entry added or removed
    (missing-path remedies legitimately delete entries), or a null→sha first stamp (no prior
    claim to falsify). This check targets the bulk re-stamp an honest session performs by
    accident, not adversarial evasion."""
    head, cur = dict(head_front), dict(cur_front)
    hs, cs = head.pop("sources", None), cur.pop("sources", None)
    if head != cur:
        return []
    if not isinstance(hs, dict) or not isinstance(cs, dict) or set(hs) != set(cs):
        return []
    swaps = []
    for key in hs:
        old, new = hs[key], cs[key]
        if old == new:
            continue
        if not (isinstance(old, str) and old and isinstance(new, str) and new):
            return []  # null→sha (or a typed value) — not the fraud shape; leave it alone
        swaps.append((str(key), old, new))
    return swaps


def validate_stamps(root: Path, wiki: dict, nodes: list[dict]) -> list[str]:
    """Block a commit whose only change to a node is its `sources` sha (the stamp-fraud
    doc-sync forbids in prose — this is the mechanical half).

    Allowed mechanically: the meaning-preserving migration `new == git rev-parse <old>:<path>`
    (a legacy commit-sha marker rewritten to the blob it pointed at). Everything unanswerable —
    no HEAD, a new file, a rename, any git failure — is skipped (Invariant #1): the check only
    ever fires on an exact, provable "sha changed, nothing else did"."""
    changed = _git(["diff", "HEAD", "--name-only", "--", f"{wiki['root']}/"], root)
    if changed is None:
        return []  # git cannot answer → FAIL-OPEN
    changed_set = set(changed.splitlines())
    problems: list[str] = []
    for node in nodes:
        if not node["id"] or node["path"] not in changed_set:
            continue
        head_text = _git(["show", f"HEAD:{node['path']}"], root)
        if head_text is None:
            continue  # new file / no HEAD → the first stamp is authorship, not fraud
        head_front = parse_front_matter(head_text)
        if head_front is None:
            continue
        swaps = _sources_only_swaps(head_front, node["front"])
        if not swaps:
            continue
        if _split_body(head_text) != _split_body(node.get("text") or ""):
            continue  # the body was edited too → a legitimate sync
        for src, old, new in swaps:
            if _git(["rev-parse", f"{old}:{src}"], root) == new:
                continue  # meaning-preserving migration (spec §2)
            problems.append(
                f"{node['path']}: sources['{src}'] 의 sha 만 갱신되고 본문 변경이 없습니다 — "
                f"본문을 실제 동기화한 커밋에서 함께 찍으세요(본문 수정을 이미 커밋했다면 "
                f"amend). 동기화하지 않았다면 sha 를 되돌리세요"
            )
    return problems
```

`cmd_verify`에서 (authoritative 가드 뒤):

```python
    problems = validate_structure(root, wiki, nodes, graph) + validate_stamps(root, wiki, nodes)
```

- [ ] **Step 4: 통과 확인 + 회귀**

Run: `uv run pytest tests/test_wiki_graph.py -v`
Expected: 전부 PASS (`_git` 는 stdout 을 strip 하므로 `git show` 본문 비교는 `_split_body` 의 `.strip()` 과 맞물려 안전 — 끝 공백만의 차이는 "본문 변경"으로 치지 않는 보수적 방향)

---

### Task 4: `--nodes-for` 역조회 + neighbors docstring

**Files:**
- Modify: `scripts/wiki_graph.py` (`cmd_nodes_for` 신설, argparse, `neighbors` docstring)
- Test: `tests/test_wiki_graph.py`

**Interfaces:**
- Produces: `cmd_nodes_for(root: Path, queries: list[str]) -> int` (항상 0), CLI `--nodes-for PATH...`. 출력 `쿼리경로<TAB>노드id` 줄.
- Consumes: `_load`·`_norm_rel`·`_as_list` (기존).

- [ ] **Step 1: 실패 테스트 작성**

```python
def _nodes_for_repo(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/index.md", "wiki_id: index\ntitle: I\nrelated: [auth.jwt]\n")
    _node(
        tmp_path, "docs/jwt.md",
        "wiki_id: auth.jwt\ntitle: JWT\nsources:\n  src/auth/jwt.py: null\n",
    )
    return tmp_path


def test_nodes_for_exact_match(tmp_path: Path, capsys):
    root = _nodes_for_repo(tmp_path)
    assert wiki_graph.cmd_nodes_for(root, ["src/auth/jwt.py"]) == 0
    assert capsys.readouterr().out.splitlines() == ["src/auth/jwt.py\tauth.jwt"]


def test_nodes_for_directory_prefix_is_segment_bounded(tmp_path: Path, capsys):
    root = _nodes_for_repo(tmp_path)
    assert wiki_graph.cmd_nodes_for(root, ["src/auth", "src/auth-x"]) == 0
    # `src/auth` 는 덮고, 형제 `src/auth-x` 는 안 덮는다 (Invariant #6 과 같은 footgun)
    assert capsys.readouterr().out.splitlines() == ["src/auth\tauth.jwt"]


def test_nodes_for_undocumented_path_is_silent_success(tmp_path: Path, capsys):
    root = _nodes_for_repo(tmp_path)
    assert wiki_graph.cmd_nodes_for(root, ["src/nowhere.py"]) == 0
    assert capsys.readouterr().out == ""   # 미문서화는 정상 답 — --neighbors 의 exit 1 과 다르다


def test_nodes_for_without_wiki_is_noop(tmp_path: Path, capsys):
    assert wiki_graph.cmd_nodes_for(tmp_path, ["src/a.py"]) == 0
    assert capsys.readouterr().out == ""
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_wiki_graph.py -k "nodes_for" -v`
Expected: FAIL (`cmd_nodes_for` 부재 — AttributeError)

- [ ] **Step 3: 구현** — `cmd_neighbors` 아래:

```python
def _covers(source: str, query: str) -> bool:
    """Segment-boundary containment — `src/auth` covers `src/auth/jwt.py`, not `src/auth-x/…`."""
    return source == query or source.startswith(query + "/")


def cmd_nodes_for(root: Path, queries: list[str]) -> int:
    """Print `query<TAB>node id` for every node whose `sources` documents that path (or a file
    under it). The wiki's read entry point for development flow: changed file → owning nodes →
    --neighbors. Lookup only, always exit 0 — an undocumented path is a NORMAL answer (silence),
    unlike --neighbors' unknown id (a caller-side typo, exit 1). No wiki → silent 0."""
    wiki, nodes, _graph, _authoritative = _load(root)
    if wiki is None:
        return 0
    for query in queries:
        norm = _norm_rel(query)
        if not norm:
            continue
        for node in nodes:
            if not node["id"]:
                continue
            sources = node["front"].get("sources")
            keys = sources.keys() if isinstance(sources, dict) else _as_list(sources)
            if any(_covers(_norm_rel(str(k)), norm) for k in keys):
                print(f"{query}\t{node['id']}")
    return 0
```

argparse group에 추가 + 디스패치 (try 안, `--neighbors` 분기 앞):

```python
    group.add_argument(
        "--nodes-for", nargs="+", metavar="PATH", help="경로를 문서화한 노드 조회 (경로<TAB>id)"
    )
```
```python
        if args.nodes_for:
            return cmd_nodes_for(root, args.nodes_for)
```

`neighbors()` docstring 끝에 한 줄 추가:

```python
    Budget semantics are GREEDY: a neighbour that does not fit is cut and expansion continues
    through cheaper ones (the design doc's "stop at budget" reads stricter than what runs —
    this docstring is the authority).
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_wiki_graph.py -k "nodes_for" -v`
Expected: 전부 PASS

---

### Task 5: 게이트 spawn 통합 (main 흡수 + runner 스테이지 2 삭제)

**Files:**
- Modify: `scripts/flow_gate_check.py` (`_wiki_stage` 신설, `main`·`wiki_check_output` 수정)
- Modify: `scripts/precommit-runner.sh` (스테이지 1 흡수·스테이지 2 삭제)
- Modify: `scripts/_harness_paths.py` (RUNTIME_GATES 의 wiki 주석 갱신)
- Test: `tests/test_flow_gate_check.py`

**Interfaces:**
- Produces: `_wiki_stage(root: Path, gates: list[str] | None) -> None` — 차단 시 `sys.exit(BLOCK_EXIT_CODE)`, 경고 시 stdout `systemMessage` JSON. `HARNESS_PRECOMMIT_DRYRUN=1` 이면 무동작. `--wiki-check` alias 존치 (계약 불변).
- Consumes: 기존 `wiki_gate`·`_resolve_context_tier`·`required_gates`.

- [ ] **Step 1: 실패 테스트 작성** — main 통합 경로 (subprocess로 실제 CLI 계약 검증). 기존 runner 테스트들(`test_runner_wiki_step_*`)이 쓰는 픽스처(분류된 tier 마커 + wiki fixture) 준비 방식을 재사용:

```python
def _main_gate(root: Path, env_extra: dict | None = None) -> subprocess.CompletedProcess:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root), **(env_extra or {})}
    return subprocess.run(
        [sys.executable, str(PLUGIN / "scripts" / "flow_gate_check.py")],
        capture_output=True, text=True, env=env,
    )


def test_main_runs_wiki_gate_in_process_and_blocks(tmp_path: Path):
    root = _wiki_drift_fixture(tmp_path)   # 기존 runner 테스트의 drift 준비 재사용/추출
    _classify_docs_tier(root)              # tier 마커 + 정상 policy (기존 헬퍼 재사용)
    r = _main_gate(root)
    assert r.returncode == 2
    assert "graph" in r.stdout             # 사유는 stdout (runner 계약)


def test_main_emits_system_message_on_passing_wiki_warnings(tmp_path: Path):
    root = _wiki_warning_fixture(tmp_path)  # orphan 등 warn-only 상태
    _classify_docs_tier(root)
    r = _main_gate(root)
    assert r.returncode == 0
    assert '"systemMessage"' in r.stdout


def test_main_skips_wiki_under_dryrun(tmp_path: Path):
    root = _wiki_drift_fixture(tmp_path)
    _classify_docs_tier(root)
    r = _main_gate(root, {"HARNESS_PRECOMMIT_DRYRUN": "1"})
    assert r.returncode == 0 and r.stdout == ""


def test_wiki_check_alias_keeps_the_old_contract(tmp_path: Path):
    root = _wiki_drift_fixture(tmp_path)
    _classify_docs_tier(root)
    r = subprocess.run(
        [sys.executable, str(PLUGIN / "scripts" / "flow_gate_check.py"), "--wiki-check"],
        capture_output=True, text=True,
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(root)},
    )
    assert r.returncode == 2 and "graph" in r.stdout
```

(픽스처 함수 3개가 기존 테스트에 인라인으로 있으면 추출해 공유. `_classify_docs_tier` 는 `.flow/tier` 에 `docs:<branch>` 기록 + flow-tiers.yaml 복사 — 기존 테스트 준비 코드에서 그대로.)

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_flow_gate_check.py -k "main_runs_wiki or system_message_on_passing or skips_wiki_under_dryrun or alias_keeps" -v`
Expected: main 3종 FAIL (main 이 wiki 를 안 돈다), alias 는 PASS

- [ ] **Step 3: python 구현** — `wiki_check_output` 을 분해:

```python
def _wiki_stage(root: Path, gates: list[str] | None) -> None:
    """The wiki gate as main()'s final stage — one process for both gates (spawn 2→1).

    Contract unchanged from the old --wiki-check step: block → reason on STDOUT +
    exit BLOCK_EXIT_CODE (stdout-only is load-bearing — `python3 <missing file>` exits 2
    complaining on stderr, and the runner must not read that shape as a verdict); pass with
    warnings → a systemMessage JSON on stdout the runner forwards when it allows the commit.
    HARNESS_PRECOMMIT_DRYRUN=1 skips (the runner's old stage-2 guard, kept behind the env var
    so dry runs never pay the graph walk)."""
    if os.environ.get("HARNESS_PRECOMMIT_DRYRUN") == "1":
        return
    captured = io.StringIO()
    with contextlib.redirect_stderr(captured):
        blocked = wiki_gate(root, gates)
    text = captured.getvalue().strip()
    if blocked:
        if text:
            print(text)
        sys.exit(BLOCK_EXIT_CODE)
    if text:
        print(json.dumps({"systemMessage": f"wiki graph 경고\n{text}"}, ensure_ascii=False))
```

`main()` 의 pass 경로 두 곳을 잇는다 — `gates` 확보 이후의 최종 `sys.exit(0)` 앞:

```python
    miss = missing_gates(flow, gates)
    if miss:
        ...
        sys.exit(BLOCK_EXIT_CODE)
    _wiki_stage(root, gates)
    sys.exit(0)
```

(tier None → exit 0 경로와 gates None → exit 0 경로는 그대로 둔다: 구 `wiki_check_output` 도 그 상황이면 `gates` falsy 로 `wiki_gate` 가 no-op 이었다 — 행동 등가.)

`wiki_check_output` 은 alias 로 축소 (독스트링에 "흡수 후 호환 alias — 반쯤 복사된 호스트의 runner skew 대비" 명시):

```python
def wiki_check_output() -> None:
    force_utf8_io()
    root = host_root()
    try:
        tier, _ = _resolve_context_tier(root, flow_dir(root), _current_branch(root))
        gates = required_gates(tiers_path(root), tier) if tier else None
    except Exception:
        return  # FAIL-OPEN
    _wiki_stage(root, gates)
```

`os` import 확인 (flow_gate_check 상단에 이미 있는지 — 없으면 추가).

- [ ] **Step 4: runner 수정** — 스테이지 1 을 흡수형으로, 스테이지 2 블록(주석 포함) 삭제:

```bash
# 1) flow gate + wiki runtime gate — ONE process. flow_gate_check.py reads the host root from
#    CLAUDE_PROJECT_DIR and FAIL-OPENs (exit 0) on internal error; after the flow verdict it
#    runs the wiki gate in the same interpreter (tier resolved once, spawn 2→1). exit 2 +
#    stdout reason → deny (either gate). At exit 0 a non-empty stdout is the wiki gate's
#    systemMessage JSON, held until the commit is allowed. stdout-only stays load-bearing:
#    `python3 <missing file>` exits 2 complaining on stderr — reading stderr would turn a
#    half-copied install into a repo-wide block. HARNESS_PRECOMMIT_DRYRUN is consumed inside
#    the script (the wiki stage skips itself).
flow_reason="$(CLAUDE_PROJECT_DIR="$ROOT" python3 "$PLUGIN_SCRIPTS/flow_gate_check.py" 2>/dev/null)"
flow_rc=$?
if [ "$flow_rc" -eq 2 ] && [ -n "$flow_reason" ]; then
  deny "$flow_reason"
fi
[ "$flow_rc" -eq 0 ] && wiki_note="$flow_reason"
```

`allow()` 정의·스테이지 3 은 그대로 (번호 주석만 `2)` 로 당긴다). 파일 헤더의 스테이지 목록 주석도 2단 구조로 갱신. **주의**: `HARNESS_PRECOMMIT_DRYRUN` 은 이제 python 이 읽는다 — runner 테스트가 이 변수를 subprocess `env` 로 넘기는지 확인 (shell 로컬 변수면 상속 안 됨).

`_harness_paths.py` RUNTIME_GATES 주석의 wiki 항목을 갱신: "through its OWN --wiki-check step" → "as main()'s in-process final stage (`--wiki-check` remains a compat alias)". 나머지 근거 문장(오류 계약·경고 전달)은 유지.

- [ ] **Step 5: 통과 확인 + 회귀**

Run: `uv run pytest tests/test_flow_gate_check.py -v`
Expected: 신규 4종 PASS. 기존 `test_runner_wiki_step_*` 는 deny JSON/systemMessage 관찰이 동일해 PASS 가 기본 — `--wiki-check` 호출 자체를 단언하는 테스트가 있으면 통합 구조로 기대를 수정.

- [ ] **Step 6: ShellCheck (WSL)**

Run: `wsl shellcheck scripts/precommit-runner.sh`
Expected: 신규 경고 0 (기존 baseline 유지)

---

### Task 6: CI wiki-verify — 템플릿·렌더·도그푸드

**Files:**
- Create: `github/wiki-verify.workflow.example.yml`
- Create: `.github/workflows/wiki-verify.yml`
- Modify: `scripts/flow_init_setup.py` (`render_wiki_verify_workflow` + `run_setup` + `_render_one` label 인자)
- Test: `tests/test_flow_init_setup.py`

**Interfaces:**
- Produces: `render_wiki_verify_workflow(host: Path, plugin: Path) -> list[str]`, 상수 `WIKI_VERIFY_TEMPLATE`·`WIKI_VERIFY_DEST`.
- `_render_one(src, dest, subs, label="versioning 렌더")` — 기존 호출부는 무인자(기본값 유지).

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_render_wiki_verify_workflow_unconditional(tmp_path: Path):
    # flow-config 유무·wiki enable 여부와 무관하게 렌더 — 스크립트가 no-op green 을 보장한다.
    from scripts.flow_init_setup import render_wiki_verify_workflow

    out = render_wiki_verify_workflow(tmp_path, PLUGIN)
    assert any("생성" in line for line in out)
    dest = tmp_path / ".github" / "workflows" / "wiki-verify.yml"
    text = dest.read_text(encoding="utf-8")
    assert "__HARNESS_" not in text
    data = _yaml.safe_load(text)
    assert data["jobs"]["wiki-verify"]["timeout-minutes"] == 5


def test_render_wiki_verify_workflow_preserves_existing(tmp_path: Path):
    from scripts.flow_init_setup import render_wiki_verify_workflow

    dest = tmp_path / ".github" / "workflows" / "wiki-verify.yml"
    dest.parent.mkdir(parents=True)
    dest.write_text("# custom\n", encoding="utf-8")
    out = render_wiki_verify_workflow(tmp_path, PLUGIN)
    assert any("이미" in line for line in out)
    assert dest.read_text(encoding="utf-8") == "# custom\n"


def test_run_setup_renders_wiki_verify(tmp_path: Path, capsys):
    run_setup(tmp_path, PLUGIN)
    assert (tmp_path / ".github" / "workflows" / "wiki-verify.yml").is_file()
    assert "wiki 검증" in capsys.readouterr().out
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_flow_init_setup.py -k "wiki_verify" -v`
Expected: FAIL (ImportError)

- [ ] **Step 3: 템플릿 작성** — `github/wiki-verify.workflow.example.yml`:

```yaml
# harness-tier wiki-verify CI — copied as-is by /flow-init (no config tokens).
# Layer-3 safety net for the LLM Wiki: the layer-2 wiki gate sees only Claude-session commits,
# so graph drift arriving via terminal/direct/CI commits would otherwise surface only at the
# next session commit — here it fails the push/PR instead. Read-only: CI never builds
# graph.yaml (doc-sync and /wiki-init own --build).
# Rendered unconditionally: with no wiki installed (flow-config.wiki absent or enable: false)
# wiki_graph.py --verify exits 0 silently, so the job is green — which keeps /flow-init
# independent of whether /wiki-init has run yet.
name: wiki-verify

on:
  push:
  pull_request:

jobs:
  wiki-verify:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v7
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - name: Install PyYAML
        run: python3 -m pip install pyyaml
      - name: Verify wiki graph
        run: python3 .claude/harness-tier/scripts/wiki_graph.py --verify
```

- [ ] **Step 4: 렌더 구현** — `flow_init_setup.py`: 상수는 `UNIT_TEST_DEST` 옆, 함수는 `render_unit_test_workflow` 옆:

```python
WIKI_VERIFY_TEMPLATE = "github/wiki-verify.workflow.example.yml"  # SOURCE (plugin-owned)
WIKI_VERIFY_DEST = ".github/workflows/wiki-verify.yml"  # host (GitHub-forced — HARNESS_DIR exception)
```

`_render_one` 에 label 인자 추가 (기존 메시지 문자열이 하드코딩이라):

```python
def _render_one(src: Path, dest: Path, subs: dict, label: str = "versioning 렌더") -> list[str]:
    ...
    return [f"  [+] .github/workflows/{dest.name} 생성 ({label})"]
```

```python
def render_wiki_verify_workflow(host: Path, plugin: Path) -> list[str]:
    """Copy wiki-verify.yml as-is — no enable gate, no tokens. Unconditional on purpose:
    without a wiki the script no-ops green, so rendering at /flow-init time removes the
    ordering dependency on /wiki-init (which usually runs later). Idempotent·non-destructive
    (existing dest → report only), same as every other workflow render here."""
    return _render_one(plugin / WIKI_VERIFY_TEMPLATE, host / WIKI_VERIFY_DEST, {}, "wiki-verify 렌더")
```

`run_setup` 에 (유닛 테스트 워크플로우 섹션 뒤):

```python
    print("[wiki 검증 워크플로우]")
    for line in render_wiki_verify_workflow(host, plugin):
        print(line)
```

- [ ] **Step 5: 도그푸드** — `.github/workflows/wiki-verify.yml`. **먼저 `.github/workflows/unit-test.yml`(자체 CI)을 열어 uv 셋업 스텝 관례를 그대로 복사**한 뒤 작성 (아래는 그 관례가 `astral-sh/setup-uv` 일 때의 형태 — 실제 파일의 액션/버전을 따른다):

```yaml
# Dogfood of github/wiki-verify.workflow.example.yml (CLAUDE.md: a workflow-rendering feature
# lands in this repo's OWN CI too). This repo has no host install, so it runs the SOURCE
# script directly; with no flow-config.wiki here the run exercises the no-op-green contract
# consumers without a wiki rely on.
name: wiki-verify

on:
  push:
  pull_request:

jobs:
  wiki-verify:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
      - run: uv sync
      - name: Verify wiki graph
        run: uv run python scripts/wiki_graph.py --verify
```

- [ ] **Step 6: 통과 확인 + 가드 회귀**

Run: `uv run pytest tests/test_flow_init_setup.py -v`
Expected: 신규 3종 PASS + 템플릿 일괄 가드(timeout-minutes 스캔 · `run:` 블록 `${{ }}` 스캔)가 신규 템플릿을 자동 포함해 PASS

---

### Task 7: 스킬·규칙·CLAUDE.md 문서 반영

**Files:**
- Modify: `skills/wiki-init/SKILL.md` (Step 2·4·5·6·8)
- Modify: `skills/doc-sync/SKILL.md` (Mode W 1·3·4·6)
- Modify: `skills/flow/SKILL.md` (Dev 경로)
- Modify: `CLAUDE.md` (검증 레이어 서술)
- Test: `tests/test_skills.py` (자동 — frontmatter·링크 검사)

**Interfaces:** Consumes Task 2 (`migrated`·hash-object 도장), Task 3 (기계 검증 존재), Task 4 (`--nodes-for`), Task 5 (통합 구조), Task 6 (wiki-verify). 코드 없음 — 각 편집의 핵심 문구를 아래에 고정한다 (정확한 주변 문장은 파일에서 맞춘다).

- [ ] **Step 1: wiki-init Step 2·4 — H2 휴리스틱 완화.** Step 2의 "**A file with a high line count and multiple H2s is a file holding multiple concepts.**" 를:

> A high line count with multiple H2s is a **signal** of multiple concepts, not a verdict — an Installation/Usage/FAQ page is several H2s and still one concept. Judge the boundary by content in Step 4.

Step 4의 "Two or more H2s" 분기 서두에: "split **only the H2s that are separate concepts** — a structural section (usage, FAQ) stays with its concept."

- [ ] **Step 2: wiki-init Step 5 — collision 문구 축소 + rename 규칙.** "The order inside the rule is what makes it collision-free …" 문단을:

> The order inside the rule is what keeps `docs/a.b.md` (→ `a-b`) distinct from `docs/a/b.md` (→ `a.b`) — sanitize each segment **before** joining. It is **not** collision-free across siblings: `a.b.md`, `a-b.md` and `a_b.md` in one directory all derive `a-b`. `--verify` reports the duplicate; the remedy is renaming one file.
>
> `wiki_id` is immutable once assigned: moving or renaming the file does **not** re-derive it — the id is what keeps links stable. Derivation is for first assignment only.

- [ ] **Step 3: wiki-init Step 6 — orphan 의미 복원.** 현행 "carrying **every** node id in the wiki … / body 링크 상호 동기화" 문단을 다음 취지로 재작성:

> Give it front matter with its own `wiki_id` (conventionally `index`) and a `related:` list of the **top-level entry nodes** — the concepts a reader (or the graph walk) starts from. Every other node must be reachable from the index through real edges: link it (`related`/`depends_on`) to the nodes it actually belongs with, not to the index. An orphan warning therefore means "this node is connected to nothing that matters" — fix it by wiring the node to its related concepts, or to the index only when it genuinely is a top-level entry. Reachability reads front-matter edges only, direction ignored; markdown links in the body never count (design §3). The body's link list is for people — keep it useful, but it is not the graph and needs no 1:1 sync with `related:`.

- [ ] **Step 4: wiki-init Step 8 — graph.yaml 충돌 안내.** Step 8 말미에 단락 추가:

> **Merge conflicts in `graph.yaml` are never resolved by hand** — it is a generated file, so hand-merged markers survive as either broken YAML or a graph that `--verify` rejects as drift. Take either side (`git checkout --ours -- <root>/graph/graph.yaml` or `--theirs`), re-run `--build`, and stage the rebuilt file with the documents. (No merge driver on purpose: an automatic `ours` would silently pass the wrong graph along to the next `--verify` block; a conflict forces the rebuild now.)

- [ ] **Step 5: doc-sync Mode W 갱신.** ① 1단계: `--stale` 항목의 `recorded`/`current` 가 blob hash 임을 명시하고 `migrated` 처리 추가:

> An entry with a `migrated` key carries a legacy commit-sha marker: rewrite `sources[path]` to the `migrated` value — it is the meaning-preserving conversion (`git rev-parse <old>:<path>`), so no re-reading is needed and the verify gate accepts it without a body edit. If `migrated` equals `current` that rewrite is the whole fix; if it differs (or is `null`), the node is also genuinely stale — sync the body, then stamp. `"missing": true` handling is unchanged.

② 3단계: 도장 값 명시 + 기계 검증 언급:

> Stamp with the file's **working-tree blob hash** — the output of `git hash-object -- <path>` (what you just read), never a commit sha. The verify gate now enforces the discipline mechanically: a commit whose only change to a node is its `sources` sha is **blocked** (the `migrated` rewrite above is the one allowed exception), so a bulk refresh does not merely violate prose — it fails.

③ 4단계의 "**Add the new id to the index node's `related:` list**" 지시를:

> **Wire the new node to the nodes it belongs with** (`related`/`depends_on` on either side) so it is reachable from the index through real edges; add it to the index's `related:` only when it is a genuine top-level entry ([wiki-init](../wiki-init/SKILL.md) Step 6).

④ 6단계 말미: Task 7 Step 4와 같은 충돌 단락 요약 1문장 + wiki-init Step 8 링크.

- [ ] **Step 6: flow SKILL Dev 경로 — 읽기 단계 신설.** "### Dev — any code" 목록의 현행 1을 2로 밀고 새 1:

> 1. **Load the wiki context first** (skip silently when there is no wiki — both commands print nothing and exit 0): name the files you are about to change to
>    `python3 .claude/harness-tier/scripts/wiki_graph.py --nodes-for <paths…>`, then for each printed id run `… --neighbors <id>` and **read the documents it lists** before planning. An empty result is a normal answer (the code is undocumented) — proceed without it.

이후 항목 번호 2·3·4 로 재조정.

- [ ] **Step 7: CLAUDE.md 검증 레이어 서술 갱신.** 레이어 2의 "The `wiki` runtime gate runs in its **own** `--wiki-check` step (not the module-command channel — …)" 문장을:

> The `wiki` runtime gate runs **in-process as the flow gate's final stage** (one spawn; `--wiki-check` remains a compat alias) — never through the module-command channel, whose "any nonzero exit = failure" contract would make an internal error block every commit.

레이어 3 문장 "renders `api-contract.yml` + `unit-test.yml`" 에 `+ wiki-verify.yml (read-only graph verify — closes the wiki gate's terminal/merge blind spot)` 추가. `rules/` 에도 stale/`--wiki-check` 표현이 있으면 같은 취지로 손본다: `Grep "wiki" rules/` 로 확인.

- [ ] **Step 8: 검사**

Run: `uv run pytest tests/test_skills.py tests/test_evals.py -v`
Expected: PASS (링크·frontmatter·구조). FAIL 시 해당 링크/표기 수정.

---

### Task 8: 종합 검증 + 게이트 + 커밋

**Files:** 없음 (검증·기록만)

- [ ] **Step 1: 전체 테스트·린트**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check`
Expected: 전부 PASS. format 위반은 `uv run ruff format` 후 재확인.

- [ ] **Step 2: ShellCheck 재확인 (WSL)** — `wsl shellcheck scripts/precommit-runner.sh`

- [ ] **Step 3: evals outcome 재측정** — SKILL.md 본문 변경으로 `outcome_sha` 가 바뀐 스킬만:

Run: `uv run python -m evals.outcome`
Expected: doc-sync·wiki-init (·flow 가 시나리오 보유 시) 재측정 → `evals/outcome_scores.json` 갱신. 점수 하락 시 원인(스킬 문구가 시나리오 golden 과 어긋남)을 고치고 재실행. 모델 호출 비용 발생 — 실행 전 사용자에게 고지.

- [ ] **Step 4: vdev 게이트** — 독립 review 에이전트(체크리스트: 회귀·계약·게이트 계약 위반) 통과 → `review.done`; `doc-sync` 스킬 실행(이번 변경의 README/USAGE·한국어 쌍둥이 조화 포함) 통과 → `doc-sync.done`. 마커는 `.claude/vway-kit/.vdev/` (이 저장소의 게이트 경로).

- [ ] **Step 5: 단일 feat 커밋** — spec·plan·구현·테스트·워크플로 전부 한 커밋. 메시지는 산문체 (사용자 규율):

```
feat(wiki): open a read path and harden stale, stamps, and the gate

The wiki gains its first consumer: --nodes-for maps changing code paths
to the nodes documenting them, and /flow's Dev path now loads that
context before planning. Staleness switches from last-commit shas to
working-tree blob hashes, so squash/rebase promotions can no longer fake
drift; --stale offers a meaning-preserving migration value for legacy
markers, and --verify mechanically blocks a sha stamp that arrives
without its body edit. The wiki gate now runs in-process as the flow
gate's final stage (one spawn; --wiki-check stays as an alias), a
rendered wiki-verify workflow closes the terminal/merge blind spot in
CI, the front-matter parser stops closing blocks on ruler lines, and
wiki-init/doc-sync drop the index-lists-every-node rule so orphan
detection measures real connectivity again.
```

---

## Self-Review 결과 (계획 검수)

- Spec §1→Task 4·7, §2→Task 2·7, §3→Task 3, §4→Task 6, §5→Task 7, §6→Task 7, §7→Task 1, §8→Task 5, §9→Task 4(독스트링)·7, §10→각 태스크 내장, §11→Task 8. 공백 없음.
- 타입/시그니처: `validate_stamps(root, wiki, nodes)` — cmd_verify 호출부와 일치. `_render_one` label 기본값으로 기존 호출 무영향. node dict `text`/`dup_marker` 는 `.get` 소비.
- 실행 순서: Task 1 → 3 (정규식·`text` 의존), Task 2 → 3 (마이그레이션 의미), 나머지 병행 가능. 문서(Task 7)는 코드 태스크 뒤.
