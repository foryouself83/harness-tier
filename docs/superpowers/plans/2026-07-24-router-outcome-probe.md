# 라우터 outcome probe 구현 계획 (③-a)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** flow가 분류한 tier를 headless 세션에서 결정적으로 캡처할 수 있는지 실증하는 독립 probe를 만든다.

**Architecture:** `run.py`의 subprocess 실행부를 `_claude_stream` 헬퍼로 순수 추출해 원시 스트림 텍스트를 재사용 가능하게 하고, 신규 `evals/outcome_probe.py`가 flow의 golden 라벨 프롬프트를 실제 세션으로 돌려 두 방식(스트림 파싱 / 마커 파일)으로 tier를 복원해 golden과 대조·보고한다. 채점 경로(scored arm)·`scores.py`·`stream.py`·`test_evals.py`는 건드리지 않는다.

**Tech Stack:** Python 3, `uv`, pytest, PyYAML, 기존 `evals/` 모듈(`run`, `stream`, `sandbox`).

## Global Constraints

- 모든 `open()`/`read_text()`/`write_text()`는 `encoding="utf-8"` (Windows cp949 로케일).
- `scores.json` · `test_evals.py` · `stream.py` · `run.py`의 scored arm(`measure`/`_one`/`cases_for`) **무변경**.
- `run_session` 외부 동작(시그니처·반환 `(obs, err)`) **동일** — 순수 추출.
- 미배포 eval 계측 → 커밋은 `refactor:`/`test:`(버전 bump 없음).
- probe는 flow만 다룬다(golden 라벨 프롬프트 4개; `golden_tier` 없는 "Commit these changes"는 제외).
- 브랜치 `feature/eval-router-golden-tier` 유지(② golden 라벨 의존).

---

### Task 1: `run.py` — `_claude_stream` 헬퍼 추출 (순수 리팩터)

**Files:**
- Modify: `evals/run.py` (현 `run_session` 362-426)

**Interfaces:**
- Produces: `_claude_stream(prompt: str, fixture: str | None, workdir: Path, config_dir: Path, restricted: bool = False) -> tuple[str, str]` — `(stdout_text, stderr_text)`, 둘 다 utf-8 decode.
- `run_session(...) -> tuple[stream.Observation, str]` 시그니처·반환 불변.

- [ ] **Step 1: `_claude_stream` 추출**

`run_session` 본문에서 cmd 구성 · `subprocess.Popen` · timeout 트리-kill · decode 부분을 아래 함수로 이동한다(로직 그대로, `stream.observe`/`maybe_capture`/`return`만 남기지 않고 떼어냄):

```python
def _claude_stream(
    prompt: str, fixture: str | None, workdir: Path, config_dir: Path, restricted: bool = False
) -> tuple[str, str]:
    """Run one headless `claude -p` session; return (stdout_text, stderr_text), both utf-8.

    Extracted from run_session so a caller that needs the raw stream (outcome_probe) can
    reuse the subprocess + timeout-kill + decode logic without duplicating it. run_session
    keeps its (obs, err) contract by observing the returned text itself."""
    if fixture:
        workdir = sandbox.build(sandbox.BY_NAME[fixture], workdir)
    cmd = [
        "claude", "-p", prompt,
        "--output-format", "stream-json",
        "--verbose",
        "--max-turns", str(MAX_TURNS),
        "--model", scores.MODEL,
        "--plugin-dir", str(REPO),
    ]
    if restricted:
        cmd += ["--allowedTools", "Skill"]
    proc = subprocess.Popen(
        cmd, cwd=workdir, env=session_env(config_dir),
        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        start_new_session=os.name != "nt",
    )
    try:
        out, err = proc.communicate(timeout=SESSION_TIMEOUT)
    except subprocess.TimeoutExpired:
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True, check=False,
            )
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                proc.kill()
        out, err = proc.communicate()
    return out.decode("utf-8", errors="replace"), err.decode("utf-8", errors="replace")
```

- [ ] **Step 2: `run_session`을 헬퍼 호출로 축약**

```python
def run_session(
    prompt: str, fixture: str | None, workdir: Path, config_dir: Path, restricted: bool = False
) -> tuple[stream.Observation, str]:
    """Returns the observation plus the session's stderr. (docstring 유지)"""
    text, err = _claude_stream(prompt, fixture, workdir, config_dir, restricted)
    obs = stream.observe(text)
    maybe_capture(obs, text)
    return obs, err
```

