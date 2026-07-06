---
name: playwright-scaffold
description: Automatically generates a deterministic "main-screen smoke" Playwright case for a web project. Finds the baseURL from playwright.config → the codebase (docker-compose.yml, .env, framework config, package.json), confirms it with the user, and idempotently generates main.smoke.spec (goto('/') + response OK + non-empty title) in testDir. A starting point for integration verification of a new/case-less web project — invoked by the integration skill when there are zero cases.
allowed-tools: Bash, Read, Write, Grep, Glob, AskUserQuestion
---

# playwright-scaffold

Generates a single **deterministic main-screen smoke** Playwright case for a web project. It creates only
the universal, deterministic check of "does the app come up?" and **does not generate arbitrary user
scenarios** (that is the job of a human or codegen).
Since it only writes files without any browser interaction, it is safe in CI/automation.

> **When**: when a new/empty web project needs its first integration case. When the integration skill
> detects web + zero cases, it invokes this skill to create a main-screen smoke and then runs it immediately.

---

## Step 1 — Detect baseURL (in order, with user confirmation at the end)

1. **`use.baseURL` in playwright.config**:
   ```bash
   ls playwright.config.* 2>/dev/null && grep -n "baseURL" playwright.config.* 2>/dev/null
   ```
2. If absent, **scan the codebase** (gather candidates rather than asserting):
   ```bash
   # docker-compose port mapping (web service host port)
   grep -nE '^\s*-\s*"?[0-9]+:[0-9]+' docker-compose.y*ml compose.y*ml 2>/dev/null
   # PORT / BASE_URL / public URL in .env
   grep -nhE '^(PORT|BASE_URL|VITE_[A-Z_]*URL|NEXT_PUBLIC_[A-Z_]*URL)=' .env .env.* 2>/dev/null
   # framework config / dev script port
   grep -nE 'server\s*:|port\s*:' vite.config.* next.config.* 2>/dev/null
   grep -nE '"dev"\s*:.*(--port|-p )\s*[0-9]+' package.json 2>/dev/null
   # Dockerfile EXPOSE
   grep -niE '^EXPOSE\s+[0-9]+' Dockerfile* 2>/dev/null
   ```
   - If the scan comes up empty, use framework default ports as candidates: Vite=5173, Next/CRA/Nuxt=3000, Angular=4200.
3. **User confirmation (required)**: present the collected candidates via `AskUserQuestion` and finalize the baseURL
   (offer them as choices if there are several; ask for direct input if none was found). Do not assert a guess as fact.

---

## Step 2 — Detect testDir and Language

```bash
# testDir: testDir from playwright.config, else ./tests
grep -n "testDir" playwright.config.* 2>/dev/null
# Language: .spec.ts for a TS project, otherwise .spec.js
ls tsconfig.json 2>/dev/null; grep -E '"(typescript|@playwright/test)"' package.json 2>/dev/null
```
- `testDir` unset → `tests/`. TS (tsconfig.json or a typescript dependency) → `.spec.ts`, otherwise `.spec.js`.

---

## Step 3 — Idempotent Generation (skip if already present)

```bash
# Do not generate if any existing case is present (the starter is for empty projects only)
# Matches the testMatch default exactly — same pattern used by integration/SKILL.md and web-playwright.md,
# so all three files agree on what counts as "an existing case" (previously this used a broader `*.spec.*`
# wildcard that could also match non-Playwright files like `foo.spec.md`).
find "${TESTDIR:-tests}" -regextype posix-extended -regex '.*\.(spec|test)\.(c|m)?[jt]sx?' 2>/dev/null | head -1
```
- If cases already exist or `main.smoke.spec.*` exists, **only report and do not generate** (no overwriting).
- Only when absent, write `<testDir>/main.smoke.spec.<ts|js>` based on
  [`examples/main.smoke.spec.ts`](examples/main.smoke.spec.ts). Do not hardcode baseURL into the spec;
  inject it via **`use.baseURL` in playwright.config** (the spec uses only the `'/'` relative path). If the
  config has no baseURL, add it to the config in Step 4.

---

## Step 4 — Playwright Not Installed / Config Absent (opt-in)

- If `@playwright/test` is not installed or `playwright.config.*` is absent, scaffold a minimal config and
  **guide** installation (do not force auto-install — only with consent):
  ```bash
  npm install -D @playwright/test && npx playwright install chromium
  ```
  ```javascript
  // playwright.config.ts (minimal — inject the baseURL finalized in Step 1)
  import { defineConfig } from '@playwright/test';
  export default defineConfig({
    testDir: './tests',
    use: { baseURL: 'http://localhost:3000' }, // ← the baseURL finalized in Step 1
  });
  ```

---

## Step 5 — Report + Extension Guidance

- Report the generated file path and the injected baseURL.
- **State that this is a starter smoke**: "This is only a 'does the app come up?' check. Add real scenarios
  (login, checkout, etc.) yourself, or record them with `npx playwright codegen <baseURL>` and save them under `tests/`."

---

## Discipline
- **Deterministic and non-interactive** — generate files only, without browser interaction (no arbitrary scenarios, main-screen smoke only).
- **No overwriting, idempotent** — do not generate if existing cases are present.
- **Do not assert a guessed baseURL** — gather candidates from codebase evidence and confirm with the user.
- Free OSS only — Playwright (Apache-2.0). Source: https://playwright.dev/docs/writing-tests ·
  configuration https://playwright.dev/docs/test-configuration
