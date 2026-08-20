# Risk-Tiered Workflow

> This rule is injected into every session context via the harness-tier
> SessionStart hook — it is always active without a `paths` trigger.

Always-on rule. Core idea: **do not apply the heaviest AI process to
every task — scale process rigor to risk.** The tier a request lands
in decides **which skills run** (notably whether the heavy `superpowers`
pipeline engages) and **which gates are mandatory and enforced**.

This file is the single source of truth for tier classification and
the per-tier workflow. [`/flow`](../skills/flow/SKILL.md) and
[`flow-tiers.yaml`](../flow-tiers.yaml) both defer to it, and
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

Each gate is defined **once here**; every table and step below refers to a
gate by name only. (For how gates are enforced — chokepoints, markers,
fail-open/closed — see Hard gates.)

Two kinds:

- **Runtime gates** — executed directly by the commit hook
  (`precommit-runner.sh`, layer 2), no `.done` marker. They are **timing buckets**
  over the `flow-config.modules[].checks`; each check routes to a bucket by its
  `when` (`every-commit` | `promotion`):
  - **`precommit`** — the **every-commit** bucket: the every-commit checks of the
    **changed modules** (lint/static/import_lint/test + any custom
    `when: every-commit`), on every commit.
  - **`security-scan`** — the **promotion** bucket: the promotion checks of **all
    modules** (`security` + any custom `when: promotion`), on staging/release
    promotion.
  - **`wiki`** — not a timing bucket, and not a module check either: the hook's gate
    script runs it in-process as its final stage, plus a new blocking rule: a commit whose
    only change to a node is its `sources` sha (no body edit) is rejected — see
    doc-sync's stamp discipline. When `flow-config.wiki` is enabled it verifies, read-only, that
    `graph.yaml` still matches the docs' front matter and that no structural rule is
    broken. It runs on **every tier including `docs`** — a docs commit is exactly when the
    graph drifts. No wiki configured (absent · `enable: false` · missing root) → nothing
    runs, so a repo without a wiki never notices this gate. The graph is **built** by
    `/doc-sync` or `/wiki-init`, never by the hook and never by CI, and it is built from
    **git's index** — `git add` is what admits a document to the wiki, so stage new documents
    before building. Only a real verification failure blocks; an internal error passes
    (Invariant #1) — including a git that cannot list its own index, where the node set falls
    back to the filesystem and would otherwise count the very files git hides. Its
    non-blocking quality warnings — orphans, over-size documents, `sources` paths that are
    not on disk, defect→rule promotion, front matter that fails to parse without a
    `wiki_id:` line, a wiki-only field (`related`/`depends_on`/`affects`/`sources`) present
    without a `wiki_id` — come back as a `systemMessage` on a passing commit, each kind
    capped at three entries plus a count. A defect node's `regression_test` /
    `promoted_to_rule` path is the one file reference that *does* block when it is missing,
    unlike `sources`: those two assert a tracked repository artifact exists, and both the fix
    and the escape hatch are one edit in the document, whereas a `sources` entry may
    legitimately name a generated or gitignored file that no edit can conjure.
    Two things it cannot see. It reads the **working tree**, because the hook fires before
    `git commit` stages anything — so `graph.yaml` must be staged with the documents it
    was built from, or the commit records new front matter beside the old graph and
    nothing catches it until the next session commit. And on a **promotion** (Staging /
    Release) no gate rebuilds the graph — `doc-sync` is not a promotion gate — so a drift
    that arrived via a terminal commit surfaces here as a blocked promotion: run
    `python3 .claude/harness-tier/scripts/wiki_graph.py --build` and include the result in
    the promotion commit.

  Hosts add their own runtime checks by putting extra keys under
  `flow-config.modules[].checks` — a command string (timing defaults by key name:
  `security` → promotion, else every-commit) or `{ run, when }` to set timing
  explicitly (use `when`, not `on` — YAML reads a bare `on` key as a boolean).
  **Timing is bound to that bucket's gate existing in the tier**: the `docs` tier has
  neither *bucket* gate, so host custom checks never run on a docs commit — the module
  pre-check short-circuits there. (`wiki` still runs on a docs commit; it is not a module
  check and never enters that path.) Both gates are ordinary entries in each tier's `flow-tiers.yaml`
  `gates` list, so **removing one disables that whole bucket** for that tier (the
  gates list is the single on/off switch, not a hardcoded branch). Like all
  layer-2 checks these run **only on Claude-session commits** — terminal/CI commits
  are not gated (add a CI safety net if you need hard enforcement).
- **Marker gates** — recorded as `<gate>.done` only after the work genuinely
  passes (a marker is an audit trail + forcing function, not proof of quality):
  - **`review`** — an independent `general-purpose` agent (separate context)
    reviewing **every** changed file — git's list, count reported — against the
    checklist: regression, cross-service contract, DB/migration & transactions,
    async task idempotency & queue routing, API error conventions, plus the
    callers of every changed public symbol. Step 3.
  - **`doc-sync`** — `/doc-sync` harmonizes the doc set (root CLAUDE.md,
    per-service docs, rules) and reconciles code↔doc drift.
    Where the project has an LLM Wiki, it also refreshes each node's front matter
    `sources` marker (the file's working-tree **blob hash**, so history rewrites
    cannot fake staleness) and rebuilds `graph.yaml` (Mode W) — the `wiki` runtime
    gate then verifies that rebuild.
  - **`bump`** (Staging) — the human major/minor/patch choice; fail-closed
    (the staging commit is blocked until `bump.done` exists). Detail in Step 1b.
  - **`security`** (Release) — `/security-review`.

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

## Step 1b — Promotion events (Staging / Release)

These are **not** per-task classifications — they are git-flow
promotion gates run once over the accumulated work.

### Staging — integration → staging branch (QA / rc cut)

The release candidate enters QA/staging. Gates: `precommit`, `review`,
`security-scan`, `bump`, `wiki` (see Gate glossary). Performance and integration are
independent skills; the `/security-review` LLM review is added at Release.

Staging also **forces a human bump-level choice**: `/flow` asks major/minor/patch
(default = commit-derived) and records a `bump` gate marker; the commit gate blocks
the staging commit until `bump.done` exists (fail-closed). The choice rides the
staging commit as a `Release-Level:` trailer and CI forces
`semantic-release version --<level> --as-prerelease`. main finalizes the rc by
dropping the token deterministically (an overridden level would otherwise be lost —
python-semantic-release recomputes on the stable branch). `major` on a 0.x project
jumps to `1.0.0`.

The trailer is for the **first** forced promotion only. `version --<level>` bumps the
**base** version every time it is applied, so re-promoting with the trailer to fold in
a follow-up takes `X.Y.Z-rc.1` → `X.Y.(Z+1)-rc.1`, skipping `X.Y.Z` as a stable
release rather than continuing to `rc.2`. To iterate an rc on the same target version,
re-promote **without** the trailer — the auto-derive path continues the series.

### Release — staging → production branch

Two entry points:

- **Lifecycle (primary)** — the staging → production promotion
  (official release), or a production deploy (e.g., an air-gapped
  offline deploy). Gates: Staging + `security`.
- **Content (escalation)** — a single change that hits an
  irreversible/large data migration, a **performance-critical path**
  (search/embedding/GPU/inference config), or a security surface
  (auth/authz, secrets, gateway rate-limiting). Escalate that task to
  Release even on a feature branch.

### Tie-breakers

1. **When in doubt, escalate one tier.**
2. Criteria spanning multiple tiers → the **highest** tier wins.
3. Pure non-code (docs/comments only) → Docs; the review gate may be
   skipped with a one-line note.

## When each tier applies (git-flow mapping)

Branch names in this doc are `flow-config.branches` **keys** —
`integration` / `staging` / `production` are roles, each resolving to
your project's actual branch (e.g. integration→dev, staging→stage,
production→main). No branch is literally named `integration`.

