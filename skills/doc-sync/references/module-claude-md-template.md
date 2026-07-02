# Per-Module CLAUDE.md Template

The template and quality criteria that Mode B follows when creating or updating a `service_docs` entry (a per-module local CLAUDE.md).
Its purpose differs from the harness-root CLAUDE.md (`skills/harness-authoring/templates/claude-md.template.md` — baseline principles and rule-marker
management): this template holds only **practical, in-use information about a single module** (commands, structure, gotchas, dependencies) and
does not cover project-wide working principles.

Source: Anthropic's official `claude-md-management` plugin (the `claude-md-improver` skill),
its templates.md, quality-criteria.md, and update-guidelines.md.

Create new files only in a project where the harness is installed (`docs/code-style/` exists, or a sibling module
already has a CLAUDE.md — the same harness-detection signal as [`flow-init`](../../flow-init/SKILL.md)).
Creating one arbitrarily in a project without the harness installed will break that detection — for the detailed judgment, see
[`doc-sync/SKILL.md`](../SKILL.md), Check item 5.

## Core Principles

- **Concise**: one line per concept. Density over verbose explanation.
- **Actionable**: commands must be directly copy-pasteable.
- **Module-specific**: only content that applies to this module. No generalities, no facts duplicated from other modules (the SSOT lives in exactly one place).
- **Current**: reflect the actual state of the code. Do not list paths or commands that do not exist.

## Recommended Sections (only the applicable ones — you need not fill all of them)

````markdown
# <module name>

<one-line description — what this module is responsible for>

## Commands

| Command | Description |
|---------|-------------|
| `<install/build/test/lint command>` | <description> |

## Architecture

```text
<dir>/    # <role>
<dir>/    # <role>
```

## Key Files

- `<path>` - <role>

## Dependencies

- `<dependency>` - <why this module depends on it, initialization order, or other non-obvious relationships>

## Environment

- `<VAR_NAME>` - <purpose, whether required>

## Testing

- `<test command>` - <what it verifies>

## Gotchas

- <non-obvious patterns, troubleshooting history, common mistakes>
````

## Quality Criteria (deciding whether to create/update)

Review an existing module CLAUDE.md along the following axes, and fix only the items that fall short (no full rewrites — preserve
project-specific content):

- **Commands / workflow** — do the build, test, and lint commands actually exist and work?
- **Architecture** — are the key directories, entry points, and inter-module relationships explained?
- **Gotchas** — are non-obvious patterns, issues, and workarounds recorded?
- **Conciseness** — does it avoid repeating what the code already says (e.g., "the UserService class handles user processing")?
- **Currency** — do the file paths, commands, and tech-stack versions match the actual codebase?
- **Actionability** — are the examples usable as-is rather than theoretical (no fake paths, no unfinished TODOs)?

## Red flags (remove on sight)

- References to nonexistent paths/commands (deleted files, changed commands)
- Template placeholders (`<...>`) left in without customization
- The same fact recorded differently (or redundantly) across multiple module CLAUDE.md files or the index — an SSOT violation
- One-off fix history that will never recur (e.g., "fixed the login bug in commit abc123") — delete it
- Generic development advice ("be sure to write tests," etc.) — delete unless it is knowledge specific to this project
