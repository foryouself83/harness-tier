# Configuration

**English** · [한국어](configuration.ko.md) · [Usage guide](../../USAGE.md)

Two files under `.claude/harness-tier/config/` decide what the harness does: `flow-config.yaml`,
which you edit, and `flow-tiers.yaml`, which you do not.

## `flow-config.yaml` — repo-specific values

`/flow-init` creates it. It is git-tracked, so everyone sharing the repo runs the same settings.
The full template, with a comment on every slot, is
[`flow-config.example.yaml`](../../flow-config.example.yaml). The core of it:

```yaml
branches:
  integration: dev           # where feature work merges
  staging: stage             # QA / release-candidate branch
  production: main           # production release branch

merge_workflow:
  pull_request: []           # flows routed through a PR; [] = every flow is a direct merge

modules:                     # per-module pre-checks
  - name: api
    path: services/api/      # run this module's checks when a file under this path changes
    checks:
      lint:        "ruff check services/api"
      static:      "uv run pyright services/api"
      import_lint: "uv run lint-imports --config services/api/.importlinter"
      test:        "uv run pytest services/api"
      security:    "uv run bandit -r services/api"

review_checklist:            # what the Dev review gate judges every changed file against
  - "regression tests pass"
  - "cross-service contract validity"
  - "DB transaction & migration safety"
  - "async task idempotency & queue routing"
  - "API error conventions"

commit_guide: docs/operations/commit-versioning-guide.md   # read by /commit when present

gate_evidence:
  invalidate_on_edit: true   # false: an edit no longer voids the review/doc-sync evidence

doc_sync:                    # what /doc-sync reconciles
  index: CLAUDE.md
  dirs:
    - "docs/"
    - ".claude/rules/"
  service_docs: "services/*/CLAUDE.md"
```

### `branches`

The three keys name your branches. The branch-flow rules match work branches by fixed
prefixes — `feature/*`, `fix/*`, `hotfix/*` — which are not configurable.

### `merge_workflow.pull_request`

The flows that go through a pull request instead of a local `git merge`:

- `daily` — `feature/*` and `fix/*` into integration;
- `promotion` — integration → staging, staging → production, and `hotfix/*` → production.

Empty (the default) keeps every flow a direct merge. Commit discipline is unaffected either
way; only the merge moves. What a PR-routed flow loses and how to replace it is in
[PR workflow and branch rulesets](promotion-and-release.md#pr-workflow-and-branch-rulesets).

### `modules` and `checks`

A file belongs to the first module whose `path` is a prefix of it; `path: ""` matches every
file, which is how a single-stack repo is one module. A changed file no module covers skips the
pre-check, and the gate lists it when it blocks.

Each `checks` key is one check. Its value is a command string, or `{ run: <cmd>, when: … }`.
Beyond `lint` · `static` · `import_lint` · `test` · `security` you can add your own keys
(license, sbom, secret-scan). The field is `when`, not `on` — YAML reads a bare `on` key as a
boolean, and the same goes for check keys named `off`, `yes`, `no`, `true` or `false`.

| `when` | Gate | Scope | Runs at |
|--------|------|-------|---------|
| `every-commit` (default for every string value except `security`) | `precommit` | changed modules | Dev, Staging and Release commits |
| `promotion` (default for the string `security`) | `security-scan` | all modules | Staging and Release commits |

A timing runs only where its gate is in the tier, so no module check runs on a Docs commit. An
unknown `when` value is read as `every-commit`, with a warning. Commands run inside the commit
hook — see [what the gate sees](tiers-and-gates.md#what-the-gate-sees).

### `review_checklist`

The categories the Dev `review` gate judges every changed file against. The five above come from
[`rules/risk-tiers.md`](../../rules/risk-tiers.md) Step 3; append your own rather than dropping one.

### `commit_guide`

Your own commit and versioning document, which `/harness-init` generates. `/commit` prefers its
project facts — scope vocabulary, 0.x policy, whether the release tool reads a `Release-Level`
trailer. A missing file leaves `/commit` on `risk-tiers.md` alone.

### `gate_evidence.invalidate_on_edit`

`true` (the default) makes any edit void the `review` and `doc-sync` evidence, the fixes a
review asked for included. `false` lets an edit after a pass commit under a review that never
saw it. Detail in [gate evidence](tiers-and-gates.md#gate-evidence).

### `doc_sync`

The documents [`/doc-sync`](daily-work.md#doc-sync--keep-the-docs-in-step) reconciles: the
`index` file, the `dirs` globs, and the per-module `service_docs` glob.

### `wiki`

Written by [`/wiki-init`](project-harness.md#wiki-init--build-the-docs-into-a-knowledge-graph).
With `enable: false` or no section, the `wiki` gate does nothing.

| Slot | Meaning |
|------|---------|
| `enable` | Turns the `wiki` gate on |
| `root` | Wiki root, `docs/` by default |
| `index` | Graph entry point, the baseline for orphan detection |
| `max_lines` | One-file-one-concept size warning; `0` turns it off |
| `context_lines` | Default line budget of `wiki_graph.py --neighbors` |
| `defect_rule_threshold` | Times one tag may fire before a promote-to-rule warning; `0` turns it off |

### `doc_style`

The prose check against [`rules/doc-style.md`](../../rules/doc-style.md).

| Slot | Meaning |
|------|---------|
| `enable` | Turns on the commit-time check and the `doc-style.yml` workflow together |
| `paths` | Repo-relative globs in scope, `["**/*.md"]` by default; add `**/*.py` · `**/*.sh` for comments |
| `exclude` | Globs kept out, added to the three the checker always skips |

The checker always skips `CHANGELOG.md`, `docs/superpowers/` and `.superpowers/`; `exclude` adds
to them and cannot remove one. `/flow-init` asks about this section.

### `design_docs`

Read by the six [design deliverable skills](design-docs.md).

| Slot | Default | Meaning |
|------|---------|---------|
| `templates` | `.claude/harness-tier/templates/design-docs` | Where the `<doc>.template.md` files live; `/flow-init` seeds them once, never overwrites |
| `docs` | `docs/deliverables` | Where a writer skill (architecture, API, ERD, table) writes `<doc>.md` — SRS and SDS stay in `docs/srs/`, `docs/sds/` |
| `output` | `docs/deliverables/results` | Where every `<doc>.docx` is rendered |
| `renderer` | `https://kroki.io` | Where a `mermaid`/`d2` diagram block is POSTed and rendered to SVG — point it at a self-hosted Kroki to keep diagram source off the public service |
| `base_docx` | `null` | A company `.docx` whose styles the render reuses; `null` uses `python-docx`'s own default styling |
| `gitignore_output` | `false` | `true` has `/flow-init` add `output` to `.gitignore` |

### CI sections

`contract_test`, `unit_test`, `e2e` and `versioning` each render a GitHub Actions workflow;
`deploy` renders the deployment workflows. Their slots and what each flag switches are in
[CI workflows](ci-workflows.md) and [deployments](deployments.md#the-deploy-block).

## `flow-tiers.yaml` — tier policy (do not edit)

It sits beside `flow-config.yaml` but belongs to the plugin, and every `/flow-init` run
overwrites it. An edit to the host copy lasts until the next run; an edit to the plugin cache
lasts until the next plugin update. There is no lasting way to change it from a host — to stop
enforcement altogether, run [`/flow-uninstall`](update-and-removal.md#flow-uninstall--remove-host-side-wiring).

It holds two things: which gates each tier requires, and `merge_strategy`, the flags each branch
flow's `git merge` must carry. Both are described in [tiers and gates](tiers-and-gates.md).
