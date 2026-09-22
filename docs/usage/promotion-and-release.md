# Promotion and release

**English** · [한국어](promotion-and-release.ko.md) · [Usage guide](../../USAGE.md)

A promotion moves integration to staging (a release candidate) or staging to production (a
release). The branch the commit lands on sets the tier, so there is no `tier` marker and no
`/flow` step. The rules behind every step are in [`rules/promotion.md`](../../rules/promotion.md).

## `/release-commit` — run one promotion

```text
/release-commit [staging | release]
```

With no argument it asks which promotion. A bare "cut the release" reaches it too.

1. **Reads your release model.** `grep -c Release-Level .github/workflows/release.yml`
   answers whether the bump level can be forced. The `python-semantic-release`, `jreleaser`,
   `gitversion` and `cargo-release` templates read the trailer; Node `semantic-release` derives
   the level from commit types and reads none. With no `release.yml` it stops and points you to
   `/flow-init`. No workflow takes a level from a `workflow_dispatch`, so triggering one forces
   nothing.
2. **Staging** —
   - an independent review of `origin/<staging>..origin/<integration>` against
     `review_checklist`;
   - a recommended level from the commit types and your `commit_guide`'s 0.x policy;
   - where the level can be forced, it always asks major / minor / patch, and warns when `major`
     on `0.x` jumps to `1.0.0`;
   - a warning when the release token cannot push (best effort, never blocks);
   - the `review` and `bump` markers.
3. **Release** — confirms `origin/<staging>` carries an `X.Y.Z-rc.N` version, runs
   `/security-review`, and writes the `security` marker. No code review: Dev and Staging read
   this diff already.
4. **Merges, then commits.** `git merge --no-ff --no-commit origin/<source>`, then `/commit`
   writes the pending merge as `Merge <source>: <headline>`. The `Release-Level:` trailer goes
   on only at Staging, only where the workflow reads it, and only on the first promotion of a
   version — re-promoting the same rc series with a trailer bumps the base version again and
   skips the release. CI reads `git log -1` alone, so the order matters: a trailer committed
   before the merge sits one commit back and the run auto-derives the bump.
5. **Closes the cycle.** After a release:
   - back-merge production → integration — not optional; the released tag is otherwise
     unreachable from integration and the next version comes out wrong;
   - back-merge production → staging, fast-forward only — a refused fast-forward is skipped,
     never forced with `--no-ff`, which would cut an rc nobody promoted.

   Either promotion then deletes its own evidence markers. A run that stopped at the rc included:
   nothing else removes `bump.done`, and the next promotion would read it as its own pass.

When the `wiki` gate blocks a promotion commit, rebuild with
`python3 .claude/harness-tier/scripts/wiki_graph.py --build` and stage `graph.yaml` into it.

A promotion versions the whole repository at one version. Never put a CI-skip marker in a
promotion merge message: the release job never runs and nothing reports it.

## PR workflow and branch rulesets

With `merge_workflow.pull_request` listing a flow
([configuration](configuration.md#merge_workflowpull_request)), that flow's merge becomes a pull
request. Commits are still made locally, so gitlint and the tier gates fire as before. The
[merge strategy](tiers-and-gates.md#merge-strategy) check never sees a `git merge` for that flow,
so enforcement moves to a GitHub branch ruleset's allowed merge methods:

| Target branch | Allowed methods |
|---------------|-----------------|
| integration | `squash` + `rebase` |
| staging · production | `merge` only |

`/flow-init` reads the current rulesets with `gh` and reports the gap. It never changes them.

- **`promotion` is an exact swap.** One method per branch. Merge a promotion PR with "Create a
  merge commit" only — a rebase leaves the `[skip ci]` release commit as the head, so the release
  never runs; a squash destroys the release history. With a forced level, pin the trailer:
  `gh pr merge "$PR" --merge --subject "Merge <staging>: release X.Y.Z" --body "Release-Level: patch"`.
- **`daily` is partial.** A ruleset targets the destination branch, so it cannot tell a
  `feature/*` PR from a `fix/*` one. It guarantees only "no merge commit into integration".
  Say which method the PR takes when you hand it over: "Squash and merge" for `feature/*`,
  "Rebase and merge" for `fix/*`.
- **A ruleset governs every merge into its branch.** On production it also catches `hotfix/*`,
  so under `promotion` a hotfix goes through a PR too. On integration it blocks the push of the
  post-release back-merge. On staging it blocks the staging back-merge push, which needs no
  fix — a refused push is that step's end.
- **Bypass actors.** A `promotion` ruleset needs a release-automation bypass actor, or the
  release tool's version-bump push is refused and releases stop. A ruleset on integration needs
  one for whoever performs the back-merge. Both with `bypass_mode: always` — a `pull_request`
  actor may not push directly.

Under PR mode, `/flow` and `/release-commit` clear the evidence only after the PR merges: a
review-feedback commit on the PR branch is gated like the first.

## Release token write permission

The release workflow pushes the version bump and tag, so its token needs **write**. Every
rendered release template authenticates with `${{ secrets.RELEASE_TOKEN || secrets.GITHUB_TOKEN }}`:
with no `RELEASE_TOKEN` secret it runs on the default `GITHUB_TOKEN`.

1. **Repository setting** — Settings → Actions → General → **Workflow permissions** →
   **Read and write permissions** → Save.
2. **Organization cap** — if the organization limits Actions to read-only, an organization admin
   has to relax it or let repositories choose.
3. **Protected branch or ruleset** — if the release branch restricts pushes, add the Actions bot
   or the token owner to the bypass list.
4. **`RELEASE_TOKEN`** — when `GITHUB_TOKEN` is not enough (bypassing protection, triggering
   downstream workflows), create a fine-grained PAT with `Contents: Read and write`, plus
   `Workflows: Read and write` if the release touches workflow files, and store it as the
   repository secret `RELEASE_TOKEN`. No workflow edit is needed.

The rendered workflows have no token preflight: a read-only token fails at the push.
`/release-commit` runs `check-token-write.sh` during a Staging promotion and warns first when
it can tell.
