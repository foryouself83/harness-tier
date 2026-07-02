---
name: performance
description: 코드베이스의 언어별 성능 안티패턴(N+1·쿼리플랜·재귀/복잡도·프론트 리렌더)을 정적으로 플래깅하고, 백엔드가 있으면 OpenAPI에서 API를 추출해 openapi-to-k6+k6로 각 API를 100회 부하 측정해 p50/p95/p99·throughput·에러율을 SLO 대비 보고한다. 게이트가 아닌 수동 스킬 — 성능 점검이 필요할 때 호출.
allowed-tools: Bash, Read, Grep, Glob, WebFetch
---

# performance

코드베이스의 **성능 안티패턴을 정적으로 플래깅**하고, 백엔드가 있으면 **API 부하 측정**을 수행한다.
게이트가 아닌 수동 스킬이다 — `/vdev` 게이트에 묶이지 않는다.

> **포지셔닝**: 이 스킬은 정적 코드 분석으로 **의심 패턴을 플래깅**하는 것이지, 확정 탐지가
> 아니다. 런타임에만 알 수 있는 결과(실측 지연·N+1 횟수·메모리 사용)는 본질적으로 **런타임
> 도구로 검증**해야 한다. false positive는 "검토 요망"으로 표기하고 해당 런타임 도구로
> 최종 판정을 위임한다.

---

## 1. 스택 감지

먼저 호스트 문서를 우선 소비하고, 없으면 내장 카탈로그로 폴백한다.

```bash
# 호스트 harness-researcher가 생성한 문서 확인 (Phase 4, 있으면 우선 소비)
ls docs/performance.md 2>/dev/null && cat docs/performance.md
```

- `docs/performance.md` **존재 시**: 파일에서 스택 목록·SSOT·도구를 읽어 해당 스택 섹션만 실행한다.
- `docs/performance.md` **부재 시**: `references/static-checks.md`·`references/api-load.md`로 폴백한다.

### 스택 자동 감지 (폴백 시)

| 신호 파일/패턴 | 판정 스택 |
|---|---|
| `pyproject.toml` / `setup.py` / `*.py` | Python |
| `package.json` (`"dependencies"` 내 ORM/express) | Node.js |
| `package.json` (`react`/`next`) | React |
| `pom.xml` / `*.java` / `build.gradle` | Java/Hibernate |
| `Gemfile` / `*.rb` | Ruby |
| `*.csproj` / `*.cs` | .NET |
| `go.mod` / `*.go` | Go |
| `*.sql` / DB 관련 마이그레이션 | DB |

복수 스택이 감지되면 **해당 스택 모두 실행**한다.

---

## 2. 언어별 정적 안티패턴 플래깅

> **권위 카탈로그(SSOT) = [`references/static-checks.md`](references/static-checks.md)** — 스택별
> 도구·패턴·SSOT URL은 거기서만 관리한다(스택 추가/수정은 references에서, 이 SKILL 사본이 아니라).
> 아래 §2.x는 그 카탈로그를 적용하는 **실행 절차 요약**이다(중복 시 references가 우선).

감지된 각 스택에 대해 `references/static-checks.md`의 해당 행을 따른다.

### 2.1 N+1 쿼리

루프 내 ORM 접근 패턴을 정적으로 탐지한다. 탐지 휴리스틱:

```bash
# Python/Django 예: for 루프 내 .objects.get() / .filter()
grep -rn "for .*:" src/ | xargs grep -l "\.objects\.\(get\|filter\|all\)()"
```

플래깅 후 **반드시 런타임 도구**(nplusone, bullet, Hibernate Statistics 등)로 검증을 위임한다.
`references/static-checks.md`의 "N+1 탐지" 열을 참고한다.

### 2.2 DB 쿼리 플랜 주의 패턴

정적으로 탐지 가능한 패턴만 플래깅한다:

- `SELECT *` — 전체 컬럼 조회
- `WHERE FUNC(column) = ?` — 함수 래핑으로 인덱스 미사용
- `LIKE '%keyword%'` — 선행 와일드카드로 인덱스 미사용
- 복잡 `OR` 체인 — 인덱스 분기 불량

탐지 후 `EXPLAIN ANALYZE`(PostgreSQL) / `EXPLAIN`(MySQL) / `EXPLAIN QUERY PLAN`(SQLite) 절차를
안내한다. 상세는 `references/static-checks.md` "DB 쿼리 플랜" 절 참조.

### 2.3 재귀 / 알고리즘 복잡도

> **중요**: 순환복잡도(Cyclomatic Complexity)는 분기 수이며 Big-O 시간복잡도가 아니다.
> 두 개념은 구분한다.

정적 탐지 범위:

- 중첩 루프 깊이 ≥ 3 — 이차 이상 복잡도 후보로 플래깅
- 메모 없는 재귀 함수 — 인수 공간에 따라 지수 복잡도 가능성

탐지 후 **프로파일러**(py-spy·0x·async-profiler 등)로 실측 위임. 상세는 `references/static-checks.md` 참조.

### 2.4 프론트엔드 리렌더 (React)

