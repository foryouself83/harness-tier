# Trigger & Secrets — cross-cutting guide

The wiring/secret/authentication principles that apply commonly to every deploy target
(registry-publish·container-image·app-deploy). For individual stack recipes, see each category folder.

---

## 1. Wiring — release.yml calls deploy.yml in the same run

`release.yml` **calls** `deploy.yml` (the orchestrator) **via `workflow_call` inside the same workflow run**.
It is not a cross-workflow trigger that creates a new event/new run, so **no PAT (`RELEASE_TOKEN`) is needed and
the GITHUB_TOKEN recursion problem does not arise in the first place.** The components (`deploy-<name>.yml`) have
only `on: workflow_call` (+ `workflow_dispatch` for manual re-runs) — they use neither `workflow_run` nor
`release: published`. The release job passes the actual tag via `outputs.tag`, and if the release is skipped
(`tag == ''`), the `if:` on the deploy-calling job blocks the deployment itself. The wiring (managed-block
insertion) is handled by a script, and `/harness-deployments` does not ask the user about this trigger
(there is no choice — always this way).

## 2. (Background) GITHUB_TOKEN recursion prevention — why cross-workflow triggers are avoided

GitHub Actions is designed **so that an event raised with the default `GITHUB_TOKEN` does not trigger a new
workflow run** (infinite-loop prevention). Example: even if a release workflow creates a tag/release with
`GITHUB_TOKEN`, another workflow listening for `workflow_run`/`release: published` on that event does not run
(absent a condition) — to avoid this problem, the release-creation step itself had to be run with a separate
PAT (`RELEASE_TOKEN`).

**This is exactly why rev.3 chose the same-run `workflow_call` of §1** — `workflow_call` is a reusable-workflow
invocation that runs directly inside the caller's workflow run, so there is no separate event in the first place,
and it is not subject to the recursion-prevention rule at all. Neither a PAT nor a cross-workflow condition is needed.

## 3. Prefer OIDC over long-lived tokens

| Target | Long-lived token (secrets) | OIDC/trusted-publishing alternative |
|---|---|---|
| PyPI | `PYPI_API_TOKEN` | trusted publishing(`id-token: write`) — available |
| npm | `NPM_TOKEN` | Trusted Publishing(2025-07-31 GA) — available |
| Maven Central | `MAVEN_CENTRAL_USERNAME/PASSWORD` | None (a Portal user token is the only path) |
| NuGet | `NUGET_API_KEY` | Trusted Publishing(`NuGet/login@v1`, phased rollout) — available |
| crates.io | `CARGO_REGISTRY_TOKEN` | Trusted Publishing(`rust-lang/crates-io-auth-action@v1`) — available (but the first publish requires a token) |
| GHCR | None (`GITHUB_TOKEN` is itself short-lived) | — (not applicable, already optimal) |
| Docker Hub | `DOCKERHUB_USERNAME/TOKEN` | None |
| SSH server | `SSH_KEY` | None (SSH is key-based — issuing a deploy-only key with least privilege is the de facto counterpart) |
| Kubernetes | `KUBE_CONFIG` | None (the counterpart is minimizing the scope with a namespace-scoped ServiceAccount token) |
| Cloud Run | Service Account Key JSON (not recommended) | **WIF (Workload Identity Federation)** — available, recommended |
| ECS | None (no AWS key is used at all) | **IAM role OIDC assume** — available, recommended |

**Principle**: for targets that have an OIDC/trusted-publishing alternative in the table, propose it as the default
(no long-lived secret carrying a theft risk has to be stored in the repo, and no manual rotation is needed). For
targets without an alternative (Maven Central·Docker Hub·SSH·Kubernetes), a token/key is the only path, so compensate
by issuing it with a least-privilege scope and leaving a rotation plan in the operations guide
(`docs/operations/deploy-guide.md`).

## 4. JVM signing keys — the format differs per build tool (verified in §6.4)

Maven Central publication requires a GPG signature, but **the secret encoding each build tool requires differs**:

| Build tool | Secret | Format | Notes |
|---|---|---|---|
| maven(`setup-java` `gpg-private-key`) | `MAVEN_GPG_PRIVATE_KEY` | **ASCII-armored** (`gpg --armor --export-secret-keys`) | **shares the same secret** with gradle |
| gradle(vanniktech `signingInMemoryKey`) | `MAVEN_GPG_PRIVATE_KEY` | **ASCII-armored**(same command) | **shares the same secret** with maven |
| sbt(`sbt-ci-release` `PGP_SECRET`) | `PGP_SECRET` | **base64**(`gpg --armor --export-secret-keys $ID \| base64 -w0`) | **separate secret** from maven/gradle (different format) |

maven·gradle can reuse the same ASCII-armored key as-is, so only one secret needs to be registered, but sbt requires
re-encoding the same key as base64 and registering it as a separate secret — confusing the formats makes signing fail silently.

**auto-publish trap**: the `publishingType` of the Sonatype Central Portal API (and the
`publish`/`publishAndReleaseToMavenCentral`-style commands each build tool wraps it in) defaults across the
ecosystem to **`USER_MANAGED`** (upload only; publishing is a manual click in the portal). "Upload only" vs.
"immediate permanent publication (irreversible)" is a decision with no safe universal default, so the
`flow-config.deploy.targets[].publish` command is **required with no default** and must be specified by the
user (force-confirmed in the skill Q&A).

---

## Source

- https://docs.github.com/en/actions/how-tos/write-workflows/choose-when-workflows-run/trigger-a-workflow
- https://docs.github.com/en/actions/concepts/security/github_token
- https://vanniktech.github.io/gradle-maven-publish-plugin/central/
- https://central.sonatype.org/publish/publish-portal-api/
- https://github.com/actions/setup-java/blob/main/docs/advanced-usage.md
- https://typelevel.org/sbt-typelevel/secrets.html