| Moment | Tier | Gates |
|--------|------|-------|
| Work on `feature/*` / `fix/*` → integration branch | **Docs** (no code) / **Dev** (any code) | Docs: doc-sync, wiki · Dev: precommit, review, doc-sync, wiki |
| integration → staging (QA / rc cut) | **Staging** | precommit, review, security-scan, bump, wiki |
| staging → production, or prod deploy | **Release** | + security |
| A feature-branch change that is irreversible / prod-critical / security | escalate to **Release** | — |

Staging and Release are **promotion/deploy gates**, not per-commit
tiers you pick during feature development.

## Step 2 — Skill gate (the tier decides which skills run)

| Tier | `superpowers` pipeline | Validation skills | Suppressed |
|------|------------------------|-------------------|------------|
| **Docs** | OFF — no code | `/doc-sync` (harmonize docs), `wiki` (verify graph) | brainstorming, writing-plans, TDD |
| **Dev** | ON | selective TDD, domain review, verification, `/doc-sync`, `wiki` | — |
| **Staging** | (promotion gate) | precommit, review, security-scan, `wiki` | — |
| **Release** | (promotion gate) | + security | — |

**Docs = `superpowers` OFF** (no-code edit, made directly).
**Dev = `superpowers` ON**: enter via `using-superpowers` — it
auto-runs the pipeline (brainstorm → plan → implement → verify →
review). Overlays on top: selective TDD scope, domain review,
`/doc-sync` (see Step 3).
**Staging / Release** are validation checklists over already-built
work, not new implementation.

