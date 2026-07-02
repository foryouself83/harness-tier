# Harness Generation Rules

> 이 룰은 자동 주입되지 않는다(risk-tiers.md 와 다름). `/harness-init`·
> `harness-authoring` 스킬이 실행 시점에 defer 해 읽는 SSOT.

## 안전
1. **검증→계획→미리보기→확정→쓰기.** 어떤 파일도 미리보기·확정 전 쓰지 않는다.
2. **덮어쓰기 금지.** 기존 파일은 마커블록 upsert(전용 영역)만. create 는 부재 시만.
3. **harness-init 은 커밋하지 않는다**(/vdev 책임).
4. **모호하면 질문**(Karpathy). 프레임워크 미감지·충돌 시 사용자에게 묻는다.
4-1. **편입 사본 cleanup**: apply 성공 후 docs 로 편입된 중간 사본(`.harness/research/` 등)은
   `harness_scaffold.py cleanup` 으로 제거한다. 감사용 증거(`plan.json`·`manifest.json`·
   `critic-report.json`·`rationale.md`)는 보존. FAIL-OPEN(정리 실패는 흐름을 막지 않는다).
   **링크 가드(FAIL-SAFE)**: 문서 출처 링크는 편입 위치 `docs/research/` 를 가리키고 `.harness/` 를
   참조하지 않는다. cleanup 은 제거 전 docs 가 `.harness/research` 를 참조하는지 검사해, 참조가
   있으면 제거를 보류하고 경고한다(링크 깨짐 방지).

## 산출물
5. **.md 기본**, 실설정(bandit·CI·pre-commit·실폴더·실제 ==핀)은 항목별 opt-in.
5-1. **스킬 보조폴더**: 스킬 생성 시 역할상 참조/사례가 있으면 `references/`·`examples/` 를 동반한다(YAGNI — 단순 스킬엔 강제 안 함).
6. **필수 룰 5종 항상 주입**: Karpathy 4원칙 + DRY/상수 + ==버전핀 + 보안 + **reuse-first**
   ([rule-reuse-first.md](../skills/harness-authoring/references/rule-reuse-first.md)).
   **로드경로 보장** — CLAUDE.md 본문/명시 import(`.claude/rules/` 단독 금지). 앵커 `<!-- rule:<key> -->`
   (key: `karpathy`·`dry-constants`·`version-pinning`·`security`·`reuse-first`)는 **claude-md 템플릿이 소유**해
   baseline 마커블록에서 각 룰 슬롯 앞에 둔다. 룰 reference 본문 파일엔 앵커를 넣지 않는다(중복 금지).
7. **중복 생성 금지**: name+description 으로 기능 중복 확인.
8. **기술문서(분류별 폴더)**: `docs/README.md`(전체 인덱스·마지막) · `docs/srs/`(기능/비기능
   요구사항·greenfield 전용·가장 먼저) · `docs/sds/`(구조 + **Mermaid 필수**; 컴포넌트가
   경계(프로세스/오리진/호스트/인증)를 넘어 통신하면 **통합 지점 계약** 절 포함) ·
   `docs/code-style/`(스택별 `<stack>.md`, 코드 스니펫 제외, 툴체인 설정 한 세트) ·
   `docs/research/`(편입, 출처 링크) · `docs/onboarding/`(실행/디버그 + 주요 문서 링크·마지막) ·
   `docs/performance.md`(스택별 성능 SSOT — N+1·프로파일러·쿼리플랜·API 부하, 확정 스택만·빈 절 금지) ·
   `docs/integration.md`(스택별 통합 검증 SSOT — 웹=Playwright·비웹=human-in-the-loop, 확정 스택만·빈 절 금지).
   진입 문서는 `README.md`. 구조적 컨벤션은 룰, 행위적 스타일은 문서 — **한 사실 한 곳**.
   **모든 문서는 참조 출처를 링크로** 단다.
