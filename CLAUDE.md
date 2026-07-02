# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This repo is the **Claude Code plugin itself** (not a consumer of it). For usage, see [README.md](README.md)·[USAGE.md](USAGE.md).
For component authoring specs (command/agent/hook/skill frontmatter), verify against the official docs as the SSOT, not model knowledge:
[plugins-reference](https://code.claude.com/docs/en/plugins-reference.md) · [hooks](https://code.claude.com/docs/en/hooks.md) · [skills](https://code.claude.com/docs/en/skills.md).

## Commands

Gate scripts are Python; run tooling via `uv`.

```bash
uv sync                                                  # install dependencies
uv run pytest                                            # run all tests
uv run pytest tests/test_flow_gate_check.py::<name>      # run a single test
uv run ruff check && uv run ruff format --check          # lint + format check
uv run pre-commit run --all-files                        # full static analysis
```

When modifying `*.sh`, verify with ShellCheck (the hook runtime is Windows, so bugs are hidden as FAIL-OPEN — see Invariants).

## Folder structure

`agents/`·`hooks/hooks.json`·`skills/` declare no path in the manifest — they are **auto-discovered from their default locations** (adding a component = just adding a file).

```text
.claude-plugin/
  plugin.json              plugin manifest (minimal — name/description/version/author)
  marketplace.json         marketplace manifest (harness-tier exposes itself; plugin source=github + immutable sha pin)
agents/     harness-researcher · harness-code-analyzer · harness-critic   (harness research/analysis/critique)
hooks/      hooks.json (SessionStart rule injection + Notification) · inject-risk-tiers.sh
skills/     flow · flow-init · flow-uninstall · harness-init · doc-sync · harness-authoring · harness-insight
            playwright-scaffold · integration · performance   (/slash = skill)
rules/      risk-tiers.md  ← SSOT for tier classification & commit discipline (not auto-loaded; injected by a hook)
            harness-rules.md  ← SSOT for harness-generation discipline (loaded by the harness-init skill)
scripts/    flow_gate_check.py · precommit-runner.sh · teams_alert.py · notify-push.sh
            check-deps.sh (dependency check & guidance) · flow_init_setup.py (flow-init setup/re-run + --uninstall cleanup)
            harness_scaffold.py (harness-init scaffold generation)
            harness_insight.py (harness-insight transcript aggregation — project-agnostic, emits a temporary txt)
github/     api-contract.workflow.example.yml   contract-test SOURCE (/flow-init renders it via flow-config.contract_test)
            release.python-semantic-release.workflow.example.yml · release.semantic-release.workflow.example.yml
            branch-naming.workflow.example.yml · entropy-check.workflow.example.yml
            (the 4 above are rendered by /flow-init via flow-config.versioning — release picks one via release_tool)
.github/    workflows/ (release·branch-naming·entropy-check — harness-tier's own CI) · scripts/pin-marketplace-sha.py (pins the marketplace sha at release)
flow-tiers.yaml            tier→gates policy (plugin-owned, immutable)
flow-config.example.yaml   host environment-value slots (the real file is the host's .claude/harness-tier/config/flow-config.yaml, team-shared & git-tracked)
tests/      test_flow_gate_check.py · test_flow_init_setup.py · test_harness_scaffold.py · test_harness_insight.py
```

## Architecture (must-know)

- **The plugin is installed outside the host (in a cache) → dual paths.** `${CLAUDE_PLUGIN_ROOT}` = reads (templates/policy), `${CLAUDE_PROJECT_DIR}` = writes (host config/evidence). **Never write into the plugin directory.**
- **Host writes are grouped by purpose under `${CLAUDE_PROJECT_DIR}/.claude/harness-tier/`** (no scattering across the root): `scripts/` (copied gate scripts, plugin-owned & git-tracked) · `config/` (flow-config.yaml (team-shared & git-tracked — developers of the same repo use identical settings) · flow-tiers.yaml (tier→gates policy — plugin-owned, overwritten on every install, do not edit) · webhooks; host-owned) · `.flow/` (gate evidence, gitignored). The only exceptions are the files whose location is forced by external tools: `.gitignore` (git) · `.pre-commit-config.yaml` (pre-commit) · `.claude/settings.json` (Claude Code) · `.github/workflows/` (GitHub Actions).
- **The commit gate is registered in the host's `settings.json`** (not the plugin's hooks.json), because of deny-enforcement reliability and because `${CLAUDE_PLUGIN_ROOT}` is not resolved there. `/flow-init` **copies** the gate scripts to the host's `.claude/harness-tier/scripts/` and the `flow-tiers.yaml` policy to `.claude/harness-tier/config/`.
- **Script propagation is one-way**: `scripts/`·`flow-tiers.yaml` (SOURCE·SSOT) → cache (reinstall) → `<host>/.claude/harness-tier/scripts/` (gate scripts)·`config/flow-tiers.yaml` (policy execution copy). Fix only the SOURCE; never edit the host copies directly (they are overwritten on reinstall). After a plugin update, sync the host copies by re-running `/flow-init` (config left intact); clean up the host with `/flow-uninstall`.
- **Policy vs. environment values**: `flow-tiers.yaml` (tier→gates, immutable · plugin-owned · do not edit) vs. `flow-config.yaml` (branches · modules, host-owned · team-shared · git-tracked, human-edited). Both live in `.claude/harness-tier/config/` but their ownership differs.
- **Tier-discipline SSOT = `rules/risk-tiers.md`** — `flow.md`·`flow-tiers.yaml`·the gates all defer to it. Change the discipline here, then bring whatever diverges into line.
- **Versioning & release (tightly coupled)**: for harness-tier distribution, plugin.json `version` gates updates (Claude Code Explicit-version — when the manifest has a version, a sha change alone does not propagate; reinstall happens only on a version bump). `.github/workflows/release.yml` (python-semantic-release) parses the Conventional Commits (feat/fix) of pushes to main/stage to bump the pyproject + plugin.json version and tag (`vX.Y.Z`), and on main, `pin-marketplace-sha.py` **immutably pins** the marketplace `source.sha` into the release commit (pin-to-parent — no tag refs allowed; supply-chain integrity). Therefore `.md` (rules/skills) changes that affect consumer behavior must be committed as `feat`/`fix`, not `docs`, to propagate (risk-tiers Commit Discipline). Branches: `feature/*` → dev → stage → main.
- **The plugin's `rules/` is not auto-loaded** → `hooks/inject-risk-tiers.sh` injects it as `additionalContext` at SessionStart (the output key differs per host).
- **Three verification layers** (independent): static analysis & hygiene = the host's `.pre-commit-config.yaml` (git-native — gitlint (commit-msg) · teams-notify-push (pre-push) · language-agnostic hygiene; per-module lint/static/import_lint/test moved to layer 2) / flow gate = `precommit-runner.sh` (**Claude-session commits only** — PreToolUse, self-filters to `git commit` only; direct terminal commits and CI do not go through it — blocks unclassified commits + runs only the items enabled in the tier's `gates` (`flow-tiers.yaml`): `precommit` = **lint/static/import_lint/test of the changed modules (every commit)**, `security-scan` = a full-module `security` scan on staging/release promotion — both are RUNTIME_GATES, so the hook runs them directly without a marker, and removing one from that tier's `gates` disables just that check) / **contract testing = `.github/workflows/api-contract.yml` (GitHub Actions, collaboration/promotion branches only — schemathesis, rendered by `/flow-init` via `flow-config.contract_test`)**.

