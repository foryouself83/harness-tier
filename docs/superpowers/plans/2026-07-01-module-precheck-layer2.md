# 모듈 사전검사 레이어2 통합 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 모듈별 사전검사(`lint`/`static`/`import_lint`/`test`)를 레이어1 pre-commit에서 레이어2 vdev 게이트(`precommit-runner.sh`)로 이동해 "Claude 세션 커밋에만 검증"으로 일원화한다.

**Architecture:** 로직은 `vdev_gate_check.py`(Python)에 집중하고 셸은 명령을 받아 실행만 한다. `git diff`로 변경 모듈을 감지하고, `vdev-config.modules[].checks` 의 `security` 제외 키는 매 커밋(변경 모듈), `security` 키는 승격(전체 모듈)에 실행한다. 기존 `security_commands` 파이프라인을 `module_commands` 로 일반화한다.

**Tech Stack:** Python 3.8+ (stdlib + PyYAML), bash, pytest, ruff.

## Global Constraints

- **실행 규약(subagent-driven)**: vway-kit dev 게이트가 모든 커밋에 review/doc-sync 증거를 요구하므로 implementer subagent 는 **커밋하지 않는다**(구현 + `uv run pytest` 통과까지만). controller 가 전체 Task 완료 후 단일 커밋한다. Task 간 리뷰는 working tree diff 기반.
- **Invariant #1 FAIL-OPEN**: git diff 실패·config 파싱 실패·빈 명령·미커버 파일은 모두 통과(`([], [])`). 차단은 기존 vdev 미분류 게이트만(이 plan은 미분류 차단 로직을 건드리지 않는다).
- **Invariant #2 Windows 인코딩**: 모든 파일 I/O 는 `encoding="utf-8"`, subprocess 는 `encoding="utf-8"`, `force_utf8_io()` 유지.
- **Invariant #3 차단 = exit 2 + stderr 사유**: `precommit-runner.sh` `deny()` 그대로.
- **Invariant #4 settings.json `if` 금지** / **#5 `/vdev-init` 멱등** / **#6 Teamer keyring**: 이 plan에서 변경 없음(보존).
- **checks 키 분류(verbatim)**: `security` = 승격(staging/release)·전체 모듈 / `security` 제외 모든 키 = 매 커밋(dev+)·변경 모듈.
- **미커버 정책(verbatim)**: 변경 파일이 어떤 `modules[].path` 에도 매칭 안 되면 통과 + stderr 리포트(차단 안 함).
- **검증 명령**: `uv run pytest` · `uv run ruff check && uv run ruff format --check` · `*.sh` 변경 시 ShellCheck.
- **No SOURCE-only 편집 호스트 사본**: `scripts/`·`vdev-tiers.yaml` SOURCE 만 수정(호스트 사본은 재설치로 전파).

---

## File Structure

| 파일 | 책임 | 변경 |
|---|---|---|
| `scripts/vdev_gate_check.py` | 변경 모듈 감지 + `module_commands` + CLI | Task 1 |
| `scripts/precommit-runner.sh` | 모듈 사전검사 실행 블록 | Task 2 |
| `scripts/vdev_init_setup.py` | 모듈 훅 생성 제거 | Task 3 |
| `pre-commit-hooks.example.yaml` | 언어별 정적분석 local 훅 제거 | Task 4 |
| `vdev-config.example.yaml` · `scripts/_vway_paths.py` | modules 주석 재정의 · 주석 잔재 정리 | Task 5 |
| `CLAUDE.md` · `rules/*.md` · `skills/*` · `USAGE.md` | 문서 정합(doc-sync) | Task 6 |

---

## Task 1: vdev_gate_check.py — 변경 모듈 감지 + module_commands + CLI

**Files:**
- Modify: `scripts/vdev_gate_check.py` (`security_commands` 188-208, `security_commands_output` 257-275, `skip_if_docs` 278-287, `__main__` 290-302 교체)
- Test: `tests/test_vdev_gate_check.py`

