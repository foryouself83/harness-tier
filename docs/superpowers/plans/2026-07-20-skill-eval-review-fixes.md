# Skill Eval 리뷰 발견 수정 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 커밋 82f6b98 리뷰에서 검증된 15건 + 경미 항목을 수정한다 — 측정 재현성(모델 고정·환경 격리), 게이트 견고성(scores.py), 소비자 배포 스킬의 이식성/권한, 스펙 문서 모순 제거.

**Architecture:** evals/(측정·게이트)와 skills/(배포 대상)와 docs/(스펙)를 각각 독립 커밋으로 수정한다. 게이트 로직(scores.py·stream.py·run.py)은 TDD, 스킬/문서는 기존 테스트(test_skills.py)가 회귀 방어. baseline 재측정은 하지 않는다(사용자 결정) — 대신 측정 조건 변경이 다음 측정에서 드러나도록 `model` 지문을 도입한다.

**Tech Stack:** Python 3.12, pytest, PyYAML, ruff (line-length 100).

## Global Constraints

- **인코딩**: 모든 `open()`/`read_text()`/`write_text()`는 `encoding="utf-8"` (cp949 로케일).
- **스타일**: 매 커밋 `uv run ruff check && uv run ruff format --check` 통과.
- **커밋 타입**: evals/·tests/·scripts/skill_sandbox.py → `chore(evals)`/`test(...)`, skills/*.md(소비자 전파 필요) → `fix(skills)`, docs/·CLAUDE.md → `docs:`, .gitignore → `chore:`. 제목 ≤50자, 본문 ≤72자/줄.
- **재측정 없음**: scores.json의 측정값(k/n)은 건드리지 않는다. 스키마 필드 추가(backfill)만 허용.
- **브랜치**: `fix/skill-eval-review`. merge는 risk-tiers 전략(fix/* → dev rebase/ff).
- **의도적 제외**(scope 협의 결과): git 이력 재작성(커밋 제목 62자, fix/test 분리), 테스트 parametrize 리팩터(G1·G8), 성능 캐싱(H4–H6), make_project↔sandbox 통합(F5), REPO 상수 통일(F7), issued_commands의 따옴표-내-`|` 분할(E4 일부), backend non-web 신호 확장(설계 필요 — Go 한정어 모순만 제거).

---

### Task 1: scores.py — 게이트 견고성 + 모델 지문 (TDD)

**Files:**
- Modify: `evals/scores.py`
- Test: `tests/test_evals.py`

**Interfaces:**
- Produces: `scores.MODEL: str` ("claude-opus-4-8"), `scores.parse_frontmatter(path: Path) -> dict`, `check()` 시그니처 불변(entry의 `model` 키를 내부에서 검사).
- Consumes: 없음 (최하층).

- [ ] **Step 1: 실패하는 테스트 추가** — `tests/test_evals.py`에 (기존 테스트 옆, gate 관련 섹션):

```python
def test_check_order_fails_an_undeclared_skill_even_when_unmeasured():
    """스펙 §6: 선언 없는 스킬은 게이트가 판정을 거부하고 FAIL한다 — 측정 여부와 무관하게.
    entry-None warn이 expect-None fail보다 먼저 반환되면 미측정+미선언 스킬이 경고로 통과한다."""
    v = scores.check("ghost", None, "whatever", None, n_skills=7)
    assert v.level == "fail" and "expect_invoke" in v.message


def test_check_fails_a_missing_count_key_with_a_verdict_not_a_keyerror():
    """이 모듈의 위협 모델은 손으로 고친 scores.json이다 — KeyError는 스킬명도 원인도
    말해주지 않는다."""
    entry = {"description_sha": "x", "invoke_rate": 0.5}
    v = scores.check("integration", entry, "x", 0.7, n_skills=7)
    assert v.level == "fail" and "invoke_hits" in v.message


def test_false_fire_ceiling_reads_the_raw_counts_not_the_rounded_rate():
    """반올림된 파생 필드는 손편집으로 카운트와 어긋날 수 있고, 큰 n에서는 0.204가
    0.20으로 반올림돼 천장을 넘고도 통과한다."""
    entry = _entry(false_hits=5, false_n=15, false_fire=0.0)  # 파생 필드가 거짓말
    v = scores.check("integration", entry, entry["description_sha"], 0.7, n_skills=7)
    assert v.level == "fail" and "false" in v.message


def test_a_model_mismatch_fails_like_a_stale_sha():
    """baseline은 측정된 모델에 관한 사실이다. 모델 지문이 다르면 sha처럼 재측정을 강제한다."""
    entry = _entry(model="claude-sonnet-5")
    v = scores.check("integration", entry, entry["description_sha"], 0.7, n_skills=7)
    assert v.level == "fail" and "model" in v.message


def test_may_write_skips_the_ratchet_across_a_model_change():
    """다른 모델의 k/n과 비교하는 것은 두 양을 하나로 취급하는 짓이다(스킬 회귀가 아니라
    모델 차이를 측정). 모델이 바뀌면 새 baseline으로 취급한다 — MODEL 상수 변경은
    코드 리뷰를 거치는 명시적 행위이므로 우회 경로가 아니다."""
    new = _entry(invoke_hits=0, invoke_n=15, model=scores.MODEL)
    old = _entry(invoke_hits=15, invoke_n=15, model="claude-sonnet-5")
    v = scores.may_write("integration", new, old, accepted=False, n_skills=7)
    assert v.level == "ok"
```

`_entry`는 같은 파일에 두는 픽스처 팩토리(기존 인라인 dict 갱신 부담을 줄인다):

```python
def _entry(**overrides) -> dict:
    base = {
        "description_sha": scores.description_sha("integration"),
        "model": scores.MODEL,
        "invoke_hits": 4, "invoke_n": 15, "invoke_rate": 0.27,
        "false_hits": 0, "false_n": 15, "false_fire": 0.0,
    }
    return {**base, **overrides}
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_evals.py -k "check_order or count_key or raw_counts or model" -q` → FAIL (AttributeError: MODEL 없음 / 순서·KeyError).

- [ ] **Step 3: 구현** — `evals/scores.py`:

(a) 상수 추가 (ALPHA_FAMILY 아래):

```python
# The baseline describes exactly one model. "opus" (a floating CLI alias) held this slot
# for a while and defeated its own comment: when the alias retargets, every re-measure
# silently compares a new model's k/n against an old model's — the measured spread on one
# case was 0/4 vs 4/4 across models. Pin the full ID, stamp it per entry, and fail
# freshness on a mismatch exactly like description_sha.
MODEL = "claude-opus-4-8"
```

(b) `description_sha`의 프론트매터 파싱을 분리해 SSOT로 승격 (테스트 파일 2곳이 재사용):

```python
def parse_frontmatter(path: Path) -> dict:
    """The one frontmatter grammar for this repo's eval/test layers. scripts/
    harness_scaffold.py keeps its own copy on purpose — it ships to consumer hosts and
    must run without evals/ on the path; these two are the only sanctioned copies."""
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if m is None:
        raise ValueError(f"{path} has no frontmatter block")
    return yaml.safe_load(m.group(1))


def description_sha(name: str) -> str:
    """(기존 독스트링 유지)"""
    front = parse_frontmatter(REPO / f"skills/{name}/SKILL.md")
    return hashlib.sha256(front["description"].encode("utf-8")).hexdigest()[:12]
```

(c) `check()` 재구성 — 순서·키 검증·카운트 게이트·모델 지문:

```python
def check(name: str, entry: dict | None, sha: str, expect: float | None, n_skills: int) -> Verdict:
    # Before anything else: the gate refuses to operate on a skill that has not declared
    # what it expects — measured or not. Checking entry first returned "warn" for an
    # unmeasured-and-undeclared skill, quietly bypassing the forcing function that
    # replaced the floor.
    if expect is None:
        return Verdict("fail", f"{name}: declare expect_invoke and expect_why in cases.yaml")
    if entry is None:
        return Verdict("warn", f"{name}: not measured yet — run python -m evals.run")
    # The threat model here is a hand-edited scores.json (see the lowered_from note
    # below). A missing key must name the skill and the fix, not raise a bare KeyError.
    missing = [k for k in ("invoke_hits", "invoke_n", "false_hits", "false_n") if k not in entry]
    if missing:
        return Verdict("fail", f"{name}: entry is missing {missing} — re-measure")
    if entry.get("description_sha") != sha:
        return Verdict("fail", f"{name}: description changed since the score — re-measure")
    if entry.get("model") != MODEL:
        return Verdict(
            "fail",
            f"{name}: score measured on {entry.get('model')!r}, gate pinned to {MODEL!r}"
            f" — re-measure",
        )
    # (기존 zero-floor 주석 유지)
    if entry["invoke_hits"] == 0:
        return Verdict("fail", f"{name}: invoke_rate is 0 — description never fires, re-measure")
    # Counts, not the rounded derived rate: the derived field can drift from the counts
    # under a hand edit, and at a reps-raised n a true rate in (0.20, 0.205] rounds down
    # to a passing 0.20. Same reason the zero floor above reads the integer hits.
    if entry["false_hits"] > MAX_FALSE_FIRE * entry["false_n"]:
        return Verdict(
            "fail",
            f"{name}: false_fire {entry['false_hits']}/{entry['false_n']} > {MAX_FALSE_FIRE}",
        )
    # (이하 lowered_from 검사 · 선언 미달 warn · ok — 기존 그대로, expect None 분기는 위로 이동했으므로 삭제)
```

(d) `may_write()` — 모델 경계에서 래칫 중단:

```python
    if old is None or accepted or old.get("model") != new.get("model"):
        # A model change makes old and new k/n incomparable — the exact binomial would
        # attribute model drift to the description. MODEL is a reviewed code constant,
        # so this is a re-baseline, not an escape hatch.
        return Verdict("ok", f"{name}: writing")
```

- [ ] **Step 4: 통과 확인 + 기존 테스트 수리** — `uv run pytest tests/test_evals.py -q`. 기존 entry dict를 쓰는 테스트가 model/missing-key 검사에 걸리면 해당 dict에 `"model": scores.MODEL`(및 필요한 카운트 키)를 추가하거나 `_entry()` 팩토리로 교체한다. pytest 실패 메시지가 갱신 지점을 정확히 가리킨다. (Task 2 전이므로 committed-baseline 테스트는 아직 빨간불 — 정상. Task 2에서 초록.)

- [ ] **Step 5: 커밋**

```bash
git add evals/scores.py tests/test_evals.py
git commit -m "chore(evals): pin eval model, harden gate checks" -m "check() refuses an undeclared skill before the unmeasured warn, reads
false_fire from raw counts, fails missing keys with a verdict, and fails
a model-fingerprint mismatch like a stale sha. may_write() re-baselines
across a model change instead of ratcheting incomparable k/n. MODEL is
the pinned full ID (claude-opus-4-8), not the floating alias."
```

---

### Task 2: scores.json backfill — model·lost_to 스키마 동질화

**Files:**
- Modify: `evals/scores.json`
- Test: `tests/test_evals.py` (committed-baseline 게이트가 검증)

**Interfaces:**
- Consumes: Task 1의 `scores.MODEL`.
- Produces: 7개 항목 전부 `"model": "claude-opus-4-8"`, `"lost_to": {}` 보유.

- [ ] **Step 1: 7개 항목 각각에 두 키 추가** (알파벳 순서 유지 — run.py의 save()가 sort_keys로 쓰므로 자리: `invoke_rate` 다음 `lost_to`, `measured_at` 다음 `model`):

```json
      "invoke_rate": 0.67,
      "lost_to": {},
      "measured_at": "2026-07-19",
      "model": "claude-opus-4-8",
```

근거: 커밋된 baseline은 2026-07-19에 `--model opus`로 측정됐고 당시 alias는 opus-4-8이었다(설계 문서 §2의 모델 표가 그 측정이다). `lost_to`는 measure()가 항상 쓰는 필드지만 재구성된 baseline에만 없어 다음 실행부터 스키마가 이질화된다 — 빈 dict가 정직한 값이다(재구성 시점에 손실 기록 없음).

- [ ] **Step 2: 게이트 초록 확인** — `uv run pytest tests/test_evals.py -q` → PASS (특히 `test_the_committed_baseline_passes_the_gate`).

- [ ] **Step 3: 커밋**

```bash
git add evals/scores.json
git commit -m "chore(evals): stamp model on committed baseline" -m "Backfill model (claude-opus-4-8, what the opus alias resolved to at
measurement time per the design doc's model table) and lost_to ({}) so
the schema matches what measure() writes and the new model-freshness
check has a fingerprint to validate."
```

---

### Task 3: stream.py — rejected만 치명 + skill:null 방어 (TDD)

**Files:**
- Modify: `evals/stream.py`
- Test: `tests/test_evals.py`

- [ ] **Step 1: 실패하는 테스트**

```python
def test_a_rate_limit_warning_is_not_a_stop_signal():
    """allowed_warning은 요청이 성공하면서 붙는 상태다 — 이것으로 전량 측정을 중단하면
    창 후반의 모든 실행이 시작 즉시 죽는다. 중단은 rejected(요청이 실제로 실패)만."""
    warned = "\n".join([
        json.dumps({"type": "rate_limit_event", "rate_limit_info": {"status": "allowed_warning"}}),
    ])
    assert not stream.observe(warned).rate_limited


def test_a_null_skill_input_is_skipped_not_fatal():
    """중단된 Skill 호출이 {"skill": null}로 직렬화되면 .get("skill", "")은 None을
    돌려주고 _local(None)이 스트림 전체 관측을 죽인다."""
    line = json.dumps({
        "type": "assistant",
        "message": {"content": [{"type": "tool_use", "name": "Skill", "input": {"skill": None}}]},
    })
    obs = stream.observe(line)
    assert obs.fired == [] and obs.tool_calls == 1
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_evals.py -k "warning_is_not or null_skill" -q` → FAIL.

- [ ] **Step 3: 구현** — `evals/stream.py`:

```python
        elif event.get("type") == "rate_limit_event":
            # Only an actual refusal stops a run. A warning-level status rides on a
            # session whose request *succeeded*; treating any non-"allowed" status as
            # fatal made every run started late in the window abort on its first
            # session. An unknown exhausted-but-not-"rejected" status still fails loudly
            # downstream: refused requests error the session and trip `errored`.
            obs.rate_limited = (event.get("rate_limit_info") or {}).get("status") == "rejected"
```

```python
                if block.get("name") == "Skill":
                    name = _local((block.get("input") or {}).get("skill") or "")
```

- [ ] **Step 4: 통과 확인** — 위 -k 재실행 → PASS. 전체 `uv run pytest tests/test_evals.py -q` → PASS.

- [ ] **Step 5: 커밋**

```bash
git add evals/stream.py tests/test_evals.py
git commit -m "chore(evals): stop only on rejected rate limit" -m "A warning-level rate_limit status rides on successful sessions; aborting
on it made late-window runs die on their first session. Also guard a
null Skill input, which killed observe() for the whole stream."
```

---

### Task 4: run.py — 환경 격리·트리 킬·자잘한 방어 (TDD 가능한 부분만)

**Files:**
- Modify: `evals/run.py`
- Test: `tests/test_evals.py`

**Interfaces:**
- Consumes: `scores.MODEL` (Task 1).
- Produces: `run.session_env(config_dir: Path) -> dict[str, str]` (테스트가 사용).

- [ ] **Step 1: 실패하는 테스트**

```python
def test_session_env_strips_provider_variables(monkeypatch):
    """격리는 config 디렉터리만이 아니다 — ANTHROPIC_BASE_URL 하나가 세션 전부를
    프록시로 보내고, 그 baseline은 한 개발자의 셸에 관한 사실이 된다."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-leak")
    monkeypatch.setenv("CLAUDE_CODE_EXTRA", "x")
    monkeypatch.setenv("PATH", os.environ.get("PATH", ""))
    env = run.session_env(Path("/tmp/cfg"))
    assert "ANTHROPIC_API_KEY" not in env
    assert "CLAUDE_CODE_EXTRA" not in env
    assert env["CLAUDE_CONFIG_DIR"] == str(Path("/tmp/cfg"))
    assert "PATH" in env  # 시스템 변수는 살아야 CLI가 뜬다


def test_reps_must_be_positive():
    with pytest.raises(SystemExit):
        run.main.__wrapped__ if False else None  # argparse 검증은 아래 방식으로
```

`--reps 0` 검증은 argparse 레벨이라 subprocess 없이 이렇게 잰다:

```python
def test_reps_zero_is_rejected(monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["evals.run", "--reps", "0", "--dry-run", "--all"])
    with pytest.raises(SystemExit) as e:
        run.main()
    assert e.value.code == 2  # argparse error
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/test_evals.py -k "session_env or reps_zero" -q` → FAIL (session_env 없음).

- [ ] **Step 3: 구현** — `evals/run.py`:

(a) `MODEL = "opus"` 상수와 그 주석 블록 삭제, `MODEL` 사용처를 `scores.MODEL`로 교체 (cmd 조립부 `"--model", scores.MODEL`).

(b) `session_env` 추출 + 블랙리스트 (env 조립부 교체):

```python
def session_env(config_dir: Path) -> dict[str, str]:
    """Everything provider-shaped is stripped rather than whitelisting the world: the
    CLI needs an unknowable, platform-varying set of system variables (PATH, APPDATA,
    node's own), while the contamination surface is exactly the provider-prefixed names
    — ANTHROPIC_BASE_URL reroutes every session through a proxy, ANTHROPIC_API_KEY
    switches the auth path away from the copied credential, CLAUDE_CODE_* flips CLI
    behaviour. One developer's shell must not become a fact in the committed baseline."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not (k.startswith("ANTHROPIC_") or k.startswith("CLAUDE_"))
    }
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    return env
```

run_session에서 `env = session_env(config_dir)`.

(c) 타임아웃 트리 킬 — `subprocess.run(...)` 블록을 Popen으로 교체:

```python
    proc = subprocess.Popen(
        cmd,
        cwd=workdir,
        env=env,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    try:
        out, err = proc.communicate(timeout=SESSION_TIMEOUT)
    except subprocess.TimeoutExpired:
        # subprocess.run()'s timeout path kills only the direct child and then drains
        # the pipes with an UNBOUNDED communicate(); a surviving grandchild holding the
        # inherited write handles blocks that read forever — on this repo's own Windows
        # evidence that children outlive the kill, the "hang guard" was itself the hang.
        # Kill the tree first, then drain: with every writer dead the pipes close.
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
        else:
            proc.kill()
        out, err = proc.communicate()
```

(d) `--reps` 검증 (argparse 파싱 직후, --accept 검증들 옆):

```python
    if args.reps < 1:
        ap.error("--reps must be >= 1")
```

(e) rate-limit 복구 안내를 남은 대상 명시로 교체 (RateLimited except 블록):

```python
            except RateLimited as e:
                save()
                print(f"\n{e}", file=sys.stderr)
                remaining = targets[targets.index(name):]
                # "re-run without --all" was wrong advice for an interrupted --all run:
                # the remaining skills' old entries still carry matching shas, so the
                # incremental default would skip them and report everything current.
                print(
                    f"{measured}/{len(targets)} skills measured and saved. When the "
                    f"window resets, finish with: "
                    + " ".join(f"--skill {n}" for n in remaining),
                    file=sys.stderr,
                )
                return 1
```

(f) credentials 부재 메시지 확장 (isolated_config_dir):

```python
        if not src.exists():
            raise SystemExit(
                f"no credentials at {src} — isolated sessions cannot authenticate. "
                f"Keychain-stored logins (macOS) and API-key auth keep nothing there; "
                f"this runner currently requires a machine whose login wrote "
                f".credentials.json (Windows/Linux subscription login)."
            )
```

- [ ] **Step 4: 통과 확인** — `uv run pytest tests/test_evals.py -q` → PASS (`_NoRealSessions` 몽키패치가 실세션을 막는지 확인 — run.subprocess를 patched 객체로 바꾸는 기존 픽스처와 Popen 사용이 충돌하면 픽스처의 스텁에 Popen 속성을 추가).

- [ ] **Step 5: 커밋**

```bash
git add evals/run.py tests/test_evals.py
git commit -m "chore(evals): isolate session env, kill tree" -m "session_env() strips ANTHROPIC_*/CLAUDE_* so one developer's shell
cannot leak into the baseline; the timeout path kills the process tree
before draining pipes (run()'s unbounded post-kill communicate() hung on
surviving grandchildren); --reps<1 is rejected; the rate-limit recovery
message names the remaining skills instead of advice that skips them;
the model pin moves to scores.MODEL; the credentials error explains the
Keychain/API-key limitation."
```

---

### Task 5: test_evals.py — 경고 집합 스냅숏 해제 + gate() 일원화

**Files:**
- Modify: `tests/test_evals.py`

- [ ] **Step 1: `test_the_committed_baseline_passes_the_gate` 교체**

```python
def test_the_committed_baseline_passes_the_gate():
    """The gate itself, applied to the file that is actually committed. Fail is the only
    hard state; warns surface via pytest's warning summary. The warn set is deliberately
    NOT pinned: a ratchet-approved dip adds a warn and an improvement removes one, and a
    suite that turns red on either teaches people to edit the test instead of reading
    the warning (the spec's warn-is-information semantics, §6)."""
    baseline = scores.load()
    for name in SKILLS:
        gate(
            name,
            baseline.get("skills", {}).get(name),
            scores.description_sha(name),
            CASES["skills"][name].get("expect_invoke"),
            len(SKILLS),
        )
