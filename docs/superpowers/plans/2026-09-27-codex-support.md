# Codex CLI 지원 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** harness-tier 플러그인을 Codex CLI 에서도 설치·규칙 주입·커밋 차단·skill 실행이 되게 하고, 기존 Claude 소비자는 byte-identical 로 유지.

**Architecture:** 하이브리드 — 공유 skill 본문(행동 어휘) + `rules/harness-tools/codex.md` 매핑, `/flow-init` 이
canonical gate spec 을 하네스별 설정으로 렌더(`scripts/harness/<name>/install.py`), 공유 hook 스크립트는 `--harness`
명시 인자로 Codex 입력 차이 흡수. Codex gate 는 wrapper(`gate.sh`/`gate.cmd`)가 러너 exit 2 → 0 변환(deny JSON 이 차단).

**Tech Stack:** Python 3.8+ (stdlib + PyYAML), bash, Windows cmd, pytest, codex-cli 0.157.1.

**Spec:** `docs/superpowers/specs/2026-09-27-codex-support-design.md` · 근거: `docs/superpowers/reference/claude-code-vs-codex.md`

## Global Constraints

- 기존 Claude 호스트 산출물·hook 출력 byte-identical. `--harness` 인자 없으면 기존 코드 경로.
- 수정 금지: `scripts/precommit-runner.sh`, `scripts/flow_gate_check.py`, `scripts/bump_version.py`, host 복사 script 의 CLI.
- 불변식 1–7 (CLAUDE.md) 유지. 특히 1 FAIL-OPEN, 2 `force_utf8_io`/`encoding="utf-8"`, 4 `if` 필드 금지, 5 idempotent, 7 분류기 단일.
- Codex gate 명령 문자열·플러그인 hook 정의는 상수 — 테스트로 pin (변경 = 전 소비자 `/hooks` 재승인).
- `.codex-plugin/plugin.json` `hooks` 는 `"./hooks/codex/hooks.json"` (`./` 필수). 루트 `plugin.json` 금지.
- 스크립트 호출은 interpreter 접두사(`bash x.sh`, `python3 x.py`, Windows `& "x.cmd"`).
- `.cmd` 파일은 label·`goto` 없음(LF 체크아웃 안전), 괄호 블록 안 `echo` 에 `(` `)` 금지.
- 저장소 언어: 코드·주석·`rules/`·`docs/usage/` 영어(+ `.ko.md` 쌍), `docs/superpowers/` 한국어.
- `.sh` 변경은 WSL ShellCheck (`wsl.exe -d Ubuntu -- shellcheck …`).
- Mutation test 는 Python 으로 적용(`assert old in text`) 하고 **원본 바이트를 메모리에서 복원** — 이 브랜치는 끝까지
  미커밋이라 `git checkout --` 복원 금지(작업 유실).
- 커밋: 모든 태스크 리뷰 통과 후 **단일 커밋**(`/flow` gate: doc-sync → review → `Skill: commit`). 중간 커밋 없음.
- eval·Codex 실측은 사용자 quota — 실행 전 세션 수·모델 보고 후 승인.

## Review Focus

