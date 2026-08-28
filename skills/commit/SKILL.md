---
name: commit
description: "Use when a commit message has to be written or a commit issued — choosing the Conventional Commits type, drafting the subject and body, staging the affected files, fixing a subject that is too long, or adding the `Release-Level` trailer to a staging promotion. Writing one freehand is where the rules get missed: the 50/72 limit, and the rule that a consumer-facing `.md` must be `feat`/`fix` because `docs` and `chore` never reach a consumer at all. /flow invokes it at each of its commit steps. It does not classify the tier, so it never stands in for /flow on a development request."
argument-hint: "[tier · bump level · what changed]"
---

# Commit — author and issue one commit

**Source of truth**: [`risk-tiers.md`](../../rules/risk-tiers.md) Commit Discipline owns the
message format, the type-to-version table, and the language rule. It is already in context —
the SessionStart hook injects it. This skill does not restate it; it is the procedure that
applies it to one concrete commit.

## Input

- **$ARGUMENTS** — the tier, a hint at what changed, and on a staging promotion the bump
  level (`major`/`minor`/`patch`) that `/flow` asked the user for. The level arrives here or
  not at all: nothing on disk carries it, `.flow/bump.done` being an empty marker. Everything
  else is derivable — with no arguments, read `git status` and the diff.

## Host commit guide (optional, and it wins on stack facts)

`flow-config.commit_guide` names the host's own commit/versioning document — `/harness-init`
generates one at `docs/operations/commit-versioning-guide.md`. When that file exists, read it
and take its **project-specific facts** over this skill's generic ones: the scope vocabulary
this repo actually uses, its 0.x policy, and whether its release tool reads the
`Release-Level` trailer or derives the bump from the commits itself. Its remaining subject —
which files carry the version, how the changelog is filtered — belongs to the release CI, not
to writing a commit.

```bash
guide=$(python3 -c "import pathlib,yaml
p = pathlib.Path('.claude/harness-tier/config/flow-config.yaml')
print((yaml.safe_load(p.read_text(encoding='utf-8')) or {}).get('commit_guide', '') if p.exists() else '')" 2>/dev/null)
if [ -n "$guide" ] && [ -f "$guide" ]; then cat "$guide"; else echo "no host guide"; fi
```

No config, no slot, or no such file → `no host guide`, which is a normal answer, not a
failure: `risk-tiers.md` alone then governs. The `if` is what makes it one — a `&&` chain
exits 1 on the common no-config path and reads as a broken step. The host guide never
relaxes the format either way: the 50/72 rule and the type table stay as written there.

## Step 1 — Stage only what this commit is about

```bash
git status --short
```

Stage the affected paths by name. Never `git add -A` or `git add .` — one unrelated file swept
in makes the subject a lie about the diff, and the gate reads the same staged set you do.
`.claude/harness-tier/.flow/` is gitignored evidence; it never belongs in a commit.

## Step 2 — Pick the type

The type-to-version table in `risk-tiers.md` decides. Two traps it calls out that cost a
release when missed:

- **A consumer-facing `.md` change is `feat` or `fix`, never `docs`.** `docs` and `chore` do not
  bump the version, so they never propagate to a consumer. Only developer-only docs stay `docs`.
- **A squash merge carries the highest-priority type** among the commits it bundles.

## Step 3 — Draft

`type(scope): description`, a blank line, `-` bullets one sentence each, a blank line, footers.
Scope comes from the host guide's vocabulary when it has one, otherwise the module or area the
diff touches. The body says what and why; the commit *is* the history entry, so it carries no
account of earlier rounds of the same work.

## Step 4 — Verify, then issue

One block: a heredoc cannot survive into a second one, and a check the agent runs *after*
committing is a check that changed nothing. On a staging promotion the `Release-Level` trailer
of Step 5 goes **into this heredoc**, below a blank line — this step issues the commit, so a
trailer left for the step after it lands nowhere.

```bash
msg=$(cat <<'EOF'
<type>(<scope>): <subject, replacing this whole heredoc>

- <what changed, and the reason it had to>
EOF
)
python3 -c 'import sys
t = sys.argv[1].splitlines()
bad = ["the heredoc is still the template"] if not t or "<" in t[0] else []
bad += [f"subject is {len(t[0])} chars > 50"] if t and len(t[0]) > 50 else []
bad += [f"line {n} is {len(x)} chars > 72" for n, x in enumerate(t[1:], 2) if len(x) > 72]
if bad:
    sys.exit("REWRITE — " + "; ".join(bad))' "$msg"   && printf '%s
' "$msg" | git -C . commit -F -
```

Three things block here, all in the one block on purpose. A template subject still carrying
`<` aborts — left runnable it would pass the length check, satisfy gitlint, and land as a real
commit. Over 50 means rewrite the subject; `risk-tiers.md` admits no exception, and a non-ASCII
character counts as one, which is what Python's `len` already measures. And `-C` keeps the worktree
inside the command rather than in prose beside it: a bare `git commit` after a separate `cd` can
leave the gate checking the main repo, since `--resolve-worktree` reads the `git -C` the command
actually carries. Write that path **literally** — `.` for the main repo, the worktree's own path
when the work lives in one. A shell variable in the flag's own place is the
trap: the hook is handed the command *before* the shell expands it, and
`precommit-runner.sh`'s self-filters need the token after `git` to start with `-`. A variable
that supplies the flag itself matches neither, so the runner takes the line for something that
is not a commit and every gate behind it is skipped without a word. A variable used as a
flag's *argument* is fine — it is the flag that has to be literal.

The commit prompt itself is deliberately left unapproved — it is the mechanical backstop behind
the tier gate.

## Step 5 — Promotion commits only: the `Release-Level` trailer

The **first** forced staging promotion of a version ends with a blank line and
`Release-Level: <level>`, taking the level from `$ARGUMENTS`. CI reads it to force the bump.

Re-promoting to iterate the **same** rc series takes **no trailer**: `version --<level>` bumps
the base version every time it is applied, so a second trailer turns `X.Y.Z-rc.1` into
`X.Y.(Z+1)-rc.1` and skips `X.Y.Z` as a stable release instead of continuing to `rc.2` — the
auto-derive path is what continues the series
([`risk-tiers.md`](../../rules/risk-tiers.md) Staging). A **production** commit never takes a
level; the finalize step is deterministic.

## Guardrails

1. **Never `--no-verify`.** A blocked commit is the gate working. Read its reason and satisfy
   it; bypassing it is what the gate exists to prevent.
2. **One commit, one subject.** If the staged set needs two subjects, it is two commits.
3. **The merge is not this skill's job.** `/flow` applies the Merge strategy afterwards, and
   several of its rows are hook-enforced.
