# 모듈 단위 사전검사 (모노레포)

- 날짜: 2026-07-01
- 티어: DEV (게이트 실행 로직·설정 스키마·티어 정책 변경)

## 배경 / 문제

모노레포는 모듈(서비스·라이브러리·패키지)마다 개발 언어가 다를 수 있다.
현재 vway-kit 검증 모델은:

- **레이어1 pre-commit**: 파일 단위 정적 분석(서비스 단위 아님).
- **레이어2 vdev 게이트**: 단일 전역 `test.command` 하나를 통째 실행(티어
  이분법 — docs 면제 / dev 전체).

따라서 "어떤 모듈의 파일이 변경되면 그 모듈 전체에 그 언어에 맞는 사전검사
(린트·정적분석·유닛테스트·보안·import-lint)를 돌려 모듈 단위 영향도를
판단"하는 것이 불가능하다.

## 목표

모듈 폴더 내 파일이 변경되면 **그 모듈 전체**에 대해 언어에 맞는 사전검사를
실행한다. 검증 종류마다 시점이 다르다(아래 매핑). 검증 명령의 근거는 사람이
손으로 적기보다 harness 리서치·스캐폴드가 남긴 docs SSOT를 참고해 **초안**으로
작성하고, 사람이 수정 가능하다.

## 핵심 결정 (브레인스토밍 합의)

1. **레이어**: 일상 검증은 레이어1 pre-commit(모든 개발자·모든 커밋). 보안은
   레이어2 vdev 게이트(승격 시).
2. **정의 방식**: `vdev-config.modules[]` 명시 선언. 값의 출처는 docs SSOT를
   참고한 LLM 초안이되, 사람이 수정하는 명시적 중간 계약.
3. **전역 test 폐기**: 전역 `test.command`를 완전히 제거(하위호환 없음). 테스트는
   항상 모듈별.
4. **명칭**: 단위 키는 `modules`(앱·라이브러리·패키지 포괄).

## 검증 종류 → 레이어·시점 매핑

| check | 레이어 | 시점 | 범위 |
|-------|--------|------|------|
| `lint` · `static` · `import_lint` · `test` | pre-commit (레이어1) | 모든 커밋 | 변경된 모듈 |
| `security`(도구, 예: bandit) | vdev 게이트 (레이어2) | STAGE + RELEASE | 전체 모듈 |
| `/security-review`(LLM 리뷰) | vdev 게이트 (레이어2) | RELEASE만 | 기존 게이트 |

- 유닛테스트는 무거워도 **모든 커밋**에 포함(사용자 결정).
- 보안 도구 사전검사는 일상 커밋이 아니라 **승격 시 전체 모듈**(승격 = 통합
  검증이므로 변경분 추적이 아닌 전체).

## config 스키마

```yaml
# 모듈 단위 사전검사 (모노레포 — 모듈별 언어·도구가 다를 때).
# 선언하면 pre-commit 이 "모듈 경로 변경 시 그 모듈 전체"에 검증을 돌린다.
# 검증 명령의 초안은 harness SSOT 를 참고해 /vdev-init 이 작성하고, 사람이 수정한다.
modules:
  - name: api
    path: services/api/                       # 이 경로 하위 변경 시 발화
    checks:                                   # 가변 키 — 있는 것만 훅 생성
      lint:        "ruff check services/api"
      static:      "uv run pyright services/api"
      import_lint: "uv run lint-imports --config services/api/.importlinter"
      test:        "uv run pytest services/api"
      security:    "uv run bandit -r services/api --severity-level medium"
  - name: web
    path: services/web/
    checks:
      lint:   "npm --prefix services/web run lint"
      static: "npm --prefix services/web run typecheck"
      test:   "npm --prefix services/web test"
```

- `checks`는 **가변 키**: `lint`/`static`/`import_lint`/`test`/`security` 중 해당
  언어에 있는 것만. 빈 값/생략이면 그 단계는 만들지 않는다.
- 전역 `test` 필드는 **폐기**(deprecated). 기존 설치엔 마이그레이션 안내.

## 컴포넌트별 설계

### A. config 스키마 — `modules[]`

