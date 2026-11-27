---
name: ux-review
description: Use when someone asks whether a web UI is usable or intuitive — a screen users find confusing, a multi-step task like signup or checkout a first-time user might not get through, a UX or accessibility pass before shipping, or a request to make a page easier to use. Review before any fix is written. Judged only from the builder's own context, a screen passes while a first-time user still trips on it.
argument-hint: "[flow or URL] [--full]"
---

# ux-review

Reviews a web app's screens from three seats and applies only the fixes the user picks:

- **owner** — this session. Knows the product, its code, its design system and the intended
  path. Prepares the capture, merges, triages and fixes.
- **customer** — an isolated subagent that sees only the capture and a one-line task, like a
  first-time user.
- **auditor** — an isolated subagent that judges the capture against a checklist, with no
  knowledge of why the screen looks the way it does.

Outsiders run from the role file `agents/ux-outsider.md`. Their whole value is the missing
context: never pass them code, intent or the design system in capture mode.

**Interaction.** Wherever this skill asks the user something, use the host's blocking question
tool already in your tool list, matched by capability rather than by a host-specific name; if it
is listed but not loaded, load it first with the host's tool-discovery primitive; only when no
such tool is listed, or a question call errors, offer numbered options in chat and end your turn
to wait for the reply — never answer the question yourself or skip it.

References, read on demand: [checklist](references/checklist.md) (the auditor's input),
[finding format](references/finding-format.md), and the full sources behind the checklist —
[heuristics](references/heuristics.md), [accessibility](references/accessibility.md),
[laws of UX](references/laws-of-ux.md), [visual hierarchy](references/visual-hierarchy.md),
[forms](references/forms-and-input.md), [microcopy](references/microcopy.md).

## 1. Scope

`$ARGUMENTS` may name flows or URLs, and `--full`.

- **Named flows or URLs** → review those.
- **Nothing named** → diff mode: the UI files this branch changed against the integration branch,
  committed or not.

```bash
base=$(python3 -c "import pathlib,sys,yaml
p = pathlib.Path(sys.argv[1], '.claude/harness-tier/config/flow-config.yaml')
c = (yaml.safe_load(p.read_text(encoding='utf-8')) or {}) if p.exists() else {}
print((c.get('branches') or {}).get('integration', ''))" "$(git rev-parse --show-toplevel 2>/dev/null)" 2>/dev/null)
[ -n "$base" ] || base=$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')
echo "base: ${base:-none}"
{ [ -n "$base" ] && git -c core.quotePath=false diff --name-only "origin/$base...HEAD"
  git -c core.quotePath=false diff --name-only HEAD
  git -c core.quotePath=false ls-files --others --exclude-standard --full-name :/
} 2>/dev/null | sort -u | grep -E '\.(tsx|jsx|vue|svelte|astro|html|css|scss|sass|less)$' \
  || echo "no UI file in this branch's diff"
```

Map the changed files to the routes or screens they render (file-based routing first: `app/`,
`pages/`, `src/routes/`), and group screens into flows. When a file's mapping is uncertain (a
shared component, a style sheet), ask the user which screens to cover rather than guessing. When
the list has no UI file, report `no UI file in this branch's diff` and ask the user (structured
choice) which flow to review, or stop — never fall back to reviewing the whole app silently.

For each flow, settle one task line in the user's terms ("create an account and verify the
email"): from `docs/srs/` when it describes the flow, otherwise ask the user. Note the
design-system sources you will triage against (tokens, the component library) — outsiders never
see them.

`--full` reviews every primary flow and splits the auditor by checklist section (step 4).

## 2. Prepare

**Web app and base URL.** Detect the web app with
[web-playwright.md](../integration/references/web-playwright.md) §1, and the base URL with
[playwright-scaffold](../playwright-scaffold/SKILL.md) Step 1. In a monorepo, the app directory
is the one whose `package.json` carries the framework; every later command runs from it.
No base URL resolves and the user cannot name one → **static mode**.

**Dependencies.** Check both packages from the app directory:

```bash
node -e "for (const m of ['playwright', '@axe-core/playwright']) { try { require.resolve(m); console.log('ok ' + m) } catch { console.log('missing ' + m) } }"
```

