---
name: wiki-init
description: Set up an LLM Wiki in this repo — migrate existing docs into one-concept-per-file nodes with YAML front matter, then build the knowledge graph. Idempotent, incremental on re-run.
disable-model-invocation: true
---

# Wiki-Init — LLM Wiki Setup Wizard

Migrates existing docs into wiki nodes and builds `graph.yaml`. No embeddings —
relationships are written by hand in front matter, and the graph mechanically reads
them.

**Precondition**: `.claude/harness-tier/config/flow-config.yaml` must exist. If it
doesn't, tell the user to run [`/flow-init`](../flow-init/SKILL.md) first and
**stop**.

Re-running is incremental. Documents that already carry a `wiki_id` are left
untouched.

## 1. Confirm the wiki root

Confirm via `AskUserQuestion`. Default is `docs/` — keeping it in the same tree as
`/harness-init`'s output keeps the doc set unified.

## 2. Scan

Walk the `.md` files under root and build a migration-candidate table. Each row is:
file path · line count · H2 count · whether the front matter carries a `wiki_id`. A high
line count with multiple H2s is a **signal** of multiple concepts, not a verdict — an
Installation/Usage/FAQ page is several H2s and still one concept; the boundary is judged
by content in Step 4. A row
whose front matter has a `wiki_id` is already a wiki node — keep it in the table for
context, but it is not a migration candidate.

**`wiki_id` is the node marker — not the `---` block, and not `id`.** A doc site's own
metadata (MkDocs · Docusaurus · Jekyll: `id`, `sidebar_position`, `slug`, `layout`, …) is
front matter too, and `id` in particular is a documented first-class field in several of
them — which is why the wiki does not use it. Those files are *not* nodes; validation
ignores them. They are ordinary migration candidates: merge the wiki fields into the
existing block rather than adding a second one, and leave their `id` alone.

## 3. Select

The candidate list offers only documents **without a `wiki_id`** — a document that already
has one is already a node and is never re-offered, on this run or any later one. That is
what makes re-running incremental. Let the user pick which of the remaining documents to
migrate. If there are many candidates, ask in batches. Documents not chosen are left
as-is — without a `wiki_id` they sit outside the wiki and are not subject to validation.

## 4. Split

Branch on the H2 count recorded in Step 2:

- **Zero H2s** — nothing to split. The document becomes one node as-is: add
  front matter to it directly, no new files.
- **Exactly one H2** — splitting would produce one new file plus an original
  reduced to a stub, for no benefit. Treat it like the zero-H2 case: add front
  matter to the original as a single node.
- **Two or more H2s** — split **only the H2s that are separate concepts** — a
  structural section (usage, FAQ, installation) stays with its concept, and a
  document whose H2s are all facets of one concept is not split at all. For the
  H2s that do split, make new files. **Do not delete the original** — leave a
  link to the new document in each section's place. The goal is to keep the
  change easy to revert.

  The leftover original becomes a node too, not a bare shell of links to
  elsewhere: give it front matter with a `wiki_id` derived from its own path (Step
  5) and `related` entries pointing at every document split out of it.
  Otherwise it would hold links while sitting outside the wiki itself, and
  nothing in the graph would ever reach it.

## 5. Assign front matter

`wiki_id` is derived mechanically from the path **relative to the wiki root** — never
pick one by hand, and never derive it by hand either: run
[`wiki_graph.py`](../../scripts/wiki_graph.py) `--derive-id`, one call for all the
selected documents, substituting their real paths and the root confirmed in Step 1 (e.g.
`python3 .claude/harness-tier/scripts/wiki_graph.py --root docs --derive-id
docs/code-style/python.md docs/api_spec.md`). Pass `--root` even when it is `docs`:
nothing has written `wiki.root` to flow-config yet — Step 7 does that — so a call without
it derives against the default instead of the chosen root, and `website/docs` comes back
as `website.docs.auth.jwt`. Such an id is well-formed and unique, so `--verify` is green
on it forever, and a `wiki_id` is immutable once written. Each stdout line is
`path<TAB>id`. A path that cannot produce an id — a segment with no `[a-z0-9]` left after
sanitizing, e.g. a Korean-only filename — is named on stderr with the reason and the call
exits nonzero, though every path that succeeded still prints its line: rename only the
named file(s) and re-run.
`derive_wiki_id` owns the mechanics; this table is parity-tested against it
(`tests/test_wiki_graph.py`), so adding a row here adds a test case:

| path (root `docs/`) | wiki_id |
|---|---|
| `docs/code-style/python.md` | `code-style.python` |
| `docs/a.b.md` | `a-b` |
| `docs/a/b.md` | `a.b` |
| `docs/api_spec.md` | `api-spec` |
| `docs/sds/README.md` | `sds.readme` |
| `docs/onboarding/README.md` | `onboarding.readme` |

The order inside the rule is what keeps `docs/a.b.md` (→ `a-b`) distinct from
`docs/a/b.md` (→ `a.b`) — each segment is sanitized **before** the segments are joined
with `.`. It is **not** collision-free across siblings: `a.b.md`, `a-b.md` and `a_b.md`
in one directory all derive `a-b`. `--verify` reports the duplicate either way (an id
derived by hand in the wrong order fails the same check); the remedy is renaming one
file and re-deriving.

`wiki_id` is immutable once assigned: moving or renaming the file does **not** re-derive
it — the id is what keeps links stable across renames. Derivation is for first
assignment only.

