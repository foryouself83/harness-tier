---
name: design-srs
description: Render the SRS in docs/srs/ to .docx after checking its ids and links.
disable-model-invocation: true
model: sonnet
# Both commands below run a fixed subcommand plus this skill's own doc name, so each rule
# is the exact command issued — no trailing `*`, which would grant `<command> &&
# <anything>` too. `pip install …` stays promptable: the user's own yes/no in Step 1
# decides it.
allowed-tools: Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --paths) Bash(python3 .claude/harness-tier/scripts/design_doc_render.py --check-deps) Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --templates) Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --doc srs) Bash(python3 .claude/harness-tier/scripts/design_doc_render.py srs)
---

# Design-SRS

Converts the SRS as written — the files `srs.template.md` lists under `sources`, in that
order — to `<output>/srs.docx`. Nothing here edits `docs/srs/`: it is reviewed text.

**Precondition**: `.claude/harness-tier/scripts/design_doc_check.py` must exist. If it
doesn't, tell the user to run [`/flow-init`](../flow-init/SKILL.md) and **stop**.

## 1. Resolve paths and dependencies

```bash
python3 .claude/harness-tier/scripts/design_doc_check.py --paths
python3 .claude/harness-tier/scripts/design_doc_render.py --check-deps
```

When the second prints `missing: ...`, ask via `AskUserQuestion` whether to install them,
showing the command. **Yes** → run `python3 -m pip install python-docx markdown-it-py` and
continue. **No** → stop.

## 2. Check

```bash
python3 .claude/harness-tier/scripts/design_doc_check.py --templates
python3 .claude/harness-tier/scripts/design_doc_check.py --doc srs
```

A template violation → relay it and **stop**. A document violation → relay the list and
ask via `AskUserQuestion` whether to render anyway or stop so the SRS can be fixed first.

## 3. Render

```bash
python3 .claude/harness-tier/scripts/design_doc_render.py srs
```

The revision history comes from `revisions` in `srs.template.md`; tell the user to add a
row there when this render is a new version.

## 4. Report

The `.docx` path, the violation count, and every `warning:` line.