1. **Windows Codex 에서 커밋이 실제로 막히는가** — exit 2 무시(#48183). `gate.cmd` 가 exit 0 + deny JSON 을 내는지, Git Bash 부재 시 commit/merge 명령을 막는지. → Task 4 테스트.
2. **Claude 전용 기존 호스트가 `/flow-init` 재실행 후에도 동일한가** — 새 파일(`scripts/harness/…`, `.codex/`) 생성 없음, settings.json 동일. → Task 3·6 테스트.
3. **shell 안에서 실행된 apply_patch 편집도 marker 를 지우는가, `git add` 같은 일반 Bash 는 지우지 않는가.** → Task 7 테스트.
4. **`.codex/hooks.json` 에 사용자 hook 이 이미 있을 때** 보존·위치 불변(trust key 가 배열 위치 포함), 최상위에 `description`·`hooks` 외 키가 있으면 손대지 않고 보고. → Task 5 테스트.
5. **Codex 에서 8 KB 초과 skill 이 잘려 주입될 때** 모델이 파일을 끝까지 읽는 지시가 매핑 문서에 있는가. → Task 8 테스트(문구 존재).

---

## 파일 구조

```text
scripts/harness/__init__.py            하네스 레지스트리 (KNOWN, SUPPORTED, installer(name))
scripts/harness/jsonfile.py            JSON 파일 안전 읽기·쓰기 (flow_init_setup 에서 이동)
scripts/harness/gate_spec.py           canonical gate IR: GateSpec, GATE
scripts/harness/claude/__init__.py
scripts/harness/claude/install.py      settings.json gate·marketplace 등록/해제/검증 (flow_init_setup 에서 이동)
scripts/harness/codex/__init__.py
scripts/harness/codex/install.py       .codex/hooks.json gate 등록/해제/검증 + trust 확인
scripts/harness/codex/hook_io.py       Codex payload → 편집 경로 (CLI: edited-paths)
scripts/harness/codex/gate.sh          host 복사: 러너 실행, exit 2 → 0
scripts/harness/codex/gate.cmd         host 복사: Windows Git Bash 탐색 → gate.sh
scripts/harness/antigravity/__init__.py stub
scripts/flow_init_setup.py             오케스트레이션, 이동한 이름 re-export, harnesses 설정
hooks/codex/hooks.json                 Codex 플러그인 hook
hooks/codex/run-hook.cmd               Windows: Git Bash 탐색 → hooks/<script>
hooks/antigravity/README.md            자리 표시 (한 줄)
hooks/inject-risk-tiers.sh             --harness codex 분기
hooks/invalidate-gate-markers.sh       --harness codex 분기
.codex-plugin/plugin.json              Codex manifest
.agents/plugins/marketplace.json       Codex marketplace
rules/harness-tools/vocabulary.md      행동 어휘 SSOT (영어)
rules/harness-tools/codex.md           Codex 고유 대응 (영어, SessionStart 주입)
rules/harness-tools/antigravity.md     stub
skills/*/SKILL.md 외 references        행동 어휘로 재작성
skills/<disable-model-invocation>/agents/openai.yaml
flow-config.example.yaml               harnesses 슬롯
scripts/finalize_prerelease.py         .codex-plugin/plugin.json 버전 동기화(존재 시)
pyproject.toml · .github/workflows/release.yml   버전 동기화
docs/usage/codex.md · codex.ko.md · USAGE.md · USAGE.ko.md · README.md · README.ko.md · CLAUDE.md
tests/harness/…                        신규 테스트 (claude/ codex/ 하위, __init__.py 포함)
```

---

### Task 1: JSON 파일 IO 헬퍼를 `scripts/harness/jsonfile.py` 로 추출

동작 보존 리팩터. Claude·Codex installer 가 공유할 `_write_json` 계열을 하네스 중립 모듈로 옮김.

**Files:**
- Create: `scripts/harness/__init__.py` (Task 2 에서 채움 — 여기선 docstring 한 줄), `scripts/harness/jsonfile.py`
- Modify: `scripts/flow_init_setup.py` (`_why`, `_ACCESS_ENTRIES`, `_access_entries`, `_default_mode`, `_carry_over`, `_write_json` 제거 → import 로 대체)
- Modify: `tests/flow_init/test_settings_writes.py` (monkeypatch 대상만 `jsonfile` 로 — 기계적 수정)

**Interfaces:**
- Produces: `scripts.harness.jsonfile` — `why(exc) -> str`, `access_entries(path) -> bytes|None`, `write_json(path, data) -> str|None`, `load_json_object(path, label) -> tuple[dict|None, str|None]`.
  `flow_init_setup` 은 기존 이름 `_why`, `_access_entries`, `_write_json` 을 re-export.

- [ ] **Step 1: 수집 node id 기준선 저장**

Run: `uv run pytest --collect-only -q tests > "$SCRATCH/nodeids-before.txt"`
(`$SCRATCH` = 세션 scratchpad). Expected: 파일 생성, 마지막 줄 `N tests collected`.

- [ ] **Step 2: `jsonfile.py` 작성 — 기존 함수 본문을 그대로 이동**

`flow_init_setup.py` 의 `_why`·`_ACCESS_ENTRIES`·`_access_entries`·`_default_mode`·`_carry_over`·`_write_json` 을
docstring·주석 포함 **바이트 그대로** 옮기고 이름만 공개형으로:

```python
"""Write and read the JSON files an installer touches in a host, without ever leaving a half-written one."""

from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

ACCESS_ENTRIES = "system.posix_acl_access"


def why(exc: BaseException) -> str:
    ...  # body of flow_init_setup._why, unchanged


def access_entries(path: Path) -> bytes | None:
    ...  # body of _access_entries, ACCESS_ENTRIES in place of _ACCESS_ENTRIES


def _default_mode(tmp: Path) -> None:
    ...  # unchanged


def _carry_over(before: os.stat_result, acl: bytes | None, tmp: Path) -> None:
    ...  # unchanged, ACCESS_ENTRIES in place of _ACCESS_ENTRIES


def write_json(path: Path, data: dict) -> str | None:
    ...  # body of _write_json, calling access_entries / why


def load_json_object(path: Path, label: str) -> tuple[dict | None, str | None]:
    """Parse `path` as a JSON object. Absent → ({}, None). Unreadable or not an object →
    (None, the line to report). `label` names the file in that line."""
    try:
        exists = path.is_file()
    except OSError as exc:
        return None, f"  [!] {label} 을 읽지 못했습니다({why(exc)}) — 수동 확인 필요"
    if not exists:
        return {}, None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError:
        return None, f"  [!] {label} 이 UTF-8 이 아닙니다 — 수동 확인 필요"
    except (json.JSONDecodeError, RecursionError):
        return None, f"  [!] {label} 파싱 실패 — 수동 확인 필요"
    except OSError as exc:
        return None, f"  [!] {label} 을 읽지 못했습니다({why(exc)}) — 수동 확인 필요"
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return None, f"  [!] {label} 이 객체가 아닙니다 — 수동 확인 필요"
    return data, None
```

`...` 자리는 기존 본문 복사(여기 재기재 생략이 아니라 **이동** — 새 로직 없음). `load_json_object` 의 문구는
`_load_settings` 의 기존 문구와 `label="settings.json"` 일 때 문자 단위로 같아야 함(Task 2 가 그 위에 얹음).

- [ ] **Step 3: `flow_init_setup.py` 에서 import + re-export**

기존 import 블록(`try: from _harness_paths …`) 아래에:

```python
try:
    from harness.jsonfile import access_entries as _access_entries
    from harness.jsonfile import why as _why
    from harness.jsonfile import write_json as _write_json
except ImportError:
    from scripts.harness.jsonfile import access_entries as _access_entries
    from scripts.harness.jsonfile import why as _why
    from scripts.harness.jsonfile import write_json as _write_json
```

`import stat`, `import tempfile` 가 더는 쓰이지 않으면 제거.

- [ ] **Step 4: 테스트의 monkeypatch 대상 이동 (기계적)**

`tests/flow_init/test_settings_writes.py`: `fis.tempfile` → `jf.tempfile`, `monkeypatch.setattr(fis, "_access_entries", …)` →
`monkeypatch.setattr(jf, "access_entries", …)`, 파일 상단 `import scripts.harness.jsonfile as jf`. 그 외 줄 수정 금지.
`grep -rn "_access_entries\|fis.tempfile\|fis.os\|fis.stat" tests` 로 누락 확인 — `fis.os.getuid/getgid` 는 `os` 모듈
전역 patch 라 그대로 동작하지만 `fis.os` 속성 접근이 남아 있으므로 `fis` 에 `import os` 가 남아 있는지 확인(남아 있음).

- [ ] **Step 5: 전체 테스트 + node id diff**

Run: `uv run pytest -q tests/flow_init tests/flow_gate` → Expected: 전부 PASS.
Run: `uv run pytest --collect-only -q tests > "$SCRATCH/nodeids-after.txt" && diff "$SCRATCH/nodeids-before.txt" "$SCRATCH/nodeids-after.txt"`
Expected: diff 없음.

---

### Task 2: 하네스 레지스트리 + gate IR + Claude installer 이동

**Files:**
- Modify: `scripts/harness/__init__.py`
- Create: `scripts/harness/gate_spec.py`, `scripts/harness/claude/__init__.py`, `scripts/harness/claude/install.py`, `scripts/harness/antigravity/__init__.py`
- Modify: `scripts/flow_init_setup.py` (Claude settings.json 코드 제거 → re-export)
- Test: `tests/harness/__init__.py`, `tests/harness/claude/__init__.py`, `tests/harness/claude/test_gate_spec_render.py`, `tests/harness/test_registry.py`

**Interfaces:**
- Consumes: `scripts.harness.jsonfile.write_json`, `load_json_object`, `why`.
- Produces:
  - `scripts.harness.gate_spec.GateSpec` (frozen dataclass: `runner_rel: str`, `timeout: int`, `status: str`), `GATE: GateSpec`
  - `scripts.harness.KNOWN = ("claude", "codex", "antigravity")`, `SUPPORTED = ("claude", "codex")`,
    `installer(name: str) -> module` (raise `ValueError` for unknown / `NotImplementedError` for antigravity)
  - `scripts.harness.claude.install`: `GATE_MARKER`, `GATE_COMMAND`, `GATE_STATUS`, `GATE_ENTRY`, `MARKETPLACE_NAME`,
    `MARKETPLACE_REPO`, `MARKETPLACE_ENTRY`, `load_settings(host)`, `is_gate_hook(hook)`, `covers_bash(matcher)`,
    `register(host) -> str`, `unregister(host) -> str`, `register_marketplace(host) -> str`,
    `unregister_marketplace(host) -> str`, `problems(host) -> list[str]`, `hook_remains(host) -> bool`
  - `flow_init_setup` re-exports the old names: `GATE_MARKER, GATE_COMMAND, GATE_STATUS, GATE_ENTRY, MARKETPLACE_*,
    _load_settings, _is_gate_hook, _covers_bash, register_gate, unregister_gate, register_marketplace,
    unregister_marketplace, _strip_gate_hooks, _is_own_empty_entry, _gate_hook_remains`.

- [ ] **Step 1: 실패 테스트 — IR 렌더가 기존 GATE_ENTRY 와 동일**

`tests/harness/claude/test_gate_spec_render.py`:

```python
"""The Claude entry rendered from the gate IR is the entry every existing host already carries."""

import scripts.flow_init_setup as fis
from scripts.harness.claude import install
from scripts.harness.gate_spec import GATE

EXISTING_ENTRY = {
    "matcher": "Bash",
    "hooks": [
        {
            "type": "command",
            "shell": "bash",
            "command": 'bash "${CLAUDE_PROJECT_DIR:-.}/.claude/harness-tier/scripts/precommit-runner.sh"',
            "timeout": 600,
            "statusMessage": "harness-tier: flow 게이트 + 테스트 검사 중…",
        }
    ],
}


def test_rendered_claude_entry_is_byte_identical_to_the_shipped_one():
    assert install.GATE_ENTRY == EXISTING_ENTRY


def test_flow_init_setup_reexports_the_same_objects():
    assert fis.GATE_ENTRY is install.GATE_ENTRY
    assert fis.register_gate is install.register
    assert fis._is_gate_hook is install.is_gate_hook


def test_ir_holds_the_values_both_harnesses_render_from():
    assert GATE.runner_rel == ".claude/harness-tier/scripts/precommit-runner.sh"
    assert GATE.timeout == 600
```

`tests/harness/test_registry.py`:

```python
import pytest

from scripts import harness


def test_known_and_supported():
    assert harness.KNOWN == ("claude", "codex", "antigravity")
    assert harness.SUPPORTED == ("claude", "codex")


def test_installer_rejects_unknown_and_stub():
    with pytest.raises(ValueError):
        harness.installer("gemini")
    with pytest.raises(NotImplementedError):
        harness.installer("antigravity")


def test_installer_returns_modules_with_the_shared_contract():
    for name in harness.SUPPORTED:
        mod = harness.installer(name)
        for attr in ("register", "unregister", "problems", "hook_remains"):
            assert callable(getattr(mod, attr)), (name, attr)
```

`tests/harness/__init__.py`, `tests/harness/claude/__init__.py`, `tests/harness/codex/__init__.py`: 빈 파일.

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest -q tests/harness` → Expected: FAIL (`ModuleNotFoundError: scripts.harness.gate_spec`).

- [ ] **Step 3: `gate_spec.py`**

```python
"""The commit gate, said once. Each harness package renders its own hook entry from this."""

from __future__ import annotations

from dataclasses import dataclass

try:
    from _harness_paths import SCRIPTS_DIR
except ImportError:
    from scripts._harness_paths import SCRIPTS_DIR


@dataclass(frozen=True)
class GateSpec:
    runner_rel: str
    timeout: int
    status: str


GATE = GateSpec(
    runner_rel=f"{SCRIPTS_DIR}/precommit-runner.sh",
    timeout=600,
    status="harness-tier: flow 게이트 + 테스트 검사 중…",
)
```

(`scripts/harness/` 모듈이 sibling import 로 `_harness_paths` 를 찾으려면 `scripts/` 가 `sys.path` 에 있어야 함 —
`flow_init_setup.py` 를 스크립트로 실행하면 이미 그 상태, 테스트는 `scripts.` fallback.)

- [ ] **Step 4: `harness/__init__.py` 레지스트리**

```python
"""Which agent harnesses this plugin installs its gate into, and the package that does it for each."""

from __future__ import annotations

import importlib

KNOWN = ("claude", "codex", "antigravity")
SUPPORTED = ("claude", "codex")


def installer(name: str):
    if name not in KNOWN:
        raise ValueError(f"unknown harness: {name}")
    if name not in SUPPORTED:
        raise NotImplementedError(f"harness not supported yet: {name}")
    try:
        return importlib.import_module(f"harness.{name}.install")
    except ImportError:
        return importlib.import_module(f"scripts.harness.{name}.install")
```

`scripts/harness/antigravity/__init__.py`:

```python
"""Placeholder: Antigravity has no SessionStart event and a different hook payload; nothing installs here yet."""
```

- [ ] **Step 5: `claude/install.py` — 코드 이동**

`flow_init_setup.py` 에서 다음을 **본문·docstring 그대로** 이동: `GATE_MARKER`, `GATE_COMMAND`, `GATE_STATUS`, `GATE_ENTRY`
(주석 포함), `MARKETPLACE_NAME/REPO/ENTRY`(주석 포함), `_load_settings` → `load_settings`, `_is_gate_hook` → `is_gate_hook`,
`_EXACT_MATCHER_RE`, `_covers_bash` → `covers_bash`, `register_gate` → `register`, `register_marketplace`,
`_strip_gate_hooks`, `_is_own_empty_entry`, `unregister_gate` → `unregister`, `unregister_marketplace`,
`_gate_hook_remains` → `hook_remains`. 이동 후 단 두 가지 변경:

```python
from ..gate_spec import GATE  # (try/except 로 harness.gate_spec / scripts.harness.gate_spec)

GATE_COMMAND = f'bash "${{CLAUDE_PROJECT_DIR:-.}}/{GATE.runner_rel}"'
GATE_STATUS = GATE.status
# GATE_ENTRY 의 "timeout": GATE.timeout
```

`load_settings` 는 `jsonfile.load_json_object(settings, "settings.json")` 위에 mkdir 단계만 얹음:

```python
def load_settings(host: Path) -> tuple[Path, dict | None, str | None]:
    """Return the settings.json path·parse result. On parse failure, (path, None, error message)."""
    settings = host / ".claude" / "settings.json"
    try:
        settings.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return settings, None, f"  [!] .claude 를 만들지 못했습니다({why(exc)}) — 수동 확인 필요"
    data, err = load_json_object(settings, "settings.json")
    return settings, data, err
```

`_gate_problems` 의 settings 부분(“settings.json 을 읽지 못해…” 이하, `disableAllHooks` 까지)을 `problems(host)` 로
이동 — 문자열·순서 불변. `flow_init_setup._gate_problems` 는 파일 검사 목록 뒤에 `problems.extend(install.problems(host))`.

- [ ] **Step 6: `flow_init_setup.py` re-export**

```python
try:
    from harness.claude import install as _claude
except ImportError:
    from scripts.harness.claude import install as _claude

GATE_MARKER = _claude.GATE_MARKER
GATE_COMMAND = _claude.GATE_COMMAND
GATE_STATUS = _claude.GATE_STATUS
GATE_ENTRY = _claude.GATE_ENTRY
MARKETPLACE_NAME = _claude.MARKETPLACE_NAME
MARKETPLACE_REPO = _claude.MARKETPLACE_REPO
MARKETPLACE_ENTRY = _claude.MARKETPLACE_ENTRY
_load_settings = _claude.load_settings
_is_gate_hook = _claude.is_gate_hook
_covers_bash = _claude.covers_bash
register_gate = _claude.register
unregister_gate = _claude.unregister
register_marketplace = _claude.register_marketplace
unregister_marketplace = _claude.unregister_marketplace
_strip_gate_hooks = _claude._strip_gate_hooks
_is_own_empty_entry = _claude._is_own_empty_entry
_gate_hook_remains = _claude.hook_remains
```

- [ ] **Step 7: 통과 확인 + 기존 테스트 무수정 green + node id diff**

Run: `uv run pytest -q tests/harness tests/flow_init tests/flow_gate` → Expected: PASS.
Run: collect-only diff (Task 1 Step 5 와 동일, 이번엔 `tests/harness` 신규 id 만 추가돼야 함).
Run: `git diff --stat -- tests/flow_init tests/flow_gate` → Expected: Task 1 의 `test_settings_writes.py` 외 변경 없음.

---

### Task 3: 상대 경로 보존 복사 + 하네스별 복사 목록

**Files:**
- Modify: `scripts/flow_init_setup.py` (`copy_artifacts`, `GATE_FILES`, 신규 `HARNESS_COPY_FILES`, `gate_files(harnesses)`)
- Test: `tests/harness/test_copy_paths.py`

**Interfaces:**
- Produces: `HARNESS_COPY_FILES: dict[str, list[str]]` (`{"codex": ["scripts/harness/codex/gate.sh", "scripts/harness/codex/gate.cmd"]}`),
  `copy_artifacts(plugin, host, harnesses=("claude",)) -> list[str]`, `gate_files(harnesses) -> tuple[tuple[str, str], ...]`.
- Destination rule: `scripts/<rel>` → `<host>/.claude/harness-tier/scripts/<rel minus "scripts/">` — 평탄 파일의 목적지는 기존과 동일.

- [ ] **Step 1: 실패 테스트**

```python
"""A file copied into the host lands at its path under scripts/, so two harnesses may ship the same basename."""

from pathlib import Path

import scripts.flow_init_setup as fis
from tests.flow_init._helpers import PLUGIN

DEST = Path(".claude/harness-tier/scripts")


def test_flat_files_keep_their_destination(tmp_path: Path):
    fis.copy_artifacts(PLUGIN, tmp_path)
    for rel in fis.COPY_FILES:
        assert (tmp_path / DEST / Path(rel).name).is_file(), rel


def test_claude_only_host_gets_no_harness_tree(tmp_path: Path):
    fis.copy_artifacts(PLUGIN, tmp_path)
    assert not (tmp_path / DEST / "harness").exists()


def test_codex_files_keep_their_subpath(tmp_path: Path):
    fis.copy_artifacts(PLUGIN, tmp_path, harnesses=("claude", "codex"))
    assert (tmp_path / DEST / "harness" / "codex" / "gate.sh").is_file()
    assert (tmp_path / DEST / "harness" / "codex" / "gate.cmd").is_file()


def test_gate_files_include_codex_wrappers_only_when_enabled():
    claude_only = {rel for rel, _ in fis.gate_files(("claude",))}
    both = {rel for rel, _ in fis.gate_files(("claude", "codex"))}
    assert not any("harness/codex" in r for r in claude_only)
    assert {f"{DEST.as_posix()}/harness/codex/gate.sh", f"{DEST.as_posix()}/harness/codex/gate.cmd"} <= both
```

(`gate.sh`/`gate.cmd` 는 Task 4 산출물 — **Task 4 를 Task 3 보다 먼저 실행**.)

- [ ] **Step 2: 실패 확인** — `uv run pytest -q tests/harness/test_copy_paths.py` → FAIL (`unexpected keyword 'harnesses'`).

- [ ] **Step 3: 구현**

```python
HARNESS_COPY_FILES: dict[str, list[str]] = {
    "codex": ["scripts/harness/codex/gate.sh", "scripts/harness/codex/gate.cmd"],
}


def _dest_rel(rel: str) -> Path:
    """Where a SOURCE path under scripts/ lands under the host scripts dir."""
    parts = Path(rel).parts
    return Path(*parts[1:]) if parts and parts[0] == "scripts" else Path(Path(rel).name)


def gate_files(harnesses) -> tuple[tuple[str, str], ...]:
    extra = tuple(
        (f"{SCRIPTS_DIR}/{_dest_rel(rel).as_posix()}", rel)
        for name in harnesses
        for rel in HARNESS_COPY_FILES.get(name, [])
    )
    return GATE_FILES + extra
```

`copy_artifacts(plugin, host, harnesses=("claude",))`: 루프 대상을
`[*COPY_FILES, *(rel for n in harnesses for rel in HARNESS_COPY_FILES.get(n, []))]` 로, 목적지를
`dest_dir / _dest_rel(rel)` (부모 `mkdir(parents=True, exist_ok=True)`), 보고 문자열은 평탄 파일일 때 기존과 같도록
`_dest_rel(rel).as_posix()` 사용(평탄이면 basename 과 동일). `missed & set(GATE_SCRIPT_SOURCES)` 검사는 그대로.
`_gate_problems(host, plugin, harnesses=("claude",))` 는 `gate_files(harnesses)` 로 검사.

- [ ] **Step 4: 통과** — `uv run pytest -q tests/harness/test_copy_paths.py tests/flow_init` → PASS.

---

### Task 4: Codex gate wrapper (`gate.sh`, `gate.cmd`)

**Files:**
- Create: `scripts/harness/codex/__init__.py` (빈 docstring), `scripts/harness/codex/gate.sh`, `scripts/harness/codex/gate.cmd`
- Test: `tests/harness/codex/test_gate_wrapper.py`

**Interfaces:**
- Produces: host 경로 `.claude/harness-tier/scripts/harness/codex/gate.sh` — stdin 을 러너(`../../precommit-runner.sh`)에 전달,
  러너 exit 2 → 0 (stdout 의 deny JSON 이 차단), 그 외 exit 그대로.

- [ ] **Step 1: 실패 테스트** (가짜 러너로 wrapper 만 검증)

```python
"""Codex reads the deny JSON, not exit 2 (Windows pwsh rewrites 2 to 1), so the wrapper turns the runner's 2 into 0."""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.invalidate_gate_markers._helpers import BASH  # repo-visible bash (Git Bash on Windows)

REPO = Path(__file__).resolve().parents[3]
WRAP_SH = REPO / "scripts" / "harness" / "codex" / "gate.sh"
WRAP_CMD = REPO / "scripts" / "harness" / "codex" / "gate.cmd"
DENY = {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny",
                               "permissionDecisionReason": "fake"}}


