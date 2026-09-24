# Update and removal

**English** · [한국어](update-and-removal.ko.md) · [Usage guide](../../USAGE.md)

## Re-run `/flow-init` — sync after a plugin update

A session says when an update is waiting. At startup a hook compares the build it loaded with
the version the marketplace publishes, and prints one line when the marketplace is ahead. Both
numbers come from local files — the marketplace clone Claude Code keeps beside its install cache
— so nothing goes over the network, and a clone that has not refreshed says nothing. A release
candidate you run ahead of what is published gets no notice.

Take the update with `/plugin`, then re-run `/flow-init`. The update alone changes nothing in
your repo: the gate scripts and the policy are copies.

A re-run, with `flow-config.yaml` present:

1. **Re-syncs**, without asking — re-copies the gate scripts and `flow-tiers.yaml`, and repairs
   the gate registration.
2. **Backfills** — offers the config slots your file lacks that the plugin's example carries.
3. **Reconfigures** — asks what to change. Picking nothing leaves a re-sync. Config and
   webhooks are kept.
4. **Re-renders** — only when a reconfigure changed an `enable` flag.

Rendered workflows are created only when absent. A workflow already in `.github/workflows/`
is reported and left untouched, so a template fix in a new plugin version does not reach it —
delete the file and re-run `/flow-init` to take the new template. The same holds for
`.pre-commit-config.yaml`, whose missing hooks are reported, not added. The exceptions are the
`deploy.yml` orchestrator and the managed deploy block in `release.yml`, which are regenerated
on every run.

## `/flow-uninstall` — remove host-side wiring

```text
/flow-uninstall   # no arguments; asks for confirmation, default no
```

Run it **before** `/plugin uninstall`: the cleanup lives inside the plugin, so removing the
plugin first leaves you with the [manual cleanup](#manual-cleanup-after-the-plugin-is-gone).

It removes:

- the commit gate from `.claude/settings.json` `hooks.PreToolUse`, keeping your other hooks;
- the `harness-tier` entry from `extraKnownMarketplaces`;
- the two harness-tier lines from `.gitignore`;
- the `harness-tier:teams` block from `CLAUDE.md`;
- `.claude/harness-tier/` — scripts, config, evidence, and both webhook files, the team-shared
  `teams-webhooks.json` included.

It leaves, and tells you to handle:

- `.pre-commit-config.yaml` — its `teams-notify-push` and static-analysis hooks stay;
- the installed git hooks —
  `pre-commit uninstall --hook-type pre-commit --hook-type commit-msg --hook-type pre-push`;
- `.github/workflows/` — see step 5 of the manual cleanup for what each one does next;
- the deletion itself — `.claude/harness-tier/` was tracked, so commit it.

When it ends on `커밋 게이트 훅이 settings.json 에 남았습니다`, the hook it could not remove points
at a script that no longer exists. Delete that hook by hand (step 2 below).

## Manual cleanup after the plugin is gone

1. Delete `.claude/harness-tier/`.
2. In `.claude/settings.json`, remove the `hooks.PreToolUse` hook whose command is
   `bash "${CLAUDE_PROJECT_DIR:-.}/.claude/harness-tier/scripts/precommit-runner.sh"` — only
   that hook — and `extraKnownMarketplaces.harness-tier`.
3. Remove `.teams-webhooks.local.json` and `.claude/harness-tier/.flow/` from `.gitignore`.
4. Remove the `harness-tier:teams` block from `CLAUDE.md`.
5. Decide on each rendered workflow:
   - `wiki-verify.yml`, `doc-style.yml`, `srs-verify.yml` — each skips when its script is gone,
     stays green, verifies nothing, and still spends a runner on every push. Delete them.
   - release workflows — every template computes the rc version with
     `.claude/harness-tier/scripts/bump_version.py`, unguarded, so every staging push fails.
     On the stable branch `gitversion`, `jreleaser` and `semantic-release` fail too;
     `python-semantic-release` guards its call and falls back to plain compute;
     `cargo-release` skips the finalize guard and releases. Delete the workflow, or replace
     its version step by hand.
   - `branch-naming.yml` (every push), `entropy-check.yml` (weekly), `api-contract.yml`,
     `unit-test.yml`, `e2e.yml`, `deploy.yml` and `deploy-*.yml` reference nothing of ours and
     keep running. Delete the ones you no longer want; `docs/operations/deploy-guide.md` goes
     with the deploy workflows.
6. Either run
   `pre-commit uninstall --hook-type pre-commit --hook-type commit-msg --hook-type pre-push`, or
   remove the `teams-notify-push` hook from `.pre-commit-config.yaml` — its entry points at
   `.claude/harness-tier/scripts/notify-push.sh`, which step 1 deleted.
7. Commit the result.
