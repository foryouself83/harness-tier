# evals 계측 정직성 3건 구현 계획

> **Status:** 완료(2026-07-20). 체크박스는 실행 기록이다.
> 설계 SSOT는 **기존** [`2026-07-18-skill-invocation-eval-design.md`](../specs/2026-07-18-skill-invocation-eval-design.md)
> 를 갱신했다 — 새 spec을 만들면 "`truncated`란 무엇인가"가 두 문서로 갈라진다.

**Goal:** evals가 재는 값이 자기가 잰다고 말하는 것과 일치하게 만든다. 세 건 모두 "숫자가
틀렸다"가 아니라 **"숫자의 의미가 주장과 다르다"**는 문제다.

**Architecture:** 계측 로직은 `evals/run.py`, 선언은 `evals/cases.yaml`, 검증은
`tests/test_evals.py`(모델 없이 도는 절반). 게이트 예측자(`scores.py`)는 건드리지 않는다 —
세 지표 모두 diagnostic이라 `gate()`가 읽지 않는다.

**Tech Stack:** Python 3.12 (PyYAML · re) · pytest

## Global Constraints

- **evals/ 는 소비자에게 가지 않는다** → 커밋 타입은 `fix`가 아니라 `test`/`chore`
  (`agents/`·`skills/`·`hooks/`만 ship). 불필요한 버전 범프를 만들지 않는다.
- **게이트 판정은 불변** — `invoke_rate`·`false_fire`·래칫 산식에 손대지 않는다. 이번 변경은
  진단 지표와 선언 필드에 국한된다.
- **기존 측정값(`scores.json`)은 재계산하지 않는다** — 분자 카운트가 저장돼 있지 않아 비율에서
  역산하면 반올림 오차가 남는다. diagnostic이라 게이트를 오판시키지 않고 다음 측정에서 갱신된다.
- **Bash 도구에서 PowerShell here-string(`@'...'@`) 금지** — heredoc 사용.

---

### Task 1: A1 — `truncated` 분모를 미스로 (TDD)

**Files:** Modify: `tests/test_evals.py` · `evals/run.py`

- [x] **Step 1: RED** — `test_truncated_is_a_share_of_the_misses_not_of_every_sample` 추가.
      해피 4건 중 2 발동 · 2 미스(둘 다 잘림) → 기대 1.00, 실제 0.50으로 실패.
- [x] **Step 2: 0 분모 가드 테스트** — `test_truncated_reports_zero_when_there_was_nothing_to_miss`.
      구현 전에는 통과하지만 구현 후 `ZeroDivisionError`를 잡는 회귀 방지다.
- [x] **Step 3: GREEN** — 분모를 `misses`/`quiet`로. 주석과 경고 문구도 함께 정정
      (`"of happy samples"` → `"of happy misses"` — 문구가 분모를 잘못 말하고 있었다).
- [x] **Step 4: 기존 테스트 재계산** — `test_the_narrowed_rule_lowers_truncated_below_the_old_constant`
      의 기대값 0.3 → 0.38(3/8). 이 테스트의 **주장**(좁힌 규칙이 값을 낮춘다)은 그대로 성립하고
      산식만 바뀌므로, 옛 0.80이 옛 분모의 수치였음을 docstring에 남긴다.

### Task 2: A3 — turn-cap 갈래가 공집합임을 고정

**Files:** Modify: `evals/run.py` · `tests/test_evals.py`

RED-GREEN이 **아니다**. 동작을 바꾸는 게 아니라, 주석에만 있던 주장을 검사되는 사실로 만든다.

- [x] **Step 1: 불변조건 테스트** — `test_a_spent_turn_cap_cannot_be_ambiguous_at_this_budget`:
      `MAX_TURNS > FIRE_BY_TOOL_CALL`을 고정하고, 예산 바닥에서 턴을 소진한 세션이 모호하지
      않음을 직접 확인한다. 두 상수가 교차하면 실패한다.
- [x] **Step 2: 갈래는 유지** — 옳은 것은 규칙("판단하기 전에 멈췄는가")이지 산술이 아니다.
      `MAX_TURNS`를 2로 낮추면 갈래는 살아난다.
- [x] **Step 3: 시나리오 표 주석 정정** — (c)·(d)가 러너가 만들 수 없는 **합성 상태**임을 명시.
      기존 주석은 그 갈래가 발화하는 것처럼 읽혔다.

