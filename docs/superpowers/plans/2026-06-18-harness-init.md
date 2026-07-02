# harness-init Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** vway-kit에 `/harness-init` 를 추가해, 프레임워크를 자동 감지하고 웹검색으로 최신 컨벤션을 끌어와 AI 하네스(.md 기본, 실설정 opt-in)를 안전하게 생성한다.

**Architecture:** 접근 A(vway-kit 네이티브). 얇은 command 오케스트레이터 + 격리 research 에이전트 + authoring 스킬(templates/+references/) + 생성규율 rule + 결정론·멱등 `harness_scaffold.py`(detect/marker-upsert/apply, pytest). harness-init은 파일만 쓰고 **커밋하지 않는다** — /flow가 거버넌스를 담당.

**Tech Stack:** Python 3.8+ (stdlib `json`/`pathlib`/`re` + PyYAML), pytest, Claude Code 플러그인 컴포넌트(.md frontmatter).

설계 SSOT: [docs/superpowers/specs/2026-06-18-harness-init-design.md](../specs/2026-06-18-harness-init-design.md)

## Global Constraints

- **경로 규율**: 읽기=`${CLAUDE_PLUGIN_ROOT}`, 쓰기=`${CLAUDE_PROJECT_DIR}`. 플러그인 디렉터리에 쓰지 않는다.
- **덮어쓰기 금지**: 기존 호스트 파일은 절대 덮어쓰지 않는다. 변경은 마커블록 upsert(전용 영역)만 허용. create는 부재 시에만.
- **harness-init은 커밋하지 않는다** (/flow 책임).
- **산출물 .md 기본**, 실설정(bandit·CI·pre-commit·실폴더 스캐폴딩·실제 `==`핀)은 항목별 consent로 opt-in.
- **검증→계획→미리보기→확정→쓰기**. 모호하면 추측 말고 질문(Karpathy).
- **컴포넌트 중복검사는 name + frontmatter `description` 까지만** 읽는다(본문 X).
- **Windows 인코딩**: `PYTHONUTF8=1`, 모든 파일 I/O `encoding="utf-8"`, stdout/stderr UTF-8 재설정.
- **Python ≥ 3.8, PyYAML 사용 가능**(repo 의존성).
- **린트/임포트 규율**(ruff `select=["E","F","I","UP"]`, line-length 100, target py312, pre-commit이 매 .py 커밋마다 ruff 실행): 모든 import는 **파일 최상단**에 isort 순서로(미사용 import 금지=F401, 코드 뒤 import 금지=E402). 조건부 `import yaml`·`import argparse`도 상수 정의 **위**에 둔다. `harness_scaffold.py`는 **런타임 3.8+** 대상이라 `from __future__ import annotations` 를 둔다(flow_gate_check.py와 동일).
- **테스트 임포트 관례**: `pythonpath=["."]` 이므로 `import scripts.harness_scaffold as hs` (sys.path 조작 금지 — test_flow_init_setup.py 와 동일).
- **flow 감지 시 프로세스 규율(PR·머지·커밋)은 risk-tiers.md 로 defer**, 하네스는 코드스타일+프레임워크 컨벤션만 emit.
- **커밋 규율**: Conventional Commits, 제목 ≤50자(비ASCII 1자), 본문 ≤72자.

---

## File Structure

- `scripts/harness_scaffold.py` — detect / marker-upsert / apply (결정론·멱등, 안전성 척추)
- `tests/test_harness_scaffold.py` — 위 스크립트 단위테스트
- `skills/harness-authoring/references/*.md` — 4종 작성법 + 필수 룰 블록(Karpathy/DRY/버전핀/보안)
- `skills/harness-authoring/templates/*.template.md` — skill/command/agent/rule/claude-md 골격
- `skills/harness-authoring/SKILL.md` — 생성 규율 + 진입점
- `agents/harness-researcher.md` — 격리 웹리서치 에이전트
- `rules/harness-rules.md` — 하네스 생성 규율 SSOT(자동주입 X)
- `commands/harness-init.md` — 대화형 오케스트레이터
- `README.md` · `USAGE.md` · `CLAUDE.md` — 신규 컴포넌트 등재(doc-sync)

### 모듈 공개 인터페이스 (`scripts/harness_scaffold.py`)

```python
def force_utf8_io() -> None: ...
def detect_state(root: Path) -> str:                 # "greenfield" | "brownfield"
def detect_frameworks(root: Path) -> list[dict]:     # [{"name","version","manifest"}]
def scan_components(claude_dir: Path) -> dict:        # {"skills":[{name,description,path}], "commands":[...], "agents":[...]}
def upsert_marker_block(path: Path, marker_id: str, body: str) -> str:  # "created"|"inserted"|"replaced"
def apply_plan(root: Path, plan: dict) -> dict:      # {"created":[],"skipped":[],"updated":[],"conflicts":[]}
def main(argv: list[str]) -> int:                    # CLI: detect|apply
```

**Plan 데이터 구조** (command가 만들어 `apply_plan`에 넘김):

```python
plan = {"files": [
    {"path": "CLAUDE.md", "action": "marker_upsert", "marker_id": "harness:baseline", "content": "<block body>"},
    {"path": ".claude/rules/baseline.md", "action": "create", "content": "..."},
]}
# action ∈ {"create", "marker_upsert"}. create는 부재 시에만 쓰고, 존재하면 conflicts에 보고(미작성).
```

---

## Task 1: 감지 — `detect_state` + `detect_frameworks`

**Files:**
- Create: `scripts/harness_scaffold.py`
- Test: `tests/test_harness_scaffold.py`

