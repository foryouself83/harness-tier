# vdev 재명명 + performance/integration 스킬 신설 — 설계

> 작성일: 2026-06-29 · 티어: dev(구 standard) · 상태: 승인됨(설계)

## 1. 배경 / 목적

vway-kit의 위험도 티어 워크플로우 명명을 정리하고, staging/release 게이트에 묶여 있던
`performance`·`integration`을 **게이트에서 분리해 독립 스킬로 승격**한다. 동시에 두 신규
스킬이 defer할 **권위 있는 SSOT를 사전 리서치로 확보**(2026-06 기준, 1차 출처 + 라이선스)하여
모델 기억이 아니라 공식 문서에 근거하도록 한다(프로젝트 CLAUDE.md 원칙).

## 2. 범위 (4개 컴포넌트)

1. **재명명(클린 교체)** — `flow`→`vdev` 전 패밀리, 티어 키 `fast`→`docs`·`standard`→`dev`,
   문서 산출물 PRD→SRS·architecture→SDS.
2. **신규 `performance` 스킬** — 언어별 정적 안티패턴 플래깅 + API 부하분석(openapi-to-k6+k6).
3. **신규 `integration` 스킬** — 웹=Playwright 기존 케이스 실행 / 비웹=human-in-the-loop.
4. **`harness-researcher` 확장** — 스택 reconcile 후 perf/integration SSOT 리서치 →
   호스트 `docs/performance.md`·`docs/integration.md` 생성.

비범위(YAGNI): 이력 문서(`docs/superpowers/specs|plans/*`)의 과거 `flow` 언급은 **갱신하지
않는다**(날짜 기록). 신규 스킬에 자체 부하/E2E 엔진을 구현하지 않는다(기성 OSS에 defer).

## 3. 컴포넌트 A — 재명명 (클린 교체)

하위호환 없음. 구 이름은 완전히 제거하고, 기존 호스트 설치는 `/vdev-init` 재실행으로 재복사
마이그레이션한다(멱등).

### 3.1 명명 변경 맵

| 종류 | 현재 | 변경 |
|---|---|---|
| 스킬(커맨드) | `skills/flow/` → `/flow` | `skills/vdev/` → `/vdev` |
| 스킬 | `skills/flow-init`, `skills/flow-uninstall` | `skills/vdev-init`, `skills/vdev-uninstall` |
| 정책(불변) | `flow-tiers.yaml` | `vdev-tiers.yaml` |
| 설정 | `flow-config.yaml`, `flow-config.example.yaml` | `vdev-config.yaml`, `vdev-config.example.yaml` |
| 게이트 스크립트 | `scripts/flow_gate_check.py` | `scripts/vdev_gate_check.py` |
| 셋업 스크립트 | `scripts/flow_init_setup.py` | `scripts/vdev_init_setup.py` |
| 증거 디렉터리 | `.claude/vway-kit/.flow/` | `.claude/vway-kit/.vdev/` |
| 티어 키 | `fast` / `standard` | `docs` / `dev` |
| 티어 키 | `staging` / `release` | **유지** |
| 문서 산출물 | PRD (`skills/harness-authoring/templates/prd.template.md`) | **SRS** (`srs.template.md`) |
| 문서 산출물 | architecture (`architecture.template.md`) | **SDS** (`sds.template.md`) |
| 테스트 | `tests/test_flow_gate_check.py`, `test_flow_init_setup.py` | `test_vdev_gate_check.py`, `test_vdev_init_setup.py` |

> 슬래시 커맨드 이름은 **디렉터리명**에서 온다(공식 문서 확인 — frontmatter `name`이 아님).
> 따라서 디렉터리 이동이 `/flow`→`/vdev`의 핵심이며, 각 SKILL.md `name:`도 일관되게 맞춘다.
> `.vdev/`·`vdev_gate_check.py`·`vdev-config.yaml`은 스킬명과 별개 자산이며 호스트
> `settings.json` 훅 경로·증거 마커와 엮인다 → 클린 교체이므로 호스트는 재-init 필요.

### 3.2 갱신 대상 (전수)

