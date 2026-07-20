# Registry Publish — .NET (NuGet)

## Official action / build command
- Publish: there is no dedicated GitHub Action — install `actions/setup-dotnet@v4`, then run `dotnet nuget push "**/*.nupkg" --source https://api.nuget.org/v3/index.json`.
- Build/packaging: `dotnet pack -c Release` (or the pack command of the project's convention).

## Secrets
| Method | What's needed | Workflow config |
|---|---|---|
| Long-lived API key (current default template) | `NUGET_API_KEY` | `env: NUGET_API_KEY: ${{ secrets.NUGET_API_KEY }}` + `--api-key "$NUGET_API_KEY"` (never interpolate into `run:`) |
| **NuGet Trusted Publishing (OIDC, phased rollout in progress)** | None (only the nuget.org username) | `permissions: id-token: write` + the `NuGet/login@v1` action to issue a 1-hour temporary API key |

## Gotchas
- When using Trusted Publishing, add a `NuGet/login@v1` step to the workflow to receive a temporary key:
  ```yaml
  - uses: NuGet/login@v1
    id: login
    with:
      user: ${{ secrets.NUGET_USER }}   # nuget.org profile name (not the email) — keeping it in a secret is recommended
  - env:
      NUGET_API_KEY: ${{ steps.login.outputs.NUGET_API_KEY }}   # dotnet does not read this natively, so --api-key stays — but via env, never interpolated into run:
    run: dotnet nuget push "**/*.nupkg" --api-key "$NUGET_API_KEY" --source https://api.nuget.org/v3/index.json
  ```
- The **Trusted Publishing** policy must be pre-registered on nuget.org: account menu → *Trusted Publishing* → repository owner/repo/workflow **filename only** (excluding the path, e.g. `deploy-nuget.yml`)/optional environment.
- The issued temporary API key is valid for **1 hour** only — it must be issued right before the push, and expires if you wait long after issuance.
- This feature is **in phased rollout**, so it may not be exposed on your account yet — if you don't see it, fall back to the `NUGET_API_KEY` path.
- When the policy is first created on a private repo, it is in a "temporarily active" state for 7 days, and an actual publish must succeed once within that period for it to become permanently active.

## Corresponding template
`github/deploy.nuget.workflow.example.yml` — the registry+c# combination is statically rendered by `/flow-init --render-deploy`.

## SSOT
| Item | URL |
|---|---|
| NuGet.org Trusted Publishing | https://learn.microsoft.com/en-us/nuget/nuget-org/trusted-publishing |
