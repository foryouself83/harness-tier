# 모듈 사전검사 레이어2 통합 — 설계

> 선행 설계: [`2026-07-01-module-precheck-design.md`](2026-07-01-module-precheck-design.md)
> (commit `e4efee6`). 이 문서는 그 후속 개정이다.

## 목표

모듈별 사전검사(`lint`/`static`/`import_lint`/`test`)를 **레이어1 pre-commit에서
레이어2 vdev 게이트(`precommit-runner.sh`)로 이동**한다. 모든 언어별 정적분석·검증을
`vdev-config.modules[]` 단일 SSOT로 모으고, **Claude 세션을 통한 커밋에만** 검증이
동작하도록 일원화한다.

## 배경 — 이전 설계와의 차이

이전(`e4efee6`)은 검증이 두 레이어로 갈렸다:

- 레이어1 pre-commit: `lint`/`static`/`import_lint`/`test` (`render_module_hooks`가
  `.pre-commit-config.yaml`에 모듈×check local 훅 생성 — 변경 모듈만)
- 레이어2 게이트: `security`만 (승격 시 전체 모듈)

문제:

1. **정적분석이 두 레이어에 분산** — 같은 도구(`ruff`/`pyright`/`bandit`)가 모듈은
   레이어1, 글로벌 example은 레이어1, security는 레이어2로 흩어져 혼란.
2. **레이어1은 강제력이 약하다** — `pre-commit install` 한 개발자만 동작하고, 개별
   우회가 가능하며, `check_precommit`이 자동 삽입을 안 해(주석 보존) 사용자가 수동
   추가해야 했다.

해결: 모든 모듈 사전검사를 레이어2로 통합한다. 변경 모듈은 `git diff`로 감지한다.

## 설계

### 1. 레이어 역할 재분리

| 레이어 | 담당 | git 단계 | 트리거 |
|---|---|---|---|
| **레이어1 pre-commit** (유지) | `gitlint`(commit-msg) · `teams-notify-push`(pre-push) · 언어무관 위생(trailing-whitespace, check-yaml/json/toml, shellcheck, hadolint…) | commit-msg / pre-push / pre-commit | `pre-commit install` 한 개발자 |
| **레이어2 게이트** (`precommit-runner.sh`) | vdev 미분류 차단 + **모든 모듈 사전검사** | PreToolUse(`git commit`) | **Claude 세션 커밋만** |
| 레이어3 CI | 계약 테스트(schemathesis) | GitHub Actions | 협업/promotion 브랜치 |

핵심: 레이어1은 **모듈과 무관한 부수 기능 전담**으로 남고(`gitlint`/`teams-notify-push`는
commit/push 단계라 레이어2로 옮길 수 없다), 레이어2가 **모든 언어별 사전검사 전담**이 된다.

### 2. 레이어2 모듈 검증 메커니즘

로직은 **`vdev_gate_check.py`(Python)에 집중**하고 `precommit-runner.sh`는 명령을 받아
실행만 한다(기존 `--security-commands` 패턴 연장). Python은 이미 `_current_branch()` 등
git을 subprocess로 호출하므로 `git diff`도 내부에서 돈다(테스트 가능).

**변경 모듈 감지** (`vdev_gate_check.py` 내부):

1. `git diff --cached --name-only`(staged)로 변경 파일 목록을 얻는다. 비어 있으면
   `git diff HEAD --name-only`로 폴백한다(`git commit -a` 케이스 — staging 전 시점).
2. 각 파일 경로를 `modules[].path` 와 prefix 매칭한다. 매칭되면 그 모듈을 "변경 모듈"에
   넣고, 어떤 path 에도 매칭 안 되면 "미커버 파일"에 넣는다.

**checks 키 분류** (가변 키 철학 유지 — 고정 튜플 `PRECOMMIT_CHECKS` 폐기):