**React Compiler v1.0 활성 감지 먼저** — 패키지나 Babel 설정에서 `babel-plugin-react-compiler`
/ `@babel/plugin-react-compiler` / Vite `reactCompiler` 옵션 확인.

```bash
grep -r "react-compiler\|babel-plugin-react-compiler" package.json babel.config.* vite.config.* 2>/dev/null
```

| 상태 | 적용 룰 |
|---|---|
| **Compiler 활성** | 수동 `memo`/`useMemo`/`useCallback` 룰 완화. 대신 **Rules of React 위반** 중심으로 점검(`eslint-plugin-react-hooks`). |
| **Compiler 미활성** | 인라인 객체/함수 prop, `useCallback` 누락, 불필요 `React.createElement` 재생성 등 정적 탐지. |

상세 패턴·SSOT는 `references/static-checks.md` "React 리렌더" 절 참조.

---

## 3. 백엔드 존재 시 API 부하분석

> 상세 절차·도구·리포트 템플릿은 → [`references/api-load.md`](references/api-load.md) 참조.

### 3.1 OpenAPI 스펙 자동 발견

> **권위 절차·후보 경로 전체 = [`references/api-load.md`](references/api-load.md) §1**(스택별
> 경로·ASP.NET documentName 가변 처리 포함). 아래는 실행 요약이다.

BASE_URL은 **하드코딩하지 말고 감지**한다(playwright-scaffold의 baseURL 감지와 동일 원칙 —
vdev-config·실행 서버·docker-compose·.env·프레임워크 기본에서 찾아 확인):

```bash
BASE_URL="${BASE_URL:?감지한 베이스 URL로 설정 — api-load.md §1 참조}"
for path in /openapi.json /v3/api-docs /swagger/v1/swagger.json /swagger.json /api-docs; do
  curl -sf "${BASE_URL}${path}" && break
done
```

### 3.2 부하 스크립트 생성 및 실행

**1순위 (AGPL-3.0 — 내부 CI 사용 무해):**

```bash
# openapi-to-k6로 operation별 함수 클라이언트 생성
npx openapi-to-k6 openapi.json -o k6-client.js
# 엔드포인트마다 k6 scenario(iterations:100)를 구성해 실행 — "각 엔드포인트 100회"
# (k6 --iterations 는 스크립트 전체 횟수라 엔드포인트별 보장 X. 상세: references/api-load.md)
k6 run --out json=k6-result.json k6-load.js
```

**MIT 폴백 (AGPL 회피 시):** `oha`·`autocannon`·`vegeta` — `references/api-load.md` 참조.

> 반복 횟수(기본 100)·SLO 임계는 스킬 기본값이다. 팀 부하 프로파일이 필요하면 스킬을 fork하지
> 말고 호스트 `docs/performance.md`(harness 생성)에 두어 그 값을 우선한다(config-주도 원칙).

### 3.3 리포트 수집 기준

`references/api-load.md`의 리포트 템플릿을 따른다. 핵심 강제 사항:

- **평균 단독 금지** — 반드시 p50/p95/p99 (+p99.9) 분포 보고
- throughput(RPS) + 동시성(VU) + 에러율 포함
- **SLO 대비 PASS/FAIL** 명시
- 측정 메타 기록: 도구·버전·부하모델·지속시간·warm-up 제외 여부·CO 보정 여부
- 백분위는 평균 내지 않음(비가산성 — `references/api-load.md` 통계 관례 절 참조)

---

## 4. 리포트 형식 (Four Golden Signals 골격)

```
## 성능 점검 결과 — <날짜>

### 정적 플래깅 결과
| 스택 | 패턴 | 위치 | 판정 | 권고 |
|---|---|---|---|---|
| Python/Django | N+1 의심 | users/views.py:42 | 검토 요망 | select_related('profile') 사용 |
| React | 인라인 객체 prop | components/List.tsx:17 | 검토 요망 | useMemo로 메모화 |

> 위 항목은 정적 탐지 후보 — 런타임 도구로 최종 판정 위임.

### API 부하 결과 (있는 경우)
| 엔드포인트 | p50 | p95 | p99 | RPS | VU | 에러율 | SLO | 판정 |
|---|---|---|---|---|---|---|---|---|
| GET /users | 12ms | 45ms | 120ms | 850 | 10 | 0.0% | p99≤200ms | PASS |
| POST /orders | 80ms | 350ms | 890ms | 210 | 10 | 1.2% | p99≤500ms | FAIL |

**측정 메타**: openapi-to-k6 0.3.x + k6 0.52.x / iterations=100 per endpoint / VU=10 /
warm-up 제외(첫 10회) / CO 보정 없음 / 로컬 실행(네트워크 오버헤드 없음)

### Golden Signals 요약
- **지연(Latency)**: …
- **트래픽(Traffic)**: …
- **에러율(Errors)**: …
- **포화도(Saturation)**: …
```

---

## 참조

- [`references/static-checks.md`](references/static-checks.md) — 스택별 정적 안티패턴 SSOT (§10.1~§10.4)
- [`references/api-load.md`](references/api-load.md) — OpenAPI 발견 + openapi-to-k6/k6 + 리포트 표준 (§10.5~§10.6)
