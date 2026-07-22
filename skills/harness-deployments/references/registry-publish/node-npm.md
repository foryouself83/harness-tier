# Registry Publish — Node (npm)

## Official action / build command
- Publish: there is no dedicated GitHub Action — set up Node/registry-url with `actions/setup-node@v6`, then run `npm publish --provenance --access public` directly via the npm CLI.
- Build: the project's build script (`npm ci && npm run build`) — a pure JS library may have no build step at all.

## Secrets
| Method | What's needed | Workflow config |
|---|---|---|
| Long-lived token (current default template) | `NPM_TOKEN` (Automation-type token) | `env: NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}`, `registry-url: https://registry.npmjs.org` |
| **npm Trusted Publishing (OIDC, 2025-07-31 GA)** | None | `permissions: id-token: write`. Requires npm CLI ≥ 11.5.1, Node ≥ 22.14.0. Running just `npm publish` (no separate `--provenance` needed — it is attached automatically on the OIDC path) publishes without a token. |

## Gotchas
- To use Trusted Publishing, go to npmjs.com package settings → **Trusted Publisher** section, select GitHub Actions, and register org/user, repo, workflow filename, and (optionally) environment — the same pre-registration pattern as PyPI/crates.io.
- `--provenance` requires Sigstore-based signing, so it only works on **GitHub-hosted runners** (self-hosted runners are not possible, since the public OIDC issuer cannot be verified).
- Scoped packages (`@org/name`) are published as private by default and fail unless `--access public` is specified (on the free plan).
- The current harness-tier static template (`deploy.npm.workflow.example.yml`) uses the `NPM_TOKEN` + `--provenance` combination as its default — to switch to Trusted Publishing, remove the template's `NODE_AUTH_TOKEN` step and keep only the permission above.

## Corresponding template
`github/deploy.npm.workflow.example.yml` — the registry+node combination is statically rendered by `/flow-init --render-deploy`.

## SSOT
| Item | URL |
|---|---|
| npm trusted publishers docs | https://docs.npmjs.com/trusted-publishers/ |
| GitHub Changelog — npm trusted publishing GA | https://github.blog/changelog/2025-07-31-npm-trusted-publishing-with-oidc-is-generally-available/ |
