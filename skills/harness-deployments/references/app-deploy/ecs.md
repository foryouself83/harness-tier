# App Deploy — AWS ECS (authoring recipe)

> Not a static template — the skeleton + decision points to follow when `/harness-deployments` fills in
> the AWS account/region/cluster/service/task-definition and authors `.github/workflows/deploy-<name>.yml` directly.

## Official actions
- Auth (OIDC role assume): `aws-actions/configure-aws-credentials@v4`.
- ECR login: `aws-actions/amazon-ecr-login@v2`.
- Apply the new image to the task-definition: `aws-actions/amazon-ecs-render-task-definition@v1`.
- Service deploy: `aws-actions/amazon-ecs-deploy-task-definition@v2` — handles registering the new revision + updating the service + waiting on `wait-for-service-stability`.

## Auth (OIDC role assume — not a secret)
Do not keep long-lived `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY` as secrets. Instead:
1. **Register once** a GitHub OIDC provider (`token.actions.githubusercontent.com`, audience `sts.amazonaws.com`) in AWS IAM.
2. Create an IAM role that trusts that provider, and restrict the trust policy's `sub` condition to `repo:<owner>/<repo>:ref:refs/heads/<branch>` (or an environment).
3. Assume it in the workflow via `role-to-assume: arn:aws:iam::<account-id>:role/<GitHubActionsEcsRole>`.

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
  id-token: write        # OIDC role assume

jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 15
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.tag }}
          fetch-depth: 0
      - uses: aws-actions/configure-aws-credentials@v4
        with:
          role-to-assume: arn:aws:iam::<account-id>:role/<GitHubActionsEcsRole>
          aws-region: <region>
      - uses: aws-actions/amazon-ecr-login@v2
        id: ecr
      - name: Render task definition
        id: render
        uses: aws-actions/amazon-ecs-render-task-definition@v1
        with:
          task-definition: <path-to-task-def.json>
          container-name: <container-name>
          image: ${{ steps.ecr.outputs.registry }}/<repo>:${{ inputs.tag }}
      - uses: aws-actions/amazon-ecs-deploy-task-definition@v2
        with:
          task-definition: ${{ steps.render.outputs.task-definition }}
          service: <ecs-service-name>
          cluster: <ecs-cluster-name>
          wait-for-service-stability: true
```

The orchestrator `deploy.yml` calls the component via `uses:` (`on: workflow_call` — `inputs.tag` is the
actual tag resolved by release.yml, not resolved by the component itself). `workflow_dispatch` is for standalone manual runs.

## Decision points (what the skill asks/decides)
- Whether to keep the task-definition JSON in the repo (recommended — the revision history stays in git) or to fetch the latest revision already registered in AWS via `describe-task-definition`.
- ECR (whether this deploy's upstream is the same repository as the container-image stage) vs a different registry.
- Cluster/service name/container name — if not detectable, confirm with the user.

## Rollback
ECS task definitions are immutable and versioned, so rollback = designating a previous revision as "current" again:
```bash
aws ecs update-service --cluster <cluster> --service <service> \
  --task-definition <family>:<prev-revision> --force-new-deployment
```
Or re-run `amazon-ecs-deploy-task-definition` passing the previous revision ARN again.

## Gotchas
- Do not confuse the task **execution** role (ECR pull and log shipping permissions) with the task **role** (the AWS permissions the application actually uses) — they are different IAM roles.
- Omitting `wait-for-service-stability: true` can let the deploy step be treated as successful without waiting for a task start-up failure — always turn it on.
- The IAM role trust policy's audience must be `sts.amazonaws.com` (otherwise the OIDC token exchange is rejected).

## SSOT
| Item | URL |
|---|---|
| aws-actions/amazon-ecs-deploy-task-definition | https://github.com/aws-actions/amazon-ecs-deploy-task-definition |
| aws-actions/configure-aws-credentials | https://github.com/aws-actions/configure-aws-credentials |
| GitHub Docs — Configuring OIDC in AWS | https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services |
