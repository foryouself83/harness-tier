#!/usr/bin/env python3
"""Power Automate 웹훅으로 Teams 알림을 보낸다. hook·스크립트에서 재사용한다.

채널별 웹훅 URL은 두 파일을 병합해 쓴다(local 이 tracked 를 덮어씀).
호스트 측 vway-kit 산출물은 .claude/vway-kit/ 아래 용도별로 모이고, 웹훅은
config/ 에 둔다(호스트 루트 = CLAUDE_PROJECT_DIR, 없으면 git toplevel, 그다음
이 스크립트 위치 기준):
  - .claude/vway-kit/config/teams-webhooks.json        (git 추적: 브랜치 채널, 팀 공용)
  - .claude/vway-kit/config/.teams-webhooks.local.json (git 제외: personal, 사용자별)

채널 용도:
  - personal        -> 응답 대기 / 중지 (사용자별, local 파일)
  - 그 외(브랜치명)  -> 같은 이름의 브랜치 push 시 (팀 공용, tracked 파일).
                       teams-webhooks.json 에 키를 추가하면 코드 수정 없이
                       알림 대상 브랜치를 늘릴 수 있다.

채널의 URL 이 비었거나 없으면 조용히 skip 하므로 채널을 점진적으로 켤 수 있다.
알림 실패는 호출측으로 전파하지 않는다 — 깨진 웹훅이 hook 을 막으면 안 된다.
personal 이 미설정이면 send() 가 stderr 로 등록 안내를 출력해 등록을 유도한다.

사용법 (CLI):
  python teams_alert.py --channel personal --title "..." --text "..."
  python teams_alert.py --set personal https://...   # URL만 넣으면 자동 저장

사용법 (import):
  from teams_alert import send
  send("personal", "제목", "내용")
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.request
from pathlib import Path

# 호스트 루트 폴백·config 경로는 공용 SSOT(_vway_paths)에서 가져온다(중복 정의 금지).
# teams_alert 는 COPY_FILES 로 호스트에 복사돼 직접 실행되거나(형제 import) 테스트에서
# 패키지로 import 된다 — _vway_paths 모듈 docstring 의 양립 관용구 참조.
try:
    from _vway_paths import config_dir, host_root
except ImportError:
    from scripts._vway_paths import config_dir, host_root

# _host_root 는 이전 함수명. 하위호환(테스트·외부 참조)을 위해 공용 host_root 의 alias 로
# 노출한다. 폴백 로직(env → git toplevel → .claude 마커 → cwd)은 host_root 에 통합됐다.
_host_root = host_root

# 호스트 측 vway-kit config(웹훅)는 .claude/vway-kit/config/ 에 모인다.
ROOT = host_root()
CONFIG_DIR = config_dir(ROOT)
TRACKED_FILE = CONFIG_DIR / "teams-webhooks.json"
LOCAL_FILE = CONFIG_DIR / ".teams-webhooks.local.json"
LOCAL_CHANNELS = {"personal"}  # gitignored local 파일에 저장하는 채널

# 이벤트별 내장 메시지(제목, 본문). hook command 를 ASCII 로 유지하려고 여기 둔다.
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
    """채널의 웹훅 URL 을 반환(없으면 None). local 이 tracked 를 덮어쓴다."""
    merged = {**_load(TRACKED_FILE), **_load(LOCAL_FILE)}
    return merged.get(channel, "").strip() or None


def push_channels() -> list[str]:
    """push 알림 대상 채널(=브랜치명) 목록. tracked 파일의 키에서 동적으로 읽는다.

    notify-push.sh 가 호출해 "어떤 브랜치를 push 했을 때 알릴지"를 결정한다.
    브랜치명을 코드에 하드코딩하지 않으므로, teams-webhooks.json 에 키를
    추가/삭제하는 것만으로 대상 브랜치를 바꿀 수 있다. personal 등 local
    전용 채널(LOCAL_CHANNELS)은 push 대상이 아니므로 제외한다.
    """
    return [k for k in _load(TRACKED_FILE) if k not in LOCAL_CHANNELS]


def set_webhook(channel: str, url: str) -> Path:
    """채널 URL 자동 저장: personal 은 local(git 제외), 그 외는 tracked 파일."""
    target = LOCAL_FILE if channel in LOCAL_CHANNELS else TRACKED_FILE
    target.parent.mkdir(parents=True, exist_ok=True)  # .claude/vway-kit/ 보장
    data = _load(target)
    data[channel] = url.strip()
    target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return target


def _context_label() -> str:
    """알림 출처 식별용 라벨(프로젝트명 @ git 브랜치). 세션/작업 구별에 쓴다."""
    label = ROOT.name
    try:
        out = subprocess.run(
            ["git", "-C", str(ROOT), "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=3,
        )
        branch = out.stdout.strip()
        if branch:
            label = f"{label} @ {branch}"
    except Exception:
        pass
    return label


def send(channel: str, title: str, text: str) -> bool:
    """채널 웹훅으로 알림을 POST 한다. skip/실패 시 예외 없이 False 반환."""
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
                "     python .claude/vway-kit/scripts/teams_alert.py --set personal <복사한_URL>",
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
        with urllib.request.urlopen(req, timeout=10) as resp:
            return 200 <= resp.status < 300
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="Teams 알림 전송/등록")
    parser.add_argument(
        "--set",
        nargs=2,
        metavar=("CHANNEL", "URL"),
        help="채널 웹훅 URL 등록 (올바른 파일에 자동 저장)",
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
        target = set_webhook(channel, url)
        print(f"[teams_alert] '{channel}' 등록됨 -> {target.name}")
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
    sys.exit(0)  # 알림은 절대 호출측 hook 을 실패시키지 않는다


if __name__ == "__main__":
    main()
