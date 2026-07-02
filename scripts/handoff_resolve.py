"""handoff 종류별 결정 로직 — 순수 함수. /task-sync · /task-import 가 호출해
각 종류의 (source_mode, write_mode, template_path, ...) 를 JSON 으로 받아 소비한다.

커밋 게이트가 아니므로 강제 차단과 무관하다. 결정 로직만 담고 실제 내용 생성(AI
대필, AskUserQuestion, Teamer PUT)은 호출자(커맨드/에이전트)가 한다. 파싱/입력
오류 시 빈 결과를 돌려 호출자가 기존 동작으로 떨어지게 한다.

각 함수는 인자로 받은 값만으로 결과를 반환하므로 단위 테스트가 가능하다.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# 인코딩 방어·루트 폴백·config 경로는 공용 SSOT(_vway_paths)에서 가져온다(중복 정의
# 금지). handoff_resolve 는 플러그인 위치에서 실행되므로 형제 import 가 기본이고,
# 패키지(테스트)에서는 scripts._vway_paths 로 떨어진다.
try:
    from _vway_paths import config_path as _config_path
    from _vway_paths import force_utf8_io, host_root, plugin_root
except ImportError:
    from scripts._vway_paths import config_path as _config_path
    from scripts._vway_paths import force_utf8_io, host_root, plugin_root

AI_AUTHORS = {"ai", "llm", "agent"}


def load_handoff_config(config_path: Path) -> dict:
    """vdev-config.yaml 의 handoff 트리(dict). 파일/키 없음·파싱 실패 시 {}."""
    import yaml

    if not config_path.is_file():
        return {}
    try:
        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return {}
    handoff = data.get("handoff")
    return handoff if isinstance(handoff, dict) else {}


def is_ai_author(author: str) -> bool:
    """author 가 AI 주체(ai/llm/agent, 대소문자 무시)면 True."""
    return str(author).strip().lower() in AI_AUTHORS


def resolve_source_mode(spec: dict) -> str:
    """종류 spec → source_mode. value 최우선(literal), 다음 AskUserQuestion 토글·author."""
    if spec.get("value") is not None:
        return "literal"
    ai = is_ai_author(spec.get("author", ""))
    ask = spec.get("AskUserQuestion") is True
    if ai:
        return "ai_guided" if ask else "ai_auto"
    return "human_ask" if ask else "human_doc"


def resolve_write_mode(field: str, append: object = None) -> str:
    """append 가 불리언이면 우선(True→append, False→replace).
    아니면 field 기반 폴백(item_content → append, 그 외 colXX → replace)."""
    if isinstance(append, bool):
        return "append" if append else "replace"
    return "append" if field == "item_content" else "replace"


def resolve_template_path(spec: dict, kind: str, plugin: Path, host: Path) -> str | None:
    """template 파일 해석. rel = spec.template 또는 handoff/<kind>.html.
    templates/<rel> 을 host 우선·plugin fallback 으로 탐색. 없으면 None."""
    rel = spec.get("template") or f"handoff/{kind}.html"
    for root in (host, plugin):
        cand = root / "templates" / rel
        if cand.is_file():
            return str(cand)
    return None


def resolve_handoff(config_path: Path, plugin: Path, host: Path) -> list[dict]:
    """enable:true 종류만 결정 결과 리스트로. 입력 이상은 건너뛴다."""
    handoff = load_handoff_config(config_path)
    result: list[dict] = []
    for kind, spec in handoff.items():
        if not isinstance(spec, dict) or spec.get("enable") is not True:
            continue
        field = str(spec.get("field", ""))
        result.append(
            {
                "kind": kind,
                "author": spec.get("author", ""),
                "field": field,
                "value": spec.get("value"),
                "source_mode": resolve_source_mode(spec),
                "write_mode": resolve_write_mode(field, spec.get("append")),
                "template_path": resolve_template_path(spec, kind, plugin, host),
                "instruction": spec.get("instruction", ""),
            }
        )
    return result


def main() -> None:
    force_utf8_io()
    config = Path(sys.argv[1]) if len(sys.argv) > 1 else _config_path(host_root())
    result = resolve_handoff(config, plugin_root(), host_root())
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