- **플러그인 컴포넌트**: `agents/`, `hooks/hooks.json`·`hooks/inject-risk-tiers.sh`,
  `skills/*/SKILL.md`(상호 `../flow/` 상대경로 링크 포함), `scripts/*.py`·`*.sh`,
  `rules/risk-tiers.md`·`rules/harness-rules.md`, `flow-tiers.yaml`, `flow-config.example.yaml`,
  `tests/*`, `.claude-plugin/marketplace.json`(필요 시), `pre-commit-hooks.example.yaml`,
  `github/api-contract.workflow.example.yml`.
- **사용자 문서**: `README.md`, `USAGE.md`, `CLAUDE.md`(루트), `.gitignore`(`.flow/`→`.vdev/`).
- **티어 마커 값**: `vdev_gate_check.py`의 미분류 차단 로직에서 허용 마커를 `docs|dev`로 갱신
  (구 `fast|standard` 제거 — 클린 교체).

### 3.3 마이그레이션 노트 (USAGE에 추가)

플러그인 업그레이드 후 기존 호스트는 `/vdev-init`를 재실행한다 — settings.json 게이트 훅의
스크립트 경로(`vdev_gate_check.py`)·증거 디렉터리(`.vdev/`)·설정 파일(`vdev-config.yaml`)을
재복사/이전한다(멱등, config 무손상). 정리는 `/vdev-uninstall`.

### 3.4 불변식 보존 (CLAUDE.md Invariants — 절대 깨지 않음)

1. FAIL-OPEN, 단 의존성 부재·미분류는 fail-CLOSED.
2. Windows 인코딩 방어(`PYTHONUTF8=1`·`force_utf8_io()`·`encoding="utf-8"`).
3. 차단 = exit 2 + stderr 사유.
4. settings.json 게이트 훅에 `if` 필드 금지.
5. `/vdev-init` 멱등(중복 추가 금지).
6. Teamer 자격증명은 keyring.

## 4. 컴포넌트 B — `vdev-tiers.yaml` 정책

```yaml
tiers:
  docs:        # 구 fast — 코드 없는 변경(문서/주석/설정값)
    superpowers: false
    gates: [doc-sync]
  dev:         # 구 standard — 코드 포함 변경
    superpowers: true
    gates: [precommit, review, doc-sync]
  staging:     # QA/RC 승격 (dev → stage)
    superpowers: true
    gates: [precommit, review]            # performance·integration 제거
  release:     # 프로덕션 배포 (stage → main)
    superpowers: true
    gates: [precommit, review, security]  # performance·integration 제거
```

`performance`·`integration`은 게이트에서 제거되어 **강제되지 않는 독립 수동 스킬**
(`/performance`, `/integration`)이 된다. `risk-tiers.md`는 "성능/통합 검증은 게이트가 아닌
스킬로 수행(비강제)"으로 문서화하고, 스킬 호출을 안내한다.

## 5. 컴포넌트 C — `performance` 스킬

위치: `skills/performance/SKILL.md` (+ `references/` SSOT 카탈로그). 호출: `/performance`
(정식 `/vway-kit:performance`). 완전 수동.

### 5.1 포지셔닝 (리서치 합의)

정적 검사는 **"확정 탐지"가 아니라 "의심 패턴 플래깅 → 런타임 도구로 검증"**. N+1·복잡도·
실측 지연은 본질적으로 런타임 측정이 필요하므로, 스킬은 정적으로 후보를 표시하고 검증을 런타임
도구로 위임한다(false positive를 "검토 요망"으로 표현).

### 5.2 흐름

1. **스택 감지** → 호스트 `docs/performance.md`(harness-researcher 생성)가 있으면 우선
   소비, 없으면 스킬 내장 카탈로그(references)로 폴백.
2. **언어별 정적 안티패턴 플래깅** (해당 스택 행만):
   - **N+1**: 루프 내 ORM 접근 등 플래깅 + 올바른 eager-loading 권고(스택별).
   - **쿼리 플랜**: `SELECT *`·WHERE 함수 래핑·선행 와일드카드 `LIKE '%x'`·OR 남용 정적
     플래그 → `EXPLAIN ANALYZE` 절차 안내.
   - **재귀/복잡도**: 중첩 루프 깊이·메모 없는 재귀 프록시 휴리스틱 → 프로파일러 위임.
     (순환복잡도 ≠ Big-O 구분 명시.)
   - **프론트 리렌더(React)**: 메모 컴포넌트에 인라인 객체/함수 prop 등 정적 탐지.
     **React Compiler v1.0 활성 감지 시 수동 메모 룰 완화**, 대신 Rules of React 위반 중심.
