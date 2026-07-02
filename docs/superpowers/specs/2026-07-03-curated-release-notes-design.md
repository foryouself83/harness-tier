# Grouped release notes (mechanical) — Design

- **Date**: 2026-07-03
- **Status**: Approved (brainstorming) → pending implementation plan
- **Scope**: harness-tier plugin (python release template shipped to consumers) **and** harness-tier's own release flow (dogfood)
- **Sibling**: follows [`2026-07-03-staging-bump-selection-design.md`](2026-07-03-staging-bump-selection-design.md).

## 1. Goal

Make the **GitHub Release body** a type-grouped, plumbing-filtered summary instead of
today's flat `--generate-notes` commit list — at **zero recurring cost and zero
hallucination risk** — by reusing the changelog `python-semantic-release` (PSR)
**already generates**.

## 2. Decision history (why this is mechanical, not LLM)

An earlier draft proposed LLM curation (Claude writes the notes at each promotion).
Cold ROI review rejected it for this project:

- **Value ∝ readers × how much they read notes.** harness-tier is a dev-tooling
  plugin with a small technical audience — curated prose does not pay back the build +
  per-promotion + human-review cost, nor the hallucination risk.
- **PSR already does the grouping for free.** With Conventional Commits (already
  gate-enforced), PSR's `--changelog` produces a changelog **grouped by type**:

  ```
  ## v0.1.1-rc.1 (2026-07-02)
  ### Documentation
  - Bump-gate spec/plan + token-permission guide (…)
  ### Features
  - Staging bump-level gate + token-write guard (…)
  ```

- **Plumbing filtering is NOT free — it must be configured.** PSR auto-excludes only its
  own release commits (`chore(release): … [skip ci]`); user `chore`/`ci`/`refactor`/
  `style`/`test`/`build` commits **appear** unless `[tool.semantic_release.changelog]
  exclude_commit_patterns` is set (PSR ships no default exclusions — verified against the
  PSR docs + its own `pyproject.toml`). This design **adds** the recommended exclusion set
  so the changelog (and thus the release body) stays signal-only. (`docs` is intentionally
  kept.)

**Decisions:**

