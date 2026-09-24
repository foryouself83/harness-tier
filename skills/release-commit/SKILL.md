---
name: release-commit
description: >-
  Use when a branch is promoted toward a release — dev/integration to stage/staging, stage to
  main/production — or a release candidate is cut or finalized, including bare asks like
  "stage로 올려줘", "릴리즈 해", "main 승격", "promote to main", "cut an rc". Use it before
  answering a question about this repo's promotions too: whether the bump level is forced by a
  Release-Level commit trailer or a workflow dispatch, whether a re-promotion takes the trailer
  again, why a promotion produced no release candidate, or the back-merge after a release. An
  answer from generic git-flow habit is where a release breaks unseen — the wrong merge shape,
  a trailer off HEAD or a `[skip ci]` cuts no rc, and nothing reports it. /flow hands every
  promotion here; /commit only writes the message this skill decides. Not for installing
  release CI (/flow-init).
argument-hint: "[staging | release]"
# Every rule below matches a command spelled out in the body — a rule matching nothing grants
# nothing (tests/skills/test_gate_reachability.py). Exact marker paths, no trailing glob: a
# glob's `*` crosses path separators including `..`. `git commit` and `git merge` are
# deliberately absent — the commit prompt is the mechanical backstop behind the gate, and this
# skill's whole subject is which merge shape the release CI needs.
allowed-tools: Bash(grep -c Release-Level .github/workflows/release.yml) Bash(grep -c next-version .github/workflows/release.yml) Bash(git fetch origin) Bash(git fetch --tags origin) Bash(python3 .claude/harness-tier/scripts/bump_version.py state) Bash(python3 .claude/harness-tier/scripts/changelog_section.py pending) Bash(mkdir -p .claude/harness-tier/.flow) Bash(touch .claude/harness-tier/.flow/review.done) Bash(touch .claude/harness-tier/.flow/bump.done) Bash(touch .claude/harness-tier/.flow/security.done)
---

# Release Commit — integration → staging → production

One promotion end to end: the gates it records, the commit that carries the bump level, the
merge the release CI needs, and the back-merge that closes the cycle.

**Source of truth**: [`merge-strategy.md`](../../rules/merge-strategy.md) owns Merge
strategy; [`risk-tiers.md`](../../rules/risk-tiers.md) owns Commit
Discipline and the gate glossary, and the SessionStart hook injects it, so that half is already
in context. PR workflow, Merge commit messages and Back-merge after release sit in
[`promotion.md`](../../rules/promotion.md), which **nothing injects — read it before running a
promotion**. This skill is the procedure that applies both and does not restate them. Where a
rule file and this skill disagree, follow the rule file and tell the user this skill has
drifted. [`flow-tiers.yaml`](../../flow-tiers.yaml) carries the per-tier
gate list the commit hook enforces — read it, nothing injects it.

Branch names come from `flow-config.branches` (`integration` / `staging` / `production`).

## Input

- **$ARGUMENTS** — `staging` (integration → staging) or `release` (staging → production). With
  neither, ask the user which promotion this is. A `hotfix/*` branch `/flow` hands over takes
  neither: it runs [`references/hotfix.md`](references/hotfix.md).

Three more procedures sit in `references/`, each read only when it applies:
[`changelog.md`](references/changelog.md) at Step 2 item 5,
[`pr-mode.md`](references/pr-mode.md) when `flow-config.merge_workflow.pull_request` names
`promotion` or `daily`, and [`wiki-gate.md`](references/wiki-gate.md) when the `wiki` gate
blocks a promotion commit.

## Which gates need a marker

A promotion is gated at the **commit on the target branch** — the branch drives it, so no tier
marker is written. `precommit`, `security-scan`, `wiki` and `doc-style` are runtime gates the
commit hook runs itself: no marker to write, no skill behind them. The gates needing a recorded
marker are `review` and `bump` (Staging), `security` alone (Release) — Release runs no code
review at all, for the reason [`promotion.md`](../../rules/promotion.md) gives under
Release.

## Step 0 — Read the host's release model

The bump level reaches CI one of two ways, and the wrong assumption cuts no release candidate
at all. Ask the rendered workflow, not a template list:

```bash
grep -c Release-Level .github/workflows/release.yml
grep -c next-version .github/workflows/release.yml
```

**`grep -c` exits 1 on zero matches.** That non-zero exit is an answer — "no trailer", "no
shared next-version block" — not a failure; do not report it as an error.

- **count >= 1** — the level can be forced. Every template `/flow-init` renders lands here —
  python-semantic-release, Node semantic-release, jreleaser, gitversion, cargo-release. The
  staging commit carries `Release-Level: <choice>` and CI applies it.
