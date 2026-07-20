---
name: harness-deployments
description: Add a CI deployment layer on top of the release workflow — registry publish, container image, or app deploy. Requires /flow-init to have run first.
disable-model-invocation: true
---

# Harness-Deployments — Deployment Layer Setup

Run after `/flow-init`. Adds deployment (registry publish · image · app deploy) on top of the
release (tag + notes). CI performs the actual deployment; this skill only detects, asks, and
generates (it never deploys from the host).

**Orchestrator structure — wiring is always automatic**: `release.yml` calls `deploy.yml` (the
orchestrator, generated) **via `workflow_call` in the same run** — no cross-workflow trigger and no
PAT. `deploy.yml` resolves the real tag once and calls each target component `deploy-<name>.yml`
(`on: workflow_call`) with per-target permissions. The **script** (`flow_init_setup.py`
`--render-deploy` / `/flow-init`) fills this wiring idempotently into release.yml's managed block.
Trigger and wiring therefore belong to the script; §2 and §3 say what that leaves you.

## Path conventions
- Reads (templates/reference): `${CLAUDE_PLUGIN_ROOT}/...`
- Host writes: `${CLAUDE_PROJECT_DIR}/.github/workflows/`, `.../.claude/harness-tier/config/flow-config.yaml`, `.../docs/`
- **Never write into the plugin directory.**

## Execution

### 0. Guard (hard stop)
- If `${CLAUDE_PROJECT_DIR}/.claude/harness-tier/config/flow-config.yaml` is absent →
  tell the user to "run `/flow-init` first" and stop.

### 1. Detection
- Stack: flow-config's `versioning.release_tool` / `version_files` / `modules[].checks` language.
- Artifacts: does a `Dockerfile` exist? A package library (`pyproject.toml`/`package.json`/`Cargo.toml`/`pom.xml`/`*.csproj`)?
- `build_tool` (needed only for `target: maven-central`): `build.gradle`/`build.gradle.kts` → gradle,
  `pom.xml` → maven, `build.sbt` → sbt. This value decides whether the renderer uses the maven or the
  gradle template. §2 confirms it and §3 writes it.
- Existing deployment: publish/deploy steps already in `.github/workflows/*` (Grep).
- Secrets: where possible, check already-registered registry/signing secrets with `gh secret list` (for reference in the report step).

### 2. Q&A (AskUserQuestion, adaptive) — ask only what cannot be derived
- Present the detected candidates and let the user pick deployment targets ("Dockerfile found → GHCR? pyproject → PyPI?").
- Per-target `auth` (`oidc` | `token` — not detectable from the repo. Default to the per-target recommendation, mostly oidc).
- Deployment `order` (omitted → all parallel — ask only when ordering between targets is needed).
- `image`/`context`/`dockerfile` for monorepo image targets (do not ask for a single image — the renderer
  fills the derived defaults `ghcr.io/${{ github.repository }}` · `.` · `<context>/Dockerfile`).
- `permissions`/`with` for custom targets (not derivable — the orchestrator uses them verbatim).
- brownfield: when an existing deployment is found, choose adopt/augment/replace (never overwrite silently).
- **Confirm** the detected `build_tool` (do not re-ask). Advise that `version`/`build` may be omitted
  without forcing it (omitted → the renderer fills the stack default). The `publish` command for
  `maven-central`+`build_tool: gradle/sbt` is the sole exception — task names vary per project, so there
  is no safe universal default and the user must state it (`build_tool: maven` does not apply — the
  template's `mvn deploy` performs the pom's central-publishing-maven-plugin configuration as-is).
- **The trigger is already settled** — release.yml→deploy.yml is always a same-run
  reusable-workflow call that the script wires, so there is no trigger to offer a choice about.

### 3. Generation
- Write/update the `deploy:` block in `flow-config.yaml` (team-shared · git-tracked) — **config carries
  only non-derivable values**: write the human-decided `enable`/`name`/`target`/`order`/`auth`/custom
  `permissions`, omit what the renderer can fill (`image`/`context`/`dockerfile`/`build`/`version`), and
  write the skill-detected `build_tool`.