**Interfaces:**
- Consumes: `config_path`, `STAGING_TIER`, `RELEASE_TIER`, `_current_branch`, `_resolve_context_tier`, `vdev_dir`, `host_root`, `force_utf8_io` (모두 기존).
- Produces:
  - `_changed_files(root: Path) -> list[str]`
  - `_match_modules(changed: list[str], modules: list[dict]) -> tuple[list[dict], list[str]]`
  - `module_commands(root: Path, tier: str | None) -> tuple[list[str], list[str]]`
  - `module_commands_output() -> None` (CLI `--module-commands`)

- [ ] **Step 1: 기존 `security_commands` 테스트를 `module_commands` 로 대체하는 실패 테스트 작성**

`tests/test_vdev_gate_check.py` 의 `test_security_commands_emitted_on_release`(172-189)를 삭제하고 아래를 추가한다. 헬퍼는 파일 상단 `import scripts.vdev_gate_check as fgc` 를 그대로 쓴다.

```python
_MODCFG = (
    "branches:\n  production: main\n"
    "modules:\n"
    "  - name: api\n    path: services/api/\n"
    "    checks:\n"
    "      lint: 'ruff check services/api'\n"
    "      test: 'pytest services/api'\n"
    "      security: 'bandit -r services/api'\n"
    "  - name: web\n    path: services/web/\n"
    "    checks:\n      lint: 'eslint web'\n"
)


def _write_modcfg(tmp_path: Path) -> None:
    cfg = tmp_path / ".claude" / "vway-kit" / "config"
    cfg.mkdir(parents=True)
    (cfg / "vdev-config.yaml").write_text(_MODCFG, encoding="utf-8")


def test_module_commands_dev_runs_changed_non_security(tmp_path: Path, monkeypatch):
    _write_modcfg(tmp_path)
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/x.py"])
    cmds, report = fgc.module_commands(tmp_path, "dev")
    # api 변경 → api 의 non-security(lint, test). web 미변경 → 제외. security 제외.
    assert cmds == ["ruff check services/api", "pytest services/api"]
    assert report == []


def test_module_commands_release_adds_full_security(tmp_path: Path, monkeypatch):
    _write_modcfg(tmp_path)
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/x.py"])
    cmds, _ = fgc.module_commands(tmp_path, "release")
    # 변경 모듈 non-security + 전체 모듈 security(api 만 security 있음 → bandit).
    assert cmds == ["ruff check services/api", "pytest services/api", "bandit -r services/api"]


def test_module_commands_docs_empty(tmp_path: Path):
    assert fgc.module_commands(tmp_path, "docs") == ([], [])
    assert fgc.module_commands(tmp_path, None) == ([], [])


def test_module_commands_uncovered_reported_not_blocked(tmp_path: Path, monkeypatch):
    _write_modcfg(tmp_path)
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["scripts/build.py", "services/api/y.py"])
    cmds, report = fgc.module_commands(tmp_path, "dev")
    assert "ruff check services/api" in cmds  # 커버된 모듈은 실행
    assert any("scripts/build.py" in line for line in report)  # 미커버는 리포트로만


def test_module_commands_failopen_no_config(tmp_path: Path):
    assert fgc.module_commands(tmp_path, "dev") == ([], [])


def test_match_modules_prefix_and_empty_path():
    mods = [{"name": "api", "path": "services/api/"}, {"name": "app", "path": ""}]
    # 빈 path 는 전체 매칭(단일스택 단일모듈). 명시 path 가 먼저 매칭되면 그쪽.
    matched, uncovered = fgc._match_modules(["services/api/a.py", "README.md"], mods)
    assert {m["name"] for m in matched} == {"api", "app"}
    assert uncovered == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_vdev_gate_check.py -k module_commands -v`
Expected: FAIL — `AttributeError: module 'scripts.vdev_gate_check' has no attribute 'module_commands'`

- [ ] **Step 3: `security_commands`(188-208)를 변경 모듈 감지 + `module_commands` 로 교체**

