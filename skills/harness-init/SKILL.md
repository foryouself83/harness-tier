---
name: harness-init
description: A wizard that detects the framework and, using multiple sub-agents, researches the latest conventions and free off-the-shelf solutions to generate an AI harness (.md by default, real configuration opt-in) — detect → interview → research (fan-out) → rationale → generate → critique/validate → preview → confirm → write, no overwrites, no commands generated
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion, Glob, Grep, Agent, SendMessage, WebSearch, WebFetch, Skill
argument-hint: (none)
disable-model-invocation: true
---

# Harness-Init — AI Harness Generation Wizard

Generates a Claude Code harness tailored to the target project using multiple agents. The output is **.md by default**, and real configuration (security scanners, CI, folder scaffolding, etc.) is applied **only after asking and receiving consent**. **No commands are generated.**
**Discipline SSOT**: [harness-rules.md](../../rules/harness-rules.md) — read and follow it (no duplication).

## Paths
```bash
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
PLUGIN="${CLAUDE_PLUGIN_ROOT}"
HARNESS_DIR="${ROOT}/.claude/harness-tier/.harness"   # evidence (research/rationale/plan/critic/manifest), gitignored
```
Per the harness-tier convention, evidence is collected in a single place — `.claude/harness-tier/.harness/` (no scattering across the root):
`research/<agent>_<topic>.md` · `rationale.md` · `plan.json` · `critic-report.json` · `manifest.json`.
Before the first write, **idempotently add** `.claude/harness-tier/.harness/` to `.gitignore` (skip if already present).
Because harness-init is independent of flow, it ignores its own evidence itself (no dependence on flow-init).

## Step 0 — Validation/Detection (script)
```bash
python3 "${PLUGIN}/scripts/harness_scaffold.py" detect --root "${ROOT}"
```
Show the result (state/frameworks/existing) to the user **as a table**. Also report whether flow is installed
(.claude/harness-tier/config/flow-config.yaml).

## Step 1 — Interview (AskUserQuestion, keep it minimal but scope it clearly)
0. **Clarify the development scope (greenfield/SRS gate — no guessing)**: If detect reports greenfield, or an SRS
   artifact is selected, parse the received prompt to fix the development scope **before Step 2 research and Step 4 SRS
   authoring**. Ask **all blank required SRS slots plus every ambiguous item** via `AskUserQuestion` — **ambiguous = not
   measurable, multiple interpretations, or unclear scope** (e.g., "quickly", "user-friendly"). Keep asking **until each
   is measurable and single-interpretation**, but do not re-ask what is already clear (no over-generation, no
   interrogation). Required slots = purpose · goals/non-goals (YAGNI boundary) · core functional requirements · target
   users/scenarios · key constraints (scale, performance, security, deployment environment). Additionally, fix the
   **classification axes** (domain as primary; user role/subdomain as secondary) and the **depth (2–3 levels)**. For axes
   that do not apply, leave the literal "N/A — reason" in the SRS (for the detailed discipline and structure, see
   harness-rules 8-1, the SRS section of `tech-doc-guide.md`, and `srs.template.md`).
   - **Gate**: do not proceed to Step 2 or Step 4 while scope blanks or ambiguities remain. For slots still unknown after
     asking, **explicitly mark them "needs confirmation"** in the SRS and never fabricate them (harness-rules 4, 8-1).
   - Output = a **scope summary** → the single input source for research, rationale, and the SRS (single downstream source).
   - **brownfield (no SRS generated) skips this gate** — take scope from the code-analyzer's code analysis, and optionally
     ask only about intent that the code does not resolve (goals/non-goals, etc.).
1. **Fix the primary development language (hard gate, see harness-rules)**: Always fix the primary development language via
   `AskUserQuestion` (ask regardless of the detected value). If a language was detected, offer it as the first option
   (recommended); if multiple/none were detected, list candidates. If the detected value and the user's choice differ,
   **the user's choice wins**. **Primary language ≠ the same language across every layer** — split the project into layers
   (frontend/backend/other) and, for each layer, present the **more production-ready, standard-conforming stack as the top
   recommendation** (with research backing where possible), then **confirm "same across all layers vs. per-layer split"
   via `AskUserQuestion`**. The result = a **per-layer language/stack map** (provisional — reconciled and **frozen** with
   research findings in Step 2.5; user sign-off is Step 6; single downstream source). Do not guess and fill in a stack that
   has not yet surfaced (infrastructure especially — locking in early without knowing leads to omissions; fill it in during
   reconcile after research, harness-rules 10-1).
