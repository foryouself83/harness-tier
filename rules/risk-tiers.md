# Risk-Tiered Workflow

> This rule is injected into every session context via the harness-tier
> SessionStart hook — it is always active without a `paths` trigger.

Always-on rule. Core idea: **do not apply the heaviest AI process to
every task — scale process rigor to risk.** The tier a request lands
in decides **which skills run** (notably whether the heavy `superpowers`
pipeline engages) and **which gates are mandatory and enforced**.

This file is the single source of truth for tier classification and
the per-tier workflow. [`/flow`](../skills/flow/SKILL.md),
[`/release-commit`](../skills/release-commit/SKILL.md), and
[`flow-tiers.yaml`](../flow-tiers.yaml) all defer to it, and
[`inject-risk-tiers.sh`](../hooks/inject-risk-tiers.sh) is what injects it.

There are four tiers across two axes:

- **Day-to-day tasks** (on `feature/*` / `fix/*`): **Docs** or
  **Dev**.
- **Promotion events** (git-flow gates): **Staging**
  (`flow-config.branches.integration → staging`) and **Release**
  (`flow-config.branches.staging → production` / prod deploy).

## Principle

Higher tier = more skills engaged + more mandatory gates; the *depth* of
process the verdict selects is what varies. When the tier is ambiguous,
`/flow` escalates one tier (bias to safety).

**Enter `/flow` (via the Skill tool) as your FIRST action** on any code
change, feature, fix, or development request — *before* reading code,
planning, or editing. You do not judge the tier on your own and proceed:
`/flow` runs the classification, confirms the tier with the user, and
writes the marker the commit gate reads. Skipping `/flow` leaves the commit
**unclassified**, and the commit gate **blocks it** (fail-closed — a commit
with no tier marker is refused; see Hard gates). If the workflow is
genuinely unwanted, the user removes the gate with `/flow-uninstall` — you
never work around it.

## Gates (glossary)

Every gate is named **once here** — what it does, when it runs, whether it blocks — and
every table and step below refers to it by name. Chokepoints and markers: Hard gates.
Everything else: [`gate-mechanics.md`](gate-mechanics.md).

Two kinds:

- **Runtime gates** — executed directly by the commit hook
  (`precommit-runner.sh`, layer 2), no `.done` marker. Four of them, in two shapes.
  `precommit` and `security-scan` are **timing buckets** over the
  `flow-config.modules[].checks`, each check routing to a bucket by its `when`
  (`every-commit` | `promotion`); `wiki` and `doc-style` are neither buckets nor module
  checks, and the gate script runs them in its own process:
  - **`precommit`** — the **every-commit** bucket: the every-commit checks of the
    **changed modules** (lint/static/import_lint/test + any custom
    `when: every-commit`), on every commit.
  - **`security-scan`** — the **promotion** bucket: the promotion checks of **all
    modules** (`security` + any custom `when: promotion`), on staging/release
    promotion.
  - **`wiki`** — verifies, read-only, that `graph.yaml` still matches the docs' front
    matter and that no structural rule is broken, when `flow-config.wiki` is enabled.
    Also rejects a commit whose only change to a node is its `sources` sha with no body
    edit ([`doc-sync`](../skills/doc-sync/SKILL.md) Mode W owns that stamp). Runs on
    **every tier including `docs`** — a docs commit is exactly when the graph drifts.
    No wiki configured → nothing runs. Warning taxonomy, what it cannot see, and the
    blocked-promotion remedy: [`gate-mechanics.md`](gate-mechanics.md).
  - **`doc-style`** — lints the files this commit changes that `flow-config.doc_style`'s
    `paths`/`exclude` globs put in scope, against [`doc-style.md`](doc-style.md), and
    reports as a `systemMessage`. It **never blocks**: the verdict belongs to
    `doc-style.yml` in CI, which sees the whole tree. One flag drives both arms —
    `/flow-init` renders that workflow only when `enable` is true, so `false` leaves the
    rule enforced nowhere rather than enforced lightly. Runs on every tier including
    `docs`. Scope resolution and the config gate:
    [`gate-mechanics.md`](gate-mechanics.md).