**Precondition** — Dev/Staging/Release require the `superpowers`
plugin (`superpowers@claude-plugins-official`). If it is not installed,
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
  branches off freshly fetched `origin/<integration>` (see Feature
  branch base); with **uncommitted changes**, branch off the current
  `HEAD` to carry them along and rebase onto `origin/<integration>` at
  merge time (see Merge strategy).

Write the tier marker only **after** switching — the commit gate is
branch-bound, so the marker must carry the work branch, not the branch
work started on. `hotfix/*` off the production branch is the exception
(left in place).

## Step 3 — Per-tier workflow

### Docs (no code)

1. Make the edit directly (`superpowers` OFF).
2. Run `/doc-sync` to harmonize the doc set (root CLAUDE.md,
   per-service docs, rules; also reconciles code↔doc drift)
   → record `doc-sync`.
3. Commit (Conventional Commits, 50/72 rule — see Commit Discipline
   below) → merge per **Merge strategy**, or open a PR when
   `merge_workflow.pull_request` includes `daily` (see PR workflow).

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
     committed on the branch, and since the `review` marker is
     branch-bound and survives across commits, those files would
     never appear in *any* review's list. `ls-files --others`
     recovers untracked files only, never modified tracked ones.

     At a promotion the working tree is clean and both ends are
     branches, so use the two adjacent `flow-config.branches` refs
     for the promotion in hand — **destination first**, so the diff
     is what the promotion would add:
     `git diff --name-only "origin/<staging>..origin/<integration>"`
     for Staging, and
     `git diff --name-only "origin/<production>..origin/<staging>"`
     for Release. Always the **freshly fetched `origin/` refs**,
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
   - **`/doc-sync`** → record `doc-sync`.
3. Integration human gate (feature → integration branch; see Merge
   Strategy below) → commit → merge, or open a PR when
   `merge_workflow.pull_request` includes `daily` (see PR workflow).

### Staging (integration → staging)

1. Regression review — Dev Step 3's procedure with ①'s promotion form
   for **this** pair (`git fetch origin`, then
   `git diff --name-only "origin/<staging>..origin/<integration>"`;
   the workspace form would list nothing here) → record `review`.
   `precommit` and `security-scan` run automatically on
   promotion commits (runtime gates — no marker; see Gate glossary).
2. Promote integration → staging (rc), or open a PR when
   `merge_workflow.pull_request` includes `promotion` (see PR workflow).

### Release (staging → production)

Staging gates **plus** — but the regression `review` re-runs against
**this** promotion's pair, `git fetch origin` then
`git diff --name-only "origin/<production>..origin/<staging>"`.
Inheriting Staging's pair is the trap here, and it does not announce
itself: staging is not empty relative to integration, it is *ahead* by
the rc bump CI just pushed, so the wrong pair returns a plausible
handful of release plumbing (`plugin.json`, `CHANGELOG.md`,
`pyproject.toml`, `uv.lock`) while hiding every substantive change in
the release. The highest-risk gate then reports full coverage of the
wrong set, with no empty result to give it away.

