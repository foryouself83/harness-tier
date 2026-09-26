# The stable changelog section

> Read at [`SKILL.md`](../SKILL.md) Step 2 item 5, with the production merge open and its
> commit not yet written.
>
> Under `promotion` PR mode, skip it now: the PR merges `origin/<staging>`, never this local
> merge, so nothing folded here reaches production. Tell the user the release keeps the notes
> its tool generated.

The release workflow replaces a stable release's notes with the `## vX.Y.Z` section of
`CHANGELOG.md`, when one exists. Without it the notes are whatever the tool generated: the rc
sections repeated as they were cut, or GitHub's raw commit list — and after a re-promotion
that bumped the base, the earlier rc's commits are missing from them. This step writes that
section: a summary, not a concatenation.

**1. Read what the release folds in.**

```bash
python3 .claude/harness-tier/scripts/changelog_section.py pending
```

The first line, `since: vA.B.C`, is the last stable tag. Every rc section above it follows,
a series a re-promotion abandoned included. `invalid choice: 'pending'` or a missing script
means the host copy predates this step: tell the user to re-run `/flow-init`, and skip it.

Then read the commits themselves — the authority, and on a host whose release tool writes no
changelog the only input. Write `vA.B.C` from the `since:` line:

```bash
git log --no-merges --format='- %h %s%n%b' vA.B.C..origin/<staging>
```

**2. Draft the section body.**

- Group under the headings the file already uses — `### Breaking Changes`, `### Features`,
  `### Bug Fixes`, `### Performance Improvements` on a PSR host — and only the groups that
  have entries.
- One bullet per change a consumer notices: `- **scope**: what changed`. Commits fixing the
  same thing become one bullet. A change and its revert both drop. A fix to a feature this
  same release introduces folds into that feature's bullet.
- Leave out what the host's changelog configuration excludes — a PSR host's
  `exclude_commit_patterns` — and every `chore(release)` commit; with no such list, leave out
  `chore`, `ci`, `test`, `refactor`, `style` and `build`.
- The fact in force, in the language the changelog is already written in. No heading line:
  the script writes it.

**3. Show the draft to the user** — `AskUserQuestion`: use it, or edit it. Consumers read this
text; nothing is written before the answer.

**4. Fold it in.** Write the approved body to `.claude/harness-tier/.flow/release-notes.md`,
then, with `X.Y.Z` the base of Step 2 item 1's `pending:` rc:

```bash
python3 .claude/harness-tier/scripts/changelog_section.py fold --version X.Y.Z --body-file .claude/harness-tier/.flow/release-notes.md
git add CHANGELOG.md
```

`fold` removes every rc section `pending` printed, writes one `## vX.Y.Z (date)` section at
the top of the release list — where PSR inserts its next one — and keeps every older section.
It creates `CHANGELOG.md` when there is none. Exit 2 names its reason:
`CHANGELOG already has a vX.Y.Z section` on a rerun (leave it), or an empty body.

The staged file joins the open merge, so Step 2 item 6's commit carries it.

**Not here:**

- A hotfix folds nothing. PSR's hotfix path writes its own stable section, and the release
  step reads that one.
- A Node host whose `.releaserc` runs `@semantic-release/changelog` gets a second section,
  prepended above this one, whenever semantic-release rather than the forced-level path
  finalizes the rc — and the release step reads that first one. Tell the user once: dropping
  the plugin keeps this summary as the release notes.
