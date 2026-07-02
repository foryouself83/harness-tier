# 정적 성능 안티패턴 카탈로그

> SSOT: 스펙 §10.1~§10.4 사전 리서치 기준 (2026-06). 출처 URL·라이선스 명시.
> **런타임 도구는 "검증 위임" 표기** — 정적 탐지로 후보를 뽑고, 런타임 도구로 최종 판정한다.

---

## 1. N+1 쿼리 탐지

### Python / Django

| 탐지 패턴 | 올바른 형태 | 도구 | 출처 |
|---|---|---|---|
| `for obj in qs: obj.related_set.all()` — 루프 내 역방향 릴레이션 접근 | `prefetch_related('related_set')` | nplusone (MIT) | https://github.com/jmcarp/nplusone |
| `for obj in qs: obj.fk_field.attr` — 루프 내 외래키 순방향 접근 | `select_related('fk_field')` | nplusone / django-zen-queries | https://github.com/dabapps/django-zen-queries (BSD-2) |
| 현대 fork (Django 5.x 지원) | — | nplus1 | https://github.com/huynguyengl99/nplus1 |

정적 플래깅 휴리스틱: `for` 블록 내 `.objects.get()`·`.objects.filter()`·`.all()` 패턴 grep.
**검증 위임**: `nplusone.hooks.NPlusOneHook`을 테스트에 연결하면 런타임 N+1을 예외로 포착한다.

### SQLAlchemy (Python ORM)

| 탐지 패턴 | 올바른 형태 | 출처 |
|---|---|---|
| 루프 내 lazy load (기본값 `lazy='select'`) | `joinedload()` / `selectinload()` | https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html (MIT) |
| `Session.get()` 루프 반복 | 배치 조회 or `in_()` 필터 | 위 동일 |

### Java / Hibernate

| 탐지 패턴 | 올바른 형태 | 도구 | 출처 |
|---|---|---|---|
| `@OneToMany` 기본 `FetchType.LAZY` + 루프 접근 | `FetchType.EAGER` or `JOIN FETCH` JPQL | Hibernate Statistics (런타임 검증 위임) | https://docs.jboss.org/hibernate/orm/5.4/javadocs/org/hibernate/stat/Statistics.html |
| 루프 내 `entityManager.find()` | `entityManager.createQuery("...JOIN FETCH...")` | — | 위 동일 |

**검증 위임**: `hibernate.generate_statistics=true` 후 `StatisticsImpl.getQueryExecutionCount()`로
루프당 쿼리 수 실측.

### Ruby / Rails

| 탐지 패턴 | 올바른 형태 | 도구 | 출처 |
|---|---|---|---|
| 루프 내 `belongs_to` / `has_many` 접근 (lazy) | `includes(:assoc)` / `eager_load(:assoc)` | bullet (MIT) | https://github.com/flyerhzm/bullet (MIT) |
| `where` 후 루프 내 연관 접근 | `preload` 사용 | prosopite (Apache-2.0) | https://github.com/charkost/prosopite |

**검증 위임**: `bullet` gem을 test 환경에서 활성화하면 N+1·unused eager loading을 로그에 기록.

### .NET / EF Core

| 탐지 패턴 | 올바른 형태 | 출처 |
|---|---|---|
| `foreach (var x in ctx.Entities) { x.Nav.Load(); }` | `.Include(e => e.Nav)` | https://learn.microsoft.com/en-us/ef/core/performance/efficient-querying (MIT) |
| 대형 결과셋에 `.Include()` 체인 남용 | Split Query(`AsSplitQuery()`) 고려 | https://learn.microsoft.com/en-us/ef/core/querying/single-split-queries |

### Prisma (Node.js)

| 탐지 패턴 | 올바른 형태 | 출처 |
|---|---|---|
| `for (const u of users) { await prisma.post.findMany({ where: { userId: u.id } }) }` | `include: { posts: true }` or `prisma.$transaction` 배치 | https://www.prisma.io/docs/orm/prisma-client/queries/query-optimization-performance (Apache-2.0) |

