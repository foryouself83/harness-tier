# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This repo is the **Claude Code plugin itself** (not a consumer of it). For usage, see [README.md](README.md)·[USAGE.md](USAGE.md).
For component authoring specs (agent/hook/skill frontmatter), verify against the official docs as the SSOT, not model knowledge:
[plugins-reference](https://code.claude.com/docs/en/plugins-reference.md) · [hooks](https://code.claude.com/docs/en/hooks.md) · [skills](https://code.claude.com/docs/en/skills.md) · [permissions](https://code.claude.com/docs/en/permissions.md).
(`allowed-tools` pre-approves tools, it does not restrict — enforced at point of use by
[`.claude/rules/skill-frontmatter.md`](.claude/rules/skill-frontmatter.md) and [`tests/test_skills.py`](tests/test_skills.py).)

## Commands

Gate scripts are Python; run tooling via `uv`.

```bash
uv sync                                                  # install dependencies
uv run pytest                                            # run all tests
uv run pytest tests/test_flow_gate_check.py::<name>      # run a single test
uv run ruff check && uv run ruff format --check          # lint + format check
uv run pre-commit run --all-files                        # full static analysis
uv run python -m evals.run --dry-run --all               # session count + wall-clock, no model calls
uv run python -m evals.run                               # measure only skills whose description changed
uv run python -m evals.run --skill integration --capture-fixtures   # …+ stream fixture candidates (*.jsonl.new)
```

When modifying `*.sh`, verify with ShellCheck (the hook runtime is Windows, so bugs are hidden as FAIL-OPEN — see Invariants).

## Folder structure

`agents/`·`hooks/hooks.json`·`skills/` declare no path in the manifest — they are **auto-discovered from their default locations** (adding a component = just adding a file). Each entry below is folder + purpose; the per-file detail lives in the folder itself.

```text
.claude-plugin/  plugin.json (minimal manifest) · marketplace.json (self-exposed; source=github + immutable sha pin)
agents/          harness-researcher · harness-code-analyzer · harness-critic
hooks/           hooks.json (SessionStart rule injection + Notification) · inject-risk-tiers.sh
skills/          /slash = skill — one dir each; open the dir for its SKILL.md
rules/           risk-tiers.md (SSOT: tier classification + commit discipline) · harness-rules.md (SSOT: harness-gen)
                 — both SHIP to consumers, unlike .claude/rules/ which never leaves this repo
.claude/rules/   skill-frontmatter.md — dev-only, fires on opening a skills/**/*.md (never ships)
scripts/         gate + setup scripts — authoritative copy list = flow_init_setup.py COPY_FILES (open the dir for the rest)
github/          *.workflow.example.yml SOURCEs /flow-init renders (CI · release.<tool> · deploy.<target>);
                 authoring gotchas (timeout-minutes cap · no ${{ }} in a run: block) guarded by test_flow_init_setup.py
.github/         this repo's OWN CI (release · branch-naming · entropy-check · unit-test, all timeout-capped) · scripts/pin-marketplace-sha.py
flow-tiers.yaml            tier→gates + merge_strategy — plugin-owned, immutable
flow-config.example.yaml   host environment slots (real file → host .claude/harness-tier/config/, team-shared)
tests/           pytest over scripts/ · test_skills.py (skill FILES: frontmatter/links/refs) · test_evals.py (model-free half of evals/)
evals/           skill-invocation measurement (cases.yaml · run.py · scores.py) — NOT shipped → commit as test:/chore:
```

## Architecture (must-know)

- **Installed outside the host (in a cache) → dual paths.** `${CLAUDE_PLUGIN_ROOT}` = reads (templates/policy), `${CLAUDE_PROJECT_DIR}` = writes (host config/evidence). **Never write into the plugin directory.**
- **Host writes group under `${CLAUDE_PROJECT_DIR}/.claude/harness-tier/`**: `scripts/` (copied gate scripts, git-tracked) · `config/` (flow-config.yaml + flow-tiers.yaml) · `.flow/` (gate evidence, gitignored). The only exceptions are files whose location external tools force: `.gitignore` · `.pre-commit-config.yaml` · `.claude/settings.json` · `.github/workflows/`.
- **The commit gate is registered in the host's `settings.json`** (not the plugin's hooks.json) — for deny-enforcement reliability and because `${CLAUDE_PLUGIN_ROOT}` isn't resolved there. `/flow-init` **copies** the gate scripts + `flow-tiers.yaml` policy into the host.
- **Script propagation is one-way**: `scripts/`·`flow-tiers.yaml` (SOURCE·SSOT) → cache → host copies. **Fix only the SOURCE** — host copies are overwritten on reinstall (`/flow-init` re-syncs, `/flow-uninstall` cleans up). Never edit the host copies directly.
- **Policy vs. environment**: `flow-tiers.yaml` (tier→gates + `merge_strategy`; immutable · plugin-owned · do not edit) vs. `flow-config.yaml` (branches · modules; host-owned · team-shared · git-tracked). `merge_strategy` names flows by `flow-config.branches` **key**, so the policy stays environment-free.
- **Tier-discipline SSOT = [`rules/risk-tiers.md`](rules/risk-tiers.md)** — `flow.md` · `flow-tiers.yaml` · the gates all defer to it.
- **Versioning & release**: plugin.json `version` gates updates — a sha change alone does not propagate; reinstall happens only on a version bump. `.github/workflows/release.yml` (python-semantic-release) bumps from the Conventional Commits of pushes to main/stage; on main, `pin-marketplace-sha.py` immutably pins the marketplace `source.sha`. **Therefore consumer-facing `.md` (rules/skills) changes must be committed as `feat`/`fix`, not `docs`, to propagate.** Branches: `feature/*` → dev → stage → main.
- **The plugin's `rules/` is not auto-loaded** → `hooks/inject-risk-tiers.sh` injects it as `additionalContext` at SessionStart.
- **Three verification layers**, independent (per-gate mechanism → [`rules/risk-tiers.md`](rules/risk-tiers.md) · [`flow-tiers.yaml`](flow-tiers.yaml)):
  1. **Hygiene** — the host's `.pre-commit-config.yaml` (git-native): gitlint · teams-notify-push · language-agnostic checks.
  2. **Flow gate** — `precommit-runner.sh` (PreToolUse), **Claude-session commits & merges only** (terminal commits and CI bypass it). Blocks unclassified commits, then runs the tier's `gates`; `git merge` takes a separate path judged against `merge_strategy`. Gate internals & the FAIL-OPEN rules → **Invariants** below.
  3. **CI (GitHub Actions)** — `/flow-init` renders `api-contract.yml` + `unit-test.yml`, closing layer 2's blind spot (it never sees direct/terminal/CI commits). Every job is timeout-capped.
