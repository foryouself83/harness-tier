# Gate Mechanics

> Read when a gate blocked, or when wiring `flow-config`. Not injected into the session
> context — [`risk-tiers.md`](risk-tiers.md) is, and its glossary points here.

## `wiki`

Neither a timing bucket nor a module check: the hook's gate script runs it in-process as its
final stage, plus a new blocking rule: a commit whose only change to a node is its `sources` sha
(no body edit) is rejected — [`doc-sync`](../skills/doc-sync/SKILL.md) Mode W owns that stamp.
When `flow-config.wiki` is enabled it verifies, read-only, that `graph.yaml` still matches the
docs' front matter and that no structural rule is broken. It runs on **every tier including
`docs`** — a docs commit is exactly when the graph drifts. No wiki configured (absent · `enable:
false` · missing root) → nothing runs, so a repo without a wiki never notices this gate. The
graph is **built** by `/doc-sync` or `/wiki-init`, never by the hook and never by CI, and it is
built from **git's index** — `git add` is what admits a document to the wiki, so stage new
documents before building. Only a real verification failure blocks; an internal error passes
(Invariant #1) — including a git that cannot list its own index, where the node set falls back
to the filesystem and would otherwise count the very files git hides. Its non-blocking quality
warnings — orphans, over-size documents, `sources` paths that are not on disk, an `sds` document
whose `sources` key is absent or has no value, defect→rule promotion, front matter that fails to
parse without a `wiki_id:` line, a wiki-only field (`related`/`depends_on`/`affects`/`sources`)
present without a `wiki_id` — come back as a `systemMessage` on a passing commit, each kind
capped at three entries plus a count. A defect node's `regression_test` / `promoted_to_rule`
path is the one file reference that *does* block when it is missing, unlike `sources`: those two
assert a tracked repository artifact exists, and both the fix and the escape hatch are one edit
in the document, whereas a `sources` entry may legitimately name a generated or gitignored file
that no edit can conjure. Two things it cannot see. It reads the **working tree**, because the
hook fires before `git commit` stages anything — so `graph.yaml` must be staged with the
documents it was built from, or the commit records new front matter beside the old graph and
nothing catches it until the next session commit. And on a **promotion** (Staging / Release) no
gate rebuilds the graph — `doc-sync` is not a promotion gate — so a drift that arrived via a
terminal commit surfaces here as a blocked promotion: run
`python3 .claude/harness-tier/scripts/wiki_graph.py --build` and include the result in the
promotion commit.

## `doc-style`

The prose gate, the other in-process stage. When `flow-config.doc_style` is enabled it lints the
files this commit changes that its `paths`/`exclude` globs put in scope (default `**/*.md`; name
`**/*.py`·`**/*.sh` to cover comments and docstrings) against [`doc-style.md`](doc-style.md) and
reports what it finds as a `systemMessage`. Scope is read by the same function CI's
`--lint-config` uses, so an `exclude` holds in both arms. It **never blocks**: the verdict
belongs to
`doc-style.yml` in CI, which sees the whole tree, where a rule tightening cannot deny a commit
nobody could predict. One flag drives both arms: `/flow-init` renders that workflow only when
`enable` is true, so turning it off does not leave the lighter of two checks — it leaves the
rule written down and enforced nowhere. No `doc_style` block, `enable: false`, or any internal
error → nothing runs (Invariant #1). Runs on every tier including `docs`.

## Host custom checks

Hosts add their own runtime checks by putting extra keys under `flow-config.modules[].checks` —
a command string (timing defaults by key name: `security` → promotion, else every-commit) or `{
run, when }` to set timing explicitly (use `when`, not `on` — YAML reads a bare `on` key as a
boolean). **Timing is bound to that bucket's gate existing in the tier**: the `docs` tier has
neither *bucket* gate, so host custom checks never run on a docs commit — the module pre-check
short-circuits there. (`wiki`·`doc-style` still run on a docs commit; neither is a module check
and neither enters that path.) `precommit` and `security-scan` are ordinary entries in each
tier's `flow-tiers.yaml` `gates` list, so **removing one disables that whole bucket** for that
tier (the gates list is the single on/off switch, not a hardcoded branch). Like all layer-2
checks these run **only on Claude-session commits** — terminal/CI commits are not gated (add a
CI safety net if you need hard enforcement).

## Enforcement properties

- **Fail-open on errors** — missing/unparseable policy or config, or
  any internal error → the action is allowed (a broken gate never bricks
  commits or deploys). The test is "the gate works reliably", not "a
  file exists". The unclassified-commit block in [`risk-tiers.md`](risk-tiers.md) Hard gates
  is the exception —
  it is what stops a skipped `/flow` from silently disabling the gate —
  and promotion gates are likewise fail-*closed* on missing evidence.
  Both still fail open on an internal error.
- **Branch-bound** — markers carry the branch, so stale state cannot
  block an unrelated task on another branch.
- The four runtime gates — `precommit`, `security-scan`, `wiki`, `doc-style` — are run
  by the hook rather than recorded as markers; layer 2, not the layer-1 pre-commit
  (Gate glossary).
- Judgment gates (review quality, human integration test) can only be
  *recorded*, not verified.
- **Air-gapped limit** — an offline production machine runs on a
  separate host a local hook cannot reach; the staging → production
  commit is the local release-authorization gate.

Clear state with `rm -rf .claude/harness-tier/.flow`, which is what `/flow` does after a
successful commit/merge. `/release-commit` deletes its three promotion markers by name at its
end state instead, so a `doc-sync.done` earned by day-to-day work survives the promotion.

---

*Pilot: Docs & Dev enforced at commit; Staging at integration → staging, Release at staging →
production / offline deploy. `/release-commit` runs the Staging and Release pipelines end to
end; one-shot `/flow` automation of the Dev pipeline is a follow-up.*