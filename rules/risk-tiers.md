# Risk-Tiered Workflow

> This rule is injected into every session context via the vway-kit
> SessionStart hook — it is always active without a `paths` trigger.

Always-on rule. Core idea: **do not apply the heaviest AI process to
every task — scale process rigor to risk.** The tier a request lands
in decides **which skills run** (notably whether the heavy `superpowers`
pipeline engages) and **which gates are mandatory and enforced**.

This file is the single source of truth for tier classification and
the per-tier workflow. [`/vdev`](../skills/vdev/SKILL.md),
[`vdev-tiers.yaml`](../vdev-tiers.yaml), and the `warn-risk-tier` hook
all defer to it.

There are four tiers across two axes:

- **Day-to-day tasks** (on `feature/*` / `fix/*`): **Docs** or
  **Dev**.
- **Promotion events** (git-flow gates): **Staging**
  (`vdev-config.branches.integration → staging`) and **Release**
  (`vdev-config.branches.staging → production` / prod deploy).

## Principle

Every code-change request is classified **by `/vdev` before** work
starts — you do not judge the tier on your own and proceed. Higher
tier = more skills engaged + more mandatory gates. Running `/vdev` is
non-negotiable; the *depth* of process its verdict selects is what
varies. When the tier is ambiguous, `/vdev` escalates one tier (bias
to safety).

**You do not classify free-form — enter `/vdev` (via the Skill tool) as
your FIRST action** on any code change, feature, fix, or development
request, *before* reading code, planning, or editing. `/vdev` runs the
classification, confirms the tier with the user, and writes the marker
the commit gate reads. This is not optional: skipping `/vdev` leaves the
commit **unclassified**, and the commit gate **blocks it** (fail-closed
— a commit with no tier marker is refused). If the workflow is genuinely
unwanted, the user removes the gate with `/vdev-uninstall` — you never
work around it.

## Step 1 — Classify the task (Docs or Dev)

The line is deliberately simple: **code, or no code.**

### Docs — no code implementation

All of these hold:

- **No source-code change** — nothing in `.py` / `.js` / `.ts` /
  `.jsx` / `.tsx`, no DB migration, no shell script logic.
- Only docs (`.md`), narrative content, comments/docstrings, or pure
  config-text.
- Single service; no contract / schema / dependency change.

Typical: documentation edits, README/guide changes,
comment/docstring-only tweaks.

### Dev — any code implementation (default for development work)

**Any one** of these:

- **Any change to source code (`.py` / `.js` / `.ts` …), however
  small — even a single line.** If real code is touched, it is at
  least Dev.
- New feature or new API endpoint; a requirement change.
- DB schema change (migration).
- Touches a **cross-service shared package** (→ propagates to all
  dependent services).
- New/changed **business logic / core nodes / validators / workflow
  orchestration** (→ selective TDD).
- Dependency add/change (→ follow the project's dependency-update
  procedure).
- Affects 2+ services.

## Step 1b — Promotion events (Staging / Release)

These are **not** per-task classifications — they are git-flow
promotion gates run once over the accumulated work.

### Staging — integration → staging branch (QA / rc cut)

The release candidate enters QA/staging. Gates:
`precommit, review, security-scan` (`security-scan` = 전체 모듈 보안 도구 사전검사).
(`precommit` = 모듈 lint/static/import_lint/test, 레이어2 vdev 게이트가 일상 커밋(변경 모듈)
에서 담당한다. Performance·integration 은 독립 스킬. `/security-review` LLM 리뷰는 Release 에서
추가.)

### Release — staging → production branch

Two entry points:

- **Lifecycle (primary)** — the staging → production promotion
  (official release), or a production deploy (e.g., an air-gapped
  offline deploy). Gates: Staging + `security`.
- **Content (escalation)** — a single change that hits an
  irreversible/large data migration, a **performance-critical path**
  (search/embedding/GPU/inference config), or a security surface
  (auth/authz, secrets, gateway rate-limiting). Escalate that task to
  Release even on a feature branch.

