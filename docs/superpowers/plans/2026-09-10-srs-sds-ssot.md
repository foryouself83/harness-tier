# SRS/SDS SSOT 승격 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 요구·설계 텍스트의 정본을 repo 문서로 못박고, 그 정본이 `/flow` Dev 티어에서 증분으로 갱신되는 경로를 만든다.

**Architecture:** SRS 를 `README.md`(공통 절) + `<영역>.md`(§5 기능요구)로 나누고, 번호 발급·무결성 검사를 `scripts/srs_check.py` 가 맡는다. 이 스크립트는 `harness_scaffold.py` 에서 뽑아낸 `scripts/_md_anchors.py` 의 앵커 해석기를 재사용한다. 커밋 게이트는 손대지 않고(FAIL-OPEN), 판정은 새 `srs-verify` CI 워크플로가 한다.

**Tech Stack:** Python 3.8+ (stdlib `re`·`argparse`·`pathlib` 만) · pytest · uv · GitHub Actions

**Spec:** [`docs/superpowers/specs/2026-09-10-srs-sds-ssot-design.md`](../specs/2026-09-10-srs-sds-ssot-design.md)

## Global Constraints

- **저장소 언어는 영어** — 문서 · 커밋 메시지 · 주석/docstring · 테스트 단언 메시지. 한국어는 저장소가 *저작*하지 않고 *인용*하는 곳에만 남는다: 게이트/CLI 출력, 그 출력과 비교하는 테스트의 기대 문자열. 예외: `docs/superpowers/specs/`·`plans/` 는 한국어.
- **`scripts/*.py` 는 산문 린트 대상** — `uv run python scripts/doc_style_check.py --root . --lint <파일>` 통과. 주석/docstring 은 코드가 말할 수 없는 것만 쓴다.
- **커밋 본문에도 같은 규율** — 변경 이력·마이그레이션 노트·before/after 서술 금지.
- **문서는 400줄 이하** — 이 작업이 만들거나 고치는 모든 `.md`.
- **테스트 파일이 500줄을 넘으면 폴더** — `tests/<대상>/`, 안의 각 파일도 500줄 미만, `__init__.py` 필수.
- **CRLF 주의** — 개발 호스트는 Windows(`core.autocrlf=true`, `.gitattributes` 없음)라 추적 파일은 워크트리에서 CRLF, blob 에서 LF. 추적 파일의 raw 바이트를 다이제스트하지 말 것.
- **`wiki_graph.py` 를 수정하지 말 것** — outcome eval 의 `copy_from_repo` 소스라 한 바이트만 바뀌어도 생측정을 문다.
- **`rules/risk-tiers.md` 를 수정하지 말 것** — 주입되는 유일한 룰이라 바이트가 eval 입력이고, `hook_assisted` 4개 스킬의 생측정을 문다.
- **스킬의 `description` frontmatter 를 수정하지 말 것** — invocation eval 재측정 비용.
- **`.sh` 를 고치면 WSL 에서 ShellCheck** — 워크트리가 CRLF라 Windows 에서 돌리면 CR 오류가 수백 줄 먼저 난다. 이 계획은 `.sh` 를 건드리지 않는다.
- 전체 테스트: `uv run pytest`. 린트: `uv run ruff check && uv run ruff format --check`.

---

### Task 1: `scripts/_md_anchors.py` 추출

`harness_scaffold.py` 의 마크다운 앵커 해석기를 자체 모듈로 옮긴다. **순수 이동이다** — 동작이 한 줄도 바뀌면 안 된다. 이걸 먼저 하는 이유는 `srs_check.py` 가 이 모듈에 의존하고, `COPY_FILES` 가 flat 복사(`dest_dir / Path(rel).name`)라 호스트에 `harness_scaffold.py` 가 없으면 `ImportError` 로 조용히 죽기 때문이다.

**Files:**
- Create: `scripts/_md_anchors.py`
- Modify: `scripts/harness_scaffold.py` (상수 686-712 · 함수 718-753 · 756-757 · 818-826 제거, import 추가, 미사용 import 제거)
- Test: `tests/harness_scaffold/test_validate_links.py` (기존, 무수정 통과) · `tests/md_anchors/test_extraction.py` (신규)

**Interfaces:**
- Consumes: 없음
- Produces: `scripts/_md_anchors.py` 가 `_slugify(text: str) -> str`, `_has_anchor(text: str, frag: str) -> bool`, `_strip_frontmatter(text: str) -> str`, `_strip_code(text: str) -> str` 를 공개한다. Task 2·3·4 가 `_has_anchor` 와 `_slugify` 를 쓴다.

- [ ] **Step 1: 옮길 범위를 정확히 확인**

```bash
sed -n '686,712p;715,757p;818,827p' scripts/harness_scaffold.py
grep -n '_slugify\|_has_anchor\|_strip_frontmatter\|_strip_code' scripts/harness_scaffold.py
```

옮기는 것: `_A_TAG_RE` · `_ID_ATTR_RE` · `_HEADING_RE` · `_SETEXT_RE` · `_MD_INLINE_LINK_RE` · `_HTML_TAG_RE` · `_HTML_ENTITY_RE` · `_SLUG_DROP_RE` · `_CODE_FENCE_RE` · `_INLINE_CODE_RE` · `_slugify` · `_has_anchor` · `_strip_frontmatter` · `_strip_code`. **각 상수 위의 주석을 함께 옮긴다** — 그 주석이 정규식이 왜 그 모양인지(quadratic 회피, CRLF, CommonMark 차이)를 담고 있고, 코드가 스스로 말할 수 없는 유일한 부분이다.

남기는 것: `_MD_LINK_RE`(686) · `_LINE_FRAGMENT_RE`(715-716) · `_WIN_ABS_RE`(758) · `OPS_ANCHOR_RE` · `OPS_MAX_LINES`.

- [ ] **Step 2: 이동이 실제로 적용됐는지 단언하는 테스트를 먼저 쓴다**

`tests/md_anchors/__init__.py` (빈 파일) 과 `tests/md_anchors/test_extraction.py`:

```python
"""The extraction is a move, not a rewrite: both module surfaces must agree.

`harness_scaffold` re-exports rather than redefines — a second definition would drift
the moment either copy is touched, and the drift is silent because both pass their own
tests.
"""

import scripts._md_anchors as ma
import scripts.harness_scaffold as hs


def test_harness_scaffold_reexports_the_moved_names():
    for name in ("_slugify", "_has_anchor", "_strip_frontmatter", "_strip_code"):
        assert getattr(hs, name) is getattr(ma, name), name


def test_module_defines_no_second_copy():
    src = (ma.__file__, hs.__file__)
    assert src[0] != src[1]
    body = open(hs.__file__, encoding="utf-8").read()
    for name in ("def _slugify", "def _has_anchor", "def _strip_frontmatter"):
        assert name not in body, f"{name} still defined in harness_scaffold"


def test_slugify_still_handles_the_hard_cases():
    assert ma._slugify("Step 1 — Classify the task") == "step-1--classify-the-task"
    assert ma._slugify("flow_gate_check") == "flow_gate_check"
    assert ma._slugify("Map<K,V>") == "mapkv"


def test_has_anchor_reads_an_explicit_id():
    assert ma._has_anchor('<a id="fr-payment-001"></a>**FR-PAYMENT-001**', "fr-payment-001")
    assert not ma._has_anchor("# Heading\n", "fr-payment-001")
```

- [ ] **Step 3: 테스트가 실패하는지 확인**

Run: `uv run pytest tests/md_anchors/ -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts._md_anchors'`

- [ ] **Step 4: `scripts/_md_anchors.py` 를 만든다**

머리말은 이렇게 시작한다 (`harness_scaffold.py` 의 import fallback 패턴은 여기엔 필요 없다 — 이 모듈은 아무것도 import 하지 않는다):

```python
"""GitHub's anchor rules, as the repo's markdown consumers need them.

Its own module because two entry points need it: `harness_scaffold.validate_plan` checks
a plan's links at generation time, and `srs_check` checks a hand-edited SRS. The host
receives them as flat sibling files, so a shared helper has to be importable without
`harness_scaffold`, which is not copied there.
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import unquote
```

그 아래에 Step 1 이 나열한 상수와 함수를 **주석까지 그대로** 옮겨 붙인다. 순서는 상수 → `_slugify` → `_has_anchor` → `_strip_frontmatter` → `_strip_code`.

