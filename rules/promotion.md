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

The `require`/`forbid` cells in [`merge-strategy.md`](merge-strategy.md)'s table are
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
> **back-merge** (table row 7, `production → integration`): it blocks the documented
> `git push origin <integration>` step outright, and routing the back-merge through a PR
> instead is worse — rebase and squash both rewrite SHAs, so the released tag never
> becomes an ancestor of integration, which is exactly the failure the Back-merge section
> calls **not optional**. An integration ruleset therefore also needs a bypass actor, for
> whoever performs the back-merge (the maintainer or the release automation) — the same
> requirement `daily` alone does not otherwise carry. The re-promotion back-merge (table
> row 6, `staging → integration`) ends in the same `git push origin <integration>`, rejected
> the same way, and needs the same bypass actor.
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
> The same ruleset on staging rejects the direct push of the **production → staging
> back-merge** (table row 8), and that one needs no fix: a rejected push is the documented
> end of that step — report it, leave the local fast-forward where it stands, and switch
> away. A bypass actor
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

Pin the trailer in the merge command rather than typing it into the web UI — the level the
Staging question chose, `auto` included:

```bash
PR=123    # the promotion PR's number — a literal, never a `<n>` placeholder: bash reads
          # `<n` as "stdin from a file named n" and silently eats the next word as its target
gh pr merge "$PR" --merge \
  --subject "Merge <staging>: release X.Y.Z" \
  --body "Release-Level: patch"
```

A merge with no trailer runs as `auto`; a hand-written workflow that reads none takes none.


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
— one merge, nothing else. A hotfix release is one too: `hotfix/*` → production
never passes through `/release-commit`'s Release, so its back-merge runs from
[`release-commit`](../skills/release-commit/SKILL.md)'s Hotfix section. The merge:

```bash
git fetch origin
git switch <integration> && git merge --ff-only origin/<integration>
git merge --ff-only origin/<production>
git push origin <integration>
```

Fast-forward when the branch is strictly behind; else `--no-ff` Merge. After a hotfix
release, an integration that took a re-promotion back-merge carries the rc version, so the
version files conflict: **keep integration's rc version lines** — the next promotion
computes from the tag list, not from that file.
Under `daily` PR mode the integration ruleset **rejects this push**; see PR
workflow for the bypass actor it needs and why a PR cannot stand in.
This one is **not optional**: without it the released tag is unreachable
from integration and semantic-release miscomputes the next version. It is
needed because Explicit-version gating forces the version into a
**committed file** (not a tag-only release, which would never drift).

**staging takes the same back-merge, `--ff-only` and nothing else:**

