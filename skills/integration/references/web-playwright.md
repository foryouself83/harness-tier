# Web-Frontend Detection + Playwright Integration Testing SSOT

> **Note**: Web-frontend detection is a **heuristic**, not a definitive SSOT. The signal list is based on common
> conventions, and non-standard setups or monorepo structures can produce false positives. Always validate the
> detection result against context.

---

## 1. Web-Frontend Detection Signals

### 1.1 Primary signal — package.json dependency allowlist

If `package.json`'s `dependencies` or `devDependencies` contains one or more of the packages below, classify it as a web frontend:

| Package | Framework |
|---|---|
| `react` | React |
| `vue` | Vue.js |
| `next` | Next.js |
| `nuxt` | Nuxt |
| `svelte` | Svelte / SvelteKit |
| `@angular/core` | Angular |
| `solid-js` | SolidJS |
| `astro` | Astro |

### 1.2 Supporting signals

When present alongside the primary signal, they strengthen the web verdict:

| Signal file/path | Meaning |
|---|---|
| `vite.config.ts` / `vite.config.js` | Vite-based build |
| `index.html` (root or `public/`) | SPA entry point |
| `public/` directory | Static asset serving |
| `webpack.config.js` | Webpack bundler |
| `next.config.js` / `nuxt.config.ts` | Framework config |

### 1.3 Non-web signals (if present, the non-web verdict takes precedence)

| Signal | Verdict |
|---|---|
| `"bin"` field in `package.json` | CLI tool |
| `"react-native"` dependency | React Native (mobile) |
| `metro.config.js` | React Native bundler |
| `pubspec.yaml` | Flutter |
| `main.go` / `go.mod` (+ no web signals) | Go CLI/service |

> **Electron is not listed here** — it is checked *before* this table (see `integration/SKILL.md` §2) and is
> its own verdict, not a non-web signal. For the full procedure, see [`electron.md`](electron.md).

---

## 2. Parsing Playwright Config

### 2.1 Config-file detection order

```bash
ls playwright.config.ts playwright.config.js \
   playwright.config.mjs playwright.config.cjs 2>/dev/null | head -1
```

### 2.2 testDir / testMatch defaults

Source: [Playwright TestConfig API](https://playwright.dev/docs/api/class-testconfig)

| Config key | Default | Description |
|---|---|---|
| `testDir` | `./tests` | Root directory for case files |
| `testMatch` | `**/*.@(spec\|test).?(c\|m)[jt]s?(x)` | Glob pattern for case files |

If a value is specified in the config file, use that value.

---

## 3. Discovering and Running Cases

### 3.1 Discovering case files

```bash
# Matches the testMatch default exactly: **/*.@(spec|test).?(c|m)[jt]s?(x)
find ./tests -regextype posix-extended -regex '.*\.(spec|test)\.(c|m)?[jt]sx?' 2>/dev/null
```

**Handling zero cases**: use the `playwright-scaffold` skill to generate a **main-screen smoke** (a deterministic
"does the app come up?" check) and run it immediately (it does not generate arbitrary user scenarios). Extend it into
richer real cases with codegen:

```bash
# After the starter smoke, record real scenarios with codegen and save them under tests/
npx playwright codegen https://your-app.example.com
```

### 3.2 Deterministic run — `--reporter=json` (+junit)

Source: [Playwright reporters](https://playwright.dev/docs/test-reporters) · [Playwright CLI](https://playwright.dev/docs/test-cli)

```bash
# Emit JSON + JUnit reporters together. To capture to files, set OUTPUT_NAME (otherwise JSON goes to stdout).
PLAYWRIGHT_JSON_OUTPUT_NAME=results.json \
PLAYWRIGHT_JUNIT_OUTPUT_NAME=results.xml \
  npx playwright test --reporter=json,junit
```

`--reporter=json` outputs to the file named by `PLAYWRIGHT_JSON_OUTPUT_NAME` when it is set, and to stdout when it is not.

### 3.3 Parsing the result JSON

Top-level structure of `results.json`:

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

Parsing example (defensive — a crashed or incomplete Playwright run must still produce a clear FAIL
report, not an uncaught exception):

```bash
node -e "
  const fs = require('fs');
  let r;
  try { r = JSON.parse(fs.readFileSync('results.json', 'utf8')); }
  catch (e) { console.log('FAIL: results.json missing or invalid (' + e.message + ')'); process.exit(1); }
  const s = r && r.stats;
  if (!s || typeof s.unexpected !== 'number') {
    console.log('FAIL: results.json has no stats — the Playwright run likely crashed before completing');
    process.exit(1);
  }
  console.log('PASS:', s.expected, '/ FAIL:', s.unexpected, '/ SKIP:', s.skipped);
  process.exit(s.unexpected > 0 ? 1 : 0);
"
```

---

## 4. Playwright MCP (auxiliary path)

Source: [Getting started with Playwright MCP](https://playwright.dev/docs/getting-started-mcp) · [playwright-mcp GitHub](https://github.com/microsoft/playwright-mcp) (Apache-2.0)

Use the session's playwright MCP only for **exploration when cases are absent** or for **manual confirmation**.
It is not the SSOT for regression testing and does not guarantee deterministic reproduction.

```bash
# Take a screenshot with a headless browser, without MCP
npx playwright screenshot --browser chromium https://your-app.example.com screenshot.png
```

---

## 5. Best Practices

Source: [Playwright Best Practices](https://playwright.dev/docs/best-practices) · [Writing tests](https://playwright.dev/docs/writing-tests) · [Test configuration](https://playwright.dev/docs/test-configuration)

| Principle | Content |
|---|---|
| Locator priority | `getByRole` > `getByLabel` > `getByText` > `getByTestId` order |
| Independent tests | Each test starts from an independent state (initialize with `beforeEach`) |
| Avoid `waitForSelector` | Use the auto-waiting `expect(locator).toBeVisible()` |
| Parallel execution | Speed up with `fullyParallel: true` (when no shared state) |
| Environment isolation | Inject `baseURL` via an environment variable (`process.env.BASE_URL`) |
| Fixed reporter | Fix `--reporter=json,junit` in CI (standardize CI parsing) |

---

## 6. SSOT URL Summary

| Item | URL | License |
|---|---|---|
| Best Practices | https://playwright.dev/docs/best-practices | Apache-2.0 |
| Writing tests | https://playwright.dev/docs/writing-tests | Apache-2.0 |
| Test configuration | https://playwright.dev/docs/test-configuration | Apache-2.0 |
| TestConfig API (testDir/testMatch) | https://playwright.dev/docs/api/class-testconfig | Apache-2.0 |
| Reporters (json/junit) | https://playwright.dev/docs/test-reporters | Apache-2.0 |
| CLI | https://playwright.dev/docs/test-cli | Apache-2.0 |
| Getting started with MCP | https://playwright.dev/docs/getting-started-mcp | Apache-2.0 |
| playwright-mcp GitHub | https://github.com/microsoft/playwright-mcp | Apache-2.0 |
