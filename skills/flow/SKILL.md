---
name: flow
description: MANDATORY first step for ALL development work — invoke BEFORE starting any code change, feature, fix, or free-text dev request. Classifies the task as Docs/Dev by risk, confirms the tier, runs the matching workflow, and records the gate evidence the commit hook enforces; skipping it leaves the commit unclassified and the commit gate blocks it. Staging/Release apply at integration→staging / staging→production.
allowed-tools: Bash, Read, Grep, Glob, Skill, AskUserQuestion, Edit, Write
argument-hint: "[free-text request]"
---

# Flow — Risk-Tiered Workflow Router

Classify the incoming work by risk, confirm the tier, run the matching workflow,
and record gate evidence under `.claude/harness-tier/.flow/` so the `git commit` hook
enforces the tier's required gates.

**Source of truth**: [`risk-tiers.md`](../../rules/risk-tiers.md) (criteria, skill
gate, per-tier steps) and [`flow-tiers.yaml`](../../flow-tiers.yaml) (tier→gates the
commit hook enforces). Read them first; do not duplicate their content.

Branch names referenced below come from `flow-config.branches`
(`integration` / `staging` / `production`). Domain-review items come from
`flow-config.review_checklist` and per-module pre-checks from `flow-config.modules`.

Four tiers, two axes:
- **Day-to-day task** (this command's main job): **Docs** (no code) or
  **Dev** (any code).
- **Promotion** (run when cutting a release): **Staging** (integration → staging)
  and **Release** (staging → production) — see "Promotion" below.

## Input

- **$ARGUMENTS** — a free-text request.
- If empty, ask the user what the task is.

## Phase 0 — Resolve input

Treat `$ARGUMENTS` as the request text.

Carry the **resolved request text** forward as *the task* for every later step — it
is the explicit input to `brainstorming` and the reference for the commit scope.

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
- Gates: precommit, review, doc-sync
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
(module lint/static/import_lint/test) and `security-scan` are executed by the
commit hook itself — no marker (both are ordinary `gates` entries; removing
one from a tier's list in [`flow-tiers.yaml`](../../flow-tiers.yaml) disables
it for that tier).

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
3. Commit (Conventional Commits, 50/72; stage only affected files; from a worktree
   use `git -C <worktree> commit …` — rule 5) → merge **applying the risk-tiers
   Merge strategy** (rule 3 — not a plain merge). (The commit hook blocks until
   `doc-sync.done` exists.)

### Dev — any code (`superpowers` ON)

1. **Enter `superpowers:using-superpowers`** — it drives the pipeline automatically
   (brainstorm → plan → implement → verify → review; each skill self-triggers).
   Feed the resolved request from Phase 0 in as the task.
2. Apply the project overlays `superpowers` does not know about:
   - **Implementation minimalism** — right after the plan, before writing code,
     climb the reuse-before-build ladder (YAGNI → codebase → stdlib → native →
     dependency → one line → minimum code) and stop at the earliest rung. Detail
     and non-negotiable floor in [`risk-tiers.md`](../../rules/risk-tiers.md) Step 3.
   - **Selective TDD** — only business logic / core nodes / validators / workflow
     orchestration (see [`risk-tiers.md`](../../rules/risk-tiers.md) Step 3), not
     every change.
   - **Domain review** — an independent `general-purpose` review agent (separate
     context) against `flow-config.review_checklist` (regression, cross-service
     contract, DB/migration & transactions, async task idempotency, API errors).
     On pass → `touch .claude/harness-tier/.flow/review.done`.
   - **invoke the `doc-sync` skill** (not part of `superpowers`) → `touch .claude/harness-tier/.flow/doc-sync.done`.
3. Commit → merge **applying the risk-tiers Merge strategy** (rule 3 — not a plain
   merge; from a worktree use `git -C <worktree> commit …` — rule 5). (The commit
   hook blocks until `review.done` and `doc-sync.done`.)

## Promotion — Staging (integration → staging) / Release (staging → production)

Promotions are gated at the **commit on the target branch** (no tier marker
needed — the branch drives it). Record each gate before committing the promotion:

- **Staging** (integration → staging): regression `review` (independent
  `general-purpose` agent) **and bump-level selection**:
  1. Compute the commit-derived level as the default: `semantic-release version --print`
     (best-effort) — compare to the current version to suggest major/minor/patch.
  2. `AskUserQuestion`: **major / minor / patch** (default = the derived level).
     **If the choice is `major` while the current version is `0.x`, warn that it jumps
     to `1.0.0`** (explicit `--major` overrides `major_on_zero=false`).
  3. Before committing the staging promotion, **best-effort** warn if the release token
     lacks write: if `gh`/a token is available, run
     `.claude/harness-tier/scripts/check-token-write.sh` (exit 10 → warn with the
     Settings/PAT how-to; exit 20/no tool → skip silently, never block).
  4. `touch .claude/harness-tier/.flow/{review,bump}.done`.
  5. Commit on the staging branch **with a trailer** `Release-Level: <level>` (blank
     line before the trailer). CI reads it to force
     `semantic-release version --<level> --as-prerelease`. main needs no level — it
     finalizes the rc deterministically.
- **Release** (staging → production): Staging gates **plus** `/code-review` at
  `ultra` effort (extra independent layer) and `/security-review` →
  `touch .claude/harness-tier/.flow/security.done`, then commit on the production branch.
  ⚠️ **Merge the freshly fetched `origin/<staging>`** (post-rc — it carries the
  `X.Y.Z-rc.N` bump), not a stale local staging ref: otherwise the rc-strip finalize
  has no prerelease to strip, falls back to plain compute, and the bump-level override
  is lost (e.g. `0.2.0` instead of `0.1.2`). Always `git fetch origin` first.
  Deploy (project-specific / offline) — not gated; the production-branch commit
  is the gate.
- **Back-merge after the production release (not optional)** — once the finalize
  CI has pushed its `chore(release)` version-bump + marketplace-sha-pin commits to
  production, back-merge them **production → integration and → staging** so the
  released tag returns to the day-to-day branches: `git fetch origin`, then
  `git switch <integration> && git merge --ff-only origin/<production>` (same for
  `<staging>`), and push each (FF when strictly behind, else `--no-ff`). Skipping it
  leaves the released tag unreachable from integration/staging → semantic-release
  miscomputes the next version. Rationale/steps:
  [`risk-tiers.md`](../../rules/risk-tiers.md) "Back-merge after release".

The commit hook ([`flow_gate_check.py`](../../scripts/flow_gate_check.py)) blocks
the staging/production commit until those markers exist.

## Phase 4 — Finalize

After the commit/merge completes — and, for a **production release**, after the
back-merge in the Release step above (production → integration/staging, not
optional) — clear the flow state:

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
   Discipline.
4. **Inherit the pre-commit gate** — never bypass the `git commit` hook
   (no `--no-verify`).
5. **Commit from a git worktree with `git -C <worktree> commit …`** — a single
   command, not a preceding `cd`. `CLAUDE_PROJECT_DIR` is fixed at session start,
   so when the commit runs in a worktree, the gate re-points to it by branch-key
   (`flow_gate_check.py --resolve-worktree`); the explicit `git -C <worktree>` is the
   deterministic signal that keeps that detection unambiguous. (No worktree → no
   change.) Stands alongside rules 4 (no `--no-verify`) and "stage only affected files".
6. **Worker / service-process safety** — Dev+ changes touching long-running
   worker processes: inspect for in-flight tasks and require explicit user
   approval before restarting.
7. **[`risk-tiers.md`](../../rules/risk-tiers.md) and
   [`flow-tiers.yaml`](../../flow-tiers.yaml) are the source of truth** — if this
   command diverges, follow them and fix this command.