`scripts/vdev_gate_check.py` 에서 `def security_commands(...)` 블록(188-208) 전체를 아래로 교체한다.

```python
def _changed_files(root: Path) -> list[str]:
    """커밋 대상 변경 파일 목록. staged(--cached) 우선, 비면 working tree(HEAD diff)
    폴백(`git commit -a` 케이스). git 실패/변경 없음은 [] (FAIL-OPEN)."""
    for args in (["diff", "--cached", "--name-only"], ["diff", "HEAD", "--name-only"]):
        try:
            out = subprocess.run(
                ["git", *args],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
        except Exception:
            continue
        files = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
        if files:
            return files
    return []


def _match_modules(changed: list[str], modules: list[dict]) -> tuple[list[dict], list[str]]:
    """변경 파일을 modules[].path 와 prefix 매칭한다.

    반환 ``(매칭 모듈(순서 보존·중복 제거), 미커버 파일)``. 빈 path("")는 전체 매칭
    (단일스택 단일모듈). 첫 매칭 모듈에 귀속하고, 어떤 path 에도 안 걸리면 미커버.
    """
    matched: list[dict] = []
    seen: set[str] = set()
    uncovered: list[str] = []
    for f in changed:
        hit: dict | None = None
        for mod in modules:
            path = str(mod.get("path") or "")
            if path == "" or f.startswith(path):
                hit = mod
                break
        if hit is None:
            uncovered.append(f)
            continue
        key = str(hit.get("name") or hit.get("path") or "")
        if key not in seen:
            seen.add(key)
            matched.append(hit)
    return matched, uncovered


def _check_cmds(mod: dict, *, security: bool) -> list[str]:
    """모듈 checks 명령. security=True 면 security 키만, False 면 security 제외 전부
    (config 작성 순서 보존, 빈 명령 skip)."""
    checks = mod.get("checks") or {}
    if security:
        cmd = checks.get("security")
        return [str(cmd)] if cmd else []
    return [str(v) for k, v in checks.items() if k != "security" and v]


def module_commands(root: Path, tier: str | None) -> tuple[list[str], list[str]]:
    """tier 별 모듈 사전검사 명령과 미커버 리포트.

    - docs/None → ([], [])
    - dev → 변경 모듈의 non-security checks
    - staging/release → 변경 모듈 non-security + 전체 모듈 security
    config 파싱 실패·modules 부재는 ([], []) (FAIL-OPEN — Invariant #1)."""
    if tier is None or tier == "docs":
        return [], []
    cfg = config_path(root)
    if not cfg.is_file():
        return [], []
    try:
        import yaml

        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except Exception:
        return [], []
    modules = data.get("modules") or []
    if not modules:
        return [], []
    matched, uncovered = _match_modules(_changed_files(root), modules)
    cmds: list[str] = []
    for mod in matched:
        cmds += _check_cmds(mod, security=False)
    if tier in (STAGING_TIER, RELEASE_TIER):
        for mod in modules:
            cmds += _check_cmds(mod, security=True)
    report: list[str] = []
    if uncovered:
        report.append(
            "다음 파일은 모듈 미커버라 사전검사 생략 — 새 모듈이면 "
            "vdev-config.modules[] 에 등록하세요:"
        )
        report += [f"  - {f}" for f in uncovered]
    return cmds, report
```

- [ ] **Step 4: `security_commands_output`·`skip_if_docs`(257-287)를 `module_commands_output` 으로 교체**

`def security_commands_output(...)` 와 `def skip_if_docs(...)` 두 블록(257-287)을 아래 하나로 교체한다.

```python
def module_commands_output() -> None:
    """현재 tier 의 모듈 사전검사 명령을 stdout(줄단위), 미커버 리포트를 stderr 로 낸다.

    판정 실패는 빈 출력(FAIL-OPEN). precommit-runner.sh 가 stdout 명령을 실행하고
    stderr 리포트는 그대로 사용자에게 노출한다."""
    force_utf8_io()
    root = host_root()
    try:
        tier, _ = _resolve_context_tier(root, vdev_dir(root), _current_branch(root))
    except Exception:
        return  # FAIL-OPEN
    cmds, report = module_commands(root, tier)
    for line in report:
        print(line, file=sys.stderr)
    for cmd in cmds:
        print(cmd)
```

