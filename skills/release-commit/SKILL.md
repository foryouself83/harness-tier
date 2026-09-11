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
allowed-tools: Bash(grep -c Release-Level .github/workflows/release.yml) Bash(git fetch origin) Bash(mkdir -p .claude/harness-tier/.flow) Bash(touch .claude/harness-tier/.flow/review.done) Bash(touch .claude/harness-tier/.flow/bump.done) Bash(touch .claude/harness-tier/.flow/security.done)
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
  neither, ask the user which promotion this is.

## Which gates need a marker

A promotion is gated at the **commit on the target branch** — the branch drives it, so no tier
marker is written. `precommit`, `security-scan`, `wiki` and `doc-style` are runtime gates the
commit hook runs itself: no marker to write, no skill behind them. The gates needing a recorded
marker are `review` and `bump` (Staging), `security` alone (Release) — Release runs no code
review at all, for the reason [`risk-tiers.md`](../../rules/risk-tiers.md) gives under that
tier.

## Step 0 — Read the host's release model

The bump level reaches CI one of two ways, and the wrong assumption cuts no release candidate
at all. Ask the rendered workflow, not a template list:

```bash
grep -c Release-Level .github/workflows/release.yml
```

**`grep -c` exits 1 on zero matches.** That non-zero exit is the answer "no trailer", not a
failure — do not report it as an error.

- **count >= 1** — the level can be forced. The staging commit carries
  `Release-Level: <level>` and CI forces the bump.
- **count 0** — nothing in this workflow reads the trailer, so the level **cannot** be forced
  and the bump comes from the commit types alone (Node `semantic-release` is the rendered
  case). Say so and skip the level question.
- **no such file** — no release CI is installed. Stop and tell the user to run `/flow-init`.

Whether the file was rendered from a template is not the question — a hand-written
`release.yml` gets the same answer from the same grep, because the subject is the artifact
that runs.

**Cross-check the host commit guide.** `flow-config.commit_guide` (ships as
`docs/operations/commit-versioning-guide.md`) already records which kind the host is on. Read
it when it exists. If it disagrees with the grep, **the workflow wins** — and report the
disagreement in one line, because it means the guide has gone stale. No guide is a normal
answer, not a failure.

**No workflow here takes the level from a `workflow_dispatch`.** The sister plugin vway-kit
does; this one does not. Never trigger one to force a level — it forces nothing and the
promotion silently produces no rc.

## Step 1 — Staging (integration → staging)

**1. Regression review.** An independent **`general-purpose`** agent (separate context, runs
its own shell commands), judged against `flow-config.review_checklist` plus the callers of
every changed public symbol. A promotion starts on a clean working tree, so the file list
comes from this promotion's own pair rather than from the workspace:

```bash
git fetch origin
git diff --name-only "origin/<staging>..origin/<integration>"
```

Use the freshly fetched `origin/` refs — a stale local ref shrinks the reviewed set with no
sign that it did. Two dots, not three: `git diff` reads that as a two-endpoint diff, so a
commit sitting on staging alone still surfaces — inverted, as a deletion this merge will not
make. Staging is the only promotion that reviews at all; Release has no pair to carry this
one into.

**2. Compute a recommended level.** Two inputs:

- The commit-derived level over the promoted range — the type-to-version mapping lives in
  [`risk-tiers.md`](../../rules/risk-tiers.md) Commit type → version impact. Where the release
  tool derives its own bump, `semantic-release version --print` prints the **version** it would
  pick (best effort); compare it against the current version to read off major/minor/patch.
- The host commit guide's 0.x policy: `major_on_zero=false`, and `1.0.0` only by an explicit
  decision. With no guide, the first input alone is the recommendation — a normal path.

**3. Ask the user — where Step 0 answered `count >= 1`.** `AskUserQuestion` with
**major / minor / patch**, defaulting to the recommendation. The recommendation never stands in
for the answer: **always ask.** When the current version is `0.x` and the choice is `major`,
warn that it jumps straight to `1.0.0`.

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

**6. Merge integration into staging, leaving the commit unwritten:**

```bash
git merge --no-ff --no-commit origin/<integration>
```

**7. Write that pending merge** through `Skill: commit`, **passing the chosen level in the
arguments** where item 3 asked for one. That is the only channel it has: `bump.done` is an
empty marker and nothing on disk carries the level. The commit skill appends the trailer
`Release-Level: <level>`, which CI reads to force
`semantic-release version --<level> --as-prerelease`, and gives the commit the subject a
promotion merge takes — `Merge <integration>: <headline>`, capital `Merge`, no Conventional
type ([`promotion.md`](../../rules/promotion.md) Merge commit messages).

On a **count 0** host pass no level, and the commit takes no trailer: nothing reads one, and a
trailer written where nothing reads it is a promise the release does not keep. Same subject
form, same order.