1. Extra independent review — `/code-review` at `ultra` effort
   (high-risk layer).
2. Security review — `/security-review` → record `security`.
3. Release note — Conventional Commits + semantic-release; the grouped, plumbing-filtered
   CHANGELOG section becomes the GitHub Release body (auto-notes fallback).
4. Promote staging → production and/or deploy, or open a PR for the
   promotion when `merge_workflow.pull_request` includes `promotion`
   (see PR workflow). A `hotfix/*` → production landing takes the same
   conditional — under `promotion` it is a PR too, never a local squash
   and push.

## Commit Discipline

Always apply before every `git commit -m` and every merge.

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
- **No history narration in the body** — no "previously X", no
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

### Merge strategy

Branch names refer to `flow-config.branches` keys.

| Branch flow | Strategy | Gate |
|-------------|----------|------|
| `feature/*` → integration | **Rebase onto integration → integration-test gate → Squash** | ✅ enforced |
| `fix/*` / non-`feature/*` → integration | **Rebase** | ✅ `fix/*` only: `--no-ff` blocked |
| integration → staging | **`--no-ff` Merge** | ✅ enforced |
| staging → production | **`--no-ff` Merge** | ✅ enforced |
| `hotfix/*` → production | **Squash** — under `promotion` PR mode a **PR** (merge commit) | ✅ enforced |
| production → integration (after release) | **FF / `--no-ff` Merge** (back-merge) | — |

> The **Gate** column reflects `flow-tiers.yaml`'s `merge_strategy` policy, checked by the
> PreToolUse hook on `git merge`. Every ✅ row blocks (exit 2) a merge whose flags violate the
> strategy — whether the rule *requires* a flag ("enforced") or *forbids* one ("blocked");
> `—` rows state a choice ("or"), so there is nothing to enforce. A ✅ cell that names a
> narrower pattern than its row (row 2) is enforced for **that pattern only** — the rest of the
> row is discipline the gate does not check. Enforcement covers
> **Claude-session merges only** — a terminal merge bypasses it, same as every layer-2 gate.
> The rebase step of row 1 is **warned, not blocked** (a stale `origin` ref would otherwise
> produce false positives).

> `staging → production` is a `--no-ff` **Merge**, not Squash:
> semantic-release must parse the individual conventional commits, and
> the merge commit's non-`[skip ci]` title is what makes the release
> workflow fire — FF would land staging's `[skip ci]` rc commit as the
> head and skip the release. (A direct `hotfix/*` → production merge stays
> Squash — a single `fix:` commit is still a valid, non-`[skip ci]` release
> input. Under `promotion` PR mode that flow becomes a PR merge commit
> instead; see PR workflow.)

> ⚠️ **Merge the *post-rc* `origin/<staging>`, never a stale local ref.**
> The `staging → production` merge must take the **freshly fetched
> `origin/<staging>`** — the staging state *after* the rc CI ran and
> semantic-release committed the `X.Y.Z-rc.N` version bump. A local
> `<staging>` ref from before that bump does not carry the prerelease
> version into production, so the deterministic rc-strip finalize has
> nothing to strip and **falls back to plain compute — silently losing
> the forced bump-level override** (e.g. releasing `0.2.0` instead of the
> intended `0.1.2`). Always `git fetch origin` first and merge
> `origin/<staging>`.

### PR workflow (`flow-config.merge_workflow`)

Flows listed in `merge_workflow.pull_request` go through a **pull request** instead of a
local merge. An empty list (the default) means every flow is a direct merge and this
section does not apply.

| Value | Flows |
|---|---|
| `daily` | `feature/*` · `fix/*` → integration |
| `promotion` | integration → staging, staging → production — **and `hotfix/*` → production**, because the production ruleset governs every merge into that branch (see below) |