- [ ] **Step 5: `__main__`(290-302) 분기 교체**

`--security-commands`·`--skip-if-docs` 를 `--module-commands` 하나로 교체한다.

```python
if __name__ == "__main__":
    try:
        if "--module-commands" in sys.argv:
            module_commands_output()
        else:
            main()
    except SystemExit:
        raise
    except Exception as exc:  # FAIL-OPEN
        print(f"[vdev-gate] unexpected error, allowing: {exc}", file=sys.stderr)
        sys.exit(0)
```

- [ ] **Step 6: 죽은 `--skip-if-docs` 테스트 제거**

`tests/test_vdev_gate_check.py` 에서 `_run_skip_if_docs`(192-201)와 `test_skip_if_docs_*` 4개(204-235)를 삭제한다(소비자 `--skip-if-docs` 제거됨).

- [ ] **Step 7: stdout/stderr 분리 in-process 테스트 추가**

`tests/test_vdev_gate_check.py` 에 추가:

```python
def test_module_commands_output_splits_streams(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    _write_modcfg(tmp_path)
    (tmp_path / "vdev-tiers.yaml").write_text(
        "tiers:\n  dev:\n    gates: [review]\n", encoding="utf-8"
    )
    vdev = tmp_path / ".claude" / "vway-kit" / ".vdev"
    vdev.mkdir(parents=True)
    (vdev / "tier").write_text("dev:feature/x", encoding="utf-8")
    monkeypatch.setattr(fgc, "_current_branch", lambda _r: "feature/x")
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["scripts/x.py", "services/api/y.py"])
    fgc.module_commands_output()
    out = capsys.readouterr()
    assert "ruff check services/api" in out.out  # 명령 → stdout
    assert "scripts/x.py" in out.err             # 미커버 → stderr
```

- [ ] **Step 8: 전체 테스트 + 린트**

Run: `uv run pytest tests/test_vdev_gate_check.py -v && uv run ruff check scripts/vdev_gate_check.py tests/test_vdev_gate_check.py && uv run ruff format --check scripts/vdev_gate_check.py tests/test_vdev_gate_check.py`
Expected: PASS (전부 통과, ruff clean)

---

## Task 2: precommit-runner.sh — 모듈 사전검사 실행 블록

**Files:**
- Modify: `scripts/precommit-runner.sh` (헤더 주석 7행, "2) 승격 보안" 블록 92-118)

**Interfaces:**
- Consumes: Task 1 의 `--module-commands` (stdout 명령 줄단위, stderr 미커버 리포트).

- [ ] **Step 1: 헤더 주석(7행) 갱신**

`scripts/precommit-runner.sh` 의 헤더 주석에서 승격 보안 전용 설명을 모듈 사전검사로 바꾼다. 7행:
```
#   2) 승격 보안 사전검사 — staging/release 티어면 modules[].checks.security 를 실행. 실패 시 deny.
```
→
```
#   2) 모듈 사전검사 — 변경 모듈의 lint/static/import_lint/test(+승격 시 전체 security)
#      를 실행. config 파싱 실패/명령 없음은 FAIL-OPEN(skip), 하나라도 실패하면 deny.
```

- [ ] **Step 2: "2) 승격 보안" 블록(92-118)을 모듈 사전검사로 교체**

92행 `# 2) 승격 보안 사전검사...` 부터 118행 `exit 0` 까지(2번 블록 전체)를 아래로 교체한다. stdout 만 명령 substitution 으로 캡처하고 stderr(미커버 리포트)는 부모로 흐르게 둔다(`2>/dev/null` 쓰지 않음).

