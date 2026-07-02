# vdev-tiers.yaml 을 scripts/ → config/ 로 이동 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 플러그인 정책 파일 `vdev-tiers.yaml` 의 호스트 복사 위치를 `.claude/vway-kit/scripts/` 에서 `.claude/vway-kit/config/` 로 옮기고, 게이트가 그곳을 읽으며, 기존 호스트는 `/vdev-init` 재실행 시 자동 전환되게 한다.

**Architecture:** `_vway_paths` 상수/주석 갱신 → `vdev_gate_check.tiers_path()` 의 호스트 탐색을 config/ 로 교체 → `vdev_init_setup` 의 복사 목적지 분리 + 마이그레이션 → 문서·테스트 갱신. 정책 해석은 `__file__` 기준(`scripts/` 의 형제 `config/`)을 계승해 `host_root()` 불안정성에 영향받지 않는다.

**Tech Stack:** Python 3.8+ (stdlib + PyYAML), pytest, uv.

## Global Constraints

- Invariant #1 (FAIL-OPEN, 미분류·정책부재는 fail-closed) — 정책 "파싱 성공 판정" 로직 불변.
- Invariant #2 (Windows 인코딩) — `encoding="utf-8"` 유지.
- 단방향 전파(SOURCE → 캐시 → 호스트 사본) — 목적지만 변경, 방향 유지. `vdev-tiers.yaml` 은 항상 덮어씀(SSOT).
- DRY (rule-dry-constants) — 파일명/디렉터리명은 `_vway_paths` 상수(`TIERS_FILENAME`·`CONFIG_DIR`) 재사용, 리터럴 금지.
- 커밋은 task 별이 아니라 **dev 게이트(review·doc-sync) 통과 후 최종 1회**.
- 슬래시 커맨드 신규 생성 없음.

---

### Task 1: `_vway_paths` 주석 — 정책 파일 위치를 config/ 로 표기

**Files:**
- Modify: `scripts/_vway_paths.py:39-45`

**Interfaces:**
- Produces: 상수값 변경 없음(주석만). `SCRIPTS_DIR`·`CONFIG_DIR`·`TIERS_FILENAME` 동일.

- [ ] **Step 1: 주석 교체**

`scripts/_vway_paths.py` 의 해당 줄들:

```python
SCRIPTS_DIR = f"{VWAY_DIR}/scripts"  # 복사 게이트 스크립트 (플러그인 소유·git추적)
CONFIG_DIR = f"{VWAY_DIR}/config"  # vdev-config·vdev-tiers(정책)·계정·웹훅
VDEV_DIR = f"{VWAY_DIR}/.vdev"  # 게이트 증거 (gitignored)

# ── config 디렉터리 하위 파일명 ────────────────────────────────────────────────
CONFIG_FILENAME = "vdev-config.yaml"  # 호스트 환경값(브랜치·test.command·teamer·handoff, 사람이 편집)
TIERS_FILENAME = "vdev-tiers.yaml"  # 플러그인 정책(tier→gates, 불변·SSOT — config/ 에 있으나 편집 금지)
```

- [ ] **Step 2: 린트 확인**

Run: `uv run ruff check scripts/_vway_paths.py`
Expected: 통과(주석만 변경).

---

### Task 2: `tiers_path()` 호스트 탐색을 config/ 로 교체

**Files:**
- Modify: `scripts/vdev_gate_check.py:18-41` (import 에 `CONFIG_DIR` 추가), `:186-200` (`tiers_path`)
- Test: `tests/test_vdev_init_setup.py` (복사-환경 end-to-end 테스트 추가 — copy_artifacts 사용)

**Interfaces:**
- Consumes: `_vway_paths.CONFIG_DIR`, `_vway_paths.TIERS_FILENAME`.
- Produces: `tiers_path(root: Path) -> Path` — 해석 순서 ①CLAUDE_PLUGIN_ROOT ②`scripts/` 의 형제 `config/<TIERS_FILENAME>` ③호스트 루트.

- [ ] **Step 1: 실패 테스트 작성 (복사-환경에서 config/ 해석)**

