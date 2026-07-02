# 웹 프론트 감지 + Playwright 통합 테스트 SSOT

> **주의**: 웹 프론트 감지는 **휴리스틱**이며 단정 SSOT가 아니다. 신호 목록은 일반적인 관례 기반이고,
> 비표준 설정이나 모노레포 구조에서 오탐이 발생할 수 있다. 감지 결과는 항상 맥락으로 검증한다.

---

## 1. 웹 프론트 감지 신호

### 1.1 주 신호 — package.json 의존성 화이트리스트

`package.json`의 `dependencies` 또는 `devDependencies`에 아래 패키지 중 하나 이상이 존재하면 웹 프론트로 판정한다:

| 패키지 | 프레임워크 |
|---|---|
| `react` | React |
| `vue` | Vue.js |
| `next` | Next.js |
| `nuxt` | Nuxt |
| `svelte` | Svelte / SvelteKit |
| `@angular/core` | Angular |
| `solid-js` | SolidJS |
| `astro` | Astro |

### 1.2 보조 신호

주 신호와 함께 존재하면 웹 판정을 강화한다:

| 신호 파일/경로 | 의미 |
|---|---|
| `vite.config.ts` / `vite.config.js` | Vite 기반 빌드 |
| `index.html` (루트 또는 `public/`) | SPA 엔트리 |
| `public/` 디렉터리 | 정적 에셋 서빙 |
| `webpack.config.js` | Webpack 번들러 |
| `next.config.js` / `nuxt.config.ts` | 프레임워크 설정 |

### 1.3 비웹 신호 (존재 시 비웹 판정 우선)

| 신호 | 판정 |
|---|---|
| `package.json` 내 `"bin"` 필드 | CLI 도구 |
| `"react-native"` 의존성 | React Native (모바일) |
| `metro.config.js` | React Native 번들러 |
| `pubspec.yaml` | Flutter |
| `"electron"` 의존성 | Electron 데스크톱 |
| `main.go` / `go.mod` (+ 웹 신호 없음) | Go CLI/서비스 |

> **Electron 예외**: `"electron"` 의존성이 있더라도, 내부적으로 Chromium을 사용하므로
> `playwright chromium`으로 렌더러 프로세스 부분 자동화가 가능하다.
> 단, 주 프로세스(Node.js IPC·파일시스템 접근)는 Playwright로 제어 불가 —
> 해당 부분은 human-in-the-loop으로 처리한다.

---

## 2. Playwright 설정 파싱

### 2.1 설정 파일 탐지 순서

```bash
ls playwright.config.ts playwright.config.js \
   playwright.config.mjs playwright.config.cjs 2>/dev/null | head -1
```

### 2.2 testDir / testMatch 기본값

