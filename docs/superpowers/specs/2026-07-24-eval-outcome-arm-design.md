# eval outcome arm 설계 (③-b 통합, v1)

> eval 하네스에 invocation과 **분리된 outcome(수행 결과) arm**을 정식 편입한다.
> 스킬이 golden fixture에서 실제로 실행되어 올바른 종단 상태(end-state)를 만들었는지를
> 결정적으로 채점하는 레이어. 선행 프로브
> [2026-07-24-router-outcome-probe-design.md](2026-07-24-router-outcome-probe-design.md)의
> ③-b 실측(스파이크)을 기반으로 한다.

## 배경 / 목적

- 현재 eval(`evals/`)은 **invocation만** 측정한다: `stream.observe`가 세션 스트림에서
  `fired`(어떤 Skill이 호출됐나)만 관측하고, `run.py`가 recall·false_fire·ratchet을 채점한다.
- 부재한 것 = **outcome**: 스킬이 발화한 *뒤* 실제로 옳게 수행했는가.
- ③-b 스파이크(2026-07-24)가 다음을 실측 증명했다(재론 불필요):
  - 격리 세션에서 스킬이 실행 못 하던 원인은 플러그인 등록이 아니라 `-p` 세션의
    파일시스템 샌드박스였다.
  - **검증된 레시피** = isolated creds-only config + `--plugin-dir <REPO>` +
    `--permission-mode bypassPermissions` + `--add-dir <REPO>` + `--max-turns 25` +
    종단 파일 assert. 이 조합으로 doc-sync가 로드·실행되어 README 8080→9090,
    docs/api 3000→9090을 실제로 디스크에 반영(turns 미소진, 자연 종료).
  - **채점 = golden-fixture END-STATE assertion**(SWE-bench류): `grep 9090` /
    `8080·3000 부재`로 결정적. LLM-judge 불필요.

## 스코프 (v1 — YAGNI)

- **첫 outcome 대상은 doc-sync 하나.** fixture는 기존 `doc-sync-drift`(scripts/skill_sandbox.py) 재사용.
- 라우터 tier-marker outcome(원래 ③ 목표: flow의 `.flow/tier` == golden_tier)은 **v1 범위 밖 — 후속.**
- 미배포 eval 계측 → 커밋은 `test:`/`chore:`.

## 무손상 불변식 (반드시 지킬 것)

- scored invocation arm — `run.py`의 `measure`/`_one`/`cases_for`, `stream.py`의 현 `Observation`,
  `scores.json`, `scores.py`의 invocation 게이트, `test_evals.py`의 현 게이트 — **동작 무변경.**
- outcome은 **별도 arm**(별도 모듈·별도 베이스라인 파일·신규 테스트).
- `_claude_stream` 확장은 기본값이 현 커맨드를 **바이트 동일** 재현 → 유일 호출자
  `run_session`은 새 인자를 넘기지 않으므로 외부 동작 불변.
- `bypassPermissions` 세션의 쓰기 경계는 **cwd(던져버릴 임시 fixture) + fixture-scoped
  프롬프트**다. 검증된 레시피가 요구하는 `--add-dir <REPO>`는 플러그인 로드를 위해 REPO도
  쓰기 가능하게 만들지만(`--add-dir`는 read-only 변형이 없음), cwd와 프롬프트가 편집을
  fixture 안에 묶는다 — 스파이크 ③-b와 시딩 런 전부 클린. 레시피는 불변이므로 REPO 쓰기
  가능성은 **잔여 리스크로 기록**한다(엄밀 봉쇄가 필요해지면 필요한 플러그인 파일을 fixture로
  복사).

## 아키텍처 — 두 arm의 완전 분리