### TypeORM (Node.js)

| 탐지 패턴 | 올바른 형태 | 출처 |
|---|---|---|
| `@ManyToOne` 기본 lazy + 루프 접근 | `eager: true` or `QueryBuilder.leftJoinAndSelect()` | https://typeorm.io/docs/relations/eager-and-lazy-relations/ (MIT) |

---

## 2. DB 쿼리 플랜 주의 패턴

> 정적으로 탐지 가능한 패턴만 플래깅. 최종 판정은 EXPLAIN ANALYZE 실행으로 위임.

| 정적 패턴 | 문제 | 권고 | 검증 명령 |
|---|---|---|---|
| `SELECT *` | 불필요 컬럼 전송, 인덱스 커버리지 손실 | 필요 컬럼만 명시 | `EXPLAIN ANALYZE SELECT *` 후 플랜 확인 |
| `WHERE func(column) = ?` | 함수 래핑으로 인덱스 스캔 불가 | 함수 없는 조건 재작성 or 함수 기반 인덱스 | `EXPLAIN ANALYZE` |
| `LIKE '%keyword%'` | 선행 와일드카드로 풀 스캔 | 역방향 인덱스·FTS 고려 | `EXPLAIN ANALYZE` |
| 복잡 `OR` 체인 | 옵티마이저가 인덱스 병합 실패 가능 | `UNION ALL` 재작성 검토 | `EXPLAIN ANALYZE` |
| 서브쿼리 `IN (SELECT ...)` 남용 | 상관 서브쿼리로 N×M 스캔 가능 | `JOIN` 또는 `EXISTS` 재작성 | `EXPLAIN ANALYZE` |

### EXPLAIN 공식 문서

| DB | 명령 | 출처 |
|---|---|---|
| PostgreSQL | `EXPLAIN (ANALYZE, BUFFERS)` | https://www.postgresql.org/docs/current/sql-explain.html · https://www.postgresql.org/docs/current/using-explain.html |
| MySQL 8.4 | `EXPLAIN FORMAT=JSON` | https://dev.mysql.com/doc/refman/8.4/en/explain.html · https://dev.mysql.com/doc/refman/8.4/en/explain-output.html |
| SQLite | `EXPLAIN QUERY PLAN` | https://www.sqlite.org/eqp.html |

### 보조 자료

- **Use The Index, Luke!** (쿼리 플랜 해석 가이드): https://use-the-index-luke.com/sql/explain-plan
- **PEV2** (PostgreSQL EXPLAIN 시각화, PostgreSQL License): https://github.com/dalibo/pev2

---

## 3. 프로파일링 / 복잡도

> **중요**: 순환복잡도(Cyclomatic Complexity, CC)는 분기 수이며 **Big-O 시간복잡도가 아니다**.
> CC가 높아도 O(n)일 수 있고, CC가 낮아도 O(n²)일 수 있다. 두 개념을 혼용하지 말 것.

### 정적 복잡도 보조 도구 (탐지 보조 — 런타임 검증 아님)

| 도구 | 지원 언어 | 라이선스 | 출처 |
|---|---|---|---|
| lizard | Python·C/C++·Java·JS 등 다중 | MIT | https://github.com/terryyin/lizard |
| radon | Python | MIT | https://radon.readthedocs.io/ |

lizard 사용 예:
```bash
lizard src/ -C 10  # 순환복잡도 10 초과 함수 보고
```

> 출력은 "CC가 높은 함수 목록"이며 알고리즘 복잡도 증거가 아니다. 중첩 루프나 재귀 패턴을
> 별도 grep으로 보완한다.

### 중첩 루프 / 재귀 정적 탐지 휴리스틱