```

(gate()의 시그니처가 이미 `(name, entry, sha, expect, n_skills)`이므로 그대로 사용 — G3의 "gate()가 자기 테스트에만 쓰인다" 문제도 이 일원화로 해소된다.)

- [ ] **Step 2: 확인** — `uv run pytest tests/test_evals.py -q` → PASS, 경고 요약에 integration·flow가 보인다.

- [ ] **Step 3: 커밋**

```bash
git add tests/test_evals.py
git commit -m "test(evals): unpin the baseline warn set" -m "warned == {integration, flow} turned every legitimate write red — a
ratchet-approved dip adds a warn, an improvement removes one, and an
--accept'ed drop still warns. The gate asserts no fail and lets warns
surface as warnings, which is the spec's stated semantics."
```

---

### Task 6: 케이스↔픽스처 정합화 + 샌드박스 수정

**Files:**
- Modify: `evals/cases.yaml`, `scripts/skill_sandbox.py`
- Test: `uv run pytest tests/test_skills.py tests/test_evals.py -q` (기존 스위트가 방어)

- [ ] **Step 1: cases.yaml — integration 해피 2건에 per-case fixture**

```yaml
    happy:
      - Run the end-to-end tests for this project and tell me what fails.
      # These two describe a project with no automation, which contradicts the skill's
      # default fixture (custom-testdir ships a real 2-spec suite): the agent spent its
      # turns reconciling the contradiction and the misses were frozen into the 4/15
      # baseline. empty-web is the project state the prompts actually describe.
      # Prompts corrected 2026-07-20; the committed scores predate this — the next
      # measurement re-baselines them (the ratchet's --accept path exists for that).
      - prompt: I need to verify this app works end to end — there is no automation yet.
        fixture: empty-web
      - Check that the whole flow works in a real browser, not just unit tests.
      - Can you do integration verification on this repo?
      - prompt: Set up e2e coverage for this project.
        fixture: empty-web
