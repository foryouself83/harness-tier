---
name: flow
description: MANDATORY first step for ALL development work — invoke BEFORE starting any code change, feature, fix, or free-text dev request, and before any commit. Skipping it leaves the commit unclassified and the commit gate blocks it.
argument-hint: "[free-text request]"
# Pre-approves only the gate-evidence writes — the one thing this skill does several
# times per run. Exact marker paths, no trailing glob: a glob's `*` crosses path
# separators including `..`, so `.flow/*` pre-approved touch of any path on disk.
# `git commit` and `rm -rf` are deliberately absent: the commit prompt is the mechanical
# backstop behind the gate, and the Phase 4 cleanup should stay deliberate.
allowed-tools: Bash(mkdir -p .claude/harness-tier/.flow) Bash(touch .claude/harness-tier/.flow/doc-sync.done) Bash(touch .claude/harness-tier/.flow/review.done)
---

# Flow — Risk-Tiered Workflow Router

Classify the incoming work by risk, confirm the tier, run the matching workflow,
and record gate evidence under `.claude/harness-tier/.flow/` so the `git commit` hook
enforces the tier's required gates.

**Source of truth**: [`risk-tiers.md`](../../rules/risk-tiers.md) (criteria, skill
gate, per-tier steps) and [`flow-tiers.yaml`](../../flow-tiers.yaml) (tier→gates the
commit hook enforces). `risk-tiers.md` is already in context — the SessionStart hook
injects it — but **read `flow-tiers.yaml`**, which is not injected and carries the
gate list you must report in Phase 1. On a promotion also read
[`promotion.md`](../../rules/promotion.md), the promotion-only half of the rule,
which nothing injects either.

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

**A promotion is not a day-to-day task.** A request to promote a branch, cut a release
candidate, or release — integration → staging, staging → production — has no tier to
classify: the target branch decides it. Hand it to `Skill: release-commit` and stop here.
The rubric below is the wrong instrument for that ask.

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
- Gates: precommit, review, doc-sync, wiki, doc-style
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
[`flow-tiers.yaml`](../../flow-tiers.yaml) disables it for that tier). **`wiki`** and
**`doc-style`** are two more gates needing no marker — neither is a timing bucket; the
hook's gate script runs both in-process, `wiki_graph.py --verify` whenever
`flow-config.wiki` is enabled and the prose lint whenever `flow-config.doc_style` is
(each a no-op otherwise). `doc-style` only ever warns; `doc-style.yml` in CI holds the
verdict. Do **not** `touch .claude/harness-tier/.flow/wiki.done` or `doc-style.done`, and
do not go looking for a skill behind either — none exists; the hook runs the checks.

