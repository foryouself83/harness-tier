---
name: design-api
description: Write the API specification from the SRS, SDS, architecture and code, check every id, and render it to .docx.
disable-model-invocation: true
model: sonnet
# Same rule as design-erd: each command below is exact, since a trailing `*` would grant
# `<command> && <anything>` too. `pip install …` stays promptable for the same reason.
allowed-tools: Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --paths) Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --templates) Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --doc api) Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --wiki-id api) Bash(python3 .claude/harness-tier/scripts/design_doc_render.py --check-deps) Bash(python3 .claude/harness-tier/scripts/design_doc_render.py api) Bash(python3 .claude/harness-tier/scripts/wiki_graph.py --build)
---

# Design-API

Writes `<docs>/api.md` against the host's `api.template.md`, then renders
`<output>/api.docx`. Conventions: [`design-docs.md`](../../rules/design-docs.md).

**Precondition**: `.claude/harness-tier/scripts/design_doc_check.py` must exist. If it
doesn't, tell the user to run [`/flow-init`](../flow-init/SKILL.md) and **stop**.

## 1. Resolve paths and dependencies

```bash
python3 .claude/harness-tier/scripts/design_doc_check.py --paths
python3 .claude/harness-tier/scripts/design_doc_render.py --check-deps
```

When the second prints `missing: ...`, ask via `AskUserQuestion` whether to install them,
showing the command. **Yes** → run `python3 -m pip install python-docx markdown-it-py` and
continue. **No** → stop; the check steps below still run without them if the user asks.

## 2. Check the templates

```bash
python3 .claude/harness-tier/scripts/design_doc_check.py --templates
```

Any violation → relay the list and **stop**. A template is the consumer's; do not edit it.

## 3. Take the code inventory

List every route the code registers: router decorators, route tables, controller
mappings. Run the listing as one command and keep it: it goes into the inventory section
verbatim.

## 4. Write the document

Read `docs/srs/`, `docs/sds/`, `architecture.md` and the inventory's sources. Write
`<docs>/api.md` in the template's shape: every template heading in order, every table with
the template's header, one `API-NNN` block per operation, the traceability table, and the
inventory. Each operation names the `CMP-NNN` from `architecture.md` that serves it, inside
that operation's own block table — the cross-check reads the block, not the traceability
table. When
the file exists, update it: keep every id, number new operations after the highest, and
append one `revisions` row. Get `wiki_id` from:

```bash
python3 .claude/harness-tier/scripts/design_doc_check.py --wiki-id api
```

## 5. Check the document

```bash
python3 .claude/harness-tier/scripts/design_doc_check.py --doc api
```

Fix what it names and run it again, at most three rounds. Relay every violation still
standing and every `note:` line; do not render over a violation without the user's
go-ahead via `AskUserQuestion`.

## 6. Render

```bash
python3 .claude/harness-tier/scripts/design_doc_render.py api
```

When `flow-config.wiki` is enabled, rebuild the graph so the new node is in it, and tell
the user to stage `graph.yaml` with the document:

```bash
python3 .claude/harness-tier/scripts/wiki_graph.py --build
```

## 7. Report

The `.docx` path, the violation count, and every `warning:` line (a diagram left as code).