- [ ] **Step 5: `harness_scaffold.py` 에서 제거하고 import 로 바꾼다**

`wiki_graph` import 블록(28-31행) 바로 아래에 같은 fallback 패턴으로 추가한다:

```python
try:
    from _md_anchors import _has_anchor, _slugify, _strip_code, _strip_frontmatter
except ImportError:
    from scripts._md_anchors import _has_anchor, _slugify, _strip_code, _strip_frontmatter
```

그리고 옮긴 상수·함수 정의를 지운다. `from html import unescape`(9행)와 `from urllib.parse import unquote`(11행)도 지운다 — 옮긴 함수들이 유일한 사용처였다.

- [ ] **Step 6: 테스트 통과 + 기존 테스트 무회귀 확인**

```bash
uv run pytest tests/md_anchors/ tests/harness_scaffold/ -v
```
Expected: 전부 PASS. `tests/harness_scaffold/test_validate_links.py` 가 `hs._slugify` 를 모듈 속성으로 부르는데, import 된 이름도 모듈 속성이므로 한 줄도 고치지 않고 통과해야 한다.

- [ ] **Step 7: 수집된 테스트 id 가 줄지 않았는지 확인**

```bash
git stash && uv run pytest --collect-only -q > /tmp/before.txt; git stash pop
uv run pytest --collect-only -q > /tmp/after.txt
comm -23 <(sort /tmp/before.txt) <(sort /tmp/after.txt)
```
Expected: 사라진 id 없음(출력 없음). 기계적 편집이 테스트를 조용히 누락시키는 것을 잡는다.

- [ ] **Step 8: 린트**

```bash
uv run ruff check && uv run ruff format --check
uv run python scripts/doc_style_check.py --root . --lint scripts/_md_anchors.py scripts/harness_scaffold.py
```

---

### Task 2: `srs_check.py --areas` 와 부재 계약

가장 얇은 슬라이스부터. `docs/srs/` 가 없을 때 exit 0 · 무출력이라는 계약이 나머지 전부의 전제다 — 이게 깨지면 SRS 없는 저장소의 모든 커밋에 잡음이 낀다.

**Files:**
- Create: `scripts/srs_check.py`
- Test: `tests/srs_check/__init__.py` · `tests/srs_check/_helpers.py` · `tests/srs_check/test_areas.py`

**Interfaces:**
- Consumes: Task 1 의 `scripts/_md_anchors.py` (이 태스크에선 아직 안 씀)
- Produces: `srs_dir(root: Path) -> Path | None` (없으면 None) · `areas(root: Path) -> list[tuple[str, str]]` — `(stem, title)` 목록, stem 오름차순. CLI `--areas`. Task 3·4 가 `srs_dir` 를 쓴다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/srs_check/__init__.py` (빈 파일), `tests/srs_check/_helpers.py`:

```python
from pathlib import Path

import scripts.srs_check as sc


def write(root: Path, rel: str, text: str) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")
    return p


def run(argv: list[str], capsys) -> tuple[int, str]:
    """Both streams, joined: problems go to stderr, listings to stdout."""
    try:
        code = sc.main(argv)
    except SystemExit as exc:
        code = exc.code or 0
    cap = capsys.readouterr()
    return code, cap.out + cap.err
```

`tests/srs_check/test_areas.py`:

```python
"""`--areas` is the routing input the /flow SRS step reads.

The absent-docs/srs contract is asserted first: every subcommand inherits it, and a
repo without an SRS must see no output at all rather than a warning it cannot act on.
"""

from pathlib import Path

from ._helpers import run, write


def test_no_srs_dir_is_silent_success(tmp_path: Path, capsys):
    code, out = run(["--root", str(tmp_path), "--areas"], capsys)
    assert code == 0
    assert out == ""


def test_empty_srs_dir_is_silent_success(tmp_path: Path, capsys):
    (tmp_path / "docs" / "srs").mkdir(parents=True)
    code, out = run(["--root", str(tmp_path), "--areas"], capsys)
    assert code == 0
    assert out == ""


def test_areas_lists_stem_and_title(tmp_path: Path, capsys):
    write(tmp_path, "docs/srs/README.md", "# SRS\n")
    write(tmp_path, "docs/srs/payment.md", "---\nwiki_id: srs.payment\n---\n# Payment\n")
    write(tmp_path, "docs/srs/user-auth.md", "# User Auth\n")
    code, out = run(["--root", str(tmp_path), "--areas"], capsys)
    assert code == 0
    assert out.splitlines() == ["payment\tPayment", "user-auth\tUser Auth"]


def test_readme_is_not_an_area(tmp_path: Path, capsys):
    write(tmp_path, "docs/srs/README.md", "# SRS\n")
    code, out = run(["--root", str(tmp_path), "--areas"], capsys)
    assert out == ""
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/srs_check/ -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.srs_check'`

- [ ] **Step 3: 최소 구현**

`scripts/srs_check.py`:

```python
"""Numbering and integrity for docs/srs — the requirement text's SSOT.

Its own entry point because nothing else reads a hand-edited SRS: `_has_anchor` runs only
inside `validate_plan`, which sees generated plans; `doc_invariants` counts links without
resolving them; `wiki_graph --verify` reads front-matter edges. The dead anchors that
incremental editing produces have no reader today.

Not a gate. An absent docs/srs is exit 0 with no output, and every check reports rather
than blocks — the verdict is the srs-verify workflow's.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    from _harness_paths import force_utf8_io
except ImportError:
    from scripts._harness_paths import force_utf8_io

SRS_REL = "docs/srs"
INDEX_STEM = "README"
_H1_RE = re.compile(r"^[ \t]{0,3}#[ \t]+(.+)$", re.MULTILINE)
_FRONT_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)


def srs_dir(root: Path) -> Path | None:
    d = root / SRS_REL
    return d if d.is_dir() else None


def _title(text: str) -> str:
    body = _FRONT_RE.sub("", text)
    m = _H1_RE.search(body)
    return m.group(1).strip() if m else ""


def area_files(root: Path) -> list[Path]:
    d = srs_dir(root)
    if d is None:
        return []
    return sorted(p for p in d.glob("*.md") if p.stem != INDEX_STEM)


def areas(root: Path) -> list[tuple[str, str]]:
    return [(p.stem, _title(p.read_text(encoding="utf-8"))) for p in area_files(root)]


def main(argv: list[str] | None = None) -> int:
    force_utf8_io()
    parser = argparse.ArgumentParser(description="docs/srs numbering and integrity")
    parser.add_argument("--root", default=".", help="repository root (default: cwd)")
    parser.add_argument("--areas", action="store_true", help="list area stem and title")
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.areas:
        for stem, title in areas(root):
            print(f"{stem}\t{title}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/srs_check/ -v`
Expected: PASS

- [ ] **Step 5: 린트**

```bash
uv run ruff check && uv run ruff format --check
uv run python scripts/doc_style_check.py --root . --lint scripts/srs_check.py
```

---

### Task 3: `srs_check.py --next-id`

번호 발급. KIND 목록을 어디에도 하드코딩하지 않는 것이 이 태스크의 핵심 제약이다 — 대상 파일의 기존 앵커를 스캔해 도출한다.

**Files:**
- Modify: `scripts/srs_check.py`
- Test: `tests/srs_check/test_next_id.py`

**Interfaces:**
- Consumes: Task 2 의 `srs_dir` · `INDEX_STEM`
- Produces: `next_id(path: Path, kind: str, scope: str | None) -> str` — `FR-PAYMENT-008` 같은 문자열. CLI `--next-id <file> --kind <KIND> [--scope <token>]`, stdout 한 줄.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/srs_check/test_next_id.py`:

```python
"""Numbers are issued, never chosen — by a human or a model.

The KIND set is open: nothing here enumerates it. A kind is whatever a document already
anchors, so adding one is writing an anchor, not editing this script.
"""

from pathlib import Path

from ._helpers import run, write


def test_first_id_in_an_empty_area_file(tmp_path: Path, capsys):
    f = write(tmp_path, "docs/srs/payment.md", "# Payment\n")
    code, out = run(["--root", str(tmp_path), "--next-id", str(f), "--kind", "FR"], capsys)
    assert code == 0
    assert out.strip() == "FR-PAYMENT-001"