```

- [ ] **Step 2: cases.yaml — doc-sync 해피 1행을 픽스처의 실제 파일로**

```yaml
      - I renamed the config keys in app/server.py — check the docs still match.
```

- [ ] **Step 3: skill_sandbox.py — perf-n-plus-one에 프런트 파일 추가** (performance 해피 "React table re-renders"가 참조할 실체; files dict에 추가):

```python
            "frontend/Table.jsx": (
                "export function Table({ rows }) {\n"
                "  // re-render churn: a fresh object + closure per row per render\n"
                "  return rows.map((r) => (\n"
                "    <Row key={r.id} style={{ padding: 4 }} onClick={() => select(r)} />\n"
                "  ));\n"
                "}\n"
            ),
```

- [ ] **Step 4: skill_sandbox.py — scaffold-baseurl-unknown에 baseURL 없는 config 추가** (why가 서술하는 바로 그 상태 — Step 4의 "기존 config 수정, 교체 금지" 분기가 처음으로 픽스처를 갖는다). files에 추가 + expect 보강:

```python
            "playwright.config.ts": (
                "import { defineConfig } from '@playwright/test';\n"
                "export default defineConfig({ testDir: './tests' });\n"
            ),
```

```python
        expect=[
            "gathers baseURL candidates from the codebase (8080 and/or 5173)",
            "asks the user to confirm which baseURL is right",
            "adds use.baseURL to the existing config rather than replacing it",
        ],
