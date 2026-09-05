---
name: doc-sync
description: "Use when a change may have left the documentation drifted or inconsistent — after editing code that docs describe, after editing docs themselves, when verifying doc consistency, or when a module has no local CLAUDE.md. Also the /flow doc-sync gate."
# The gate marker this skill writes on pass — an exact path, no trailing glob (a glob's
# `*` crosses path separators including `..`, so `.flow/*` pre-approved touch of any path
# on disk). Doc edits themselves stay promptable. `--neighbors <id>` is deliberately absent:
# its argument is a node id, so the only rule that would cover it ends in `*`, and a trailing
# `*` is a prefix match — `… --neighbors x && <anything>` would be pre-approved too. The
# per-node prompt is the cost of not granting that.
# `--derive-id <paths>` is absent for the same reason — path arguments force a trailing `*`.
allowed-tools: Bash(mkdir -p .claude/harness-tier/.flow) Bash(touch .claude/harness-tier/.flow/doc-sync.done) Bash(python3 .claude/harness-tier/scripts/wiki_graph.py --build) Bash(python3 .claude/harness-tier/scripts/wiki_graph.py --verify) Bash(python3 .claude/harness-tier/scripts/wiki_graph.py --stale)
---

# doc-sync

Analyze **both code and documentation changes**, update the related docs, and
harmonize the whole doc set for consistency.

## When

- Called by `/flow` at the **Docs gate** (doc-only changes) and the **Dev
  gate** (after superpowers completes) → on pass, record
  `.claude/harness-tier/.flow/doc-sync.done`.
- Whenever you need to verify documentation consistency after a code/doc change.

## 1. Determine the change scope

```bash
git diff HEAD                                   # the change itself — hunks per file
git diff --name-only HEAD                       # the complete file list — a large refactor's
                                                # diff can be truncated by tool-output caps,
                                                # and a file dropped here is a file never
                                                # classified into Mode A/B
git ls-files --others --exclude-standard        # new files, which the diff does not show
```

Classify changed files into two tracks (if both, run **A → B** in order):

- **Code changes** (`.py` / `.js` / `.ts` / config / router …) → **Mode A**
- **Doc changes** (`.md`: the index doc, the doc dirs, the rule dir) → **Mode B**
- If the project has a wiki, run **A → B → W** in order.

## Mode A — code → doc sync

Reflect code changes into the related docs.

1. **Extract keywords**: class names, field names, type annotations,
   `Field(description=...)`, env-var names/defaults, route paths, function names,
   `summary`.
2. **Find related docs**: Grep `**/*.md` by keyword (`files_with_matches`).
   Select by relevance score ≥ 0.6:
   `score = keyword_freq×0.4 + file_type×0.3 + context_match×0.2 + path_pattern×0.1`
3. **Update**: Read each file → locate the target section (`#### Request Body`,
   env table, etc.) → replace via Edit to match the code change.

## Mode B — doc → doc harmonization

When docs change, harmonize **the consistency of the whole doc set**.

### Reference targets (read from `flow-config.doc_sync`)

Resolve the targets to check from the project's
`.claude/harness-tier/config/flow-config.yaml`, not from a hardcoded list:

- **`doc_sync.index`** — the documentation index / SSOT (e.g. the root
  `CLAUDE.md`): the service-map table + the `Auto-loaded Rules` table. Links fan
  out from here to each service/rule doc.
- **`doc_sync.service_docs`** (glob) — the per-service local docs linked from the
  index.
- **`doc_sync.dirs`** (globs) — the guide / operations / standards doc dirs and
  the auto-loaded rule dir.

Check every target; track the index by following its links.

### Check items

1. **Cross-reference integrity** — does every file/link/rule a doc points to
   exist (including paths/anchors broken by the change)?
2. **Factual consistency (SSOT)** — do two docs record the same value (model
   name, port, path, policy, version) differently? Keep the value in a single
   source of truth and reduce the rest to links.
3. **Index sync** — does the index's rule/service tables match the actual file
   set (the rule dir, the service dirs)?
4. **Hierarchy consistency** — do the per-service docs contradict the index's
   higher-level rules?
5. **Module CLAUDE.md template compliance** — take the module dirs from
   `flow-config.modules[].path` (the authoritative module list — same one used
   for per-module pre-checks) that fall under the `service_docs` glob's
   directory (e.g. `services/*/`), since the glob itself only matches files
   that already exist and can't surface a *missing* one.
   - If harness is **not** installed for this project (no `docs/code-style/`
     dir and no sibling module already has a local `CLAUDE.md` — the same
     signal [`flow-init`](../flow-init/SKILL.md) uses to decide "harness
     installed"), do **not** create one — creating it here would falsely trip
     that detection for a project that never ran `/harness-init`. Note the
     gap in the Report and stop.
   - Otherwise, if a module has **no** local `CLAUDE.md`, generate one from
     [`module-claude-md-template.md`](references/module-claude-md-template.md)
     by reading the module's actual code (entry points, build/test/lint
     commands, key deps) to fill each section — do not leave placeholders
     unfilled.
   - If a module **already has** one, audit it against that reference's quality
     criteria (commands work, architecture explained, gotchas captured,
     concise, current, actionable) and fix only what falls short — preserve
     existing project-specific content, do not rewrite wholesale.
