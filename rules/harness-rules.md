# Harness Generation Rules

> This rule is NOT auto-injected (unlike risk-tiers.md). It is the SSOT that the
> `/harness-init` and `harness-authoring` skills defer to and read at run time.

## Safety
1. **Verify → plan → preview → confirm → write.** No file is written before it is previewed and confirmed.
2. **No overwriting.** Existing files get only marker-block upserts (a dedicated region). Creation happens only when the file is absent.
3. **harness-init does not commit** (that is /flow's responsibility).
4. **When ambiguous, ask** (Karpathy). If the framework cannot be detected or there is a conflict, ask the user.
4-1. **Merged-copy cleanup**: after a successful apply, remove the intermediate copies that were merged into docs (`.harness/research/`, etc.)
   with `harness_scaffold.py cleanup`. Audit evidence (`plan.json`, `manifest.json`,
   `critic-report.json`, `rationale.md`) is preserved. FAIL-OPEN (a cleanup failure does not block the flow).
   **Link guard (FAIL-SAFE)**: document source links point at the merged location `docs/research/` and do not
   reference `.harness/`. Before removing, cleanup checks whether docs reference `.harness/research`, and if a
   reference exists it holds off on removal and warns (to avoid broken links).

## Deliverables
5. **`.md` by default**; real configuration (bandit, CI, pre-commit, real folders, actual `==` pins) is opt-in per item.
5-1. **Skill helper folders**: when creating a skill, if its role warrants references/examples, include `references/`·`examples/` alongside it (YAGNI — not forced for simple skills).
6. **The five mandatory rules are always injected**: Karpathy's 4 principles + DRY/constants + `==` version pinning + security + **reuse-first**
   ([rule-reuse-first.md](../skills/harness-authoring/references/rule-reuse-first.md)).
   **Load-path guarantee** — CLAUDE.md body / explicit import (`.claude/rules/` alone is not enough). The anchor `<!-- rule:<key> -->`
   (key: `karpathy`·`dry-constants`·`version-pinning`·`security`·`reuse-first`) is **owned by the claude-md template** and
   placed before each rule slot in the baseline marker block. Do not put anchors in the rule reference body files (no duplication).
7. **No duplicate generation**: check for functional duplication by name+description.
8. **Technical docs (folders by category)**: `docs/README.md` (overall index, done last) · `docs/srs/` (functional/non-functional
   requirements, greenfield-only, done first) · `docs/sds/` (structure + **Mermaid required**; when a component communicates
   across a boundary (process/origin/host/auth), include an **integration-point contract** section) ·
   `docs/code-style/` (per-stack `<stack>.md`, no code snippets, one toolchain-config set) ·
   `docs/research/` (merged in, source links) · `docs/onboarding/` (run/debug + links to key docs, done last) ·
   `docs/verification/performance.md` (per-stack performance SSOT — N+1 · profiler · query plan · API load; confirmed stacks only, no empty sections) ·
   `docs/verification/integration.md` (per-stack integration-verification SSOT — web = Playwright · non-web = human-in-the-loop; confirmed stacks only, no empty sections).
   The entry document is `README.md`. Structural conventions are rules, behavioral style is docs — **one fact, one place**.
   **Every document cites its reference sources as links.**
8-1. **SRS scope-clarification gate (greenfield-only, no guessing)**: for greenfield/SRS deliverables, parse the received prompt
   **before** research and SRS writing to fix the development scope. For the SRS's mandatory slots (purpose · goals/non-goals · core functional
   requirements · target users/scenarios · key constraints), ask about **every blank + ambiguous item** via `AskUserQuestion` —
   **ambiguous = unmeasurable · multiply interpretable · scope unclear** (e.g. "fast" · "user-friendly"). Keep asking **until it is measurable
   and single-interpretation**, but do not re-ask what is already clear (ambiguity is a sign of incomplete requirements analysis —
   resolve it at the SRS stage). Additionally, fix what the **classification axes** are (domain etc. as primary; user roles/subdomains etc. as secondary) and the **depth
   (2nd–3rd level)** — ask which axes apply, and for axes that do not apply, do not delete them from the SRS but leave them as "N/A — reason"
   (distinguishing them from omissions — isomorphic to 9-2). If still unknown after asking, mark it "needs confirmation" in the SRS
   (no fabrication — rule 4). The produced **scope summary** is the single input source for research · rationale · SRS. Brownfield skips
   this gate and uses code-analyzer's code analysis as its scope (only intent that code cannot resolve becomes a selective question).
