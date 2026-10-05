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
| staging → integration (before a re-promotion) | **FF / `--no-ff` Merge** (back-merge) | — |
| production → integration (after a release or hotfix) | **FF / `--no-ff` Merge** (back-merge) | — |
| production → staging (after a release or hotfix) | **FF only** (back-merge; refused → skip) | — |

**Gate column** — `flow-tiers.yaml`'s `merge_strategy`, checked by the PreToolUse hook on
`git merge` and on a `git pull` that names a branch without rebasing. ✅ = exit 2 on a
violating flag, `require` and `forbid` alike. `—` = no `merge_strategy` entry.

- Flags are read as git reads them: an abbreviation (`--no-f`), the last of two opposing
  options, and a `-c merge.ff=…` (for a pull, `-c pull.ff=…` over it) on the command line
  all count. A source with a revision suffix (`stage^0`, `stage~1`) is judged as its branch.
- Read from the command alone: a `merge.ff`, `pull.ff`, `branch.<name>.mergeoptions` or
  `pull.rebase` set in git config is not seen.
- A `$( … )` or backtick among the operands is one word, so flags after it count; a merge
  inside one is judged. A `git merge` written among the arguments of another merge, pull,
  switch or checkout that starts its command runs nothing and is not judged.
- `eval`, `watch` (without `-x`) and `ssh` parse the words after them again, and the gate
  reads them as that parse does: a merge among another's arguments is judged, and a quoted
  separator or `#` ends the merge before it — a later merge's flags do not count for it.
- A redirection and its target (`>|log`, `2>&1`, `&>log`) are not operands: the flags after
  one still count.
- A command the gate cannot decide lets the merge through: no matching rule, a command it
  cannot parse, or merges that all run in another directory. A merge behind a `cd` beside one
  naming no directory is judged anyway. One naming no directory at all, in a command that
  moves the shell nowhere else (no `cd`, `pushd`, `popd`, subshell, `env`, `--git-dir`,
  `--work-tree`, `GIT_DIR` or `GIT_WORK_TREE`), takes its implicit target from the branch of
  the tree the shell runs in, not the main checkout — a worktree session merges into its own
  branch this way. `-C .` names that same tree outright and reads the same branch.

- Rows 6 and 7: a choice ("or") — nothing to enforce.
- Row 8: a refused fast-forward needs a **skip**, and `require: --ff-only` would block the
  `--no-ff` retry instead of ending the step.
- Row 2's ✅ names a narrower pattern than its row — enforced for that pattern only; the
  rest is unchecked discipline.
- Row 1's rebase step: **warned, not blocked** — a stale `origin` ref would false-positive.
- Scope: **agent-session (Claude Code or Codex) merges only**. A terminal merge bypasses it,
  like every layer-2 gate.

**`staging → production` = `--no-ff` Merge, never Squash.** semantic-release parses the
individual conventional commits, and the merge commit's non-`[skip ci]` title is what fires
the release workflow. FF lands staging's `[skip ci]` rc commit as the head — no release.
(`hotfix/*` → production stays Squash: one `fix:` commit is still valid non-`[skip ci]`
release input.)

⚠️ **`staging → production` takes the *post-rc* `origin/<staging>`, never a stale local ref.**
Required state: after the rc CI ran and semantic-release committed the `X.Y.Z-rc.N` bump.
A pre-bump local ref carries no prerelease version into production, so the rc-strip
finalize has nothing to strip and **falls back to plain compute — the forced bump-level
override is lost silently** (`0.2.0` shipped where `0.1.2` was intended).
`git fetch origin` first, merge `origin/<staging>`.

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

Rule: [`/flow`](../skills/flow/SKILL.md) Phase 2. Command:

```bash
git fetch origin
git switch -c feature/<name> origin/<integration-branch>
```

Branch names in English.
