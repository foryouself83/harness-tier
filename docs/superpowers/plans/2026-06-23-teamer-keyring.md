# Teamer Credential keyring Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Teamer 마스터 id/pw를 OS 키체인(keyring)으로 옮기고 인증·API 호출을 독립 스크립트가 소유해, 비밀이 LLM 컨텍스트·트랜스크립트·평문 파일에 노출되지 않게 한다.

**Architecture:** 새 `scripts/teamer_api.py`가 keyring에서 자격증명을 읽어 인증·검색·GET·PUT을 프로세스 내부에서 수행하고 최소 JSON만 출력한다. 순수 로직(필드 보존·append·multipart·status 해석·redact·파싱)은 테스트 가능한 함수로 분리하고, keyring·HTTP는 lazy-import 레이어로 격리한다. 두 에이전트는 삭제하고 두 스킬이 스크립트를 직접 호출한다.

**Tech Stack:** Python 3.8+ 런타임(호스트 bare python), 개발/테스트는 Python 3.12 + uv + pytest, stdlib `urllib`(HTTP) + `keyring`(새 의존성), `_vway_paths` 공용 헬퍼.

## Global Constraints

- **로컬 데스크톱 전용** — CI/헤드리스 미지원, env-var fallback 없음.
- **비밀 무노출** — id/pw/token을 stdout/stderr/로그/모델 컨텍스트/평문 파일에 절대 출력 금지. 에러도 redact.
- **토큰 캐시 없음** — 매 호출 keyring 비번으로 자동 재로그인.
- **Windows 인코딩**(CLAUDE.md Invariant #2) — `force_utf8_io()` 호출, 모든 `open()`은 `encoding="utf-8"`, JSON 출력은 `json.dumps(..., ensure_ascii=False)`.
- **lazy import** — `keyring`·HTTP는 함수 내부에서 import(순수 함수 테스트가 keyring 비의존이 되도록). `_vway_paths` import 는 sibling→`scripts.` fallback 의 try/except 패턴(handoff_resolve.py 와 동일).
- **테스트 import 경로** — `from scripts.teamer_api import ...` (pyproject `pythonpath=["."]`).
- **keyring 스키마** — service=`vway-kit-teamer`, 엔트리 `id` / `password`.
- **Teamer API** — base `https://teamer.live`. 인증 `POST /api/auth/local` JSON `{username,password}`→`token`. 검색 `POST /api/new/items/getItemList?project_no=&workitem_no=&page=0&size=50&view_type=list&text=` Bearer + body `{}`. 워크플로 `GET /api/workflowAction?workflow_no=&project_no=&workitem_no=` Bearer. 업데이트 `PUT /api/new/items/{itemNo}` multipart/form-data(`itemVO.*`) + `Authorization: Bearer` + `Cookie: Admin-Token={token}; language=ko`.
- **커밋 규율** — gitlint: 제목 ≤50자, conventional, 2번째 줄 공백. 매 task 끝 커밋.

---

### Task 1: redact() — 비밀 마스킹 순수함수

**Files:**
- Create: `scripts/teamer_api.py`
- Test: `tests/test_teamer_api.py`

**Interfaces:**
- Produces: `redact(text: str, secrets: list[str]) -> str` — `text` 안의 각 secret 부분문자열을 `***`로 치환. 빈/None secret은 무시.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_teamer_api.py
from scripts.teamer_api import redact


def test_redact_masks_all_secrets():
    out = redact("user=bob token=abc123", ["bob", "abc123"])
    assert out == "user=*** token=***"


def test_redact_ignores_empty_secret():
    assert redact("hello", ["", None]) == "hello"


def test_redact_no_match_returns_input():
    assert redact("nothing here", ["secret"]) == "nothing here"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_teamer_api.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.teamer_api'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/teamer_api.py
"""Teamer.live API 클라이언트 — 자격증명을 keyring 에서 읽어 인증·검색·업데이트를
프로세스 내부에서 수행하고 최소 JSON 만 출력한다. 비밀(id/pw/token)은 stdout/stderr/
로그/모델 컨텍스트에 절대 노출하지 않는다(에러도 redact). 로컬 데스크톱 전용.

순수 로직(redact·파싱·필드보존·append·multipart·status 해석)은 테스트 가능한 함수로
분리하고, keyring·HTTP 는 함수 내부 lazy import 레이어로 격리한다.
"""

from __future__ import annotations


def redact(text: str, secrets: list[str]) -> str:
    """text 안의 각 secret 부분문자열을 '***' 로 치환. 빈/None secret 은 무시."""
    out = str(text)
    for s in secrets:
        if s:
            out = out.replace(str(s), "***")
    return out
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_teamer_api.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/teamer_api.py tests/test_teamer_api.py
git commit -m "feat(teamer): add redact helper"
```

---

### Task 2: parse_account_md() — 평문 계정파일 파서

**Files:**
- Modify: `scripts/teamer_api.py`
- Test: `tests/test_teamer_api.py`

**Interfaces:**
- Produces: `parse_account_md(text: str) -> tuple[str | None, str | None]` — `- id: X` / `- password: Y` 라인에서 (id, password) 추출. `id:` 값은 `@` 보존·verbatim. 없으면 해당 항목 None.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_teamer_api.py 에 추가
from scripts.teamer_api import parse_account_md


def test_parse_account_md_basic():
    text = "# Teamer Account\n- id: bob@vway.co.kr\n- password: pw12345!\n"
    assert parse_account_md(text) == ("bob@vway.co.kr", "pw12345!")


def test_parse_account_md_preserves_at_and_specials():
    # id 는 verbatim(@ 보존), password 의 ':' 등 특수문자 보존
    text = "- id: handle\n- password: a:b#c!\n"
    assert parse_account_md(text) == ("handle", "a:b#c!")


def test_parse_account_md_missing_returns_none():
    assert parse_account_md("# empty\n") == (None, None)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_teamer_api.py::test_parse_account_md_basic -v`
Expected: FAIL — `ImportError: cannot import name 'parse_account_md'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/teamer_api.py 에 추가
import re


def parse_account_md(text: str) -> tuple[str | None, str | None]:
    """'- id: X' / '- password: Y' 라인에서 (id, password) 추출.
    id 는 verbatim(@ 보존). 첫 ':' 뒤 전체를 값으로(password 의 ':' 보존)."""
    cid = cpw = None
    for line in text.splitlines():
        m = re.match(r"\s*-?\s*(id|password)\s*:\s*(.+?)\s*$", line, re.IGNORECASE)
        if not m:
            continue
        key, val = m.group(1).lower(), m.group(2)
        if key == "id":
            cid = val
        else:
            cpw = val
    return cid, cpw
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_teamer_api.py -v`
Expected: PASS (6 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/teamer_api.py tests/test_teamer_api.py
git commit -m "feat(teamer): add account md parser"
```

---

### Task 3: append_item_content() — 본문 append 병합

**Files:**
- Modify: `scripts/teamer_api.py`
- Test: `tests/test_teamer_api.py`

**Interfaces:**
- Produces: `append_item_content(existing: str | None, new: str) -> str` — 기존 본문 뒤에 new 를 append. 기존이 null/공백이면 new 만 반환.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_teamer_api.py 에 추가
from scripts.teamer_api import append_item_content


def test_append_to_existing():
    assert append_item_content("<p>old</p>", "<p>new</p>") == "<p>old</p><p>new</p>"


def test_append_when_existing_empty():
    assert append_item_content("", "<p>new</p>") == "<p>new</p>"
    assert append_item_content(None, "<p>new</p>") == "<p>new</p>"


def test_append_when_existing_whitespace():
    assert append_item_content("   \n  ", "<p>new</p>") == "<p>new</p>"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_teamer_api.py::test_append_to_existing -v`
Expected: FAIL — `ImportError: cannot import name 'append_item_content'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/teamer_api.py 에 추가
def append_item_content(existing: str | None, new: str) -> str:
    """기존 item_content 뒤에 new 를 append. 기존이 null/공백이면 new 만 반환."""
    base = (existing or "").strip()
    return new if not base else existing + new
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_teamer_api.py -v`
Expected: PASS (9 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/teamer_api.py tests/test_teamer_api.py
git commit -m "feat(teamer): add item_content append merge"
```

---

### Task 4: merge_preserve_fields() — GET non-null 필드 보존

**Files:**
- Modify: `scripts/teamer_api.py`
- Test: `tests/test_teamer_api.py`

**Interfaces:**
- Produces: `merge_preserve_fields(item: dict) -> dict[str, str]` — GET 항목 dict → `itemVO.*` base 필드. non-null `colXX` 전부, `item_title`→`itemVO.itemTitle`, `upper_item_no`→`itemVO.upperItemNo`, `depth`→`itemVO.depth`, `biz_workitem_item_charge_user[i].user_no`→`itemVO.chargeUserNoes[i]` 보존. `item_content`·status·override 는 제외(호출자 처리). 모든 값 str.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_teamer_api.py 에 추가
from scripts.teamer_api import merge_preserve_fields


def test_merge_preserves_non_null_cols_and_skips_null():
    item = {"col07": "2026-06-01", "col22": None, "col30": "done"}
    out = merge_preserve_fields(item)
    assert out["itemVO.col07"] == "2026-06-01"
    assert out["itemVO.col30"] == "done"
    assert "itemVO.col22" not in out


def test_merge_preserves_key_fields_and_chargers():
    item = {
        "item_title": "제목",
        "upper_item_no": 5,
        "depth": 2,
        "biz_workitem_item_charge_user": [{"user_no": 11}, {"user_no": 22}],
        "charge_user_noes": None,
    }
    out = merge_preserve_fields(item)
    assert out["itemVO.itemTitle"] == "제목"
    assert out["itemVO.upperItemNo"] == "5"
    assert out["itemVO.depth"] == "2"
    assert out["itemVO.chargeUserNoes[0]"] == "11"
    assert out["itemVO.chargeUserNoes[1]"] == "22"


def test_merge_omits_missing_optional_fields():
    out = merge_preserve_fields({"item_title": "t"})
    assert out == {"itemVO.itemTitle": "t"}
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_teamer_api.py::test_merge_preserves_non_null_cols_and_skips_null -v`
Expected: FAIL — `ImportError: cannot import name 'merge_preserve_fields'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/teamer_api.py 에 추가
def merge_preserve_fields(item: dict) -> dict[str, str]:
    """GET 항목 → itemVO.* base 필드. non-null colXX·key 필드·charge 유저 보존.
    item_content/status/override 는 제외(호출자 처리). 누락 필드는 omit(=null 처리)."""
    fields: dict[str, str] = {}
    for key, val in item.items():
        if key.startswith("col") and key[3:].isdigit() and val is not None:
            fields[f"itemVO.{key}"] = str(val)
    for src, dst in (
        ("item_title", "itemVO.itemTitle"),
        ("upper_item_no", "itemVO.upperItemNo"),
        ("depth", "itemVO.depth"),
    ):
        if item.get(src) is not None:
            fields[dst] = str(item[src])
    for i, user in enumerate(item.get("biz_workitem_item_charge_user") or []):
        uno = user.get("user_no") if isinstance(user, dict) else None
        if uno is not None:
            fields[f"itemVO.chargeUserNoes[{i}]"] = str(uno)
    return fields
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_teamer_api.py -v`
Expected: PASS (12 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/teamer_api.py tests/test_teamer_api.py
git commit -m "feat(teamer): preserve non-null GET fields"
```

---

### Task 5: resolve_status_no() — 워크플로 status 해석

**Files:**
- Modify: `scripts/teamer_api.py`
- Test: `tests/test_teamer_api.py`

**Interfaces:**
- Produces: `resolve_status_no(actions: list[dict], target_name: str) -> int` — `to_status_name == target_name` 인 항목의 `to_status_no` 반환. 미매치면 `ValueError`(가용 목록 포함).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_teamer_api.py 에 추가
import pytest

from scripts.teamer_api import resolve_status_no


def test_resolve_status_no_match():
    actions = [
        {"to_status_no": 10, "to_status_name": "진행"},
        {"to_status_no": 20, "to_status_name": "검토"},
    ]
    assert resolve_status_no(actions, "검토") == 20


def test_resolve_status_no_raises_with_available():
    actions = [{"to_status_no": 10, "to_status_name": "진행"}]
    with pytest.raises(ValueError) as e:
        resolve_status_no(actions, "완료")
    assert "진행" in str(e.value)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_teamer_api.py::test_resolve_status_no_match -v`
Expected: FAIL — `ImportError: cannot import name 'resolve_status_no'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/teamer_api.py 에 추가
def resolve_status_no(actions: list[dict], target_name: str) -> int:
    """to_status_name == target_name 인 to_status_no 반환. 미매치면 ValueError."""
    for action in actions:
        if action.get("to_status_name") == target_name:
            return action.get("to_status_no")
    available = [a.get("to_status_name") for a in actions]
    raise ValueError(f"status '{target_name}' not found; available: {available}")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_teamer_api.py -v`
Expected: PASS (14 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/teamer_api.py tests/test_teamer_api.py
git commit -m "feat(teamer): resolve workflow status no"
```

---

### Task 6: build_multipart() — UTF-8 multipart 바디

**Files:**
- Modify: `scripts/teamer_api.py`
- Test: `tests/test_teamer_api.py`

**Interfaces:**
- Produces: `build_multipart(fields: dict, boundary: str) -> bytes` — `itemVO.*` 필드맵을 multipart/form-data UTF-8 바이트로. CRLF 구분, 마지막 `--{boundary}--`. 한글 값은 UTF-8 인코딩.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_teamer_api.py 에 추가
from scripts.teamer_api import build_multipart


def test_build_multipart_structure_and_utf8():
    body = build_multipart({"itemVO.itemTitle": "제목"}, "BOUNDARY")
    assert isinstance(body, bytes)
    text = body.decode("utf-8")
    assert text.startswith("--BOUNDARY\r\n")
    assert 'Content-Disposition: form-data; name="itemVO.itemTitle"' in text
    assert "제목" in text
    assert text.endswith("--BOUNDARY--\r\n")
    # 한글이 UTF-8 바이트로 인코딩되었는지
    assert "제목".encode("utf-8") in body


def test_build_multipart_multiple_fields():
    body = build_multipart({"a": "1", "b": "2"}, "B").decode("utf-8")
    assert body.count('Content-Disposition') == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_teamer_api.py::test_build_multipart_structure_and_utf8 -v`
Expected: FAIL — `ImportError: cannot import name 'build_multipart'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/teamer_api.py 에 추가
def build_multipart(fields: dict, boundary: str) -> bytes:
    """필드맵 → multipart/form-data UTF-8 바이트(CRLF 구분). curl 대신 사용해
    Windows 비ASCII 깨짐을 피한다(명시 UTF-8 인코딩)."""
    lines: list[str] = []
    for key, val in fields.items():
        lines.append(f"--{boundary}")
        lines.append(f'Content-Disposition: form-data; name="{key}"')
        lines.append("")
        lines.append(str(val))
    lines.append(f"--{boundary}--")
    lines.append("")
    return "\r\n".join(lines).encode("utf-8")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_teamer_api.py -v`
Expected: PASS (16 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/teamer_api.py tests/test_teamer_api.py
git commit -m "feat(teamer): build utf-8 multipart body"
```

---

### Task 7: keyring 레이어 + setup() — 자격증명 저장/이전

**Files:**
- Modify: `scripts/teamer_api.py`
- Test: `tests/test_teamer_api.py`

**Interfaces:**
- Consumes: `parse_account_md` (Task 2)
- Produces:
  - `SERVICE = "vway-kit-teamer"`
  - `get_credentials() -> tuple[str, str] | None` — keyring 에서 (id, pw). 둘 중 하나라도 없으면 None.
  - `store_credentials(cid: str, cpw: str) -> None` — keyring 에 저장.
  - `setup(account_path: Path) -> str` — account_path(평문) 있으면 파싱→저장→파일삭제 후 `"migrated"`; 없으면 getpass 입력→저장 후 `"prompted"`. 비밀 미출력.

- [ ] **Step 1: Write the failing test**

```python
# tests/test_teamer_api.py 에 추가
import sys
import types
from pathlib import Path

from scripts import teamer_api


class _FakeKeyring:
    def __init__(self):
        self.store = {}

    def set_password(self, service, name, value):
        self.store[(service, name)] = value

    def get_password(self, service, name):
        return self.store.get((service, name))


def _install_fake_keyring(monkeypatch):
    fake = _FakeKeyring()
    mod = types.ModuleType("keyring")
    mod.set_password = fake.set_password
    mod.get_password = fake.get_password
    monkeypatch.setitem(sys.modules, "keyring", mod)
    return fake


def test_store_and_get_credentials(monkeypatch):
    _install_fake_keyring(monkeypatch)
    teamer_api.store_credentials("bob@x.com", "pw1")
    assert teamer_api.get_credentials() == ("bob@x.com", "pw1")


def test_get_credentials_none_when_missing(monkeypatch):
    _install_fake_keyring(monkeypatch)
    assert teamer_api.get_credentials() is None


def test_setup_migrates_and_deletes_file(monkeypatch, tmp_path):
    fake = _install_fake_keyring(monkeypatch)
    acct = tmp_path / "teamer_account.md"
    acct.write_text("- id: bob@x.com\n- password: pw1\n", encoding="utf-8")
    result = teamer_api.setup(acct)
    assert result == "migrated"
    assert fake.store[(teamer_api.SERVICE, "id")] == "bob@x.com"
    assert fake.store[(teamer_api.SERVICE, "password")] == "pw1"
    assert not acct.exists()  # 평문 파일 삭제


def test_setup_prompts_when_no_file(monkeypatch, tmp_path):
    fake = _install_fake_keyring(monkeypatch)
    monkeypatch.setattr(teamer_api, "_prompt_credentials", lambda: ("h", "p"))
    result = teamer_api.setup(tmp_path / "missing.md")
    assert result == "prompted"
    assert fake.store[(teamer_api.SERVICE, "id")] == "h"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_teamer_api.py::test_store_and_get_credentials -v`
Expected: FAIL — `AttributeError: module 'scripts.teamer_api' has no attribute 'store_credentials'`

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/teamer_api.py 에 추가 (상단 import 에 from pathlib import Path 추가)
from pathlib import Path

SERVICE = "vway-kit-teamer"


def get_credentials() -> tuple[str, str] | None:
    """keyring 에서 (id, password). 하나라도 없으면 None."""
    import keyring  # lazy: 순수 함수 테스트가 keyring 비의존이 되도록

    cid = keyring.get_password(SERVICE, "id")
    cpw = keyring.get_password(SERVICE, "password")
    if not cid or not cpw:
        return None
    return cid, cpw


def store_credentials(cid: str, cpw: str) -> None:
    """keyring 에 id/password 저장."""
    import keyring

    keyring.set_password(SERVICE, "id", cid)
    keyring.set_password(SERVICE, "password", cpw)


def _prompt_credentials() -> tuple[str, str]:
    """터미널에서 id/비번 입력(getpass). 비번은 화면에 표시되지 않는다."""
    import getpass

    cid = input("Teamer id (verbatim, @ 포함 가능): ").strip()
    cpw = getpass.getpass("Teamer password: ")
    return cid, cpw


def setup(account_path: Path) -> str:
    """account_path(평문) 있으면 이전(파싱→keyring 저장→파일삭제), 없으면 getpass 입력.
    비밀은 출력하지 않는다."""
    if account_path.is_file():
        cid, cpw = parse_account_md(account_path.read_text(encoding="utf-8"))
        if cid and cpw:
            store_credentials(cid, cpw)
            account_path.unlink()
            return "migrated"
    cid, cpw = _prompt_credentials()
    store_credentials(cid, cpw)
    return "prompted"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_teamer_api.py -v`
Expected: PASS (20 passed)

- [ ] **Step 5: Commit**

```bash
git add scripts/teamer_api.py tests/test_teamer_api.py
git commit -m "feat(teamer): keyring store and setup migration"
```

---

### Task 8: HTTP 레이어 + CLI — search/update/setup 배선

**Files:**
- Modify: `scripts/teamer_api.py`
- Modify: `pyproject.toml` (keyring 의존성 추가)

**Interfaces:**
- Consumes: 모든 Task 1–7 함수.
- Produces: `main()` — argparse 서브커맨드 `setup`/`search`/`update`. search→`[{item_no,item_id,item_title,item_content,status_name}]` JSON, update→`{item_id,item_title,item_workflow_status_no,mode}` JSON. 자격증명 미설정 시 안내 후 비차단 종료(exit 0). keyring 미설치 시 설치 안내 후 종료.

- [ ] **Step 1: pyproject.toml 에 keyring 의존성 추가**

`pyproject.toml` 의 `dependencies` 를 수정:

```toml
dependencies = ["pyyaml>=6.0", "keyring>=24"]
```

- [ ] **Step 2: HTTP 레이어 + CLI 구현 추가**

`scripts/teamer_api.py` 상단 import 블록을 보강하고(아래 첫 블록), 파일 끝에 HTTP·CLI 함수를 추가한다:

```python
# scripts/teamer_api.py — 파일 상단 import 영역(redact 위)에 추가
import json
import sys

# _vway_paths: sibling(플러그인 실행) → scripts.(테스트) fallback
try:
    from _vway_paths import force_utf8_io
except ImportError:
    from scripts._vway_paths import force_utf8_io

BASE = "https://teamer.live"

# PUT 정적 필드(에이전트 사양에서 이관 — 회사/타임존/언어 등 고정값)
_STATIC_PUT_FIELDS = {
    "itemVO.companyNo": "11",
    "itemVO.webUrl": "https://teamer.live/#",
    "itemVO.hasFiles": "false",
    "itemVO.position": "after",
    "itemVO.language": "ko",
    "itemVO.updateType": "put",
    "itemVO.userTimezone": "Asia/Seoul",
}
```

```python
# scripts/teamer_api.py — 파일 끝(순수 함수들 뒤)에 추가
def _secrets_for_redaction() -> list[str]:
    creds = get_credentials()
    return list(creds) if creds else []


def _post_json(url: str, payload: dict, token: str | None = None) -> dict:
    import urllib.request

    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str, token: str) -> dict | list:
    import urllib.request

    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {token}"}, method="GET"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def authenticate(cid: str, cpw: str) -> str:
    """POST /api/auth/local → Bearer token. 실패 시 RuntimeError(비밀 미포함)."""
    resp = _post_json(f"{BASE}/api/auth/local", {"username": cid, "password": cpw})
    token = resp.get("token") if isinstance(resp, dict) else None
    if not token:
        raise RuntimeError("authentication failed")
    return token


def search_items(token, project_no, workitem_no, text) -> list[dict]:
    import urllib.parse

    qs = urllib.parse.urlencode(
        {
            "project_no": project_no,
            "workitem_no": workitem_no,
            "page": 0,
            "size": 50,
            "view_type": "list",
            "text": text,
        }
    )
    resp = _post_json(f"{BASE}/api/new/items/getItemList?{qs}", {}, token)
    return resp.get("content", []) if isinstance(resp, dict) else []


def _minimal_item(item: dict) -> dict:
    return {
        "item_no": item.get("item_no"),
        "item_id": item.get("item_id"),
        "item_title": item.get("item_title"),
        "item_content": item.get("item_content"),
        "status_name": item.get("item_workflow_status_no_name"),
    }


def _build_put_fields(item, project_no, workitem_no, item_no, new_content,
                      col_overrides, status_no):
    """GET 보존 필드 + itemContent(append) + overrides + status + 정적 필드."""
    fields = merge_preserve_fields(item)
    fields.update(_STATIC_PUT_FIELDS)
    fields["itemVO.itemNo"] = str(item_no)
    fields["itemVO.projectNo"] = str(project_no)
    fields["itemVO.workitemNo"] = str(workitem_no)
    fields["itemVO.itemContent"] = append_item_content(item.get("item_content"), new_content)
    for col, val in (col_overrides or {}).items():
        fields[f"itemVO.{col}"] = val
    if status_no is not None:
        fields["itemVO.itemWorkflowStatusNo"] = str(status_no)
    elif item.get("item_workflow_status_no") is not None:
        fields["itemVO.itemWorkflowStatusNo"] = str(item["item_workflow_status_no"])
    return fields


def put_item(token, item_no, fields) -> dict:
    import urllib.request

    boundary = "----vwayTeamerBoundary7a6e47d"
    body = build_multipart(fields, boundary)
    headers = {
        "Authorization": f"Bearer {token}",
        "Cookie": f"Admin-Token={token}; language=ko",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }
    req = urllib.request.Request(
        f"{BASE}/api/new/items/{item_no}", data=body, headers=headers, method="PUT"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _require_credentials() -> tuple[str, str]:
    """keyring 자격증명 반환. 없으면 안내 후 비차단 종료(exit 0)."""
    creds = get_credentials()
    if creds is None:
        print(
            "Teamer 자격증명이 설정되지 않았습니다. 터미널에서 실행하세요:\n"
            '  python "%s" setup' % __file__
        )
        sys.exit(0)
    return creds


def _read_file(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _parse_col_overrides(pairs: list[str]) -> dict:
    """['col22=path', ...] → {'col22': <file 내용>}."""
    out = {}
    for pair in pairs or []:
        col, _, fpath = pair.partition("=")
        out[col] = _read_file(fpath)
    return out


def main() -> None:
    import argparse

    force_utf8_io()
    parser = argparse.ArgumentParser(prog="teamer_api")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup")

    ps = sub.add_parser("search")
    ps.add_argument("--project-no", required=True)
    ps.add_argument("--workitem-no", required=True)
    ps.add_argument("--text", required=True)

    pu = sub.add_parser("update")
    pu.add_argument("--project-no", required=True)
    pu.add_argument("--workitem-no", required=True)
    pu.add_argument("--item-no", required=True)
    pu.add_argument("--searchtext", required=True)
    pu.add_argument("--content-file", required=True)
    pu.add_argument("--col-override", action="append", default=[])
    pu.add_argument("--target-status-name")
    pu.add_argument("--workflow-no")

    args = parser.parse_args()

    try:
        if args.cmd == "setup":
            from pathlib import Path as _P

            try:
                from _vway_paths import config_path, host_root
            except ImportError:
                from scripts._vway_paths import config_path, host_root
            acct = _P(config_path(host_root())).parent / "teamer_account.md"
            result = setup(acct)
            print(json.dumps({"setup": result}, ensure_ascii=False))
            return

        cid, cpw = _require_credentials()
        token = authenticate(cid, cpw)

        if args.cmd == "search":
            items = search_items(token, args.project_no, args.workitem_no, args.text)
            print(json.dumps([_minimal_item(i) for i in items],
                             ensure_ascii=False, indent=2))
            return

        if args.cmd == "update":
            items = search_items(token, args.project_no, args.workitem_no, args.searchtext)
            match = next((i for i in items if str(i.get("item_no")) == str(args.item_no)), None)
            if match is None:
                raise RuntimeError(f"item_no {args.item_no} not found")
            status_no = None
            if args.target_status_name:
                actions = _get_json(
                    f"{BASE}/api/workflowAction?workflow_no={args.workflow_no}"
                    f"&project_no={args.project_no}&workitem_no={args.workitem_no}",
                    token,
                )
                status_no = resolve_status_no(actions, args.target_status_name)
            fields = _build_put_fields(
                match, args.project_no, args.workitem_no, args.item_no,
                _read_file(args.content_file),
                _parse_col_overrides(args.col_override), status_no,
            )
            resp = put_item(token, args.item_no, fields)
            print(json.dumps(
                {
                    "item_id": resp.get("item_id"),
                    "item_title": resp.get("item_title"),
                    "item_workflow_status_no": resp.get("item_workflow_status_no"),
                    "mode": resp.get("mode"),
                },
                ensure_ascii=False, indent=2,
            ))
            return
    except Exception as exc:  # noqa: BLE001 — 비밀 누출 방지 위해 메시지 redact 후 비차단 보고
        print(redact(str(exc), _secrets_for_redaction()), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: 전체 단위 테스트 + 린트 통과 확인**

Run: `uv run pytest tests/test_teamer_api.py -v && uv run ruff check scripts/teamer_api.py && uv run ruff format --check scripts/teamer_api.py`
Expected: 20 passed, ruff 통과. (필요 시 `uv run ruff format scripts/teamer_api.py` 후 재확인)

- [ ] **Step 4: 수동 스모크 (실네트워크 — 자동 테스트 없음, 명시)**

> HTTP 경로는 실 Teamer 자격증명·네트워크가 필요해 단위 테스트하지 않는다(스펙 §8). 사용자가 직접 검증한다.

```bash
python scripts/teamer_api.py setup        # 평문 파일 있으면 이전+삭제, 없으면 getpass
python scripts/teamer_api.py search --project-no <P> --workitem-no <W> --text <TASKID>
```
Expected: setup → `{"setup":"migrated"}` 또는 `{"setup":"prompted"}` + 평문 파일 사라짐. search → 최소 JSON 배열. 어떤 출력에도 id/pw/token 미노출.

- [ ] **Step 5: Commit**

```bash
git add scripts/teamer_api.py pyproject.toml
git commit -m "feat(teamer): http layer and cli wiring"
```

---

### Task 9: 에이전트 제거 + task-import 스킬 전환

**Files:**
- Delete: `agents/teamer-api-searcher.md`
- Delete: `agents/teamer-item-updater.md`
- Modify: `skills/task-import/SKILL.md`

**Interfaces:**
- Consumes: `teamer_api.py search` (Task 8).

- [ ] **Step 1: 두 에이전트 파일 삭제**

```bash
git rm agents/teamer-api-searcher.md agents/teamer-item-updater.md
```

- [ ] **Step 2: task-import frontmatter 의 allowed-tools 에서 Agent 제거**

`skills/task-import/SKILL.md:4` 를 수정:

```markdown
allowed-tools: Bash, Read, Write, Edit
```

- [ ] **Step 3: Execution 1·2단계를 keyring + 스크립트 호출로 교체**

`skills/task-import/SKILL.md` 의 `## Execution` 1·2단계(기존 평문 Read + searcher 호출)를 아래로 교체:

```markdown
## Execution
1. **자격증명 확인 (keyring)** — Teamer 자격증명은 OS 키체인(keyring)에서 스크립트가 직접 읽는다(평문 파일·모델 컨텍스트 노출 금지). 스킬은 id/pw 를 다루지 않는다. 미설정이면 다음 단계의 `search` 가 안내 메시지를 출력하므로, 사용자에게 터미널에서 `python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" setup` 을 실행하도록 안내하고 중단한다.
2. **Teamer 검색** — `flow-config.yaml` 의 `teamer.project_no` / `teamer.workitem_no` 를 읽어 스크립트를 직접 호출한다:
   ```bash
   python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" search \
     --project-no <teamer.project_no> --workitem-no <teamer.workitem_no> --text {task_id}
   ```
   출력은 최소 JSON 배열 `[{item_no,item_id,item_title,item_content,status_name}]`. 자격증명 미설정 안내가 출력되면 1단계 안내 후 중단. 결과가 비었으면 사용자에게 알리고 중단.
```

- [ ] **Step 4: Claude Code Integration 절의 에이전트 언급 갱신**

`skills/task-import/SKILL.md` 의 `## Claude Code Integration` 첫 줄을 수정:

```markdown
- Uses **scripts/teamer_api.py `search`** to fetch the Teamer item context (자격증명은 keyring)
```

- [ ] **Step 5: 검증 후 커밋**

Run: `git status` 로 두 에이전트 삭제 + task-import 수정 확인.

```bash
git add agents/ skills/task-import/SKILL.md
git commit -m "refactor(teamer): task-import calls script not agent"
```

---

### Task 10: task-sync 스킬 전환

**Files:**
- Modify: `skills/task-sync/SKILL.md`

**Interfaces:**
- Consumes: `teamer_api.py search` / `update` (Task 8).

- [ ] **Step 1: frontmatter allowed-tools 에서 Agent 제거**

`skills/task-sync/SKILL.md:4` 를 수정:

```markdown
allowed-tools: Bash, Read, Glob, AskUserQuestion
```

- [ ] **Step 2: 1단계(Load credentials)를 keyring 안내로 교체**

`skills/task-sync/SKILL.md` 의 `1. **Load credentials**` 블록 전체(기존 teamer_account.md Read)를 아래로 교체:

```markdown
1. **자격증명 확인 (keyring)**
   - Teamer 자격증명은 OS 키체인(keyring)에서 스크립트가 직접 읽는다(평문 파일·모델 컨텍스트 노출 금지). 스킬은 id/pw 를 다루지 않는다.
   - 6·8단계의 스크립트가 미설정 시 안내를 출력하면, 사용자에게 터미널에서 `python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" setup` 을 실행하도록 안내하고 중단한다.
```

- [ ] **Step 3: 6단계(검색·보존)를 스크립트 search 로 교체**

`skills/task-sync/SKILL.md` 의 `6. **Search Teamer item and preserve existing values**` 블록을 아래로 교체:

```markdown
6. **Teamer 항목 검색**
   - `flow-config.yaml` 의 `teamer.project_no` / `teamer.workitem_no` 를 읽어 호출:
     ```bash
     python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" search \
       --project-no <project_no> --workitem-no <workitem_no> --text {task_id}
     ```
   - 출력 `[{item_no,item_id,item_title,item_content,status_name}]` 에서 `item_no`·`item_title`·`status_name` 추출.
   - 결과가 여러 개면 사용자에게 선택받는다. 없으면 알리고 중단.
   - **필드 보존·item_content append 는 8단계의 `update` 스크립트가 내부에서 수행한다**(스킬은 보존 로직을 다루지 않는다).
```

- [ ] **Step 4: 8단계(업데이트)를 스크립트 update 로 교체**

`skills/task-sync/SKILL.md` 의 `8. **Update Teamer item**` 블록을 아래로 교체:

```markdown
8. **Teamer 항목 업데이트**
   - 생성한 본문(append 대상)은 임시 파일에 쓰고, 각 col override 도 임시 파일로 쓴 뒤 스크립트를 호출한다:
     ```bash
     python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" update \
       --project-no <project_no> --workitem-no <workitem_no> \
       --item-no <item_no> --searchtext {task_id} \
       --content-file <tmp_content.html> \
       [--col-override col22=<tmp_col22.html> ...] \
       [--target-status-name 검토 --workflow-no <teamer.workflow_no>]
     ```
   - `update` 가 내부에서 GET→non-null colXX 보존→item_content append→(target-status-name 있으면)status 해석→multipart PUT 을 수행한다.
   - 출력 `{item_id,item_title,item_workflow_status_no,mode}` 로 성공을 사용자에게 보고한다. 자격증명 미설정 안내가 출력되면 1단계 안내 후 중단.
```

- [ ] **Step 5: API Notes 의 Node 언급 갱신**

`skills/task-sync/SKILL.md` 의 `## API Notes` 에서 "use Node.js `https` module to build UTF-8 multipart body" 줄을 아래로 교체:

```markdown
- **Non-ASCII encoding**: `teamer_api.py` 가 Python `urllib` 로 UTF-8 multipart 바디를 직접 만들어 보낸다(curl/Node 불필요).
```

- [ ] **Step 6: 커밋**

```bash
git add skills/task-sync/SKILL.md
git commit -m "refactor(teamer): task-sync calls script not agent"
```

---

### Task 11: CLAUDE.md · check-deps.sh · flow_init_setup.py 갱신

**Files:**
- Modify: `CLAUDE.md`
- Modify: `scripts/check-deps.sh`
- Modify: `scripts/flow_init_setup.py`

- [ ] **Step 1: CLAUDE.md Invariant #6 재작성**

`CLAUDE.md` 의 `## Invariants` 6번 항목을 아래로 교체:

```markdown
6. **Teamer 자격증명은 keyring에서 스크립트가 읽는다** — 평문 파일·모델 컨텍스트·트랜스크립트에 id/pw/token 노출 금지(에러도 redact). `scripts/teamer_api.py`(stdlib + keyring)가 인증·검색·GET·PUT을 프로세스 내부에서 수행하고 최소 JSON만 출력한다. PUT은 multipart/form-data·UTF-8(**Python urllib**, curl/Node 아님), GET non-null colXX 전부 보존·status name→no 해석은 스크립트 내부. Teamer 번호는 `flow-config.teamer`에서 읽어 인자로 넘긴다(하드코딩 폴백 금지). 자격증명 세팅은 사용자가 터미널에서 `teamer_api.py setup`(getpass)으로만 한다(AskUserQuestion 금지).
```

- [ ] **Step 2: CLAUDE.md Folder structure 의 agents/scripts 줄 갱신**

`CLAUDE.md` 의 folder structure 에서 `agents/` 줄과 `scripts/` 줄을 수정:

```text
agents/     harness-researcher · harness-code-analyzer · harness-critic   (하네스 리서치/분석/비판)
```
그리고 `scripts/` 설명에 `teamer_api.py(keyring 자격증명 + Teamer API 클라이언트)` 를 추가한다(기존 나열 끝에 ` · teamer_api.py(...)`).

- [ ] **Step 3: CLAUDE.md config 설명의 teamer_account.md 갱신**

`CLAUDE.md` Architecture 의 `config/`(...teamer_account.md...) 언급을 "teamer_account.md(평문)는 setup 이전 후 삭제 — 자격증명은 keyring 소유" 취지로 갱신한다(해당 괄호 안 `teamer_account.md` 항목 옆에 주석).

- [ ] **Step 4: check-deps.sh 에 keyring 점검 추가**

`scripts/check-deps.sh` 의 pre-commit 점검(3번 항목) 뒤, superpowers(4번) 앞에 추가:

```bash
# 3.5) keyring (Teamer 연동 시 필요) — task-import/task-sync 자격증명 저장소. 안내만.
if command -v python3 >/dev/null 2>&1 && python3 -c "import keyring" >/dev/null 2>&1; then
  ok "keyring (Teamer 연동)"
else
  need "keyring 미설치(Teamer 연동 시 필요) — 설치: python3 -m pip install keyring"
  need "    (bare python3 환경에 설치 — uv venv 아님. 설치 후 python3 .../teamer_api.py setup)"
fi
```

- [ ] **Step 5: flow_init_setup.py 의 COPY_MAP 에서 teamer_account.md 시딩 제거**

`scripts/flow_init_setup.py` 의 `COPY_MAP` 에서 다음 줄을 삭제:

```python
    ("teamer_account.md", f"{CONFIG_DIR}/teamer_account.md"),
```
(`.gitignore` 의 `teamer_account.md` 라인은 방어적으로 **유지** — `GITIGNORE_LINES` 는 건드리지 않는다.)

- [ ] **Step 6: 영향 테스트 + 커밋**

Run: `uv run pytest tests/test_flow_init_setup.py -v`
Expected: PASS (teamer_account.md 시딩 제거로 깨지는 단언이 있으면 그 테스트의 기대값을 갱신 — COPY_MAP 에서 teamer_account.md 를 기대하던 단언 삭제).

```bash
git add CLAUDE.md scripts/check-deps.sh scripts/flow_init_setup.py tests/test_flow_init_setup.py
git commit -m "docs(teamer): keyring invariant and deps"
```

- [ ] **Step 7: ShellCheck (check-deps.sh 수정 검증)**

Run: `shellcheck scripts/check-deps.sh` (가능 환경에서). Expected: 신규 경고 없음. (CLAUDE.md: `*.sh` 수정 시 ShellCheck 검증)

---

### Task 12: README · USAGE 갱신 + 루트 평문파일 제거

**Files:**
- Modify: `README.md`
- Modify: `USAGE.md`
- Delete: `teamer_account.md` (플러그인 루트)

- [ ] **Step 1: 루트 평문 teamer_account.md 제거**

```bash
rm -f teamer_account.md   # .gitignore 되어 추적되지 않음 — 로컬 파일만 제거
```

- [ ] **Step 2: README 에이전트 표 행 제거**

`README.md:159` 의 다음 행을 삭제:

```markdown
| 에이전트 | `teamer-api-searcher` · `teamer-item-updater` | Teamer API 검색 / 업데이트 |
```

- [ ] **Step 3: README 준비물의 Teamer 안내를 keyring setup 으로 교체**

`README.md:57` 의 다음 줄을 교체:

```markdown
- **Teamer** — 최초 1회 터미널에서 `python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" setup` 실행(getpass). 자격증명은 OS 키체인(keyring)에 저장되며 평문 파일로 두지 않는다. 한 번 설정하면 세션·재부팅과 무관하게 재입력 불필요.
```

- [ ] **Step 4: README 에 "Teamer 인증 설정" 짧은 절 추가**

`README.md` 의 적절한 위치(설치/준비물 절 이후)에 추가:

```markdown
### Teamer 인증 설정

Teamer 연동(`/task-import`·`/task-sync`)은 OS 키체인(keyring)에 저장된 자격증명을 사용한다.
평문 파일이나 대화에 비밀번호를 두지 않는다.

```bash
python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" setup
```

- 기존 `teamer_account.md` 가 있으면 자동으로 keyring 으로 옮긴 뒤 그 평문 파일을 삭제한다.
- 없으면 `getpass` 로 id/비밀번호를 입력받는다(화면에 표시되지 않음).
- 최초 1회만 실행한다. 비밀번호 교체 시에만 재실행한다. `keyring` 미설치 시 `python3 -m pip install keyring`.
```
```

- [ ] **Step 5: USAGE 에이전트 표 행 제거 + §7 갱신**

`USAGE.md:84` 의 에이전트 표 행(`teamer-api-searcher · teamer-item-updater`)을 삭제하고, `USAGE.md` §7 "계정 — `.claude/vway-kit/config/teamer_account.md`" 절을 교체:

```markdown
### 계정 — OS 키체인(keyring)

최초 1회 터미널에서 `python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" setup` 을 실행한다.
기존 `teamer_account.md` 가 있으면 자동 이전 후 삭제하고, 없으면 getpass 로 입력받는다.
자격증명은 키체인에 저장되어 세션·재부팅과 무관하게 유지된다(재입력 불필요). 비밀은 평문 파일·
대화에 남지 않는다. `keyring` 미설치 시 `python3 -m pip install keyring`.
```
그리고 준비물(`USAGE.md:46`)의 `teamer_account.md` 안내도 동일 취지로 갱신한다.

- [ ] **Step 6: 커밋**

```bash
git add README.md USAGE.md teamer_account.md
git commit -m "docs(teamer): readme usage keyring setup"
```

---

## Self-Review

**Spec coverage:**
- §3 아키텍처(스크립트 소유·Node 제거·토큰캐시 없음·에이전트 삭제) → Task 1–8, 9.
- §4 인터페이스(setup/search/update I/O) → Task 7, 8.
- §5 자격증명 수명주기(setup 이전·keyring 스키마·미설정 안내·미설치 안내) → Task 7, 8.
- §6 스킬 변경(에이전트 삭제·task-import·task-sync) → Task 9, 10.
- §7 CLAUDE.md·check-deps·flow_init_setup·README·USAGE·루트파일 → Task 11, 12.
- §8 테스트(merge/append/multipart/resolve/redact + parse) → Task 1–6, 7. keyring/HTTP 격리·mock → Task 7(monkeypatch), Task 8(수동 스모크, 자동테스트 없음 명시).
- §9 잔여위험 → 설계문서에 기록(구현 산출물 아님).

**Placeholder scan:** 모든 코드 step 은 실제 코드 포함. "수동 스모크"는 네트워크 의존이라 의도적 비자동(명시). 플레이스홀더 없음.

**Type consistency:** `get_credentials`(Task7)→`_require_credentials`/`_secrets_for_redaction`(Task8) 사용 일치. `merge_preserve_fields`/`append_item_content`/`build_multipart`/`resolve_status_no`(Task3–6)→`_build_put_fields`/`put_item`(Task8) 호출 시그니처 일치. `parse_account_md`(Task2)→`setup`(Task7) 일치. `SERVICE` 상수 Task7 정의·Task8 참조 일치.