**Merge before commit, never after.** CI reads `git log -1` alone, so the trailer has to land
**on HEAD**: written first and merged after, it sits one commit back, the run finds no trailer
and auto-derives the bump with nothing to say it did.

**A run that stops at the rc goes to End state from here** — the ordinary case, with the
release following days later. `bump.done` outlives it otherwise: the PostToolUse hook deletes
the `review` and `doc-sync` markers only, and `/flow` Phase 4 leaves a promotion's markers to
this skill.

## Step 2 — Release (staging → production)

**1. Fetch first, and confirm staging carries the rc.**

```bash
git fetch origin
```

`origin/<staging>` must sit at `X.Y.Z-rc.N` — the version bump the rc CI pushed. Merging
before it lands leaves the finalize step with no pending rc to strip; it falls back to plain
compute and the forced level is gone.

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

**4. Merge the freshly fetched staging into production, leaving the commit unwritten:**

```bash
git merge --no-ff --no-commit origin/<staging>
```

**5. Write that pending merge** through `Skill: commit` — **no level here.** Finalize is
deterministic: it strips the rc token off the version staging already carries. Same subject
form as Staging (`Merge <staging>: <headline>`), and the same fixed order, for the same
reason: HEAD is the only commit CI reads.

Deploy is project-specific and not gated; the production-branch commit is the gate.

## PR-mode promotion

When `flow-config.merge_workflow.pull_request` includes `promotion`, the merge moves to a pull
request and the hook stops seeing it. Gate recording is unchanged — every marker above is
still written on the local commit.

- The PR **must** land as a **merge commit**. A rebase stops the release; a squash destroys the
  history semantic-release reads.
- With a forced level, pin the trailer in the merge command. `PR` is a literal number: written
  as `<n>`, bash reads `<n` as a redirection and eats the next word.

  ```bash
  PR=123
  gh pr merge "$PR" --merge --subject "Merge <staging>: release X.Y.Z" --body "Release-Level: <level>"
  ```

- A **`hotfix/*` → production** landing is a PR under this mode too — the production ruleset
  governs every merge into that branch and rejects the local squash-and-push.

## When the `wiki` gate blocks the promotion commit

`doc-sync` is the only thing that rebuilds `graph.yaml`, and it is not a promotion gate — so
graph drift that reached the integration branch through a terminal commit surfaces here, as a
blocked promotion commit. Resolve it in place:

```bash
python3 .claude/harness-tier/scripts/wiki_graph.py --build
```

Stage the rebuilt `graph.yaml` into the promotion commit. A failure naming a **structure**
violation instead — `wiki_id` format or duplicate, missing `title`, dangling `depends_on`, a
cycle, front matter that carries a `wiki_id` and does not parse — is a document's front matter
to fix; `--build` cannot resolve those.

## End state

**Both promotions end here**, a run that stopped at the rc included. The back-merge is
Release's alone; the marker clearing is every run's.

**Back-merge production → integration (Release). Not optional.** Once the finalize CI has
pushed its `chore(release)` version-bump and marketplace-sha-pin commits to production:

```bash
git fetch origin
git switch <integration> && git merge --ff-only origin/<production>
git push origin <integration>
```

Fast-forward when the branch is strictly behind, else `--no-ff`. Skipping this leaves the
released tag unreachable from integration, and the next version is computed wrong.

**Then staging, `--ff-only` and nothing else:**

```bash
git switch <staging> && git merge --ff-only origin/<production>
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
rm -f .claude/harness-tier/.flow/review.done .claude/harness-tier/.flow/bump.done .claude/harness-tier/.flow/security.done
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

A promotion versions **the whole repository at one version**. Multiple modules are first-class
in gates, tests and deployment (`modules[]`, `unit_test.jobs[]`, a `deploy-<name>.yml` per
target), but the `versioning` block is singular and has no slot for a per-service version — a
backend and a frontend in one repo work correctly on lockstep versions with per-target deploys.
Do not read `versioning.version_files` as evidence of anything: no script and no workflow reads
that slot, and what stamps a version into a file is the release tool's own configuration.

## Never

- **Never force a level through a `workflow_dispatch`** — no workflow here reads one.
- **Never put `[skip ci]` in a promotion merge.**
- **Re-promote without the trailer.** `version --<level>` bumps the base every time it is
  applied, so a second forced promotion takes `X.Y.Z-rc.1` → `X.Y.(Z+1)-rc.1` and skips
  `X.Y.Z` as a stable release. To continue the rc series on the same target version, drop the
  trailer and let the auto-derive path run.
- **Never spell a `git merge` flag through a variable.** The commit hook reads the command
  text unexpanded, so a variable where a flag belongs makes it read "not a merge" and every
  merge-strategy check switches off in silence (CLAUDE.md Invariant 7).
