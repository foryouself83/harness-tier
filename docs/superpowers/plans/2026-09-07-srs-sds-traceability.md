# SRS·SDS 추적성 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** SDS·SRS 문서가 `--stale`·`--nodes-for`·`/flow` Dev 진입·FR 앵커 검증 네 경로에서 조용히 빠지는 것을 막는다.

**Architecture:** 저작 시점에 `sources`를 강제하지 않는다. 대신 (1) wiki가 붙은 뒤 `sds` 노드의 `sources` 누락을 경고로 표면화하고, (2) 그 경고의 수리 책임을 `doc-sync`에 명시하고, (3) wiki가 답을 못 줄 때 `/flow` Dev가 `docs/sds/README.md`를 직접 읽고, (4) `validate_plan`이 `#fragment`까지 검증한다.

**Tech Stack:** Python 3.8+ · PyYAML · pytest · uv

**Spec:** [docs/superpowers/specs/2026-09-07-srs-sds-traceability-design.md](../specs/2026-09-07-srs-sds-traceability-design.md)

## 개정 (2026-09-07, 도메인 리뷰 4회 후)

**Task 1·2·3 의 코드 블록과 문구 지시는 낡았다 — 배포된 코드를 읽어라.** 바뀐 결정:

- 경고 조건: "`sources` 비어 있음" → "키가 없거나 값이 없음". 템플릿이 `sources: {}` 를
  싣고, 그것은 침묵한다.
- `_slugify` 는 github-slugger 를 따른다: `_` 보존, 공백 개별 치환, 태그·완전 엔티티만 제거.
- 앵커 대상은 **디스크 우선** — `apply_plan` 의 `create` 는 기존 파일을 덮어쓰지 않는다.
- `tech-doc-guide.md` 가 brownfield SDS 의 `sources` 저작을 지시한다.

## Global Constraints

- 저장소 산문은 **영어** — 주석·docstring·테스트 assertion 메시지. 한국어는 코드가 **출력하는** 문자열과 그 문자열을 비교하는 테스트 기대값에만 남는다 (CLAUDE.md Conventions).
- 게이트 출력 문자열은 한국어 — `wiki_graph.py`의 기존 경고들과 같은 어투를 따른다.
- 새 경고·새 issue는 전부 **비차단**. `collect_warnings`는 원래 비차단이고, `validate_plan`의 새 issue는 `severity: "warn"` (기존 `dead-link`과 동급).
- 새 스크립트 파일을 만들지 않는다. `scripts/` 파일 목록은 `flow_init_setup.py` COPY_FILES와 묶여 있다.
- 테스트 파일 500줄 상한 — 초과하면 폴더로 쪼갠다. 이번 작업은 기존 파일에 추가만 한다.
- 커밋 타입은 `feat` — 소비자 배포 `.md`+`scripts/`를 바꾸므로 `docs`·`chore`는 전파되지 않는다.
- 검증 명령은 `uv run pytest`, 린트는 `uv run ruff check && uv run ruff format --check`.

---

### Task 1: `sds` 노드 `sources` 누락 경고

**Files:**
- Modify: `scripts/wiki_graph.py` — 상수 1개 추가(`DEFECT_PREFIX` 근처), `collect_warnings()` 에 체크 1개 추가
- Test: `tests/wiki_graph/test_warnings.py`

**Interfaces:**
- Consumes: 기존 `collect_warnings(wiki, nodes, graph, root=None)` · `_capped(warns, items, label)` · `_as_list(value)`
- Produces: 모듈 상수 `CODE_BEARING_TAG = "sds"` (Task 3의 산문이 이 태그를 참조한다)

- [ ] **Step 1: 실패하는 테스트 4개를 작성한다**

`tests/wiki_graph/test_warnings.py` 끝에 추가:

