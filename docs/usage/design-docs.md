# Design deliverables

**English** · [한국어](design-docs.ko.md) · [Usage guide](../../USAGE.md)

Six user-invoked skills turn the requirement and design documents into `.docx`
deliverables: `/design-srs`, `/design-sds`, `/design-architecture`, `/design-api`,
`/design-erd`, `/design-table`. Run `/flow-init` first — it seeds the templates.

## Order

`/design-srs` → `/design-sds` → `/design-architecture` → `/design-erd` → `/design-table` →
`/design-api`. A later document refers to ids an earlier one issues; run out of order, the
cross-document check is skipped and says which document is missing.

## What each writes

| Skill | Source | Writes |
|---|---|---|
| `/design-srs`, `/design-sds` | `docs/srs/`, `docs/sds/` as written | `.docx` only |
| `/design-architecture` | SRS, SDS, code | `<docs>/architecture.md` + `.docx` |
| `/design-api` | SRS, SDS, architecture, code | `<docs>/api.md` + `.docx` |
| `/design-erd` | SRS, SDS, code | `<docs>/erd.md` + `.docx` |
| `/design-table` | SRS, SDS, ERD, code | `<docs>/table.md` + `.docx` |

Paths come from `design_docs` in `flow-config.yaml`; setting `gitignore_output: true` has
`/flow-init` add `output` to `.gitignore`.

## Changing a template

Edit the file under `design_docs.templates`. Headings, table header rows and
`<!-- repeat: PREFIX -->` blocks are what the check demands and what the `.docx` shows;
`id_prefix` and `refs` in the front matter are the id rules. A `labels` key in the front
matter renames the `.docx`'s fixed sections — revision history, table of contents — for a
template written in another language; the shipped templates carry Korean labels. Check an
edit with:

```bash
python3 .claude/harness-tier/scripts/design_doc_check.py --templates
```

`/flow-init` never overwrites a template that exists. Delete one to get the shipped
version back on the next run.

## Diagrams leave the host

A ` ```mermaid ` or ` ```d2 ` block goes to `design_docs.renderer` (`https://kroki.io` by
default) and comes back as SVG, embedded in the `.docx` — Word 2016 or later renders it,
an older version shows a fallback image instead. Point the renderer at a self-hosted Kroki
to keep diagram content inside the network.

## Dependencies

`python-docx` and `markdown-it-py`. A skill that finds them missing asks before installing.
