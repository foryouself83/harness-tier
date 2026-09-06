---
paths:
  - "CLAUDE.md"
---

# Editing this repo's CLAUDE.md

CLAUDE.md is the SSOT. It carries the fact itself — never a pointer to
`docs/superpowers/specs/*` or `plans/*`. Those are point-in-time records that can be
missed or superseded, and a reader who has to follow a pointer to find a rule is a
reader who can lose the rule. Put a long rationale in the spec; the rule stays
readable without it.

## What earns a line

The trim axis: **is CLAUDE.md the only home for this, or is it enforced and
discoverable elsewhere?**

- **Mechanism** — how a gate computes, when a test enforces it or a cited SSOT spells
  it out (`rules/risk-tiers.md` · `flow-tiers.yaml` · `evals/`) — shrinks to a
  one-line pointer.
- **Sole-SSOT silent-failure warnings** stay inline, because nothing else catches
  them: `.md` must commit as `feat`/`fix` not `docs` to propagate · one-way
  SOURCE-only edits · the gate lives in the host's `settings.json` · never write into
  the plugin dir.
- **War stories are neither** — delete them.

## Write the durable fact, not the incident

An entry gets the rule and, at most, a parenthetical on what enforces it. No commit
shas, no naming the skill or test whose absence caused the gap, no account of a past
incident. Shas rot fastest: a squash merge can make a cited sha unreachable
within the same session that wrote it.

## Keep it dense AND short-lined

Both the line count and the line length (~100 chars, matching neighbouring entries).
Compress by dropping what a filename already implies and by cutting retrospective
asides — never by dropping the non-obvious judgement that made the entry worth
writing.
