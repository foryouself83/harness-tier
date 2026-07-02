---
name: harness-authoring
description: "Authoring discipline and templates for generating framework-appropriate AI harnesses (.md components). Invoked by /harness-init. Fills the skeletons of 3 component types (skill/agent/rule) + CLAUDE.md + technical docs (folders by category) using the authoring guides and mandatory rules in references. Does not generate commands."
---

# harness-authoring

The generation engine of `/harness-init`. It fills `templates/` (skeletons) with `references/`
(authoring guides and mandatory rules) plus research results to produce the host harness.

## Principles
- **Concise and lean** — keep generated .md short. State a fact in one SSOT, link the rest.
- **Always inject the 5 mandatory rules** — put `references/karpathy-principles.md`, `rule-dry-constants.md`,
  `rule-version-pinning.md`, `security-rule.md`, and `rule-reuse-first.md` into the CLAUDE.md `harness:baseline`
  block. Preserve each rule's anchor (`<!-- rule:<key> -->`) (guarantees the load path — do not place them
  standalone in `.claude/rules/`).
- **Authoring quality** — load and follow `references/skill-writing-guide.md` (pushy desc, Why-first, generalization),
  `agent-design-guide.md` (separation, reuse, team protocol), and `tech-doc-guide.md` (technical docs). For official
  frontmatter, follow `references/authoring-spec.md` (official-docs SSOT).
- **SSOT separation** — structural conventions go in a rule (`<framework>-conventions.md`); behavioral style, best
  practices, and anti-patterns go in a doc (`docs/code-style/<stack>.md`). Do not duplicate the same fact in two places.
- **No library assertions** — outputs (skills, agents, docs) must not hardcode a specific library/tool without evidence
  from research or code-analyzer. For greenfield, generalize to a category or ask (reuse candidates go in the reuse
  section of `docs/code-style/<stack>.md`). Example: "Zod schema" → "the project's validation library (pick one from
  the candidates if none exists)".
- **No command generation** — never create any output under `.claude/commands/`.
- **No duplicate generation** — if a feature overlaps by name+description from detect, skip or ask.
- **When flow is detected**, defer process discipline to risk-tiers; the harness covers only code style + conventions.

## Outputs
- `CLAUDE.md` (baseline marker block + framework conventions summary) · rules (the 5 baseline +
  `<framework>-conventions.md` — inside it, put operational directives 1-3 lines each under the `<!-- ops-conventions -->`
  anchor section, with the flesh linked to docs/code-style. **Do not create new marker blocks**)
- If needed, a skill / agent (authoring guide enforced, with companion folders references/examples) — **command excluded**
- Technical docs (folders by category, `tech-doc-guide.md` discipline):
  `docs/README.md` · `docs/srs/README.md` (greenfield) · `docs/sds/README.md` (Mermaid) ·
  `docs/code-style/README.md` + `docs/code-style/<stack>.md` · `docs/research/` (incorporated) · `docs/onboarding/README.md` ·
  `docs/verification/performance.md` (performance SSOT per confirmed stack — stack section + shared API load section, no empty stack sections) ·
  `docs/verification/integration.md` (integration-verification SSOT per confirmed stack — stack section + shared E2E section, no empty stack sections) ·
  `docs/operations/commit-versioning-guide.md` (Conventional Commits + SemVer + release-tool setup for the detected stack · 0.x policy —
  always generated regardless of whether flow is detected; authoring guidance: `references/commit-versioning-guide.md`)

## Generation Procedure
1. Take the detect results + research results (`.harness/research/*.md`) + user choices.
2. For each output, clone the corresponding `templates/*.template.md` and fill placeholders (there is no command template).
3. Read the 5 mandatory rule blocks from `references/` and merge them into the CLAUDE.md block (preserve anchors). Do
   **not** put the `harness:baseline` BEGIN/END lines into the marker_upsert content — body only (apply wraps it).
4. Fill the technical docs following the folder structure and authoring order of `tech-doc-guide.md`
   (SRS → research incorporation → SDS → code-style → onboarding → docs/README). Source links are mandatory; no
   speculation. SRS is greenfield only. If you generate a skill, add companion folders (references/examples) per the
   `skill-writing-guide.md` discipline. Generate `commit-versioning-guide` under `docs/operations/` using the
   `references/commit-versioning-guide.md` guidance (harness-rules 13-1 · 13-2 — regardless of whether flow is detected;
   defer tier/commit discipline to risk-tiers).
5. **Operational directive/standard separation (9-3 · 9-4)**: take the research operational-axes section, place a
   `<!-- ops-conventions -->` anchor in the rule `<framework>-conventions.md`, and under it write per-axis directives at
   **≤ 3 lines each** (a category instruction + a `docs/code-style/<stack>.md#<axis>` link). Concrete standard names,
   details, sources, and alternatives go in the operational-concerns section of docs/code-style, not in the rule. For
   greenfield, the rule carries only the category.
6. Collect everything into a `plan` (files[]), validate with `harness_scaffold.py validate`, then pass it to `apply`
   (after preview).
