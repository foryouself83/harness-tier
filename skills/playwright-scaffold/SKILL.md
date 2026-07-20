---
name: playwright-scaffold
description: Use when a web project needs its first Playwright integration case — no test cases exist yet, or the integration skill found zero cases. Not for adding scenarios to a project that already has a suite.
---

# playwright-scaffold

Generates a single **deterministic main-screen smoke** Playwright case for a web project. It creates only
the universal, deterministic check of "does the app come up?" and **does not generate arbitrary user
scenarios** (that is the job of a human or codegen).

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
# testDir from playwright.config, falling back to Playwright's ./tests default
grep -hoE "testDir:[[:space:]]*['\"][^'\"]+" playwright.config.* 2>/dev/null | head -1 | sed -E "s/.*['\"]//"
# Language: any of these three means TypeScript
ls tsconfig.json playwright.config.ts 2>/dev/null; grep -E '"typescript"' package.json 2>/dev/null
```
- `testDir` unset → `tests/`.
- **TypeScript when *any* of `tsconfig.json`, `playwright.config.ts`, or a `typescript`
  dependency is present** → `.spec.ts`; otherwise `.spec.js`. A `playwright.config.ts`
  counts on its own: `@playwright/test` bundles its own TypeScript, so a TS Playwright
  project routinely has neither a `tsconfig.json` nor a `typescript` dependency, and
  keying only on those two drops a `.js` spec into a TypeScript suite.
- Carry the resolved `testDir` forward as a literal in Step 3 — each `bash` call is a fresh
  shell, so a variable set here is gone by the next command.

---

## Step 3 — Idempotent Generation (skip if already present)

The starter is for empty projects, so an existing case means report-and-stop. Resolve
`testDir` and search it in one command — the same regex `integration/SKILL.md` and
`web-playwright.md` use, so all three agree on what counts as an existing case.

```bash
# POSIX find + grep -E: -regextype is GNU-only (BSD/macOS find rejects it, exits 1, and an
# `&& … || echo MISSING` chain then reports every healthy project as MISSING — conflating
# any find failure with an absent directory). `|| true`: grep exits 1 on zero matches, and
# an empty suite is an answer, not an error. MISSING comes only from the [ -d ] test.
TESTDIR=$(grep -hoE "testDir:[[:space:]]*['\"][^'\"]+" playwright.config.* 2>/dev/null | head -1 | sed -E "s/.*['\"]//")
TESTDIR="${TESTDIR:-./tests}"
if [ -d "$TESTDIR" ]; then find "$TESTDIR" -type f 2>/dev/null | grep -E '\.(spec|test)\.(c|m)?[jt]sx?$' || true; else echo "MISSING: $TESTDIR"; fi
```
- Any case path means cases already exist → **only report and do not generate** (no
  overwriting). The regex already matches `main.smoke.spec.ts`, so a previous run's smoke
  counts as a hit.
- `MISSING:` for a **config-declared** `testDir` is a misconfiguration — report it and
  stop. Generating into a directory the config does not point at leaves a spec Playwright
  will never run. `MISSING: ./tests` with no `testDir` in the config is just a new project:
  create the directory and generate.
- Only when absent, write `<testDir>/main.smoke.spec.<ts|js>` based on
  [`examples/main.smoke.spec.ts`](examples/main.smoke.spec.ts). The spec navigates to `'/'`
  and nothing else — Playwright resolves that against **`use.baseURL` in playwright.config**,
  which is where the baseURL belongs. Step 4 puts it there.

---

## Step 4 — Settle playwright.config (opt-in)

Three states, each with somewhere to go — a config that exists but declares no `baseURL`
is the common one, and the spec written in Step 3 resolves `'/'` against nothing until it
is handled:

| State | Action |
|---|---|
| `playwright.config.*` exists **with** a `use.baseURL` | nothing to do config-wise — but if `@playwright/test` itself is missing, still guide the install below |
| `playwright.config.*` exists, **no** `use.baseURL` | add `use: { baseURL: '<the value confirmed in Step 1>' }` to the existing config — edit it, do not replace it |
| `playwright.config.*` absent | scaffold the minimal config below |

- If `playwright.config.*` is absent, scaffold the minimal config below. If
  `@playwright/test` is not installed (config present or not), **guide** installation —
  do not force auto-install, only with consent:
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
- **Files only** — write the spec and stop; leave running it to `npx playwright test`. The
  one case to write is the main-screen smoke. Step 1's baseURL confirmation and Step 4's
  install consent both still apply — ask the user for each.
- **No overwriting, idempotent** — do not generate if existing cases are present.
- **Do not assert a guessed baseURL** — gather candidates from codebase evidence and confirm with the user.
- Free OSS only — Playwright (Apache-2.0). Source: https://playwright.dev/docs/writing-tests ·
  configuration https://playwright.dev/docs/test-configuration
