# 기술문서 작성 가이드

`harness-authoring` 이 호스트 프로젝트용 기술문서를 생성할 때 따르는 규율.

## 폴더 구조 (분류별)

문서는 분류별 폴더에 두고 진입 문서는 `README.md` 로 한다(GitHub 폴더 렌더링 친화적).

```text
docs/
  README.md                  전체 인덱스 · 가장 마지막 작성(다른 문서를 링크)
  srs/README.md              기능/비기능 요구사항 · greenfield 전용 · 가장 먼저 작성
  sds/README.md     구조 + Mermaid 구조도(필수)
  code-style/
    README.md                스택 인덱스 + 공통 원칙
    <stack>.md               스택별 컨벤션(스니펫 제외)
  research/
    README.md                리서치 요약 인덱스
    <topic>.md               .harness/research/ 에서 편입(출처 링크)
  onboarding/README.md       실행/디버그 + 주요 문서 링크 · 가장 마지막 작성
```

**작성 순서**: `SRS → research편입 → SDS → code-style → onboarding → docs/README`.
research 는 SDS·code-style 의 **입력(근거)이므로 먼저 편입**한다(그래야 두 문서가 이미
편입된 `docs/research/` 를 출처로 링크할 수 있다).
**기존 `docs/` 관례 존중**: 이미 다른 구조(`documentation/` 등)면 그쪽을 우선하고 누락 분류만 추가한다.
**SRS 는 greenfield 전용** — brownfield 에선 SRS 를 만들지 않는다.
**출처 링크 의무** — 모든 문서는 참조한 research 문서/외부 URL 을 마크다운 링크로 단다. 근거 없으면 "출처 미확인".

## SSOT 분리 (중복 금지)

- **구조적 컨벤션**(폴더/스키마 위치) → `.claude/rules/<framework>-conventions.md`(룰).
- **행위적 가이드**(네이밍·포맷·BP·안티패턴·툴체인 설정) → `docs/code-style/<stack>.md`(문서).
- 룰이 문서를 가리키되 내용을 복제하지 않는다.

## SRS (greenfield) — srs/README.md

`srs.template.md` 를 채운다. **범위 요약(harness-init Step 1-0 의 scope summary)을 SSOT 로** 채우고
research 로 보강한다. 미상 슬롯은 추측하지 말고 "확인 필요"로 둔다(harness-rules 8-1 — 공백뿐 아니라
모호 항목도 작성 전 질문으로 해소). **두 레벨로 분리**: 고객 요구(§4)는 측정가능하진 않아도 무엇을
원하는지 명확하게("편했으면" ✗ → "카드·간편결제 지원" ✓), 기능 요구사항(§5, FR)은 측정 가능·단일 해석.

**계층 분류(고정 스키마)**:
- **고객 요구(§4)** — 고객/이해관계자가 원하는 것을 `C-x` 로. 각 C 에 `<a id="c-xxx">` 앵커. §5 FR 이
  `(← [C-x])` 로 역참조해 고객요구→FR 추적 원천이 된다. **외부 고객/이해관계자가 없으면(개인·내부 도구)
  "해당 없음 — 단일 이해관계자"로 두고 생략한다(빈 의례 금지)**.
- **기능 요구사항(§5)** — `도메인(1차) > 사용자권한/하위영역(2차) > 개별 FR(3차)`. 각 FR 은
  `ID · 설명 · 우선순위(P0/P1/P2) · 수용 기준(측정 가능)`이며, **각 FR 에 `<a id="fr-xxx">` 앵커를 달아
  SDS 모듈 개요가 링크로 역추적하게 한다**. 출처 고객 요구가 있으면 `(← [C-x])` 역참조. 적용 안 되는
  축은 삭제하지 말고 "해당 없음 — 사유".
- **비기능 요구사항(§6)** — ISO/IEC 25010 정렬 고정 하위축: 성능·보안·가용성·확장성·접근성·유지보수성·호환성.
  각 축은 정량 기준 또는 "해당 없음 — 사유"(빈칸 금지).
- **사용자/시나리오(§3)** — 사용자 권한(role)별로 분류해 기능의 권한 축과 연결한다.

## SDS — sds/README.md

