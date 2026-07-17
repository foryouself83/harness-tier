# Container Image — GitHub Container Registry (GHCR)

## Official actions
- Login: `docker/login-action@v3` — `registry: ghcr.io`, `username: ${{ github.actor }}`, `password: ${{ secrets.GITHUB_TOKEN }}`.
- Build+push: `docker/build-push-action@v6` — `context: .`, `push: true`, `tags: <owner>/<repo>:<tag>`, etc.

## Secrets
**Not needed.** Use the repository's default `GITHUB_TOKEN` as-is — but the job permissions must declare `packages: write`:
```yaml
permissions:
  contents: read
  packages: write
```

## OIDC / trusted-publishing alternative
Not applicable — on GHCR the GITHUB_TOKEN is itself a short-lived credential already scoped to the repository, so no separate OIDC exchange is needed (the simplest case).

## Gotchas
- `GITHUB_TOKEN` works only within **the scope of that repository** — it cannot push to packages owned by another repo/org.
- After the first push of a new package, the default visibility may be **private** — to expose it publicly, either change the visibility directly in the GHCR package settings, or turn on "Inherit access from source repository" in the org settings so the package is automatically linked to and inherited by the repo.
- The image name must be lowercase (`ghcr.io/<owner>/<name>`) — a repo name with uppercase letters mixed in produces a tag error.

## Corresponding template
`github/deploy.ghcr.workflow.example.yml` — the image+docker combination is statically rendered by `/flow-init --render-deploy`.

## SSOT
| Item | URL |
|---|---|
| docker/login-action | https://github.com/docker/login-action |
| docker/build-push-action | https://github.com/docker/build-push-action |
| GitHub Docs — Working with the Container registry | https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry |
