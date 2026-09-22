---
name: design-architecture
description: Write the architecture design document from the SRS, SDS and code, check every id, and render it to .docx.
disable-model-invocation: true
model: sonnet
# Same rule as design-erd: each command below is exact, since a trailing `*` would grant
# `<command> && <anything>` too. `pip install …` stays promptable for the same reason.
allowed-tools: Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --paths) Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --templates) Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --doc architecture) Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --wiki-id architecture) Bash(python3 .claude/harness-tier/scripts/design_doc_render.py --check-deps) Bash(python3 .claude/harness-tier/scripts/design_doc_render.py architecture) Bash(python3 .claude/harness-tier/scripts/wiki_graph.py --build)
---

# Design-Architecture

Writes `<docs>/architecture.md` against the host's `architecture.template.md`, then
renders `<output>/architecture.docx`. Conventions:
[`design-docs.md`](../../rules/design-docs.md).

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

## 3. Survey the components

Read every SDS module and list the deployable units, processes and external systems the
code and deployment files show. Run the listing as one command and keep it: it grounds the
component and deployment sections below.

## 4. Write the document

Read `docs/srs/` and `docs/sds/`. Write `<docs>/architecture.md` in the template's shape:
every template heading in order, every table with the template's header, one `CMP-NNN` per
component, one `IF-NNN` per interface, the context/component/deployment/sequence diagrams,
and the traceability table. Every FR and every numbered NFR in the SRS must appear in the
traceability table or a component row — the check lists each one that does not. When the
file exists, update it: keep every id, number new components and interfaces after the
highest, and append one `revisions` row. Get `wiki_id` from:

```bash
python3 .claude/harness-tier/scripts/design_doc_check.py --wiki-id architecture
```

## 5. Check the document

```bash
python3 .claude/harness-tier/scripts/design_doc_check.py --doc architecture
```

Fix what it names and run it again, at most three rounds. Relay every violation still
standing and every `note:` line; do not render over a violation without the user's
go-ahead via `AskUserQuestion`.

## 6. Render

```bash
python3 .claude/harness-tier/scripts/design_doc_render.py architecture
```

When `flow-config.wiki` is enabled, rebuild the graph so the new node is in it, and tell
the user to stage `graph.yaml` with the document:

```bash
python3 .claude/harness-tier/scripts/wiki_graph.py --build
```

## 7. Report

The `.docx` path, the violation count, and every `warning:` line (a diagram left as code).
