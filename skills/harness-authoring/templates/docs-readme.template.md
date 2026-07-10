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
<!-- Sources: {{SOURCES}} -->