- [ ] **Step 3: import·무손상 확인 (모델 없음)**

Run: `cd c:/Work/llm_ai/harness-tier && uv run python -c "from evals.run import _claude_stream, run_session; print('ok')"`
Expected: `ok`

Run: `uv run python -m evals.run --dry-run --all`
Expected: `7 skill(s), 245 sessions, 8 at a time, ~30 min` (실행 안 됨, dry-run)

- [ ] **Step 4: 기존 게이트 그린 확인**

Run: `uv run pytest tests/test_evals.py -q`
Expected: `... passed` (실패 0; 기존 flow warn 경고만)

- [ ] **Step 5: Commit**

```bash
git add evals/run.py
git commit -m "refactor(evals): extract _claude_stream from run_session"
```

---

### Task 2: `parse_stream_tier` — 스트림에서 분류 tier 파싱 (TDD)

**Files:**
- Create: `evals/outcome_probe.py`
- Test: `tests/test_outcome_probe.py`

**Interfaces:**
- Produces: `parse_stream_tier(text: str) -> str | None` — assistant 텍스트에서 `- Tier: X`의 X를 소문자로; 여러 개면 마지막; 없으면 None.

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_outcome_probe.py`:

```python
import json
from pathlib import Path

from evals.outcome_probe import parse_stream_tier


def _assistant(text: str) -> str:
    return json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}})


def test_parse_stream_tier_reads_last_classification():
    stream = "\n".join([
        _assistant("thinking..."),
        _assistant("## Tier Classification\n- Tier: DEV\n- Reason: touches .py"),
    ])
    assert parse_stream_tier(stream) == "dev"


def test_parse_stream_tier_picks_last_when_reclassified():
    stream = "\n".join([
        _assistant("- Tier: Docs"),
        _assistant("- Tier: Dev"),
    ])
    assert parse_stream_tier(stream) == "dev"


def test_parse_stream_tier_none_when_absent():
    assert parse_stream_tier(_assistant("no classification here")) is None
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_outcome_probe.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'evals.outcome_probe'`

- [ ] **Step 3: 최소 구현**

`evals/outcome_probe.py`:

```python
"""Probe: can flow's classified tier be captured deterministically from a headless
session, and does it match the golden_tier? Standalone — the scored path never imports it.
See docs/superpowers/specs/2026-07-24-router-outcome-probe-design.md."""

import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# The Phase-1 line /flow prints before any interactive gate (flow/SKILL.md, risk-tiers.md).
_TIER_RE = re.compile(r"(?im)^\s*-\s*Tier:\s*(\w+)")


def parse_stream_tier(text: str) -> str | None:
    """The tier from /flow's '## Tier Classification' block, lower-cased. Last match wins
    (a reclassification supersedes), None if the block never appeared."""
    chunks = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text":
                    chunks.append(block.get("text", ""))
    matches = _TIER_RE.findall("\n".join(chunks))
    return matches[-1].lower() if matches else None
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_outcome_probe.py -q`
Expected: `3 passed`

- [ ] **Step 5: Commit**

```bash
git add evals/outcome_probe.py tests/test_outcome_probe.py
git commit -m "test(evals): parse_stream_tier for outcome probe"
```

---

### Task 3: `read_marker_tier` — 마커 파일에서 tier 읽기 (TDD)

**Files:**
- Modify: `evals/outcome_probe.py`
- Test: `tests/test_outcome_probe.py`

**Interfaces:**
- Produces: `read_marker_tier(workdir: Path) -> str | None` — `<workdir>/.claude/harness-tier/.flow/tier`(`<tier>:<branch>`)의 tier를 소문자로, 없으면 None.

- [ ] **Step 1: 실패 테스트 추가**

`tests/test_outcome_probe.py`에 추가:

```python
from evals.outcome_probe import read_marker_tier


def test_read_marker_tier_reads_prefix(tmp_path):
    d = tmp_path / ".claude" / "harness-tier" / ".flow"
    d.mkdir(parents=True)
    (d / "tier").write_text("staging:feature/x", encoding="utf-8")
    assert read_marker_tier(tmp_path) == "staging"


