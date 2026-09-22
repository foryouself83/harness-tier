# Deployments

**English** · [한국어](deployments.ko.md) · [Usage guide](../../USAGE.md)

`/harness-deployments` layers publishing on top of the release workflow: `release.yml` mints
the tag, `deploy.yml` consumes it in the **same run** via `workflow_call` — no cross-workflow
trigger, no PAT — and fans out to per-target components with least-privilege permissions.

```text
/harness-deployments   # no arguments — interactive
```

It requires `/flow-init` to have run (it needs `flow-config.yaml`) and stops with guidance
otherwise. Order: `/harness-init` → `/flow-init` → `/harness-deployments`.

## What it does

1. **Detects** — the stack from `versioning.release_tool` / `version_files` / `modules[].checks`,
   build artifacts (`Dockerfile`, `pyproject.toml` / `package.json` / `Cargo.toml` / `pom.xml` /
   `*.csproj`), the JVM `build_tool` (`build.gradle[.kts]` → gradle, `pom.xml` → maven,
   `build.sbt` → sbt), any deploy steps already in `.github/workflows/*`, and, where possible,
   already-registered secrets via `gh secret list`.
2. **Asks** only what it cannot derive — deploy targets from the detected candidates, per-target
   `auth` (OIDC vs. token), deploy `order` across targets, a monorepo image's
   `image`/`context`/`dockerfile` (skipped for a single image, which gets a derived default), and
   a custom target's `permissions`/`with`. `build_tool` is only confirmed. `version`/`build` are
   optional — the renderer fills a stack default — except the `publish` command for
   `maven-central` with `build_tool: gradle` or `sbt`: task names vary per project, so you must
   state it. A brownfield deploy step gets an adopt/augment/replace choice, never a silent
   overwrite. There is no trigger question — the wiring is always the same.
3. **Generates**:
   - the `deploy:` block in `flow-config.yaml`, holding only what it could not derive;
   - a mapped registry/image target (or `maven-central` with `build_tool: maven`/`gradle`) via
     the plugin's static template;
   - a custom or app-deploy target with a matching reference recipe (ssh, kubernetes, cloud-run,
     ecs) or `maven-central`+`build_tool: sbt`, authored directly from that recipe;
   - an unmatched target, researched and authored with a "verify needed" flag and its required
     secrets;
   - `deploy.yml`, the orchestrator, generated from the targets;
   - the managed block in `release.yml` that calls the orchestrator — regenerated on legacy or
     foreign files only after you confirm a diff;
   - `docs/operations/deploy-guide.md` — secrets to configure, including the JVM signing-key
     format per build tool, manual re-deploy, and rollback pointers.
4. **Reports** the files created or changed, the secrets the repository admin must set, and any
   conflicts found.

## Wiring

`release.yml` exposes `outputs.tag` — the tag created, or empty when the release was skipped —
and calls the orchestrator with it in the same run. The orchestrator resolves the tag once and
calls each target component with its own least-privilege permissions. To re-deploy a tag by hand,
run `.github/workflows/deploy.yml` via `workflow_dispatch` with a `tag` input, and an optional
`target` to redeploy only one.

## The `deploy` block

```yaml
deploy:
  enable: false
  # timeout_minutes: 15        # component job timeout, default 15
  # order: [pypi, api-image]   # listed names run sequentially; omitted → all parallel
  targets:
    - name: pypi
      target: pypi             # pypi | npm | maven-central | nuget | cratesio | ghcr | dockerhub | custom
```

Config holds only non-derivable values: `enable`, `name`, `target`, `order`, `auth`, and a
custom target's `permissions`. The renderer fills `image`/`context`/`dockerfile`/`build`/`version`
when omitted.

Deployment is opt-in and separate from release: `versioning.enable` mints the tag and notes
regardless of whether `deploy.enable` is set.
