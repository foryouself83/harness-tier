---
name: doc-sync
description: "Sync documentation with BOTH code and documentation changes via git diff. For code changes, update related markdown. For doc changes, harmonize the whole doc set (the targets declared in vdev-config.doc_sync — index, dirs, service_docs) for consistency, including creating or updating each module's local CLAUDE.md against a best-practice template. Use when docs need updating, when code/doc changes affect docs, or to verify documentation consistency (the /vdev doc-sync gate)."
---

# doc-sync

Analyze **both code and documentation changes**, update the related docs, and
harmonize the whole doc set for consistency.

## When

- Called by `/vdev` at the **Docs gate** (doc-only changes) and the **Dev
  gate** (after superpowers completes) → on pass, record
  `.claude/vway-kit/.vdev/doc-sync.done`.
- Whenever you need to verify documentation consistency after a code/doc change.

## 1. Determine the change scope

```bash
git diff HEAD
git diff --name-only HEAD
git ls-files --others --exclude-standard
```

Classify changed files into two tracks (if both, run **A → B** in order):

- **Code changes** (`.py` / `.js` / `.ts` / config / router …) → **Mode A**
- **Doc changes** (`.md`: the index doc, the doc dirs, the rule dir) → **Mode B**

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

### Reference targets (read from `vdev-config.doc_sync`)

Resolve the targets to check from the project's
`.claude/vway-kit/config/vdev-config.yaml`, not from a hardcoded list:

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
   actually exist (including paths/anchors broken by the change)?
2. **Factual consistency (SSOT)** — do two docs record the same value (model
   name, port, path, policy, version) differently? Keep the value in a single
   source of truth and reduce the rest to links.
3. **Index sync** — does the index's rule/service tables match the actual file
   set (the rule dir, the service dirs)?
4. **Hierarchy consistency** — do the per-service docs contradict the index's
   higher-level rules?
5. **Module CLAUDE.md template compliance** — take the module dirs from
   `vdev-config.modules[].path` (the authoritative module list — same one used
   for per-module pre-checks) that fall under the `service_docs` glob's
   directory (e.g. `services/*/`), since the glob itself only matches files
   that already exist and can't surface a *missing* one.
   - If harness is **not** installed for this project (no `docs/code-style/`
     dir and no sibling module already has a local `CLAUDE.md` — the same
     signal [`vdev-init`](../vdev-init/SKILL.md) uses to decide "harness
     installed"), do **not** create one — creating it here would falsely trip
     that detection for a project that never ran `/harness-init`. Just note the
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

### Action

On a mismatch, harmonize the related docs via Edit and record **what changed and
why** in the Report. If a new rule/doc was added but is missing from the index,
add the index row. A newly generated module `CLAUDE.md` also gets an index row
(service-map table) if the index doesn't already list that module.

## 2. Gate marker (when called by `/vdev`)

After checking/updating, leave the gate evidence (the commit is blocked without it):

```bash
mkdir -p .claude/vway-kit/.vdev && touch .claude/vway-kit/.vdev/doc-sync.done
```

## 3. Report

```
doc-sync result:
- [A] services/<svc>/README.md — added priority field to env table
- [B] <index> ↔ services/<svc>/CLAUDE.md — harmonized model-name mismatch (SSOT: .env.example)
- [B] <index> rule index — missing risk-tiers.md row → added
- [B] services/<svc>/CLAUDE.md — generated from module-claude-md-template.md (Commands/Architecture/Gotchas filled from source); added to index service map
- fixed 1 cross-reference (broken link)
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
