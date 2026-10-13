<!-- Wiki front matter for this doc. Fill every {{…}} below, then delete this comment line
     so the "---" that follows becomes the literal first line of the generated file
     (wiki_graph.py only recognizes front matter starting at byte 0 — leaving this comment
     in place keeps the file harmlessly outside the wiki, same as a plain markdown file). -->
---
# wiki_id: derive mechanically from this file's output path relative to the wiki root, the
# same way wiki-init Step 5 does (e.g. docs/code-style/python.md -> code-style.python). A
# multi-stack project clones this template once per stack — hand-picking <stack> here
# instead risks every clone landing on the literal same id and colliding.
wiki_id: {{ID}}
title: <stack> code style
tags: [code-style, <stack>]
# sources is optional — uncomment and list real code paths this style doc describes; delete
# these two lines if none apply.
# sources:
#   src/path/to/code.py: null
---
# {{STACK_LABEL}} Code Style

> {{LANGUAGE}} + {{FRAMEWORK_OR_PLATFORM}}. Describe the discipline in prose, **without code snippets**. Sources: {{SOURCES}}

## Naming · Formatting · Imports
{{STYLE_RULES}}

## Best Practices (by quality lens)
<!-- Each applicable lens = a managed block. Emit ONLY the lenses that apply to this stack
     (harness-rules 9-7 · 9-8, 9-2 evidence-based). Order = correctness · ux · a11y · performance ·
     security · maintainability · cross-cutting · i18n. Each block holds coding guidance only (1-2 lines +
     source each) — link the SSOT that owns the rest, never duplicate it. On re-run, harness-init
     additively upserts any missing lens block into this section; blocks already present are left
     untouched unless the user selects a refresh.

     Emit the marker below VERBATIM — byte-exact, only <stack>/<lens> substituted — so a re-run upserts
     in place instead of duplicating a new block (shown as a fenced example so its own `-->` cannot
     terminate this comment early): -->
```
<!-- code-style:lens:<stack>:<lens> BEGIN (managed by /harness-init — edits inside are overwritten) -->
### <Lens heading>
- ...
<!-- code-style:lens:<stack>:<lens> END -->
```
{{BEST_PRACTICES_LENS_BLOCKS}}

## Anti-patterns (avoid)
{{ANTI_PATTERNS}}
- **Reinventing the wheel**: if a free, commercial-use-OK off-the-shelf solution (official image, standard library, OSS) exists, use it instead of implementing your own.
- **Ephemeral plan indices in comments**: don't reference one-off spec/plan indices (`Step 3`, `Task 11`, `§2.1`) in code comments — comments explain intent, not planning artifacts that go stale and dangle.

## Toolchain / Config
{{TOOLCHAIN_CONFIG}}  <!-- Build, bundle, type-check, lint, test as one set. Based on the output of the official scaffolder for the detected version. Cite sources. -->

## Reuse Candidates (free, commercial-use-OK)
{{REUSE_EXAMPLES}}
