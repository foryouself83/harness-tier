# App Deploy — Google Cloud Run (저작 레시피)

> 정적 템플릿이 아니다 — `/harness-deployments`가 GCP project/region/service를 채워
> `.github/workflows/deploy-<name>.yml`을 직접 저작할 때 따르는 스켈레톤 + 결정 포인트.

## 공식 액션
- 인증: `google-github-actions/auth@v3` — **WIF(Workload Identity Federation, OIDC) 권장.**
- 배포: `google-github-actions/deploy-cloudrun@v3` — 이미지 또는 소스에서 직접 배포 가능.

## 인증 (WIF/OIDC 권장 — 시크릿 아님)
| 방식 | 필요한 값 | 비고 |
|---|---|---|
| **WIF (권장)** | `workload_identity_provider`(풀/프로바이더 전체 리소스명), `service_account`(이메일) | 장수 키 없음 — GCP에 IAM Workload Identity Pool + Provider + 서비스 계정 바인딩을 **1회 사전 프로비저닝**해야 한다 |
| Service Account Key JSON(비권장) | `GCP_SA_KEY` 시크릿 | 장수 자격증명 — 유출 위험, WIF로 이관 권장 |

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

컴포넌트는 오케스트레이터 `deploy.yml`이 `uses:`로 호출한다(`on: workflow_call` — `inputs.tag`는
release.yml이 해석한 실제 태그, 자기 해석 안 함). `workflow_dispatch`는 단독 수동 실행용.

## 결정 포인트 (스킬이 질문/판단할 것)
- 이미지 배포(사전에 GHCR/Artifact Registry로 푸시된 이미지) vs 소스 배포(`deploy-cloudrun`이 buildpacks로 직접 빌드) — 이미지 배포가 registry-publish/container-image 단계와 자연스럽게 연결되므로 기본값으로 권장.
- project_id/region/service는 감지 불가 — 사용자에게 확인.
- Cloud Run이 pull할 이미지 레지스트리(Artifact Registry/GCR/인증된 GHCR)에 대한 접근 권한이 서비스 계정에 있는지 확인.

## 롤백
Cloud Run은 리비전을 자동 보존한다 — 별도 액션 없이 `gcloud` CLI로 트래픽을 이전 리비전으로 되돌린다:
```bash
gcloud run services update-traffic <service-name> --region <region> --to-revisions=<prev-revision>=100
```

## 주의사항 (gotchas)
- WIF 풀/프로바이더/서비스 계정 IAM 바인딩(`roles/run.admin`, `roles/iam.serviceAccountUser`)과, 특정 리포로 제한하는 attribute-condition을 GCP 쪽에서 **1회 사전 설정**해야 한다 — 이 스킬은 워크플로우만 저작하고 GCP IAM 리소스는 만들지 않는다(운영 가이드에 pointer만 남긴다).
- `id-token: write`가 없으면 `google-github-actions/auth`의 OIDC 토큰 요청이 조용히 실패한다.

## SSOT
| 항목 | URL |
|---|---|
| google-github-actions/deploy-cloudrun | https://github.com/google-github-actions/deploy-cloudrun |
| google-github-actions/auth | https://github.com/google-github-actions/auth |
| Cloud Run — GitHub Actions로 배포 | https://cloud.google.com/blog/products/devops-sre/deploy-to-cloud-run-with-github-actions |
