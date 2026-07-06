# commit-versioning-guide Authoring Instructions

The discipline `harness-authoring` follows when generating `docs/operations/commit-versioning-guide.md`.
**Discipline SSOT**: [harness-rules.md](../../../rules/harness-rules.md) §Version/release convention research (13·13-1·13-2).

---

## Generation Conditions

- **Always generate** (regardless of flow detection) — since it falls within code-style + convention documentation scope, it is not subject to rule 14 defer.
- Output path: `docs/operations/commit-versioning-guide.md`
- Link sources to `docs/research/` (never reference `.harness/` paths — they break after cleanup).

---

## Document Structure (section order)

### 1. Conventional Commits Summary
- Format: `<type>[optional scope]: <description>` (official spec link required)
- Key types: `feat` (MINOR) · `fix` (PATCH) · `BREAKING CHANGE` (MAJOR) · `chore`/`docs`/`ci` (no version impact)
- Source: <https://www.conventionalcommits.org> (link required)

### 2. SemVer Policy
- Explain the meaning of `MAJOR.MINOR.PATCH` (source: <https://semver.org>).
- **Recommended policy for 0.x projects**:
  - `major_on_zero=false` — stay on 0.x even with a `BREAKING CHANGE` commit (prevents accidental promotion to 1.0.0).
  - Use annotated tags: `git tag -a v0.x.y -m "release v0.x.y"` (more changelog-tool-friendly than lightweight tags).
  - Promotion to 1.0.0 is done only by an explicit, manual decision.

### 3. Release Tool Configuration (per stack)
If the stack is confirmed, describe the corresponding tool. **If unconfirmed, leave it as "needs confirmation" and do not fabricate (harness-rules 4).**

#### Default Tool Candidates per Stack

**SSOT**: [harness-rules.md §13](../../../rules/harness-rules.md) "Version/release convention
research" holds the definitive per-stack candidate list — do not duplicate it here (harness-rules
rule 8, no duplication).

> **Do not assert a library**: the candidates there are starting points; do not commit to a
> specific tool without research·code-analyzer evidence (harness-authoring principle).

#### Rendered CI Templates — Bump-Level Mechanism Differs by Tool

`/flow-init` renders `.github/workflows/release.yml` from `github/release.<tool>.workflow.example.yml`
(case-insensitive match on `release_tool`) for: `python-semantic-release` · `semantic-release` ·
`jreleaser` · `gitversion` · `cargo-release`. Other candidates (Scala/sbt-release, C++/PHP/Ruby/Swift/Go)
have no template yet — CI wiring stays opt-in/manual (rule 13-2).

- **The current version always comes from the release branch's git tag**
  (`git describe --tags --abbrev=0`), never a value the human types in — this is the one
  language-agnostic part all templates share.
- **Python/Node read Conventional Commits themselves** — patch/minor/major is auto-derived.
- **JReleaser/GitVersion/cargo-release do not** (verified against each tool's docs — do not
  assume otherwise for a new stack without the same verification). Their templates instead read
  the same `Release-Level: major|minor|patch` commit trailer the `/flow` staging-bump step
  already writes (the human picks the *level*, not a version number), defaulting to `patch` when
  absent. JReleaser/GitVersion compute the next version with the shared `scripts/bump_version.py`
  helper; cargo-release takes the level as a native CLI argument instead (no helper needed).
- **GitVersion/cargo-release don't create a GitHub Release natively** (only a git tag) — their
  templates add a `gh release create` step, same as the Python template's `gh` usage.

#### Configuration Items (fill in per tool from research results)
- whether a changelog is generated·file location
- **changelog noise filter** — the rendered release workflow uses the latest changelog
  section as the GitHub Release body, so exclude plumbing commit types to keep it
  signal-only (e.g. python-semantic-release `[tool.semantic_release.changelog]
  exclude_commit_patterns` for `chore`/`ci`/`refactor`/`style`/`test`/`build`-non-deps/merge;
  PSR ships no defaults). Feed the tool's own recommended patterns; do not fabricate.
- pre/post-release CI hooks
- proposed value for the `flow-config.versioning.release_tool` slot
- proposed value for the `flow-config.versioning.version_files` slot (file list)

### 3b. CI Token Write Permission — how to grant
- The release CI pushes tags/commits, so its token needs **write**. Document, in order:
  primary (Settings → Actions → Workflow permissions = Read and write), org override,
  protected-branch bypass, and PAT/`RELEASE_TOKEN` escalation (Contents+Workflows: RW,
  repo secret).
- **State the default/fallback**: the rendered release workflow already references
  `${{ secrets.RELEASE_TOKEN || secrets.GITHUB_TOKEN }}`, so by default it runs on the
  auto-provided `GITHUB_TOKEN` — `RELEASE_TOKEN` is an **opt-in escalation** (bypass branch
  protection / trigger downstream). When the secret is unset the expression falls back to
  `GITHUB_TOKEN`, and adding it later needs no YAML edit.
- This is the single canonical location; guard messages link here.

### 4. Version Check Commands
```bash
# Check the current tag-based version (common to all stacks)
git describe --tags --abbrev=0

# Release-tool dry-run (fill in after confirming the tool — per stack)
# Python:      semantic-release version --dry-run
# Node:        semantic-release --dry-run
# Rust:        cargo release <level>              # dry-run BY DEFAULT — add --execute to apply
# Go:          goreleaser release --skip-publish --snapshot
# Java/Kotlin: jreleaser full-release --dry-run
# C#:          dotnet-gitversion /showvariable SemVer   # reports only — does not drive the release
# Scala:       sbt "release with-defaults"         # no --dry-run flag; no CI template yet (opt-in/manual)
# C++/PHP/Ruby/Swift: project-specific — no ecosystem-standard tool (see harness-rules.md §13)
```

### 5. Guidance When flow Is Detected
- **flow detected** — defer the `commit-versioning-guide`'s **tier·commit discipline content** to [risk-tiers.md](../../../rules/risk-tiers.md).
  This doc describes only the *version·release mechanism* and does not duplicate process discipline (approval·merge·PR, etc.).
- **flow not detected** — propose the actual release-tool setup (CI workflows·hooks) as opt-in (generate only with user consent).

---

## Authoring Rules

1. **Source URLs required** — attach the Conventional Commits·SemVer official links + the release tool's official docs links.
2. **State the 0.x policy** — if the project is 0.x, be sure to describe `major_on_zero=false` + annotated tags in the recommendation section.
3. **Do not emit tier·commit discipline** — for approval flow·branching strategy·PR discipline, keep only the risk-tiers defer wording and do not emit them yourself.
4. **No duplicate flow generation** — do not generate in this doc the actual CI workflow·release hook files that `/flow-init` renders when flow is detected.
5. **Unconfirmed stack — "needs confirmation"** — if the release tool·version file is uncertain, do not fabricate (harness-rules 4).
6. **Concise** — 1-3 lines per item. Concrete commands/config values over verbose explanation.
7. **Emit the token-write-permission section** — always include §3b (single canonical
   location); the rendered release workflow's guard message links to it.
