# Codex tool notes

Harness-tier skills name actions (`vocabulary.md` beside this file). On Codex they map as follows.

- **Ask the user (structured choice):** call `request_user_input` when it is in your tool list (Plan
  mode). Otherwise write the question and numbered options in chat, then end your turn and wait for
  the reply — do not pick an option yourself.
- **Ask the user (multi-select):** `request_user_input` has no multi-select option, in Plan mode or
  any other. Always use the chat fallback above instead: numbered options, ask for one or more
  numbers, then end your turn and wait for the reply.
- **Invoke skill `<name>`:** open that skill's `SKILL.md` from the skills list and follow it in full.
  When an injected skill body ends in a truncation warning (Codex cuts at 8,000 bytes), read the
  whole `SKILL.md` file before acting.
- **`$ARGUMENTS`:** Codex does not substitute this either. In a skill it is the text written after
  the skill's name (`$flow <text>`), or the user's request when the skill runs without one.
- **Dispatch subagent `<role>`:** call `spawn_agent` with `fork_turns: "none"` (V2) or
  `fork_context: false` (V1), passing the text of `agents/<role>.md` followed by the task as the
  message. Without a subagent tool, do the work inline.
- **Track steps:** use `update_plan` when available, else a checklist in chat.
- **Plugin root:** Codex does not substitute `${CLAUDE_PLUGIN_ROOT}` inside skills. Replace it with
  the directory two levels above the `SKILL.md` you are following.
- **Skill frontmatter:** Codex ignores `allowed-tools`, `context: fork`, `agent` and `model`. A skill
  marked `context: fork` runs inline. `disable-model-invocation: true` has no effect here either —
  a sibling `agents/openai.yaml` (`policy: {allow_implicit_invocation: false}`) hides the skill
  from Codex's catalog instead.
- **Project instructions:** the harness-tier block in the root `AGENTS.md` is generated from
  `CLAUDE.md` and `.claude/rules/`, except `.claude/rules/harness-tier/` (the plugin's own
  rules an older `/flow-init` may have left there, covered already by the SessionStart hook
  injection instead); edit those sources, never the block. A directory's own `CLAUDE.md`
  applies to its files: read it before working under that directory.
- **Commit gate:** a commit is blocked by a hook that returns a deny decision; read its reason and
  fix the cause — never work around it.
