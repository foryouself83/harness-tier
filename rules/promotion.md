# Promotion Reference

> Not injected. [`risk-tiers.md`](risk-tiers.md) is the SSOT and the SessionStart hook injects
> it whole; these are its promotion-only sections, kept out so a day-to-day request does not
> carry them. `/flow` reads this at a promotion, `/release-commit` when it writes the merge.

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

The `require`/`forbid` cells in [`risk-tiers.md`](risk-tiers.md)'s Merge strategy table are
enforced by a hook watching
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

> **A branch ruleset covers every merge into that branch, not only the flow named above.**
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
>
> The same ruleset on staging rejects the direct push of the **staging back-merge** (table
> row 7), and that one needs no fix: a rejected push is the documented end of that step —
> report it, leave the local fast-forward where it stands, and switch away. A bypass actor
> there buys an earlier close of the window, never correctness, which is what separates it
> from the integration back-merge above.

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

### Back-merge after release (production → integration · staging)

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
Under `daily` PR mode the integration ruleset **rejects this push**; see PR
workflow for the bypass actor it needs and why a PR cannot stand in.
This one is **not optional**: without it the released tag is unreachable
from integration and semantic-release miscomputes the next version. It is
needed because Explicit-version gating forces the version into a
**committed file** (not a tag-only release, which would never drift).

**staging takes the same back-merge, `--ff-only` and nothing else:**

```bash
git switch <staging> && git merge --ff-only origin/<production>
git push origin <staging>
```

**A refused fast-forward ends it — never fall back to `--no-ff`.** The
release workflow fires on a push to **staging as well as production**, and
reads `[skip ci]` off the head commit alone. A fast-forward lands
production's `chore(release): … [skip ci]` commit as that head, so the
workflow stays asleep; a `--no-ff` merge commit carries no such marker, so
the same push **cuts an rc nobody promoted to staging**. That is why
integration takes the fallback and staging does not — integration is not a
trigger branch. Skip it, and **report the skip**: silence reads as a
completed step. Under `promotion` PR mode the staging ruleset rejects the
**push** instead, after the merge has already moved the local ref — leave
it where it stands and switch away; the next promotion's push absorbs it.
That rejection is a normal finish here and a gap to fix on integration.

Skipping loses no correctness, but leaves one thing to do by hand. The
chain is `integration → staging → production` and closes without this leg:
staging's rc bump reaches production through the promotion merge,
production's release commits reach integration through the back-merge
above, and the next `integration → staging` promotion carries them into
staging on its own. What the skip leaves until then is a released tag
unreachable from staging, and a staging that has diverged — the refusal is
what says so — so that next promotion is a three-way merge rather than a
descendant one, and its version file conflicts: integration carrying the
released `X.Y.Z`, staging its own `X.Y.Z-rc.N`. **Keep staging's rc.** The
rc line continues from there, while resolving to the stable value leaves
finalize no prerelease to strip — it exits non-zero, the release falls back
to plain compute, and the forced bump level is lost.

Measured 2026-07-27 (0.1.12): the 0.1.11 back-merge to staging was
skipped, so `v0.1.11` was **unreachable** from staging (nearest reachable
tag: `v0.1.11-rc.1`). The `integration → staging` merge pulled it into
ancestry and the rc came out correct — `0.1.12-rc.1`.

This holds **only because the promotion is a merge.** A rebase promotion
would replay the release commits under new SHAs, dropping the stable tag
out of staging's ancestry — which is why [`risk-tiers.md`](risk-tiers.md)'s Merge strategy table
enforces `--no-ff` on that row.