9. **No command generation**: no deliverable is created under `.claude/commands/` (revfactory alignment).

## Operational conventions

9-1. **Operational-concern checklist (no omissions · open list)**: for the detected stack, researcher/
   code-analyzer **review all** of the following *concern axes* (language/framework agnostic). It is not a closed floor
   but a **common set of starting axes** — researcher adds more per the stack's characteristics.
   Error/exception handling · logging (debugging-oriented: level rules · debugging context · structured/searchable · no secrets/PII) ·
   configuration · secrets · env · observability (metrics/tracing) · health check/readiness · graceful shutdown ·
   input validation · authentication/authorization · retry/timeout · circuit breaker · data migration/schema evolution ·
   rate limiting.
9-2. **Emit is evidence-based**: coverage is mandatory, but each axis is **emitted only when the concern actually exists**
   for that stack (do not force health check/shutdown onto a static site). When applicability is **uncertain**, do not fabricate — ask the user in the Step 6
   preview (over-generation guard — FAIL-OPEN leans "skip + ask").
9-3. **Directive is a rule, the flesh is a doc**: operational directives (1–3 line instructions) go in the `<!-- ops-conventions -->`
   anchor section of `.claude/rules/<framework>-conventions.md`; the standard details · mappings · anti-patterns ·
   examples · **source URLs (SSOT)** · alternatives go in the "Operational concerns" section of `docs/code-style/<stack>.md`.
   The rule links the doc and does not duplicate the same fact (one fact, one place).
9-4. **Standard selection (avoid over-asserting)**: for brownfield, code-analyzer detects the standard used in the code and states it.
   For greenfield/undecided, researcher **auto-adopts the currently recommended latest standard (without asking)**, but puts the concrete
   standard name **in the doc** only as "recommended (changeable) + source + alternatives", and puts only the category directive in the rule.
9-5. **Security-axis escalation path**: for axes that need enforcement, like secrets · authentication/authorization · input validation, do not stop at a one-line
   directive — propose the **real-configuration opt-in** from harness-init Step 1 (secret scanner · linter)
   (only with consent). No "policy" enforcement illusion — real enforcement comes from detection tools.
9-6. **Every confirmed stack is a convention target (reuse artifact ≠ stack)**: *every* stack confirmed via reconcile (10-1) receives
   conventions (structure/detail SSOT separation follows 9-3 — no duplication here). In particular, infrastructure (DB · cache · queue ·
   container/image · CI/CD · IaC · cloud) tends to end as a mere reuse artifact, so if conventions (best practices · anti-patterns · operational axes)
   **actually exist**, promote it to a stack (otherwise leave it as a reuse candidate only — 9-2 evidence-based).