### Task 3: A2 — 훅 캐비앳을 필드로 (TDD)

**Files:** Modify: `tests/test_evals.py` · `evals/cases.yaml`

- [x] **Step 1: RED** — `test_every_skill_the_injected_rule_names_declares_hook_assisted`:
      `rules/risk-tiers.md`의 `/이름` 집합과 `cases.yaml`의 `hook_assisted` 선언을 **양방향**
      대조. `doc-sync`가 미선언이라 실패.
- [x] **Step 2: GREEN** — `flow`·`doc-sync`에 `hook_assisted: true` + 각 항목에 훅이 무엇을
      해주는지 서술. `flow`의 "the one skill measured with outside help" 문장은 거짓이므로 제거.
- [x] **Step 3: 주석 → 필드 전환의 근거를 주석에 남김** — 손으로 세어 적은 문장이 틀렸던 것이
      이 필드가 존재하는 이유다.

### Task 4: 설계 문서 갱신

**Files:** Modify: `docs/superpowers/specs/2026-07-18-skill-invocation-eval-design.md`

- [x] **Step 1: §4 지표표** — `truncated`/`truncated_quiet` 정의에 분모 명시 + 정정 문단
      (왜 전체 분모가 임계값의 의미를 스킬마다 다르게 만들었는지).
- [x] **Step 2: §2 신규 절 — 격리가 제거하지 못하는 것** — 플러그인 자신의 SessionStart 훅.
      **이 설계가 원래 빠뜨렸던 변수다**: 격리를 상세히 다루면서 우리 훅을 세지 않았고, 그래서
      캐비앳이 cases.yaml 주석에만 (그것도 틀린 채로) 존재했다.
- [x] **Step 3: §2 turn 예산 절** — `cut_early`의 공집합 갈래를 기록.
- [x] **Step 4: 실측표 각주 + cases.yaml 필드 목록** — 6턴 실측표의 `truncated`가 옛 분모
      기준임을 명시하고 미스 분모로 환산(3턴 1.00 · 6턴 0.25). 결론은 불변.

### Task 5: 도메인 리뷰 → FAIL 수용

리뷰가 검증 가능한 주장 셋을 반증했다. **런타임 결함은 0건이었고 전부 "주장"의 결함**이라는
점이 이 브랜치의 논지를 그대로 되돌려 받은 셈이다.

- [x] **#1 spec 각주가 A3를 반증** — 실측표의 옛 `truncated`는 분모뿐 아니라 **분자 정의도**
      달랐다(당시 분자 = "턴 상한에 걸린 표본", `.superpowers/sdd/progress.md:173`). 분모만
      환산해 "3턴 1.00"이라 적었는데, 오늘 규칙으로는 캡 세션이 이미 3콜을 넘겨 **0.00**이다.
      같은 문서의 turn 예산 절과 정면 모순이었다 → 각주를 "오늘 값과 비교 금지"로 교체.
- [x] **#2 교차검사가 주입 텍스트의 절반만 읽음** — `inject-risk-tiers.sh`가 규칙 파일 앞에
      붙이는 서문에 `/flow`가 4회 있고 도움의 가장 강한 형태가 거기다. 규칙 파일만 스캔하면
      (a) 규칙을 산문화했을 때 "도움이 사라졌다"는 **거짓 메시지**를 내고, (b) 서문에 스킬을
      추가하면 조용히 놓친다 → `_injected_session_text()`가 훅+규칙을 함께 읽는다.
- [x] **#3 "five times" → 실제 6회** — 손으로 센 문장을 금지하는 주석에서 같은 실수를 했다.
      숫자를 정정하는 대신 **삭제**했다(테스트가 센다).
- [x] **#4 경고가 상단에서 무조건 발화** — 분모를 미스로 바꾸면서 경고까지 바꾼 것이 실수.
      기록값과 경고는 다른 질문이다: "미스 중 미설명 비율"(미스 분모) vs "재측정할 만큼
      왜곡됐나"(전체 분모). 14/15에서 미스 1건이 타임아웃이면 새 경고는 100%로 울리지만 실제
      왜곡은 0.067이다 → 경고만 전체 분모로 되돌리고 회귀 테스트 추가.
