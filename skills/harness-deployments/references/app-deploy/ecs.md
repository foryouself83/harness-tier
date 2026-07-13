# App Deploy — AWS ECS (저작 레시피)

> 정적 템플릿이 아니다 — `/harness-deployments`가 AWS 계정/리전/클러스터/서비스/task-definition을 채워
> `.github/workflows/deploy-<name>.yml`을 직접 저작할 때 따르는 스켈레톤 + 결정 포인트.

## 공식 액션
- 인증(OIDC role assume): `aws-actions/configure-aws-credentials@v4`.
- ECR 로그인: `aws-actions/amazon-ecr-login@v2`.
- task-definition에 새 이미지 반영: `aws-actions/amazon-ecs-render-task-definition@v1`.
- 서비스 배포: `aws-actions/amazon-ecs-deploy-task-definition@v2` — 새 리비전 등록 + 서비스 갱신 + `wait-for-service-stability` 대기까지 처리.

## 인증 (OIDC 역할 assume — 시크릿 아님)
장수 `AWS_ACCESS_KEY_ID`/`AWS_SECRET_ACCESS_KEY`를 시크릿으로 두지 않는다. 대신:
1. AWS IAM에 GitHub OIDC 프로바이더(`token.actions.githubusercontent.com`, audience `sts.amazonaws.com`)를 **1회 등록**.
2. 그 프로바이더를 신뢰하는 IAM 역할을 만들고, trust policy의 `sub` 조건을 `repo:<owner>/<repo>:ref:refs/heads/<branch>`(또는 environment)로 제한.
3. 워크플로에서 `role-to-assume: arn:aws:iam::<account-id>:role/<GitHubActionsEcsRole>`로 assume.

## 워크플로우 스켈레톤

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
        description: "배포할 태그 (예: v1.2.3)"
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

컴포넌트는 오케스트레이터 `deploy.yml`이 `uses:`로 호출한다(`on: workflow_call` — `inputs.tag`는
release.yml이 해석한 실제 태그, 자기 해석 안 함). `workflow_dispatch`는 단독 수동 실행용.

## 결정 포인트 (스킬이 질문/판단할 것)
- task-definition JSON을 리포에 보관할지(권장 — 리비전 이력이 git에 남음) 아니면 AWS에 이미 등록된 최신 리비전을 `describe-task-definition`으로 가져올지.
- ECR(이 배포의 상류가 container-image 단계와 같은 리포지토리인지) vs 다른 레지스트리.
- 클러스터/서비스명/컨테이너명 — 감지 불가하면 사용자에게 확인.

## 롤백
ECS task definition은 불변(immutable)·버전 관리되므로, 롤백 = 이전 리비전을 다시 "현재"로 지정:
```bash
aws ecs update-service --cluster <cluster> --service <service> \
  --task-definition <family>:<prev-revision> --force-new-deployment
```
또는 `amazon-ecs-deploy-task-definition`에 이전 리비전 ARN을 다시 넘겨 재실행.

## 주의사항 (gotchas)
- task **execution** role(ECR pull, 로그 전송 권한)과 task **role**(애플리케이션이 실제 사용하는 AWS 권한)을 혼동하지 말 것 — 둘은 다른 IAM 역할이다.
- `wait-for-service-stability: true`를 빼면 배포 스텝이 태스크 기동 실패를 기다리지 않고 성공 처리될 수 있다 — 반드시 켠다.
- IAM 역할 trust policy의 audience는 `sts.amazonaws.com`이어야 한다(다르면 OIDC 토큰 교환이 거부된다).

## SSOT
| 항목 | URL |
|---|---|
| aws-actions/amazon-ecs-deploy-task-definition | https://github.com/aws-actions/amazon-ecs-deploy-task-definition |
| aws-actions/configure-aws-credentials | https://github.com/aws-actions/configure-aws-credentials |
| GitHub Docs — Configuring OIDC in AWS | https://docs.github.com/actions/deployment/security-hardening-your-deployments/configuring-openid-connect-in-amazon-web-services |
