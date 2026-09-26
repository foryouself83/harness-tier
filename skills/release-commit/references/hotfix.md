# Hotfix (hotfix/* → production)

> Read when `/flow` hands a `hotfix/*` branch to `/release-commit`.

A hotfix reaches production without passing through staging or
[`SKILL.md`](../SKILL.md) Step 2, and still ships a release — so End state's back-merge is
owed after it too. `/flow` hands a `hotfix/*` branch here once its Dev-tier commit is on the
branch. "End state" below is [`SKILL.md`](../SKILL.md#end-state)'s.

**1. Record the baseline before merging** — production's current tag, which item 4 compares
against, and the `pending:` line of the release-state probe, which item 6 compares against:

```bash
git fetch --tags origin
git describe --tags --abbrev=0 origin/<production>
python3 .claude/harness-tier/scripts/bump_version.py state
```

Write both into the run's output literally, as `before: vX.Y.Z` and the `pending:` line —
each Bash call is a fresh shell, so a variable holding them is gone by item 4.

**2. Security review, then the marker.** The squash commit lands on production, so the commit
hook gates it as Release: `/security-review` over the hotfix branch's changes, then

```bash
mkdir -p .claude/harness-tier/.flow
touch .claude/harness-tier/.flow/security.done
```

**3. Squash the hotfix into production** —
[`merge-strategy.md`](../../../rules/merge-strategy.md) row 5; the hook blocks this merge
without `--squash`:

```bash
git switch <production> && git merge --ff-only origin/<production>
git merge --squash hotfix/<name>
```

Write it through `Skill: commit` as a `fix:` commit — not a `Merge` subject, and never
`[skip ci]`: this commit is what fires the release workflow and what the release tool reads a
patch from. Then push:

```bash
git push origin <production>
```

Under `promotion` PR mode the production ruleset rejects that local path: open a PR from the
hotfix branch and merge it with "Create a merge commit" instead
([`promotion.md`](../../../rules/promotion.md) PR workflow). Items 4 to 6 run once it merges.

**4. Confirm the release shipped.** Wait for the release run on that push, then read production's
tag again — the `after` value:

```bash
git fetch --tags origin
git describe --tags --abbrev=0 origin/<production>
```

The release shipped when this `after` value is a stable `vX.Y.Z` — no `-rc.` — and differs
from item 1's `before`. `after` equal to `before` means the run has not finished or has
failed; the back-merge waits for it, because what it carries is that run's `chore(release)`
commits.

**5. Back-merge**, both steps of End state with its commands as written there: production →
integration, fast-forward else `--no-ff`, not optional; then production → staging,
`--ff-only` alone, a refused fast-forward skipped and reported. An integration that took a
re-promotion back-merge carries the rc version, so the version files conflict: keep
integration's rc version lines.

**6. Tell the user when the hotfix overtook the pending rc.** When item 1 recorded
`pending: vX.Y.Z-rc.N` and item 4's `after` is `vX.Y.Z` — the same base — or higher, that
rc can no longer be released. The finalize step fails its release run, printing (for a higher
one, `is below the latest release`):

```text
::error::vX.Y.Z already exists — a hotfix shipped this base. Re-promote staging with Release-Level: patch (or higher) before releasing.
```

It is no longer pending either, so `continue` fails too. The next integration → staging
promotion must choose `patch` or higher (`1.1.1-rc.1` behind a shipped `1.1.1` →
`1.1.2-rc.1`). Any other answer needs nothing further.

**7. Clear the markers** with End state's `rm -f`.
