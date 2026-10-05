#!/usr/bin/env python3
"""Send Teams notifications via a Power Automate webhook. Reused by hooks and scripts.

Per-channel webhook URLs are read by merging two files (local overrides tracked).
Host-side harness-tier artifacts are collected by purpose under .claude/harness-tier/,
and webhooks live in config/ (host root = CLAUDE_PROJECT_DIR, else git toplevel, then
relative to this script's location):
  - .claude/harness-tier/config/teams-webhooks.json        (git-tracked: watched branches)
  - .claude/harness-tier/config/.teams-webhooks.local.json (git-excluded: personal, URLs)

Channel purposes:
  - personal        -> waiting for response / stop (per-user, local file)
  - others (branch name) -> on push of a branch with the same name. The tracked file names
                       the watched branches for every clone; the URL stays in the local
                       file unless registered with --shared, since a Power Automate URL
                       carries its `sig=` credential.

If a channel's URL is empty or missing it is silently skipped, so channels can be
enabled incrementally. Notification failures are not propagated to the caller — a
broken webhook must not block the hook. If personal is unconfigured, send() prints
registration guidance to stderr to prompt registration.

Usage (CLI):
  python teams_alert.py --channel personal --title "..." --text "..."
  python teams_alert.py --set personal https://...   # the URL alone auto-saves it
  python teams_alert.py --set dev https://... [--shared]

Usage (import):
  from teams_alert import send
  send("personal", "title", "body")
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

# The host-root fallback and config paths come from the shared SSOT (_harness_paths)
# (no duplicate definitions). teams_alert is copied to the host via COPY_FILES and run
# directly (sibling import) or imported as a package in tests — see the compatibility
# idiom in the _harness_paths module docstring.
try:
    from _harness_paths import config_dir, force_utf8_io, host_root
except ImportError:
    from scripts._harness_paths import config_dir, force_utf8_io, host_root

# _host_root is the former function name. It is exposed as an alias of the shared host_root for
# backward compatibility (tests·external references). The fallback logic
# (env → git toplevel → .claude marker → cwd) was merged into host_root.
_host_root = host_root

# Host-side harness-tier config (webhooks) is collected under .claude/harness-tier/config/.
ROOT = host_root()
CONFIG_DIR = config_dir(ROOT)
TRACKED_FILE = CONFIG_DIR / "teams-webhooks.json"
LOCAL_FILE = CONFIG_DIR / ".teams-webhooks.local.json"
LOCAL_CHANNELS = {"personal"}  # channels stored in the gitignored local file
# Seconds, per call: urlopen's applies to each socket wait, not the whole post. Sized so a post
# finishes inside the Notification hook's timeout in hooks/hooks.json, which kills it unsent.
GIT_TIMEOUT = 2
POST_TIMEOUT = 5

# Per-event built-in messages (title, body). Kept here to keep the hook command ASCII.
EVENT_MESSAGES = {
    "waiting": ("입력 대기", "Claude 가 입력 또는 권한 승인을 기다립니다."),
    "done": ("작업 완료", "Claude 가 응답을 마쳤습니다."),
}


def _load(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return {k: v for k, v in data.items() if isinstance(v, str)}


def resolve_webhook(channel: str) -> str | None:
    """Return the channel's webhook URL (None if absent). local overrides tracked."""
    merged = {**_load(TRACKED_FILE), **_load(LOCAL_FILE)}
    return merged.get(channel, "").strip() or None


def resolve_webhook_tracked(channel: str) -> str | None:
    """The URL the tracked file alone holds for `channel` (None if none)."""
    return _load(TRACKED_FILE).get(channel, "").strip() or None


def push_channels() -> list[str]:
    """List of push notification target channels (= branch names), from both files' keys.

    Called by notify-push.sh to decide "which branch push should trigger a notification".
    Local-only channels such as personal (LOCAL_CHANNELS) are not push targets.
    """
    keys = dict.fromkeys([*_load(TRACKED_FILE), *_load(LOCAL_FILE)])
    return [k for k in keys if k not in LOCAL_CHANNELS]


