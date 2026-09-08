# E2E CI 안전망 — 설계

- **Date**: 2026-09-08
- **Status**: 결정 14개 **전부 확정** (D8 = 선택지 C §4, D14 = 웹 전용 §3.3) → 구현 착수 가능
- **리뷰 반영(라운드 6)**: D1 보강(§3.1 · §3.2) · D6 모델 인용 정정 · §9 불리언 모순 해소 ·
  산출물 baseURL 자리 수 정정 · `risk-tiers.md` 인용 재해석
- **리뷰 반영(라운드 7)**: D6 표 행 복구 · §3.1을 `RUNTIME_GATES` 두 종류로 재작성(미검증
  스큐 논거 기각) · §4 제약 불릿 복원 · **D8 마감**
- **리뷰 반영(라운드 8)**: **D14 신설**(§3.3) — 토큰 없는 템플릿이 무엇을 도는지가 미기술이었고
  §1의 일반 서술과 D7·D8·D9의 Playwright 전제가 어긋나 있었다. 적용 범위를 웹으로 못박고,
  REST 전용 백엔드의 답(`api-contract`)과 그것이 덮지 못하는 구멍(§9)을 함께 적는다
- **리뷰 반영(라운드 9)**: D14 근거를 넷으로 재정렬(배달 경로 정합 · **스텝 가드 신설** ·
  어법 선례 · 일관성) · `contract_test`가 `enable: true`로 출하된다는 사실 반영해 §3.3 근거 3
  인용 정정 · D6의 "자기-no-op 불가"에 단서 · §9 경로 필터 항목 정정 · 자체 폭 기준을 이
  저장소 cap(`doc_style_check.py:52` `MAX_LINE = 100`)에 맞춤
- **Scope**: harness-tier가 소비자에게 배송하는 E2E 워크플로 템플릿 · `flow-config` 슬롯 1개 ·
  `skills/playwright-scaffold/` 수정. 게이트 정책(`flow-tiers.yaml`)과 승격 스킬은 **불변**
- **Sibling**: 이월 결함은 [렌더 토큰 치환 규율](2026-09-08-render-token-substitution-design.md)로
  분리. 그 문서의 결함들은 이 기능과 무관하게 오늘 배송 중인 템플릿에 존재한다

## 1. 목표

승격 브랜치(stage · main)에서 E2E 스위트를 CI로 돌려, 레이어 2가 보지 못하는 커밋
(터미널 · CI · GitHub 직접 커밋)에서 생긴 통합 회귀를 **보이게** 만든다.

차단하지 않는다. `unit-test.yml` · `api-contract.yml` · `wiki-verify.yml` · `doc-style.yml`
과 같은 부류의 다섯 번째 CI 안전망이다.

**위 두 문단은 목표이고, 범위는 D14가 정한다.** 템플릿이 토큰을 갖지 않으므로 실행 명령이
리터럴이고 그 리터럴이 Playwright이므로, 실제 커버 범위는 "**Linux 러너에서 도는 Playwright
스위트**"다(§3.3 · §9 첫 항목). 비웹 소비자에게는 슬롯이 `false`로 남는다.

## 2. 배경 — 왜 범위가 이만큼인가

초안 4개가 적대 리뷰 4라운드에서 모두 FAIL했다. 라운드 5에서 리터럴 YAML · 셸 · 정규식 ·
액션 핀을 문서에서 걷어내고 결정만 남기자 3개 리뷰 중 2개가 같은 단일 항목(D8)만 지목했다.

실패가 반복된 것이 아니라 **범위가 계속 줄면서 남은 핵심이 단단해졌다**. 폐기된 것과 그 이유:

| 초안이 가졌던 것 | 폐기 이유 |
|---|---|
| `flow-tiers.yaml`에 `e2e` 게이트 추가 | 게이트 디스패치가 미지의 이름을 마커 게이트로 처리하고 마커 부재 시 차단한다. 마커 생산자를 같은 릴리스에 싣지 않으면 소비자 전원의 승격이 막힌다 |
| `gh run list`로 CI 결과 조회 후 마커 기록 | `gh`가 인가 의존성이 된다. 오프라인 프로덕션 배포는 문서화된 Release 진입점이라 조회가 정의상 불가 |
| self-hosted 러너 · 개발서버 타깃(`ssh`/`url` kind) | 러너를 재발명하는 것이었고, 미지 소비자에게 self-hosted를 권하는 것은 방어 불가 |
| `environments[] × suites[]` 2차원 매트릭스 | 엔트리별 브랜치 필터가 필요한데, 매트릭스 잡은 `jobs.<id>.if`에서 `matrix`를 못 읽는다. 스텝 레벨로 내리면 잡이 성공으로 보고되어 **아무것도 안 돌고 초록** |
| `env_from_secrets` | 포크 PR은 시크릿을 못 받아 외부 기여가 영구 레드가 되고, 같은 저장소 PR 브랜치는 작성자가 실행 내용을 통제한다 |
| `base_url` 필드 | 스캐폴드가 `use.baseURL`을 리터럴로 박으므로 환경변수가 도달하지 않는다. 두 프론트가 조용히 같은 앱을 친다 |
| config 구동 렌더러 전반 | 필드를 더할 때마다 검증 · 이스케이프 · 타 블록과의 정합 · 소비자가 패치할 수 없는 산출물이 딸려왔다. 신규 결함이 전부 이 한 결정에서 나왔다 |