3. **백엔드 존재 시 API 부하분석**:
   - **OpenAPI 스펙 자동 발견**: 후보 경로 순차 GET — `/openapi.json`(FastAPI)·
     `/v3/api-docs`(springdoc)·`/swagger/v1/swagger.json`(ASP.NET; documentName 가변 →
     실패 시 `/swagger` HTML에서 spec URL 파싱)·`/swagger.json`·`/api-docs`.
   - **부하 스크립트 생성·실행(1순위, 최소 작업)**: `openapi-to-k6`로 OpenAPI→k6 스크립트
     생성 → `k6`로 **각 API 100회**(k6 iterations) 실행. (둘 다 AGPL-3.0 — 내부 CI 사용은
     무해. 도구 재배포/SaaS 호스팅만 회피.) **폴백(MIT 선호 시)**: `oha`/`autocannon`(JSON
     출력)으로 직접 엔드포인트 순회.
   - **리포트(표준 강제)**: **평균 단독 금지** — p50/p95/p99(+p99.9) 분포 + throughput(RPS)
     + 동시성(VU) + 에러율 + **SLO 대비 PASS/FAIL**. Four Golden Signals 골격. 측정 메타
     (도구/버전·부하모델·지속시간·warm-up 제외·CO 보정 여부) 기록. 백분위는 평균내지 않음.

### 5.3 SSOT 부록 (references/에 수록, §10)

## 6. 컴포넌트 D — `integration` 스킬

위치: `skills/integration/SKILL.md` (+ `references/`). 호출: `/integration`. 완전 수동.

### 6.1 흐름

1. **웹 프론트 감지**(휴리스틱 — 단정 SSOT 아님): `package.json` 의존성 화이트리스트
   (`react`/`vue`/`next`/`nuxt`/`svelte`/`@angular/core`/`solid-js`/`astro` …) + 보조
   신호(`vite.config.*`·`index.html`·`public/`). 비웹 신호: `bin`(CLI)·`react-native`/
   `metro.config.js`(RN)·`pubspec.yaml`(Flutter)·`electron`(데스크톱).
2. **웹이면** → `playwright.config.*` 파싱 → `testDir`(기본 `./tests`)·testMatch
   (`**/*.@(spec|test).?(c|m)[jt]s?(x)`)로 **기존 케이스 발견** →
   `npx playwright test --reporter=json`(+junit) **결정적 실행** → 결과 JSON 파싱해
   PASS/FAIL. **케이스 0개면 임의 생성 금지 → 사람에게 보고/위임**(codegen 안내).
   세션의 playwright MCP는 케이스 부재/탐색용 보조 경로로만(회귀 SSOT 아님).
3. **비웹이면** → **human-in-the-loop**: AskUserQuestion으로 시나리오·통과 기준을 사람에게
   받는다. 참고 OSS(Newman/Maestro/Appium, 전부 Apache-2.0)만 안내하고 자동 강제 안 함.
   (Electron은 Chromium 내부라 부분 자동화 가능 — 예외 주석.)

## 7. 컴포넌트 E — `harness-researcher` 확장

`agents/harness-researcher.md`에 차원 추가. harness-init Step 2.5(스택 reconcile/동결) 이후,
**확정된 (계층,스택)별로 performance·integration SSOT를 추가 리서치**한다.

- **performance 차원**: 해당 스택의 N+1 탐지 도구·프로파일러·정적 복잡도 도구, DB 쿼리플랜
  도구, API 부하(openapi-to-k6+k6 또는 MIT 폴백) — 각 출처 URL·라이선스·비용.
- **integration 차원**: 웹이면 Playwright, 비웹이면 human-in-the-loop + 참고 OSS.
- **산출**: authoring(harness-init Step 4)이 **호스트 `docs/performance.md`·`docs/integration.md`**
  (별도 기술문서)로 생성. 빈 스택 절은 만들지 않는다(확정 스택만). 출처는 `docs/research/`로 링크.