```bash
# 2) 모듈 사전검사. tier 별로 변경 모듈의 lint/static/import_lint/test(+승격 시 전체
#    모듈 security)를 실행한다. 명령은 stdout, 미커버 리포트는 stderr 로 분리돼 온다
#    (stderr 는 캡처하지 않고 그대로 사용자에게 노출). config 파싱 실패/명령 없음 시
#    FAIL-OPEN(skip). 하나라도 실패하면 deny.
mod_cmds="$(CLAUDE_PROJECT_DIR="$ROOT" python3 "$PLUGIN_SCRIPTS/vdev_gate_check.py" --module-commands)"
[ -n "$mod_cmds" ] || exit 0

if [ "${VWAY_PRECOMMIT_DRYRUN:-0}" = "1" ]; then
  echo "DRYRUN: 모듈 사전검사 명령 →" 1>&2
  printf '%s\n' "$mod_cmds" 1>&2
  exit 0
fi

LOG_DIR="${TMPDIR:-/tmp}"
mod_log="$LOG_DIR/vway-precommit-module.log"
while IFS= read -r mod_cmd; do
  [ -n "$mod_cmd" ] || continue
  echo "▶ 모듈 사전검사 실행: $mod_cmd …" 1>&2
  if ! bash -c "$mod_cmd" > "$mod_log" 2>&1; then
    cat "$mod_log" 1>&2
    deny "모듈 사전검사 실패: $mod_cmd. 위 출력을 확인해 수정한 뒤 다시 커밋하세요."
  fi
done <<EOF
$mod_cmds
EOF

exit 0
```

- [ ] **Step 3: ShellCheck 검증**

Run: `bash -n scripts/precommit-runner.sh && shellcheck -e SC1091 -e SC2086 scripts/precommit-runner.sh`
Expected: 문법 오류 없음, shellcheck 통과(기존 제외 코드 동일).

- [ ] **Step 4: DRYRUN 수동 확인 (선택)**

dev tier 마커가 있는 임시 repo 에서:
Run: `VWAY_PRECOMMIT_DRYRUN=1` 환경에서 `precommit-runner.sh` 에 `{"tool_input":{"command":"git commit -m x"}}` 를 stdin 으로 주면 "DRYRUN: 모듈 사전검사 명령 →" 출력.
Expected: 변경 모듈 명령이 나열되고 실행은 안 됨.

---

## Task 3: vdev_init_setup.py — 모듈 훅 생성 제거

**Files:**
- Modify: `scripts/vdev_init_setup.py` (`PRECOMMIT_CHECKS` 437, `render_module_hooks` 440-479, `missing_module_hooks` 482-484, `check_precommit` 모듈훅 분기 512-520·549-576)
- Test: `tests/test_vdev_init_setup.py`

**Interfaces:**
- Removed: `PRECOMMIT_CHECKS`, `render_module_hooks`, `missing_module_hooks` (모듈 훅은 레이어2로 이동 — 더 이상 생성하지 않음).
- Preserved: `check_precommit` 의 example 복사·`_find_hook_entry` drift 보고(글로벌 example 관리는 유지).

- [ ] **Step 1: 모듈 훅 테스트 삭제(실패 유도)**

`tests/test_vdev_init_setup.py` 에서 아래를 삭제한다:
- `test_render_module_hooks_generates_per_check` (866-889)
- `test_missing_module_hooks_skips_existing_ids` (892-903)
- `test_check_precommit_creates_reports_module_hooks_when_modules_declared` (531-546)

그리고 `test_check_precommit_creates_no_module_hooks_when_none_declared`(549-554)를 "modules 선언돼도 모듈 훅 보고 없음"으로 강화 교체한다:

```python
def test_check_precommit_creates_never_reports_module_hooks(tmp_path: Path):
    # 모듈 훅은 레이어2로 이동 → modules 선언돼도 pre-commit 에 모듈 훅을 보고하지 않는다.
    cfg_dir = tmp_path / ".claude" / "vway-kit" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "vdev-config.yaml").write_text(
        "modules:\n  - name: api\n    path: services/api/\n"
        "    checks:\n      lint: 'ruff check services/api'\n",
        encoding="utf-8",
    )
    report = check_precommit(PLUGIN, tmp_path)
    assert (tmp_path / ".pre-commit-config.yaml").is_file()
    assert any("생성" in line for line in report)
    assert not any("모듈 훅" in line for line in report)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_vdev_init_setup.py -k "module or precommit_creates" -v`