```python
def _sources_warns(nodes):
    """Only this warning. Matching on 'sds' alone would also catch the orphan line, which
    names the same path — every quiet assertion below would then pass on the wrong warning."""
    return [
        w
        for w in collect_warnings(_wiki(), nodes, build_graph(nodes))
        if "sds 문서인데" in w
    ]


def test_sds_node_without_sources_warns():
    nodes = [_mk("index", path="docs/index.md"), _mk("sds.readme", {"tags": ["sds"]}, "docs/sds/README.md")]
    assert any("docs/sds/README.md" in w for w in _sources_warns(nodes))


def test_sds_node_with_empty_sources_warns():
    # `sources: {}` is a dict, so an isinstance-only test would call this node documented.
    node = _mk("sds.readme", {"tags": ["sds"], "sources": {}}, "docs/sds/README.md")
    assert any("docs/sds/README.md" in w for w in _sources_warns([node]))


def test_sds_node_with_sources_is_quiet():
    node = _mk("sds.readme", {"tags": ["sds"], "sources": {"src/a.py": None}}, "docs/sds/README.md")
    assert _sources_warns([node]) == []


def test_non_sds_node_without_sources_is_quiet():
    # The whole point of the tag narrowing: requirements and onboarding pages map to no code
    # path, and warning on them is the permanent noise that makes the block unread.
    node = _mk("srs.readme", {"tags": ["srs"]}, "docs/srs/README.md")
    assert _sources_warns([node]) == []
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/wiki_graph/test_warnings.py -k sds -v`
Expected: `test_sds_node_without_sources_warns`·`test_sds_node_with_empty_sources_warns` 가 FAIL (경고가 안 나옴). 나머지 둘은 이미 PASS — 아직 아무 경고도 없으므로. 실패 2건을 확인하는 것이 이 단계의 목적이다.

- [ ] **Step 3: 상수를 추가한다**

`scripts/wiki_graph.py`, `DEFECT_PREFIX` 정의 바로 아래:

```python
# The one doc kind whose whole subject is code. A node tagged this way with no `sources` is
# invisible to --stale and --nodes-for at once, and nothing else reports it. Deliberately not
# generalized to every node: an onboarding page or an SRS maps to no code path legitimately,
# and warning on those is the permanent noise that makes the whole warning block unread.
CODE_BEARING_TAG = "sds"
```

- [ ] **Step 4: 체크를 추가한다**

`collect_warnings()` 안, `if root is not None:` 블록 **바로 앞**에 (root 를 안 쓰므로 그 밖에 둔다):

```python
    _capped(
        warns,
        [
            f"{node['path']}: sds 문서인데 sources 가 없습니다 — 이 설계가 기술하는 코드 "
            f"경로를 적으세요. 비어 있는 동안 --stale 도 --nodes-for 도 이 노드를 보지 못합니다"
            for node in nodes
            if node["id"]
            and CODE_BEARING_TAG in _as_list(node["front"].get("tags"))
            and not (
                isinstance(node["front"].get("sources"), dict) and node["front"]["sources"]
            )
        ],
        "sources 없는 sds 문서",
    )
```

- [ ] **Step 5: 통과를 확인한다**

Run: `uv run pytest tests/wiki_graph/ -v`
Expected: 전부 PASS. 기존 테스트가 깨지면 그 테스트의 노드가 `sds` 태그를 달고 있다는 뜻이니, 깨진 테스트를 읽고 의도를 확인한 뒤 판단한다.

- [ ] **Step 6: 뮤테이션으로 테스트가 실제로 무는지 확인한다**

`CODE_BEARING_TAG = "sds"` 를 `"sds-nonexistent"` 로 바꾸고 `uv run pytest tests/wiki_graph/test_warnings.py -k sds` 실행 → 2건 FAIL 해야 한다. 되돌리기는 **`git checkout --` 을 쓰지 않는다** — 이 트리는 커밋 전 작업물을 담고 있어 그 명령이 변경을 통째로 지운다 (CLAUDE.md: 이미 깨끗한 트리에서만). Python 으로 읽어-바꿔-쓰되 `assert old in text` 로 뮤테이션이 실제로 적용됐는지 먼저 확인하고, 되돌린 뒤 md5 로 바이트 동일함을 확인한다.