```

- [ ] **Step 5: skill_sandbox.py — --list 잘림·--json 제거**

`--list` 출력: `s.why.split('.')[0]` → 파일명 마침표에서 끊긴다:

```python
        for s in SCENARIOS:
            first = s.why.split(". ")[0].rstrip(".")
            print(f"{s.name:26} /{s.skill:20} {first}.")
```

`--json` 인자와 그 분기 전체 삭제 (소비자 없음 — run.py는 build()/BY_NAME을 직접 import, 테스트는 CLI를 안 부른다).

- [ ] **Step 6: 확인** — `uv run pytest -q` → PASS. `uv run python scripts/skill_sandbox.py --list` → 3개 시나리오의 rationale이 문장 단위로 출력.

- [ ] **Step 7: 커밋**

```bash
git add evals/cases.yaml scripts/skill_sandbox.py
git commit -m "chore(evals): align case prompts with fixtures" -m "Two integration happy prompts described a project with no automation
while running inside a fixture shipping a real suite; doc-sync named a
file its fixture lacks; performance asked about a React table in a pure
Django fixture. Prompts/fixtures now agree (per-case fixture overrides;
a JSX file with a re-render anti-pattern). scaffold-baseurl-unknown now
ships the no-baseURL config its why describes, so Step 4's edit-not-
replace branch is exercised. --list stops truncating inside filenames;
the consumerless --json flag is gone."
```

---

### Task 7: 케이스 발견 명령 이식성 (스킬 3파일 + 추출기·행동 테스트)

**Files:**
- Modify: `skills/integration/SKILL.md`(§3.2), `skills/integration/references/web-playwright.md`(§3.1), `skills/playwright-scaffold/SKILL.md`(Step 3) — 세 곳 동일하게
- Modify: `tests/test_skills.py` (`case_discovery_command`)

- [ ] **Step 1: 세 파일의 발견 명령 교체** — 기존:

```bash
TESTDIR=$(grep -hoE "testDir:[[:space:]]*['\"][^'\"]+" playwright.config.* 2>/dev/null | head -1 | sed -E "s/.*['\"]//")
TESTDIR="${TESTDIR:-./tests}"
[ -d "$TESTDIR" ] && find "$TESTDIR" -regextype posix-extended -regex '.*\.(spec|test)\.(c|m)?[jt]sx?' || echo "MISSING: $TESTDIR"
```

교체 (마지막 줄만 변경 — 위 두 줄은 그대로):

```bash
if [ -d "$TESTDIR" ]; then find "$TESTDIR" -type f 2>/dev/null | grep -E '\.(spec|test)\.(c|m)?[jt]sx?$' || true; else echo "MISSING: $TESTDIR"; fi
```

이유를 명령 위 주석에 남긴다 (세 파일 동일):

```bash
# POSIX find + grep -E: -regextype is GNU-only (BSD/macOS find rejects it, exits 1, and
# the old `&& … || echo MISSING` chain then reported every healthy project as MISSING —
# and conflated any find failure with an absent directory). `|| true`: zero matches is
# an answer, not an error. MISSING now comes only from the [ -d ] test.
```

- [ ] **Step 2: 추출기 갱신** — `tests/test_skills.py` `case_discovery_command`:

```python
    search = re.search(r'^if \[ -d "\$TESTDIR" \]; then find .*fi$', text, re.M)
