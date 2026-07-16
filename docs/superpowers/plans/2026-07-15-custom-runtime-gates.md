# 사용자 정의 런타임 게이트(모듈 커스텀 검사) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 호스트가 `flow-config.modules[].checks`에 임의 이름의 검사를 추가하고 각 검사의 실행 타이밍(`every-commit`|`promotion`)을 선언할 수 있게 하여, 불변 정책(`flow-tiers.yaml`)을 건드리지 않고 커밋 시 자동 실행되는 커스텀 런타임 게이트를 지원한다.

**Architecture:** 런타임 게이트는 마커 시스템과 분리돼 있고 `precommit-runner.sh`는 stdout 명령을 실행하는 제네릭 실행기라, 변경은 "어떤 명령을 emit할지 정하는" `scripts/flow_gate_check.py`(`_parse_check`/`_check_cmds`/`module_commands`)에 격리된다. `checks` 값이 문자열이면 기존대로(키-이름 기본 타이밍), dict `{run, on}`이면 타이밍을 명시한다. 타이밍→게이트→범위(`every-commit`→`precommit`/변경 모듈, `promotion`→`security-scan`/전체 모듈)는 파생된다.

**Tech Stack:** Python 3.8+ · PyYAML · pytest · uv · ruff. (게이트 스크립트는 cp949 Windows 훅 런타임에서 실행됨.)

## Global Constraints

- **하위호환 절대**: 기존 host `flow-config.yaml`(문자열 `checks`)은 동작이 한 글자도 바뀌지 않아야 함. 문자열 `security`→`promotion`, 문자열 기타 키→`every-commit`. 기존 `tests/test_flow_gate_check.py`의 모든 단언이 그대로 통과해야 함.
- **Invariant #1 FAIL-OPEN**: 잘못된 `checks`/config는 차단이 아니라 건너뜀. 강한 fail-closed는 미분류 커밋·python/PyYAML 부재에만. 미인식 `on` 값은 fail-safe로 `every-commit`(더 자주) + stderr 경고.
- **Invariant #2 UTF-8**: 새 print 경로 없음(경고는 `module_commands`의 report로 반환 → `module_commands_output`이 이미 `force_utf8_io` 뒤 stderr 출력).
- **`module_commands` 반환은 2-tuple `(cmds, report)` 유지** — 기존 호출부(`module_commands_output`) 시그니처 불변.
- **커밋 규율**: 이 레포는 플러그인 자체 → consumer 동작 변경이므로 최종 커밋 type은 **`feat`**(전파). 50/72 규칙.
- **경로 이중성**: 편집 대상은 SOURCE(`flow-*` 네이밍: `scripts/flow_gate_check.py`, `flow-config.example.yaml`, `flow-tiers.yaml`, `rules/risk-tiers.md`, `skills/flow-init/`). 반면 **내 커밋을 게이팅하는 건 설치된 vway-kit 게이트**라, 내 workflow 마커는 `.claude/vway-kit/.vdev/`에 쓴다. SOURCE 편집은 실행 중인 게이트(설치 복사본)에 영향 없음 → 자기간섭 없음.
- **커밋 타이밍**: Dev 게이트가 `review.done`·`doc-sync.done` 전까지 커밋을 막으므로(fail-closed), **태스크별 커밋 금지**. Task 1–4는 "테스트 그린"으로 끝나고, **Task 5(finalize)에서 도메인 리뷰 → doc-sync → 단일 커밋**.
- **명령**: `uv run pytest` · `uv run ruff check && uv run ruff format --check`. `*.sh`를 만졌으면 ShellCheck.

> **⚠️ 실행 중 교정 — 필드명 `on` → `when`**: YAML 1.1(PyYAML)이 bare 키 `on`을 불리언 `True`로 파싱해
> `on: promotion`이 되읽히지 않는다(Task 2에서 발견). 아래 태스크 코드/예시의 `on:`은 모두 **`when:`** 으로
> 읽어라 — 실제 코드·테스트·shipped 파일은 `when`이 SSOT. 스펙 §3/§4에 근거 기록됨.

---

### Task 1: `_parse_check` / `_default_timing` — 검사 항목 파싱(순수 함수)

**Files:**
- Modify: `scripts/flow_gate_check.py` (기존 `_check_cmds` 위, 약 243행 부근에 신규 헬퍼 추가)
- Test: `tests/test_flow_gate_check.py`