### Tie-breakers

1. **When in doubt, escalate one tier.**
2. Criteria spanning multiple tiers → the **highest** tier wins.
3. Pure non-code (docs/comments only) → Docs; the review gate may be
   skipped with a one-line note.

## When each tier applies (git-flow mapping)

Branch names in this doc are `vdev-config.branches` **keys** —
`integration` / `staging` / `production` are roles, each resolving to
your project's actual branch (e.g. integration→dev, staging→stage,
production→main). No branch is literally named `integration`.

| Moment | Tier | Gates |
|--------|------|-------|
| Work on `feature/*` / `fix/*` → integration branch | **Docs** (no code) / **Dev** (any code) | Docs: doc-sync · Dev: precommit, review, doc-sync (precommit = 모듈 lint/static/import_lint/test, 변경 모듈에 실행) |
| integration → staging (QA / rc cut) | **Staging** | precommit, review, security-scan |
| staging → production, or prod deploy | **Release** | + security |
| A feature-branch change that is irreversible / prod-critical / security | escalate to **Release** | — |

Staging and Release are **promotion/deploy gates**, not per-commit
tiers you pick during feature development.

## Step 2 — Skill gate (the tier decides which skills run)

| Tier | `superpowers` pipeline | Validation skills | Suppressed |
|------|------------------------|-------------------|------------|
| **Docs** | OFF — no code | `/doc-sync` (harmonize docs) | brainstorming, writing-plans, TDD |
| **Dev** | ON | selective TDD, domain review, verification, `/doc-sync` | — |
| **Staging** | (promotion gate) | precommit, review, security-scan | — |
| **Release** | (promotion gate) | + security | — |

**Docs = `superpowers` OFF** (no-code edit, made directly).
**Dev = `superpowers` ON**: enter via `using-superpowers` — it
auto-runs the pipeline (brainstorm → plan → implement → verify →
review). Overlays on top: selective TDD scope, domain review,
`/doc-sync` (see Step 3).
**Staging / Release** are validation checklists over already-built
work, not new implementation.

**Precondition** — Dev/Staging/Release require the `superpowers`
plugin (`superpowers@claude-plugins-official`). If it is not installed,
`/vdev` **stops** and asks the user to install it — no manual fallback.

## Step 2b — Ensure a work branch

Both Docs and Dev day-to-day work happens on `feature/*` / `fix/*` —
never directly on an integration/staging/production branch
(`vdev-config.branches`). `/vdev` ensures this **after** confirming the
tier and **before** writing the tier marker:

- Already on `feature/*` / `fix/*` / `hotfix/*` → stay (idempotent).
- On an integration/staging/production branch → cut a work branch and
  switch to it. The prefix follows the Conventional type (`feat` →
  `feature/`, `fix` → `fix/`); derive a short English `<slug>` from the
  task (or ALM task-id) and confirm it with the user. A **clean** tree
  branches off freshly fetched `origin/<integration>` (see Feature
  branch base); with **uncommitted changes**, branch off the current
  `HEAD` to carry them along and rebase onto `origin/<integration>` at
  merge time (see Merge strategy).

Write the tier marker only **after** switching — the commit gate is
branch-bound, so the marker must carry the work branch, not the branch
work started on. `hotfix/*` off the production branch is the exception
(left in place).

## Step 3 — Per-tier workflow

### Docs (no code)

1. Make the edit directly (`superpowers` OFF).
2. Run `/doc-sync` to harmonize the doc set (root CLAUDE.md,
   per-service docs, rules; also reconciles code↔doc drift)
   → record `doc-sync`.
3. Commit (Conventional Commits, 50/72 rule — see Commit Discipline
   below) → direct merge.

### Dev (any code)

1. **Enter `superpowers:using-superpowers`** — it auto-runs the
   pipeline (brainstorm → plan → implement → verify → review). Feed
   the resolved request in.
