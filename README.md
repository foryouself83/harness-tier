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
   single `/flow-init`. The gate works **regardless of the project's language** (Go/JS/Java
   repos behave the same).

## Benefits

- **Process that's neither too much nor too little** — Typo fixes go through instantly;
  logic changes go through design, review, and tests. The tier decides.
- **Discipline you can't bypass** — Unclassified commits are blocked at commit time, so
  "skipping because I'm busy" is structurally prevented.
- **Portability across repos** — Governance config is split into files and replicated to a
  new repo as-is.
- **Automatic project-harness generation** — `/harness-init` detects your framework and
  generates a matching `CLAUDE.md`, rules, and technical docs from web research + code
  analysis.
- **Built-in team notifications** — Notifies a Microsoft Teams channel when waiting for
  input, or at any point you choose.

## Requirements

For the gate to work **without silently no-op'ing**, you need the following. Most of these
are checked and installed (with your consent) by `/flow-init`, so you don't have to set
everything up in advance — but you can prepare them yourself before installing.

| Item | Level | Without it |
|------|-------|------------|
| `bash` + coreutils (`timeout`, `grep`, `sed`, `awk`) | Required | The gate silently no-ops (use Git Bash on Windows) |
| **Python ≥ 3.8** + **PyYAML** | Required | Commits are **blocked** (prevents silent non-enforcement) |
| `pre-commit` | Recommended | Only lint/format/commit-message checks are skipped |
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

**`superpowers` plugin** — the Dev-tier implementation pipeline relies on it.

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
pre-commit install --hook-type commit-msg --hook-type pre-push
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
| Skills | `playwright-scaffold` · `integration` · `performance` | E2E scaffold / integration & performance checks (non-enforcing manual skills) |
| Agents | `harness-researcher` · `harness-code-analyzer` · `harness-critic` | Research / code analysis / output verification for harness generation |
| Rule | `risk-tiers` | The single source of truth for risk classification + commit discipline |
| Hooks | SessionStart · Notification · PreToolUse(commit) | Rule injection · Teams alerts · commit gate |

> **Release CI token** — the release workflow that `/flow-init` renders authenticates via
> `${{ secrets.RELEASE_TOKEN || secrets.GITHUB_TOKEN }}`, so it runs on the default
> `GITHUB_TOKEN` out of the box (just grant Actions write permission). A `RELEASE_TOKEN`
> secret is an **opt-in escalation** (bypass branch protection / trigger downstream) and,
> when unset, falls back to `GITHUB_TOKEN` — see [USAGE.md](USAGE.md) → "Release token
> write permission".

## Update & removal

- **Update** — When the plugin updates, the host's copied scripts don't change
  automatically. Re-run `/flow-init` to re-sync (config and webhooks are preserved).
- **Removal** — ⚠️ **Always run `/flow-uninstall` before `/plugin uninstall`.** The cleanup
  tool lives inside the plugin, so if you remove the plugin first, the host-side settings
  can't be cleaned up automatically.

> The detailed update/removal procedure and manual cleanup are in [USAGE.md](USAGE.md) §9.

## License

Apache License 2.0 — see [LICENSE](LICENSE).
