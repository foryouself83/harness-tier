# performance/integration 스킬 버그 수정 + 언어별 재구성 — Design

- **Date**: 2026-07-06
- **Status**: Approved (brainstorming) → pending implementation plan
- **Scope**: `skills/performance/` · `skills/integration/` (+ `skills/playwright-scaffold/` testMatch 정합화 한정)

## 1. Goal

`/code-review`로 `skills/performance`·`skills/integration`을 심층 분석해 발견한
**11개 CONFIRMED 버그**를 모두 고치고, 그 과정에서 성능 스킬의 `static-checks.md`를
언어/도구 축으로 재구성해 SKILL.md가 감지된 스택에 필요한 파일만 읽도록 한다.
통합 스킬은 Electron을 진짜 3번째 분기로 승격시키고 나머지 구조는 유지한다.

## 2. Background — 발견된 11개 버그 (검증 완료)

| # | 파일:라인 | 결함 |
|---|---|---|
| 1 | `static-checks.md:121` | 재귀 탐지 grep이 `\n`을 라인 단위 매칭 도구에 넣어 항상 0건 |
| 2 | `static-checks.md:118` | 중첩루프 grep — globstar 누락, 깊이 요구조건 오류, 줄번호로 정렬(깊이 아님), 4-space 가정 |
| 3 | `performance/SKILL.md:63` | N+1 탐지 `grep \| xargs grep` — 공백 포함 매치 시 인자가 깨져 사실상 항상 실패 |
| 4 | `integration/SKILL.md:124` | 결과 파싱이 `r.stats` 존재를 가정 — 비정상 종료 시 처리되지 않은 예외 |
| 5 | `integration/SKILL.md:60-67` | Web/Non-web/Electron 3분류인데 실행 분기는 2개뿐 + Electron 예외가 2개 파일에 중복 서술 |
| 6 | `performance/SKILL.md:115-128` | BASE_URL 확인 절차 없음(playwright-scaffold와 "동일 원칙" 주장이 거짓) + curl에 `-o` 누락으로 후속 단계가 참조할 파일이 없음 |
| 7 | `api-load.md:89-121` | "100회/엔드포인트" 약속 대비 2개 예시뿐, N개 엔드포인트용 시나리오 자동 생성 스크립트 없음 |
| 8 | `integration/SKILL.md:91` | 케이스 탐색 `find`가 문서화된 기본 testMatch보다 좁음 + `web-playwright.md`/`playwright-scaffold`와 서로 다른 glob (드리프트) |
| 9 | `performance/SKILL.md:99` | React Compiler 감지 grep이 Vite의 카멜케이스 `reactCompiler` 옵션을 못 잡음 |
| 10 | `integration/SKILL.md:51-58` | non-web 신호 체크에 SSOT(`web-playwright.md`)가 명시한 `go.mod`/`main.go` 누락 |
| 11 | `performance/SKILL.md:19-30` | host 문서(`docs/verification/performance.md`)가 일부 스택만 커버할 때 나머지 스택을 fallback으로 보완하는 규칙 없음 |

## 2a. Addendum — 3 additional bugs found during plan review (not in the original 11)

플랜 문서 작성 중 사용자가 직접 발견하고, k6 공식 문서(`shared-iterations`/`per-vu-iterations`)로 교차 검증한 항목:

| # | 파일:라인 | 결함 |
|---|---|---|
| 12 | `api-load.md` §2.1 워크드 예시 | k6 `per-vu-iterations` executor는 "각 VU가 `iterations`회씩" 실행 → 총 실행 횟수 = `vus × iterations`. `vus:10, iterations:100`이면 실제로는 1000회 실행되어 "100회/엔드포인트" 약속과 모순. `shared-iterations`(전체 VU에 걸쳐 `iterations`가 총량)로 교체 필요 |
| 13 | `performance/SKILL.md:4` | frontmatter `allowed-tools`에 `WebFetch`가 선언되어 있지만 스킬 전체에서 실제로 호출되는 곳이 전혀 없음 (미사용 권한) |
| 14 | `integration/SKILL.md:156` | Non-web `AskUserQuestion` 프롬프트가 "(CLI/RN/Flutter, etc.)"를 하드코딩 — `non-web.md:37`의 원본 템플릿은 이미 `<type>`으로 파라미터화되어 있어, §2에서 감지된 실제 타입을 채워 넣기만 하면 됨 (파일 분리 불필요) |

## 3. Decisions (from brainstorming)