`vdev-config.example.yaml`에 `modules[]` 추가, `test:` 섹션 제거(주석에
"모듈별 checks.test 로 이전" 안내). `missing_config_slots`/슬롯 점검은 기존
패턴대로 `modules` 최상위 섹션을 인식.

### B. pre-commit 훅 생성 — `vdev_init_setup.py` (기계)

`modules[].checks` 중 **pre-commit 대상 종류**(`lint`/`static`/`import_lint`/
`test`)에 대해 모듈×check별 local 훅을 생성:

```yaml
- repo: local
  hooks:
    - id: api-lint
      name: "api: lint"
      entry: bash -c 'ruff check services/api'
      language: system
      files: ^services/api/        # 모듈 경로 변경 시만 발화
      pass_filenames: false        # 변경 파일이 아니라 모듈 전체
      stages: [pre-commit]
    # api-static, api-import_lint, api-test 동일 패턴
```

- `security`는 pre-commit 훅으로 만들지 않는다(레이어2에서 처리).
- **중복 체크**(invariant — 기존 config 보존):
  - 기존 `.pre-commit-config.yaml`의 hook `id` 수집 → 만들 훅 id가 이미 있으면
    skip(멱등).
  - 만들 훅의 명령·`files`가 기존 전역 훅과 의미 겹칠 가능성 → `[!]` 보고(자동
    제거 안 함).
  - 파일 없으면 example + 모듈 훅 전체 생성, 있으면 빠진 훅만 보고
    (render_workflow/check_precommit 패턴).
- 변경이 두 모듈에 걸치면 각 모듈 훅이 독립 발화(pre-commit files 글롭의 자연
  동작).

### C. 전역 test 제거 + 승격 보안 — `precommit-runner.sh` (레이어2)

- **전역 test 실행 단계 삭제**([:93-123] 의 `test.command` 읽기·실행 제거).
- **미분류 차단**(Invariant #1 예외 2)·python3/PyYAML 도구 검사는 유지.
- **승격 보안**: 현재 티어가 `staging`/`release`면(vdev_gate_check 의 티어 판정
  재사용) `modules[].checks.security`를 **전체 모듈** 실행. 하나라도 실패 시
  deny(exit 2). security 명령이 없는 모듈은 skip.
  - FAIL-OPEN 유지: config 파싱 실패 시 보안 단계 skip(게이트 영구 차단 방지).

### D. 티어 정책 — `vdev-tiers.yaml` / `vdev_gate_check.py`

```yaml
tiers:
  docs:    { superpowers: false, gates: [doc-sync] }
  dev:     { superpowers: true,  gates: [review, doc-sync] }   # 전역 precommit 제거
  staging: { superpowers: true,  gates: [review, security-scan] }
  release: { superpowers: true,  gates: [review, security-scan, security] }
```

- **dev 의 `precommit` 게이트 제거**: 모듈 test/정적분석은 레이어1 pre-commit이
  담당하므로 vdev 게이트는 더 이상 전역 test를 강제하지 않는다. vdev 게이트의
  dev 책임 = 미분류 차단 + `review`/`doc-sync` 증거.
- **`security-scan`**(신규 게이트 키): 전체 모듈 보안 도구 사전검사.
  precommit-runner.sh가 staging/release 커밋 시 실행하므로 별도 `.done` 마커가
  아닌 **런타임 게이트**(RUNTIME_GATE 와 동류) — `precommit`처럼 `.done` 검사에서
  제외.
- **`security`**(기존): release 의 `/security-review` LLM 리뷰 → `security.done`.
- `RUNTIME_GATE`/`STAGING_TIER`/`RELEASE_TIER` 상수와 `gates` 키는 byte-match
  유지(desync 시 FAIL-OPEN — `_vway_paths.py` 주석 규율).

### E. 초안 작성 — `vdev-init` 스킬 (LLM)

`skills/vdev-init/SKILL.md`에 단계 추가:
- harness 설치 감지 시(Step 0) `docs/code-style/<stack>.md`의 툴체인·운영
  관심사 섹션 + `services/*/CLAUDE.md`(모듈별 SSOT)를 읽어 `modules[].checks`
  초안 작성. 스캐폴드 하위 폴더(`tests/` 등) 감지로 test 경로 추정.
- **SSOT 에서 도구를 못 찾거나 모호하면 AskUserQuestion** 으로 확인(추측 금지).
- harness 없으면 사용자에게 직접 입력 요청하거나 스킵(harness 비의존).
- 리서치 결과는 기본값 — 사람이 config 에서 수정, config 가 최종 권한.

### F. harness SSOT 가이드 확장 — harness-authoring / harness-rules

- `skills/harness-authoring/references/tech-doc-guide.md`(또는 적절 reference)에
  "언어/스택별 **필요한 사전검사 도구 목록**(lint/format/typecheck/security/
  import-lint/test runner)과 **폴더 구조**(tests/ 위치 등)를 SSOT 로 가이드"
  하도록 지침 추가.
