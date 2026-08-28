---
name: flow
description: MANDATORY first step for ALL development work — invoke BEFORE starting any code change, feature, fix, or free-text dev request, and before any commit. Skipping it leaves the commit unclassified and the commit gate blocks it. Also applies when promoting integration→staging or staging→production.
argument-hint: "[free-text request]"
# Pre-approves only the gate-evidence writes — the one thing this skill does several
# times per run. Exact marker paths, no trailing glob: a glob's `*` crosses path
# separators including `..`, so `.flow/*` pre-approved touch of any path on disk.
# `git commit` and `rm -rf` are deliberately absent: the commit prompt is the mechanical
# backstop behind the gate, and the Phase 4 cleanup should stay deliberate.
allowed-tools: Bash(mkdir -p .claude/harness-tier/.flow) Bash(touch .claude/harness-tier/.flow/doc-sync.done) Bash(touch .claude/harness-tier/.flow/review.done) Bash(touch .claude/harness-tier/.flow/bump.done) Bash(touch .claude/harness-tier/.flow/security.done)
---

# Flow — Risk-Tiered Workflow Router

Classify the incoming work by risk, confirm the tier, run the matching workflow,
and record gate evidence under `.claude/harness-tier/.flow/` so the `git commit` hook
enforces the tier's required gates.

**Source of truth**: [`risk-tiers.md`](../../rules/risk-tiers.md) (criteria, skill
gate, per-tier steps) and [`flow-tiers.yaml`](../../flow-tiers.yaml) (tier→gates the
commit hook enforces). `risk-tiers.md` is already in context — the SessionStart hook
injects it — but **read `flow-tiers.yaml`**, which is not injected and carries the
gate list you must report in Phase 1.

Branch names referenced below come from `flow-config.branches`
(`integration` / `staging` / `production`). Domain-review items come from
`flow-config.review_checklist` and per-module pre-checks from `flow-config.modules`.