2. Confirm the detected framework/version (correct it if wrong; request input if not detected).
3. Select the artifacts to generate: CLAUDE.md / rules (the 5 baseline rules + framework conventions) / skills / agents /
   technical docs (SRS greenfield · SDS · per-stack code-style · research · onboarding · **performance/integration SSOT docs (`docs/verification/performance.md` · `docs/verification/integration.md`)**, in classified folders). **There is no command option.**
4. **Opt-in real configuration**: installing a security scanner · adding CI · scaffolding real folders · real version pins — ask about each one.
   For the operational axes of secrets, authentication/authorization, and input validation, do not stop at a directive alone; also propose opting into a scanner (9-5).
5. Brownfield conflicts (existing), per item: skip / user's choice.

## Step 2 — Research (sub-agent fan-out, isolated)
**Standard**: Using `Agent` (formerly `Task`, alias), **dispatch as parallel sub-agents** `harness-researcher` (web conventions, best practices, anti-patterns, free off-the-shelf solutions) plus, if brownfield,
`harness-code-analyzer` (the codebase's actual conventions, anti-patterns, hand-rolled code).
The sub-agents **return** their findings as their final message; the **leader owns the fan-in write** — it assigns each a **unique topic** and persists the returned output to `.harness/research/<agent>_<topic>.md`, then reads them back to synthesize (and for Step 4 authoring). Sub-agents do not write these files themselves, so parallel dispatch cannot collide on a filename and the read-only code-analyzer needs no write access (harness-rules 10).
- **Scope injection**: for greenfield/SRS, include the **scope summary** from Step 1-0 in the dispatch input so that
  research is confined to the actual requirements (do not expand scope by guessing — investigate while leaving unknown slots as "needs confirmation").
- **Operational-concern injection**: when dispatching research, pass the harness-rules 9-1 checklist and the **per-layer language/stack map**
  so that, for each (layer, stack), the sub-agent researches the latest standards, sources, alternatives, and applicability per operational axis (9-2 to 9-4).
- **Quality-lens injection**: pass the harness-rules 9-7 lens checklist (correctness · UX · a11y · performance · security · maintainability/testability ·
  cross-cutting/integration · i18n) alongside the stack map so that, per (layer, stack), the sub-agent researches best practices **by lens** with
  applicability (9-2) and **links** — not duplicates — the owning SSOT (9-8).
- **code-style incremental (lens-gap) path — unified gap model**: classify `docs/code-style/<stack>.md` deterministically and
  token-free by running `python3 "${PLUGIN}/scripts/harness_scaffold.py" scan <path> <stack>` (not a hand LLM read) to get its
  3-state classification (`state`: none / `"flat"` legacy / `"lens"` doc, plus the `present` lens list) and tally the present
  lenses. `gap = applicable lenses − present` (applicable lenses = a lightweight, stack-nature judgment — not research). **Before
  research**, use `AskUserQuestion` to
  confirm what to fill: flat legacy is confirmed **per stack** (migrate all applicable lenses), lens docs **per lens** (add what's
  missing). Only the confirmed `(stack, lens)` set is sent to research dispatch → applied via the `lens_upsert` action (flat =
  `migrate:true` section replace / lens doc = additive). The replace/migration safety net is **git diff + preview→confirm** (no edit
  detection, no manifest).
- **Version/release tooling research**: research the standard release tool (`release_tool`), `version_files`, and 0.x policy for the detected stack (harness-rules 13, 13-1).
- **Performance/integration dimension injection**: after the stack is fixed by the Step 2.5 reconcile, when re-dispatching harness-researcher,
  pass the finalized `stack_map` as well and instruct it to research procedure 9 (performance SSOT, integration-verification SSOT).
  Save the findings to `.harness/research/` and consume them in Step 4 authoring.
- **Cross-talk (optional)**: cross-talk via `SendMessage` is only possible on builds where the Agent Teams experimental feature (`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`)
  is enabled (code-analyzer "found hand-rolled X" → researcher "research a free replacement"). Without it,
  operate as parallel dispatch → fan-in with no cross-talk (do not use deprecated tools such as `TeamCreate`/`TaskCreate`).
- **Partial fan-in check**: after fan-in, verify each expected output is present and non-empty; mark any missing/empty area **"needs confirmation"** (distinguish a legitimate code-analyzer "insufficient sample" from a lost dispatch — do not read absence as "no conventions"). FAIL-OPEN below covers total failure; this covers the partial state (harness-rules 10).
- **FAIL-OPEN**: on network/dispatch failure, do not fabricate; warn and offer the choice "proceed with a minimal generic structure / abort".

## Step 2.5 — Stack inventory reconcile (converge before freezing, harness-rules 10-1)
Merge the stacks surfaced by research (researcher's autonomous expansion, off-the-shelf candidates, the stack-compatibility matrix — **including infrastructure**)
into the *provisional* stack_map from Step 1. **Promote** stacks that have real conventions (best practices, anti-patterns, operational axes) to convention targets
(do not stop at reuse artifacts alone — 9-6). **Because a newly promoted stack was not dispatched as a (layer, stack) in the first fan-out**,
run **targeted follow-up research** for just that stack (re-dispatch researcher **with the first pass's frozen stack-compatibility matrix / ceiling included in its input**, covering that stack's full ops_axes and **constraining any version pick to that ceiling** — 12-2) to fill in its conventions. **Repeat until the stack set stabilizes**
(terminate when there are no new promotions — usually one pass). **Then re-validate the whole merged set against the global ceiling as a single authoritative compatibility matrix before freezing**, and hand that one matrix to the Step 5 critic (so version-compat cross-checks a single matrix, not divergent per-dispatch ones). Do not grow the stack set by guessing (findings only; FAIL-OPEN is "skip + ask"). The promotion/rejection decisions and rationale are
**drafted by authoring (Step 4)**, one line each, in `docs/sds/README.md`, and confirmed by the user in the Step 6 preview along with the other artifacts (draft@4 → confirm@6 → write@7; not a duplicate of rationale).

## Step 3 — Rationale authoring (rationale)
Synthesize detect + research + the **scope summary (Step 1-0)** to write `${HARNESS_DIR}/rationale.md`: domain analysis, **the reason for generating each artifact**,
adopted patterns, a best-practice/anti-pattern summary, **the adopted standard + source + applicability per operational axis (including emit/skip rationale)**,
a **reuse-before-build recommendation** (free / commercially usable, paid excluded), and sources.
**Conflict resolution (no cross-talk mode)**: when researcher's recommendation (a best practice) conflicts with code-analyzer's in-code reality (an anti-pattern), record **both**, prefer the best practice with a one-line migration note, and for operational-axis standards apply the 9-4 precedence (brownfield → the in-code standard; greenfield → the recommended latest); if still ambiguous, ask (Karpathy, rule 4).

## Step 4 — Generation (authoring skill + scaffold)
The convention targets are the **entire stack set finalized by the Step 2.5 reconcile** (including promoted infrastructure) — not the initial stack_map.
Per the 9-3 split, fill each stack's structure/detailed conventions into both the rules and `docs/code-style/<stack>.md`.
1. Use `Skill: harness-authoring` to fill templates/ from research + rationale + references.
   - Inject the 5 required rule blocks (`references/karpathy-principles.md` · `rule-dry-constants.md` ·
     `rule-version-pinning.md` · `security-rule.md` · `rule-reuse-first.md`) into the CLAUDE.md `harness:baseline`
     block (preserve each rule's anchor `<!-- rule:<key> -->`).
   - Fill the technical docs into classified folders. **Author the SRS with the scope summary (Step 1-0) as SSOT** and leave unknown slots as
     "needs confirmation" (fill from research but do not guess). (Order: SRS greenfield → merge into research → SDS (Mermaid) → per-stack
     code-style → onboarding → docs/README, with source links.) First refine `.harness/research/` and merge it into
     `docs/research/` (the basis for the SDS and code-style); thereafter docs link their sources to
     `docs/research/` (do not reference `.harness/`). When generating a skill, include the accompanying references/examples subfolders.
   - **Absent vs. existing code-style routing (unambiguous)**: a **brand-new / absent** `docs/code-style/<stack>.md` is always
     generated via the normal full-template `create` action (every section — title, naming/formatting/imports, toolchain,
     anti-patterns, reuse candidates; its Best Practices section already carries lens managed blocks per the template, so it is
     never headless). The `lens_upsert` action is for **existing** docs only, as surfaced by the Step 2 gap scan: flat legacy
     (`migrate: true`, whole-section replace) or an existing lens doc (additive per-lens). `lens_upsert`'s own absent-file branch
     is a defensive fallback for a stray plan entry, never the first-run authoring path.
   - When flow is detected, put only a risk-tiers defer note for process discipline and do not emit your own process rules.
   - **Performance/integration SSOT docs**: generate `docs/verification/performance.md` · `docs/verification/integration.md` via authoring only when
     there is a finalized stack. Do not create empty stack sections. Link sources to `docs/research/`.
     (The `/performance` · `/integration` skills consume these docs first and, when absent, fall back to the skills' built-in references.)
   - **commit-versioning-guide**: generate `docs/operations/commit-versioning-guide.md` (Conventional Commits + SemVer + the release-tool setup for the detected stack; regardless of whether flow is detected — harness-rules 13-1, 13-2). When flow is detected, do not duplicate the release tool's real configuration (CI workflows, etc.).
2. Create a `plan` (files[]) and save it to `${HARNESS_DIR}/plan.json`.

## Step 5 — Critique/Validation (lightweight, FAIL-OPEN)
1. **Deterministic structure check**:
   ```bash
   python3 "${PLUGIN}/scripts/harness_scaffold.py" validate --root "${ROOT}" --plan "${HARNESS_DIR}/plan.json"
   ```
   (Not a gate — exit 0 even on high issues. The leader reads the report.)
2. **Quality/coherence critique**: dispatch `harness-critic` → `${HARNESS_DIR}/critic-report.json`.
   If `verdict: revise`, return to authoring and revise **up to 2 times**. Explicitly mark any remaining issues as "unresolved".
   (The critic reviews **deliverable** quality/coherence; **fan-in/process integrity** — missing sub-agent outputs, global-ceiling re-validation — is guarded by the leader in Step 2·2.5, not by the critic.)

## Step 6 — Preview/Confirm
Show the `plan` (generate/skip/conflict) + `rationale` + `critic-report` to the user and get confirmation (no writing before confirmation).
For **operational axes whose applicability is uncertain**, confirm "whether to include" here via `AskUserQuestion` (9-2), and expose greenfield
auto-adopted standards as "recommended default (changeable)" for confirmation.

## Step 7 — apply (scaffold)
```bash
python3 "${PLUGIN}/scripts/harness_scaffold.py" apply --root "${ROOT}" --plan "${HARNESS_DIR}/plan.json"
```
Marker upsert / create only when absent. Opt-in real configuration is not auto-merged into existing files — only the missing parts are announced (.pre-commit-config.yaml, etc.).

## Step 7.5 — cleanup (clean up merged copies)
After apply succeeds, clean up the intermediate copies that were merged into docs (to avoid confusion on re-run/update).
```bash
python3 "${PLUGIN}/scripts/harness_scaffold.py" cleanup --root "${ROOT}"
```
Remove only the merged copies such as `.harness/research/`, and preserve the evidence metadata (`plan.json` · `manifest.json` ·
`critic-report.json` · `rationale.md`) (for audit/re-run). **Link guard**: if docs reference
`.harness/research`, defer removal and report it via `link_warnings` (to prevent broken links).
FAIL-OPEN — a cleanup failure does not block the flow. If there are `link_warnings`, surface them in the report.

## Step 8 — Report
Summarize **as a table**: generated/skipped/deferred-by-user + source URLs + critic results (including `version-compat`) + cleanup results (removed/preserved) +
follow-ups (scanner install commands, etc.).
Record the generation history, framework, sources, and critic results in `${HARNESS_DIR}/manifest.json` (for audit/re-run).
**Do not commit** — instruct the user to commit via `/flow`.

## Critical rules
1. No overwrites — marker upsert / create only when absent.
2. No writing before preview/confirmation.
3. The host is `${CLAUDE_PROJECT_DIR}`; read the plugin from `${CLAUDE_PLUGIN_ROOT}`.
4. No commands generated — do not create any artifact under `.claude/commands/`.
5. Defer commit/merge/PR discipline to risk-tiers (when flow is detected).
6. Team/network failures are FAIL-OPEN (warn + offer a choice); do not fabricate. When ambiguous, ask (Karpathy).