**Interfaces:**
- Produces: `force_utf8_io()`, `detect_state(root) -> str`, `detect_frameworks(root) -> list[dict]`

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_harness_scaffold.py
import json
from pathlib import Path

import scripts.harness_scaffold as hs


def test_detect_state_greenfield(tmp_path):
    (tmp_path / "README.md").write_text("# hi", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    assert hs.detect_state(tmp_path) == "greenfield"


def test_detect_state_brownfield_when_source_present(tmp_path):
    (tmp_path / "app.py").write_text("print(1)\n", encoding="utf-8")
    assert hs.detect_state(tmp_path) == "brownfield"


def test_detect_state_ignores_vendored_dirs(tmp_path):
    nm = tmp_path / "node_modules" / "x"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("//x", encoding="utf-8")
    (tmp_path / "README.md").write_text("# hi", encoding="utf-8")
    assert hs.detect_state(tmp_path) == "greenfield"


def test_detect_frameworks_package_json(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"next": "15.0.1", "react": "19.0.0"}}),
        encoding="utf-8",
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("next.js") == "15.0.1"


def test_detect_frameworks_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["fastapi==0.118.0", "uvicorn"]\n', encoding="utf-8"
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("fastapi") == "0.118.0"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_harness_scaffold.py -q`
Expected: FAIL (`ModuleNotFoundError` 또는 `AttributeError: detect_state`)

- [ ] **Step 3: 최소 구현 작성**

```python
# scripts/harness_scaffold.py
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

VENDOR_DIRS = {
    ".git", "node_modules", ".venv", "venv", "__pycache__", "dist", "build",
    ".next", "target", "vendor", ".mypy_cache", ".pytest_cache", ".idea", ".vscode",
}
SOURCE_EXTS = {
    ".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".kt",
    ".rb", ".php", ".cs", ".cpp", ".c", ".swift", ".scala", ".vue", ".svelte",
}
# 의존성 키 → 프레임워크 라벨
FRAMEWORK_SIGNATURES = {
    "next": "next.js", "react": "react", "vue": "vue", "nuxt": "nuxt",
    "svelte": "svelte", "@angular/core": "angular", "express": "express",
    "nestjs": "nestjs", "@nestjs/core": "nestjs",
    "fastapi": "fastapi", "django": "django", "flask": "flask",
}


def force_utf8_io() -> None:
    os.environ.setdefault("PYTHONUTF8", "1")
    for stream in ("stdout", "stderr"):
        s = getattr(sys, stream, None)
        if s is not None and hasattr(s, "reconfigure"):
            try:
                s.reconfigure(encoding="utf-8")
            except Exception:
                pass


def _walk_files(root: Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in VENDOR_DIRS]
        for fn in filenames:
            yield Path(dirpath) / fn


def detect_state(root: Path) -> str:
    for f in _walk_files(root):
        if f.suffix in SOURCE_EXTS:
            return "brownfield"
    return "greenfield"


def _norm_version(spec: str) -> str:
    # "==0.118.0", "^15.0.1", ">=2,<3" → 첫 숫자 버전만 추출(없으면 원문)
    m = re.search(r"\d+(?:\.\d+)*", spec or "")
    return m.group(0) if m else (spec or "").strip()


def detect_frameworks(root: Path) -> list[dict]:
    out: list[dict] = []

    pkg = root / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            deps = {}
            deps.update(data.get("dependencies", {}) or {})
            deps.update(data.get("devDependencies", {}) or {})
            for dep, ver in deps.items():
                label = FRAMEWORK_SIGNATURES.get(dep)
                if label:
                    out.append({"name": label, "version": _norm_version(str(ver)), "manifest": "package.json"})
        except Exception:
            pass

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        text = pyproject.read_text(encoding="utf-8")
        for dep, label in FRAMEWORK_SIGNATURES.items():
            m = re.search(rf"['\"]{re.escape(dep)}\s*([=<>!~^]*\s*[\d.]+)?['\"]", text)
            if m:
                out.append({"name": label, "version": _norm_version(m.group(1) or ""), "manifest": "pyproject.toml"})

    gomod = root / "go.mod"
    if gomod.is_file():
        out.append({"name": "go", "version": "", "manifest": "go.mod"})

    return out
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_harness_scaffold.py -q`
Expected: PASS (5 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/harness_scaffold.py tests/test_harness_scaffold.py
git commit -m "feat(harness): 프로젝트 상태·프레임워크 감지 추가"
```

---

## Task 2: 컴포넌트 스캔 — `scan_components` (name + description)

**Files:**
- Modify: `scripts/harness_scaffold.py`
- Test: `tests/test_harness_scaffold.py`

**Interfaces:**
- Consumes: (없음)
- Produces: `scan_components(claude_dir: Path) -> dict`

- [ ] **Step 1: 실패 테스트 작성** (기존 테스트 파일에 추가)

```python
def _write_component(path: Path, name: str, desc: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\ndescription: {desc}\n---\n\nbody\n", encoding="utf-8")


def test_scan_components_reads_name_and_description(tmp_path):
    cdir = tmp_path / ".claude"
    _write_component(cdir / "commands" / "deploy.md", "deploy", "Deploy the app")
    _write_component(cdir / "agents" / "reviewer.md", "reviewer", "Reviews code")
    _write_component(cdir / "skills" / "lint" / "SKILL.md", "lint", "Lint sources")
    result = hs.scan_components(cdir)
    assert {"name": "deploy", "description": "Deploy the app", "path": str((cdir / "commands" / "deploy.md"))} in result["commands"]
    assert result["agents"][0]["name"] == "reviewer"
    assert result["skills"][0]["description"] == "Lint sources"


def test_scan_components_missing_dirs_returns_empty(tmp_path):
    result = hs.scan_components(tmp_path / ".claude")
    assert result == {"skills": [], "commands": [], "agents": []}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_harness_scaffold.py -q`
