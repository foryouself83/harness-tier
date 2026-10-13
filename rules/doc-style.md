# Prose Discipline

Applies to every `.md` a project ships and every comment and docstring in its code.
`.claude/harness-tier/scripts/doc_style_check.py --lint` checks the patterns; `prose-review`
applies the judgement. The checker reads `flow-config.doc_style.paths` (default `**/*.md`; add
`**/*.py` · `**/*.sh` for comments) and always skips every `CHANGELOG.md`, GitHub's issue and
pull request templates, `docs/superpowers/` and `.superpowers/`; a project's `exclude` adds
to those.

**Write the fact in force. Nothing else** — not how it got here, what it was, which plan
proposed it, or an apology for its shape.

## Banned (`--lint` errors)

| Code | What | Instead |
|------|------|---------|
| `HIST` | History narration: `used to` · `previously` · `for months` · `turned out` · `이전에는` | The current behaviour |
| `SHA` | A commit sha in prose | Name the rule |
| `PLAN` | Pointers into `docs/superpowers/plans/`·`specs/`, checklist items | The fact itself |
| `FILLER` | `just` · `simply` · `actually` · `however` · `in order to` · `of course` | Delete |
| `ENDING` | Korean `~다` endings | Nominal endings (`~함`, `~임`, a noun) |
| `ANCHOR` | A line number appended to a filename | The filename alone |
| `META` | A revision field: `@author` · `Author:` · `Last updated:` · `작성자` | Nothing; git holds it |
| `TRAP` | A `CRITICAL TRAP:` box missing `Trigger:` or `Symptom:` | All three lines, or no box |

Warnings: `LONG` above 100 characters of prose on a line; `CLAIM` on a hedged magnitude
(`approximately` · `roughly` · `대략` · `약` before a digit · `30% faster` · `2x cheaper` ·
`2배 빠름`).

## Numbers

Write a number only when it is a contract (a timeout, a limit, a protocol constant) or a
measurement carrying its conditions (`0.76 at reps 5 (n=25)`). Everything else is a direction:
`faster`, `bounded`. Never let an inline-code span cross a line break — the lint reads one line
at a time.

## Comments are the last resort

- Never explain how; the code says how.
- A constraint a reader could violate is a check — an `assert`, a raised error, a type — not a
  sentence.
- No revision history, date or name. A filename, never a line number. Nothing self-evident.
- A trap with no runtime moment to fire at gets exactly this box, its keys literal in every
  project, the text after them in the project's comment language:

  ```
  # CRITICAL TRAP: <what breaks, silently>
  # Trigger: <the condition that reaches it>
  # Symptom: <what a reader sees when it does>
  ```

What is left is a reason or a constraint, on one line.

## Per artifact

- **`CLAUDE.md`** — common rules; a mechanism enforced elsewhere shrinks to a pointer, and a
  silent-failure warning with no other home stays inline.
- **`rules/`** — the rule in force, with at most a parenthetical on what enforces it.
- **`SKILL.md`** — `description` says *when* and the stake of skipping; the body holds the
  procedure.
- **README · USAGE** — what a consumer does, and what breaks without it.

## A rewrite is verified

```bash
python3 .claude/harness-tier/scripts/doc_style_check.py --verify-git <path>…  # vs HEAD
python3 .claude/harness-tier/scripts/doc_style_check.py --verify <before> <after>
```

Markdown keeps every heading, fenced block, URL and inline-code span; source keeps its code
byte-identical once comments are stripped.
