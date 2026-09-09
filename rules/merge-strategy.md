# Merge Strategy

> Read at a merge. Not injected into the session context —
> [`risk-tiers.md`](risk-tiers.md) is, and it points here.

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

**Gate column** — `flow-tiers.yaml`'s `merge_strategy`, checked by the PreToolUse hook on
`git merge`. ✅ = exit 2 on a violating flag, `require` and `forbid` alike. `—` = no
`merge_strategy` entry.

- Row 6: a choice ("or") — nothing to enforce.
- Row 7: a refused fast-forward needs a **skip**, and `require: --ff-only` would block the
  `--no-ff` retry instead of ending the step.
- Row 2's ✅ names a narrower pattern than its row — enforced for that pattern only; the
  rest is unchecked discipline.
- Row 1's rebase step: **warned, not blocked** — a stale `origin` ref would false-positive.
- Scope: **Claude-session merges only**. A terminal merge bypasses it, like every layer-2
  gate.

**`staging → production` = `--no-ff` Merge, never Squash.** semantic-release parses the
individual conventional commits, and the merge commit's non-`[skip ci]` title is what fires
the release workflow. FF lands staging's `[skip ci]` rc commit as the head — no release.
(`hotfix/*` → production stays Squash: one `fix:` commit is still valid non-`[skip ci]`
release input.)

⚠️ **`staging → production` takes the *post-rc* `origin/<staging>`, never a stale local ref.**
Required state: after the rc CI ran and semantic-release committed the `X.Y.Z-rc.N` bump.
A pre-bump local ref carries no prerelease version into production, so the rc-strip
finalize has nothing to strip and **falls back to plain compute — the forced bump-level
override is lost silently** (`0.2.0` shipped where `0.1.2` was intended). `git fetch
origin` first, merge `origin/<staging>`.

### Merging `feature/*` → integration (integration-test gate)

Not a one-shot squash — three gated steps. The integration-test confirmation is a **human
gate**: never skipped, never assumed.

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

   A green `e2e.yml` does not satisfy this gate. That workflow is a layer-3 net on the
   promotion branches: it reports *after* a merge and blocks nothing. Different point,
   different flow — dropping this gate for a downstream signal is a net coverage loss.

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

Rule: [`risk-tiers.md`](risk-tiers.md) Step 2b. Command:

```bash
git fetch origin
git switch -c feature/<name> origin/<integration-branch>
```

Branch names in English.
