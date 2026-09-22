# Prose Discipline

Applies to every `.md` a project ships and every comment and docstring in its code.
`.claude/harness-tier/scripts/doc_style_check.py --lint` enforces the mechanical half;
the judgement below is the half it cannot make. Which files it reads comes from
`flow-config.doc_style.paths` — `**/*.md` alone by default, so a project that wants its
comments checked names `**/*.py` · `**/*.sh` there too. The checker carves back out what no
edit could pass: a regenerated `CHANGELOG.md`, and the `docs/superpowers/` · `.superpowers/`
trees, whose records are checklist lines and pointers to themselves by construction. A
project's own `exclude` is added to those three; it cannot subtract one.

## The rule

**Write the fact in force. Nothing else.**

A reader arrives to learn what is true now. Everything that is not that — how the code
got here, what it was before, which plan proposed it, an apology for its shape — costs
the reader attention and earns nothing.

## Banned outright (`--lint` errors)

| Code | What | Instead |
|------|------|---------|
| `HIST` | History narration: `used to` · `previously` · `for months` · `turned out` · `이전에는` | The current behaviour, stated once |
| `SHA` | A commit sha in prose | Name the rule; a squash merge can orphan the sha |
| `PLAN` | Pointers into `docs/superpowers/plans/`·`specs/`, checklist items | The fact itself — plan records are point-in-time and get superseded |
| `FILLER` | `just` · `simply` · `actually` · `however` · `in order to` · `of course` | Delete. The sentence keeps its meaning |
| `ENDING` | Korean `~다` endings | Nominal endings (`~함`, `~임`, a noun) |
| `ANCHOR` | A line number appended to a filename | The filename alone — the number is false after the next insert |
| `META` | A revision field: `@author` · `Author:` · `Last updated:` · `작성자` | Nothing. Git holds the history, the date and the name |
| `TRAP` | A `CRITICAL TRAP:` box missing `Trigger:` or `Symptom:` | All three lines, or no box |

`LONG` warns above 100 characters of prose on one line. Long lines are not wrong, but a
line that needs 300 characters is usually three facts pretending to be one.

`CLAIM` warns on a hedged magnitude — `approximately` · `roughly` · `대략` · `약` before a
digit · `30% faster` · `2x cheaper` · `2배 빠름`. It reads hedges only, never bare digits,
because the rule below is a judgement no pattern makes.

## A number is a measurement or a contract

Write a number when it is one of two things:

- **A value something is bound to** — a timeout, a limit, a schema bound, a protocol
  constant. The number *is* the behaviour; replacing it with a direction deletes the fact.
- **A figure someone measured**, carrying the conditions that produced it.
  `0.76 at reps 5 (n=25)` survives review because a reader can reproduce it; `0.76` on its
  own does not. Never let an inline-code span cross a line break — the lint reads one line
  at a time, so a wrapped span masks the prose after it and hides real violations.

Everything else is a direction: `faster`, `bounded`, `most of the tree`. A direction does
not go stale and cannot be measured wrong.

The failure this prevents is not an inaccurate document. A guess written as a number reads
as a contract to the next reader, who defends it, and to a reviewer, who flags it — every
round, on prose no one can verify.

## A comment is the last resort

Before writing one, try to delete the need for it.

1. **Never explain how.** The code says how. A comment that paraphrases the next line ages
   into a lie the moment that line changes, and a reader who trusts it is worse off than one
   who read the code.
2. **Make the code raise instead.** A constraint a reader could violate is a check, not a
   sentence: an `assert`, a raised error, a validated bound, a type. Prose asks to be
   believed; a failing call cannot be ignored.
3. **When it cannot raise, use the box.** Some traps have no runtime moment to fire at — a
   locale that silently changes an encoding, an ordering nothing observes until it is wrong.
   Those get exactly this shape, and nothing else earns three lines:

   ```
   # CRITICAL TRAP: <what breaks, silently>
   # Trigger: <the condition that reaches it>
   # Symptom: <what a reader sees when it does>
   ```

4. **No revision history, date, or name.** Git holds all three, and holds them correctly.
5. **A filename, never a line number.** `precommit-runner.sh` survives an edit; a `:31`
   appended to it is false the next time anyone inserts a line above it.
6. **Nothing self-evident.** A comment restating the identifier it sits on is noise that
   costs the reader a line and teaches them to skim the next one.

Everything left over is a reason or a constraint, and it fits on one line.

The three box keys are literals the checker parses, so they stay as written in every
project. What follows each key is prose: write it in the language the project's comments
are written in.

## Per artifact

- **`CLAUDE.md`** — common rules only. A mechanism enforced elsewhere (a gate, a test, a
  cited SSOT) shrinks to a one-line pointer. Silent-failure warnings with no other home
  stay inline. War stories go nowhere.
- **`rules/`** — the rule in force, with at most a parenthetical on what enforces it.
- **`SKILL.md`** — `description` states *when* to reach for it and the stake of skipping
  it; the body holds the procedure. Neither restates the other.
- **README · USAGE** — what a consumer does, and what breaks without it. No pitch.
- **Comments and docstrings** — see "A comment is the last resort" above.

## Compression is verified, not trusted

Rewriting prose is how substance goes missing. After a rewrite, prove nothing was lost:

```bash
python3 .claude/harness-tier/scripts/doc_style_check.py --verify-git <path>…  # vs HEAD
python3 .claude/harness-tier/scripts/doc_style_check.py --verify <before> <after>
```

Markdown must keep every heading, fenced block, URL and inline-code span. Source must
keep its code byte-identical once comments and docstrings are stripped — a prose pass
that alters code is a bug at any size.