| Question | Decision |
|----------|----------|
| Approach | **Mechanical** — reuse PSR's grouped `CHANGELOG.md`; no LLM, no `/flow` change |
| Release body source | **Top (latest) section of `CHANGELOG.md`**, header stripped (GitHub Release title comes from the tag) |
| Section names | **PSR default** (`Features` / `Bug Fixes` / `Documentation` …) — zero cost; Keep-a-Changelog renaming (Added/Changed/Fixed) is a deferred cosmetic follow-up (§7) |
| Plumbing filter | **Add `exclude_commit_patterns`** (PSR's recommended set) at changelog-generation time — chore/ci/refactor/style/test/build-non-deps/merge/version-only never enter `CHANGELOG.md`. Not free by default (§2) |
| Version-match guard | The `awk` selects only leading sections whose `X.Y.Z` core equals the tag core (so it also **merges multiple rc's** into a stable body); a top-section mismatch → empty → `--generate-notes`. Neutralizes the "silently wrong body on format drift / stale changelog" risk |
| Fallback | Missing/empty/unparseable/mismatched changelog → `--generate-notes` (today's behavior) — never breaks a release. **errexit-safe**: GitHub runs `run:` under `bash -eo pipefail`, so every substitution/pipe that may find nothing ends with `\|\| true`, else the step would abort and skip the fallback |
| Extraction | **Inline `awk`** in the workflow step (CI runs on ubuntu; no new shipped script, no `COPY_FILES` change). A wrong/empty extraction is low-severity because of the fallback |
| Scope | harness-tier's own `release.yml` + the **python** consumer template. **node** template needs **no change** (see §4) |
| main (stable) body | PSR does not run on main (rc-strip finalize), so the top `CHANGELOG.md` section(s) are the **rc** section(s) for this version; the guard merges **all** leading same-core rc sections so nothing that landed across `-rc.1…-rc.N` is dropped, headers stripped and the title from `vX.Y.Z` |

## 3. Change: the "Create GitHub Release" step

Both `release.yml` (own) and the python template share this shape. Replace the single
`--generate-notes` call with extract-or-fallback:

```bash
TAG="$(git describe --tags --abbrev=0)"
# … existing delete-if-exists + $PRERELEASE logic …
# Body = every LEADING CHANGELOG section whose "## vX.Y.Z" core equals the tag core, headers
# dropped. Merges multiple rc's (…-rc.1, -rc.2) into a stable body; stops at the first older
# version. A top-section mismatch / stale / missing changelog → empty output → auto-notes
# fallback. `|| true` keeps GitHub's `bash -eo pipefail` from aborting the step on a no-match.
TCORE="$(printf '%s' "$TAG" | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1 || true)"
awk -v core="$TCORE" '/^## /{v=""; if (match($0,/[0-9]+\.[0-9]+\.[0-9]+/)) v=substr($0,RSTART,RLENGTH); if (v!=core) exit; seen=1; next} seen{print}' CHANGELOG.md > release-body.md 2>/dev/null || true
if [ -n "$TCORE" ] && [ -s release-body.md ] && grep -q '[^[:space:]]' release-body.md; then
  gh release create "$TAG" --title "$TAG" --notes-file release-body.md $PRERELEASE
else
  gh release create "$TAG" --title "$TAG" --generate-notes $PRERELEASE
fi
```

`awk` logic: for each `## ` header, parse its `X.Y.Z` core; if it differs from the tag core,
`exit` (so a top-section mismatch yields empty output → fallback, and iteration stops at the
first older version); if it matches, set `seen` and drop the header (`next`). Body lines print
only once `seen` — so the `# CHANGELOG` title and `<!-- version list -->` preamble (before any
matching header) are never printed. **The `awk` only selects/slices sections — it does not
filter commit types; plumbing filtering happens upstream at PSR changelog generation (see §2 /
`exclude_commit_patterns`), so the extracted body inherits an already-clean changelog.**

## 4. Components & changes

| # | File | Change | Kind |
|---|------|--------|------|
| 1 | `.github/workflows/release.yml` | "Create GitHub Release" step → extract-or-fallback (§3) | CI (own) |
| 2 | `github/release.python-semantic-release.workflow.example.yml` | same extract-or-fallback (§3); header comment notes `CHANGELOG.md` is the PSR default path | CI template |
| 3 | `github/release.semantic-release.workflow.example.yml` | **no code change** — `npx semantic-release` (+`@semantic-release/github`) already publishes the changelog as the release body. Add a one-line comment stating notes come from the changelog (documentation only) | CI template (doc) |
| 4 | `tests/test_release_workflow.py` | structure: both workflows contain the core-aware `awk`, `--notes-file`, `--generate-notes` fallback, `TCORE`, `[ -n "$TCORE" ]`, and `\|\| true` | test |
| 5 | `tests/test_release_workflow.py` | behavior: run the real "Create GitHub Release" block (gh/git stubbed) under `bash -eo pipefail` — missing/headerless/mismatched changelog → falls back without aborting (C1 guard); matching multi-rc changelog → merges both rc bodies, drops headers, stops before the older version | test |
| 6 | `USAGE.md` / `USAGE.ko.md` | one line under the release section: the GitHub Release body is the latest grouped `CHANGELOG.md` section; missing/empty → auto-generated fallback | doc |
| 7 | `pyproject.toml` | add `[tool.semantic_release.changelog] exclude_commit_patterns` (PSR's recommended set) so plumbing types never enter the changelog/release body (dogfood) | config (own) |
| 8 | `skills/harness-authoring/references/commit-versioning-guide.md` | authoring instruction: recommend the release tool's changelog noise-filter (e.g. PSR `exclude_commit_patterns`) so consumers' release bodies are signal-only | authoring instruction (SSOT) |

Both workflow steps also carry the **version-match guard** (§3).

`rules/risk-tiers.md` gets a **one-line clarification only** (the Release promotion note now
says the grouped CHANGELOG section becomes the GitHub Release body) — no tier/gate change.

**Not touched**: `/flow` skill, `flow-tiers.yaml`, `flow_init_setup.py` (no new shipped
script), `scripts/*`. This is a CI-body + changelog-config change.

## 5. Error handling & edge cases

- **A. Fallback is the safety net — and it must be reachable.** No `CHANGELOG.md`, empty
  output, or a core mismatch → guard false → `--generate-notes`. GitHub runs `run:` under
  `bash -eo pipefail`, so a `grep`/`awk` that finds nothing exits non-zero and would abort
  the whole step (skipping the fallback) — every such substitution/pipe therefore ends with
  `|| true`. A dedicated test runs the real block under `-eo pipefail` with a missing/headerless
  changelog and asserts it falls back (regression guard for this exact trap).
- **B. rc header(s) on main.** On main the top section header(s) say `-rc.N`; the guard
  compares the `X.Y.Z` core (not the full string) so `v1.2.3-rc.N` matches tag `v1.2.3`, and
  it **merges all leading same-core rc sections** — so a version that went through several rc's
  on stage keeps every entry (fixes the single-rc assumption). Header(s) stripped; title from `vX.Y.Z`.
- **C. Consumer changelog path.** Uses `CHANGELOG.md` (PSR default). A consumer who set a
  custom `changelog_file` adjusts the path; documented in the template comment. Default is
  the common case.
- **D. Duplication across two files.** The snippet lives in `release.yml` and the python
  template; the workflow-structure test (#4) guards both against drift.
- **E. No fabrication.** Notes are verbatim from PSR's changelog — nothing is invented.
- **F. Plumbing filtered at the source, not in awk.** `exclude_commit_patterns` runs at PSR
  changelog **generation**, so chore/ci/test/etc. never enter `CHANGELOG.md`; the awk only
  slices a section. `CHANGELOG.md` and the release body therefore carry the identical,
  already-filtered content (single source, no drift). Applies from the next PSR render.
- **G. Version-match guard = drift safety.** If PSR's changelog format ever drifts or the
  changelog is stale, the top header's `X.Y.Z` core will not match the tag → the guard
  falls back to `--generate-notes` instead of shipping a wrong-but-nonempty body.

## 6. Testing strategy

1. **Workflow structure** (`tests/test_release_workflow.py`) — the extract-or-fallback
   step exists in `release.yml` and the python template (regression guard against drift).
2. **Extraction correctness** — run the `awk` one-liner over a fixture `CHANGELOG.md`
   (two versions) via subprocess; assert it returns the first section's body only, header
   dropped, and returns empty for a no-`## ` input. `pytest.skip` if `awk` is unavailable
   (portable across the Windows dev box / ubuntu CI).
3. **Static analysis** — `ruff`/`pre-commit` pass; no new `.sh` (avoids the Windows-hook
   ShellCheck concern); the awk lives in CI YAML (ubuntu runtime).
4. **Manual smoke** (verification-before-completion) — during a live promotion, confirm
   the rc + stable GitHub Releases show the grouped section, and that deleting
   `CHANGELOG.md` falls back to `--generate-notes`.

## 7. Non-goals / follow-ups

- **Keep-a-Changelog section names** (Added/Changed/Fixed) — deferred; needs a PSR custom
  Jinja changelog template or git-cliff (cosmetic; PSR defaults are a widely-used standard).
- **LLM curation** — explicitly rejected for this project (§2); could be revisited as an
  opt-in for a high-readership consumer, but not shipped on by default.
- **Node force-level / body customization** — node already publishes the changelog as the
  body; nothing to do.

## 8. Rollout / propagation

Same mechanics as the sibling feature (this repo is the plugin itself):

1. **Release as `feat`** so `plugin.json` bumps and consumers pick up the update.
2. **Consumers re-run `/flow-init`** to re-render `.github/workflows/release.yml` from the
   updated python template. No new host script is required (extraction is inline).
3. **harness-tier's own** `release.yml` is live on the next stage/main push after merge.