- harness-researcher 출력 형식에 `### 성능 SSOT (스택별)`·`### 통합 검증 SSOT` 절을 추가하고,
  기존 규율(출처 필수·유료 제외·라이선스 불명확 시 "확인 필요"·한글 출력)을 그대로 적용.

## 8. 검증

- `uv run pytest`(리네임된 `test_vdev_*.py` 포함)·`uv run ruff check`·`ruff format --check`·
  `*.sh` ShellCheck·`pre-commit run --all-files` 통과.
- 신규 스킬은 `.md` 컴포넌트라 단위테스트 비대상 — frontmatter 유효성 + 상호 링크 정합성
  (harness-critic 류 검토)으로 확인.
- 게이트 회귀: `vdev_gate_check`가 `docs|dev` 마커를 인식하고 미분류는 차단(fail-CLOSED),
  정책/설정 파싱 실패는 fail-OPEN을 유지하는지 테스트로 확인.

## 9. 구현 순서 (계획에서 단계로 분리)

1. 재명명(A) + 티어 정책(B) + 테스트 갱신 — 게이트 무결성 우선.
2. `performance` 스킬(C) + references SSOT.
3. `integration` 스킬(D) + references SSOT.
4. `harness-researcher` 확장(E) + harness-init/authoring 연계(docs/performance.md·integration.md).
5. 문서(README/USAGE/CLAUDE.md) + 마이그레이션 노트.

## 10. SSOT 부록 (사전 리서치 — 2026-06, 출처+라이선스)

### 10.1 N+1 탐지 (스택별)
- Python: nplusone https://github.com/jmcarp/nplusone (MIT) / 현대 fork https://github.com/huynguyengl99/nplus1 / django-zen-queries https://github.com/dabapps/django-zen-queries (BSD-2)
- SQLAlchemy: https://docs.sqlalchemy.org/en/20/orm/queryguide/relationships.html (MIT)
- Java/Hibernate Statistics: https://docs.jboss.org/hibernate/orm/5.4/javadocs/org/hibernate/stat/Statistics.html
- Ruby: bullet https://github.com/flyerhzm/bullet (MIT) / prosopite https://github.com/charkost/prosopite (Apache-2.0)
- .NET EF Core: https://learn.microsoft.com/en-us/ef/core/performance/efficient-querying / split: https://learn.microsoft.com/en-us/ef/core/querying/single-split-queries (MIT)
- Prisma: https://www.prisma.io/docs/orm/prisma-client/queries/query-optimization-performance (Apache-2.0)
- TypeORM: https://typeorm.io/docs/relations/eager-and-lazy-relations/ (MIT)

### 10.2 DB 쿼리 플랜
- PostgreSQL EXPLAIN: https://www.postgresql.org/docs/current/sql-explain.html / Using EXPLAIN: https://www.postgresql.org/docs/current/using-explain.html
- MySQL 8.4 EXPLAIN: https://dev.mysql.com/doc/refman/8.4/en/explain.html / 출력: https://dev.mysql.com/doc/refman/8.4/en/explain-output.html
- SQLite EXPLAIN QUERY PLAN: https://www.sqlite.org/eqp.html
- Use The Index, Luke!: https://use-the-index-luke.com/sql/explain-plan
- PEV2 시각화(PostgreSQL License): https://github.com/dalibo/pev2

### 10.3 프로파일링 / 복잡도
- Python: py-spy https://github.com/benfred/py-spy (MIT) · cProfile https://docs.python.org/3/library/profile.html · Scalene https://github.com/plasma-umass/scalene (Apache-2.0)
- Node: 내장 --prof https://nodejs.org/learn/getting-started/profiling · 0x https://github.com/davidmarkclements/0x (MIT) · Clinic.js https://github.com/clinicjs/node-clinic (MIT, 유지보수 비활성 주의)
- Go: runtime/pprof https://pkg.go.dev/runtime/pprof · net/http/pprof https://pkg.go.dev/net/http/pprof (BSD-3)
- Java: async-profiler https://github.com/async-profiler/async-profiler (Apache-2.0) · JFR https://docs.oracle.com/en/java/java-components/jdk-mission-control/9/user-guide/using-jdk-flight-recorder.html
- 정적 복잡도 보조: lizard https://github.com/terryyin/lizard (MIT) · radon https://radon.readthedocs.io/

