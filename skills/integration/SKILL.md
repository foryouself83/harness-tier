---
name: integration
description: 프로젝트가 웹 프론트면 기존 Playwright 케이스를 결정적으로 실행(--reporter=json)해 통합 검증 결과를 PASS/FAIL로 보고한다. 웹인데 케이스가 0개이면 playwright-scaffold로 메인화면 smoke를 생성해 바로 실행하고, 웹이 아니면 사람에게 시나리오·통과 기준을 묻는다(human-in-the-loop). 게이트가 아닌 수동 스킬 — 통합 검증이 필요할 때 호출.
allowed-tools: Bash, Read, Grep, Glob, AskUserQuestion, Skill
---

# integration

프로젝트의 **통합 테스트를 수동으로 실행**하거나, 자동화가 없을 때 **사람에게 시나리오를 수집**한다.
게이트가 아닌 수동 스킬이다 — `/vdev` 게이트에 묶이지 않는다.

> **포지셔닝**: 이 스킬은 **기존 Playwright 케이스를 결정적으로 실행**한다. 웹인데 케이스가
> 없으면 `playwright-scaffold`로 **메인화면 smoke**("앱이 뜨는가" 결정적 검증)만 생성해 실행하고
> (임의 시나리오는 생성하지 않음), 웹이 아니면 human-in-the-loop으로 처리한다.
> 웹 프론트 감지는 휴리스틱이며 단정 SSOT가 아니다 — 상세는
> [`references/web-playwright.md`](references/web-playwright.md) 참조.

---

## 1. 호스트 문서 우선 소비

```bash
# harness-researcher가 생성한 통합 문서 확인 (Phase 4, 있으면 우선 소비)
ls docs/integration.md 2>/dev/null && cat docs/integration.md
```

- `docs/integration.md` **존재 시**: 파일의 스택별 통합 전략·도구·실행 명령을 따른다.
- `docs/integration.md` **부재 시**: `references/web-playwright.md`·`references/non-web.md`로 폴백한다.

---

## 2. 웹 프론트 감지 (휴리스틱)

> 감지 신호 전체 목록과 한계는 → [`references/web-playwright.md`](references/web-playwright.md) 참조.

`package.json`의 `dependencies`/`devDependencies`에서 웹 프레임워크 화이트리스트를 확인한다:

```bash
# 웹 프레임워크 의존성 확인
grep -E '"(react|vue|next|nuxt|svelte|@angular/core|solid-js|astro)"' package.json 2>/dev/null
```

보조 신호도 함께 확인한다:

```bash
# 보조 신호: vite.config, index.html, public/
ls vite.config.* index.html public/ 2>/dev/null
```

**비웹 신호** 확인(있으면 비웹으로 판정):

```bash
# CLI: bin 필드, RN: react-native/metro.config.js, Flutter: pubspec.yaml, Electron: electron
grep '"bin"' package.json 2>/dev/null
grep '"react-native"\|"electron"' package.json 2>/dev/null
ls metro.config.js pubspec.yaml 2>/dev/null
```

| 판정 | 조건 |
|---|---|
| **웹** | 화이트리스트 의존성 존재 + 비웹 신호 없음 |
| **비웹** | 비웹 신호 존재, 또는 화이트리스트 미탐지 |
| **Electron** | `"electron"` 의존성 — Chromium 내부라 부분 자동화 가능(web-playwright §1.3) |

> **Electron 예외** 상세(렌더러 부분 자동화 / 주 프로세스는 human-in-the-loop)는
> [`references/web-playwright.md`](references/web-playwright.md) §1.3 참조 — 중복 정의를 피해 한 곳에 둔다.

---

## 3. 웹이면 — Playwright 기존 케이스 실행

> Playwright 설정·testDir/testMatch 기본값·리포터 옵션 상세는
> → [`references/web-playwright.md`](references/web-playwright.md) 참조.

### 3.1 playwright.config.* 파싱

```bash
# 설정 파일 탐지
ls playwright.config.ts playwright.config.js playwright.config.mjs playwright.config.cjs 2>/dev/null | head -1
```

설정 파일에서 `testDir`·`testMatch`를 읽는다. 기본값은:
- `testDir`: `./tests`
- `testMatch`: `**/*.@(spec|test).?(c|m)[jt]s?(x)`

### 3.2 기존 케이스 발견

```bash
# testDir 내 케이스 파일 수 확인 (기본 ./tests)
find ./tests -name "*.spec.ts" -o -name "*.spec.js" -o -name "*.test.ts" -o -name "*.test.js" 2>/dev/null | wc -l
```