2. Project overlays `superpowers` does not know about:
   - **Implementation minimalism (reuse-before-build ladder)** —
     right after the plan, before writing each piece of code, climb
     this ladder top-down and stop at the earliest rung that holds:
     ① does it need to exist (YAGNI) → ② already in this codebase
     (reuse helpers / utilities / patterns) → ③ stdlib → ④ native
     platform feature → ⑤ already-installed dependency → ⑥ one line
     → ⑦ only then the minimum code that works. The ladder runs
     *after* understanding the problem, not instead of it — read the
     task and the code it touches and trace the flow end to end
     first ("lazy about the solution, never about reading"). It cuts
     volume, never validation / error handling / security /
     accessibility: that floor is enforced by the selective TDD and
     domain-review overlays below and the Release security gate
     (non-trivial logic keeps selective TDD's one-check minimum).
     Mark intentional simplifications with a comment noting the
     ceiling and upgrade path. (Concept from ponytail, MIT.)
   - **Selective TDD** — business logic / core nodes / validators /
     workflow orchestration only; not every change.
   - **Domain review** — an independent `general-purpose` review agent
     (separate context) against the checklist: regression,
     cross-service contract, DB/migration & transactions, async task
     idempotency & queue routing, API error conventions
     → record `review`.
   - **`/doc-sync`** → record `doc-sync`.
3. Integration human gate (feature → integration branch; see Merge
   Strategy below) → commit → direct merge.

### Staging (integration → staging)

1. Regression review (independent `general-purpose` agent)
   → record `review`. `precommit`(변경 모듈 lint/static/import_lint/test)과
   `security-scan`(전체 모듈 보안 도구)은 precommit-runner 가 승격 커밋 시
   자동 실행한다(둘 다 런타임 게이트 — 마커 불요). 둘 다 `vdev-tiers.yaml`
   gates 리스트의 항목이므로, 그 tier 의 gates 에서 빼면 그 검사만 꺼진다.
2. Promote integration → staging (rc).

### Release (staging → production)

Staging gates **plus**:

1. Extra independent review — `/code-review` at `ultra` effort
   (high-risk layer).
2. Security review — `/security-review` → record `security`.
3. Release note — Conventional Commits + semantic-release.
4. Promote staging → production and/or deploy.

## Commit Discipline

Always apply before every `git commit -m` and every merge.

### Hard limits — 50/72 rule

- **Subject**: ≤50 chars total. Non-ASCII chars counted as 1 char
  each (per Conventional Commits standard).
- **Body**: each line ≤72 chars. Wrap at natural word boundaries.
  No one-line paragraphs.
- **Footer** (`BREAKING CHANGE:`, `Refs:`, etc.): same 72-char rule.

If subject > 50, **REWRITE**. No exceptions, even for descriptive
richness.

### Language

`type`/`scope`/`BREAKING CHANGE` keywords stay English (spec format —
`semantic-release`/`gitlint` parse them). The `<description>` and body
follow the host's configured response language (e.g. a `CLAUDE.md`
language directive); default to English if unset.

### Commit type → version impact

| Type | Version | When |
|------|---------|------|
| `feat` | MINOR | New feature |
| `fix` / `perf` | PATCH | Bug fix / perf improvement |
| `docs` / `chore` / `refactor` / `test` / `style` / `ci` / `build` | none | No release |
| `BREAKING CHANGE:` in footer | MAJOR | Incompatible change |

**Squash** merges pick the **highest-priority type** among bundled
commits.

> **플러그인 전파 규율** — vway-kit은 강결합(plugin.json `version`) 배포다. `docs`/
> `chore`는 버전 bump를 트리거하지 않으므로 **소비자에게 전파되지 않는다**. rules·skills
> 등 **소비자 동작에 영향을 주는 `.md` 변경은 `feat`/`fix`로 커밋**해야 릴리스에 실려
> 전파된다. 순수 내부 문서(개발자 전용, 소비자 무관)만 `docs`로 둔다.