Expected: FAIL (`AttributeError: scan_components`)

- [ ] **Step 3: 최소 구현 작성** — 아래 `try/except yaml` 블록은 **`from pathlib import Path` 바로 다음(VENDOR_DIRS 상수 위)** 에 넣어 E402 를 피한다. 함수들은 기존 코드 뒤에 추가.

```python
# (import 구역, from pathlib import Path 바로 아래)
try:
    import yaml  # PyYAML (repo 의존성)
except Exception:  # pragma: no cover
    yaml = None
```

```python
# (파일 끝, 함수 추가)
def _read_frontmatter(md_path: Path) -> dict:
    try:
        text = md_path.read_text(encoding="utf-8")
    except Exception:
        return {}
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return {}
    block = m.group(1)
    if yaml is not None:
        try:
            data = yaml.safe_load(block) or {}
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    # 폴백: name/description 만 라인 파싱
    out = {}
    for line in block.splitlines():
        mm = re.match(r"\s*(name|description)\s*:\s*(.+?)\s*$", line)
        if mm:
            out[mm.group(1)] = mm.group(2).strip().strip("'\"")
    return out


def _component_entry(md_path: Path) -> dict:
    fm = _read_frontmatter(md_path)
    return {"name": fm.get("name", ""), "description": fm.get("description", ""), "path": str(md_path)}


def scan_components(claude_dir: Path) -> dict:
    result = {"skills": [], "commands": [], "agents": []}
    cmd_dir = claude_dir / "commands"
    if cmd_dir.is_dir():
        result["commands"] = [_component_entry(p) for p in sorted(cmd_dir.glob("*.md"))]
    agt_dir = claude_dir / "agents"
    if agt_dir.is_dir():
        result["agents"] = [_component_entry(p) for p in sorted(agt_dir.glob("*.md"))]
    skl_dir = claude_dir / "skills"
    if skl_dir.is_dir():
        result["skills"] = [_component_entry(p) for p in sorted(skl_dir.glob("*/SKILL.md"))]
    return result
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_harness_scaffold.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add scripts/harness_scaffold.py tests/test_harness_scaffold.py
git commit -m "feat(harness): 컴포넌트 name+description 스캔 추가"
```

---

## Task 3: 마커블록 upsert — `upsert_marker_block`

**Files:**
- Modify: `scripts/harness_scaffold.py`
- Test: `tests/test_harness_scaffold.py`

**Interfaces:**
- Produces: `upsert_marker_block(path, marker_id, body) -> str` ("created"|"inserted"|"replaced"), 상수 `MARKER_BEGIN`/`MARKER_END` 포맷

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_marker_created_when_file_absent(tmp_path):
    p = tmp_path / "CLAUDE.md"
    assert hs.upsert_marker_block(p, "harness:baseline", "RULE A") == "created"
    text = p.read_text(encoding="utf-8")
    assert "harness:baseline BEGIN" in text and "RULE A" in text and "harness:baseline END" in text


def test_marker_inserted_when_no_marker(tmp_path):
    p = tmp_path / "CLAUDE.md"
    p.write_text("# Existing\n\nuser content\n", encoding="utf-8")
    assert hs.upsert_marker_block(p, "harness:baseline", "RULE A") == "inserted"
    text = p.read_text(encoding="utf-8")
    assert "user content" in text and "RULE A" in text


def test_marker_replaced_in_place_preserves_outside(tmp_path):
    p = tmp_path / "CLAUDE.md"
    hs.upsert_marker_block(p, "harness:baseline", "OLD")
    p.write_text("PRE\n" + p.read_text(encoding="utf-8") + "POST\n", encoding="utf-8")
    assert hs.upsert_marker_block(p, "harness:baseline", "NEW") == "replaced"
    text = p.read_text(encoding="utf-8")
    assert "NEW" in text and "OLD" not in text
    assert text.startswith("PRE") and text.rstrip().endswith("POST")


def test_marker_idempotent_same_content(tmp_path):
    p = tmp_path / "CLAUDE.md"
    hs.upsert_marker_block(p, "harness:baseline", "RULE A")
    before = p.read_text(encoding="utf-8")
    hs.upsert_marker_block(p, "harness:baseline", "RULE A")
    assert p.read_text(encoding="utf-8") == before
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_harness_scaffold.py -q`
Expected: FAIL (`AttributeError: upsert_marker_block`)

- [ ] **Step 3: 최소 구현 작성**

```python
def _marker_begin(marker_id: str) -> str:
    return f"<!-- {marker_id} BEGIN (managed by /harness-init — edits inside are overwritten) -->"


def _marker_end(marker_id: str) -> str:
    return f"<!-- {marker_id} END -->"


