# CI workflows

**English** · [한국어](ci-workflows.ko.md) · [Usage guide](../../USAGE.md)

`/flow-init` renders GitHub Actions workflows from `flow-config.yaml`. Each is created only when
absent — a template fix in a newer plugin does not reach a workflow you already have; delete the
file and re-run `/flow-init` to take it.

| Workflow | Switch | Blocks a push/PR? |
|----------|--------|--------------------|
| `api-contract.yml` | `contract_test.enable` | No — reports |
| `unit-test.yml` | `unit_test.enable` | No — reports |
| `e2e.yml` | `e2e.enable` | No — reports; see [E2E](#e2e-safety-net) |
| `doc-style.yml` | `doc_style.enable` | No — reports |
| `wiki-verify.yml` | offered by `/wiki-init`, not `/flow-init` | No — reports |
| `srs-verify.yml` | offered by `/flow-init` once `docs/srs/` exists | No — reports |
| `release.yml` | `versioning.enable` + a supported `release_tool` | — mints the tag |
| `branch-naming.yml` | `versioning.branch_naming.enable` | Yes — invalid branch names |
| `entropy-check.yml` | `versioning.entropy.enable` | No — weekly report |
| `deploy.yml` + `deploy-<name>.yml` | `deploy.enable` | — deploys on a release |

None of the verification workflows above **block** a push or PR by themselves; each is a
visibility net for the commits [layer 2 never sees](tiers-and-gates.md#what-the-gate-sees) —
terminal, direct, or CI commits on a promotion branch. Making one a required status check is a
separate decision, covered under [E2E](#e2e-safety-net) below (the same preconditions apply to
any of them).

## `contract_test` — REST API contract testing

`enable: true` renders `api-contract.yml` (schemathesis) on the branches you list — usually
collaboration and promotion branches, not `feature/*`. `tool` and `action_ref` are pinned once at
setup to avoid a stale-tool surprise in CI. `schema`, `base_url` and `server`
(`compose_file`/`health_url`/`health_timeout`) point it at your API.

## `unit_test` — CI safety net

The local flow gate runs unit tests only on Claude-session commits; `enable: true` renders
`unit-test.yml` so they also run in CI. `jobs[]` is declared independently of `modules[]` — the
local gate and CI run in different contexts — one entry per language/module
(`name`/`language`/`version`/`setup`/`test`), rendered into a `strategy.matrix.include`. A
`language` of python/node/java/go/rust uses that language's official setup action; anything else
relies on your own `setup` command. The match is case-sensitive — a capitalized `Python` skips
the setup action silently. `timeout_minutes` caps every matrix job, default 10.

## E2E safety net

Playwright suites only — no browser front end, nothing to render. `enable: true` copies
`.github/workflows/e2e.yml` **as-is**; if no `playwright.config.*` exists at the repo root or up
to two levels down, `/flow-init` also points you at
[`playwright-scaffold`](manual-verification.md#playwright-scaffold). Until that config exists,
the workflow's own detect step skips every later step rather than failing — the flag renders the
file, a suite is what makes it mean anything.

This flag is a **render switch, not a run switch**: setting it back to `false` leaves an
already-rendered `e2e.yml` running; delete the file to stop it. Windows desktop UI (WPF, WinForms,
MAUI) is out of scope — no browser driver reaches it; that host still gets `unit-test.yml` and,
where a REST API exists, `api-contract.yml`.

`github/e2e.workflow.example.yml` carries four `EDIT` markers you fill in: the trigger branches,
the language setup step, the stack start/wait/teardown steps (delete all three if your Playwright
config starts what it needs via `webServer`), and the test package directory (set in two steps
that must stay in sync).

**To promote it to a required status check**, all four of these, or none:

1. add a `pull_request:` trigger — a check that never reports leaves a PR stuck on "Waiting for
   status to be reported", and requiring it on direct pushes deadlocks;
2. keep `workflow_dispatch:` — it produces a missing check during an incident with no empty
   commit needed;
3. give the branch ruleset a bypass actor, or agree who edits it when the suite breaks for an
   unrelated reason;
4. remember fork PRs get no secrets, so a credentialed suite red-lights every outside
   contribution.

The plugin does not wire this up and takes no position on whether you should.

**To block a promotion in practice** instead, add a check under `modules[].checks` with
`when: promotion` in your own config — that timing routes into the `security-scan` bucket, which
is already mandatory at Staging and Release. Four costs come with it: it runs synchronously
inside the commit hook, so the commit stalls for as long as the suite takes; the module channel
buffers output and prints it only on failure; `security-scan` runs every module regardless of
what changed; and a module check command has no timeout of its own — a hung browser suite is an
indefinitely hung commit.

## `doc-style.yml`, `wiki-verify.yml`, `srs-verify.yml`

Each guards on its script being present in the checkout (a repo that gitignores `.claude/` has
none) and exits 0 rather than failing — a repo that never opted in stays green with nothing to
verify. `doc-style.yml` lints the `doc_style.paths` scope with `doc_style_check.py --lint-config`;
a `flow-config.yaml` that does not parse fails the job instead of reading as "off".
`wiki-verify.yml` runs `wiki_graph.py --verify`, catching graph drift from commits the flow gate
never sees. `srs-verify.yml` runs `srs_check.py --verify`, catching a dead requirement anchor or a
duplicate id introduced on separate branches — the flow gate never reads an SRS at all.

## `versioning` — release, branch-naming, entropy

`enable: true` renders up to three independent workflows:

- **`release.yml`** from the template matching `release_tool` (case-insensitive):
  `python-semantic-release`, `semantic-release` (Node), `jreleaser`, `gitversion`,
  `cargo-release`. An unrecognized value is reported and no `release.yml` is rendered. Every
  template authenticates with `${{ secrets.RELEASE_TOKEN || secrets.GITHUB_TOKEN }}`
  ([release token](promotion-and-release.md#release-token-write-permission)). On the stable
  branch, every template runs a shared step that replaces the GitHub Release's notes with
  `CHANGELOG.md`'s `## vX.Y.Z` section for that tag
  ([the stable changelog section](promotion-and-release.md#the-stable-changelog-section)),
  fail-open to the notes the release tool already created when that section is missing. The
  `python-semantic-release` template additionally derives its own initial release notes from
  `CHANGELOG.md`; the other templates create theirs with `--generate-notes` and rely on the
  shared step alone to pull from the file.
- **`branch-naming.yml`** under its own `branch_naming.enable`, on every push. It fails a push
  whose branch does not match a fixed set of patterns: `feature/*`, `fix/*`, `docs/*`,
  `hotfix/X.Y.Z`, `release/X.Y.Z`, the literal `dev`, and `versioning.branches.stable`/
  `.prerelease`. The template hardcodes `dev` regardless of what `flow-config.branches.integration`
  names — a repo whose integration branch is not literally `dev` fails every push to it.
- **`entropy-check.yml`** under its own `entropy.enable`, on the `schedule` cron (default weekly)
  over `entropy.paths`.

`version_files` tells the release tool which file:field carries the version; nothing else reads
that slot.

## `deploy` — deployment layer

Covered on its own page: [Deployments](deployments.md).
