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
- **PSR already does the useful part for free.** With Conventional Commits (already
  gate-enforced), PSR's `--changelog` produces a changelog **grouped by type** and
  **with plumbing filtered**. Verified against the live `CHANGELOG.md`:

  ```
  ## v0.1.1-rc.1 (2026-07-02)
  ### Documentation
  - Bump-gate spec/plan + token-permission guide (…)
  ### Features
  - Staging bump-level gate + token-write guard (…)
  ```

  Note the `chore(release): pin sha` / `sync uv.lock` plumbing commits are **absent** —
  PSR excludes `chore` from the changelog by default. The grouping + filter we would
  have scripted **already exist**.

**Decisions:**

| Question | Decision |
|----------|----------|
| Approach | **Mechanical** — reuse PSR's grouped `CHANGELOG.md`; no LLM, no `/flow` change |
| Release body source | **Top (latest) section of `CHANGELOG.md`**, header stripped (GitHub Release title comes from the tag) |
| Section names | **PSR default** (`Features` / `Bug Fixes` / `Documentation` …) — zero cost; Keep-a-Changelog renaming (Added/Changed/Fixed) is a deferred cosmetic follow-up (§7) |
| Fallback | Missing/empty/unparseable changelog → `--generate-notes` (today's behavior) — never breaks a release |
| Extraction | **Inline `awk`** in the workflow step (CI runs on ubuntu; no new shipped script, no `COPY_FILES` change). A wrong/empty extraction is low-severity because of the fallback |
| Scope | harness-tier's own `release.yml` + the **python** consumer template. **node** template needs **no change** (see §4) |
| main (stable) body | PSR does not run on main (rc-strip finalize), so the top `CHANGELOG.md` section is the **rc** section — its *content* equals the stable content; header is stripped and the title comes from `vX.Y.Z`, so it is correct |

## 3. Change: the "Create GitHub Release" step

Both `release.yml` (own) and the python template share this shape. Replace the single
`--generate-notes` call with extract-or-fallback:

```bash
TAG="$(git describe --tags --abbrev=0)"
# … existing delete-if-exists + $PRERELEASE logic …
# Extract the latest CHANGELOG section body (drop the "## vX.Y.Z (date)" header,
# stop at the next "## " version header). CI is ubuntu → awk is standard.
awk '/^## /{n++; if (n==2) exit} n==1 && !/^## /' CHANGELOG.md > release-body.md 2>/dev/null || true
if [ -s release-body.md ] && grep -q '[^[:space:]]' release-body.md; then
  gh release create "$TAG" --title "$TAG" --notes-file release-body.md $PRERELEASE
else
  gh release create "$TAG" --title "$TAG" --generate-notes $PRERELEASE
fi
```

`awk` boundary: the first `## ` sets `n=1` and is itself a `## ` line, so the header is
dropped; section body (`### …`, bullets) prints; the next `## ` sets `n=2` → exit. One
section total → prints to EOF. The `<!-- version list -->` comment precedes the first
`## ` (`n==0`) → not printed.

## 4. Components & changes

| # | File | Change | Kind |
|---|------|--------|------|
| 1 | `.github/workflows/release.yml` | "Create GitHub Release" step → extract-or-fallback (§3) | CI (own) |
| 2 | `github/release.python-semantic-release.workflow.example.yml` | same extract-or-fallback (§3); header comment notes `CHANGELOG.md` is the PSR default path | CI template |
| 3 | `github/release.semantic-release.workflow.example.yml` | **no code change** — `npx semantic-release` (+`@semantic-release/github`) already publishes the changelog as the release body. Add a one-line comment stating notes come from the changelog (documentation only) | CI template (doc) |
| 4 | `tests/test_release_workflow.py` | assert `release.yml` + python template "Create GitHub Release" step contains the `awk … CHANGELOG.md` extraction, `--notes-file`, and the `--generate-notes` fallback | test |
| 5 | `tests/test_release_workflow.py` (or new) | run the `awk` snippet against a fixture changelog (skip if `awk` absent) → asserts header dropped, sub-sections kept, stops before the next version, empty on a headerless input | test |
| 6 | `USAGE.md` / `USAGE.ko.md` | one line under the release section: the GitHub Release body is the latest grouped `CHANGELOG.md` section; missing/empty → auto-generated fallback | doc |

**Not touched**: `/flow` skill, `rules/risk-tiers.md`, `flow-tiers.yaml`,
`flow_init_setup.py` (no new shipped script), `scripts/*`. This is a CI-body change only.

## 5. Error handling & edge cases

- **A. Fallback is the safety net.** No `CHANGELOG.md`, empty top section, or awk failure
  → `[ -s … ]`/`grep` guard false → `--generate-notes`. A release never fails on this.
- **B. rc header on main.** On main the top section header says `-rc.N`; the header is
  stripped and the title is `v$STABLE`, so the body is correct (content == stable).
- **C. Consumer changelog path.** Uses `CHANGELOG.md` (PSR default). A consumer who set a
  custom `changelog_file` adjusts the path; documented in the template comment. Default is
  the common case.
- **D. Duplication across two files.** The snippet lives in `release.yml` and the python
  template; the workflow-structure test (#4) guards both against drift.
- **E. No fabrication.** Notes are verbatim from PSR's changelog — nothing is invented.

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
