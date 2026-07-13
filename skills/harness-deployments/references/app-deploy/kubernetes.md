# App Deploy — Kubernetes (저작 레시피)

> 정적 템플릿이 아니다 — `/harness-deployments`가 클러스터/네임스페이스/디플로이먼트명을 채워
> `.github/workflows/deploy-<name>.yml`을 직접 저작할 때 따르는 스켈레톤 + 결정 포인트.

## 공식 액션 / 명령
- kubectl 설치: `azure/setup-kubectl@v4` (`with: version: '<pinned version>'`).
- 이미지 롤아웃(택1):
  - **imperative**: `kubectl set image deployment/<name> <container>=<image>:<tag> -n <namespace>`
  - **declarative(kustomize)**: `kubectl apply -k overlays/<env>` — 이미지 태그는 `kustomization.yaml`의 `images:` 항목을 CI에서 패치(`kustomize edit set image` 또는 `kubectl apply -k`) 후 적용. kubectl 1.14+는 kustomize를 내장하므로 별도 액션 불필요.

## 시크릿
| 시크릿 | 용도 |
|---|---|
| `KUBE_CONFIG` | base64 인코딩된 kubeconfig — **네임스페이스로 스코프를 좁힌 ServiceAccount 토큰** 기반이어야 하며, 클러스터 admin kubeconfig를 그대로 넣지 않는다 |

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

컴포넌트는 오케스트레이터 `deploy.yml`이 `uses:`로 호출한다(`on: workflow_call` — `inputs.tag`는
release.yml이 해석한 실제 태그, 자기 해석 안 함). `workflow_dispatch`는 단독 수동 실행용.

## 결정 포인트 (스킬이 질문/판단할 것)
- `kubectl set image`(단발성, GitOps 이력 없음, 빠름) vs kustomize `apply -k`(선언형, 이미지 태그가 git에 남아 감사 추적 가능) — 단일 컨테이너 단순 배포면 전자, 매니페스트를 여러 개 함께 관리하면 후자를 권장.
- 네임스페이스/디플로이먼트명/컨테이너명 — 감지 불가하면 사용자에게 확인.
- `kubectl rollout status`를 배포 스텝 뒤에 반드시 넣어, 롤아웃이 멈춰도 CI가 실패로 끝나게 한다(넣지 않으면 `kubectl set image`는 즉시 성공 리턴하고 실제 파드 기동 실패를 놓친다).

## 롤백
```bash
kubectl rollout undo deployment/<name> -n <namespace>            # 바로 이전 리비전
kubectl rollout undo deployment/<name> -n <namespace> --to-revision=<N>   # 특정 리비전 지정
```
운영 가이드(`docs/operations/deploy-guide.md`)에 이 두 명령을 롤백 포인터로 남긴다.

## 주의사항 (gotchas)
- `KUBE_CONFIG`는 최소권한 RBAC(대상 네임스페이스의 `deployments`에 대한 get/list/patch 정도)로 바인딩된 ServiceAccount여야 한다 — 사고 시 피해 반경을 그 네임스페이스로 한정.
- GitHub 호스팅 러너에서 클러스터 API 서버에 도달 가능해야 한다(퍼블릭 엔드포인트이거나, VPC 내부라면 self-hosted 러너 필요).

## SSOT
| 항목 | URL |
|---|---|
| azure/setup-kubectl | https://github.com/Azure/setup-kubectl |
| kubectl rollout 문서 | https://kubernetes.io/docs/reference/kubectl/generated/kubectl_rollout/ |
| kubectl kustomize 통합 | https://kubernetes.io/docs/tasks/manage-kubernetes-objects/kustomization/ |
