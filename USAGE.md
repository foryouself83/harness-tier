# harness-tier Usage Guide

**English** · [한국어](USAGE.ko.md)

If [README](README.md) is "core idea + installation", this document covers **detailed
descriptions of each skill, detailed settings, usage, troubleshooting, and
update/removal**. (The internals of *how* the plugin works are in the developer-facing
[CLAUDE.md](CLAUDE.md).)

## Table of contents

1. [Installation flow (summary)](#1-installation-flow-summary)
2. [Settings in detail](#2-settings-in-detail)
3. [Skills in detail](#3-skills-in-detail)
4. [Teams notifications](#4-teams-notifications)
5. [Release token write permission](#release-token-write-permission)
6. [Troubleshooting](#6-troubleshooting)
7. [Update & removal](#7-update--removal)

---

## 1. Installation flow (summary)

The full installation procedure, including installing dependencies, is in
[README](README.md#installation). In short:

1. **Dependencies** — Python ≥ 3.8 + PyYAML (+ pre-commit), the `superpowers` plugin.
2. **Install the plugin** — `/plugin marketplace add foryouself83/harness-tier` →
   `/plugin install harness-tier@harness-tier`.
3. **`/harness-init`** — generate the project harness (`CLAUDE.md`, docs); new projects start here.
4. **`/flow-init`** — wire up governance such as the commit gate and Teams (interactive, idempotent).
5. **Finish** — `pre-commit install --hook-type commit-msg --hook-type pre-push`.

Everything created in the host repo after installation is gathered under a single
**`.claude/harness-tier/`** directory:

| Path | Owner | git | Contents |
|------|-------|-----|----------|
| `.claude/harness-tier/config/` | host/plugin | tracked | `flow-config.yaml` (team-shared settings) · `flow-tiers.yaml` (policy) · `teams-webhooks.json` |
| `.claude/harness-tier/config/.teams-webhooks.local.json` | user | gitignored | Personal Teams webhook |
| `.claude/harness-tier/scripts/` | plugin | tracked | Copied gate scripts |
| `.claude/harness-tier/.flow/` | runtime | gitignored | Gate progress records (evidence) |

---

## 2. Settings in detail

### 2.1 `flow-config.yaml` — repo-specific values (team-shared)

`/flow-init` creates `.claude/harness-tier/config/flow-config.yaml`. It is **git-tracked**,
so every developer sharing the repo uses the same settings. Humans edit it.

```yaml
branches:
  integration: dev          # integration branch where features merge
  staging: stage            # QA/RC promotion branch
  production: main           # production release branch
  feature_prefix: "feature/" # prefix for day-to-day work branches

modules:                     # per-module monorepo pre-checks (when modules use different languages/tools)
  - name: api
    path: services/api/      # run checks when something under this path changes
    checks:                  # only the ones that exist — /flow-init drafts from the harness SSOT, humans edit
      lint:        "ruff check services/api"
      static:      "uv run pyright services/api"
      import_lint: "uv run lint-imports --config services/api/.importlinter"
      test:        "uv run pytest services/api"
      security:    "uv run bandit -r services/api"

review_checklist:            # items to check in the Dev-tier domain review
  - "regression / regression tests pass"
  - "cross-service contract / cross-service contract validity"
  - "DB transaction / migration safety"
  - "async task idempotency"

doc_sync:                    # doc-sync targets
  index: CLAUDE.md
  dirs:
    - "docs/"
    - ".claude/rules/"
  service_docs: "services/*/CLAUDE.md"
```

**When each `checks` key runs** (module pre-checks):

| Key | When |
|-----|------|
| `lint` · `static` · `import_lint` · `test` | changed modules, **every commit** (Dev gate) |
| `security` | all modules, **at staging/release promotion** (security-scan gate) |

**Optional sections** (only when you need a REST API / release automation; `/flow-init`
asks and renders them):

- **`contract_test`** — REST API contract testing (schemathesis). With `enable: true`,
  `/flow-init` generates `.github/workflows/api-contract.yml`. Slots: `branches` ·
  `schema` (OpenAPI URL/path) · `base_url` · `server` (compose_file/health_url/health_timeout) ·
  `tool`/`action_ref` (pinned once at setup).
- **`unit_test`** — unit-test CI safety net. The local flow gate runs unit tests only on
  Claude-session commits; direct/terminal/CI/GitHub commits bypass it, so with `enable: true`
  `/flow-init` generates `.github/workflows/unit-test.yml` to run them in CI too. Slots:
  `branches` · `timeout_minutes` (per-job cap, default 10) · `jobs[]` — one entry per
  language/module (`name`/`language`/`version`/`setup`/`test`), rendered into a
  `strategy.matrix.include`. A `language` of python/node/java/go/rust uses that official setup
  action; any other value lets the `setup` command prepare the runtime. Declared independently
  of `modules[]` (local gate and CI run in different contexts).
- **`versioning`** — release automation such as python-semantic-release. With `enable: true`
  it renders the release / branch-naming / entropy-check workflows. The **GitHub Release
  body** is the latest grouped `CHANGELOG.md` section (semantic-release output — grouped by
  type, plumbing commits filtered), falling back to GitHub's auto-generated notes if the
  changelog is missing/empty.

### 2.2 `flow-tiers.yaml` — tier→gate policy (do not edit)

It sits in the same `config/` folder but is **plugin-owned**. It is overwritten on every
install, so **do not edit it directly** (if you need to change it, edit the plugin SOURCE
and re-run `/flow-init`). This file defines which gates are mandatory for each tier.

### 2.3 Risk tiers and gates

Work is classified into four tiers (two axes), and the tier determines **which gates must
pass before it can commit**.

| Tier | When | superpowers | Mandatory gates |
|------|------|:---:|-----------------|
| `docs` | no-code change (docs/comments/config values) | ✗ | `doc-sync` |
| `dev` | change with code (feature/fix) | ✓ | `precommit` (changed modules lint/static/import_lint/test) · `review` (domain review) · `doc-sync` |
| `staging` | QA/RC promotion (integration→staging) | ✓ | `precommit` · `review` · `security-scan` (all-module security) |
| `release` | production deploy (staging→production) | ✓ | `precommit` · `review` · `security-scan` · `security` (security review) |

- **`precommit` · `security-scan`** are executed by the commit hook itself (no marker).
  Removing one from a tier's `gates` list disables just that check.
- **`review` · `doc-sync` · `security`** leave an evidence marker after `/flow` passes the
  gate; the commit hook passes only when the marker exists.
- The single source of truth for risk classification is the `risk-tiers` rule, injected
  automatically every session.

> Performance/integration checks are separated from the gates and provided as **manual
> skills** `/performance` · `/integration` (non-enforcing — recommended before promotion).

---

## 3. Skills in detail

The slash commands are all skills. Here are their timing, arguments, and behavior.

### 3.1 `/flow` — day-to-day work router

```text
/flow <free-text request>
```

The **mandatory first step for all code changes**. Sequence:

1. **Resolve input** — take the request text as-is as the task.
2. **Risk classification** — split Docs/Dev by whether the actual change is **code or not**.
   - docs/comments/config values only → **Docs**
   - `.py`/`.js`/`.ts`… code, new features, DB schema, dependency changes, etc. → **Dev**
3. **Confirm the tier** — ask for the classification (overridable), then switch to a work
   branch after confirmation. When uncertain, escalate one tier up.
4. **Execute** — run the tier's process and gates.
   - **Docs**: edit directly → reconcile docs via `doc-sync` → commit
   - **Dev**: `superpowers` pipeline (design → plan → implement → verify → review) →
     domain review (against `review_checklist`) → `doc-sync` → commit

> **Promotion (Staging/Release)**: integration→staging and staging→production merges are
> driven by the **target branch** (no separate marker needed). Each tier's mandatory gates
> (§2.3) must pass before it can commit.

> **`/flow` cannot be skipped.** If you commit without going through it, there's no tier
> marker and the gate blocks the commit as **unclassified**. If a repo doesn't need
> enforcement, remove the gate with `/flow-uninstall`.

### 3.2 `/flow-init` — setup/update wizard

```text
/flow-init        # no arguments — interactive
```

Handles **governance wiring** such as the commit gate and Teams. **Safe to re-run.**

- **First run** (no config) — dependency check + install consent, generate
  `flow-config.yaml`, register the commit gate, check/create pre-commit, register
  auto-update, wire up Teams.
- **Re-run** (config present) — first runs **re-sync** non-interactively (re-copy gate
  scripts/policy, repair the gate path), then offers to backfill any missing config slots,
  then asks what to reconfigure (re-sync only if you pick nothing).

Everything written to the host lives under `${CLAUDE_PROJECT_DIR}/.claude/harness-tier/`
(except the files external tools pin: `.gitignore`, `.pre-commit-config.yaml`,
`.claude/settings.json`, `.github/workflows/`).

### 3.3 `/flow-uninstall` — remove host-side wiring

```text
/flow-uninstall   # no arguments — interactive (removes after confirmation)
```

The **inverse of `/flow-init`**. Unregisters the commit gate and marketplace, strips the
`.gitignore`/`CLAUDE.md` managed blocks, and deletes `.claude/harness-tier/`. pre-commit/git
hooks carry too much destruction risk, so it only **reports** them and guides manual removal.

> ⚠️ **Run it before `/plugin uninstall`** — the cleanup tool lives inside the plugin, so if
> you remove the plugin first you can't use this skill (manual cleanup in §7).

### 3.4 `/harness-init` — generate the project harness

```text
/harness-init     # no arguments — interactive wizard
```

Generates a `CLAUDE.md`, rules, and technical docs tailored to your project. It is a
**separate, independent command** from `/flow-init` (governance wiring). Sequence:

1. **Framework detection** — determine language/framework from dependency files
   (`package.json`, `pyproject.toml`, `go.mod`, `Cargo.toml`, `pom.xml`/`build.gradle[.kts]`,
   `*.csproj`, `CMakeLists.txt`/`vcpkg.json`/`conanfile.*`, `composer.json`, `Gemfile`,
   `Package.swift`, `build.sbt`, etc.) and directories.
2. **Research** — use multiple subagents (`harness-researcher`) to web-research current
   conventions, best practices, and free off-the-shelf solutions; if code exists, analyze
   its real conventions with `harness-code-analyzer`. Versions are chosen not as *each
   one's latest* but as a **compatible set that boots together**.
3. **Generation** — produce `CLAUDE.md`, rules, and technical docs (SRS, SDS, code style,
   onboarding, etc.) into classified folders. By default it creates **only `.md` files** and
   does not touch actual config files.
4. **Critique & verification** — `harness-critic` checks the output's quality, consistency,
   and version compatibility (config coherence + runtime-combination compatibility) and
   refines it.
5. **Preview then confirm** — it shows what it will create first, and **only writes files
   after you confirm**.
6. **Cleanup** — removes temporary research copies made during the work (keeps only the
   final docs).

- **No overwrite** — existing files are updated only in managed blocks, and conflicts are reported.
- **Actual settings** like security scanners, CI, folder creation, and version pinning are
  applied **only with per-item consent** during the interview.
- **It does not generate slash commands.**

| | `/flow-init` | `/harness-init` |
|---|---|---|
| Purpose | governance wiring (gates, Teams) | generate the project harness (`CLAUDE.md`, docs) |
| When | once, at repo setup | any time, new or existing repos |

### 3.5 `doc-sync` skill

Analyzes code and doc changes via `git diff`, updates related docs, and keeps the doc set
consistent.

- **Code → docs**: find related docs by the changed code's keywords (class/field/type/route/
  function) and update them.
- **Docs → docs**: check cross-references, factual consistency, and index sync across the
  `flow-config.doc_sync` targets (index/dirs/service_docs). If a module matched by
  `service_docs` has no local `CLAUDE.md`, create one from a best-practice template; if it
  exists, only fill in the gaps (preserving existing content).

`/flow` calls it automatically. To see only the plan, say "doc-sync preview".

### 3.6 `harness-insight` skill

```text
/harness-insight [period]   # e.g. 7 days · 2 weeks · 30 days (default 7 days)
```

Aggregates the Claude Code transcript (sent prompts, tool_use) over the given period and
**prints a 4-section insight report in the conversation**, then reviews and consolidates
the accumulated **project memory**.

- Derives the distribution of work done, repeated instructions (harness candidates),
  activity hotspots, and next actions.
- Memory consolidation: delete invalid/duplicate entries; promote persistent knowledge to
  `.claude/rules` or `docs/` (deletion/promotion **only after user approval**).
- **It does not create a report file (.md)** (intermediate txt is deleted after output).

### 3.7 Manual verification skills — `/integration` · `/performance` · `playwright-scaffold`

These are **manual skills**, not gates (call them directly when needed, recommended before
promotion).

- **`/integration`** — for a web front-end, run existing Playwright cases deterministically
  (`--reporter=json`) and report PASS/FAIL. If it's web but has zero cases, use
  `playwright-scaffold` to create a main-screen smoke test and run it immediately; if it's
  not web, ask the human for scenarios and pass criteria (human-in-the-loop).
- **`/performance`** — statically flag language-specific performance anti-patterns
  (N+1, query plans, complexity, front-end re-renders); if there's a backend, extract APIs
  from OpenAPI and load-test each with k6 → report p50/p95/p99, throughput, and error rate
  against the SLO.
- **`playwright-scaffold`** — idempotently create a deterministic "main-screen smoke" case
  for a web project. It finds the baseURL from config/codebase, confirms it, and generates
  `goto('/')` + response OK + non-empty title. Usually invoked by `/integration` when there
  are zero cases.

---

## 4. Teams notifications

Notifies a Microsoft Teams channel when waiting for input, or at any point you choose.

### Prep — per-channel webhook URLs

For each channel you'll use (personal, branch), obtain a Teams **incoming webhook URL** (a
URL built with a Power Automate workflow — includes a `sig=` token). Channels can be turned
on incrementally: start with just the personal channel and add branch channels later.

### Webhook setup — 2 files

| File | git | Channel |
|------|-----|---------|
| `.claude/harness-tier/config/teams-webhooks.json` | tracked | team channels (dev/stage/main, etc.) |
| `.claude/harness-tier/config/.teams-webhooks.local.json` | gitignored | personal channel (`personal`) |

```bash
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
# Register a channel URL
python3 "${ROOT}/.claude/harness-tier/scripts/teams_alert.py" --set personal https://...
# Manual notification
python3 "${ROOT}/.claude/harness-tier/scripts/teams_alert.py" --channel personal --title "..." --text "..."
```

- If a channel URL is empty, it is **silently skipped**. A failed notification never blocks work.
- **Automatic** — on permission/input waits, a notification goes to the `personal` channel
  (Notification hook).
- **Manual (right before presenting options)** — `AskUserQuestion` does not fire an
  automatic notification, so notify manually with the command above right before waiting for input.

> Once you configure a Teams channel, `/flow-init` inserts a notification-guidance block
> into the host `CLAUDE.md` (translated to match the host doc's language) so the repo's
> Claude notifies you itself when waiting for input.
> **Security exception** — a tracked Power Automate URL is an incoming webhook, so the worst
> case is channel-message injection (no data exfiltration or privilege escalation); treat it
> as a secret-scanner exception.

---

## Release token write permission

The release workflow pushes the version bump/tag, so its token needs **write**.

> **Default** — the workflow authenticates with the auto-provided `GITHUB_TOKEN`. Every
> checkout/step references `${{ secrets.RELEASE_TOKEN || secrets.GITHUB_TOKEN }}`, so when
> `RELEASE_TOKEN` is unset it **falls back to `GITHUB_TOKEN`** — releases work out of the box
> with just the write permission below. `RELEASE_TOKEN` is an opt-in escalation (item 4).

1. **Primary** — Settings → Actions → General → **Workflow permissions** → **Read and
   write permissions** → Save.
2. **Organization override** — if an org caps Actions permissions to read-only, an org
   admin must relax it (or allow repos to configure their own).
3. **Protected branch / ruleset** — if the release branch restricts pushes, add the
   Actions bot/token to the bypass list, or use a token that can bypass.
4. **PAT / `RELEASE_TOKEN` (escalation)** — when `GITHUB_TOKEN` is insufficient (bypass
   protection, trigger downstream workflows): create a fine-grained PAT with
   `Contents: Read and write` (+ `Workflows: Read and write` if the release touches
   workflow files) and store it as the repo secret `RELEASE_TOKEN`. The workflow already
   references `${{ secrets.RELEASE_TOKEN || secrets.GITHUB_TOKEN }}`, so **just adding the
   secret takes effect — no YAML edit**; when it is absent the run falls back to `GITHUB_TOKEN`.

The release preflight (`check-token-write.sh`) fails fast with this pointer when the
token is read-only.

---

## 6. Troubleshooting

### My commit is blocked — "python3 / PyYAML required"

The gate uses `python3` (3.8+) and `PyYAML` (regardless of the project's language). Without
them it **deliberately blocks commits** (to prevent checks silently dropping out). Fix:

```bash
python3 -m pip install pyyaml                       # install into the python3 the hook calls
bash .claude/harness-tier/scripts/check-deps.sh    # check what's missing
```

> `uv add` only goes into the venv and may be invisible to the hook, so install with
> `python3 -m pip` as above.

### Blocked as an unclassified commit

If you commit without going through `/flow`, there's no tier marker and the gate blocks it.
Classifying the task with `/flow` clears it. If a repo doesn't need enforcement, remove the
gate with `/flow-uninstall`.

### Dev work but the process doesn't run

The `superpowers@claude-plugins-official` plugin must be installed. Without it `/flow` stops
and guides you — don't skip to manual implementation.

### It blocked me just for mentioning `git commit`

The commit gate matches whenever the command contains the string `git commit`. A command
that merely mentions that string (e.g. `grep "git commit"`) can be blocked too — this is
expected.

### The gate does nothing (suspected no-op)

The gate checker is itself bash, so it can't detect a missing `bash`/coreutils on its own
(FAIL-OPEN). On Windows, check that Git Bash is present.

> *Why* the gate behaves this way (validation layers, Windows encoding, file propagation,
> and other internals) is documented in the developer-facing [CLAUDE.md](CLAUDE.md).

---

## 7. Update & removal

### Re-run `/flow-init` — sync after a plugin update

When the plugin updates, the host's copied scripts don't change automatically (they're
copies). Re-running `/flow-init` re-copies the scripts/policy files and repairs the gate
path (re-sync always runs first, non-interactively). If any config slots are missing it
offers to backfill them; otherwise it asks what to reconfigure (re-sync only if you pick
nothing; config and webhooks are preserved).

### `/flow-uninstall` — remove host-side wiring

`/plugin uninstall` only clears the cache; what `/flow-init` wrote to the host remains.
`/flow-uninstall` cleans that up (after confirmation): unregister the commit gate and
marketplace, strip the `.gitignore`/`CLAUDE.md` managed blocks, and delete
`.claude/harness-tier/`.

> ⚠️ **Order matters.** Because the cleanup tool lives inside the plugin, run
> **`/flow-uninstall` before `/plugin uninstall`**.

### Manual cleanup (if you already removed the plugin)

If `/flow-uninstall` is no longer available, remove things by hand:

1. Delete the `.claude/harness-tier/` directory.
2. In `.claude/settings.json`, remove the commit-gate hook (`hooks.PreToolUse`) and the
   marketplace registration (`extraKnownMarketplaces.harness-tier`).
3. Remove the harness-tier lines from `.gitignore`.
4. Remove the `harness-tier:teams` managed block from `CLAUDE.md`.
5. (Optional) `pre-commit uninstall --hook-type pre-commit --hook-type commit-msg --hook-type pre-push`.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).
