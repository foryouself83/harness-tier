# Technical Documentation Authoring Guide

The discipline `harness-authoring` follows when generating technical documentation for the host project.

## Folder Structure (by category)

Place docs in category folders and make the entry document `README.md` (friendly to GitHub folder rendering).

```text
docs/
  README.md                  overall index · written last · links EVERY category below (incl. verification/ · operations/)
  srs/README.md              functional/non-functional requirements · greenfield only · written first
  sds/README.md     structure + Mermaid structure diagram (required)
  code-style/
    README.md                stack index + shared principles
    <stack>.md               per-stack conventions (no snippets)
  research/
    README.md                research summary index
    <topic>.md               incorporated from .harness/research/ (source links)
  verification/
    performance.md           per-stack performance SSOT (consumed by /performance)
    integration.md           per-stack integration-verification SSOT (consumed by /integration)
  operations/
    commit-versioning-guide.md  Conventional Commits · SemVer · release-tool setup
  onboarding/README.md       run/debug + key doc links · written last
```

**Authoring order**: `SRS → research incorporation → SDS → code-style → onboarding → docs/README`.
research is the **input (evidence) for SDS and code-style, so incorporate it first** (so that both docs
can link to the already-incorporated `docs/research/` as their source).
**Respect existing `docs/` conventions**: if a different structure already exists (`documentation/`, etc.), prefer that and only add the missing categories.
**SRS is greenfield only** — do not create an SRS for brownfield.
**Source-link obligation** — every doc links the research docs/external URLs it references as markdown links. If there is no basis, mark it "source unverified".

## SSOT Separation (no duplication)

- **Structural conventions** (folder/schema locations) → `.claude/rules/<framework>-conventions.md` (rule).
- **Behavioral guidance** (naming·formatting·best practices·anti-patterns·toolchain config) → `docs/code-style/<stack>.md` (doc).
- The rule points to the doc but does not copy its content.

## SRS (greenfield) — srs/README.md

Fill in `srs.template.md`. Fill it with the **scope summary (the scope summary from harness-init Step 1-0) as the SSOT** and
reinforce it with research. Do not guess unknown slots — leave them as "needs confirmation" (harness-rules 8-1 — resolve not only
blanks but also ambiguous items via questions before writing). **Separate into two levels**: customer needs (§4) must be clear about what
is wanted even if not measurable ("would be nice if it were convenient" ✗ → "support cards·simple payment" ✓), while functional requirements (§5, FR) must be measurable and single-interpretation.

**Hierarchical classification (fixed schema)**:
- **Customer needs (§4)** — express what customers/stakeholders want as `C-x`. Give each C an `<a id="c-xxx">` anchor. §5 FRs
  back-reference via `(← [C-x])`, making this the source of customer-need→FR traceability. **If there are no external customers/stakeholders (personal·internal tools),
  leave it as "not applicable — single stakeholder" and omit it (no empty ceremony)**.
- **Functional requirements (§5)** — `domain (1st) > user role/sub-area (2nd) > individual FR (3rd)`. Each FR is
  `ID · description · priority (P0/P1/P2) · acceptance criteria (measurable)`, and **give each FR an `<a id="fr-xxx">` anchor so
  the SDS module overview can back-trace to it via a link**. If there is an originating customer need, back-reference via `(← [C-x])`. Do not delete
  axes that do not apply — mark them "not applicable — reason".
- **Non-functional requirements (§6)** — fixed sub-axes aligned to ISO/IEC 25010: performance·security·availability·scalability·accessibility·maintainability·compatibility.
  Each axis gets a **priority [P0/P1/P2]** + a quantitative criterion (or "not applicable — reason", no blanks) + an `<a id="nfr-xxx">` anchor, so the
  SDS "NFR Realization" section can back-trace it. **The verification procedure is owned by `docs/verification/*` (SSOT) — link it, do not restate it here.**
- **Data requirements (§7)** — requirements ABOUT data (retention/deletion policy, GDPR/PCI-DSS/PII handling, classification/ownership, integrity, volume/growth),
  NOT the schema/ERD (that is SDS Data Design). `<a id="dr-xxx">` anchors. Stateless / no regulated data → "not applicable — reason" (YAGNI).
- **External interface requirements (§8)** — external interfaces the system MUST conform to as a constraint (mandated legacy API/protocol/data format, third-party
  SLA/rate limits), NOT the internal integration design (that is SDS Integration Points). `<a id="eir-xxx">` anchors. None mandated → "not applicable — reason" (YAGNI).
- **Users/scenarios (§3)** — classify by user role and connect it to the permission axis of the features.

## SDS — sds/README.md