**Interfaces:**
- Consumes: 없음(신규 순수 함수).
- Produces:
  - `_default_timing(key: str) -> str` — `"promotion" if key == "security" else "every-commit"`.
  - `_parse_check(key: str, val) -> tuple[str | None, str, str | None]` — `(command|None, timing, warning|None)`. `timing ∈ {"every-commit","promotion"}`.
  - 모듈 상수 `_TIMINGS = ("every-commit", "promotion")`.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_flow_gate_check.py` 끝에 추가:

```python
# ── per-check timing (_parse_check / _default_timing) ─────────────────────────────
def test_parse_check_plain_string_is_every_commit():
    assert fgc._parse_check("lint", "ruff .") == ("ruff .", "every-commit", None)


def test_parse_check_security_string_defaults_promotion():
    # back-compat: the reserved 'security' key stays promotion even as a plain string.
    assert fgc._parse_check("security", "bandit -r .") == ("bandit -r .", "promotion", None)


def test_parse_check_dict_on_promotion():
    assert fgc._parse_check("sbom", {"run": "syft .", "on": "promotion"}) == (
        "syft .",
        "promotion",
        None,
    )


def test_parse_check_dict_on_every_commit():
    assert fgc._parse_check("license", {"run": "make lic", "on": "every-commit"}) == (
        "make lic",
        "every-commit",
        None,
    )


def test_parse_check_dict_without_on_uses_key_default():
    # dict form without `on` → key-name default (security→promotion, else every-commit).
    assert fgc._parse_check("license", {"run": "make lic"}) == ("make lic", "every-commit", None)
    assert fgc._parse_check("security", {"run": "bandit ."}) == ("bandit .", "promotion", None)


def test_parse_check_unknown_on_failsafe_every_commit_with_warning():
    cmd, timing, warn = fgc._parse_check("license", {"run": "make lic", "on": "promo"})
    assert cmd == "make lic"
    assert timing == "every-commit"  # fail-safe: run more often, not less
    assert warn is not None and "license" in warn and "promo" in warn


def test_parse_check_dict_without_run_is_none():
    cmd, _timing, _warn = fgc._parse_check("license", {"on": "promotion"})
    assert cmd is None


def test_parse_check_empty_string_is_none():
    assert fgc._parse_check("lint", "")[0] is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_flow_gate_check.py -k parse_check -v`
Expected: FAIL — `AttributeError: module 'scripts.flow_gate_check' has no attribute '_parse_check'`

- [ ] **Step 3: 최소 구현** — `scripts/flow_gate_check.py`의 기존 `_check_cmds` 정의 **바로 위**에 추가:

```python
_TIMINGS = ("every-commit", "promotion")


def _default_timing(key: str) -> str:
    """Timing for a check that does not declare `on`.

    Back-compat: the reserved key ``security`` keeps its historical promotion timing; every
    other key defaults to every-commit (the historical non-security path).
    """
    return "promotion" if key == "security" else "every-commit"


def _parse_check(key: str, val: object) -> tuple[str | None, str, str | None]:
    """Parse one ``checks`` entry → ``(command|None, timing, warning|None)``. Pure (no I/O).

    A value is either a plain string (command) or an extended dict ``{run, on}``:
      - string/scalar → key-name default timing.
      - dict → ``on`` if it is a known timing, else FAIL-SAFE ``every-commit`` (bias to safety:
        run MORE often, never silently less) plus a warning surfaced on stderr. ``run`` missing
        or empty → command None (skipped). Runtime stays FAIL-OPEN (Invariant #1); strict
        validation of ``on`` is /flow-init's job.
    """
    if isinstance(val, dict):
        run = val.get("run")
        cmd = str(run) if run else None
        on = val.get("on")
        if on in _TIMINGS:
            return cmd, str(on), None
        if on is None:
            return cmd, _default_timing(key), None
        return (
            cmd,
            "every-commit",
            f"checks['{key}'].on='{on}' 알 수 없음 → every-commit 로 처리 "
            f"(허용값: {', '.join(_TIMINGS)})",
        )
    return (str(val) if val else None, _default_timing(key), None)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_flow_gate_check.py -k parse_check -v`
Expected: PASS (7 passed)

---

### Task 2: `_check_cmds` 타이밍 필터 + `module_commands` 경고 병합

**Files:**
- Modify: `scripts/flow_gate_check.py` — `_check_cmds`(시그니처 변경), `module_commands`(호출부·경고 병합)
- Test: `tests/test_flow_gate_check.py`

**Interfaces:**
- Consumes: Task 1의 `_parse_check`.
- Produces:
  - `_check_cmds(mod: dict, *, promotion: bool) -> tuple[list[str], list[str]]` — `(commands, warnings)`. `promotion=False`→every-commit 검사, `True`→promotion 검사.
  - `module_commands(root, tier, gates) -> tuple[list[str], list[str]]` — 반환 `(cmds, report)` 불변. report는 `dedup(warnings) + uncovered-report`.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_flow_gate_check.py`에 추가(기존 `_MODCFG`/`_write_modcfg` 재사용):