- **Marker gates** — recorded as `<gate>.done` only after the work genuinely
  passes (a marker is an audit trail + forcing function, not proof of quality):
  - **`review`** — an independent `general-purpose` agent (separate context)
    reviewing **every** changed file — git's list, count reported — against the
    checklist, plus the callers of every changed public symbol. Step 3 carries
    both the checklist and the procedure. **Dev and Staging only**
    — Release drops it; that tier's step says why.
  - **`doc-sync`** — `/doc-sync` harmonizes the doc set (root CLAUDE.md,
    per-service docs, rules) and reconciles code↔doc drift.
    Where the project has an LLM Wiki, it also refreshes each node's front matter
    `sources` marker (the file's working-tree **blob hash**, so history rewrites
    cannot fake staleness) and rebuilds `graph.yaml` (Mode W) — the `wiki` runtime
    gate then verifies that rebuild.
  - **`bump`** (Staging) — the human major/minor/patch choice; fail-closed
    (the staging commit is blocked until `bump.done` exists). Detail in
    [`promotion.md`](promotion.md).
  - **`security`** (Release) — `/security-review`. A dangerous Dev-tier
    change runs it too, unenforced — [`promotion.md`](promotion.md) says why.

## Step 1 — Classify the task (Docs or Dev)

The line is deliberately simple: **code, or no code.**

### Docs — no code implementation

All of these hold:

- **No source-code change** — nothing in `.py` / `.js` / `.ts` /
  `.jsx` / `.tsx`, no DB migration, no shell script logic.
- Only docs (`.md`), narrative content, comments/docstrings, or pure
  config-text.
- Single service; no contract / schema / dependency change.

Typical: documentation edits, README/guide changes,
comment/docstring-only tweaks.

### Dev — any code implementation (default for development work)

**Any one** of these:

- **Any change to source code (`.py` / `.js` / `.ts` …), however
  small — even a single line.** If real code is touched, it is at
  least Dev.
- New feature or new API endpoint; a requirement change.
- DB schema change (migration).
- Touches a **cross-service shared package** (→ propagates to all
  dependent services).
- New/changed **business logic / core nodes / validators / workflow
  orchestration** (→ selective TDD).
- Dependency add/change (→ follow the project's dependency-update
  procedure).
- Affects 2+ services.

### Tie-breakers

The promotion tiers are branch-driven and are never picked this way.

1. **When in doubt, escalate one tier.**
2. Criteria spanning multiple tiers → the **highest** tier wins.
3. Pure non-code (docs/comments only) → Docs. That tier carries no
   `review` gate to begin with (git-flow mapping) — nothing is being
   waived, so no note is owed.

## When each tier applies (git-flow mapping)

What each promotion decides, and the steps its rows take, are in
[`promotion.md`](promotion.md).

Branch names in this doc are `flow-config.branches` **keys** —
`integration` / `staging` / `production` are roles, each resolving to
your project's actual branch (e.g. integration→dev, staging→stage,
production→main). No branch is literally named `integration`.

| Moment | Tier | Gates |
|--------|------|-------|
| Work on `feature/*` / `fix/*` → integration branch | **Docs** (no code) / **Dev** (any code) | Docs: doc-sync, wiki, doc-style · Dev: precommit, review, doc-sync, wiki, doc-style |
| integration → staging (QA / rc cut) | **Staging** | precommit, review, security-scan, bump, wiki, doc-style |
| staging → production, or prod deploy | **Release** | precommit, security-scan, security, wiki, doc-style |
| A feature-branch change that is irreversible / prod-critical / security | **Dev** | Dev's set, plus `/security-review` as an unenforced step |

## Step 2 — Skill gate (the tier decides which skills run)

| Tier | `superpowers` pipeline | Suppressed |
|------|------------------------|------------|
| **Docs** | OFF — no code | brainstorming, writing-plans, TDD |
| **Dev** | ON | — |
| **Staging** | (promotion gate) | — |
| **Release** | (promotion gate) | — |

Each tier's gates are in the git-flow mapping table above. `precommit`,
`security-scan`, `wiki` and `doc-style` have no skill behind them — the commit hook
runs them (Gate glossary). Dev's `review` carries the selective-TDD and verification
overlays named below.

**Docs = `superpowers` OFF** (no-code edit, made directly).
**Dev = `superpowers` ON**, entered via `using-superpowers`; the pipeline it
runs and the project overlays on top of it are Step 3's.
**Staging / Release** are validation checklists over already-built
work, not new implementation.