> **Precondition (Dev)** — the `superpowers` plugin must
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
   **applying [`merge-strategy.md`](../../rules/merge-strategy.md)** (rule 3 — not a
   plain merge). (The commit
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
   When that produces nothing — no wiki, or no node owns the paths — read
   `docs/sds/README.md` and `docs/srs/README.md` directly if they exist
   ([`harness-rules.md`](../../rules/harness-rules.md) 8 fixes those locations). Neither
   existing is normal — proceed. **Docs tier skips this**: reading a design document to
   change a paragraph is the process-to-risk mismatch the tiers exist to prevent.
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
   - **invoke the `doc-sync` skill** (not part of `superpowers`) →
     `touch .claude/harness-tier/.flow/doc-sync.done`.
   - **Domain review** — an independent **`general-purpose`** review agent
     (separate context; it runs shell commands). `git` is the authority on the
     changed-file list — **every** file is reviewed and the count is reported —
     judged against `flow-config.review_checklist` (regression, cross-service
     contract, DB/migration & transactions, async task idempotency, API errors),
     plus the callers of every changed public symbol. Procedure in
     [`risk-tiers.md`](../../rules/risk-tiers.md) Step 3.
     On pass → `touch .claude/harness-tier/.flow/review.done`.
     **Every edit after that pass voids it** — the fixes the review itself asked
     for included. A `PostToolUse` hook deletes `review.done` **and**
     `doc-sync.done` the moment a file changes, so passing is a fixpoint: both
     recorded, nothing edited since. A fix therefore re-runs doc-sync and then
     this review, over a recomputed changed-file list. An edit the hook never
     saw (a terminal command, another tool) leaves the markers standing —
     `rm -f .claude/harness-tier/.flow/review.done .claude/harness-tier/.flow/doc-sync.done`.
4. Commit through the `commit` skill — invoke `Skill: commit` with the tier and what
   changed (rule 4) → merge **applying
   [`merge-strategy.md`](../../rules/merge-strategy.md)** (rule 3 — not a
   plain merge). (The commit hook blocks until `review.done` and `doc-sync.done`.)
   When `flow-config.merge_workflow.pull_request` includes `daily`, open a **PR** instead
   of merging: rebase → integration-test human gate (unchanged) → push → `gh pr create` →
   hand over the PR URL **and name the merge method it must use** — **"Squash and merge"**
   from a `feature/*` branch, **"Rebase and merge"** from `fix/*` (Merge strategy rows 1·2;
   the integration ruleset allows both and cannot tell them apart, so this one is on you) —
   then stop. Without `gh`, print the compare URL and let the user create it — never block.

## Promotion — Staging (integration → staging) / Release (staging → production)

Promotions are gated at the **commit on the target branch**, so they need no tier marker —
the branch drives it. Read [`promotion.md`](../../rules/promotion.md) first — nothing
injects it. The procedure itself lives in
[`release-commit`](../release-commit/SKILL.md): which bump-level mechanism the host's release
CI is on, the gates and their markers, the merge shape each promotion takes, and the end state
the three branches settle into. Invoke `Skill: release-commit` rather than restating any of it
here — one fact, one place.

## Phase 4 — Finalize

After the commit/merge completes, clear the flow state. The command below removes the
evidence directory whole — every marker in it, never a selected subset. Phase 4 is the
day-to-day task's finalize step, and a promotion never reaches it: those markers are
`release-commit`'s to clear at its own end state, where the post-release back-merges also
happen — production → integration (not optional) and production → staging (fast-forward
only, skipped when refused).

**Under PR mode, clear only after the PR is merged.** A review-feedback commit pushed to the
PR branch is gated like any other, and the gate reads whether the tier marker and each gate's
evidence file exists. Clearing at PR-creation time leaves that commit unclassified and blocked.

```bash
rm -rf .claude/harness-tier/.flow
```

## Critical rules

1. **Always classify before working** — confirm with the user (Phase 2), then
   write the tier marker.
2. **Record gate evidence honestly** — `touch .claude/harness-tier/.flow/<gate>.done` only
   after the gate genuinely passes. A marker is a forcing function, not a stamp.
   It is a plain file that outlives the commit that used it, so **a gate whose
   subject changed after it passed is no longer recorded honestly**. The
   `PostToolUse` hook enforces that for `review` and `doc-sync` — any edit
   deletes both — so what is left to you is the edit it cannot see (a terminal
   command, another tool): delete the marker yourself and earn it again.
3. **Apply the documented Merge strategy** — direct commit + merge, but
   **do not default to a plain / `--no-ff` merge**. For every merge, look up its
   branch-flow row in [`merge-strategy.md`](../../rules/merge-strategy.md)
   and follow it exactly — the required strategy varies by flow (rebase / squash /
   `--no-ff` merge). Commit types & the 50/72 rule live in
   [`risk-tiers.md`](../../rules/risk-tiers.md) Commit Discipline. Several of those rows
   are **enforced by the hook**: a merge whose flags
   violate its row is blocked (exit 2) naming the flag it wants. The table's **Gate**
   column says which rows fire — the rest still depend on you following them.
4. **Every commit goes through the `commit` skill** — invoke `Skill: commit`, which
   owns staging, the type choice, and the 50/72 rule so this skill does not restate
   them. It inherits the pre-commit gate like any other commit: never `--no-verify`.
5. **Commit from a git worktree with `git -C <worktree> commit …`** — a single
   command, not a preceding `cd`. `CLAUDE_PROJECT_DIR` is fixed at session start,
   so when the commit runs in a worktree, the gate re-points to it by branch-key
   (`flow_gate_check.py --classify`); the explicit `git -C <worktree>` is the
   deterministic signal that keeps that detection unambiguous. (No worktree → no
   change.) The `commit` skill issues it that way (rule 4), and owns
   "never `--no-verify`" and "stage only affected files" with it.
6. **Worker / service-process safety** — Dev+ changes touching long-running
   worker processes: inspect for in-flight tasks and require explicit user
   approval before restarting.
7. **On conflict, [`risk-tiers.md`](../../rules/risk-tiers.md) and
   [`flow-tiers.yaml`](../../flow-tiers.yaml) win** — where this skill disagrees with
   them, follow them, and tell the user this skill has drifted.