```python
# ── per-check timing routing in module_commands ──────────────────────────────────
_CUSTOMCFG = (
    "branches:\n  production: main\n"
    "modules:\n"
    "  - name: api\n    path: services/api/\n"
    "    checks:\n"
    "      lint: 'ruff check services/api'\n"
    "      license:\n        run: 'make license'\n        on: every-commit\n"
    "      sbom:\n        run: 'syft services/api'\n        on: promotion\n"
    "      security: 'bandit -r services/api'\n"
)


def _write_customcfg(tmp_path: Path) -> None:
    cfg = tmp_path / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-config.yaml").write_text(_CUSTOMCFG, encoding="utf-8")


def test_custom_every_commit_runs_on_changed_precommit(tmp_path: Path, monkeypatch):
    _write_customcfg(tmp_path)
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/x.py"])
    cmds, report = fgc.module_commands(tmp_path, "dev", ["precommit", "review", "doc-sync"])
    # every-commit: lint + license (custom). promotion (sbom, security) excluded on dev.
    assert cmds == ["ruff check services/api", "make license"]
    assert report == []


def test_custom_promotion_runs_all_modules_on_release(tmp_path: Path, monkeypatch):
    _write_customcfg(tmp_path)
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/x.py"])
    cmds, _ = fgc.module_commands(
        tmp_path, "release", ["precommit", "review", "security-scan", "security"]
    )
    # precommit(changed): lint, license. security-scan(all): sbom + security (both promotion).
    assert cmds == ["ruff check services/api", "make license", "syft services/api", "bandit -r services/api"]


def test_multiple_promotion_checks_one_module(tmp_path: Path, monkeypatch):
    # the pre-generalization limit (single `security` slot) is gone: sbom + security both emit.
    _write_customcfg(tmp_path)
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/x.py"])
    cmds, _ = fgc.module_commands(tmp_path, "staging", ["security-scan"])
    assert cmds == ["syft services/api", "bandit -r services/api"]


def test_unknown_on_warned_once_and_command_emitted(tmp_path: Path, monkeypatch):
    cfg = tmp_path / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-config.yaml").write_text(
        "modules:\n  - name: api\n    path: services/api/\n"
        "    checks:\n      lint:\n        run: 'ruff .'\n        on: bogus\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/x.py"])
    # release runs both passes → the module is seen twice, but the warning is de-duped to one line.
    cmds, report = fgc.module_commands(tmp_path, "release", ["precommit", "security-scan"])
    assert cmds == ["ruff ."]  # fail-safe every-commit
    warn_lines = [ln for ln in report if "bogus" in ln]
    assert len(warn_lines) == 1
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_flow_gate_check.py -k "custom or promotion_checks or unknown_on" -v`
Expected: FAIL — `_check_cmds`가 아직 `security=` 시그니처라 `make license`/`syft`가 누락되거나 TypeError.

- [ ] **Step 3: `_check_cmds` 교체** — 기존 정의를 통째로 치환:

```python
def _check_cmds(mod: dict, *, promotion: bool) -> tuple[list[str], list[str]]:
    """Module checks for the given timing → ``(commands, warnings)``.

    ``promotion=False`` → every-commit checks (changed modules); ``True`` → promotion checks
    (all modules). Each entry is a plain string or an extended ``{run, on}`` dict (see
    :func:`_parse_check`). Config authoring order preserved; empty commands skipped.
    """
    checks = mod.get("checks") or {}
    want = "promotion" if promotion else "every-commit"
    cmds: list[str] = []
    warns: list[str] = []
    for key, val in checks.items():
        cmd, timing, warn = _parse_check(key, val)
        if warn:
            warns.append(warn)
        if cmd and timing == want:
            cmds.append(cmd)
    return cmds, warns
```

