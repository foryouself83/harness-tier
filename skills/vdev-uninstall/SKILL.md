---
name: vdev-uninstall
description: Remove vway-kit's host-side wiring (the inverse of /vdev-init) — unregisters the commit gate and marketplace from settings.json, strips the .gitignore lines and CLAUDE.md teams block, and deletes .claude/vway-kit/. Confirms before deleting; pre-commit/git hooks are reported for manual removal. Run BEFORE /plugin uninstall.
allowed-tools: Bash, Read, AskUserQuestion
argument-hint: (none)
disable-model-invocation: true
---

# Vdev-Uninstall — Remove host-side wiring

Undo what [`/vdev-init`](../vdev-init/SKILL.md) installed in the host repo.
`/plugin uninstall vway-kit` removes only the **cache** (the plugin outside the
host); everything vdev-init wrote **into** the host repo stays unless removed here.

> **Run this BEFORE `/plugin uninstall`.** The cleanup runs the plugin's
> `vdev_init_setup.py --uninstall`, which is reachable only while the plugin is
> still installed (`${CLAUDE_PLUGIN_ROOT}`). If the plugin is already gone, fall
> back to the manual steps in [USAGE.md](../../USAGE.md) (§ uninstall).

## Path conventions

```bash
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
PLUGIN="${CLAUDE_PLUGIN_ROOT}"
```

## Execution

1. **Confirm (destructive)** — deleting `.claude/vway-kit/` removes host-owned
   files too: `vdev-config.yaml`, **webhooks**
   (`teams-webhooks.json` is git-tracked/team-shared), and gate evidence. List what
   will be removed and use `AskUserQuestion` to confirm (default: **no**). Stop if
   declined. (Teamer 자격증명은 OS keyring(`vway-kit-teamer`)에 있어 파일 삭제로는
   지워지지 않는다 — 필요하면 사용자가 키체인에서 직접 제거.)

2. **Run the cleanup** (idempotent — match-then-skip, the inverse of `/vdev-init`):
   ```bash
   python3 "${PLUGIN}/scripts/vdev_init_setup.py" --uninstall
   ```
   Relay its report. It:
   - **Unregisters** the commit gate and the `vway` marketplace from
     `.claude/settings.json` (preserves any other hooks).
   - **Strips** the vway-kit `.gitignore` lines and the `CLAUDE.md` `vway-kit:teams`
     managed block.
   - **Deletes** `.claude/vway-kit/` (scripts, config, evidence, webhooks).

3. **Relay the manual follow-ups** the script prints (it does **not** do these —
   they're destructive to user-owned files):
   - `.pre-commit-config.yaml`'s `teams-notify-push` / static-analysis hooks are
     left in place (team customizations / comments). Remove by hand if desired.
   - Disable the installed git hooks:
     `pre-commit uninstall --hook-type pre-commit --hook-type commit-msg --hook-type pre-push`.
   - Commit the deletions (the removed `.claude/vway-kit/` files were git-tracked).

4. After cleanup, the user can `/plugin uninstall vway-kit` to remove the cached
   plugin.

## Critical rules

1. **Confirm before destroying** — never delete `.claude/vway-kit/` without explicit
   `AskUserQuestion` approval; it contains host-owned config/credentials/webhooks.
2. **Order matters** — run before `/plugin uninstall` (the cleanup script lives in
   the plugin).
3. **Leave user-owned tool config alone** — `.pre-commit-config.yaml` and installed
   git hooks are reported for manual removal, never auto-edited (avoids destroying
   team customizations).
