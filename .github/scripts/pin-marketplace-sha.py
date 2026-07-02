#!/usr/bin/env python3
"""marketplace.json 의 vway-kit source.sha 를 인자로 받은 커밋 SHA 로 갱신한다.

포맷/주석 보존을 위해 JSON 라운드트립(reformat) 대신 기존 sha 문자열만 치환한다.
이미 동일하거나 sha 필드가 없으면 아무것도 하지 않는다 — 실제 변경 여부는 호출측이
git diff 로 판단한다. (release.yml 이 main 릴리스 커밋에서만 호출.)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = "Developments-3/vway-kit"
MANIFEST = Path(".claude-plugin/marketplace.json")


def main() -> None:
    sha = sys.argv[1]
    txt = MANIFEST.read_text(encoding="utf-8")
    old = None
    for plugin in json.loads(txt).get("plugins", []):
        src = plugin.get("source")
        if isinstance(src, dict) and src.get("repo") == REPO:
            old = src.get("sha")
    if old and old != sha:
        # 40자 SHA 는 사실상 유일하므로 문자열 치환이 안전(포맷 보존).
        MANIFEST.write_text(txt.replace(old, sha), encoding="utf-8")


if __name__ == "__main__":
    main()
