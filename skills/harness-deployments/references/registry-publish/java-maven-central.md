# Registry Publish — Java (Maven Central)

## 공식 액션 / 빌드 명령
- 배포: 전용 GitHub Action은 없다 — `actions/setup-java@v5`(Temurin) 설치 후 Maven CLI로 `mvn -B -DskipTests deploy`를 실행한다. `deploy` 목표가 `org.sonatype.central:central-publishing-maven-plugin`(pom.xml에 설정) 경유로 Sonatype **Central Portal**에 업로드한다.
- **2025-06-30부로 레거시 OSSRH(oss.sonatype.org)가 완전히 종료**됐다 — 신규/기존 프로젝트 모두 Central Portal(central.sonatype.com) 경로로만 배포 가능. `nexus-staging-maven-plugin` 기반의 옛 가이드는 더 이상 유효하지 않다.

## 시크릿
| 방식 | 필요한 것 | 워크플로 설정 |
|---|---|---|
| Central Portal user token (유일한 경로) | `MAVEN_CENTRAL_USERNAME` / `MAVEN_CENTRAL_PASSWORD` | Central Portal에서 발급한 **User Token** 쌍(계정 로그인 비밀번호 아님) — `env`로 주입 |
| GPG 서명(별도 필수) | `MAVEN_GPG_PRIVATE_KEY` / `MAVEN_GPG_PASSPHRASE` | `maven-gpg-plugin`을 `deploy` 단계에 바인딩해 아티팩트에 서명 |

## 주의사항 (gotchas)
- **OIDC/trusted-publishing 대안이 없다** — PyPI·npm·NuGet·crates.io와 달리 Maven Central은 이 문서 작성 시점 기준 GitHub OIDC 기반 trusted publishing을 지원하지 않는다. Portal user token이 유일한 인증 경로.
- `central-publishing-maven-plugin`은 유효한 배포 번들(체크섬 + **GPG 서명 파일**)을 자동으로 만들어주지 않는다 — `maven-gpg-plugin`으로 서명 스텝을 pom.xml에 별도 구성해야 하며, 빠지면 Central 검증에서 거부된다.
- Central Portal User Token은 Sonatype 계정 → *View Account* → *Generate User Token*에서 발급하며, 로그인 자격증명과는 별개다.
- groupId 네임스페이스(도메인 소유권 또는 GitHub 계정 기반)를 Central Portal에 먼저 등록·검증해야 첫 배포가 가능하다.

## 대응 템플릿
`github/deploy.maven-central.workflow.example.yml` — registry+java(및 kotlin) 조합은 `/flow-init --render-deploy`가 정적 렌더링한다.

## SSOT
| 항목 | URL |
|---|---|
| OSSRH sunset 공지 | https://central.sonatype.org/pages/ossrh-eol/ |
| Central Portal Maven 플러그인 가이드 | https://central.sonatype.org/publish/publish-portal-maven/ |
