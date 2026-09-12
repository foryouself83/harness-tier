# Step 2 — What the mechanical setup script does

Loaded by [`/flow-init`](../SKILL.md) Step 2. The script's own printed report is what you
relay; this list is what each line of it means, and which config key decides whether the
step runs at all.

The script performs the following, idempotently:

- **Copies** the gate scripts into `.claude/harness-tier/scripts/`, and the
  `flow-tiers.yaml` policy into `.claude/harness-tier/config/` (copied — not symlinked —
  so a host `settings.json` hook can run the scripts by `${CLAUDE_PROJECT_DIR}` path; the
  gate resolves `flow-tiers.yaml` from its sibling `config/` directory). The script's
  printed report is the single source of truth for which files it copied — relay it verbatim.
- **Registers** the commit gate in `.claude/settings.json` `hooks.PreToolUse` (skips
  if already present; no `if` field — `precommit-runner.sh` self-filters on stdin).
- **Registers** the `harness-tier` marketplace in `.claude/settings.json`
  `extraKnownMarketplaces` with `autoUpdate: true` (adds if absent, repairs the flag
  if present). Third-party marketplaces default to *no* auto-update and the author
  cannot force it via `marketplace.json` (supply-chain boundary) — so the host opts in
  here. Committed → the whole team auto-updates the plugin at startup.
- **Checks** the static-analysis hooks: **creates** `.pre-commit-config.yaml` from the
  example if absent (the `local` hooks are Python defaults to swap); if it **already
  exists, does NOT auto-merge** (a PyYAML round-trip would strip the team's
  comments/formatting) — instead **detects missing repos/hooks by `id` and reports
  them** for the user to add manually.
- **Appends** missing `.gitignore` lines (the gate-evidence `.flow/` directory and
  the personal webhook file), skipping any already present.
- **Renders** `.github/workflows/api-contract.yml` from `flow-config.contract_test`
  when `enable: true` (creates if absent; if it already exists, **does NOT overwrite** —
  reports for manual review). `.github/workflows/` is GitHub's enforced location — a
  documented exception to the `.claude/harness-tier/` rule. Skips entirely when
  `enable: false` or the section is absent.
- **Renders** `.github/workflows/unit-test.yml` from `flow-config.unit_test` when
  `enable: true` (same create-if-absent / never-overwrite / GitHub-forced-location
  rules as api-contract). The variable-length `unit_test.jobs[]` is rendered into a
  GitHub Actions `strategy.matrix.include` (one job per line), so each language/module
  runs in parallel with its own `timeout-minutes`. Skips when `enable: false` or the
  section is absent.
- **Does not render** `.github/workflows/wiki-verify.yml` — the workflow verifies a wiki,
  and at this point in a repo's life there is none to verify, so the question could only be
  put to a user with nothing to answer it from. [`/wiki-init`](../../wiki-init/SKILL.md)
  owns that render and the risk disclosure with it, at the step where the graph exists and
  `--verify` has passed on it. A host that already has the file from an earlier build keeps
  it — nothing here deletes it.
- **Renders** `.github/workflows/doc-style.yml` when `flow-config.doc_style.enable` is true
  (same create-if-absent / never-overwrite rules; skipped when the section is absent or the
  flag is false). It runs `doc_style_check.py --lint-config`, guarded on the script being in
  the checkout — a repo that gitignores `.claude/` has none and would otherwise go red on
  every push. A `flow-config.yaml` that is present but does not parse fails the job instead
  of reading as "off": one typo would take the whole layer down with nothing red to say so.
  The flag is a run switch as well as a render switch — the script empties its own path list
  when `enable` is falsy — so turning it back off silences an already-rendered file without
  deleting it.
- **Renders** `.github/workflows/e2e.yml` from `flow-config.e2e` when `enable: true` —
  copied as-is, no tokens, same create-if-absent / never-overwrite rules. Its flag is a
  render switch only: the no-op lives in the template (a detect step that finds no
  `playwright.config.*` skips the run), so setting it back to false leaves an already
  rendered file running where doc-style's would go quiet. Report the
  `/playwright-scaffold` pointer the step prints when no config exists: the flag renders the
  file, a suite is what makes it mean anything. It blocks nothing.
