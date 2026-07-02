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

| Stack | Recommended Tool | Version File |
|------|-----------|-----------|
| Python | `python-semantic-release` | `[tool.poetry] version` or `__version__` in `pyproject.toml` |
| Node/TypeScript | `semantic-release` | `"version"` in `package.json` |
| Rust | `cargo-release` | `[package] version` in `Cargo.toml` |
| Go | `goreleaser` | `go.mod` tag-based (no file version — git tags are the SSOT) |
| Other | researcher investigates the ecosystem standard and proposes with rationale | — |

> **Do not assert a library**: the list above is candidates; do not commit to a specific tool without research·code-analyzer evidence (harness-authoring principle).

#### Configuration Items (fill in per tool from research results)
- whether a changelog is generated·file location
- pre/post-release CI hooks
- proposed value for the `flow-config.versioning.release_tool` slot
- proposed value for the `flow-config.versioning.version_files` slot (file list)

### 4. Version Check Commands
```bash
# Check the current tag-based version (common to all stacks)
git describe --tags --abbrev=0

# Release-tool dry-run (fill in after confirming the tool — per stack)
# Python: semantic-release version --dry-run
# Node:   semantic-release --dry-run
# Rust:   cargo release --dry-run
# Go:     goreleaser release --skip-publish --snapshot
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
