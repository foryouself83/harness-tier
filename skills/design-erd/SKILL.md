---
name: design-erd
description: Write the ERD (entity-relationship design) from the SRS, SDS and code, check every id, and render it to .docx.
disable-model-invocation: true
model: sonnet
# design_doc_check.py and design_doc_render.py each run on a fixed subcommand plus this
# skill's own doc name, so every rule below is the exact command it issues — no trailing
# `*`, since a trailing `*` is a prefix match and would pre-approve `<command> &&
# <anything>` too. `pip install …` stays promptable: the user's own yes/no in Step 1
# decides it.
allowed-tools: Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --paths) Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --templates) Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --doc erd) Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --wiki-id erd) Bash(python3 .claude/harness-tier/scripts/design_doc_render.py --check-deps) Bash(python3 .claude/harness-tier/scripts/design_doc_render.py erd) Bash(python3 .claude/harness-tier/scripts/wiki_graph.py --build)
---

# Design-ERD

Writes `<docs>/erd.md` against the host's `erd.template.md`, then renders
`<output>/erd.docx`. Conventions: [`design-docs.md`](../../rules/design-docs.md).

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

List every persistent model the code defines — ORM model classes, migration
`CREATE TABLE` statements, schema files. Run the listing as one command and keep it: it
goes into the inventory section verbatim.

## 4. Write the document

Read `docs/srs/`, `docs/sds/` and the inventory's sources. Write `<docs>/erd.md` in the
template's shape: every template heading in order, every table with the template's header,
one `ENT-NNN` per entity, the `erDiagram` block, the traceability table, and the inventory.
When the file exists, update it: keep every id, number new entities after the highest, and
append one `revisions` row. Get `wiki_id` from:

```bash
python3 .claude/harness-tier/scripts/design_doc_check.py --wiki-id erd
```

## 5. Check the document

```bash
python3 .claude/harness-tier/scripts/design_doc_check.py --doc erd
```

Fix what it names and run it again, at most three rounds. Relay every violation still
standing and every `note:` line; do not render over a violation without the user's
go-ahead via `AskUserQuestion`.

## 6. Render

```bash
python3 .claude/harness-tier/scripts/design_doc_render.py erd
```

When `flow-config.wiki` is enabled, rebuild the graph so the new node is in it, and tell
the user to stage `graph.yaml` with the document:

```bash
python3 .claude/harness-tier/scripts/wiki_graph.py --build
```

## 7. Report

The `.docx` path, the violation count, and every `warning:` line (a diagram left as code).