- [ ] **Step 4: `module_commands`의 두 호출부 + 경고 병합 수정** — precommit/security-scan 블록을 아래로 교체(변경 모듈 매칭·uncovered 로직은 유지):

```python
    cmds: list[str] = []
    report: list[str] = []
    warns: list[str] = []
    if "precommit" in gates:
        matched, uncovered = _match_modules(_changed_files(root), modules)
        for mod in matched:
            c, w = _check_cmds(mod, promotion=False)
            cmds += c
            warns += w
        if uncovered:
            report.append(
                "다음 파일은 모듈 미커버라 사전검사 생략 — 새 모듈이면 "
                "flow-config.modules[] 에 등록하세요:"
            )
            report += [f"  - {f}" for f in uncovered]
    if "security-scan" in gates:
        for mod in modules:
            c, w = _check_cmds(mod, promotion=True)
            cmds += c
            warns += w
    # de-dup warnings (a module can appear in both passes), order-preserving; warnings lead so
    # they are visible above the uncovered report on stderr.
    seen: set[str] = set()
    deduped = [w for w in warns if not (w in seen or seen.add(w))]
    return cmds, deduped + report
```

- [ ] **Step 5: 신규 + 기존(회귀) 테스트 통과 확인**

Run: `uv run pytest tests/test_flow_gate_check.py -v`
Expected: PASS — 신규 4개 + 기존 전부(특히 `test_module_commands_dev_runs_changed_non_security`, `test_module_commands_release_adds_full_security`, `test_module_commands_docs_empty`가 하위호환으로 그대로 통과).

---

### Task 3: config 템플릿 + 예시 + 예시 회귀 테스트

**Files:**
- Modify: `flow-config.example.yaml` (주석 19–24행 + api 모듈 checks)
- Test: `tests/test_flow_gate_check.py`

**Interfaces:**
- Consumes: Task 2의 `module_commands`.
- Produces: 없음(문서/설정 + 회귀 가드).

- [ ] **Step 1: 예시 회귀 테스트 작성** — 배포되는 example이 유효 YAML이고 커스텀 검사가 의도대로 라우팅되는지 고정:

```python
def test_shipped_example_config_custom_check_routing(monkeypatch):
    # the shipped example must stay valid and demonstrate a custom every-commit check.
    import yaml

    root = Path(__file__).resolve().parent.parent
    data = yaml.safe_load((root / "flow-config.example.yaml").read_text(encoding="utf-8"))
    api = next(m for m in data["modules"] if m["name"] == "api")
    cmd, timing, warn = fgc._parse_check("license", api["checks"]["license"])
    assert warn is None
    assert timing in fgc._TIMINGS
    assert cmd  # non-empty command
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_flow_gate_check.py -k shipped_example_config -v`
Expected: FAIL — `KeyError: 'license'` (예시에 아직 커스텀 검사 없음).

- [ ] **Step 3: `flow-config.example.yaml` 편집**

(a) 주석 블록(현행 19–24행)을 교체:

```yaml
# Per-module pre-checks. Each key under `checks` is a check; its VALUE is either a command
# string or an extended form `{ run: <cmd>, on: every-commit | promotion }`.
#   - string value  → command; timing defaults by key name (`security` → promotion, else every-commit).
#   - dict value     → declare timing explicitly with `on`. Add your OWN keys freely (license, sbom, …).
# Timing → gate → scope (derived, not chosen separately):
#   every-commit → `precommit` gate, CHANGED modules (dev/staging/release, every commit).
#   promotion    → `security-scan` gate, ALL modules (staging/release promotion).
# NOTE: timing is bound to that gate EXISTING in the tier — docs tier has neither, so custom
# checks never run on a docs commit. /flow-init drafts these; a human edits them.
```

(b) `api` 모듈 `checks`에 커스텀 예시 2개 추가(기존 lint/static/import_lint/test/security 아래):

```yaml
      # custom checks (host-defined) — add your own keys:
      license:                                   # runs every commit on changed modules
        run: "uv run pip-licenses --fail-on 'GPL'"
        on: every-commit
      sbom:                                      # runs only on staging/release promotion, all modules
        run: "uv run cyclonedx-py environment -o sbom.json"
        on: promotion
```

