# Critique/review checklist (critic defer)

The checklist the `harness-critic` agent follows when reviewing generated output.
Deterministic structural checks are handled by `harness_scaffold.py validate`; this guide
covers the **judgment-based quality and coherence** aspects.

## Output format

Return the review result in this schema (`.harness/critic-report.json`):

```json
{
  "issues": [
    {"severity": "high|med|low", "file": "<rel>",
     "kind": "quality|coherence|reuse|command|version-compat",
     "evidence": "<evidence>", "fix": "<fix proposal>"}
  ],
  "summary": {"high": 0, "med": 0, "low": 0, "verdict": "pass|revise"}
}
```

If there is even one `high` issue, `verdict: revise`. The leader rewrites **at most twice**
and reports any remainder as "unresolved".

## 1. Authoring quality (`kind: quality`)

- **Description assertiveness**: Are the trigger situations and boundary conditions present?
  Is it non-vague (not "~related work")?
- **Why-First**: Are there only coercive rules (ALWAYS/NEVER) with no reasons?
- **Lean**: Is content Claude already knows, extra docs, or meta-info mixed in?
- **Generalization**: Is it an overfitted rule that fits only a specific example?
- **Load path**: Are the required rules inside the CLAUDE.md baseline marker block (the body)
  (not `.claude/rules/` alone)?

## 2. Interface coherence (`kind: coherence`)

- Do CLAUDE.md ↔ rules ↔ docs **point to each other correctly** (cross-references, dead links)?
- Is the same fact not **duplicated in two places** (structure = rule, behavior = doc SSOT separation)?
- Do the marker-block BEGIN/END pairs match?
- Does the generating agent's I/O protocol mesh with the orchestration?
- **Operational conventions (9-1~9-5)**: (a) full review across the checklist axes — if any is
  missing, does the rationale have an emit/skip reason, (b) do operational standards have a
  source URL (if not, is it marked "source unverified"), (c) does the directive (rule) ↔
  standard detail (doc) not duplicate the same fact, (d) is the security axis (secrets/auth/
  input validation) not ending at directives alone but connected to an opt-in scanner?
  Violations are `high`.
- **Stack reconcile coverage (9-6·10-1)**: are **all** the "stacks needing conventions"
  (infrastructure included) reported by the researcher either (a) given conventions (rule +
  `docs/code-style/<stack>.md`) or (b) recorded with a **rejection reason** in the SDS
  reconcile-decision section — i.e. a convention wasn't wholesale dropped just because it was
  discovered outside the initial stack_map? If it was discovered but has neither a convention
  nor a rejection reason, `high` (the very omission this change aims to prevent).
- **Runtime integration coherence** (only in multi-component topologies): is the
  inter-component communication the SDS declares **actually wired** in the output — catches
  "each setting is right but they don't mesh". (a) **Reachability**: do issuer/hostnames
  resolve in the deployment topology (container DNS/`extra_hosts`/routing), and is there a
  path to the component declared behind the reverse proxy? (b) **identity/origin**: do
  issuer/origin **match** between the browser's view and the internal (container) view (JWT
  `iss` validation, CORS)? (c) **policy continuity**: do security headers/CSP (e.g.
  `connect-src`·`frame-src`) not block the declared cross-origin flow (OIDC, etc.) and stay
  in effect on **all response paths** (a sub-location's header re-declaration doesn't break
  parent inheritance)? (d) **credentials**: is an app-specific account provisioned (don't
  assume root-only)? (e) **global-config blast radius**: does a global policy
  (statement_timeout, preload, etc.) not unintentionally constrain a declared heavy path
  (migration, recursive query)? Violations are `high`.

## 3. reuse violations (`kind: reuse`)

- Does the generated guide recommend **reinventing the wheel instead of a free,
  commercial-use-OK off-the-shelf solution**?
- Does it **recommend a paid solution** (paid managed service, paid license, SaaS
  subscription)? → violation.
- Did it assert and recommend a reuse candidate whose cost/license was "needs verification"?

## 4. No commands generated (`kind: command`)

- Was nothing generated under `.claude/commands/` by any output (double-check with validate)?

## 5. Version compatibility (`kind: version-compat`)

Look at **two axes** — (A) config-authoring coherence, (B) runtime-combination compatibility.
A violation on either is `high`.

### (A) Config-authoring coherence

Treat the toolchain as **one set** (build runner, compiler, bundler, type checker, linter,
test runner are interlocked).

- Do the outputs (especially real-folder scaffolding config files) match the official
  authoring conventions of the detected **actual package versions**?
- **Toolchain axis completeness (omission detection)**: does each axis — build, **package
  manager**, lint/format, test — have an **explicit decision + source**? In particular, if
  the package manager solidified into an inertial default (npm/pip, etc.) in the output
  (Dockerfile `npm ci`, `package.json` scripts, etc.) with no decision/source anywhere in the
  researcher output/rationale → an inertia-boundary violation (harness-rules 9-4 · researcher
  discipline). Include it if the decision/pin (lockfile, `packageManager`) and source aren't
  consistent across the output. A missing/unsupported inertial value is `med` (not a runtime
  break — a coverage/evidence gap).
- **Toolchain mutual consistency**: do the build scripts ↔ config not conflict? (e.g. `tsc -b`
  (project references mode) but the root tsconfig has no `references`; the root
  `vite.config.ts` isn't captured by any tsconfig project scope, so it's outside `include`.)
- Did it misapply a config schema/default that varies by major version?
- Did it hand-infer and cobble the config together? → cloning the **official scaffolder
  output** of the detected framework is the authoritative baseline.

### (B) Runtime-combination compatibility

Look for "each item is right but booting them together breaks". **Build passing ≠ boot success.**

- **Dependency co-GA compatibility**: do the components running together on one runtime (app
  framework ↔ plugin/starter/engine) **support each other's major as GA**? If one doesn't yet
  support the other's major, it's a violation. (e.g. bundling Spring Boot 4 ↔ a workflow
  engine/circuit-breaker starter that doesn't yet GA-support Boot 4; pinning the core to a
  prerelease/unreleased version → violates "latest ≠ independently-latest, ceiling first".
  Cross-check with the researcher's compatibility matrix.)
- **Off-the-shelf artifact feature reality**: does the recommended stock image/package
  **actually provide** the feature the architecture assumes? (e.g. loading an extension the
  stock postgres image lacks via `shared_preload_libraries`, so boot fails; assuming an
  `--optimized` run mode without a prior build; assuming an app-specific account when only
  root credentials exist.) If it doesn't provide it, is a custom build/provisioning step
  **explicitly stated** in the output — if it only assumes and omits it, it's a violation.

## 6. Dry run (judgment)

- Given the generated skill's description, does it seem **likely to trigger** in the actually
  intended situation? Does it not conflict with adjacent skills?
- Is the generated rule on an actual load path so it **will be reflected in the session**?
- Does the generated agent have the tool access it needs when invoked (no mismatch like an
  Explore agent that needs write access)?

## Principles

- **No issue without evidence** — back it with file, line, and quote.
- **Fix proposal required** — one line on what to fix and how.
- Judge by the **objective criteria above**, not subjective taste.
