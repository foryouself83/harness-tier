# Component Authoring (SSOT: official docs)

Confirm against the official docs, not model knowledge, as the SSOT:
[plugins-reference](https://code.claude.com/docs/en/plugins-reference.md) ·
[hooks](https://code.claude.com/docs/en/hooks.md) ·
[skills](https://code.claude.com/docs/en/skills.md).

> **Do not author commands.** Harness outputs do not include `.claude/commands/`
> ([harness-rules.md](../../../rules/harness-rules.md) #9). Below are the only components to generate.

- **agent** (`.claude/agents/<name>.md`): frontmatter `name` · `description` (+ invocation examples)
  · `model` (optional) + a single-responsibility system prompt.
- **skill** (`.claude/skills/<name>/SKILL.md`): frontmatter `name` · `description`
  (including trigger signals) + triggers and procedure. Progressive Disclosure (details in references/).
- **rule** (`.claude/rules/<name>.md`): frontmatter is **only an optional `paths` (glob list)** —
  do not use `name`/`description` fields (a rule is not a component but CLAUDE.md-family instructions).
  Without `paths` it auto-loads every session (`.claude/CLAUDE.md` priority); with `paths` it loads when working on matching files.
  The template's `{{PATHS_FRONTMATTER_OR_REMOVE}}` is replaced with a `---`/`paths:`/`---` block for a path-scoped rule,
  or with an empty string for a global rule. **The 5 mandatory rules are injected into the CLAUDE.md baseline body for certainty.**

**Common discipline**: concise and lean; keep a fact in a single SSOT and link the rest.