## Multi-agent / critique
10. **Research fans out via `Agent` (formerly `Task`, an alias) subagents** (researcher + code-analyzer for brownfield), dispatched in parallel and fanned in.
    Cross-talk happens via `SendMessage` only when the Agent Teams experimental feature (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`) is on (optional).
    Deprecated tools (`TeamCreate`·`TaskCreate`, etc.) are forbidden. Network/dispatch failures are FAIL-OPEN (warn + selection), not fabricated.
10-1. **Stack-inventory reconcile (converge before freeze — omission guard)**: `stack_map` is *provisionally*
    fixed during the interview, and the stacks (including infrastructure) surfaced by research (researcher's autonomous expansion · off-the-shelf solutions · stack-compatibility matrix)
    are merged into `stack_map` **before** authoring. Stacks whose conventions actually exist (infrastructure is especially easy to miss)
    are promoted to convention targets (9-6), and because a newly promoted stack was not dispatched as (layer, stack) in the first fan-out,
    run **targeted follow-up research** (a full sweep of that stack's ops_axes) to fill in its conventions. Repeat **until the stack set is stable**
    (usually once). **Do not grow the stack set by guessing** — only what has discovery evidence. The promote/reject decisions and reasons are **recorded** by authoring, one line each,
    in `docs/sds/README.md` (confirmed by the user in the preview alongside the other deliverables) —
    a version-controlled decision record (not a rationale duplicate).
11. **Write the rationale**: after synthesizing research, `.harness/rationale.md` (per-deliverable generation rationale · adopted patterns · reuse recommendations · sources).
12. **Lightweight critique**: `validate` (deterministic structure) → `harness-critic` (quality · coherence · reuse violations · no command generation).
    At most 2 rewrites; the remainder is stated as "unresolved" in the preview/report (no blocking).
12-1. **Version compatibility (`version-compat`) — two axes**: (a) **config-authoring coherence** — treat the toolchain as one set and
    verify the deliverables against the official authoring for the detected actual version (build ↔ config, e.g. `tsc -b` ↔ references).
    (b) **runtime-combination compatibility** — do the components that go onto one runtime together (app framework ↔ plugin/starter/
    engine/image) form the **latest set that is GA-compatible together**, and does the recommended off-the-shelf artifact
    **actually provide** the assumed feature. **When building**, do not infer the config; **replicate the official scaffolder
    output** of the detected framework as the baseline (the config counterpart of reuse-first). researcher collects the config method per version
    and autonomously expands the items the framework's characteristics require.
12-2. **Latest ≠ independently latest (ceiling first)**: **when selecting a version** (greenfield · undecided · intentional upgrade)
    researcher does not pick each component's independent latest separately. Identify the **anchor (ceiling)
    dependency** that caps the platform major, and pick the latest version set that anchor **supports as GA** (if they are not GA-compatible together, step down to the latest one to arrive;
    do not pin the core to a prerelease/unpublished dependency). Leave a **stack-compatibility
    matrix** (component → version → ceiling constraint → source) in the output. 9-4's "auto-adopt the latest standard" applies only within this ceiling constraint.
    (Checking whether brownfield's *detected* version combination is GA-compatible is not optional but detection, so it is handled by 12-1(b) —
    7-1 · critique-guide(B) cite this selection part.)

## Version/release convention research

13. **Release-tool research (per detected stack)**: during Step 2 research, investigate the standard release tool of the detected stack and propose
    `flow-config.versioning.release_tool`·`version_files` candidates.
    Default candidates per stack:
    - Python → `python-semantic-release`
    - Node/TypeScript → `semantic-release`
    - Rust → `cargo-release`
    - Go → `goreleaser`
    - Other → researcher investigates the ecosystem standard and proposes with rationale
    (if the stack is absent or uncertain, do not fabricate — leave it "needs confirmation" — rule 4).
13-1. **Generate `commit-versioning-guide` (technical doc)**: in Step 4 authoring, generate
    `docs/operations/commit-versioning-guide.md`. Contents:
    - Conventional Commits + SemVer basics (source URL required)
    - The detected stack's release-tool config (version files · changelog · CI hook — "needs confirmation" if the stack is undecided)
    - **0.x projects** recommendation: `major_on_zero=false` + annotated tags (prevent accidental 1.0.0 promotion)
    - Version-check commands (e.g. `git describe --tags`, per-tool dry-run commands)
    - **The tier and commit discipline themselves defer to [risk-tiers.md](risk-tiers.md)** — do not emit them directly here.
    Document sources link to `docs/research/` (do not reference `.harness/` paths, harness-rules 4-1·8).
13-2. **Opt-in branching (whether flow is detected)**:
    - **flow not detected** — propose the release-tool config (CI workflow · hooks, etc.) as opt-in
      (create the real config files only with user consent — same as rule 5's real-configuration opt-in).
    - **flow detected** — since `/flow-init` renders workflows such as `flow-config.contract_test`,
      do not duplicate-create the release-tool real config. Generating the `commit-versioning-guide` document proceeds always,
      regardless of whether flow is detected (it is within the code-style + convention doc scope — not a rule 14 defer target).

## flow coexistence
14. **When flow is detected (.claude/harness-tier/config/flow-config.yaml)**, process · commit · merge · PR discipline
    defer to [risk-tiers.md](risk-tiers.md). The harness emits only code-style + framework conventions.
14-1. **Pre-check tools and folder structure are an SSOT guide (enforcement is flow's job)**: the harness records, in the `docs/code-style/<stack>.md`
    toolchain-config section, a per-language/stack list of pre-check tools (lint/format/typecheck/import_lint/security/test runner) and
    the tests/ folder structure as SSOT — `/flow-init` references this when drafting `flow-config.modules[].checks`.
    But the harness only *guides* (tech-stack information); the actual gate enforcement (running/blocking checks) is
    flow's job (an extension of the rule 14 defer). Do not change `harness_scaffold.py`'s stack_map/scaffold logic here.
15. **Do not touch settings.json hooks** (not a gate). Security lives only in workflow/pre-commit files.