Expected: FAIL — 삭제한 import(`render_module_hooks` 등)나 강화 테스트가 깨짐.

- [ ] **Step 3: `PRECOMMIT_CHECKS`·`render_module_hooks`·`missing_module_hooks` 제거**

`scripts/vdev_init_setup.py` 의 436-484(주석 `# pre-commit 대상...` 부터 `missing_module_hooks` 끝까지) 전체를 삭제한다. (`_find_hook_entry` 487行 이후는 보존.)

- [ ] **Step 4: `check_precommit` 의 모듈 훅 분기 제거**

`check_precommit`(498-577) 내부에서 모듈 훅 관련을 제거해 글로벌 example 처리만 남긴다.

greenfield 분기(509-521)를 단순화:
```python
    if not dest.is_file():
        shutil.copyfile(example, dest)
        return ["  [+] .pre-commit-config.yaml 생성 (예시 복사 — local 훅은 팀 언어로 교체)"]
```

기존 파일 분기에서 `existing_ids`·`mod_missing`·`mod_lines`(549-560, 570-576) 제거. 561-577 을 아래로 교체:
```python
    if not missing:
        return ["  [=] pre-commit 훅 이미 충족 (변경 없음)", *stale]
    out = [
        "  [i] .pre-commit-config.yaml 가 이미 있어 자동 병합하지 않음(주석/포맷 보존).",
        "  [i] 아래 빠진 항목을 pre-commit-hooks.example.yaml 참고해 직접 추가하세요:",
    ]
    out += [f"        - {m}" for m in missing]
    return out + stale
```

- [ ] **Step 5: 테스트 + 린트**

Run: `uv run pytest tests/test_vdev_init_setup.py -v && uv run ruff check scripts/vdev_init_setup.py tests/test_vdev_init_setup.py && uv run ruff format --check scripts/vdev_init_setup.py tests/test_vdev_init_setup.py`
Expected: PASS (모듈 훅 테스트 부재, 나머지 통과)

---

## Task 4: pre-commit-hooks.example.yaml — 언어별 정적분석 local 훅 제거

**Files:**
- Modify: `pre-commit-hooks.example.yaml` (local repo 의 lint/format-check/security/typecheck/lint-imports 제거)

- [ ] **Step 1: `local` repo 의 정적분석 훅 제거**

`pre-commit-hooks.example.yaml` 의 `- repo: local` 블록(30-83)에서 `id: lint`(33-38)·`id: format-check`(41-46)·`id: security`(49-54)·`id: typecheck`(57-62)·`id: lint-imports` 주석(64-70)을 삭제한다. `id: teams-notify-push`(75-82)만 남긴다. 결과:

```yaml
  # vway-kit 소유 훅 — push 알림(언어별 정적분석/모듈 검증은 레이어2 vdev 게이트로 이동).
  - repo: local
    hooks:
      # Teams push 알림 — push 대상 브랜치가 등록된 채널이면 알림(그 외 skip).
      # entry 는 호스트 저장소 기준 경로다. /vdev-init 이 notify-push.sh +
      # teams_alert.py 를 .claude/vway-kit/scripts/ 로 복사하므로 그 경로를 가리킨다.
      - id: teams-notify-push
        name: Teams push notification
        entry: .claude/vway-kit/scripts/notify-push.sh
        language: script
        stages: [pre-push]
        always_run: true
        pass_filenames: false
        verbose: true
```

- [ ] **Step 2: 상단 설명 주석(5-13) 갱신**

5-9행의 "언어별 훅(아래 'local' 의 ruff/bandit/pyright)은 팀 스택에 맞게 교체" 안내를 모듈 검증이 레이어2로 갔음을 반영해 수정한다:

```yaml
# 이 파일은 commit-msg 린트(gitlint)·push 알림(teams-notify-push)·언어무관 위생
# (파일 위생/shellcheck/hadolint)만 담는다. 언어별 정적분석·모듈 검증(lint/static/
# test/security)은 레이어2 vdev 게이트(scripts/precommit-runner.sh)가 vdev-config.modules
# 기반으로 수행한다 — 여기에 두지 않는다.
```

- [ ] **Step 3: YAML 유효성 확인**

Run: `uv run python -c "import yaml; yaml.safe_load(open('pre-commit-hooks.example.yaml', encoding='utf-8'))"`
Expected: 예외 없음(유효 YAML).

- [ ] **Step 4: 정적분석 id 부재 확인**

Run: `uv run python -c "import yaml; d=yaml.safe_load(open('pre-commit-hooks.example.yaml',encoding='utf-8')); ids=[h['id'] for r in d['repos'] for h in r.get('hooks',[])]; assert not ({'lint','format-check','security','typecheck','lint-imports'} & set(ids)), ids; assert 'teams-notify-push' in ids and 'gitlint' in ids; print('OK', ids)"`
Expected: `OK [...]` — 정적분석 id 없음, gitlint·teams-notify-push 보존. (`id: security` 는 위생 repo 에 없고 local 에서 제거됨 — 검증 set 에 포함해 확인)

---

## Task 5: vdev-config.example.yaml + _vway_paths.py — 설정 주석 정합

**Files:**
- Modify: `vdev-config.example.yaml` (modules 섹션 주석 19-25)
- Modify: `scripts/_vway_paths.py` (CONFIG_FILENAME 주석 46)

- [ ] **Step 1: modules 주석(19-25) 재정의 — 레이어2 시점**

`vdev-config.example.yaml` 19-25행의 주석을 레이어2 동작으로 교체한다:

```yaml
# 모듈 단위 사전검사 (모노레포 — 모듈별 언어·도구가 다를 때). 단일스택도 모듈 하나로 표현.
# 선언하면 레이어2 vdev 게이트(Claude 세션 커밋)가 "변경 모듈 전체"에 검증을 돌린다.
# checks 는 가변 키(lint/static/import_lint/test/security) — 해당 언어에 있는 것만.
# 이 값들의 초안은 /vdev-init 이 harness docs SSOT 를 참고해 작성하고, 사람이 수정한다.
# 시점: security 제외 키(lint/static/import_lint/test) → 매 커밋(변경 모듈) /
#       security → staging·release 승격(전체 모듈).
# (구버전 전역 test.command 는 폐기 — 모듈별 checks 로 이전. 레이어1 pre-commit 모듈 훅도 폐기.)
```

- [ ] **Step 2: `_vway_paths.py` CONFIG_FILENAME 주석(46)의 test.command 잔재 제거**

`scripts/_vway_paths.py` 46행:
```python
CONFIG_FILENAME = "vdev-config.yaml"  # 호스트 환경값(브랜치·test.command·teamer·handoff)
```
→
```python
CONFIG_FILENAME = "vdev-config.yaml"  # 호스트 환경값(브랜치·modules·teamer·handoff)
```

- [ ] **Step 3: 검증**

Run: `uv run python -c "import yaml; yaml.safe_load(open('vdev-config.example.yaml',encoding='utf-8')); print('OK')" && uv run ruff check scripts/_vway_paths.py`
Expected: `OK`, ruff clean.

---

## Task 6: 문서 정합 (doc-sync)

**Files:**
- Modify: `CLAUDE.md` · `rules/risk-tiers.md` · `rules/harness-rules.md` · `skills/vdev/SKILL.md` · `skills/vdev-init/SKILL.md` · `skills/harness-authoring/references/tech-doc-guide.md` · `USAGE.md`

> 이 Task 는 `doc-sync` 스킬로 수행한다(Mode A 코드→문서 + Mode B 문서 정합). 아래는 반드시 반영할 사실 변경의 체크리스트다.

- [ ] **Step 1: CLAUDE.md "검증 3레이어" 갱신**