출처: [Playwright TestConfig API](https://playwright.dev/docs/api/class-testconfig)

| 설정 키 | 기본값 | 설명 |
|---|---|---|
| `testDir` | `./tests` | 케이스 파일 루트 디렉터리 |
| `testMatch` | `**/*.@(spec\|test).?(c\|m)[jt]s?(x)` | 케이스 파일 글로브 패턴 |

설정 파일에 명시된 값이 있으면 해당 값을 우선 사용한다.

---

## 3. 케이스 발견 및 실행

### 3.1 케이스 파일 발견

```bash
# testDir 기본값(./tests) 기준, testMatch 패턴 적용
find ./tests \( \
  -name "*.spec.ts" -o -name "*.spec.js" -o \
  -name "*.spec.mts" -o -name "*.spec.mjs" -o \
  -name "*.test.ts" -o -name "*.test.js" \
\) 2>/dev/null
```

**케이스 0개 시 처리**: `playwright-scaffold` 스킬로 **메인화면 smoke**("앱이 뜨는가" 결정적 검증)를
생성해 바로 실행한다(임의 사용자 시나리오는 생성하지 않음). 더 풍부한 실제 케이스는 codegen으로 확장:

```bash
# 스타터 smoke 이후, 실제 시나리오는 codegen으로 녹화해 tests/ 에 저장
npx playwright codegen https://your-app.example.com
```

### 3.2 결정적 실행 — `--reporter=json`(+junit)

출처: [Playwright 리포터](https://playwright.dev/docs/test-reporters) · [Playwright CLI](https://playwright.dev/docs/test-cli)

```bash
# JSON + JUnit 리포터 동시 출력. 파일로 받으려면 OUTPUT_NAME 지정(미지정 시 JSON은 stdout).
PLAYWRIGHT_JSON_OUTPUT_NAME=results.json \
PLAYWRIGHT_JUNIT_OUTPUT_NAME=results.xml \
  npx playwright test --reporter=json,junit
```

`--reporter=json`은 `PLAYWRIGHT_JSON_OUTPUT_NAME` 지정 시 그 파일로, 미지정 시 stdout 으로 출력한다.

### 3.3 결과 JSON 파싱

`results.json` 최상위 구조:

```json
{
  "stats": {
    "expected": 15,
    "unexpected": 2,
    "skipped": 1,
    "flaky": 0,
    "duration": 12340
  },
  "suites": [ ... ]
}
```

파싱 예시:

```bash
node -e "
  const r = JSON.parse(require('fs').readFileSync('results.json','utf8'));
  const {expected, unexpected, skipped} = r.stats;
  console.log('PASS:', expected, '/ FAIL:', unexpected, '/ SKIP:', skipped);
  process.exit(unexpected > 0 ? 1 : 0);
"
```

---

## 4. Playwright MCP (보조 경로)

출처: [Playwright MCP 시작하기](https://playwright.dev/docs/getting-started-mcp) · [playwright-mcp GitHub](https://github.com/microsoft/playwright-mcp) (Apache-2.0)

세션의 playwright MCP는 **케이스 부재 시 탐색 보조** 또는 **수동 확인**에만 활용한다.
회귀 테스트의 SSOT는 아니며, 결정적 재현을 보장하지 않는다.

```bash
# MCP 없이 헤드리스 브라우저로 스크린샷 확인
npx playwright screenshot --browser chromium https://your-app.example.com screenshot.png
```

---

## 5. Best Practices

출처: [Playwright Best Practices](https://playwright.dev/docs/best-practices) · [테스트 작성](https://playwright.dev/docs/writing-tests) · [테스트 설정](https://playwright.dev/docs/test-configuration)

| 원칙 | 내용 |
|---|---|
| 로케이터 우선순위 | `getByRole` > `getByLabel` > `getByText` > `getByTestId` 순 |
| 독립적 테스트 | 각 테스트는 독립 상태에서 시작 (`beforeEach`로 초기화) |
| `waitForSelector` 지양 | `expect(locator).toBeVisible()` 자동 대기 사용 |
| 병렬 실행 | `fullyParallel: true` 로 속도 향상 (상태 공유 없는 경우) |
| 환경 분리 | `baseURL`을 환경변수로 주입 (`process.env.BASE_URL`) |
| 리포터 고정 | CI에서는 `--reporter=json,junit` 고정 (CI 파싱 표준화) |

---

## 6. SSOT URL 요약

| 항목 | URL | 라이선스 |
|---|---|---|
| Best Practices | https://playwright.dev/docs/best-practices | Apache-2.0 |
| 테스트 작성 | https://playwright.dev/docs/writing-tests | Apache-2.0 |
| 테스트 설정 | https://playwright.dev/docs/test-configuration | Apache-2.0 |
| TestConfig API (testDir/testMatch) | https://playwright.dev/docs/api/class-testconfig | Apache-2.0 |
| 리포터(json/junit) | https://playwright.dev/docs/test-reporters | Apache-2.0 |
| CLI | https://playwright.dev/docs/test-cli | Apache-2.0 |
| MCP 시작하기 | https://playwright.dev/docs/getting-started-mcp | Apache-2.0 |
| playwright-mcp GitHub | https://github.com/microsoft/playwright-mcp | Apache-2.0 |