def test_continues_from_the_highest_existing(tmp_path: Path, capsys):
    f = write(
        tmp_path,
        "docs/srs/payment.md",
        '# Payment\n<a id="fr-payment-001"></a>\n<a id="fr-payment-007"></a>\n',
    )
    code, out = run(["--root", str(tmp_path), "--next-id", str(f), "--kind", "FR"], capsys)
    assert out.strip() == "FR-PAYMENT-008"


def test_area_prefix_comes_from_the_file_stem(tmp_path: Path, capsys):
    f = write(tmp_path, "docs/srs/user-auth.md", "# User Auth\n")
    code, out = run(["--root", str(tmp_path), "--next-id", str(f), "--kind", "FR"], capsys)
    assert out.strip() == "FR-USER-AUTH-001"


def test_readme_takes_no_area_prefix(tmp_path: Path, capsys):
    f = write(tmp_path, "docs/srs/README.md", '# SRS\n<a id="c-003"></a>\n')
    code, out = run(["--root", str(tmp_path), "--next-id", str(f), "--kind", "C"], capsys)
    assert out.strip() == "C-004"


def test_scope_separates_counters_in_one_file(tmp_path: Path, capsys):
    f = write(
        tmp_path,
        "docs/srs/README.md",
        '# SRS\n<a id="nfr-perf-001"></a>\n<a id="nfr-security-001"></a>\n'
        '<a id="nfr-security-002"></a>\n',
    )
    _, perf = run(
        ["--root", str(tmp_path), "--next-id", str(f), "--kind", "NFR", "--scope", "perf"],
        capsys,
    )
    assert perf.strip() == "NFR-PERF-002"
    _, sec = run(
        ["--root", str(tmp_path), "--next-id", str(f), "--kind", "NFR", "--scope", "security"],
        capsys,
    )
    assert sec.strip() == "NFR-SECURITY-003"


def test_an_unlisted_kind_needs_no_code_change(tmp_path: Path, capsys):
    f = write(tmp_path, "docs/srs/README.md", '# SRS\n<a id="risk-002"></a>\n')
    code, out = run(["--root", str(tmp_path), "--next-id", str(f), "--kind", "RISK"], capsys)
    assert code == 0
    assert out.strip() == "RISK-003"


def test_a_scoped_kind_ignores_an_unscoped_one(tmp_path: Path, capsys):
    """`c-003` must not feed the `C-PAYMENT-nnn` counter, nor the reverse."""
    f = write(
        tmp_path,
        "docs/srs/payment.md",
        '# Payment\n<a id="fr-001"></a>\n<a id="fr-payment-002"></a>\n',
    )
    _, out = run(["--root", str(tmp_path), "--next-id", str(f), "--kind", "FR"], capsys)
    assert out.strip() == "FR-PAYMENT-003"


