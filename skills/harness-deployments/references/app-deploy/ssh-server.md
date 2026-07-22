# App Deploy — SSH Server (authoring recipe)

> This file is **not a static template.** Rather than a render target that substitutes placeholders like
> `github/deploy.*.workflow.example.yml`, it is the skeleton + decision points to follow when `/harness-deployments`
> fills in detected values (host/port/deploy path/service name) directly and **authors** `.github/workflows/deploy-<name>.yml`.

## Official actions / methods (pick one)

| Method | Action/tool | When |
|---|---|---|
| A. Run the build+deploy script on the remote | `appleboy/ssh-action@v1` | When the server has the same toolchain as CI (git/runtime) and a remote `git pull && build && restart` flow is simple |
| B. Build in CI and transfer only the artifacts | rsync-over-ssh (`webfactory/ssh-agent@v0.9` + native `rsync`) | When you want the build finished on the GitHub runner and only the artifacts needed to run placed on the server (minimal server toolchain, faster and reproducible) |

**Recommended**: B where possible (build in CI, the server as a pure deploy target) — server dependencies shrink and failure points concentrate in the CI log.

## Secrets
| Secret | Purpose |
|---|---|
| `SSH_HOST` | Deploy target server host/IP |
| `SSH_USER` | Login account |
| `SSH_KEY` | Deploy-only SSH private key (PEM, the full `-----BEGIN ... PRIVATE KEY-----`) — issued exclusively for the server deploy account; do not reuse a human account's key |
| `SSH_PORT` (optional) | If not the default 22 |

## Workflow skeleton (method B — rsync-over-ssh)

```yaml
name: deploy-<name>

on:
  workflow_call:
    inputs:
      tag:
        required: true
        type: string
  workflow_dispatch:
    inputs:
      tag:
        description: "Tag to deploy (e.g. v1.2.3)"
        required: true
        type: string

concurrency:
  group: deploy-<name>-${{ github.ref }}
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 15           # substituted with flow-config.deploy.timeout_minutes
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.tag }}
          fetch-depth: 0
      - name: Build
        run: <build command>       # per-stack build command
      - uses: webfactory/ssh-agent@v0.9
        with:
          ssh-private-key: ${{ secrets.SSH_KEY }}
      - name: Deploy via rsync
        env:
          SSH_HOST: ${{ secrets.SSH_HOST }}
          SSH_USER: ${{ secrets.SSH_USER }}
        run: |
          mkdir -p ~/.ssh && ssh-keyscan -H "$SSH_HOST" >> ~/.ssh/known_hosts
          RELEASE=releases/$(date +%Y%m%d%H%M%S)
          rsync -az --delete ./dist/ "$SSH_USER@$SSH_HOST:/srv/app/$RELEASE/"
          ssh "$SSH_USER@$SSH_HOST" "ln -sfn /srv/app/$RELEASE /srv/app/current && systemctl restart app"
```

The orchestrator `deploy.yml` calls the component via `uses:` (`on: workflow_call` — `inputs.tag` is the
actual tag resolved by release.yml, not resolved by the component itself). `workflow_dispatch` is for standalone manual runs.

## Decision points (what the skill asks/decides)
- Whether it is the remote-execution type (A) or the artifact-transfer type (B).
- Deploy path/service restart command (systemd `restart`, pm2 `reload`, docker `compose up -d`, etc.) — if not detectable, confirm with the user.
- Port/known_hosts handling (with a fixed IP, populating it in CI every time with `ssh-keyscan` is safer — hardcoding known_hosts as a secret breaks on server key rotation).

## Zero-downtime deploy notes
- Take the **release directory + symlink swap** pattern as the default: upload the new version wholesale to `releases/<timestamp>/`, then atomically (`ln -sfn`) swap out the `current` symlink — it switches over instantly with no service interruption, and because the previous release directory remains, rollback is immediately possible with `ln -sfn releases/<prev> current`.
- Avoid running `git pull` directly on the service process to overwrite files (files changing mid-request can cause partial failures).
- With multiple servers (behind a load balancer), consider deploying one at a time sequentially (rolling) + health-checking before proceeding to the next target.

## SSOT
| Item | URL |
|---|---|
| appleboy/ssh-action | https://github.com/appleboy/ssh-action |
| webfactory/ssh-agent | https://github.com/webfactory/ssh-agent |
