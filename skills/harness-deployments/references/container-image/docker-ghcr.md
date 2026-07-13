# Container Image — GitHub Container Registry (GHCR)

## 공식 액션
- 로그인: `docker/login-action@v3` — `registry: ghcr.io`, `username: ${{ github.actor }}`, `password: ${{ secrets.GITHUB_TOKEN }}`.
- 빌드+푸시: `docker/build-push-action@v6` — `context: .`, `push: true`, `tags: <owner>/<repo>:<tag>` 등.

## 시크릿
**불필요.** 리포지토리 기본 `GITHUB_TOKEN`을 그대로 쓴다 — 단, 잡(job) 권한에 `packages: write`를 명시해야 한다:
```yaml
permissions:
  contents: read
  packages: write
```

## OIDC / trusted-publishing 대안
해당 없음 — GHCR은 GITHUB_TOKEN 자체가 이미 리포지토리 범위로 스코프된 단기 자격증명이라 별도 OIDC 교환이 필요 없다(가장 단순한 케이스).

## 주의사항 (gotchas)
- `GITHUB_TOKEN`은 **해당 리포지토리 범위**로만 동작 — 다른 리포/조직 소유 패키지로는 푸시 불가.
- 새 패키지의 첫 푸시 후 기본 가시성은 **private**일 수 있다 — public으로 노출하려면 GHCR 패키지 설정에서 직접 visibility를 바꾸거나, org 설정에서 "Inherit access from source repository"를 켜야 패키지가 리포에 자동 연결·상속된다.
- 이미지 이름은 소문자여야 한다(`ghcr.io/<owner>/<name>`) — 대문자가 섞인 리포명은 태그 오류를 낸다.

## 대응 템플릿
`github/deploy.ghcr.workflow.example.yml` — image+docker 조합은 `/flow-init --render-deploy`가 정적 렌더링한다.

## SSOT
| 항목 | URL |
|---|---|
| docker/login-action | https://github.com/docker/login-action |
| docker/build-push-action | https://github.com/docker/build-push-action |
| GitHub Docs — Working with the Container registry | https://docs.github.com/en/packages/working-with-a-github-packages-registry/working-with-the-container-registry |
