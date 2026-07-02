"""Teamer.live API 클라이언트 — 자격증명을 keyring 에서 읽어 인증·검색·업데이트를
프로세스 내부에서 수행하고 최소 JSON 만 출력한다. 비밀(id/pw/token)은 stdout/stderr/
로그/모델 컨텍스트에 절대 노출하지 않는다(에러도 redact). 로컬 데스크톱 전용.

순수 로직(redact·파싱·필드보존·append·multipart·status 해석)은 테스트 가능한 함수로
분리하고, keyring·HTTP 는 함수 내부 lazy import 레이어로 격리한다.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# _vway_paths: sibling(플러그인 실행) → scripts.(테스트) fallback
try:
    from _vway_paths import force_utf8_io
except ImportError:
    from scripts._vway_paths import force_utf8_io

BASE = "https://teamer.live"

# PUT 정적 필드(에이전트 사양에서 이관 — 회사/타임존/언어 등 고정값)
_STATIC_PUT_FIELDS = {
    "itemVO.companyNo": "11",
    "itemVO.webUrl": "https://teamer.live/#",
    "itemVO.hasFiles": "false",
    "itemVO.position": "after",
    "itemVO.language": "ko",
    "itemVO.updateType": "put",
    "itemVO.userTimezone": "Asia/Seoul",
}


def redact(text: str, secrets: list[str]) -> str:
    """text 안의 각 secret 부분문자열을 '***' 로 치환. 빈/None secret 은 무시."""
    out = str(text)
    for s in secrets:
        if s:
            out = out.replace(str(s), "***")
    return out


def parse_account_md(text: str) -> tuple[str | None, str | None]:
    """'- id: X' / '- password: Y' 라인에서 (id, password) 추출.
    id 는 verbatim(@ 보존). 첫 ':' 뒤 전체를 값으로(password 의 ':' 보존)."""
    cid = cpw = None
    for line in text.splitlines():
        m = re.match(r"\s*-?\s*(id|password)\s*:\s*(.+?)\s*$", line, re.IGNORECASE)
        if not m:
            continue
        key, val = m.group(1).lower(), m.group(2)
        if key == "id":
            cid = val
        else:
            cpw = val
    return cid, cpw


def append_item_content(existing: str | None, new: str) -> str:
    """기존 item_content 뒤에 new 를 append. 기존이 null/공백이면 new 만 반환."""
    if not existing or not existing.strip():
        return new
    return existing + new


def merge_preserve_fields(item: dict) -> dict[str, str]:
    """GET 항목 → itemVO.* base 필드. non-null colXX·key 필드·charge 유저 보존.
    item_content/status/override 는 제외(호출자 처리). 누락 필드는 omit(=null 처리)."""
    fields: dict[str, str] = {}
    for key, val in item.items():
        if key.startswith("col") and key[3:].isdigit() and val is not None:
            fields[f"itemVO.{key}"] = str(val)
    for src, dst in (
        ("item_title", "itemVO.itemTitle"),
        ("upper_item_no", "itemVO.upperItemNo"),
        ("depth", "itemVO.depth"),
    ):
        if item.get(src) is not None:
            fields[dst] = str(item[src])
    for i, user in enumerate(item.get("biz_workitem_item_charge_user") or []):
        uno = user.get("user_no") if isinstance(user, dict) else None
        if uno is not None:
            fields[f"itemVO.chargeUserNoes[{i}]"] = str(uno)
    return fields


def username_from_id(account_id: str) -> str:
    """Teamer id 의 로컬파트(@ 앞부분)를 username 으로. @ 없으면 전체를 그대로."""
    return account_id.split("@", 1)[0]


def resolve_status_no(actions: list[dict], target_name: str) -> int:
    """to_status_name == target_name 인 to_status_no 반환. 미매치면 ValueError."""
    for action in actions:
        if action.get("to_status_name") == target_name:
            return action["to_status_no"]
    available = [a.get("to_status_name") for a in actions]
    raise ValueError(f"status '{target_name}' not found; available: {available}")


def build_multipart(fields: dict, boundary: str) -> bytes:
    """필드맵 → multipart/form-data UTF-8 바이트(CRLF 구분). curl 대신 사용해
    Windows 비ASCII 깨짐을 피한다(명시 UTF-8 인코딩)."""
    lines: list[str] = []
    for key, val in fields.items():
        lines.append(f"--{boundary}")
        lines.append(f'Content-Disposition: form-data; name="{key}"')
        lines.append("")
        lines.append(str(val))
    lines.append(f"--{boundary}--")
    lines.append("")
    return "\r\n".join(lines).encode("utf-8")


# ---------------------------------------------------------------------------
# Task 7: keyring 자격증명 레이어 + setup() 마이그레이션
# ---------------------------------------------------------------------------

SERVICE = "vway-kit-teamer"


def get_credentials() -> tuple[str, str] | None:
    """keyring 에서 (id, password). 하나라도 없으면 None."""
    import keyring  # lazy: 순수 함수 테스트가 keyring 비의존이 되도록

    cid = keyring.get_password(SERVICE, "id")
    cpw = keyring.get_password(SERVICE, "password")
    if not cid or not cpw:
        return None
    return cid, cpw


def store_credentials(cid: str, cpw: str) -> None:
    """keyring 에 id/password 저장."""
    import keyring

    keyring.set_password(SERVICE, "id", cid)
    keyring.set_password(SERVICE, "password", cpw)


def _prompt_credentials() -> tuple[str, str]:
    """터미널에서 id/비번 입력(getpass). 비번은 화면에 표시되지 않는다."""
    import getpass

    cid = input("Teamer id (verbatim, @ 포함 가능): ").strip()
    cpw = getpass.getpass("Teamer password: ")
    return cid, cpw


def setup(account_path: Path) -> str:
    """account_path(평문) 있으면 이전(파싱→keyring 저장→파일삭제), 없으면 getpass 입력.
    비밀은 출력하지 않는다. 파일이 있으나 파싱 실패 시 ValueError."""
    if account_path.is_file():
        cid, cpw = parse_account_md(account_path.read_text(encoding="utf-8"))
        if not cid or not cpw:
            raise ValueError(
                f"{account_path} 가 존재하지만 id/password 를 파싱할 수 없습니다 — "
                "파일을 고치거나 삭제한 뒤 다시 실행하세요."
            )
        store_credentials(cid, cpw)
        account_path.unlink()
        return "migrated"
    cid, cpw = _prompt_credentials()
    store_credentials(cid, cpw)
    return "prompted"


def _secrets_for_redaction() -> list[str]:
    creds = get_credentials()
    return list(creds) if creds else []


def _post_json(url: str, payload: dict, token: str | None = None) -> dict:
    import urllib.request

    data = json.dumps(payload).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _get_json(url: str, token: str) -> dict | list:
    import urllib.request

    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"}, method="GET")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def authenticate(cid: str, cpw: str) -> str:
    """POST /api/auth/local → Bearer token. 실패 시 RuntimeError(비밀 미포함)."""
    resp = _post_json(f"{BASE}/api/auth/local", {"username": cid, "password": cpw})
    token = resp.get("token") if isinstance(resp, dict) else None
    if not token:
        raise RuntimeError("authentication failed")
    return token


def search_items(token, project_no, workitem_no, text) -> list[dict]:
    import urllib.parse

    qs = urllib.parse.urlencode(
        {
            "project_no": project_no,
            "workitem_no": workitem_no,
            "page": 0,
            "size": 50,
            "view_type": "list",
            "text": text,
        }
    )
    resp = _post_json(f"{BASE}/api/new/items/getItemList?{qs}", {}, token)
    return resp.get("content", []) if isinstance(resp, dict) else []


def _minimal_item(item: dict) -> dict:
    return {
        "item_no": item.get("item_no"),
        "item_id": item.get("item_id"),
        "item_title": item.get("item_title"),
        "item_content": item.get("item_content"),
        "status_name": item.get("item_workflow_status_no_name"),
    }


def _build_put_fields(
    item, project_no, workitem_no, item_no, new_content, col_overrides, status_no, col_appends=None
):
    """GET 보존 필드 + itemContent(append) + overrides(replace) + appends(누적) + status + 정적."""
    fields = merge_preserve_fields(item)
    fields.update(_STATIC_PUT_FIELDS)
    fields["itemVO.itemNo"] = str(item_no)
    fields["itemVO.projectNo"] = str(project_no)
    fields["itemVO.workitemNo"] = str(workitem_no)
    fields["itemVO.itemContent"] = append_item_content(item.get("item_content"), new_content)
    for col, val in (col_overrides or {}).items():
        fields[f"itemVO.{col}"] = val
    for col, val in (col_appends or {}).items():
        fields[f"itemVO.{col}"] = append_item_content(item.get(col), val)
    if status_no is not None:
        fields["itemVO.itemWorkflowStatusNo"] = str(status_no)
    elif item.get("item_workflow_status_no") is not None:
        fields["itemVO.itemWorkflowStatusNo"] = str(item["item_workflow_status_no"])
    return fields


def put_item(token, item_no, fields) -> dict:
    import urllib.request

    boundary = "----vwayTeamerBoundary7a6e47d"
    body = build_multipart(fields, boundary)
    headers = {
        "Authorization": f"Bearer {token}",
        "Cookie": f"Admin-Token={token}; language=ko",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }
    req = urllib.request.Request(
        f"{BASE}/api/new/items/{item_no}", data=body, headers=headers, method="PUT"
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _require_credentials() -> tuple[str, str]:
    """keyring 자격증명 반환. 없으면 안내 후 비차단 종료(exit 0)."""
    creds = get_credentials()
    if creds is None:
        print(
            "Teamer 자격증명이 설정되지 않았습니다. 터미널에서 실행하세요:\n"
            f'  python "{__file__}" setup'
        )
        sys.exit(0)
    return creds


def _read_file(path: str) -> str:
    with open(path, encoding="utf-8") as fh:
        return fh.read()


def _parse_col_overrides(pairs: list[str]) -> dict:
    """['col22=path', ...] → {'col22': <file 내용>}. 'itemVO.' 접두는 제거."""
    out = {}
    for pair in pairs or []:
        col, _, fpath = pair.partition("=")
        if col.startswith("itemVO."):
            col = col[len("itemVO.") :]
        out[col] = _read_file(fpath)
    return out


def main() -> None:
    import argparse

    force_utf8_io()
    parser = argparse.ArgumentParser(prog="teamer_api")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup")
    sub.add_parser("whoami")

    ps = sub.add_parser("search")
    ps.add_argument("--project-no", required=True)
    ps.add_argument("--workitem-no", required=True)
    ps.add_argument("--text", required=True)

    pu = sub.add_parser("update")
    pu.add_argument("--project-no", required=True)
    pu.add_argument("--workitem-no", required=True)
    pu.add_argument("--item-no", required=True)
    pu.add_argument("--searchtext", required=True)
    pu.add_argument("--content-file", required=True)
    pu.add_argument("--col-override", action="append", default=[])
    pu.add_argument("--col-append", action="append", default=[])
    pu.add_argument("--target-status-name")
    pu.add_argument("--workflow-no")

    args = parser.parse_args()

    try:
        if args.cmd == "setup":
            from pathlib import Path as _P

            try:
                from _vway_paths import config_path, host_root
            except ImportError:
                from scripts._vway_paths import config_path, host_root
            acct = _P(config_path(host_root())).parent / "teamer_account.md"
            result = setup(acct)
            print(json.dumps({"setup": result}, ensure_ascii=False))
            return

        if args.cmd == "whoami":
            cid, _ = _require_credentials()
            print(json.dumps({"username": username_from_id(cid)}, ensure_ascii=False))
            return

        cid, cpw = _require_credentials()
        token = authenticate(cid, cpw)

        if args.cmd == "search":
            items = search_items(token, args.project_no, args.workitem_no, args.text)
            print(json.dumps([_minimal_item(i) for i in items], ensure_ascii=False, indent=2))
            return

        if args.cmd == "update":
            if args.target_status_name and not args.workflow_no:
                raise ValueError("--workflow-no is required when --target-status-name is set")
            items = search_items(token, args.project_no, args.workitem_no, args.searchtext)
            match = next((i for i in items if str(i.get("item_no")) == str(args.item_no)), None)
            if match is None:
                raise RuntimeError(f"item_no {args.item_no} not found")
            status_no = None
            if args.target_status_name:
                raw_actions = _get_json(
                    f"{BASE}/api/workflowAction?workflow_no={args.workflow_no}"
                    f"&project_no={args.project_no}&workitem_no={args.workitem_no}",
                    token,
                )
                actions = raw_actions if isinstance(raw_actions, list) else []
                status_no = resolve_status_no(actions, args.target_status_name)
            fields = _build_put_fields(
                match,
                args.project_no,
                args.workitem_no,
                args.item_no,
                _read_file(args.content_file),
                _parse_col_overrides(args.col_override),
                status_no,
                col_appends=_parse_col_overrides(args.col_append),
            )
            resp = put_item(token, args.item_no, fields)
            print(
                json.dumps(
                    {
                        "item_id": resp.get("item_id"),
                        "item_title": resp.get("item_title"),
                        "item_workflow_status_no": resp.get("item_workflow_status_no"),
                        "mode": resp.get("mode"),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
            return
    except Exception as exc:  # noqa: BLE001 — 비밀 누출 방지 위해 메시지 redact 후 비차단 보고
        try:
            secrets = _secrets_for_redaction()
        except Exception:  # noqa: BLE001 — redaction 준비 실패 시 빈 목록으로 안전 처리
            secrets = []
        print(redact(str(exc), secrets), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
