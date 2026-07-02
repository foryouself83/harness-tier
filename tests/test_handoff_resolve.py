from pathlib import Path

from scripts.handoff_resolve import (
    is_ai_author,
    load_handoff_config,
    resolve_handoff,
    resolve_source_mode,
    resolve_template_path,
    resolve_write_mode,
)


def test_is_ai_author_variants():
    assert is_ai_author("AI")
    assert is_ai_author("llm")
    assert is_ai_author("Agent")
    assert not is_ai_author("bsyu")
    assert not is_ai_author("")


def test_resolve_source_mode_ai_guided():
    assert resolve_source_mode({"author": "AI", "AskUserQuestion": True}) == "ai_guided"


def test_resolve_source_mode_ai_auto():
    assert resolve_source_mode({"author": "AI", "AskUserQuestion": False}) == "ai_auto"


def test_resolve_source_mode_human_ask():
    assert resolve_source_mode({"author": "bsyu", "AskUserQuestion": True}) == "human_ask"


def test_resolve_source_mode_human_doc():
    assert resolve_source_mode({"author": "bsyu", "AskUserQuestion": False}) == "human_doc"


def test_resolve_source_mode_ask_defaults_false():
    # AskUserQuestion 미지정 → false 취급
    assert resolve_source_mode({"author": "AI"}) == "ai_auto"


def test_resolve_write_mode():
    assert resolve_write_mode("item_content") == "append"
    assert resolve_write_mode("col22") == "replace"


def test_resolve_write_mode_append_flag_overrides():
    # 불리언 플래그가 field 기반 기본을 덮어쓴다
    assert resolve_write_mode("col22", True) == "append"
    assert resolve_write_mode("item_content", False) == "replace"


def test_resolve_write_mode_falls_back_when_no_flag():
    # 플래그 미지정(None) → field 기반 폴백
    assert resolve_write_mode("item_content", None) == "append"
    assert resolve_write_mode("col22", None) == "replace"


def test_resolve_write_mode_ignores_non_bool_flag():
    # 불리언이 아닌 값(문자열 등)은 미지정 취급 → field 폴백
    assert resolve_write_mode("col22", "yes") == "replace"
    assert resolve_write_mode("item_content", "no") == "append"


def test_load_handoff_config_missing(tmp_path: Path):
    assert load_handoff_config(tmp_path / "absent.yaml") == {}


def test_load_handoff_config_reads_tree(tmp_path: Path):
    cfg = tmp_path / "vdev-config.yaml"
    cfg.write_text("handoff:\n  qa:\n    enable: true\n    field: col22\n", encoding="utf-8")
    assert load_handoff_config(cfg) == {"qa": {"enable": True, "field": "col22"}}


def test_load_handoff_config_no_handoff_key(tmp_path: Path):
    cfg = tmp_path / "vdev-config.yaml"
    cfg.write_text("branches:\n  staging: stage\n", encoding="utf-8")
    assert load_handoff_config(cfg) == {}


def _mk(p: Path, text: str = "x") -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


def test_resolve_template_path_host_overrides_plugin(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    _mk(plugin / "templates" / "handoff" / "summary.html", "P")
    _mk(host / "templates" / "handoff" / "summary.html", "H")
    assert resolve_template_path({}, "summary", plugin, host) == str(
        host / "templates" / "handoff" / "summary.html"
    )


def test_resolve_template_path_plugin_fallback(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    _mk(plugin / "templates" / "handoff" / "summary.html", "P")
    assert resolve_template_path({}, "summary", plugin, host) == str(
        plugin / "templates" / "handoff" / "summary.html"
    )


def test_resolve_template_path_implicit_kind_lookup(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    _mk(plugin / "templates" / "handoff" / "qa.html", "Q")
    assert resolve_template_path({}, "qa", plugin, host) == str(
        plugin / "templates" / "handoff" / "qa.html"
    )


def test_resolve_template_path_explicit_value(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    _mk(plugin / "templates" / "custom" / "x.html", "X")
    assert resolve_template_path({"template": "custom/x.html"}, "qa", plugin, host) == str(
        plugin / "templates" / "custom" / "x.html"
    )


def test_resolve_template_path_missing_returns_none(tmp_path: Path):
    assert resolve_template_path({}, "qa", tmp_path / "p", tmp_path / "h") is None


def test_resolve_handoff_filters_disabled(tmp_path: Path):
    cfg = tmp_path / "vdev-config.yaml"
    cfg.write_text(
        "handoff:\n"
        "  summary:\n    enable: false\n    author: AI\n    field: item_content\n"
        "  qa:\n    enable: true\n    author: AI\n"
        "    AskUserQuestion: true\n    field: col22\n"
        '    instruction: "QA 인수인계"\n',
        encoding="utf-8",
    )
    result = resolve_handoff(cfg, tmp_path / "p", tmp_path / "h")
    assert [r["kind"] for r in result] == ["qa"]
    assert result[0]["source_mode"] == "ai_guided"
    assert result[0]["write_mode"] == "replace"
    assert result[0]["template_path"] is None
    assert result[0]["instruction"] == "QA 인수인계"


def test_resolve_handoff_skips_non_dict_and_missing_enable(tmp_path: Path):
    cfg = tmp_path / "vdev-config.yaml"
    cfg.write_text(
        "handoff:\n  bad: 123\n  qa:\n    author: AI\n    field: col22\n",  # enable 없음 → skip
        encoding="utf-8",
    )
    assert resolve_handoff(cfg, tmp_path / "p", tmp_path / "h") == []


def test_resolve_source_mode_value_is_literal():
    # value 가 있으면 author/AskUserQuestion 보다 우선해 literal
    assert resolve_source_mode({"value": "완료", "author": "AI"}) == "literal"
    assert resolve_source_mode({"value": "${today}", "AskUserQuestion": True}) == "literal"


def test_resolve_source_mode_no_value_unchanged():
    # value 없으면 기존 결정 그대로(회귀)
    assert resolve_source_mode({"author": "AI"}) == "ai_auto"
    assert resolve_source_mode({"author": "bsyu", "AskUserQuestion": True}) == "human_ask"


def test_resolve_handoff_includes_value_and_append(tmp_path: Path):
    cfg = tmp_path / "vdev-config.yaml"
    cfg.write_text(
        "handoff:\n"
        "  done_date:\n    enable: true\n    field: col30\n"
        '    value: "${today}"\n    append: false\n'
        "  progress_log:\n    enable: true\n    field: col33\n    append: true\n",
        encoding="utf-8",
    )
    result = resolve_handoff(cfg, tmp_path / "p", tmp_path / "h")
    by_kind = {r["kind"]: r for r in result}
    assert by_kind["done_date"]["value"] == "${today}"
    assert by_kind["done_date"]["source_mode"] == "literal"
    assert by_kind["done_date"]["write_mode"] == "replace"
    assert by_kind["progress_log"]["value"] is None
    assert by_kind["progress_log"]["write_mode"] == "append"
    assert by_kind["progress_log"]["source_mode"] == "human_doc"
