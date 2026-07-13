# Registry Publish — Scala (Maven Central via sbt) — 저작 레시피

`target: maven-central` + `build_tool: sbt`(build.sbt 감지). maven/gradle과 달리 **정적 템플릿이 없다**
— `DEPLOY_TEMPLATE_BY_TARGET`에 sbt 항목이 없어 `/harness-deployments`가 이 레시피를 청사진으로
`.github/workflows/deploy-<name>.yml`을 직접 저작한다(§7.4 3계층 폴백의 b계층).

## 공식 플러그인 / 빌드 명령
- 플러그인: `sbt-ci-release`(sbt-typelevel 계열, `project/plugins.sbt`에 추가) — 서명·발행·태그 기반
  버전 산출까지 한 명령으로 처리한다. `mvn deploy`/vanniktech처럼 개별 스텝을 조합하지 않는다.
  ```scala
  // project/plugins.sbt
  addSbtPlugin("org.typelevel" % "sbt-typelevel-ci-release" % "<latest>")
  ```
- 발행 명령: `sbt ci-release` 한 줄. 내부적으로 `publishSigned` + Central 발행을 태그 유무로 자동
  판단한다(태그 커밋이면 release 좌표로, 아니면 snapshot으로) — maven/gradle처럼 auto vs manual 공개를
  명령으로 선택하지 않는다.

## 시크릿
| 시크릿 | 형식 | 비고 |
|---|---|---|
| `PGP_SECRET` | **base64**(`gpg --armor --export-secret-keys $ID \| base64 -w0`) | maven/gradle의 `MAVEN_GPG_PRIVATE_KEY`(ASCII-armored)와 **다른 인코딩** — 같은 GPG 키라도 재인코딩해서 별도 시크릿으로 등록해야 한다 |
| `PGP_PASSPHRASE` | GPG 키 passphrase | |
| `SONATYPE_USERNAME` / `SONATYPE_PASSWORD` | Central Portal user token | maven의 `MAVEN_CENTRAL_USERNAME/PASSWORD`와 같은 성격, 시크릿 이름만 다름(sbt-ci-release 관례) |

**sbt만 base64를 요구하는 이유**: `sbt-ci-release`(sbt-typelevel)는 `PGP_SECRET`을 셸에서
`echo "$PGP_SECRET" | base64 -d | gpg --import`로 복원하는 방식을 쓴다 — ASCII-armored 텍스트를 그대로
넘기면 개행/특수문자가 워크플로 YAML·env 전달 과정에서 깨질 수 있어 base64로 감싸 안전하게 전달한다.
maven/gradle(setup-java `gpg-private-key`, vanniktech `signingInMemoryKey`)은 액션/플러그인이 자체적으로
ASCII-armored 텍스트를 직접 받아 처리하므로 이 재인코딩이 필요 없다.

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

jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: 15           # flow-config.deploy.timeout_minutes 로 치환
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.tag }}
          fetch-depth: 0
      - uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: "<version>"   # flow-config 의 version, 생략 시 템플릿 기본
      - name: Publish (sbt-ci-release)
        run: sbt ci-release
        env:
          PGP_SECRET: ${{ secrets.PGP_SECRET }}
          PGP_PASSPHRASE: ${{ secrets.PGP_PASSPHRASE }}
          SONATYPE_USERNAME: ${{ secrets.SONATYPE_USERNAME }}
          SONATYPE_PASSWORD: ${{ secrets.SONATYPE_PASSWORD }}
```

## 주의사항 (gotchas)
- **저작 대상**(정적 템플릿 아님) — 스킬이 위 스켈레톤에 JDK 버전 등 config 값을 채워 직접 커밋한다.
  향후 수요가 늘면 `DEPLOY_TEMPLATE_BY_TARGET`에 정적 템플릿으로 승격할 수 있다(스펙 §11 열린 질문).
- `PGP_SECRET`을 maven/gradle의 ASCII-armored 키를 그대로 붙여넣으면 **조용히 실패**한다 — 반드시
  `base64 -w0`로 재인코딩한 값을 등록한다.
- OIDC/trusted-publishing 대안 없음(maven/gradle과 동일 — Maven Central 자체의 제약).

## SSOT
| 항목 | URL |
|---|---|
| sbt-typelevel — CI 시크릿 설정 | https://typelevel.org/sbt-typelevel/secrets.html |
| Central Portal API 가이드 | https://central.sonatype.org/publish/publish-portal-api/ |
