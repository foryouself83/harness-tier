# CI 계약 테스트(Schemathesis) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** vway-kit에 세 번째 검증 레이어 — REST API 계약 테스트(schemathesis)를 GitHub Actions로 추가하되, 협업 브랜치(dev/stage/main 등)에만 걸고 `/flow-init`이 `flow-config.contract_test`를 읽어 워크플로우를 렌더링·설치하게 한다.

**Architecture:** SOURCE 워크플로우 템플릿(플러그인 소유)에 플레이스홀더 토큰을 두고, `scripts/flow_init_setup.py`의 새 `render_workflow()`가 호스트 `flow-config.yaml`의 `contract_test` 값으로 치환해 `<host>/.github/workflows/api-contract.yml`로 쓴다. 설치는 기존 `.pre-commit-config.yaml` 패턴(없으면 생성·있으면 보고만)과 멱등성을 그대로 따른다.

**Tech Stack:** Python 3.8+ (stdlib + PyYAML), GitHub Actions, schemathesis/action@v3 (Docker), docker compose. 테스트는 `uv run pytest`.

## Global Constraints

이 절의 값은 모든 task에 암묵 적용된다(verbatim):

- **FAIL-OPEN, 단 필수도구 부재는 fail-CLOSED** — 렌더링 내부 오류가 셋업·커밋을 막지 않게 한다(보고만).
- **Windows 인코딩 방어** — 모든 파일 I/O는 `encoding="utf-8"`. stdout은 `force_utf8_io()`로 보호(기존 `main()`이 호출).
- **멱등** — match-then-skip. 대상 워크플로우가 이미 있으면 덮어쓰지 않고 보고만.
- **DRY 상수** — 경로 세그먼트는 `scripts/_vway_paths.py`의 SSOT(`CONFIG_DIR` 등)에서 가져온다. 중복 정의 금지(`rule-dry-constants`).
- **이중 경로** — 호스트 쓰기는 `host` 인자(`CLAUDE_PROJECT_DIR`) 아래, 플러그인 읽기는 `plugin` 인자(`CLAUDE_PLUGIN_ROOT`) 아래. 플러그인 디렉터리에 쓰지 않는다.
- **테스트 가능 함수** — 각 함수는 경로를 인자로 받고 `list[str]` 보고를 반환한다(기존 `copy_artifacts`/`check_precommit` 패턴).
- **린트/포맷** — `uv run ruff check && uv run ruff format --check` 통과.

---

### Task 1: SOURCE 워크플로우 템플릿 + flow-config 슬롯

**Files:**
- Create: `github/api-contract.workflow.example.yml`
- Modify: `flow-config.example.yaml` (끝에 `contract_test` 섹션 추가)

**Interfaces:**
- Produces: 템플릿 파일은 다음 플레이스홀더 토큰을 포함한다 — Task 2의 `render_workflow()`가 정확히 이 토큰을 치환한다:
  `__VWAY_BRANCHES__`, `__VWAY_ACTION_REF__`, `__VWAY_SCHEMA__`, `__VWAY_BASE_URL__`, `__VWAY_COMPOSE_FILE__`, `__VWAY_HEALTH_URL__`, `__VWAY_HEALTH_TIMEOUT__`.

- [ ] **Step 1: 워크플로우 SOURCE 템플릿 작성**

`github/api-contract.workflow.example.yml` 생성. 토큰은 치환 후에도, 치환 전에도 유효한 YAML이 되도록 배치한다(브랜치는 단일요소 리스트 토큰, URL은 따옴표 스칼라).