| | invocation arm (기존·무손상) | outcome arm (신규) |
|---|---|---|
| 측정 | 스킬이 *발화*하는가 (`fired`) | 스킬이 *올바른 end-state*를 만드는가 |
| 러너 | `run.measure` / `_one` / `cases_for` | `evals/outcome.py` |
| 세션 | 기본 권한, `MAX_TURNS`=6 | `bypassPermissions` + `--add-dir` + `--max-turns 25` |
| 채점 | `stream.observe` → 이진분포 ratchet | golden **END-STATE assertion** |
| 데이터 | `cases.yaml` | `Scenario.outcome` 필드 |
| 베이스라인 | `scores.json` | `evals/outcome_scores.json` |
| freshness | `description_sha` + `model` | `outcome_sha`(SKILL.md+prompt+fixture+golden) + `model` |

공유 프리미티브만 재사용: `_claude_stream`·`isolated_config_dir`·`session_env`(run.py),
`build`·`Scenario`·`BY_NAME`(skill_sandbox), `observe`·`Observation`(stream), `MODEL`·`Verdict`(scores).

### 비대칭의 근거 (Q3의 "별도 지문")

invocation과 outcome은 무엇이 결과를 **결정하는지**가 다르다. invocation은 *description*이
결정 → `description_sha`. outcome은 *스킬 본문 실행*이 결정 → `outcome_sha`가 본문·prompt·fixture·golden을
덮어야 한다. `description_sha`는 fixture/golden을 안 덮으므로 재사용 불가.

## 컴포넌트

### 1. `scripts/skill_sandbox.py` — golden과 채점기를 fixture 옆에 병치

- `Scenario`에 선택적 필드 추가 (`files`와 대칭, 기본 빈값):
  ```python
  outcome: dict[str, dict[str, list[str]]] = field(default_factory=dict)
  # { "<relpath>": {"must_contain": [...], "must_not_contain": [...]} }
  ```