| 질문 | 결정 |
|---|---|
| performance 파일 구조 | `static-checks.md` → 언어/ORM별 분리 (`static-checks-{python,java,ruby,dotnet,node,react}.md`) + DB(`static-checks-db.md`)·복잡도(`static-checks-complexity.md`)는 언어 무관이라 별도 공유 파일로 유지 |
| 중첩루프/재귀 탐지 | 버그투성이 grep 폐기 → **lizard**로 교체 (다국어 지원, 이미 카탈로그에 존재) |
| N+1 xargs 파이프 | grep 기반 유지, `comm -12 <(grep -rl ...) <(grep -rl ...)` 로 안전하게 수정 (ORM별 세부 패턴은 언어별 분리 파일에 그대로 유지) |
| k6 시나리오 생성 | OpenAPI spec의 (method, path, operationId) 목록을 파싱해 `scenarios` 객체를 자동 생성하는 Node 스크립트를 `api-load.md`에 추가 |
| host-doc 부분 커버리지 | 이번 수정 범위에 **포함** — SKILL.md §1에 "host 문서가 언급하지 않은 감지된 스택은 fallback 카탈로그로 보완" 규칙 추가 |
| integration Electron 분기 | `SKILL.md`에 독립 `## 4. If Electron` 섹션 신설 (Web 절차의 렌더러 자동화 + Non-web 절차의 메인프로세스 human-in-the-loop 조합), 이후 섹션 번호 한 칸씩 밀림 |
| integration 파일 분리 범위 | **Electron만** `references/electron.md`로 분리 (하이브리드 절차라 자기 파일이 자연스러움). CLI/RN/Flutter는 동일한 human-in-the-loop 절차를 공유하므로 `non-web.md`에 표 형태로 유지 (과잉 분할 방지) |
| 케이스 탐색 `find` 정합화 | `SKILL.md`·`web-playwright.md`·`playwright-scaffold/SKILL.md` 3곳의 glob을 문서화된 testMatch 파생 패턴으로 통일 |

## 4. 최종 파일 구조

```
skills/performance/
  SKILL.md                              (디스패처로 축소 — 감지된 스택에 맞는 파일만 안내)
  references/
    static-checks-python.md             (N+1: Django, SQLAlchemy)
    static-checks-java.md               (N+1: Hibernate)
    static-checks-ruby.md               (N+1: Rails)
    static-checks-dotnet.md             (N+1: EF Core)
    static-checks-node.md               (N+1: Prisma, TypeORM)
    static-checks-react.md              (프런트엔드 리렌더링, reactCompiler 감지 버그 수정)
    static-checks-db.md                 (DB 쿼리플랜 — DB 엔진 기준, 언어 무관)
    static-checks-complexity.md         (lizard 기반 복잡도/중첩루프/재귀 탐지 — 언어 무관, 런타임 프로파일러 표)
    api-load.md                         (BASE_URL 확인 절차 추가, k6 시나리오 자동생성 스크립트 추가, 파일 경로 통일)

skills/integration/
  SKILL.md                              (§4 If Electron 신설, find glob 정합화, go.mod 신호 추가, r.stats 방어)
  references/
    web-playwright.md                   (find glob 정합화)
    electron.md                         (신설 — Electron 렌더러+메인프로세스 절차, 유일한 SSOT)
    non-web.md                          (Electron 중복 서술 제거 → electron.md 링크로 대체, CLI/RN/Flutter는 유지)

skills/playwright-scaffold/
  SKILL.md                              (idempotency glob을 동일 testMatch 패턴으로 정합화)
```

## 5. 위험 요소 및 하위 호환

- 파일을 쪼개면서 `SKILL.md`의 "§2.x 요약 vs references 상세"라는 기존 참조 관계를 유지해야 한다 — 각 신규 파일 생성 후 `SKILL.md`의 참조 링크를 전부 갱신.
- lizard로의 교체는 "lizard가 설치되어 있어야 함"이라는 새 전제를 추가하므로, `static-checks-complexity.md`에 설치 안내(이미 카탈로그에 존재하는 `pip install lizard` 등)를 명시.
- Electron 분기 신설로 §번호가 밀리므로, `SKILL.md` 내부의 다른 상호참조(`§3`, `§4` 언급)도 함께 갱신 필요.

## 6. Out of scope

- CLI/React Native/Flutter의 개별 파일 분리 (동일 절차 공유, 과잉 분할 판단)
- N+1 탐지를 semgrep/ast-grep 같은 AST 기반 도구로 전면 교체 (사용자가 grep 유지 결정)
- playwright-scaffold의 baseURL 감지 로직 자체 변경 (find glob 정합화만 범위)
