# Teams notifications

**English** · [한국어](teams.ko.md) · [Usage guide](../../USAGE.md)

Posts to a Microsoft Teams channel when Claude waits for your input, when a watched branch is
pushed, or whenever you call it.

## Webhook URLs

For each channel, create a Teams **incoming webhook URL** with a Power Automate workflow — the
URL carries a `sig=` token. Start with the personal channel and add branch channels later.

| File | git | Channels |
|------|-----|----------|
| `.claude/harness-tier/config/.teams-webhooks.local.json` | gitignored | `personal`, and by default a branch channel's own URL |
| `.claude/harness-tier/config/teams-webhooks.json` | tracked | the watched branch names (a URL too, only once registered with `--shared`) |

```bash
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
# Register a channel URL — personal and branch URLs default to the local file; a branch
# registration also adds its key (with no URL) to the tracked file, so every clone watches it
python3 "${ROOT}/.claude/harness-tier/scripts/teams_alert.py" --set personal https://...
python3 "${ROOT}/.claude/harness-tier/scripts/teams_alert.py" --set dev https://...
# Commit the branch URL itself to the tracked file for the whole team
python3 "${ROOT}/.claude/harness-tier/scripts/teams_alert.py" --set dev https://... --shared
# Send a notification by hand
python3 "${ROOT}/.claude/harness-tier/scripts/teams_alert.py" --channel personal --title "..." --text "..."
```

## When each channel fires

- **`personal`** — the plugin's `Notification` hook posts whenever Claude waits for a permission
  or for input. `AskUserQuestion` fires no such event, so when a Teams channel is configured
  `/flow-init` adds a `harness-tier:teams` block to your `CLAUDE.md` that tells Claude to post by
  hand right before asking. The block is written in your `CLAUDE.md`'s language.
- **A branch channel** — the `teams-notify-push` pre-push hook posts the pushed commit's subject
  when the pushed branch's name equals a key in either `teams-webhooks.json` or the local
  webhook file. It needs `pre-commit install --hook-type pre-push`; registering a branch adds a
  watched branch for every clone, whether or not its URL was shared.

A channel with no URL is skipped in silence, except `personal`, which prints how to register one.
A failed post never blocks the hook or the push.

## Security

A Power Automate URL's `sig=` token is the credential that posts to the channel. By default it
stays in the gitignored local file, so only the branch name itself is public. Register it with
`--shared` only once you want the whole team posting as that channel — anyone who can read the
repo can then post into it too (message injection only, no data exfiltration or privilege
escalation); mark it as an exception in your secret scanner if you do.