Stack/versions + folder structure + **Mermaid structure diagram (required, at least 1)** + module overview.
Turn only confirmed facts into nodes (no speculative nodes). Add a data-flow diagram where possible.
**Module overview**: step each node of the structure diagram down one level into an implementation unit and record `implementation requirements·responsibility (single)·provided interfaces·
used interfaces·owned data` (architecture = nodes, SDS = the nodes' contracts). **Implementation requirements back-trace to the SRS FRs this module
satisfies via markdown links** — to the SRS FR anchor as `[FR-xxx](../srs/README.md#fr-xxx)`
(kept paired with the SRS `<a id="fr-xxx">` anchor, serving as the standard Requirements Matrix). **However, brownfield (no SRS generated)
omits this field, and infrastructure/cross-cutting modules (logging·config·DB adapters) are left as "no FR mapping"** (no forced mapping·no dead links).
Provided/used interfaces follow the UML provided/required split — provided = the contract exposed to the outside, used = the external
contract needed to operate (other internal modules + external systems, = the concretization of dependencies). **Decomposition axis**: procedural·data-pipeline·functional projects use
processing stages·data flows as the primary unit instead of modules. Class/type details are absorbed into interfaces. If it is a single module, keep just one (YAGNI).
**NFR Realization (requirement→design→verification bridge)**: FRs are traced per-module via "Implemented requirements"; NFRs are traced in a dedicated
`## NFR Realization` section — map each measurable SRS §6 NFR (`#nfr-xxx`) to the module/design decision that satisfies it, plus a link to the verification
SSOT (`docs/verification/*`). Cross-cutting NFRs need not bind to one module. Brownfield (no SRS) or no measurable NFR → omit (YAGNI).
**Requirements Coverage (bidirectional check)**: close the one-way module→FR link with a `## Requirements Coverage` section confirming every SRS FR is
implemented by ≥1 module and every measurable NFR is realized, listing any unmapped FR/NFR as an explicit gap (never a silent drop). Brownfield → omit.
**Data design (only when there is a DB)**: only module↔data linkage·transaction boundaries. Schema details are owned by code/migrations as
SSOT — do not duplicate. If there is no DB, omit the section (YAGNI). **UI flow (only when there is a UI)**: screen transitions·state·key actions
(no screenshots, flow only). If there is no UI, omit. **Do not place exception handling·error handling in the SDS** —
the error-handling sub-section of `docs/code-style/<stack>.md` is the SSOT (9-1), no duplication.
**Integration points (multiple components)**: when components communicate across a boundary (process/origin/host/auth), specify the per-communication-pair contract in an `## Integration Points`
section — reachability (host/route resolution)·identity/origin match (issuer·CORS)·policy
continuity (security headers/CSP do not block the flow and are preserved across all response paths)·credential provisioning·global-config blast radius.
Reflect the integration requirements provided by research and cite sources. **Omit for a single process** (YAGNI — do not invent boundaries that do not exist).
**Stack reconcile decision section** (harness-rules 10-1): leave one line each for stacks (including infrastructure) promoted/rejected in research, with reasons — a
version-controlled decision outlet (not a duplicate of the gitignored `.harness/rationale.md`, but only its key
decisions as a doc). If there are no promotions/rejections, omit the section.
**Module splitting (conditional)**: the default is a single `sds/README.md` file. Only large projects with a confirmed multiplicity of modules split into `sds/<module>.md`,
where the shared `README.md` keeps only the index + overall structure diagram + integration/reconcile, and the module overview body is owned by the module file as
SSOT (no duplication on either side). If greenfield modules are not yet confirmed early on, do not split (no premature lock-in — confirm during implementation, then split).

## code-style — code-style/README.md + <stack>.md

- Split files per stack. Filename = `<language>` or `<language>-<framework>` (or platform).
  E.g. `typescript-react.md`·`python-fastapi.md`·`go.md`. **Split even for the same language when the framework/platform
  differs** (the emphasis differs, so bundling into one file makes both shallow). **If infrastructure has real conventions, give it a stack
  file too** (e.g. `docker.md`·`postgresql.md`·`github-actions.md`) — including stacks promoted via the Step 2.5 reconcile
  (harness-rules 9-6). The target is not the initial stack_map but **the entire reconcile-confirmed set**.
- Each `<stack>.md` writes naming·formatting·imports / **best practices organized by quality lens** / anti-patterns (including reinventing the wheel) /
  toolchain config / reuse candidates **in detailed prose**. **Do not include code snippets**.
- **Best Practices by quality lens (harness-rules 9-7 · 9-8)** — structure the Best Practices section into per-lens sub-sections
  (correctness · UX · accessibility · performance · security · maintainability/testability · cross-cutting/integration · i18n),
  **emitting only the lenses that apply to the stack** (9-2 — no UX/a11y on a headless backend, no cross-cutting on a single process; uncertain →
  ask in the preview, never fabricate). Each lens holds the *coding* guidance only and **links** the SSOT that owns the rest (perf tools →
  `docs/verification/performance.md`; integration contract → `docs/sds` Integration Points; security enforcement → the ops-conventions rule +
  scanner) — no duplication.
- **Toolchain config as one set** — describe together the mutual consistency of the build runner·compiler·bundler·type checker·linter·test runner (e.g. `tsc -b` (references) ↔
  bundler include scope). With the official authoring for the detected version, and its source.
- **Specify the pre-check tool list (required)** — `/flow-init` references this SSOT when drafting the `flow-config.modules[].checks`
  draft. Within the toolchain config section, specify the following axes **per language/stack**:
  - **lint**: code-quality linter (e.g. ruff, eslint, golangci-lint)
  - **format**: formatter (e.g. ruff format, prettier, gofmt)
  - **typecheck**: type-checking tool (e.g. mypy, tsc --noEmit, go build)
  - **import_lint**: import-ordering tool (e.g. isort, import-sort, goimports) — "not applicable" if none
  - **security**: static security scanner (e.g. bandit, semgrep, govulncheck) — "not applicable" if none
  - **test runner**: test execution command (e.g. pytest, vitest, go test)

  For each tool, record together the **currently recommended version (confirmed by research)·execution command·config file location**. Without this list,
  `/flow-init` would rely on inference for the draft checks, so it must be specified.
- **Folder structure (specify tests/ location)** — describe together in the toolchain config section the test folder location·convention (e.g. whether `tests/unit/`·`tests/integration/` are separated,
  filename patterns `test_*.py`·`*.test.ts`). If there are multiple modules, specify each module's
  tests/ location (e.g. `packages/<module>/tests/`). `/flow-init` uses this information when matching module boundaries to test
  paths.
  However, **this item is guidance (an SSOT record), not gate enforcement** — enforcement is flow's job (harness-rules 14-1).
- **Base it on currently recommended tools** — for tools like package managers·build, record **what is recommended now** as
  confirmed by research, not the learned past standard (ecosystem standards move — do not revert to inertial defaults).
- `code-style/README.md` keeps only the stack list links + shared principles (source attribution, etc.).
- **Operational-concern sections** (9-1~9-4): give each `<stack>.md` a sub-section per operational axis (`## error-handling`, etc.). The
  sub-section holds the **adopted standard (recommended default/detected)·mapping·anti-patterns·examples·alternatives** and the **source URL (SSOT)**. Mark a greenfield
  unconfirmed standard as "recommended (subject to change)". Structural directives (rules) are not copied here; the rule links to this section
  by anchor (`#error-handling`). Emit only the axes that actually exist for that stack (9-2).

## research — research/README.md + <topic>.md

Refine `.harness/research/*.md` to be human-readable (adding source links) and incorporate them into `docs/research/`.
`research/README.md` is a summary index of the research items. **When another doc links to research as a source, point to the incorporated
location `docs/research/` — never put the gitignored evidence `.harness/` path into deliverables**
(after incorporation, the `.harness/research/` copy is cleaned up by init, so `.harness/` links break).

## onboarding — onboarding/README.md (last)

Run/debug + a **"key doc links for newcomers"** section (links to SRS·SDS·code-style·research).
When flow is detected, defer commit·PR discipline to risk-tiers (no duplication here). Write it last, after all other docs are done.

## performance — docs/verification/performance.md

Generated by consuming the `### Performance SSOT (per stack)` section of harness-researcher.

- **Purpose**: the per-stack performance SSOT that the `/performance` skill consumes first. Falls back to the skill's built-in references when absent.
- **Structure**:
  - Per-stack section (`## <stack>`) — N+1 detection tools·profilers·static complexity·query-plan procedures·source links.
    Write confirmed stacks only; no empty sections.
  - Shared API-load section (`## API Load (common)`) — openapi-to-k6+k6 (AGPL-3.0) first choice /
    MIT fallback (oha/autocannon/vegeta) / report standard (p50/p95/p99·SLO PASS/FAIL·Four Golden Signals).
  - Link sources to `docs/research/`. No direct `.harness/` path references.

## integration — docs/verification/integration.md

Generated by consuming the `### Integration-verification SSOT` section of harness-researcher.

- **Purpose**: the integration-verification SSOT that the `/integration` skill consumes first. Falls back to the skill's built-in references when absent.
- **Structure**:
  - Per-stack section (`## <stack>`) — for web, Playwright config (testDir/testMatch·`--reporter=json`);
    for non-web, human-in-the-loop + reference OSS (Newman/Maestro/Appium). Confirmed stacks only; no empty sections.
  - Shared E2E section (`## E2E (common)`) — with 0 cases, no arbitrary generation·report to a human, playwright MCP as an auxiliary path.
  - Link sources to `docs/research/`.

## Shared Discipline

- **Source attribution** — cite the research/scan basis. If none, "source unverified".
- **Concise** — 1-2 lines per item. Concrete over verbose.
- Docs are read by both humans and agents — make them clear and scannable.