- **Skill invocation is measured, not assumed** — `tests/test_skills.py` checks a skill *file* is well-formed; `evals/` checks it is actually *reached* (half a skill's failure modes live in its `description`). Gate SSOT = [`evals/scores.py`](evals/scores.py); mechanics in [`evals/`](evals/).
- **Deployment is not a verification layer** — a release-decoupled opt-in: `/harness-deployments` writes `flow-config.deploy` and renders per-target `deploy-<name>.yml` components + a generated `deploy.yml` orchestrator; `release.yml` calls it via `workflow_call` in-run (no PAT). None of it gates a commit.

## Invariants (break these and the gate is silently neutralized)

When modifying the gate scripts (`scripts/*`, `hooks/*.sh`), these must be preserved:

1. **FAIL-OPEN, except for missing dependencies, unclassified commits, and merge-strategy violations** — transient internal errors let the gate pass rather than block (so a broken gate never permanently blocks commits). **Exception 1**: if the required tools (`python3` ≥ 3.8 · `PyYAML`) are missing or outdated, `precommit-runner.sh` **blocks the commit** (to prevent silent non-enforcement; independent of the project's language). To detect commits even without python3, it falls back to grepping the raw stdin. **Exception 2**: when the policy (`flow-tiers.yaml`) and config (`flow-config.yaml`) parse correctly but the `tier` marker is absent, `flow_gate_check` **blocks** such an **unclassified commit** (to prevent the gate being silently neutralized by bypassing `/flow`). The criterion, however, is not "the file exists" but "**parsing succeeded** (= it works reliably)" — if the policy/config is broken, it is treated as an internal error and fails open. **Exception 3**: a `git merge` whose flags violate its branch flow's `merge_strategy` row is **blocked** — a missing `require` flag or a present `forbid` flag, nothing else. This one differs in kind from the other two: it is decided **from the command string alone** and reads no repository state, so no internal error can misfire it. Everything uncertain around it fails open (no policy · no matching rule · an unparseable command · a command naming another worktree · a rebase that only *warns*). (superpowers cannot be detected from the shell → guarded in `/flow`·`/flow-init`.)
2. **Windows encoding** — the hook's Python runs in a cp949 locale. A Korean `print()` / UTF-8 `open()` can FAIL-OPEN on an encoding error and *let a commit that should be blocked pass through*. Do not omit the `PYTHONUTF8=1` · `force_utf8_io()` · `encoding="utf-8"` defenses.
3. **Block = exit 2 + a reason on stderr** (emit the JSON `permissionDecision` too, but the actual blocking mechanism is exit 2).
4. **No `if` field on the settings.json gate hook** — it would suppress the hook from firing per build. Do filtering via `precommit-runner.sh`'s stdin self-filter.
5. **`/flow-init` is idempotent** — no duplicate additions of the settings.json hook · pre-commit id · .gitignore line (match-then-skip).
6. **Worktree re-designation stays FAIL-OPEN** — `CLAUDE_PROJECT_DIR` is fixed at session start, so `precommit-runner.sh` detects the commit's actual worktree by branch-key (`flow_gate_check.py --resolve-worktree` → `_harness_paths.working_root`) and re-points `ROOT` to it, so status/diff/tier-marker/module-lint all read the worktree. Any uncertainty — detached HEAD · `--git-common-dir` mismatch · no worktree · parse/exception — must return main (= current behavior); never newly block. Same-repo identity uses **`--git-common-dir` equality, never a path prefix** (sibling `…/kit` vs `…/kit-feature` must not false-match). The commit self-filter must keep matching `git -C <wt> commit` (not just the bare `git commit` substring), else a worktree commit slips the gate entirely.
