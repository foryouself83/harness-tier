# Plugin marketplace auto-update conditions

For the harness-tier plugin to **auto-update at startup**, the conditions below must be met.
If any one is missing, the background update is silently skipped (no error, no propagation).

## 1. autoUpdate on

- Host `settings.json` `extraKnownMarketplaces.<name>.autoUpdate = true`.
- Third-party marketplaces are **OFF** by default, and the distributor cannot force it via `marketplace.json` (supply-chain
  boundary). The host must turn it on explicitly, and `/flow-init`'s `register_marketplace` registers it.

## 2. Change detection (version / SHA)

- Version resolution order: `plugin.json` version → marketplace entry version → git commit SHA.
- **Omit version and each commit is a new version** (SHA-based). harness-tier pins to a specific commit via `marketplace.json`'s
  `source.sha`, so a reinstall is triggered **only when this sha string changes**.
- Because it is a **public repository**, the background fetch needs no separate authentication (token · credential helper).

## Release — the plugin branch and its pin (distributor)

Consumers install from the `plugin` branch, whose root is the plugin alone
(`.github/scripts/plugin_dist.py` holds the shipped list): Anthropic's and OpenAI's directory
validators read every file a plugin source names, and tests, CI and evals are not the plugin. On
a main release `release.yml` rebuilds that branch from the release commit, then pins
`source.sha` in both `.claude-plugin/marketplace.json` and `.agents/plugins/marketplace.json`
to the new branch commit, with `ref: plugin`. A marketplace still names a main commit with no
`ref` until the first such release: a `ref` naming a branch that does not exist yet would break
every install in between.

- **Prerequisite**: repository Settings → Actions → Workflow permissions = **Read and write** (see [Promotion and release → Release token write permission](../usage/promotion-and-release.md#release-token-write-permission)).
- If the Action is off or when updating by hand:
  `python3 .github/scripts/plugin_dist.py build <dir>` → commit `<dir>` as the `plugin` branch ·
  push → `python3 .github/scripts/plugin_dist.py pin <that sha>` → commit · push main.

## Directory submissions

- **Anthropic** — repository `foryouself83/harness-tier`, tracked branch `plugin`, plugin path
  empty (the branch root). The directory follows the branch for new versions.
- **OpenAI** — upload the `harness-tier-codex-<version>.zip` attached to the GitHub release. It
  carries no lifecycle hook; `/flow-init` registers the Codex session hooks in the host.