```yaml
# vway-kit 계약 테스트 — /flow-init 이 flow-config.contract_test 로 렌더링한 산출물.
# 직접 수정해도 /flow-upgrade 는 덮어쓰지 않고 "수동 확인"으로 보고만 한다.
# 트리거 브랜치는 contract_test.branches 에서 옴(협업 브랜치만; feature/* 제외).
name: api-contract

on:
  push:
    branches: [__VWAY_BRANCHES__]
  pull_request:
    branches: [__VWAY_BRANCHES__]

jobs:
  api-contract:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Start API server (docker compose)
        run: docker compose -f "__VWAY_COMPOSE_FILE__" up -d

      - name: Wait for health
        run: |
          timeout __VWAY_HEALTH_TIMEOUT__ sh -c \
            'until curl -sf "__VWAY_HEALTH_URL__"; do sleep 2; done'

      - name: Contract test (schemathesis)
        uses: __VWAY_ACTION_REF__
        with:
          schema: "__VWAY_SCHEMA__"
          base-url: "__VWAY_BASE_URL__"

      - name: Teardown
        if: always()
        run: docker compose -f "__VWAY_COMPOSE_FILE__" down
```

- [ ] **Step 2: `flow-config.example.yaml`에 `contract_test` 섹션 추가**

파일 끝(`doc_sync` 섹션 뒤)에 추가:

```yaml

# REST API 계약 테스트 (CI 전용 — GitHub Actions). REST API 없으면 enable:false → 미설치.
# /flow-init 이 이 값을 읽어 .github/workflows/api-contract.yml 을 렌더링한다.
contract_test:
  enable: true
  # 이 워크플로우가 동작할 브랜치 (push/PR 모두). 직접 나열 — 확장 자유.
  # GitHub Actions 브랜치 필터 문법 그대로 사용 가능 (예: 'release/**').
  # 보통 협업/promotion 브랜치. feature/* 는 넣지 않는다(무거운 검증 제외).
  branches: [dev, stage, main]
  # 셋업 시 웹 확인으로 pin (정체 도구 회피). CI는 이 고정값으로 결정적 실행.
  tool: schemathesis
  action_ref: "schemathesis/action@v3"   # 메이저 핀
  # OpenAPI 스펙 위치 (서버 URL 경로 또는 레포 내 파일 경로)
  schema: "http://localhost:8000/openapi.json"
  base_url: "http://localhost:8000"
  # 서버 기동 = docker compose
  server:
    compose_file: "docker-compose.yml"
    health_url: "http://localhost:8000/health"
    health_timeout: 60                    # 초
```

- [ ] **Step 3: YAML 유효성 확인**

Run: `uv run python -c "import yaml; yaml.safe_load(open('flow-config.example.yaml', encoding='utf-8')); yaml.safe_load(open('github/api-contract.workflow.example.yml', encoding='utf-8')); print('OK')"`
Expected: `OK` (토큰 상태에서도 두 파일 모두 유효한 YAML)

- [ ] **Step 4: Commit**

```bash
git add github/api-contract.workflow.example.yml flow-config.example.yaml
git commit -m "feat(contract-test): add workflow template and flow-config slot"
```

---

### Task 2: `render_workflow()` — flow-config로 워크플로우 렌더링

**Files:**
- Modify: `scripts/flow_init_setup.py` (새 상수 + `load_contract_config()` + `render_workflow()`)
- Test: `tests/test_flow_init_setup.py`

**Interfaces:**
- Consumes: Task 1의 템플릿 토큰, `_vway_paths.config_path(root)` (이미 존재 — `.claude/vway-kit/config/flow-config.yaml` 절대경로).
- Produces:
  - `WORKFLOW_DEST = ".github/workflows/api-contract.yml"` (str, host-relative)
  - `WORKFLOW_TEMPLATE = "github/api-contract.workflow.example.yml"` (str, plugin-relative)
  - `load_contract_config(host: Path) -> dict | None` — flow-config의 `contract_test` dict 반환(파일/섹션 부재·파싱실패 시 None)
  - `render_workflow(host: Path, plugin: Path) -> list[str]` — 보고 라인 리스트

- [ ] **Step 1: 실패 테스트 작성 — 렌더링 생성 + 치환**

