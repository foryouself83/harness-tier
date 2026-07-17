# App Deploy — Kubernetes (authoring recipe)

> Not a static template — the skeleton + decision points to follow when `/harness-deployments` fills in
> the cluster/namespace/deployment name and authors `.github/workflows/deploy-<name>.yml` directly.

## Official actions / commands
- kubectl install: `azure/setup-kubectl@v4` (`with: version: '<pinned version>'`).
- Image rollout (pick one):
  - **imperative**: `kubectl set image deployment/<name> <container>=<image>:<tag> -n <namespace>`
  - **declarative (kustomize)**: `kubectl apply -k overlays/<env>` — the image tag is applied after patching the `images:` entry of `kustomization.yaml` in CI (`kustomize edit set image` or `kubectl apply -k`). kubectl 1.14+ bundles kustomize, so no separate action is needed.

## Secrets
| Secret | Purpose |
|---|---|
| `KUBE_CONFIG` | base64-encoded kubeconfig — must be based on a **ServiceAccount token scoped down to the namespace**; do not put in a cluster-admin kubeconfig as-is |

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

jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.tag }}
          fetch-depth: 0
      - uses: azure/setup-kubectl@v4
        with:
          version: 'v1.31.0'
      - name: Configure kubeconfig
        run: |
          mkdir -p "$HOME/.kube"
          echo "${{ secrets.KUBE_CONFIG }}" | base64 -d > "$HOME/.kube/config"
      - name: Roll out image
        run: kubectl set image deployment/<name> <container>=<image>:${{ inputs.tag }} -n <namespace>
      - name: Wait for rollout
        run: kubectl rollout status deployment/<name> -n <namespace> --timeout=5m
```

The orchestrator `deploy.yml` calls the component via `uses:` (`on: workflow_call` — `inputs.tag` is the
actual tag resolved by release.yml, not resolved by the component itself). `workflow_dispatch` is for standalone manual runs.

## Decision points (what the skill asks/decides)
- `kubectl set image` (one-shot, no GitOps history, fast) vs kustomize `apply -k` (declarative, the image tag stays in git so it is auditable) — recommend the former for a simple single-container deploy, the latter when managing several manifests together.
- Namespace/deployment name/container name — if not detectable, confirm with the user.
- Always put `kubectl rollout status` after the deploy step so CI ends in failure even when the rollout stalls (without it, `kubectl set image` returns success immediately and misses the actual pod start-up failure).

## Rollback
```bash
kubectl rollout undo deployment/<name> -n <namespace>            # the immediately previous revision
kubectl rollout undo deployment/<name> -n <namespace> --to-revision=<N>   # a specific revision
```
Leave these two commands in the operations guide (`docs/operations/deploy-guide.md`) as rollback pointers.

## Gotchas
- `KUBE_CONFIG` must be a ServiceAccount bound with least-privilege RBAC (roughly get/list/patch on `deployments` in the target namespace) — confining the blast radius of an incident to that namespace.
- The cluster API server must be reachable from the GitHub-hosted runner (either a public endpoint, or, if inside a VPC, a self-hosted runner is required).

## SSOT
| Item | URL |
|---|---|
| azure/setup-kubectl | https://github.com/Azure/setup-kubectl |
| kubectl rollout docs | https://kubernetes.io/docs/reference/kubectl/generated/kubectl_rollout/ |
| kubectl kustomize integration | https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/ |