- **Component generation — 3-tier fallback** (in order of confidence):
  a. **Mapped target** (registry/image — `pypi`/`npm`/`nuget`/`cratesio`/`ghcr`/`dockerhub`, plus
     `maven-central`+`build_tool=maven|gradle`) → call `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/flow_init_setup.py"
     --render-deploy` to render the static template (**call the plugin SOURCE path directly** — `flow_init_setup.py`
     is not in `COPY_FILES` and so is never copied to the host; run it from `${CLAUDE_PLUGIN_ROOT}`, not the
     host copy under `${CLAUDE_PROJECT_DIR}/.claude/harness-tier/scripts/`).
  b. **custom/app-deploy that has references** (ssh·kubernetes·cloud-run·ecs) or **sbt**
     (`target: maven-central`+`build_tool=sbt`, no static template) → author
     `.github/workflows/deploy-<name>.yml` directly, using the matching recipe
     (`references/app-deploy/*.md`, `references/registry-publish/jvm-sbt.md`) as the blueprint.
  c. **A new target not in references either** → research the official action, required secrets, and OIDC
     support via `WebSearch`/`WebFetch`, then author to the contract + a "needs verification" flag + the
     required-secret list in the report.
  Whichever tier applies, the authored file honours this contract: `on: workflow_call` (`inputs.tag`
  required) + `workflow_dispatch` (`inputs.tag` required) + `ref: ${{ inputs.tag }}` checkout +
  `timeout-minutes` on the running job + its own `permissions:`. Declare it in config as `target: custom`
  + `workflow`/`permissions`/`with` so the orchestrator wraps it uniformly as a `uses:` job.
- The **orchestrator** (`deploy.yml`) is generated dynamically from targets by `--render-deploy` (it is not
  a static template) — no separate skill work needed.
- **The script owns release wiring**: `--render-deploy` (and a `/flow-init` re-run) fills release.yml's
  `# __HARNESS_DEPLOY_BEGIN/END__` managed block with the deploy-call job idempotently via
  `integrate_release_deploy` (union permissions auto-recomputed, re-synced on a flow-init re-run too).
  **The skill does not edit release.yml** — the sole exception is when the script prints a `[!]` refusal
  because the managed block is absent (legacy-ours or truly-foreign). In that case the skill:
  - **Path A (regenerate)**: guide regenerating release.yml from the latest template → the script wires it
    automatically (simple, but customisations need review).
  - **Path B (semantic patch — the only path where the skill edits release.yml)**: read the release job and
    insert `outputs.tag` + the `# __HARNESS_DEPLOY_BEGIN/END__` markers + the deploy-call job **after the
    point where the released signal is produced** (a per-tool semantic judgement the script cannot make, so
    the skill makes it) — apply **only after showing the diff and getting user confirmation** (preserves
    customisations).
  - Whichever path is taken, **in the meantime** the components and `deploy.yml` are already generated and
    can be run manually via `workflow_dispatch` (tag input) — deployment is not blocked, only the automatic
    wiring is deferred.
- Write/update `docs/operations/deploy-guide.md` — see the content below.

### 4. Report
- Summarise the created/changed files, the secrets the repo admin must set (including the JVM signing-key
  format caution in the deploy-guide section below), whether release.yml changed (wired automatically / or
  there was a `[!]` consultation because it was legacy·foreign), and any conflicts found.

## `docs/operations/deploy-guide.md` content
- The secrets to set (per target — see `references/registry-publish/*.md`·`references/container-image/*.md`).
  `maven-central` differs in format by `build_tool`: maven·gradle use the ASCII-armored
  `MAVEN_GPG_PRIVATE_KEY` (shared), sbt uses base64 `PGP_SECRET` (separate) — confusing them makes signing
  fail silently.
- That wiring is **always automatic** (release.yml → deploy.yml, same-run `workflow_call`, no PAT needed).
- Manual redeploy: run `.github/workflows/deploy.yml` directly via `workflow_dispatch` (tag required, target optional).
- Rollback pointers (see the rollback section of each target's `references/*.md`).

## Reuse before build
- Each stack prefers the official action (pypa/gh-action-pypi-publish, docker/build-push-action,
  com.vanniktech.maven.publish, etc. — see references).
- When recommending a paid service, state the cost/licence explicitly.
