---
wiki_id: readme
title: Documentation Index
tags: [readme]
---
# {{PROJECT_NAME}} Documentation

The full structure of the project documentation. If you are new, start with [Onboarding](onboarding/README.md).

## Structure
{{SRS_INDEX_LINE_IF_GREENFIELD}}
- [Design (SDS)](sds/README.md) — structure + Mermaid diagram
- [Code Style](code-style/README.md) — per-stack conventions, best practices, anti-patterns, toolchain config
{{VERIFICATION_INDEX_LINE_IF_ANY}}<!-- emit "- [Verification](verification/) — performance & integration verification SSOT (per stack)" only when docs/verification/* was generated; otherwise leave this line blank -->
- [Operations](operations/commit-versioning-guide.md) — Conventional Commits · SemVer · release-tool setup
- [Research](research/README.md) — framework conventions, configuration, off-the-shelf solution survey
- [Onboarding](onboarding/README.md) — run, debug, documentation guide

<!-- This index is the single map of the whole design set — EVERY generated doc category must be linked here (harness-rules 8:
     "docs/README links all the other docs"). The one exception is structural conventions: they live outside docs/ as a rule at
     .claude/rules/<framework>-conventions.md (loaded via CLAUDE.md), so they are reached from CLAUDE.md, not from this index. -->
<!-- This file's id is `readme` (its path, mechanically derived), not the wiki graph's entry point — that is
     `wiki.index` (default docs/index.md), a separate file `/wiki-init` creates. Still link every child doc here,
     not just the categories above: it is what makes this page useful as a human landing map regardless of the
     wiki, and every doc reachable from `docs/index.md` should also be reachable from here. -->
<!-- Sources: {{SOURCES}} -->
