# Tiers and gates

**English** · [한국어](tiers-and-gates.ko.md) · [Usage guide](../../USAGE.md)

Work is classified into one of four tiers, and the tier decides which gates must pass before it
can commit. The classification rules themselves live in
[`rules/risk-tiers.md`](../../rules/risk-tiers.md), which a SessionStart hook injects into every
session.

## Tiers

| Tier | When | superpowers | Required gates |
|------|------|:---:|----------------|
| `docs` | no-code change (docs, comments, config values) | ✗ | `doc-sync` · `wiki` · `doc-style` |
| `dev` | change with code (feature, fix) | ✓ | `precommit` · `review` · `doc-sync` · `wiki` · `doc-style` |
| `staging` | integration → staging promotion | ✗ | `precommit` · `review` · `security-scan` · `bump` · `wiki` · `doc-style` |
| `release` | staging → production promotion | ✗ | `precommit` · `security-scan` · `security` · `wiki` · `doc-style` |

`docs` and `dev` come from [`/flow`](daily-work.md#flow--the-day-to-day-router), which writes a
`tier` marker. `staging` and `release` come from the branch the commit lands on;
[`/release-commit`](promotion-and-release.md) runs them. Release has no `review`: Dev and Staging
already read that diff.

## What the gate sees

Three layers check your work, and each sees a different set of commits:

1. **pre-commit** — `.pre-commit-config.yaml`: commit-message lint and file checks, on every
   `git commit` in a repo where `pre-commit install` ran.
2. **The flow gate** — the `PreToolUse` hook `/flow-init` registers in `.claude/settings.json`.
   It sees only `git commit`, `git merge`, and branch-naming, non-rebasing `git pull`
   commands **Claude runs in a session**. A commit or merge from your own terminal, from CI,
   or on GitHub bypasses it. It reads the command as written: a git alias (`git ci`,
   `git -c alias.ci=commit ci`) or a subcommand built by expansion (`git $(echo commit)`,
   `$g commit`) is not read as a commit, and other commands that create commits, such as
   `cherry-pick`, `revert`, `am`, `rebase` and `commit-tree`, are not gated. A commit in a
   worktree is judged by that worktree's own `.claude/harness-tier/`, so one branched before
   the `/flow-init` setup commit carries no policy and passes ungated until it takes that
   commit (merge or rebase it in). A single `git -C <dir> commit` or `cd <dir> && git commit`
   that names another repository outright — proven by a `--git-common-dir` that differs from
   this one's — is not read as this repo's commit either; a second command, a directory
   reached by expansion, a stacked `-C`, or a `--git-dir`/`GIT_DIR` that could send it back
   here all leave that unproven, so the commit stays gated.
3. **CI** — the workflows `/flow-init` renders, which run on every push and close the gap
   layer 2 leaves ([CI workflows](ci-workflows.md)).

Every gate on this page is layer 2. The hook entry carries a 600-second timeout, which covers
every module check it runs; a single check has no timeout of its own.

## Gates

### Evidence gates — `review` · `doc-sync` · `security` · `bump`

Each passes when its marker `.claude/harness-tier/.flow/<gate>.done` exists. The skill that runs
the gate writes the marker: `/flow` for `review` and `doc-sync`, `/release-commit` for
`review`, `bump` and `security` at a promotion. `bump` is the human major / minor / patch
choice, and it fails closed: a staging commit stays blocked until the choice is made.

### Module-check gates — `precommit` · `security-scan`

The commit hook runs `modules[].checks` itself: `precommit` the changed modules'
`every-commit` checks, `security-scan` every module's `promotion` checks
([`when`](configuration.md#modules-and-checks)). A nonzero exit blocks the commit. The output is
buffered and printed only on failure. Removing either gate from a tier in the policy turns that
bucket off for the tier.

### `wiki`

Runs in the hook process when `flow-config.wiki.enable` is true, and does nothing otherwise.
It checks `docs/graph/graph.yaml` against the documents' front matter, read-only, and reads the
**working tree** — the hook fires before `git commit` stages anything. Stage `graph.yaml`
together with the documents it was built from; a rebuilt but unstaged graph passes the gate
while the commit records the stale one.

It blocks two things:

- a structure violation — the list is capped at 10 entries plus a count;
- a commit whose only change to a node is its `sources` stamp, with no body edit. Two stamp
  swaps stay allowed: `/doc-sync` migrating a legacy marker, and a stamp whose body edit landed
  in the commit right before it, a rename in that commit included.

Graph-quality findings come back as a warning, even on a commit that passes: orphans, oversize
documents, `sources` paths not on disk, an `sds` document with no `sources` value, a tag ready
to promote to a rule, front matter that fails to parse, and a wiki-only field on a document with
no `wiki_id`.

### `doc-style`

The one gate that never blocks. When `flow-config.doc_style.enable` is true, it lints the files
the commit changes that `paths` and `exclude` put in scope, and reports **error**-level findings
— history narration, plan-record pointers, filler, Korean `~다` endings and the rest of the
banned list in [`rules/doc-style.md`](../../rules/doc-style.md). The `LONG` and `CLAIM` warnings
appear only in `doc_style_check.py --lint` and in CI.

The verdict belongs to the `doc-style.yml` workflow, which sees the whole tree. The hook and CI
read the scope through one function, so an `exclude` holds in both. A `flow-config.yaml` that
does not parse fails the CI job rather than reading as "off". With `enable: false` there is no
check in either layer.

### SRS integrity is not a gate

The flow gate never reads an SRS. `srs-verify.yml`, which `/flow-init` offers once `docs/srs/`
exists, is the only check that catches a dead requirement anchor or a number two branches both
took ([CI workflows](ci-workflows.md)).

## Gate evidence

`review` and `doc-sync` judge the working tree, so a `PostToolUse` hook deletes **both** markers
when Claude edits a file — the fixes a review asked for included — and tells the session which
evidence it voided. A fix therefore re-runs `/doc-sync` and the review. An edit the hook never
sees — a terminal command, another tool — leaves the markers standing; delete them yourself.

`gate_evidence.invalidate_on_edit: false` turns the deletion off, at the cost of commits made
under a review that never saw the last edit.

The `tier` marker is bound to its branch. A `<gate>.done` file is not: `/flow` and
`/release-commit` clear the evidence when they finish, but a task that stops before that step
leaves its markers for whatever runs next, on any branch.

## Merge strategy

`flow-tiers.yaml`'s `merge_strategy` checks the flags of a `git merge`, and of a `git pull`
that names a branch without rebasing, against its branch flow. Flags are read as git reads
them: an abbreviation, the last of two opposing options, and a `-c merge.ff=…` (for a pull,
`-c pull.ff=…` over it) on the command line all count; a `merge.ff`, `pull.ff`,
`branch.<name>.mergeoptions` or `pull.rebase` set in git config is not seen. Branch names
resolve from `flow-config.branches`, and a source with a revision suffix (`stage^0`) is judged
as its branch. A `$( … )` or backtick among the operands is one word, so flags after it count
and a merge inside one is judged; a `git merge` written among the arguments of another merge,
pull, switch or checkout that starts its command runs nothing and is not judged (behind `eval`,
`watch` or `ssh`, which parse the arguments again, it is).

| Merge | Enforced |
|-------|----------|
| `feature/*` → integration | `--squash` required |
| `hotfix/*` → production | `--squash` required |
| integration → staging | `--no-ff` required |
| staging → production | `--no-ff` required |
| `fix/*` → integration | `--no-ff` refused |

A violation is blocked. Only flows with a single correct flag are checked: the production →
integration back-merge and the staging → integration back-merge before a re-promotion allow
fast-forward or `--no-ff`, and the production → staging back-merge wants a skip when the
fast-forward is refused, which no `require` rule expresses. A `feature/*` merge not rebased
first is warned about, not blocked — a stale `origin` ref would otherwise raise false alarms.

A command the gate cannot decide lets the merge through: no matching rule, a command it cannot
parse, or merges that all run in another directory. A merge behind a `cd` beside one naming no
directory is judged anyway. One naming no directory at all, in a command that moves the shell
nowhere else (no `cd`, `pushd`, `popd`, subshell, `env`, `--git-dir`, `--work-tree`, `GIT_DIR`
or `GIT_WORK_TREE`), takes its implicit target from the branch of the tree the shell runs in,
not the main checkout — a worktree session merges into its own branch this way. `-C .` names
that same tree outright and reads the same branch.

The check sees only direct merges. A flow routed through a pull request moves enforcement to a
GitHub branch ruleset —
[PR workflow and branch rulesets](promotion-and-release.md#pr-workflow-and-branch-rulesets).
The procedure for every flow is [`rules/merge-strategy.md`](../../rules/merge-strategy.md).
