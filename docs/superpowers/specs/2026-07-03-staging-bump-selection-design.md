# Staging-promotion version-bump selection gate — Design

- **Date**: 2026-07-03
- **Status**: Approved (brainstorming) → pending implementation plan
- **Scope**: harness-tier plugin (SSOT templates shipped to consumers) **and** harness-tier's own release flow (dogfood)

## 1. Goal

At **staging promotion** (integration → staging), force the human to choose the
version bump level (**major / minor / patch**) before the release runs, and make
that choice authoritative — it overrides the Conventional-Commits auto-derivation
that `python-semantic-release` performs today. The choice is enforced by the
existing flow gate (fail-closed) and carried to CI where the bump is executed.

## 2. Background — current state

- Version bump is **fully automatic**. On push to `stage`/`main`,
  `.github/workflows/release.yml` runs `semantic-release version`, which parses
  commits since the last tag (`feat`→minor, `fix`→patch, `BREAKING CHANGE`→major)
  and computes the level. **No human choice point exists.**
- The commit gate (`scripts/flow_gate_check.py`, PreToolUse) is **non-interactive**
  — it cannot prompt. Interactive asking belongs in the `/flow` skill; the gate's
  job is to **verify evidence** (fail-closed) that the step happened.
- `python-semantic-release` supports forcing a level: `version --major/--minor/--patch`,
  and `--as-prerelease` to force a prerelease (rc) from a forced level
  (e.g. `--minor --as-prerelease` → `0.3.0-rc.1`).
  Source: <https://python-semantic-release.readthedocs.io/en/latest/api/commands.html>

## 3. Decisions (from brainstorming)

