# eval outcome arm Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** eval 하네스에 invocation과 분리된 outcome arm을 편입한다 — 스킬이 golden fixture에서 실제 실행되어 올바른 end-state를 만들었는지를 결정적으로 채점한다(v1: doc-sync).

**Architecture:** 두 arm 완전 분리. 신규 `evals/outcome.py`가 공유 프리미티브(`run._claude_stream`·`isolated_config_dir`, `sandbox.build`, `stream.observe`)를 재사용해 `bypassPermissions`+`--add-dir`+`--max-turns 25`로 doc-sync를 `doc-sync-drift` fixture에서 실행하고, golden END-STATE assertion으로 채점한다. 베이스라인은 별도 `evals/outcome_scores.json`, freshness 지문은 `outcome_sha`(SKILL.md 본문+fixture+golden).

**Tech Stack:** Python 3, `uv`, pytest, stdlib(`hashlib`/`json`/`tempfile`/`subprocess`). 모델 세션은 `claude -p --output-format stream-json`.

**Spec:** [docs/superpowers/specs/2026-07-24-eval-outcome-arm-design.md](../specs/2026-07-24-eval-outcome-arm-design.md)

## Global Constraints

- scored invocation arm — `run.measure`/`_one`/`cases_for`, `stream.py`의 현 `Observation`, `scores.json`, `scores.py`의 invocation 게이트, `test_evals.py`의 현 게이트 — **동작 무변경**.
- `_claude_stream` 확장은 기본값이 현 커맨드를 **바이트 동일** 재현(유일 호출자 `run_session` 무영향).
- outcome은 **별도 arm**: 별도 모듈 `evals/outcome.py`, 별도 베이스라인 `evals/outcome_scores.json`, **신규 테스트만**.
- `bypassPermissions`는 던져버릴 `TemporaryDirectory` fixture 안에서만 작동.
- 커밋 타입은 **`test:`/`chore:`**(evals는 소비자 미배포).
- Windows/인코딩: 파일 쓰기 `encoding="utf-8"`; 콘솔 메시지 cp949 안전(em-dash 금지); `_claude_stream`의 taskkill 트리-kill 상속.
- 모든 신규 테스트 model-free; 기존 `no_real_sessions` autouse(=`run.subprocess` 패치)가 `run._claude_stream` 경유로 라이브 경로를 계속 차단.
- `evals/`는 어떤 manifest에도 명시 금지(`test_the_eval_harness_is_never_distributed_to_consumers`가 강제).
- 핀 모델 = `scores.MODEL`(`claude-opus-4-8`); outcome 엔트리는 이를 스탬프.

## File Structure

- `scripts/skill_sandbox.py` — Modify: `Scenario`에 `outcome` 필드, `doc-sync-drift`에 golden, `check_outcome` 추가.
- `evals/run.py` — Modify: `_claude_stream`에 키워드 전용 파라미터(`permission_mode`/`add_dirs`/`max_turns`/`timeout`).
- `evals/outcome.py` — Create: outcome arm(순수 게이트 `outcome_sha`/`outcome_check` + 러너 `run_outcome` + CLI).
- `evals/outcome_scores.json` — Create(라이브 시딩): 커밋 베이스라인.
- `tests/test_evals.py` — Modify: 신규 테스트만.
- `CLAUDE.md` — Modify: Commands + eval 아키텍처 불릿(doc-sync 게이트 대상).

---

### Task 1: `Scenario.outcome` + `check_outcome` (golden과 채점기 병치)

**Files:**
- Modify: `scripts/skill_sandbox.py` (Scenario dataclass ~52-61, doc-sync-drift ~354-378, build 근처)
- Test: `tests/test_evals.py`

**Interfaces:**
- Produces: `sandbox.Scenario.outcome: dict[str, dict[str, list[str]]]`; `sandbox.check_outcome(scenario, built: Path) -> tuple[bool, list[str]]`.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_evals.py` 하단에 추가:

```python
def test_doc_sync_drift_declares_a_machine_checkable_outcome():
    s = sandbox.BY_NAME["doc-sync-drift"]
    assert s.outcome, "doc-sync-drift must declare a golden end-state"
    assert set(s.outcome) == {"README.md", "docs/api.md", "app/server.py"}