`tests/test_flow_init_setup.py`에 추가. import에 `render_workflow`, `load_contract_config`를 더한다.

```python
import yaml as _yaml  # 파일 상단 import 블록에 추가


def _write_flow_config(host: Path, contract: dict) -> None:
    cfg_dir = host / ".claude" / "vway-kit" / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "flow-config.yaml").write_text(
        _yaml.safe_dump({"contract_test": contract}, allow_unicode=True), encoding="utf-8"
    )


def test_render_workflow_creates_and_substitutes(tmp_path: Path):
    _write_flow_config(
        tmp_path,
        {
            "enable": True,
            "branches": ["dev", "stage", "main"],
            "action_ref": "schemathesis/action@v3",
            "schema": "http://localhost:8000/openapi.json",
            "base_url": "http://localhost:8000",
            "server": {
                "compose_file": "docker-compose.yml",
                "health_url": "http://localhost:8000/health",
                "health_timeout": 60,
            },
        },
    )
    out = render_workflow(tmp_path, PLUGIN)
    assert any("생성" in line for line in out)
    dest = tmp_path / ".github" / "workflows" / "api-contract.yml"
    text = dest.read_text(encoding="utf-8")
    # 토큰이 모두 치환됐다
    assert "__VWAY_" not in text
    # 렌더 결과가 유효 YAML 이다(예외 없이 파싱). 주의: GitHub Actions 의 'on:' 키는
    # PyYAML 이 boolean True 키로 파싱하므로(YAML 1.1 함정) data["on"] 접근은 KeyError.
    # 의도(브랜치/액션/스키마 치환)는 텍스트로 직접 검증한다.
    _yaml.safe_load(text)
    assert "branches: [dev, stage, main]" in text
    assert "schemathesis/action@v3" in text
    assert "http://localhost:8000/openapi.json" in text
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_flow_init_setup.py::test_render_workflow_creates_and_substitutes -v`
Expected: FAIL — `ImportError: cannot import name 'render_workflow'`

- [ ] **Step 3: `render_workflow()` 구현**

`scripts/flow_init_setup.py`에 추가. `_vway_paths` import 블록에 `config_path`를 더한다(try/except 양쪽).

```python
# import 블록(try/except 양쪽)에 config_path 추가:
#   from _vway_paths import (..., config_path, ...)
#   from scripts._vway_paths import (..., config_path, ...)

# 모듈 상단 상수부(다른 상수들 옆)에 추가:
WORKFLOW_TEMPLATE = "github/api-contract.workflow.example.yml"  # SOURCE(플러그인 소유)
WORKFLOW_DEST = ".github/workflows/api-contract.yml"  # 호스트(GitHub 강제 위치 — VWAY_DIR 예외)


def load_contract_config(host: Path) -> dict | None:
    """flow-config.yaml 의 contract_test dict 를 반환(없거나 파싱 실패 시 None — FAIL-OPEN)."""
    import yaml

    cfg = config_path(host)
    if not cfg.is_file():
        return None
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return None
    ct = data.get("contract_test")
    return ct if isinstance(ct, dict) else None


def render_workflow(host: Path, plugin: Path) -> list[str]:
    """contract_test 설정으로 .github/workflows/api-contract.yml 을 렌더링한다.

    멱등·비파괴: enable=false/섹션부재면 미설치, 대상 파일이 이미 있으면 보고만
    (자동 병합·덮어쓰기 X — .pre-commit-config.yaml 과 동일 패턴). GitHub 이 위치를
    강제하므로 .github/workflows/ 는 VWAY_DIR 규칙의 예외다.
    """
    ct = load_contract_config(host)
    if ct is None:
        return ["  [=] contract_test 미설정 — 워크플로우 skip"]
    if not ct.get("enable"):
        return ["  [=] contract_test.enable=false — 워크플로우 미설치"]
    template = plugin / WORKFLOW_TEMPLATE
    if not template.is_file():
        return ["  [!] 워크플로우 템플릿 없음 — skip"]
    dest = host / WORKFLOW_DEST
    if dest.is_file():
        return [
            "  [i] .github/workflows/api-contract.yml 이미 있어 자동 병합 안 함(주석/커스텀 보존).",
            "  [i] 갱신하려면 기존 파일을 지우고 /flow-init 을 재실행하거나 직접 수정하세요.",
        ]
    branches = ct.get("branches") or ["dev", "stage", "main"]
    server = ct.get("server") or {}
    replacements = {
        "__VWAY_BRANCHES__": ", ".join(str(b) for b in branches),
        "__VWAY_ACTION_REF__": str(ct.get("action_ref", "schemathesis/action@v3")),
        "__VWAY_SCHEMA__": str(ct.get("schema", "")),
        "__VWAY_BASE_URL__": str(ct.get("base_url", "")),
        "__VWAY_COMPOSE_FILE__": str(server.get("compose_file", "docker-compose.yml")),
        "__VWAY_HEALTH_URL__": str(server.get("health_url", "")),
        "__VWAY_HEALTH_TIMEOUT__": str(server.get("health_timeout", 60)),
    }
    try:
        text = template.read_text(encoding="utf-8")
        for token, value in replacements.items():
            text = text.replace(token, value)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    except OSError as exc:
        return [f"  [!] 워크플로우 렌더링 실패(수동 확인): {exc}"]
    return ["  [+] .github/workflows/api-contract.yml 생성 (contract_test 렌더링)"]
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_flow_init_setup.py::test_render_workflow_creates_and_substitutes -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add scripts/flow_init_setup.py tests/test_flow_init_setup.py
git commit -m "feat(contract-test): render workflow from flow-config contract_test"
```

