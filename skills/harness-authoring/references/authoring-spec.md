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
  Optional fields earn their place one at a time — the official reference lists many, and each
  costs something when it says nothing:
  - `argument-hint` only when the body reads `$ARGUMENTS`; it is the autocomplete hint, so a
    skill taking no arguments has none to show (`(none)` renders that literal string).
  - `disable-model-invocation: true` for setup/teardown you want to trigger by hand. It also
    keeps the `description` out of the model's context, so write that description for the human
    reading the `/` menu: one line, no trigger list.
  - `allowed-tools` **pre-approves** tools; it does not restrict them ("every tool remains
    callable"). Bare `Bash` therefore grants every command — scope each rule to a command the
    skill actually runs (`Bash(k6 run *)`), and leave out anything whose prompt is doing real
    work, such as an install or a commit. Tools that never prompt (`Read`, `Grep`, `Glob`,
    `AskUserQuestion`, `Agent`) add nothing but the false look of a limit. The grant expires at
    the user's next message, so a multi-turn wizard gets little from it; a session-wide grant
    belongs in `settings.json` `permissions.allow`.
- **rule** (`.claude/rules/<name>.md`): frontmatter is **only an optional `paths` (glob list)** —
  do not use `name`/`description` fields (a rule is not a component but CLAUDE.md-family instructions).
  Without `paths` it auto-loads every session (`.claude/CLAUDE.md` priority); with `paths` it loads when working on matching files.
  The template's `{{PATHS_FRONTMATTER_OR_REMOVE}}` is replaced with a `---`/`paths:`/`---` block for a path-scoped rule,
  or with an empty string for a global rule. **The 5 mandatory rules are injected into the CLAUDE.md baseline body for certainty.**

**Common discipline**: concise and lean; **no duplication** — keep a fact in a single
SSOT and link the rest ([harness-rules.md](../../../rules/harness-rules.md) rule 7·8).
