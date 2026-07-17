---
name: flow-uninstall
description: Remove harness-tier's wiring from this repo — the inverse of /flow-init. Deletes host-owned config, so it confirms first. Run BEFORE /plugin uninstall.
disable-model-invocation: true
---

# Flow-Uninstall — Remove host-side wiring

Undo what [`/flow-init`](../flow-init/SKILL.md) installed in the host repo.
`/plugin uninstall harness-tier` removes only the **cache** (the plugin outside the
host); everything flow-init wrote **into** the host repo stays unless removed here.

> **Run this BEFORE `/plugin uninstall`.** The cleanup runs the plugin's
> `flow_init_setup.py --uninstall`, which is reachable only while the plugin is
> still installed (`${CLAUDE_PLUGIN_ROOT}`). If the plugin is already gone, fall
> back to the manual steps in [USAGE.md](../../USAGE.md) (§ uninstall).

## Execution

1. **Confirm (destructive)** — deleting `.claude/harness-tier/` removes host-owned
   files too: `flow-config.yaml`, **webhooks**
   (`teams-webhooks.json` is git-tracked/team-shared), and gate evidence. List what
   will be removed and use `AskUserQuestion` to confirm (default: **no**). Stop if
   declined.

2. **Run the cleanup** (idempotent — match-then-skip, the inverse of `/flow-init`):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/flow_init_setup.py" --uninstall
   ```
   Relay its report. It:
   - **Unregisters** the commit gate and the `harness-tier` marketplace from
     `.claude/settings.json` (preserves any other hooks).
   - **Strips** the harness-tier `.gitignore` lines and the `CLAUDE.md` `harness-tier:teams`
     managed block.
   - **Deletes** `.claude/harness-tier/` (scripts, config, evidence, webhooks).

3. **Relay the manual follow-ups** the script prints (it does **not** do these —
   they're destructive to user-owned files):
   - `.pre-commit-config.yaml`'s `teams-notify-push` / static-analysis hooks are
     left in place (team customizations / comments). Remove by hand if desired.
   - Disable the installed git hooks:
     `pre-commit uninstall --hook-type pre-commit --hook-type commit-msg --hook-type pre-push`.
   - Commit the deletions (the removed `.claude/harness-tier/` files were git-tracked).

4. After cleanup, the user can `/plugin uninstall harness-tier` to remove the cached
   plugin.

## Critical rules

1. **Confirm before destroying** — never delete `.claude/harness-tier/` without explicit
   `AskUserQuestion` approval; it contains host-owned config/credentials/webhooks.
2. **Order matters** — run before `/plugin uninstall` (the cleanup script lives in
   the plugin).
3. **Leave user-owned tool config alone** — `.pre-commit-config.yaml` and installed
   git hooks are reported for manual removal, never auto-edited (avoids destroying
   team customizations).