---

### Task 3: 멱등·비활성·부재 분기 테스트

**Files:**
- Test: `tests/test_flow_init_setup.py`

**Interfaces:**
- Consumes: Task 2의 `render_workflow()`, `_write_flow_config()` 헬퍼.

- [ ] **Step 1: 분기 테스트 3종 작성**

```python
def test_render_workflow_disabled(tmp_path: Path):
    _write_flow_config(tmp_path, {"enable": False, "branches": ["dev"]})
    out = render_workflow(tmp_path, PLUGIN)
    assert any("enable=false" in line for line in out)
    assert not (tmp_path / ".github" / "workflows" / "api-contract.yml").exists()


def test_render_workflow_absent_section(tmp_path: Path):
    # flow-config 자체가 없으면 미설정 — skip
    out = render_workflow(tmp_path, PLUGIN)
    assert any("미설정" in line for line in out)
    assert not (tmp_path / ".github" / "workflows" / "api-contract.yml").exists()


def test_render_workflow_idempotent_reports_only(tmp_path: Path):
    contract = {
        "enable": True,
        "branches": ["dev", "stage", "main"],
        "action_ref": "schemathesis/action@v3",
        "schema": "http://localhost:8000/openapi.json",
        "base_url": "http://localhost:8000",
        "server": {
            "compose_file": "docker-compose.yml",
            "health_url": "http://localhost:8000/health",
            "health_timeout": 60,
        },
    }
    _write_flow_config(tmp_path, contract)
    render_workflow(tmp_path, PLUGIN)  # 1차 생성
    dest = tmp_path / ".github" / "workflows" / "api-contract.yml"
    sentinel = dest.read_text(encoding="utf-8") + "\n# user edit\n"
    dest.write_text(sentinel, encoding="utf-8")  # 사용자 수정 흉내
    out = render_workflow(tmp_path, PLUGIN)  # 2차 — 보고만
    assert any("이미 있어" in line for line in out)
    assert dest.read_text(encoding="utf-8") == sentinel  # 덮어쓰지 않음
```

- [ ] **Step 2: 통과 확인**