## 3. 결정 사항

| # | 결정 | 근거 |
|---|---|---|
| D1 | E2E는 **CI 안전망이지 티어 게이트가 아니다** | `_harness_paths.py:82`의 `RUNTIME_GATES` 4-튜플 밖 이름은 마커 게이트가 되고 (`flow_gate_check.py:534-536`) 마커 부재 시 차단한다(`:875-881`). 마커 게이트에 no-op 경로가 없다. 런타임 게이트 경로는 §3.1, **이 결정이 증명하지 않는 것**은 §3.2 |
| D2 | 게이트 경로에 의존성을 더하지 않고, CI 상태로 인가를 판단하지 않는다 | 차단성 의존은 셸 · python3 · PyYAML뿐(`check-deps.sh:73`). 게이트 경로의 `gh` 사용은 read-only에 exit 20 undetermined(`check-merge-ruleset.sh:20`). 오프라인 Release 진입점은 `risk-tiers.md:197-199`. **인용 주의**: `08b92f1`이 이 절을 "Two entry points" → "One entry point"로 재작성했다. 오프라인 배포가 Release라는 사실은 살았고 줄 위치도 같지만, 이제 그것은 두 번째 진입점이 아니라 승격 진입점의 한 사례다 |
| D3 | 승격 스킬(`flow` · `release-commit`)은 불변 | `7480639`가 승격 절차를 `release-commit`으로 분리했다. 마커를 쓰고 지우는 곳이 거기다 |
| D4 | `feature/*` → integration의 인간 통합테스트 게이트는 유지 | 그것은 daily flow, E2E는 promotion flow다. 머지 **전** 게이트를 머지 **후** 신호로 대체하면 순 커버리지가 준다 |
| D5 | GitHub-hosted 러너 전용. self-hosted를 렌더하지도 권하지도 않는다 | 러너 라벨은 권한 경계가 아니고, 러너는 잡 간 ephemeral이 아니며, 포크 승인 게이트는 같은 저장소 PR을 덮지 않는다. 플러그인은 소비자의 저장소 가시성과 네트워크 위치를 모른다 |
| D6 | 기존 **토큰 없는 복사 경로**로 배달하고, host config의 **불리언 하나**로 켠다 | `_render_one(src, dest, {}, label)`(`flow_init_setup.py:915-925`)이 빈 치환맵 · 비파괴이고 wiki-verify · doc-style 두 워크플로가 이미 쓴다. **모델은 절반만 같다** — 그 둘은 불리언이 없고 무조건 렌더되며 자기-no-op이 두 겹이다(스크립트가 config 없이 exit 0, 스텝이 `if [ ! -f … ]`로 가드: `wiki-verify.workflow.example.yml:35-38` · `doc-style.workflow.example.yml:29-32`). E2E는 그 두 겹 중 스크립트 자체 no-op을 가질 수 없어 불리언이 그 자리를 대신한다. **단, 스텝 가드 한 겹은 가능하다** — D14가 실행 도구를 리터럴로 고정하면서 `playwright.config.*`라는 이름 관례가 알려지기 때문이다(§3.3 근거 2). 초안이 "자기-no-op을 가질 수 없다"고 적은 것은 범용 템플릿을 전제한 서술이었다. `COPY_FILES`에 `github/` 항목이 없으므로(`:99-111`) 캐시에 둔 파일은 소비자 디스크에 닿을 경로가 아예 없다. **불리언은 치환 sink가 아니다** — 풍부한 config 블록은 sibling 문서의 결함 계열을 새로 만들지만 불리언은 만들 수 없다 |
| D7 | per-suite 설정을 두지 않고, 다중 앱 팬아웃을 Playwright `projects[]`에 위임한다 | 스택 기동과 브라우저 설치가 1회로 끝나고 리포트가 하나로 모인다. **근거 정정**: 초안은 "per-suite 목록은 순차 실행이라 첫 실패에서 멈춘다"를 근거로 삼았으나 이 저장소가 반박한다 — `unit_test.jobs[]`가 같은 형태를 `strategy.matrix.include` + `fail-fast: false`로 풀어 병렬 실행하고 전 실패를 수집한다(`github/unit-test.workflow.example.yml:19-24`). 결론은 살되 근거는 비용과 리포트 단일성이다 |
| D8 | 다중 앱 설정은 **렌더 경로가 아니라 `playwright-scaffold` 확장**으로 배달한다 | 그 파일을 이미 소유한 컴포넌트가 하나 있고(`skills/playwright-scaffold/SKILL.md:105-113`), 비파괴 규칙상 이미 설정이 있는 소비자에게는 렌더든 스킬이든 결과가 똑같이 "보고"다. 새 호스트 쓰기 위치 · 새 `*_DEST` · `flow_init_setup.py` 변경이 전부 0이다 — §4 |
| D9 | 스캐폴드 config는 baseURL을 환경변수에서 읽고 리터럴을 fallback으로 두며, trace 정책을 명시한다 | `skills/integration/references/web-playwright.md:193`이 `process.env.BASE_URL` 주입을 규정하는데 `skills/playwright-scaffold/SKILL.md:112`는 리터럴을 쓴다. 플러그인 자기 산출물 둘이 어긋난다. **근거 정정**: reporter는 이미 선언돼 있다(`web-playwright.md:194`, `skills/integration/SKILL.md:137-144`가 `--reporter=json,junit`을 고정). 미선언은 trace뿐이고, trace는 요청 · 응답 본문과 세션 토큰을 담으므로 아티팩트 업로드 안전성이 여기에 달려 있다. D8이 C로 닫히면서 이 수정과 같은 파일 · 같은 스킬에 떨어진다 |
| D10 | 배달된 워크플로는 소비자가 소유하고 편집하는 출발점이다 | 모든 렌더 경로가 비파괴다(`:853` · `:919` · `:1364`). 대가로 템플릿 수정이 기존 소비자에게 도달하지 않는다 — sibling 문서의 C3 |
| D11 | required status check 승격은 **전제조건 목록으로 문서화만** 하고 수행하지 않는다 | 보고되지 않는 필수 체크는 PR을 영구 차단하고, 직접 푸시에 걸면 그 체크를 만들 푸시가 거부되어 교착한다. `check-merge-ruleset.sh:4-8`이 같은 자세를 이미 채택했다 — "READ-ONLY … that decision stays with the repo owner" |
| D12 | 기본값으로 시크릿 없음, `pull_request` 트리거 없음 | 포크 PR은 시크릿을 못 받고, 같은 저장소 PR 브랜치는 작성자가 실행 내용을 통제한다. 귀결로 이 신호는 **머지 후**에만 온다 |
| D13 | stage → production 강제를 제공하지 않으며, 그렇다고 명시한다 | 마커 생산자 · 커밋 결속 증거 · undetermined 상태 · break-glass가 모두 필요하고 그것은 별도 설계다 |
| D14 | 템플릿은 Playwright를 **리터럴로** 부르고, 적용 대상을 **웹 프론트가 있는 저장소**로 한정한다 | 토큰이 없으므로 실행 명령은 리터럴이거나 문서화되지 않은 관례이거나 둘뿐이고, 관례는 §2가 폐기한 계열이다. 비웹 절반은 이 저장소가 이미 판정했다 — `skills/integration/references/non-web.md:3-5`가 "integration-test automation is **not enforced**"이고 산출물이 수동 체크리스트다. §3.3 |