`related` · `depends_on`: read the existing docs, **propose** values, then confirm
with the user before finalizing. **Never write** `used_by` · `defects` — they are
generated fields, and writing them by hand blocks validation.

`sources` records the code paths the document describes, as a map. Prefer **file**
paths: staleness is a content hash of the file (`git hash-object`), so a directory key
is looked up by `--nodes-for` but never appears in `--stale` and its marker is never
refreshed — write one when the document is about the directory as a whole and
you accept that, not as a shorthand for the files inside it. Leave `sha` as
`null` — [`doc-sync`](../doc-sync/SKILL.md) fills it in. Never write an empty string for
an unknown sha: `""` compares equal to everything, so the node reports fresh forever.

**Quote every sha, and any `title` that could read as a keyword.** Front matter is YAML
1.1: unquoted `0123456` is octal and parses as the number 42798, and `title: no` parses
as `false`. Validation rejects both by type, but quoting avoids the round trip.

When authoring a defect document, follow the five-section body structure in
[`defect-template.md`](references/defect-template.md) — its `wiki_id` follows that
template's `defect.<slug>` convention, not this section's path derivation.

## 6. Generate the index

`<root>/index.md` is itself a wiki node, not only a human landing page — reachability
is computed **only** from front-matter edges (`related` · `depends_on` · `used_by`,
direction ignored); markdown links in the body are never read for it (design §3). Give
it front matter with its own `wiki_id` (conventionally `index`) and a `related:` list
of the **top-level entry nodes** — the concepts a reader (or the graph walk) starts
from. Do **not** enumerate every node id there: an index that lists everything turns
the graph into a star, and the orphan check degenerates into "forgot to update the
index" instead of measuring real connectivity.

Every other node must be reachable from the index through real edges: wire it
(`related`/`depends_on`) to the nodes it belongs with. An orphan warning
therefore means "this node is connected to nothing that matters" — fix it by linking
the node to its related concepts, or to the index only when it genuinely is a
top-level entry. A body-only bullet list of links, with no front matter or an empty
`related:`, still silently disables the whole orphan check (every node then reports as
unreachable, or `_index_id` finds no node at all and skips the check).

The body's human-readable link list is for people browsing the file — keep it useful,
but it is not the graph and needs no 1:1 sync with `related:`.

## 7. Update flow-config

`flow-config.example.yaml` already ships a `wiki:` key with `enable: false`, so
on a `/flow-init`'d host this is normally **editing that key's existing values
in place** (starting with `enable: true`), not inserting a new block at an
undefined location. If the key is somehow absent, insert it as its own
top-level section. Either way, touch only the `wiki` key — preserve the rest of
the config.

```yaml
wiki:
  enable: true
  root: docs/
  index: docs/index.md
  max_lines: 400
  context_lines: 2000
  defect_rule_threshold: 3
```

## 8. Build and verify the graph

`git add` every document you created or split out first. The graph is built from git's index,
not from the filesystem — a file git does not know about is not a node, because a graph that
named it would be unreproducible for anyone who cloned the repo.

```bash
python3 .claude/harness-tier/scripts/wiki_graph.py --build
python3 .claude/harness-tier/scripts/wiki_graph.py --verify
```

If `--verify` fails, fix the reported reason and re-run. Do not finish until it
passes. Two failure classes, two different fixes — the output says which:

- **structure violation** (`wiki_id` format or duplicate · missing `title` · a `depends_on`
  pointing at nothing · a cycle · a scalar YAML read as a number or boolean · front matter
  that does not parse while carrying a `wiki_id`) — fix the **document's front matter**.
  `--build` cannot help; it only makes the graph match whatever the front matter already
  says. This list is capped at 10 entries plus a count when printed — fix those and re-run
  to see the rest.
- **graph mismatch** — re-run `--build`.

Everything else it prints is a warning and does not block: orphans, over-size documents,
`sources` paths that are not on disk, rule-promotion candidates, front matter that fails to
parse without a `wiki_id:` line, and a wiki-only field (`related`/`depends_on`/`affects`/
`sources`) present without a `wiki_id`. Each is capped at three entries plus a count.

If you cannot make `--verify` pass within this session, set Step 7's `enable` back to
`false` before you finish and report the violations you left behind. `--build` requires
`enable: true`, so the gate is necessarily on from Step 7 onward — finishing with it on and
the graph invalid blocks every commit in the repository until someone fixes it by hand.

`--verify` reads the **working tree**, so a fresh `graph.yaml` on disk satisfies it even
if the commit does not carry it. `docs/graph/graph.yaml` must be staged together with the
documents it was built from, or the commit records the new front matter beside the old
graph — a drift nothing catches until someone else's next session commit.

**Merge conflicts in `graph.yaml` are never resolved by hand** — it is a generated file,
so hand-merged markers survive as either broken YAML or a graph `--verify` rejects as
drift. Take either side (`git checkout --ours -- <root>/graph/graph.yaml` or
`--theirs`), re-run `--build`, and stage the rebuilt file with the documents. (No merge
driver on purpose: an automatic `ours` would silently pass the wrong graph along to the
next `--verify` block; a conflict forces the rebuild now.)

## 9. Report

Report what was split and what `id`s were assigned, plus any remaining orphans and
over-size documents.

**Do not commit** — committing is [`/flow`](../flow/SKILL.md)'s job.
