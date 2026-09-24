# PR-mode promotion

> Read when `flow-config.merge_workflow.pull_request` includes `promotion` or `daily`.

When `flow-config.merge_workflow.pull_request` includes `promotion`, the merge moves to a pull
request and the hook stops seeing it. Gate recording is unchanged — every marker
[`SKILL.md`](../SKILL.md) records is still written on the local commit.

- The PR **must** land as a **merge commit**. A rebase stops the release; a squash destroys the
  history semantic-release reads.
- On a `count >= 1` host, pin the trailer Step 1 item 3 chose in the merge command, `auto`
  included (a legacy re-promotion pins none).
  `PR` is a literal number: written as `<n>`, bash reads `<n` as a redirection and eats the
  next word.

  ```bash
  PR=123
  gh pr merge "$PR" --merge --subject "Merge <staging>: release X.Y.Z" --body "Release-Level: <choice>"
  ```

- The PR merge replaces Step 1 item 8's and Step 2 item 6's push: confirm the rc once it lands.
- The Release PR carries no stable changelog section: the PR merges `origin/<staging>`, not
  the local merge Step 2 item 5 folds into ([`changelog.md`](changelog.md)).
- A **`hotfix/*` → production** landing is a PR under this mode too — the production ruleset
  governs every merge into that branch and rejects the local squash-and-push.
- Under `daily` PR mode the integration ruleset rejects the re-promotion back-merge's
  `git push origin <integration>`, as it does the release back-merge's: whoever runs it needs
  the integration bypass actor ([`promotion.md`](../../../rules/promotion.md) PR workflow).