### 3.1 D1 보충 — 런타임 게이트 경로도 닫힌다

D1의 표는 마커 게이트 경로만 반박한다. 당연히 따라오는 질문 — "`wiki` · `doc-style`처럼
`RUNTIME_GATES`에 넣고 설정 없으면 no-op 하면 되지 않나" — 에 **두 가지**로 답한다.
초안은 셋이었고 세 번째(버전 스큐)는 아래에서 기각했다.

**먼저 `RUNTIME_GATES`가 한 종류가 아니라는 것을 짚어야 한다.** 튜플은 네 이름을 담지만
실행 모델과 에러 계약이 둘로 갈린다(`_harness_paths.py:70-81`).

| 종류 | 예 | 에러 계약 |
|---|---|---|
| `main()` 편승 (in-process) | `wiki` · `doc-style` | 판정이 **아닌** 모든 것에 FAIL-OPEN (Invariant 1) |
| 모듈 채널 (타이밍 버킷) | `precommit` · `security-scan` | nonzero exit = 판정 → 차단 |

그 위에서 답은 둘이다.

1. **in-process 종류는 E2E에 안 맞는다.** 그쪽 계약은 "진짜 판정이 아닌 모든 것에 FAIL-OPEN"이라
   플레이키 · 타임아웃 · 브라우저 부재가 전부 통과가 된다 — E2E의 최빈 실패 모드 전부가
   무보고다. 그리고 훅이 커밋 프로세스 안에서 직접 돌리므로(`flow_gate_check.py:535` docstring)
   PreToolUse 훅이 브라우저 스위트를 띄운다.
2. **모듈 채널 종류는 맞는다 — 그런데 그것이 정확히 §3.2의 경로이고, 새 이름 없이 오늘
   도달 가능하다.** E2E는 nonzero가 진짜 판정이므로 모듈 채널 계약이 옳고, `security-scan`이
   이미 그 계약의 승격 버킷이다. `RUNTIME_GATES`에 `e2e`라는 **새 이름**을 넣는 것은 같은 실행
   모델에 새 타이밍 어휘와 정책 동기화 부담만 얹는 것이다 — `_harness_paths.py:62-64`가
   "Must exactly match the same keys in the flow-tiers.yaml gates list (on desync, missing_gates
   wrongly reports the gate as unmet)"로 그 부담을 명시한다.

**검증했으나 기각한 논거**: "`RUNTIME_GATES`가 `COPY_FILES`에 있으니 새 정책 + 낡은 모듈
스큐가 재발한다"는 성립하지 않는다. `tiers_path`(`flow_gate_check.py:592`)와
`precommit-runner.sh:97`이 **같은 `CLAUDE_PLUGIN_ROOT` 스위치**로 정책과 스크립트를 함께
고르고, 그 `PLUGIN_SCRIPTS`가 모든 `flow_gate_check` 스폰을 통과한다(`:108` · `:173` · `:186`
· `:232` · `:249`). 둘이 어긋날 경로가 없다. 위 1 · 2만으로 충분하므로 확인되지 않은 논거는
싣지 않는다.