`tests/test_vdev_init_setup.py` 끝에 추가:

```python
def test_copied_gate_reads_tiers_from_config(tmp_path: Path):
    # 호스트 복사 환경 end-to-end: 복사된 scripts/vdev_gate_check.py 의 __file__ 은
    # tmp/.claude/vway-kit/scripts/ → 형제 config/ 의 vdev-tiers.yaml 을 해석해야 한다.
    # config/→scripts/ 회귀(형제 탐색이 옛 scripts/ 를 보면) 시 이 경로가 깨진다.
    copy_artifacts(PLUGIN, tmp_path)
    scripts_dir = tmp_path / ".claude" / "vway-kit" / "scripts"
    config_tiers = tmp_path / ".claude" / "vway-kit" / "config" / "vdev-tiers.yaml"
    assert config_tiers.is_file()  # copy 가 config/ 에 넣었다(Task 3)
    code = (
        "from pathlib import Path;"
        "from vdev_gate_check import tiers_path;"
        "import sys; sys.stdout.write(str(tiers_path(Path(sys.argv[1]))))"
    )
    env = {**os.environ, "PYTHONPATH": str(scripts_dir), "PYTHONIOENCODING": "utf-8"}
    env.pop("CLAUDE_PLUGIN_ROOT", None)  # ① 분기 비활성화 → ② config/ 탐색 검증
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        env=env, capture_output=True, text=True, encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(config_tiers)
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_vdev_init_setup.py::test_copied_gate_reads_tiers_from_config -v`
Expected: FAIL (현재는 scripts/ 형제를 보고, copy 도 아직 config/ 에 안 넣음 — Task 3 와 함께 GREEN).

- [ ] **Step 3: import 에 CONFIG_DIR 추가**

`scripts/vdev_gate_check.py` 의 `try/except` import 블록 양쪽에 `CONFIG_DIR,` 를 추가(알파벳 위치 — `BLOCK_EXIT_CODE` 다음):

```python
    from _vway_paths import (
        BLOCK_EXIT_CODE,
        CONFIG_DIR,
        RELEASE_TIER,
        ...
    )
```
(except 분기의 `from scripts._vway_paths import (...)` 에도 동일하게 `CONFIG_DIR,` 추가.)

- [ ] **Step 4: tiers_path 교체**

`scripts/vdev_gate_check.py:186-200` 을 교체:

```python
def tiers_path(root: Path) -> Path:
    """vdev-tiers.yaml(플러그인 정책)의 위치를 해석한다.

    정책 파일은 게이트 스크립트와 함께 호스트로 배포되므로 다음 순서로 찾는다:
    1. ``CLAUDE_PLUGIN_ROOT/vdev-tiers.yaml`` — 플러그인 hook 으로 직접 실행될 때
    2. config 디렉터리의 ``vdev-tiers.yaml`` — ``.claude/vway-kit/config/`` 로
       복사된 경우(게이트 스크립트는 형제 ``scripts/`` 에 있으므로 그 형제
       디렉터리 config/ 를 __file__ 기준으로 가리킨다 — host_root() 불안정성에
       영향받지 않는다).
    3. 호스트 루트 ``vdev-tiers.yaml`` — 폴백(개발/테스트).
    """
    plugin = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin and (p := Path(plugin) / TIERS_FILENAME).is_file():
        return p
    config_copy = Path(__file__).resolve().parent.parent / Path(CONFIG_DIR).name / TIERS_FILENAME
    if config_copy.is_file():
        return config_copy
    return root / TIERS_FILENAME
```

- [ ] **Step 5: GREEN 확인 (Task 3 의 copy 변경 후 최종 통과)**

Run: `uv run pytest tests/test_vdev_init_setup.py::test_copied_gate_reads_tiers_from_config -v`
Expected: Task 3 완료 후 PASS. (Task 3 의 copy_artifacts 가 config/ 에 넣어야 `config_tiers.is_file()` 성립.)

---

### Task 3: 복사 목적지 분리 — 정책은 config/, 스크립트는 scripts/