def _host(tmp_path: Path, runner_exit: int) -> Path:
    scripts = tmp_path / "scripts"
    (scripts / "harness" / "codex").mkdir(parents=True)
    shutil.copyfile(WRAP_SH, scripts / "harness" / "codex" / "gate.sh")
    shutil.copyfile(WRAP_CMD, scripts / "harness" / "codex" / "gate.cmd")
    body = f"cat > /dev/null\nprintf '%s\\n' '{json.dumps(DENY)}'\nexit {runner_exit}\n"
    (scripts / "precommit-runner.sh").write_text(body, encoding="utf-8", newline="\n")
    return scripts / "harness" / "codex"


@pytest.mark.skipif(BASH is None, reason="a repo-visible bash is required")
@pytest.mark.parametrize("runner_exit,want", [(2, 0), (0, 0), (1, 1)])
def test_sh_maps_only_exit_2(tmp_path, runner_exit, want):
    where = _host(tmp_path, runner_exit)
    run = subprocess.run([BASH, (where / "gate.sh").as_posix()], input=b"{}", capture_output=True)
    assert run.returncode == want
    assert json.loads(run.stdout.decode().strip()) == DENY


@pytest.mark.skipif(sys.platform != "win32", reason="cmd wrapper is Windows-only")
def test_cmd_blocks_through_git_bash(tmp_path):
    where = _host(tmp_path, 2)
    run = subprocess.run(["cmd", "/d", "/c", str(where / "gate.cmd")], input=b'{"tool_input":{"command":"git commit"}}',
                         capture_output=True)
    assert run.returncode == 0
    assert json.loads(run.stdout.decode().strip()) == DENY


@pytest.mark.skipif(sys.platform != "win32", reason="cmd wrapper is Windows-only")
def test_cmd_without_git_bash_denies_commit_words_only(tmp_path):
    where = _host(tmp_path, 0)
    env = {**os.environ, "PATH": r"C:\Windows\System32", "ProgramFiles": str(tmp_path / "nowhere")}
    commit = subprocess.run(["cmd", "/d", "/c", str(where / "gate.cmd")], env=env,
                            input=b'{"tool_input":{"command":"git commit -m x"}}', capture_output=True)
    other = subprocess.run(["cmd", "/d", "/c", str(where / "gate.cmd")], env=env,
                           input=b'{"tool_input":{"command":"ls"}}', capture_output=True)
    assert commit.returncode == 0 and "deny" in commit.stdout.decode()
    assert other.returncode == 0 and other.stdout.strip() == b""
