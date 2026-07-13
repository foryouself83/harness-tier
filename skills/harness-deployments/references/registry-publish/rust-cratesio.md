# Registry Publish — Rust (crates.io)

## 공식 액션 / 빌드 명령
- 배포: 전용 배포 액션은 `dtolnay/rust-toolchain@stable`로 toolchain을 세팅한 뒤 `cargo publish --token <token>`을 실행한다.
- 빌드: `cargo build --release` (publish 자체가 패키징을 포함하므로 별도 빌드는 검증용).

## 시크릿
| 방식 | 필요한 것 | 워크플로 설정 |
|---|---|---|
| Long-lived token(현재 기본 템플릿) | `CARGO_REGISTRY_TOKEN` | `cargo publish --token "${{ secrets.CARGO_REGISTRY_TOKEN }}"` |
| **crates.io Trusted Publishing (OIDC)** | 없음 | `permissions: id-token: write` + `rust-lang/crates-io-auth-action@v1`으로 임시 토큰 발급 |

## 주의사항 (gotchas)
- Trusted Publishing 워크플로 형태:
  ```yaml
  permissions:
    id-token: write
  steps:
    - name: Authenticate with crates.io
      id: auth
      uses: rust-lang/crates-io-auth-action@v1
    - name: Publish to crates.io
      run: cargo publish --token ${{ steps.auth.outputs.token }}
  ```
  발급된 토큰은 잡 종료 시 액션의 post-step이 자동 폐기(revoke)한다.
- **첫 배포는 OIDC로 할 수 없다** — crate가 crates.io에 최소 한 번 수동/토큰 배포로 존재해야, crate 설정 화면에서 GitHub 리포를 Trusted Publishing 대상으로 연결할 수 있다. 부트스트랩은 `CARGO_REGISTRY_TOKEN`으로 하고, 이후 릴리스부터 OIDC로 전환.
- 등록 시 owner/repo, workflow 파일명을 crates.io UI에서 지정해야 하며, GitHub Actions 외 다른 CI 제공자 지원은 아직 제한적(GitLab/CircleCI는 로드맵).

## 대응 템플릿
`github/deploy.cratesio.workflow.example.yml` — registry+rust 조합은 `/flow-init --render-deploy`가 정적 렌더링한다.

## SSOT
| 항목 | URL |
|---|---|
| crates.io Trusted Publishing 문서 | https://crates.io/docs/trusted-publishing |
| rust-lang/crates-io-auth-action | https://github.com/rust-lang/crates-io-auth-action |
| RFC 3691 (Trusted Publishing for crates.io) | https://rust-lang.github.io/rfcs/3691-trusted-publishing-cratesio.html |
