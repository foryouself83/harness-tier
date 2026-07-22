# stream 픽스처 재캡처 준비 구현 계획

> **Status:** 완료(2026-07-21). 회수까지 끝남 — 마지막 Task 참조.

**Goal:** 커밋된 stream 픽스처가 담고 있는 캡처 머신 인벤토리를 없앤다. 편집으로는 불가능하고
(캡처가 아니라 창작이 된다) 재캡처만이 해법인데, 재캡처 전용 세션을 태우는 것은 낭비다 —
정식 측정이 스킬당 35세션을 만들므로 **그 부산물로 회수**한다.

**Architecture:** 순수 함수 둘(`reduce_capture`·`fixture_role`) + 저장 한 곳(`maybe_capture`).
`run_session`이 이미 stdout을 디코드하므로 그 지점에서 호출한다. 플래그는 모듈 전역 —
`run_session`의 시그니처는 모든 테스트가 `_one`을 monkeypatch하는 기준면이라 건드리지 않는다.

**Tech Stack:** Python 3.12 · pytest

## Global Constraints

- **살아남는 이벤트는 바이트 동일** — 픽스처의 가치가 "실제 CLI 바이트"인데 재직렬화하면
  키 순서·공백·이스케이프가 정규화되어 **캡처의 렌더링**이 된다. 줄 단위로 버리기만 한다.
- **덮어쓰지 않는다** — 커밋된 픽스처는 7개 단언을 통과 중이고 `fixture_role`은 그 부분집합만
  검사한다. 후보는 `.jsonl.new`로 쓰고 교체는 사람이 한다.
- **기본은 꺼짐** — 정식 측정이 픽스처를 건드리면 안 된다.
- **evals/ 는 ship되지 않는다** → 커밋 타입 `test:`.

---

### Task 1: 순수 함수 둘 (TDD)

**Files:** Modify: `tests/test_evals.py` · `evals/run.py`

- [x] **Step 1: RED** — 5개 테스트가 `AttributeError`로 실패.
- [x] **Step 2: `reduce_capture`** — `stream.observe`가 읽는 4종만 유지. 바이트 동일성과
      파싱 불가 줄 폐기를 각각 별도 테스트로 고정.
- [x] **Step 3: `fixture_role`** — 거부 조건 셋(`errored` · `available` 빔 · `tool_calls==0`)이
      각각 커밋된 픽스처가 만족하는 단언에 대응한다.
- [x] **Step 4: GREEN**.

### Task 2: 배선 (TDD)

**Files:** Modify: `tests/test_evals.py` · `evals/run.py`

- [x] **Step 1: RED** — `maybe_capture` 부재.
- [x] **Step 2: GREEN** — `.jsonl.new` 기록, first-wins, 기본 꺼짐. 세 성질 모두 테스트.
- [x] **Step 3: `run_session`에서 호출** + `--capture-fixtures` 플래그.

### Task 3: 셀프 리뷰에서 발견한 구멍

- [x] **turn cap이 걸린 미발동 세션이 `stream-quiet`으로 판정됐다.** 두 픽스처의 가치는
      **끝나는 방식이 다르다**는 것인데(하나는 턴캡, 하나는 `success`), 그대로 두면 둘 다
      턴캡이 되어 success 경로 커버리지가 사라진다 → `not turns_exhausted` 추가 + 테스트.

### Task 4: 도메인 리뷰 → FAIL, 6건

리뷰 판정: "기존 것을 깨뜨려서가 아니라, **이 기능이 자기가 새로 추가한 문서대로 호출됐을 때**
쓸 수 없는 픽스처를 만들거나 아무것도 만들지 못하며, 두 실패 모두 무출력이기 때문."

- [x] **F1 (High) — `fixture_role`이 스킬 이름을 검사하지 않았다.** 테스트는
      `"integration" in obs.fired`를 하드코딩하는데 역할 판정은 **어떤 스킬이 발동했든** 수락한다.
      증분 기본 모드는 알파벳순으로 도므로 `doc-sync` 세션이 `stream-invoked`를 차지한다 →
      스위트가 거부하는 픽스처가 만들어진다.
      **그리고 그 위험한 호출을 내가 CLAUDE.md에 새로 적었다** — plan에는 안전한
      `--skill integration`을 쓰고서. 이 세션에서 **세 번째로 반복한 "한 곳만 고침"**이다.
      → `fixture_role(obs, skill)` + `--capture-fixtures`가 `--skill`을 요구 + CLAUDE.md 정정.