**케이스 0개이면** `playwright-scaffold` 스킬을 호출해 **메인화면 smoke를 생성한 뒤 바로 실행**한다
(임의 시나리오가 아니라 "앱이 뜨는가" 결정적 검증):

1. `Skill` 도구로 `playwright-scaffold` 를 호출한다 → baseURL 확인(코드베이스 스캔 + 사용자 확인)
   → `<testDir>/main.smoke.spec.*` 멱등 생성. (Playwright 미설치 시 scaffold가 설치를 안내.)
2. 생성된 smoke를 §3.3대로 `--reporter=json`으로 실행하고 §3.4로 PASS/FAIL 보고한다.
3. 보고에 **"스타터 smoke이니 실제 케이스로 확장하라"**(`npx playwright codegen <baseURL>`)를 명시한다.

> 실행 러너는 `npx playwright test`(결정적·SSOT)다. 세션의 playwright MCP는 케이스 부재·탐색
> 보조 경로로만 활용한다(회귀 SSOT 아님). MCP 참조:
> [`references/web-playwright.md`](references/web-playwright.md) "playwright MCP" 절.

### 3.3 결정적 실행

케이스가 존재하면 `--reporter=json`(+junit)으로 결정적 실행한다. `--reporter=json`은 기본적으로
**stdout**으로 내보내므로, 파일로 받으려면 `PLAYWRIGHT_JSON_OUTPUT_NAME`을 지정한다(미지정 시
§3.4의 파일 파싱이 ENOENT로 깨진다):

```bash
PLAYWRIGHT_JSON_OUTPUT_NAME=results.json \
PLAYWRIGHT_JUNIT_OUTPUT_NAME=results.xml \
  npx playwright test --reporter=json,junit
```

### 3.4 결과 파싱 및 PASS/FAIL 보고

§3.3에서 지정한 `results.json`을 파싱한다:

```bash
# 결과 요약: 통과/실패/건너뜀 수 추출
node -e "
  const r = JSON.parse(require('fs').readFileSync('results.json','utf8'));
  const s = r.stats;
  console.log('PASS:', s.expected, '/ FAIL:', s.unexpected, '/ SKIP:', s.skipped);
  process.exit(s.unexpected > 0 ? 1 : 0);
"
```

**리포트 형식**:

```
## 통합 테스트 결과 — <날짜>

### Playwright 실행 결과
| 스위트 | 통과 | 실패 | 건너뜀 | 판정 |
|---|---|---|---|---|
| tests/auth.spec.ts | 5 | 0 | 0 | PASS |
| tests/checkout.spec.ts | 3 | 1 | 0 | FAIL |

**전체 판정**: FAIL (실패 1건)
실패 케이스: tests/checkout.spec.ts › 결제 완료 후 확인 페이지 이동
```

---

## 4. 비웹이면 — human-in-the-loop

> 비웹 타입별 신호·참고 OSS 상세는 → [`references/non-web.md`](references/non-web.md) 참조.

자동 통합 테스트를 강제하지 않는다. `AskUserQuestion`으로 시나리오와 통과 기준을 수집한다:

```
이 프로젝트는 비웹(CLI/RN/Flutter 등)으로 감지되었습니다.
통합 테스트 자동화 도구를 강제하지 않습니다.

아래 항목을 알려주세요:
1. 검증할 핵심 시나리오 (예: "사용자 로그인 후 데이터 조회")
2. 각 시나리오의 통과 기준 (예: "응답 코드 200, 데이터 포함")
3. 현재 사용 중인 테스트 도구가 있으면 알려주세요.
```

수집한 시나리오를 기반으로 수동 검증 체크리스트를 작성하고, 적용 가능한 OSS를 안내한다
(Newman/Maestro/Appium — 모두 Apache-2.0, 자동 강제 없음). 상세는
[`references/non-web.md`](references/non-web.md) 참조.

---

## 참조

- [`references/web-playwright.md`](references/web-playwright.md) — 웹 감지 신호·testDir/testMatch·리포터·best-practices·SSOT URL (§10.7)
- [`references/non-web.md`](references/non-web.md) — 비웹 타입 신호·human-in-the-loop 절차·참고 OSS
- [`playwright-scaffold`](../playwright-scaffold/SKILL.md) — 웹+케이스 0개일 때 메인화면 smoke 생성기(이 스킬이 호출)
