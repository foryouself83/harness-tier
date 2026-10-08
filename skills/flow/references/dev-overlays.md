# Dev Overlays

The project overlays `/flow` applies on top of the `superpowers` pipeline in the Dev tier, and
the domain review a Staging promotion reuses ([`promotion.md`](../../../rules/promotion.md)).

## Implementation minimalism

Right after the plan, before writing each piece of code, climb this ladder top-down and stop
at the earliest rung that holds:

① does it need to exist (YAGNI) → ② already in this codebase → ③ stdlib → ④ native platform
feature → ⑤ already-installed dependency → ⑥ one line → ⑦ only then the minimum code that works.

- Run the ladder after reading the task and the code it touches, never instead of reading.
- Fix the root cause. Before editing a function, grep every caller: one guard in the shared
  function beats a guard per caller, and patching only the reported path leaves siblings broken.
- It cuts volume, never validation, error handling, security or accessibility. Non-trivial
  logic keeps selective TDD's one-check minimum.
- Mark an intentional simplification with its ceiling and upgrade path.

(Concept from [ponytail](https://github.com/DietrichGebert/ponytail), MIT.)

## Selective TDD

Business logic, core nodes, validators and workflow orchestration only; not every change.

## Domain review

The last gate before commit. The `superpowers` reviews run per task for plan conformance; this
one runs once, at commit, for **coverage**. Dispatch an independent **`general-purpose`** agent
(separate context; it runs shell commands, so not a read-only reviewer type).

① **git is the authority on what changed.** Every path it lists is reviewed, and the count goes
in the report. Take the union of three lists:

```bash
git fetch origin
# A failing term inside the braces contributes nothing while the pipeline still exits 0, so
# probe the branch point first: merge-base fails on a missing ref, a shallow clone and an
# unrelated history alike. Abort here; never review the remainder.
git merge-base "origin/<integration>" HEAD >/dev/null || exit 1
{ git diff --name-only "origin/<integration>...HEAD"   # committed on the branch
  git diff --name-only HEAD                            # staged + unstaged
  git ls-files --others --exclude-standard             # untracked
} | sort -u
```

None subsumes another: the review runs before the commit, so the three-dot form alone lists
nothing new, and `HEAD` alone misses what is already committed on the branch.

At a promotion the tree is clean and both ends are branches. Use the two adjacent
`flow-config.branches` refs, **destination first**, freshly fetched, two dots:
`git diff --name-only "origin/<staging>..origin/<integration>"`. A stale local ref shrinks the
reviewed set; the two-dot form over-reports, which is the safe direction for a coverage gate.

② Judge each file's diff against `flow-config.review_checklist` — regression, cross-service
contract, DB/migration & transactions, async task idempotency & queue routing,
API error conventions.

③ For every changed **public symbol** (signature, schema, event, error contract) find its
callers — `LSP` `incomingCalls` / `findReferences`, else `grep`; say which. Callers only:
dynamic dispatch, DI wiring and HTTP contracts stay with the checklist's cross-service row.

④ Report High + Medium, discard Low, and state the reviewed-file count against ①'s list →
record `review`.

## Evidence invalidation

A `PostToolUse` hook deletes `review.done` **and** `doc-sync.done` the moment a file changes,
the review's own fixes included. Passing is a fixpoint — both recorded, nothing edited since —
so doc-sync runs first and a fix re-runs doc-sync, then the review. An edit the hook never saw
(a terminal command, another tool) leaves the markers standing; delete them by hand:
`rm -f .claude/harness-tier/.flow/review.done .claude/harness-tier/.flow/doc-sync.done`.

`gate_evidence.invalidate_on_edit: false` in `flow-config.yaml` turns the deletion off, and an
edit after the pass then commits under a review that never saw it. `<gate>.done` markers are
not branch-bound, so a task that ends without `/flow`'s cleanup leaves them for whatever runs
next. The hook ships with the plugin, so a version bump arms it with no `/flow-init` step.
Armed is the default: the hook reads `false` under a top-level `gate_evidence:` and nothing
else — `no`/`off`/`False`, or the key under another block, leaves it armed. It reads line by
line, so a file YAML cannot load still disarms on that one line, and a line it cannot make out
leaves it armed.