- [ ] **Step 4: 테스트 통과 + 예시 YAML 유효성 확인**

Run: `uv run pytest tests/test_flow_gate_check.py -k shipped_example_config -v`
Expected: PASS

---

### Task 4: 문서·주석 갱신(SSOT 정합)

**Files:**
- Modify: `scripts/_harness_paths.py` (RUNTIME_GATES 주석) · `flow-tiers.yaml` (dev/staging description) · `scripts/precommit-runner.sh` (헤더 주석) · `skills/flow-init/SKILL.md` · `rules/risk-tiers.md` (Gate glossary) · `USAGE.md` · `USAGE.ko.md`

**Interfaces:** 없음(프로세스/SSOT 문서).

- [ ] **Step 1: `scripts/_harness_paths.py`** — RUNTIME_GATES 주석(약 61–69행)을 타이밍 버킷 관점으로 갱신. 핵심 문구:

  - `precommit`: every-commit 타이밍 버킷 — 변경 모듈의 every-commit 검사(lint/static/import_lint/test + 사용자 커스텀 `on: every-commit`).
  - `security-scan`: promotion 타이밍 버킷 — 전체 모듈의 promotion 검사(`security` + 사용자 커스텀 `on: promotion`).
  - 튜플 값 `("precommit", "security-scan")` 자체는 **무변경**.

- [ ] **Step 2: `flow-tiers.yaml`** — dev description을 일반화(정책 매핑 무변경):

  - dev: `"Changes that include code (precommit = every-commit module checks on changed modules)"`
  - (staging/release는 그대로 두되, 필요 시 "security-scan = promotion module checks on all modules" 뉘앙스로.)

- [ ] **Step 3: `scripts/precommit-runner.sh`** — 헤더 주석의 `2) module pre-check — lint/static/import_lint/test …` 문구를 "every-commit module checks (changed) + promotion checks (all) on promotion"으로 정정. **코드는 무변경**(제네릭 실행기). `.sh`를 만졌으므로 Task 5에서 ShellCheck.

- [ ] **Step 4: `skills/flow-init/SKILL.md`** — 모듈 checks 추론 지침(약 240–243행)에 다음을 추가:

  - `checks` 키는 고정 어휘가 아님 — 호스트가 임의 키(license/sbom/secret-scan…)를 추가 가능.
  - 확장 형식 `{ run, on }`; `on ∈ {every-commit, promotion}`을 **검증**(그 외 값은 경고 + every-commit fallback되므로 오타 주의).
  - 타이밍 매핑: every-commit→변경 모듈 매 커밋 / promotion→전체 모듈 승격. docs 티어는 검사 미실행.

- [ ] **Step 5: `rules/risk-tiers.md`** — Gate glossary의 Runtime gates 항목(약 48–53행)을 갱신:

  - `precommit` = **every-commit 타이밍 버킷**(변경 모듈의 every-commit 검사), `security-scan` = **promotion 타이밍 버킷**(전체 모듈의 promotion 검사).
  - "호스트는 `flow-config.modules[].checks`에 임의 키 + `on:`으로 커스텀 런타임 검사를 추가할 수 있다" 1–2줄.
  - **타이밍은 해당 게이트가 그 티어에 존재하는지에 종속**(docs 티어는 둘 다 없고, `module_commands`가 docs를 단락 → docs 커밋엔 커스텀 검사 미적용) 명시.
  - 강제 범위 재확인: 이 검사들은 기존 `precommit`과 동일하게 **Claude 세션 커밋(layer-2)만** 강제(터미널/CI 커밋 비강제).

- [ ] **Step 6: `USAGE.md` / `USAGE.ko.md`** — 게이트/검사 표(약 85–88행)를 일반화:

  - `USAGE.ko.md`: `| lint · static · import_lint · test | 변경 모듈, 매 커밋(Dev 게이트) |` 행을 "every-commit 검사(기본 + 커스텀 `on: every-commit`) — 변경 모듈, 매 커밋"으로, 그리고 promotion 행 추가: "promotion 검사(`security` + 커스텀 `on: promotion`) — 전체 모듈, staging/release 승격".
  - `USAGE.md`: 동일 내용 영어. 두 파일의 표 구조 일치 유지.

- [ ] **Step 7: 전체 스위트 그린(문서 변경이 테스트를 깨지 않았는지)**

Run: `uv run pytest`
Expected: PASS (전부)

---

