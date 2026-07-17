# Container Image — Docker Hub

## Official actions
- Login: `docker/login-action@v3` — `username: ${{ secrets.DOCKERHUB_USERNAME }}`, `password: ${{ secrets.DOCKERHUB_TOKEN }}` (when the registry input is omitted, the default is Docker Hub).
- Build+push: `docker/build-push-action@v6` — same usage as GHCR.

## Secrets
| Secret | Value |
|---|---|
| `DOCKERHUB_USERNAME` | Docker Hub account/organization username |
| `DOCKERHUB_TOKEN` | **Access Token** (not the account password) — Docker Hub → Account Settings → Security → *New Access Token*, issued with Read & Write scope |

## OIDC / trusted-publishing alternative
**None** — as of this document's writing, Docker Hub does not support GitHub OIDC-based trusted publishing. An Access Token is the only authentication path, so issue a least-privilege token (Read & Write on that repo only) and rotate it periodically.

## Gotchas
- You must issue and use an **Access Token** — do not put the account login password in a secret (for 2FA accounts, password login is blocked at the API in the first place).
- The token scope must be set to "Read & Write" for the push to succeed (the default "Read-only" fails).
- The free plan has an anonymous pull rate limit — if CI pulls base images frequently, pulling while logged in (`docker/login-action`) can ease the limit.

## Corresponding template
`github/deploy.dockerhub.workflow.example.yml` — the image+docker-hub combination is statically rendered by `/flow-init --render-deploy`.

## SSOT
| Item | URL |
|---|---|
| docker/login-action | https://github.com/docker/login-action |
| docker/build-push-action | https://github.com/docker/build-push-action |
| Docker Hub Access Tokens docs | https://docs.docker.com/security/for-developers/access-tokens/ |
