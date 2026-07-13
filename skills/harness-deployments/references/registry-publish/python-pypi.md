# Registry Publish — Python (PyPI)

## 공식 액션 / 빌드 명령
- 배포: `pypa/gh-action-pypi-publish@release/v1` — `dist/` 아래 sdist/wheel을 자동으로 찾아 업로드한다(기본 `packages-dir: dist`).
- 빌드: `uv build`(권장, uv 프로젝트) 또는 `python -m build`(표준 PyPA 빌드 프론트엔드) — 둘 다 `dist/*.whl` + `dist/*.tar.gz`를 만든다.

## 시크릿
| 방식 | 필요한 것 | 워크플로 설정 |
|---|---|---|
| **OIDC trusted publishing (권장)** | 없음 | `permissions: id-token: write` 만 추가. `password`/`username` 입력 불필요 — 액션이 OIDC 토큰을 PyPI 임시 API 토큰으로 자동 교환한다. |
| Long-lived token | `PYPI_API_TOKEN` | `with: password: ${{ secrets.PYPI_API_TOKEN }}` (username은 기본값 `__token__`) |

## 주의사항 (gotchas)
- **trusted publisher를 PyPI 프로젝트 설정에 먼저 등록해야 OIDC가 동작한다.** PyPI 프로젝트 페이지 → *Publishing* 탭 → *Add a new publisher* → GitHub 선택 → `owner/repo`, workflow 파일명(예: `deploy-pypi.yml`, 경로 없이 파일명만), 선택적으로 environment name을 입력.
- 아직 PyPI에 한 번도 배포한 적 없는 신규 프로젝트는 "pending publisher"로 사전 등록 가능 — 첫 배포가 그 등록을 활성 publisher로 전환시킨다.
- OIDC와 토큰 방식은 상호 배타적이지 않지만, 시크릿이 설정돼 있으면 액션이 토큰 경로를 우선하므로 OIDC로 전환하려면 `PYPI_API_TOKEN`을 제거해야 한다.
- `id-token: write` 권한은 잡(job) 단위로 선언해야 하며, 이 권한이 없으면 OIDC 토큰 발급이 조용히 실패한다.

## 대응 템플릿
`github/deploy.pypi.workflow.example.yml` — 이미 OIDC(`id-token: write`) 기본 + `PYPI_API_TOKEN`이 설정된 경우로 전환 가능하게 구성돼 있다. registry+python 조합은 `/flow-init --render-deploy`가 정적 렌더링하므로, 이 스택은 별도 저작이 필요 없다.

## SSOT
| 항목 | URL |
|---|---|
| gh-action-pypi-publish | https://github.com/pypa/gh-action-pypi-publish |
| PyPI trusted publishers 가이드 | https://docs.pypi.org/trusted-publishers/ |
