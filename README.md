# harness-tier

**English** · [한국어](README.ko.md)

**A Claude Code plugin that automatically scales AI process rigor to the risk of the task.**

Light for a one-line doc fix, heavy for core business-logic changes — it never forces
the same heavyweight procedure on every task. It also ships with **Teams notifications**
for team collaboration.

> 📖 Detailed usage of each skill and setting, troubleshooting, and update/removal are
> in **[USAGE.md](USAGE.md)**.

## Core idea

Running the heavy AI pipeline (design → plan → implement → verify → review) **the same
way on every change** means even fixing a typo drags in excessive process. harness-tier
does the opposite:

> **Scale the weight of the process to the risk.**

That one sentence leads to three design choices.

1. **Risk classification → tier-specific process** — When `/flow` receives a task, it
   first splits the risk (Docs / Dev) by **code vs. no code**, then runs only the process
   and quality gates that tier needs. The riskier the change, the more checks it must pass
   before it can commit.
2. **Enforced by a gate, not by documentation** — Discipline that lives only in docs
   doesn't get followed. harness-tier enforces it with a **commit hook**. A commit that
   didn't go through `/flow` classification has no tier marker and is **blocked
   (fail-closed)**.
3. **A harness you build once and port** — Repo-specific values like branch names and
   test commands are all pulled out into a config file, so a new repo picks it up with a
   single `/flow-init`. The gate works **regardless of the project's language** (Go/JS/Java/
   C++/C#/Rust repos behave the same).

## Why harness-tier?

**The core payoff — quality can't silently erode.** AI writes code faster than anyone keeps
it disciplined: tests get skipped, docs drift, a "quick fix" ships unreviewed. harness-tier
binds the checks a change needs to its risk tier and **enforces them at commit time**, so a
risky change can't land without clearing them — the quality bar holds even at AI speed,
because the gate won't let anything slip below it.

Most Claude Code plugins pick one lane. harness-tier works on a different axis — it decides
*how much* process each change needs, and enforces it:

| Aspect | Methodology plugins (e.g. [`superpowers`](https://github.com/obra/superpowers)) | Guardrail / security plugins | **harness-tier** |
|--------|--------------------------------------------------------------------------------|------------------------------|------------------|
| Optimizes for | *How* to build well — TDD, debugging, spec-driven planning | Blocking dangerous actions, scanning for vulnerabilities | *How much* process a change actually needs |
| Applied to each task | The same ceremony every time | The same checks every time | **Scaled to the risk tier** |
| Enforcement | Advisory | Blocks specific actions | **Commit gate — an unclassified commit is blocked (fail-closed)** |

harness-tier doesn't compete with these — its Dev tier **runs on `superpowers`**, and it
sits happily alongside guardrail plugins. On top of that methodology layer it adds the
governance they leave out — **generate the harness → enforce the right process → keep docs
and CI in sync → evolve from how you actually work**:

| Capability | What you get |
|------------|--------------|
| **Risk-tier classification, enforced** | A typo fix commits instantly; a logic change must first clear design, review, and tests. The tier decides, and a commit hook blocks anything that skipped `/flow` classification — and it stays enforced even when you commit from a `git worktree` (as the Dev pipeline often does). A quality floor nothing slips below, however busy the day. |
| **Project-harness scaffolding** | `/harness-init` fingerprints your stack — **12 languages and their frameworks** ([supported list](USAGE.md#auto-detected-languages-and-frameworks)) — and generates a tailored `CLAUDE.md` **plus auto-loaded `.claude/rules/`** (the current Claude Code rules convention — path-scoped, high-priority only for the files they match, going beyond the usual single-`CLAUDE.md` harness) and per-topic technical docs, from live web research plus a read of your actual code. By default it writes only `.md` files (never overwriting yours); with per-item consent it can also scaffold the folder structure, CI, and security tooling. |
| **Quality gates in one file** | lint · static analysis · import-linting · tests · security scans · API contract tests, declared per module in a single `flow-config.yaml` — **freely add and extend modules, branches, and CI jobs**. **Language-agnostic** (the gate just runs the commands you configure); a new repo inherits the whole setup with one `/flow-init`, and it runs only what the active tier needs. |
| **A living SSOT for docs** | `doc-sync` diffs code and docs together — code changes propagate into the related markdown, and doc changes are harmonized across the whole doc set, so documentation stops drifting from the code it describes. |
| **CI that writes itself** | `/flow-init` renders ready-to-run GitHub Actions from your config: a unit-test safety net, API contract tests, semantic-versioning releases that bump and tag from your Conventional Commits, plus branch-naming and entropy checks — every job timeout-capped. |
| **Deployment on top of release** | `/harness-deployments` adds publishing to the artifact-less release: detect the stack, ask what to ship where, and render the CI — an orchestrator `release.yml` calls in the **same run** (no cross-workflow trigger, no PAT) that fans out to per-target components (PyPI · npm · Maven Central/Gradle · NuGet · crates.io · GHCR · Docker Hub, plus authored app deploys) with per-target least-privilege permissions. |
| **A harness that learns from you** | `harness-insight` aggregates your Claude Code activity, surfaces the instructions you keep repeating as **harness candidates**, and prunes stale memory — so the harness keeps sharpening around how your team actually works. |
| **Team notifications built in** | A Microsoft Teams channel is pinged when the workflow is waiting on your input, or at any checkpoint you choose. |

## Requirements

For the gate to work **without silently no-op'ing**, you need the following. Most of these
are checked and installed (with your consent) by `/flow-init`, so you don't have to set
everything up in advance — but you can prepare them yourself before installing.

| Item | Level | Without it |
|------|-------|------------|
| `bash` + coreutils (`timeout`, `grep`, `sed`, `awk`) | Required | The gate silently no-ops (use Git Bash on Windows) |
| **Python ≥ 3.8** + **PyYAML** | Required | Commits are **blocked** (prevents silent non-enforcement) |
| `pre-commit` | Recommended | Commit-message lint (gitlint), push notify, and language-agnostic file checks (whitespace, newlines, YAML validation, etc.) are skipped — per-module lint/static/test still run via the flow gate |
| **`superpowers`** plugin | Required for Dev work | `/flow` stops at the Dev tier and guides installation |

## Installation

### 1. Install the dependencies first

**Python ≥ 3.8** — install via your OS package manager (skip if already present).

```bash
# Windows
winget install Python.Python.3.12
# macOS
brew install python@3.12
# Debian/Ubuntu
sudo apt install python3 python3-pip
```

**PyYAML + pre-commit** — these must land in the **same `python3`** the gate hook calls,
so install with `python3 -m pip` (a venv-only `uv add` may be invisible to the hook).

```bash
python3 -m pip install pyyaml pre-commit
```

**[`superpowers`](https://github.com/obra/superpowers) plugin** — the Dev-tier
implementation pipeline relies on it.

```
/plugin marketplace add anthropics/claude-plugins-official
/plugin install superpowers@claude-plugins-official
```

### 2. Install the plugin

```
/plugin marketplace add foryouself83/harness-tier
/plugin install harness-tier@harness-tier
```

> It's a public repo, so install and auto-update work without any authentication.

### 3. `/harness-init` — generate the project harness

Creates a `CLAUDE.md`, rules, and technical docs tailored to your project. **If you're
starting a brand-new project, start here** — it's natural to have the manual (the harness)
in place before wiring up the gate. If you already have a well-formed `CLAUDE.md`, you can
skip this.

### 4. `/flow-init` — wire up governance

An interactive wizard generates the config file, registers the commit gate, checks the
pre-commit hooks, registers auto-update, and wires up Teams (safe to re-run). Finally:

```bash
pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push
```

After that, start day-to-day work with **`/flow <task description>`**.

> Everything created in the host repo after installation is gathered under a single
> **`.claude/harness-tier/`** directory (config, scripts, gate evidence). See
> [USAGE.md](USAGE.md) for the detailed layout.

## What's included

| Kind | Item | Role |
|------|------|------|
| Skill | `/flow` | Classify risk → run the tier's workflow → record gate evidence |
| Skill | `/flow-init` | Setup/update wizard (initial setup + re-sync/reconfigure on re-run, preserving config) |
| Skill | `/flow-uninstall` | Remove harness-tier's host-side wiring |
| Skill | `/harness-init` | Framework detection + research/verification to generate a harness (`.md` by default, no overwrite) |
| Skill | `doc-sync` | Code ↔ doc synchronization + doc-set consistency |
| Skill | `harness-insight` | Aggregate Claude Code activity over a period + insight report |
| Skill | `/harness-deployments` | Layer deployment (registry publish / container image / app deploy) on the release workflow — detect → ask → render deploy CI (opt-in, after `/flow-init`) |
| Skills | `playwright-scaffold` · `integration` · `performance` | E2E scaffold / integration & performance checks (non-enforcing manual skills) |
| Agents | `harness-researcher` · `harness-code-analyzer` · `harness-critic` | Research / code analysis / output verification for harness generation |
| Rule | `risk-tiers` | The single source of truth for risk classification + commit discipline |
| Hooks | SessionStart · Notification · PreToolUse(commit) | Rule injection · Teams alerts · commit gate |

> **Release CI token** — the rendered release workflow runs on the default `GITHUB_TOKEN`
> out of the box (just grant Actions write permission); a `RELEASE_TOKEN` secret is an
> opt-in escalation. Details in
> [USAGE.md → Release token write permission](USAGE.md#release-token-write-permission).

## Update & removal

- **Update** — When the plugin updates, the host's copied scripts don't change
  automatically. Re-run `/flow-init` to re-sync (config and webhooks are preserved).
- **Removal** — ⚠️ **Always run `/flow-uninstall` before `/plugin uninstall`.** The cleanup
  tool lives inside the plugin, so if you remove the plugin first, the host-side settings
  can't be cleaned up automatically.

> The detailed update/removal procedure and manual cleanup are in [USAGE.md](USAGE.md) §7.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