```bash
# 중첩 for 3단계 이상 (Python 예)
grep -Pn "^(\s{4})+for " src/**/*.py | awk -F: '{print $2, $1}' | sort -rn | head -20

# 재귀 함수 (함수명이 자기 자신 내부에서 호출)
grep -Pn "def (\w+).*:\n.*\1(" src/**/*.py  # 단순 휴리스틱, 교차 검증 필요
```

### 런타임 프로파일러 (검증 위임)

| 언어 | 도구 | 라이선스 | 출처 |
|---|---|---|---|
| Python | py-spy | MIT | https://github.com/benfred/py-spy |
| Python | cProfile (내장) | PSF | https://docs.python.org/3/library/profile.html |
| Python | Scalene | Apache-2.0 | https://github.com/plasma-umass/scalene |
| Node.js | --prof (내장 V8) | MIT(Node) | https://nodejs.org/learn/getting-started/profiling |
| Node.js | 0x | MIT | https://github.com/davidmarkclements/0x |
| Node.js | Clinic.js | MIT *(유지보수 비활성 주의)* | https://github.com/clinicjs/node-clinic |
| Go | runtime/pprof (내장) | BSD-3 | https://pkg.go.dev/runtime/pprof |
| Go | net/http/pprof (내장) | BSD-3 | https://pkg.go.dev/net/http/pprof |
| Java | async-profiler | Apache-2.0 | https://github.com/async-profiler/async-profiler |
| Java | JDK Flight Recorder (JFR) | GPL+CE | https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html |

---

## 4. 프론트엔드 리렌더 (React)

### React Compiler v1.0 활성 시 (2025-10 GA 기준)

**Compiler 활성 감지 먼저** — `babel-plugin-react-compiler` / `@babel/plugin-react-compiler` /
Vite `reactCompiler` 플러그인 여부 확인.

Compiler가 활성화되면 **자동 메모화**가 적용되므로 수동 `memo`/`useMemo`/`useCallback` 룰을
완화한다. 대신 **Rules of React 위반** 중심으로 점검한다:

- `eslint-plugin-react-hooks`의 `rules-of-hooks` + `exhaustive-deps` 규칙 (Compiler와 통합)
- 컴포넌트 외부에서 훅 호출 / 조건부 훅 호출 등 Rules of React 위반

| 항목 | 출처 |
|---|---|
| eslint-plugin-react-hooks (MIT) | https://react.dev/reference/eslint-plugin-react-hooks |
| React Compiler v1.0 블로그 | https://react.dev/blog/2025/10/07/react-compiler-1 |
| React Compiler 소개 | https://react.dev/learn/react-compiler/introduction |

### React Compiler 미활성 시

| 정적 탐지 패턴 | 문제 | 권고 | 출처 |
|---|---|---|---|
| JSX prop에 인라인 객체 `<Comp style={{ color: 'red' }}>` | 매 렌더마다 새 객체 참조 → 자식 리렌더 | `useMemo`로 메모화 또는 모듈 상수로 추출 | https://react.dev/reference/react/useMemo |
| JSX prop에 인라인 함수 `<Comp onClick={() => handler(id)}>` | 매 렌더마다 새 함수 참조 | `useCallback(…, [id])` | https://react.dev/reference/react/useCallback |
| `React.memo` 감싼 컴포넌트에 인라인 prop | memo가 무효화됨 | prop을 안정 참조로 | https://react.dev/reference/react/memo |
| `useEffect` deps 배열 누락 또는 과다 | stale closure / 무한 루프 | `exhaustive-deps` lint 룰 적용 | https://react.dev/reference/eslint-plugin-react-hooks |

### 런타임 리렌더 도구 (검증 위임)

| 도구 | 라이선스 | 출처 |
|---|---|---|
| React DevTools Profiler | MIT | https://react.dev/reference/react/Profiler |
| why-did-you-render | MIT | https://github.com/welldone-software/why-did-you-render |
| react-scan | MIT | https://github.com/aidenybai/react-scan |