Run: `uv run pytest tests/test_flow_init_setup.py -k render_workflow -v`
Expected: PASS (4 tests — Task 2의 것 포함)

- [ ] **Step 3: Commit**

```bash
git add tests/test_flow_init_setup.py
git commit -m "test(contract-test): cover disabled/absent/idempotent render branches"
```

---

### Task 4: `run_setup` 연결 + uninstall 안내

**Files:**
- Modify: `scripts/flow_init_setup.py` (`run_setup`에 호출 추가, `run_uninstall` 안내 추가)
- Test: `tests/test_flow_init_setup.py`

**Interfaces:**
- Consumes: Task 2의 `render_workflow(host, plugin)`.

- [ ] **Step 1: end-to-end 테스트 작성 — run_setup이 워크플로우를 만든다**

`main()`을 monkeypatch 환경변수로 구동하는 기존 패턴이 있으면 그대로, 없으면 `run_setup` 직접 호출로 검증한다.

```python
def test_run_setup_renders_workflow(tmp_path: Path, capsys):
    from scripts.flow_init_setup import run_setup

    _write_flow_config(
        tmp_path,
        {
            "enable": True,
            "branches": ["dev", "stage", "main"],
            "action_ref": "schemathesis/action@v3",
            "schema": "http://localhost:8000/openapi.json",
            "base_url": "http://localhost:8000",
            "server": {
                "compose_file": "docker-compose.yml",
                "health_url": "http://localhost:8000/health",
                "health_timeout": 60,
            },
        },
    )
    run_setup(tmp_path, PLUGIN)
    captured = capsys.readouterr().out
    assert "계약 테스트" in captured
    assert (tmp_path / ".github" / "workflows" / "api-contract.yml").is_file()
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_flow_init_setup.py::test_run_setup_renders_workflow -v`
Expected: FAIL — 워크플로우 파일이 생성되지 않음(아직 연결 전)

- [ ] **Step 3: `run_setup`에 렌더링 단계 추가**

`scripts/flow_init_setup.py`의 `run_setup`에서 `[자동 업데이트 인증]` 블록 **앞**에 삽입(플러그인 인자 `plugin`이 이미 시그니처에 있음):

```python
    print("[계약 테스트 워크플로우]")
    for line in render_workflow(host, plugin):
        print(line)
```

- [ ] **Step 4: uninstall 안내 추가**

`run_uninstall`의 `[남는 항목 — 수동 처리 안내]` 블록에 한 줄 추가(워크플로우는 호스트 소유 `.github/` 위치라 자동 삭제하지 않고 보고만 — `.pre-commit` 패턴과 일관):

```python
    print("  - .github/workflows/api-contract.yml 은 자동 삭제하지 않습니다(팀 커스텀 보존).")
    print("    계약 테스트를 끄려면 직접 제거하세요.")
```

- [ ] **Step 5: 통과 확인 + 전체 회귀**

Run: `uv run pytest tests/test_flow_init_setup.py -v`
Expected: PASS (전체)

- [ ] **Step 6: 린트 통과 확인**

Run: `uv run ruff check && uv run ruff format --check`
Expected: 통과(에러 없음)

- [ ] **Step 7: Commit**

```bash
git add scripts/flow_init_setup.py tests/test_flow_init_setup.py
git commit -m "feat(contract-test): wire render into run_setup; uninstall notice"
```

---

### Task 5: `/flow-init` 스킬 — contract_test 수집 + 도구 리서치

**Files:**
- Modify: `skills/flow-init/SKILL.md`

**Interfaces:** 없음(문서 — 리뷰로 검증).

- [ ] **Step 1: Step 1(flow-config 생성)에 contract_test 수집 추가**

[skills/flow-init/SKILL.md](../../skills/flow-init/SKILL.md)의 "Step 1 — Generate `flow-config.yaml`" 3번 항목 목록에 추가:

