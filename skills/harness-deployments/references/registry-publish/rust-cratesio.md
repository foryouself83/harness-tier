# Registry Publish — Rust (crates.io)

## Official action / build command
- Publish: there is no dedicated deploy action — set up the toolchain with `dtolnay/rust-toolchain@stable`, then run `cargo publish --token <token>`.
- Build: `cargo build --release` (publish itself includes packaging, so a separate build is for verification).

## Secrets
| Method | What's needed | Workflow config |
|---|---|---|
| Long-lived token (current default template) | `CARGO_REGISTRY_TOKEN` | `cargo publish --token "${{ secrets.CARGO_REGISTRY_TOKEN }}"` |
| **crates.io Trusted Publishing (OIDC)** | None | `permissions: id-token: write` + issue a temporary token with `rust-lang/crates-io-auth-action@v1` |

## Gotchas
- Trusted Publishing workflow form:
  ```yaml
  permissions:
    id-token: write
  steps:
    - name: Authenticate with crates.io
      id: auth
      uses: rust-lang/crates-io-auth-action@v1
    - name: Publish to crates.io
      # cargo reads CARGO_REGISTRY_TOKEN natively, so no --token flag: passing it would put the
      # secret in argv, where the runner's process list exposes it.
      env:
        CARGO_REGISTRY_TOKEN: ${{ steps.auth.outputs.token }}
      run: cargo publish
  ```
  The issued token is automatically revoked by the action's post-step when the job ends.
- **The first publish cannot be done with OIDC** — the crate must exist on crates.io through at least one manual/token publish before the GitHub repo can be linked as a Trusted Publishing target on the crate settings screen. Bootstrap with `CARGO_REGISTRY_TOKEN`, then switch to OIDC from the following releases.
- At registration, owner/repo and the workflow filename must be specified in the crates.io UI, and support for CI providers other than GitHub Actions is still limited (GitLab/CircleCI are on the roadmap).

## Corresponding template
`github/deploy.cratesio.workflow.example.yml` — the registry+rust combination is statically rendered by `/flow-init --render-deploy`.

## SSOT
| Item | URL |
|---|---|
| crates.io Trusted Publishing docs | https://crates.io/docs/trusted-publishing |
| rust-lang/crates-io-auth-action | https://github.com/rust-lang/crates-io-auth-action |
| RFC 3691 (Trusted Publishing for crates.io) | https://rust-lang.github.io/rfcs/3691-trusted-publishing-cratesio.html |