### Merge strategy

Branch names refer to `vdev-config.branches` keys.

| Branch flow | Strategy |
|-------------|----------|
| `feature/*` → integration | **Rebase onto integration → integration-test gate → Squash** |
| `fix/*` / non-`feature/*` → integration | **Rebase** |
| integration → staging | **Rebase** or **Merge** |
| staging → production | **`--no-ff` Merge** |
| `hotfix/*` → production | **Squash** |
| production → integration/staging (after release) | **FF / `--no-ff` Merge** (back-merge) |

> `staging → production` is a `--no-ff` **Merge**, not Squash:
> semantic-release must parse the individual conventional commits, and
> the merge commit's non-`[skip ci]` title is what makes the release
> workflow fire — FF would land staging's `[skip ci]` rc commit as the
> head and skip the release. (`hotfix/*` → production stays Squash — a
> single `fix:` commit is still a valid, non-`[skip ci]` release input.)

### Merging `feature/*` → integration (integration-test gate)

`feature/*` → integration is NOT a one-shot squash. It is a
three-step gated flow. The integration-test confirmation is a
**human gate** — never skip it, never assume tested.

1. **Rebase first.** Rebase the feature branch onto freshly fetched
   `origin/<integration>` and resolve conflicts on the feature branch
   (keeps integration history linear, no merge commit):

   ```bash
   git fetch origin
   git rebase origin/<integration-branch>
   ```

2. **Ask the user — STOP and wait.** Before merging, ask whether they
   ran the **integration test** (real end-to-end — NOT unit tests,
   which do not satisfy this gate). Merge ONLY if the user explicitly
   confirms they tested. If unconfirmed, do not merge.

3. **Squash, then merge.** Choose squash granularity by change size:
   - **Small change** → collapse to **1 commit**.
   - **Larger change** → keep **one commit per category** (e.g. a
     `feat` commit + a separate `test` commit + a `docs` commit),
     rather than one giant blob. Each commit still obeys the 50/72
     rule and carries its own Conventional type.

   ```bash
   git switch <integration>
   git pull --ff-only origin <integration>
   git merge --squash feature/<name>
   ```

### Merge commit messages (integration → staging)

integration → staging makes a `--no-ff` merge commit. Its **title
MUST start with a capital `Merge`** — gitlint recognizes a commit as
a merge only when the title begins with capital `Merge`, and only then
exempts it from the type/50-char checks.

- `Merge <integration>: <headline>` — put the merge summary in the
  **body**, not the title.
- Never use lowercase `merge ...` — full-checked as a normal commit.
- Never use `chore(release): ...` — that prefix is the auto-release
  bot's namespace.

Do not attach a Conventional type to a merge commit. The version is
decided by semantic-release parsing the **individual merged commits**.

### Back-merge after release (production → integration)

semantic-release writes the version bump (`plugin.json` / `pyproject`)
and the marketplace sha pin **only on `production`** (as `[skip ci]`
`chore(release)` commits). They never reach integration on their own,
so integration's `plugin.json` drifts to a stale version.

After every production release, **back-merge** the release commits
production → integration (and → staging), so those commits and the
reachable stable tag return to the day-to-day branches:

```bash
git fetch origin
git switch <integration> && git merge --ff-only origin/<production>
git switch <staging>     && git merge --ff-only origin/<production>
# then push each
```

Fast-forward when the branch is strictly behind; else `--no-ff` Merge.
This is standard git-flow, **not optional**: without it semantic-release
miscomputes the next version (the released tag is unreachable from
integration/staging). It is needed because Explicit-version gating
forces the version into a **committed file** (not a tag-only release,
which would never drift).

### PR workflow

**Not used in vway-kit projects.** Direct merge + push. Never propose
creating a PR; merge straight to the target branch and push.

### Feature branch base