8-1. **SRS 범위 명확화 게이트(greenfield 전용·추측 금지)**: greenfield/SRS 산출물 시 리서치·SRS 작성
   **전에** 받은 프롬프트를 파싱해 개발 범위를 확정한다. SRS 필수 슬롯(목적·목표/비목표·핵심 기능
   요구사항·대상 사용자/시나리오·핵심 제약)에서 **공백 + 모호한 항목을 모두** `AskUserQuestion` 으로
   묻는다 — **모호 = 측정 불가·복수 해석 가능·범위 불분명**(예: "빠르게"·"사용자 친화적"). **측정 가능
   하고 단일 해석이 될 때까지** 묻되 이미 명확한 건 되묻지 않는다(모호함은 요구 분석 미완의 신호 —
   SRS 단계에서 해소한다). 추가로 **분류 축**(도메인 등 1차, 사용자권한/하위영역 등 2차)과 **깊이
   (2~3차)** 가 무엇인지도 확정한다 — 어떤 축이 적용되는지 질문하고, 적용 안 되는 축은 SRS 에서
   삭제하지 말고 "해당 없음 — 사유"로 남긴다(누락과 구분 — 9-2 와 동형). 질문 후에도 미상이면 SRS 에
   "확인 필요"로 명시한다(지어내기 금지·rule 4). 산출 **범위 요약(scope summary)** 은
   research·rationale·SRS 의 단일 입력원이다. brownfield 는 이 게이트를 건너뛰고 범위를 code-analyzer
   코드 분석으로 삼는다(코드로 안 풀리는 의도만 선택 질문).
9. **커맨드 미생성**: 어떤 산출물도 `.claude/commands/`에 만들지 않는다(revfactory 정렬).

## 운영 컨벤션 (operational conventions)

9-1. **운영 관심사 체크리스트(누락 금지·열린 목록)**: 감지된 스택에 대해 researcher/
   code-analyzer 는 다음 *관심사 축*을 **전수 검토**한다(언어/프레임워크 무관). 닫힌 floor 가
   아니라 **흔한 출발 축** — researcher 가 스택 특성상 더 추가한다.
   에러/예외 처리 · 로깅(디버깅 지향: 레벨 규칙·디버깅 컨텍스트·구조적/검색가능·시크릿/PII 금지) ·
   설정·시크릿·env · 관측성(메트릭/트레이싱) · 헬스체크/레디니스 · 그레이스풀 셧다운 ·
   입력 검증 · 인증·인가 · 재시도/타임아웃·서킷브레이커 · 데이터 마이그레이션/스키마 진화 ·
   rate limiting.
9-2. **emit 은 증거 기반**: 커버리지는 필수이되, 각 축은 그 스택에 **관심사가 실재할 때만 emit**
   한다(정적 사이트에 헬스체크/셧다운 강제 금지). 적용성 **불확실** 시 지어내지 말고 Step 6
   미리보기에서 사용자에게 묻는다(과생성 방지 — FAIL-OPEN 은 "스킵+질문" 방향).
9-3. **directive 는 룰, 살은 문서**: 운영 directive(1~3줄 지시)는 `.claude/rules/
   <framework>-conventions.md` 의 `<!-- ops-conventions -->` 앵커 절에, 표준 상세·매핑·안티패턴·
   예제·**출처 URL(SSOT)**·대안은 `docs/code-style/<stack>.md` "운영 관심사" 섹션에 둔다.
   룰은 문서를 링크하고 같은 사실을 복제하지 않는다(한 사실 한 곳).
9-4. **표준 선택(단정 회피)**: brownfield 는 code-analyzer 가 코드에서 쓰는 표준을 감지해 명시.
   greenfield/미확정은 researcher 가 **현재 권장 최신 표준을 자동 채택(묻지 않음)** 하되, 구체
   표준명은 **문서에** "권장(변경 가능)+출처+대안"으로만 두고 룰엔 카테고리 directive 만 둔다.
9-5. **보안성 축 승격 경로**: 시크릿·인증/인가·입력 검증처럼 강제력이 필요한 축은 directive 한
   줄로 끝내지 말고, harness-init Step 1 의 **실설정 opt-in**(secret scanner·linter)을 제안한다
   (동의 시에만). "정책" 강제 착시 금지 — 진짜 강제는 탐지 도구로.