def upsert_marker_block(path: Path, marker_id: str, body: str) -> str:
    begin, end = _marker_begin(marker_id), _marker_end(marker_id)
    block = f"{begin}\n{body.rstrip()}\n{end}\n"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(block, encoding="utf-8")
        return "created"
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", re.DOTALL)
    if pattern.search(text):
        new_text = pattern.sub(block, text, count=1)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
        return "replaced"
    sep = "" if text.endswith("\n") else "\n"
    path.write_text(text + sep + "\n" + block, encoding="utf-8")
    return "inserted"
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_harness_scaffold.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add scripts/harness_scaffold.py tests/test_harness_scaffold.py
git commit -m "feat(harness): 마커블록 멱등 upsert 추가"
```

---

## Task 4: 계획 적용 — `apply_plan` (덮어쓰기 금지 불변식)

**Files:**
- Modify: `scripts/harness_scaffold.py`
- Test: `tests/test_harness_scaffold.py`

**Interfaces:**
- Consumes: `upsert_marker_block`
- Produces: `apply_plan(root, plan) -> {"created","skipped","updated","conflicts"}`

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_apply_creates_when_absent(tmp_path):
    plan = {"files": [{"path": ".claude/rules/baseline.md", "action": "create", "content": "RULES"}]}
    report = hs.apply_plan(tmp_path, plan)
    assert report["created"] == [".claude/rules/baseline.md"]
    assert (tmp_path / ".claude/rules/baseline.md").read_text(encoding="utf-8") == "RULES"


def test_apply_never_overwrites_existing_create(tmp_path):
    target = tmp_path / "CLAUDE.md"
    target.write_text("ORIGINAL", encoding="utf-8")
    plan = {"files": [{"path": "CLAUDE.md", "action": "create", "content": "NEW"}]}
    report = hs.apply_plan(tmp_path, plan)
    assert report["conflicts"] == ["CLAUDE.md"]
    assert report["created"] == []
    assert target.read_text(encoding="utf-8") == "ORIGINAL"  # 불변식


def test_apply_marker_upsert_updates(tmp_path):
    plan = {"files": [{"path": "CLAUDE.md", "action": "marker_upsert", "marker_id": "harness:baseline", "content": "B"}]}
    report = hs.apply_plan(tmp_path, plan)
    assert report["updated"] == ["CLAUDE.md"]
    assert "harness:baseline BEGIN" in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")


def test_apply_idempotent_rerun(tmp_path):
    plan = {"files": [
        {"path": ".claude/rules/baseline.md", "action": "create", "content": "RULES"},
        {"path": "CLAUDE.md", "action": "marker_upsert", "marker_id": "harness:baseline", "content": "B"},
    ]}
    hs.apply_plan(tmp_path, plan)
    snapshot = {p: p.read_text(encoding="utf-8") for p in tmp_path.rglob("*") if p.is_file()}
    report2 = hs.apply_plan(tmp_path, plan)
    assert report2["created"] == [] and report2["conflicts"] == [".claude/rules/baseline.md"]
    after = {p: p.read_text(encoding="utf-8") for p in tmp_path.rglob("*") if p.is_file()}
    assert snapshot == after  # 재실행해도 내용 동일
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_harness_scaffold.py -q`
Expected: FAIL (`AttributeError: apply_plan`)

- [ ] **Step 3: 최소 구현 작성**

```python
def apply_plan(root: Path, plan: dict) -> dict:
    report = {"created": [], "skipped": [], "updated": [], "conflicts": []}
    for entry in plan.get("files", []):
        rel = entry["path"]
        target = root / rel
        action = entry.get("action", "create")
        if action == "marker_upsert":
            upsert_marker_block(target, entry["marker_id"], entry.get("content", ""))
            report["updated"].append(rel)
        elif action == "create":
            if target.exists():
                report["conflicts"].append(rel)  # 덮어쓰기 금지
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(entry.get("content", ""), encoding="utf-8")
            report["created"].append(rel)
        else:
            report["skipped"].append(rel)
    return report
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_harness_scaffold.py -q`
Expected: PASS

- [ ] **Step 5: 커밋**

```bash
git add scripts/harness_scaffold.py tests/test_harness_scaffold.py
git commit -m "feat(harness): 멱등 apply_plan + 덮어쓰기 금지 불변식"
```

---

## Task 5: CLI — `detect` / `apply` 서브커맨드

**Files:**
- Modify: `scripts/harness_scaffold.py`
- Test: `tests/test_harness_scaffold.py`

