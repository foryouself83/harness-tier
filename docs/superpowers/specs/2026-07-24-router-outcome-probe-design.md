# 라우터 outcome probe 설계 (③-a)

> eval 하네스에 invocation과 별개의 **outcome(수행 결과)** 측정을 도입하기 위한
> 첫 단계 — 최소 probe. 사용자 합의: **(a) probe 먼저 → (b) 통합 레이어**.

## 배경 / 목적

- 현재 eval(`evals/`)은 **invocation만** 측정한다: `stream.py`의 `observe()`가
  세션 스트림에서 `fired`(어떤 Skill이 호출됐나)만 관측하고, `run.py`가
  recall·false_fire·ratchet을 채점한다.
- 부재한 것 = **outcome**: 스킬이 발화한 *뒤* 실제로 옳게 수행했는가. 라우터(`flow`)의
  경우 = 분류한 tier가 옳은가.
- ②(커밋 `2485aa8`)에서 `flow`의 happy 프롬프트에 `golden_tier` 라벨을 부착했다
  (dev×3, staging×1; "Commit these changes"는 diff 미지정이라 결정적 golden 없어
  **의도적 미라벨**).
- ③-a = 이 라벨을 소비해 "flow가 분류한 tier == golden_tier"를 **결정적으로 캡처할 수
  있는지** 실증하는 probe. 통합(b) 착수 전에 불확실성을 먼저 소진한다.

## 스코프

- 본 스펙 = **(a) probe만**. flow의 `golden_tier` 라벨 4개 프롬프트 대상.
- (b) 통합(신규 지표·게이트·freshness)은 **별도 스펙/사이클**. 본 문서 말미에 방향만 기록.
- 미배포 eval 계측 → 커밋은 `test:`/`chore:`.

## 접근: A2 — 독립 probe + `run.py` 최소 추출

핵심 제약: `- Tier: X`는 assistant **텍스트** 블록에 있는데 `observe()`는 텍스트를
버리고, `run_session`은 `(obs, err)`만 반환할 뿐 **원시 스트림 텍스트를 안 준다**
([run.py:426](../../../evals/run.py)). 따라서 스트림 파싱을 하려면 원시 텍스트 접근이
필요하다. reuse 사다리상 subprocess 로직 재구현은 금지 → **공유 헬퍼로 추출**한다.

## 컴포넌트

### 1. `run.py` 추출 — `_claude_stream`

- 현재 `run_session`(362-420)이 cmd 구성 · `subprocess` · timeout 트리-kill · decode를
  인라인으로 수행.
- 이를 `_claude_stream(prompt, fixture, workdir, config_dir, restricted) -> (text, err)`
  로 **추출**한다.
- `run_session`은 그 헬퍼를 호출하도록 바뀐다:
  `text, err = _claude_stream(...); obs = stream.observe(text); maybe_capture(obs, text);
  return obs, err` — **외부 동작 동일**(순수 이동).
- 목적: probe가 `_claude_stream`으로 원시 텍스트 + 자체 workdir을 얻는다.

### 2. `evals/outcome_probe.py` (신규, 독립 실행)

- `cases.yaml`의 `flow.happy`에서 `golden_tier`가 있는 케이스만 추출.
- 각 케이스를 **자체 workdir**로 `_claude_stream` 실행 (기본 `reps=3` → 4×3 = 12세션 ≈ 2분).
- **두 캡처 방식을 동시에** 시도:
  1. **스트림 파싱** — 스트림 JSON에서 assistant 텍스트 블록을 모아
     `(?im)^-\s*Tier:\s*(\w+)`로 매칭 → 소문자화. 여러 개면 **마지막**(최종 분류)을 채택.
     이 출력은 Phase 1에 나오므로 `AskUserQuestion`(Phase 2) **이전**이다.
  2. **파일 마커** — 세션 후 `<workdir>/.claude/harness-tier/.flow/tier`를 읽어
     `<tier>:<branch>`의 tier 부분. Phase 2(대화형 확정+브랜치 전환)를 **통과해야** 기록됨.
     (전제: `flow`의 `fixture`는 `null`이라 `_claude_stream` 안에서 `sandbox.build`이
     workdir을 바꾸지 않는다 → probe가 넘긴 workdir이 그대로 세션 CWD가 되어 마커 경로가
     그 아래에 놓인다. 본 probe는 flow만 다루므로 이 전제가 성립한다.)
