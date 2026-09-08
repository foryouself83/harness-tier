# 렌더 토큰 치환 규율 — 설계

- **Date**: 2026-09-08
- **Status**: 결함 확인 완료(전 항목 실측) · **미착수**
- **Scope**: `scripts/flow_init_setup.py`의 `__HARNESS_*__` 치환 전 경로와, 그 값이 도달하는
  `github/*.workflow.example.yml`
- **Sibling**: [`2026-07-20-workflow-shell-interpolation-design.md`](2026-07-20-workflow-shell-interpolation-design.md)
  가 같은 계열의 **런타임 절반**을 이미 닫았다. 이 문서는 **렌더 타임 절반**이다
- **발견 경위**: [`2026-09-08-e2e-ci-design.md`](2026-09-08-e2e-ci-design.md) 리뷰 중 확인.
  E2E 기능과 무관하게 오늘 배송 중인 템플릿에 존재한다

## 1. 목표

`flow-config.yaml`의 값이 검증 없이 워크플로의 **구조 위치**(YAML 키 · `uses:`)와 **코드 위치**
(`run:` 셸)로 치환되는 경로를 닫고, 재발을 테스트로 막는다.

## 2. 배경 — 이미 닫은 절반과 남은 절반

2026-07-20 작업은 `run:` 블록 안의 `${{ }}` 컨텍스트 인터폴레이션을 제거하고 allow-list
(`matrix` · `steps`)와 테스트를 세웠다. 그 문서의 명제가 여기에도 그대로 적용된다 —
값이 셸 파싱 **전에** 텍스트로 치환되면 데이터가 아니라 코드가 된다.

남은 절반은 **치환 계층이 다르다**.

| | 런타임 절반(닫힘) | 렌더 타임 절반(이 문서) |
|---|---|---|
| 치환 주체 | GitHub Actions | `flow_init_setup.py`의 `text.replace()` |
| 시점 | 워크플로 실행 시 | `/flow-init` 실행 시 |
| 값의 출처 | `github.*` 등 컨텍스트 | `flow-config.yaml`(git 추적 · 팀 공유) |
| 형태 | `${{ ... }}` | `__HARNESS_*__` |

**기존 테스트가 이쪽에 구조적으로 눈이 멀어 있다.** `tests/flow_init/test_workflow_contexts.py`의
`_run_block_expressions`는 YAML을 파싱해 `step["run"]` 안의 `${{ }}`만 정규식으로 찾는다.
`__HARNESS_*__`는 `${{ }}`가 아니므로 이 검사에 **완전히 투명**하다.

그리고 sibling 문서의 "발견 경과" 표가 그대로 반복될 위험을 경고한다 — 손 감사가 두 번 틀렸고,
검사를 먼저 작성했을 때 건수가 늘었으며, 생성기와 references는 glob 밖이라 끝까지 안 보였다.
**"이 값은 안전한가"를 값마다 판단한 것이 실패 원인**이라는 진단이 여기서도 유효하다.

## 3. 결함 목록

전부 실측 확인했다. `render_workflow`의 치환 딕셔너리는 `scripts/flow_init_setup.py:858-866`,
치환 루프는 `:869-870`의 `text.replace(token, value)`다 — 전역 치환이고 검증이 없다.

