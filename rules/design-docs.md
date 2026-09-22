# Design Deliverables

Read by the `/design-*` skills. The Markdown under `design_docs.docs` is the source; the
`.docx` is rebuilt from it and never edited.

## The template decides the shape

`design_docs.templates` holds one `<doc>.template.md` per document, seeded once by
`/flow-init` and owned by the host afterwards. Its headings, in order, are the document's
required headings; each table header row is the exact header the table under that heading
must carry. A `<!-- repeat: PREFIX -->` line makes the heading below it one block per issued
id, every block carrying the tables the template puts inside it. `{{...}}` marks what to
fill; none may survive.

## Ids

- Issue an id where the item is defined: `<a id="tbl-001"></a>TBL-001` — in the block
  heading for a repeat block, in the first cell for a table row. Three digits, next free
  number; an existing id keeps its number on every re-run.
- Issue only the template's `id_prefix` kinds. Refer to everything else.
- Refer by link where the target is a document: `[FR-PAY-001](../srs/pay.md#fr-pay-001)`,
  `[ENT-003](erd.md#ent-003)`. A bare id is checked too, so a typo is caught either way.
- Refer only to kinds in the template's `refs`.
- An id kind whose template carries a `<!-- repeat: PREFIX -->` block is issued only in
  that block's heading; a list table that names the same item links to the id instead of
  issuing it again — issuing it in both places is an S-ID duplicate. For the API document
  specifically, each `API-NNN` block's own table names the `CMP-NNN` that serves it; the
  cross-check reads the block, not the traceability table.

## Front matter

Every document written here carries wiki front matter: `wiki_id` from
`design_doc_check.py --wiki-id <doc>` (never typed by hand), `title`, `tags`,
`related` (only ids of documents that have front matter), `sources`, and
`revisions` — one `{version, date, summary}` row per run, appended, never rewritten.

`sources` is a map `path: null` — the wiki format, keyed by the repo-relative code path
each claim rests on. A value is `null` or a sha; the checker keys on the map's paths, not
its values. A non-mapping `sources` (a list, for instance) is an S-FRONT violation.

## Code inventory

API, ERD and table documents end with the inventory section the template names: the
command that listed the routes, models or tables (a fenced `bash` block), then one row per
item found — the document id that covers it, or `N/A: <reason>`. The command is what lets a
reviewer re-run it; the checker cannot know what the code holds. A host with no code for
that inventory still writes the command that found nothing, plus one row `N/A: <reason>`.

The `근거` column — the checker keys on that exact column name — holds one repo-relative
path per cell (a `#fragment` is allowed, a line number is not), or `-` when the row has no
source. Never "needs confirmation" in that column.

## Unknowns

A fact neither the SRS, the SDS nor the code states is written as the document's own
language's equivalent of "needs confirmation" (a Korean document: `확인 필요`), never
invented.

## Diagrams

A ` ```mermaid ` or ` ```d2 ` block is sent to `design_docs.renderer`, a Kroki server, and
embedded in the document as SVG. When that fails the source stays in the document as code
and the render reports it.
