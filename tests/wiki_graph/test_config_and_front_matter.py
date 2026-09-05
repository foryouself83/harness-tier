from pathlib import Path

from scripts import wiki_graph
from scripts.wiki_graph import (
    build_graph,
    collect_nodes,
    collect_warnings,
    load_wiki_config,
    parse_front_matter,
)
from tests.wiki_graph._helpers import _node, _write_config


def test_config_absent_is_noop(tmp_path: Path):
    assert load_wiki_config(tmp_path) is None


def test_wiki_key_absent_is_noop(tmp_path: Path):
    _write_config(tmp_path, "branches:\n  integration: dev\n")
    assert load_wiki_config(tmp_path) is None


def test_wiki_disabled_is_noop(tmp_path: Path):
    _write_config(tmp_path, "wiki:\n  enable: false\n  root: docs/\n")
    assert load_wiki_config(tmp_path) is None


def test_wiki_root_missing_dir_is_noop(tmp_path: Path):
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    assert load_wiki_config(tmp_path) is None


def test_non_canonical_root_still_matches_node_paths(tmp_path: Path):
    # Node paths are built with relative_to(root).as_posix(). Left raw, './docs/' yields the
    # index path './docs/index.md', which can never equal any node path — and orphan detection
    # then switches itself off silently across the whole repository.
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: ./docs/\n")
    cfg = load_wiki_config(tmp_path)
    assert cfg["root"] == "docs"
    assert cfg["index"] == "docs/index.md"


def test_non_canonical_index_is_normalized(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n  index: ./docs/home.md\n")
    assert load_wiki_config(tmp_path)["index"] == "docs/home.md"


def test_orphan_check_survives_a_non_canonical_root(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: ./docs/\n")
    _node(tmp_path, "docs/index.md", "wiki_id: index\ntitle: Index\n")
    _node(tmp_path, "docs/lonely.md", "wiki_id: lonely\ntitle: Lonely\n")
    wiki = load_wiki_config(tmp_path)
    nodes = collect_nodes(tmp_path, wiki)
    warns = collect_warnings(wiki, nodes, build_graph(nodes))
    assert any("orphan" in w and "lonely" in w for w in warns)
    assert not any("orphan 검사를 생략" in w for w in warns)


def test_wiki_enabled_fills_defaults(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    cfg = load_wiki_config(tmp_path)
    assert cfg["root"] == "docs"
    assert cfg["index"] == "docs/index.md"
    assert cfg["max_lines"] == 400
    assert cfg["context_lines"] == 2000
    assert cfg["defect_rule_threshold"] == 3


def test_broken_config_is_noop(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki: [this is: not: valid\n")
    assert load_wiki_config(tmp_path) is None


def test_top_level_list_preserves_fail_open(tmp_path: Path):
    """Non-mapping top level (e.g. bare list) must return None, never raise."""
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "- not a mapping\n")
    assert load_wiki_config(tmp_path) is None


def test_parse_front_matter_returns_none_without_delimiters():
    assert parse_front_matter("# 그냥 문서\n\n본문\n") is None


def test_parse_front_matter_reads_yaml():
    text = "---\nwiki_id: auth.jwt\ntitle: JWT\n---\n\n본문\n"
    assert parse_front_matter(text) == {"wiki_id": "auth.jwt", "title": "JWT"}


def test_parse_front_matter_broken_yaml_is_none():
    assert parse_front_matter("---\nwiki_id: [unclosed\n---\n\n본문\n") is None


def test_front_matter_ruler_first_line_is_not_a_block():
    # `----` is not an opening delimiter. Under find("\n---") a document starting with a
    # horizontal rule was reported as broken front matter.
    assert wiki_graph._front_matter_block("----\n제목\n----\n본문\n") is None


def test_front_matter_crlf_closing_line():
    text = "---\r\nwiki_id: a\r\ntitle: T\r\n---\r\n\r\n본문\r\n"
    assert parse_front_matter(text) == {"wiki_id": "a", "title": "T"}


def test_front_matter_closing_line_tolerates_trailing_blanks():
    text = "---\nwiki_id: a\ntitle: T\n---  \n본문\n"
    assert parse_front_matter(text) == {"wiki_id": "a", "title": "T"}


def test_front_matter_body_dashes_line_does_not_close_early():
    # A column-0 `--- note` line inside the block is not a closing delimiter. Closing early
    # pushed the wiki_id out of the block and the node disappeared without a word.
    text = "---\ntitle: T\n--- note\nwiki_id: a\n---\n본문\n"
    block = wiki_graph._front_matter_block(text)
    assert block is not None and "wiki_id: a" in block
