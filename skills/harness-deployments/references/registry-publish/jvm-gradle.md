# Registry Publish — Java/Kotlin (Maven Central via Gradle)

`target: maven-central` + `build_tool: gradle` (detected from build.gradle/build.gradle.kts).
The same target as maven (Maven Central), but the plugin, command, and signing key format differ per build tool, so it is
split into a separate template (`github/deploy.gradle.workflow.example.yml`).

## Official plugin / build command
- Plugin: `com.vanniktech.maven.publish` (configured in `build.gradle(.kts)`) — handles Central Portal upload, signing, and POM
  metadata in a single plugin (simpler than combining `maven-publish` + `signing` + upload separately).
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
- Publish command (pick one — there is no safe default; because of the §6.4 auto-publish trap,
  `flow-config.deploy.targets[].publish` is required):
  | Command | Behavior |
  |---|---|
  | `./gradlew publishAndReleaseToMavenCentral` | Upload + **automatic release** (irreversible) |
  | `./gradlew publishToMavenCentral` | Upload only (release is a manual click in the Central Portal) |
- **`--no-configuration-cache` is a required Gradle-only flag** — the vanniktech plugin does not support the
  configuration cache on the Maven Central **release** (publish) path (Gradle issue #22779). The corresponding
  Maven command (`mvn deploy`) has no such concept at all (do not add the flag). Final command example:
  `./gradlew publishAndReleaseToMavenCentral --no-configuration-cache`.
- CI setup: `gradle/actions/setup-gradle@v4` (caching included — no separate `actions/cache` needed).

## Secrets
| Secret | Format | Workflow config (`ORG_GRADLE_PROJECT_*` env) |
|---|---|---|
| `MAVEN_CENTRAL_USERNAME` / `MAVEN_CENTRAL_PASSWORD` | Central Portal user token (not login credentials) | `ORG_GRADLE_PROJECT_mavenCentralUsername` / `ORG_GRADLE_PROJECT_mavenCentralPassword` |
| `MAVEN_GPG_PRIVATE_KEY` | **ASCII-armored** (`gpg --armor --export-secret-keys`) — **shares the same secret as the maven template** | `ORG_GRADLE_PROJECT_signingInMemoryKey` |
| `MAVEN_GPG_PASSPHRASE` | The passphrase set when the GPG key was created | `ORG_GRADLE_PROJECT_signingInMemoryKeyPassword` |

vanniktech's in-memory signing (`signingInMemoryKey`) is a path designed to be usable straight from CI without
`gpg-agent` or a local keyring — it leaves no key file in the workspace.

## OIDC / trusted-publishing
**None** — Maven Central does not support GitHub OIDC trusted publishing regardless of build tool (the Portal
user token is the only authentication path). Unlike PyPI/npm/crates.io, there is no alternative.

## Gotchas
- `MAVEN_GPG_PRIVATE_KEY` can be **shared as-is with the maven template** — both require ASCII-armored, so
  there is no need to re-encode the key. Conversely, sbt (`PGP_SECRET`) requires **base64**, so even the same key
  must be re-encoded and registered as a separate secret (see `references/registry-publish/jvm-sbt.md`).
- If `--no-configuration-cache` is omitted, release publishing on a project with the configuration cache enabled can
  fail silently or upload a wrong cached state.
- The groupId namespace must be registered and verified with the Central Portal before the first publish is possible (same premise as maven).
- `publishAndReleaseToMavenCentral` is **irreversible** — to avoid accidentally publishing a wrong artifact
  permanently, starting with `publishToMavenCentral` (manual release) is recommended.

## Corresponding template
`github/deploy.gradle.workflow.example.yml` — the `target: maven-central` + `build_tool: gradle` combination is
statically rendered by `/flow-init --render-deploy` (the `publish` command and JDK version are substituted from config).

## SSOT
| Item | URL |
|---|---|
| vanniktech gradle-maven-publish-plugin (Central) | https://vanniktech.github.io/gradle-maven-publish-plugin/central/ |
| Central Portal API guide | https://central.sonatype.org/publish/publish-portal-api/ |
| gradle/actions/setup-gradle | https://github.com/gradle/actions |
