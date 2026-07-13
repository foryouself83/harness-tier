# Registry Publish — Java/Kotlin (Maven Central via Gradle)

`target: maven-central` + `build_tool: gradle`(build.gradle/build.gradle.kts 감지).
maven과 같은 타깃(Maven Central)이지만 빌드 도구별로 플러그인·명령·서명 키 형식이 달라 별도 템플릿으로
분리돼 있다(`github/deploy.gradle.workflow.example.yml`).

## 공식 플러그인 / 빌드 명령
- 플러그인: `com.vanniktech.maven.publish`(`build.gradle(.kts)`에 설정) — Central Portal 업로드·서명·POM
  메타데이터를 한 플러그인으로 처리한다(별도 `maven-publish`+`signing`+업로드 조합보다 단순).
  ```kotlin
  // build.gradle.kts
  plugins {
      id("com.vanniktech.maven.publish") version "<latest>"
  }
  mavenPublishing {
      publishToMavenCentral()
      signAllPublications()
      coordinates("<groupId>", "<artifactId>", version.toString())
  }
  ```
- 발행 명령(택1, 안전한 기본값 없음 — §6.4 auto-publish 함정으로 `flow-config.deploy.targets[].publish`는
  필수):
  | 명령 | 동작 |
  |---|---|
  | `./gradlew publishAndReleaseToMavenCentral` | 업로드 + **자동 공개**(되돌릴 수 없음) |
  | `./gradlew publishToMavenCentral` | 업로드만(공개는 Central Portal에서 수동 클릭) |
- **`--no-configuration-cache`는 Gradle 전용 필수 플래그**다 — vanniktech 플러그인은 Maven Central
  **release**(공개) 발행 경로에서 configuration cache를 지원하지 않는다(Gradle 이슈 #22779). 대응하는
  Maven 명령(`mvn deploy`)에는 이 개념 자체가 없다(플래그를 붙이지 않는다). 최종 명령 예:
  `./gradlew publishAndReleaseToMavenCentral --no-configuration-cache`.
- CI 셋업: `gradle/actions/setup-gradle@v4`(캐싱 포함 — 별도 `actions/cache` 불필요).

## 시크릿
| 시크릿 | 형식 | 워크플로 설정(`ORG_GRADLE_PROJECT_*` env) |
|---|---|---|
| `MAVEN_CENTRAL_USERNAME` / `MAVEN_CENTRAL_PASSWORD` | Central Portal user token(로그인 자격증명 아님) | `ORG_GRADLE_PROJECT_mavenCentralUsername` / `ORG_GRADLE_PROJECT_mavenCentralPassword` |
| `MAVEN_GPG_PRIVATE_KEY` | **ASCII-armored**(`gpg --armor --export-secret-keys`) — **maven 템플릿과 동일 시크릿 공유** | `ORG_GRADLE_PROJECT_signingInMemoryKey` |
| `MAVEN_GPG_PASSPHRASE` | GPG 키 생성 시 설정한 passphrase | `ORG_GRADLE_PROJECT_signingInMemoryKeyPassword` |

vanniktech의 in-memory 서명(`signingInMemoryKey`)은 `gpg-agent`나 로컬 keyring 없이 CI에서 바로 쓸 수
있도록 설계된 경로다 — 키 파일을 워크스페이스에 남기지 않는다.

## OIDC / trusted-publishing
**없다** — Maven Central은 빌드 도구 무관하게 GitHub OIDC trusted publishing을 지원하지 않는다(Portal
user token이 유일한 인증 경로). PyPI/npm/crates.io와 달리 대안이 없다.

## 주의사항 (gotchas)
- `MAVEN_GPG_PRIVATE_KEY`를 **maven 템플릿과 그대로 공유**할 수 있다 — 둘 다 ASCII-armored를 요구하므로
  키를 다시 인코딩할 필요가 없다. 반대로 sbt(`PGP_SECRET`)는 **base64**를 요구하므로 같은 키라도 별도
  시크릿으로 다시 인코딩해 등록해야 한다(`references/registry-publish/jvm-sbt.md` 참고).
- `--no-configuration-cache`를 빠뜨리면 configuration cache가 켜진 프로젝트에서 release 발행이 조용히
  실패하거나 캐시된 잘못된 상태로 업로드될 수 있다.
- groupId 네임스페이스를 Central Portal에 먼저 등록·검증해야 첫 배포가 가능하다(maven과 동일 전제).
- `publishAndReleaseToMavenCentral`은 **되돌릴 수 없다** — 잘못된 아티팩트를 실수로 영구 공개하지
  않으려면 처음엔 `publishToMavenCentral`(수동 공개)로 시작하는 것을 권장.

## 대응 템플릿
`github/deploy.gradle.workflow.example.yml` — `target: maven-central`+`build_tool: gradle` 조합은
`/flow-init --render-deploy`가 정적 렌더링한다(`publish` 명령·JDK 버전은 config에서 치환).

## SSOT
| 항목 | URL |
|---|---|
| vanniktech gradle-maven-publish-plugin (Central) | https://vanniktech.github.io/gradle-maven-publish-plugin/central/ |
| Central Portal API 가이드 | https://central.sonatype.org/publish/publish-portal-api/ |
| gradle/actions/setup-gradle | https://github.com/gradle/actions |