### 10.4 프론트엔드 리렌더 (React)
- eslint-plugin-react-hooks(정적, 의존성배열+컴파일러룰 통합): https://react.dev/reference/eslint-plugin-react-hooks (MIT)
- React Compiler v1.0: https://react.dev/blog/2025/10/07/react-compiler-1 · 소개 https://react.dev/learn/react-compiler/introduction
- memo/useMemo/useCallback: https://react.dev/reference/react/memo · https://react.dev/reference/react/useMemo · https://react.dev/reference/react/useCallback
- 런타임: React DevTools Profiler https://react.dev/reference/react/Profiler · why-did-you-render https://github.com/welldone-software/why-did-you-render (MIT) · react-scan https://github.com/aidenybai/react-scan (MIT)

### 10.5 OpenAPI 추출 + 부하 도구
- OpenAPI Spec 3.1.1(example override 규칙): https://spec.openapis.org/oas/v3.1.1.html · 3.0→3.1: https://learn.openapis.org/upgrading/v3.0-to-v3.1.html
- spec 경로 관례: FastAPI https://fastapi.tiangolo.com/tutorial/metadata/ · springdoc https://github.com/springdoc/springdoc-openapi · ASP.NET https://learn.microsoft.com/en-us/aspnet/core/tutorials/getting-started-with-swashbuckle
- $ref/example 생성 보조: prance https://github.com/RonnyPfannschmidt/prance (MIT) · schemathesis https://github.com/schemathesis/schemathesis (MIT) · json-schema-faker https://github.com/json-schema-faker/json-schema-faker (MIT)
- **부하(1순위)**: openapi-to-k6 https://github.com/grafana/openapi-to-k6 (AGPL-3.0) + k6 https://grafana.com/docs/k6/latest/ (AGPL-3.0)
- **부하(MIT 폴백)**: oha https://github.com/hatoo/oha (MIT, JSON schema) · autocannon https://github.com/mcollina/autocannon (MIT) · vegeta https://github.com/tsenart/vegeta (MIT, targets 파일)
- 단일URL 참고: hey https://github.com/rakyll/hey (Apache-2.0, CSV만) · wrk https://github.com/wg/wrk (Apache-2.0, p95 미제공) · ab https://httpd.apache.org/docs/2.4/programs/ab.html (Apache-2.0)

### 10.6 성능 통계 보고 표준
- Google SRE — SLO: https://sre.google/sre-book/service-level-objectives/ · Four Golden Signals: https://sre.google/sre-book/monitoring-distributed-systems/
- The Tail at Scale: https://cacm.acm.org/research/the-tail-at-scale/
- HdrHistogram(coordinated omission 보정): https://github.com/HdrHistogram/HdrHistogram
- 백분위 비가산성: https://orangematter.solarwinds.com/2016/11/18/why-percentiles-dont-work-the-way-you-think/
- warm-up 제외: https://www.azul.com/blog/ramps-in-performance-tests-best-practices/

### 10.7 통합 테스트 (Playwright)
- 베스트프랙티스: https://playwright.dev/docs/best-practices · 작성: https://playwright.dev/docs/writing-tests · 설정: https://playwright.dev/docs/test-configuration
- testDir/testMatch 기본값: https://playwright.dev/docs/api/class-testconfig
- 리포터(json/junit): https://playwright.dev/docs/test-reporters · CLI: https://playwright.dev/docs/test-cli
- MCP: https://playwright.dev/docs/getting-started-mcp · https://github.com/microsoft/playwright-mcp (Apache-2.0)
- 비웹 참고 OSS: Newman https://github.com/postmanlabs/newman (Apache-2.0) · Maestro https://maestro.dev/ (Apache-2.0) · Appium https://github.com/appium/appium (Apache-2.0)

### 10.8 작성 스펙 (Claude Code 공식)
- SKILL.md frontmatter / 호출명=디렉터리명: https://code.claude.com/docs/en/skills.md
- 플러그인 스킬 자동 발견·네임스페이스: https://code.claude.com/docs/en/plugins-reference.md
- 보강 반영: description+when_to_use 합산 1,536자 캡 / 본문 500줄 이하 / `name`은 표시 라벨(디렉터리명이 호출명 결정).
