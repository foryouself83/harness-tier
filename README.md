# harness-tier

**English** · [한국어](README.ko.md)

**A Claude Code plugin that scales AI process rigor to the risk of the task.**

Light for a one-line doc fix, heavy for core business-logic changes. Ships with **Teams
notifications** for team collaboration.

> 📖 Per-skill usage, settings, troubleshooting, and update/removal live in
> **[USAGE.md](USAGE.md)**.

## Core idea

Running the heavy AI pipeline (design → plan → implement → verify → review) **the same way on
every change** drags excessive process into fixing a typo. harness-tier does the opposite:

> **Scale the weight of the process to the risk.**

Three design choices follow.

1. **Risk classification → tier-specific process** — `/flow` splits an incoming task by **code
   vs. no code** (Docs / Dev), then runs only that tier's process and quality gates. The riskier
   the change, the more checks it clears before it can commit.
2. **Enforced by a gate, not by documentation** — discipline that lives only in docs is not
   followed. A **commit hook** enforces it: a commit that skipped `/flow` classification carries
   no tier marker and is **blocked (fail-closed)**.
3. **A harness you build once and port** — branch names, test commands, and every other
   repo-specific value sit in a config file, so a new repo picks the setup up with one
   `/flow-init`. The gate is **language-agnostic** (Go/JS/Java/C++/C#/Rust repos behave the same).

## Why harness-tier?

**Quality cannot silently erode.** AI writes code faster than anyone keeps it disciplined: tests
get skipped, docs drift, a "quick fix" ships unreviewed. harness-tier binds the checks a change
needs to its risk tier and **enforces them at commit time**, so a risky change cannot land
without clearing them.

Most Claude Code plugins pick one lane. harness-tier works on a different axis — it decides *how
much* process each change needs, and enforces it:

| Aspect | Methodology plugins (e.g. [`superpowers`](https://github.com/obra/superpowers)) | Guardrail / security plugins | **harness-tier** |
|--------|--------------------------------------------------------------------------------|------------------------------|------------------|
| Optimizes for | *How* to build well — TDD, debugging, spec-driven planning | Blocking dangerous actions, scanning for vulnerabilities | *How much* process a change needs |
| Applied to each task | The same ceremony every time | The same checks every time | **Scaled to the risk tier** |
| Enforcement | Advisory | Blocks specific actions | **Commit gate — an unclassified commit is blocked (fail-closed)** |

It does not compete with these — its Dev tier **runs on `superpowers`**, and it sits alongside
guardrail plugins. On that methodology layer it adds the governance they leave out: **generate
the harness → enforce the right process → keep docs and CI in sync → evolve from how you
work**.

| Capability | What you get |
|------------|--------------|
| **Risk-tier classification, enforced** | A typo fix commits instantly; a logic change must first clear design, review, and tests. A commit hook blocks anything that skipped `/flow` classification, and stays enforced when you commit from a `git worktree` (as the Dev pipeline often does). |
| **Project-harness scaffolding** | `/harness-init` fingerprints your stack — **12 languages and their frameworks** ([supported list](USAGE.md#auto-detected-languages-and-frameworks)) — and generates a tailored `CLAUDE.md` **plus auto-loaded `.claude/rules/`** (path-scoped, high-priority only for the files they match) and per-topic technical docs, from live web research plus a read of your code. By default it writes only `.md` files, never overwriting yours; with per-item consent it also scaffolds folder structure, CI, and security tooling. |
| **Quality gates in one file** | lint · static analysis · import-linting · tests · security scans · API contract tests, declared per module in a single `flow-config.yaml` — **modules, branches, and CI jobs extend freely**. **Language-agnostic**: the gate runs the commands you configure, a new repo inherits the setup with one `/flow-init`, and only the active tier's checks run. |
| **A review that cannot skip a file** | The `review` gate takes its file list from **`git` itself** — every changed file is reviewed and the count stated, so a large changeset never gets the treatment where an agent reviews some files and drops the rest. It then resolves the **callers of every changed public symbol** via the language server, `grep` as fallback, because that is where a regression lands and the diff never shows it. An independent review agent judges against your own `review_checklist`. |
| **A living SSOT for docs** | `doc-sync` diffs code and docs together — code changes propagate into the related markdown, doc changes are harmonized across the doc set, and `doc_style_check.py` proves the rewrite dropped no heading, code block, URL, or inline-code span. |
| **CI that writes itself** | `/flow-init` renders ready-to-run GitHub Actions from your config: a unit-test safety net, API contract tests, semantic-versioning releases that bump and tag from your Conventional Commits, wiki and prose verification, plus branch-naming and entropy checks — every job timeout-capped. |
| **Deployment on top of release** | `/harness-deployments` adds publishing to the artifact-less release: detect the stack, ask what to ship where, and render the CI — an orchestrator `release.yml` calls in the **same run** (no cross-workflow trigger, no PAT) that fans out to per-target components (PyPI · npm · Maven Central/Gradle · NuGet · crates.io · GHCR · Docker Hub, plus authored app deploys) with per-target least-privilege permissions. |
| **A harness that learns from you** | `harness-insight` aggregates your Claude Code activity, surfaces the instructions you keep repeating as **harness candidates**, and prunes stale memory. |
| **Team notifications built in** | A Microsoft Teams channel is pinged when the workflow waits on your input, or at any checkpoint you choose. |

## Requirements

For the gate to work **without silently no-op'ing**, you need the following. `/flow-init` checks
and (with your consent) installs most of them.

| Item | Level | Without it |
|------|-------|------------|
| `bash` + coreutils (`timeout`, `grep`, `sed`, `awk`) | Required | The gate silently no-ops (use Git Bash on Windows) |
| **Python ≥ 3.8** + **PyYAML** | Required | Commits are **blocked** (prevents silent non-enforcement) |
| `pre-commit` | Recommended | Commit-message lint (gitlint), push notify, and language-agnostic file checks (whitespace, newlines, YAML validation, etc.) are skipped — per-module lint/static/test still run via the flow gate |
| **`superpowers`** plugin | Required for Dev work | `/flow` stops at the Dev tier and guides installation |

## Installation

### 1. Install the dependencies first

**Python ≥ 3.8** — via your OS package manager (skip if already present).

```bash
# Windows
winget install Python.Python.3.12
# macOS
brew install python@3.12
# Debian/Ubuntu
sudo apt install python3 python3-pip
```

**PyYAML + pre-commit** — these must land in the **same `python3`** the gate hook calls, so
install with `python3 -m pip` (a venv-only `uv add` can be invisible to the hook).

```bash
python3 -m pip install pyyaml pre-commit
```

**[`superpowers`](https://github.com/obra/superpowers) plugin** — the Dev-tier implementation
pipeline relies on it.

```
/plugin marketplace add anthropics/claude-plugins-official
/plugin install superpowers@claude-plugins-official
```

### 2. Install the plugin

```
/plugin marketplace add foryouself83/harness-tier
/plugin install harness-tier@harness-tier
```

> A public repo, so install and auto-update need no authentication.

### 3. `/harness-init` — generate the project harness

Creates a `CLAUDE.md`, rules, and technical docs tailored to your project. **On a brand-new
project, start here** — the manual belongs in place before the gate is wired up. Skip it if you
already have a well-formed `CLAUDE.md`.

### 4. `/flow-init` — wire up governance

An interactive wizard generates the config file, registers the commit gate, checks the pre-commit
hooks, registers auto-update, and wires up Teams. Safe to re-run. Finally:

```bash
pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push
```

Then start day-to-day work with **`/flow <task description>`**.

> Everything created in the host repo after installation is gathered under a single
> **`.claude/harness-tier/`** directory (config, scripts, gate evidence). Layout in
> [USAGE.md](USAGE.md).

## What's included

| Kind | Item | Role |
|------|------|------|
| Skill | `/flow` | Classify risk → run the tier's workflow → record gate evidence |
| Skill | `/flow-init` | Setup/update wizard (initial setup + re-sync/reconfigure on re-run, preserving config) |
| Skill | `/flow-uninstall` | Remove harness-tier's host-side wiring |
| Skill | `/harness-init` | Framework detection + research/verification to generate a harness (`.md` by default, no overwrite) |
| Skill | `/wiki-init` | Build docs into a knowledge graph, no embeddings — front-matter-driven, setup wizard |
| Skill | `commit` | Author and issue one commit — type choice, 50/72, staging; `/flow` calls it at every commit step |
| Skill | `doc-sync` | Code ↔ doc synchronization + doc-set consistency + lossless-rewrite verification |
| Skill | `harness-insight` | Aggregate Claude Code activity over a period + insight report |
| Skill | `/harness-deployments` | Layer deployment (registry publish / container image / app deploy) on the release workflow — detect → ask → render deploy CI (opt-in, after `/flow-init`) |
| Skills | `playwright-scaffold` · `integration` · `performance` | E2E scaffold / integration & performance checks (non-enforcing manual skills) |
| Agents | `harness-researcher` · `harness-code-analyzer` · `harness-critic` | Research / code analysis / output verification for harness generation |
| Rule | `risk-tiers` | The single source of truth for risk classification + commit discipline |
| Rule | `doc-style` | The single source of truth for prose discipline in docs, comments, and docstrings |
| Hooks | SessionStart · Notification · PreToolUse(commit·merge) · PostToolUse(edit) | Rule injection + stale-build warning · Teams alerts · commit gate + merge-strategy gate · voids the review/doc-sync evidence an edit outdated |

> **Release CI token** — the rendered release workflow runs on the default `GITHUB_TOKEN` out of
> the box (grant Actions write permission); a `RELEASE_TOKEN` secret is an opt-in escalation.
> Details in [USAGE.md → Release token write permission](USAGE.md#release-token-write-permission).

## Update & removal

- **Update** — a plugin update does not change the host's copied scripts. Re-run `/flow-init` to
  re-sync (config and webhooks are preserved).
- **Removal** — ⚠️ **Always run `/flow-uninstall` before `/plugin uninstall`.** The cleanup tool
  lives inside the plugin, so removing the plugin first leaves the host-side settings
  uncleanable.

> The detailed update/removal procedure and manual cleanup are in [USAGE.md](USAGE.md) §7.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