---

### Task 2: `validate_plan` 앵커 검증

**Files:**
- Modify: `scripts/harness_scaffold.py` — 정규식 1개 수정, 헬퍼 3개 추가, 링크 루프 확장
- Test: `tests/harness_scaffold/test_validate_links.py`

**Interfaces:**
- Consumes: 기존 `_MD_LINK_RE` · `_norm_rel(path)` · `_strip_code(text)` · `_strip_frontmatter(text)` · `validate_plan(root, plan)` · `plan_paths`
- Produces: `_slugify(text) -> str` · `_has_anchor(text, frag) -> bool` · issue `kind: "dead-anchor"`, `severity: "warn"`

- [ ] **Step 1: 실패하는 테스트를 작성한다**

`tests/harness_scaffold/test_validate_links.py` 끝에 추가:

```python
def _linking_plan(target_content, link):
    return {
        "files": [
            _baseline_entry(),
            {"path": "docs/sds/README.md", "action": "create", "content": f"[FR]({link})"},
            {"path": "docs/srs/README.md", "action": "create", "content": target_content},
        ]
    }


def _anchor_issues(tmp_path, target_content, link):
    rep = hs.validate_plan(tmp_path, _linking_plan(target_content, link))
    return [i for i in rep["issues"] if i["kind"] == "dead-anchor"]


def test_dead_anchor_warns(tmp_path):
    hits = _anchor_issues(tmp_path, '<a id="fr-001"></a>FR-001\n', "../srs/README.md#fr-999")
    assert len(hits) == 1 and hits[0]["severity"] == "warn"


def test_explicit_anchor_resolves(tmp_path):
    assert _anchor_issues(tmp_path, '<a id="fr-001"></a>FR-001\n', "../srs/README.md#fr-001") == []


def test_heading_slug_resolves(tmp_path):
    # An <a id> lookup alone would flag every heading link in this repo's own docs.
    assert _anchor_issues(tmp_path, "## Requirements Coverage\n", "../srs/README.md#requirements-coverage") == []


def test_hangul_heading_slug_resolves(tmp_path):
    # GitHub keeps unicode letters in a slug; an ASCII-only strip makes every Korean
    # heading link a false positive.
    assert _anchor_issues(tmp_path, "## 요구 추적\n", "../srs/README.md#요구-추적") == []


def test_link_without_fragment_is_not_checked(tmp_path):
    assert _anchor_issues(tmp_path, "no anchors here\n", "../srs/README.md") == []


def test_anchor_check_skips_an_unresolvable_target(tmp_path):
    # A target that is neither in the plan nor on disk is already a dead-link; adding a
    # second issue for the same cause is noise.
    plan = {
        "files": [
            _baseline_entry(),
            {"path": "docs/sds/README.md", "action": "create", "content": "[FR](../nope/README.md#fr-001)"},
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert not [i for i in rep["issues"] if i["kind"] == "dead-anchor"]


def test_slugify_strips_inline_markup():
    assert hs._slugify("`code` and **bold**") == "code-and-bold"


def test_slugify_unwraps_a_link():
    assert hs._slugify("[FR-001](../srs/README.md) 매핑") == "fr-001-매핑"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/harness_scaffold/test_validate_links.py -k "anchor or slug" -v`
Expected: `test_dead_anchor_warns`·`test_slugify_strips_inline_markup`·`test_slugify_unwraps_a_link` 가 FAIL (`_slugify` 미정의 / `dead-anchor` issue 없음).

- [ ] **Step 3: 정규식이 fragment 를 캡처하게 바꾼다**

`scripts/harness_scaffold.py`, `_MD_LINK_RE` 를 교체 — `(?:#[^)\s]*)?` 를 캡처 그룹으로:

