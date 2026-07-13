# Container Image — Docker Hub

## 공식 액션
- 로그인: `docker/login-action@v3` — `username: ${{ secrets.DOCKERHUB_USERNAME }}`, `password: ${{ secrets.DOCKERHUB_TOKEN }}` (registry 입력 생략 시 기본값이 Docker Hub).
- 빌드+푸시: `docker/build-push-action@v6` — GHCR과 동일한 사용법.

## 시크릿
| 시크릿 | 값 |
|---|---|
| `DOCKERHUB_USERNAME` | Docker Hub 계정/조직 사용자명 |
| `DOCKERHUB_TOKEN` | **Access Token**(계정 비밀번호 아님) — Docker Hub → Account Settings → Security → *New Access Token*, Read & Write 스코프로 발급 |

## OIDC / trusted-publishing 대안
**없음** — Docker Hub는 이 문서 작성 시점 기준 GitHub OIDC 기반 trusted publishing을 지원하지 않는다. Access Token이 유일한 인증 경로이므로, 최소 권한(해당 리포만 Read & Write) 토큰을 발급하고 주기적으로 로테이션할 것.

## 주의사항 (gotchas)
- 반드시 **Access Token**을 발급해서 써야 한다 — 계정 로그인 비밀번호를 시크릿에 넣지 말 것(2FA 계정은 애초에 비밀번호 로그인이 API에서 막혀 있다).
- 토큰 스코프를 "Read & Write"로 지정해야 push가 성공한다(기본 "Read-only"로는 실패).
- 무료 플랜은 익명 pull rate limit이 있다 — CI에서 base 이미지를 자주 pull한다면 로그인된 상태(`docker/login-action`)로 pull해 리밋을 완화할 수 있다.

## 대응 템플릿
`github/deploy.dockerhub.workflow.example.yml` — image+docker-hub 조합은 `/flow-init --render-deploy`가 정적 렌더링한다.

## SSOT
| 항목 | URL |
|---|---|
| docker/login-action | https://github.com/docker/login-action |
| docker/build-push-action | https://github.com/docker/build-push-action |
| Docker Hub Access Tokens 문서 | https://docs.docker.com/security/for-developers/access-tokens/ |
