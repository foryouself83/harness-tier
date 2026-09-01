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
5. **Finish** — `pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push`.

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

merge_workflow:
  pull_request: []          # flows routed through a PR instead of a direct merge; [] = all direct (default)

modules:                     # per-module monorepo pre-checks (when modules use different languages/tools)
  - name: api
    path: services/api/      # run checks when something under this path changes
    checks:                  # only the ones that exist — /flow-init drafts from the harness SSOT, humans edit
      lint:        "ruff check services/api"
      static:      "uv run pyright services/api"
      import_lint: "uv run lint-imports --config services/api/.importlinter"
      test:        "uv run pytest services/api"
      security:    "uv run bandit -r services/api"

review_checklist:            # what the Dev review gate judges every changed file against
  - "regression / regression tests pass"
  - "cross-service contract / cross-service contract validity"
  - "DB transaction / migration safety"
  - "async task idempotency"

commit_guide: docs/operations/commit-versioning-guide.md   # host's own commit/versioning doc,
                             # read by the `commit` skill (missing file → risk-tiers alone)

doc_sync:                    # doc-sync targets
  index: CLAUDE.md
  dirs:
    - "docs/"
    - ".claude/rules/"
  service_docs: "services/*/CLAUDE.md"
```

**`merge_workflow.pull_request`** — flows to route through a PR instead of a direct
`git merge`. Values: `daily` (`feature/*`/`fix/*` → integration) · `promotion`
(integration → staging, staging → production). Empty (the default) means every flow
stays a direct merge, unchanged from before this setting existed. Commit discipline
(gitlint, tier gates) is unaffected either way — only the merge itself moves. For a
PR-routed flow, enforcement of the merge method moves server-side to a GitHub branch
ruleset — exactly so for `promotion`, only partly for `daily` (§2.2 below). `/flow-init`
Step 2.7 reads the repo's current ruleset state and reports the gap (branches · allowed
merge methods · a bypass actor), but never edits it for you. Full detail — including why a promotion ruleset needs a bypass actor
and how the back-merge interacts with a `daily` ruleset — lives in
[`rules/risk-tiers.md`](rules/risk-tiers.md)'s **PR workflow** section.

**When each `checks` key runs** (module pre-checks):

Each `checks` key is one check; its value is either a **command string** or the extended form **`{ run: <cmd>, when: every-commit | promotion }`**. Beyond `lint`/`static`/`import_lint`/`test`/`security` you may **add your own keys** (license, sbom, secret-scan, …). (The field is `when`, not `on` — YAML parses a bare `on` key as a boolean.)

| Timing (`when`) | Gate | Scope | When |
|-----------------|------|-------|------|
| `every-commit` (default for string values except `security`) | `precommit` | **changed modules** | dev/staging/release, every commit |
| `promotion` (default for the string `security`) | `security-scan` | **all modules** | at staging/release promotion |

Timing applies only when that gate exists in the tier — the docs tier has neither, so custom checks never run on a docs commit. Enforcement is **Claude-session commits only** (layer-2), same as every runtime gate — terminal/CI commits are not gated.

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
  action; any other value lets the `setup` command prepare the runtime. The match is
  case-sensitive, so `/flow-init` warns on a capitalised variant like `Python` — it would skip
  the setup action silently and test against whatever runtime the runner already has. Declared
  independently of `modules[]` (local gate and CI run in different contexts).
- **`versioning`** — release automation such as python-semantic-release. With `enable: true`
  it renders the release / branch-naming / entropy-check workflows. The **GitHub Release
  body** is the latest grouped `CHANGELOG.md` section (semantic-release output — grouped by
  type, plumbing commits filtered), falling back to GitHub's auto-generated notes if the
  changelog is missing/empty.

### 2.2 `flow-tiers.yaml` — tier→gate policy (do not edit)

It sits in the same `config/` folder but is **plugin-owned**. It is overwritten on every
install, so **do not edit it directly** (if you need to change it, edit the plugin SOURCE
and re-run `/flow-init`). This file defines which gates are mandatory for each tier.

It also carries `merge_strategy`, which checks the flags of a `git merge` against the
branch flow it belongs to (branch names resolve from your `flow-config.branches`):

| Merge | Enforced |
|-------|----------|
| `feature/*` → integration | `--squash` required |
| `integration` → staging | `--no-ff` required |
| `staging` → production | `--no-ff` required |
| `hotfix/*` → production | `--squash` required |
| `fix/*` → integration | `--no-ff` refused |

Scope is deliberately narrow. Only rows where the strategy is a single choice can be
checked — the back-merge (`production` → integration, after a release) allows fast-forward
*or* `--no-ff`, so there is nothing to enforce there. Rebasing before a `feature/*` merge is
**warned about, not blocked** (a stale `origin` ref would otherwise produce false alarms).
And like every layer-2 gate this only sees **merges made inside a Claude session** —
merging from your own terminal bypasses it entirely.

This local-hook enforcement applies only while the flow's merge stays a direct `git merge`.
When `flow-config.merge_workflow.pull_request` routes a flow through a PR instead (see
`rules/risk-tiers.md`'s **PR workflow** section), the hook never sees a `git merge`
command, so the corresponding row above stops firing — enforcement moves server-side to a
GitHub branch ruleset (allowed merge methods), which `/flow-init` Step 2.7 checks but never
changes for you.

**The ruleset is an exact swap only for `promotion`**, where one method (`merge`) is allowed
per branch. A branch ruleset targets the *destination* branch, so under `daily` it cannot
tell a `feature/*` PR from a `fix/*` one: allowing `squash`+`rebase` guarantees only "no
merge commit into integration", and picking the right one of the two stays discipline — say
which method the PR must use when you hand it over. The same destination-wide reach pulls in
flows you did not select: "require a pull request" on integration also blocks the
post-release back-merge push, and on production it also catches `hotfix/*`. Both need
handling — a bypass actor, or routing that flow through a PR as well. `rules/risk-tiers.md`'s
**PR workflow** section spells out each case.

Anything the gate cannot decide lets the merge through: no matching rule, a command it
cannot parse, or a command naming another worktree. To turn the check off, delete the
whole `merge_strategy` key from the plugin SOURCE and re-run `/flow-init` (or remove the
gate altogether with `/flow-uninstall`).

### 2.3 Risk tiers and gates

Work is classified into four tiers (two axes), and the tier determines **which gates must
pass before it can commit**.

| Tier | When | superpowers | Mandatory gates |
|------|------|:---:|-----------------|
| `docs` | no-code change (docs/comments/config values) | ✗ | `doc-sync` · `wiki` |
| `dev` | change with code (feature/fix) | ✓ | `precommit` (changed-module every-commit checks) · `review` (domain review) · `doc-sync` · `wiki` |
| `staging` | QA/RC promotion (integration→staging) | ✓ | `precommit` · `review` · `security-scan` (all-module promotion checks) · `bump` (human release-level choice) · `wiki` |
| `release` | production deploy (staging→production) | ✓ | `precommit` · `review` · `security-scan` · `security` (security review) · `wiki` |

- **`precommit` · `security-scan`** are executed by the commit hook itself (no marker).
  Removing one from a tier's `gates` list disables just that check.
- **`wiki`** is likewise executed by the commit hook itself (no marker), in-process as
  the flow gate's final stage — never through the module-check channel — but only when
  `flow-config.wiki` is enabled; otherwise nothing runs. Its graph-quality warnings
  (orphans, over-size documents, `sources` paths that are not on disk, defect→rule
  promotion, front matter that fails to parse without a `wiki_id:` line, a wiki-only
  field present without a `wiki_id`) come back
  as a `systemMessage` even when the commit passes. A blocked commit's structure-violation
  list is capped at 10 entries plus a count. Read-only: it
  checks `docs/graph/graph.yaml` against the docs' front matter (§3.9), and it also
  blocks a commit whose only change to a node is its `sources` sha with no body edit
  (stamp discipline — two swaps stay allowed: doc-sync's legacy-marker migration
  rewrite, and a stamp whose body edit landed in the immediately preceding commit, so
  stamping or amending the sync you just committed works — the gate follows a rename in
  that commit, so moving the document does not cost you the allowance). It reads the
  **working tree** — the hook fires before `git commit` stages anything, so there is no
  commit to inspect yet. Stage `graph.yaml` together with the documents it was built
  from; a rebuilt-but-unstaged graph satisfies the gate while the commit records the
  stale one. `/flow-init` also renders a `wiki-verify.yml` CI workflow that runs the
  same verification read-only on push/PR, catching drift from terminal and merge
  commits the hook never sees.
- **`review` · `doc-sync` · `security` · `bump`** leave an evidence marker after `/flow`
  passes the gate; the commit hook passes only when the marker exists. `bump` is the
  human major/minor/patch choice at a staging promotion — fail-closed, so the staging
  commit stays blocked until the choice is made.
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
   - **Docs**: edit directly → reconcile docs via `doc-sync` → commit via `/commit`
   - **Dev**: `superpowers` pipeline (design → plan → implement → verify → review) →
     domain review (`review_checklist` + callers of changed symbols) → `doc-sync` →
     commit via `/commit`

> **Promotion (Staging/Release)**: integration→staging and staging→production merges are
> driven by the **target branch** (no separate marker needed). Each tier's mandatory gates
> (§2.3) must pass before it can commit.

> **`/flow` cannot be skipped.** If you commit without going through it, there's no tier
> marker and the gate blocks the commit as **unclassified**. If a repo doesn't need
> enforcement, remove the gate with `/flow-uninstall`.

Every commit step above goes through the **`commit`** skill, which stages the affected
files, picks the Conventional Commits type, and checks the 50/72 rule before issuing
`git commit`. It reads the host's own `commit_guide` when that file exists and prefers
its stack facts — scope vocabulary, 0.x policy, whether the release tool reads the
`Release-Level` trailer — while [`risk-tiers.md`](rules/risk-tiers.md) keeps the message
format. `/commit` on its own handles a standalone commit, but it does **not** classify:
a commit made without `/flow` is still unclassified and still blocked.

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
- **`.claude/rules/`, not just `CLAUDE.md`** — framework and structural conventions are
  written as auto-loaded `.claude/rules/<name>.md` files (Claude Code's rules convention; an
  optional `paths` glob scopes a rule so it loads only when a matching file is read), so the
  harness follows the current multi-file convention rather than one monolithic `CLAUDE.md`.
  `doc-sync` keeps them in step as the code changes.

#### Auto-detected languages and frameworks

Step 1 fingerprints your stack from its manifest files. Deterministic auto-detection covers:

| Language | Manifest(s) | Auto-detected frameworks / libraries |
|----------|-------------|--------------------------------------|
| Python | `pyproject.toml` · `requirements.txt` | FastAPI · Django · Flask |
| JavaScript / TypeScript | `package.json` | Next.js · React · Vue · Nuxt · Svelte · Angular · Express · NestJS |
| Go | `go.mod` | (module-level) |
| Java | `pom.xml` · `build.gradle[.kts]` | Spring Boot · Spring · Quarkus · Micronaut · Ktor |
| Kotlin | `build.gradle.kts` · `pom.xml` | shares the JVM table above |
| C# | `*.csproj` | ASP.NET Core · Blazor WASM · Razor · WPF · WinForms · MAUI · EF Core |
| C++ | `CMakeLists.txt` · `vcpkg.json` · `conanfile.*` | CMake · Boost · Qt · OpenCV · GoogleTest · Catch2 · fmt · spdlog |
| Rust | `Cargo.toml` | actix-web · axum · Rocket · warp · tokio |
| PHP | `composer.json` | Laravel · Symfony · Slim · CodeIgniter |
| Ruby | `Gemfile` | Rails · Sinatra · Hanami |
| Swift | `Package.swift` · `*.xcodeproj`/`*.xcworkspace` | Vapor · SwiftNIO · Alamofire · RxSwift |
| Scala | `build.sbt` | Play · Akka · Akka HTTP · http4s · Cats Effect |

- Detected frameworks come with a **version**, and the versions are reconciled into a set
  that boots together — not each one's latest in isolation.
- **A stack outside this table still gets a harness.** Greenfield vs. brownfield is decided
  from source-file extensions, and `harness-researcher` researches conventions for whatever
  framework you're on; only the deterministic fingerprint above is limited to these entries.

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

### 3.8 `/harness-deployments` — deployment layer

```text
/harness-deployments   # no arguments — interactive
```

Adds a **deployment layer** on top of the release workflow (tag + notes). It **requires
`/flow-init` to have already run** (it needs `flow-config.yaml`) and hard-stops with
guidance otherwise. Order: `/harness-init` → `/flow-init` → **`/harness-deployments`**.

1. **Detect** — stack from `flow-config.yaml` (`versioning.release_tool`/`version_files`/
   `modules[].checks`), build artifacts (`Dockerfile`, `pyproject.toml`/`package.json`/
   `Cargo.toml`/`pom.xml`/`*.csproj`), the JVM `build_tool` (`build.gradle`/
   `build.gradle.kts` → gradle, `pom.xml` → maven, `build.sbt` → sbt — needed only for a
   `maven-central` target, to pick the matching component template), and existing
   publish/deploy steps already in `.github/workflows/*`.
2. **Ask** (`AskUserQuestion`, adaptive — only for what can't be derived) — deploy target(s)
   from the detected candidates (registry publish / container image / app deploy), per-target
   `auth` (OIDC vs. token — not detectable from the repo), deploy `order` across targets, a
   monorepo image's `image`/`context`/`dockerfile` (skipped for a single image — the renderer
   fills a derived default), and a custom target's `permissions`/`with`. `build_tool` is only
   confirmed (detected, not asked); `version`/`build` are optional (mention the default,
   don't force a choice). On a brownfield repo with an existing deploy step, you choose
   adopt/augment/replace — it never silently overwrites. There is no trigger question —
   wiring is always the same (see "Wiring" below).
3. **Generate**:
   - Writes/updates the `deploy:` block in `flow-config.yaml` (team-shared, git-tracked;
     config holds only non-derivable values — derivable fields are omitted).
   - For a registry/image target with a mapped `target` (including `maven-central` with
     `build_tool: maven|gradle`), renders the component CI workflow via
     `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/flow_init_setup.py" --render-deploy` — the
     **plugin SOURCE script**, not a host copy (`flow_init_setup.py` isn't among the files
     `/flow-init` copies to the host).
   - For a references-backed custom/app-deploy target or `maven-central`+`build_tool: sbt`
     (no static template), authors `.github/workflows/deploy-<name>.yml` directly from the
     matching `references/app-deploy/*` or `references/registry-publish/jvm-sbt.md` recipe.
   - For a target with no matching reference, researches the official action/secrets/OIDC
     support via `WebSearch`/`WebFetch`, then authors the component and flags it
     "verify needed" with the secrets it requires.
   - The generated `deploy.yml` orchestrator and the release.yml wiring (the managed
     `# __HARNESS_DEPLOY_BEGIN/END__` block) are handled by the script automatically — the
     skill only steps in when the script reports a legacy/foreign release.yml (no markers):
     it offers to regenerate release.yml from the template, or to semantically patch it
     (insert `outputs.tag` + the deploy job at the right spot, after showing a diff for
     confirmation). Meanwhile `deploy.yml` is already runnable via `workflow_dispatch`.
   - Writes `docs/operations/deploy-guide.md` (secrets to configure — including the JVM
     signing-key format per build tool, manual re-deploy via dispatch, rollback pointers).
4. **Report** — summarizes created/changed files, secrets the repo admin must set, and any
   conflicts found.

**Wiring** — `release.yml` calls `deploy.yml` via `workflow_call` in the **same run**: no
cross-workflow trigger, no `RELEASE_TOKEN` for deploy. The release job exposes
`outputs.tag` (the actual tag just created, or empty when the release was skipped) and a
managed block calls the orchestrator with that tag; the orchestrator resolves it once and
calls each target component with per-target least-privilege permissions. Manual re-deploy:
run `.github/workflows/deploy.yml` via `workflow_dispatch` with a `tag` input (and an
optional `target` to redeploy just one).

**Decoupled from release** — release (`versioning`) produces the tag and notes; deployment
is a separate, opt-in layer (`flow-config.deploy.enable`) on top of it, not part of the
release process itself.

### 3.9 `/wiki-init` — LLM Wiki setup wizard

```text
/wiki-init   # no arguments — interactive; disable-model-invocation, call it explicitly
```

Builds docs into a knowledge graph, no embeddings — migrates existing docs into
one-concept-per-file nodes with YAML front matter and generates `docs/graph/graph.yaml`;
relationships are the front matter you write by hand, mechanically read into the graph.
Idempotent: a document that already carries a `wiki_id` is never re-offered on a later
run. Once built, `doc-sync` (Mode W) keeps the graph and each node's `sources` marker
(the source file's working-tree **blob hash**, so squash/rebase promotions cannot fake
staleness) in sync, and the `wiki` runtime gate (§2.3) verifies that sync, read-only, at
every commit. The graph is also the development read path: `/flow`'s Dev track starts by
mapping the files about to change to their documenting nodes
(`wiki_graph.py --nodes-for <paths…>`) and loading their neighbourhood
(`--neighbors <id>`) as working context.

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

It should not. The gate reads the command the way a shell does and asks one question: is there
a real `git … commit` in it? A mention inside quotes, a comment or a heredoc body is text, so
`grep "git commit"` and `git log --oneline && echo "now commit"` both run untouched.
If one of those is still blocked, the host's copy of the gate scripts is older than the plugin
— re-run `/flow-init`.

### The gate does nothing (suspected no-op)

The gate checker is itself bash, so it can't detect a missing `bash`/coreutils on its own
(FAIL-OPEN). On Windows, check that Git Bash is present.

> *Why* the gate behaves this way (validation layers, Windows encoding, file propagation,
> and other internals) is documented in the developer-facing [CLAUDE.md](CLAUDE.md).

---

## 7. Update & removal

### Re-run `/flow-init` — sync after a plugin update

A session tells you when an update is waiting: at startup the hook compares the build it
loaded against the version the marketplace publishes and reports a difference in one line.
Both numbers are local files — the marketplace clone Claude Code keeps beside the install
cache — so nothing goes over the network, and a clone that has not refreshed says nothing.

Take the update with `/plugin`, then re-run `/flow-init`. The update alone is not enough:
the host's copied scripts don't change with it (they're copies). Re-running `/flow-init`
re-copies the scripts/policy files and repairs the gate path (re-sync always runs first,
non-interactively). If any config slots are missing it offers to backfill them; otherwise it
asks what to reconfigure (re-sync only if you pick nothing; config and webhooks are preserved).

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
5. Delete `.github/workflows/wiki-verify.yml`, and any release workflow that calls
   `.claude/harness-tier/scripts/` — with step 1 done they run a script that is gone.
   `wiki-verify.yml` guards on that and stays green — it verifies nothing, and still spends
   a runner on every push to say so. Among the release renders, `gitversion` and `jreleaser`
   call the path unguarded and fail on pushes to your release branches;
   `python-semantic-release` guards its call, and `cargo-release` / `semantic-release` never
   reference the path. (`api-contract.yml` / `unit-test.yml` reference nothing of ours and
   simply stay active.)
6. (Optional) `pre-commit uninstall --hook-type pre-commit --hook-type commit-msg --hook-type pre-push`.

---

## License

Apache License 2.0 — see [LICENSE](LICENSE).