- [x] **F2 (High) — `turns_exhausted` 요구가 폐기된 3턴 예산의 부산물.** 커밋된
      `stream-invoked`가 turn cap인 것은 구 예산에서 캡처됐기 때문인데, `MAX_TURNS=6`은 절단을
      **드물게 만들려고** 올린 값이다. 발동 후 정상 종료한 세션은 어느 role에도 안 걸려 버려진다.
      그리고 **미매칭을 보고하지 않아** 절반만 회수한 실행과 성공한 실행이 구분되지 않는다.
      → `report_capture()`가 종료 시 못 잡은 role을 이유와 함께 보고.
- [x] **F3 (Medium) — 남은 `.new`가 조용히 재캡처를 막는다.** rate-limit 중단은 정확히 그 상태를
      남기고, 재개 안내(`--skill {n}`)에는 `--capture-fixtures`가 빠져 있었다 → 조기 return에
      출력 추가 + 재개 안내에 플래그 전달.
- [x] **F4 (Medium) — gitignore되지 않은 `.new`는 `git add -A` 한 번 거리.** 이 저장소가 이미
      같은 문제를 반대로 결론낸 기록이 있다(세션 증거를 `.git/info/exclude`에서 `.gitignore`로
      되돌린 건). 커밋되면 어떤 테스트도 보지 않는 두 번째 사본이 남는다 →
      `test_the_fixtures_directory_holds_exactly_the_committed_pair`가 디렉터리를 glob.
- [x] **F5 (Nit) — 후행 개행이 load-bearing인데 테스트가 `.strip()`으로 지웠다.** 뮤테이션
      (`+ "\n"` 제거)에 92개가 전부 통과했다 → 개행 전용 테스트 추가, **뮤테이션으로 잡히는 것을
      확인**(1 failed).
- [x] **F6 (Nit)** — 전역을 argparse 검증 **뒤**로 이동, `maybe_capture`의 `dest_dir` 기본값을
      def-time 바인딩에서 런타임 해석으로(그 전에는 `FIXTURES_DIR` monkeypatch가 안 먹었다).
- [x] 끊어진 상호참조(`test_observe_counts_every_tool_use` — 존재하지 않는 이름)와 "35 per
      skill" 주석이 전체-스킬 실행을 전제하던 것 정정.

### Task 5: 2차 리뷰 → FAIL(범위 축소), 5건

판정: "산출물이 잘못되는 결함은 남아있지 않다. 그럼에도 FAIL인 이유는 하나 — F2/F3이 새로 만든
**보고 계층이, 정확히 자기가 만들어진 두 상황에서 사실의 반대를 말한다**."

- [x] **NEW-1 — `CAPTURE_FOR`가 `if args.skill:` 분기에서만 대입.** 같은 프로세스에서
      플래그 없는 `--all`이 직전 실행의 캡처 대상을 물려받았다(실증). Global Constraint
      "기본은 꺼짐"의 정면 위반이고, **이 브랜치에서 "한 분기에서만" 계열의 세 번째 반복**이다
      → 분기 앞에서 무조건 대입 + `CAPTURED.clear()`.
- [x] **NEW-2 — rate-limit 경로의 보고가 살아있는 워커와 경합.** `shutdown(wait=False)`는
      시작 안 한 것만 취소하므로 최대 8개가 여전히 `maybe_capture` 안에 있다. 리뷰어가
      "후보 없음" 출력 직후 파일이 생기는 것을 실증 → `provisional=True`로 "확정 아님" 명시.
      같은 실증에서 **check-then-write 경합이 실제로 발동**(한 파일에 "written" 3줄)했다 —
      지난 라운드에 "무해"로 분류했던 것 → `Lock` + 임시 파일 `os.replace`.
- [x] **NEW-3 — "already exists"와 `report_capture`가 같은 실행에서 모순.** 조기 return이
      `CAPTURED.add`를 안 해 파일이 있는데도 "없음"으로 보고했다. 게다가 그 `[i]` 줄이
      매칭 세션마다(35 중 ~25) 출력됐다 → `CAPTURED.add` + role당 1회.
- [x] **NEW-4 — 가장 유력한 실패 경로에 보고가 없었다.** `verdict.level == "fail"` return과
      `measure`의 SystemExit들. 계획서 Task 6이 직접 예고하는 경로다(`integration` 4/15,
      재측정은 re-baseline) → `main()`을 얇은 래퍼로 감싸 `finally`에서 한 번 보고.
- [x] **NEW-5 — 디렉터리 테스트가 과했고 "커밋 불가"는 거짓.** 이 저장소엔 pytest를 도는
      pre-commit이 없어 `.new`는 커밋을 막지 않고 push에서 CI가 잡는다. 그리고 검토 중인
      후보가 스위트를 빨갛게 만들어 **검토 대신 삭제를 유도**한다 → `git ls-files` 기준으로
      좁혀 추적 파일만 검사(후보가 있어도 초록 유지 확인).