**Precondition** — Dev requires the `superpowers` plugin
(`superpowers@claude-plugins-official`). If it is not installed,
`/flow` **stops** and asks the user to install it — no manual fallback.

## Step 2b — Ensure a work branch

Both Docs and Dev day-to-day work happens on `feature/*` / `fix/*` —
never directly on an integration/staging/production branch
(`flow-config.branches`). `/flow` ensures this **after** confirming the
tier and **before** writing the tier marker:

- Already on `feature/*` / `fix/*` / `hotfix/*` → stay (idempotent).
- On an integration/staging/production branch → cut a work branch and
  switch to it. The prefix follows the Conventional type (`feat` →
  `feature/`, `fix` → `fix/`); derive a short English `<slug>` from the
  task and confirm it with the user. A **clean** tree
  branches off freshly fetched `origin/<integration>`
  ([`merge-strategy.md`](merge-strategy.md) Feature branch base); with
  **uncommitted changes**, branch off the current
  `HEAD` to carry them along and rebase onto `origin/<integration>` at
  merge time ([`merge-strategy.md`](merge-strategy.md)).

Write the tier marker only **after** switching — the commit gate is
branch-bound, so the marker must carry the work branch, not the branch
work started on. `hotfix/*` off the production branch is the exception
(left in place).

## Step 3 — Per-tier workflow

Docs and Dev here; the promotion tiers' steps are in
[`promotion.md`](promotion.md), beside the promotion events themselves.

### Docs (no code)

1. Make the edit directly (`superpowers` OFF).
2. Run `/doc-sync` (Gate glossary) → record `doc-sync`.
3. Commit via `/commit` (it applies Commit Discipline below)
   → merge per [`merge-strategy.md`](merge-strategy.md), or open a PR when
   `merge_workflow.pull_request` includes `daily` (PR workflow in
   [`promotion.md`](promotion.md)).

### Dev (any code)

1. **Enter `superpowers:using-superpowers`** — it auto-runs the
   pipeline (brainstorm → plan → implement → verify → review). Feed
   the resolved request in.
