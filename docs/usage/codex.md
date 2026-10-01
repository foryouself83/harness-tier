# Codex

**English** · [한국어](codex.ko.md) · [Usage guide](../../USAGE.md)

harness-tier's plugin hooks and commit gate install into the Codex CLI alongside Claude Code.
This page covers what a Codex host needs beyond the
[regular install](../../README.md#installation), and where its behavior differs.

## Install the plugin

```
codex plugin marketplace add foryouself83/harness-tier
codex plugin add harness-tier@harness-tier
```

Both commands are headless — no TUI needed, so this works in a script or CI. Running
`/plugins` in the Codex TUI and installing `harness-tier` from there does the same thing
interactively.

## Trust the project

Project trust gates everything under `.codex/`, including the commit gate in `.codex/hooks.json`:
an untrusted project ignores the directory entirely, with no warning. The plugin's own hooks sit
outside project trust, so an untrusted project still gets the rules at session start while its
commit gate stays off — the session reads that commits are gated, and they are not. Trust the
folder from the Codex TUI, or set `trust_level = "trusted"` for its path under `[projects]` in
`config.toml`. Trust is a separate gate from hook approval — every non-managed hook, the plugin's
own and the project's alike, still runs only after you approve it in `/hooks`, and a changed hook
needs re-approval.

## Approve the hooks in `/hooks`

A hook Codex has not approved runs as if it were absent: the risk-tiers injection at session
start, the marker invalidation on every edit, and the commit gate itself all go silent instead
of blocking anything. Open `/hooks` and approve `harness-tier`'s entries before relying on any
of them. Approval is keyed to a hook's content — its command string, event, matcher and
platform variant — and to its position in the file, so a plugin update that changes one needs
re-approval, and so does moving or reordering entries in `.codex/hooks.json`: an entry of your
own inserted ahead of the gate silences the gate until you re-approve it. An unrelated plugin
change does not.

## Enable the commit gate with `/flow-init`

`/flow-init` run inside Codex installs the gate into Codex too, without asking — on every
run, including a re-run on a host first set up from Claude Code. Run from Claude Code, the
first run asks when it finds a `.codex/` directory or you mention Codex; a later run adds
Codex only when you pick "flow-config.yaml values" from its reconfigure menu. Either way
`codex` lands in `flow-config.yaml`'s `harnesses` and the gate registers as a `Bash`
`PreToolUse` hook in the host's `.codex/hooks.json` — a separate registration from Claude's
own, in `.claude/settings.json`.
**Windows also needs Git for Windows**: the gate's Windows wrapper looks for Git's bundled
`bash.exe` next to `git.exe` or under `%ProgramFiles%\Git`, and without it **denies every
commit and merge** rather than passing them through unchecked.

The registered command finds the gate through `$(git rev-parse --show-toplevel)`, expanded by
the shell Codex runs hooks in; a shell that does not expand `$(…)` (fish before 3.4, tcsh) runs
no gate at all. A command typed into a shell session Codex keeps open (`write_stdin`) fires no
`PreToolUse`, so CI is the backstop there, as for terminal commits. Hook behaviour on Linux and
macOS is read from Codex's source, not measured; Windows is measured.

## What differs from Claude Code

- **Questions** arrive as numbered options in chat, not a structured picker, except in Plan
  mode, where `request_user_input` offers one instead.
- **A skill runs as `$name`**, not `/name` — `$flow <task>` starts the day-to-day router.
- **Teams notifications and `harness-insight` are Claude-only.** Codex has no `Notification`
  hook event to post from, and no Claude Code transcript for `harness-insight` to aggregate.
- **Project instructions render into `AGENTS.md`.** Codex never reads `CLAUDE.md` or
  `.claude/rules/` directly — only the session directory and its ancestors, and only one
  instructions file per directory. `/flow-init`, `/doc-sync` and `/harness-init` keep one
  managed block in the root `AGENTS.md`, rendered from your `CLAUDE.md`, `.claude/rules/`
  (except `.claude/rules/harness-tier/`, the plugin's own copied rules — the SessionStart hook
  injection already covers those) and each module's own `CLAUDE.md`; edit those sources, never
  the block — the next render overwrites it. The rendered file is capped at 32 KiB; past that,
  a rule's full text is replaced by an index entry pointing at the file to read.

## Remove

Run [`/flow-uninstall`](update-and-removal.md#flow-uninstall--remove-host-side-wiring) first —
it removes the Codex gate from `.codex/hooks.json` and the managed block from `AGENTS.md` in
the same run as its Claude-side cleanup, whether or not `codex` is still listed under
`harnesses`. Dropping `codex` from `harnesses` alone removes nothing — `/flow-init` then
reports what is left. Then remove the plugin itself, headlessly or from the TUI:

```
codex plugin remove harness-tier@harness-tier
codex plugin marketplace remove harness-tier
```