6. **Translation parity** — for each changed `.md`, look for sibling files whose
   name is the same stem plus a language tag (`README.md` → `README.ko.md`,
   `docs/guide.md` → `docs/guide.ja.md`). A repo with none skips this entirely.
   Where one exists it is a **translation of the file you changed**, so the
   same change belongs in it: carry it over and note it in the Report. Do not
   create a translation that does not already exist, and do not rewrite one
   wholesale — port the delta.
   Nothing else catches this: a translation drifts silently, staying valid
   markdown while describing a version of the product that no longer exists.

### Action

On a mismatch, harmonize the related docs via Edit and record **what changed and
why** in the Report. If a new rule/doc was added but is missing from the index,
add the index row. A newly generated module `CLAUDE.md` also gets an index row
(service-map table) if the index doesn't already list that module.

## Mode W — wiki sync

Runs only when the project has an LLM Wiki (`flow-config.wiki` present and enabled).
Without it, skip this whole mode — the commands below no-op and exit 0.

1. **Find what the code change made stale**:

```bash
python3 .claude/harness-tier/scripts/wiki_graph.py --stale
```

   Each JSON entry names a wiki node whose recorded `sources` value no longer matches the
   file — `recorded` and `current` are **working-tree blob hashes** (`git hash-object`),
   so history rewrites (squash/rebase promotions) cannot fake staleness. An entry with a
   `migrated` key carries a legacy commit-sha marker: rewrite `sources[path]` to the
   `migrated` value — it is the meaning-preserving conversion (`git rev-parse
   <old>:<path>`), needs no re-reading, and the verify gate accepts it without a body
   edit. If `migrated` equals `current`, that rewrite is the whole fix; if it differs (or
   is `null`), the node is also genuinely stale — sync the body, then stamp. An entry
   with `"missing": true` is a different problem: that source **path** no longer exists
   (the file was renamed or deleted). Fix the path — or drop the entry — in the node's
   front matter. Do **not** stamp a sha on it: `--verify` warns on the missing path
   itself, and a fresh sha leaves the problem exactly where it was.