```python
_MD_LINK_RE = re.compile(
    r"(?<!!)\[[^\]]*\]\(\s*([^)\s#]+\.md)(?:#([^)\s]*))?(?:\s+[\"'][^\")]*[\"'])?\s*\)"
)
```

`findall` 이 이제 2-튜플을 낸다 — 기존 루프의 `for link in ...` 를 반드시 Step 5 에서 함께 고쳐야 한다. 이 단계만 하고 테스트를 돌리면 기존 dead-link 테스트가 깨진다(정상).

- [ ] **Step 4: 슬러그·앵커 헬퍼를 추가한다**

`_MD_LINK_RE` 정의 아래:

```python
_EXPLICIT_ANCHOR_RE = re.compile(r"<a\s+[^>]*id=[\"']([^\"']+)[\"']", re.IGNORECASE)
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)
_MD_INLINE_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
_SLUG_DROP_RE = re.compile(r"[^\w\s-]", re.UNICODE)


def _slugify(text: str) -> str:
    """GitHub's heading slug: unwrap inline markup, lowercase, drop punctuation, spaces→'-'.

    `\\w` under re.UNICODE keeps Hangul and every other letter, which is what GitHub does.
    An ASCII-only strip would turn every Korean heading link into a dead-anchor report.
    """
    text = _MD_INLINE_LINK_RE.sub(r"\1", text)
    text = text.replace("`", "").replace("*", "").replace("_", "")
    return re.sub(r"\s+", "-", _SLUG_DROP_RE.sub("", text.strip().lower()))


def _has_anchor(text: str, frag: str) -> bool:
    """True when `frag` names an explicit <a id> or a heading in `text`."""
    if frag in _EXPLICIT_ANCHOR_RE.findall(text):
        return True
    low = frag.lower()
    return any(_slugify(h) == low for h in _HEADING_RE.findall(text))
```

`_slugify` 는 `_` 를 지운 **뒤** `_SLUG_DROP_RE` 를 태운다. `\w` 가 `_` 를 포함하므로 순서를 뒤집으면 언더스코어가 살아남아 GitHub 와 어긋난다.

- [ ] **Step 5: 링크 루프를 확장한다**

먼저 루프 위쪽, `plan_paths` 정의 옆에 content 맵을 만든다:

```python
    # `marker_upsert` content is a fragment that `apply` wraps into an existing file, not the
    # file itself — searching it for an anchor would miss every anchor outside the marker and
    # report a live link as dead. Those targets fall through to the on-disk read below.
    plan_contents = {
        _norm_rel(e.get("path", "")): e.get("content", "")
        for e in files
        if e.get("action") != "marker_upsert"
    }
```

그리고 링크 루프를 다음으로 교체한다 (`for link in ...` → 2-튜플 언팩):

```python
        for link, frag in _MD_LINK_RE.findall(_strip_code(_strip_frontmatter(content))):
            if link.startswith(("http://", "https://", "/")) or _WIN_ABS_RE.match(link):
                continue
            target = _norm_rel(str(Path(rel).parent / link))
            if target.startswith(".."):
                continue
            if target not in plan_paths and not (root / target).exists():
                issues.append(
                    {
                        "severity": "warn",
                        "kind": "dead-link",
                        "path": rel,
                        "detail": f"링크 대상 없음: {link}",
                    }
                )
                continue
            if not frag:
                continue
            target_text = plan_contents.get(target)
            if target_text is None:
                try:
                    target_text = (root / target).read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue  # unreadable target — the anchor question has no answer
            if not _has_anchor(target_text, frag):
                issues.append(
                    {
                        "severity": "warn",
                        "kind": "dead-anchor",
                        "path": rel,
                        "detail": f"앵커 대상 없음: {link}#{frag}",
                    }
                )
