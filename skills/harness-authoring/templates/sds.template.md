# {{PROJECT_NAME}} Software Design Specification (SDS)

## Stack / Framework
{{FRAMEWORK}} {{VERSION}} — {{STACK_SUMMARY}}  <!-- Sources: {{SOURCES}} -->

## Structure Diagram
```mermaid
{{MERMAID_DIAGRAM}}
```
<!-- Component/module relationships (at least 1). Only turn confirmed facts into nodes (no speculative nodes). Add a data-flow diagram if possible. -->

## Folder Structure
{{FOLDER_MAP}}

## Module Overview
<!-- Take each node in the structure diagram down one level into an implementation unit (architecture = nodes, SDS = the nodes' contracts).
     Confirmed facts only — no speculation. If there are class/type details, include them in the interface (no separate section).
     If it is a single module, list only 1 (YAGNI).
     **Decomposition axis**: for procedural, data-pipeline, or functional projects, use processing stages / data flow
     as the primary unit instead of modules (rename to "processing stages" and list in flow order). Use modules only for projects where module boundaries are natural. -->
#### {{MODULE_NAME}}
- Implemented requirements: [FR-001](../srs/README.md#fr-001)  <!-- The SRS FRs this module satisfies (link via each FR anchor, serving as the standard Requirements Matrix). **For brownfield (no SRS generated), omit this field. Infrastructure/cross-cutting modules (logging, config, DB adapters) get "no FR mapping"** — no forced mappings or dead links. -->
- Responsibility: {{MODULE_RESPONSIBILITY}}  <!-- One sentence. Single responsibility — if an "and" appears, consider splitting. -->
- Provided interface: {{MODULE_PROVIDED_IF}}  <!-- The public API/functions/endpoints exposed externally (input→output, errors). Omit internal-only ones. -->
- Required interface: {{MODULE_REQUIRED_IF}}  <!-- The external contracts needed to operate (= concretization of dependencies). Both other internal modules and external systems (third-party APIs, services, DBs, message brokers, etc.). If none, "none". -->
- Owned data: {{MODULE_DATA}}  <!-- Core data structures/tables it owns/mutates. If not applicable, "N/A". -->

## Data Design
<!-- Write only when there is a DB/persistent store. If none, omit this section (YAGNI). Schema details are owned by code/migrations
     as the SSOT — here, only module↔data linkage, transaction boundaries, and key entity relationships (no duplication). -->
{{DATA_DESIGN}}

## UI Flow
<!-- Write only when there is a UI. If none, omit this section (YAGNI). Screen transitions, states, key actions. Do not include screenshots (flow only). -->
{{UI_FLOW}}

## Integration Points (contracts between components)
<!-- Write only when there are component pairs that communicate across a boundary (process/origin/host/auth). For a single process, omit this section (YAGNI). -->
{{INTEGRATION_CONTRACTS}}
<!-- For each communicating pair: reachability (does the hostname/route resolve in the deployment topology) · identity/origin (do issuer and origin
     match from both the browser's and the internal perspective) · policy continuity (do security headers/CSP not block the declared flow, and are they preserved across all response
     paths) · credential provisioning (is an app-specific account created) · global-config blast radius (does a global policy not constrain the
     declared heavy path against intent). Confirmed facts only, with source links. -->

## Stack Reconcile Decisions
<!-- The SSOT for design rationale (harness-rules 10-1). One line each for the stacks (including infrastructure) promoted/rejected in research, with reasons —
     a version-controlled decision outlet (only the core decisions as a doc, not a duplicate of the gitignored `.harness/rationale.md`).
     If there are no promotions/rejections, omit this section. -->
{{STACK_RECONCILE}}