**Commit discipline does not change.** Commits are still made locally under PR mode, so
gitlint (50/72 · Conventional Commits) and the tier gate (markers, unclassified block)
fire exactly as before. What moves is the **merge**, and only the merge.

The `require`/`forbid` cells in the Merge strategy table are enforced by a hook watching
`git merge`, so they **do not fire** for a flow that goes through a PR. A GitHub Ruleset
carries what it can of that enforcement instead, as allowed merge methods per branch —
exactly for the promotion rows, partially for integration (caveat under the table):

| Target branch | Allowed merge methods | Source rows |
|---|---|---|
| integration | `squash` + `rebase` (no merge commit) | row 1 `feature/*`=Squash, row 2 `fix/*`=Rebase |
| staging · production | `merge` only | rows 3·4 = `--no-ff` Merge |

> ⚠️ **On integration this is a relaxation, not a translation.** A branch ruleset targets the
> **destination** ref, so it cannot tell a `feature/*` PR from a `fix/*` one. All it
> guarantees is **"no merge commit into integration"**. Row 1's `--squash` and row 2's Rebase
> become **discipline the ruleset cannot separate**: a `feature/*` PR merged with "Rebase and
> merge" lands N replayed commits where row 1 wants one squashed commit, and nothing objects
> (the local gate never sees a `git merge`, and the ruleset permits rebase). Name the method
> when you hand over the PR — **"Squash and merge" for `feature/*`, "Rebase and merge" for
> `fix/*`** — the way the promotion PR names "Create a merge commit". On staging · production
> the single allowed method makes the ruleset an exact translation; only integration carries
> this gap.

> **A branch ruleset covers every merge into that branch, not just the flow named above.**
> The `daily` ruleset's "require a PR" + `rebase,squash` on integration also governs the
> **back-merge** (table row 6, `production → integration`): it blocks the documented
> `git push origin <integration>` step outright, and routing the back-merge through a PR
> instead is worse — rebase and squash both rewrite SHAs, so the released tag never
> becomes an ancestor of integration, which is exactly the failure the Back-merge section
> calls **not optional**. An integration ruleset therefore also needs a bypass actor, for
> whoever performs the back-merge (the maintainer or the release automation) — the same
> requirement `daily` alone does not otherwise carry.
>
> The `promotion` ruleset's `merge`-only rule on production also governs `hotfix/* →
> production` (table row 5, Squash) — and allowed merge methods hang off **"Require a pull
> request before merging"** (see the bypass warning below), which **rejects a direct push to
> production**. So the documented local path — `git switch <production>` ·
> `git merge --squash hotfix/x` · `git commit` · `git push origin <production>` — is
> rejected *during the incident*, and the release-automation bypass actor does not rescue it
> (that identity is the `github-actions` app or the `RELEASE_TOKEN` owner, not the maintainer
> running the hotfix). **Under `promotion` PR mode a hotfix therefore goes through a PR too**,
> merged with "Create a merge commit". The merge commit is harmless — its title is not
> `[skip ci]`, so the release workflow still fires, no rc is pending to strip, and
> semantic-release computes the release from the `fix:` commit inside it. (A team that would
> rather keep the local squash must instead add a **maintainer** bypass actor to the
> production ruleset — and then nothing enforces the merge method on that path at all.)

`/flow-init` Step 2.7 reads the current state and reports the gap; it does not change repo
settings.

> ⚠️ **Merge a promotion PR with "Create a merge commit" only.** The release workflow reads
> a single pushed **head commit** — it gates execution on `[skip ci]` and reads the
> `Release-Level:` trailer from that same message. A rebase-merge replays staging's commits
> and leaves `chore(release): … [skip ci]` as the head, so **the release never runs**; a
> squash destroys the individual release-commit history.

> ⚠️ **A promotion ruleset MUST carry a release-automation bypass actor.** Allowed merge
> methods hang off the "require a pull request before merging" rule, so applying it without
> a bypass blocks semantic-release's direct `chore(release)` version-bump push and **halts
> the release pipeline**.
>
> The actor's **`bypass_mode` must be `always`, not `pull_request`** — here and for the
> integration back-merge actor above. A `pull_request` actor may merge a PR that fails the
> rule but **may not push directly**, and a direct push is the whole point in both cases. An
> actor in the wrong mode is present-but-useless: it reads as configured and still stops the
> release. `check-merge-ruleset.sh` treats it as a gap for that reason.

With a forced bump level, pin the trailer in the merge command rather than typing it into
the web UI:

```bash
PR=123    # the promotion PR's number — a literal, never a `<n>` placeholder: bash reads
          # `<n` as "stdin from a file named n" and silently eats the next word as its target