`CLAUDE.md` Architecture 의 "검증 3레이어" 항목에서 레이어 분담을 수정한다:
- 레이어1 `.pre-commit-config.yaml`: "모듈별 lint/static/import_lint/test" 문구 제거 → "gitlint(commit-msg)·teams-notify-push(pre-push)·언어무관 위생" 으로.
- 레이어2 `precommit-runner.sh`: "promotion 시 전체 모듈 security" → "변경 모듈의 lint/static/import_lint/test + 승격 시 전체 모듈 security" 로.
- "정책 vs 환경값" 항목의 modules 설명 유지(이미 modules 기반).

- [ ] **Step 2: rules/risk-tiers.md 게이트 설명 갱신**

모듈 사전검사가 레이어1 pre-commit 이 아니라 레이어2 vdev 게이트(Claude 커밋)에서 변경 모듈에 실행됨을 반영한다(게이트 표·Staging/Release 단계 설명에서 precommit/security-scan 서술을 모듈 사전검사 기준으로 정정).

- [ ] **Step 3: skills/vdev/SKILL.md · vdev-init/SKILL.md 갱신**

- `skills/vdev/SKILL.md`: "per-module pre-checks from vdev-config.modules" 문맥에서 레이어2 실행임을 명확히(레이어1 pre-commit 모듈 훅 언급 제거).
- `skills/vdev-init/SKILL.md`: Step 2.6 모듈 초안 설명에서 "pre-commit 모듈 훅 생성"을 "vdev-config.modules 작성(레이어2 게이트가 소비)"으로 정정.

- [ ] **Step 4: rules/harness-rules.md(14-1) · tech-doc-guide.md 갱신**

harness 가 가이드하는 모듈 사전검사가 레이어2에서 변경 모듈에 실행됨을 반영(레이어1 pre-commit 표현 정정).

- [ ] **Step 5: USAGE.md 갱신**

vdev-config modules 예시 설명에서 검증 시점(레이어2 Claude 커밋)을 반영.

- [ ] **Step 6: 정합 검증**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check`
Expected: 전체 PASS, ruff clean. (문서 변경이 코드 테스트를 깨지 않음 확인)

---

## Self-Review

**1. Spec coverage** (spec 섹션 → task):
- 레이어 역할 재분리 → Task 1·2·4 ✓
- 변경 모듈 감지(git diff staged + 폴백) → Task 1 `_changed_files` ✓
- checks 키 분류(security 제외=매커밋, security=승격) → Task 1 `module_commands`·`_check_cmds` ✓
- tier별 동작(docs 스킵/dev/staging·release) → Task 1 + 테스트 ✓
- 미커버 정책(통과+stderr) → Task 1 `_match_modules`·report + Task 2 stderr 노출 ✓
- 레이어1 축소(정적분석 제거) → Task 3·4 ✓
- 마이그레이션=안내(자동변경 안 함) → 코드 변경 없음(기존 `check_precommit` 보고 유지) ✓ — 별도 task 불필요(invariant 보존).
- 문서 정합 → Task 6 ✓

**2. Placeholder scan:** 모든 코드 step 에 완전한 코드 포함. "직접 추가"·"교체" 는 정확한 라인 범위 명시. 통과.

**3. Type consistency:** `module_commands(root, tier) -> tuple[list[str], list[str]]` 가 Task 1(정의)·Task 2(`--module-commands` 소비)에서 일관. `_changed_files`/`_match_modules`/`_check_cmds` 시그니처가 테스트와 일치. `tier: str | None` 이 docs/None 분기와 일치.

**Note (마이그레이션):** spec 의 "마이그레이션=안내" 는 `run_uninstall`(901-902)에 이미 ".pre-commit-config.yaml 의 정적분석 훅은 자동 제거 안 함" 안내가 있어 추가 코드 불필요. 모듈 훅 잔재 안내가 필요하면 Task 6 doc-sync 에서 USAGE/SKILL 에 한 줄 추가로 충분(자동 변경 금지 invariant 보존).