9-6. **모든 확정 스택이 컨벤션 대상(reuse 아티팩트 ≠ 스택)**: reconcile(10-1)로 확정된 *모든* 스택은
   컨벤션을 받는다(구조/상세 SSOT 분리는 9-3 따름 — 여기서 복제하지 않는다). 특히 인프라(DB·캐시·큐·
   컨테이너/이미지·CI/CD·IaC·클라우드)는 reuse 아티팩트로만 끝내기 쉬우니, 컨벤션(BP·안티패턴·운영 축)이
   **실재하면** 스택으로 승격한다(없으면 reuse 후보로만 — 9-2 증거 기반).

## 다중 에이전트 / 비판
10. **리서치는 `Agent`(구 `Task`, alias) 서브에이전트 fan-out**(researcher + 브라운필드 시 code-analyzer) 을 병렬 디스패치·팬인.
    교차대화는 Agent Teams 실험 기능(`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`)이 켜진 경우만 `SendMessage` 로(옵션).
    폐기 도구(`TeamCreate`·`TaskCreate` 등) 금지. 네트워크/디스패치 실패는 FAIL-OPEN(경고 + 선택), 지어내지 않는다.
10-1. **스택 인벤토리 reconcile(동결 전 수렴 — 누락 방지)**: `stack_map` 은 인터뷰에서 *잠정*
    확정하고, 리서치(researcher 자율확장·기성솔루션·스택 호환성 매트릭스)가 드러낸 (인프라 포함)
    스택을 authoring **전에** `stack_map` 에 병합한다. 컨벤션이 실재하는 스택(인프라가 특히 누락되기
    쉬움)은 컨벤션 대상으로 승격하고(9-6), 새로 승격된 스택은 1차 fan-out 에서 (계층,스택)으로
    디스패치되지 않았으므로 **타깃
    후속 리서치**(해당 스택 ops_axes 전수)를 돌려 컨벤션을 채운다. 스택 집합이 **안정될 때까지 반복**
    (보통 1회). **추측으로 스택을 늘리지 않는다** — 발견 근거가 있는 것만. 승격/기각 결정·사유는 authoring 이
    `docs/sds/README.md` 에 한 줄씩 **남기고**(미리보기에서 다른 산출물과 함께 사용자 확정) —
    버전관리되는 결정 출구(rationale 중복 아님).
11. **사유 작성**: research 종합 후 `.harness/rationale.md`(산출물별 생성 근거·채택 패턴·reuse 권고·출처).
12. **경량 비판**: `validate`(결정적 구조) → `harness-critic`(품질·정합성·reuse 위반·커맨드 미생성).
    재작성 최대 2회, 잔여는 "미해결"로 미리보기/보고에 명시(차단 금지).
12-1. **버전 호환성(`version-compat`) — 두 축**: (a) **설정 작성 정합** — 툴체인을 한 세트로 보고
    감지된 실제 버전의 공식 작성법과 산출물 정합성을 검증한다(빌드↔설정, 예: `tsc -b`↔references).
    (b) **런타임 조합 호환** — 한 런타임에 함께 올라가는 구성요소(앱 프레임워크 ↔ 플러그인/스타터/
    엔진/이미지)가 **함께 GA-호환되는 최신 집합**인가, 그리고 추천한 기성 아티팩트가 가정한 기능을
    **실제로 제공**하는가. **만들 때**는 설정을 추론하지 말고 감지된 프레임워크의 **공식 스캐폴더
    출력을 복제**해 baseline 으로 삼는다(reuse-first 의 설정판). researcher 는 설정 방법을 버전별로
    수집하고 프레임워크 특성상 필요한 항목을 자율 확장한다.