```bash
git switch <staging> && git merge --ff-only origin/<staging>
git merge --ff-only origin/<production>
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
out of staging's ancestry — which is why [`merge-strategy.md`](merge-strategy.md)'s table
enforces `--no-ff` on that row.

## Promotion events (Staging / Release)

These are **not** per-task classifications — they are git-flow
promotion gates run once over the accumulated work. They sit on their
own axis: the Docs → Dev escalation ladder in Principle is the
day-to-day one, and each promotion's gate set is chosen for that
promotion rather than stacked on Dev's.

### Staging — integration → staging branch (QA / rc cut)

The release candidate enters QA/staging; its gates are in the git-flow mapping
table in [`risk-tiers.md`](risk-tiers.md). Performance and integration are independent skills; the
`/security-review` LLM review is added at Release.

Staging also **forces a human bump-level choice**: `/release-commit` asks the level and
records a `bump` gate marker; the commit gate blocks the staging commit until `bump.done`
exists (fail-closed). The choice rides the staging commit's HEAD as a `Release-Level:`
trailer, one of `auto | continue | patch | minor | major`, written explicitly whatever the
choice. No trailer reads as `auto`. Any other value, an empty one, two different ones, or
`continue` with no pending rc **fails the prerelease run** — nothing falls back silently.
Every rendered release template reads it; `major` on a 0.x project jumps to `1.0.0`.

The **pending rc** is the highest `vX.Y.Z-rc.N` tag whose base `X.Y.Z` has no stable tag
and sits above the highest stable tag, read from the repository's whole tag list, never from
`git describe`. A released rc is never pending, even on a staging whose release back-merge
refused the fast-forward; nor is one a later stable release left behind (`v0.2.3-rc.5` beside
`v0.4.0`), since finishing it would ship a downgrade. `next` fails rather than cut an rc tag
that already exists.
`bump_version.py next` computes the next version from the trailer and that list, the same
code in every workflow and in `/release-commit`'s labels:

| Choice | No pending rc (last stable `1.0.3`) | Pending `1.1.0-rc.2` |
|---|---|---|
| `auto` | the release tool's commit-derived level | not offered |
| `continue` | the run fails | `1.1.0-rc.3` |
| `patch` | `1.0.4-rc.1` | `1.1.1-rc.1` |
| `minor` | `1.1.0-rc.1` | `1.2.0-rc.1` |
| `major` | `2.0.0-rc.1` | `2.0.0-rc.1` |

**A re-promotion asks the level again.** A re-promotion is an integration → staging
promotion while an rc is pending. It first back-merges staging → integration
([`merge-strategy.md`](merge-strategy.md)), so integration carries the rc version commit,
then asks **continue / patch / minor / major**. A forced level bumps the **base** again, so on
a re-promotion it skips `X.Y.Z` as a stable release. That is a choice the user makes, not a
default: continuing the series is the recommendation.

A forced level is applied deterministically; only `auto` is left to the tool:

| Tool | `auto` | A forced level |
|---|---|---|
| python-semantic-release | `semantic-release version` | the computed version, committed and tagged; stamps pyproject `[project]` version and `.claude-plugin/plugin.json` only — other `version_variables` / `version_toml` targets move on the `auto` path alone |
| Node semantic-release | `npx semantic-release` | an annotated tag `release vX (Release-Level)` and a GitHub prerelease, no `.releaserc` plugins (no npm publish, changelog or version commit) |
| gitversion · jreleaser | continue the pending rc, else `patch` | the computed version |
| cargo-release | `cargo release rc` | `cargo release <version>` |

Node carries two consequences. While a forced rc is pending, a push with no trailer continues
it and the commit types' level is ignored until it ships. On the stable branch, a forced rc
reachable from HEAD is finalized by `gh release create`; a squash promotion hides it from HEAD
and semantic-release decides the release instead.

### Release — staging → production branch

One entry point: the staging → production promotion (official release),
or a production deploy (e.g., an air-gapped offline deploy). Gates in the
git-flow mapping table in [`risk-tiers.md`](risk-tiers.md).

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

## Promotion steps

### Staging (integration → staging)

1. Regression review — [`risk-tiers.md`](risk-tiers.md) Step 3's procedure with ①'s form
   for **this** pair (`git fetch origin`, then
   `git diff --name-only "origin/<staging>..origin/<integration>"`;
   the workspace form would list nothing here) → record `review`.
   `precommit` and `security-scan` run automatically on
   promotion commits (runtime gates — no marker; see
   [`risk-tiers.md`](risk-tiers.md) Gate glossary).
2. Promote integration → staging (rc), or open a PR when
   `merge_workflow.pull_request` includes `promotion` (the PR workflow above).

### Release (staging → production)

Gates: Staging's set with `security` added and both `bump` and `review`
dropped, the finalize taking no level.

**A hotfix that shipped the rc's base, or a higher one, blocks the finalize.** When the
stable tag the finalize is about to create already exists, or sits below the highest stable
tag, the run fails before writing anything:
`vX.Y.Z already exists — a hotfix shipped this base`, or
`vX.Y.Z is below the latest release vA.B.C`. The rc is no longer pending, so
`continue` fails too; re-promote staging with `patch` or higher (`1.1.1-rc.1` behind a
shipped `1.1.1` → `1.1.2-rc.1`), then release that.

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
   (the PR workflow above, which covers `hotfix/*` →
   production under the same value).