```

(기존 `\[ -d ... \] && find` 패턴 교체. `re.sub`의 trailing-consumer 제거 로직은 그대로 두되 대상이 없어졌으므로 no-op — 삭제하지 말 것, 어느 파일이 `| wc -l`을 되살리면 다시 필요하다.)

- [ ] **Step 3: 확인** — `uv run pytest tests/test_skills.py -q` → PASS (agreement 테스트가 세 파일 일치를, 픽스처 행동 테스트 7종이 4-outcome 시맨틱 보존을 검증한다 — custom-testdir 2건 발견, 빈 디렉터리 0건+rc0, 부재 디렉터리 MISSING, config-선언 MISSING 구분).

- [ ] **Step 4: 커밋**

```bash
git add skills/integration/SKILL.md skills/integration/references/web-playwright.md skills/playwright-scaffold/SKILL.md tests/test_skills.py
git commit -m "fix(skills): portable case discovery command" -m "find -regextype is GNU-only: on macOS/BSD the old chain exited nonzero
and the || branch reported every healthy project as MISSING (config-
declared testDirs then dead-end at 'report the misconfiguration'). An
explicit if/else keeps MISSING strictly for the absent-directory case,
and grep -E carries the regex portably. Same line in all three files;
the extractor and fixture tests follow."
```

---

### Task 8: allowed-tools 정밀화 + 그 테스트 지반 강화

**Files:**
- Modify: `skills/performance/SKILL.md`, `skills/flow/SKILL.md`, `skills/doc-sync/SKILL.md`, `.claude/rules/skill-frontmatter.md`
- Modify: `tests/test_skills.py`

- [ ] **Step 1: performance — npx 사전승인 제거** (frontmatter):

```yaml
# The measurement tools this skill drives. `pip install lizard` is absent on purpose —
# installing into the host's environment is the user's call, not a pre-approved one.
# `npx @grafana/openapi-to-k6` is absent for the same reason: on first use npx *fetches
# the package into the host's npm cache*, so pre-approving it pre-approves an install.
allowed-tools: Bash(k6 run *) Bash(lizard *)
```

- [ ] **Step 2: flow·doc-sync — 경로 글롭을 정확 매치로** (`*`가 `..`를 포함해 경로 구분자를 넘는다 — 이 저장소 자체의 매처 모델(fnmatch)로 `touch …/.flow/../../../<any>`가 통과했다):

`skills/flow/SKILL.md`:

```yaml
# Pre-approves only the gate-evidence writes — the one thing this skill does several
# times per run. Exact rules, no trailing path glob: a glob's `*` crosses `..`, so
# `touch …/.flow/*` pre-approved touch of any path on disk. `git commit` and `rm -rf`
# are deliberately absent: the commit prompt is the mechanical backstop behind the
# gate, and the Phase 4 cleanup should stay deliberate.
allowed-tools: Bash(mkdir -p .claude/harness-tier/.flow) Bash(touch .claude/harness-tier/.flow/doc-sync.done) Bash(touch .claude/harness-tier/.flow/review.done) Bash(touch .claude/harness-tier/.flow/bump.done) Bash(touch .claude/harness-tier/.flow/security.done)
```

`skills/doc-sync/SKILL.md`:

```yaml
# The gate marker this skill writes on pass — an exact rule, no trailing path glob
# (a glob's `*` crosses `..`). Doc edits themselves stay promptable.
allowed-tools: Bash(mkdir -p .claude/harness-tier/.flow) Bash(touch .claude/harness-tier/.flow/doc-sync.done)
```

- [ ] **Step 3: flow:168의 brace 확장을 명시 2행으로** (정확 매치 룰이 brace 리터럴과 안 맞고, "명령은 쓰인 대로 실행된다" 규율에도 맞다):

```markdown
  4. `touch .claude/harness-tier/.flow/review.done` ·
     `touch .claude/harness-tier/.flow/bump.done`.
