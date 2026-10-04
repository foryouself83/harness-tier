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
> `flow_init_setup.py --uninstall`, reachable only through `${CLAUDE_PLUGIN_ROOT}` —
> so uninstalling the plugin first strands the host files this skill exists to remove.
> Order is the whole point of the skill.

**Interaction.** Wherever this skill asks the user something, use the host's blocking question
tool already in your tool list, matched by capability rather than by a host-specific name; if it
is listed but not loaded, load it first with the host's tool-discovery primitive; only when no
such tool is listed, or a question call errors, offer numbered options in chat and end your turn
to wait for the reply — never answer the question yourself or skip it.

## Execution

1. **Confirm (destructive)** — deleting `.claude/harness-tier/` removes host-owned
   files too: `flow-config.yaml`, **webhooks**
   (`teams-webhooks.json` is git-tracked/team-shared), the **design-doc templates** under
   `templates/` with any edits made to them, and gate evidence. List what will be removed —
   saying the templates can be copied out first — and ask the user (structured choice) to
   confirm (default: **no**). Stop if declined.

2. **Run the cleanup** (idempotent — match-then-skip, the inverse of `/flow-init`):
   ```bash
   python3 "${CLAUDE_PLUGIN_ROOT}/scripts/flow_init_setup.py" --uninstall
   ```
   Relay its report. It:
   - **Unregisters** the commit gate and the `harness-tier` marketplace from
     `.claude/settings.json` (preserves any other hooks), and deletes the file when nothing
     else is left in it.
   - **Strips** the harness-tier `.gitignore` lines — keeping `.teams-webhooks.local.json`,
     which may still guard a secret — and the `CLAUDE.md` `harness-tier:teams` managed block.
   - **Deletes** `.claude/harness-tier/` (scripts, config, evidence, webhooks, templates) and
     `.claude/rules/harness-tier/` (the plugin's rules an older `/flow-init` may have copied in
     — the host's own rules stay).

3. **Relay the manual follow-ups** the script prints (it does **not** do these —
   they're destructive to user-owned files):
   - `.pre-commit-config.yaml`'s `teams-notify-push` / static-analysis hooks are
     left in place (team customizations / comments). Remove by hand if desired.
   - The workflows it names under `.github/workflows/`, read from the files there:
     - the ones calling the deleted `.claude/harness-tier/` **without a guard fail** —
       `release.yml` from every release tool, on each push to the prerelease branch;
     - `wiki-verify.yml`, `doc-style.yml` and `srs-verify.yml` guard their script and exit 0,
       verifying nothing while each still spends a runner on every push;
     - self-contained renders (`branch-naming.yml`, `entropy-check.yml`, `unit-test.yml`,
       `api-contract.yml`, `e2e.yml`, `deploy*.yml`) keep running and costing runner minutes.
     Remove what is no longer wanted by hand.
   - Disable the installed git hooks:
     `pre-commit uninstall --hook-type pre-commit --hook-type commit-msg --hook-type pre-push`.
   - Commit the deletions (the removed `.claude/harness-tier/` files were git-tracked, and so
     may be the changed or deleted `.claude/settings.json`).

4. After cleanup, the user can `/plugin uninstall harness-tier` to remove the cached
   plugin.

## Critical rules

1. **Confirm before destroying** — never delete `.claude/harness-tier/` without explicit
   approval — ask the user (structured choice); it contains host-owned config/credentials/webhooks.
2. **Order matters** — run before `/plugin uninstall` (the cleanup script lives in
   the plugin).
3. **Leave user-owned tool config alone** — `.pre-commit-config.yaml` and installed
   git hooks are reported for manual removal, never auto-edited (avoids destroying
   team customizations).