**Interfaces:**
- Consumes: 전 함수
- Produces: `main(argv) -> int`, `__main__` 진입점

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_main_detect_outputs_json(tmp_path, capsys):
    (tmp_path / "app.py").write_text("x=1\n", encoding="utf-8")
    rc = hs.main(["detect", "--root", str(tmp_path)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["state"] == "brownfield"
    assert "frameworks" in out and "existing" in out


def test_main_apply_reads_plan_file(tmp_path, capsys):
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps({"files": [{"path": "a.md", "action": "create", "content": "X"}]}), encoding="utf-8")
    rc = hs.main(["apply", "--root", str(tmp_path), "--plan", str(plan_file)])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["created"] == ["a.md"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_harness_scaffold.py -q`
Expected: FAIL (`AttributeError: main`)

- [ ] **Step 3: 최소 구현 작성** — `import argparse` 는 **최상단 import 블록**(`import json` 위, isort 순서)에 추가한다. 함수들은 파일 끝에 추가.

```python
# (import 구역 최상단에 argparse 추가 — isort: argparse, json, os, re, sys)


def _detect_payload(root: Path) -> dict:
    return {
        "state": detect_state(root),
        "frameworks": detect_frameworks(root),
        "existing": scan_components(root / ".claude"),
    }


def main(argv: list[str]) -> int:
    force_utf8_io()
    parser = argparse.ArgumentParser(prog="harness_scaffold")
    sub = parser.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("detect")
    d.add_argument("--root", default=".")
    a = sub.add_parser("apply")
    a.add_argument("--root", default=".")
    a.add_argument("--plan", required=True)
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.cmd == "detect":
        print(json.dumps(_detect_payload(root), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "apply":
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        print(json.dumps(apply_plan(root, plan), ensure_ascii=False, indent=2))
        return 0
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
```

- [ ] **Step 4: 테스트 통과 + 린트**

Run: `uv run pytest tests/test_harness_scaffold.py -q && uv run ruff check scripts/harness_scaffold.py`
Expected: PASS, ruff 0 errors

- [ ] **Step 5: 커밋**

```bash
git add scripts/harness_scaffold.py tests/test_harness_scaffold.py
git commit -m "feat(harness): detect/apply CLI 진입점"
```

---

## Task 6: 필수 룰 references (Karpathy/DRY/버전핀/보안)

**Files:**
- Create: `skills/harness-authoring/references/karpathy-principles.md`
- Create: `skills/harness-authoring/references/rule-dry-constants.md`
- Create: `skills/harness-authoring/references/rule-version-pinning.md`
- Create: `skills/harness-authoring/references/security-rule.md`
- Create: `skills/harness-authoring/references/authoring-spec.md`

**Interfaces:** 생성 시 호스트 `CLAUDE.md`/`baseline.md`에 주입되는 블록 원문.

- [ ] **Step 1: `karpathy-principles.md` 작성** (검증된 4원칙 + 출처 확인 지시)

````markdown
# Karpathy CLAUDE.md 원칙 (주입 블록)

> 구현 시 실제 원전을 fetch해 최신 문구로 갱신할 것(추측 금지). 원전: Forrest Chang의
> `andrej-karpathy-skills`(Karpathy의 LLM 코딩 관찰 distill). 아래는 검증된 4원칙 요지.

1. **Think Before Coding** — 가정을 명시하고, 모호하면 추측하지 말고 질문한다.
   복수 해석이 가능하면 임의로 고르지 말고 제시한다. 더 단순한 길이 있으면 반박한다.
2. **Simplicity First** — 요청한 것만, 최소 코드로. 요청 안 한 추상화·기능·설정·
   과방어 코드 금지. 50줄로 될 일을 200줄로 쓰지 않는다.
3. **Surgical Changes** — 변경된 모든 줄이 요청에 직결되어야 한다. 건드릴 것만
   건드리고, 내가 만든 것만 정리한다.
4. **Goal-Driven Execution** — 명령을 검증 가능한 성공기준으로 바꾼다. 다단계 작업은
   검증 체크포인트가 있는 짧은 계획을 먼저 세운다.
````

- [ ] **Step 2: `rule-dry-constants.md` 작성**

````markdown
# DRY / 매직값 상수화 (주입 블록)

- **매직 넘버·매직 문자열·매직 코드를 반복하지 않는다.** 의미 있는 이름의 상수로
  추출하고 한 곳에서 정의한다.
- **같은 로직·같은 값을 복붙하지 않는다(DRY).** 두 번 이상 나타나면 공통화한다.
- 단, YAGNI 위배 금지 — 한 번만 쓰는 일회성 코드를 미리 추상화하지 않는다.
````

- [ ] **Step 3: `rule-version-pinning.md` 작성**

````markdown
# 버전 고정 (주입 블록)

- 참조하는 **패키지·라이브러리·컨테이너 이미지** 버전은 `>=`·`^`·`~`·latest 등
  범위/부동 지정 금지 → **정확히 `==`(또는 락파일·다이제스트)로 고정**한다.
- 예: `fastapi==0.118.0`, `node:22.11.0-bookworm`(다이제스트 권장),
  `react@19.0.0`. 재현 가능한 빌드를 보장한다.
- 업그레이드는 의도적·개별 변경으로 수행한다(부동 업데이트로 흘려보내지 않는다).
````

- [ ] **Step 4: `security-rule.md` 작성**

````markdown
# 기본 보안 (주입 블록)

- **시크릿·키·토큰·비밀번호를 코드/커밋에 넣지 않는다.** `.env`·시크릿 매니저로
  분리하고 `.env`·자격증명 파일은 `.gitignore` 에 둔다.
- 사용자 입력은 **신뢰하지 않는다** — 경계에서 검증·이스케이프(인젝션/XSS/경로탐색).
- 디버그/관대한 기본값(`debug=true`, `CORS *`, 와일드카드 권한)을 운영에 남기지 않는다.
- 의존성은 알려진 취약 버전을 피하고(§버전 고정) 보안 스캐너를 CI에 둔다(opt-in).
````

- [ ] **Step 5: `authoring-spec.md` 작성** (4종 작성법 + 공식문서 SSOT)

````markdown
# 컴포넌트 작성법 (SSOT: 공식문서)

모델 지식이 아니라 공식문서를 SSOT로 확인:
[plugins-reference](https://code.claude.com/docs/en/plugins-reference.md) ·
[hooks](https://code.claude.com/docs/en/hooks.md) ·
[skills](https://code.claude.com/docs/en/skills.md).

- **command** (`.claude/commands/<name>.md`): frontmatter `description`(필수),
  `argument-hint`·`allowed-tools`(선택) + 절차적 본문. 간결하게.
- **agent** (`.claude/agents/<name>.md`): frontmatter `name`·`description`(+호출 예시)
  ·`model`(선택) + 단일 책임 시스템 프롬프트.
- **skill** (`.claude/skills/<name>/SKILL.md`): frontmatter `name`·`description`
  (트리거 신호 포함) + 트리거·절차. Progressive Disclosure(상세는 references/).
- **rule** (`.claude/rules/<name>.md` 또는 CLAUDE.md 본문): 자동 로드 보장 위치에 둘 것
  — `.claude/rules/`는 기본 자동로드 안 될 수 있으니 CLAUDE.md 본문/명시 import로 건다.

**공통 규율**: 간결·lean, 사실은 SSOT 한 곳에만 두고 나머지는 링크.
````

- [ ] **Step 6: 커밋**

```bash
git add skills/harness-authoring/references/
git commit -m "feat(harness): 필수 룰·작성법 references 추가"
```

---

## Task 7: templates (skill/command/agent/rule/claude-md 골격)

**Files:**
- Create: `skills/harness-authoring/templates/command.template.md`
- Create: `skills/harness-authoring/templates/agent.template.md`
- Create: `skills/harness-authoring/templates/skill.template.md`
- Create: `skills/harness-authoring/templates/rule.template.md`
- Create: `skills/harness-authoring/templates/claude-md.template.md`

**Interfaces:** `{{PLACEHOLDER}}` 채움 골격. command가 research 결과로 채운다.

- [ ] **Step 1: `command.template.md`**

````markdown
---
description: {{ONE_LINE_PURPOSE}}
argument-hint: {{ARG_HINT_OR_REMOVE}}
allowed-tools: {{TOOLS_CSV_OR_REMOVE}}
---

# {{COMMAND_TITLE}}

{{WHAT_IT_DOES}}

## Steps
1. {{STEP_1}}
2. {{STEP_2}}
````

- [ ] **Step 2: `agent.template.md`**

````markdown
---
name: {{AGENT_NAME}}
description: {{WHEN_TO_USE_WITH_EXAMPLES}}
model: {{MODEL_OR_REMOVE}}
---

You are {{ROLE}}. {{SINGLE_RESPONSIBILITY}}

## Responsibilities
- {{R1}}

## Output
{{OUTPUT_FORMAT}}
````

- [ ] **Step 3: `skill.template.md`**

````markdown
---
name: {{SKILL_NAME}}
description: {{TRIGGER_SIGNALS_AND_PURPOSE}}
---

# {{SKILL_TITLE}}

## When
{{WHEN_TO_USE}}

## Steps
{{PROCEDURE}}
````

- [ ] **Step 4: `rule.template.md`**

````markdown
# {{RULE_TITLE}}

{{RULE_BODY}}
````

- [ ] **Step 5: `claude-md.template.md`** (필수 룰 주입 + 로드경로 보장)

````markdown
# {{PROJECT_NAME}}

{{PROJECT_OVERVIEW}}

## 프레임워크 컨벤션 ({{FRAMEWORK}} {{VERSION}})
{{FRAMEWORK_CONVENTIONS_FROM_RESEARCH}}  <!-- 출처: {{SOURCES}} -->

<!-- harness:baseline BEGIN (managed by /harness-init — edits inside are overwritten) -->
## 필수 작업 원칙
{{KARPATHY_PRINCIPLES}}
{{DRY_CONSTANTS}}
{{VERSION_PINNING}}
{{SECURITY}}
<!-- harness:baseline END -->

{{FLOW_DEFER_NOTE_IF_FLOW_DETECTED}}
````

- [ ] **Step 6: 커밋**

```bash
git add skills/harness-authoring/templates/
git commit -m "feat(harness): 4종+claude-md 생성 템플릿 추가"
```

---

## Task 8: authoring 스킬 — `SKILL.md`

**Files:**
- Create: `skills/harness-authoring/SKILL.md`

**Interfaces:** command가 진입. templates/+references/ 를 묶는 생성 규율.

- [ ] **Step 1: `SKILL.md` 작성**

````markdown
---
name: harness-authoring
description: "프레임워크에 맞는 AI 하네스(.md 컴포넌트)를 생성하는 작성 규율과 템플릿. /harness-init 가 호출. 4종(skill/command/agent/rule)+CLAUDE.md 골격을 references 의 작성법·필수룰로 채운다."
---

# harness-authoring

`/harness-init` 의 생성 엔진. `templates/`(골격)을 `references/`(작성법·필수룰)와
research 결과로 채워 호스트 하네스를 만든다.

## 원칙
- **간결·lean** — 생성 .md 는 짧게. 사실은 SSOT 한 곳, 나머지는 링크.
- **필수 룰 항상 주입** — `references/karpathy-principles.md`·`rule-dry-constants.md`·
  `rule-version-pinning.md`·`security-rule.md` 를 CLAUDE.md `harness:baseline` 블록에
  넣는다(로드경로 보장 — `.claude/rules/` 단독 배치 금지).
- **컴포넌트 작성법** — `references/authoring-spec.md`(공식문서 SSOT) 준수.
- **중복 생성 금지** — detect 의 name+description 으로 기능 중복 시 스킵/질문.
- **flow 감지 시** 프로세스 규율은 risk-tiers 로 defer, 하네스는 코드스타일+컨벤션만.

## 생성 절차
1. detect 결과 + research 결과 + 사용자 선택을 받는다.
2. 산출물별로 해당 `templates/*.template.md` 를 복제하고 플레이스홀더를 채운다.
3. 필수 룰 4블록을 `references/` 에서 읽어 CLAUDE.md 블록에 합친다.
4. `plan`(files[]) 으로 모아 `harness_scaffold.py apply` 에 넘긴다(미리보기 후).
````

- [ ] **Step 2: 커밋**

```bash
git add skills/harness-authoring/SKILL.md
git commit -m "feat(harness): authoring 스킬 추가"
```

---

## Task 9: research 에이전트 — `harness-researcher.md`

**Files:**
- Create: `agents/harness-researcher.md`

**Interfaces:** 입력=framework+version+관심사. 출력=구조화 결과+출처 URL.

- [ ] **Step 1: `harness-researcher.md` 작성**

````markdown
---
name: harness-researcher
description: Use when /harness-init needs the latest framework conventions. Given a framework + version, web-search the current folder/schema layout, best practices, and a fitting security scanner, returning a structured summary with source URLs.\n\n<example>\nContext: harness-init detected next.js 15.\nuser: "Research latest conventions for next.js 15"\nassistant: "Launching harness-researcher to gather current layout, best practices, and security tooling with sources."\n</example>
model: sonnet
---

너는 프레임워크 컨벤션 리서처다. 주어진 framework+version 에 대해 **최신** 공식
컨벤션을 웹검색으로 수집하고, **출처 URL과 함께** 구조화해 반환한다.

## 입력
- `framework`, `version`, `concerns`(folder/schema/best-practices/security)

## 절차
1. 공식 문서·릴리스 노트를 우선 검색(WebSearch → WebFetch). awesome 리스트는 보조.
2. 버전에 맞는 내용만 채택. 버전 불일치/불확실하면 **명시**(추측 금지).
3. 보안 스캐너는 생태계에 맞게(예: Python=bandit, JS=npm audit/eslint-security,
   Go=gosec) + 최소 CI 스니펫.

## 출력 (이 형식 그대로)
```
## {framework} {version} — 최신 컨벤션 (조사일 기준)
### 폴더/레이아웃
- ... (출처: URL)
### 스키마/설정 컨벤션
- ... (출처: URL)
### 베스트프랙티스 (N개)
- ... (출처: URL)
### 보안 스캐너
- 도구: <name> / CI 스니펫:
  ```
  ...
  ```
  (출처: URL)
### 취약/권장 최소버전
- ... (출처: URL) | 또는 "확인 불가"
```

## 규율
- 모든 항목에 출처. 출처 없으면 "출처 미확인"으로 표기, 지어내지 않는다.
- 간결하게. 항목당 1~2줄.
````

- [ ] **Step 2: 커밋**

```bash
git add agents/harness-researcher.md
git commit -m "feat(harness): research 에이전트 추가"
```

---

## Task 10: 생성 규율 rule — `harness-rules.md`

**Files:**
- Create: `rules/harness-rules.md`

**Interfaces:** /harness-init·authoring 스킬이 defer 하는 SSOT. **SessionStart 자동주입 안 함.**

- [ ] **Step 1: `harness-rules.md` 작성**

````markdown
# Harness Generation Rules

> 이 룰은 자동 주입되지 않는다(risk-tiers.md 와 다름). `/harness-init`·
> `harness-authoring` 스킬이 실행 시점에 defer 해 읽는 SSOT.

## 안전
1. **검증→계획→미리보기→확정→쓰기.** 어떤 파일도 미리보기·확정 전 쓰지 않는다.
2. **덮어쓰기 금지.** 기존 파일은 마커블록 upsert(전용 영역)만. create 는 부재 시만.
3. **harness-init 은 커밋하지 않는다**(/flow 책임).
4. **모호하면 질문**(Karpathy). 프레임워크 미감지·충돌 시 사용자에게 묻는다.

## 산출물
5. **.md 기본**, 실설정(bandit·CI·pre-commit·실폴더·실제 ==핀)은 항목별 opt-in.
6. **필수 룰 항상 주입**: Karpathy 4원칙 + DRY/상수 + ==버전핀 + 보안.
   **로드경로 보장** — CLAUDE.md 본문/명시 import(`.claude/rules/` 단독 금지).
7. **중복 생성 금지**: name+description 으로 기능 중복 확인.

## flow 공존
8. **flow 감지(flow-config.yaml/.claude/vway-kit/)** 시 프로세스·커밋·머지·PR 규율은
   [risk-tiers.md](risk-tiers.md) 로 defer. 하네스는 코드스타일+프레임워크 컨벤션만 emit.
9. **settings.json 훅 건드리지 않음**(게이트 아님). 보안은 워크플로/pre-commit 파일로만.
````

- [ ] **Step 2: 커밋**

```bash
git add rules/harness-rules.md
git commit -m "feat(harness): 하네스 생성 규율 SSOT 추가"
```

---

## Task 11: 오케스트레이터 command — `harness-init.md`

**Files:**
- Create: `commands/harness-init.md`

**Interfaces:** Consumes: `harness_scaffold.py`(detect/apply), `harness-researcher`(에이전트), `harness-authoring`(스킬), `references/`·`templates/`.

- [ ] **Step 1: `harness-init.md` 작성**

````markdown
---
description: 프레임워크를 감지하고 최신 컨벤션을 웹검색해 AI 하네스(.md 기본, 실설정 opt-in)를 안전하게 생성하는 마법사 — 검증→계획→미리보기→확정→쓰기, 덮어쓰기 없음
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion, Glob, Grep, Task, WebSearch, WebFetch, Skill
argument-hint: (none)
---

# Harness-Init — AI 하네스 생성 마법사

대상 프로젝트에 맞는 Claude Code 하네스를 생성한다. 산출물은 **.md 기본**이며 실제
설정(보안 스캐너·CI·폴더 스캐폴딩 등)은 **물어보고 동의 시에만** 적용한다.
**규율 SSOT**: [harness-rules.md](../rules/harness-rules.md) — 읽고 따른다(중복 금지).

## 경로
```bash
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
PLUGIN="${CLAUDE_PLUGIN_ROOT}"
```

## Step 0 — 검증/감지 (스크립트)
```bash
python3 "${PLUGIN}/scripts/harness_scaffold.py" detect --root "${ROOT}"
```
결과(state/frameworks/existing)를 사용자에게 **표로** 보여준다. flow 설치
(flow-config.yaml·.claude/vway-kit/) 여부도 보고.

## Step 1 — 인터뷰 (AskUserQuestion, 최소)
1. 감지 프레임워크/버전 확인(틀리면 정정, 미감지면 입력 요청).
2. 생성 산출물 선택: CLAUDE.md / rules(baseline+컨벤션) / skills / commands / agents / docs.
3. **실설정 opt-in**: 보안 스캐너 설치·CI 추가·실폴더 스캐폴딩·실제 버전핀 — 각각 물어봄.
4. 브라운필드 충돌(existing) 항목별: 스킵 / 사용자선택.

## Step 2 — 리서치 (에이전트, 격리)
`harness-researcher` 를 Task 로 디스패치(framework+version+concerns). 구조화 결과+출처를 받는다.
네트워크 실패 시: 지어내지 말고 경고 + 「최소 일반구조로 진행 / 중단」 선택.

## Step 3 — 생성 (authoring 스킬 + scaffold)
1. `Skill: harness-authoring` 로 templates/ 를 research+references 로 채운다.
   - 필수 룰 4블록(`references/karpathy-principles.md`·`rule-dry-constants.md`·
     `rule-version-pinning.md`·`security-rule.md`)을 CLAUDE.md `harness:baseline` 블록에 주입.
   - flow 감지 시 프로세스 규율은 risk-tiers defer 노트만 넣고 자체 프로세스 룰 emit 금지.
2. `plan`(files[]) 을 만들어 JSON 으로 저장 후 **미리보기**(생성/스킵/충돌)를 사용자에게 보여주고 확정받는다.
3. 확정 시:
   ```bash
   python3 "${PLUGIN}/scripts/harness_scaffold.py" apply --root "${ROOT}" --plan "${ROOT}/.claude/.harness/plan.json"
   ```
4. opt-in 실설정은 기존 파일 자동병합 금지 — 누락분만 안내(.pre-commit-config.yaml 등).

## Step 4 — 보고
생성/스킵/사용자보류 + 출처 URL + 후속(스캐너 설치 명령 등)을 **표로** 요약.
`.claude/.harness/manifest.json` 에 생성내역·프레임워크·출처를 기록(감사/재실행용).
**커밋하지 않는다** — 사용자에게 `/flow` 로 커밋하라고 안내.

## Critical rules
1. 덮어쓰기 금지 — 마커 upsert/부재시 create 만.
2. 미리보기·확정 전 쓰기 금지.
3. 호스트는 `${CLAUDE_PROJECT_DIR}`, 플러그인은 `${CLAUDE_PLUGIN_ROOT}` 읽기.
4. 커밋·머지·PR 규율은 risk-tiers 로 defer(flow 감지 시).
5. 모호하면 질문(Karpathy).
````

- [ ] **Step 2: frontmatter 검증** (pre-commit/수동)

Run: `uv run pre-commit run --all-files` (실패 없으면 통과)
Expected: PASS (또는 관련 무변경 Skipped)

- [ ] **Step 3: 커밋**

```bash
git add commands/harness-init.md
git commit -m "feat(harness): /harness-init 오케스트레이터 추가"
```

---

## Task 12: 문서 등재 (README/USAGE/CLAUDE.md) + doc-sync

**Files:**
- Modify: `README.md` — 커맨드 목록에 `/harness-init` 추가
- Modify: `USAGE.md` — 사용법 섹션 추가
- Modify: `CLAUDE.md` — Folder structure 트리에 신규 컴포넌트 등재

**Interfaces:** (문서)

- [ ] **Step 1: `CLAUDE.md` Folder structure 갱신**

`commands/` 줄에 `harness-init`, `agents/` 에 `harness-researcher`,
`skills/` 에 `harness-authoring`, `rules/` 에 `harness-rules.md`,
`scripts/` 에 `harness_scaffold.py` 를 한 줄씩 추가(기존 포맷에 맞춰).

- [ ] **Step 2: `README.md` / `USAGE.md` 갱신**

`/harness-init` 의 1~2줄 소개(프레임워크 감지+웹검색으로 하네스 생성, .md 기본/실설정
opt-in, 덮어쓰기 없음)와 `/flow-init` 과의 구분(거버넌스 배선 vs 하네스 생성)을 추가.

- [ ] **Step 3: doc-sync 일관성 확인**

Run: `git diff --name-only HEAD` 로 변경 문서 확인 → 상호참조 링크 정합성 점검.

- [ ] **Step 4: 커밋**

```bash
git add README.md USAGE.md CLAUDE.md
git commit -m "docs(harness): /harness-init 컴포넌트 문서 등재"
```

---

## Self-Review (작성자 체크)

**1. Spec coverage** — 산출물(.md 기본+opt-in)=Task 7·8·11, 검증/감지=Task 1·2·11,
컴포넌트 중복(name+desc)=Task 2, 최신성/웹검색=Task 9·11, 필수룰(Karpathy/DRY/버전핀/
보안)=Task 6, 로드경로 보장=Task 6·7·8·10, 덮어쓰기 금지/멱등=Task 3·4, flow 비모순=
Task 10·11, 에러처리=Task 11(리서치 실패)·4(충돌), 테스트=Task 1~5. 전 항목 매핑됨.

**2. Placeholder scan** — 템플릿의 `{{...}}` 는 의도된 골격 플레이스홀더(런타임 채움),
플랜 자체의 미정 항목 아님. 그 외 TBD/TODO 없음.

**3. Type consistency** — `detect_state`→str, `detect_frameworks`→list[dict],
`scan_components`→{skills,commands,agents}, `upsert_marker_block`→str,
`apply_plan`→{created,skipped,updated,conflicts}, plan.files[].action∈{create,
marker_upsert}. 태스크 간 시그니처·키 일관.

## 후속(범위 밖)
- manifest 기반 "버전 상승 → 변경분만 최신화" 모드
- 비-Claude 멀티타깃(AGENTS.md/Cursor) 출력
- 생성 docs 의 flow-config.doc_sync 자동 등재