def test_missing_file_is_silent_success(tmp_path: Path, capsys):
    f = tmp_path / "docs" / "srs" / "gone.md"
    code, out = run(["--root", str(tmp_path), "--next-id", str(f), "--kind", "FR"], capsys)
    assert code == 0
    assert out == ""
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/srs_check/test_next_id.py -v`
Expected: FAIL — `--next-id` 인자가 없어 `SystemExit: 2`

- [ ] **Step 3: 구현**

`scripts/srs_check.py` 에 추가한다. `INDEX_STEM` 아래에:

```python
_ANCHOR_RE = re.compile(r'<a\s[^>]*\bid\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)


def _anchors(text: str) -> list[str]:
    return [a.lower() for a in _ANCHOR_RE.findall(text)]


def _default_scope(path: Path) -> str | None:
    """An area file scopes by its own stem; the index scopes by nothing.

    The file decides, not the kind — which is what keeps the KIND set open.
    """
    return None if path.stem == INDEX_STEM else path.stem


def next_id(path: Path, kind: str, scope: str | None = None) -> str | None:
    if not path.is_file():
        return None
    if scope is None:
        scope = _default_scope(path)
    prefix = f"{kind}-{scope}-" if scope else f"{kind}-"
    pat = re.compile(rf"^{re.escape(prefix.lower())}(\d+)$")
    used = [int(m.group(1)) for a in _anchors(path.read_text(encoding="utf-8"))
            if (m := pat.match(a))]
    return f"{prefix.upper()}{max(used, default=0) + 1:03d}"
```

`main` 의 argparse 에:

```python
    parser.add_argument("--next-id", metavar="FILE", help="issue the next id for --kind")
    parser.add_argument("--kind", help="id kind (FR, C, NFR, CON, ROLE, …) — an open set")
    parser.add_argument("--scope", help="counter scope within the file (an NFR axis stem)")
```

`main` 본문의 `--areas` 분기 앞에:

```python
    if args.next_id:
        if not args.kind:
            parser.error("--next-id requires --kind")
        got = next_id(Path(args.next_id), args.kind, args.scope)
        if got:
            print(got)
        return 0
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/srs_check/ -v`
Expected: 전부 PASS

- [ ] **Step 5: 변이 테스트 — 잡히는지 확인**

먼저 베이스라인이 초록인지 확인하고(`uv run pytest -q`), 그 다음 `_default_scope` 의 `INDEX_STEM` 비교를 뒤집는다:

```bash
uv run python - <<'PY'
from pathlib import Path
p = Path("scripts/srs_check.py"); t = p.read_text(encoding="utf-8")
old = 'return None if path.stem == INDEX_STEM else path.stem'
assert old in t, "anchor moved — pick a new mutation target"
p.write_text(t.replace(old, 'return path.stem if path.stem == INDEX_STEM else None'), encoding="utf-8")
print("mutation applied")
PY
uv run pytest tests/srs_check/test_next_id.py -q
git checkout -- scripts/srs_check.py
```
Expected: `mutation applied` 이 찍히고, 그 뒤 테스트가 FAIL. 변이가 적용됐음을 단언하는 것이 요점이다 — no-op 편집은 원본을 돌려 초록으로 보인다. 되돌리기는 이미 깨끗한 트리에서 `git checkout --` 로 한다.

- [ ] **Step 6: 린트**

```bash
uv run ruff check && uv run ruff format --check
uv run python scripts/doc_style_check.py --root . --lint scripts/srs_check.py
```

---

### Task 4: `srs_check.py --verify`

무결성 검사. **파일 간 링크**가 이 태스크의 핵심 — C 가 `README.md` 에 살고 FR 이 영역 파일에 사므로 백링크가 파일을 넘는다.

**Files:**
- Modify: `scripts/srs_check.py`
- Test: `tests/srs_check/test_verify.py`

**Interfaces:**
- Consumes: Task 1 의 `_has_anchor` · Task 2 의 `srs_dir`/`INDEX_STEM` · Task 3 의 `_anchors(text) -> list[str]`(소문자 앵커 id 목록)
- Produces: `verify(root: Path, paths: list[Path] | None) -> list[str]` — 문제 한 줄씩. CLI `--verify [경로…]`, 문제가 있으면 stderr 로 내고 exit 1.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/srs_check/test_verify.py`:

```python
"""What incremental editing breaks, and nothing else currently reads.

The cross-file case is the one the split introduced: a C lives in README while the FR
citing it lives in an area file, so a same-file fragment check would pass a dead link.
"""

from pathlib import Path

from ._helpers import run, write


def _index(body: str = "") -> str:
    return "# SRS\n" + body


def test_clean_tree_is_silent_success(tmp_path: Path, capsys):
    write(tmp_path, "docs/srs/README.md", _index('<a id="c-001"></a>C-001 Cards.\n'))
    write(
        tmp_path,
        "docs/srs/payment.md",
        '# Payment\n<a id="fr-payment-001"></a>**FR-PAYMENT-001** '
        "(← [C-001](README.md#c-001)) Pay.\n",
    )
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 0
    assert out == ""


def test_dead_cross_file_link(tmp_path: Path, capsys):
    write(tmp_path, "docs/srs/README.md", _index('<a id="c-001"></a>C-001 Cards.\n'))
    write(
        tmp_path,
        "docs/srs/payment.md",
        '# Payment\n<a id="fr-payment-001"></a>(← [C-009](README.md#c-009))\n',
    )
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 1
    assert "README.md#c-009" in out
    assert "payment.md" in out


def test_dead_same_file_fragment(tmp_path: Path, capsys):
    write(tmp_path, "docs/srs/README.md", _index("[gone](#nfr-perf-004)\n"))
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 1
    assert "#nfr-perf-004" in out


def test_duplicate_anchor_in_one_file(tmp_path: Path, capsys):
    write(
        tmp_path,
        "docs/srs/payment.md",
        '# Payment\n<a id="fr-payment-001"></a>\n<a id="fr-payment-001"></a>\n',
    )
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 1
    assert "fr-payment-001" in out


def test_duplicate_anchor_across_area_files(tmp_path: Path, capsys):
    """Two branches issuing the same number is detected, not prevented."""
    write(tmp_path, "docs/srs/payment.md", '# Payment\n<a id="fr-payment-001"></a>\n')
    write(tmp_path, "docs/srs/refund.md", '# Refund\n<a id="fr-payment-001"></a>\n')
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 1
    assert "fr-payment-001" in out


def test_prefix_mismatch_in_an_area_file(tmp_path: Path, capsys):
    write(tmp_path, "docs/srs/payment.md", '# Payment\n<a id="fr-refund-001"></a>\n')
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 1
    assert "fr-refund-001" in out
    assert "payment" in out


def test_index_anchors_take_no_prefix_check(tmp_path: Path, capsys):
    write(
        tmp_path,
        "docs/srs/README.md",
        _index('<a id="c-001"></a>\n<a id="nfr-perf-001"></a>\n<a id="role-001"></a>\n'),
    )
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 0


def test_external_and_absolute_links_are_out_of_scope(tmp_path: Path, capsys):
    write(
        tmp_path,
        "docs/srs/README.md",
        _index("[x](https://example.com#frag)\n[y](../sds/README.md#mod)\n"),
    )
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 0


def test_no_srs_dir_is_silent_success(tmp_path: Path, capsys):
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 0
    assert out == ""
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/srs_check/test_verify.py -v`
Expected: FAIL — `--verify` 인자 없음

- [ ] **Step 3: 구현**

import 블록에 Task 1 의 모듈을 더한다:

```python
try:
    from _md_anchors import _has_anchor
except ImportError:
    from scripts._md_anchors import _has_anchor
```

그리고:

```python
# A link into another SRS document, or a bare fragment in this one. Images (`![…]`) are
# excluded: they carry no anchor.
_LINK_RE = re.compile(r"(?<!!)\[[^\]]*\]\(\s*([^)\s]*?)(?:#([^)\s]*))?\s*\)")


def _files(root: Path, paths: list[Path] | None) -> list[Path]:
    d = srs_dir(root)
    if d is None:
        return []
    if paths:
        return [p for p in paths if p.is_file()]
    return sorted(d.glob("*.md"))


def _check_duplicates(texts: dict[Path, str]) -> list[str]:
    out, seen = [], {}
    for path, text in texts.items():
        local = set()
        for anchor in _anchors(text):
            if anchor in local:
                out.append(f"{path}: duplicate anchor '{anchor}' in this file")
            local.add(anchor)
            if anchor in seen and seen[anchor] != path:
                out.append(f"{path}: anchor '{anchor}' also defined in {seen[anchor]}")
            seen.setdefault(anchor, path)
    return out


def _check_prefix(path: Path, text: str) -> list[str]:
    """An area file's ids carry its stem. The index's ids carry no area at all."""
    if path.stem == INDEX_STEM:
        return []
    want = path.stem.lower()
    out = []
    for anchor in _anchors(text):
        parts = anchor.rsplit("-", 1)
        if len(parts) != 2 or not parts[1].isdigit():
            continue
        head = parts[0]
        if "-" not in head or not head.split("-", 1)[1] == want:
            out.append(f"{path}: anchor '{anchor}' does not carry the area prefix '{want}'")
    return out


def _check_links(path: Path, text: str, texts: dict[Path, str]) -> list[str]:
    out = []
    for target, frag in _LINK_RE.findall(text):
        if not frag or target.startswith(("http://", "https://", "/", "\\")):
            continue
        # Keyed by resolved path, this file included — a bare `#frag` targets itself.
        dest = path.resolve() if not target else (path.parent / target).resolve()
        body = texts.get(dest)
        if body is None:
            continue  # outside docs/srs — another checker's subject
        if not _has_anchor(body, frag):
            shown = f"{target}#{frag}" if target else f"#{frag}"
            out.append(f"{path}: dead link '{shown}'")
    return out


def verify(root: Path, paths: list[Path] | None = None) -> list[str]:
    files = _files(root, paths)
    if not files:
        return []
    texts = {p.resolve(): p.read_text(encoding="utf-8") for p in files}
    by_path = {p.resolve(): p for p in files}
    out = _check_duplicates({by_path[k]: v for k, v in texts.items()})
    for key, body in texts.items():
        path = by_path[key]
        out += _check_prefix(path, body)
        out += _check_links(path, body, texts)
    return out
```

argparse 와 `main`:

```python
    parser.add_argument(
        "--verify", nargs="*", metavar="PATH", default=None,
        help="check anchors and links under docs/srs (default: all of them)",
    )
```

```python
    if args.verify is not None:
        problems = verify(root, [Path(p) for p in args.verify] or None)
        for line in problems:
            print(line, file=sys.stderr)
        return 1 if problems else 0
```

`verify` 가 `texts` 를 `.resolve()` 로 키잉하므로 `_check_links` 의 자기 참조도 같은 형태여야 한다.

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/srs_check/ -v`
Expected: 전부 PASS

- [ ] **Step 5: 변이 테스트**

```bash
uv run pytest -q   # 베이스라인 초록 확인
uv run python - <<'PY'
from pathlib import Path
p = Path("scripts/srs_check.py"); t = p.read_text(encoding="utf-8")
old = "if not _has_anchor(body, frag):"
assert old in t, "anchor moved — pick a new mutation target"
p.write_text(t.replace(old, "if False:"), encoding="utf-8")
print("mutation applied")
PY
uv run pytest tests/srs_check/test_verify.py -q
git checkout -- scripts/srs_check.py
```
Expected: `mutation applied` 후 `test_dead_cross_file_link` 와 `test_dead_same_file_fragment` FAIL.

- [ ] **Step 6: 파일 크기 확인**

```bash
wc -l scripts/srs_check.py tests/srs_check/*.py
```
`tests/srs_check/` 안의 각 파일이 500줄 미만이어야 한다. 넘으면 케이스별로 더 쪼갠다.

- [ ] **Step 7: 린트**

```bash
uv run ruff check && uv run ruff format --check
uv run python scripts/doc_style_check.py --root . --lint scripts/srs_check.py
```

---

### Task 5: 호스트 복사 목록 등록

`COPY_FILES` 에 빠지면 증분 단계가 호스트에서 스크립트를 못 찾아 조용히 무력화되고, 소비자 CI 도 `--verify` 를 돌릴 수 없다.

**Files:**
- Modify: `scripts/flow_init_setup.py:101-113` (`COPY_FILES`)
- Test: `tests/flow_init/test_copy_and_uninstall.py`

**Interfaces:**
- Consumes: Task 1 의 `scripts/_md_anchors.py` · Task 4 까지의 `scripts/srs_check.py`
- Produces: 없음

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/flow_init/test_copy_and_uninstall.py` 끝에 붙인다:

```python
def test_srs_check_and_its_import_land_together(tmp_path: Path):
    """A flat copy makes the import chain the contract.

    `srs_check` imports `_md_anchors`; `harness_scaffold`, which also holds it, is not
    copied. One name without the other is an ImportError at the moment the /flow step
    runs it, and the step fails open — so the gap is invisible.
    """
    run_setup(tmp_path, PLUGIN)
    dest = tmp_path / ".claude" / "harness-tier" / "scripts"
    assert (dest / "srs_check.py").is_file()
    assert (dest / "_md_anchors.py").is_file()
```

`run_setup`·`PLUGIN` 은 이 파일이 이미 import 하고 있다. 아니라면 `tests/flow_init/_helpers.py` 에서 가져온다.

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/flow_init/test_copy_and_uninstall.py -v -k srs_check`
Expected: FAIL — `assert False` (`srs_check.py` 가 복사되지 않음)

- [ ] **Step 3: `COPY_FILES` 에 두 줄 추가**

`scripts/flow_init_setup.py` 의 리스트에 넣는다. `_harness_paths.py` 바로 아래가 자리다 — 둘 다 다른 스크립트가 import 하는 잎 모듈이다.

```python
COPY_FILES = [
    "scripts/_harness_paths.py",
    "scripts/_md_anchors.py",
    "scripts/flow_gate_check.py",
    "scripts/precommit-runner.sh",
    "scripts/wiki_graph.py",
    "scripts/doc_style_check.py",
    "scripts/srs_check.py",
    "scripts/teams_alert.py",
    "scripts/notify-push.sh",
    "scripts/check-deps.sh",
    "scripts/check-token-write.sh",
    "scripts/finalize_prerelease.py",
    "scripts/bump_version.py",
]
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/flow_init/ -v`
Expected: 전부 PASS

- [ ] **Step 5: 복사본이 실제로 import 되는지 확인**

```bash
uv run python - <<'PY'
import subprocess, sys, tempfile, pathlib
sys.path.insert(0, "scripts")
from flow_init_setup import run_setup, plugin_root
d = pathlib.Path(tempfile.mkdtemp())
run_setup(d, plugin_root())
s = d / ".claude/harness-tier/scripts"
print(subprocess.run([sys.executable, str(s / "srs_check.py"), "--areas"],
                     capture_output=True, text=True))
PY
```
Expected: `returncode=0`, stdout 빈 문자열. `docs/srs/` 가 없으므로 무출력이 정답이고, `ImportError` 가 나면 Step 3 이 불완전하다.

---

### Task 6: `srs-verify` CI 워크플로

판정 주체를 만든다. 커밋 게이트는 SRS 를 보지 않으므로 이 워크플로가 죽은 앵커와 중복 번호를 보는 유일한 곳이다.

**Files:**
- Create: `github/srs-verify.workflow.example.yml` · `.github/workflows/srs-verify.yml`
- Modify: `scripts/flow_init_setup.py` (상수 75-78 옆 · `render_wiki_verify_workflow` 아래 · argparse · uninstall 안내 1631)
- Test: `tests/flow_init/test_render_workflows.py`

**Interfaces:**
- Consumes: Task 5 의 `COPY_FILES`
- Produces: `render_srs_verify_workflow(host: Path, plugin: Path) -> list[str]` · CLI `--render-srs-verify`. Task 11 의 `/flow-init` 단계가 이 명령을 부른다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/flow_init/test_render_workflows.py` 의 import 에 `render_srs_verify_workflow` 를 더하고, 끝에 붙인다:

```python
def test_render_srs_verify_workflow_reads_no_config(tmp_path: Path):
    """The user's yes is the gate — /flow-init asks, this only copies."""
    out = render_srs_verify_workflow(tmp_path, PLUGIN)
    dest = tmp_path / ".github" / "workflows" / "srs-verify.yml"
    assert dest.is_file()
    assert any("srs-verify" in line for line in out)
    data = yaml.safe_load(dest.read_text(encoding="utf-8"))
    assert data["jobs"]["srs-verify"]["timeout-minutes"] == 5


def test_render_srs_verify_never_overwrites(tmp_path: Path):
    dest = tmp_path / ".github" / "workflows" / "srs-verify.yml"
    dest.parent.mkdir(parents=True)
    dest.write_text("custom\n", encoding="utf-8")
    render_srs_verify_workflow(tmp_path, PLUGIN)
    assert dest.read_text(encoding="utf-8") == "custom\n"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/flow_init/test_render_workflows.py -v -k srs_verify`
Expected: FAIL — `ImportError: cannot import name 'render_srs_verify_workflow'`

- [ ] **Step 3: 소비자용 템플릿을 만든다**

`github/srs-verify.workflow.example.yml`. `${{ }}` 를 `run:` 블록에 쓰지 않고, `timeout-minutes` 를 반드시 단다:

```yaml
# Requirement-text integrity over docs/srs. Rendered by /flow-init once docs/srs exists —
# the commit gate never reads an SRS, so this job holds the only verdict.
name: srs-verify

on:
  push:
  pull_request:

jobs:
  srs-verify:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"

      - name: Verify SRS anchors and links
        run: python3 .claude/harness-tier/scripts/srs_check.py --verify
```

- [ ] **Step 4: 이 저장소 자신의 워크플로를 만든다**

`.github/workflows/srs-verify.yml`. CLAUDE.md 의 dogfood 규칙이다. 이 저장소엔 호스트 설치가 없으므로 SOURCE 스크립트를 직접 돌리고, `docs/srs/` 가 없으므로 no-op-green 계약을 검증하는 역할이 된다 — `wiki-verify.yml` 과 같은 처지:

```yaml
# Dogfood of github/srs-verify.workflow.example.yml (CLAUDE.md: a workflow-rendering
# feature lands in this repo's OWN CI too). This repo has no host install, so it runs the
# SOURCE script directly; with no docs/srs here the run exercises the no-op-green contract
# consumers without an SRS rely on.
name: srs-verify

on:
  push:
  pull_request:

jobs:
  srs-verify:
    runs-on: ubuntu-latest
    timeout-minutes: 5
    steps:
      - uses: actions/checkout@v7

      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"

      - name: Verify SRS anchors and links
        run: python3 scripts/srs_check.py --verify
```

- [ ] **Step 5: 렌더 함수와 CLI 플래그를 더한다**

`scripts/flow_init_setup.py` 의 상수 78 아래:

```python
SRS_VERIFY_TEMPLATE = "github/srs-verify.workflow.example.yml"  # SOURCE (plugin-owned)
SRS_VERIFY_DEST = ".github/workflows/srs-verify.yml"  # host (GitHub-forced — HARNESS_DIR exc.)
```

`render_wiki_verify_workflow` 바로 아래:

```python
def render_srs_verify_workflow(host: Path, plugin: Path) -> list[str]:
    """Copy srs-verify.yml as-is — no enable gate, no tokens.

    Reached from `/flow-init`'s own step (`--render-srs-verify`), never from run_setup: the
    workflow reads docs/srs, and a host without one has nothing to point it at. The user's
    yes IS the gate, which is why nothing is read from config here.

    Idempotent·non-destructive (existing dest → report only), like every render here.
    """
    return _render_one(
        plugin / SRS_VERIFY_TEMPLATE, host / SRS_VERIFY_DEST, {}, "srs-verify 렌더"
    )
```

argparse 에 `--render-wiki-verify` 아래:

```python
    parser.add_argument(
        "--render-srs-verify",
        action="store_true",
        help="SRS 검증 워크플로우만 렌더(/flow-init 이 사용자 동의를 받은 뒤 호출).",
    )
```

`main` 의 `--render-wiki-verify` 분기 아래:

```python
    if args.render_srs_verify:
        for line in render_srs_verify_workflow(host, plugin_root()):
            print(line)
        return
```

1631행의 uninstall 안내 문구에 `srs-verify.yml` 을 더한다:

```python
    print("  - .github/workflows/wiki-verify.yml·doc-style.yml·srs-verify.yml 은 방금 삭제된")
```

- [ ] **Step 6: 통과 확인**

Run: `uv run pytest tests/flow_init/ -v`
Expected: 전부 PASS. `test_copy_and_uninstall.py` 의 기존 uninstall 안내 단언이 문구 변경으로 깨지면, 그 테스트가 무엇을 지키려던 것인지 읽고 새 문구에 맞춘다.

- [ ] **Step 7: 워크플로 YAML 을 직접 검증**

```bash
uv run python -c "
import yaml
for f in ('github/srs-verify.workflow.example.yml', '.github/workflows/srs-verify.yml'):
    d = yaml.safe_load(open(f, encoding='utf-8'))
    assert d['jobs']['srs-verify']['timeout-minutes'] == 5, f
    print(f, 'ok')
"
uv run python scripts/srs_check.py --verify; echo "exit=$?"
```
Expected: 둘 다 `ok`, `--verify` 는 `exit=0` 무출력(이 저장소엔 `docs/srs/` 가 없다).

---

### Task 7: SRS 템플릿 재편

절 구조와 채번을 문서 쪽에 반영한다. DR·EIR 절 삭제, §9 → §7 번호 당김, 영역 파일용 새 템플릿.

**Files:**
- Modify: `skills/harness-authoring/templates/srs.template.md`
- Create: `skills/harness-authoring/templates/srs-area.template.md`
- Test: `uv run pytest tests/skills/ -v`

**Interfaces:**
- Consumes: Task 3 의 `--next-id` (템플릿 주석이 이 명령을 가리킨다)
- Produces: `srs-area.template.md` — Task 8·9 의 가이드 문서가 이 파일을 가리킨다.

- [ ] **Step 1: 현재 상태를 읽는다**

```bash
cat skills/harness-authoring/templates/srs.template.md
```

- [ ] **Step 2: `srs.template.md` 를 README 전용으로 고친다**

- 머리말의 `> Greenfield only —` 를 지운다 (Task 9 가 나머지 greenfield 표기를 푼다). 대신 이 문서가 **인덱스**임을 밝힌다: 공통 절을 갖고, §5 기능요구는 `<영역>.md` 가 갖는다.
- **§7 Data Requirements 절 전체를 삭제**한다 (현재 92-97행). 데이터 보존/삭제 정책, 규제 제약은 측정 가능한 FR 로 쓴다.
- **§8 External Interface Requirements 절 전체를 삭제**한다 (현재 99-103행). 외부가 부과한 인터페이스 의무는 §7 제약이다.
- **§9 Constraints / Assumptions 를 §7 로 번호를 당긴다.** 각 항목에 `<a id="con-001">` 앵커를 준다. 삭제한 EIR 이 여기로 오므로, 주석에 그 예를 든다 — "must integrate via legacy system X's SOAP API v1.2" 는 시스템이 수행하는 것이 아니라 외부가 부과한 것이므로 제약이다.
- **§3.1 User Role Classification** 의 각 역할에 `<a id="role-001">` 앵커를 준다. §5 의 2차 분류축이 역할일 때 영역 파일이 이 앵커를 링크한다 — **하위 영역일 때는 링크하지 않는다**(없는 역할이 생긴다).
- **§4 Customer Requirements** 형식을 `C-1` 에서 `C-001` 로 바꾼다: `<a id="c-001"></a>**C-001** …`. 이 절은 README 에 남는다 — 횡단 고객 요구를 억지로 한 영역에 배정하지 않기 위해서다.
- **§5 Functional Requirements** 자리에는 영역 인덱스만 남긴다:

```markdown
## 5. Functional Requirements
<!-- One file per requirement area, cloned from srs-area.template.md. The file stem IS the
     area key, and every FR in it carries that stem uppercased. Splitting here rather than
     later is deliberate: the SDS links each FR anchor, so a split after the fact breaks
     those links. -->
{{AREA_INDEX}}
<!-- Format — - [Payment](payment.md) — card and express payment -->
```

- **§6 Non-functional Requirements**: 각 축의 섹션 앵커(`<a id="nfr-perf">` 등)를 **그대로 둔다** — `sds.template.md` 와 `tech-doc-guide.md` 가 링크한다. 그 아래에 항목 앵커를 더한다:

```markdown
### 6.1 <a id="nfr-perf"></a>Performance
{{NFR_PERFORMANCE}}  <!-- [P0/P1/P2] Throughput, latency (p50/p95), concurrency.
     Verify → docs/verification/performance.md. Format —
     - <a id="nfr-perf-001"></a>**NFR-PERF-001** [P0] p95 < 200ms at 100 rps.
     The section anchor is the axis; the item anchor is the individual requirement. An axis
     added as §6.8 yields NFR-<its stem>-NNN with no other change. -->
```

- 문서 어딘가에 채번 규칙을 한 곳으로 못박는다:

```markdown
<!-- Ids are issued, never chosen — by a human or a model:
     python3 .claude/harness-tier/scripts/srs_check.py --next-id <file> --kind <KIND> [--scope <axis>]
     An area file's ids carry its stem; this index's ids carry no area. The KIND set is open —
     it is whatever a document already anchors. -->
```

- [ ] **Step 3: `srs-area.template.md` 를 만든다**

`srs.template.md` 와 같은 front matter 주석 규약(1-17행)을 그대로 쓴다 — `wiki_id` 는 경로에서 기계적으로 파생하고 손으로 고르지 않는다. 본문은 §5 만 갖는다:

```markdown
# {{AREA_TITLE}} Functional Requirements

> One requirement area of [the SRS](README.md). Common sections — purpose, goals, users
> and roles, customer requirements, non-functional requirements, constraints — live there.

## 5. Functional Requirements
<!-- Hierarchical classification (fixed schema): domain (level 1) > user role/sub-area
     (level 2) > individual FR (level 3). Level 2 links a role anchor only when the axis IS
     a role — a sub-area gets plain text, since a forced link invents a role that does not
     exist. Each FR has measurable acceptance criteria. -->

### 5.1 {{DOMAIN_A}}
#### 5.1.1 {{ROLE_OR_SUBAREA_A}}
{{FR_LIST_A}}
<!-- Format —
     - <a id="fr-payment-001"></a>**FR-PAYMENT-001** [P0/P1/P2] (← [C-003](README.md#c-003))
       Description. Acceptance criteria: <measurable, verifiable condition>.
     The area prefix is this file's stem uppercased, and the number comes from
     `srs_check.py --next-id <this file> --kind FR`. The back-reference crosses files
     because customer requirements live in README — omit it when there is no originating
     one. If ambiguous or unknown, state "needs confirmation" in the acceptance criteria. -->
```

- [ ] **Step 4: 링크·언어·크기 검사**

```bash
uv run pytest tests/skills/ -v
wc -l skills/harness-authoring/templates/srs.template.md \
      skills/harness-authoring/templates/srs-area.template.md
uv run python scripts/doc_style_check.py --root . --lint \
  skills/harness-authoring/templates/srs.template.md \
  skills/harness-authoring/templates/srs-area.template.md
```
Expected: 전부 PASS, 둘 다 400줄 미만.

- [ ] **Step 5: 템플릿 예시가 `--verify` 를 실제로 통과하는지 확인**

템플릿의 형식 주석이 실제로 유효한 앵커/링크를 보여주는지 맨눈 대신 스크립트로 확인한다:

```bash
mkdir -p /tmp/srscheck/docs/srs
printf '# SRS\n<a id="c-003"></a>**C-003** Cards.\n' > /tmp/srscheck/docs/srs/README.md
printf '# Payment\n<a id="fr-payment-001"></a>**FR-PAYMENT-001** (← [C-003](README.md#c-003)) Pay.\n' \
  > /tmp/srscheck/docs/srs/payment.md
uv run python scripts/srs_check.py --root /tmp/srscheck --verify; echo "exit=$?"
uv run python scripts/srs_check.py --next-id /tmp/srscheck/docs/srs/payment.md --kind FR
rm -rf /tmp/srscheck
```
Expected: `exit=0` 무출력, 그리고 `FR-PAYMENT-002`.

---

### Task 8: SDS 템플릿과 tech-doc-guide

SDS 가 새 FR 앵커를 가리키게 하고, brownfield 생략을 푼다. 안 풀면 SRS 는 생기는데 SDS 가 안 가리켜 Requirements Matrix 가 반쪽이 된다.

**Files:**
- Modify: `skills/harness-authoring/templates/sds.template.md` (40-42 · 55 · 89행 부근)
- Modify: `skills/harness-authoring/references/tech-doc-guide.md` (12 · 32 · 41-63 · 79-89행 부근)
- Test: `uv run pytest tests/skills/ -v`

**Interfaces:**
- Consumes: Task 7 의 `srs-area.template.md` 와 새 앵커 형식
- Produces: 없음

- [ ] **Step 1: 현재 문구를 확인**

```bash
sed -n '38,58p;85,92p' skills/harness-authoring/templates/sds.template.md
sed -n '8,16p;30,34p;41,63p;76,92p' skills/harness-authoring/references/tech-doc-guide.md
```

- [ ] **Step 2: `sds.template.md` 를 고친다**

- `Implemented requirements` 예시를 `[FR-001](../srs/README.md#fr-001)` 에서 `[FR-PAYMENT-001](../srs/payment.md#fr-payment-001)` 로 바꾼다. 영역 파일이 FR 을 갖기 때문이다.
- 같은 주석의 **"For brownfield (no SRS generated), omit this field"** 를 지운다. 인프라·횡단 모듈의 `"no FR mapping"` 은 **그대로 둔다** — 억지 매핑과 죽은 링크를 막는 장치다.
- NFR Realization 예시(55행)는 `../srs/README.md#nfr-perf` 를 **그대로 둔다** — NFR 은 README 에 남고 섹션 앵커도 남는다. 항목 단위로 가리키고 싶을 때를 위해 `#nfr-perf-001` 형태를 한 줄 덧붙인다.
- NFR Realization 과 Requirements Coverage 의 **"Brownfield (no SRS) → omit"** 을 지운다.

- [ ] **Step 3: `tech-doc-guide.md` 를 고친다**

- 12행의 폴더 표 `srs/README.md  … greenfield only` 를 고친다: `srs/README.md` 는 공통 절 + 영역 인덱스, `srs/<area>.md` 는 기능요구.
- 32행 **"SRS is greenfield only — do not create an SRS for brownfield."** 를 지우고, 대신 brownfield 는 골격만 만들고 요구는 증분으로 들어온다고 쓴다. **코드에서 FR 을 역산하지 않는다** — 코드는 "무엇을 하는가"지 "무엇을 원했는가"가 아니고, 역산한 FR 은 요구가 아니라 현재 동작의 서술이라 harness-rules 4(추측 금지) 위반이다.
- 41행 제목 `## SRS (greenfield) — srs/README.md` 에서 `(greenfield)` 를 뺀다.
- §7 데이터요구 · §8 외부인터페이스요구 문단을 지운다. 대신 한 줄로 어디로 갔는지 밝힌다: 데이터 보존/규제 요구는 측정 가능한 FR, 외부가 부과한 인터페이스 의무는 §7 제약. 소유 데이터와 통합 지점 계약 자체는 SDS 가 SSOT 다.
- §6 NFR 문단에 섹션 앵커 = 축, 항목 앵커 = 개별 요구를 밝히고 축 키가 섹션 앵커 stem 이라고 쓴다.
- 79-80행의 FR 링크 형식을 `[FR-<AREA>-xxx](../srs/<area>.md#fr-<area>-xxx)` 로 고치고, **"Brownfield (no SRS generated) omits this field"** 를 지운다.
- 87 · 89행의 NFR Realization · Requirements Coverage 의 brownfield 생략을 지운다.
- §5 문단에 채번이 `srs_check.py --next-id` 소관임을 한 줄로 못박고, 번호를 손으로 짓지 않는다고 쓴다.

- [ ] **Step 4: 검사**

```bash
uv run pytest tests/skills/ -v
wc -l skills/harness-authoring/references/tech-doc-guide.md \
      skills/harness-authoring/templates/sds.template.md
uv run python scripts/doc_style_check.py --root . --lint \
  skills/harness-authoring/references/tech-doc-guide.md \
  skills/harness-authoring/templates/sds.template.md
```
Expected: PASS, 둘 다 400줄 미만.

- [ ] **Step 5: greenfield 표기가 남았는지 확인**

```bash
grep -rn -i 'greenfield' skills/harness-authoring/references/tech-doc-guide.md \
  skills/harness-authoring/templates/sds.template.md
```
Expected: SRS 를 greenfield 로 제한하는 문장은 없다. 버전 선택·표준 채택처럼 SRS 와 무관한 greenfield 언급은 남아 있어도 된다.

---

### Task 9: brownfield 개방 — 룰과 스킬

`harness-rules` 와 두 스킬에서 SRS 를 greenfield 로 묶는 문장을 푼다. `harness-rules` 7-1 도 여기서 더한다.

**Files:**
- Modify: `rules/harness-rules.md` (7 아래 신설 · 44-45 · 53-63)
- Modify: `skills/harness-authoring/SKILL.md:38,52`
- Modify: `skills/harness-init/SKILL.md:31,44,58,71,133`
- Test: `uv run pytest tests/skills/ -v`

**Interfaces:**
- Consumes: Task 7·8 의 문서 구조
- Produces: 없음

- [ ] **Step 1: 현재 문구를 확인**

```bash
sed -n '44,63p' rules/harness-rules.md
sed -n '36,40p;50,54p' skills/harness-authoring/SKILL.md
sed -n '29,34p;42,46p;56,60p;69,73p;131,135p' skills/harness-init/SKILL.md
```

- [ ] **Step 2: `harness-rules.md` 7-1 을 신설한다**

룰 7 바로 아래(현재 43행 다음)에 넣는다. 룰 7 이 이미 "one fact, one place" SSOT 룰이라 여기가 자리다:

```markdown
7-1. **SSOT axes are named separately** — requirement and design **text** lives in the repo's
   documents (`docs/srs/` · `docs/sds/`); **status, approval and assignee** live in the
   external tracker. Each axis names exactly one authority. No two-way automatic merge.
```

- [ ] **Step 3: 룰 8 과 8-1 을 푼다**

- 44-45행: `docs/srs/` 설명에서 `greenfield-only` 를 뺀다. 대신 `README.md` 가 공통 절 + 영역 인덱스, `<area>.md` 가 기능요구임을 밝힌다.
- 53행 제목 `**SRS scope-clarification gate (greenfield-only, no guessing)**` 에서 `greenfield-only` 를 뺀다.
- 61-63행 **"Brownfield skips this gate and uses code-analyzer's code analysis as its scope"** 를 고친다. 범위 명확화 게이트(`AskUserQuestion` 으로 측정 가능·단일 해석까지)는 **brownfield 에도 적용**한다. 다만 brownfield 는 뼈대만 만들고 미수집으로 표기하며, **코드에서 FR 을 역산하지 않는다** — 역산한 FR 은 요구가 아니라 현재 동작의 서술이라 룰 4 위반이다. 코드 분석은 범위의 *입력*이지 요구의 *출처*가 아니다.

- [ ] **Step 4: 두 스킬을 고친다**

`skills/harness-authoring/SKILL.md`:
- 38행 `docs/srs/README.md` 뒤의 `(greenfield)` 를 뺀다. `docs/srs/<area>.md` 를 나란히 적는다.
- 52행 `SRS is greenfield only.` 를 지운다.

`skills/harness-init/SKILL.md`:
- 31행 `greenfield/SRS gate` 표현을 고쳐, 게이트가 greenfield 전용이 아님을 밝힌다.
- 44행 `brownfield (no SRS generated) skips this gate` 를 고친다 — brownfield 도 이 게이트를 거치되, 뼈대만 만들고 요구는 증분으로 들어온다.
- 58 · 71 · 133행의 `SRS greenfield` 표기를 정리한다.
- 보고 마지막 줄에 한 문장을 더한다: 이번 실행이 `docs/srs/` 를 새로 만들었다면 `/flow-init` 을 다시 돌려 `srs-verify` 워크플로 제안을 받으라는 안내. 이게 없으면 greenfield 사용자가 `/flow-init` 을 먼저 돌린 경우 제안을 영영 못 본다.

**두 파일 모두 `description` frontmatter 는 건드리지 않는다** — invocation eval 재측정 비용.

- [ ] **Step 5: 검사**

```bash
uv run pytest tests/skills/ -v
git diff --stat
grep -n 'description:' skills/harness-authoring/SKILL.md skills/harness-init/SKILL.md
git diff skills/harness-authoring/SKILL.md skills/harness-init/SKILL.md | grep '^[-+].*description:'
```
Expected: 테스트 PASS. 마지막 명령은 **출력이 없어야** 한다 — `description` 이 바뀌면 eval 을 다시 돌려야 한다.

- [ ] **Step 6: 크기와 산문**

```bash
wc -l rules/harness-rules.md skills/harness-authoring/SKILL.md skills/harness-init/SKILL.md
uv run python scripts/doc_style_check.py --root . --lint \
  rules/harness-rules.md skills/harness-authoring/SKILL.md skills/harness-init/SKILL.md
```
Expected: 전부 400줄 미만, 린트 PASS.

---

### Task 10: `/flow` 증분 2단계

Dev 티어에만 넣는다. 순서가 고정인 이유가 있다 — SDS 증분이 `doc-sync` 뒤로 밀리면 `PostToolUse` 훅이 `doc-sync.done` 과 `review.done` 을 지워 재실행 루프가 생긴다.

**Files:**
- Modify: `skills/flow/SKILL.md` (Dev 절, 현재 152-206행 부근)
- Test: `uv run pytest tests/skills/ -v`

**Interfaces:**
- Consumes: Task 2·3 의 `--areas`·`--next-id`
- Produces: 없음

- [ ] **Step 1: 현재 Dev 절을 읽는다**

```bash
sed -n '150,210p' skills/flow/SKILL.md
grep -n 'allowed-tools\|^description:' skills/flow/SKILL.md
```

- [ ] **Step 2: Dev 절 1번(위키 컨텍스트) 뒤에 SRS 증분을 넣는다**

번호는 `1b` 로 매겨 기존 2·3·4 를 밀지 않는다:

```markdown
1b. **Record a new requirement in the SRS first** (skip silently when `docs/srs/` is absent —
   the command prints nothing and exits 0). This runs only for a **new customer requirement**;
   implementing an existing one, a bug, or a refactor skips it. Route with
   `python3 .claude/harness-tier/scripts/srs_check.py --areas`, then take the number from
   `… --next-id docs/srs/<area>.md --kind FR` and add the FR to that file, plus a `C-NNN` in
   `docs/srs/README.md` (`--next-id docs/srs/README.md --kind C`) when the request names a
   customer need the SRS does not yet carry. **You judge two things only** — whether this is a
   new requirement, and which area it belongs to; the number comes from `--next-id` and the
   integrity from `--verify`. FAIL-OPEN: a failure here warns and does not block the commit —
   the `srs-verify` workflow holds the verdict.

   A **new** area file is the one part of this that is fail-CLOSED. Where the host has a wiki,
   give it front matter — `wiki_id` from
   `python3 .claude/harness-tier/scripts/wiki_graph.py --derive-id docs/srs/<area>.md`, a
   `title`, and a `related` edge to `srs.readme` — then rebuild with `… wiki_graph.py --build`
   and stage `graph.yaml` alongside it. Without that the commit gate's `--verify` blocks, and
   its reason names the graph rather than the step that wrote the file.
```

- [ ] **Step 3: 3번 오버레이에 SDS 증분을 넣는다**

`구현 최소화` 바로 다음, `선택적 TDD` 앞에 넣는다 — 둘 다 "계획 직후, 코드 전" 지점이다:

```markdown
   - **Record the design before the code** — right after the plan, alongside the reuse
     ladder: a new module, an integration-point contract, or a structural change goes into
     `docs/sds/` now, with its `Implemented requirements` linking the FR anchors it satisfies.
     This is the structure half; `doc-sync` reconciles the rest (sources · stale · orphans)
     AFTER the code. Doing it after `doc-sync` instead would have the `PostToolUse` hook
     delete `doc-sync.done` and `review.done`, so both would have to run again.
```

- [ ] **Step 4: Docs 절은 건드리지 않는다**

확인만 한다 — Docs 티어는 위키 컨텍스트 로드조차 건너뛰는 설계고, 문단 하나 고치려 설계 문서를 읽는 것이 티어가 막으려는 바로 그 불일치다.

```bash
sed -n '133,152p' skills/flow/SKILL.md
```
Expected: Docs 절에 SRS·SDS 증분이 없다.

- [ ] **Step 5: frontmatter 를 확인한다**

```bash
git diff skills/flow/SKILL.md | grep '^[-+].*description:'
git diff skills/flow/SKILL.md | grep '^[-+].*allowed-tools'
```
Expected: `description` 변경 없음(출력 없음). `allowed-tools` 를 늘릴지는 선택이다 — 늘리면 `srs_check.py --areas` 가 프롬프트 없이 돌지만, 경로 인자를 받는 `--next-id` 는 뒤에 `*` 가 붙어야 해서 접두 매칭이 되므로 **추가하지 않는다**(`doc-sync` 가 `--neighbors`·`--derive-id` 를 뺀 것과 같은 이유).

- [ ] **Step 6: 검사**

```bash
uv run pytest tests/skills/ -v
wc -l skills/flow/SKILL.md
uv run python scripts/doc_style_check.py --root . --lint skills/flow/SKILL.md
```
Expected: PASS, 400줄 미만.

---

### Task 11: `/flow-init` 제안 단계와 `doc-sync` 경계

렌더를 무조건 하지 않고 사용자에게 묻는다. 그리고 `doc-sync` 의 담당 경계를 한 곳으로 못박는다.

**Files:**
- Modify: `skills/flow-init/SKILL.md` (Step 2.7 부근)
- Modify: `skills/doc-sync/SKILL.md` (Mode W 절)
- Test: `uv run pytest tests/skills/ -v`

**Interfaces:**
- Consumes: Task 6 의 `--render-srs-verify`
- Produces: 없음

- [ ] **Step 1: 현재 Step 2.7 과 doc-sync Mode W 를 읽는다**

```bash
grep -n '2\.7\|check-merge-ruleset' skills/flow-init/SKILL.md | head
sed -n '123,160p;210,232p' skills/doc-sync/SKILL.md
```

- [ ] **Step 2: `/flow-init` 에 제안 단계를 넣는다**

Step 2.7 옆에, `docs/srs/` 존재를 가드로 둔다. 옵션 설명 자체가 거절 비용을 져야 한다 — `/wiki-init` 의 `wiki-verify` 제안과 같은 규율이다:

```markdown
   2.8. **srs-verify workflow** — only when `docs/srs/` exists in the checkout (without one
   there is nothing to point a workflow at). Ask via `AskUserQuestion` whether to render it.
   **The option descriptions carry what declining costs**: the commit gate never reads an
   SRS, so this workflow is the only thing that sees a dead anchor or a number two branches
   both took. Declining does not leave a lighter check, it leaves none.

   On **yes**:

   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/flow_init_setup.py" --render-srs-verify
   ```

   Relay its line. An existing `srs-verify.yml` is reported and never overwritten.

   On **no**, say plainly that nothing now checks the SRS's anchors, and that re-running
   `/flow-init` offers this again.
```

Step 의 최종 보고 목록(334행 부근 "doc-style and e2e workflows rendered-or-skipped")에 `srs-verify` 를 더한다.

- [ ] **Step 3: `doc-sync` 에 경계를 못박는다**

Mode W 절에 넣는다. 한 사실 한 곳 — `/flow` 는 증분 단계에서 구조를 쓰고, 여기는 정합만 맞춘다:

```markdown
### What this skill does not own

Structure is recorded **before** the code, by `/flow`'s Dev incremental steps: module
overview · Mermaid nodes · integration-point contracts · FR back-links. This skill runs
**after** the code and reconciles: `sources` shas, stale nodes, splits, orphans. One fact,
one place — a design decision written here would be written twice.

**An SRS document is never split mechanically.** Step 6's H2 split would break the anchors
the SDS links (`#nfr-perf` · `#c-003`) and dead-link every FR reference. When one grows past
`max_lines`, promote a whole section to its own file and fix the links with it — an explicit
migration, not a mechanical split.
```

Step 6(215행) 의 분할 지침에도 이 예외를 한 줄로 가리킨다.

- [ ] **Step 4: frontmatter 확인**

```bash
git diff skills/flow-init/SKILL.md skills/doc-sync/SKILL.md | grep '^[-+].*description:'
```
Expected: 출력 없음.

- [ ] **Step 5: 검사**

```bash
uv run pytest -q
uv run ruff check && uv run ruff format --check
wc -l skills/flow-init/SKILL.md skills/doc-sync/SKILL.md
uv run python scripts/doc_style_check.py --root . --lint \
  skills/flow-init/SKILL.md skills/doc-sync/SKILL.md
```
Expected: 전부 PASS, 둘 다 400줄 미만.

- [ ] **Step 6: 전체 회귀와 수집 id 확인**

```bash
uv run pytest -q
uv run pytest --collect-only -q | tail -3
uv run pre-commit run --all-files
git ls-files '*.md' | grep -v '^docs/superpowers/' | grep -v '^CHANGELOG\.md$' \
  | xargs wc -l | awk '$1>400 && $2!="total"'
```
Expected: 테스트 전부 통과. 마지막 명령은 `USAGE.md` · `USAGE.ko.md` · `rules/risk-tiers.md` 만 나열해야 한다 — 이 작업이 400을 넘긴 문서를 새로 만들지 않았다는 뜻이다.

---

## 마무리

전체가 초록이 되면 `/flow` 의 Dev 절차로 돌아간다: `doc-sync` 스킬 → 도메인 리뷰 에이전트(`VERDICT: PASS`/`VERDICT: FAIL` 한 줄을 명시적으로 요구) → `commit` 스킬. 커밋은 이 작업 전체를 접은 하나로 만들고, 이후 수정은 amend 한다.

`evals/` 는 돌리지 않는다. 이 계획은 어떤 스킬의 `description` 도, `rules/risk-tiers.md` 도, `wiki_graph.py` 도 건드리지 않으므로 `description_sha` 와 `outcome_sha` 가 그대로다. Task 9·10·11 을 마친 뒤 그 사실을 실제로 확인한다:

```bash
git diff --name-only HEAD | grep -E 'risk-tiers\.md|wiki_graph\.py|_harness_paths\.py'
git diff HEAD -- 'skills/*/SKILL.md' | grep '^[-+]description:'
```
Expected: 둘 다 출력 없음. 하나라도 나오면 재측정 비용이 발생했다는 뜻이므로 그 편집이 정말 필요한지 먼저 따진다.