- [x] 부수 — `--dry-run`이 캡처 경고를 내던 것(세션을 안 돌리는데) 수정, 테스트 간
      `CAPTURED` 누수를 autouse fixture로 차단.

### Task 6: 3차 리뷰 → PASS-WITH-NITS, 3건 + 구조 권고

- [x] **NEW-6 — `CAPTURE_PROVISIONAL`이 어디서도 리셋되지 않았다.** NEW-1을 고친 **바로 그
      커밋에서 네 번째 전역을 같은 처리 없이 추가**했다. rate-limit된 실행 뒤 정상 완료한
      실행이 자기 집계를 믿지 말라고 말한다. 리뷰어 지적 중 가장 아픈 것: **autouse 테스트
      픽스처가 세 전역을 모두 리셋해 프로덕션(둘)보다 정확했고**, 그래서 스위트가 초록이었다.
- [x] **NEW-7 — 캡처 대입이 `unknown skill` 검증 앞.** `--dry-run`을 고치면서 **네 줄 옆의
      형제 경로**를 놓쳤다. 오타 하나가 세션 0개인 실행에 캡처 리포트를 붙였다.
- [x] **NEW-8 — `with_suffix`가 `stream-quiet.jsonl.jsonl.new.<pid>.tmp`를 만든다.** 원자성은
      유효했지만 이름이 틀렸다 → `with_name`. `pid`도 제거(8워커가 같은 pid — 실제 보호는 락).
- [x] **Q1 nit — `finally` 안의 `print`가 예외를 대체한다.** em dash + cp949 리다이렉트면
      `UnicodeEncodeError`가 실제 종료 코드를 가린다(Invariant #2 계열) → `try/except`로 감쌈.

**구조 권고 수용** — 리뷰어: "네 라운드 연속 같은 계열이 재발했고 이번엔 그 계열을 고치는
커밋 안에서 재발했다. 개별 수정보다 전역 셋을 한 함수로 묶는 봉합이 값이 크다."
→ `_reset_capture_state(skill)` 하나로 세 전역을 항상 함께 설정하고, **테스트 픽스처가 그
함수를 호출**한다(다시 나열하지 않는다). 진입부에서 무조건 무장 해제 + 측정 직전 무장 —
두 호출의 역할이 다르고, 조기 return이 리셋을 건너뛸 자리가 없다.

- [x] 그 과정에서 **내가 새 결함을 만들었다** — 리셋을 dry-run return 뒤로 옮겨 dry-run 경로가
      리셋을 아예 못 받게 됐다. 진입부 무장 해제로 해결, 세 조기 종료 경로 모두 `(None, False)` 확인.

### Task 7: 검증

- [x] `uv run pytest -q` → **692 passed**
- [x] `uv run ruff check` → All checks passed
- [x] doc-sync — CLAUDE.md 명령 블록에 `--capture-fixtures` 한 줄. spec은 무변경(stream
      픽스처는 측정 설계가 아니라 파서 테스트 자산이고, SSOT는 test_evals.py 주석).

### Task 8: 회수 — 측정 1회 실행

**완료(2026-07-21).** 이것만이 rate-limit 예산을 썼다 — 35세션, 약 4분(8 병렬).

- [x] `uv run python -m evals.run --skill integration --capture-fixtures` → `.new` 둘 다 생성
      (`stream-invoked`까지 잡힘 — turn cap이 드물다는 예고에도 불구하고).
- [x] 대조 — 두 `.new` 모두 `init.plugins`가 `harness-tier@inline` 하나만 나열(18→1),
      7개 단언 × 2 픽스처 = **14/14 통과**. 남은 유출은 계정 단위 claude.ai MCP 커넥터
      이름뿐(토큰 없음, `apiKeySource: none`) — 설정 격리가 못 벗기는 부분이라 순감으로 수용.
- [x] 교체 후 `uv run pytest -q` → **692 passed**. 픽스처 주석 두 곳("deliberately not
      spent", "captured BEFORE MAX_TURNS became 6 … num_turns 4")을 새 사실(num_turns 7/9,
      지출 완료)에 맞게 수정.
- [x] 재측정이 `invoke_rate`를 0.27→0.60으로 새로 씀 — cases.yaml이 예고한 re-baseline이자
      **상승**이라 래칫은 회귀만 잡고 통과, `--accept` 불필요. 놓친 6건 중 4건은 `flow`가
      대신 발동(`lost_to: {flow: 4}`) — 훅 주입이 integration의 천장을 깎는 관측.
