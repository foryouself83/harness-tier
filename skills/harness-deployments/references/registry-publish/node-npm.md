# Registry Publish — Node (npm)

## 공식 액션 / 빌드 명령
- 배포: 전용 GitHub Action은 없다 — `actions/setup-node@v6`로 Node/registry-url을 세팅한 뒤 npm CLI로 직접 `npm publish --provenance --access public`을 실행한다.
- 빌드: 프로젝트의 빌드 스크립트(`npm ci && npm run build`) — 순수 JS 라이브러리는 빌드 단계가 없을 수도 있다.

## 시크릿
| 방식 | 필요한 것 | 워크플로 설정 |
|---|---|---|
| Long-lived token (현재 기본 템플릿) | `NPM_TOKEN` (Automation 타입 토큰) | `env: NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}`, `registry-url: https://registry.npmjs.org` |
| **npm Trusted Publishing (OIDC, 2025-07-31 GA)** | 없음 | `permissions: id-token: write`. npm CLI ≥ 11.5.1, Node ≥ 22.14.0 필요. `npm publish`만 실행하면(별도 `--provenance` 불필요 — OIDC 경로에서는 자동 첨부) 토큰 없이 발행된다. |

## 주의사항 (gotchas)
- Trusted Publishing을 쓰려면 npmjs.com 패키지 설정 → **Trusted Publisher** 섹션에서 GitHub Actions를 선택하고 org/user, repo, workflow 파일명, (선택) environment를 등록해야 한다 — PyPI/crates.io와 동일한 사전 등록 패턴.
- `--provenance`는 Sigstore 기반 서명이 필요해 **GitHub 호스팅 러너**에서만 동작한다(퍼블릭 OIDC 발급자 검증 불가로 self-hosted 러너는 불가).
- scoped 패키지(`@org/name`)는 `--access public`을 명시하지 않으면 기본적으로 private로 발행되어 실패한다(무료 플랜 기준).
- 현재 harness-tier 정적 템플릿(`deploy.npm.workflow.example.yml`)은 `NPM_TOKEN` + `--provenance` 조합을 기본값으로 쓴다 — Trusted Publishing으로 전환하려면 템플릿의 `NODE_AUTH_TOKEN` 스텝을 제거하고 위 권한만 남기면 된다.

## 대응 템플릿
`github/deploy.npm.workflow.example.yml` — registry+node 조합은 `/flow-init --render-deploy`가 정적 렌더링한다.

## SSOT
| 항목 | URL |
|---|---|
| npm trusted publishers 문서 | https://docs.npmjs.com/trusted-publishers/ |
| GitHub Changelog — npm trusted publishing GA | https://github.blog/changelog/2025-07-31-npm-trusted-publishing-with-oidc-is-generally-available/ |