12-2. **최신 ≠ 독립 최신(천장 우선)**: **버전을 선택할 때**(greenfield·미확정·의도적 업그레이드)
    researcher 는 각 구성요소의 독립 최신을 따로 고르지 않는다. 플랫폼 major 를 가두는 **앵커(천장)
    의존성**을 식별하고 그 앵커가 **GA 로 지원하는** 최신 버전 집합으로 고른다(함께 GA-호환 안 되면 가장
    늦게 따라온 것에 맞춰 내림; 프리릴리스·미배포 의존에 본체를 맞추지 않는다). 산출에 **스택 호환성
    매트릭스**(구성요소→버전→천장 제약→출처)를 남긴다. 9-4 의 "최신 표준 자동 채택"은 이 천장 제약 안에서만
    적용된다. (brownfield 의 *검출된* 버전 조합이 GA-호환되는지의 점검은 선택이 아니라 검출이므로 12-1(b)
    가 담당한다 — 7-1·critique-guide(B)는 이 selection 부분을 인용한다.)

## 버전/릴리스 컨벤션 리서치

13. **릴리스 도구 리서치(감지 스택별)**: Step 2 리서치 시 감지 스택의 표준 릴리스 도구를 조사해
    `vdev-config.versioning.release_tool`·`version_files` 후보를 제안한다.
    스택별 기본 후보:
    - Python → `python-semantic-release`
    - Node/TypeScript → `semantic-release`
    - Rust → `cargo-release`
    - Go → `goreleaser`
    - 기타 → researcher 가 생태계 표준 조사 후 근거와 함께 제안
    (스택이 없거나 불확실하면 지어내지 말고 "확인 필요"로 둔다 — rule 4.)
13-1. **`commit-versioning-guide` 생성(기술문서)**: Step 4 authoring 에서
    `docs/operations/commit-versioning-guide.md` 를 생성한다. 내용:
    - Conventional Commits + SemVer 기본 설명(출처 URL 필수)
    - 감지 스택의 릴리스 도구 설정(버전 파일·changelog·CI 훅 — 스택 미확정이면 "확인 필요")
    - **0.x 프로젝트** 권장: `major_on_zero=false` + annotated 태그(우발적 1.0.0 승격 방지)
    - 버전 확인 명령(예: `git describe --tags`, 도구별 dry-run 명령)
    - **티어·커밋 규율 자체는 [risk-tiers.md](risk-tiers.md) 로 defer** — 여기서 직접 emit 금지.
    문서 출처는 `docs/research/` 로 링크(`.harness/` 경로 참조 금지, harness-rules 4-1·8).
13-2. **opt-in 분기(vdev 감지 여부)**:
    - **vdev 미감지** — 릴리스 도구 설정(CI 워크플로·훅 등)을 opt-in 으로 제안한다
      (사용자 동의 시에만 실설정 파일 생성 — rule 5 실설정 opt-in 동일).
    - **vdev 감지** — `/vdev-init` 이 `vdev-config.contract_test` 등 워크플로를 렌더하므로
      릴리스 도구 실설정 중복 생성 금지. `commit-versioning-guide` 문서 생성은 vdev 감지 여부
      무관하게 항상 진행한다(코드스타일+컨벤션 문서 범위 — rule 14 의 defer 대상이 아님).

## vdev 공존
14. **vdev 감지(.claude/vway-kit/config/vdev-config.yaml)** 시 프로세스·커밋·머지·PR 규율은
    [risk-tiers.md](risk-tiers.md) 로 defer. 하네스는 코드스타일+프레임워크 컨벤션만 emit.
14-1. **사전검사 도구·폴더구조는 SSOT 가이드(강제는 vdev 몫)**: 하네스는 `docs/code-style/<stack>.md`
    툴체인 설정 섹션에 언어/스택별 사전검사 도구 목록(lint/format/typecheck/import_lint/security/test runner)과
    tests/ 폴더 구조를 SSOT 로 기록한다 — `/vdev-init` 이 `vdev-config.modules[].checks` 초안을 작성할 때
    이를 참조한다. 단 하네스는 *가이드(기술 스택 정보)* 만 하고, 실제 게이트 강제(checks 실행·차단)는
    vdev 의 몫이다(rule 14 defer 연장). `harness_scaffold.py` 의 stack_map/스캐폴드 로직은 여기서
    변경하지 않는다.
15. **settings.json 훅 건드리지 않음**(게이트 아님). 보안은 워크플로/pre-commit 파일로만.
