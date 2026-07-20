# 워크플로 셸 인터폴레이션 차단 구현 계획

> **Status:** 완료(2026-07-20). 체크박스는 실행 기록이다 — 이 계획은 TDD로 실행되며 작성됐고,
> 검사를 먼저 써서 RED를 확인한 순서가 결과를 바꿨다(Task 1 참조).

**Goal:** 저작되는 모든 GitHub Actions 워크플로에서 `run:` 블록의 `${{ }}` 컨텍스트
인터폴레이션을 제거하고, 재발을 pytest로 막는다.

**Architecture:** 정책은 코드가 아니라 **테스트**다 — 별도 게이트 스크립트를 만들지 않고
`tests/test_flow_init_setup.py`에 검사를 둔다(`uv run pytest`와 `unit-test.yml`이 이미 돌리므로
새 실행 경로가 필요 없다). 검사는 YAML을 파싱해 `run:` 문자열 안의 `${{ }}`를 뽑고, 표현식이
참조하는 **모든** 컨텍스트를 `{matrix, steps}` allow-list와 대조한다.

**Tech Stack:** Python 3.12 (PyYAML · re) · pytest · ruff

## Global Constraints

- **allow-list 유지** — 예외 추가 금지. 무해해 보이는 값(`github.run_number`)도 막는다.
  값별 안전성 판정이 최초 누락의 원인이다.
- **검사 대상은 파일이 아니라 텍스트** — `_run_block_expressions(text: str)`. Path를 받으면
  생성기 출력이 구조적으로 사각지대가 된다.
- **단방향 전파** — SOURCE(`github/`·`scripts/`)만 수정. 호스트 사본은 건드리지 않는다.
- **커밋 타입** — `github/`·`scripts/`·`skills/`는 소비자 도달이므로 `fix`
  (`docs`/`chore`는 버전이 안 올라 전파되지 않는다).
- **최소 변경** — 셸이 보는 값이 이전과 동일해야 한다. 플래그 제거·인용 변경은 근거를 주석에 남긴다.
- **Bash 도구에서 PowerShell here-string(`@'...'@`) 금지** — heredoc 사용.

---

### Task 1: 검사 작성 → RED (선행)

**Files:** Modify: `tests/test_flow_init_setup.py`

- [x] **Step 1: `_run_block_expressions` + allow-list 검사 작성**
      `github/*.yml` + `.github/workflows/*.yml`을 파싱해 `run:` 안의 `${{ }}`를 수집.
- [x] **Step 2: RED 확인** — `uv run pytest -k run_block` → **9건** 검출.
      손 감사가 7건으로 셌던 것과 어긋난다: `github.run_number` 2건이 추가로 나왔다.
      **이 불일치가 이 계획의 근거다** — 검사를 나중에 썼다면 9건을 못 봤다.

### Task 2: 템플릿 5개 수정 → GREEN

**Files:** Modify: `github/release.{cargo-release,gitversion,jreleaser}.workflow.example.yml` ·
`github/deploy.{cratesio,nuget}.workflow.example.yml`

- [x] **Step 1: `REF_NAME`/`RUN_NUMBER` env 이관** — `release.python-semantic-release`에 이미
      있던 패턴을 그대로 이식(새 패턴 창작 아님).
- [x] **Step 2: 시크릿 env 이관** — cratesio는 `--token` 제거(cargo가 변수를 네이티브로 읽음),
      nuget은 `--api-key` 유지(dotnet은 읽지 않음).
- [x] **Step 3: GREEN 확인** + `pytest -q` 671 passed + `pre-commit run --all-files` Passed.

### Task 3: 도메인 리뷰 → FAIL 수용

- [x] **Step 1: 독립 `general-purpose` 에이전트 리뷰** → **FAIL**.
- [x] **Step 2: 지적 5건 개별 검증**(수용 전 재현). 요지 둘:
      - 생성기 `_orchestrator_yaml`의 `inputs.tag`가 **미수정** — 자유입력이라 가장 위험한데
        검사가 Python 문자열을 볼 수 없어 구조적 사각.
      - allow-list `startswith`가 첫 토큰만 봐서
        `steps.x.outputs.y || github.event.head_commit.message`가 통과(직접 재현).

### Task 4: 검사 강화 + 생성기 수정 (TDD)

**Files:** Modify: `tests/test_flow_init_setup.py` · `scripts/flow_init_setup.py`

- [x] **Step 1: `_disallowed_contexts` 도입** — 표현식의 **모든** 컨텍스트 참조를 검사.
      `_run_block_expressions`를 Path → text로 변경.
- [x] **Step 2: 생성기 검사 테스트 추가 → RED** — `step 'resolve' interpolates ${{ inputs.tag }}`.
- [x] **Step 3: `_orchestrator_yaml` 수정 → GREEN** — `TAG_INPUT` env 경유.
      빈 입력 fallback(`[ -z "$TAG" ]` → `git describe`) 불변 확인.

### Task 5: 재검토 → NEW-A 대응

- [x] **Step 1: 재검토 요청** → **PASS-WITH-NITS**. 병합 전 권고 1건(NEW-A).
- [x] **Step 2: NEW-A 재현** — `toJSON(github)` · `github['event'][…]` · `GITHUB.actor` 3종이
      통과함을 확인. 부수로 `steps.env.outputs.x` 오탐도 확인.
- [x] **Step 3: 정규식 반전 → GREEN** — "점이 뒤따르는 이름"에서 **"점이 앞서지 않는 식별자"**
      + `.lower()`. 3종과 오탐이 함께 닫힘.

### Task 6: references 문서 + 문서화

**Files:** Modify: `skills/harness-deployments/references/**` (4개) · `CLAUDE.md`

- [x] **Step 1: 셸 도달 라인 수정** — kubernetes(2) · ssh-server(3) · rust-cratesio(1) ·
      dotnet-nuget(1). `with:`/`concurrency.group:` 위치 히트는 셸이 아니므로 제외.
- [x] **Step 2: yaml 펜스 수동 파싱 검증** — 테스트 범위 밖이므로 손으로 확인(4개 OK).
- [x] **Step 3: CLAUDE.md** — 3개 표면 커버 + references가 커버 밖이라는 사실을 명시.

### Task 7: 최종 검증

- [x] `uv run pytest -q` → **674 passed**
- [x] `uv run pre-commit run --all-files` → 전항목 Passed
- [x] 생성기 4경로 수동 확인(렌더 · 파싱 · 빈입력 · 악성입력)