- **count >= 1, `next-version` count 0** — a **legacy render**, older than the shared
  next-version block, that `/flow-init` never overwrites: `major | minor | patch` alone, no
  finalize guard. Warn once, follow items 3 and 7's legacy lines, and tell the user to delete
  `.github/workflows/release.yml` and re-run `/flow-init`.
- **count 0** — a hand-written workflow that reads no trailer, so the level **cannot** be
  forced and the bump is whatever that workflow derives. Say so and skip the level question.
- **no such file** — no release CI is installed. Stop and tell the user to run `/flow-init`.

**Cross-check the host commit guide** (`flow-config.commit_guide`, ships as
`docs/operations/commit-versioning-guide.md`): where it disagrees with the grep, **the
workflow wins** — report the stale guide in one line. No guide is a normal answer.

## Step 1 — Staging (integration → staging)

**Read the release state first** — the code the release CI runs, over the same tag list:

```bash
git fetch --tags origin
python3 .claude/harness-tier/scripts/bump_version.py state
```

`pending:` names the **pending rc**: the highest `vX.Y.Z-rc.N` whose base `X.Y.Z` has no
stable tag and sits above the highest stable tag. `pending: none`, with
`continue: fails — … no pending rc to continue`, is the answer "no pending rc", not an error.
The four level lines are the versions item 3 labels its options with. `invalid choice: 'state'`
means the host copy predates it: tell the user to re-run `/flow-init`. Keep the `pending:`
line: item 8 compares against it. Never read the pending rc off `git describe`: it follows one
branch's ancestry, and a staging whose release back-merge refused the fast-forward still sits
on the rc that release shipped.

**A pending rc makes this a re-promotion: back-merge staging first.** Integration takes
staging's rc version commit before the review, so the review reads the pair after it.
Fast-forward when integration is strictly behind:

```bash
git switch <integration> && git merge --ff-only origin/<integration>
git merge --ff-only origin/<staging>
```

A refused fast-forward takes a merge commit instead — the row
[`merge-strategy.md`](../../rules/merge-strategy.md) gives this back-merge:

```bash
git merge --no-ff origin/<staging>
```

Either way, push it before the review reads `origin/<integration>`:

```bash
git push origin <integration>
```

No pending rc skips the back-merge.

**1. Regression review.** An independent **`general-purpose`** agent (separate context, runs
its own shell commands), judged against `flow-config.review_checklist` plus the callers of
every changed public symbol. A promotion starts on a clean working tree, so the file list
comes from this promotion's own pair rather than from the workspace:

```bash
git fetch origin
git diff --name-only "origin/<staging>..origin/<integration>"
```

Freshly fetched `origin/` refs — a stale local ref shrinks the reviewed set in silence. Two
dots, not three: a commit on staging alone still surfaces, inverted, as a deletion. Staging
is the only promotion that reviews at all.

**2. Compute a recommended level** from the commit types over the promoted range
([`risk-tiers.md`](../../rules/risk-tiers.md) Commit type → version impact; where the tool
derives its own bump, `semantic-release version --print` shows its pick, best effort), under
the host guide's 0.x policy: `major_on_zero=false`, `1.0.0` only by an explicit decision.

**3. Ask the user — where Step 0 answered `count >= 1`.** `AskUserQuestion`, every option
labelled with the version the release-state block printed for it. The recommendation never
stands in for the answer: **always ask.**

- **No pending rc** — **auto / patch / minor / major**, defaulting to the recommendation.
  `auto` leaves the level to the release tool: label it "commit-derived", with the level item 2
  read off when it read one. Where the workflow sets `AUTO_LEVEL: patch` (the gitversion and
  jreleaser templates — those tools derive nothing), `auto` is `patch`: label it with that
  version.
- **Pending rc** — **continue / patch / minor / major**, `continue` first and recommended: it
  cuts the next rc of the same base, `1.1.0-rc.2` → `1.1.0-rc.3`. A forced level bumps the base
  again and skips `X.Y.Z` as a stable release (`patch` → `1.1.1-rc.1`); say so in each forced
  option's description. `auto` is not offered: `continue` names the outcome rather than leaving
  it to the tool.

When the current version is `0.x` and the choice is `major`, warn that it jumps straight to
`1.0.0`.

On a **legacy** host (Step 0) a first promotion offers **patch / minor / major** alone, and
a re-promotion asks nothing: that workflow's no-trailer path continues the rc series, while a
forced level there bumps the base again.

On a **count 0** host, skip it: no workflow reads the trailer, so the answer would change
nothing and the bump is whatever the commit types derive. Item 5 still records `bump.done` —
the gate is fail-closed on that file, and the recommendation is what the promotion reports.

**4. Warn if the release token cannot push (best effort, never blocks).** With `gh` or a token
available:

```bash
.claude/harness-tier/scripts/check-token-write.sh
```

Exit 10 → warn, with the Settings/PAT how-to. Exit 20, or no tool at all → skip silently.

**5. Record the markers**, one command per line — a brace form matches neither the exact
`allowed-tools` rules nor a reader's eye:

```bash
mkdir -p .claude/harness-tier/.flow
touch .claude/harness-tier/.flow/review.done
touch .claude/harness-tier/.flow/bump.done
```

**6. Merge integration into staging, leaving the commit unwritten.** Start on an up-to-date
staging — a re-promotion's back-merge left HEAD on integration:

```bash
git switch <staging> && git merge --ff-only origin/<staging>
git merge --no-ff --no-commit origin/<integration>
```

**7. Write that pending merge** through `Skill: commit`, **passing the chosen level in the
arguments** where item 3 asked for one. That is the only channel it has: `bump.done` is an
empty marker and nothing on disk carries the level. The commit skill appends
`Release-Level: <choice>` — every choice written out, `auto` included: an absent trailer runs
as `auto` too, but only a written one records that the level was asked. It gives the commit
the subject a promotion merge takes — `Merge <integration>: <headline>`, capital `Merge`, no
Conventional type ([`promotion.md`](../../rules/promotion.md) Merge commit messages).

CI reads the trailer off HEAD: `auto` hands the bump to the release tool, any other choice
becomes the version the release-state block printed for it. A value outside
`auto | continue | patch | minor | major`, an empty one, two different ones, or `continue`
with no pending rc **fails the release run** — nothing falls back to a derived bump.

On a **count 0** host, and on a **legacy** re-promotion, pass no level, and the commit takes
no trailer: a trailer written where nothing reads it is a promise the release does not keep.
Same subject form, same order.

**Merge before commit, never after.** CI reads `git log -1` alone, so the trailer has to land
**on HEAD**: written first and merged after, it sits one commit back, and the run reads `auto`
with nothing to say it did.

**8. Push, then confirm the rc was cut** — on every host, count 0 included:

```bash
git push origin <staging>
```

Wait for the release run on that push, then read the release state again:

```bash
git fetch --tags origin
python3 .claude/harness-tier/scripts/bump_version.py state
```

The rc was cut when `pending:` names `v` plus the version the chosen option was labelled
with — the `continue` line's on a legacy re-promotion, and for `auto` or a count 0 host any rc
other than the first read's `pending:`. The same line, `none` or a failed run: **no rc was cut
and the promotion is not finished** — report it and stop. Under PR mode, check after the merge
([`pr-mode.md`](references/pr-mode.md)).

**A run that stops at the rc goes to End state from here** — the ordinary case. `bump.done`
outlives it otherwise: the PostToolUse hook deletes the `review` and `doc-sync` markers only,
and `/flow` Phase 4 leaves a promotion's markers to this skill.

## Step 2 — Release (staging → production)

**1. Fetch first, and confirm staging carries a pending rc.**

```bash
git fetch --tags origin
python3 .claude/harness-tier/scripts/bump_version.py state
```

`origin/<staging>` must sit at the `X.Y.Z-rc.N` the rc CI pushed — merged before it lands,
finalize has no rc to strip and falls back to plain compute, losing the forced level — and
`pending:` must name that rc. `none` or another rc means a hotfix shipped `X.Y.Z` or a higher
base first, and finalize fails the run before writing anything:
`vX.Y.Z already exists — a hotfix shipped this base`, or `vX.Y.Z is below the latest release`.
Stop, and re-promote staging through Step 1 choosing `patch` or higher. A release run failing
with either error means the same thing.

**2. Security review** — `/security-review` over this promotion. It is the only review layer
here; do not add a code-review pass back.

**3. Record the marker:**

```bash
mkdir -p .claude/harness-tier/.flow
touch .claude/harness-tier/.flow/security.done
```