### 3.2 D1이 증명하지 않은 것 — 차단은 오늘도 가능하다

D1이 증명한 명제는 **"`flow-tiers.yaml`에 `e2e`라는 게이트 이름을 추가하면 안 된다"**이다.
**"E2E는 차단하면 안 된다"**는 다른 명제이고 이 문서는 그것을 증명하지 않는다. 섞어 읽으면
"이 플러그인으로는 E2E를 차단하게 만들 수 없다"는 잘못된 결론이 나오므로 분리해 적는다.

**차단은 플러그인 코드 0줄로 오늘 가능하다.** 호스트가 자기 `flow-config.yaml`의 모듈에
`when: promotion`으로 체크를 하나 넣으면 된다. `promotion` 타이밍은 `security-scan` 버킷으로
들어가고(`flow-config.example.yaml:44-48`이 "promotion → `security-scan` 게이트, ALL modules
(staging/release promotion only)"로 명시), `security-scan`은 `flow-tiers.yaml`의 staging ·
release 티어에 이미 있으며, 모듈 채널은 "nonzero exit = 판정"이므로 승격 커밋이 차단된다.
새 게이트 이름이 없으니 §3.1의 버전 스큐도 없다. `{run, when}` 확장형은
`_parse_check`(`flow_gate_check.py:678-691`)가 받고, `checks` 키 어휘는 열려 있다
(`flow-config.example.yaml:38` "Add your OWN keys freely").

§7이 `performance`의 정적 절반에 대해 이미 같은 말을 한다 — "`modules[].checks`의 모양
그대로다 … 플러그인 코드 0줄로 오늘 가능하다". **그 관찰은 E2E 자신에게도 적용된다.**

**그래서 둘은 대안이 아니라 서로 다른 구멍이다.**

| | 이 문서의 CI 안전망 | 호스트의 `modules[].checks` 게이트 |
|---|---|---|
| 보는 것 | 터미널 · CI · GitHub 직접 커밋 — 레이어 2가 **구조적으로** 못 보는 것 | Claude 세션 승격만 |
| 시점 | 머지 후 | 승격 커밋 **전** |
| 차단 | 안 함 | 함 |
| 켜는 주체 | 플러그인이 배송, 불리언 | 호스트가 자기 설정에 |

티어 게이트는 터미널 승격을 원리적으로 못 본다. 그것이 §1이 겨냥한 구멍이고 게이트로는 메울
수 없다. 반대로 CI 안전망은 승격을 못 막는다. 레포가 이미 쓰는 3계층 구조 그대로다.

**"가능하다"까지만 적고 권하지는 않는다.** 그 경로의 대가가 넷이고 마지막 하나가 결정적이다.

- **동기 실행** — PreToolUse 훅 안에서 브라우저 스위트가 돌아 승격 커밋이 몇 분간 멈춘다.
- **출력이 안 보인다** — 모듈 채널은 출력을 버퍼링해 실패했을 때만 로그를 뿌린다
  (`_harness_paths.py:78-81`). 도는 동안 아무 신호가 없다.
- **경로 필터 없음** — `security-scan`은 전 모듈 버킷이라(`flow_gate_check.py:826-829`
  `for mod in modules`) 매 승격에 전체 E2E가 돈다.
- **타임아웃이 없다** — 이 경로 전체의 타임아웃은 둘뿐이고(`flow_gate_check.py:410` git
  서브프로세스 5초, `precommit-runner.sh:60` stdin 5초) 체크 명령에는 하나도 걸리지 않는다.
  멈춘 스위트는 무한정 멈춘 커밋이 되고, 그것이 훅 안에서 일어난다.

이 대가는 자기 저장소를 아는 호스트가 지는 것이지 미지의 소비자 전원에게 플러그인이 지울
것이 아니다 — D5 · D11과 같은 자세다. 따라서 `USAGE.md`의 활성화 절에 **이 경로를 사실로
기록**하되(D11 체크리스트와 같은 자리) 기본값으로 제안하지 않는다.

### 3.3 D14 보충 — 템플릿이 무엇을 돌고, 누구에게 적용되는가

D6이 치환맵을 비웠으므로 워크플로의 실행 명령은 **리터럴**이다. 그것을 적지 않으면 §1의
"E2E 스위트"(일반)와 D7 · D8 · D9(전부 Playwright) 사이의 비대칭이 남는다. 셋 중 하나다.

| 템플릿이 하드코딩하는 것 | 귀결 |
|---|---|
| Playwright 호출 | 웹 전용이 된다. 비웹 소비자는 이 기능을 받지 않는다 |
| 관례(`make e2e` 등) | 검증도 테스트도 없는 새 플러그인↔소비자 계약. §2가 폐기한 계열이다 |
| 사실상 빈 출발점 | 위와 구분되지 않고, D9(baseURL · trace)가 겨냥할 대상을 잃는다 |

**첫째를 고른다.** 근거 넷, 단단한 순서로.

1. **배달 경로와 정합한다.** D8이 C로 닫히면서 설정 파일의 배달처가 `playwright-scaffold`다.
   그 스킬은 구성상 웹 전용이므로, 설정은 Playwright 스킬이 배달하는데 워크플로만 범용이면
   둘이 어긋난다. 구성 논증이라 다른 셋과 성격이 다르다.
2. **범용을 포기한 대가로 스텝 가드를 얻는다.** 리터럴이 Playwright이면 플러그인이 **설정
   파일의 이름 관례를 알게 된다** — `playwright.config.*`는 Playwright의 설정 해석이 강제하는
   이름이다(§4가 위치를 정당화할 때 쓴 것과 같은 사실). **이 근거는 D14 하나에서 나오고 D8의
   답과 무관하다** — D8이 A였어도 가드는 성립한다. 그러면 `wiki-verify`와 같은 모양의 스텝 가드가 가능하다 — 설정이 없으면 메시지를
   찍고 `exit 0`. 없어지는 것 둘: 스위트 없이 불리언을 켠 소비자의 영구 레드, 실수로 켠 비웹
   소비자의 영구 레드. **D6의 "E2E는 자기-no-op을 가질 수 없다"는 범용 템플릿을 전제한
   서술이었고 D14가 그 전제를 바꾼다** — D6 행에 그 단서를 달았다.
3. **"해당 없으면 끄라"는 어법의 선례가 같은 파일에 있다.**
   `flow-config.example.yaml:127`의 `contract_test` 주석이 "No REST API → enable:false →
   not installed"다. **기본값의 선례는 아니다** — 바로 아래 `:130`이 `enable: true`이고, 그
   주석은 기본값 서술이 아니라 사람에게 끄라고 안내하는 문장이다. e2e 슬롯이 `false`로
   출하되는 근거는 §5(`wiki:105` · `doc_style:116` · `deploy:218` 계열)이고 `:127`에서
   빌리는 것은 **어법**뿐이다. 그 결과 비웹 소비자에게 영구 레드가 생기지 않는다.
4. **비웹에 대한 이 저장소의 자세와 일관된다.**
   `skills/integration/references/non-web.md`가 비웹에 대해 "integration-test automation is
   **not enforced**"라 선언하고(`:3`) 산출물을 **수동 체크리스트**로 둔다(`:54`). 그 스킬의
   `allowed-tools`도 `Bash(npx playwright test *)` 하나뿐이다(`skills/integration/SKILL.md:7`).
   **선례가 아니라 유비다** — non-web.md가 정한 것은 "비웹 통합검증을 어떻게 하나"이지
   "CI 템플릿이 범용이어야 하나"가 아니다. 일관성 논거로만 세우고 이것만으로 결론을 지탱하지
   않는다.

**가드가 덮지 못하는 것, 명시한다.** 근거 2는 두 겹 중 **한 겹**이다 — `wiki-verify`는 스크립트
자체가 설정 없이 `exit 0`하는 두 번째 겹을 갖지만 E2E에는 그것이 없다. 그리고 둘이 남는다.

- 설정이 있고 테스트 파일이 0개면 Playwright가 "no tests found"로 실패한다. 여전히 레드다.
- 가드가 저장소 루트만 보면 설정을 하위에 둔 모노레포 — **D7이 겨냥한 바로 그 경우** — 가
  조용히 초록이 된다. 가드는 테스트 스텝과 **같은 `working-directory`**를 써야 하고, 그 값은
  소비자 편집 지점이다(D10).

§5의 함정(불리언은 렌더 스위치라 `false`로 돌려도 이미 렌더된 파일이 계속 돈다)은 **줄되
사라지지 않는다** — 설정을 지우면 no-op이지만, 설정을 둔 채 멈추려는 소비자에게는 여전히 파일
삭제뿐이다.

**데스크톱 네이티브는 한 겹 더 세다.** REST 백엔드는 템플릿이 임의 명령만 돌릴 수 있으면
되지만, WPF는 리터럴이 브라우저 드라이버라는 것 자체에 걸린다. 합쳐진 범위와 그 귀결은 §9의
첫 항목에 적는다.

**다만 대체가 아니다.** schemathesis는 스키마에서 유도하므로 다중 서비스 시나리오 · DB 상태에
의존하는 순서(생성 → 조회 → 수정 → 삭제) · 인증 시퀀스를 커버하지 않는다. 그것이 E2E가 순증할
자리이고, 이 설계는 그 자리를 **채우지 않는다** — §9에 한계로 남긴다. 채우려면 API 전용
시나리오 저작 가이드가 새로 필요한데, 그것은 `non-web.md`의 판정을 뒤집는 별도 설계다.

## 4. D8 — 결정: 선택지 C (`playwright-scaffold` 확장)

**질문**: 다중 앱 Playwright 설정 파일을 플러그인이 배송하는가.

**결정**: **렌더 경로로 배송하지 않는다.** 그 파일을 이미 소유한 `skills/playwright-scaffold/`를
확장해, 스캐폴드할 때 `projects[]`를 함께 쓰고, 설정이 이미 있으면 필요한 `projects[]` 모양을
**보고**한다.

D7이 팬아웃을 `projects[]`에 위임했으므로 이 기능의 모노레포 가치 전부가 그 설정 파일에
걸려 있다. 배송에는 제약이 둘이었다.

- **위치는 새 예외가 아니다.** 초안은 저장소 루트의 `playwright.config.*`를 `CLAUDE.md:113-114`
  예외 넷(`.gitignore` · `.pre-commit-config.yaml` · `.claude/settings.json` ·
  `.github/workflows/`)에 이은 **다섯 번째**로 서술했으나 그것은 B의 비용을 과대평가한 것이다.
  `skills/playwright-scaffold/SKILL.md:105-113`이 **오늘 이미** 그 파일을 저장소 루트에
  스캐폴드한다 — 렌더 경로가 아니라 스킬 경유일 뿐 위치는 같다. 그리고 그 위치는 Playwright의
  설정 해석이 강제하므로 `.pre-commit-config.yaml`과 정확히 같은 종류로 "external tools force"
  절에 들어맞는다. B는 예외를 **만드는** 것이 아니라 이미 있는 예외에 **이름을 붙이는** 것이다.
  **부수 결함**: 그렇다면 `CLAUDE.md`의 예외 목록은 이미 불완전하다 — 플러그인이 쓰는 다섯 번째
  위치가 문서화돼 있지 않다. E2E와 무관하게 한 줄로 고칠 것.
- **비파괴가 D7의 대상 경우를 항상 스킵한다.** 모든 렌더 경로가 비파괴이고
  `skills/playwright-scaffold/SKILL.md:75`가 케이스가 있으면 보고만 하고 중단하므로, 배송된
  설정은 D7이 겨냥한 바로 그 경우(이미 케이스가 있는 모노레포)에서 늘 스킵된다. 덮어쓰면
  D10과 저장소 전체 관례를 깬다. **이것이 남은 진짜 블로커였다.**

**선택지**:

| | 내용 | 대가 |
|---|---|---|
| A | 설정을 배송하지 않고 `projects[]` 패턴을 문서화만 한다 | D8·D9가 축소되고 남은 결정 전부가 정합해진다. 대신 소비자가 받는 것은 워크플로 하나와 문서 — 리뷰가 반복해서 "얇다"고 한 지점 |
| B | 렌더 경로로 설정을 배송한다 | 위치는 이미 정당화돼 있으므로 남는 것은 충돌 시 동작 하나. skip이면 다수 소비자에게 1일차부터 무의미한 워크플로, 덮어쓰면 소비자 스위트 파괴 |
| **C** | **`playwright-scaffold`를 확장한다** — 스캐폴드할 때 `projects[]`를 함께 쓰고, 설정이 이미 있으면 필요한 `projects[]` 모양을 보고한다 | 아래 |

**왜 C인가**:

1. **새 호스트 쓰기 위치 0개 · 새 `*_DEST` 상수 0개 · `flow_init_setup.py` 변경 0줄.** sibling
   문서가 다루는 렌더 토큰 결함 표면을 아예 건드리지 않는다.
2. **파일의 소유자가 하나로 유지된다.** B는 같은 경로를 렌더러와 스킬이 나눠 소유하게 만든다.
   D9가 고치는 baseURL 드리프트가 정확히 그런 분할에서 나온 것이다.
3. **D7의 대상 경우에서 B와 C의 결과가 같다.** 이미 케이스가 있는 모노레포에서 비파괴 규칙상
   둘 다 "보고"로 끝난다. C는 그 보고를 읽는 사람이 이미 보고 있는 자리에 놓을 뿐이므로,
   B가 더 사는 것이 없다. B와 C의 차이는 "덮어쓸 것인가"가 아니라 "어디서 보고할 것인가"다.
4. **D9가 같은 파일 · 같은 스킬에 떨어진다.** 커밋 하나, 리뷰 하나, 커밋 타입 하나(`feat`).

**C가 지는 비용 둘, 명시한다**:

- **배달이 사람 트리거가 된다.** D6의 불리언이 워크플로를 렌더했는데 `projects[]`가 없는 상태가
  가능하다. 닫는 법은 새 메커니즘이 아니라 한 줄이다 — `/flow-init` 스텝 보고(§5의
  `report_missing_config_slots`가 찍는 그 자리, `flow_init_setup.py:810-812`)가
  `/playwright-scaffold`를 가리킨다.
- **frontmatter `description` 수정이 eval 재측정을 부른다.** 현재 description이 "Not for adding
  scenarios to a project that already has a suite"이고 `evals/cases.yaml:117-119`가 그것을
  negative 케이스로 못박는다. C는 설정이 있을 때 스킬이 **보고라도** 하게 만들므로 문구를 그
  negative가 살아남게 써야 하고, description 바이트가 바뀌면 라이브 재측정 비용이 붙는다.

**C가 풀지 않는 것**: 이미 설정이 있는 소비자는 여전히 파일이 아니라 보고를 받는다. 그것은 C의
한계가 아니라 저장소 전체가 지키는 비파괴 규칙의 귀결이므로 A·B도 같다.

## 5. 배달과 활성화

`/flow-init`의 `run_setup`에 유닛 테스트 스텝 다음으로 한 단계를 추가하고,
`render_unit_test_workflow`가 아니라 `render_wiki_verify_workflow` 쪽 모양을 따른다 —
치환맵이 비어 있고 불리언 하나로만 게이트된다.

**`flow-config.example.yaml`에 슬롯을 추가하는 것이 필수다.** 불리언이 **기존** 소비자에게
알려지는 유일한 통로가 `missing_config_slots`/`report_missing_config_slots`
(`flow_init_setup.py:787-812`, `:1528`에 배선)이고, 이것이 예제 파일의 최상위 슬롯과 호스트
설정을 비교하기 때문이다. 슬롯이 없으면 기능이 존재하되 아무도 모르는 채 배포된다.

슬롯은 `wiki` · `doc_style` · `deploy`와 같이 **`false`로 출하**한다. 백필은 켜지 않는다 —
`skills/flow-init/SKILL.md:247`이 "`enable`-style flags stay as in the example"를 못박는다.

**한계로 기록**: 불리언은 렌더 스위치이지 실행 스위치가 아니다. 나중에 `false`로 돌려도 이미
렌더된 파일은 계속 돈다. 복구는 파일 삭제 후 재실행이다.

## 6. 강제하지 않음 — 정직함의 조건

D13이 참으로 남으려면 이름이 조건이다. `e2e`라는 낱말이 `flow-tiers.yaml`이나
`rules/risk-tiers.md`의 게이트 용어집에 등장하는 순간 "차단하지 않는다"는 명시가 무효가 된다.
배달물은 다른 네 CI 워크플로와 같은 자리에서 같은 어투로 소개한다.

§3.2가 여기에 걸리지 않는다. 호스트가 자기 `flow-config.yaml`의 `checks`에 `e2e`라는 키를
쓰는 것은 **호스트 어휘**이고, D13이 금지하는 것은 **플러그인이 소유한 정책 · 용어집**에 그
이름이 등장하는 것이다. 다만 `USAGE.md`가 그 경로를 적을 때 게이트 이름처럼 보이지 않게 써야
한다 — 그것이 §3.2가 "권하지 않는다"로 끝나는 두 번째 이유다.

**job 이름은 미룰 수 없다.** 필수 상태 체크는 job 이름으로 식별되므로 D11의 체크리스트를
쓰는 시점에 확정돼 있어야 한다.

**D11 체크리스트의 집도 결정 사항이다.** `rules/`는 `hooks/inject-risk-tiers.sh`가 매 세션
`additionalContext`로 주입하므로, 실행 가능한 절차를 거기 두면 "절대 수행하지 않는다"가
사람에 대해서만 성립하고 에이전트에 대해서는 성립하지 않는다. `USAGE.md` 계열에 결과 중심
산문으로 둔다. 위치가 곧 커밋 타입과 ko 쌍둥이 의무와 릴리스 전파를 동시에 결정한다.

## 7. 범위 밖 — `performance` 스킬

`integration`과 `performance`는 쌍둥이다. 둘 다 frontmatter가 "A manual skill, not a gate."
이고 `risk-tiers.md`가 Staging 티어에서 함께 "independent skills"로 부른다. 이 설계는
integration 절반만 CI로 올린다. performance는 수동 스킬로 남긴다.

- **부하 절반은 CI 형태가 아니다.** p50/p95/p99는 SLO 없이 판정이 안 되는데 `flow-config`에
  SLO를 담을 자리가 없다. 2-4 vCPU 공유 러너에서 잰 p95는 코드의 속성이 아니라 이웃 소음이다.
  SLO 설정을 추가하는 순간 §2가 폐기한 config 표면 문제가 되살아난다.
- **정적 절반은 이미 확장점이 있다.** (같은 관찰의 E2E 적용은 §3.2) N+1 grep과 lizard 복잡도는 "종료 코드가 곧 판정" 형태라
  `modules[].checks`의 모양 그대로다. `flow-config.example.yaml:38`이 "Add your OWN keys
  freely"로 열린 어휘를 초대한다. 플러그인 코드 0줄로 오늘 가능하다.
- **측정 가능한 조각은 이미 CI로 나가 있다.** `entropy-check.yml`이 파일 크기와 복잡도를 주간
  cron으로 돌리되 모든 스텝이 `continue-on-error: true`이고 헤더가 `informational`이다.
  저장소가 이미 같은 판단을 내렸다 — 잴 수는 있지만 게이트할 수 없는 것은 정보성 CI로,
  주기 실행으로.

"지금은 아니다"이지 "영원히 아니다"는 아니다. E2E가 CI에서 스택을 띄우면 그 스택이 곧 부하
테스트가 필요로 하는 것이므로, 워크플로의 스택 섹션을 나중에 얹을 수 있게 분리해 둔다.

## 8. 산출물

D8이 C로 닫혔으므로 목록이 갈리는 항목은 없다. 전부 확정이다.

- `github/e2e.workflow.example.yml` — 신규 템플릿(토큰 없음). 실행 명령은 Playwright 리터럴이고
  편집 지점을 마커로 표시한다(D14 · §3.3)
- `scripts/flow_init_setup.py` — 렌더 함수 · TEMPLATE/DEST 상수 · `run_setup` 한 단계 ·
  uninstall 안내 한 줄
- `flow-config.example.yaml` — 불리언 슬롯 (`false`로 출하). 주석은 `:127`의
  "No REST API → enable:false → not installed" 어투를 따른다
- `skills/playwright-scaffold/` — D9. baseURL **값**이 실제로 사는 곳은 **두 자리**다:
  `SKILL.md:98`(기존 config에 추가할 플레이스홀더 `'<the value confirmed in Step 1>'`) ·
  `:112`(스캐폴드 리터럴 `'http://localhost:3000'`). `:83-85`와
  `examples/main.smoke.spec.ts:4`는 "baseURL은 config에 속한다"는 산문 · 주석이라 값을 담지
  않는다 — 넷으로 세면 고칠 자리를 잘못 짚는다. 두 자리의 일치를 검사하는 테스트가 없다
- `skills/flow-init/SKILL.md` — 한 줄. **영어여야 한다** —
  `tests/skills/_helpers.py`의 한국어 리터럴 allowlist가 이 파일에 허용하는 것은
  `"config 슬롯 점검"` 하나뿐이다
- `rules/risk-tiers.md` — E2E는 CI 안전망이며 인간 통합테스트 게이트는 불변임을 한 문단
- `USAGE.md` + `USAGE.ko.md` — 활성화 방법 · D11 체크리스트 · §3.2의 호스트 게이트 경로
  (사실로만). 카피 성격의 산출물에서는 **인간이 곧 활성화 경로**이므로 이 항목이 없으면
  기능이 도달하지 않는다. **비웹 소비자가 받는 것도 한 줄** — `unit-test.yml`(호스트가 정한
  `matrix.test`라 `dotnet test` · `pytest` 무엇이든 된다)과 `api-contract.yml`이 그들 몫이다.
  "기능이 없을 뿐"은 참이지만 읽는 사람에게는 "아무것도 없다"로 읽힌다
- `tests/flow_init/` — 렌더 · 불리언 게이트 · 슬롯 보고
- `evals/` — `playwright-scaffold`의 description을 고치면 재측정. `evals/cases.yaml:117-119`의
  negative 케이스(기존 스위트)가 살아남는지가 통과 조건이다 (§4)

**커밋 타입**: `rules/` · `skills/` · `github/` · `flow-config.example.yaml`은 전부
소비자 대면이므로 `feat`. `docs`/`chore`로는 소비자에게 전파되지 않는다.

## 9. 한계 · 미커버

- **머지 후 신호.** D12가 `pull_request`를 빼므로 기존 두 CI 템플릿과 달리 병합 전에는
  아무것도 보고하지 않는다.
- **경로 필터 없음.** per-suite 설정이 없으므로 트리거 브랜치로의 모든 푸시가 전체 앱 E2E를
  돌린다. **탈출구는 불리언이 아니다** — §5가 적었듯 불리언은 렌더 스위치라 이미 렌더된 파일에
  듣지 않는다. 소비자의 실제 탈출은 렌더된 파일을 지우거나 직접 편집하는 것이고, 그것이 D10이
  말하는 "소비자가 소유하는 출발점"의 다른 얼굴이다. **정정**: 스텝 가드는 E2E도 한 겹 갖는다
  (§3.3 근거 2). 없는 것은 `wiki-verify` · `doc-style`이 가진 두 번째 겹, 곧 스크립트 자체가
  설정 없이 `exit 0`하는 부분이다. 가드가 있어도 설정을 둔 채 멈추려면 파일 삭제뿐이다.
- **dogfood 면제.** 이 저장소에는 브라우저 앞단 앱이 없어 로컬 인스턴스를 둘 수 없다.
  `api-contract.yml`과 8종 deploy 템플릿도 같은 상태이나 어디에도 기록돼 있지 않다. 면제는
  개별 열거가 아니라 "로컬 인스턴스가 성립하지 않는 템플릿"이라는 한 줄 일반 조항으로 적는다.
- **커버 범위는 "Linux 러너에서 도는 Playwright 스위트"다.** D5 · D14 · 템플릿의 `runs-on`
  리터럴이 합쳐진 결과인데, 셋은 각각 적혀 있어도 **합계가 어디에도 없었다**. Windows 데스크톱
  UI(WPF · WinForms)는 범위 밖이다. **러너가 이유는 아니다** — GitHub-hosted `windows-latest`가
  존재하므로 D5가 닫는 것은 self-hosted뿐이고, 결정적 제약은 D14의 리터럴이 **브라우저 드라이버**
  라는 것이다. 그 유형에 대한 이 저장소의 답은 `non-web.md`의 수동 체크리스트이고
  (분류가 웹 프레임워크 부재를 **기본 분기**로 삼으므로 WPF는 배제로 거기 떨어진다),
  자동화를 원하는 소비자의 자리는 `docs/verification/integration.md`다
  (`skills/integration/SKILL.md:23-24`).
- **비웹 소비자는 이 기능을 받지 않는다.** D14의 귀결이다. REST 전용 백엔드에는
  `api-contract.yml`이 있으나 그것은 스키마 유도라 상태 있는 시나리오 · 인증 시퀀스를 덮지
  않는다. 그 구멍은 이 설계가 메우지 않고, `non-web.md`가 수동 체크리스트로 남겨 둔 자리다.
- **템플릿 수정 전파 불가.** D10의 대가이자 sibling 문서의 C3다. 이 기능 단독으로는 못 푼다.

## 10. 이월 결함

리뷰 과정에서 이 기능과 무관하게 오늘 배송 중인 템플릿의 결함 6건을 확인했다. 전부
[`2026-09-08-render-token-substitution-design.md`](2026-09-08-render-token-substitution-design.md)
로 분리했다. 그중 C3(버전 스탬프 부재)은 D10의 대가를 직접 결정하므로, 그 문서가 먼저 처리되면
이 설계의 §9 마지막 항목이 사라진다.