2. Project overlays `superpowers` does not know about:
   - **Implementation minimalism (reuse-before-build ladder)** —
     right after the plan, before writing each piece of code, climb
     this ladder top-down and stop at the earliest rung that holds:
     ① does it need to exist (YAGNI) → ② already in this codebase
     (reuse helpers / utilities / patterns) → ③ stdlib → ④ native
     platform feature → ⑤ already-installed dependency → ⑥ one line
     → ⑦ only then the minimum code that works. The ladder runs
     *after* understanding the problem, not instead of it — read the
     task and the code it touches and trace the flow end to end
     first ("lazy about the solution, never about reading"). A fix
     targets the root cause, not the symptom — before editing, grep
     every caller of the function you are about to touch: one guard
     in the shared function is a smaller diff than a guard per
     caller, and patching only the path the report names leaves the
     sibling callers broken. It cuts volume, never validation /
     error handling / security / accessibility: that floor is
     enforced by the selective TDD and domain-review overlays below
     and the Release security gate (non-trivial logic keeps
     selective TDD's one-check minimum). Mark intentional
     simplifications with a comment noting the ceiling and upgrade
     path. (Concept from
     [ponytail](https://github.com/DietrichGebert/ponytail), MIT.)
   - **Selective TDD** — business logic / core nodes / validators /
     workflow orchestration only; not every change.
   - **`/doc-sync`** → record `doc-sync`.
   - **Domain review** — the last gate before commit, and *not* a
     repeat of the `superpowers` reviews: those run per task for
     plan-conformance (recall); this one runs once, at commit, for
     **coverage**. Dispatch an independent **`general-purpose`** review
     agent (separate context; it runs shell commands, so not a
     read-only reviewer type):
     ① **git is the authority on what changed** — every path it lists
     gets reviewed, and that count goes in the report. Run
     `git fetch origin` first, then take the **union of three
     lists**, deduplicated:

     ```bash
     git fetch origin
     # Probe the BRANCH POINT first, not merely the ref. Inside the brace group a failing
     # term writes to stderr, contributes nothing, and the pipeline still exits 0 — a short
     # list that looks complete. `rev-parse --verify` is not enough: on a shallow clone, or
     # against an unrelated history, the ref resolves fine and the three-dot diff still dies
     # with "no merge base". `merge-base` fails in both cases and covers a missing ref too.
     # Per-term `|| exit 1` inside the braces does NOT work — it exits only the pipeline's
     # subshell and `sort`'s status masks it. Abort here; never review the remainder.
     git merge-base "origin/<integration>" HEAD >/dev/null || exit 1
     { git diff --name-only "origin/<integration>...HEAD"   # committed on the branch
       git diff --name-only HEAD                            # staged + unstaged
       git ls-files --others --exclude-standard             # untracked
     } | sort -u
     ```

     All three are needed and none subsumes another. The three-dot
     form is commit-to-commit from the branch point, so on its own it
     reports **zero** files for the ordinary case — review runs
     *before* the commit. `HEAD` on its own misses everything already
     committed on the branch, and since the `review` marker
     survives across commits, those files would never appear in
     *any* review's list. `ls-files --others`
     recovers untracked files only, never modified tracked ones.

     At a promotion the working tree is clean and both ends are
     branches, so use the two adjacent `flow-config.branches` refs —
     **destination first**:
     `git diff --name-only "origin/<staging>..origin/<integration>"`.
     Two dots, not three: `git diff` reads that as a **two-endpoint**
     diff, so it also surfaces what sits on the destination alone —
     inverted, as a deletion the merge will not make. That is the safe
     direction for a coverage gate; the three-dot form drops those
     files outright. Always the **freshly fetched `origin/` refs**,
     never a bare local ref: a stale local ref silently *shrinks* the
     reviewed set, which is the one direction a coverage gate must
     never fail in.
     ② Read each file's diff and judge it against the checklist —
     regression, cross-service contract, DB/migration & transactions,
     async task idempotency & queue routing, API error conventions.
     ③ For every changed **public symbol** (signature, schema, event,
     error contract) find its callers — `LSP documentSymbol` for the
     symbol's line/character, then `incomingCalls` (functions) or
     `findReferences`; no language server, or no `LSP` tool in this
     client → `grep`, and say which you used. An unreviewed caller is
     where a regression lands. Callers only, not the whole import
     graph: dynamic dispatch, DI wiring, and HTTP contracts stay with
     the checklist's cross-service row.
     ④ Report High + Medium, discard Low, and state the reviewed-file
     count against ①'s list → record `review`.
     ⑤ The marker is a plain file that outlives the commit that used
     it, so an edit after the pass would commit against evidence
     earned over code no reviewer saw. A `PostToolUse` hook deletes
     the `review` **and** `doc-sync` markers the moment a file
     changes — the fixes this review asked for included. Passing is
     therefore a fixpoint: both recorded, nothing edited since, which
     is also why doc-sync runs first. A fix re-runs doc-sync, then
     this review. An edit the hook never saw (a terminal command,
     another tool) leaves the markers standing — delete them by hand:
     `rm -f .claude/harness-tier/.flow/review.done .claude/harness-tier/.flow/doc-sync.done`.
     A team that wants the older order — a small fix after a pass not
     costing a re-run — sets `gate_evidence.invalidate_on_edit: false`
     in `flow-config.yaml`, and pays for it in coverage: an edit after
     the pass — the review's own fixes included — commits under a
     review that never saw it. `/flow` still clears the evidence
     directory after the commit/merge, but a `<gate>.done` is not
     branch-bound the way the `tier` marker is, so a task that ends
     without that step leaves its markers standing for whatever runs
     next, on any branch.
     The hook is registered by the plugin, so a
     version bump arms it with no `/flow-init` step to agree to; the
     switch is how the host that carries the cost answers. Armed is the
     default: the hook reads `false` under a top-level `gate_evidence:`
     and nothing else, so a YAML-false spelled `no`/`off`/`False`, or
     the key written under another block, leaves it armed. It reads the
     file line by line, so a file YAML cannot load still disarms on that
     one line — and a line the reader cannot make out leaves it armed.
3. Integration human gate (feature → integration branch;
   [`merge-strategy.md`](merge-strategy.md)) → commit via `/commit` →
   merge, or open a PR when
   `merge_workflow.pull_request` includes `daily` (PR workflow in
   [`promotion.md`](promotion.md)).

## Commit Discipline

Always apply before every `git commit -m` and every merge. `/commit` carries out
the mechanics — staging, the type choice, the length check — and defers here for
every rule it applies.

### Message format (Conventional Commits)

```
<type>[(scope)][!]: <description>
                                   ← blank line
[body]
                                   ← blank line
[footer(s)]
```

- **Subject** — `type(scope): description`; ≤50 chars (non-ASCII = 1
  each); lowercase, imperative; no trailing period. Over 50 →
  **REWRITE**, no exceptions.
- **Body** — what & why as `-` bullets, **one sentence each**, not
  prose; each line ≤72, wrap at word boundaries. Fragments over
  sentences (noun phrases + `cause → effect`). Never prefix a bullet
  with `feat:`/`fix:` — the subject owns the type. Drop anything that
  restates another bullet, and anything the reader need not know.
- **No history narration in the body** — no before-and-after, no
  migration note, no account of what an earlier round of the same
  work did. The commit *is* the history entry.
- **Footer** — `BREAKING CHANGE: …`, `Refs: #123`; same ≤72.

Subject/body limits (the **50/72 rule**) + no-trailing-period are
lint-enforced; bullets, fragments, and terseness are soft style.

Example:

```
feat(auth): rotate refresh tokens per use

- Old tokens: 15-min re-login churn.
- Per-use rotation → replayed tokens rejected.

BREAKING CHANGE: refresh tokens now single-use.
Refs: #421
```

### Language

`type`/`scope`/`BREAKING CHANGE` keywords stay English (spec format —
`semantic-release`/`gitlint` parse them). The `<description>` and body
follow the host's configured response language (e.g. a `CLAUDE.md`
language directive); default to English if unset.

### Commit type → version impact

| Type | Version | When |
|------|---------|------|
| `feat` | MINOR | New feature |
| `fix` / `perf` | PATCH | Bug fix / perf improvement |
| `docs` / `chore` / `refactor` / `test` / `style` / `ci` / `build` | none | No release |
| `BREAKING CHANGE:` in footer | MAJOR | Incompatible change |

**Squash** merges pick the **highest-priority type** among bundled
commits.

> **Plugin propagation discipline** — harness-tier ships as a tightly coupled release (plugin.json
> `version`). `docs`/`chore` do not trigger a version bump, so they **do not propagate to
> consumers**. Any `.md` change that affects consumer behavior (rules, skills, etc.) **must be
> committed as `feat`/`fix`** so it rides along in a release and propagates. Leave only purely
> internal docs (developer-only, irrelevant to consumers) as `docs`.

### When asked "is this commit compliant?"

Re-measure subject char count and each body line length yourself.
Don't trust your earlier write.

## Repo conventions baked in

- **Never bypass the layer-1 hook with `--no-verify`** — the host's
  `.pre-commit-config.yaml` chain is git-native and runs on every commit,
  tier or no tier. The tier-driven check is a different thing: the
  `precommit` runtime gate (Gate glossary), carried by every tier except
  `docs`.

## Hard gates (enforced mechanically)

Gates are enforced at chokepoints, driven by
[`flow-tiers.yaml`](../flow-tiers.yaml) and the evidence markers
`/flow` and `/release-commit` record under
`.claude/harness-tier/.flow/` (gitignored):
`tier` (`<tier>:<branch>`) plus `<gate>.done` per completed gate.

1. **Commit gate (Docs/Dev)** — the PreToolUse hook on `git commit` (via the project's
   `flow_gate_check` script) **blocks the commit** when the active tier's
   required marker gate has no `.done` marker, and also **blocks an
   unclassified commit** (policy intact but no `tier` marker — `/flow` was
   skipped). Branch-bound; fail-closed ([`gate-mechanics.md`](gate-mechanics.md)).
2. **Promotion gates (Staging / Release)** — enforced at `git commit`.
   The branch decides first: a commit on the staging branch enforces the
   `staging` gates, one on the production branch the `release` gates (the same
   PreToolUse hook). With no lifecycle branch the `tier` marker's own label
   selects the set instead, which is the path a hand-written
   `release:feature/x` takes ([`promotion.md`](promotion.md) Release).
   **Deploy commands are not
   gated.**
