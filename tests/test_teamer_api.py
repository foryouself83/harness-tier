import sys
import types

import pytest

from scripts import teamer_api
from scripts.teamer_api import (
    _build_put_fields,
    append_item_content,
    build_multipart,
    merge_preserve_fields,
    parse_account_md,
    redact,
    resolve_status_no,
    username_from_id,
)


def test_append_to_existing():
    assert append_item_content("<p>old</p>", "<p>new</p>") == "<p>old</p><p>new</p>"


def test_append_when_existing_empty():
    assert append_item_content("", "<p>new</p>") == "<p>new</p>"
    assert append_item_content(None, "<p>new</p>") == "<p>new</p>"


def test_append_when_existing_whitespace():
    assert append_item_content("   \n  ", "<p>new</p>") == "<p>new</p>"


def test_redact_masks_all_secrets():
    out = redact("user=bob token=abc123", ["bob", "abc123"])
    assert out == "user=*** token=***"


def test_redact_ignores_empty_secret():
    assert redact("hello", ["", None]) == "hello"


def test_redact_no_match_returns_input():
    assert redact("nothing here", ["secret"]) == "nothing here"


def test_parse_account_md_basic():
    text = "# Teamer Account\n- id: bob@vway.co.kr\n- password: pw12345!\n"
    assert parse_account_md(text) == ("bob@vway.co.kr", "pw12345!")


def test_parse_account_md_preserves_at_and_specials():
    # id 는 verbatim(@ 보존), password 의 ':' 등 특수문자 보존
    text = "- id: handle\n- password: a:b#c!\n"
    assert parse_account_md(text) == ("handle", "a:b#c!")


def test_parse_account_md_missing_returns_none():
    assert parse_account_md("# empty\n") == (None, None)


def test_merge_preserves_non_null_cols_and_skips_null():
    item = {"col07": "2026-06-01", "col22": None, "col30": "done"}
    out = merge_preserve_fields(item)
    assert out["itemVO.col07"] == "2026-06-01"
    assert out["itemVO.col30"] == "done"
    assert "itemVO.col22" not in out


def test_merge_preserves_key_fields_and_chargers():
    item = {
        "item_title": "제목",
        "upper_item_no": 5,
        "depth": 2,
        "biz_workitem_item_charge_user": [{"user_no": 11}, {"user_no": 22}],
        "charge_user_noes": None,
    }
    out = merge_preserve_fields(item)
    assert out["itemVO.itemTitle"] == "제목"
    assert out["itemVO.upperItemNo"] == "5"
    assert out["itemVO.depth"] == "2"
    assert out["itemVO.chargeUserNoes[0]"] == "11"
    assert out["itemVO.chargeUserNoes[1]"] == "22"


def test_merge_omits_missing_optional_fields():
    out = merge_preserve_fields({"item_title": "t"})
    assert out == {"itemVO.itemTitle": "t"}


def test_resolve_status_no_match():
    actions = [
        {"to_status_no": 10, "to_status_name": "진행"},
        {"to_status_no": 20, "to_status_name": "검토"},
    ]
    assert resolve_status_no(actions, "진행") == 10
    assert resolve_status_no(actions, "검토") == 20


def test_resolve_status_no_raises_with_available():
    actions = [{"to_status_no": 10, "to_status_name": "진행"}]
    with pytest.raises(ValueError) as e:
        resolve_status_no(actions, "완료")
    assert "진행" in str(e.value)
    assert "완료" in str(e.value)
    assert "available" in str(e.value)


def test_build_multipart_structure_and_utf8():
    body = build_multipart({"itemVO.itemTitle": "제목"}, "BOUNDARY")
    assert isinstance(body, bytes)
    text = body.decode("utf-8")
    assert text.startswith("--BOUNDARY\r\n")
    assert 'Content-Disposition: form-data; name="itemVO.itemTitle"' in text
    assert "제목" in text
    assert text.endswith("--BOUNDARY--\r\n")
    # 한글이 UTF-8 바이트로 인코딩되었는지
    assert "제목".encode() in body