```

기존 코드의 `if target in plan_paths or (root / target).exists(): continue` 를 뒤집어 `continue` 를 dead-link 쪽으로 옮긴 것이다 — 대상이 **있을** 때만 앵커를 마저 봐야 하기 때문이다. 대상이 없으면 dead-link 하나로 끝낸다(같은 원인에 issue 두 개를 달지 않는다).

- [ ] **Step 6: 통과를 확인한다**

Run: `uv run pytest tests/harness_scaffold/ -v`
Expected: 전부 PASS. 특히 기존 dead-link 테스트들이 살아 있어야 한다 — Step 3 의 튜플 변경이 그것들을 깨뜨리는 지점이다.

- [ ] **Step 7: 저장소 자체 문서로 오탐을 확인한다**

Run:
```bash
uv run python -c "
import scripts.harness_scaffold as hs, pathlib
p = pathlib.Path('.')
for f in ['skills/harness-authoring/templates/sds.template.md', 'CLAUDE.md', 'rules/risk-tiers.md']:
    t = (p/f).read_text(encoding='utf-8')
    for link, frag in hs._MD_LINK_RE.findall(hs._strip_code(hs._strip_frontmatter(t))):
        if not frag: continue
        tgt = p / hs._norm_rel(str(pathlib.Path(f).parent / link))
        if not tgt.exists(): continue
        if not hs._has_anchor(tgt.read_text(encoding='utf-8'), frag):
            print(f, '->', link + '#' + frag)
"
```
Expected: 출력이 비거나, 나온 항목이 **진짜 죽은 앵커**여야 한다. 살아 있는 앵커가 잡히면 `_slugify` 가 GitHub 과 어긋난 것이므로 고친다. 이 단계를 건너뛰면 오탐을 소비자에게 배포하게 된다.

- [ ] **Step 8: 뮤테이션으로 확인한다**

`_has_anchor` 의 `return True` 를 `return False` 로 바꾸고 `uv run pytest tests/harness_scaffold/test_validate_links.py -k anchor` → `test_explicit_anchor_resolves` FAIL. Task 1 Step 6 과 같은 방식으로 되돌린다 — `git checkout --` 금지.

---

### Task 3: doc-sync backfill 책임 + 템플릿 정정

**Files:**
- Modify: `skills/doc-sync/SKILL.md` — Mode W 에 backfill 단계 추가
- Modify: `skills/harness-authoring/templates/sds.template.md` — `sources` 주석 교체
- Test: `tests/skills/` (기존 링크·언어 검사가 자동 적용 — 새 테스트 없음)

**Interfaces:**
- Consumes: Task 1 의 경고 문자열 `"sources 없는 sds 문서"` (doc-sync 산문이 이 경고를 지목한다)
- Produces: 없음 (산문 변경)

- [ ] **Step 1: `sds.template.md` 의 `sources` 주석을 교체한다**

현재 13-16행:

```markdown
# sources is optional — uncomment and list real code paths this design describes; delete
# these two lines entirely if none apply.
# sources:
#   src/path/to/code.py: null
```

교체:

```markdown
# sources: the code paths this design describes. Leave it out here — at authoring time the
# code may not exist yet, and a guessed path is worse than an absent one. `/wiki-init` assigns
# it when a wiki is installed and `doc-sync` keeps it current; until then this doc is outside
# stale tracking, which `--verify` reports rather than leaving silent.
```

주석이 `sources:` 예시 줄을 더 이상 담지 않는다 — 저작자가 채우는 필드가 아니기 때문이다.

- [ ] **Step 2: `doc-sync` Mode W 에 backfill 단계를 추가한다**

`skills/doc-sync/SKILL.md` Mode W 의 4번 단계(신규 `.md` front matter 부여) **뒤**, 5번(max_lines 분할) **앞**에 새 단계를 넣고 이후 번호를 하나씩 민다:

```markdown
5. **Backfill the `sources` a node never got**. `--verify` reports `sds` documents with an
   empty `sources`; step 4 does not reach them, because it only touches documents this change
   created. Read the SDS's Module Overview and record the real code paths each module names,
   with `sha` left `null` — `--stale` then reports the node, and the next body sync stamps it
   through step 3's ordinary path. Nothing else fills these: `/wiki-init` assigns `sources`
   once at migration, so a document it did not cover, or one added later by
   `/harness-init`, stays outside stale tracking forever. A module whose code genuinely does
   not exist yet (a greenfield design) is left alone and named in the Report — an invented
   path is what this exists to prevent.
