# Electron Integration Testing — Hybrid Procedure (SSOT)

> Electron apps are neither pure Web nor pure Non-web: the renderer process is Chromium-based and can be
> driven by Playwright; the main process (Node.js, IPC, filesystem, native APIs) cannot. **This file is the
> single source of truth for the Electron exception** — other files link here instead of restating it.

---

## 1. Renderer-Process Automation (Playwright)

Playwright supports Electron directly via `_electron.launch()` — **not** the plain `chromium` browser channel,
which cannot attach to an existing Electron app's renderer process:

```javascript
const { _electron: electron } = require('playwright');
const app = await electron.launch({ args: ['main.js'] });
const window = await app.firstWindow();
await window.waitForLoadState('domcontentloaded');
// assertions against `window` use the same Locator API as a normal Page
await app.close();
```

Source: https://playwright.dev/docs/api/class-electron (Apache-2.0)

`electron.launch()` returns an `ElectronApplication`, and `app.firstWindow()` returns its first `Page` — see the
[`ElectronApplication` API](https://playwright.dev/docs/api/class-electronapplication) for the full set of methods
available on that object (e.g. `windows()`, `context()`, `evaluate()` against the main process).

Reuse the same `playwright.config.*`/`testDir`/`--reporter=json,junit` conventions as
[`web-playwright.md`](web-playwright.md) §2-§3 for the renderer suite — only the launch mechanism differs
(`_electron.launch()` instead of `browser.newPage()`).

---

## 2. Main-Process Scenarios — human-in-the-loop

IPC handlers, filesystem access, and native OS integration (menus, tray, notifications) are not reachable
through Playwright. Collect these via `AskUserQuestion`, following the same procedure as
[`non-web.md`](non-web.md) §2 (scenarios + pass criteria + manual checklist).

---

## 3. Report Format

```
## Electron Integration Test Results — <date>

### Renderer (Playwright)
| Suite | Passed | Failed | Skipped | Verdict |
|---|---|---|---|---|
| tests/renderer/app.spec.ts | 4 | 0 | 0 | PASS |

### Main Process (manual checklist)
| Scenario | Verdict |
|---|---|
| IPC: save-file dialog returns a valid path | PASS |

**Overall verdict**: PASS
```

---

## 4. SSOT URL Summary

| Item | URL | License |
|---|---|---|
| Playwright Electron API | https://playwright.dev/docs/api/class-electron | Apache-2.0 |
| Playwright ElectronApplication | https://playwright.dev/docs/api/class-electronapplication | Apache-2.0 |