## Invariants (break these and the gate is silently neutralized)

When modifying the gate scripts (`scripts/*`, `hooks/*.sh`), these must be preserved:

1. **FAIL-OPEN, except that missing dependencies & unclassified commits are fail-CLOSED** — transient internal errors let the gate pass rather than block (so a broken gate never permanently blocks commits). **Exception 1**: if the required tools (`python3` ≥ 3.8 · `PyYAML`) are missing or outdated, `precommit-runner.sh` **blocks the commit** (to prevent silent non-enforcement; independent of the project's language). To detect commits even without python3, it falls back to grepping the raw stdin. **Exception 2**: when the policy (`flow-tiers.yaml`) and config (`flow-config.yaml`) parse correctly but the `tier` marker is absent, `flow_gate_check` **blocks** such an **unclassified commit** (to prevent the gate being silently neutralized by bypassing `/flow`). The criterion, however, is not "the file exists" but "**parsing succeeded** (= it works reliably)" — if the policy/config is broken, it is treated as an internal error and fails open. (superpowers cannot be detected from the shell → guarded in `/flow`·`/flow-init`.)
2. **Windows encoding** — the hook's Python runs in a cp949 locale. A Korean `print()` / UTF-8 `open()` can FAIL-OPEN on an encoding error and *let a commit that should be blocked pass through*. Do not omit the `PYTHONUTF8=1` · `force_utf8_io()` · `encoding="utf-8"` defenses.
3. **Block = exit 2 + a reason on stderr** (emit the JSON `permissionDecision` too, but the actual blocking mechanism is exit 2).
4. **No `if` field on the settings.json gate hook** — it would suppress the hook from firing per build. Do filtering via `precommit-runner.sh`'s stdin self-filter.
5. **`/flow-init` is idempotent** — no duplicate additions of the settings.json hook · pre-commit id · .gitignore line (match-then-skip).
