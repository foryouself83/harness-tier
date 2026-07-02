# Skill Writing Guide

The quality discipline `harness-authoring` follows when generating skills for a host project.
Adapted from the [revfactory/harness](https://github.com/revfactory/harness) skill-writing-guide, condensed into the harness-tier tone.

## Core Principle

**One skill, one role.** If it has more than one role, first check whether it can be split.

## 1. Description — the only trigger mechanism

Claude decides whether to use a skill based on `name` + `description` alone. It triggers conservatively on simple tasks,
so write the description slightly **pushy** (to compensate).

Authoring principles:
1. Describe both **what it does** + the **specific trigger situations**.
2. State the **boundary conditions** that are similar but should not trigger.
3. Make it trigger on abbreviations and casual phrasing too — include implicit expressions like "the xlsx in my downloads folder".

Good example: `"All PDF work — reading, extracting, merging, splitting, OCR, and more. Must be used whenever a .pdf is
mentioned or a PDF output is requested. Especially when conversion, editing, or analysis is needed rather than simple viewing."`

Bad example: `"A skill that processes data"` (vague), `"PDF-related work"` (does not describe action or trigger).

## 2. Body — Why-First

An LLM **judges correctly even in edge cases when it knows the reason**. Context is more effective than coercive rules.

- Bad: `ALWAYS use pdfplumber. NEVER use PyPDF2 for tables.`
- Good: `Use pdfplumber for table extraction. PyPDF2 is text-specialized and loses row/column structure.`

**Imperative tone** — use "do/shall" rather than polite forms. A skill is an instruction sheet.

## 3. Generalization — no overfitting

When a test or feedback reveals a problem, fix it at the **principle level**, not around the specific example.

- Overfit: `If there is a "Q4 revenue" column, convert to numbers.`
- Generalized: `If a column name contains numeric-hinting keywords like "revenue, amount, quantity", convert to numbers. On failure, keep the original.`

**No library/tool assertions**: generated outputs must not hardcode a specific library (e.g., Zod, Prisma) without
confirming the project convention. If there is research/code-analyzer evidence, use that library; if it is greenfield
with no evidence, **generalize to a category ("validation library") or ask** (list reuse candidates in the reuse section
of `docs/code-style/<stack>.md`).

- Overfit: `Do input validation with a Zod schema.`
- Generalized: `Do input validation with the project's validation library (if none exists, pick one from free/commercial-OK candidates; ask if ambiguous), shared between server and client.`

## 4. Output format · examples

If the output format matters, specify a template. **One example is more effective than a long explanation.**

```
Input: Add JWT-based user authentication
Output: feat(auth): implement JWT-based authentication
```

## 5. Progressive Disclosure

- **Domain separation**: split into `references/finance.md` · `sales.md` so only what is needed is loaded.
- **Conditional detail**: the body is an overview, with pointers like "see [REDLINING.md] if change tracking is needed".
- **A reference over 300 lines gets a table of contents at the top.**

**Companion folders** — when generating a skill, if there are references/cases that the role warrants splitting out,
create `<skill>/references/` (detailed references) · `<skill>/examples/` (at least one input/output case) alongside it.
Keep the body to an overview + pointers and push the detail down into references. **Do not force this on a simple skill**
(YAGNI) — only when references/cases actually exist.

## 6. Context economy

Context is a shared resource. Ask whether every sentence earns its tokens.
- "Does Claude already know this?" → delete. "Will it err without this?" → keep. "Would an example be better?" → make it an example.

## 7. Script-bundling signal

If tests keep creating the same helper / the same install / the same workaround, bundle it into `scripts/` or describe
it as a standard procedure in the body. Bundled scripts must be verified by running them.

## 8. What not to put in a skill

- Ancillary docs like README, CHANGELOG, install guides.
- Generation-process meta info (test results, iteration history).
- User-facing manuals (a skill is an AI instruction sheet).
- General knowledge Claude already has.

## 9. Reuse design (avoid duplication)

Before generating something new, check for overlap with existing skills.

| Situation | Action |
|------|------|
| Existing fully contains the new one | No new one — wire the existing one to the agent |
| Partial containment and generalizable | Generalize/extend the existing one |
| Intended domain-specialized partial containment | Proceed with the new one (keep separate) |
| Scope is entirely different | Proceed with the new one |

Generalization stops at the **intended responsibility scope**. Remove only accidental coupling; keep intended specialization.
