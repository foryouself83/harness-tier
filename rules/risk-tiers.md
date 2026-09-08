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

Each gate is defined **once here**; every table and step below refers to a
gate by name only. (For how gates are enforced — chokepoints, markers,
fail-open/closed — see Hard gates.)

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
    not on disk, an `sds` document whose `sources` key is absent or has no value,
    defect→rule promotion, front matter that fails to parse without a
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

  - **`doc-style`** — the prose gate, the other in-process stage. When
    `flow-config.doc_style` is enabled it lints the files this commit changes that its
    `paths`/`exclude` globs put in scope (default `**/*.md`; name `**/*.py`·`**/*.sh` to
    cover comments and docstrings) against [`doc-style.md`](doc-style.md) and reports
    what it finds as a `systemMessage`. Scope is read by the same function CI's
    `--lint-config` uses, so an `exclude` holds in both arms. It **never blocks**: the
    verdict belongs to `doc-style.yml` in CI, which sees the whole tree, where a rule
    tightening cannot deny a commit nobody could predict. No `doc_style` block,
    `enable: false`, or any internal error → nothing runs (Invariant #1). Runs on every
    tier including `docs`.

  Hosts add their own runtime checks by putting extra keys under
  `flow-config.modules[].checks` — a command string (timing defaults by key name:
  `security` → promotion, else every-commit) or `{ run, when }` to set timing
  explicitly (use `when`, not `on` — YAML reads a bare `on` key as a boolean).
  **Timing is bound to that bucket's gate existing in the tier**: the `docs` tier has
  neither *bucket* gate, so host custom checks never run on a docs commit — the module
  pre-check short-circuits there. (`wiki`·`doc-style` still run on a docs commit; neither is
  a module check and neither enters that path.) `precommit` and `security-scan` are ordinary
  entries in each tier's `flow-tiers.yaml`
  `gates` list, so **removing one disables that whole bucket** for that tier (the
  gates list is the single on/off switch, not a hardcoded branch). Like all
  layer-2 checks these run **only on Claude-session commits** — terminal/CI commits
  are not gated (add a CI safety net if you need hard enforcement).
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
    (the staging commit is blocked until `bump.done` exists). Detail in Step 1b.
  - **`security`** (Release) — `/security-review`. A dangerous Dev-tier
    change runs it too, unenforced — Step 1b Release says why.

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
promotion gates run once over the accumulated work. They sit on their
own axis: the Docs → Dev escalation ladder in Principle is the
day-to-day one, and each promotion's gate set is chosen for that
promotion rather than stacked on Dev's.

### Staging — integration → staging branch (QA / rc cut)

The release candidate enters QA/staging; its gates are in the git-flow mapping
table below. Performance and integration are independent skills; the
`/security-review` LLM review is added at Release.

Staging also **forces a human bump-level choice**: `/release-commit` asks major/minor/patch
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

One entry point: the staging → production promotion (official release),
or a production deploy (e.g., an air-gapped offline deploy). Gates in the
git-flow mapping table below.

**A dangerous change does not escalate into this tier.** A single change
that hits an irreversible/large data migration, a **performance-critical
path** (search/embedding/GPU/inference config), or a security surface
(auth/authz, secrets, gateway rate-limiting) stays at **Dev** and adds
`/security-review` before the merge. Release carries no `review`, so
escalating into it would buy a security pass by giving up the domain
review — the wrong trade for the one change that needs both. Nothing
stops it mechanically: the gate reads the tier marker's label and checks
only that its branch matches, so a hand-written `release:feature/x` does
select this set. That security pass is therefore discipline, not a gate.

### Tie-breakers

Within the day-to-day **Docs → Dev** axis only — the promotion tiers are
branch-driven and are never picked this way.

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
2. Run `/doc-sync` (Gate glossary) → record `doc-sync`.
3. Commit via `/commit` (it applies Commit Discipline below)
   → merge per **Merge strategy**, or open a PR when
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
     in `flow-config.yaml`. The hook is registered by the plugin, so a
     version bump arms it with no `/flow-init` step to agree to; the
     switch is how the host that carries the cost answers. Armed is the
     default: the hook reads `false` under a top-level `gate_evidence:`
     and nothing else, so a YAML-false spelled `no`/`off`/`False`, or
     the key written under another block, leaves it armed. It reads the
     file line by line, so a file YAML cannot load still disarms on that
     one line — and a line the reader cannot make out leaves it armed.
3. Integration human gate (feature → integration branch; see Merge
   Strategy below) → commit via `/commit` → merge, or open a PR when
   `merge_workflow.pull_request` includes `daily` (PR workflow in
   [`promotion.md`](promotion.md)).

### Staging (integration → staging)

1. Regression review — Dev Step 3's procedure with ①'s promotion form
   for **this** pair (`git fetch origin`, then
   `git diff --name-only "origin/<staging>..origin/<integration>"`;
   the workspace form would list nothing here) → record `review`.
   `precommit` and `security-scan` run automatically on
   promotion commits (runtime gates — no marker; see Gate glossary).
2. Promote integration → staging (rc), or open a PR when
   `merge_workflow.pull_request` includes `promotion` (PR workflow in
   [`promotion.md`](promotion.md)).

### Release (staging → production)

Gates: Staging's set with `security` added and both `bump` and `review`
dropped, the finalize taking no level.

**Code review does not run here.** Everything this promotion carries was
read twice already — per task at Dev, as a batch at Staging — and what
staging holds beyond that is CI's `chore(release)` bump. A third pass buys
a second opinion on the same diff at the one moment where acting on a
finding means unwinding a release. Two paths it does leave unread, both
worth knowing: a `hotfix/*` → production landing never passes through
staging, so its Dev-tier `review` at commit time is the whole of its
review; and a commit made onto staging from a terminal is read by no gate
at all — Staging's pair surfaces it only inverted, as a deletion the merge
will not make, never as the change that was written, and this was the only
layer that read it the right way round.

1. Security review — `/security-review` → record `security`.
2. Release note — Conventional Commits + semantic-release; the grouped, plumbing-filtered
   CHANGELOG section becomes the GitHub Release body (auto-notes fallback).
3. Promote staging → production and/or deploy, or open a PR for the
   promotion when `merge_workflow.pull_request` includes `promotion`
   (PR workflow in [`promotion.md`](promotion.md), which covers `hotfix/*` →
   production under the same value).

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
| production → staging (after release) | **FF only** (back-merge; refused → skip) | — |

> The **Gate** column reflects `flow-tiers.yaml`'s `merge_strategy` policy, checked by the
> PreToolUse hook on `git merge`. Every ✅ row blocks (exit 2) a merge whose flags violate the
> strategy — whether the rule *requires* a flag ("enforced") or *forbids* one ("blocked");
> `—` rows carry no `merge_strategy` entry at all. Row 6 states a choice ("or"), so there is
> nothing to enforce; row 7 names a single flag and still carries none, because what it needs
> on a refused fast-forward is a **skip**, and a `require: --ff-only` rule would block the
> `--no-ff` attempt rather than end the step. A ✅ cell that names a
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
> input.)

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

   A green `e2e.yml` in CI does not satisfy this gate. That workflow is a layer-3 safety net
   on the promotion branches — it reports after a merge, never before one, and it blocks
   nothing. This gate is a human confirmation at a different point in a different flow;
   removing it because a signal appeared downstream is a net loss of coverage.