2. **Narrow the harmonize set**. For each stale node, ask the graph for its neighbourhood
   instead of guessing — run `wiki_graph.py --neighbors` once per stale node, substituting
   that node's own id from step 1's JSON (the `id` key of the JSON entry — the graph's
   node id, which is what the document's `wiki_id` becomes):
   `python3 .claude/harness-tier/scripts/wiki_graph.py --neighbors auth.jwt`.
   (Not shown as a copyable block on purpose: there is no id to hardcode, and an id the
   graph does not know exits non-zero with the reason on stderr.)

   Mode A keyword-greps every markdown file and scores relevance. Where a wiki exists the
   graph already holds those relations, so this is a lookup, not an estimate.

3. **Update the bodies**, then stamp `sources[path]` with the file's **working-tree blob
   hash** — the `current` value from step 1's JSON (equivalently `git hash-object --
   <path>`), never a commit sha — **only for nodes whose body you changed**. A
   stale node you did not touch stays stale and goes in the Report — do not stamp its
   sha. Stamping without reading the code behind it turns the marker into a lie, and the
   gate now enforces this mechanically: a commit whose only change to a node is its
   `sources` sha is **blocked** by `--verify`, so a bulk refresh does not merely violate
   prose — it fails. Two swaps stay allowed: step 1's `migrated` rewrite, and a stamp
   whose body edit landed in the immediately preceding commit (so stamping the sync you
   committed, or amending it in, works — including when that commit also renamed
   the document, which the gate follows).
   A stale node you **read and found still accurate** (the code change was cosmetic) is
   deliberately the same case: leave the marker alone and report it as "verified
   accurate, still stale" — the marker only ever moves with a body edit, and it clears
   naturally the next time the body genuinely changes.

4. **Give any new `.md` under the wiki root its front matter** — get `wiki_id` from one
   derivation call for all the new documents, substituting their real paths (e.g.
   `python3 .claude/harness-tier/scripts/wiki_graph.py --derive-id docs/auth/jwt.md
   docs/auth/session.md`; each stdout line is `path<TAB>id`, a failure names its path
   on stderr and the call exits nonzero, though every path that succeeded still prints
   its line — fix that path and re-run; rationale in
   [wiki-init](../wiki-init/SKILL.md) Step 5). No `--root` here, unlike Step 5: this mode
   runs only with the wiki enabled, so the call reads the configured root itself, and a
   hardcoded one would be wrong for every root that is not `docs`. A defect document is
   the exception: its
   `wiki_id` follows the `defect.<slug>` convention in
   [`defect-template.md`](../wiki-init/references/defect-template.md), not this
   derivation. Then `title`, and the `sources` it
   documents. Never write `used_by` or
   `defects`; they are generated. **Wire the new node to the nodes it belongs with**
   (`related`/`depends_on` on either side) so it is reachable from the index through
   real edges; add it to the index's `related:` only when it genuinely is a top-level
   entry ([wiki-init](../wiki-init/SKILL.md) Step 6) — orphan detection reads
   front-matter edges only, never markdown links, so a node wired to nothing reports
   as an orphan forever even if some body links it in prose.

5. **Split any node over `max_lines`**. `--verify` (below) warns on this but nothing acts
   on the warning — `/wiki-init` refuses to re-offer a document that already carries a
   `wiki_id`, so the migration wizard never revisits it either. Split it exactly as
   [`wiki-init`](../wiki-init/SKILL.md) Steps 4-5 direct, including their zero- and
   one-H2 branches — do not assume an H2 split always applies. Record the outcome in the
   Report.

6. **Stage new documents, then rebuild and verify**. A document joins the wiki by being in
   git — the graph is built from the index, not the filesystem, so an unstaged new `.md` is
   not yet a node and a rebuild would omit it. `git add` the new documents first, then:

```bash
python3 .claude/harness-tier/scripts/wiki_graph.py --build
python3 .claude/harness-tier/scripts/wiki_graph.py --verify
```

   `--verify` must exit 0 before the gate marker is written — the commit gate runs the
   same command and will block otherwise. A structure violation (`wiki_id` format/duplicate ·
   missing `title` · dangling `depends_on` · cycle · front matter that does not parse while
   carrying a `wiki_id`) is not fixed by `--build`; fix the document's front matter instead.
   `--verify` reads the **working tree**, so
   `docs/graph/graph.yaml` must be staged alongside the documents it was built from —
   otherwise the commit records the new front matter beside the old graph and the drift
   goes unnoticed until someone else's next session commit. If a merge left conflict
   markers in `graph.yaml`, never resolve them by hand — take either side and re-run
   `--build` ([wiki-init](../wiki-init/SKILL.md) Step 8).

## 1b. Prove the rewrite lost nothing

Every mode above rewrites prose, which is where substance goes missing. Before the marker,
check each `.md` you touched against what `HEAD` holds:

```bash
python3 .claude/harness-tier/scripts/doc_style_check.py --verify-git <changed .md paths>
```

An error names what disappeared — a heading, a fenced block, a URL, an inline-code span.
Restore it, or state in the Report why the removal was the point. Warnings (bullet count,
paths) are advisory. A file `HEAD` never had is skipped; a repo with no
`doc_style_check.py` yet has nothing to run and this step is skipped whole.

Prose itself follows [`doc-style.md`](../../rules/doc-style.md): no history narration, no
pointer to a plan record, no filler, and Korean documents take nominal endings.

## 2. Gate marker (when called by `/flow`)

After checking/updating, leave the gate evidence (the commit is blocked without it):

```bash
mkdir -p .claude/harness-tier/.flow && touch .claude/harness-tier/.flow/doc-sync.done
```

## 3. Report

```
doc-sync result:
- [A] services/<svc>/README.md — added priority field to env table
- [B] <index> ↔ services/<svc>/CLAUDE.md — harmonized model-name mismatch (SSOT: .env.example)
- [B] <index> rule index — missing risk-tiers.md row → added
- [B] services/<svc>/CLAUDE.md — generated from module-claude-md-template.md (Commands/Architecture/Gotchas filled from source); added to index service map
- [B] README.ko.md — ported the same change from README.md (translation parity)
- fixed 1 cross-reference (broken link)
- [W] docs/auth/jwt.md — sources sha refreshed; graph.yaml rebuilt (12 nodes)
- [W] docs/auth/session.md — still stale, body not updated (needs a human call)
- [W] docs/api/auth.md — split by H2 into 3 nodes (over max_lines); original kept as a node with related back-links
```

## Tips

- Writing Pydantic `Field(description=...)` improves Mode A keyword-extraction
  accuracy.
- Unifying markdown section headers at the `####` level makes section replacement
  stable.
- Keep the same fact only in its SSOT (e.g. `.env.example`, a service's local
  doc) and link from other docs — this prevents Mode B mismatches at the root.
- To preview the plan only, request "doc-sync preview" (planning without actual
  Edits).
- The module template ([`module-claude-md-template.md`](references/module-claude-md-template.md))
  covers only a single module's usage info (commands/architecture/gotchas). It
  is a different artifact from the harness root
  `CLAUDE.md`(`skills/harness-authoring/templates/claude-md.template.md`),
  which carries project-wide baseline principles managed by `/harness-init` —
  do not conflate the two or generate baseline-principle content here.