def test_build_multipart_multiple_fields():
    body = build_multipart({"a": "1", "b": "2"}, "B").decode("utf-8")
    assert body.count("Content-Disposition") == 2


# ---------------------------------------------------------------------------
# Task 7: keyring 레이어 + setup()
# ---------------------------------------------------------------------------


class _FakeKeyring:
    def __init__(self):
        self.store = {}

    def set_password(self, service, name, value):
        self.store[(service, name)] = value

    def get_password(self, service, name):
        return self.store.get((service, name))


def _install_fake_keyring(monkeypatch):
    fake = _FakeKeyring()
    mod = types.ModuleType("keyring")
    mod.set_password = fake.set_password
    mod.get_password = fake.get_password
    monkeypatch.setitem(sys.modules, "keyring", mod)
    return fake


def test_store_and_get_credentials(monkeypatch):
    _install_fake_keyring(monkeypatch)
    teamer_api.store_credentials("bob@x.com", "pw1")
    assert teamer_api.get_credentials() == ("bob@x.com", "pw1")


def test_get_credentials_none_when_missing(monkeypatch):
    _install_fake_keyring(monkeypatch)
    assert teamer_api.get_credentials() is None


def test_setup_migrates_and_deletes_file(monkeypatch, tmp_path):
    fake = _install_fake_keyring(monkeypatch)
    acct = tmp_path / "teamer_account.md"
    acct.write_text("- id: bob@x.com\n- password: pw1\n", encoding="utf-8")
    result = teamer_api.setup(acct)
    assert result == "migrated"
    assert fake.store[(teamer_api.SERVICE, "id")] == "bob@x.com"
    assert fake.store[(teamer_api.SERVICE, "password")] == "pw1"
    assert not acct.exists()  # 평문 파일 삭제


def test_setup_prompts_when_no_file(monkeypatch, tmp_path):
    fake = _install_fake_keyring(monkeypatch)
    monkeypatch.setattr(teamer_api, "_prompt_credentials", lambda: ("h", "p"))
    result = teamer_api.setup(tmp_path / "missing.md")
    assert result == "prompted"
    assert fake.store[(teamer_api.SERVICE, "id")] == "h"


def test_setup_raises_on_unparseable_file(monkeypatch, tmp_path):
    _install_fake_keyring(monkeypatch)
    acct = tmp_path / "teamer_account.md"
    acct.write_text("garbage with no fields\n", encoding="utf-8")
    with pytest.raises(ValueError):
        teamer_api.setup(acct)
    assert acct.exists()  # 파싱 실패 시 평문 파일 보존(사용자가 처리)


# ---------------------------------------------------------------------------
# Task 9: username_from_id
# ---------------------------------------------------------------------------


def test_username_from_id_email():
    assert username_from_id("bob@vway.co.kr") == "bob"


def test_username_from_id_plain_handle():
    assert username_from_id("handle") == "handle"


def test_build_put_fields_col_append_concats_existing():
    item = {"item_content": None, "col33": "<p>old</p>"}
    fields = _build_put_fields(
        item, "996", "188180", "1", "", {}, None, col_appends={"col33": "<p>new</p>"}
    )
    assert fields["itemVO.col33"] == "<p>old</p><p>new</p>"


def test_build_put_fields_col_append_when_existing_null():
    item = {"item_content": None, "col33": None}
    fields = _build_put_fields(
        item, "996", "188180", "1", "", {}, None, col_appends={"col33": "<p>new</p>"}
    )
    assert fields["itemVO.col33"] == "<p>new</p>"


def test_build_put_fields_col_override_still_replaces():
    item = {"item_content": None, "col33": "<p>old</p>"}
    fields = _build_put_fields(item, "996", "188180", "1", "", {"col33": "REPLACED"}, None)
    assert fields["itemVO.col33"] == "REPLACED"
