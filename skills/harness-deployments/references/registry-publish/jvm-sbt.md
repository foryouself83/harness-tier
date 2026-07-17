# Registry Publish — Scala (Maven Central via sbt) — authoring recipe

`target: maven-central` + `build_tool: sbt` (detected from build.sbt). Unlike maven/gradle, there is **no static template**
— since `DEPLOY_TEMPLATE_BY_TARGET` has no sbt entry, `/harness-deployments` authors
`.github/workflows/deploy-<name>.yml` directly, using this recipe as the blueprint (tier b of the §7.4 3-tier fallback).

## Official plugin / build command
- Plugin: `sbt-ci-release` (sbt-typelevel family, added to `project/plugins.sbt`) — handles signing, publishing, and
  tag-based version derivation in a single command. It does not compose individual steps like `mvn deploy`/vanniktech.
  ```scala
  // project/plugins.sbt
  addSbtPlugin("org.typelevel" % "sbt-typelevel-ci-release" % "<latest>")
  ```
- Publish command: a single line, `sbt ci-release`. Internally it runs `publishSigned` + Central publishing, deciding
  automatically by the presence of a tag (release coordinates on a tag commit, snapshot otherwise) — unlike
  maven/gradle, auto vs. manual release is not selected by command.

## Secrets
| Secret | Format | Notes |
|---|---|---|
| `PGP_SECRET` | **base64** (`gpg --armor --export-secret-keys $ID \| base64 -w0`) | A **different encoding** from maven/gradle's `MAVEN_GPG_PRIVATE_KEY` (ASCII-armored) — even the same GPG key must be re-encoded and registered as a separate secret |
| `PGP_PASSPHRASE` | GPG key passphrase | |
| `SONATYPE_USERNAME` / `SONATYPE_PASSWORD` | Central Portal user token | Same nature as maven's `MAVEN_CENTRAL_USERNAME/PASSWORD`, only the secret names differ (sbt-ci-release convention) |

**Why only sbt requires base64**: `sbt-ci-release` (sbt-typelevel) restores `PGP_SECRET` in the shell with
`echo "$PGP_SECRET" | base64 -d | gpg --import` — passing ASCII-armored text as-is can break newlines/special
characters while being handed through workflow YAML/env, so it is wrapped in base64 for safe transport.
maven/gradle (setup-java `gpg-private-key`, vanniktech `signingInMemoryKey`) do not need this re-encoding, because the
action/plugin itself takes and handles ASCII-armored text directly.

## Workflow skeleton

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
        description: "Tag to deploy (e.g. v1.2.3)"
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
    timeout-minutes: 15           # substituted from flow-config.deploy.timeout_minutes
    steps:
      - uses: actions/checkout@v7
        with:
          ref: ${{ inputs.tag }}
          fetch-depth: 0
      - uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: "<version>"   # version from flow-config; template default when omitted
      - name: Publish (sbt-ci-release)
        run: sbt ci-release
        env:
          PGP_SECRET: ${{ secrets.PGP_SECRET }}
          PGP_PASSPHRASE: ${{ secrets.PGP_PASSPHRASE }}
          SONATYPE_USERNAME: ${{ secrets.SONATYPE_USERNAME }}
          SONATYPE_PASSWORD: ${{ secrets.SONATYPE_PASSWORD }}
```

## Gotchas
- **An authoring target** (not a static template) — the skill fills config values such as the JDK version into the
  skeleton above and commits it directly. If demand grows later, it can be promoted to a static template in
  `DEPLOY_TEMPLATE_BY_TARGET` (spec §11 open question).
- Pasting maven/gradle's ASCII-armored key as-is into `PGP_SECRET` **fails silently** — always register the value
  re-encoded with `base64 -w0`.
- No OIDC/trusted-publishing alternative (same as maven/gradle — a constraint of Maven Central itself).

## SSOT
| Item | URL |
|---|---|
| sbt-typelevel — CI secrets setup | https://typelevel.org/sbt-typelevel/secrets.html |
| Central Portal API guide | https://central.sonatype.org/publish/publish-portal-api/ |