**Files:**
- Modify: `scripts/vdev_init_setup.py:43-64` (import 에 `TIERS_FILENAME` 추가), `:74-82` (COPY_FILES), `:173-185` (copy_artifacts)
- Test: `tests/test_vdev_init_setup.py:538-543` (test_copy_artifacts), 신규 테스트

**Interfaces:**
- Consumes: `_vway_paths.TIERS_FILENAME`, `_vway_paths.CONFIG_DIR`.
- Produces: `copy_artifacts(plugin, host)` 가 `host/CONFIG_DIR/vdev-tiers.yaml` 생성, `host/SCRIPTS_DIR/vdev-tiers.yaml` 미생성.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_vdev_init_setup.py` 의 `test_copy_artifacts` (line 538-543) 를 교체:

```python
def test_copy_artifacts(tmp_path: Path):
    copy_artifacts(PLUGIN, tmp_path)
    vd = tmp_path / ".claude" / "vway-kit"
    assert (vd / "scripts" / "precommit-runner.sh").is_file()
    assert (vd / "scripts" / "vdev_gate_check.py").is_file()
    # 정책 파일은 config/ 로, scripts/ 에는 두지 않는다.
    assert (vd / "config" / "vdev-tiers.yaml").is_file()
    assert not (vd / "scripts" / "vdev-tiers.yaml").exists()
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_vdev_init_setup.py::test_copy_artifacts -v`
Expected: FAIL (현재 copy 는 scripts/ 에만 넣음).

- [ ] **Step 3: import 에 TIERS_FILENAME 추가**

`scripts/vdev_init_setup.py:43-64` 의 try/except import 양쪽에 `TIERS_FILENAME,` 추가(`SCRIPTS_DIR` 다음 알파벳 위치는 아니지만 기존 정렬에 맞춰 `config_path` 위, 즉 상수군 끝에):

```python
    from _vway_paths import (
        CONFIG_DIR,
        SCRIPTS_DIR,
        TIERS_FILENAME,
        VDEV_DIR,
        VWAY_DIR,
        config_path,
        force_utf8_io,
        host_root,
        plugin_root,
    )
```
(except 분기에도 동일.)

- [ ] **Step 4: COPY_FILES 에서 vdev-tiers.yaml 제거**

`scripts/vdev_init_setup.py:74-82` 의 COPY_FILES 에서 `"vdev-tiers.yaml",` 줄을 삭제하고, 주석을 갱신:

```python
# .claude/vway-kit/scripts/ 로 복사할 게이트 스크립트(SOURCE → HOST). _vway_paths.py 는
# 복사 스크립트들이 import 하는 공용 모듈이라 함께 따라가야 한다(단일파일 복사 환경에서
# 형제 import 성립). 정책 파일 vdev-tiers.yaml 은 config/ 로 따로 복사한다(copy_artifacts).
COPY_FILES = [
    "scripts/_vway_paths.py",
    "scripts/precommit-runner.sh",
    "scripts/vdev_gate_check.py",
    "scripts/teams_alert.py",
    "scripts/notify-push.sh",
    "scripts/check-deps.sh",
]
```

- [ ] **Step 5: copy_artifacts 에 config/ 복사 추가**

`scripts/vdev_init_setup.py:173-185` 의 copy_artifacts 를 교체:

```python
def copy_artifacts(plugin: Path, host: Path) -> list[str]:
    """배포 산출물 복사(항상 덮어씀 — SOURCE 가 SSOT). 게이트 스크립트는
    scripts/ 로, 플러그인 정책 vdev-tiers.yaml 은 config/ 로(vdev-config 과 한곳)."""
    dest_dir = host / SCRIPTS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    report: list[str] = []
    for rel in COPY_FILES:
        src = plugin / rel
        if not src.is_file():
            report.append(f"  [!] 소스 없음, skip: {rel}")
            continue
        shutil.copyfile(src, dest_dir / Path(rel).name)
        report.append(f"  [+] 복사: {Path(rel).name}")
    # 정책 파일은 config/ 로(호스트 소유 디렉터리지만 이 파일만은 플러그인 소유·SSOT).
    cfg_dir = host / CONFIG_DIR
    cfg_dir.mkdir(parents=True, exist_ok=True)
    tiers_src = plugin / TIERS_FILENAME
    if tiers_src.is_file():
        shutil.copyfile(tiers_src, cfg_dir / TIERS_FILENAME)
        report.append(f"  [+] 복사: {TIERS_FILENAME} → config/")
    else:
        report.append(f"  [!] 소스 없음, skip: {TIERS_FILENAME}")
    return report
