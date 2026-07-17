# App Deploy — Google Cloud Run (authoring recipe)

> Not a static template — the skeleton + decision points to follow when `/harness-deployments` fills in
> the GCP project/region/service and authors `.github/workflows/deploy-<name>.yml` directly.

## Official actions
- Auth: `google-github-actions/auth@v3` — **WIF (Workload Identity Federation, OIDC) recommended.**
- Deploy: `google-github-actions/deploy-cloudrun@v3` — can deploy from an image or directly from source.

## Auth (WIF/OIDC recommended — not a secret)
| Method | Required values | Notes |
|---|---|---|
| **WIF (recommended)** | `workload_identity_provider` (full pool/provider resource name), `service_account` (email) | No long-lived key — an IAM Workload Identity Pool + Provider + service account binding must be **provisioned once up front** on GCP |
| Service Account Key JSON (not recommended) | `GCP_SA_KEY` secret | Long-lived credential — leak risk, migrating to WIF recommended |

## Workflow skeleton

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
  id-token: write        # WIF/OIDC

jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.tag }}
          fetch-depth: 0
      - uses: google-github-actions/auth@v3
        with:
          workload_identity_provider: <projects/.../workloadIdentityPools/.../providers/...>
          service_account: <deploy-sa>@<project-id>.iam.gserviceaccount.com
      - uses: google-github-actions/deploy-cloudrun@v3
        with:
          project_id: <project-id>
          region: <region>
          service: <service-name>
          image: <image>:${{ inputs.tag }}
```

The orchestrator `deploy.yml` calls the component via `uses:` (`on: workflow_call` — `inputs.tag` is the
actual tag resolved by release.yml, not resolved by the component itself). `workflow_dispatch` is for standalone manual runs.

## Decision points (what the skill asks/decides)
- Image deploy (an image pushed to GHCR/Artifact Registry beforehand) vs source deploy (`deploy-cloudrun` builds directly with buildpacks) — image deploy connects naturally to the registry-publish/container-image stage, so recommend it as the default.
- project_id/region/service cannot be detected — confirm with the user.
- Verify the service account has access to the image registry Cloud Run will pull from (Artifact Registry/GCR/authenticated GHCR).

## Rollback
Cloud Run retains revisions automatically — roll traffic back to a previous revision with the `gcloud` CLI, no separate action needed:
```bash
gcloud run services update-traffic <service-name> --region <region> --to-revisions=<prev-revision>=100
```

## Gotchas
- The WIF pool/provider/service-account IAM bindings (`roles/run.admin`, `roles/iam.serviceAccountUser`) and the attribute-condition restricting to a specific repo must be **set up once up front** on the GCP side — this skill only authors the workflow and does not create GCP IAM resources (it leaves only a pointer in the operations guide).
- Without `id-token: write`, `google-github-actions/auth`'s OIDC token request fails silently.

## SSOT
| Item | URL |
|---|---|
| google-github-actions/deploy-cloudrun | https://github.com/google-github-actions/deploy-cloudrun |
| google-github-actions/auth | https://github.com/google-github-actions/auth |
| Cloud Run — Deploy with GitHub Actions | https://cloud.google.com/blog/products/devops-sre/deploy-to-cloud-run-with-github-actions |