For each `missing`, show the install command for the lockfile present (`npm install -D`,
`pnpm add -D`, `yarn add -D`; `playwright` also needs `npx playwright install chromium`) and ask
the user (structured choice) whether to install. Never install without a yes.

When `playwright` is present, check its version — `ariaSnapshot` needs 1.49 or later:

```bash
node -p "require('playwright/package.json').version"
```

Older → offer the upgrade the same way,
`npm install -D playwright@latest` and `npx playwright install chromium` (or the lockfile's
equivalent); declined counts as `playwright` declined.

- `playwright` declined → **static mode**.
- Only `@axe-core/playwright` declined → capture without axe; outsiders get no `axe.json`.

**App running.** The app must answer at the base URL. Start it the way the project documents
(`npm run dev`, a compose file) only after asking the user; when it cannot start → **static mode**.

**Authentication.** When a flow sits behind a login, ask the user for a Playwright
`storageState` file path or a test account. Never capture a login wall in place of the screen.

**Run directory.**

```bash
root=$(git rev-parse --show-toplevel) || exit 1
mkdir -p "$root/.claude/harness-tier/ux-review"
printf '*\n' > "$root/.claude/harness-tier/ux-review/.gitignore"
run="$root/.claude/harness-tier/ux-review/$(date +%Y%m%d-%H%M%S)"
mkdir -p "$run" && echo "$run"
```

The `.gitignore` keeps every run out of the host's commits without touching the host's own
`.gitignore`. The run directory always sits at the repository root, even in a monorepo; write
`flows.json` and `capture.mjs` to the absolute path the block prints.

## 3. Capture

Write `flows.json` into the run directory:

```json
[
  {
    "flow": "signup",
    "task": "create an account and verify the email",
    "screens": [
      { "name": "form", "steps": [{ "goto": "/signup" }] },
      { "name": "error", "steps": [{ "fill": ["#email", "not-an-email"] }, { "click": "text=Create account" }] }
    ]
  }
]
```

Steps run in order and carry over within a flow: `goto` (path or URL), `click` (selector),
`fill` (`[selector, value]`), `press` (`[selector, key]`), `wait` (selector). A step with
`"viewport": "desktop"` or `"viewport": "mobile"` runs only there — use it for controls one
layout hides, such as a menu button that exists only on mobile. Cover the states the task
meets: empty, filled, error, success.

Write this as `capture.mjs` in the run directory, unchanged except `BASE_URL` and `STORAGE`:

```js
import { createRequire } from "node:module";
import { readFileSync, mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const BASE_URL = "http://localhost:3000";
const STORAGE = null; // path to a storageState JSON, or null
const req = createRequire(process.cwd() + "/");
const { chromium } = req("playwright");
let AxeBuilder = null;
try { AxeBuilder = req("@axe-core/playwright").default; } catch { /* axe declined */ }

const RUN = dirname(fileURLToPath(import.meta.url));
const flows = JSON.parse(readFileSync(join(RUN, "flows.json"), "utf8"));
const VIEWPORTS = { desktop: { width: 1280, height: 800 }, mobile: { width: 390, height: 844 } };
const TAGS = ["wcag2a", "wcag2aa", "wcag21aa", "wcag22aa"];

const browser = await chromium.launch();
let shots = 0, violations = 0;
for (const [vp, viewport] of Object.entries(VIEWPORTS)) {
  for (const f of flows) {
    const ctx = await browser.newContext({ viewport, ...(STORAGE ? { storageState: STORAGE } : {}) });
    const page = await ctx.newPage();
    mkdirSync(join(RUN, f.flow), { recursive: true });
    for (const s of f.screens) {
      for (const st of s.steps) {
        if (st.viewport && st.viewport !== vp) continue;
        if (st.goto) await page.goto(new URL(st.goto, BASE_URL).href);
        if (st.click) await page.click(st.click);
        if (st.fill) await page.fill(...st.fill);
        if (st.press) await page.press(...st.press);
        if (st.wait) await page.waitForSelector(st.wait);
      }
      await page.waitForLoadState("networkidle").catch(() => {});
      const base = join(RUN, f.flow, s.name);
      await page.screenshot({ path: `${base}.${vp}.png`, fullPage: false });
      shots++;
      if (vp === "desktop") {
        writeFileSync(`${base}.aria.txt`, await page.locator("body").ariaSnapshot());
        if (AxeBuilder) {
          const r = await new AxeBuilder({ page }).withTags(TAGS).analyze();
          writeFileSync(`${base}.axe.json`, JSON.stringify(r.violations, null, 1));
          violations += r.violations.length;
        }
      }
    }
    await ctx.close();
  }
}
await browser.close();
console.log(`run: ${RUN}\nscreenshots: ${shots}\naxe violations: ${AxeBuilder ? violations : "not run"}`);
```