def test_check_outcome_passes_the_golden_end_state(tmp_path):
    s = sandbox.BY_NAME["doc-sync-drift"]
    built = sandbox.build(s, tmp_path)
    (built / "README.md").write_text(
        "# Sandbox\n\nThe server listens on port 9090.\n", encoding="utf-8"
    )
    (built / "docs/api.md").write_text(
        "# API\n\nBase URL: `http://localhost:9090`\n", encoding="utf-8"
    )
    passed, failures = sandbox.check_outcome(s, built)
    assert passed, failures


def test_check_outcome_fails_on_the_original_drift(tmp_path):
    s = sandbox.BY_NAME["doc-sync-drift"]
    built = sandbox.build(s, tmp_path)  # ships 8080 / 3000 — unsynced drift
    passed, failures = sandbox.check_outcome(s, built)
    assert not passed
    assert any("8080" in f for f in failures)


def test_check_outcome_treats_a_missing_file_as_failure(tmp_path):
    s = sandbox.BY_NAME["doc-sync-drift"]
    built = sandbox.build(s, tmp_path)
    (built / "README.md").unlink()
    passed, failures = sandbox.check_outcome(s, built)
    assert not passed
    assert any("README.md: missing" in f for f in failures)
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_evals.py -k "outcome or drift" -v`
Expected: FAIL (`AttributeError: 'Scenario' object has no attribute 'outcome'` 또는 `check_outcome` 미정의)

- [ ] **Step 3: `Scenario`에 필드 추가** — `scripts/skill_sandbox.py`의 dataclass에 마지막 필드로:

```python
@dataclass
class Scenario:
    name: str
    skill: str
    why: str
    prompt: str
    expect: list[str]
    reject: list[str]
    files: dict[str, str] = field(default_factory=dict)
    dirs: list[str] = field(default_factory=list)
    # Machine-checkable golden end-state for the outcome arm (evals/outcome.py). Prose
    # expect/reject above stay for the human-judged invocation sandbox; this is asserted.
    # { "<relpath>": {"must_contain": [...], "must_not_contain": [...]} }
    outcome: dict[str, dict[str, list[str]]] = field(default_factory=dict)
```

- [ ] **Step 4: `doc-sync-drift`에 golden 채우기** — 해당 `Scenario(...)` 호출의 `files={...}` 뒤에 추가:

```python
        outcome={
            "README.md": {"must_contain": ["9090"], "must_not_contain": ["8080"]},
            "docs/api.md": {"must_contain": ["9090"], "must_not_contain": ["3000"]},
            # server.py must keep 9090: the scenario's reject forbids rewriting code to the docs.
            "app/server.py": {"must_contain": ["9090"]},
        },
```

- [ ] **Step 5: `check_outcome` 추가** — `build()` 함수 바로 뒤에:

```python
def check_outcome(scenario: Scenario, built: Path) -> tuple[bool, list[str]]:
    """Assert a built fixture reached the scenario's golden end-state.

    Deterministic substring checks per file — the SWE-bench-style score for the outcome
    arm. A missing file is a failure, not a crash: an agent that deleted or renamed the doc
    it was asked to sync did not reach the end-state either."""
    failures: list[str] = []
    for rel, spec in scenario.outcome.items():
        path = built / rel
        if not path.exists():
            failures.append(f"{rel}: missing")
            continue
        text = path.read_text(encoding="utf-8")
        for needle in spec.get("must_contain", []):
            if needle not in text:
                failures.append(f"{rel}: missing {needle!r}")
        for needle in spec.get("must_not_contain", []):
            if needle in text:
                failures.append(f"{rel}: still contains {needle!r}")
    return not failures, failures
```

- [ ] **Step 6: 통과 확인**

Run: `uv run pytest tests/test_evals.py -k "outcome or drift" -v`
Expected: PASS (4 passed)

- [ ] **Step 7: 기존 스위트 무손상 확인**

Run: `uv run pytest tests/ -q`
Expected: 전부 PASS (신규 4 포함, 기존 회귀 없음)

- [ ] **Step 8: 커밋**

```bash
git add scripts/skill_sandbox.py tests/test_evals.py
git commit -m "test(evals): golden end-state field + check_outcome"
```

---

### Task 2: `_claude_stream` 키워드 파라미터화 (scored 경로 무변경)

**Files:**
- Modify: `evals/run.py:353-417` (`_claude_stream` 시그니처·cmd·communicate)
- Test: `tests/test_evals.py`

**Interfaces:**
- Consumes: 없음(내부 확장).
- Produces: `run._claude_stream(prompt, fixture, workdir, config_dir, restricted=False, *, permission_mode=None, add_dirs=(), max_turns=MAX_TURNS, timeout=SESSION_TIMEOUT) -> tuple[str, str]`.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_evals.py`에 추가:

```python
class _CapturingSubprocess:
    """Records the argv and communicate timeout without spawning claude. Overrides the
    autouse no_real_sessions guard within a test that needs to inspect the command."""

    DEVNULL = subprocess.DEVNULL
    PIPE = subprocess.PIPE
    TimeoutExpired = subprocess.TimeoutExpired

    def __init__(self):
        self.captured = {}

    def Popen(self, cmd, **kwargs):
        self.captured["cmd"] = cmd
        cap = self.captured

        class _Proc:
            def communicate(self, timeout=None):
                cap["timeout"] = timeout
                return (b"", b"")

        return _Proc()


def test_claude_stream_defaults_reproduce_the_scored_command(monkeypatch):
    fake = _CapturingSubprocess()
    monkeypatch.setattr(run, "subprocess", fake)
    run._claude_stream("p", None, Path("."), Path("cfg"))
    cmd = fake.captured["cmd"]
    assert cmd[cmd.index("--max-turns") + 1] == str(run.MAX_TURNS)
    assert "--permission-mode" not in cmd
    assert "--add-dir" not in cmd
    assert fake.captured["timeout"] == run.SESSION_TIMEOUT


def test_claude_stream_threads_the_outcome_flags(monkeypatch):
    fake = _CapturingSubprocess()
    monkeypatch.setattr(run, "subprocess", fake)
    run._claude_stream(
        "p", None, Path("."), Path("cfg"),
        permission_mode="bypassPermissions", add_dirs=(run.REPO,), max_turns=25, timeout=300,
    )
    cmd = fake.captured["cmd"]
    assert cmd[cmd.index("--permission-mode") + 1] == "bypassPermissions"
    assert cmd[cmd.index("--add-dir") + 1] == str(run.REPO)
    assert cmd[cmd.index("--max-turns") + 1] == "25"
    assert fake.captured["timeout"] == 300
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_evals.py -k claude_stream -v`
Expected: FAIL (`test_claude_stream_threads_the_outcome_flags`가 `TypeError: unexpected keyword argument 'permission_mode'`)

- [ ] **Step 3: 시그니처 확장** — `evals/run.py`의 `_claude_stream` 정의를 교체:

```python
def _claude_stream(
    prompt: str,
    fixture: str | None,
    workdir: Path,
    config_dir: Path,
    restricted: bool = False,
    *,
    permission_mode: str | None = None,
    add_dirs: tuple[Path, ...] = (),
    max_turns: int = MAX_TURNS,
    timeout: int = SESSION_TIMEOUT,
) -> tuple[str, str]:
```

- [ ] **Step 4: cmd 구성 확장** — `--max-turns` 값을 `str(max_turns)`로, `restricted` 블록 뒤에 새 플래그 추가:

```python
    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--max-turns",
        str(max_turns),
        "--model",
        scores.MODEL,
        "--plugin-dir",
        str(REPO),
    ]
    if restricted:
        cmd += ["--allowedTools", "Skill"]
    # Outcome arm only: defaults leave the scored command byte-identical.
    if permission_mode:
        cmd += ["--permission-mode", permission_mode]
    for d in add_dirs:
        cmd += ["--add-dir", str(d)]
```

- [ ] **Step 5: timeout 파라미터화** — `proc.communicate(timeout=SESSION_TIMEOUT)`를 `proc.communicate(timeout=timeout)`로 교체(TimeoutExpired 핸들러 내부 로직은 불변):

```python
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
```

- [ ] **Step 6: 통과 확인**

Run: `uv run pytest tests/test_evals.py -k claude_stream -v`
Expected: PASS (2 passed)

- [ ] **Step 7: scored 경로 회귀 없음 확인**

Run: `uv run pytest tests/ -q`
Expected: 전부 PASS (`run_session`/`measure` 테스트 그린 유지)

- [ ] **Step 8: 커밋**

```bash
git add evals/run.py tests/test_evals.py
git commit -m "test(evals): parameterize _claude_stream for the outcome recipe"
```

---

### Task 3: outcome 순수 게이트 — `outcome_sha` + `outcome_check`

**Files:**
- Create: `evals/outcome.py` (순수 함수만)
- Test: `tests/test_evals.py`

