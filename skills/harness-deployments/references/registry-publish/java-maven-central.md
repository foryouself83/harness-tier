# Registry Publish — Java (Maven Central)

## Official action / build command
- Publish: there is no dedicated GitHub Action — install `actions/setup-java@v5` (Temurin), then run `mvn -B -DskipTests deploy` via the Maven CLI. The `deploy` goal uploads to the Sonatype **Central Portal** via `org.sonatype.central:central-publishing-maven-plugin` (configured in pom.xml).
- **As of 2025-06-30 the legacy OSSRH (oss.sonatype.org) is fully shut down** — both new and existing projects can only publish through the Central Portal (central.sonatype.com) path. Old guides based on `nexus-staging-maven-plugin` are no longer valid.

## Secrets
| Method | What's needed | Workflow config |
|---|---|---|
| Central Portal user token (the only path) | `MAVEN_CENTRAL_USERNAME` / `MAVEN_CENTRAL_PASSWORD` | The **User Token** pair issued by the Central Portal (not the account login password) — injected via `env` |
| GPG signing (separately required) | `MAVEN_GPG_PRIVATE_KEY` / `MAVEN_GPG_PASSPHRASE` | Bind `maven-gpg-plugin` to the `deploy` phase to sign the artifacts |

## Gotchas
- **There is no OIDC/trusted-publishing alternative** — unlike PyPI, npm, NuGet, and crates.io, Maven Central does not support GitHub OIDC-based trusted publishing as of this writing. The Portal user token is the only authentication path.
- `central-publishing-maven-plugin` does not automatically build a valid deployment bundle (checksums + **GPG signature files**) — the signing step must be configured separately in pom.xml with `maven-gpg-plugin`, and if it is missing, Central validation rejects it.
- The Central Portal User Token is issued from the Sonatype account → *View Account* → *Generate User Token*, and is separate from the login credentials.
- The groupId namespace (based on domain ownership or a GitHub account) must be registered and verified with the Central Portal before the first publish is possible.

## Corresponding template
`github/deploy.maven-central.workflow.example.yml` — the registry+java (and kotlin) combination is statically rendered by `/flow-init --render-deploy`.

## SSOT
| Item | URL |
|---|---|
| OSSRH sunset notice | https://central.sonatype.org/pages/ossrh-eol/ |
| Central Portal Maven plugin guide | https://central.sonatype.org/publish/publish-portal-maven/ |