- 채점 경로(`run.py`의 scored arm)·`scores.py`·`stream.py`·`test_evals.py`는 **import도
  변경도 하지 않는다**.

## 판정 규칙

- **fired** — `stream.observe(text).fired`에 `"flow"`가 있으면 발화. 미발화면 outcome 판정
  불가(N/A로 표기).
- **captured(방식별)** — 그 방식이 tier 문자열을 1개 이상 복원했는가.
- **match** — `captured.lower() == golden_tier`.
- 세션별 행: `프롬프트 | golden | fired? | 스트림-tier | 파일-tier | match?`.
- 요약: 방식별 **캡처율**(복원/발화), **일치율**(match/발화), reps 분포.

## 무손상 보장 (invariants)

- `scores.json` · `test_evals.py` · `stream.py` **무변경**.
- `run_session` 외부 동작 동일 — 순수 추출. 재검증: `test_evals` 그린 유지 확인 + 추출이
  코드 이동임을 리뷰로 확인(세션 예산 없이).
- probe는 `run.py`를 import하지만 scored arm 함수(`measure`/`_one`/`cases_for`)는 건드리지
  않는다.

## 성공 기준 (probe로서)

- probe가 방식별 **캡처율·일치율 데이터를 산출**한다(음성 결과도 유효한 발견).
- **최소 한 방식이 headless에서 tier를 결정적으로 복원**한다(기대: 스트림 파싱).
- 이 데이터로 (b)가 채택할 캡처 방식이 확정된다.

## 리스크 / 열린 질문

- **`AskUserQuestion` headless 동작** — stdin=DEVNULL 세션에서 막힐 공산이 커 파일 마커가
  자주 미기록될 것으로 추정. probe가 실증한다(음성이면 스트림 파싱으로 확정).
- **비-git workdir** — probe workdir은 git 저장소가 아니므로 /flow Phase 2b 브랜치 전환이
  실패할 수 있고, 이는 파일 마커 미기록의 또 다른 사유. 관측 대상.
- **flow는 hook_assisted** — 단 여기서 재는 것은 invocation이 아니라 **분류값(outcome)**
  이라 훅 교란과 무관.
- **스트림 파싱은 출력 형식(`- Tier: X`)에 결합** — 형식은 SSOT(`flow/SKILL.md`·
  `risk-tiers.md`)라 안정적이나, (b)에서 형식 변경 시 재검토 필요.

## (b) 후속 방향 (본 스펙 범위 외, 참고)

- probe가 증명한 캡처를 `stream.py`의 `observe()`에 편입(`classified_tier`).
- `scores.json`에 `outcome_pass_rate` 등 신규 지표 + `test_evals` 게이트·freshness 편입.
- reps 기반 variance 처리·exact-binomial 재사용 여부 검토.

## ③-a 실측 결과 (2026-07-24)

probe 실행(flow 4 golden × reps=3 = 12세션) + raw-stream 진단(1세션):

- `fired 9/12` — flow는 발화(Skill 호출)했으나 **스킬 본문이 로드 실패**
  ("The /flow skill failed to load" / "Execute skill: harness-tier:flow 오류"). Phase 1
  분류(`- Tier: X`)가 아예 생성 안 됨(raw `- Tier` count 0, `turns_exhausted` False →
  turn-cap 아님).
- **스트림 캡처 0/9, 마커 캡처 0/9** — probe·파서는 정확(음성은 실제 음성).
- **구조적 결론**: 현재 하네스(`--plugin-dir` + isolated config dir)는 스킬 **발화는
  관측하나 실행은 못 한다**. invocation eval이 성립하는 이유(Skill 툴 호출은 스킬 본문
  로드 *전에* 일어남)의 동전 양면 — 그래서 outcome을 이 하네스에 얹는 (b)의 전제는 성립
  불가.
- **(b) 선행 과제**: 스킬이 격리 세션에서 실행 실패하는 원인 규명(플러그인 install vs
  `--plugin-dir`, 접근 허용 경로). 해결 전엔 outcome-eval 통합 착수 불가. `_claude_stream`
  추출·`outcome_probe.py`는 그 조사가 끝나면 재사용 가능.