**Interfaces:**
- Consumes: `sandbox.Scenario`(Task 1의 `outcome` 필드), `scores.Verdict`/`scores.MODEL`.
- Produces: `outcome.REPO`; `outcome.OUTCOME_SCORES`; `outcome.outcome_sha(skill: str, scenario) -> str`; `outcome.outcome_check(skill: str, entry: dict | None, sha: str) -> scores.Verdict`.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_evals.py`에 추가(상단 import 근처에 `import evals.outcome as outcome`와 `from dataclasses import replace` 추가):

```python
def test_outcome_sha_is_sensitive_to_body_fixture_and_golden():
    s = sandbox.BY_NAME["doc-sync-drift"]
    base = outcome.outcome_sha("doc-sync", s)
    # stable when nothing changes
    assert outcome.outcome_sha("doc-sync", s) == base
    # golden change
    moved_golden = replace(s, outcome={**s.outcome, "README.md": {"must_contain": ["7070"]}})
    assert outcome.outcome_sha("doc-sync", moved_golden) != base
    # fixture change
    moved_files = replace(s, files={**s.files, "README.md": "port 1234\n"})
    assert outcome.outcome_sha("doc-sync", moved_files) != base
    # body change — a different skill's SKILL.md is a different body
    assert outcome.outcome_sha("integration", s) != base


def test_outcome_check_warns_when_unmeasured():
    assert outcome.outcome_check("doc-sync", None, "abc").level == "warn"


def test_outcome_check_fails_on_a_stale_fingerprint():
    entry = {"outcome_hits": 3, "outcome_n": 3, "outcome_sha": "old", "model": scores.MODEL}
    v = outcome.outcome_check("doc-sync", entry, "new")
    assert v.level == "fail"
    assert "re-measure" in v.message


def test_outcome_check_fails_on_a_model_mismatch():
    entry = {"outcome_hits": 3, "outcome_n": 3, "outcome_sha": "s", "model": "claude-sonnet-5"}
    assert outcome.outcome_check("doc-sync", entry, "s").level == "fail"


def test_outcome_check_fails_an_all_zero_baseline():
    entry = {"outcome_hits": 0, "outcome_n": 3, "outcome_sha": "s", "model": scores.MODEL}
    assert outcome.outcome_check("doc-sync", entry, "s").level == "fail"


def test_outcome_check_passes_a_fresh_nonzero_entry():
    entry = {"outcome_hits": 3, "outcome_n": 3, "outcome_sha": "s", "model": scores.MODEL}
    assert outcome.outcome_check("doc-sync", entry, "s").level == "ok"
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_evals.py -k "outcome_sha or outcome_check" -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'evals.outcome'`)

- [ ] **Step 3: `evals/outcome.py` 생성(순수 함수)**:

```python
"""The outcome arm: does a skill, once it fires, actually reach the right end-state?

Separate from run.py's invocation arm by design. The invocation arm asks whether a
description makes the skill fire; this asks whether the skill's *body*, executed for real,
produces the golden end-state — a different question, with a different freshness signal
(body + fixture + golden, not the description) and a different recipe (bypassPermissions +
--add-dir, so the session can actually edit files).

The pure half here (outcome_sha, outcome_check) is model-free like scores.py. run_outcome
and the CLI spend real sessions and are guarded by the suite's no_real_sessions fixture
through run._claude_stream.
"""

import hashlib
import json
from pathlib import Path

import evals.scores as scores
import scripts.skill_sandbox as sandbox

REPO = Path(__file__).resolve().parent.parent
OUTCOME_SCORES = REPO / "evals/outcome_scores.json"


