<!-- Wiki front matter for this doc. Fill every {{…}} below, then delete this comment line
     so the "---" that follows becomes the literal first line of the generated file
     (wiki_graph.py only recognizes front matter starting at byte 0 — leaving this comment
     in place keeps the file harmlessly outside the wiki, same as a plain markdown file). -->
---
# wiki_id: derive mechanically from this file's output path relative to the wiki root, the
# same way wiki-init Step 5 does (e.g. docs/srs/README.md -> srs.readme). Never hand-pick a
# slug — this file is the project's single SRS index; a mechanical id keeps it aligned
# with every other generated doc's id instead of one guessed by hand.
wiki_id: {{ID}}
title: SRS Index
tags: [srs]
# sources is optional — requirements rarely map to specific code paths; uncomment only if
# this SRS genuinely does, else leave it deleted.
# sources:
#   src/path/to/code.py: null
---
# {{PROJECT_NAME}} Software Requirements Specification (SRS)

> The SSOT for what the system must do (requirements). Write this first. Sources: {{SOURCES}}
>
> **This file is the index**: it holds the sections common to the whole SRS — overview, goals,
> users and roles, customer requirements, non-functional requirements, constraints. §5
> Functional Requirements lives one file per requirement area (`<area>.md`, cloned from
> `srs-area.template.md`) — see the area index at §5.
>
> **Split into two levels**: customer requirements (§4) need not be measurable, but must clearly state what is wanted
> ("would be nice if it were convenient" ✗ → "supports cards and simple/express payment" ✓). Functional requirements (§5, FR) must be measurable and single-interpretation
> ("fast" ✗ → "p95 < 200ms" ✓). If something is ambiguous or unknown, do not invent it — mark it `needs confirmation` (harness-rules 8-1).

<!-- Ids are issued, never chosen — by a human or a model:
     python3 .claude/harness-tier/scripts/srs_check.py --next-id <file> --kind <KIND> [--scope <axis>]
     An area file's ids carry its stem; this index's ids carry no area. The KIND set is open —
     it is whatever a document already anchors. -->

## 1. Overview / Purpose
{{PRODUCT_PURPOSE}}

## 2. Goals / Non-goals
- Goals: {{GOALS}}
- Non-goals (YAGNI): {{NON_GOALS}}

## 3. Users / Scenarios
{{USERS_AND_SCENARIOS}}  <!-- List classified by user role (linked to the permission axis in §5).
                              If there is a single role, state "N/A — single user". -->

### 3.1 User Role Classification
{{USER_ROLES}}  <!-- One line per role, each with an `<a id="role-xxx">` anchor and covering its
                     responsibilities and access scope. An area file's §5 links a role anchor
                     only when its level-2 axis IS that role — a sub-area axis gets plain text,
                     since a forced link invents a role that does not exist. Format —
                     - <a id="role-001"></a>**Admin** Full access; manages billing and users.
                     If there is no role distinction, state "N/A — reason". -->

## 4. Customer Requirements (C, non-measurable)
<!-- State clearly what the customer/stakeholder wants — measurable acceptance criteria and implementation approach belong to §5 FR and the SDS.
     No vague sentiments ("would be nice if it were convenient"); be explicit about what will be provided. Give each C an `<a id="c-xxx">` anchor
     so an area file's §5 FR can back-reference it with `(← [C-xxx](README.md#c-xxx))` (the origin of customer-requirement→FR traceability).
     If there is no external customer/stakeholder (personal/internal tool), leave "N/A — single stakeholder" and go straight to §5 (no empty ceremony). -->
{{CUSTOMER_REQUIREMENTS}}
<!-- Format — - <a id="c-001"></a>**C-001** Payment supports cards and simple/express payment. -->

## 5. Functional Requirements
<!-- One file per requirement area, cloned from srs-area.template.md. The file stem IS the
     area key, and every FR in it carries that stem uppercased. Splitting here rather than
     later is deliberate: the SDS links each FR anchor, so a split after the fact breaks
     those links. -->
{{AREA_INDEX}}
<!-- Format — - [Payment](payment.md) — card and express payment -->

## 6. Non-functional Requirements
<!-- Fixed sub-axes (aligned to ISO/IEC 25010). For each axis give a **priority [P0/P1/P2]** and a **measurable, verifiable
     criterion** ("fast" ✗ → "p95 < 200ms" ✓), or leave "N/A — reason" (no blanks). Each axis carries an `<a id="nfr-xxx">` anchor
     so the SDS "NFR Realization" section can back-trace which design satisfies it (the requirement→design→verification chain).
     **How a criterion is verified is owned by `docs/verification/*` (performance.md · integration.md) as SSOT — link there;
     do not restate the procedure here (no duplication). -->

### 6.1 <a id="nfr-perf"></a>Performance
{{NFR_PERFORMANCE}}  <!-- [P0/P1/P2] Throughput, latency (p50/p95), concurrency.
     Verify → docs/verification/performance.md. Format —
     - <a id="nfr-perf-001"></a>**NFR-PERF-001** [P0] p95 < 200ms at 100 rps.
     The section anchor is the axis; the item anchor is the individual requirement. An axis
     added as §6.8 yields NFR-<its stem>-NNN with no other change. -->

### 6.2 <a id="nfr-security"></a>Security
{{NFR_SECURITY}}  <!-- [P0/P1/P2] Authentication/authorization, encryption, secrets, vulnerability criteria. -->

### 6.3 <a id="nfr-availability"></a>Availability / Reliability
{{NFR_AVAILABILITY}}  <!-- [P0/P1/P2] SLA, recovery objectives (RTO/RPO), fault tolerance. -->

### 6.4 <a id="nfr-scalability"></a>Scalability
{{NFR_SCALABILITY}}  <!-- [P0/P1/P2] Response to increased load, horizontal/vertical scaling criteria. -->

### 6.5 <a id="nfr-accessibility"></a>Accessibility
{{NFR_ACCESSIBILITY}}  <!-- [P0/P1/P2] WCAG level, etc. If there is no UI, "N/A". -->

### 6.6 <a id="nfr-maintainability"></a>Maintainability
{{NFR_MAINTAINABILITY}}  <!-- [P0/P1/P2] Test coverage, documentation, module boundary criteria. -->

### 6.7 <a id="nfr-compatibility"></a>Compatibility
{{NFR_COMPATIBILITY}}  <!-- [P0/P1/P2] Supported OS/browser/runtime, API version policy. -->

## 7. Constraints / Assumptions
<!-- Environment, technology, and regulatory constraints imposed on the system from the
     outside, not something the system performs. A data-retention or PII rule is
     measurable, so it belongs in §5 as an FR instead ("PII is purged 90 days after
     account deletion. Acceptance: 0 rows older than 90d"). An externally mandated
     interface belongs here — "must integrate via legacy system X's SOAP API v1.2" is
     imposed from outside, not performed by the system, and stating it as an FR leaves
     it with no acceptance criteria. Give each item an `<a id="con-xxx">` anchor. -->
{{CONSTRAINTS_ASSUMPTIONS}}
<!-- Format — - <a id="con-001"></a>**CON-001** Must integrate via legacy system X's SOAP API v1.2. -->
