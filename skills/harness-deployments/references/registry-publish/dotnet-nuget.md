# Registry Publish — .NET (NuGet)

## 공식 액션 / 빌드 명령
- 배포: 전용 GitHub Action은 없다 — `actions/setup-dotnet@v4` 설치 후 `dotnet nuget push "**/*.nupkg" --source https://api.nuget.org/v3/index.json`을 실행한다.
- 빌드/패키징: `dotnet pack -c Release` (또는 프로젝트 컨벤션의 pack 명령).

## 시크릿
| 방식 | 필요한 것 | 워크플로 설정 |
|---|---|---|
| Long-lived API key(현재 기본 템플릿) | `NUGET_API_KEY` | `--api-key "${{ secrets.NUGET_API_KEY }}"` |
| **NuGet Trusted Publishing (OIDC, 순차 롤아웃 중)** | 없음(nuget.org 사용자명만) | `permissions: id-token: write` + `NuGet/login@v1` 액션으로 1시간짜리 임시 API key 발급 |

## 주의사항 (gotchas)
- Trusted Publishing 사용 시 워크플로에 `NuGet/login@v1` 스텝을 추가해 임시 키를 받아야 한다:
  ```yaml
  - uses: NuGet/login@v1
    id: login
    with:
      user: ${{ secrets.NUGET_USER }}   # nuget.org 프로필 이름(이메일 아님) — 시크릿로 보관 권장
  - run: dotnet nuget push "**/*.nupkg" --api-key ${{ steps.login.outputs.NUGET_API_KEY }} --source https://api.nuget.org/v3/index.json
  ```
- nuget.org에서 **Trusted Publishing** 정책을 사전 등록해야 한다: 계정 메뉴 → *Trusted Publishing* → repository owner/repo/workflow **파일명만**(경로 제외, 예: `deploy-nuget.yml`)/선택적 environment.
- 발급되는 임시 API key는 **1시간**만 유효 — push 직전에 발급받아야 하며, 발급 후 오래 대기하면 만료된다.
- 이 기능은 **순차 롤아웃 중**이라 계정에 아직 노출되지 않을 수 있다 — 안 보이면 `NUGET_API_KEY` 경로로 폴백.
- private repo에서 처음 정책을 만들면 7일간 "임시 활성" 상태이며, 그 기간 안에 실제 publish가 한 번 성공해야 영구 활성화된다.

## 대응 템플릿
`github/deploy.nuget.workflow.example.yml` — registry+c# 조합은 `/flow-init --render-deploy`가 정적 렌더링한다.

## SSOT
| 항목 | URL |
|---|---|
| NuGet.org Trusted Publishing | https://learn.microsoft.com/en-us/nuget/nuget-org/trusted-publishing |