```

- [ ] **Step 4: skill-frontmatter.md — 취약 예시 자체를 교정** (규칙 문서의 예시가 이 버그를 가르쳤다; line ~32):

```yaml
allowed-tools: Bash(k6 run *) Bash(touch .claude/harness-tier/.flow/doc-sync.done)
```

예시 아래 한 문장 추가:

```markdown
Never end a rule in a path glob (`…/.flow/*`): `*` crosses path separators including
`..`, so it pre-approves the command against any path on disk. Marker sets are finite —
enumerate them exactly.
```

- [ ] **Step 5: 테스트 지반 — test_skills.py 세 가지**

(a) 경로 글롭 금지 (신규):

```python
@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_no_allowed_tools_rule_ends_in_a_path_glob(skill: Path):
    """`Bash(touch dir/*)`'s star crosses path separators including `..` — it grants the
    command against every path on disk while reading as a directory scope. A space
    before `*` (`k6 run *`) is the prefix-boundary form and stays legal."""
    for rule in declared_rules(skill):
        assert not re.search(r"/\*\)?$", rule), (
            f"{skill.parent.name}: {rule} ends in a path glob — enumerate exact paths"
        )
```

(b) MUST_STILL_PROMPT 문자열이 스킬 본문에서 여전히 도출되는지 (신규 — 리터럴 부패 방지):

```python
@pytest.mark.parametrize("name", sorted(MUST_STILL_PROMPT), ids=sorted(MUST_STILL_PROMPT))
def test_must_still_prompt_literals_track_the_skill_text(name: str):
    """A stale literal guards nothing: if the skill rewords the command, the old string
    keeps matching no rule while a new rule matching the new wording ships unseen. Each
    probe's first two tokens must still appear in a command the skill issues."""
    issued = issued_commands(REPO / f"skills/{name}/SKILL.md")
    for command in MUST_STILL_PROMPT[name]:
        head = " ".join(command.split()[:2])
        assert any(c.startswith(head) for c in issued), (
            f"{name}: no issued command starts with {head!r} — the probe {command!r} "
            f"is stale; update MUST_STILL_PROMPT to the skill's current wording"
        )
```

주의: `performance`의 `pip install lizard`는 본문 prose에 인라인 코드로 존재해야 통과한다 — SKILL.md 4행 주석이 아니라 **본문**에서 확인하고, 없으면 references의 설치 안내 문구를 확인해 head가 도출되는 파일을 issued_commands 스캔 대상에 맞춘다(스캔은 SKILL.md+references 전체다). `integration`의 npm/npx install 프로브도 §3.2/scaffold 참조 문구에서 도출된다. 실패 시 프로브를 현재 문구로 갱신하는 것이 fix다(테스트 메시지가 그렇게 안내).

또한 performance에 npx 프로브 추가:

```python
    "performance": ["pip install lizard", "npx @grafana/openapi-to-k6 --version"],
```

(c) issued_commands 인라인 수확 조이기 — 한 단어 백틱(`lizard`, `testDir`)이 명령으로 세지 않게:

```python
    raw += re.findall(r"`([a-z][\w.-]* [^`\n]+)`", text)
```

독스트링의 해당 불릿도 갱신: "inline `` `touch ...` `` in prose (**an argument required** — a bare one-word token is a name, not a command)".

- [ ] **Step 6: 확인** — `uv run pytest tests/test_skills.py -q` → PASS. 특히 dead-rule 테스트: flow의 정확 룰 4종은 본문 인라인/펜스 명령(124·146·147·168분리·175)과, doc-sync 룰 2종은 본문 108행 `mkdir … && touch …` 분리 결과와 매치.

- [ ] **Step 7: 커밋**

```bash
git add skills/performance/SKILL.md skills/flow/SKILL.md skills/doc-sync/SKILL.md .claude/rules/skill-frontmatter.md tests/test_skills.py
git commit -m "fix(skills): scope grants, drop npx install" -m "performance no longer pre-approves npx @grafana/openapi-to-k6 — npx
fetches the package on first use, which is an install the rule and the
commit that shipped it promised would stay prompted. flow/doc-sync's
touch rules become exact marker paths: a trailing path glob crosses ..
and granted touch anywhere on disk. The rule doc's own example taught
the bug and is corrected. Tests: path-glob ban, MUST_STILL_PROMPT
staleness tracking, one-word backtick spans no longer count as issued
commands."
```

---

### Task 9: 스킬 문서 정합성 — web verdict·doc-sync diff·scaffold Step 4

**Files:**
- Modify: `skills/integration/references/web-playwright.md`, `skills/doc-sync/SKILL.md`, `skills/playwright-scaffold/SKILL.md`

- [ ] **Step 1: web-playwright.md §1.3 — Go 행 한정어 제거 + §1.2에 우선순위 문장** (SKILL.md의 "non-web이 항상 우선"과 참조 문서가 서로 다른 판정을 내리던 모순 제거):

§1.3 Go 행: `main.go / go.mod (+ no web signals)` → `main.go / go.mod`

§1.2 표 아래 한 문장 추가:

```markdown
Supporting signals carry the Web verdict on their own **only when no non-web signal
(§1.3) is present** — §1.3 takes precedence unconditionally, exactly as
`integration/SKILL.md` §2 states. An Electron or Go project also ships an `index.html`.
```

(backend 스택용 non-web 신호 확장은 이번 범위에서 의도적으로 제외 — §1.3에 새 신호를 더하는 것은 판정 설계 변경이라 별도 검토가 필요하다.)

- [ ] **Step 2: doc-sync SKILL.md §1 — 잘림 내성 파일 목록 복원**:

```bash
git diff HEAD                                   # the change itself — hunks per file
git diff --name-only HEAD                       # the complete file list — immune to a
                                                # truncated diff on a large refactor
