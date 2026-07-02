---
name: playwright-scaffold
description: 웹 프로젝트에 결정적 "메인화면 smoke" Playwright 케이스를 자동 생성한다. baseURL을 playwright.config → 코드베이스(docker-compose.yml·.env·프레임워크 설정·package.json)에서 찾아 사용자에게 확인받고, testDir에 main.smoke.spec(goto('/')+응답 OK+비어있지 않은 title)을 멱등 생성한다. 케이스가 없는/새 웹 프로젝트의 통합 검증 출발점 — integration 스킬이 케이스 0개일 때 호출한다.
allowed-tools: Bash, Read, Write, Grep, Glob, AskUserQuestion
---

# playwright-scaffold

웹 프로젝트에 **결정적 메인화면 smoke** Playwright 케이스 하나를 생성한다. "앱이 뜨는가"라는
보편·결정적 검증만 만들고 **임의 사용자 시나리오는 생성하지 않는다**(그건 사람·codegen 몫).
브라우저 상호작용 없이 파일만 쓰므로 CI·자동화에서 안전하다.

> **언제**: 새/빈 웹 프로젝트에 최초 통합 케이스가 필요할 때. integration 스킬이 웹 + 케이스 0개를
> 감지하면 이 스킬을 호출해 메인화면 smoke를 만든 뒤 바로 실행한다.

---

## Step 1 — baseURL 감지 (순서대로, 마지막엔 사용자 확인)

1. **playwright.config**의 `use.baseURL`:
   ```bash
   ls playwright.config.* 2>/dev/null && grep -n "baseURL" playwright.config.* 2>/dev/null
   ```
2. 없으면 **코드베이스 스캔**(단정하지 말고 후보를 모은다):
   ```bash
   # docker-compose 포트 매핑(웹 서비스 host 포트)
   grep -nE '^\s*-\s*"?[0-9]+:[0-9]+' docker-compose.y*ml compose.y*ml 2>/dev/null
   # .env 의 PORT / BASE_URL / 공개 URL
   grep -nhE '^(PORT|BASE_URL|VITE_[A-Z_]*URL|NEXT_PUBLIC_[A-Z_]*URL)=' .env .env.* 2>/dev/null
   # 프레임워크 설정 / dev 스크립트 포트
   grep -nE 'server\s*:|port\s*:' vite.config.* next.config.* 2>/dev/null
   grep -nE '"dev"\s*:.*(--port|-p )\s*[0-9]+' package.json 2>/dev/null
   # Dockerfile EXPOSE
   grep -niE '^EXPOSE\s+[0-9]+' Dockerfile* 2>/dev/null
   ```
   - 스캔이 비면 프레임워크 기본 포트를 후보로: Vite=5173, Next/CRA/Nuxt=3000, Angular=4200.
3. **사용자 확인(필수)**: 수집한 후보를 `AskUserQuestion`으로 제시해 baseURL을 확정한다
   (후보 여러 개면 선택지로, 못 찾았으면 직접 입력 요청). 추측으로 단정하지 않는다.

---

## Step 2 — testDir·언어 감지

```bash
# testDir: playwright.config 의 testDir, 없으면 ./tests
grep -n "testDir" playwright.config.* 2>/dev/null
# 언어: TS 프로젝트면 .spec.ts, 아니면 .spec.js
ls tsconfig.json 2>/dev/null; grep -E '"(typescript|@playwright/test)"' package.json 2>/dev/null
```
- `testDir` 미설정 → `tests/`. TS(tsconfig.json 또는 typescript 의존성) → `.spec.ts`, 아니면 `.spec.js`.

---

## Step 3 — 멱등 생성 (이미 있으면 skip)

```bash
# 기존 케이스가 하나라도 있으면 생성하지 않는다(스타터는 빈 프로젝트 전용)
find "${TESTDIR:-tests}" \( -name '*.spec.*' -o -name '*.test.*' \) 2>/dev/null | head -1
```
- 케이스가 이미 있거나 `main.smoke.spec.*`가 존재하면 **생성하지 않고 보고만** 한다(덮어쓰기 금지).
- 없을 때만 [`examples/main.smoke.spec.ts`](examples/main.smoke.spec.ts)를 기반으로
  `<testDir>/main.smoke.spec.<ts|js>`를 쓴다. baseURL은 spec에 박지 않고
  **playwright.config의 `use.baseURL`**로 주입한다(spec은 `'/'` 상대경로만 사용). config에
  baseURL이 없으면 Step 4에서 config에 추가한다.

---

## Step 4 — Playwright 미설치/config 부재 (opt-in)

- `@playwright/test` 미설치 또는 `playwright.config.*` 부재 시, 최소 config를 스캐폴드하고 설치를
  **안내**한다(자동 설치 강제 금지 — 동의 시에만):
  ```bash
  npm install -D @playwright/test && npx playwright install chromium
  ```
  ```javascript
  // playwright.config.ts (최소 — Step 1에서 확정한 baseURL 주입)
  import { defineConfig } from '@playwright/test';
  export default defineConfig({
    testDir: './tests',
    use: { baseURL: 'http://localhost:3000' }, // ← Step 1에서 확정한 baseURL
  });
  ```

---

## Step 5 — 보고 + 확장 안내

- 생성한 파일 경로와 주입한 baseURL을 보고한다.
- **스타터 smoke임을 명시**: "이건 '앱이 뜨는가' 검증일 뿐이다. 실제 시나리오(로그인·결제 등)는
  직접 추가하거나 `npx playwright codegen <baseURL>`로 녹화해 `tests/`에 저장하라."

---

## 규율
- **결정적·비대화** — 브라우저 상호작용 없이 파일만 생성(임의 시나리오 금지, 메인화면 smoke만).
- **덮어쓰기 금지·멱등** — 기존 케이스가 있으면 생성하지 않는다.
- **baseURL 추측 단정 금지** — 코드베이스 근거로 후보를 모아 사용자에게 확인.
- 무료 OSS만 — Playwright(Apache-2.0). 출처: https://playwright.dev/docs/writing-tests ·
  설정 https://playwright.dev/docs/test-configuration
