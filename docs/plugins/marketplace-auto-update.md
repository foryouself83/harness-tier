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

## Release — automatic sha pin (distributor)

`marketplace.json`'s `source.sha` is the effective pin, and consumer auto-update triggers a reinstall only when this sha
changes (§2). On every main push, `release.yml`'s `pin-marketplace-sha.py`
automatically updates and commits the sha to the just-released commit.

- **Prerequisite**: repository Settings → Actions → Workflow permissions = **Read and write** (see [USAGE.md → Release token write permission](../../USAGE.md#release-token-write-permission)).
- If the Action is off or when updating manually: commit · push the code → confirm the sha with `git rev-parse HEAD` →
  update `marketplace.json`'s `source.sha` to that value · commit · push.