| # | 값 → 도달 위치 | 등급 | 근거 |
|---|---|---|---|
| C2b | `contract_test.action_ref` → **`uses:`** | **최상** | `flow_init_setup.py:860` (`str()` 평문) → `github/api-contract.workflow.example.yml:28`. 임의 action 참조 = 워크플로 토큰을 든 **임의 코드 실행**. 셸 문자열 주입보다 엄격히 나쁘다 |
| C2 | `contract_test.server.health_url` → `sh -c` 안의 셸 문자열 | 상 | `:864` → 템플릿 `:24-25`의 `timeout … sh -c 'until curl -sf "…"; do sleep 2; done'`. 작은따옴표 안이지만 값이 그 따옴표를 닫을 수 있다 |
| C2c | `contract_test.server.compose_file` → `run:` (2곳) | 상 | `:862` → 템플릿 `:20`, `:35` |
| C2c′ | `contract_test.server.health_timeout` → `run:`의 `timeout` 인자 | 상 | `:865` → 템플릿 `:24`. 따옴표 없이 명령줄에 놓인다 |
| C2d | `versioning.entropy.paths` → `run:`의 `find` 인자 | 상 | `:969`의 `" ".join(...)` → `github/entropy-check.workflow.example.yml`의 `find __HARNESS_ENTROPY_PATHS__ -type f …` |
| C1 | `contract_test.branches` / `unit_test.branches` → 트리거 매핑 | 중 | `:859`, `:1370`의 `", ".join(...)` → `api-contract:8,10` · `unit-test:12,14` |
| C2e | `contract_test.schema` / `base_url` → `with:`의 인용 스칼라 | 중 | `:861-862` → 템플릿 `:30-31`. 값이 `"`를 담으면 스칼라를 벗어나 YAML을 주입한다 |
| C2f | `versioning.entropy.schedule` → `cron` 문자열 | 하 | `:968`. 인용 스칼라 안이라 이탈에 `"`가 필요하지만 검증은 없다 |
| C3 | 렌더 산출물에 템플릿 버전 스탬프 없음 | 별건 | 아래 §5 |

### C1의 실현 경로 — 서술을 정확히 할 것

초안 단계에서 이 항목의 영향을 두 번 잘못 서술했다. 확정된 사실만 적는다.

토큰은 각 템플릿에 **두 번** 나오고(push · pull_request) `text.replace()`는 전역이므로 페이로드가
양쪽에 삽입된다. 외부 전제에 의존하지 않는 유일한 실현은 이것이다:

```
branches 값에 `main]` + 개행 + `paths: ["nonexistent/**"` 를 넣는다
→ push · pull_request 각각이 branches + paths 를 갖는다. 중복 키 없음.
→ 완전히 유효한 YAML, 완전히 유효한 Actions 스키마. "Invalid workflow file" 주석 없음.
→ 워크플로가 영원히 트리거되지 않는다.
```

즉 **권한 상승이 아니라 안전망의 무성 정지**다. 다른 변종(컬럼 0 dedent, `on:` 안 중복 키)은
GitHub 파서의 중복 키 처리에 의존하는데 그것은 검증하지 못했고, 이 저장소가 쓰는 PyYAML은
중복을 last-wins로 받아들인다. 따라서 C1은 `paths` 경로로 기록한다.

**렌더는 실패하지 않는다.** 렌더러는 자기 산출물을 파싱하지 않으므로 성공적으로 잘못된 파일을
디스크에 쓴다. 로컬에서 잡히지 않는다.

### 결함이 아닌 것 — 목록에서 제외

`run: ${{ matrix.test }}`(`github/unit-test.workflow.example.yml`)와 `matrix.setup`은 **의도된
설계**다. `tests/flow_init/test_workflow_contexts.py:15-17`이 "`matrix.*` IS the command the host
configured"라고 적고 `:45`의 allow-list가 그것을 고정한다. 그리고 그 값은
`_unit_test_matrix_include`(`:1292-1313`)가 `yaml.safe_dump`로 내보내므로 YAML 이탈도 막힌다.
**같은 파일 안에서 안전한 치환 하나(matrix)와 위험한 치환 하나(branches)가 공존한다는 사실이
이 결함군의 성격을 가장 잘 보여준다.**

## 4. 왜 개별 패치가 아니라 규율인가

여덟 개 sink는 서로 다른 필드 · 다른 템플릿 · 다른 렌더 함수에 흩어져 있지만 원인은 하나다 —
**`str()`로 감싼 config 값을 `text.replace()`로 템플릿에 밀어 넣는 것**. 하나씩 고치면
sibling 문서가 기록한 실패가 반복된다. 그 문서의 결정을 이 계층으로 옮긴다.

| 질문 | 제안 결정 |
|---|---|
| 값별로 안전성을 판정하는가 | **아니다.** `entropy.schedule`처럼 이탈이 어려운 값도 똑같이 다룬다. 판정을 허용하면 다음 사람이 다시 판정하고, 그것이 sibling 문서에서 `run_number` 2건을 놓친 원인이다 |
| 셸에 도달하는 값 | 템플릿에서 제거하고 스텝 `env:`에 바인딩해 `"$VAR"`로 읽는다 — sibling 문서가 이미 확립한 형태. 셸이 값을 다시 파싱하지 않는다 |
| YAML 구조에 도달하는 값 | 문자열 조인 대신 `yaml.safe_dump`로 내보낸다. `_unit_test_matrix_include`가 이미 그렇게 한다 |
| `uses:`에 도달하는 값 | `env:`도 `safe_dump`도 답이 아니다 — `uses:`는 값 위치가 아니라 **참조 위치**다. 형식 검증(`owner/repo@ref` 또는 로컬 경로)만이 답이다 |
| 검증 실패 시 | 렌더를 건너뛰고 보고한다. 부분 렌더된 워크플로를 쓰지 않는다 |
| 검사 범위 | sibling 문서와 같은 세 표면 — 템플릿 · 자체 CI · 생성기. 파일 glob만으로는 생성기를 볼 수 없다 |

## 5. C3 — 전파 불가

렌더된 워크플로에 템플릿 버전 스탬프가 없고, 모든 렌더 경로가 비파괴다. 결과: **§3의 수정이
기존 소비자에게 도달하지 않는다.** 소비자도 `/flow-init`도 자기 파일이 어느 세대인지 알 방법이
없다.

두 렌더 경로의 보고가 다르다는 점도 기록한다.

- `_render_one:919` — `"  [i] {dest.name} 이미 있어 자동 병합 안 함(커스텀 보존)."` 한 줄뿐
- `render_workflow:851-855` — 위 문장에 `"갱신하려면 기존 파일을 지우고 /flow-init 을
  재실행하거나 직접 수정하세요."`가 붙는다

**managed 모델은 이미 사내에 있다.** `flow_init_setup.py:1094`의 `deploy.yml`은 docstring이
"FULLY GENERATED/MANAGED — regenerated on every render"라고 선언하고 매 렌더 재생성된다.
C3의 수정 비용을 낮추는 사실이다.

제안: 렌더 헤더에 플러그인 버전을 찍고, "이미 있음" 보고가 템플릿이 더 새로운지 함께 말한다.

## 6. 부수 관찰 — 템플릿 하드닝 비대칭

CI 템플릿 **네 개**(`api-contract` · `unit-test` · `wiki-verify` · `doc-style`)가 모두
`permissions:` 블록을 선언하지 않고 `actions/checkout`의 `persist-credentials`를 기본값으로
둔다. `permissions:`가 없으면 `GITHUB_TOKEN`이 조직/저장소 기본 권한을 상속하므로, 기본이
permissive한 조직에서는 쓰기 토큰이다. `permissions:`는 release/deploy 템플릿에만 있다.

이 문서의 수정 대상은 아니지만, **새 템플릿만 하드닝하면 구형이 상대적으로 더 약해진다**는
사실을 함께 기록한다.

## 7. 한계 · 미커버

- **소비자 저장소에 이미 렌더된 파일은 이 작업이 닿지 않는다** — C3가 풀리기 전까지.
- **`skills/harness-deployments/references/**`의 저작 가이드**는 sibling 문서가 이미
  "검사 대상 제외 · CLAUDE.md에 미커버로 명시"로 처리했다. 렌더 타임 절반에도 같은 한계가
  적용되는지 확인이 필요하다.
- **`entropy.schedule`의 cron 문법 자체**는 검증하지 않는다. 잘못된 cron은 GitHub이 거부하고,
  그것은 이 문서가 다루는 계열의 문제가 아니다.

## 8. 커밋 타입

`github/*.workflow.example.yml`과 `scripts/flow_init_setup.py`는 소비자에게 전파되어야 하므로
`fix`. `docs`/`chore`로는 도달하지 않는다.