```markdown
   - **contract_test** (REST API 계약 테스트 — CI 전용): 먼저 `AskUserQuestion`으로
     "이 repo에 REST API가 있습니까?"를 묻는다. **아니오** → `enable: false`로 쓰고
     이하 슬롯은 생략. **예** → `branches`(기본값으로 `flow-config.branches`의
     integration/staging/production 값을 제안하되 독립 편집 가능), `schema`(OpenAPI
     스펙 URL/경로), `base_url`, `server.compose_file`/`health_url`/`health_timeout`을
     수집한다.
     - **도구 pin (셋업 시 1회)**: `harness-researcher` 에이전트로 OpenAPI 계약 테스트
       도구 후보의 **최신 유지보수 상태**를 웹 확인 → 추천(기본 `schemathesis` +
       `schemathesis/action@v3`)을 제시하고, 선택을 `tool`/`action_ref`에 **고정(pin)**한다.
       이후 CI는 이 고정값으로 결정적으로 실행된다(매 CI마다 웹 확인하지 않음).
```

- [ ] **Step 2: Step 2(mechanical setup) 보고 항목 추가**

"Step 2 — Run the mechanical setup"의 "It performs … and prints a report to relay:" 목록에 추가:

```markdown
- **Renders** `.github/workflows/api-contract.yml` from `flow-config.contract_test`
  when `enable: true` (creates if absent; if it already exists, **does NOT overwrite** —
  reports for manual review). `.github/workflows/` is GitHub's enforced location — a
  documented exception to the `.claude/vway-kit/` rule. Skips entirely when
  `enable: false` or the section is absent.
```

- [ ] **Step 3: Completion report 항목 추가**

"## Completion report" 문단에 계약 테스트 워크플로우 상태(생성/스킵-존재/미설치-disable)를 보고에 포함하도록 한 줄 덧붙인다:

```markdown
the **Step 2** script report (copied / registered / pre-commit checked / **contract-test
workflow rendered-or-skipped** / skipped, …)
```

- [ ] **Step 4: Commit**

```bash
git add skills/flow-init/SKILL.md
git commit -m "docs(flow-init): collect contract_test + pin tool via researcher"
```

---

### Task 6: `/flow-upgrade` 스킬 — 워크플로우 보고(리서치 없음)

**Files:**
- Modify: `skills/flow-upgrade/SKILL.md`

**Interfaces:** 없음(문서).

- [ ] **Step 1: refresh 보고 항목 추가**

[skills/flow-upgrade/SKILL.md](../../skills/flow-upgrade/SKILL.md)의 "Run the mechanical refresh" 보고 목록(`- **Checks** …` 뒤)에 추가. 도구 리서치는 넣지 않는다(upgrade는 비대화형·config 무손상 원칙):

```markdown
   - **Renders** the contract-test workflow only if absent; if
     `.github/workflows/api-contract.yml` already exists it is **reported, never
     overwritten** (host-owned customizations preserved). Tool re-pinning (the
     interactive web research) is **`/flow-init`'s job only** — upgrade leaves
     `flow-config.contract_test` untouched.
```

- [ ] **Step 2: Critical rules 보강(선택)**

"Critical rules" 1번(Non-destructive to host config)에 워크플로우도 포함됨을 한 구절 덧붙인다(이미 "never regenerate flow-config" 취지에 포함되나 명시):

```markdown
   ... Those are `/flow-init`'s interactive job. (The contract-test workflow is also
   never overwritten if present.)
```

- [ ] **Step 3: Commit**

```bash
git add skills/flow-upgrade/SKILL.md
git commit -m "docs(flow-upgrade): report contract-test workflow, no re-pin"
```

---

### Task 7: CLAUDE.md 예외 명시 + pre-commit 주석

**Files:**
- Modify: `CLAUDE.md`
- Modify: `pre-commit-hooks.example.yaml`

**Interfaces:** 없음(문서).

- [ ] **Step 1: CLAUDE.md Architecture에 `.github/workflows/` 예외 + 레이어 3 명시**