One marker, not two. A `review.done` sitting here is **Staging's**, left behind by a run that
stopped at the rc — clear it (the End state's `rm -f` covers it) rather than reading it as
evidence for anything on this tier.

**4. Merge the freshly fetched staging into production, leaving the commit unwritten,**
starting on an up-to-date production:

```bash
git switch <production> && git merge --ff-only origin/<production>
git merge --no-ff --no-commit origin/<staging>
```

**5. Write the stable changelog section** into the open merge —
[`references/changelog.md`](references/changelog.md): a deduplicated summary of every rc this
release folds in, approved by the user, which the release CI publishes as the release notes.

**6. Write that pending merge** through `Skill: commit` — **no level here.** Finalize is
deterministic: it strips the rc token off the version staging already carries. Same subject
form as Staging (`Merge <staging>: <headline>`), and the same fixed order, for the same
reason: HEAD is the only commit CI reads. Then push — this is what fires finalize:

```bash
git push origin <production>
```

Deploy is project-specific and not gated; the production-branch commit is the gate.

## End state

**Both promotions end here**, a run that stopped at the rc included, and so does a hotfix. The
back-merge follows a release alone — Release's or a hotfix's; the marker clearing is every
run's.

**Back-merge production → integration (Release). Not optional.** Once the finalize CI has
pushed its `chore(release)` version-bump and marketplace-sha-pin commits to production:

```bash
git fetch origin
git switch <integration> && git merge --ff-only origin/<integration>
git merge --ff-only origin/<production>
git push origin <integration>
```

Fast-forward when the branch is strictly behind, else `--no-ff`. Skipping this leaves the
released tag unreachable from integration, and the next version is computed wrong.

**Then staging, `--ff-only` and nothing else:**

```bash
git switch <staging> && git merge --ff-only origin/<staging>
git merge --ff-only origin/<production>
git push origin <staging>
```

**A refused fast-forward ends that step — never `--no-ff`** (failure mode 4). Skip it and say
so in the run's own output; the next integration → staging promotion carries the release
commits forward on its own. Under PR mode the ruleset rejects the **push** instead, once the
merge has already moved local `<staging>`: that is a finish too — leave the ref where it stands
and `git switch -`. Rationale in [`promotion.md`](../../rules/promotion.md) Back-merge after
release.

**Clear the promotion's evidence markers**, whichever this run recorded — `rm -f` is silent on
the ones it did not. The commit hook is fail-closed on them: it **blocks** the promotion commit
until each marker its tier requires exists. That is what makes a marker a forcing function
rather than a stamp — and what makes one left behind read to the *next* promotion as its own
passing evidence. A run that ended at Staging is where that bites: nothing else deletes
`bump.done`, so the next rc satisfies its fail-closed `bump` gate with no one choosing a level.

```bash
rm -f .claude/harness-tier/.flow/review.done .claude/harness-tier/.flow/bump.done .claude/harness-tier/.flow/security.done .claude/harness-tier/.flow/release-notes.md
```

Deleting evidence stays a deliberate prompt: no `allowed-tools` rule covers that `rm`. Under
PR mode, clear only after the PR is merged — a review-feedback commit pushed to that branch is
gated exactly like the first one, and the gate reads whether each marker file exists, so
clearing early leaves that commit blocked.

## Failure modes

Each of these produces a release that looks finished and is not.

1. **`[skip ci]` in the promotion merge message** — the release job never runs, so there is no
   rc at all and nothing downstream reports a problem.
2. **Merging a stale local staging ref** instead of the fetched `origin/<staging>` — finalize
   sees no pending rc, falls back to plain compute, and the forced level is lost (`0.2.0`
   where `0.1.2` was chosen).
3. **A skipped production → integration back-merge** — the released tag is unreachable from
   integration and the next version is miscomputed.
4. **Taking `--no-ff` when staging's back-merge refuses the fast-forward** — the merge commit
   carries no `[skip ci]`, and the release workflow fires on a push to staging, so it cuts an
   rc nobody promoted. A refused fast-forward is a skip, not a fallback; the next
   integration → staging promotion carries the release commits forward.
5. **Running `finalize_prerelease.py` locally** — it **writes** the version into
   `pyproject.toml` and `.claude-plugin/plugin.json`. It is not a read-only probe, and CI is
   the only thing that runs it.
6. **Leaving the evidence markers in place** — the next promotion reads someone else's
   `review.done`, `bump.done` and `security.done` as its own pass.

## Monorepo / multi-service

A promotion versions **the whole repository at one version**: modules are first-class in gates,
tests and per-target deploys, on lockstep versions. `versioning` has no per-service slot, and
nothing reads `versioning.version_files` — the release tool's own config stamps a version.

## Never

- **Never force a level through a `workflow_dispatch`** — no workflow here reads one (the
  sister plugin vway-kit's does): it forces nothing, and the promotion cuts no rc.
- **Never put `[skip ci]` in a promotion merge.**
- **Never offer a forced level as the way to fold a follow-up into a pending rc.** `continue`
  is that option; `patch`/`minor`/`major` there bump the base again and skip `X.Y.Z` as a
  stable release, so they are the user's explicit choice, never the default.
- **Never leave the trailer off a `count >= 1` promotion** but a legacy re-promotion. Write
  the choice, `auto` included, spelled exactly: a value outside the five fails the run.
- **Never spell a `git merge` flag through a variable.** The commit hook reads the command
  text unexpanded, so a variable where a flag belongs makes it read "not a merge" and every
  merge-strategy check switches off in silence (CLAUDE.md Invariant 7).