def test_read_marker_tier_none_when_absent(tmp_path):
    assert read_marker_tier(tmp_path) is None
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_outcome_probe.py -k marker -q`
Expected: FAIL — `ImportError: cannot import name 'read_marker_tier'`

- [ ] **Step 3: 최소 구현** (`outcome_probe.py`에 추가)

```python
def read_marker_tier(workdir: Path) -> str | None:
    """The tier from /flow's marker file (written only if Phase 2 completed), or None.
    flow's fixture is null, so <workdir> is the session CWD and the marker lands beneath it."""
    marker = Path(workdir) / ".claude" / "harness-tier" / ".flow" / "tier"
    if not marker.exists():
        return None
    tier = marker.read_text(encoding="utf-8").strip().split(":", 1)[0].lower()
    return tier or None
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_outcome_probe.py -q`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add evals/outcome_probe.py tests/test_outcome_probe.py
git commit -m "test(evals): read_marker_tier for outcome probe"
```

---

### Task 4: probe 오케스트레이션 + 보고 (glue) + `golden_cases` (TDD)

**Files:**
- Modify: `evals/outcome_probe.py`
- Test: `tests/test_outcome_probe.py`

**Interfaces:**
- Produces: `golden_cases() -> list[tuple[str, str]]` — `(prompt, golden_tier)`; `_probe_one(...)`, `main(reps, jobs)`, `_report(rows)`, CLI.
- Consumes: `evals.run._claude_stream`, `evals.run.isolated_config_dir`, `evals.stream.observe` (Task 1).

- [ ] **Step 1: `golden_cases` 실패 테스트 추가**

```python
from evals.outcome_probe import golden_cases


def test_golden_cases_are_the_labelled_flow_prompts():
    cases = golden_cases()
    tiers = sorted(g for _, g in cases)
    assert tiers == ["dev", "dev", "dev", "staging"]           # 4 labelled, unlabelled dropped
    assert all(isinstance(p, str) and p for p, _ in cases)
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_outcome_probe.py -k golden -q`
Expected: FAIL — `ImportError: cannot import name 'golden_cases'`

- [ ] **Step 3: `golden_cases` 구현** (`outcome_probe.py`에 추가, 상단 import에 `import yaml` 추가)

```python
def golden_cases() -> list[tuple[str, str]]:
    """flow's happy prompts carrying a golden_tier — (prompt, golden_tier). The unlabelled
    'Commit these changes' (tier depends on the diff) is skipped."""
    data = yaml.safe_load((REPO / "evals/cases.yaml").read_text(encoding="utf-8"))
    out = []
    for case in data["skills"]["flow"]["happy"]:
        if isinstance(case, dict) and case.get("golden_tier"):
            out.append((case["prompt"], case["golden_tier"]))
    return out
```

- [ ] **Step 4: 통과 확인**

Run: `uv run pytest tests/test_outcome_probe.py -q`
Expected: `6 passed`

- [ ] **Step 5: 오케스트레이션 + 보고 + CLI 추가** (`outcome_probe.py`에 추가; 상단 import에 `import argparse, tempfile`, `from concurrent.futures import ThreadPoolExecutor, as_completed` 추가)

```python
def _probe_one(prompt: str, golden: str, config_dir: Path) -> dict:
    """One session; capture the tier two ways. Lazy import keeps run's subprocess machinery
    off the import path of the pure-function tests."""
    import tempfile

    from evals import run, stream

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        wd = Path(tmp)
        text, _err = run._claude_stream(prompt, None, wd, config_dir, False)
        return {
            "prompt": prompt,
            "golden": golden,
            "fired": "flow" in stream.observe(text).fired,
            "stream_tier": parse_stream_tier(text),
            "marker_tier": read_marker_tier(wd),   # read before the tempdir is cleaned
        }


def _report(rows: list[dict]) -> None:
    print(f"\n{'prompt':40} {'golden':8} {'fired':6} {'stream':8} {'marker':8} match")
    for r in rows:
        m = "-" if not r["fired"] else ("ok" if r["stream_tier"] == r["golden"] else "MISS")
        print(
            f"{r['prompt'][:40]:40} {r['golden']:8} {str(r['fired']):6} "
            f"{str(r['stream_tier']):8} {str(r['marker_tier']):8} {m}"
        )
    fired = [r for r in rows if r["fired"]]
    n = len(fired) or 1
    s_cap = sum(r["stream_tier"] is not None for r in fired)
    m_cap = sum(r["marker_tier"] is not None for r in fired)
    s_hit = sum(r["stream_tier"] == r["golden"] for r in fired)
    print(
        f"\nfired {len(fired)}/{len(rows)} | "
        f"stream capture {s_cap}/{n} match {s_hit}/{n} | marker capture {m_cap}/{n}"
    )


def main(reps: int = 3, jobs: int = 8) -> None:
    from evals import run

    plan = [(p, g) for p, g in golden_cases() for _ in range(reps)]
    rows: list[dict] = []
    with run.isolated_config_dir() as cfg:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [pool.submit(_probe_one, p, g, cfg) for p, g in plan]
            for done, fut in enumerate(as_completed(futures), 1):
                rows.append(fut.result())
                print(f"\r  {done}/{len(plan)} sessions", end="", flush=True)
    _report(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Router outcome-capture probe (③-a).")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true", help="list the cases; run nothing")
    args = ap.parse_args()
    if args.dry_run:
        cases = golden_cases()
        print(f"{len(cases)} case(s) x {args.reps} reps = {len(cases) * args.reps} sessions")
        for p, g in cases:
            print(f"  [{g:8}] {p}")
    else:
        main(reps=args.reps, jobs=args.jobs)
```

