# harness-tier Usage Guide

**English** · [한국어](USAGE.ko.md)

If [README](README.md) is "core idea + installation", this guide is the per-topic detail:
settings, skill behavior, troubleshooting, and update/removal. Each topic below has an English
page and a Korean twin under [`docs/usage/`](docs/usage/); `doc-sync` keeps every twin in step.
(The internals of *how* the plugin works are in the developer-facing [CLAUDE.md](CLAUDE.md).)

| Topic | Answers |
|-------|---------|
| [Getting started](docs/usage/getting-started.md) | Setup order, what lands in your repo |
| [Configuration](docs/usage/configuration.md) | Every `flow-config.yaml` key, why `flow-tiers.yaml` is not edited |
| [Tiers and gates](docs/usage/tiers-and-gates.md) | The four tiers, what each gate checks, merge strategy, evidence |
| [Daily work](docs/usage/daily-work.md) | `/flow` · `/commit` · `/doc-sync` · `/prose-review` |
| [Promotion and release](docs/usage/promotion-and-release.md) | `/release-commit`, PR mode and branch rulesets, the release token |
| [Deployments](docs/usage/deployments.md) | `/harness-deployments` |
| [CI workflows](docs/usage/ci-workflows.md) | Every workflow `/flow-init` can render, and its switch |
| [Project harness](docs/usage/project-harness.md) | `/harness-init` (with the language table) · `/wiki-init` · `harness-insight` |
| [Manual verification](docs/usage/manual-verification.md) | `/integration` · `/performance` · `playwright-scaffold` |
| [Design deliverables](docs/usage/design-docs.md) | `/design-srs` · `/design-sds` · `/design-architecture` · `/design-api` · `/design-erd` · `/design-table` |
| [Teams](docs/usage/teams.md) | Webhook setup, when each channel fires |
| [Troubleshooting](docs/usage/troubleshooting.md) | What each block message means, and the no-op gate |
| [Update and removal](docs/usage/update-and-removal.md) | Re-running `/flow-init`, `/flow-uninstall`, manual cleanup |

## License

Apache License 2.0 — see [LICENSE](LICENSE); third-party licenses in
[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md).