```

- [ ] **Step 6: GREEN 확인 + Task 2 테스트 동반 통과**

Run: `uv run pytest tests/test_vdev_init_setup.py::test_copy_artifacts tests/test_vdev_init_setup.py::test_copied_gate_reads_tiers_from_config -v`
Expected: 둘 다 PASS.

---

### Task 4: 마이그레이션 — 옛 위치(scripts/·평면) 정책 파일 잔재 제거

**Files:**
- Modify: `scripts/vdev_init_setup.py:188-247` (migrate_legacy_paths 내부에 잔재 제거 루프 추가)
- Test: `tests/test_vdev_init_setup.py` (신규)

**Interfaces:**
- Consumes: `TIERS_FILENAME`, `SCRIPTS_DIR`, `VWAY_DIR`.
- Produces: `migrate_legacy_paths(host)` 가 `host/SCRIPTS_DIR/vdev-tiers.yaml`·`host/VWAY_DIR/vdev-tiers.yaml`(평면) 제거.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_vdev_init_setup.py` 에 추가:

```python
def test_migrate_relocates_scripts_tiers_to_config(tmp_path: Path):
    # scripts/→config/ 재배치: 옛 scripts/vdev-tiers.yaml 잔재를 제거한다.
    # (config/ 에는 copy_artifacts 가 새로 넣으므로 옛 위치는 잔재.)
    sd = tmp_path / ".claude" / "vway-kit" / "scripts"
    sd.mkdir(parents=True)
    (sd / "vdev-tiers.yaml").write_text("tiers: {}\n", encoding="utf-8")
    report = migrate_legacy_paths(tmp_path)
    assert not (sd / "vdev-tiers.yaml").exists()
    assert any("재배치 잔재" in line for line in report)
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_vdev_init_setup.py::test_migrate_relocates_scripts_tiers_to_config -v`
Expected: FAIL (현재 scripts/vdev-tiers.yaml 을 안 지움).

- [ ] **Step 3: migrate_legacy_paths 에 잔재 제거 루프 추가**

`scripts/vdev_init_setup.py` 의 migrate_legacy_paths 에서, RENAMED_SCRIPT_ORPHANS 제거 루프(`:234-243`) **바로 뒤**(`if not report:` 앞)에 추가:

```python
    # vdev-tiers.yaml 재배치(scripts/→config/): 옛 위치 사본 제거. config/ 에는
    # copy_artifacts 가 새로 넣으므로(SSOT) 옛 위치(scripts/·구버전 평면)는 잔재다.
    for old_dir in (host / SCRIPTS_DIR, host / VWAY_DIR):
        orphan = old_dir / TIERS_FILENAME
        if orphan.is_file():
            try:
                orphan.unlink()
                report.append(f"  [+] 재배치 잔재 제거: {old_dir.name}/{TIERS_FILENAME}")
            except OSError as exc:
                report.append(f"  [!] 재배치 잔재 제거 실패: {TIERS_FILENAME} ({exc})")
```

- [ ] **Step 4: GREEN 확인**

Run: `uv run pytest tests/test_vdev_init_setup.py::test_migrate_relocates_scripts_tiers_to_config tests/test_vdev_init_setup.py::test_migrate_legacy_removes_flat_scripts -v`
Expected: 둘 다 PASS. (`test_migrate_legacy_removes_flat_scripts` 는 평면 vdev-tiers.yaml 을 새 루프가 제거하므로 여전히 통과 — precommit-runner.sh 의 "평면 스크립트 제거" 메시지도 유지.)

---