3. **Squash, then merge** — or, when `merge_workflow.pull_request` includes
   `daily`, open a PR instead of this step's `git merge --squash` and say it
   must be merged with **"Squash and merge"** (the integration ruleset allows
   rebase too and cannot tell the two flows apart — PR workflow in
   [`promotion.md`](promotion.md)).
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

### Feature branch base

Step 2b owns the rule. What it does not carry is the command:

```bash
git fetch origin
git switch -c feature/<name> origin/<integration-branch>
```

Branch names in English.

### When asked "is this commit compliant?"

Re-measure subject char count and each body line length yourself.
Don't trust your earlier write.

## Repo conventions baked in

- **Never bypass the layer-1 hook with `--no-verify`** — the host's
  `.pre-commit-config.yaml` chain is git-native and runs on every commit,
  tier or no tier. The tier-driven check is a different thing: the
  `precommit` runtime gate (Gate glossary), carried by every tier except
  `docs`.
- **Worker / service-process safety** — Dev+ changes touching
  long-running worker processes: inspect for in-flight tasks and
  require explicit user approval before restarting.
- **Entry point** — a free-text request.

## Hard gates (enforced mechanically)

Gates are enforced at chokepoints, driven by
[`flow-tiers.yaml`](../flow-tiers.yaml) and the evidence markers
`/flow` and `/release-commit` record under
`.claude/harness-tier/.flow/` (gitignored):
`tier` (`<tier>:<branch>`) plus `<gate>.done` per completed gate.

1. **Commit gate (Docs/Dev)** — the `git commit` hook (via the project's
   `flow_gate_check` script) **blocks the commit** when the active tier's
   required marker gate has no `.done` marker, and also **blocks an
   unclassified commit** (policy intact but no `tier` marker — `/flow` was
   skipped). Branch-bound; fail-closed (see Properties).
2. **Promotion gates (Staging / Release)** — enforced at `git commit`.
   The branch decides first: a commit on the staging branch enforces the
   `staging` gates, one on the production branch the `release` gates (same
   commit hook). With no lifecycle branch the `tier` marker's own label
   selects the set instead, which is the path a hand-written
   `release:feature/x` takes (see Release). **Deploy commands are not
   gated.**

Properties:

- **Fail-open on errors** — missing/unparseable policy or config, or
  any internal error → the action is allowed (a broken gate never bricks
  commits or deploys). The test is "the gate works reliably", not "a
  file exists". The unclassified-commit block above is the exception —
  it is what stops a skipped `/flow` from silently disabling the gate —
  and promotion gates are likewise fail-*closed* on missing evidence.
  Both still fail open on an internal error.
- **Branch-bound** — markers carry the branch, so stale state cannot
  block an unrelated task on another branch.
- The four runtime gates — `precommit`, `security-scan`, `wiki`, `doc-style` — are run
  by the hook rather than recorded as markers; layer 2, not the layer-1 pre-commit
  (Gate glossary).
- Judgment gates (review quality, human integration test) can only be
  *recorded*, not verified.
- **Air-gapped limit** — an offline production machine runs on a
  separate host a local hook cannot reach; the staging → production
  commit is the local release-authorization gate.

Clear state with `rm -rf .claude/harness-tier/.flow`, which is what
`/flow` does after a successful commit/merge. `/release-commit`
deletes its three promotion markers by name at its end state
instead, so a `doc-sync.done` earned by day-to-day work survives
the promotion.

---

*Pilot: Docs & Dev enforced at commit; Staging at integration →
staging, Release at staging → production / offline deploy.
`/release-commit` runs the Staging and Release pipelines end to
end; one-shot `/flow` automation of the Dev pipeline is a
follow-up.*
