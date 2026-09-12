---
paths:
  - "skills/**/*.md"
---

# Editing this plugin's own skills

These files *are* the product: a frontmatter line changes what every consumer's agent
does. `tests/skills/` is the enforced contract — it reads the shipped files and
its assertion messages carry the reasoning, so run it before arguing with it. What
follows is only the judgement it cannot make: a test catches a wrong value, never a
missing field that should have been there.

`name` + `description` are the floor. Every other field has to buy something.

## `allowed-tools` grants; it does not restrict

> "It does not restrict which tools are available: every tool remains callable."
> — [skills.md](https://code.claude.com/docs/en/skills.md), *Pre-approve tools for a skill*

So `allowed-tools: Bash, Read, Write, Edit, Glob, Grep` does not say "this skill uses
these tools". It says **grant this skill every command and every file write, unasked** —
and `Read`/`Grep`/`Glob`/`AskUserQuestion`/`Agent` never prompt in the first place, so
those entries grant nothing and only make the line read like a limit.

Add it when a command the skill runs prompts on every invocation, and scope each rule to
that command — the space before `*` is a prefix boundary:

```yaml
allowed-tools: Bash(k6 run *) Bash(touch .claude/harness-tier/.flow/doc-sync.done)
```

Never end a rule in a path glob (`…/.flow/*`): the `*` crosses path separators including
`..`, so it pre-approves the command against any path on disk while reading as a
directory scope. Marker sets are finite — enumerate them exactly.

Two limits decide where this is even possible:

- **`${CLAUDE_PLUGIN_ROOT}` does not substitute.** Only `${CLAUDE_PROJECT_DIR}` is
  documented for `allowed-tools`, and the cache path carries the plugin version, so a
  literal breaks on the next release. Every wizard's work is
  `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/…"` — hence no rules on `/flow-init`,
  `/harness-init`, `/harness-insight`, `/flow-uninstall`. `Bash(python3 *)` is not a
  narrowing; it is `Bash` with extra steps.
- **The grant dies at the user's next message.** A wizard that interviews, previews, then
  acts has already lost it. A session-wide grant belongs in `settings.json`
  `permissions.allow`, which the docs name as the intended place.

Leave the prompt alone where the prompt is the mechanism: `git commit` is the backstop
behind the tier gate, an install writes into the host's environment, `rm -rf` deletes
gate evidence.

## `argument-hint` is the autocomplete hint

Add it when the body reads `$ARGUMENTS` — `flow` and `harness-insight` do. A skill that
takes no arguments has no hint to show, and `(none)` puts that literal string in the menu.

## `disable-model-invocation: true` also hides the description

It keeps the `description` out of the model's context entirely, so on those skills the
description is read by a human scanning the `/` menu: one line, no trigger list. Use it
for setup and teardown you want to fire by hand.

## `context: fork` is not the Agent tool's `fork`

They share a word and mean opposites. The Agent tool's `subagent_type: "fork"` copies the
parent conversation and ignores a model override; this one starts a **fresh** context —

> "It won't have access to your conversation history."
> — [skills.md](https://code.claude.com/docs/en/skills.md), *Run skills in a subagent*

so it is the one that lowers what the skill costs the session that called it, and
its `model:` sets the forked subagent's model rather than the session's. The SKILL.md body
becomes the subagent's whole prompt, which is why it fits a skill that is a procedure and
returns nothing useful from one that is only guidance.

`allowed-tools` **does** reach the fork — measured, 5 of 6 forked sessions, because the docs
settle only that

> "The `agent` field determines the execution environment (model, tools, and permissions)"
> — [skills.md](https://code.claude.com/docs/en/skills.md), *Run skills in a subagent*, item 3
> of the "When this skill runs" list — not the prose under it, which says something weaker
> and is what a search for this sentence tends to return instead

and leave this open. Without it a gate skill would prompt for its own marker.

A gate skill also needs `background: false`, for three reasons that are each sufficient on
their own: the marker has to land in the turn that invoked the skill or `/flow` moves on
without it, a backgrounded fork is cut to the narrower background-subagent tool set, and a
backgrounded fork's edits sit outside the session's checkpoints where `/rewind` cannot
reach them.

The eval cost lands asymmetrically. `description_sha` reads the `description` alone, so the
invocation arm does not notice any of these fields; `outcome_sha` digests the **whole**
`SKILL.md`, so one frontmatter byte costs that skill a live re-measure. Delete its
`outcome_scores.json` entry rather than leaving it — absent is a `warn`, stale is a `fail`.

## A description states when, not what

A description that summarises its own workflow becomes the shortcut the agent takes
instead of reading the body — one that names `--reporter=json` and omits the
`PLAYWRIGHT_JSON_OUTPUT_NAME` the body requires buys an agent an ENOENT. Write triggers
and the stake of skipping; let the body hold the procedure.

## Commands in the body run as written

Assume every fenced command is executed verbatim. `find "<testDir from §3.1>"` reads as a
path, fails into an empty result, and an empty result is what authorises scaffolding — so
a placeholder in command position is worse than a wrong default, because it fails quietly.
Derive the value in the same command instead: each `bash` call is a fresh shell, so a
variable set in an earlier block is already gone.