- `rules/harness-rules.md`에 동일 규율 한 줄 추가.
- **경계 준수**([harness-rules 14]): harness 는 *도구·구조를 가이드*(기술 스택
  정보)만 하고, *게이트로 강제*는 vdev 가 한다. harness-init 의 stack_map/스캐폴드
  로직 자체는 건드리지 않는다.

### G. 마이그레이션 (기존 호스트 무손실 전환)

- **기계(자동)**: 전역 test 제거 버전의 `precommit-runner.sh`·게이트 스크립트는
  `/vdev-init` 재실행 시 `copy_artifacts`로 호스트 사본 자동 갱신(단방향 전파).
- **기계(보고)**: 기존 `vdev-config`에 `test` 필드가 있고 `modules` 없으면
  → deprecation 보고(자동 제거 안 함 — config 보존 invariant).
- **LLM(초안)**: vdev-init 스킬이 기존 `test.command`를 `modules[].checks.test`
  초안의 입력으로 활용(harness SSOT 와 함께). 모호하면 질문.
- **멱등**: 재실행해도 모듈 훅 중복 추가 없음(id skip), config 덮어쓰지 않음.

## 검증 (테스트)

- B: `modules[].checks` 가변 키 → pre-commit 훅 조각 생성(빈 키 skip,
  security 제외). 중복 id skip / 의미중복 보고. 파일 없으면 생성·있으면 보고.
- C: 전역 test 제거(더 이상 test.command 실행 안 함). staging/release 티어면
  전체 모듈 security 실행, 실패 시 deny. config 파싱 실패 시 FAIL-OPEN.
- D: vdev-tiers gates 키 변경 후 `required_gates`·`should_run_precommit` 정합.
  미분류 fail-closed·정책 파싱 실패 fail-open 회귀 없음.
- G: 기존 `test` 필드 감지 → deprecation 보고. modules 미선언 시 동작.

## Invariant 영향

- **#1 FAIL-OPEN / 미분류 fail-closed**: 미분류 차단 로직 유지. security 단계는
  config 파싱 실패 시 fail-open. 모듈 검증 도구 부재는 해당 모듈 훅이 보고.
- **#2 Windows 인코딩**: 신규 Python 경로도 `encoding="utf-8"`·`force_utf8_io`.
- **#3 차단 = exit 2 + stderr**: security 실패 deny 동일.
- **#5 멱등**: 모듈 훅·config 중복 방지.

## 비목표 (YAGNI)

- 전역 `test.command` 하위호환(요청에 따라 폐기).
- 변경분 추적 기반 승격 보안(전체 모듈로 단순화).
- harness-init 의 stack_map/스캐폴드 로직 변경(가이드 문서만 확장).
- check stage 세밀 오버라이드(종류별 고정 매핑으로 충분).

## 구현 단계 (한 spec, 단계 분리)

1. A (config 스키마) + G 일부(test 폐기·deprecation)
2. B (pre-commit 모듈 훅 생성 + 중복 체크)
3. C (precommit-runner: 전역 test 제거 + 승격 보안)
4. D (vdev-tiers gates + vdev_gate_check 정합)
5. E (vdev-init 스킬 초안 작성 단계)
6. F (harness SSOT 가이드 확장)