### Task 5: 검증 → 도메인 리뷰 → doc-sync → 단일 커밋 (finalize)

**Files:**
- Marker(작업용, vway-kit 경로): `.claude/vway-kit/.vdev/review.done` · `.claude/vway-kit/.vdev/doc-sync.done`
- Commit: 위 모든 변경 + 스펙 + 이 플랜

**Interfaces:** 없음.

- [ ] **Step 1: 정적 분석 & 전체 테스트**

Run:
```bash
uv run ruff check && uv run ruff format --check
uv run pytest
```
Expected: 모두 PASS. `scripts/precommit-runner.sh`를 만졌으므로 ShellCheck도 수행(`uv run pre-commit run --all-files`로 일괄 확인).

- [ ] **Step 2: verification-before-completion(실동작 확인)** — DRYRUN으로 커스텀 검사가 emit되는지 실제 확인:

```bash
HARNESS_PRECOMMIT_DRYRUN=1 만 필요치 않음 — 단위로 확인:
uv run python -c "import sys; sys.argv=['x']; import scripts.flow_gate_check as f; print(f._parse_check('license', {'run':'make lic','on':'promotion'}))"
```
Expected: `('make lic', 'promotion', None)`. (게이트 파싱이 실제 값으로 동작함을 눈으로 확인.)

- [ ] **Step 3: 도메인 리뷰(독립 `general-purpose` 에이전트)** — 별도 컨텍스트로 `flow-config.review_checklist` 관점(회귀, 하위호환, cp949/UTF-8, fail-open 불변, 타이밍 라우팅 정확성) 리뷰. 통과 시:

```bash
touch .claude/vway-kit/.vdev/review.done
```

- [ ] **Step 4: doc-sync** — `doc-sync` 스킬로 문서 세트(루트 CLAUDE.md·rules·USAGE) 정합화 및 code↔doc drift 반영. 통과 시:

```bash
touch .claude/vway-kit/.vdev/doc-sync.done
```

- [ ] **Step 5: 단일 커밋(feat)** — 변경 파일만 스테이징 후 커밋(게이트가 review.done·doc-sync.done 확인 후 통과):

```bash
git add scripts/flow_gate_check.py scripts/_harness_paths.py scripts/precommit-runner.sh \
  flow-config.example.yaml flow-tiers.yaml skills/flow-init/SKILL.md rules/risk-tiers.md \
  USAGE.md USAGE.ko.md tests/test_flow_gate_check.py \
  docs/superpowers/specs/2026-07-15-custom-runtime-gates-design.md \
  docs/superpowers/plans/2026-07-15-custom-runtime-gates.md
git commit -m "feat(flow): per-check timing for custom module gates

- checks value now string or {run, when: every-commit|promotion}.
- every-commit → precommit/changed; promotion → security-scan/all.
- security key kept as promotion default (back-compat).
- unknown on → fail-safe every-commit + stderr warning."
```
Expected: 커밋 성공(모듈 사전검사 통과 + 마커 존재). 실패 시 출력 확인 후 수정(절대 `--no-verify` 금지).

- [ ] **Step 6: 병합 & 상태 정리** — risk-tiers Merge strategy(`feature/*`→dev: rebase → 통합테스트 human gate → squash) 적용. 병합 후:

```bash
rm -rf .claude/vway-kit/.vdev
```

---

## Self-Review (writing-plans)

**1. Spec coverage** — 스펙 §4 스키마→Task 1/3, §5 타이밍 매핑→Task 2, §6-A docs 단락 문서화→Task 4-5, §6-B security 잔존→Task 1(+테스트), §6-C 세션 강제 문서화→Task 4-5, §6-D on 오타→Task 1/2, §7 파일 표→Task 1–4, §8 테스트→각 Task + Task 5, §9 롤아웃(feat)→Task 5-5 커밋 type. 모든 스펙 항목이 태스크에 매핑됨.

**2. Placeholder scan** — TODO/TBD/"적절히 처리" 없음. 코드 스텝은 실제 코드 제시. 문서 스텝(Task 4)은 대상 파일·앵커 행·삽입 문구를 구체 지정(실행자가 Read 후 Edit).

**3. Type consistency** — `_parse_check` 3-tuple, `_check_cmds` `(list, list)`, `module_commands` `(cmds, report)` 반환이 Task 1→2→3 전반에서 일치. `_TIMINGS` 상수명 통일.