gh pr merge "$PR" --merge \
  --subject "Merge <staging>: release X.Y.Z" \
  --body "Release-Level: patch"
```

An automatic (commit-derived) level needs no trailer at all.

### Merging `feature/*` → integration (integration-test gate)

`feature/*` → integration is NOT a one-shot squash. It is a
three-step gated flow. The integration-test confirmation is a
**human gate** — never skip it, never assume tested.

1. **Rebase first.** Rebase the feature branch onto freshly fetched
   `origin/<integration>` and resolve conflicts on the feature branch
   (keeps integration history linear, no merge commit):

   ```bash
   git fetch origin
   git rebase origin/<integration-branch>
   ```

2. **Ask the user — STOP and wait.** Before merging, ask whether they
   ran the **integration test** (real end-to-end — NOT unit tests,
   which do not satisfy this gate). Merge ONLY if the user explicitly
   confirms they tested. If unconfirmed, do not merge.

3. **Squash, then merge** — or, when `merge_workflow.pull_request` includes
   `daily`, open a PR instead of this step's `git merge --squash` and say it
   must be merged with **"Squash and merge"** (the integration ruleset allows
   rebase too and cannot tell the two flows apart — see PR workflow above).
   For a direct merge, choose squash granularity by change size:
   - **Small change** → collapse to **1 commit**.
   - **Larger change** → keep **one commit per category** (e.g. a
     `feat` commit + a separate `test` commit + a `docs` commit),
     rather than one giant blob. Each commit still obeys the 50/72
     rule and carries its own Conventional type.

   ```bash
   git switch <integration>
   git pull --ff-only origin <integration>
   git merge --squash feature/<name>
   ```

### Merge commit messages (integration → staging)

integration → staging makes a `--no-ff` merge commit. Its **title
MUST start with a capital `Merge`** — gitlint recognizes a commit as
a merge only when the title begins with capital `Merge`, and only then
exempts it from the type/50-char checks.

- `Merge <integration>: <headline>` — put the merge summary in the
  **body**, not the title.
- Never use lowercase `merge ...` — full-checked as a normal commit.
- Never use `chore(release): ...` — that prefix is the auto-release
  bot's namespace.

Do not attach a Conventional type to a merge commit. The version is
decided by semantic-release parsing the **individual merged commits**.

Under `promotion` PR mode the same merge commit is created by GitHub's
"Create a merge commit"; pin its title with `gh pr merge --subject`
(see PR workflow) so this rule still holds.

### Back-merge after release (production → integration)

semantic-release writes the version bump (`plugin.json` / `pyproject`)
and the marketplace sha pin **only on `production`** (as `[skip ci]`
`chore(release)` commits). They never reach integration on their own,
so integration's `plugin.json` drifts to a stale version.

After every production release, **back-merge production → integration**
— one merge, nothing else:

```bash
git fetch origin
git switch <integration> && git merge --ff-only origin/<production>
git push origin <integration>
```

Fast-forward when the branch is strictly behind; else `--no-ff` Merge.
Under `daily` PR mode the integration ruleset **rejects this push** unless it
carries a bypass actor for whoever back-merges — routing the back-merge
through a PR instead does not work (see PR workflow).
This one is **not optional**: without it the released tag is unreachable
from integration and semantic-release miscomputes the next version. It is
needed because Explicit-version gating forces the version into a
**committed file** (not a tag-only release, which would never drift).

**staging needs no back-merge** — the next `integration → staging`
promotion carries the release commits forward on its own. The chain is
`integration → staging → production`, and it closes: staging's rc bump
reaches production through the promotion merge, and production's release
commits reach integration through the back-merge above. staging therefore
stays an **ancestor of integration**, so the next promotion is a
descendant merge and the version file cannot conflict.

Measured 2026-07-27 (0.1.12): the 0.1.11 back-merge to staging was
skipped, so `v0.1.11` was **unreachable** from staging (nearest reachable
tag: `v0.1.11-rc.1`). The `integration → staging` merge pulled it into
ancestry and the rc came out correct — `0.1.12-rc.1`.

This holds **only because the promotion is a merge.** A rebase promotion
would replay the release commits under new SHAs, dropping the stable tag
out of staging's ancestry — which is why the Merge strategy table above
enforces `--no-ff` on that row.

### Feature branch base

`/flow` cuts this branch in Step 2b. A **clean** tree branches from
freshly fetched `origin/<integration>`; with **uncommitted changes** it
branches off the current `HEAD` (carrying them) and rebases onto
`origin/<integration>` at merge:

```bash
git fetch origin
git switch -c feature/<name> origin/<integration-branch>
```

Branch names in English.

### When asked "is this commit compliant?"

Re-measure subject char count and each body line length yourself.
Don't trust your earlier write.

## Repo conventions baked in

- **Pre-commit hard gate is inherited by every tier** — the
  `git commit` hook (configured in the project's `settings.json`)
  runs the project's linter / test / formatter chain. Never bypass
  with `--no-verify`.
- **Worker / service-process safety** — Dev+ changes touching
  long-running worker processes: inspect for in-flight tasks and
  require explicit user approval before restarting.
- **Entry point** — a free-text request.

## Hard gates (enforced mechanically)

Gates are enforced at chokepoints, driven by
[`flow-tiers.yaml`](../flow-tiers.yaml) and the evidence markers
`/flow` records under `.claude/harness-tier/.flow/` (gitignored):
`tier` (`<tier>:<branch>`) plus `<gate>.done` per completed gate.

1. **Commit gate (Docs/Dev)** — the `git commit` hook (via the project's
   `flow_gate_check` script) **blocks the commit** when the active tier's
   required marker gate has no `.done` marker, and also **blocks an
   unclassified commit** (policy intact but no `tier` marker — `/flow` was
   skipped). Branch-bound; fail-closed (see Properties).
2. **Promotion gates (Staging / Release)** — enforced purely at
   `git commit` by branch: a commit on the staging branch enforces
   the `staging` gates; a commit on the production branch enforces
   the `release` gates (same commit hook). **Deploy commands are not
   gated** — tiers are separated by commit branch only.

Properties:

- **Fail-open on errors** — missing/unparseable policy or config, or
  any internal error → the action is allowed (a broken gate never bricks
  commits or deploys). The test is "the gate works reliably", not "a
  file exists". **Exception — an unclassified commit is fail-CLOSED**:
  when the policy parses and config is intact but no `tier` marker
  exists, the commit is **blocked** so skipping `/flow` cannot silently
  disable the gate. Promotion gates are likewise fail-*closed* on
  missing evidence, but still fail-open on internal errors.
- **Branch-bound** — markers carry the branch, so stale state cannot
  block an unrelated task on another branch.
- `precommit` / `security-scan` are runtime gates executed by the hook
  (`precommit-runner.sh`, layer 2 — not the layer-1 pre-commit), not markers;
  a tier's `flow-tiers.yaml` `gates` list is the single on/off switch for them
  (see Gate glossary).
- Judgment gates (review quality, human integration test) can only be
  *recorded*, not verified — a marker is an audit trail + forcing
  function, not proof.
- **Air-gapped limit** — an offline production machine runs on a
  separate host a local hook cannot reach; the staging → production
  commit is the local release-authorization gate.

Clear state with `rm -rf .claude/harness-tier/.flow` (also done by `/flow`
after a successful commit/merge).

---

*Pilot: Docs & Dev enforced at commit; Staging at integration →
staging, Release at staging → production / offline deploy. Full
one-shot `/flow` automation of the Dev/Staging/Release pipelines
is a follow-up.*