- `doc-sync-drift`만 채운다:
  ```python
  outcome={
      "README.md":     {"must_contain": ["9090"], "must_not_contain": ["8080"]},
      "docs/api.md":   {"must_contain": ["9090"], "must_not_contain": ["3000"]},
      "app/server.py": {"must_contain": ["9090"]},  # 코드 재작성 금지(scenario.reject와 정합)
  }
  ```
  `app/server.py`가 9090을 유지하는지 검사하는 것은 이 시나리오의 `reject`("edits
  app/server.py to match the docs")를 기계적으로 지키는 역할이다.
- `check_outcome(scenario, built: Path) -> tuple[bool, list[str]]`:
  각 `(relpath, spec)`에 대해 `(built/relpath).read_text` — 누락 파일은 실패로 집계.
  모든 `must_contain` 부분문자열 존재 + 모든 `must_not_contain` 부재를 검사. `(모두 통과?, 실패목록)` 반환.
- 산문 `expect`/`reject`는 **손대지 않는다**(사람-판정 invocation sandbox용, 다른 소비자).

### 2. `evals/run.py` — `_claude_stream`만 키워드 확장 (그 외 무변경)

```python
def _claude_stream(prompt, fixture, workdir, config_dir, restricted=False, *,
                   permission_mode=None, add_dirs=(), max_turns=MAX_TURNS,
                   timeout=SESSION_TIMEOUT) -> tuple[str, str]:
```

- `--max-turns str(max_turns)`; `restricted` 블록 뒤에
  `if permission_mode: cmd += ["--permission-mode", permission_mode]`,
  `for d in add_dirs: cmd += ["--add-dir", str(d)]`.
- `proc.communicate(timeout=timeout)`과 `TimeoutExpired` 경로 모두 `timeout` 파라미터 사용.
- 키워드 전용 + 현행 재현 기본값 → `run_session`(유일 기존 호출자)은 새 인자 미전달 → 커맨드 라인 바이트 동일.
- 별도 러너 신설은 subprocess+timeout+decode 로직 중복(③-a의 추출 근거 위반)이라 기각.

### 3. `evals/outcome.py` — outcome arm + CLI (신규, 독립 실행)

- 상수: `OUTCOME_MAX_TURNS = 25`, `OUTCOME_TIMEOUT = 300`(편집+flow→doc-sync 체이닝이
  `SESSION_TIMEOUT`=180 초과 가능), `REPS = 3`, `OUTCOME_SCORES = REPO / "evals/outcome_scores.json"`.
- 대상: `sandbox.SCENARIOS` 중 `outcome`이 비어있지 않은 시나리오(v1=`doc-sync-drift`).
  프롬프트는 `scenario.prompt`("The port changed. Sync the documentation."). cases.yaml과 무관.
- `run_outcome(scenario, skill, reps, config_dir) -> dict`: rep마다
  1. `TemporaryDirectory` → `built = sandbox.build(scenario, tmp)`(경로 확보를 위해 outcome arm이 직접 build)
  2. `text, err = run._claude_stream(scenario.prompt, None, built, config_dir,
     permission_mode="bypassPermissions", add_dirs=(run.REPO,),
     max_turns=OUTCOME_MAX_TURNS, timeout=OUTCOME_TIMEOUT)`
  3. `obs = stream.observe(text)` — `errored`/init 미도달 → SystemExit(조작된 0 금지),
     `rate_limited` → 부분 저장 후 중단(run.py 규율 미러). `skill in obs.fired`는 **fired 진단**으로 기록.
  4. `passed, failures = sandbox.check_outcome(scenario, built)`
- `outcome_sha(skill, scenario) -> str`: `sha256(SKILL.md 전문 +
  json.dumps(scenario.files, sort_keys=True) + json.dumps(scenario.outcome, sort_keys=True))[:12]`.
- `outcome_check(entry, sha) -> scores.Verdict`(순수·model-free):
  - `entry is None` → `warn`("not measured yet — run python -m evals.outcome")
  - 필수 키 누락 → `fail`
  - `entry["outcome_sha"] != sha` → `fail`("re-measure")
  - `entry["model"] != scores.MODEL` → `fail`
  - `entry["outcome_hits"] == 0` → `fail`(비영 플로어 — 전부 실패 베이스라인은 절대 green 금지)
  - else → `ok`

  `scores.Verdict`·`scores.MODEL` 재사용, `scores.py`는 **무수정**.
- 집계 엔트리: `outcome_hits, outcome_n(=reps), outcome_pass_rate, fired_hits, fired_rate(진단),
  model, measured_at, reps, outcome_sha`.
- CLI: `python -m evals.outcome [--reps 3] [--dry-run]`. `isolated_config_dir()` 재사용.
  결과를 `OUTCOME_SCORES`에 skill 키로 정렬 JSON 기록.

### 4. `evals/outcome_scores.json` — 신규 커밋 베이스라인

1회 라이브 `python -m evals.outcome` 실측으로 시드해 커밋. rate-limit/예산으로 미시드 시
게이트는 `warn`(레드 아님)이라 코드가 먼저 랜딩하고 예산 확보 시 시드 가능 — invocation의
"미측정=warn"과 동일. `evals/` 하위라 `test_the_eval_harness_is_never_distributed_to_consumers`가
미배포를 이미 보장.

### 5. `tests/test_evals.py` — 신규 테스트만 (기존 무손상)

- `test_doc_sync_declares_a_machine_checkable_outcome` — doc-sync-drift에 `outcome` 존재.
- `test_check_outcome_passes_the_golden`/`fails_on_stale_port` — `sandbox.build`로 tmp에
  올바른/오염된 end-state를 만들어 `check_outcome` 판정(세션 없음).
- `test_outcome_sha_is_sensitive_to_body_fixture_and_golden` — 셋 중 하나만 바꿔도 sha 변화.
- `test_outcome_gate_freshness_and_zero_floor` — invocation 게이트 미러: stale sha→fail,
  model 불일치→fail, `outcome_hits==0`→fail, 미측정→warn, 정상→ok.
- 라이브 경로는 기존 `no_real_sessions` autouse(=`run.subprocess` 패치)가 `run._claude_stream`
  경유로 그대로 차단 → outcome arm도 model-free 보장에 포함됨.

## 데이터 플로우

```
python -m evals.outcome
  → isolated_config_dir()                                    [reuse]
  → for scenario in SCENARIOS if scenario.outcome:           (v1: doc-sync-drift)
      for rep in range(reps=3):
        built = sandbox.build(scenario, tmp)                 [reuse]
        text,err = run._claude_stream(prompt, None, built, cfg,
                     permission_mode="bypassPermissions",
                     add_dirs=(run.REPO,), max_turns=25, timeout=300)  [reuse+params]
        obs = stream.observe(text)                           [reuse] → fired 진단
        passed, failures = sandbox.check_outcome(scenario, built)      [new]
      집계 → {outcome_hits, outcome_n, outcome_pass_rate, fired_rate,
              model, measured_at, reps, outcome_sha}
  → evals/outcome_scores.json (skill 키)

uv run pytest (CI, model-free)
  → outcome_scores.json 로드 + outcome_sha(doc-sync) 재계산
  → outcome_check → stale/zero fail · 미측정 warn · fresh+nonzero ok
```

## 판정 규칙

- **passed(rep)** — `check_outcome`이 모든 golden 파일 검사를 통과.
- **outcome_pass_rate** — `outcome_hits / reps`.
- **fired(진단, 비게이트)** — `skill in stream.observe(text).fired`. flow→doc-sync 체이닝처럼
  target이 다른 스킬을 경유해도 end-state로 채점(Q5). fired는 attribution 관측용으로만 기록,
  게이트하지 않음 — 프롬프트를 라우터와 싸우게 만들지 않는다.
- **게이트(v1)** — freshness(`outcome_sha`+`model`) + 비영 플로어. 이진분포 ratchet은
  스킬 1개·reps 3에선 무의미 → 후속.

## 오류 처리 / 예산

- `errored`·init 미도달 → SystemExit(조작된 0 기록 금지), `rate_limited` → 부분 저장 후 중단 — run.py 미러.
- Windows: `_claude_stream`의 taskkill 트리-kill·UTF-8 방어 상속. outcome.py 콘솔 메시지는
  cp949 안전(em-dash 회피), 파일 쓰기 `encoding="utf-8"`.
- `check_outcome`의 누락 golden 파일 → 크래시 아닌 실패로 집계.
- 예산: doc-sync 1 × reps 3 = **3세션 ≈ 3~6분**.

## 문서 (Phase 3 doc-sync 게이트 대상)

- `CLAUDE.md`의 "Skill invocation is measured, not assumed" 불릿 → outcome arm 명시
  (`evals/outcome.py` = 실행되었는가, `outcome_scores.json` 베이스라인).
- `CLAUDE.md` Commands → `uv run python -m evals.outcome` 추가.

## 성공 기준

- `python -m evals.outcome`가 doc-sync를 `doc-sync-drift`에서 실행해 golden end-state를
  결정적으로 채점하고 `outcome_scores.json`을 산출한다.
- 신규 게이트가 model-free로 freshness·비영을 강제하고, 기존 invocation 게이트·`scores.json`·
  `stream.py`·scored 경로는 **전부 그린 유지**.
- `_claude_stream` 확장이 순수 파라미터화(scored 커맨드 바이트 동일)임을 리뷰로 확인.

## 후속 (v1 범위 외)

- 라우터 tier-marker outcome(flow `.flow/tier` == golden_tier) — bypassPermissions로 재개 가능성 관측.
- outcome arm에 이진분포 ratchet(`scores.binom_cdf` 재사용) — 스킬/reps가 늘면 도입.
- 추가 스킬 outcome(integration·playwright-scaffold·performance) — 각 fixture에 `outcome` 필드 채움.
