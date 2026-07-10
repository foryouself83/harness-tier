# {{PROJECT_NAME}} Software Requirements Specification (SRS)

> Greenfield only — the SSOT for what the system must do (requirements). Write this first. Sources: {{SOURCES}}
>
> **Split into two levels**: customer requirements (§4) need not be measurable, but must clearly state what is wanted
> ("would be nice if it were convenient" ✗ → "supports cards and simple/express payment" ✓). Functional requirements (§5, FR) must be measurable and single-interpretation
> ("fast" ✗ → "p95 < 200ms" ✓). If something is ambiguous or unknown, do not invent it — mark it `needs confirmation` (harness-rules 8-1).

## 1. Overview / Purpose
{{PRODUCT_PURPOSE}}

## 2. Goals / Non-goals
- Goals: {{GOALS}}
- Non-goals (YAGNI): {{NON_GOALS}}

## 3. Users / Scenarios
{{USERS_AND_SCENARIOS}}  <!-- List classified by user role (linked to the permission axis in §5).
                              If there is a single role, state "N/A — single user". -->

### 3.1 User Role Classification
{{USER_ROLES}}  <!-- e.g. admin / regular user / guest. One line per role covering its responsibilities and access scope.
                     If there is no role distinction, state "N/A — reason". -->

## 4. Customer Requirements (C, non-measurable)
<!-- State clearly what the customer/stakeholder wants — measurable acceptance criteria and implementation approach belong to §5 FR and the SDS.
     No vague sentiments ("would be nice if it were convenient"); be explicit about what will be provided. Give each C an `<a id="c-xxx">` anchor
     so §5 FR can back-reference it with `(← [C-x])` (the origin of customer-requirement→FR traceability).
     If there is no external customer/stakeholder (personal/internal tool), leave "N/A — single stakeholder" and go straight to §5 (no empty ceremony). -->
{{CUSTOMER_REQUIREMENTS}}
<!-- Format — - <a id="c-1"></a>**C-1** Payment supports cards and simple/express payment. -->

## 5. Functional Requirements
<!-- Hierarchical classification (fixed schema): domain (level 1) > user role/sub-area (level 2) > individual FR (level 3).
     Use level-1 axes (domains) that fit the nature of the project, but do not delete an axis that does not apply —
     leave "N/A — reason" (to distinguish it from an omission). Each FR has measurable acceptance criteria. -->

### 5.1 {{DOMAIN_A}}  <!-- Level 1: domain/functional area -->
#### 5.1.1 {{ROLE_OR_SUBAREA_A}}  <!-- Level 2: user role or sub-area -->
{{FR_LIST_A}}
<!-- Level 3: requirement items. Give each FR an `<a id="fr-xxx">` anchor so the SDS can trace back to it via a link (required). Format —
     - <a id="fr-001"></a>**FR-001** [P0/P1/P2] (← [C-1](#c-1)) Description. Acceptance criteria: <measurable, verifiable condition>.
     If there is a source customer requirement, back-reference it with `(← [C-x])` (omit if none). If ambiguous/unknown, state "needs confirmation" in the acceptance criteria. -->

### 5.2 {{DOMAIN_B}}
{{FR_LIST_B}}

## 6. Non-functional Requirements
<!-- Fixed sub-axes (aligned to ISO/IEC 25010). For each axis give a **priority [P0/P1/P2]** and a **measurable, verifiable
     criterion** ("fast" ✗ → "p95 < 200ms" ✓), or leave "N/A — reason" (no blanks). Each axis carries an `<a id="nfr-xxx">` anchor
     so the SDS "NFR Realization" section can back-trace which design satisfies it (the requirement→design→verification chain).
     **How a criterion is verified is owned by `docs/verification/*` (performance.md · integration.md) as SSOT — link there;
     do not restate the procedure here (no duplication). -->

### 6.1 <a id="nfr-perf"></a>Performance
{{NFR_PERFORMANCE}}  <!-- [P0/P1/P2] Throughput, latency (p50/p95), concurrency. Verify → docs/verification/performance.md. -->

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

## 7. Data Requirements
<!-- Requirements ABOUT data — NOT the schema/ERD (that is design → SDS Data Design). State retention/deletion policy, regulatory
     constraints (GDPR/PCI-DSS/PII handling), data classification/ownership, integrity/consistency, volume/growth. Give each a
     `<a id="dr-xxx">` anchor so the SDS can trace back. If the system is stateless / holds no regulated data, leave "N/A — reason" (YAGNI). -->
{{DATA_REQUIREMENTS}}
<!-- Format — - <a id="dr-1"></a>**DR-1** [P0] PII is purged 90 days after account deletion. Acceptance: 0 rows older than 90d. -->

## 8. External Interface Requirements
<!-- Requirements ABOUT external interfaces the system MUST conform to (a constraint), NOT the internal integration design
     (that is SDS Integration Points). e.g. "must integrate via legacy system X's SOAP API v1.2", mandated protocols/data formats,
     third-party SLA/rate limits. Give each an `<a id="eir-xxx">` anchor. If none is mandated, leave "N/A — reason" (YAGNI). -->
{{EXTERNAL_INTERFACE_REQUIREMENTS}}

## 9. Constraints / Assumptions
{{CONSTRAINTS_ASSUMPTIONS}}