- [ ] **Step 6: 구조 확인 (모델 없음)**

Run: `uv run python -m evals.outcome_probe --dry-run`
Expected:
```
4 case(s) x 3 reps = 12 sessions
  [dev     ] Add a --verbose flag to the CLI.
  [dev     ] Fix the crash when the config file is missing.
  [staging ] Promote dev to stage.
  [dev     ] Refactor the parser into its own module.
```

- [ ] **Step 7: 전체 model-free 스위트 그린 확인**

Run: `uv run pytest tests/test_outcome_probe.py tests/test_evals.py tests/test_skills.py -q`
Expected: `... passed` (실패 0)

- [ ] **Step 8: Commit**

```bash
git add evals/outcome_probe.py tests/test_outcome_probe.py
git commit -m "test(evals): outcome probe orchestration and report"
```

---

### Task 5: probe 실행 → finding 기록 (모델 예산 소모, 사용자 승인 후)

**Files:** 없음(도구 실행). 결과는 대화로 보고.

- [ ] **Step 1: 사용자 승인 확인** — ~12세션(~2분, rate-limit 예산). 승인 없으면 여기서 멈춘다.

- [ ] **Step 2: probe 실행**

Run: `uv run python -m evals.outcome_probe --reps 3`
Expected: 세션별 표 + `fired .. | stream capture ../.. match ../.. | marker capture ../..` 요약.

- [ ] **Step 3: finding 판정**
- `stream capture`가 높고(≈발화 수) `marker capture`가 낮으면 → 스펙 추론 확인(스트림 파싱이 (b)의 캡처 방식).
- `match`가 golden과 일치하면 → 라우터가 옳게 분류 + 캡처 성립(outcome-eval 개념 실증).
- 예상외(둘 다 낮음/스트림도 실패) → 원인(형식 불일치·미발화) 진단해 (b) 재설계 입력으로.

- [ ] **Step 4: 결과를 대화로 보고** — 표·요약·(b) 권고. (파일 생성 안 함.)

---

## Self-Review

**1. Spec coverage:**
- 스펙 "컴포넌트 1 run.py 추출" → Task 1 ✓
- 스펙 "컴포넌트 2 outcome_probe.py (스트림·파일 캡처·판정·출력)" → Task 2(스트림)·3(마커)·4(golden_cases+오케·보고) ✓
- 스펙 "무손상 invariants" → Global Constraints + Task 1 Step 4 / Task 4 Step 7 ✓
- 스펙 "성공 기준·finding" → Task 5 ✓

**2. Placeholder scan:** 모든 코드 스텝에 실제 코드/명령/기대 출력 포함. placeholder 없음 ✓

**3. Type consistency:** `parse_stream_tier(text)->str|None`, `read_marker_tier(workdir)->str|None`, `golden_cases()->list[tuple[str,str]]`, `_probe_one(...)->dict`(키 `prompt/golden/fired/stream_tier/marker_tier`) — Task 4 `_report`/`main`이 쓰는 키와 일치 ✓. `run._claude_stream(prompt, fixture, workdir, config_dir, restricted)->(text,err)` — Task 1 정의와 Task 4 호출 일치(`fixture=None`) ✓