```

- [ ] **Step 3: 이후 단계 번호를 민다**

같은 파일 Mode W 의 기존 5번(`max_lines` 분할) → 6번, 기존 6번(`--build`/`--verify`) → 7번. 본문 안에서 "Steps 4-5" 처럼 번호를 참조하는 문구가 있는지 `grep -n "Step" skills/doc-sync/SKILL.md` 로 확인하고 함께 고친다.

- [ ] **Step 4: 테스트를 돌린다**

Run: `uv run pytest tests/skills/ -v`
Expected: PASS. 링크·언어 규약 검사가 새 산문에 자동 적용된다.

- [ ] **Step 5: 산문 린트를 돌린다**

Run: `uv run python scripts/doc_style_check.py --lint skills/doc-sync/SKILL.md skills/harness-authoring/templates/sds.template.md`
Expected: 새로 추가한 줄에 ERROR 가 없어야 한다. 기존 줄의 지적은 이번 작업 범위 밖이다.

---

### Task 4: `/flow` Dev 진입 SDS fallback

**Files:**
- Modify: `skills/flow/SKILL.md` — Dev dispatch step 1
- Test: `tests/skills/` (기존 검사 자동 적용 — 새 테스트 없음)

**Interfaces:**
- Consumes: 없음
- Produces: 없음 (산문 변경)

- [ ] **Step 1: Dev step 1 에 fallback 을 추가한다**

`skills/flow/SKILL.md` Dev dispatch 의 1번 단계 끝(“An empty result is a normal answer (the code is undocumented) — proceed without it.” 다음)에 이어 붙인다:

```markdown
   When that produces nothing — no wiki, or no node owns the paths — read
   `docs/sds/README.md` directly if it exists, and `docs/srs/README.md` alongside it. The
   graph is the better route because it answers *which* documents bear on these paths;
   this branch runs only where it gave no answer, and `docs/sds/` is a fixed location
   ([`harness-rules.md`](../../rules/harness-rules.md) 8), not a guess. Neither file
   existing is the normal state of a project without generated docs — proceed. **Docs tier
   does not do this**: reading a whole design document to change a paragraph is the
   process-to-risk mismatch the tiers exist to prevent.
```

- [ ] **Step 2: Docs 분기가 오염되지 않았는지 확인한다**

Run: `grep -n "docs/sds" skills/flow/SKILL.md`
Expected: 새 문구 1곳만. `### Docs — no code` 섹션 안에는 없어야 한다.

- [ ] **Step 3: 테스트와 린트를 돌린다**

Run: `uv run pytest tests/skills/ -v && uv run python scripts/doc_style_check.py --lint skills/flow/SKILL.md`
Expected: PASS, 새 줄에 ERROR 없음.

---

### Task 5: 전체 검증

**Files:** 없음 (검증 전용)

- [ ] **Step 1: 전체 테스트**

Run: `uv run pytest`
Expected: 전부 PASS.

- [ ] **Step 2: 린트·포맷**

Run: `uv run ruff check && uv run ruff format --check`
Expected: 통과.

- [ ] **Step 3: 정적 분석 전체**

Run: `uv run pre-commit run --all-files`
Expected: 통과. ShellCheck 대상 `.sh` 는 이번 작업에서 건드리지 않는다.

- [ ] **Step 4: 스펙 대조**

스펙 §1·§2·§3·§4 를 각각 Task 1·3·4·2 가 덮는지 확인하고, 스펙이 **범위 밖**으로 명시한 것(SRS `sources`, 역방향 FR 미매핑 검출, 신규 스크립트, 차단화)이 들어가지 않았는지 `git diff` 로 확인한다.