[CLAUDE.md](../../CLAUDE.md)의 "검증 2레이어" 항목을 **3레이어**로 갱신하고, 호스트 쓰기 예외 목록에 `.github/workflows/`를 추가한다:

```markdown
- **검증 3레이어**(독립): 정적 분석 = 호스트 `.pre-commit-config.yaml`(git-native) /
  flow 게이트 = `precommit-runner.sh`(PreToolUse, `git commit`만 self-filter) /
  **계약 테스트 = `.github/workflows/api-contract.yml`(GitHub Actions, 협업 브랜치만 —
  schemathesis, `/flow-init`이 `flow-config.contract_test`로 렌더링)**.
```

그리고 "예외는 외부 도구가 위치를 강제하는 `.gitignore`(git)·`.pre-commit-config.yaml`(pre-commit)·`.claude/settings.json`(Claude Code)뿐." 문장의 예외 목록에 `·.github/workflows/(GitHub Actions)`를 추가한다.

- [ ] **Step 2: Folder structure에 신규 파일 반영**

`CLAUDE.md`의 Folder structure의 `scripts/` 줄 부근/루트 파일 목록에 워크플로우 템플릿을 추가:

```text
github/     api-contract.workflow.example.yml   계약 테스트 워크플로우 SOURCE(/flow-init 이 렌더링)
```

- [ ] **Step 3: pre-commit-hooks.example.yaml에 참조 주석 추가**

[pre-commit-hooks.example.yaml](../../pre-commit-hooks.example.yaml) 상단 주석 블록(커밋 게이트 설명 부근)에 한 줄 추가:

```yaml
# REST API 계약 테스트(schemathesis)는 pre-commit 이 아니라 CI 레이어(.github/workflows/
# api-contract.yml — /flow-init 이 flow-config.contract_test 로 생성)에서 협업 브랜치만 돈다.
```

- [ ] **Step 4: 전체 정적 분석 확인**

Run: `uv run pre-commit run --all-files`
Expected: 통과(또는 무관한 기존 경고만)

- [ ] **Step 5: Commit**

```bash
git add CLAUDE.md pre-commit-hooks.example.yaml
git commit -m "docs: document contract-test as layer 3 and .github/workflows exception"
```

---

## Self-Review

**Spec coverage** (design §7 변경 파일 ↔ task):
- `github/api-contract.workflow.example.yml` → Task 1 ✅
- `flow-config.example.yaml` contract_test → Task 1 ✅
- `scripts/flow_init_setup.py` 렌더+설치 → Task 2·4 ✅
- `skills/flow-init/SKILL.md` → Task 5 ✅
- `skills/flow-upgrade/SKILL.md` → Task 6 ✅
- `tests/test_flow_init_setup.py` → Task 2·3·4 ✅
- `CLAUDE.md` → Task 7 ✅
- `pre-commit-hooks.example.yaml` → Task 7 ✅

design §2 핵심 결정 매핑: 트리거 브랜치(Task 1·2 `branches`), schemathesis/action(Task 1·2), 서버 compose(Task 1·2 `server`), enable 분기(Task 2·3·5), 멱등 보고만(Task 2·3), 도구 pin은 flow-init만(Task 5·6) — 모두 task로 커버됨.

**Placeholder scan:** "TBD/TODO/적절히 처리" 없음. 모든 코드 step에 실제 코드 포함. 토큰 `__VWAY_*__`은 의도된 치환 마커(Task 1 Produces에 정의, Task 2에서 소비).

**Type consistency:** `render_workflow(host, plugin) -> list[str]`, `load_contract_config(host) -> dict | None` — Task 2 정의와 Task 3·4 사용처 일치. 상수 `WORKFLOW_DEST`/`WORKFLOW_TEMPLATE`/토큰명 Task 1↔2 동일. `_write_flow_config` 헬퍼는 Task 2에서 정의되어 Task 3·4가 재사용.
