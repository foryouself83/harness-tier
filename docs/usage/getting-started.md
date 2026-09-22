# Getting started

**English** · [한국어](getting-started.ko.md) · [Usage guide](../../USAGE.md)

Installing the dependencies and the plugin is in the [README](../../README.md#installation).
This page covers what comes after: the order the setup commands run in, and what they leave
in your repo.

## Setup order

1. **`/harness-init`** — generates `CLAUDE.md`, `.claude/rules/` and the technical docs
   ([project harness](project-harness.md#harness-init--generate-the-project-harness)). On a new
   project, run it first: `/flow-init` drafts `modules[].checks` from those docs.
2. **`/flow-init`** — writes `flow-config.yaml`, registers the commit gate, and renders CI.
3. **`pre-commit install --hook-type pre-commit --hook-type commit-msg --hook-type pre-push`**
   — without it, commit-message lint, the file checks and the Teams push notice never run.
4. **`/flow <task>`** — every task from here on ([daily work](daily-work.md)).

Five commands are marked `disable-model-invocation`: `/flow-init`, `/flow-uninstall`,
`/harness-init`, `/harness-deployments` and `/wiki-init`. Claude never starts them from a
plain-language request — type the slash command.

## What `/flow-init` asks on a first run

`/flow-init` takes no arguments and is safe to re-run
([re-running it](update-and-removal.md#re-run-flow-init--sync-after-a-plugin-update)). A first
run, with no `flow-config.yaml` yet:

- checks the dependencies and offers to install what is missing — a required one still
  missing stops the run;
- asks for each `flow-config.yaml` slot: branches, which flows go through a pull request,
  the review checklist, doc-sync targets, and whether to enable the API contract test, the
  unit-test CI and the doc-style check;
- drafts `modules[].checks` from the harness docs, for you to edit;
- when a flow goes through a PR, reads the GitHub branch rulesets with `gh` and reports the
  gap ([PR workflow](promotion-and-release.md#pr-workflow-and-branch-rulesets));
- offers `srs-verify.yml` when `docs/srs/` exists;
- registers the commit gate and the marketplace auto-update, checks pre-commit, renders the
  CI workflows the config enables, and wires Teams.

`versioning` and `e2e` are not asked: they render from whatever the config holds. The example
ships `versioning.enable: true` with `python-semantic-release`, so a first run renders that
release workflow unless you change it ([CI workflows](ci-workflows.md)).

## What lands in your repo

Harness files sit under `.claude/harness-tier/`. Files whose location another tool fixes sit
where that tool looks for them.

| Path | Owner | git | Contents |
|------|-------|-----|----------|
| `.claude/harness-tier/config/flow-config.yaml` | you | tracked | Team-shared settings ([configuration](configuration.md)) |
| `.claude/harness-tier/config/flow-tiers.yaml` | plugin | tracked | Tier → gate policy; overwritten on every `/flow-init` run |
| `.claude/harness-tier/config/teams-webhooks.json` | you | tracked | Team Teams channels ([Teams](teams.md)) |
| `.claude/harness-tier/config/.teams-webhooks.local.json` | you | gitignored | Personal Teams webhook |
| `.claude/harness-tier/scripts/` | plugin | tracked | Gate scripts, also called by the rendered CI workflows |
| `.claude/harness-tier/.flow/` | runtime | gitignored | Gate evidence: the `tier` marker and `<gate>.done` files |
| `.claude/settings.json` | shared | tracked | The `PreToolUse` commit gate and the `harness-tier` marketplace entry |
| `.pre-commit-config.yaml` | you | tracked | Created from the example when absent; an existing file is only checked |
| `.gitignore` | you | tracked | Two lines: `.teams-webhooks.local.json` and `.claude/harness-tier/.flow/` |
| `CLAUDE.md` | you | tracked | The `harness-tier:teams` block, once a Teams channel is configured |
| `.github/workflows/` | you | tracked | The workflows the config enables ([CI workflows](ci-workflows.md)) |

Keep `scripts/` committed. `wiki-verify.yml`, `doc-style.yml` and `srs-verify.yml` skip when
the script is missing from the checkout, so they verify nothing; the `gitversion` and
`jreleaser` release workflows call `bump_version.py` with no such guard and fail.

The `tier` marker is bound to the branch it was written on. A `<gate>.done` file is not — see
[gate evidence](tiers-and-gates.md#gate-evidence).
