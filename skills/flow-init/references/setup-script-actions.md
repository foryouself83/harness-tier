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
- **Removes** `.claude/rules/harness-tier/` if an older `/flow-init` left it there: Claude
  Code loads every file under `.claude/rules/` in full each session, so the rule now reaches a
  session only through the SessionStart hook's own short prose summary. A symlink there is
  unlinked, never followed, and a parent that resolves outside the host is refused.
- **Registers** the commit gate in `.claude/settings.json` `hooks.PreToolUse` (skips
  if already present; no `if` field — `precommit-runner.sh` self-filters on stdin).
- **Registers** the commit gate in `.codex/hooks.json` too when `flow-config.harnesses`
  names `codex` (Claude is always registered; Codex is opt-in). Copies its wrapper
  scripts (`harness/codex/gate.sh`/`gate.cmd`) alongside the Claude gate scripts, under
  the same fail-closed rule — a wrapper that failed to copy withholds `flow-tiers.yaml`
  exactly like a missing Claude gate script. Relays Codex's own trust notes: whether
  Codex considers the project trusted (`.codex/` is ignored otherwise), and that the
  hook still needs approving in Codex's `/hooks` before it runs.
- **Renders** a managed block into the root `AGENTS.md` when `flow-config.harnesses` names
  `codex`: Codex reads neither `CLAUDE.md` nor `.claude/rules/`, so the block carries them —
  except `.claude/rules/harness-tier/` (the plugin's own rules the bullet above cleans up),
  which the SessionStart hook injection already covers and would otherwise duplicate. Generated
  from those files and never written back to them. Text outside the block is kept.
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
- **Seeds** the design-doc templates into `design_docs.templates` (default
  `.claude/harness-tier/templates/design-docs/`), one file at a time, skipping every file
  that already exists — the host copy is the consumer's to edit, and every `/design-*`
  check and render follows it. `.gitignore` also gains `design_docs.output` when
  `gitignore_output: true`.
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
- **Renders** the release workflows from `flow-config.versioning` when `enable: true` (same
  create-if-absent / never-overwrite rules): `release.yml` from the template matching
  `release_tool`, case-insensitive — `python-semantic-release` · `semantic-release` ·
  `jreleaser` · `gitversion` · `cargo-release`; any other value is reported and skipped.
  `branch-naming.yml` and `entropy-check.yml` each render only under their own
  `branch_naming.enable` / `entropy.enable`. Relay the skip line: an unrecognised tool leaves
  the repo with no release workflow and nothing else says so.
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

The same script's `--uninstall` mode (run by [`/flow-uninstall`](../../flow-uninstall/SKILL.md))
always unregisters the Codex gate from `.codex/hooks.json`, regardless of what
`flow-config.harnesses` currently lists — a host that dropped `codex` from the list after
installing it still has the hook file, and uninstall means gone, not "gone unless the config
forgot to mention it". It removes the `AGENTS.md` block the same way, and the file too when
nothing else is left in it and every Claude source could be read — a source it cannot read
may link to `AGENTS.md`, so the emptied file stays.