### Task 5: 잔여 테스트 갱신 (main end-to-end · falls_back 주석)

**Files:**
- Modify: `tests/test_vdev_init_setup.py:388-389` (test_main_setup_then_uninstall_dispatch)
- Modify: `tests/test_vdev_gate_check.py:64-69` (test_tiers_path_falls_back_to_host_root — 주석만)

- [ ] **Step 1: main end-to-end 검증 위치 변경**

`tests/test_vdev_init_setup.py:388-389` 의 두 assert 를 교체:

```python
    assert (vd / "scripts" / "precommit-runner.sh").is_file()
    assert (vd / "config" / "vdev-tiers.yaml").is_file()
```

- [ ] **Step 2: falls_back 테스트 주석 갱신**

`tests/test_vdev_gate_check.py:65` 의 주석을 교체(동작 동일 — config/ 복사본 부재 시 호스트 루트 폴백):

```python
    # 플러그인 루트 미설정 + config/ 복사본 부재 → 호스트 루트로 폴백
```

- [ ] **Step 3: 게이트·init 테스트 전체 통과 확인**

Run: `uv run pytest tests/test_vdev_init_setup.py tests/test_vdev_gate_check.py -v`
Expected: 전부 PASS.

---

### Task 6: 문서 갱신 (CLAUDE.md)

**Files:**
- Modify: `CLAUDE.md` (Folder structure, Architecture "호스트 쓰기", "정책 vs 환경값")

- [ ] **Step 1: Folder structure — scripts/·config 설명 갱신**

`CLAUDE.md` 의 Folder structure 섹션에서 `scripts/` 줄의 "vdev-tiers.yaml" 위치 표기를 config/ 로 옮기고, `vdev-tiers.yaml` 행의 위치 설명을 `config/` 로 갱신. (정확한 문구는 doc-sync 게이트에서 전체 정합 확인.)

- [ ] **Step 2: Architecture — 호스트 쓰기 항목**

"호스트 쓰기는 `${CLAUDE_PROJECT_DIR}/.claude/vway-kit/` 아래…" 항목에서 `scripts/`(복사 스크립트+vdev-tiers.yaml) → `scripts/`(복사 스크립트), `config/` 설명에 vdev-tiers.yaml(정책·플러그인 소유) 추가.

- [ ] **Step 3: 정책 vs 환경값 항목**

`vdev-tiers.yaml`(tier→gates, 불변)이 `config/` 에 위치하되 플러그인 소유·편집 금지임을 명시(vdev-config.yaml 과 같은 디렉터리, 다른 소유권).

- [ ] **Step 4: 단방향 전파 항목 경로 확인**

"스크립트 전파는 단방향: scripts/(SOURCE)…" 항목에서 정책 파일 경로 언급이 있으면 config/ 로 정합.

---

## 최종: 게이트 통과 + 단일 커밋 (vway-kit dev 워크플로우)

- [ ] **전체 테스트 + 린트**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check`
Expected: 전부 PASS.

- [ ] **도메인 review (독립 general-purpose 에이전트)** → `touch .claude/vway-kit/.vdev/review.done`
- [ ] **doc-sync 스킬** → `touch .claude/vway-kit/.vdev/doc-sync.done`
- [ ] **단일 커밋** (Conventional Commits, 영향 파일만 stage). 게이트가 review.done·doc-sync.done 확인 후 통과.

## Self-Review (spec 대비)

- 정책 위치 이동: Task 3(복사) + Task 2(탐색) + Task 4(마이그레이션) 커버. ✅
- 폴백 정책(config/만, scripts/ 폴백 없음): Task 2 의 tiers_path 에 scripts/ 분기 없음. ✅
- 마이그레이션: Task 4. ✅
- 문서·주석·테스트: Task 1·5·6. ✅
- Invariant 회귀 없음: 정책 파싱 로직 불변(Task 2 는 경로만 변경). ✅
- 타입 일관성: `tiers_path(root)->Path`·`copy_artifacts(plugin,host)->list[str]`·`migrate_legacy_paths(host)->list[str]` 시그니처 불변. ✅