```

- [ ] **Step 2: 실패 확인** — `uv run pytest -q tests/harness/codex/test_gate_wrapper.py` → FAIL (파일 없음).

- [ ] **Step 3: `gate.sh`**

```bash
#!/usr/bin/env bash
# Codex's hook for the commit gate. Codex honours the runner's deny JSON, but on Windows the
# PowerShell that runs hooks turns exit 2 into 1, which Codex reads as a failed hook and lets the
# command through — so the runner's 2 becomes 0 here and the JSON alone blocks.
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
bash "$here/../../precommit-runner.sh"
rc=$?
[ "$rc" -eq 2 ] && exit 0
exit "$rc"
```

- [ ] **Step 4: `gate.cmd`** (label 없음, 블록 안 echo 에 괄호 없음)

```bat
@echo off
setlocal
set "GB="
for /f "delims=" %%G in ('where git 2^>nul') do if not defined GB if exist "%%~dpG..\bin\bash.exe" set "GB=%%~dpG..\bin\bash.exe"
if not defined GB if exist "%ProgramFiles%\Git\bin\bash.exe" set "GB=%ProgramFiles%\Git\bin\bash.exe"
if defined GB "%GB%" "%~dp0gate.sh" & exit /b %errorlevel%
findstr /i /c:"commit" /c:"merge" >nul || exit /b 0
echo {"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"harness-tier: the commit gate needs Git Bash - install Git for Windows, then retry."}}
exit /b 0
```

(`gate.sh` 가 이미 2 → 0 변환. Git Bash 부재 시 commit/merge 단어가 있으면 차단 — 러너의 예외 1 과 같은 fail-closed,
나머지 명령은 통과.)

- [ ] **Step 5: 통과 + ShellCheck**

Run: `uv run pytest -q tests/harness/codex/test_gate_wrapper.py` → PASS (Windows 에선 cmd 테스트 포함).
Run: `wsl.exe -d Ubuntu -- bash -lc 'cd /mnt/c/Work/llm_ai/harness-tier && tr -d "\r" < scripts/harness/codex/gate.sh | shellcheck -'` → 출력 없음.

- [ ] **Step 6: Mutation** — Python 으로 `'[ "$rc" -eq 2 ] && exit 0'` 를 `'[ "$rc" -eq 3 ] && exit 0'` 로 치환(assert 존재),
테스트 실행 → `test_sh_maps_only_exit_2[2-0]` FAIL 확인, 원본 바이트 복원 후 PASS 재확인.

---

### Task 5: Codex installer (`.codex/hooks.json`)

**Files:**
- Create: `scripts/harness/codex/install.py`
- Test: `tests/harness/codex/test_install.py`

**Interfaces:**
- Consumes: `jsonfile.write_json`, `load_json_object`, `why`; `gate_spec.GATE`.
- Produces: `GATE_COMMAND`, `GATE_COMMAND_WINDOWS`, `GATE_HOOK` (dict), `GATE_ENTRY`, `register(host) -> str`,
  `unregister(host) -> str`, `problems(host) -> list[str]`, `hook_remains(host) -> bool`, `trust_notes(host, codex_home) -> list[str]`.

- [ ] **Step 1: 실패 테스트**

```python
import json
from pathlib import Path

import pytest

from scripts.harness.codex import install

HOOKS = Path(".codex/hooks.json")

PINNED_COMMAND = 'bash "$(git rev-parse --show-toplevel)/.claude/harness-tier/scripts/harness/codex/gate.sh"'
PINNED_WINDOWS = '& "$(git rev-parse --show-toplevel)/.claude/harness-tier/scripts/harness/codex/gate.cmd"'


def _read(host: Path) -> dict:
    return json.loads((host / HOOKS).read_text(encoding="utf-8"))


def test_command_strings_are_pinned():
    # Changing these makes every consumer re-approve the hook in /hooks.
    assert install.GATE_HOOK == {
        "type": "command",
        "command": PINNED_COMMAND,
        "commandWindows": PINNED_WINDOWS,
        "timeout": 600,
        "statusMessage": "harness-tier: flow 게이트 + 테스트 검사 중…",
    }
    assert install.GATE_ENTRY == {"matcher": "Bash", "hooks": [install.GATE_HOOK]}


def test_register_creates_and_is_idempotent(tmp_path):
    assert "등록" in install.register(tmp_path)
    assert "이미" in install.register(tmp_path)
    data = _read(tmp_path)
    assert data == {"hooks": {"PreToolUse": [install.GATE_ENTRY]}}


def test_register_keeps_user_hooks_and_their_positions(tmp_path):
    (tmp_path / ".codex").mkdir()
    user = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo mine"}]}
    (tmp_path / HOOKS).write_text(json.dumps({"description": "d", "hooks": {"PreToolUse": [user]}}), encoding="utf-8")
    install.register(tmp_path)
    data = _read(tmp_path)
    assert data["description"] == "d"
    assert data["hooks"]["PreToolUse"][0] == user
    assert data["hooks"]["PreToolUse"][1] == install.GATE_ENTRY


def test_register_repairs_a_stale_gate_hook_in_place(tmp_path):
    (tmp_path / ".codex").mkdir()
    stale = {"matcher": "Bash", "hooks": [{"type": "command", "command": 'bash "old/harness-tier/scripts/harness/codex/gate.sh"'}]}
    (tmp_path / HOOKS).write_text(json.dumps({"hooks": {"PreToolUse": [stale]}}), encoding="utf-8")
    assert "보정" in install.register(tmp_path)
    assert _read(tmp_path)["hooks"]["PreToolUse"] == [install.GATE_ENTRY]


@pytest.mark.parametrize("bad", ['{"hooks": {}, "extra": 1}', "[]", "{not json"])
def test_register_refuses_files_codex_would_not_load(tmp_path, bad):
    (tmp_path / ".codex").mkdir()
    (tmp_path / HOOKS).write_text(bad, encoding="utf-8")
    assert "[!]" in install.register(tmp_path)
    assert (tmp_path / HOOKS).read_text(encoding="utf-8") == bad


def test_unregister_removes_only_the_gate_and_empty_file(tmp_path):
    install.register(tmp_path)
    assert "해제" in install.unregister(tmp_path)
    assert not (tmp_path / HOOKS).exists()
    assert "없음" in install.unregister(tmp_path)


def test_unregister_keeps_a_file_with_user_hooks(tmp_path):
    (tmp_path / ".codex").mkdir()
    user = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo mine"}]}
    (tmp_path / HOOKS).write_text(json.dumps({"hooks": {"PreToolUse": [user]}}), encoding="utf-8")
    install.register(tmp_path)
    install.unregister(tmp_path)
    assert _read(tmp_path) == {"hooks": {"PreToolUse": [user]}}


def test_problems_names_a_missing_registration(tmp_path):
    assert any(".codex/hooks.json" in p for p in install.problems(tmp_path))
    install.register(tmp_path)
    assert install.problems(tmp_path) == []


def test_trust_notes_read_the_user_config_without_writing(tmp_path):
    home = tmp_path / "codexhome"
    home.mkdir()
    host = tmp_path / "Host"
    host.mkdir()
    notes = install.trust_notes(host, home)
    assert any("trusted" in n for n in notes)  # not trusted yet → says how
    key = str(host.resolve()).lower()
    (home / "config.toml").write_text(f"[projects.'{key}']\ntrust_level = \"trusted\"\n", encoding="utf-8")
    before = (home / "config.toml").read_bytes()
    notes = install.trust_notes(host, home)
    assert not any("trust_level" in n for n in notes)
    assert any("/hooks" in n for n in notes)  # hook approval is always a reminder
    assert (home / "config.toml").read_bytes() == before
```

- [ ] **Step 2: 실패 확인** — FAIL (`install` 없음).

- [ ] **Step 3: 구현**

```python
"""Register the commit gate in a host's .codex/hooks.json — Codex's project hook file.

Codex loads the file only in a trusted project and runs a hook only once the user has approved it in
/hooks; approval is keyed by the hook's content and position, so the command strings below are fixed
and the gate entry is appended, never inserted.
"""

from __future__ import annotations

import copy
import os
import re
from pathlib import Path

try:
    from harness.gate_spec import GATE
    from harness.jsonfile import load_json_object, write_json
except ImportError:
    from scripts.harness.gate_spec import GATE
    from scripts.harness.jsonfile import load_json_object, write_json

_WRAPPER = GATE.runner_rel.rsplit("/", 1)[0] + "/harness/codex/gate"
GATE_COMMAND = f'bash "$(git rev-parse --show-toplevel)/{_WRAPPER}.sh"'
GATE_COMMAND_WINDOWS = f'& "$(git rev-parse --show-toplevel)/{_WRAPPER}.cmd"'
GATE_HOOK = {
    "type": "command",
    "command": GATE_COMMAND,
    "commandWindows": GATE_COMMAND_WINDOWS,
    "timeout": GATE.timeout,
    "statusMessage": GATE.status,
}
GATE_ENTRY = {"matcher": "Bash", "hooks": [GATE_HOOK]}
MARKER = ("harness-tier", "harness/codex/gate")
ALLOWED_TOP = {"description", "hooks"}


def _path(host: Path) -> Path:
    return host / ".codex" / "hooks.json"


def _is_gate(hook: object) -> bool:
    return isinstance(hook, dict) and isinstance(hook.get("command"), str) and all(
        w in hook["command"] for w in MARKER
    )


def _load(host: Path) -> tuple[dict | None, str | None]:
    data, err = load_json_object(_path(host), ".codex/hooks.json")
    if data is None:
        return None, err
    if set(data) - ALLOWED_TOP:
        return None, "  [!] .codex/hooks.json 에 description·hooks 외 키가 있어 Codex 가 파일 전체를 읽지 않습니다 — 수동 확인 필요"
    if not isinstance(data.get("hooks", {}), dict) or not isinstance(
        data.get("hooks", {}).get("PreToolUse", []), list
    ):
        return None, "  [!] .codex/hooks.json hooks 형식 비정상 — 게이트 미등록(수동 확인)"
    return data, None


def _entries(data: dict) -> list:
    return data.get("hooks", {}).get("PreToolUse", [])


def register(host: Path) -> str:
    data, err = _load(host)
    if data is None:
        return err
    entries = _entries(data)
    gate_hooks = [h for e in entries if isinstance(e, dict) and isinstance(e.get("hooks"), list)
                  for h in e["hooks"] if _is_gate(h)]
    if any(h == GATE_HOOK for h in gate_hooks) and all(h == GATE_HOOK for h in gate_hooks):
        return "  [=] Codex 커밋 게이트 이미 등록됨 (skip)"
    if gate_hooks:
        for h in gate_hooks:
            h.clear()
            h.update(copy.deepcopy(GATE_HOOK))
        verb = "보정"
    else:
        data.setdefault("hooks", {}).setdefault("PreToolUse", []).append(copy.deepcopy(GATE_ENTRY))
        verb = "등록"
    try:
        _path(host).parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return f"  [!] .codex 를 만들지 못했습니다({exc}) — 수동 확인 필요"
    failed = write_json(_path(host), data)
    return failed or f"  [+] Codex 커밋 게이트 {verb} (.codex/hooks.json — Codex 의 /hooks 에서 승인해야 실행)"


def unregister(host: Path) -> str:
    if not _path(host).is_file():
        return "  [=] Codex 게이트 훅 없음 (skip)"
    data, err = _load(host)
    if data is None:
        return err
    removed = 0
    kept_entries = []
    for e in _entries(data):
        if isinstance(e, dict) and isinstance(e.get("hooks"), list):
            before = len(e["hooks"])
            e["hooks"] = [h for h in e["hooks"] if not _is_gate(h)]
            removed += before - len(e["hooks"])
            if before and not e["hooks"] and set(e) == {"matcher", "hooks"}:
                continue
        kept_entries.append(e)
    if not removed:
        return "  [=] Codex 게이트 훅 없음 (skip)"
    hooks = data.setdefault("hooks", {})
    if kept_entries:
        hooks["PreToolUse"] = kept_entries
    else:
        hooks.pop("PreToolUse", None)
    if not hooks and set(data) <= {"hooks"}:
        try:
            _path(host).unlink()
        except OSError as exc:
            return f"  [!] .codex/hooks.json 삭제 실패({exc}) — 수동 확인 필요"
        return "  [-] Codex 커밋 게이트 해제 (.codex/hooks.json 삭제 — 남은 훅 없음)"
    failed = write_json(_path(host), data)
    return failed or "  [-] Codex 커밋 게이트 해제 (.codex/hooks.json)"


def problems(host: Path) -> list[str]:
    data, _err = _load(host)
    if data is None:
        return [".codex/hooks.json 을 읽지 못해 Codex 커밋 게이트를 확인할 수 없습니다 — 위 [!] 를 해결한 뒤 /flow-init 를 다시 실행하세요."]
    firing = any(
        isinstance(e, dict) and e.get("matcher") in ("Bash", "", "*", None)
        and isinstance(e.get("hooks"), list) and GATE_HOOK in e["hooks"]
        for e in _entries(data)
    )
    if firing:
        return []
    return ["Codex 커밋 게이트가 .codex/hooks.json 에 없습니다 — 위 [!] 를 해결한 뒤 /flow-init 를 다시 실행하세요."]


def hook_remains(host: Path) -> bool:
    data, _err = _load(host)
    if data is None:
        return _path(host).exists()
    return any(_is_gate(h) for e in _entries(data) if isinstance(e, dict)
               for h in (e.get("hooks") if isinstance(e.get("hooks"), list) else []))


def trust_notes(host: Path, codex_home: Path | None = None) -> list[str]:
    """Warnings, never failures: both remedies are the user's to apply. Reads, never writes."""
    home = codex_home or Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    notes = []
    key = str(host.resolve())
    try:
        text = (home / "config.toml").read_text(encoding="utf-8")
    except OSError:
        text = ""
    trusted = False
    for m in re.finditer(r"^\[projects\.(['\"])(.+?)\1\]\s*$([^\[]*)", text, re.M | re.S):
        same = m.group(2).lower() == key.lower() if os.name == "nt" else m.group(2) == key
        if same and re.search(r'^\s*trust_level\s*=\s*"trusted"', m.group(3), re.M):
            trusted = True
    if not trusted:
        notes.append(f'  [!] Codex 가 이 프로젝트를 trusted 로 모릅니다 — .codex/ 가 무시됩니다. Codex 에서 이 폴더를 신뢰하거나 config.toml 에 [projects."{key}"] trust_level = "trusted"')
    notes.append("  [i] Codex 의 /hooks 에서 harness-tier 게이트 훅을 승인해야 실행됩니다(승인 전엔 조용히 skip).")
    return notes
```

(`re` 기반 읽기: Python 3.8–3.10 에 `tomllib` 없음 — 정확한 TOML 파서가 아니라 경고용 추정, 불확실하면 "미신뢰" 경고 쪽.)

- [ ] **Step 4: 통과** — `uv run pytest -q tests/harness/codex/test_install.py` → PASS.

- [ ] **Step 5: Mutation** — `if gate_hooks:` 를 `if False:` 로(보정 테스트 FAIL 확인), `ALLOWED_TOP = {"description", "hooks"}` 를
`{"description", "hooks", "extra"}` 로(거부 테스트 FAIL 확인). 각각 원본 복원 후 PASS.

---

### Task 6: `harnesses` 설정 + setup/uninstall 배선

**Files:**
- Modify: `scripts/flow_init_setup.py` (`load_harnesses`, `register_gates`, `run_setup`, `run_uninstall`, `_gate_problems`)
- Modify: `flow-config.example.yaml` (주석 슬롯)
- Modify: `skills/flow-init/SKILL.md` + `skills/flow-init/references/setup-script-actions.md` (Codex 제안 단계, 행동 어휘로)
- Test: `tests/harness/test_setup_wiring.py`

**Interfaces:**
- Consumes: `harness.installer(name)`, `claude.install`, `codex.install.trust_notes`.
- Produces: `load_harnesses(host) -> tuple[list[str], list[str]]` (harnesses, report lines), `register_gates(host, harnesses) -> list[str]`.

- [ ] **Step 1: 실패 테스트**

```python
import json
from pathlib import Path

import scripts.flow_init_setup as fis
from tests.flow_init._helpers import PLUGIN

CFG = Path(".claude/harness-tier/config/flow-config.yaml")


def _cfg(host: Path, text: str) -> None:
    (host / CFG).parent.mkdir(parents=True, exist_ok=True)
    (host / CFG).write_text(text, encoding="utf-8")


def test_absent_key_means_claude_only(tmp_path):
    assert fis.load_harnesses(tmp_path)[0] == ["claude"]


def test_claude_is_always_first_and_unknowns_are_reported(tmp_path):
    _cfg(tmp_path, "harnesses: [codex, gemini, antigravity]\n")
    names, lines = fis.load_harnesses(tmp_path)
    assert names == ["claude", "codex"]
    assert any("gemini" in l for l in lines) and any("antigravity" in l for l in lines)


def test_claude_only_setup_writes_nothing_for_codex(tmp_path):
    fis.run_setup(tmp_path, PLUGIN)
    assert not (tmp_path / ".codex").exists()
    assert not (tmp_path / ".claude/harness-tier/scripts/harness").exists()


def test_codex_setup_registers_both(tmp_path):
    _cfg(tmp_path, "harnesses: [claude, codex]\n")
    assert fis.run_setup(tmp_path, PLUGIN)
    assert (tmp_path / ".codex/hooks.json").is_file()
    assert json.loads((tmp_path / ".claude/settings.json").read_text(encoding="utf-8"))["hooks"]["PreToolUse"]


def test_uninstall_clears_codex_even_when_config_dropped_it(tmp_path):
    _cfg(tmp_path, "harnesses: [claude, codex]\n")
    fis.run_setup(tmp_path, PLUGIN)
    _cfg(tmp_path, "harnesses: [claude]\n")
    assert fis.run_uninstall(tmp_path)
    assert not (tmp_path / ".codex/hooks.json").exists()
```

- [ ] **Step 2: 실패 확인** — FAIL (`load_harnesses` 없음).

- [ ] **Step 3: 구현**

```python
def load_harnesses(host: Path) -> tuple[list[str], list[str]]:
    """The harnesses this host installs the gate into. Claude is always one: the plugin is a Claude
    Code plugin first, and an absent key is every host installed before Codex existed here."""
    cfg = _load_yaml_safe(config_path(host))
    raw = cfg.get("harnesses")
    names = ["claude"]
    lines: list[str] = []
    for name in raw if isinstance(raw, list) else []:
        if name == "claude" or name in names:
            continue
        if name in harness.SUPPORTED:
            names.append(name)
        elif name in harness.KNOWN:
            lines.append(f"  [=] harnesses: {name} 는 아직 지원하지 않습니다 (skip)")
        else:
            lines.append(f"  [!] harnesses: 알 수 없는 이름 '{name}' (skip)")
    return names, lines


def register_gates(host: Path, harnesses: list[str]) -> list[str]:
    out = [register_gate(host)]
    for name in harnesses:
        if name == "claude":
            continue
        mod = harness.installer(name)
        out.append(mod.register(host))
        if name == "codex":
            out.extend(mod.trust_notes(host))
    return out
```

(`harness` 는 `try: import harness / except ImportError: from scripts import harness`.)

`run_setup`: 첫 줄에서 `names, cfg_lines = load_harnesses(host)`; `[복사]` → `copy_artifacts(plugin, host, names)`;
`[커밋 게이트]` → `cfg_lines + register_gates(host, names)`; `_gate_problems(host, plugin, names)` 는 Claude 문제 +
`codex.install.problems(host)` (codex 포함 시). Claude 전용일 때 출력 줄은 기존과 동일해야 함 — `cfg_lines` 가 빈 리스트.

`run_uninstall`: `[커밋 게이트 해제]` 다음에 `_step("[Codex 게이트 해제]", lambda: [harness.installer("codex").unregister(host)])`
— 설정과 무관하게 항상. 마지막 판정은 `_gate_hook_remains(host) or codex.hook_remains(host)`.
**주의:** Claude 전용 호스트의 uninstall 출력에 `[Codex 게이트 해제]` / `  [=] Codex 게이트 훅 없음 (skip)` 두 줄이 추가됨 —
출력 문자열을 비교하는 기존 테스트가 있으면 이 두 줄만큼만 갱신(동작 변화 아님, 보고 추가).

`flow-config.example.yaml` 최상위에 (기존 섹션 스타일 따라):

```yaml
# Agent harnesses the commit gate is installed into. Claude Code is always included.
# harnesses: [claude, codex]
```

`skills/flow-init/SKILL.md`: 설정 대화 단계에 "호스트에 `.codex/` 가 있거나 사용자가 Codex 를 언급하면, Codex 에도 게이트를
설치할지 **ask the user (structured choice)** → yes 면 `flow-config.yaml` 에 `harnesses: [claude, codex]` 기록" 한 항목 추가.
`references/setup-script-actions.md` 의 동작 목록에 Codex 등록·trust 안내·uninstall 항목 추가.

- [ ] **Step 4: 통과** — `uv run pytest -q tests/harness tests/flow_init` → PASS.

---

### Task 7: Codex 편집 무효화 (`hook_io.py` + `invalidate-gate-markers.sh --harness codex`)

**Files:**
- Create: `scripts/harness/codex/hook_io.py`
- Modify: `hooks/invalidate-gate-markers.sh`
- Test: `tests/harness/codex/test_hook_io.py`, `tests/invalidate_gate_markers/test_codex.py`
- Fixture: `tests/harness/codex/fixtures/post_apply_patch.json`, `post_bash_patch.json`, `post_bash_plain.json` (실측 payload 기반)

**Interfaces:**
- Produces: `edited_paths(payload: dict) -> list[str]` (절대 경로), CLI `python3 hook_io.py edited-paths` (stdin JSON → 한 줄에 경로 하나).

- [ ] **Step 1: fixture (실측 형태 그대로)**

`post_apply_patch.json`:

```json
{"session_id":"s","turn_id":"t","cwd":"C:\\host\\repo","hook_event_name":"PostToolUse","model":"m","permission_mode":"bypassPermissions","tool_name":"apply_patch","tool_input":{"command":"*** Begin Patch\n*** Add File: note.txt\n+hi\n*** Update File: src/a.py\n@@\n-x\n+y\n*** Move to: src/b.py\n*** Delete File: old/c.py\n*** End Patch"},"tool_response":"Exit code: 0","tool_use_id":"u"}
```

`post_bash_patch.json`: 같은 형태, `"tool_name":"Bash"`, `"command":"apply_patch <<'EOF'\n*** Begin Patch\n*** Update File: 한글/파일.md\n@@\n-a\n+b\n*** End Patch\nEOF"`.
`post_bash_plain.json`: `"tool_name":"Bash"`, `"command":"git add -A"`.

- [ ] **Step 2: 실패 테스트**

```python
import json
import subprocess
import sys
from pathlib import Path, PureWindowsPath

from scripts.harness.codex.hook_io import edited_paths

FIX = Path(__file__).parent / "fixtures"
HOOK_IO = Path(__file__).resolve().parents[3] / "scripts" / "harness" / "codex" / "hook_io.py"


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _norm(paths):
    return [PureWindowsPath(p).as_posix() for p in paths]


def test_apply_patch_headers_resolve_against_cwd():
    assert _norm(edited_paths(_load("post_apply_patch.json"))) == [
        "C:/host/repo/note.txt", "C:/host/repo/src/a.py", "C:/host/repo/src/b.py", "C:/host/repo/old/c.py"]


def test_patch_run_through_the_shell_counts():
    assert _norm(edited_paths(_load("post_bash_patch.json"))) == ["C:/host/repo/한글/파일.md"]


def test_plain_shell_command_edits_nothing():
    assert edited_paths(_load("post_bash_plain.json")) == []


def test_garbage_is_nothing():
    assert edited_paths({}) == [] and edited_paths({"tool_input": {"command": 5}}) == []


def test_cli_prints_utf8_one_per_line():
    raw = (FIX / "post_bash_patch.json").read_bytes()
    run = subprocess.run([sys.executable, str(HOOK_IO), "edited-paths"], input=raw, capture_output=True,
                         env={"PYTHONUTF8": "0", "PATH": ""})
    assert run.returncode == 0
    assert "한글/파일.md" in PureWindowsPath(run.stdout.decode("utf-8").strip()).as_posix()
```

`tests/invalidate_gate_markers/test_codex.py` (기존 `_helpers` 사용 — 이름은 그 파일의 실제 헬퍼에 맞춤):

```python
"""Codex edits arrive as apply_patch (or a patch run through Bash); both void the evidence, a plain Bash does not."""

import json
import subprocess
from pathlib import Path

import pytest

from tests.invalidate_gate_markers._helpers import BASH, MARKERS, SCRIPT

pytestmark = pytest.mark.skipif(BASH is None, reason="a repo-visible bash is required")


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    flow = repo / ".claude/harness-tier/.flow"
    flow.mkdir(parents=True)
    for m in MARKERS:
        (flow / m).write_text("", encoding="utf-8")
    return repo


def _run(repo: Path, tool: str, command: str) -> subprocess.CompletedProcess:
    payload = {"cwd": str(repo), "hook_event_name": "PostToolUse", "tool_name": tool,
               "tool_input": {"command": command}}
    return subprocess.run([BASH, SCRIPT.as_posix(), "--harness", "codex"], input=json.dumps(payload).encode(),
                          capture_output=True, env={"PATH": __import__("os").environ["PATH"]})


def test_apply_patch_voids(tmp_path):
    repo = _repo(tmp_path)
    _run(repo, "apply_patch", "*** Begin Patch\n*** Update File: a.txt\n*** End Patch")
    assert not any((repo / ".claude/harness-tier/.flow" / m).exists() for m in MARKERS)


def test_bash_patch_voids(tmp_path):
    repo = _repo(tmp_path)
    _run(repo, "Bash", "apply_patch <<'EOF'\n*** Begin Patch\n*** Update File: a.txt\n*** End Patch\nEOF")
    assert not any((repo / ".claude/harness-tier/.flow" / m).exists() for m in MARKERS)


def test_plain_bash_keeps_evidence(tmp_path):
    repo = _repo(tmp_path)
    _run(repo, "Bash", "git add -A")
    assert all((repo / ".claude/harness-tier/.flow" / m).exists() for m in MARKERS)


def test_evidence_dir_edit_is_ignored(tmp_path):
    repo = _repo(tmp_path)
    _run(repo, "apply_patch", "*** Begin Patch\n*** Add File: .claude/harness-tier/.flow/x\n*** End Patch")
    assert all((repo / ".claude/harness-tier/.flow" / m).exists() for m in MARKERS)
```

- [ ] **Step 3: 실패 확인** — FAIL.

- [ ] **Step 4: `hook_io.py`**

```python
"""What a Codex hook payload edited. Codex reports every file edit as `apply_patch` — or as a Bash
command when the model runs apply_patch through the shell — with the patch text as the command and
the paths in its headers, relative to the session cwd."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path, PureWindowsPath

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from _harness_paths import force_utf8_io  # noqa: E402

_HEADER = re.compile(r"^\*\*\* (?:(?:Add|Update|Delete) File|Move to): (.+?)\s*$", re.M)


def edited_paths(payload: dict) -> list[str]:
    if not isinstance(payload, dict):
        return []
    command = (payload.get("tool_input") or {}).get("command") if isinstance(payload.get("tool_input"), dict) else None
    if not isinstance(command, str):
        return []
    tool = payload.get("tool_name")
    if tool == "Bash" and "*** Begin Patch" not in command:
        return []
    if tool not in ("apply_patch", "Bash"):
        return []
    cwd = payload.get("cwd") if isinstance(payload.get("cwd"), str) else ""
    base = cwd.rstrip("/\\")
    out = []
    for rel in _HEADER.findall(command):
        is_abs = rel.startswith("/") or PureWindowsPath(rel).is_absolute()
        out.append(rel if is_abs or not base else base + "/" + rel)
    return out


def main(argv: list[str]) -> int:
    force_utf8_io()
    if argv != ["edited-paths"]:
        return 2
    try:
        payload = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return 0
    for p in edited_paths(payload):
        print(p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
```


- [ ] **Step 5: `invalidate-gate-markers.sh` Codex 분기**

`set -uo pipefail` 다음:

```bash
# Which harness sent the payload. Named by the hook entry, never guessed from the environment:
# Codex also sets CLAUDE_PLUGIN_ROOT. No argument is Claude Code, which every existing host is.
HARNESS=claude
[ "${1:-}" = "--harness" ] && HARNESS="${2:-claude}"
```

`payload=…` 읽기 직후, 기존 `path=""` 블록 앞에:

```bash
if [ "$HARNESS" = codex ]; then
  case "$payload" in
    *'"apply_patch"'* | *'*** Begin Patch'*) ;;
    *) exit 0 ;;
  esac
  hook_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  edited="$(printf '%s' "$payload" | python3 "$hook_dir/../scripts/harness/codex/hook_io.py" edited-paths 2>/dev/null)" || edited=""
  targets=""
  while IFS= read -r one; do
    one="$(to_slash "$one")"
    case "$one" in */"$EVIDENCE"/*|"") continue ;; esac
    root="$(root_for "${one%/*}")" || continue
    case $'\n'"$targets"$'\n' in *$'\n'"$root"$'\n'*) ;; *) targets="${targets:+$targets
}$root" ;; esac
  done <<EOF
$edited
EOF
fi
```

기존 `path=""` ~ `esac`(targets 계산) 블록을 `if [ "$HARNESS" != codex ]; then … fi` 로 감쌈(들여쓰기만 변경).
`to_slash` 정의가 이 분기보다 위에 오도록 codex 분기를 `to_slash()` 정의 **뒤**에 둠. 이후 `[ -n "$targets" ] || exit 0`
과 무효화 루프·출력은 공유.

- [ ] **Step 6: 통과 + 기존 무효화 테스트 green + ShellCheck**

Run: `uv run pytest -q tests/harness/codex tests/invalidate_gate_markers` → PASS.
Run: WSL ShellCheck (Task 4 Step 5 형식, `hooks/invalidate-gate-markers.sh`) → 새 경고 없음.

- [ ] **Step 7: Mutation** — `*'*** Begin Patch'*` 줄 제거(Bash patch 테스트 FAIL 확인), `hook_io.py` 의
`if tool == "Bash" and "*** Begin Patch" not in command:` 를 `if False:`(plain bash 테스트 FAIL 확인). 복원 후 PASS.

---

### Task 8: Codex 규칙 주입 + 행동 어휘·매핑 문서

**Files:**
- Create: `rules/harness-tools/vocabulary.md`, `rules/harness-tools/codex.md`, `rules/harness-tools/antigravity.md`
- Modify: `hooks/inject-risk-tiers.sh`
- Test: `tests/harness/codex/test_inject.py`

**Interfaces:**
- Produces: `inject-risk-tiers.sh --harness codex` → `hookSpecificOutput.additionalContext` = Codex 머리말 + risk-tiers + prose 블록 + `<harness-tier-codex-tools>` (codex.md). stale 알림 없음.

- [ ] **Step 1: 실패 테스트**

```python
import json
import subprocess
from pathlib import Path

from tests.test_inject_risk_tiers import BASH, SCRIPT, STARTUP

REPO = Path(__file__).resolve().parents[3]


def _run(*args, env=None):
    return subprocess.run([BASH, SCRIPT.as_posix(), *args], input=STARTUP.encode(), capture_output=True,
                          env=env)


def test_claude_output_unchanged_without_argument():
    import os
    env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(REPO)}
    a = _run(env=env).stdout
    ctx = json.loads(a)["hookSpecificOutput"]["additionalContext"]
    assert "(via the Skill tool)" in ctx
    assert "<harness-tier-codex-tools>" not in ctx


def test_codex_output_names_codex_invocation_and_carries_mapping():
    import os
    env = {**os.environ, "PLUGIN_ROOT": str(REPO), "CLAUDE_PLUGIN_ROOT": str(REPO)}
    out = json.loads(_run("--harness", "codex", env=env).stdout)
    ctx = out["hookSpecificOutput"]["additionalContext"]
    assert out["hookSpecificOutput"]["hookEventName"] == "SessionStart"
    assert "Skill tool" not in ctx.split("<harness-tier-risk-tiers>")[1].split("\n\n")[0]
    assert "$flow" in ctx
    assert (REPO / "rules/harness-tools/codex.md").read_text(encoding="utf-8").strip()[:80] in ctx
    assert "<harness-tier-stale-build>" not in ctx


def test_codex_mapping_covers_the_hard_cases():
    text = (REPO / "rules/harness-tools/codex.md").read_text(encoding="utf-8")
    for needle in ("request_user_input", "numbered", "end your turn", "SKILL.md", "8,000",
                   "spawn_agent", "fork_turns", "update_plan", "allowed-tools", "context: fork"):
        assert needle in text, needle
```

- [ ] **Step 2: 실패 확인** — FAIL.

- [ ] **Step 3: `rules/harness-tools/vocabulary.md`** (영어, doc-style 준수)

```markdown
# Harness action vocabulary

Skill bodies name actions, never a harness's tool. Each harness maps these actions to its own tools;
Claude Code maps them natively, other harnesses read `<harness>.md` beside this file.

| Action (as written in a skill) | Meaning |
|---|---|
| **Ask the user (structured choice)** | Present one question with 2–4 labelled options and wait for the answer before continuing. |
| **Ask the user (multi-select)** | Same, where the user may pick several options. |
| **Invoke skill `<name>`** | Load that skill's instructions in full and follow them now. |
| **Dispatch subagent `<role>`** | Run a separate agent with the role file `agents/<role>.md` and the task; use its report. |
| **Dispatch subagent (general)** | Same, with no role file. |
| **Track steps** | Keep a visible checklist of the steps and their status. |
| **Plugin root** | The directory holding this plugin, spelled `${CLAUDE_PLUGIN_ROOT}` in commands. |

A skill that needs a capability a harness lacks says what to do instead inline, never by tool name.
```

- [ ] **Step 4: `rules/harness-tools/codex.md`** (영어)

```markdown
# Codex tool notes

Harness-tier skills name actions (`vocabulary.md` beside this file). On Codex they map as follows.

- **Ask the user (structured choice):** call `request_user_input` when it is in your tool list (Plan
  mode). Otherwise write the question and numbered options in chat, then end your turn and wait for
  the reply — do not pick an option yourself. For multi-select, ask for one or more numbers.
- **Invoke skill `<name>`:** open that skill's `SKILL.md` from the skills list and follow it in full.
  When an injected skill body ends in a truncation warning (Codex cuts at 8,000 bytes), read the
  whole `SKILL.md` file before acting.
- **Dispatch subagent `<role>`:** call `spawn_agent` with `fork_turns: "none"` (V2) or
  `fork_context: false` (V1), passing the text of `agents/<role>.md` followed by the task as the
  message. Without a subagent tool, do the work inline.
- **Track steps:** use `update_plan` when available, else a checklist in chat.
- **Plugin root:** Codex does not substitute `${CLAUDE_PLUGIN_ROOT}` inside skills. Replace it with
  the directory two levels above the `SKILL.md` you are following.
- **Skill frontmatter:** Codex ignores `allowed-tools`, `context: fork`, `agent` and `model`. A skill
  marked `context: fork` runs inline.
- **Commit gate:** a commit is blocked by a hook that returns a deny decision; read its reason and
  fix the cause — never work around it.
```

`antigravity.md`: `# Antigravity tool notes` + 한 줄 "Not supported yet: no SessionStart event, no user-question tool; see the Codex notes for the shape a port takes." (영어).

- [ ] **Step 5: `inject-risk-tiers.sh`**

`set -uo pipefail` 다음 Task 7 과 같은 `HARNESS` 파싱 3줄. `PLUGIN_ROOT=` 줄은 그대로(Codex 도 `CLAUDE_PLUGIN_ROOT` 주입).
`notice="$(published_notice)"` 를 `notice=""; [ "$HARNESS" = claude ] && notice="$(published_notice)"` 로.
`session_context=` 줄 앞에:

```bash
invoke_as="the /flow skill (via the Skill tool)"
[ "$HARNESS" = codex ] && invoke_as='the $flow skill (open its SKILL.md and follow it in full)'
```

`session_context` 문자열의 `invoke the /flow skill (via the Skill tool)` 을 `invoke ${invoke_as}` 로 — Claude 에선 문자 단위 동일.
출력 분기 앞에:

```bash
if [ "$HARNESS" = codex ]; then
  tools_file="${PLUGIN_ROOT}/rules/harness-tools/codex.md"
  if [ -f "$tools_file" ] && tools_content="$(cat "$tools_file" 2>/dev/null)"; then
    session_context="${session_context}\n\n<harness-tier-codex-tools>\n$(escape_for_json "$tools_content")\n</harness-tier-codex-tools>"
  fi
  printf '{\n  "hookSpecificOutput": {\n    "hookEventName": "SessionStart",\n    "additionalContext": "%s"\n  }\n}\n' "$session_context"
  exit 0
fi
```

- [ ] **Step 6: 통과 + 기존 inject 테스트 green + ShellCheck + evals 규칙 테스트**

Run: `uv run pytest -q tests/harness/codex/test_inject.py tests/test_inject_risk_tiers.py tests/evals/test_injected_rule.py` → PASS.
Run: WSL ShellCheck on `hooks/inject-risk-tiers.sh` → 새 경고 없음.
Run: `python3 scripts/doc_style_check.py --lint rules/harness-tools/*.md` → error 0.

- [ ] **Step 7: Mutation** — `[ "$HARNESS" = codex ] && invoke_as=` 줄 제거 → codex 테스트 FAIL 확인, 복원.

---

### Task 9: Codex 플러그인 패키징 + 버전 동기화

**Files:**
- Create: `.codex-plugin/plugin.json`, `.agents/plugins/marketplace.json`, `hooks/codex/hooks.json`, `hooks/codex/run-hook.cmd`, `hooks/antigravity/README.md`
- Modify: `pyproject.toml` (`version_variables`), `scripts/finalize_prerelease.py`, `.github/workflows/release.yml`
- Test: `tests/harness/codex/test_packaging.py`, `tests/release_level/` 기존 + `tests/test_finalize_prerelease.py` 에 케이스 추가

**Interfaces:**
- Produces: Codex 가 설치 가능한 manifest·marketplace; release 가 두 manifest 버전을 함께 올림.

- [ ] **Step 1: 실패 테스트**

```python
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
CODEX = json.loads((REPO / ".codex-plugin/plugin.json").read_text(encoding="utf-8"))
CLAUDE = json.loads((REPO / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
HOOKS = json.loads((REPO / "hooks/codex/hooks.json").read_text(encoding="utf-8"))


def test_versions_and_names_match():
    assert CODEX["name"] == CLAUDE["name"] and CODEX["version"] == CLAUDE["version"]


def test_hooks_field_points_at_the_codex_file():
    # Absent, "[]", or a path without "./" makes Codex auto-register the Claude hooks/hooks.json.
    assert CODEX["hooks"] == "./hooks/codex/hooks.json"
    assert CODEX["skills"] == "./skills/"


def test_no_root_plugin_json():
    # A root plugin.json switches Codex to the Agent Plugins loader and silently disables every hook.
    assert not (REPO / "plugin.json").exists()


def test_marketplace_lists_the_plugin():
    mk = json.loads((REPO / ".agents/plugins/marketplace.json").read_text(encoding="utf-8"))
    (entry,) = mk["plugins"]
    assert entry["name"] == CODEX["name"] and entry["source"] == {"source": "url", "url": "./"}


def test_codex_hooks_file_shape_is_pinned():
    assert set(HOOKS) <= {"description", "hooks"}
    (start,) = HOOKS["hooks"]["SessionStart"]
    (post,) = HOOKS["hooks"]["PostToolUse"]
    assert start["hooks"][0]["additionalContextLimit"] == 0
    assert post["matcher"] == "apply_patch|Bash"
    for h in (start["hooks"][0], post["hooks"][0]):
        assert h["command"].startswith('bash "${PLUGIN_ROOT}/hooks/') and h["command"].endswith("--harness codex")
        assert h["commandWindows"].startswith('& "${PLUGIN_ROOT}/hooks/codex/run-hook.cmd" ')


def test_cmd_files_have_no_labels():
    for p in (REPO / "hooks/codex/run-hook.cmd", REPO / "scripts/harness/codex/gate.cmd"):
        text = p.read_text(encoding="utf-8")
        assert not re.search(r"^\s*:[A-Za-z]", text, re.M) and "goto" not in text.lower(), p
```

- [ ] **Step 2: 실패 확인** — FAIL.

- [ ] **Step 3: 파일 작성**

`.codex-plugin/plugin.json`:

```json
{
  "name": "harness-tier",
  "version": "0.4.1",
  "description": "harness-tier risk-tiered workflow + Teams notification harness",
  "author": { "name": "foryouself83" },
  "homepage": "https://github.com/foryouself83/harness-tier",
  "repository": "https://github.com/foryouself83/harness-tier",
  "skills": "./skills/",
  "hooks": "./hooks/codex/hooks.json",
  "interface": {
    "displayName": "harness-tier",
    "shortDescription": "Risk-tiered workflow with a commit gate",
    "developerName": "foryouself83",
    "category": "Developer Tools",
    "capabilities": ["Interactive", "Read", "Write"]
  }
}
```

(`version` 은 작성 시점 `.claude-plugin/plugin.json` 값과 동일하게.)

`.agents/plugins/marketplace.json`:

```json
{
  "name": "harness-tier",
  "interface": { "displayName": "harness-tier" },
  "plugins": [
    {
      "name": "harness-tier",
      "source": { "source": "url", "url": "./" },
      "policy": { "installation": "AVAILABLE", "authentication": "ON_INSTALL" },
      "category": "Developer Tools"
    }
  ]
}
```

`hooks/codex/hooks.json`:

```json
{
  "description": "harness-tier for Codex: inject the risk-tiers rule, void gate evidence on edits.",
  "hooks": {
    "SessionStart": [
      {
        "matcher": "startup|clear|compact",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${PLUGIN_ROOT}/hooks/inject-risk-tiers.sh\" --harness codex",
            "commandWindows": "& \"${PLUGIN_ROOT}/hooks/codex/run-hook.cmd\" inject-risk-tiers.sh --harness codex",
            "timeout": 30,
            "additionalContextLimit": 0
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "apply_patch|Bash",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${PLUGIN_ROOT}/hooks/invalidate-gate-markers.sh\" --harness codex",
            "commandWindows": "& \"${PLUGIN_ROOT}/hooks/codex/run-hook.cmd\" invalidate-gate-markers.sh --harness codex",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

`hooks/codex/run-hook.cmd`:

```bat
@echo off
setlocal
set "GB="
for /f "delims=" %%G in ('where git 2^>nul') do if not defined GB if exist "%%~dpG..\bin\bash.exe" set "GB=%%~dpG..\bin\bash.exe"
if not defined GB if exist "%ProgramFiles%\Git\bin\bash.exe" set "GB=%ProgramFiles%\Git\bin\bash.exe"
if not defined GB exit /b 0
"%GB%" "%~dp0..\%~1" %2 %3
exit /b %errorlevel%
```

(Git Bash 없으면 규칙 주입·무효화는 FAIL-OPEN — gate 는 `gate.cmd` 가 따로 막음.)

`hooks/antigravity/README.md`: `# Antigravity hooks` + "Not registered yet — see `rules/harness-tools/antigravity.md`." (영어).

- [ ] **Step 4: 버전 동기화**

`pyproject.toml`: `version_variables = [".claude-plugin/plugin.json:version", ".codex-plugin/plugin.json:version"]`.
`scripts/finalize_prerelease.py` `finalize()` 와 `set_version()` 끝에 공통 헬퍼 호출:

```python
def _stamp_codex(root: Path, version: str) -> None:
    """The Codex manifest carries the same version; a host without one is untouched."""
    codex = root / ".codex-plugin" / "plugin.json"
    if not codex.exists():
        return
    text = codex.read_text(encoding="utf-8")
    codex.write_text(re.subn(r'("version"\s*:\s*)"[^"]*"', r'\g<1>"' + version + '"', text, count=1)[0],
                     encoding="utf-8")
```

`.github/workflows/release.yml` 의 두 `git add` 줄 옆에 `[ -f .codex-plugin/plugin.json ] && git add .codex-plugin/plugin.json`.
`tests/test_finalize_prerelease.py` 에 케이스 추가: `.codex-plugin/plugin.json` 있으면 둘 다 같은 버전, 없으면 기존과 동일.

- [ ] **Step 5: 통과** — `uv run pytest -q tests/harness tests/release_level tests/test_finalize_prerelease.py tests/test_release_workflow.py` → PASS.
템플릿 parity 테스트가 `release.yml` 변경을 잡으면 같은 줄을 `github/release.python-semantic-release.workflow.example.yml`
에도 동일하게 추가(소비자엔 `.codex-plugin` 이 없어 no-op).

---

### Task 10: 질문 표현 A/B 탐침 (skill 재작성 전, 사용자 승인 필요)

행동 어휘 "Ask the user (structured choice)" 가 Claude 에서 AskUserQuestion 으로 이어지는지 재작성 **전에** 확인 (R9).

**Files:**
- Create (scratchpad only, 커밋 안 함): `$SCRATCH/ask-ab/` 에 skill 두 벌 — 동일 본문에 질문 단계 한 줄만
  A: "Use AskUserQuestion to ask which color the user wants: red, blue." / B: "Ask the user (structured choice) which color they want: red, blue."

- [ ] **Step 1: 비용 보고 후 승인** — "Sonnet `claude -p` 10 세션(A 5, B 5), 각 max-turns 3" 을 사용자에게 보고, 승인 대기.
- [ ] **Step 2: 실행** — 각 변형을 `--plugin-dir` 로 로드한 `claude -p "/ab-probe" --output-format stream-json --verbose --max-turns 3 --model sonnet`
  (evals/run.py 와 같은 격리 `CLAUDE_CONFIG_DIR`). stream 에서 `tool_use` 이름 `AskUserQuestion` 출현 세션 수 집계.
- [ ] **Step 3: 판정** — B 가 A 보다 낮으면(예: 5/5 대 3/5) 어휘 문구를 "Ask the user with a structured multiple-choice question"
  로 바꿔 B 만 재측정. 결과(조건·n 포함)를 `docs/superpowers/reference/claude-code-vs-codex.md` §5 에 기록.

---

### Task 11: skill·rule·agent 본문을 행동 어휘로 재작성 + 어휘 lint + `openai.yaml`

**Files:**
- Modify: `skills/**/SKILL.md`, `skills/**/references/*.md`, `agents/*.md`, `rules/harness-rules.md`, `rules/risk-tiers.md`(도구명 있을 때만), `skills/harness-authoring/references/agent-design-guide.md`
- Create: `skills/{design-api,design-architecture,design-erd,design-sds,design-srs,design-table,flow-init,flow-uninstall,harness-deployments,harness-init,wiki-init}/agents/openai.yaml`
- Test: `tests/skills/test_harness_vocabulary.py`

- [ ] **Step 1: 실패 테스트**

```python
"""Skills name actions; the harness maps them (rules/harness-tools/). A tool name in a body is a skill only one harness can run."""

import re
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parents[2]
BANNED = re.compile(r"\bAskUserQuestion\b|\bSkill tool\b|\bAgent tool\b|\bsubagent_type\b|\bTeamCreate\b|"
                    r"\bSendMessage\b|\bTaskCreate\b|\bTodoWrite\b|\(`Task` alias\)")
SCOPE = [*REPO.glob("skills/**/*.md"), *REPO.glob("agents/*.md"), *REPO.glob("rules/*.md")]


def _body(p: Path) -> str:
    text = p.read_text(encoding="utf-8")
    return text.split("---", 2)[2] if text.startswith("---") else text


def test_no_harness_tool_names_in_shipped_prose():
    hits = [f"{p.relative_to(REPO)}: {m.group(0)}" for p in SCOPE for m in BANNED.finditer(_body(p))]
    assert hits == []


def test_every_manual_only_skill_hides_from_codex_catalog():
    for skill in REPO.glob("skills/*/SKILL.md"):
        fm = yaml.safe_load(skill.read_text(encoding="utf-8").split("---", 2)[1])
        meta = skill.parent / "agents" / "openai.yaml"
        if fm.get("disable-model-invocation") is True:
            assert yaml.safe_load(meta.read_text(encoding="utf-8")) == {"policy": {"allow_implicit_invocation": False}}, skill
        else:
            assert not meta.exists(), skill


def test_bundled_scripts_are_called_through_an_interpreter():
    bare = re.compile(r"(?<![\w/.\"'-])(?:\./|\$\{CLAUDE_PLUGIN_ROOT\}/|\.claude/harness-tier/)scripts/[\w./-]+\.(?:sh|py)\b")
    hits = []
    for p in SCOPE:
        for line in _body(p).splitlines():
            for m in bare.finditer(line):
                before = line[: m.start()].rstrip().rstrip('"').rstrip()
                if not before.endswith(("bash", "python3", "python", "sh")):
                    hits.append(f"{p.relative_to(REPO)}: {line.strip()[:120]}")
    assert hits == []
```

(마지막 테스트가 설명문 속 경로 언급까지 잡으면 — 예: "`scripts/x.py` 가 …" — 코드 스팬이 아닌 실행 문맥만 보도록 fenced block
안 줄로 한정. 첫 실행에서 오탐 목록을 보고 범위를 좁히되, 실제 bare 실행은 고침.)

- [ ] **Step 2: 실패 확인** — FAIL, 위반 목록 확인 (AskUserQuestion 55곳 + Skill/Agent/Team 표현).

- [ ] **Step 3: 치환 규칙대로 재작성** (파일별 수작업, 문맥 유지. **`git commit`/`git merge` 및 그 플래그 리터럴은 절대 손대지 않음 — 불변식 7**)

| 기존 표현 | 새 표현 |
|---|---|
| `Use AskUserQuestion to …` / `AskUserQuestion 으로 …` | `Ask the user (structured choice) …` |
| `AskUserQuestion` (multiSelect 언급) | `Ask the user (multi-select) …` |
| `invoke the X skill (via the Skill tool)` / `Skill: X` | `Invoke skill `X`` |
| `Agent` (`Task` alias) … `subagent_type: X` | `Dispatch subagent `X`` |
| `general-purpose` agent 파견 | `Dispatch subagent (general)` |
| TeamCreate / SendMessage / TaskCreate 팀 운용 | `Dispatch subagent …` 병렬 파견 + "on Claude Code with agent teams enabled, a team may run them instead" 한 줄 |
| TodoWrite / TaskCreate(진행 추적) | `Track steps` |

`rules/risk-tiers.md` 는 `## Principle` 절을 건드리지 않음(eval 위치 민감 — CLAUDE.md). 도구명이 그 절에만 있으면
이 테스트의 SCOPE 에서 `rules/risk-tiers.md` 의 해당 절만 예외로 두고 사유 주석.

- [ ] **Step 4: `openai.yaml` 11개 작성** — 각 `skills/<name>/agents/openai.yaml`:

```yaml
policy:
  allow_implicit_invocation: false
```

- [ ] **Step 5: 통과 + skill 계약 전체**

Run: `uv run pytest -q tests/skills tests/docs` → PASS (불변식 7 pin 포함).
Run: `python3 scripts/doc_style_check.py --lint $(git diff --name-only -- '*.md')` → error 0.
Run: `python3 scripts/doc_style_check.py --verify-git <변경된 .md …>` → 헤딩·코드블록·URL·인라인 코드 보존 확인
(치환된 도구명 인라인 코드 소실은 의도 — 목록 확인 후 예외 판단).

- [ ] **Step 6: Mutation** — 임의 SKILL.md 에 `AskUserQuestion` 한 단어를 Python 으로 삽입 → 첫 테스트 FAIL 확인, 복원.

---

### Task 12: 소비자 문서 + CLAUDE.md

**Files:**
- Create: `docs/usage/codex.md`, `docs/usage/codex.ko.md`
- Modify: `USAGE.md`, `USAGE.ko.md`, `README.md`, `README.ko.md`(존재 시), `docs/usage/update-and-removal*.md`, `docs/usage/troubleshooting*.md`, `CLAUDE.md`

- [ ] **Step 1: `docs/usage/codex.md`** (영어, "what a consumer does, and what breaks without it"):
  설치(`codex plugin marketplace add foryouself83/harness-tier` → `/plugins` 설치) · 프로젝트 trust · `/hooks` 승인
  (승인 전 규칙·gate 조용히 비활성, 플러그인 업데이트로 hook 정의가 바뀌면 재승인) · `/flow-init` 에서 Codex 선택 →
  `.codex/hooks.json` · Windows 는 Git for Windows 필요(없으면 commit/merge 차단) · Codex 에서 다른 점(질문은 번호 선택지,
  `$flow` 호출, Teams 알림 미지원, `request_user_input` 은 Plan 모드) · 제거(`/flow-uninstall` 이 `.codex/hooks.json` 정리).
  `.ko.md` 쌍 동일 내용.
- [ ] **Step 2: 색인·README** — USAGE 색인에 Codex 행, README 설치 절에 Codex 한 단락(+ 링크).
- [ ] **Step 3: CLAUDE.md** — Folder structure 의 `scripts/` 행에 "`harness/<name>/` per-harness installers" 추가, `hooks/` 행에
  "`codex/` Codex registration", `.codex-plugin/` · `.agents/` 한 줄. Architecture 에 한 항목: "Codex support: hooks and the gate
  are registered per harness from `scripts/harness/`; differences and their evidence live in
  `docs/superpowers/reference/claude-code-vs-codex.md`." (150줄 이하 유지.)
- [ ] **Step 4: 검증** — `uv run pytest -q tests/docs` (usage 문서 parity) → PASS, doc-style lint → error 0.

---

### Task 13: Codex acceptance (실측, 사용자 승인 필요)

- [ ] **Step 1: 비용 보고·승인** — "`gpt-6-luna` `codex exec` 2회" 보고.
- [ ] **Step 2: 임시 호스트 준비** — scratchpad 에 `git init` 한 repo, `python3 <repo>/scripts/flow_init_setup.py` 를
  `CLAUDE_PROJECT_DIR=<tmp> CLAUDE_PLUGIN_ROOT=<repo>` 로 실행하기 전에 `flow-config.yaml` 에 `harnesses: [claude, codex]`.
  `.codex/hooks.json` 생성 확인.
- [ ] **Step 3: 차단 실측** — `codex exec --json -m gpt-6-luna --sandbox workspace-write --dangerously-bypass-hook-trust -c "projects.'<tmp 소문자>'.trust_level=\"trusted\""`
  지시문: "Create file a.txt with hi, then run: git add a.txt && git commit -m test. Report whether the commit was blocked and the reason."
  Expected: commit 차단(미분류 커밋 — 예외 2), 사유가 응답에 포함. `git log` 에 test 커밋 없음.
- [ ] **Step 4: 규칙 주입 실측(플러그인 hook)** — 사용자 승인 시에만: `codex plugin marketplace add <repo 경로>` → 설치 →
  새 세션에서 "What must you do before starting a code change in this project?" → `$flow` 언급 확인. 승인 없으면 Step 3 의
  프로젝트 hook 으로 `hooks/codex/hooks.json` 의 SessionStart 항목을 복사(`${PLUGIN_ROOT}` 를 repo 절대경로로 치환)해 대체 실측.
- [ ] **Step 5: 기록** — transcript(JSONL)를 `docs/superpowers/reference/codex-acceptance-2026-09-27.jsonl` 로 보관하지 않고
  요약만 reference §8 뒤 "acceptance" 절에 조건·결과로 기록(JSONL 은 scratchpad).

---

### Task 14: Sonnet eval 재측정 (사용자 승인 필요)

- [ ] **Step 1:** `uv run python -m evals.run --dry-run --all` → 세션 수·예상 시간 보고(하락 시 재측정 2배 포함).
- [ ] **Step 2: 승인 후** `uv run python -m evals.run` (description/본문 변경 skill) 과 `uv run python -m evals.outcome`.
- [ ] **Step 3:** 하락 skill 은 CLAUDE.md 규칙대로 재측정 확인 → 원인이 어휘 치환이면 해당 skill 문구 조정 후 그 skill 만 재측정.
  `evals/scores.json`·`outcome_scores.json` 변경은 같은 브랜치 커밋에 포함(`test:`/`chore:` 가 아니라 단일 커밋에 합류).

---

### Task 15: 게이트와 단일 커밋

- [ ] **Step 1:** `Invoke skill doc-sync` → PASS 시 `.claude/harness-tier/.flow/doc-sync.done` (이 repo 는 vway-kit 설치 —
  marker 위치는 `/vdev` 지시 `.claude/vway-kit/.vdev/doc-sync.done`).
- [ ] **Step 2:** 독립 review agent — 변경 파일 전수, `VERDICT: PASS|FAIL` 리터럴 요구, "git switch/checkout/stash 금지" 명시.
  PASS → `review.done`.
- [ ] **Step 3:** `Skill: commit` — 단일 `feat:` 커밋(소비자 대상 skill·rule 변경 포함), 본문은 risk-tiers Commit Discipline.
- [ ] **Step 4:** merge strategy(`feature/*` → dev: rebase → 통합 검증 → squash)는 사용자 확인 후.
### Task 16: Instruction IR + Codex AGENTS.md renderer (user-approved, inserted before Task 12)

Why: skills write project instructions for Claude Code (root CLAUDE.md managed blocks such as the /flow-init Teams block, /harness-init's CLAUDE.md + `.claude/rules/*.md` with `paths:` frontmatter, doc-sync's per-module `services/*/CLAUDE.md`). Codex reads none of these: it loads only `AGENTS.override.md` → `AGENTS.md` → configured fallbacks, one file per directory, only for cwd and its ANCESTORS (never subdirectories), combined budget 32 KiB (`project_doc_max_bytes`), truncated silently, no `@import`, never `.claude/rules/`. Sessions normally start at the repo root, so for Codex only the ROOT `AGENTS.md` reliably loads.

User decision: the Claude artifacts ARE the IR source (hand-edited, host-owned — no new source format, no migration). A parser reads them into a neutral model; a Codex renderer writes one managed block into the host's root `AGENTS.md`. Claude artifacts are never modified. Claude-only hosts: nothing happens.

**Files:**
- Create: `scripts/harness/instructions.py` — IR model + Claude-artifact parser (harness-neutral)
- Create: `scripts/harness/codex/instructions.py` — Codex renderer + CLI (`render`, `render --check`, `remove`)
- Modify: `scripts/flow_init_setup.py` — `HARNESS_COPY_FILES["codex"]` gains both modules (host copy, path-preserving); setup step `[Codex 지침 렌더]` when codex enabled; uninstall removes the block (always, like the Codex gate step)
- Modify: `skills/doc-sync/SKILL.md` — when the host's flow-config `harnesses` includes `codex`, after updating any CLAUDE.md / `.claude/rules` run the renderer (`python3 .claude/harness-tier/scripts/harness/codex/instructions.py render`) and treat a non-zero `--check` as a doc-sync finding. Minimal, vocabulary-compliant wording.
- Modify: `skills/harness-init/SKILL.md` — after writing CLAUDE.md / rules, same conditional render step.
- Modify: `rules/harness-tools/codex.md` — one bullet: the harness-tier block in AGENTS.md is generated from CLAUDE.md and `.claude/rules/`; edit those, never the block; and (already there or add) read a directory's CLAUDE.md before working under it.
- Test: `tests/harness/test_instructions_ir.py`, `tests/harness/codex/test_instructions_render.py`

**IR (scripts/harness/instructions.py):**

```python
@dataclass(frozen=True)
class InstructionDoc:
    kind: str            # "root" | "rule" | "module"
    source: str          # repo-relative POSIX path of the Claude artifact
    scope_dir: str       # "" for repo root, else repo-relative dir ("services/api")
    paths: tuple[str, ...]  # rule `paths:` globs; () = always applies
    body: str            # text after frontmatter, @imports expanded (LF-normalized)

def collect(host: Path) -> list[InstructionDoc]
```

- root: `<host>/CLAUDE.md` if present (whole body).
- rule: every `<host>/.claude/rules/**/*.md` (frontmatter `paths:` list or string; absent = always). Skip files under `.claude/harness-tier/`.
- module: every other `CLAUDE.md` below the root (skip `.git`, `node_modules`, `.venv`, `.claude/`, and anything git ignores if cheaply knowable — use `git check-ignore --stdin` when git is available, else a fixed skip list).
- `@import` expansion: a line consisting of `@<relative path>` (Claude memory import syntax, path relative to the importing file, `~` excluded) is replaced by the imported file's body; max depth 5; a missing or cyclic import leaves the line as-is. Imports outside the host root are left as-is.
- Deterministic ordering: root, then rules sorted by path, then modules sorted by path.
- All reads `encoding="utf-8"`, CRLF → LF (Invariant 2; CLAUDE.md "normalize CRLF").

**Codex render (scripts/harness/codex/instructions.py):**
- Target: `<host>/AGENTS.md`, managed block between
  `<!-- harness-tier:codex-instructions BEGIN — generated from CLAUDE.md and .claude/rules; edit those, then re-run the renderer -->`
  and `<!-- harness-tier:codex-instructions END -->`. Text outside the block is preserved byte-for-byte. Block placed at end of file on first render; replaced in place afterwards. File created if absent (containing only the block).
- Block content, in order:
  1. root body (if any).
  2. each rule: heading `### Rule: <source>` + line `Applies to: <globs joined by ", ">` (or `Applies to: all files`) + body.
  3. module index: heading `### Directory instructions` + one line per module: ``Before working under `<scope_dir>/`, read `<source>`.``
- Budget: `project_doc_max_bytes` default 32768 bytes for the whole AGENTS.md (text outside block + block). If over: re-render with rules as index lines (``Before editing files matching `<globs>`, read `<source>`.``) instead of bodies; if still over, render anyway and return a warning line naming the size (never silently exceed).
- Idempotent: rendering twice yields identical bytes; `render` reports `[=]` when unchanged, `[+]` when written.
- `--check`: exit 1 with a one-line reason when the file's block differs from a fresh render (drift), 0 otherwise; writes nothing.
- `remove`: delete the block; delete the file if nothing else remains (whitespace only).
- No root CLAUDE.md and no rules and no modules → nothing to render: remove an existing block, create nothing.
- Claude Code reads AGENTS.md natively only when no root CLAUDE.md exists; in that case the rendered rules duplicate `.claude/rules` for Claude — accepted, note it in the module docstring (one line).
- CLI via `if __name__ == "__main__":` with sys.path set up there only (no import-time sys.path mutation — a prior regression); `force_utf8_io()`.

**flow_init_setup:**
- `HARNESS_COPY_FILES["codex"]` += `scripts/harness/__init__.py`, `scripts/harness/instructions.py`, `scripts/harness/codex/__init__.py`, `scripts/harness/codex/instructions.py` (whatever the renderer imports must travel with it; keep gate wrappers).
- run_setup with codex: step `[Codex 지침 렌더]` → call the renderer's `render(host)` in-process (plugin-side import), print its lines.
- run_uninstall: step `[Codex 지침 블록 제거]` → `remove(host)` always (FAIL-OPEN per step, like `[Codex 게이트 해제]`).

**Tests (TDD):** IR parser (frontmatter paths list/string/absent, @import expansion incl. depth cap/cycle/missing, CRLF source, ordering, skip dirs); render (new file, preserve outside text incl. CRLF host file, idempotent bytes, in-place replace, budget degrade + warning, --check drift exit codes, remove incl. file deletion, nothing-to-render removes block); flow_init wiring (Claude-only host: no AGENTS.md created or touched; codex host: AGENTS.md block present after setup; uninstall removes it, leaves user text); skill lint (tests/skills green; the new doc-sync/harness-init steps use vocabulary, no tool names). Mutation: disable budget degrade; drop outside-text preservation — each caught; restore bytes from memory.
