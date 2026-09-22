# Manual verification

**English** · [한국어](manual-verification.ko.md) · [Usage guide](../../USAGE.md)

Three skills you call yourself, when you need them — none is a gate, and none runs
automatically before a promotion.

## `/integration`

```text
/integration
```

Runs a project's existing integration suite deterministically, or collects scenarios from a
human when there is none. It reads `docs/verification/integration.md` first when
`/harness-init` generated one; otherwise it falls back to its own web/non-web references.

Detection checks Electron first, then web, then falls back to non-web:

| Verdict | Condition |
|---------|-----------|
| Electron | an `"electron"` dependency exists |
| Web | no Electron signal, and either an allowlisted framework dependency or a supporting signal (`index.html`, a bundler config, `public/`) — so a framework-less web app is still Web |
| Non-web | a CLI/React-Native/Flutter/Go signal, or none of the above matched |

- **Web** — runs the existing Playwright cases with `--reporter=json` and reports PASS/FAIL,
  writing `results.json`/`results.xml`. Zero cases hands off to
  [`playwright-scaffold`](#playwright-scaffold) rather than scaffolding inline. A
  config-declared `testDir` that does not exist is reported as a misconfiguration, not
  scaffolded.
- **Electron** — the renderer runs automatically via Playwright; the main process is a
  checklist a human works through, and both results are reported together.
- **Non-web** — asks you for scenarios and pass criteria, per project type (CLI, React
  Native, Flutter, Go).

## `/performance`

```text
/performance
```

Reads `docs/verification/performance.md` when present; otherwise falls back to its built-in
catalog (no catalog exists for Go's N+1 patterns specifically).

- **Static flagging** — language-specific anti-patterns (N+1 queries, bad query plans,
  front-end re-render churn) plus a language-agnostic recursion/complexity pass with `lizard`,
  which always runs.
- **API load testing**, when a backend exists — confirms `BASE_URL` with you via
  `AskUserQuestion` before running any load (a guessed URL points load at the wrong host, and
  the server needs to already be running); reports p50/p95/p99, throughput and error rate
  against your SLO. The default tool is k6 with `openapi-to-k6`; because both are AGPL, `oha`,
  `autocannon` and `vegeta` are the MIT-licensed fallback.

No tool here is installed automatically — `lizard`, `k6` and `openapi-to-k6` are guided, not
auto-installed, since fetching them into your environment is your call.

## `playwright-scaffold`

```text
/playwright-scaffold
```

Idempotently creates a first Playwright case for a web project with zero cases — usually
invoked by `/integration` rather than directly.

1. **Detects `baseURL`** from `playwright.config.*`, other config files, or asks you to
   confirm.
2. **Detects `testDir` and language** — a `playwright.config.ts` counts as TypeScript even
   with no `tsconfig.json`, so a TS-only Playwright project still gets a `.ts` spec.
3. **Writes** `<testDir>/main.smoke.spec.<ts|js>` only when nothing is there yet:
   `goto('/')` + response OK + non-empty title, using `use.baseURL` rather than a hardcoded
   URL. A config-declared `testDir` that does not exist is reported, not created.
4. **Settles `playwright.config`** — adds `use.baseURL` to an existing config that lacks one,
   or writes a minimal config when none exists; reports the `projects[]` shape a monorepo
   needs. If `@playwright/test` itself is missing, it guides the install rather than running
   it without asking.

It only writes files — running the suite is `/integration`'s job.