스택/버전 + 폴더 구조 + **Mermaid 구조도(필수, 최소 1개)** + 모듈 개요.
확인된 사실만 노드화한다(추측 노드 금지). 가능하면 데이터 흐름 다이어그램을 추가한다.
**모듈 개요**: 구조도의 각 노드를 구현 단위로 한 단계 내려 `구현 요구사항·책임(단일)·제공 인터페이스·
사용 인터페이스·소유 데이터`를 적는다(아키텍처=노드, SDS=노드의 계약). **구현 요구사항은 이 모듈이
충족하는 SRS FR 을 마크다운 링크로 역추적한다** — SRS 의 FR 앵커로 `[FR-xxx](../srs/README.md#fr-xxx)`
(SRS 의 `<a id="fr-xxx">` 앵커와 쌍으로 유지, 표준 Requirements Matrix 역할). **단 brownfield(SRS 미생성)는
이 필드를 생략하고, 인프라/횡단 모듈(로깅·설정·DB어댑터)은 "FR 매핑 없음"으로 둔다**(억지 매핑·죽은 링크 금지).
제공/사용 인터페이스는 UML provided/required 분리 — 제공=외부에 노출하는 계약, 사용=동작에 필요한 외부
계약(내부 다른 모듈 + 외부 시스템, = 의존의 구체화). **분해 축**: 절차적·데이터 파이프라인·함수형 프로젝트는
모듈 대신 처리 단계·데이터 흐름을 1차 단위로 쓴다. 클래스/타입 상세는 인터페이스에 흡수. 단일 모듈이면 1개만(YAGNI).
**데이터 설계(DB 있을 때만)**: 모듈↔데이터 연계·트랜잭션 경계만. 스키마 상세는 코드/마이그레이션이
SSOT — 복제 금지. DB 없으면 절 생략(YAGNI). **UI 흐름(UI 있을 때만)**: 화면 전이·상태·주요 액션
(스크린샷 제외, 흐름만). UI 없으면 생략. **예외 처리·에러 핸들링은 SDS 에 두지 않는다** —
`docs/code-style/<stack>.md` 의 error-handling 소섹션이 SSOT(9-1), 중복 금지.
**통합 지점(다중 컴포넌트)**: 컴포넌트가 경계(프로세스/오리진/호스트/인증)를 넘어 통신하면 `## 통합 지점`
절에 통신 쌍별 계약을 명시한다 — 도달성(호스트/라우트 해석)·identity/오리진 일치(issuer·CORS)·정책
연속성(보안 헤더/CSP 가 흐름을 막지 않고 전 응답 경로 유지)·자격증명 프로비저닝·전역 설정 blast radius.
research 가 제공한 통합 요구를 반영하고 출처를 단다. **단일 프로세스면 생략**(YAGNI — 없는 경계를 지어내지 않는다).
**스택 reconcile 결정 절**(harness-rules 10-1): 리서치에서 승격/기각된 (인프라 포함) 스택과 사유를 한
줄씩 남긴다 — 버전관리되는 결정 출구(gitignored 인 `.harness/rationale.md` 의 중복이 아니라, 그 핵심
결정만 doc 으로). 승격/기각이 없으면 절 생략.
**모듈 분할(조건부)**: 기본은 `sds/README.md` 단일 파일. 모듈이 다수로 확정된 큰 프로젝트만 `sds/<module>.md`
로 분할하되, 공통 `README.md` 는 인덱스 + 전체 구조도 + 통합/reconcile 만 두고 모듈 개요 본문은 모듈 파일이
SSOT(양쪽 중복 금지). greenfield 초기 모듈 미확정이면 분할하지 않는다(조기 고착 금지 — 구현하며 확정 후 분할).

## code-style — code-style/README.md + <stack>.md

- 스택별로 파일을 나눈다. 파일명 = `<language>` 또는 `<language>-<framework>`(또는 플랫폼).
  예: `typescript-react.md`·`python-fastapi.md`·`go.md`. **같은 언어여도 프레임워크/플랫폼이
  다르면 분리**(강조점이 달라 한 파일로 묶으면 둘 다 얕아진다). **인프라도 컨벤션이 실재하면 스택으로
  파일을 둔다**(예: `docker.md`·`postgresql.md`·`github-actions.md`) — Step 2.5 reconcile 로 승격된
  스택 포함(harness-rules 9-6). 대상은 초기 stack_map 이 아니라 **reconcile 확정 집합 전체**다.
- 각 `<stack>.md` 는 네이밍·포맷·임포트 / 베스트 프랙티스 / 안티패턴(바퀴 재발명 포함) /
  툴체인 설정 / reuse 후보를 **산문으로 상세히** 쓴다. **코드 스니펫은 넣지 않는다**.
- **툴체인 설정은 한 세트로** — 빌드러너·컴파일러·번들러·타입체커·린터·테스트러너의 상호
  정합성(예: `tsc -b`(references) ↔ 번들러 include scope)을 함께 기술한다. 감지된 버전의
  공식 작성법을 출처와 함께.
- **사전검사 도구 목록 명시(필수)** — `/vdev-init` 이 `vdev-config.modules[].checks` 초안을 작성할 때
  이 SSOT 를 참조한다. 툴체인 설정 섹션 안에 다음 축을 **언어/스택별로** 명시한다:
  - **lint**: 코드 품질 린터 (예: ruff, eslint, golangci-lint)
  - **format**: 포맷터 (예: ruff format, prettier, gofmt)
  - **typecheck**: 타입 검사 도구 (예: mypy, tsc --noEmit, go build)
  - **import_lint**: 임포트 질서 도구 (예: isort, import-sort, goimports) — 없으면 "해당 없음"
  - **security**: 정적 보안 스캐너 (예: bandit, semgrep, govulncheck) — 없으면 "해당 없음"
  - **test runner**: 테스트 실행 명령 (예: pytest, vitest, go test)

  각 도구는 **현재 권장 버전(research 확인)·실행 명령·설정 파일 위치**를 함께 적는다. 이 목록이 없으면
  `/vdev-init` 이 초안 checks 를 추론에 의존하므로 반드시 명시한다.
