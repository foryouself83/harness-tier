# Registry Publish — Python (PyPI)

## Official action / build command
- Publish: `pypa/gh-action-pypi-publish@release/v1` — automatically finds and uploads the sdist/wheel under `dist/` (default `packages-dir: dist`).
- Build: `uv build` (recommended, uv projects) or `python -m build` (the standard PyPA build frontend) — both produce `dist/*.whl` + `dist/*.tar.gz`.

## Secrets
| Method | What's needed | Workflow config |
|---|---|---|
| **OIDC trusted publishing (recommended)** | None | Just add `permissions: id-token: write`. No `password`/`username` input needed — the action automatically exchanges the OIDC token for a temporary PyPI API token. |
| Long-lived token | `PYPI_API_TOKEN` | `with: password: ${{ secrets.PYPI_API_TOKEN }}` (username defaults to `__token__`) |

## Gotchas
- **OIDC only works if the trusted publisher is registered in the PyPI project settings first.** PyPI project page → *Publishing* tab → *Add a new publisher* → select GitHub → enter `owner/repo`, the workflow filename (e.g. `deploy-pypi.yml` — filename only, without a path), and optionally an environment name.
- A new project that has never been published to PyPI can be pre-registered as a "pending publisher" — the first publish converts that registration into an active publisher.
- OIDC and the token method are not mutually exclusive, but the action prefers the token path when a secret is set, so switching to OIDC requires removing `PYPI_API_TOKEN`.
- The `id-token: write` permission must be declared at the job level; without it, OIDC token issuance fails silently.

## Corresponding template
`github/deploy.pypi.workflow.example.yml` — already configured with OIDC (`id-token: write`) as the default and switchable to the case where `PYPI_API_TOKEN` is set. The registry+python combination is statically rendered by `/flow-init --render-deploy`, so this stack needs no separate authoring.

## SSOT
| Item | URL |
|---|---|
| gh-action-pypi-publish | https://github.com/pypa/gh-action-pypi-publish |
| PyPI trusted publishers guide | https://docs.pypi.org/trusted-publishers/ |
