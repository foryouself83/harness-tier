# 모듈 단위 사전검사 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 모노레포에서 모듈 폴더 변경 시 그 모듈 전체에 언어별 사전검사(lint/static/import_lint/test→pre-commit, security→승격)를 실행한다.

**Architecture:** `vdev-config.modules[]`(명시 선언, harness SSOT 참고 LLM 초안)를 SSOT로, `vdev_init_setup.py`가 모듈×check별 pre-commit 훅을 생성하고, `precommit-runner.sh`가 전역 test를 폐기하고 승격 시 전체 모듈 보안을 실행한다. `vdev-tiers.yaml`의 티어 게이트를 재정의한다.

**Tech Stack:** Python 3.8+ (stdlib + PyYAML), bash, pre-commit, pytest, uv.

**Spec:** [docs/superpowers/specs/2026-07-01-module-precheck-design.md](2026-07-01-module-precheck-design.md) — 컴포넌트 A~G 상세는 spec 참조.

## Global Constraints

- Invariant #1: FAIL-OPEN, 단 미분류·필수도구 부재는 fail-closed. 정책/설정 "파싱 성공 판정" 불변.
- Invariant #2: Windows 인코딩 — Python `encoding="utf-8"`, 셸 `PYTHONUTF8=1`.
- Invariant #3: 차단 = exit 2 + stderr.
- Invariant #5: `/vdev-init` 멱등 — 훅·config 중복 추가 금지.
- DRY: 파일명·게이트 키·티어 라벨은 `_vway_paths.py` 상수 재사용.
- 검증 종류→시점: lint/static/import_lint/test→pre-commit(모든 커밋, 변경 모듈) · security(도구)→staging+release(전체 모듈) · /security-review→release만.
- 단위 키 명칭은 `modules`. 전역 `test.command` 폐기(하위호환 없음).
- 커밋은 vway-kit dev 게이트(review·doc-sync) 통과 후. Task별 커밋 또는 묶음 — 실행 단계에서 결정.

---

### Task 1: config 스키마 — `modules[]` 추가, 전역 `test` 폐기

**Files:**
- Modify: `vdev-config.example.yaml` (test 섹션 → modules 섹션)
- Test: 없음(YAML 템플릿 — Task 2~4의 파싱 테스트가 커버)

**Interfaces:**
- Produces: `modules` 최상위 키 = list of `{name: str, path: str, checks: dict[str,str]}`. `checks` 키 ∈ {lint, static, import_lint, test, security}.

- [ ] **Step 1: vdev-config.example.yaml 의 `test:` 섹션 교체**

[vdev-config.example.yaml:19-28](../../vdev-config.example.yaml#L19-L28)의 `# 테스트 설정` ~ `coverage_threshold` 블록을 삭제하고 그 자리에 추가:

```yaml
# 모듈 단위 사전검사 (모노레포 — 모듈별 언어·도구가 다를 때).
# 선언하면 pre-commit 이 "모듈 경로 변경 시 그 모듈 전체"에 검증을 돌린다.
# checks 는 가변 키(lint/static/import_lint/test/security) — 해당 언어에 있는 것만.
# 이 값들의 초안은 /vdev-init 이 harness docs SSOT 를 참고해 작성하고, 사람이 수정한다.
# 시점: lint/static/import_lint/test → pre-commit(모든 커밋, 변경 모듈) /
#       security → staging·release 승격(전체 모듈).
# (구버전 전역 test.command 는 폐기 — 모듈별 checks.test 로 이전.)
modules:
  - name: api
    path: services/api/
    checks:
      lint:        "ruff check services/api"
      static:      "uv run pyright services/api"
      import_lint: "uv run lint-imports --config services/api/.importlinter"
      test:        "uv run pytest services/api"
      security:    "uv run bandit -r services/api --severity-level medium"
  - name: web
    path: services/web/
    checks:
      lint:   "npm --prefix services/web run lint"
      static: "npm --prefix services/web run typecheck"
      test:   "npm --prefix services/web test"
```

- [ ] **Step 2: 파싱 검증**

Run: `uv run python -c "import yaml; d=yaml.safe_load(open('vdev-config.example.yaml',encoding='utf-8')); print([m['name'] for m in d['modules']], 'test' not in d)"`
Expected: `['api', 'web'] True`

---

### Task 2: pre-commit 모듈 훅 생성 — `vdev_init_setup.py`

**Files:**
- Modify: `scripts/vdev_init_setup.py` (신규 함수 `render_module_hooks` + `check_precommit` 연계)
- Test: `tests/test_vdev_init_setup.py`

**Interfaces:**
- Consumes: `config_path(host)` 의 `modules[]`.
- Produces: `render_module_hooks(host: Path) -> list[dict]` — pre-commit `repo: local` 의 `hooks` 리스트(각 dict = 훅). pre-commit 대상 종류(lint/static/import_lint/test)만, security 제외. 빈 명령 skip.
- Produces: `missing_module_hooks(host: Path, existing_ids: set[str]) -> list[dict]` — 기존 id 제외한 빠진 훅.

- [ ] **Step 1: 실패 테스트 — 훅 생성(가변 키, security 제외)**

`tests/test_vdev_init_setup.py` 에 추가:

```python
def test_render_module_hooks_generates_per_check(tmp_path: Path):
    from scripts.vdev_init_setup import render_module_hooks

    _mk_host_config(
        tmp_path,
        "modules:\n"
        "  - name: api\n"
        "    path: services/api/\n"
        "    checks:\n"
        "      lint: 'ruff check services/api'\n"
        "      test: 'uv run pytest services/api'\n"
        "      security: 'bandit -r services/api'\n",
    )
    hooks = render_module_hooks(tmp_path)
    ids = {h["id"] for h in hooks}
    assert ids == {"api-lint", "api-test"}          # security 제외, 빈 키 없음
    lint = next(h for h in hooks if h["id"] == "api-lint")
    assert lint["files"] == "^services/api/"
    assert lint["pass_filenames"] is False
    assert lint["entry"] == "bash -c 'ruff check services/api'"
    assert lint["stages"] == ["pre-commit"]
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_vdev_init_setup.py::test_render_module_hooks_generates_per_check -v`
Expected: FAIL (`render_module_hooks` 없음 — ImportError).

- [ ] **Step 3: `render_module_hooks` 구현**

`scripts/vdev_init_setup.py` 에 추가(상단에 상수, 함수는 check_precommit 근처):

```python
# pre-commit 대상 사전검사 종류(모든 커밋). security 는 레이어2(승격)라 제외.
PRECOMMIT_CHECKS = ("lint", "static", "import_lint", "test")


def render_module_hooks(host: Path) -> list[dict]:
    """vdev-config.modules[] → pre-commit local 훅 리스트. 모듈×check(빈 명령 skip,
    security 제외). files=^path/ + pass_filenames:false 로 모듈 전체를 대상으로."""
    import yaml

    cfg = config_path(host)
    if not cfg.is_file():
        return []
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return []
    hooks: list[dict] = []
    for mod in data.get("modules") or []:
        name = mod.get("name")
        path = mod.get("path")
        checks = mod.get("checks") or {}
        if not name or not path:
            continue
        files = f"^{path}" if not path.startswith("^") else path
        for kind in PRECOMMIT_CHECKS:
            cmd = checks.get(kind)
            if not cmd:
                continue
            hooks.append(
                {
                    "id": f"{name}-{kind}",
                    "name": f"{name}: {kind}",
                    "entry": f"bash -c '{cmd}'",
                    "language": "system",
                    "files": files,
                    "pass_filenames": False,
                    "stages": ["pre-commit"],
                }
            )
    return hooks
```

- [ ] **Step 4: GREEN 확인**

Run: `uv run pytest tests/test_vdev_init_setup.py::test_render_module_hooks_generates_per_check -v`
Expected: PASS.

- [ ] **Step 5: 실패 테스트 — 중복 id skip(멱등)**

```python
def test_missing_module_hooks_skips_existing_ids(tmp_path: Path):
    from scripts.vdev_init_setup import missing_module_hooks, render_module_hooks

    _mk_host_config(
        tmp_path,
        "modules:\n  - name: api\n    path: services/api/\n"
        "    checks:\n      lint: 'ruff check services/api'\n      test: 'pytest services/api'\n",
    )
    all_hooks = render_module_hooks(tmp_path)
    missing = missing_module_hooks(tmp_path, existing_ids={"api-lint"})
    assert {h["id"] for h in all_hooks} == {"api-lint", "api-test"}
    assert {h["id"] for h in missing} == {"api-test"}   # 이미 있는 api-lint 는 skip
```

- [ ] **Step 6: `missing_module_hooks` 구현**

```python
def missing_module_hooks(host: Path, existing_ids: set[str]) -> list[dict]:
    """render_module_hooks 중 기존 .pre-commit-config 에 없는 id 만(멱등·중복 방지)."""
    return [h for h in render_module_hooks(host) if h["id"] not in existing_ids]
```

- [ ] **Step 7: GREEN + check_precommit 보고 연계**

`check_precommit` 에, 기존 hook id 수집부에서 `missing_module_hooks(host, ids)` 를 호출해 빠진 모듈 훅을 보고 목록에 추가(파일 있으면 보고, 없으면 생성 경로에 포함). 보고 메시지: `"        - 모듈 훅 {id} (services/.. 변경 시 모듈 전체)"`.

Run: `uv run pytest tests/test_vdev_init_setup.py -k module_hooks -v`
Expected: 2 passed.

---

### Task 3: precommit-runner.sh — 전역 test 제거 + 승격 보안

**Files:**
- Modify: `scripts/precommit-runner.sh` ([:93-125] 전역 test 블록 → 승격 보안 블록)
- Modify: `scripts/vdev_gate_check.py` (신규 `--security-modules` 출력 모드 또는 헬퍼)
- Test: `tests/test_vdev_gate_check.py`

**Interfaces:**
- Produces (vdev_gate_check.py): `lifecycle_tier(root) -> str | None` — 현재 브랜치가 staging/release 면 그 티어, 아니면 None. (기존 `load_lifecycle_branches` + `_current_branch` 조합)
- Produces (vdev_gate_check.py): CLI `--security-commands` — 현재 티어가 staging/release 면 `modules[].checks.security` 명령을 줄단위 출력, 아니면 빈 출력.

- [ ] **Step 1: 실패 테스트 — 승격 시 security 명령 출력**

`tests/test_vdev_gate_check.py` 에 추가:

```python
def test_security_commands_emitted_on_release(tmp_path: Path, monkeypatch):
    from scripts.vdev_gate_check import security_commands

    cfg = tmp_path / ".claude" / "vway-kit" / "config"
    cfg.mkdir(parents=True)
    (cfg / "vdev-config.yaml").write_text(
        "branches:\n  production: main\n"
        "modules:\n"
        "  - name: api\n    path: services/api/\n    checks:\n      security: 'bandit -r services/api'\n"
        "  - name: web\n    path: services/web/\n    checks:\n      lint: 'eslint web'\n",
        encoding="utf-8",
    )
    # release 티어(production 브랜치) → 전체 모듈 security 명령
    cmds = security_commands(tmp_path, tier="release")
    assert cmds == ["bandit -r services/api"]      # web 은 security 없음 → 제외
    assert security_commands(tmp_path, tier="dev") == []   # dev 는 보안 면제
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_vdev_gate_check.py::test_security_commands_emitted_on_release -v`
Expected: FAIL (`security_commands` 없음).

- [ ] **Step 3: `security_commands` 구현**

`scripts/vdev_gate_check.py` 에 추가:

```python
def security_commands(root: Path, tier: str) -> list[str]:
    """staging/release 티어일 때 전체 모듈의 checks.security 명령 리스트(없으면 []).
    config 파싱 실패는 [] (FAIL-OPEN — 게이트 영구차단 방지)."""
    if tier not in (STAGING_TIER, RELEASE_TIER):
        return []
    cfg = config_path(root)
    if not cfg.is_file():
        return []
    try:
        import yaml

        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    out: list[str] = []
    for mod in data.get("modules") or []:
        cmd = (mod.get("checks") or {}).get("security")
        if cmd:
            out.append(str(cmd))
    return out
```

- [ ] **Step 4: CLI 출력 모드 추가**

`vdev_gate_check.py` 의 `main()` 인자 분기에 `--security-commands` 추가: 현재 티어(미분류면 `_resolve_context_tier` 로 lifecycle 판정)를 구해 `security_commands(root, tier)` 를 줄단위 출력하고 exit 0. (판정 실패 시 빈 출력 — FAIL-OPEN.)

- [ ] **Step 5: GREEN**

Run: `uv run pytest tests/test_vdev_gate_check.py::test_security_commands_emitted_on_release -v`
Expected: PASS.

- [ ] **Step 6: precommit-runner.sh 전역 test → 승격 보안 교체**

[scripts/precommit-runner.sh:93-125](../../scripts/precommit-runner.sh#L93) 의 전역 test 블록(`test_cmd` 읽기·tier gating·실행) 전체를 교체:

```bash
# 2) 승격 보안 사전검사. staging/release 티어면 전체 모듈의 checks.security 를 실행한다.
#    (일상 lint/static/import_lint/test 는 레이어1 pre-commit 이 담당 — 여기선 안 함.)
#    config 파싱 실패/명령 없음 시 FAIL-OPEN(skip). 하나라도 실패하면 deny.
sec_cmds="$(CLAUDE_PROJECT_DIR="$ROOT" python3 "$PLUGIN_SCRIPTS/vdev_gate_check.py" --security-commands 2>/dev/null)"
[ -n "$sec_cmds" ] || exit 0

if [ "${VWAY_PRECOMMIT_DRYRUN:-0}" = "1" ]; then
  echo "DRYRUN: 승격 보안 명령 →" 1>&2
  printf '%s\n' "$sec_cmds" 1>&2
  exit 0
fi

LOG_DIR="${TMPDIR:-/tmp}"
sec_log="$LOG_DIR/vway-precommit-security.log"
while IFS= read -r sec_cmd; do
  [ -n "$sec_cmd" ] || continue
  echo "▶ 모듈 보안 사전검사 실행: $sec_cmd …" 1>&2
  if ! bash -c "$sec_cmd" > "$sec_log" 2>&1; then
    cat "$sec_log" 1>&2
    deny "승격 보안 검사 실패: $sec_cmd. 위 출력을 확인해 수정한 뒤 다시 커밋하세요."
  fi
done <<EOF
$sec_cmds
EOF

exit 0
```

또한 헤더 주석([:5-7])의 "2) 프로젝트 테스트" 설명을 "2) 승격 보안 사전검사"로 갱신.

- [ ] **Step 7: 셸 검증 + dryrun**

Run: `bash -c 'command -v shellcheck >/dev/null && shellcheck scripts/precommit-runner.sh || echo "shellcheck 없음 — skip"'`
Expected: 통과 또는 skip.

---

### Task 4: vdev-tiers.yaml 게이트 재정의 + vdev_gate_check 정합

**Files:**
- Modify: `vdev-tiers.yaml`
- Modify: `scripts/_vway_paths.py` (게이트 키 상수)
- Test: `tests/test_vdev_gate_check.py`

**Interfaces:**
- Consumes: `RUNTIME_GATE`(기존 "precommit") — security-scan 도 런타임 게이트로 추가.
- Produces: `vdev-tiers.yaml` gates: dev=[review, doc-sync], staging=[review, security-scan], release=[review, security-scan, security].

- [ ] **Step 1: vdev-tiers.yaml 교체**

```yaml
tiers:
  docs:
    description: "코드 없는 변경 (문서, 주석, 설정값만)"
    superpowers: false
    gates:
      - doc-sync
  dev:
    description: "코드 포함 변경 (모듈 검증은 레이어1 pre-commit 이 담당)"
    superpowers: true
    gates:
      - review
      - doc-sync
  staging:
    description: "QA/RC 승격 (dev → stage) — 전체 모듈 보안 도구 사전검사"
    superpowers: true
    gates:
      - review
      - security-scan
  release:
    description: "프로덕션 배포 (stage → main) — 보안 도구 + 보안 리뷰"
    superpowers: true
    gates:
      - review
      - security-scan
      - security
```

- [ ] **Step 2: _vway_paths.py 에 RUNTIME_GATES 확장**

[scripts/_vway_paths.py:53](../../scripts/_vway_paths.py#L53) 의 `RUNTIME_GATE = "precommit"` 를, security-scan 도 런타임(증거 `.done` 없이 precommit-runner 가 직접 실행)임을 반영해 집합으로:

```python
# 마커 없이 훅이 직접 실행하는 런타임 게이트 — .done 검사에서 제외한다.
RUNTIME_GATES = ("precommit", "security-scan")
```

`vdev_gate_check.py` 에서 `RUNTIME_GATE` 단일 참조를 `RUNTIME_GATES` 멤버십 검사로 교체(`.done` 면제 로직). 기존 `precommit` 단일 사용처도 `in RUNTIME_GATES` 로.

- [ ] **Step 3: 실패 테스트 — security-scan 은 .done 불요(런타임)**

`tests/test_vdev_gate_check.py` 에서, release 티어 게이트 중 `review`/`security` 는 `.done` 필요하나 `security-scan` 은 런타임이라 `.done` 없이도 미충족 사유에 안 들어가는지 검증:

```python
def test_security_scan_is_runtime_gate_no_marker(tmp_path):
    from scripts.vdev_gate_check import RUNTIME_GATES
    assert "security-scan" in RUNTIME_GATES
    # release gates 중 security-scan 은 .done 검사 대상이 아니다
```

- [ ] **Step 4: 게이트 누락 검사에서 런타임 게이트 제외 확인**

`vdev_gate_check.py` 의 미충족 게이트 산출 로직이 `RUNTIME_GATES` 를 `.done` 검사에서 제외하는지 기존 테스트(precommit 면제 테스트)와 함께 실행.

Run: `uv run pytest tests/test_vdev_gate_check.py -v`
Expected: 전부 PASS.

---

### Task 5: vdev-init 스킬 — harness SSOT 참고 초안 작성 (LLM)

**Files:**
- Modify: `skills/vdev-init/SKILL.md`

**Interfaces:** 문서(스킬 지시) — 코드 인터페이스 없음.

- [ ] **Step 1: SKILL.md 에 modules 초안 단계 추가**

`skills/vdev-init/SKILL.md` 의 config 관련 단계에, harness 감지 시 modules 초안 작성 절차를 추가(요지를 그대로 기술):

```markdown
### 모듈 사전검사 초안 (harness 설치 시)

harness 가 설치돼 있으면(`docs/code-style/`·`services/*/CLAUDE.md` 존재),
`vdev-config.modules[]` 초안을 작성한다:

1. `docs/code-style/<stack>.md` 의 "툴체인·설정"·"운영 관심사" 섹션과
   `services/*/CLAUDE.md`(모듈별 SSOT)를 읽어 모듈별 언어·도구를 파악.
2. 모듈마다 `path` 와 `checks`(lint/static/import_lint/test/security 중 해당
   언어에 있는 것만)를 채운다. 스캐폴드 하위 폴더(`tests/` 등)로 test 경로 추정.
3. **SSOT 에서 도구를 못 찾거나 모호하면 AskUserQuestion 으로 확인**(추측 금지).
4. harness 가 없으면 사용자에게 직접 입력 요청하거나 modules 를 비워 둔다.
5. 리서치 결과는 기본값 — 사람이 config 에서 수정하며, config 가 최종 권한.

기존 `test.command`(구버전) 가 남아 있으면 그 명령을 modules[].checks.test
초안의 단서로 쓰고, `test` 필드는 폐기 안내한다(자동 제거 금지).
```

- [ ] **Step 2: 일관성 확인**

`skills/vdev-init/SKILL.md` 의 디렉터리 분류 설명에 modules 가 config 소유임이 드러나는지 확인(이미 config = 호스트 소유).

---

### Task 6: harness SSOT 가이드 확장 (F)

**Files:**
- Modify: `skills/harness-authoring/references/tech-doc-guide.md`
- Modify: `rules/harness-rules.md`

**Interfaces:** 문서(작성 규율) — 코드 인터페이스 없음.

- [ ] **Step 1: tech-doc-guide.md 에 사전검사 도구·폴더구조 가이드 지침 추가**

`docs/code-style/<stack>.md` 의 "툴체인·설정" 섹션 가이드에, 언어/스택별 **사전검사 도구 목록**(lint/format/typecheck/security/import-lint/test runner)과 **폴더 구조**(tests/ 위치 등)를 명시적으로 기술하라는 지침 추가. 목적: `/vdev-init` 의 modules 초안 작성이 이 SSOT 를 참고.

- [ ] **Step 2: harness-rules.md 에 규율 한 줄 추가**

경계 명시: harness 는 사전검사 **도구·폴더구조를 SSOT 로 가이드**(기술 스택 정보)하되, **게이트로 강제하는 것은 vdev 의 몫**([harness-rules 14] 의 defer 규율 연장). harness-init 의 stack_map/스캐폴드 로직은 변경하지 않는다.

- [ ] **Step 3: doc-sync 확인**

Run: 해당 문서 변경이 다른 문서 참조를 깨지 않는지 doc-sync 게이트에서 확인(커밋 단계).

---

### Task 7: docs 티어 가드 — 모듈 pre-commit 훅 스킵

**문제:** 모듈 훅은 레이어1 pre-commit(티어 무인지)이라, docs 티어 커밋에서 `services/<module>/` 내 문서(.md 등) 변경 시에도 발화해 모듈 lint/test 가 도는 낭비가 있다. docs 티어면 모듈 훅이 스킵돼야 한다.

**해결:** 모듈 훅 entry 를 `python3 <SCRIPTS_DIR>/vdev_gate_check.py --skip-if-docs || <cmd>` 로. `--skip-if-docs` 는 현재 tier 가 docs 면 exit 0(스킵), 아니면 exit 1(우항 `<cmd>` 실행). fail-safe: 판정 실패·미분류·docs 아님 → exit 1(실행).

**Files:**
- Modify: `scripts/vdev_gate_check.py` (`--skip-if-docs` CLI + `skip_if_docs()`)
- Modify: `scripts/vdev_init_setup.py` (`render_module_hooks` entry 가드)
- Test: `tests/test_vdev_gate_check.py`, `tests/test_vdev_init_setup.py`

**Interfaces:**
- Consumes: `_resolve_context_tier`·`host_root`·`vdev_dir`·`_current_branch`·`force_utf8_io`, `_vway_paths.SCRIPTS_DIR`.
- Produces: `skip_if_docs() -> None`(exit 0 if docs else 1). `render_module_hooks` entry 형식 변경.

- [ ] **Step 1: 실패 테스트 — --skip-if-docs exit 코드**

`tests/test_vdev_gate_check.py` 에 추가:

```python
def _run_skip_if_docs(root: Path) -> int:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root), "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, "scripts/vdev_gate_check.py", "--skip-if-docs"],
        cwd=Path(__file__).resolve().parent.parent, env=env,
        capture_output=True, text=True, encoding="utf-8",
    ).returncode


def test_skip_if_docs_exit0_for_docs_tier(tmp_path: Path):
    _write_tiers_and_tier(tmp_path, "tiers:\n  docs:\n    gates: [doc-sync]\n", "docs:")
    assert _run_skip_if_docs(tmp_path) == 0   # docs → 스킵 신호


def test_skip_if_docs_exit1_for_dev_tier(tmp_path: Path):
    _write_tiers_and_tier(tmp_path, "tiers:\n  dev:\n    gates: [review]\n", "dev:")
    assert _run_skip_if_docs(tmp_path) == 1   # dev → 모듈 훅 실행


def test_skip_if_docs_exit1_when_unclassified(tmp_path: Path):
    # 미분류(tier 마커 없음) → fail-safe 로 실행(exit 1)
    (tmp_path / "vdev-tiers.yaml").write_text(
        "tiers:\n  docs:\n    gates: [doc-sync]\n", encoding="utf-8"
    )
    (tmp_path / ".claude").mkdir()
    assert _run_skip_if_docs(tmp_path) == 1
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_vdev_gate_check.py -k skip_if_docs -v`
Expected: FAIL (`--skip-if-docs` 미구현).

- [ ] **Step 3: skip_if_docs 구현**

`scripts/vdev_gate_check.py` 에 추가(`security_commands_output` 근처):

```python
def skip_if_docs() -> None:
    """현재 tier 가 docs 면 exit 0(모듈 pre-commit 훅 스킵 신호), 아니면 exit 1.
    판정 실패·미분류·docs 아님은 모두 exit 1(명령 실행, FAIL-SAFE — docs 일 때만 스킵)."""
    force_utf8_io()
    root = host_root()
    tier, _ = _resolve_context_tier(root, vdev_dir(root), _current_branch(root))
    sys.exit(0 if tier == "docs" else 1)
```

`main()` 의 인자 분기에 추가(기존 `--security-commands`/`--precommit-decision` 분기와 같은 위치):

```python
    elif "--skip-if-docs" in sys.argv:
        skip_if_docs()
```

- [ ] **Step 4: render_module_hooks entry 가드**

`scripts/vdev_init_setup.py` 의 `render_module_hooks` 에서 entry 생성을 교체:

```python
            guard = f"python3 {SCRIPTS_DIR}/vdev_gate_check.py --skip-if-docs"
            hooks.append(
                {
                    "id": f"{name}-{kind}",
                    "name": f"{name}: {kind}",
                    "entry": f"bash -c '{guard} || {cmd}'",
                    "language": "system",
                    "files": files,
                    "pass_filenames": False,
                    "stages": ["pre-commit"],
                }
            )
```

- [ ] **Step 5: test_render_module_hooks entry 단언 갱신**

`tests/test_vdev_init_setup.py` 의 `test_render_module_hooks_generates_per_check` 의 entry 단언을 가드 포함으로 교체:

```python
    assert lint["entry"] == (
        "bash -c 'python3 .claude/vway-kit/scripts/vdev_gate_check.py "
        "--skip-if-docs || ruff check services/api'"
    )
```

- [ ] **Step 6: GREEN + 린트**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check`
Expected: 전부 PASS.

---

## Self-Review (spec 대비)

- A(config modules·test 폐기): Task 1. ✅
- B(모듈 훅 생성·중복): Task 2. ✅
- C(전역 test 제거·승격 보안): Task 3. ✅
- D(티어 게이트·정합): Task 4. ✅
- E(vdev-init 초안): Task 5. ✅
- F(harness 가이드): Task 6. ✅
- G(마이그레이션): Task 1(test 폐기)·Task 3(scripts 자동갱신)·Task 5(deprecation 안내·초안 단서) 분산 — ✅
- Invariant(#1 fail-open/fail-closed, #2 인코딩, #3 exit2, #5 멱등): Task 2·3·4 에 반영. ✅
- 타입 일관성: `render_module_hooks(host)->list[dict]`·`missing_module_hooks(host,set)->list[dict]`·`security_commands(root,tier)->list[str]`·`RUNTIME_GATES` tuple — Task 간 시그니처 일치. ✅

## 마이그레이션 검증 (G, Task 1·3·5 종합)

- 기존 `test` 필드 + `modules` 없음 → vdev-init 스킬이 deprecation 안내 + test.command 를 modules 초안 단서로(Task 5).
- precommit-runner.sh 전역 test 제거 버전은 `/vdev-init` 재실행 `copy_artifacts` 로 호스트 자동 갱신(단방향 전파 — 기존 동작, 추가 코드 불요).
- 모듈 훅 멱등: 재실행 시 id 중복 skip(Task 2).