Run it from the app directory, on the newest run:

```bash
run=$(ls -td "$(git rev-parse --show-toplevel)"/.claude/harness-tier/ux-review/*/ | head -1)
node "${run}capture.mjs"
```

Only the summary prints; every capture stays on disk. A step that throws names its selector —
fix `flows.json` and run again rather than reviewing a partial capture.

## 4. Outsider review

Per flow, dispatch two outsiders in parallel. Each prompt carries exactly:

```text
persona: customer | auditor
task: <the flow's task line>
files: <absolute paths of this flow's captures, and finding-format.md>
checklist: <auditor only: checklist.md path and section names>
```

- **customer** gets `*.desktop.png`, `*.mobile.png`, `*.aria.txt` and `finding-format.md`.
- **auditor** gets the same plus `*.axe.json`, and the checklist sections that fit the flow
  (`Forms` only where there is a form).
- **`--full`** → one auditor per checklist section instead of one auditor.

**Dispatch.** Dispatch subagent `ux-outsider` once per outsider, with no conversation context
and the prompt above as its whole task. A host that hands its project instructions to subagents
(Codex passes `AGENTS.md`) weakens the isolation; say so in the report.

**No subagent available** → write `outsiders: skipped` in the report and go on with axe and your
own checklist pass. Never role-play an outsider in this context: you already know the intent.

**Static mode** (no running app, or `playwright` declined): no capture exists, so the customer
does not run — source code or an outline you wrote would carry your intent and make its pass
meaningless. Dispatch one auditor with the flow's component files and the checklist. Record
`mode: static` and `customer: not run (static mode)`, and tell the user what would let the app
run so the next review gets a customer.

## 5. Merge

1. Turn each customer blocker into a finding: pick the checklist id that explains it and rate
   severity per [heuristics.md](references/heuristics.md). Compare the customer's `Path` with the
   intended path; each divergence is a blocker with `reason: path diverged`.
2. Add the axe violations (`heuristic: axe:<rule id>`, severity by axe impact: critical 4,
   serious 3, moderate 2; minor dropped).
3. Deduplicate on `(screen, element, heuristic)`; keep the highest severity and every source.
4. Sort by severity, highest first.
5. Renumber the merged findings `F1`…`Fn` in that order. Outsider ids collide across auditors;
   these are the ids the report and step 7 use.

## 6. Triage

Mark each finding:

- `accept` — a real problem on this product.
- `contest` — conflicts with the design system or a deliberate product decision; name it.
- `needs-human` — you cannot tell without the user.

Write `report.md` in the run directory in the [finding format](references/finding-format.md).
In chat, give only the counts by status and severity and the report path.

## 7. Choose and fix

Ask the user (multi-select) which `accept` and `needs-human` findings to fix, highest severity
first. None chosen → stop with the report.

Apply only the chosen fixes, each against its finding id, and mark them `fixed` in the report.
Use the project's components and tokens rather than the generic fix an outsider suggested.

Do not commit. Tell the user the changes are in the working tree, and to
commit them through `/flow`, which classifies them like any other code change.

## 8. Re-check

Capture mode only, once. Create a new run directory with step 2's block, so the original capture
stays the report's evidence. Copy into it the `flows.json` entries for
every screen of each flow a fix touched — steps carry over within a flow, so a later screen
cannot start alone — run step 3 there, dispatch one customer per affected flow with the same
task, and append its answer and the new run path to the original report under `## Re-check`.
A blocker that remains is reported, not looped on.
