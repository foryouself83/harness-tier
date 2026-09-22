# Daily work

**English** · [한국어](daily-work.ko.md) · [Usage guide](../../USAGE.md)

Every task starts with `/flow`, and every commit it makes goes through `/commit`. `/doc-sync`
and `/prose-review` are the documentation gates `/flow` runs, and you can call them on their own.

## `/flow` — the day-to-day router

```text
/flow <free-text request>
```

The first step of every task that ends in a commit — code or docs. It:

1. **Classifies** the change as Docs or Dev by what it touches: docs, comments and config values
   only → Docs; any source file, dependency or schema → Dev
   ([`rules/risk-tiers.md`](../../rules/risk-tiers.md) holds the full rubric).
2. **Confirms the tier** with you, overridable; when uncertain it proposes the higher tier.
3. **Moves to a work branch.** Already on `feature/*`, `fix/*` or `hotfix/*`, it stays. On an
   integration, staging or production branch it proposes `feature/<slug>` or `fix/<slug>` and
   asks you to confirm — branching from a fresh `origin/<integration>` when the tree is clean,
   or from the current `HEAD` carrying your uncommitted changes.
4. **Writes the `tier` marker** on that branch.
5. **Runs the tier's process**:
   - **Docs** — edit → `/doc-sync` → `/commit`.
   - **Dev** — the `superpowers` pipeline (design → plan → implement → verify) → `/doc-sync` →
     domain review against `review_checklist` and the callers of every changed public symbol →
     `/commit`. The review runs last because an edit voids it.
6. **Merges** by the branch flow's [merge strategy](tiers-and-gates.md#merge-strategy), or opens
   a pull request when `merge_workflow.pull_request` includes `daily`.
7. **Clears the evidence** — after the merge, or after the pull request merges.

Dev needs the `superpowers` plugin; without it `/flow` stops and tells you how to install it.
Skipping `/flow` leaves the commit
[unclassified](troubleshooting.md#blocked-as-an-unclassified-commit).

A promotion — integration → staging, staging → production — is not a `/flow` task. The target
branch decides its tier, and [`/release-commit`](promotion-and-release.md) runs it.

## `/commit` — write and issue one commit

```text
/commit [tier · bump level · what changed]
```

`/flow` and `/release-commit` call it at every commit step. It stages the affected files by name,
picks the Conventional Commits type, checks the 50/72 rule, and issues `git commit`. A
consumer-facing `.md` change is typed `feat` or `fix`, since `docs` and `chore` never produce a
release.

- It reads your `commit_guide` when that file exists
  ([configuration](configuration.md#commit_guide)) and prefers its stack facts.
- A promotion commit carries a `Release-Level:` trailer only in the cases
  [`/release-commit`](promotion-and-release.md#release-commit--run-one-promotion) describes.
- It never passes `--no-verify`, never uses `git add -A`, and never writes a CI-skip marker in
  a message — GitHub reads one anywhere in the head commit and starts no workflow run.

It does **not** classify. A commit made with `/commit` and no `/flow` is still unclassified and
still blocked.

## `/doc-sync` — keep the docs in step

```text
/doc-sync [preview | what changed and why]
```

Reads the change from `git diff` and brings the documentation along:

- **Code → docs** — updates the documents that name the changed classes, fields, routes and
  functions.
- **Docs → docs** — checks cross-references, facts and index entries across the
  `flow-config.doc_sync` targets, and applies the same change to a translation twin such as
  `README.ko.md`. When the sources disagree, code wins over config, config over the index, and
  the index over per-module docs.
- **Wiki** — when `flow-config.wiki` is enabled, refreshes stale `sources` stamps and rebuilds
  `docs/graph/graph.yaml`.
- **Module `CLAUDE.md`** — creates one for a `modules[].path` under `service_docs` that has none,
  once the project has a harness (`docs/code-style/` or a sibling module's `CLAUDE.md`);
  otherwise reports it. An existing file only gets its gaps filled.

After rewriting, it runs `/prose-review` on the files it touched, and on a pass writes the
`doc-sync` evidence marker whoever called it.

It runs in a forked context and does not see your conversation: the argument is the only intent
it receives. An argument that is exactly `preview` plans without changing anything and writes no
marker; a sentence that merely contains the word is a sync request.

## `/prose-review` — check prose against the rules

```text
/prose-review [paths… | empty = the changed files]
```

Checks comments, docstrings and documents against [`rules/doc-style.md`](../../rules/doc-style.md)
and proposes the rewrite.

- **Pattern half** — `doc_style_check.py --lint` over the paths. A repo without the script skips
  this half and keeps the rest.
- **Judgement half** — for each comment, docstring and paragraph: does it explain *how*, could
  the code raise instead, is it self-evident, is a number measured or merely written.
- **Proof** — `doc_style_check.py --verify-git` over the same paths: a Markdown rewrite must keep
  every heading, fenced block, URL and inline-code span, and a `.py` or `.sh` file must keep its
  code byte-identical once comments and docstrings are stripped. A loss is reported, not shipped.

Findings come back in the language you write in. The three box keys `CRITICAL TRAP:`,
`Trigger:` and `Symptom:` stay literal — the checker parses them.