- [x] **#5 A3 테스트가 동어반복** — `not cut_early(turns_exhausted, tool_calls=3)`은 `3 < 3`의
      재진술이라 turn 회계에 대해 아무것도 검사하지 않았다. 게다가 하중 보조정리("턴 T번이면
      T콜 이상")가 **레포 픽스처에서 반증**된다(`stream-quiet`: 4턴 3콜) → 실제 캡처에 대해
      `tool_calls >= num_turns - 1`을 단언하고, 세 곳의 근거 문장을 그 관계로 정정.
- [x] **#6 정규식 오탐** — `/([a-z-]+)`가 `and/or`·`lint/static/...`·`integration/staging/...`
      에서 37개 토큰을 잡았다. 오늘 무해한 것은 우연이고, 브랜치 역할 목록의 어순만 바꿔도
      `integration` 스킬에 거짓 캐비앳이 강제된다 → 매칭을 **측정 대상 스킬 이름으로 제한**.
- [x] **#7** 중복 단언 제거 · **#8** baseline 스케일 혼재를 spec에 기록.

### Task 6: 2차 리뷰 → 다시 FAIL

1차 수정이 **완료 보고를 틀리게 했고**, 수정 하나가 새 결함을 들여왔다.

- [x] **F1 — "고쳤다"가 거짓이었다.** spec의 "5회"가 `5회\n호명한다`로 **줄바꿈**돼 있어
      `grep '5회 호명'`이 놓쳤고, 그 결과 하나만 보고 "both에서 삭제"라고 단언했다. 검증 없는
      완료 보고는 이 브랜치의 주제와 정면 충돌한다 → 숫자 삭제 + 메커니즘 서술도 정정
      (테스트는 이제 훅 서문까지 읽는데 문단은 규칙 파일만 대조한다고 적혀 있었다).
- [x] **F2 — `\b`가 새 오탐을 만들었다.** `\b`는 하이픈 앞에서 성립하므로 `/flow`가
      `/flow-init`·`/flow-uninstall`·`](../flow-tiers.yaml)`에 매칭된다. 마크다운 링크 한 줄만
      남아도 역방향 stale 검출이 **영구 무력화**된다. 옛 정규식에는 없던 퇴행 →
      `(?![\w-])`로 교체 + `test_the_hook_scan_does_not_match_a_longer_name_or_a_path`로 고정.
- [x] **F4 — 코드만 고치고 spec은 안 따라왔다.** `num_turns - 1` 경계가 run.py·테스트에는
      들어갔는데 spec의 turn 예산 문단은 옛 논거 그대로였다. 모순이 제거된 게 아니라
      (문서 ↔ 문서)에서 (문서 ↔ 코드)로 **이동**했다 → 두 고리로 재서술.
- [x] **F5 — 과대주장을 과대주장으로 바꿨다.** 각주의 "두 행 모두 0.00"이 교정 이전 논거를
      쓴다. 교정된 경계로는 3턴이 보장하는 것은 **최소 2회**뿐이라 `tool_calls < 3`이 가능하고,
      당시 기록에 `tool_calls`가 없어 **재계산 자체가 불가능**하다 → "6턴 행만 0.00, 3턴 행은
      재계산 불가"로 정정.
- [x] **F3** 픽스처 캡처 시점 예산을 주석에 기록(그 전에는 증거인지 반례인지 구분 불가).
- [x] **F6** `hooks.json`의 SessionStart 등록을 확인 — 등록이 사라지면 `""`를 반환해 역방향
      검사가 "도움이 사라졌다"고 **보고하게** 한다(숨기지 않는다).
- [x] **F7** 경고 임계값 `> 0.20` → `>= 0.20`. 3/15가 정확히 0.20인데 래칫은 13/15에서
      트립하므로, 배타적 경계는 "절단 아티팩트만으로 게이트가 실패하는데 설명이 없는" 구간을
      남긴다.
- [x] **F9** 테스트 견고성 — `json.loads` 중복 호출, 빈 제너레이터 `max`, 잘린 마지막 줄.
- [x] **F8** CLAUDE.md는 **별도 커밋으로 분리**(아래).

### Task 7: 최종 검증

- [x] `uv run pytest -q` → **680 passed**
- [x] `uv run ruff check` → All checks passed
- [x] 게이트 예측자 무변경 확인 — `scores.py`에 `truncated` 참조 0건