Four tiers, two axes:
- **Day-to-day task** (this skill's main job): **Docs** (no code) or
  **Dev** (any code).
- **Promotion** (run when cutting a release): **Staging** (integration → staging)
  and **Release** (staging → production) — see "Promotion" below.

## Input

- **$ARGUMENTS** — a free-text request. If empty, ask the user what the task is.
- Carry that request text forward as *the task* for every later phase — it is the
  explicit input to `brainstorming` and the reference for the commit scope.

## Phase 1 — Classify the task (Docs or Dev)

The line is simple: **code, or no code.** Inspect the real change, do not guess:

```bash
git diff --name-only HEAD                       # already-changed files
git ls-files --others --exclude-standard        # new files
```

- **No source code** (`.md` / docs / comments / pure config-text only) → **Docs**.
- **Any** change to `.py` / `.js` / `.ts` … (however small), or new feature / DB
  schema / cross-service shared package / business logic·node·workflow·validator /
  dependency change / 2+ services → **Dev**. (Full rubric in
  [`risk-tiers.md`](../../rules/risk-tiers.md).)

Output the verdict — tier, reason, gates (from [`flow-tiers.yaml`](../../flow-tiers.yaml)):

```
## Tier Classification
- Tier: DEV
- Reason: changes src/*.py (source code)
- Gates: precommit, review, doc-sync, wiki
```

## Phase 2 — Confirm the tier & switch to a work branch (human gate)

Use `AskUserQuestion` to confirm the tier, allowing an override. **Do not start
before confirmation.** When uncertain, default one tier up.

**Then ensure you are on a work branch — before writing the marker.** Day-to-day
work (Docs *and* Dev) lives on `feature/*` / `fix/*`, never directly on an
integration/staging/production branch (`flow-config.branches`). See
[`risk-tiers.md`](../../rules/risk-tiers.md) Step 2b:

```bash
cur=$(git branch --show-current)
case "$cur" in
  feature/*|fix/*|hotfix/*) ;;                       # already a work branch — stay (idempotent)
  *)
    # On integration/staging/production → cut a work branch. Prefix follows the
    # Conventional type (feat → feature/, fix → fix/); <slug> from the task, English.
    # Confirm the branch name with the user first.
    if git diff --quiet && git diff --cached --quiet; then
      git fetch origin                                # clean tree → branch off fresh integration
      git switch -c <feature|fix>/<slug> "origin/<integration-branch>"
    else
      git switch -c <feature|fix>/<slug>              # uncommitted changes → carry them off current HEAD
    fi
    ;;
esac
```

Record the tier marker **after** switching, so it binds to the work branch (the
commit gate is branch-bound):

```bash
# Ensure the evidence directory is never exposed to git (idempotent). Safe even
# without running /flow-init first: add the ignore rule *before* writing the tier
# marker to close the untracked-exposure window.
grep -qxF '.claude/harness-tier/.flow/' .gitignore 2>/dev/null || printf '\n.claude/harness-tier/.flow/\n' >> .gitignore
mkdir -p .claude/harness-tier/.flow
echo "<tier>:$(git branch --show-current)" > .claude/harness-tier/.flow/tier   # docs | dev
```

## Phase 3 — Dispatch

Record each completed gate as `.claude/harness-tier/.flow/<gate>.done`. `precommit`
(every-commit module checks of changed modules) and `security-scan` (promotion module
checks of all modules) are executed by the commit hook itself — no marker (both are
ordinary `gates` entries and timing buckets over `flow-config.modules[].checks`, routed
by each check's `when`; removing one from a tier's list in
[`flow-tiers.yaml`](../../flow-tiers.yaml) disables it for that tier). **`wiki`** is a
third runtime gate needing no marker — not a timing bucket, the hook's gate script runs
`wiki_graph.py --verify` in-process whenever `flow-config.wiki` is enabled (no-op
otherwise). Do **not** `touch .claude/harness-tier/.flow/wiki.done` and do not go
looking for a `wiki` gate skill — none exists; the hook runs the check itself.

> **Precondition (Dev / Staging / Release)** — the `superpowers` plugin must
> be installed. If `superpowers:using-superpowers` is **not** among the available
> skills, **STOP**: tell the user to install it
> (`superpowers@claude-plugins-official`, e.g. via `/plugin`) and re-run `/flow`.
> Do **not** fall back to manual implementation.

### Docs — no code (`superpowers` OFF)

1. Make the edit directly. Do **not** invoke `superpowers`. precommit not needed
   (no code).
2. Invoke the `doc-sync` skill to harmonize the doc set (index `CLAUDE.md` + per-service docs +
   rule dirs from `flow-config.doc_sync`; also reconciles code↔doc drift). On pass
   → `touch .claude/harness-tier/.flow/doc-sync.done`.
3. Commit through the `commit` skill — invoke `Skill: commit` with the tier and what
   changed; it stages, picks the type, and applies the 50/72 rule (rule 4). Then merge
   **applying the risk-tiers Merge strategy** (rule 3 — not a plain merge). (The commit
   hook blocks until `doc-sync.done` exists.)
   When `flow-config.merge_workflow.pull_request` includes `daily`, open a **PR** instead
   of merging: rebase → integration-test human gate (unchanged) → push → `gh pr create` →
   hand over the PR URL **and name the merge method it must use** — **"Squash and merge"**
   from a `feature/*` branch, **"Rebase and merge"** from `fix/*` (Merge strategy rows 1·2;
   the integration ruleset allows both and cannot tell them apart, so this one is on you) —
   then stop. Without `gh`, print the compare URL and let the user create it — never block.

### Dev — any code (`superpowers` ON)

1. **Load the wiki context first** (skip silently when there is no wiki — both
   commands print nothing and exit 0): name the files you are about to change to
   `python3 .claude/harness-tier/scripts/wiki_graph.py --nodes-for <paths…>`, then
   for each printed id run
   `python3 .claude/harness-tier/scripts/wiki_graph.py --neighbors <id>` and **read
   the documents it lists** before planning. An empty result is a normal answer (the
   code is undocumented) — proceed without it.
2. **Enter `superpowers:using-superpowers`** — it drives the pipeline automatically
   (brainstorm → plan → implement → verify → review; each skill self-triggers).
   Feed the resolved request from Phase 0 in as the task.
3. Apply the project overlays `superpowers` does not know about:
   - **Implementation minimalism** — right after the plan, before writing code,
     climb the reuse-before-build ladder (YAGNI → codebase → stdlib → native →
     dependency → one line → minimum code) and stop at the earliest rung. Detail
     and non-negotiable floor in [`risk-tiers.md`](../../rules/risk-tiers.md) Step 3.
   - **Selective TDD** — only business logic / core nodes / validators / workflow
     orchestration (see [`risk-tiers.md`](../../rules/risk-tiers.md) Step 3), not
     every change.
   - **Domain review** — an independent **`general-purpose`** review agent
     (separate context; it runs shell commands). `git` is the authority on the
     changed-file list — **every** file is reviewed and the count is reported —
     judged against `flow-config.review_checklist` (regression, cross-service
     contract, DB/migration & transactions, async task idempotency, API errors),
     plus the callers of every changed public symbol. Procedure in
     [`risk-tiers.md`](../../rules/risk-tiers.md) Step 3.
     On pass → `touch .claude/harness-tier/.flow/review.done`.
   - **invoke the `doc-sync` skill** (not part of `superpowers`) → `touch .claude/harness-tier/.flow/doc-sync.done`.
4. Commit through the `commit` skill — invoke `Skill: commit` with the tier and what
   changed (rule 4) → merge **applying the risk-tiers Merge strategy** (rule 3 — not a
   plain merge). (The commit hook blocks until `review.done` and `doc-sync.done`.)
   When `flow-config.merge_workflow.pull_request` includes `daily`, open a **PR** instead
   of merging: rebase → integration-test human gate (unchanged) → push → `gh pr create` →
   hand over the PR URL **and name the merge method it must use** — **"Squash and merge"**
   from a `feature/*` branch, **"Rebase and merge"** from `fix/*` (Merge strategy rows 1·2;
   the integration ruleset allows both and cannot tell them apart, so this one is on you) —
   then stop. Without `gh`, print the compare URL and let the user create it — never block.

## Promotion — Staging (integration → staging) / Release (staging → production)

Promotions are gated at the **commit on the target branch** (no tier marker
needed — the branch drives it). Record each gate before committing the promotion.
`precommit`, `security-scan`, and `wiki` need no marker at all — they are runtime
gates the commit hook runs directly on both the staging and the production commit
(per [`flow-tiers.yaml`](../../flow-tiers.yaml)); the bullets below cover only the
gates that **do** need a recorded marker.

`wiki` is the one runtime gate with no skill behind it in a promotion. `doc-sync` — the
only thing that rebuilds `graph.yaml` — is not a promotion gate, so a graph drift that
arrived on the integration branch via a terminal commit (layer 2 never saw it) surfaces
here as a blocked promotion commit. Resolve it in place: run
`python3 .claude/harness-tier/scripts/wiki_graph.py --build` and stage the rebuilt
`graph.yaml` into the promotion commit. If instead the failure names a structure
violation (`wiki_id` format/duplicate · missing `title` · dangling `depends_on` · cycle ·
front matter that does not parse while carrying a `wiki_id`), the fix is the document's
front matter — `--build` cannot resolve those.

- **Staging** (integration → staging): regression `review` (independent
  `general-purpose` agent; the tree is clean at promotion, so `git fetch origin` and list
  the files with the pair **for this promotion** —
  `git diff --name-only "origin/<staging>..origin/<integration>"`; the Release bullet below
  has its own pair, do not reuse this one there. Always the fetched `origin/` refs, since a
  stale local ref shrinks the reviewed set; see
  [`risk-tiers.md`](../../rules/risk-tiers.md) Step 3) **and bump-level selection**:
  1. Compute the commit-derived level as the default: `semantic-release version --print`
     (best-effort) — compare to the current version to suggest major/minor/patch.
  2. `AskUserQuestion`: **major / minor / patch** (default = the derived level).
     **If the choice is `major` while the current version is `0.x`, warn that it jumps
     to `1.0.0`** (explicit `--major` overrides `major_on_zero=false`).
  3. Before committing the staging promotion, **best-effort** warn if the release token
     lacks write: if `gh`/a token is available, run
     `.claude/harness-tier/scripts/check-token-write.sh` (exit 10 → warn with the
     Settings/PAT how-to; exit 20/no tool → skip silently, never block).
  4. `touch .claude/harness-tier/.flow/review.done` ·
     `touch .claude/harness-tier/.flow/bump.done` (two commands, written out — the brace
     form neither matches the exact allowed-tools rules nor reads as what actually runs).
  5. Commit on the staging branch through the `commit` skill (`Skill: commit`) —
     **pass the chosen level in the arguments**, the only channel it has: `bump.done`
     is an empty marker and nothing on disk carries the level. It appends the
     **trailer** `Release-Level: <level>`, which CI reads to force
     `semantic-release version --<level> --as-prerelease`. main needs no level — it
     finalizes the rc deterministically.
- **Release** (staging → production): Staging gates **plus** `/code-review` at
  `ultra` effort (extra independent layer) and `/security-review` →
  `touch .claude/harness-tier/.flow/security.done`, then commit on the production branch
  through the `commit` skill (`Skill: commit`) — no level here; finalize is deterministic.
  ⚠️ The regression `review` here takes **its own** file list —
  `git diff --name-only "origin/<production>..origin/<staging>"`, not the Staging bullet's
  pair. Reusing that pair does not fail loudly: staging is *ahead* of integration by the rc
  bump CI just pushed, so it returns a plausible handful of release plumbing and hides every
  substantive change — full coverage of the wrong set, with no empty result to give it away.
  ⚠️ **Merge the freshly fetched `origin/<staging>`** (post-rc — it carries the
  `X.Y.Z-rc.N` bump), not a stale local staging ref: otherwise the rc-strip finalize
  has no prerelease to strip, falls back to plain compute, and the bump-level override
  is lost (e.g. `0.2.0` instead of `0.1.2`). Always `git fetch origin` first.
  Deploy (project-specific / offline) — not gated; the production-branch commit
  is the gate.
- **PR-mode promotion** (`merge_workflow.pull_request` includes `promotion`) — gate
  recording is unchanged; instead of committing on the target branch, open a PR. It **must**
  be merged as a merge commit (a rebase stops the release, a squash destroys the history —
  [`risk-tiers.md`](../../rules/risk-tiers.md) PR workflow). A **`hotfix/*` → production**
  landing takes the same path under this mode: the production ruleset governs every merge
  into that branch, and its "require a pull request" rule rejects the local
  squash-and-push — so open a PR for the hotfix too and merge it as a merge commit. With a
  forced bump level, pin the trailer in the merge command (`PR` is a literal number, not a
  `<n>` placeholder — bash would read `<n` as a redirection and eat the next word):

  ```bash
  PR=123
  gh pr merge "$PR" --merge --subject "Merge <staging>: release X.Y.Z" --body "Release-Level: <level>"
  ```
- **Back-merge after the production release (not optional)** — once the finalize
  CI has pushed its `chore(release)` version-bump + marketplace-sha-pin commits to
  production, back-merge **production → integration** so the released tag returns
  to the day-to-day branch: `git fetch origin`, then
  `git switch <integration> && git merge --ff-only origin/<production>`, and push
  (FF when strictly behind, else `--no-ff`). Skipping it leaves the released tag
  unreachable from integration → semantic-release miscomputes the next version.
  **staging needs no leg** — the next `integration → staging` promotion carries
  the release commits forward on its own, which is why that row is now a
  gate-enforced `--no-ff` merge. Rationale/steps:
  [`risk-tiers.md`](../../rules/risk-tiers.md) "Back-merge after release".

The commit hook ([`flow_gate_check.py`](../../scripts/flow_gate_check.py)) blocks
the staging/production commit until those markers exist.

## Phase 4 — Finalize

After the commit/merge completes — and, for a **production release**, after the
back-merge in the Release step above (production → integration, not
optional) — clear the flow state.

**Under PR mode, clear only after the PR is merged.** Markers are branch-bound, so a
review-feedback commit on the same branch needs its marker alive to pass the gate. Clearing
at PR-creation time leaves the follow-up commit unclassified and blocked.

```bash
rm -rf .claude/harness-tier/.flow
```

## Critical rules

1. **Always classify before working** — confirm with the user (Phase 2), then
   write the tier marker.
2. **Record gate evidence honestly** — `touch .claude/harness-tier/.flow/<gate>.done` only
   after the gate genuinely passes. A marker is a forcing function, not a stamp.
3. **Apply the documented Merge strategy** — direct commit + merge, but
   **do not default to a plain / `--no-ff` merge**. For every merge, look up its
   branch-flow row in [`risk-tiers.md`](../../rules/risk-tiers.md) **Merge strategy**
   and follow it exactly — the required strategy varies by flow (rebase / squash /
   `--no-ff` merge). Commit types & the 50/72 rule live in the same file's Commit
   Discipline. Several of those rows are **enforced by the hook**: a merge whose flags
   violate its row is blocked (exit 2) naming the flag it wants. The table's **Gate**
   column says which rows fire — the rest still depend on you following them.
4. **Every commit goes through the `commit` skill** — invoke `Skill: commit`, which
   owns staging, the type choice, and the 50/72 rule so this skill does not restate
   them. It inherits the pre-commit gate like any other commit: never `--no-verify`.
5. **Commit from a git worktree with `git -C <worktree> commit …`** — a single
   command, not a preceding `cd`. `CLAUDE_PROJECT_DIR` is fixed at session start,
   so when the commit runs in a worktree, the gate re-points to it by branch-key
   (`flow_gate_check.py --resolve-worktree`); the explicit `git -C <worktree>` is the
   deterministic signal that keeps that detection unambiguous. (No worktree → no
   change.) The `commit` skill issues it that way (rule 4), and owns
   "never `--no-verify`" and "stage only affected files" with it.
6. **Worker / service-process safety** — Dev+ changes touching long-running
   worker processes: inspect for in-flight tasks and require explicit user
   approval before restarting.
7. **On conflict, [`risk-tiers.md`](../../rules/risk-tiers.md) and
   [`flow-tiers.yaml`](../../flow-tiers.yaml) win** — where this skill disagrees with
   them, follow them, and tell the user this skill has drifted.
