# Trigger & Secrets — 횡단 가이드

모든 deploy 타깃(registry-publish·container-image·app-deploy)에 공통으로 적용되는 배선/시크릿/인증
원칙. 개별 스택 레시피는 각 카테고리 폴더를 참고.

---

## 1. 배선 — release.yml이 deploy.yml을 같은 런에서 호출한다

`release.yml`은 `deploy.yml`(오케스트레이터)을 **같은 워크플로 런 안에서 `workflow_call`로 호출**한다.
새 이벤트·새 런을 만드는 크로스-워크플로우 트리거가 아니므로, **PAT(`RELEASE_TOKEN`)도 필요 없고
GITHUB_TOKEN 재귀 문제도 애초에 발생하지 않는다.** 컴포넌트(`deploy-<name>.yml`)는 `on: workflow_call`
(+ 수동 재실행용 `workflow_dispatch`)만 갖는다 — `workflow_run`도 `release: published`도 쓰지 않는다.
release job이 `outputs.tag`로 실제 태그를 넘기고, 릴리스가 스킵되면(`tag == ''`) deploy 호출 job의
`if:`가 배포 자체를 막는다. 배선(관리 블록 삽입)은 스크립트가 담당하며, `/harness-deployments`는 이
트리거를 사용자에게 묻지 않는다(선택지가 없다 — 항상 이 방식).

## 2. (배경) GITHUB_TOKEN 재귀 방지 — 왜 크로스-워크플로우 트리거를 피하나

GitHub Actions는 **기본 `GITHUB_TOKEN`으로 발생시킨 이벤트가 새 워크플로 실행을 트리거하지 않도록**
설계돼 있다(무한 루프 방지). 예: 릴리스 워크플로가 `GITHUB_TOKEN`으로 태그·릴리스를 만들어도, 그
이벤트로 `workflow_run`/`release: published`를 리스닝하는 다른 워크플로가 (조건 없이는) 실행되지
않는다 — 이 문제를 피하려면 릴리스 생성 스텝 자체를 별도 PAT(`RELEASE_TOKEN`)로 실행해야 했다.

**이것이 바로 rev.3가 §1의 같은-런 `workflow_call`을 택한 이유다** — `workflow_call`은 호출자의
워크플로 런 안에서 곧바로 실행되는 재사용 워크플로 호출이라 애초에 별도 이벤트가 없고, 재귀 방지
규칙의 적용 대상 자체가 아니다. PAT도 크로스-워크플로우 조건도 필요 없다.

## 3. OIDC를 장수 토큰보다 우선한다

| 대상 | 장수 토큰(secrets) | OIDC/trusted-publishing 대안 |
|---|---|---|
| PyPI | `PYPI_API_TOKEN` | trusted publishing(`id-token: write`) — 있음 |
| npm | `NPM_TOKEN` | Trusted Publishing(2025-07-31 GA) — 있음 |
| Maven Central | `MAVEN_CENTRAL_USERNAME/PASSWORD` | 없음(Portal user token이 유일) |
| NuGet | `NUGET_API_KEY` | Trusted Publishing(`NuGet/login@v1`, 순차 롤아웃) — 있음 |
| crates.io | `CARGO_REGISTRY_TOKEN` | Trusted Publishing(`rust-lang/crates-io-auth-action@v1`) — 있음(단, 첫 배포는 토큰 필요) |
| GHCR | 없음(`GITHUB_TOKEN` 자체가 단기) | — (해당 없음, 이미 최선) |
| Docker Hub | `DOCKERHUB_USERNAME/TOKEN` | 없음 |
| SSH 서버 | `SSH_KEY` | 없음(SSH는 키 기반 — 배포 전용 키를 최소권한으로 발급하는 것이 사실상의 대응) |
| Kubernetes | `KUBE_CONFIG` | 없음(네임스페이스-스코프 ServiceAccount 토큰으로 범위를 최소화하는 것이 대응) |
| Cloud Run | Service Account Key JSON(비권장) | **WIF(Workload Identity Federation)** — 있음, 권장 |
| ECS | 없음(AWS 키 자체를 안 씀) | **IAM 역할 OIDC assume** — 있음, 권장 |

**원칙**: 표에서 OIDC/trusted-publishing 대안이 있는 대상은 그것을 기본값으로 제안한다(탈취 위험이 있는
장수 시크릿을 리포에 저장하지 않아도 되고, 수동 로테이션이 필요 없다). 대안이 없는 대상(Maven Central·
Docker Hub·SSH·Kubernetes)은 토큰/키가 유일한 경로이므로, 최소 권한 범위로 발급하고 로테이션 계획을
운영 가이드(`docs/operations/deploy-guide.md`)에 남기는 것으로 보완한다.

## 4. JVM 서명 키 — 형식이 빌드 도구별로 다르다 (§6.4 검증됨)

Maven Central 발행은 GPG 서명이 필수인데, **빌드 도구마다 요구하는 시크릿 인코딩이 다르다**:

| 빌드 도구 | 시크릿 | 형식 | 비고 |
|---|---|---|---|
| maven(`setup-java` `gpg-private-key`) | `MAVEN_GPG_PRIVATE_KEY` | **ASCII-armored** (`gpg --armor --export-secret-keys`) | gradle과 **동일 시크릿 공유** |
| gradle(vanniktech `signingInMemoryKey`) | `MAVEN_GPG_PRIVATE_KEY` | **ASCII-armored**(동일 명령) | maven과 **동일 시크릿 공유** |
| sbt(`sbt-ci-release` `PGP_SECRET`) | `PGP_SECRET` | **base64**(`gpg --armor --export-secret-keys $ID \| base64 -w0`) | maven/gradle과 **별도 시크릿**(형식 다름) |

maven·gradle은 같은 ASCII-armored 키를 그대로 재사용할 수 있어 시크릿을 하나만 등록하면 되지만, sbt는
같은 키를 base64로 다시 인코딩해 별도 시크릿에 등록해야 한다 — 형식을 혼동하면 서명이 조용히 실패한다.

**auto-publish 함정**: Sonatype Central Portal API의 `publishingType`(및 각 빌드 도구가 이를 감싼
`publish`/`publishAndReleaseToMavenCentral` 류 명령)은 생태계 전반에서 기본값이 **`USER_MANAGED`**
(업로드만, 공개는 포털에서 수동 클릭)이다. "업로드만" vs "즉시 영구 공개(되돌릴 수 없음)"는 안전한
범용 기본값이 없는 결정이라, `flow-config.deploy.targets[].publish` 명령은 **필수·무기본값**이고
사용자가 명시해야 한다(스킬 Q&A에서 강제 확인).

---

## Source

- https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow
- https://docs.github.com/en/actions/concepts/security/github_token
- https://vanniktech.github.io/gradle-maven-publish-plugin/central/
- https://central.sonatype.org/publish/publish-portal-api/
- https://github.com/actions/setup-java/blob/main/docs/advanced-usage.md
- https://typelevel.org/sbt-typelevel/secrets.html