| Question | Decision |
|----------|----------|
| Scope | **Both** — ship as a consumer feature via SSOT templates, and dogfood in harness-tier's own flow |
| Mechanism | **Override** — human choice is authoritative; auto-derived level is only the pre-selected default |
| Approach | **A — commit-trailer transport + flow-gate enforcement + CI force-level** |
| Config toggle | **None** (YAGNI) — always on for staging when `versioning.enable: true` |
| Local early warning | **Included** (best-effort, fail-open) |
| Shared token-check | **Adopted** — one `scripts/check-token-write.sh` shared by CI + local |
| CI release token (harness-tier's own) | **`RELEASE_TOKEN` PAT secret** — `release.yml` uses it for checkout `token:`, push, and `gh` auth. Consumer template keeps `GITHUB_TOKEN` default + documents the PAT opt-in |
| Token-write detection | **`.permissions.push`** on the repo object (admin-free; confirmed by a live API check) — not the admin-gated `actions/permissions/workflow` endpoint |
| Permission how-to | **One canonical section per audience** — a section in `USAGE.md` (harness-tier's own) and one emitted into the generated `commit-versioning-guide` (consumer); one-liners/guard messages link to it |
| main (stable) finalization | **Deterministic rc-strip** (drop `-rc.N` → tag stable), NOT plain PSR (loses override) nor force-on-main (double-bumps) — empirically verified §6D; hotfix (no rc) falls back to plain compute |
| `major` on 0.x | Explicit `--major` overrides `major_on_zero=false` → jumps to `1.0.0`; the bump prompt **warns** on this choice |
| Enforcement scope | **Session commits only** (existing flow-gate model) — terminal-commit commit-msg enforcement out of scope (user decision) |

## 4. Architecture & data flow

```
stage promotion (integration → staging)
  │
  ▼
① /flow  Staging step
   - best-effort: derive suggested level (semantic-release --print) → default
   - AskUserQuestion: major / minor / patch          ← forced human choice
   - write evidence:  .claude/harness-tier/.flow/bump.done   (gitignored)
   - compose promotion commit with trailer:  Release-Level: <level>
  │
  ▼
② commit gate (flow_gate_check.py, PreToolUse)
   - staging-branch commit without bump.done  →  block (exit 2, fail-closed)
   - = "enforce that asking happened" (reuses existing .done marker pattern)
  │
  ▼  (push to stage)
③ CI release.yml
   - preflight: verify token write permission (check-token-write.sh) → fail-fast w/ how-to
   - parse Release-Level:<level> from head commit
   - semantic-release version --<level> --as-prerelease   ← overrides auto-derivation
   - no trailer → safe fallback to auto-derivation
  │
  ▼
   rc tag (e.g. --minor → 0.3.0-rc.1);  main promotion = deterministic rc-strip → stable (§6D)
```

**Role split** (consistent with the 3-layer verification philosophy):
- Local (layer-2 flow gate) = blocks a session promotion commit that skipped the choice.
- CI = applies the chosen level to the actual version (override).

Two artifacts, written together by `/flow`:
- `bump.done` (gitignored marker) — local fail-closed evidence.
- `Release-Level:` (commit trailer) — transport to CI, moves atomically with the commit.

## 5. Components & changes

| # | File | Change | Kind |
|---|------|--------|------|
| 1 | `flow-tiers.yaml` | add `bump` to `staging.gates` | policy |
| 2 | `scripts/flow_gate_check.py` | **no change** — `bump` becomes a standard evidence gate needing `bump.done` (not a `RUNTIME_GATE`); verify with tests | (verified) |
| 3 | `skills/flow/SKILL.md` | Staging: `AskUserQuestion`(major/minor/patch, default=auto-derived; **warn when `major` on a 0.x project → 1.0.0**) → `touch .flow/bump.done` → insert `Release-Level:` trailer. Release (main): promote only — main finalizes via CI-side deterministic rc-strip, no level carried. Local token pre-warning (best-effort). | skill |
| 4 | `rules/risk-tiers.md` | document the staging bump-selection gate in the Staging section, the gates table, and Commit Discipline (version impact now human-forced at staging) | rule (SSOT) |
| 5 | `.github/workflows/release.yml` | switch auth to `secrets.RELEASE_TOKEN` (PAT) for checkout `token:`, push, and `gh`; token-write preflight (`.permissions.push`); **stage**: parse `Release-Level:` → `semantic-release version --<level> --as-prerelease` (fallback to auto when absent); **main**: deterministic rc-strip finalize (prerelease present → drop `-rc.N`, tag stable; else plain `semantic-release version` for hotfix) | CI (own) |
| 6 | `github/release.python-semantic-release.workflow.example.yml` | same bump logic as #5; auth stays `GITHUB_TOKEN` by default with a documented `RELEASE_TOKEN` PAT opt-in (consumer template) | CI template |
| 7 | `github/release.semantic-release.workflow.example.yml` | node: no CLI force-level → ask + gate only; **CI override deferred** (documented limitation) | CI template |
| 8 | `scripts/check-token-write.sh` | new — verify token write permission via `.permissions.push` on the repo object (admin-free); gh/token absent → fail-open (local); shared by CI preflight and local warning | script |
| 9 | `USAGE.md` / `USAGE.ko.md` | add the canonical "release token write permission (incl. PAT + `RELEASE_TOKEN` secret) — how to grant" section (harness-tier's own); `docs/plugins/marketplace-auto-update.md`'s one-liner links to it | doc |
| 10 | `skills/harness-authoring/references/commit-versioning-guide.md` | add authoring rule + section spec so the generated `docs/operations/commit-versioning-guide.md` includes a single canonical "CI token write permission — how to grant" section that guard messages link to | authoring instruction (SSOT) |
| 11 | `tests/test_flow_gate_check.py` | staging blocked without `bump.done` / passes with it; `bump` not a runtime gate; docs/dev unaffected | test |
| 12 | `tests/` (workflow + policy) | assert shipped `flow-tiers.yaml` staging gates include `bump`; assert workflow templates contain preflight + trailer-parse + force-level steps | test |

`scripts/flow_init_setup.py` copies `flow-tiers.yaml` and gate scripts to the host;
the added `bump` gate and the new `check-token-write.sh` ride along its existing
copy list — confirm `check-token-write.sh` is added to `COPY_FILES` so the local
warning can run on the host.

## 6. Error handling & edge cases

- **A. Gate invariants preserved** — `bump` is a standard evidence gate: when policy
  and config parse correctly but a staging commit lacks `bump.done`, block
  (fail-closed); on policy/config/internal error, fail-open (Invariant #1). cp949
  encoding defenses (Invariant #2) and exit-2 blocking (Invariant #3) unchanged.
- **B. Missing trailer in CI → safe fallback** — if `Release-Level:` is absent,
  `release.yml` releases via the existing auto-derivation (never breaks). `/flow`
  always writes the trailer on the normal path.
- **C. Token write-permission guard** — detection reads `.permissions.push` on the
  repo object via the GitHub API (admin-free; a live check confirmed it correctly
  reports read-only, whereas `actions/permissions/workflow` returned 403 without an
  `Administration: read` scope). Layers:
  (1) CI preflight (`check-token-write.sh`, run with `RELEASE_TOKEN`) fails fast with an
  actionable message + `$GITHUB_STEP_SUMMARY` banner when `push` is not true;
  (2) push-failure trap prints the same guidance (guaranteed fallback, since preflight
  detection may vary by environment);
  (3) local early warning — `/flow` runs the same check before staging promotion when a
  token/tool is available (`gh` or `curl` + a token); silently skips otherwise
  (fail-open, never blocks the gate — the observed "no `gh`, no local token" state is
  exactly this path).
  All guard text includes **how to obtain the permission** (see §7) and follows the
  host response-language convention (§ "Language" below).
- **D. main (stable) finalization — empirically verified (2026-07-03, scratch repo,
  harness-tier's exact SR config)**:
  - Happy path (forced level == commit-derived): stage `feat`+`--minor --as-prerelease`
    → `0.2.0-rc.1`; main plain `semantic-release version` finalizes → `0.2.0`. ✓
  - **Override higher (forced > commit-derived): stage `fix`+`--minor --as-prerelease`
    → `0.2.0-rc.1`; main plain → `0.1.1` — recomputes from the last *stable* tag and
    LOSES the override.** ✗ And forcing the same level on main double-bumps (`--minor`
    → `0.3.0`, based off the rc tag). So neither plain nor force-on-main is correct.
  - **Fix (adopted): main finalization = deterministic rc-strip.** If the current
    version is a prerelease (`X.Y.Z-rc.N`), drop the token → tag stable `vX.Y.Z`
    (compute-free). Verified: `0.2.0-rc.1` → `0.2.0`, and the next cycle correctly
    seeds off `v0.2.0` (`fix`+`--patch --as-prerelease` → `0.2.1-rc.1`). This carries
    the stage-forced level to the stable release in ALL cases.
  - Hotfix path (a commit on the production branch with no preceding rc) → fall back
    to plain `semantic-release version` (normal compute). Condition: prerelease present
    → strip; else compute.
  - The `Release-Level:` trailer is therefore needed only on the **stage** promotion
    (to force the rc level); main does not force, so it needs no trailer.
  - Sharp edge: an explicit `--major` **overrides** `major_on_zero=false` — forcing
    major on a 0.x project jumps to `1.0.0-rc.1`. The `AskUserQuestion` must warn when
    the choice is `major` on a 0.x project.
- **E. node limitation** — node `semantic-release` has no CLI force-level flag →
  ask + gate is enforced, but the CI override is deferred (documented). python-
  semantic-release (the repo default `release_tool`) is fully supported.
- **F. Session-commit scope** — the flow gate (layer 2) only intercepts Claude-session
  commits (existing CLAUDE.md property). Direct terminal promotions bypass by design —
  not a regression. **Per user decision (2026-07-03), session-commit enforcement is
  sufficient**; a git-native commit-msg trailer check for terminal commits is explicitly
  out of scope (addable later if desired).
- **G. Language** — every new user-facing string (prompts, warnings, guard messages,
  generated doc) reuses the existing convention: `risk-tiers.md` Commit Discipline →
  Language (host-configured response language; English default) and the precedent in
  `flow_gate_check.py`. No new i18n mechanism. Claude/`/flow` output follows the
  CLAUDE.md language directive automatically.
- **H. Introduction bootstrap** — the merge that introduces this feature is not itself
  gated (the gate/skill are not live yet at that moment); it applies from the next
  promotion.

## 7. Token write-permission — how to grant (guidance content)

Surfaced in the guard messages (concise, inline) and fully in the docs (#9, #10):

- **Primary** — Repository → Settings → Actions → General → **Workflow permissions**
  → select **"Read and write permissions"** → Save.
- **Organization override** — if the org caps Actions permissions to read-only
  (and enforces it), a org admin must relax it or allow repos to configure their own.
- **Protected branch / ruleset** — if the stable/prerelease branch restricts pushes,
  even a write token cannot push the release commit/tag: add the Actions bot/token to
  the bypass list, or use a token that can bypass.
- **PAT / GitHub App token (escalation)** — when `GITHUB_TOKEN` is insufficient
  (bypass protection, trigger downstream workflows): create a fine-grained PAT with
  `Contents: Read and write` (+ `Workflows: Read and write` if the release touches
  workflow files), store as a repo secret, reference it in `actions/checkout` `token:`
  and in the push.

Attach official GitHub docs links; verify exact menu paths during implementation
(do not fabricate — harness-rules 4).

## 8. Rollout / propagation

This repo is the plugin itself; the change is not automatically live everywhere:

1. **Release as `feat`** so `plugin.json` version bumps (Explicit-version gating —
   `docs`/`chore` do not propagate). Plugin-propagation discipline (risk-tiers).
2. **Consumers re-run `/flow-init`** to refresh the host's `flow-tiers.yaml` copy
   (adds the `bump` gate) and re-render `.github/workflows/release.yml` from the
   updated template, and to copy `check-token-write.sh`. The `.md` rules/skill updates
   ride along with the plugin update automatically once installed.
3. **harness-tier's own** concrete `release.yml` is live on the next stage push after
   merge; its `/flow` asking + `bump` gate become fully live after the updated plugin
   is reinstalled.

Prerequisite for harness-tier's own release: the `RELEASE_TOKEN` repo secret (fine-grained
PAT, `Contents: RW` + `Workflows: RW`, repo in access list) — **already registered**. The
old read-only PAT that lingers in a local `GITHUB_TOKEN` env var is unrelated to CI and can
be ignored.

## 9. Testing strategy

1. **Gate unit tests** (`tests/test_flow_gate_check.py`) — staging + no `bump.done`
   → blocked (`missing_gates` includes `bump`, exit 2); staging + `bump.done`
   (+`review.done`) → pass; `bump` not in `RUNTIME_GATES`; docs/dev(feature) tiers do
   not require `bump` (regression guard).
2. **Policy test** — shipped `flow-tiers.yaml` `staging.gates` includes `bump`; the
   `flow_init_setup` copy path carries it.
3. **Workflow structure test** (pytest, parse YAML) — `release.yml` + templates contain
   (a) the token preflight step, (b) `Release-Level:` parsing, (c) the `--as-prerelease`
   force invocation → template regression guard.
4. **Shared script** — `check-token-write.sh` passes ShellCheck; a small unit test of
   its permission-decode logic.
5. **Manual smoke** (verification-before-completion) — push a `Release-Level: minor`
   trailer commit to stage → confirm forced rc (`0.Y+1.0-rc.1`); flip Settings to
   read-only once → confirm the preflight fails fast with the how-to message.
6. **Static analysis** — new `.sh` via ShellCheck (hook runtime is Windows — mandatory);
   full `pre-commit` (ruff/gitlint/…) passes.

## 10. Open items / follow-ups

- Node `semantic-release` CI force-level override (E) — deferred; ask + gate only for now.
- rc→stable finalization (D) — **resolved by empirical test**: plain PSR loses an
  overridden level, force-on-main double-bumps → main uses **deterministic rc-strip**
  (hotfix falls back to plain compute). No trailer needed on main.
- Token-write detection method (C) — **resolved**: use `.permissions.push` (admin-free),
  per the live check; `actions/permissions/workflow` needs `Administration: read` and is
  not used.
- `major` on a 0.x project jumps to `1.0.0` (explicit `--major` overrides
  `major_on_zero=false`) — the bump prompt must warn on this choice. Whether to also
  offer a "stay 0.x" guard is an open UX question.