`/vdev` cuts this branch in Step 2b. A **clean** tree branches from
freshly fetched `origin/<integration>`; with **uncommitted changes** it
branches off the current `HEAD` (carrying them) and rebases onto
`origin/<integration>` at merge:

```bash
git fetch origin
git switch -c feature/<name> origin/<integration-branch>
```

Branch names in English.

### When asked "is this commit compliant?"

Re-measure subject char count and each body line length yourself.
Don't trust your earlier write.

## Repo conventions baked in

- **No PR** — direct commit + merge (see Commit Discipline above).
- **Pre-commit hard gate is inherited by every tier** — the
  `git commit` hook (configured in the project's `settings.json`)
  runs the project's linter / test / formatter chain. Never bypass
  with `--no-verify`.
- **Worker / service-process safety** — Dev+ changes touching
  long-running worker processes: inspect for in-flight tasks and
  require explicit user approval before restarting.
- **Entry point** — a free-text request or an ALM task-id.
  A task-id entry ends with `/task-sync` to sync the result back to
  the ALM.

## Hard gates (enforced mechanically)

Gates are enforced at chokepoints, driven by
[`vdev-tiers.yaml`](../vdev-tiers.yaml) and the evidence markers
`/vdev` records under `.claude/vway-kit/.vdev/` (gitignored):
`tier` (`<tier>:<branch>`) plus `<gate>.done` per completed gate.

1. **Commit gate (Docs/Dev)** — the `git commit` hook (via the
   project's `vdev_gate_check` script) **blocks the commit** if the
   active tier's required gate has no `.done` marker. Branch-bound. It
   also **blocks an unclassified commit** — when the policy is intact
   but no `tier` marker exists (i.e. `/vdev` was skipped), so bypassing
   `/vdev` cannot silently disable the gate (fail-closed).
2. **Promotion gates (Staging / Release)** — enforced purely at
   `git commit` by branch: a commit on the staging branch enforces
   the `staging` gates; a commit on the production branch enforces
   the `release` gates (same commit hook). **Deploy commands are not
   gated** — tiers are separated by commit branch only.

Properties:

- **Fail-open on errors** — missing/unparseable policy or config, or
  any internal error → the action is allowed (a broken gate never bricks
  commits or deploys). The test is "the gate works reliably", not "a
  file exists". **Exception — an unclassified commit is fail-CLOSED**:
  when the policy parses and config is intact but no `tier` marker
  exists, the commit is **blocked** so skipping `/vdev` cannot silently
  disable the gate. Promotion gates are likewise fail-*closed* on
  missing evidence, but still fail-open on internal errors.
- **Branch-bound** — markers carry the branch, so stale state cannot
  block an unrelated task on another branch.
- `precommit` (모듈 lint/static/import_lint/test, 변경 모듈) and `security-scan`
  (전체 모듈 보안 도구, 승격 시) are both **executed** by the hook
  (`precommit-runner.sh`, 레이어2 — 레이어1 pre-commit 아님), not a marker —
  both are `RUNTIME_GATES`. Both are ordinary entries in each tier's
  `vdev-tiers.yaml` `gates` list, so **removing either from a tier's gates
  disables that check for that tier** (e.g. drop `security-scan` from
  `release` to stop running the full-module security scan on release
  promotions) — the gates list is the single on/off switch, not a hardcoded
  tier branch.
- Judgment gates (review quality, human integration test) can only be
  *recorded*, not verified — a marker is an audit trail + forcing
  function, not proof.
- **Air-gapped limit** — an offline production machine runs on a
  separate host a local hook cannot reach; the staging → production
  commit is the local release-authorization gate.

Clear state with `rm -rf .claude/vway-kit/.vdev` (also done by `/vdev`
after a successful commit/merge).

---

*Pilot: Docs & Dev enforced at commit; Staging at integration →
staging, Release at staging → production / offline deploy. Full
one-shot `/vdev` automation of the Dev/Staging/Release pipelines
is a follow-up.*