def _write(path: Path, data: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)  # ensure .claude/harness-tier/config/
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def set_webhook(channel: str, url: str, shared: bool = False) -> Path:
    """Save the channel URL and return the file it went to.

    A branch URL goes to the gitignored local file unless `shared`; the tracked file then gets
    the branch as a key with no URL, so every clone watches that branch and a clone holding
    the URL posts.
    """
    local = channel in LOCAL_CHANNELS or not shared
    target = LOCAL_FILE if local else TRACKED_FILE
    data = _load(target)
    data[channel] = url.strip()
    _write(target, data)
    if local and channel not in LOCAL_CHANNELS:
        tracked = _load(TRACKED_FILE)
        if channel not in tracked:
            _write(TRACKED_FILE, {**tracked, channel: ""})
    return target


def _context_label() -> str:
    """Notification-source label (project name @ git branch); distinguishes sessions/tasks."""
    label = ROOT.name
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=GIT_TIMEOUT,
        )
        branch = out.stdout.strip()
        if branch:
            label = f"{label} @ {branch}"
    except Exception:
        pass
    return label


def send(channel: str, title: str, text: str) -> bool:
    """POST a notification to the channel webhook. Returns False without raising on skip/failure."""
    url = resolve_webhook(channel)
    if not url:
        if channel == "personal":
            try:
                sys.stderr.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
            except Exception:
                pass
            print(
                "[teams_alert] personal 웹훅이 등록되지 않았습니다.\n"
                "  1) URL 만들기: Teams 채널 추가 > 우상단 볼렛 > Workflows(Power Automate) 에서\n"
                "     'send webhook` 검색 '채널에 웹후크 알림 보내기' 템플릿을 추가하고\n"
                "     생성된 HTTP POST URL 을 복사하세요.\n"
                "  2) 등록(URL만 넣으면 자동 저장됩니다):\n"
                "     python .claude/harness-tier/scripts/teams_alert.py"
                " --set personal <복사한_URL>",
                file=sys.stderr,
            )
        return False
    card = {
        "type": "message",
        "attachments": [
            {
                "contentType": "application/vnd.microsoft.card.adaptive",
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": [
                        {"type": "TextBlock", "size": "Medium", "weight": "Bolder", "text": title},
                        {"type": "TextBlock", "text": text, "wrap": True},
                        {
                            "type": "TextBlock",
                            "text": _context_label(),
                            "size": "Small",
                            "isSubtle": True,
                            "wrap": True,
                        },
                    ],
                },
            }
        ],
    }
    body = json.dumps(card).encode("utf-8")
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=POST_TIMEOUT) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def main() -> None:
    force_utf8_io()
    parser = argparse.ArgumentParser(description="Teams 알림 전송/등록")
    parser.add_argument(
        "--set",
        nargs=2,
        metavar=("CHANNEL", "URL"),
        help="채널 웹훅 URL 등록 (올바른 파일에 자동 저장)",
    )
    parser.add_argument(
        "--shared",
        action="store_true",
        help="브랜치 채널 URL을 git 추적 파일에 저장 (기본: gitignore 된 로컬 파일)",
    )
    parser.add_argument(
        "--list-push-channels",
        action="store_true",
        help="push 알림 대상 채널(브랜치) 목록 출력 — notify-push.sh 용",
    )
    parser.add_argument("--channel", help="personal | <공유 채널=브랜치명>")
    parser.add_argument("--event", choices=list(EVENT_MESSAGES), help="내장 메시지 (waiting/done)")
    parser.add_argument("--title", default="")
    parser.add_argument("--text", default="")
    args = parser.parse_args()

    if args.set:
        channel, url = args.set
        target = set_webhook(channel, url, shared=args.shared)
        print(f"[teams_alert] '{channel}' 등록됨 -> {target.name}")
        if target == LOCAL_FILE and resolve_webhook_tracked(channel):
            print(f"[teams_alert] {TRACKED_FILE.name} 에 '{channel}' URL 이 아직 남아 있습니다")
        if target == TRACKED_FILE and _load(LOCAL_FILE).get(channel, "").strip():
            # The local file wins in resolve_webhook, so this clone keeps posting to that URL.
            print(f"[teams_alert] {LOCAL_FILE.name} 의 '{channel}' URL 이 이 URL 보다 우선합니다")
        sys.exit(0)

    if args.list_push_channels:
        print(" ".join(push_channels()))
        sys.exit(0)

    if not args.channel:
        parser.error("--channel 이 필요합니다 (또는 --set CHANNEL URL)")
    if args.event:
        title, text = EVENT_MESSAGES[args.event]
        send(args.channel, title, text)
    else:
        send(args.channel, args.title, args.text)
    sys.exit(0)  # a notification must never fail the caller's hook


if __name__ == "__main__":
    main()
