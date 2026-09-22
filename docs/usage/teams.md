# Teams notifications

**English** · [한국어](teams.ko.md) · [Usage guide](../../USAGE.md)

Posts to a Microsoft Teams channel when Claude waits for your input, when a watched branch is
pushed, or whenever you call it.

## Webhook URLs

For each channel, create a Teams **incoming webhook URL** with a Power Automate workflow — the
URL carries a `sig=` token. Start with the personal channel and add branch channels later.

| File | git | Channels |
|------|-----|----------|
| `.claude/harness-tier/config/.teams-webhooks.local.json` | gitignored | `personal` — yours alone |
| `.claude/harness-tier/config/teams-webhooks.json` | tracked | one key per branch name, shared by the team |

```bash
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
# Register a channel URL — personal goes to the local file, any other name to the tracked one
python3 "${ROOT}/.claude/harness-tier/scripts/teams_alert.py" --set personal https://...
# Send a notification by hand
python3 "${ROOT}/.claude/harness-tier/scripts/teams_alert.py" --channel personal --title "..." --text "..."
```

## When each channel fires

- **`personal`** — the plugin's `Notification` hook posts whenever Claude waits for a permission
  or for input. `AskUserQuestion` fires no such event, so when a Teams channel is configured
  `/flow-init` adds a `harness-tier:teams` block to your `CLAUDE.md` that tells Claude to post by
  hand right before asking. The block is written in your `CLAUDE.md`'s language.
- **A branch channel** — the `teams-notify-push` pre-push hook posts the pushed commit's subject
  when the pushed branch's name equals a key in `teams-webhooks.json`. It needs
  `pre-commit install --hook-type pre-push`; adding a key adds a watched branch.

A channel with no URL is skipped in silence, except `personal`, which prints how to register one.
A failed post never blocks the hook or the push.

## Security

A tracked Power Automate URL is an incoming webhook: the worst case is a message injected into
that channel, with no data exfiltration or privilege escalation. Mark it as an exception in your
secret scanner.