git ls-files --others --exclude-standard        # new files, which the diff does not show
```

- [ ] **Step 3: playwright-scaffold Step 4 — 1행과 설치 불릿의 충돌 해소**: 표 1행 `nothing to do` → `nothing to do (config-wise — if @playwright/test itself is missing, guide the install below)`, 설치 불릿에서 "scaffold a minimal config" 조건을 config-부재로 한정:

```markdown
- If `playwright.config.*` is absent, scaffold the minimal config below. If
  `@playwright/test` is not installed (config present or not), **guide** installation —
  do not force auto-install, only with consent:
```

- [ ] **Step 4: 확인** — `uv run pytest tests/test_skills.py -q` → PASS (링크·섹션 참조 테스트 통과).

- [ ] **Step 5: 커밋**

```bash
git add skills/integration/references/web-playwright.md skills/doc-sync/SKILL.md skills/playwright-scaffold/SKILL.md
git commit -m "fix(skills): align web verdict docs, diff list" -m "web-playwright's Go row carried a '+ no web signals' qualifier that
contradicted the unconditional non-web precedence SKILL.md states, so
the two shipped documents judged a Go repo with public/ differently.
doc-sync regains git diff --name-only (a truncated big diff silently
dropped files from scope). scaffold Step 4's 'nothing to do' row no
longer contradicts the install bullet when @playwright/test is absent."
```

---

### Task 10: 문서·설정 — 스펙 잔재 3곳, plan 근거, CLAUDE.md, .gitignore, DESCRIPTION_CAP 주석

**Files:**
- Modify: `docs/superpowers/specs/2026-07-18-skill-invocation-eval-design.md`, `docs/superpowers/plans/2026-07-18-skill-invocation-eval.md`, `CLAUDE.md`, `.gitignore`, `tests/test_skills.py`(주석 1줄)

- [ ] **Step 1: 설계 문서 §2 — `--max-turns 3` 단락을 6으로 재작성** (84행 부근). 단락 제목과 수치만 6으로; 살아있는 논점(무제한=13턴, 1턴=너무 짧음, 모든 tool_use 스캔)은 유지:

```markdown
**세션은 `--max-turns 6`으로 자른다.** 무제한이면 에이전트가 스킬을 로드한 뒤 실제 작업을
이어가 13턴까지 돌지만, 1턴은 반대로 **너무 짧다** — 빈 디렉터리에서는 에이전트가 `ls`부터
하고 스킬은 그다음에 부른다(2026-07-18 실측). 따라서 러너는 첫 tool_use만 보지 않고
**스트림의 모든 tool_use를 훑는다**. 1턴으로 자르면 발동했을 스킬을 미발동으로 기록하는
거짓 음성이 생기고, 그 오염은 invoke_rate에 그대로 남는다. (예산이 3이 아니라 6인 근거는
위 "턴 예산은 3이 아니라 6이다" 단락의 실측이다.)
```

- [ ] **Step 2: 설계 문서 §2 인증 단락(±58행) — 화이트리스트 서술을 배포된 블랙리스트로**:

`result.subtype == "success"`이면서 `is_error`인 세션(…)을 → 다음으로 교체:

```markdown
`is_error`이면서 `subtype`이 `error_max_turns`가 **아닌** 세션(턴 상한만이 is_error를
달고도 정당한 관측이다 — subtype 화이트리스트는 `error_during_execution`을 조용한 미발동으로
집계했다)을
```

- [ ] **Step 3: 설계 문서 §7 — 창 초과 주장·낡은 표 수정**:

표(±488행): `| 보정(전량, 반복 3) | 245 | **~15분** |` → `**~30분**`, `| 전량, 반복 5 | 385 | ~24분 |` → `~46분`, 그 위 문장 "8 동시 + 30초 타임아웃이면 30초마다 8세션이 끝난다" → "8 동시에서 세션 평균 58초 — 처리량은 약 8세션/분이 아니라 8세션/58초다". "15분이면 5시간 창을…" → "30분이면 5시간 창을…".

"**전량 실행은 5시간 창을 반드시 넘긴다.**" 단락(±502행) 도입부 교체:

```markdown
**전량 실행(~30분)은 창 안에 들지만, 러너는 중단을 전제로 짠다** — 창의 잔여량은 실행
시점마다 다르고, 한도는 도중에 닿을 수 있다. 그래서 `run.py`는 두 가지를 지켜야 한다:
```

같은 단락 끝 "8시간짜리 재측정을 요구하는 설계는…" → "중단된 실행을 처음부터 다시 요구하는 설계는…".

- [ ] **Step 4: 설계 문서 §5 스키마 예시에 실제 필드 반영** — 예시 JSON의 integration 항목에 `"model": "a1b2c3…"` 자리 대신 실제 키 4종 추가 (`"model": "claude-opus-4-8"`, `"restricted": 0.2,` `"truncated_quiet": 0.0,` `"lost_to": {}`) + §4 표에 한 행:

```markdown
| `lost_to` | 해피 미스 | 미스가 대신 부른 이웃 스킬 카운트 — 무엇에 지는지 | 기록만 |
```

- [ ] **Step 5: plan(2026-07-18) 29행 — reps 근거 교체**:

"what keeps the default at 3 now is that the committed baseline was measured at 15 samples, so raising reps without re-measuring every skill would ratchet a 25-sample rate against a 15-sample one" → 교체:

```markdown
what keeps the default at 3 now is provenance and a predictable budget (the committed
baseline's n) — NOT sample-size safety: the exact-binomial ratchet compares k/n to k/n
and is valid when n_new != n_base, which is exactly why cases.yaml supports a per-skill
`reps:` override (see run.py's --reps comment)
```

- [ ] **Step 6: CLAUDE.md — "the ONLY test that reads skills/" 문구 교정**:

```markdown
            test_skills.py  ← the test of the skill FILES themselves — frontmatter, links,
            section refs, and the case-discovery command extracted from the shipped SKILL.md
            and run against fixture projects. (test_evals.py also reads skills/ — descriptions
            via scores.description_sha for the freshness gate — so a description edit fails
            there, not here.) Everything else here tests scripts/, which is why command-era
            frontmatter went unnoticed for so long.
```

- [ ] **Step 7: .gitignore — vdev 증거 ignore 복원** (커밋 82f6b98이 로컬 `.git/info/exclude`로 옮겼지만, 로컬 exclude는 클론에 전파되지 않아 팀원의 `git add -A`가 세션 증거를 쓸어 담는다):

```
.claude/vway-kit/.vdev/
```

- [ ] **Step 8: DESCRIPTION_CAP 주석 교정** — `tests/test_skills.py:53`:

```python
# Conservative budget for `description` + `when_to_use` in the skill listing — the
# official docs put the listing truncation at 1,536 chars; 1024 leaves headroom rather
# than tracking the platform constant exactly.
DESCRIPTION_CAP = 1024
```

- [ ] **Step 9: 확인** — `uv run pytest -q` 전체 PASS + `uv run ruff check && uv run ruff format --check`.

- [ ] **Step 10: 커밋 (2건 — 타입 분리)**

```bash
git add docs/superpowers/specs/2026-07-18-skill-invocation-eval-design.md docs/superpowers/plans/2026-07-18-skill-invocation-eval.md CLAUDE.md tests/test_skills.py
git commit -m "docs: prune superseded eval spec paragraphs" -m "The spec kept three pre-redesign paragraphs that contradicted itself
and the code: a --max-turns 3 heading two paragraphs after the budget
was measured to 6, a 'full runs necessarily exceed the window' premise
its own table retracts (with the discredited 30s-timeout ~15min figure),
and the errored-session whitelist the shipped blacklist rejects. The
plan's reps rationale contradicted the spec's own retraction. Schema
examples gain the real fields (model/restricted/truncated_quiet/
lost_to); CLAUDE.md stops claiming test_skills.py is the only reader of
skills/; the DESCRIPTION_CAP comment stops presenting 1024 as the
platform's truncation value."
git add .gitignore
git commit -m "chore: restore vway-kit evidence ignore line" -m "82f6b98 moved it to .git/info/exclude, which does not propagate to
other clones — a teammate's git add -A would commit session gate
evidence. The tracked ignore is the team-wide protection."
```

---

### Task 11: 전체 검증 + 게이트 증거

- [ ] **Step 1**: `uv run pytest -q` → 전체 PASS (기준: 기존 570 + 신규 ~10).
- [ ] **Step 2**: `uv run ruff check && uv run ruff format --check` → 무출력 PASS.
- [ ] **Step 3**: `uv run python -m evals.run --dry-run --all` → "7 skill(s), 245 sessions, …" (플래그·경로 회귀 없음, 모델 상수 이동 후에도 dry-run 경로 정상).
- [ ] **Step 4**: 도메인 리뷰 — 독립 general-purpose 에이전트에 diff 전체를 주어 회귀·크로스파일 계약(추출기↔스킬 3파일 일치, scores↔tests 시그니처, cases.yaml 스키마) 검토 → 통과 시 `touch .claude/vway-kit/.vdev/review.done`.
- [ ] **Step 5**: vway-kit doc-sync 스킬 호출(문서 세트 정합) → 통과 시 `touch .claude/vway-kit/.vdev/doc-sync.done`.

## Self-Review

**Spec coverage** (리뷰 발견 → Task): 패널 1(모델)→T1·T2·T4, 2(warn-set)→T5, 3(케이스↔픽스처)→T6, 4(rate limit)→T3, 5(find)→T7, 6(env)→T4, 7(npx)→T8, 8(pipe hang)→T4, 9(false_fire/KeyError)→T1, 10(check 순서)→T1, 11(web verdict)→T9, 12(MUST_STILL_PROMPT/issued)→T8, 13(touch 글롭)→T8, 14(스펙 잔재)→T10, 15(복구 안내)→T4. 경미: plan 29행→T10, credentials 안내→T4, CLAUDE.md→T10, scaffold-baseurl-unknown→T6, doc-sync --name-only→T9, lost_to/model backfill→T2·T10, frontmatter SSOT→T1(파싱 헬퍼; 테스트 2파일의 자체 복사본 교체는 T1 Step 4에서 pytest가 강제하는 범위만 — 남는 복사본은 harness_scaffold(의도·문서화)와 test_skills.py의 assert형 frontmatter(메시지 계약이 달라 유지, T1 헬퍼의 독스트링에 명시), --list/--json/--reps/skill:null→T6·T4·T3. **Gap 없음** (의도적 제외는 Global Constraints에 명시).

**Placeholder scan**: Task 4 Step 1의 잘못된 예시 스텁(`test_reps_must_be_positive`) 제거 — 아래 `test_reps_zero_is_rejected`가 실체다. 구현자는 전자를 만들지 말 것. 그 외 모든 코드 블록은 실행 가능한 실제 내용.

**Type consistency**: `scores.MODEL: str`·`parse_frontmatter(Path)->dict`·`session_env(Path)->dict[str,str]`·`check(name, entry, sha, expect, n_skills)`(불변)·`gate(name, entry, sha, expect, n_skills)`(기존과 동일) — Task 간 시그니처 일치 확인 완료.
