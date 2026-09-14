<!-- Wiki front matter for this doc. Fill every {{…}} below, then delete this comment line
     so the "---" that follows becomes the literal first line of the generated file
     (wiki_graph.py only recognizes front matter starting at byte 0 — leaving this comment
     in place keeps the file harmlessly outside the wiki, same as a plain markdown file). -->
---
# wiki_id: derive mechanically from this file's output path relative to the wiki root, the
# same way wiki-init Step 5 does (e.g. docs/srs/payment.md -> srs.payment). Never hand-pick a
# slug — this template is cloned once per requirement area, and a hand-picked value repeated
# across clones collides on id.
wiki_id: {{ID}}
title: <requirement area>
tags: [srs]
# related is what keeps this file out of the orphan list: wiki_graph.py reaches nodes from
# the index, and an area file nothing points at is unreachable however complete it is. The
# target is the SRS index's own mechanical id (docs/srs/README.md -> srs.readme under the
# default wiki root). Uncomment it once that README carries front matter of its own — an
# edge to a document that is no node dangles, and a dangling edge blocks the commit gate
# where an orphan only warns.
# related:
#   - srs.readme
# sources is optional — requirements rarely map to specific code paths; uncomment only if
# this SRS genuinely does, else leave it deleted.
# sources:
#   src/path/to/code.py: null
---
# {{AREA_TITLE}} Functional Requirements

> One requirement area of [the SRS](README.md). Common sections — purpose, goals, users
> and roles, customer requirements, non-functional requirements, constraints — live there.

## 5. Functional Requirements
<!-- Hierarchical classification (fixed schema): domain (level 1) > user role/sub-area
     (level 2) > individual FR (level 3). Level 2 links a role anchor only when the axis IS
     a role — a sub-area gets plain text, since a forced link invents a role that does not
     exist. Each FR has measurable acceptance criteria. -->

### 5.1 {{DOMAIN_A}}
#### 5.1.1 {{ROLE_OR_SUBAREA_A}}
{{FR_LIST_A}}
<!-- Format —
     - <a id="fr-payment-001"></a>**FR-PAYMENT-001** [P0/P1/P2] (← [C-003](README.md#c-003))
       Description. Acceptance criteria: <measurable, verifiable condition>.
     The area prefix is this file's stem uppercased, and the number comes from
     `srs_check.py --next-id <this file> --kind FR`. The back-reference crosses files
     because customer requirements live in README — omit it when there is no originating
     one. If ambiguous or unknown, state "needs confirmation" in the acceptance criteria. -->
