# Harness action vocabulary

Skill bodies name actions, never a harness's tool. Each harness maps these actions to its own tools;
Claude Code maps them natively, other harnesses read `<harness>.md` beside this file.

| Action (as written in a skill) | Meaning |
|---|---|
| **Ask the user (structured choice)** | Present one question with 2–4 labelled options and wait for the answer before continuing. |
| **Ask the user (multi-select)** | Same, where the user may pick several options. |
| **Invoke skill `<name>`** | Load that skill's instructions in full and follow them now. |
| **Dispatch subagent `<role>`** | Run a separate agent with the role file `agents/<role>.md` and the task; use its report. |
| **Dispatch subagent (general)** | Same, with no role file. |
| **Track steps** | Keep a visible checklist of the steps and their status. |
| **Plugin root** | The directory holding this plugin, spelled `${CLAUDE_PLUGIN_ROOT}` in commands. |

A skill that needs a capability a harness lacks says what to do instead inline, never by tool name.

## Interaction rule

Wherever this skill asks the user something, use the host's blocking question tool already in your tool list, matched by capability rather than by a host-specific name; if it is listed but not loaded, load it first with the host's tool-discovery primitive; only when no such tool is listed, or a question call errors, offer numbered options in chat and end your turn to wait for the reply — never answer the question yourself or skip it.

Every skill or agent that asks the user carries the sentence above once, verbatim, near the top
of its body (`tests/skills/test_harness_vocabulary.py`).