- **폴더 구조(tests/ 위치 명시)** — 테스트 폴더 위치·규약(예: `tests/unit/`·`tests/integration/` 분리 여부,
  파일명 패턴 `test_*.py`·`*.test.ts`)을 툴체인 설정 섹션에 함께 기술한다. 모듈이 여러 개면 각 모듈의
  tests/ 위치를 명시(예: `packages/<module>/tests/`). `/vdev-init` 이 모듈 경계와 test 경로를
  매칭할 때 이 정보를 사용한다.
  단, **이 항목은 가이드(SSOT 기록)이지 게이트 강제가 아니다** — 강제는 vdev(harness-rules 14-1) 몫.
- **현재 권장 도구 기준** — 패키지 매니저·빌드 등 도구는 학습된 과거 표준이 아니라 research 가
  확인한 **지금 권장되는 것**을 적는다(생태계 표준은 이동한다 — 관성적 기본값으로 되돌리지 말 것).
- `code-style/README.md` 는 스택 목록 링크 + 공통 원칙(출처 표기 등)만 둔다.
- **운영 관심사 섹션**(9-1~9-4): 각 `<stack>.md` 에 운영 축별 소섹션(`## error-handling` 등)을 둔다.
  소섹션엔 **채택 표준(권장 기본/감지됨)·매핑·안티패턴·예제·대안**과 **출처 URL(SSOT)**. greenfield
  미확정 표준은 "권장(변경 가능)"으로 표기. 구조적 지시(룰)는 여기 복제하지 않고 룰이 이 섹션을
  앵커(`#error-handling`)로 링크한다. emit 은 그 스택에 실재하는 축만(9-2).

## research — research/README.md + <topic>.md

`.harness/research/*.md` 를 사람이 읽을 수 있게 정제(출처 링크 추가)해 `docs/research/` 로 편입한다.
`research/README.md` 는 조사 항목 요약 인덱스. **다른 문서가 research 를 출처로 링크할 때는 편입
위치 `docs/research/` 를 가리킨다 — gitignored 증거인 `.harness/` 경로를 산출물에 절대 넣지 않는다**
(편입 후 `.harness/research/` 사본은 init 의 cleanup 이 정리하므로 `.harness/` 링크는 깨진다).

## onboarding — onboarding/README.md (가장 마지막)

실행/디버그 + **"처음 온 사람을 위한 주요 문서 링크"** 절(SRS·SDS·code-style·research 로의 링크).
vdev 감지 시 커밋·PR 규율은 risk-tiers 로 defer(여기 중복 금지). 다른 문서가 다 작성된 뒤 마지막에 쓴다.

## performance — docs/performance.md

harness-researcher 의 `### 성능 SSOT (스택별)` 절을 소비해 생성한다.

- **목적**: `/performance` 스킬이 우선 소비하는 스택별 성능 SSOT. 부재 시 스킬 내장 references 폴백.
- **구조**:
  - 스택별 절(`## <스택>`) — N+1 탐지 도구·프로파일러·정적 복잡도·쿼리플랜 절차·출처 링크.
    확정 스택만 작성; 빈 절 금지.
  - 공통 API 부하 절(`## API 부하 공통`) — openapi-to-k6+k6(AGPL-3.0) 1순위 /
    MIT 폴백(oha/autocannon/vegeta) / 리포트 표준(p50/p95/p99·SLO PASS/FAIL·Four Golden Signals).
  - 출처는 `docs/research/` 로 링크. 직접 `.harness/` 경로 참조 금지.

## integration — docs/integration.md

harness-researcher 의 `### 통합 검증 SSOT` 절을 소비해 생성한다.

- **목적**: `/integration` 스킬이 우선 소비하는 통합 검증 SSOT. 부재 시 스킬 내장 references 폴백.
- **구조**:
  - 스택별 절(`## <스택>`) — 웹이면 Playwright 설정(testDir/testMatch·`--reporter=json`),
    비웹이면 human-in-the-loop + 참고 OSS(Newman/Maestro/Appium). 확정 스택만; 빈 절 금지.
  - 공통 E2E 절(`## E2E 공통`) — 케이스 0개 시 임의 생성 금지·사람 보고, playwright MCP 보조 경로.
  - 출처는 `docs/research/` 로 링크.

## 공통 규율

- **출처 표기** — 리서치/스캔 근거를 단다. 없으면 "출처 미확인".
- **간결** — 항목당 1-2줄. 장황한 설명보다 구체.
- 문서는 사람과 에이전트 양쪽이 읽는다 — 명확하고 스캔 가능하게.