def outcome_sha(skill: str, scenario: sandbox.Scenario) -> str:
    """Freshness fingerprint for the outcome baseline.

    Covers everything the outcome claim depends on: the skill body that executes, the
    fixture it runs against, and the golden it is scored by. description_sha covers none of
    these — it hashes the description only, because invocation is decided by the description
    while outcome is decided by the body."""
    body = (REPO / f"skills/{skill}/SKILL.md").read_text(encoding="utf-8")
    payload = (
        body
        + json.dumps(scenario.files, sort_keys=True)
        + json.dumps(scenario.outcome, sort_keys=True)
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def outcome_check(skill: str, entry: dict | None, sha: str) -> scores.Verdict:
    """Model-free gate for a committed outcome entry — freshness + a non-zero floor.

    Mirrors scores.check's shape without its ratchet: one skill at reps=3 has no family to
    ratchet against yet. It enforces that a committed baseline cannot be a stale or all-zero
    lie riding a green suite."""
    if entry is None:
        return scores.Verdict(
            "warn", f"{skill}: outcome not measured yet — run python -m evals.outcome"
        )
    missing = [k for k in ("outcome_hits", "outcome_n", "outcome_sha", "model") if k not in entry]
    if missing:
        return scores.Verdict("fail", f"{skill}: outcome entry is missing {missing} — re-measure")
    if entry["outcome_sha"] != sha:
        return scores.Verdict(
            "fail",
            f"{skill}: skill body, fixture or golden changed since the outcome score — re-measure",
        )
    if entry["model"] != scores.MODEL:
        return scores.Verdict(
            "fail",
            f"{skill}: outcome measured on model {entry['model']!r}, gate pinned to "
            f"{scores.MODEL!r} — re-measure",
        )
    if entry["outcome_hits"] == 0:
        return scores.Verdict(
            "fail", f"{skill}: outcome_pass_rate is 0 — never reached the end-state, re-measure"
        )
    return scores.Verdict("ok", f"{skill}: outcome ok")
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_evals.py -k "outcome_sha or outcome_check" -v`
Expected: PASS (6 passed)

- [ ] **Step 5: 커밋**

```bash
git add evals/outcome.py tests/test_evals.py
git commit -m "test(evals): outcome_sha fingerprint + freshness gate"
```

---

### Task 4: outcome 러너 + CLI — `run_outcome` + `main`

**Files:**
- Modify: `evals/outcome.py` (러너·CLI 추가)
- Test: `tests/test_evals.py`

**Interfaces:**
- Consumes: `run._claude_stream`(Task 2), `run.isolated_config_dir`/`run.RateLimited`/`run._tail`/`run.SECONDS_PER_SESSION`, `sandbox.build`/`sandbox.check_outcome`(Task 1), `stream.observe`, `outcome_sha`(Task 3).
- Produces: `outcome._outcome_targets() -> list[tuple[str, Scenario]]`; `outcome.run_outcome(skill, scenario, reps, config_dir) -> dict`; `outcome.main() -> int`; 상수 `OUTCOME_MAX_TURNS=25`/`OUTCOME_TIMEOUT=300`/`REPS=3`.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_evals.py`에 추가:

```python
def _fake_doc_sync_session(writes_9090: bool, fires: bool):
    """Stands in for run._claude_stream: edits the built fixture like a doc-sync run would,
    then returns a stream carrying an init event (so obs.available is populated) and,
    optionally, a doc-sync Skill firing (for the fired diagnostic)."""

    def fake(prompt, fixture, workdir, config_dir, **kw):
        port = "9090" if writes_9090 else "8080"
        (workdir / "README.md").write_text(f"port {port}\n", encoding="utf-8")
        (workdir / "docs/api.md").write_text(f"http://localhost:{port}\n", encoding="utf-8")
        # app/server.py already ships 9090 from sandbox.build()
        events = [json.dumps({"subtype": "init", "skills": ["harness-tier:doc-sync"]})]
        if fires:
            events.append(
                json.dumps(
                    {
                        "type": "assistant",
                        "message": {
                            "content": [
                                {
                                    "type": "tool_use",
                                    "name": "Skill",
                                    "input": {"skill": "harness-tier:doc-sync"},
                                }
                            ]
                        },
                    }
                )
            )
        events.append(json.dumps({"type": "result", "subtype": "success", "is_error": False}))
        return "\n".join(events), ""

    return fake


def test_run_outcome_scores_the_end_state_and_records_fired(monkeypatch):
    monkeypatch.setattr(run, "_claude_stream", _fake_doc_sync_session(writes_9090=True, fires=True))
    s = sandbox.BY_NAME["doc-sync-drift"]
    result = outcome.run_outcome("doc-sync", s, reps=2, config_dir=Path("."))
    assert result["outcome_hits"] == 2
    assert result["outcome_pass_rate"] == 1.0
    assert result["fired_rate"] == 1.0
    assert result["model"] == scores.MODEL
    assert result["outcome_sha"] == outcome.outcome_sha("doc-sync", s)


def test_run_outcome_records_a_miss_when_the_end_state_is_wrong(monkeypatch):
    monkeypatch.setattr(run, "_claude_stream", _fake_doc_sync_session(writes_9090=False, fires=True))
    s = sandbox.BY_NAME["doc-sync-drift"]
    result = outcome.run_outcome("doc-sync", s, reps=2, config_dir=Path("."))
    assert result["outcome_hits"] == 0
    assert result["outcome_pass_rate"] == 0.0


def test_run_outcome_aborts_on_an_errored_session(monkeypatch):
    def fake(prompt, fixture, workdir, config_dir, **kw):
        events = [
            json.dumps({"subtype": "init", "skills": ["harness-tier:doc-sync"]}),
            json.dumps({"type": "result", "subtype": "error_during_execution", "is_error": True}),
        ]
        return "\n".join(events), "boom\n"

    monkeypatch.setattr(run, "_claude_stream", fake)
    s = sandbox.BY_NAME["doc-sync-drift"]
    with pytest.raises(SystemExit):
        outcome.run_outcome("doc-sync", s, reps=1, config_dir=Path("."))


def test_outcome_dry_run_spawns_no_session(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["evals.outcome", "--dry-run"])
    assert outcome.main() == 0
    assert "outcome sessions" in capsys.readouterr().out


def test_outcome_reps_zero_is_rejected(monkeypatch):
    monkeypatch.setattr(sys, "argv", ["evals.outcome", "--reps", "0", "--dry-run"])
    with pytest.raises(SystemExit) as e:
        outcome.main()
    assert e.value.code == 2
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_evals.py -k "run_outcome or outcome_dry_run or outcome_reps" -v`
Expected: FAIL (`AttributeError: module 'evals.outcome' has no attribute 'run_outcome'`)

- [ ] **Step 3: 러너·CLI 추가** — `evals/outcome.py`의 import에 `argparse`/`sys`/`tempfile`/`from datetime import date`, `import evals.run as run`, `import evals.stream as stream`를 더하고, 파일 끝에 추가:

```python
OUTCOME_MAX_TURNS = 25
# Higher than run.SESSION_TIMEOUT (180): outcome sessions actually edit files and may route
# flow -> doc-sync, so they run longer than an invocation probe.
OUTCOME_TIMEOUT = 300
REPS = 3


def _outcome_targets() -> list[tuple[str, sandbox.Scenario]]:
    """(skill, scenario) for every sandbox scenario that declares a golden end-state.

    Driven by Scenario.outcome, not cases.yaml — the invocation arm's data stays untouched.
    v1 has exactly one: doc-sync via doc-sync-drift."""
    return [(s.skill, s) for s in sandbox.SCENARIOS if s.outcome]


def run_outcome(skill: str, scenario: sandbox.Scenario, reps: int, config_dir: Path) -> dict:
    """Run one skill against its golden fixture `reps` times; score each by end-state.

    Each rep gets a throwaway fixture dir so bypassPermissions edits stay contained. Judged
    by the final end-state (chain-agnostic): whether doc-sync ran directly or via flow's
    routing, a synced doc set is the outcome. `fired` is recorded as a diagnostic only.

    Aborts rather than recording a fabricated 0 when a session errored or never loaded the
    plugin — the same discipline run.measure applies to the invocation arm."""
    hits = fired_hits = 0
    for _ in range(reps):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            built = sandbox.build(scenario, Path(tmp))
            text, err = run._claude_stream(
                scenario.prompt,
                None,
                built,
                config_dir,
                permission_mode="bypassPermissions",
                add_dirs=(run.REPO,),
                max_turns=OUTCOME_MAX_TURNS,
                timeout=OUTCOME_TIMEOUT,
            )
            obs = stream.observe(text)
            if obs.rate_limited:
                raise run.RateLimited(f"{skill}: rate limit reached mid-outcome-measurement")
            if obs.errored or not obs.available:
                raise SystemExit(
                    f"{skill}: outcome session failed outright or never loaded the plugin — "
                    f"refusing to record a 0 that is not about the end-state.{run._tail(err)}"
                )
            passed, _failures = sandbox.check_outcome(scenario, built)
            hits += passed
            fired_hits += skill in obs.fired
    return {
        "outcome_sha": outcome_sha(skill, scenario),
        "model": scores.MODEL,
        "measured_at": date.today().isoformat(),
        "reps": reps,
        "outcome_hits": hits,
        "outcome_n": reps,
        "outcome_pass_rate": round(hits / reps, 2),
        # Diagnostic, never gated: did the target skill fire in the (possibly flow-routed)
        # chain? Attribution visibility without gating the score on it.
        "fired_hits": fired_hits,
        "fired_rate": round(fired_hits / reps, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--reps", type=int, default=REPS)
    ap.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    args = ap.parse_args()
    if args.reps < 1:
        ap.error("--reps must be >= 1")

    targets = _outcome_targets()
    sessions = len(targets) * args.reps
    minutes = sessions * run.SECONDS_PER_SESSION / 60
    print(f"{len(targets)} skill(s), {sessions} outcome sessions, ~{minutes:.0f} min")
    if args.dry_run:
        return 0

    baseline: dict = {}
    if OUTCOME_SCORES.exists():
        baseline = json.loads(OUTCOME_SCORES.read_text(encoding="utf-8"))
    with run.isolated_config_dir() as config_dir:
        for skill, scenario in targets:
            print(f"measuring outcome: {skill}")
            try:
                result = run_outcome(skill, scenario, args.reps, config_dir)
            except run.RateLimited as e:
                print(f"\n{e}", file=sys.stderr)
                break
            print(f"  {result}")
            baseline[skill] = result
            # Persist after each skill: a rate-limit stop keeps what was measured.
            OUTCOME_SCORES.write_text(
                json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
    print(f"wrote {OUTCOME_SCORES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_evals.py -k "run_outcome or outcome_dry_run or outcome_reps" -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 전 스위트 + 라이브 차단 가드 확인**

Run: `uv run pytest tests/ -q`
Expected: 전부 PASS. (outcome 라이브 경로는 `no_real_sessions`가 `run._claude_stream` 경유로 차단 — 신규 테스트는 `_claude_stream`를 직접 패치하므로 세션 미소비.)

- [ ] **Step 6: 커밋**

```bash
git add evals/outcome.py tests/test_evals.py
git commit -m "test(evals): outcome runner + CLI (end-state scoring)"
```

---

### Task 5: 베이스라인 시딩(라이브) + 커밋-베이스라인 게이트 + 문서

**Files:**
- Create: `evals/outcome_scores.json` (라이브 실측)
- Modify: `tests/test_evals.py` (커밋-베이스라인 freshness 테스트)
- Modify: `CLAUDE.md` (Commands + eval 불릿)

**Interfaces:**
- Consumes: `outcome.main`(Task 4), `outcome.outcome_check`/`outcome_sha`(Task 3), `outcome.OUTCOME_SCORES`.
- Produces: `evals/outcome_scores.json`.

> **전제**: 이 태스크는 **라이브 세션**(자격증명 + rate-limit 예산)이 필요하다 — CI에서 못 돈다. 예산이 없으면 시딩을 미뤄도 스위트는 그린(게이트가 warn)이며, 예산 확보 시 이 태스크만 재개하면 된다.

- [ ] **Step 1: 커밋-베이스라인 게이트 테스트 작성(시딩 전에도 그린)** — `tests/test_evals.py`에 추가:

```python
def test_committed_outcome_baseline_is_never_stale_or_zero():
    """The outcome mirror of test_a_stale_measurement_fails: whatever is committed in
    outcome_scores.json must be fresh (ok) or absent (warn) — never a stale or all-zero lie
    that would let a broken outcome ride a green suite. After seeding it is ok; before
    seeding it is warn, keeping the suite green until the first live measure."""
    baseline: dict = {}
    if outcome.OUTCOME_SCORES.exists():
        baseline = json.loads(outcome.OUTCOME_SCORES.read_text(encoding="utf-8"))
    s = sandbox.BY_NAME["doc-sync-drift"]
    v = outcome.outcome_check(
        "doc-sync", baseline.get("doc-sync"), outcome.outcome_sha("doc-sync", s)
    )
    assert v.level in ("ok", "warn"), v.message
```

- [ ] **Step 2: 시딩 전 통과 확인(warn 경로)**

Run: `uv run pytest tests/test_evals.py -k committed_outcome -v`
Expected: PASS (파일 부재 → warn → assert 통과)

- [ ] **Step 3: 라이브 시딩 실행** — 실제 3세션 소비(≈3~6분):

Run: `uv run python -m evals.outcome --reps 3`
Expected(stdout 예):
```
1 skill(s), 3 outcome sessions, ~3 min
measuring outcome: doc-sync
  {'outcome_sha': '...', 'model': 'claude-opus-4-8', ..., 'outcome_hits': 3, 'outcome_n': 3, 'outcome_pass_rate': 1.0, 'fired_hits': 3, 'fired_rate': 1.0}
wrote .../evals/outcome_scores.json
```
`evals/outcome_scores.json`이 생성되고 `doc-sync.outcome_hits > 0`인지 확인.

- [ ] **Step 4: 시딩 후 게이트가 ok로 승격 확인**

Run: `uv run pytest tests/test_evals.py -k committed_outcome -v`
Expected: PASS (엔트리 존재 → outcome_check ok)

- [ ] **Step 5: `CLAUDE.md` Commands에 outcome 라인 추가** — evals.run 3줄 뒤:

찾기:
```
uv run python -m evals.run --skill integration --capture-fixtures   # …+ stream fixture candidates (*.jsonl.new)
```
바로 아래에 추가:
```
uv run python -m evals.outcome                           # measure the outcome arm (doc-sync end-state, reps 3)
```

- [ ] **Step 6: `CLAUDE.md` eval 불릿 확장** — "Skill invocation is measured, not assumed" 불릿의 끝(`mechanics in [`evals/`](evals/).`) 뒤에 문장 추가:

```
 A second **outcome arm** ([`evals/outcome.py`](evals/outcome.py)) checks a skill actually *executed* correctly — it runs the skill in a golden fixture under `bypassPermissions` and scores the end-state deterministically (SWE-bench style); its baseline is `evals/outcome_scores.json`, fingerprinted separately (`outcome_sha` = SKILL.md body + fixture + golden, since `description_sha` covers none of them).
```

- [ ] **Step 7: 전 스위트 + 린트 확인**

Run: `uv run pytest tests/ -q && uv run ruff check && uv run ruff format --check`
Expected: 전부 PASS

- [ ] **Step 8: 커밋**

```bash
git add evals/outcome_scores.json tests/test_evals.py CLAUDE.md
git commit -m "test(evals): seed doc-sync outcome baseline + gate + docs"
```

---

## Self-Review

**1. Spec coverage**
- 컴포넌트 1(Scenario.outcome + check_outcome) → Task 1 ✅
- 컴포넌트 2(_claude_stream 파라미터화) → Task 2 ✅
- 컴포넌트 3(outcome.py: sha/check/run_outcome/CLI) → Task 3·4 ✅
- 컴포넌트 4(outcome_scores.json 시딩) → Task 5 ✅
- 컴포넌트 5(신규 테스트) → 각 태스크에 TDD로 분산 ✅
- 판정 규칙(end-state 채점 + fired 진단) → Task 4 `run_outcome` ✅
- 게이트(freshness + 비영) → Task 3 `outcome_check` + Task 5 커밋-베이스라인 테스트 ✅
- 문서(Commands + 불릿) → Task 5 ✅
- 무손상 불변식 → Global Constraints + Task 2/4 회귀 스텝(Step 7/5) ✅

**2. Placeholder scan**: TBD/TODO 없음. 모든 코드 스텝에 완전한 코드·명령·기대 출력 존재.

**3. Type consistency**:
- `check_outcome(scenario, built) -> tuple[bool, list[str]]` — Task 1 정의, Task 4에서 `passed, _failures = sandbox.check_outcome(...)`로 일치 소비 ✅
- `_claude_stream(..., *, permission_mode, add_dirs, max_turns, timeout)` — Task 2 정의, Task 4에서 동일 키워드로 호출 ✅
- `outcome_sha(skill, scenario)`·`outcome_check(skill, entry, sha)` — Task 3 정의, Task 4·5에서 동일 시그니처 사용 ✅
- 엔트리 키(`outcome_hits`/`outcome_n`/`outcome_sha`/`model`/`outcome_pass_rate`/`fired_hits`/`fired_rate`/`reps`/`measured_at`) — `run_outcome` 산출과 `outcome_check` 소비가 일치 ✅
- 베이스라인 JSON 구조: `{skill: entry}` 최상위 키 — `main`의 `baseline[skill]=result`와 Task 5 테스트의 `baseline.get("doc-sync")`가 일치 ✅

## 실행 후 (/vdev Dev 오버레이 — 계획 태스크 외 거버넌스)

Task 1~5 완료 후, `/vdev` Dev dispatch에 따라 커밋/머지 전에: (a) 독립 `general-purpose` 도메인 리뷰 → `review.done`, (b) `doc-sync` 스킬 실행(문서 정합 재확인) → `doc-sync.done`. 그 후 `feature/eval-outcome-arm` → integration을 **rebase → squash**(risk-tiers Merge strategy)로 병합.