- `security` → **승격 전용·전체 모듈** (변경과 무관)
- `security` 를 **제외한 모든 키**(`lint`/`static`/`import_lint`/`test`, 그리고 사용자가
  `format` 등을 추가하면 그것도) → **매 커밋·변경 모듈**

키 실행 순서는 config 작성 순서를 따른다(`yaml.safe_load` dict 가 삽입 순서 보존, Py3.7+).

**tier별 동작**:

| tier | 동작 |
|---|---|
| `docs` | 스킵 (검증 없음) |
| `dev` | **변경 모듈**의 non-security checks |
| `staging` / `release` | 변경 모듈 non-security + **전체 모듈** `security` (기존 유지) |

**미커버 정책** (fail-open + 가시화 — invariant #1 정합):

| 상황 | 동작 |
|---|---|
| 모듈 매칭 + 해당 키 `checks` 있음 | 그 검사 실행 |
| 모듈 매칭 + 해당 키 `checks` 없음 | 그 검사만 생략 (있는 것만) |
| 모듈 매칭 + `checks` 전체 비음 | 전체 생략 (선언했으나 검사 명령 없음) |
| 어떤 모듈에도 미매칭 | **통과 + stderr 리포트** ("다음 파일은 모듈 미커버라 검증 생략 — 새 모듈이면 `modules[]` 등록") |
| `modules[]` 자체 없음/빈 | 전체 생략 (모듈 미사용 프로젝트) |

차단(deny)은 하지 않는다. tier 분류 자체는 이미 vdev 게이트가 강제하므로(미분류=차단)
완전 무방비가 아니며, 모듈 검증(lint/test)만 생략된다. 과차단은 `--no-verify` 우회를
유발해 게이트 신뢰성을 해치므로 피한다.

**인터페이스** (`vdev_gate_check.py`):

- `module_commands(root, tier) -> tuple[list[str], list[str]]`
  반환 `(실행할 명령 리스트, 미커버 리포트 라인 리스트)`. config 파싱 실패는 `([], [])`
  (FAIL-OPEN). 기존 `security_commands(root, tier)` 를 이 함수가 흡수한다.
- `--module-commands` CLI: 실행 명령은 **stdout**(줄단위), 미커버 리포트는 **stderr**로
  분리 출력(`precommit-runner.sh`가 stdout만 실행, stderr는 사용자에게 흘림). 기존
  `--security-commands` 를 대체한다.

**`precommit-runner.sh`**: 기존 "2) 승격 보안 사전검사" 블록을 "2) 모듈 사전검사"로
확장한다. `--module-commands` 호출 → stdout 명령을 줄단위 실행 → 하나라도 실패하면
`deny`(exit 2 + 사유). 빈 출력이면 통과(FAIL-OPEN). stderr 미커버 리포트는 그대로 노출.

### 3. 레이어1 축소 (`pre-commit-hooks.example.yaml`)

- **제거**: `local` repo 의 언어별 정적분석 훅 — `lint`(ruff check), `format-check`,
  `security`(bandit), `typecheck`(pyright), `lint-imports`. 모두 `modules[]`로 흡수.
- **유지**: `gitlint`(commit-msg), `teams-notify-push`(pre-push), 파일 위생 repo
  (check-yaml/json/toml, trailing-whitespace, end-of-file-fixer…), `shellcheck`,
  `hadolint`.
- `vdev_init_setup.py`: `render_module_hooks`·`missing_module_hooks`·`PRECOMMIT_CHECKS`
  **제거**. `check_precommit`의 모듈 훅 보고 분기 제거(글로벌 example 복사·drift 보고는 유지).

단일 스택 프로젝트도 `modules[]`에 모듈 하나로 정적분석을 표현한다(예: `path: ""` 또는
`src/`). 글로벌 example 에는 더 이상 언어별 정적분석이 없다.

### 4. 마이그레이션 — 안내 (자동 변경 안 함)

기존 호스트 `.pre-commit-config.yaml`에는 모듈 훅·언어별 정적분석 훅이 남아 있을 수
있다. **자동 제거하지 않고 안내만** 한다 — PyYAML round-trip 이 주석/포맷을 파괴한다는
기존 invariant 를 보존한다(`.pre-commit-config.yaml`은 호스트 소유·커스터마이즈 대상).

`/vdev-init` 재실행 시 리포트: *"다음 훅은 레이어2로 이동했습니다. `.pre-commit-config.yaml`
에서 직접 제거하세요: `<id 목록>`."* 식별 대상은 모듈 훅(`{name}-{kind}`)과 제거된
정적분석 id(`lint`/`format-check`/`security`/`typecheck`/`lint-imports`).

## Invariant 보존

- **#1 FAIL-OPEN, 미분류만 fail-CLOSED** — `git diff`/config 파싱 실패, 미커버 파일,
  빈 명령은 모두 통과. 차단은 기존 vdev 미분류 게이트만.
- **#2 Windows 인코딩** — 새 git diff 출력 파싱에 `encoding="utf-8"`, `PYTHONUTF8=1`,
  `force_utf8_io()` 유지.
- **#3 차단 = exit 2 + stderr 사유** — `precommit-runner.sh` `deny()` 그대로.
- **#4 settings.json `if` 금지** — 변경 없음.
- **#5 `/vdev-init` 멱등** — 변경 없음.
- **#6 Teamer 자격증명 keyring** — 무관.

## 영향 파일

- **코드**: `scripts/vdev_gate_check.py`(변경 모듈 감지 + `module_commands` + CLI),
  `scripts/precommit-runner.sh`(모듈 사전검사 블록), `scripts/vdev_init_setup.py`(모듈 훅
  생성 제거), `scripts/_vway_paths.py`(`RUNTIME_GATES` 검토 — 모듈 검증은 자동 실행이라
  게이트 마커 무관, 변경 가능성 낮음).
- **설정**: `pre-commit-hooks.example.yaml`(정적분석 제거), `vdev-config.example.yaml`
  (modules 주석·시점 재정의 — lint/static/import_lint/test → 레이어2).
- **문서**: `CLAUDE.md`(검증 3레이어), `rules/risk-tiers.md`(게이트 설명),
  `skills/vdev/SKILL.md`, `skills/vdev-init/SKILL.md`, `rules/harness-rules.md`(14-1),
  `skills/harness-authoring/references/tech-doc-guide.md`, `USAGE.md`.
- **테스트**: `tests/test_vdev_gate_check.py`(변경 모듈 감지·tier별·미커버),
  `tests/test_vdev_init_setup.py`(모듈 훅 제거), `tests/test_vway_paths.py`.

## 테스트 전략

- **변경 모듈 감지**: staged diff → 모듈 매핑, `commit -a` 폴백, 미커버 파일 분리.
- **checks 분류**: `security` 제외 키가 dev 에 포함되고 `security`가 승격에만, 키 순서 보존.
- **tier별**: docs 빈 출력, dev 변경 모듈 non-security, staging/release 변경 모듈
  non-security + 전체 모듈 security.
- **미커버 리포트**: 미매칭 파일이 stderr 리포트로 나오고 stdout 명령에는 없음.
- **FAIL-OPEN**: config 파싱 실패·git 실패 시 `([], [])`.
- **vdev_init**: `render_module_hooks` 부재, `check_precommit`가 모듈 훅 보고 안 함.

## 비목표 (YAGNI)

- `.pre-commit-config.yaml` 자동 편집/마이그레이션 (invariant 보존 — 안내만).
- 변경 파일→테스트 파일 자동 탐색(예: `foo.py`→`test_foo.py`) — 모듈 단위 "전체 영향도"가
  목표이므로 모듈 전체 `checks.test`를 실행한다.
- 터미널 직접 커밋·CI 에서의 모듈 검증 — 의도적으로 "Claude 세션만"(개별 직접 커밋 안 막음).
