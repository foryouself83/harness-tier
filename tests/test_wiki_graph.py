import json
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import wiki_graph
from scripts.wiki_graph import (
    DERIVED_EDGES,
    EDGE_KEYS,
    MANUAL_EDGES,
    PROBLEM_CAP,
    _safe_int,
    build_graph,
    cmd_build,
    cmd_neighbors,
    cmd_stale,
    cmd_verify,
    collect_nodes,
    collect_warnings,
    dump_graph,
    graph_path,
    load_wiki_config,
    neighbors,
    parse_front_matter,
    undirected_adjacency,
    validate_defects,
    validate_stamps,
    validate_structure,
)


def _write_config(root: Path, body: str) -> None:
    cfg = root / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "flow-config.yaml").write_text(body, encoding="utf-8")


def _node(root: Path, rel: str, front: str, body: str = "본문\n") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{front}---\n\n{body}", encoding="utf-8")
    return p


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


def test_duplicate_wiki_id_lines_warn(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/index.md", "wiki_id: index\ntitle: Index\n")
    _node(tmp_path, "docs/a.md", "wiki_id: old\nwiki_id: a\ntitle: A\n")
    wiki = load_wiki_config(tmp_path)
    nodes = collect_nodes(tmp_path, wiki)
    warns = collect_warnings(wiki, nodes, build_graph(nodes))
    assert any("wiki_id" in w and "여러 개" in w for w in warns)


def test_collect_nodes_skips_files_without_front_matter(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/index.md", "wiki_id: index\ntitle: Index\n")
    (tmp_path / "docs" / "README.md").write_text("# 랜딩\n", encoding="utf-8")
    nodes = collect_nodes(tmp_path, load_wiki_config(tmp_path))
    assert [n["id"] for n in nodes] == ["index"]


def test_collect_nodes_records_path_and_line_count(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/auth/jwt.md", "wiki_id: auth.jwt\ntitle: JWT\n", "가\n나\n다\n")
    (node,) = collect_nodes(tmp_path, load_wiki_config(tmp_path))
    assert node["path"] == "docs/auth/jwt.md"
    assert node["line_count"] == 8  # --- id title --- blank line, then three body lines
    assert node["front"]["title"] == "JWT"


def test_collect_nodes_strips_utf8_bom(tmp_path: Path):
    # A BOM (﻿) left by a Windows editor in front of "---" survives plain utf-8 decoding and
    # breaks parse_front_matter's startswith check silently — the node drops out of the graph
    # with no warning (Invariant #2; reproduces on Windows only, and errs permissive).
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/index.md", "wiki_id: index\ntitle: Index\n")
    bommed = tmp_path / "docs" / "auth.md"
    fm = "---\nwiki_id: auth.jwt\ntitle: JWT\n---\n\n본문\n"
    bommed.write_bytes(b"\xef\xbb\xbf" + fm.encode())
    nodes = collect_nodes(tmp_path, load_wiki_config(tmp_path))
    assert sorted(n["id"] for n in nodes) == ["auth.jwt", "index"]


def test_collect_nodes_keeps_document_missing_marker(tmp_path: Path):
    # A missing id is not filtered here: it is not a node, but it has to reach the caller to
    # be surfaced as a warning.
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/broken.md", "title: 제목만\n")
    (node,) = collect_nodes(tmp_path, load_wiki_config(tmp_path))
    assert node["id"] is None


def test_collect_nodes_broken_document_shape(tmp_path: Path):
    # Every downstream consumer relies on `front` being a dict rather than None (a broken
    # node still flows through `node["front"].get(...)` calls), and on `broken` /
    # `marker_seen` being present at all — pin the exact shape collect_nodes produces for a
    # document whose front matter opens and closes but fails to parse as YAML.
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/broken.md", "title: New: Doc\n")
    (node,) = collect_nodes(tmp_path, load_wiki_config(tmp_path))
    assert node["id"] is None
    assert node["front"] == {}
    assert isinstance(node["broken"], str) and node["broken"]
    assert isinstance(node["marker_seen"], bool)


def test_used_by_is_derived_from_depends_on():
    nodes = [
        {
            "id": "auth.jwt",
            "path": "docs/a.md",
            "line_count": 3,
            "front": {"wiki_id": "auth.jwt", "title": "JWT", "depends_on": ["auth.user"]},
        },
        {
            "id": "auth.user",
            "path": "docs/b.md",
            "line_count": 3,
            "front": {"wiki_id": "auth.user", "title": "User"},
        },
    ]
    graph = build_graph(nodes)
    assert graph["edges"]["depends_on"] == {"auth.jwt": ["auth.user"]}
    assert graph["edges"]["used_by"] == {"auth.user": ["auth.jwt"]}


def test_defects_is_derived_from_affects():
    nodes = [
        {
            "id": "defect.skew",
            "path": "docs/defects/skew.md",
            "line_count": 3,
            "front": {"wiki_id": "defect.skew", "title": "skew", "affects": ["auth.jwt"]},
        },
        {
            "id": "auth.jwt",
            "path": "docs/a.md",
            "line_count": 3,
            "front": {"wiki_id": "auth.jwt", "title": "JWT"},
        },
    ]
    graph = build_graph(nodes)
    assert graph["edges"]["affects"] == {"defect.skew": ["auth.jwt"]}
    assert graph["edges"]["defects"] == {"auth.jwt": ["defect.skew"]}


def test_node_sources_are_paths_only():
    # Front matter holds a path->sha map, the graph a path list. A sync that changed only the
    # sha must not read as graph drift.
    nodes = [
        {
            "id": "auth.jwt",
            "path": "docs/a.md",
            "line_count": 3,
            "front": {
                "wiki_id": "auth.jwt",
                "title": "JWT",
                "sources": {"src/b.py": "9f3ac21", "src/a.py": None},
            },
        },
    ]
    graph = build_graph(nodes)
    assert graph["nodes"]["auth.jwt"]["sources"] == ["src/a.py", "src/b.py"]


def test_empty_fields_are_omitted_from_nodes():
    nodes = [
        {
            "id": "auth.jwt",
            "path": "docs/a.md",
            "line_count": 3,
            "front": {"wiki_id": "auth.jwt", "title": "JWT", "tags": []},
        },
    ]
    assert "tags" not in build_graph(nodes)["nodes"]["auth.jwt"]


def test_dump_is_deterministic_regardless_of_input_order():
    a = {
        "id": "b.x",
        "path": "docs/b.md",
        "line_count": 3,
        "front": {"wiki_id": "b.x", "title": "B", "related": ["a.x"]},
    }
    b = {
        "id": "a.x",
        "path": "docs/a.md",
        "line_count": 3,
        "front": {"wiki_id": "a.x", "title": "A", "related": ["b.x"]},
    }
    assert dump_graph(build_graph([a, b])) == dump_graph(build_graph([b, a]))


def test_dump_carries_the_do_not_edit_header():
    text = dump_graph(build_graph([]))
    assert text.startswith("# GENERATED by wiki_graph.py --build. Do not edit by hand.\n")


def _mk(nid, front=None, path="docs/a.md"):
    front = {"wiki_id": nid, "title": "T", **(front or {})}
    return {"id": nid, "path": path, "line_count": 3, "front": front}


def _check(tmp_path: Path, nodes):
    wiki = {
        "root": "docs/",
        "index": "docs/index.md",
        "max_lines": 400,
        "context_lines": 2000,
        "defect_rule_threshold": 3,
    }
    return validate_structure(tmp_path, wiki, nodes, build_graph(nodes))


def _wiki(**over):
    base = {
        "root": "docs/",
        "index": "docs/index.md",
        "max_lines": 400,
        "context_lines": 2000,
        "defect_rule_threshold": 3,
    }
    base.update(over)
    return base


def test_duplicate_id_blocks(tmp_path: Path):
    # The field an author would grep for is `wiki_id` (Task 1); the message must name that
    # field, not the internal `id` key, or the grep for the fault comes up empty.
    problems = _check(tmp_path, [_mk("a.x", path="docs/a.md"), _mk("a.x", path="docs/b.md")])
    assert any("wiki_id" in p and "중복" in p and "a.x" in p for p in problems)


def test_bad_wiki_id_format_blocks(tmp_path: Path):
    # Using the dedicated key states the intent to be a node, so nothing is ambiguous any
    # more and blocking is the right answer.
    assert any("형식" in p and "wiki_id" in p for p in _check(tmp_path, [_mk("Auth.JWT")]))


def test_foreign_id_front_matter_is_not_a_node_and_never_blocks(tmp_path: Path):
    # Docusaurus's `id:` is a documented first-class front matter field, and both the wiki.root
    # default and Docusaurus's default doc path are docs/. Reading it as a node makes every
    # commit in the repository fail on a format violation forever — the wiki gate runs on the
    # docs tier too.
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/getting-started.md", "id: Getting_Started\nsidebar_position: 1\n")
    nodes = collect_nodes(tmp_path, load_wiki_config(tmp_path))
    assert [n["id"] for n in nodes] == [None]
    assert _check(tmp_path, nodes) == []


def test_non_string_wiki_id_blocks(tmp_path: Path):
    # YAML 1.1 bites even the dedicated key: `wiki_id: 0123456` is octal, so it arrives as the
    # integer 42798, whose string form "42798" passes WIKI_ID_RE — a valid-looking id nobody
    # ever typed.
    node = {
        "id": "42798",
        "path": "docs/a.md",
        "line_count": 3,
        "front": {"wiki_id": 42798, "title": "T"},
    }
    assert any("wiki_id" in p and "문자열" in p for p in _check(tmp_path, [node]))


def test_front_matter_without_id_warns_capped(tmp_path: Path):
    # "related" is in WIKI_ONLY_FIELDS, so the intent to be a node is on record — which is what
    # earns the warning.
    nodes = [
        {"id": None, "path": f"docs/f{i}.md", "line_count": 3, "front": {"related": ["x"]}}
        for i in range(5)
    ]
    warns = collect_warnings({"index": "docs/index.md"}, nodes, build_graph(nodes))
    assert sum(1 for w in warns if "wiki_id 가 없어" in w) == 3  # only three are listed
    assert any("외 2건" in w for w in warns)  # the rest arrive as a count


def test_missing_marker_warns_only_when_wiki_fields_are_present(tmp_path: Path):
    # Once the key is dedicated, "has front matter but is not a node" is the normal state.
    # Warning on all of them turns into permanent per-commit noise in a Docusaurus repository.
    # A hand-written `related` is the only evidence that a node was intended.
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/theirs.md", "id: Getting_Started\nsidebar_position: 1\ntags: [x]\n")
    _node(tmp_path, "docs/meant-it.md", "title: Auth\nrelated: [index]\n")
    wiki = load_wiki_config(tmp_path)
    nodes = collect_nodes(tmp_path, wiki)
    warns = collect_warnings(wiki, nodes, build_graph(nodes), tmp_path)
    assert any("docs/meant-it.md" in w and "wiki_id" in w for w in warns)
    assert not any("docs/theirs.md" in w for w in warns)


def test_size_warning_skips_files_that_are_not_nodes(tmp_path: Path):
    nodes = [{"id": None, "path": "docs/big.md", "line_count": 999, "front": {"slug": "/x"}}]
    warns = collect_warnings({"index": "docs/index.md", "max_lines": 10}, nodes, build_graph(nodes))
    assert not any("max_lines" in w for w in warns)


def test_missing_title_blocks(tmp_path: Path):
    node = {"id": "a.x", "path": "docs/a.md", "line_count": 3, "front": {"wiki_id": "a.x"}}
    assert any("title" in p for p in _check(tmp_path, [node]))


def test_dangling_reference_blocks(tmp_path: Path):
    problems = _check(tmp_path, [_mk("a.x", {"depends_on": ["nope.x"]})])
    assert any("nope.x" in p for p in problems)


def test_depends_on_cycle_blocks(tmp_path: Path):
    nodes = [
        _mk("a.x", {"depends_on": ["b.x"]}, "docs/a.md"),
        _mk("b.x", {"depends_on": ["c.x"]}, "docs/b.md"),
        _mk("c.x", {"depends_on": ["a.x"]}, "docs/c.md"),
    ]
    assert any("순환" in p for p in _check(tmp_path, nodes))


def test_related_cycle_is_fine(tmp_path: Path):
    # `related` is bidirectional and hand-written, so mutual references are the normal shape.
    # It is not what the cycle check looks at.
    nodes = [
        _mk("a.x", {"related": ["b.x"]}, "docs/a.md"),
        _mk("b.x", {"related": ["a.x"]}, "docs/b.md"),
    ]
    assert _check(tmp_path, nodes) == []


def test_manual_used_by_blocks(tmp_path: Path):
    assert any("used_by" in p for p in _check(tmp_path, [_mk("a.x", {"used_by": ["b.x"]})]))


def test_manual_defects_blocks(tmp_path: Path):
    assert any("defects" in p for p in _check(tmp_path, [_mk("a.x", {"defects": ["d.x"]})]))


def test_missing_source_path_warns_but_does_not_block(tmp_path: Path):
    # A doc legitimately documents a generated or gitignored file (a built API client), or one
    # that exists only on another branch. Blocking froze every commit — including code-only
    # ones — with nothing --build could do about it. --stale carries the same fact to doc-sync.

    (tmp_path / "docs").mkdir()
    nodes = [_mk("a.x", {"sources": {"src/gone.py": "abc1234"}})]
    assert _check(tmp_path, nodes) == []
    warns = collect_warnings(
        {"root": "docs", "index": "docs/index.md"}, nodes, build_graph(nodes), tmp_path
    )
    assert any("src/gone.py" in w for w in warns)


def test_missing_source_path_warning_is_capped(tmp_path: Path):
    (tmp_path / "docs").mkdir()
    nodes = [_mk("a.x", {"sources": {f"src/gone{i}.py": None for i in range(6)}})]
    warns = collect_warnings(
        {"root": "docs", "index": "docs/index.md"}, nodes, build_graph(nodes), tmp_path
    )
    assert sum(1 for w in warns if "가 없습니다" in w and "src/gone" in w) == 3
    assert any("외 3건" in w for w in warns)


def test_existing_source_path_passes(tmp_path: Path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "here.py").write_text("x = 1\n", encoding="utf-8")
    assert _check(tmp_path, [_mk("a.x", {"sources": {"src/here.py": "abc1234"}})]) == []


def test_source_list_form_blocks(tmp_path: Path):
    # The design (§2) rejects this shape explicitly: sources must be a map. Hand-writing it as
    # a list is the most plausible mistake, so the shape itself is blocked, independently of
    # the missing-path check.
    problems = _check(tmp_path, [_mk("a.x", {"sources": ["src/nope.py"]})])
    assert any("map" in p for p in problems)


def test_source_scalar_form_blocks(tmp_path: Path):
    problems = _check(tmp_path, [_mk("a.x", {"sources": "src/nope.py"})])
    assert any("map" in p for p in problems)


def test_non_string_source_key_does_not_raise(tmp_path: Path):
    # YAML with a numeric key like `sources: { 42: abc1234 }` parses to {42: 'abc1234'}.
    # Must not raise TypeError anywhere it is consumed.

    (tmp_path / "docs").mkdir()
    node = {
        "id": "a.x",
        "path": "docs/a.md",
        "line_count": 3,
        "front": {"wiki_id": "a.x", "title": "T", "sources": {42: "abc1234"}},
    }
    assert _check(tmp_path, [node]) == []
    warns = collect_warnings(
        {"root": "docs", "index": "docs/index.md"}, [node], build_graph([node]), tmp_path
    )
    assert any("docs/a.md" in w and "42" in w for w in warns)


def test_dangling_reference_includes_source_file(tmp_path: Path):
    problems = _check(
        tmp_path,
        [_mk("a.x", {"depends_on": ["nope.x"]}, "docs/a.md")],
    )
    assert any("docs/a.md" in p and "nope.x" in p for p in problems)


def test_dangling_edge_names_both_sides(tmp_path: Path):
    # Naming only the referrer sent the author to inspect an index.md that was fine.
    problems = _check(tmp_path, [_mk("index", {"related": ["ghost"]}, path="docs/index.md")])
    (msg,) = [p for p in problems if "ghost" in p]
    assert "docs/index.md" in msg
    assert "wiki_id" in msg


def test_cycle_includes_all_file_paths(tmp_path: Path):
    nodes = [
        _mk("a.x", {"depends_on": ["b.x"]}, "docs/a.md"),
        _mk("b.x", {"depends_on": ["c.x"]}, "docs/b.md"),
        _mk("c.x", {"depends_on": ["a.x"]}, "docs/c.md"),
    ]
    problems = _check(tmp_path, nodes)
    cycle_msg = [p for p in problems if "순환" in p][0]
    assert "docs/a.md" in cycle_msg
    assert "docs/b.md" in cycle_msg
    assert "docs/c.md" in cycle_msg


def test_defect_without_affects_blocks(tmp_path: Path):
    node = _mk("defect.skew", {}, "docs/defects/skew.md")
    assert any("affects" in p for p in validate_defects(tmp_path, [node]))


def test_defect_with_affects_passes(tmp_path: Path):
    node = _mk("defect.skew", {"affects": ["auth.jwt"]}, "docs/defects/skew.md")
    assert validate_defects(tmp_path, [node]) == []


def test_bad_commit_sha_blocks(tmp_path: Path):
    node = _mk(
        "defect.skew", {"affects": ["auth.jwt"], "commit": "not-a-sha"}, "docs/defects/skew.md"
    )
    assert any("commit" in p for p in validate_defects(tmp_path, [node]))


def test_good_commit_sha_passes(tmp_path: Path):
    node = _mk(
        "defect.skew", {"affects": ["auth.jwt"], "commit": "66b7463"}, "docs/defects/skew.md"
    )
    assert validate_defects(tmp_path, [node]) == []


def test_missing_regression_test_file_blocks(tmp_path: Path):
    node = _mk(
        "defect.skew",
        {"affects": ["auth.jwt"], "regression_test": "tests/test_jwt.py::test_skew"},
        "docs/defects/skew.md",
    )
    assert any("tests/test_jwt.py" in p for p in validate_defects(tmp_path, [node]))


def test_regression_test_checks_only_the_path_before_the_node_id(tmp_path: Path):
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_jwt.py").write_text("", encoding="utf-8")
    node = _mk(
        "defect.skew",
        {"affects": ["auth.jwt"], "regression_test": "tests/test_jwt.py::test_skew"},
        "docs/defects/skew.md",
    )
    assert validate_defects(tmp_path, [node]) == []


def test_missing_promoted_rule_file_blocks(tmp_path: Path):
    node = _mk(
        "defect.skew",
        {"affects": ["auth.jwt"], "promoted_to_rule": "rules/gone.md"},
        "docs/defects/skew.md",
    )
    assert any("rules/gone.md" in p for p in validate_defects(tmp_path, [node]))


def test_non_defect_node_using_defect_fields_blocks(tmp_path: Path):
    node = _mk("auth.jwt", {"affects": ["auth.user"]}, "docs/a.md")
    assert any("defect" in p for p in validate_defects(tmp_path, [node]))


def test_adjacency_ignores_direction():
    nodes = [_mk("b.x", {"related": ["a.x"]}, "docs/b.md"), _mk("a.x", path="docs/a.md")]
    adj = undirected_adjacency(build_graph(nodes))
    assert "b.x" in adj["a.x"] and "a.x" in adj["b.x"]


def test_adjacency_drops_dangling_targets():
    # Carrying an id that does not exist into the adjacency makes two nodes pointing at the
    # same typo count as connected for orphan detection — a node unreachable from the index
    # then looks reachable.
    nodes = [
        _mk("a.x", {"related": ["ghost.id"]}, "docs/a.md"),
        _mk("b.x", {"related": ["ghost.id"]}, "docs/b.md"),
    ]
    adj = undirected_adjacency(build_graph(nodes))
    assert "ghost.id" not in adj
    assert adj["a.x"] == [] and adj["b.x"] == []


def test_orphan_warns():
    nodes = [
        _mk("index", path="docs/index.md"),
        _mk("lonely.x", path="docs/lonely.md"),
    ]
    warns = collect_warnings(_wiki(), nodes, build_graph(nodes))
    assert any("lonely.x" in w and "orphan" in w for w in warns)


def test_node_reachable_from_index_is_not_orphan():
    nodes = [
        _mk("index", {"related": ["a.x"]}, "docs/index.md"),
        _mk("a.x", {"related": ["index"]}, "docs/a.md"),
    ]
    assert collect_warnings(_wiki(), nodes, build_graph(nodes)) == []


def test_max_lines_warns():
    node = _mk("a.x", path="docs/a.md")
    node["line_count"] = 500
    nodes = [_mk("index", {"related": ["a.x"]}, "docs/index.md"), node]
    node["front"]["related"] = ["index"]
    warns = collect_warnings(_wiki(max_lines=400), nodes, build_graph(nodes))
    assert any("500" in w and "docs/a.md" in w for w in warns)


def test_max_lines_zero_disables_the_check():
    node = _mk("index", path="docs/index.md")
    node["line_count"] = 9999
    assert collect_warnings(_wiki(max_lines=0), [node], build_graph([node])) == []


def test_rule_promotion_threshold_warns():
    nodes = [_mk("index", path="docs/index.md")]
    for i in range(3):
        nodes.append(
            _mk(f"defect.d{i}", {"affects": ["index"], "tags": ["auth"]}, f"docs/defects/d{i}.md")
        )
    warns = collect_warnings(_wiki(), nodes, build_graph(nodes))
    assert any("auth" in w and "Rule" in w for w in warns)


def test_rule_promotion_silent_when_already_promoted():
    nodes = [_mk("index", path="docs/index.md")]
    for i in range(3):
        nodes.append(
            _mk(
                f"defect.d{i}",
                {
                    "affects": ["index"],
                    "tags": ["auth"],
                    "promoted_to_rule": "rules/x.md" if i == 0 else None,
                },
                f"docs/defects/d{i}.md",
            )
        )
    assert not any("Rule" in w for w in collect_warnings(_wiki(), nodes, build_graph(nodes)))


def test_safe_int_handles_non_numeral_strings():
    assert _safe_int("abc") == 0
    assert _safe_int("many") == 0
    assert _safe_int("42") == 42
    assert _safe_int(42) == 42
    assert _safe_int(0.0) == 0
    assert _safe_int("0") == 0
    assert _safe_int(None) == 0
    assert _safe_int("xyz", default=100) == 100


def test_index_not_a_node_skips_per_node_orphan_check():
    # With the index not resolving to a node there is no origin to compute reachability from,
    # so no individual node may be called an orphan.
    nodes = [
        _mk("a.x", path="docs/a.md"),
        _mk("b.x", path="docs/b.md"),
    ]
    warns = collect_warnings(_wiki(index="docs/missing.md"), nodes, build_graph(nodes))
    assert not any("'a.x'" in w or "'b.x'" in w for w in warns)


def test_index_not_a_node_warns_the_check_is_off():
    # With the wiki enabled and the index not resolving to a node, the operator has to learn
    # that orphan detection is switched off — as a warning, not a block.
    nodes = [_mk("a.x", path="docs/a.md")]
    warns = collect_warnings(_wiki(index="docs/missing.md"), nodes, build_graph(nodes))
    assert any("docs/missing.md" in w for w in warns)


def test_index_not_a_node_is_silent_when_there_are_no_nodes():
    # No nodes at all means nothing to check: an empty wiki gets no noise.
    warns = collect_warnings(_wiki(index="docs/missing.md"), [], build_graph([]))
    assert warns == []


def test_node_linked_to_but_not_from_is_not_orphan():
    nodes = [
        _mk("index", path="docs/index.md"),
        _mk("a.x", {"related": ["index"]}, "docs/a.md"),
    ]
    warns = collect_warnings(_wiki(), nodes, build_graph(nodes))
    assert not any("orphan" in w for w in warns)


def _wiki_repo(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/index.md", "wiki_id: index\ntitle: Index\nrelated: [auth.jwt]\n")
    _node(tmp_path, "docs/auth/jwt.md", "wiki_id: auth.jwt\ntitle: JWT\nrelated: [index]\n")
    return tmp_path


def _sized(nid, front=None, path=None, lines=10):
    node = _mk(nid, front, path or f"docs/{nid}.md")
    node["line_count"] = lines
    return node


def test_start_node_comes_first():
    nodes = [_sized("a.x", {"related": ["b.x"]}), _sized("b.x")]
    paths, _total, _cut = neighbors(build_graph(nodes), nodes, "a.x", 1000)
    assert paths[0] == "docs/a.x.md"


def test_budget_stops_expansion():
    nodes = [
        _sized("a.x", {"related": ["b.x", "c.x"]}, lines=10),
        _sized("b.x", lines=10),
        _sized("c.x", lines=10),
    ]
    paths, total, cut = neighbors(build_graph(nodes), nodes, "a.x", 25)
    assert len(paths) == 2 and total == 20 and cut == 1


def test_start_node_included_even_when_over_budget():
    nodes = [_sized("a.x", lines=9999)]
    paths, total, _cut = neighbors(build_graph(nodes), nodes, "a.x", 10)
    assert paths == ["docs/a.x.md"] and total == 9999


def test_depends_on_wins_over_related_at_the_same_hop():
    nodes = [
        _sized("a.x", {"depends_on": ["dep.x"], "related": ["rel.x"]}, lines=10),
        _sized("dep.x", lines=10),
        _sized("rel.x", lines=10),
    ]
    paths, _total, _cut = neighbors(build_graph(nodes), nodes, "a.x", 25)
    assert paths == ["docs/a.x.md", "docs/dep.x.md"]


def test_cycle_terminates():
    nodes = [_sized("a.x", {"related": ["b.x"]}), _sized("b.x", {"related": ["a.x"]})]
    paths, _total, _cut = neighbors(build_graph(nodes), nodes, "a.x", 1000)
    assert sorted(paths) == ["docs/a.x.md", "docs/b.x.md"]


def test_unknown_id_exits_nonzero(tmp_path: Path, capsys):
    # 0 with empty stdout is indistinguishable from "no neighbors", so the caller reads a
    # failed lookup as "nothing to reconcile" and moves on. The gate never calls --neighbors,
    # so answering 1 here blocks no commit.

    _wiki_repo(tmp_path)
    assert cmd_neighbors(tmp_path, "nope.x", None) == 1
    out = capsys.readouterr()
    assert out.out == "" and "nope.x" in out.err


def test_cli_uses_context_lines_when_budget_omitted(tmp_path: Path, capsys):
    _wiki_repo(tmp_path)
    assert cmd_neighbors(tmp_path, "index", None) == 0
    assert "docs/index.md" in capsys.readouterr().out


def test_dangling_reference_does_not_crash():
    # Edge to non-existent id should not crash; walk continues and entry point returns.
    nodes = [_sized("a.x", {"related": ["ghost.id"]})]
    paths, total, cut = neighbors(build_graph(nodes), nodes, "a.x", 1000)
    assert paths == ["docs/a.x.md"] and total == 10


def test_budget_stops_before_dangling_neighbor():
    # After budget exhaustion, walk reaches dangling node but correctly skips it.
    nodes = [
        _sized("a.x", {"related": ["b.x", "ghost.id"]}, lines=10),
        _sized("b.x", lines=10),
    ]
    paths, total, cut = neighbors(build_graph(nodes), nodes, "a.x", 15)
    # a.x (10) + b.x (10) = 20 > 15, so b.x skipped; ghost.id never checked.
    assert len(paths) == 1 and paths[0] == "docs/a.x.md" and total == 10 and cut == 1


def test_bom_on_index_does_not_shrink_the_graph(tmp_path: Path):
    # The concrete scenario this reproduces: a BOM on index.md drops the index itself out of
    # the node set, _index_id returns None, and orphan detection switches off silently across
    # the whole repository.
    _wiki_repo(tmp_path)
    idx = tmp_path / "docs" / "index.md"
    idx.write_bytes(b"\xef\xbb\xbf" + idx.read_bytes())
    assert cmd_build(tmp_path) == 0
    gp = graph_path(tmp_path, load_wiki_config(tmp_path))
    import yaml as _yaml

    graph = _yaml.safe_load(gp.read_text(encoding="utf-8"))
    assert len(graph["nodes"]) == 2  # as before the BOM: the index node stays


def test_build_writes_graph_and_verify_passes(tmp_path: Path):
    _wiki_repo(tmp_path)
    assert cmd_build(tmp_path) == 0
    assert graph_path(tmp_path, load_wiki_config(tmp_path)).is_file()
    assert cmd_verify(tmp_path) == 0


def test_build_does_not_truncate_before_serializing(tmp_path: Path, monkeypatch):
    # `open("w")` truncates immediately, so computing the content as the write ARGUMENT means a
    # dump_graph failure leaves a 0-byte graph.yaml while main()'s FAIL-OPEN reports exit 0 —
    # --verify then blocks every commit on a file the build claimed to have written.
    import pytest

    _wiki_repo(tmp_path)
    assert cmd_build(tmp_path) == 0
    gp = graph_path(tmp_path, load_wiki_config(tmp_path))
    before = gp.read_bytes()
    assert before  # non-empty to start with

    def _boom(_graph):
        raise RuntimeError("representer error")

    monkeypatch.setattr(wiki_graph, "dump_graph", _boom)
    with pytest.raises(RuntimeError):
        cmd_build(tmp_path)
    assert gp.read_bytes() == before  # the previous graph survives a failed rebuild


def test_default_index_is_normalized_for_a_dot_root(tmp_path: Path):
    # _norm_rel was applied only to a CONFIGURED index; the derived default was interpolated
    # raw, so `root: ./` produced index "./index.md" against node paths "index.md" — the exact
    # mismatch _norm_rel exists to close, left open on the default branch.

    _write_config(tmp_path, "wiki:\n  enable: true\n  root: ./\n")
    _node(tmp_path, "index.md", "wiki_id: index\ntitle: Index\n")
    _node(tmp_path, "lonely.md", "wiki_id: lonely\ntitle: Lonely\n")
    wiki = load_wiki_config(tmp_path)
    assert wiki["index"] == "index.md"
    nodes = collect_nodes(tmp_path, wiki)
    warns = collect_warnings(wiki, nodes, build_graph(nodes))
    assert any("orphan" in w and "lonely" in w for w in warns)
    assert not any("orphan 검사를 생략" in w for w in warns)


def _tracked_repo(tmp_path: Path, docs: dict[str, str], ignore: str = "") -> Path:
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    (tmp_path / "docs").mkdir(exist_ok=True)
    for rel, front in docs.items():
        _node(tmp_path, rel, front)
    if ignore:
        (tmp_path / ".gitignore").write_text(ignore, encoding="utf-8")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", "commit", "-qm", "seed"],
        cwd=tmp_path,
        check=True,
    )
    return tmp_path


def test_gitignored_document_is_not_a_node(tmp_path: Path):
    # Reproduced before the fix: a gitignored .md under the wiki root (a Docusaurus/MkDocs build
    # tree, node_modules) counted as a node, so the committed graph.yaml read as drift and every
    # commit in the repo was denied — including commits that touched no documentation.
    _tracked_repo(
        tmp_path,
        {"docs/index.md": "wiki_id: index\ntitle: Index\n"},
        ignore="docs/build/\n",
    )
    _node(tmp_path, "docs/build/copy.md", "wiki_id: build.copy\ntitle: Copy\n")
    assert cmd_build(tmp_path) == 0
    assert [n["id"] for n in collect_nodes(tmp_path, load_wiki_config(tmp_path))] == ["index"]
    assert cmd_verify(tmp_path) == 0


def test_non_ascii_filename_stays_a_node(tmp_path: Path):
    # `git ls-files` quotes non-ASCII paths under the default core.quotePath
    # ("docs/\355\225\234\352\270\200.md"), which resolves to no file on disk — so a
    # Korean-named document would drop out of the graph silently and block every commit as
    # drift. -z is what prevents that, and this repo's documents are Korean-facing.
    _tracked_repo(
        tmp_path,
        {
            "docs/index.md": "wiki_id: index\ntitle: Index\n",
            "docs/한글.md": "wiki_id: han\ntitle: 한글\n",
        },
    )
    ids = [n["id"] for n in collect_nodes(tmp_path, load_wiki_config(tmp_path))]
    assert sorted(ids) == ["han", "index"]
    assert cmd_build(tmp_path) == 0
    assert cmd_verify(tmp_path) == 0


def test_untracked_document_is_not_a_node(tmp_path: Path):
    # An untracked draft in the graph is worse than a local annoyance: its author commits a
    # graph.yaml naming a file no teammate has, the teammate's rebuild omits it and blocks them,
    # their rebuild blocks the author, and neither can get out.
    _tracked_repo(tmp_path, {"docs/index.md": "wiki_id: index\ntitle: Index\n"})
    assert cmd_build(tmp_path) == 0
    _node(tmp_path, "docs/scratch.md", "wiki_id: scratch\ntitle: Scratch\n")
    assert cmd_verify(tmp_path) == 0  # not staged → not a node → no drift
    subprocess.run(["git", "add", "docs/scratch.md"], cwd=tmp_path, check=True)
    assert cmd_verify(tmp_path) == 1  # staged → now a node → rebuild required


def test_node_set_falls_back_to_the_filesystem_outside_git(tmp_path: Path):
    # --build has to keep working where git cannot answer; there is no commit to gate there.
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    (tmp_path / "docs").mkdir()
    _node(tmp_path, "docs/index.md", "wiki_id: index\ntitle: Index\n")
    assert [n["id"] for n in collect_nodes(tmp_path, load_wiki_config(tmp_path))] == ["index"]


def test_unreadable_git_index_does_not_block(tmp_path: Path, monkeypatch, capsys):
    # The filesystem fallback above is right for --build and wrong for the gate: it re-admits
    # the gitignored tree, so one git hiccup (timeout, index lock, nonzero exit) would report
    # drift nobody else has and deny every commit in the repo — and the remedy it prints
    # (--build) would commit that poisoned graph. Verification fails open instead.
    _tracked_repo(
        tmp_path,
        {"docs/index.md": "wiki_id: index\ntitle: Index\n"},
        ignore="docs/build/\n",
    )
    assert cmd_build(tmp_path) == 0
    _node(tmp_path, "docs/build/copy.md", "wiki_id: build.copy\ntitle: Copy\n")
    assert cmd_verify(tmp_path) == 0  # index readable → gitignored file is not a node
    real = wiki_graph._git
    monkeypatch.setattr(
        wiki_graph,
        "_git",
        lambda args, cwd: None if args[:1] == ["ls-files"] else real(args, cwd),
    )
    assert cmd_verify(tmp_path) == 0
    assert "git 인덱스를 읽지 못했습니다" in capsys.readouterr().err


def test_git_down_entirely_still_fails_open_inside_a_repo(tmp_path: Path, monkeypatch, capsys):
    # The repo-or-not decision must not be a second git call: it shares the first call's
    # failure mode, so the load spike that timed out ls-files times it out too, misreads
    # "repo under load" as "not a repo", and gates on the filesystem set — the exact false
    # block the authoritative flag exists to prevent. Every git call failing while .git
    # exists must still land on fail-open.
    _tracked_repo(
        tmp_path,
        {"docs/index.md": "wiki_id: index\ntitle: Index\n"},
        ignore="docs/build/\n",
    )
    assert cmd_build(tmp_path) == 0
    _node(tmp_path, "docs/build/copy.md", "wiki_id: build.copy\ntitle: Copy\n")
    monkeypatch.setattr(wiki_graph, "_git", lambda args, cwd: None)
    assert cmd_verify(tmp_path) == 0
    assert "git 인덱스를 읽지 못했습니다" in capsys.readouterr().err


def test_build_refuses_the_non_authoritative_node_set(tmp_path: Path, monkeypatch, capsys):
    # cmd_verify above fails open on this flag; cmd_build is the write path the same hiccup
    # poisons. A failed ls-files mid-doc-sync drops build onto the filesystem fallback, which
    # re-admits the gitignored tree — writing THAT is the exact poisoned graph.yaml verify
    # refuses to gate on, and it gets committed before the next healthy verify can object.
    # Unlike verify there is nothing to fail open here: the write itself is the harm, and a
    # refusal costs one re-run. Outside a repository the set is authoritative, so --build
    # keeps working there (covered above).
    _tracked_repo(
        tmp_path,
        {"docs/index.md": "wiki_id: index\ntitle: Index\n"},
        ignore="docs/build/\n",
    )
    assert cmd_build(tmp_path) == 0
    _node(tmp_path, "docs/build/copy.md", "wiki_id: build.copy\ntitle: Copy\n")
    target = graph_path(tmp_path, load_wiki_config(tmp_path))
    before = target.read_text(encoding="utf-8")
    real = wiki_graph._git
    monkeypatch.setattr(
        wiki_graph,
        "_git",
        lambda args, cwd: None if args[:1] == ["ls-files"] else real(args, cwd),
    )
    assert cmd_build(tmp_path) == 1
    assert target.read_text(encoding="utf-8") == before  # the poisoned set was never written
    assert "git 인덱스를 읽지 못했습니다" in capsys.readouterr().err


def test_coerced_id_is_reported_instead_of_vanishing(tmp_path: Path):
    # `wiki_id: no` → False → the node dropped out of the graph and was reported as having no
    # wiki_id, on a document whose wiki_id is right there. `wiki_id: 0123456` → 42798 silently
    # became a valid-looking id.
    problems = _check(
        tmp_path,
        [
            {
                "id": None,
                "path": "docs/a.md",
                "line_count": 3,
                "front": {"wiki_id": False, "title": "A"},
            },
            {
                "id": "42798",
                "path": "docs/c.md",
                "line_count": 3,
                "front": {"wiki_id": 42798, "title": "C"},
            },
        ],
    )
    assert any("docs/a.md" in p and "따옴표" in p for p in problems)
    assert any("docs/c.md" in p and "따옴표" in p for p in problems)


def test_coerced_edge_target_is_reported_by_type(tmp_path: Path):
    # `depends_on: no` became the string "False" and surfaced as "points at a missing id 'False'".
    problems = _check(tmp_path, [_mk("b.x", {"depends_on": False}, "docs/b.md")])
    assert any("depends_on[]" in p and "따옴표" in p for p in problems)


def test_missing_root_directory_is_announced(tmp_path: Path, capsys):
    # A typo'd root turned the whole gate off in total silence, and /wiki-init Step 8 reads
    # --build + --verify succeeding on empty output as proof the wiki is enforced.
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: doc/\n")
    (tmp_path / "docs").mkdir()
    assert load_wiki_config(tmp_path) is None
    assert "doc" in capsys.readouterr().err


def test_orphan_warnings_are_capped(tmp_path: Path):
    nodes = [_mk("index", path="docs/index.md")] + [
        _mk(f"n{i}", path=f"docs/n{i}.md") for i in range(6)
    ]
    warns = collect_warnings({"root": "docs", "index": "docs/index.md"}, nodes, build_graph(nodes))
    assert sum(1 for w in warns if w.startswith("orphan:")) == 3
    assert any("외 3건" in w for w in warns)


def test_bom_on_graph_yaml_is_not_drift(tmp_path: Path):
    # PyYAML accepts a leading BOM, so a Windows editor re-saving graph.yaml unchanged does not
    # turn it into permanent drift. Pinned because .md reads need utf-8-sig for the same reason
    # and the asymmetry looks like a bug.
    _wiki_repo(tmp_path)
    cmd_build(tmp_path)
    gp = graph_path(tmp_path, load_wiki_config(tmp_path))
    gp.write_bytes(b"\xef\xbb\xbf" + gp.read_bytes())
    assert cmd_verify(tmp_path) == 0


def test_edge_constants_cannot_desync():
    # DERIVED_EDGES / MANUAL_EDGES / EDGE_KEYS encode one fact three times, and EDGE_KEYS keeps
    # its own ORDER (it is the --neighbors budget priority), so it cannot simply be derived.
    # Adding an edge kind and forgetting EDGE_KEYS would silently drop it from drift detection
    # and orphan reachability with no error — this is the enforcement.

    assert set(EDGE_KEYS) == set(MANUAL_EDGES) | set(DERIVED_EDGES.values())
    assert set(DERIVED_EDGES) <= set(MANUAL_EDGES)
    assert len(EDGE_KEYS) == len(set(EDGE_KEYS))


def test_build_avoids_the_python_310_only_write_text_newline(tmp_path: Path, monkeypatch):
    # The gate's runtime floor is python 3.8 (check-deps.sh / precommit-runner.sh), while
    # Path.write_text(newline=…) arrived in 3.10. On a 3.9 host that raises TypeError, main()'s
    # FAIL-OPEN swallows it into exit 0, and --build looks successful having written nothing —
    # after which --verify blocks every commit forever.
    _wiki_repo(tmp_path)
    real_write_text = Path.write_text

    def _as_python_39(self, *args, **kwargs):
        if "newline" in kwargs:
            raise TypeError("write_text() got an unexpected keyword argument 'newline'")
        return real_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", _as_python_39)
    assert cmd_build(tmp_path) == 0
    assert graph_path(tmp_path, load_wiki_config(tmp_path)).is_file()


def test_reformatted_graph_is_not_drift(tmp_path: Path):
    # PyYAML's emitter output differs subtly between versions. Comparing bytes reads a
    # semantically identical graph.yaml as drift, and A committing blocks B while B rebuilding
    # blocks A. The verdict has to be taken on the parsed result.
    import yaml as _yaml

    _wiki_repo(tmp_path)
    cmd_build(tmp_path)
    gp = graph_path(tmp_path, load_wiki_config(tmp_path))
    canonical = gp.read_bytes()
    same_graph = _yaml.safe_load(gp.read_text(encoding="utf-8"))
    gp.write_text(
        _yaml.safe_dump(same_graph, sort_keys=False, default_flow_style=True, width=20),
        encoding="utf-8",
    )
    assert gp.read_bytes() != canonical  # the bytes differ
    assert cmd_verify(tmp_path) == 0  # the meaning is the same, so it passes


def test_build_is_idempotent(tmp_path: Path):
    _wiki_repo(tmp_path)
    cmd_build(tmp_path)
    first = graph_path(tmp_path, load_wiki_config(tmp_path)).read_bytes()
    cmd_build(tmp_path)
    assert graph_path(tmp_path, load_wiki_config(tmp_path)).read_bytes() == first


def test_verify_without_graph_file_is_drift(tmp_path: Path):
    _wiki_repo(tmp_path)
    assert cmd_verify(tmp_path) == 1


def test_verify_never_writes_graph_file(tmp_path: Path):
    # --verify is read-only: once the side the commit gate calls starts writing graph.yaml, the
    # design premise that only doc-sync builds is gone.
    _wiki_repo(tmp_path)
    assert cmd_verify(tmp_path) == 1
    assert not graph_path(tmp_path, load_wiki_config(tmp_path)).exists()


def test_verify_does_not_modify_existing_graph_file(tmp_path: Path):
    _wiki_repo(tmp_path)
    cmd_build(tmp_path)
    gp = graph_path(tmp_path, load_wiki_config(tmp_path))
    before = gp.read_bytes()
    assert cmd_verify(tmp_path) == 0
    assert gp.read_bytes() == before


def test_hand_edited_graph_is_drift(tmp_path: Path):
    _wiki_repo(tmp_path)
    cmd_build(tmp_path)
    gp = graph_path(tmp_path, load_wiki_config(tmp_path))
    gp.write_text(gp.read_text(encoding="utf-8").replace("JWT", "JWT2"), encoding="utf-8")
    assert cmd_verify(tmp_path) == 1


def test_malformed_graph_yaml_is_drift_not_crash(tmp_path: Path):
    # Parses, but is not a map — or nodes/edges are not maps. _drifted_paths must not raise
    # AttributeError. It may fail to name anything (an empty list), but the drift verdict
    # itself stands.
    _wiki_repo(tmp_path)
    cmd_build(tmp_path)
    gp = graph_path(tmp_path, load_wiki_config(tmp_path))
    for bad in ("- a\n- b\n", "just text\n", "nodes: [a, b]\n", "edges: [x]\n"):
        gp.write_text(bad, encoding="utf-8")
        assert cmd_verify(tmp_path) == 1, f"crashed or passed on: {bad!r}"


def test_unreadable_graph_yaml_is_drift_not_crash(tmp_path: Path, capsys):
    # A graph.yaml that raises UnicodeDecodeError. A file that cannot be read is no evidence
    # of being current, so it is reported as drift and blocks rather than being skipped.
    _wiki_repo(tmp_path)
    cmd_build(tmp_path)
    gp = graph_path(tmp_path, load_wiki_config(tmp_path))
    gp.write_bytes(b"\xff\xfe\xfd\xfc not valid utf-8")
    assert cmd_verify(tmp_path) == 1
    err = capsys.readouterr().err
    assert "graph.yaml" in err and "읽을 수 없습니다" in err


def test_verify_blocks_on_structure_violation(tmp_path: Path, capsys):
    # Adding bad.md after the build forces exit 1 on drift alone, and the test then passes with
    # the validate_structure call deleted. Only a rebuild WITH bad.md in place clears the drift,
    # and only then can the block be claimed to come from the structure violation.
    _wiki_repo(tmp_path)
    _node(tmp_path, "docs/bad.md", "wiki_id: BAD\ntitle: Bad\n")
    _node(tmp_path, "docs/defects/skew.md", "wiki_id: defect.skew\ntitle: Skew\n")
    cmd_build(tmp_path)
    assert cmd_verify(tmp_path) == 1
    err = capsys.readouterr().err
    assert "BAD" in err and "형식" in err
    # validate_structure already composes validate_defects internally: cmd_verify calling both
    # reports every defect violation twice.
    affects_lines = [ln for ln in err.splitlines() if "defect 노드에는 affects" in ln]
    assert len(affects_lines) == 1


def test_warnings_alone_do_not_block(tmp_path: Path, capsys):
    _wiki_repo(tmp_path)
    _node(tmp_path, "docs/lonely.md", "wiki_id: lonely.x\ntitle: Lonely\n")
    cmd_build(tmp_path)
    assert cmd_verify(tmp_path) == 0
    assert "orphan" in capsys.readouterr().err


def test_noop_when_wiki_absent(tmp_path: Path, capsys):
    assert cmd_verify(tmp_path) == 0
    assert cmd_build(tmp_path) == 0
    out = capsys.readouterr()
    assert out.out == "" and out.err == ""


def test_drift_message_names_the_drifted_node_only(tmp_path: Path, capsys):
    # It has to say WHICH document drifted, not merely that something did. Picking an arbitrary
    # node names an unrelated file and deepens the confusion.
    _wiki_repo(tmp_path)
    cmd_build(tmp_path)
    _node(tmp_path, "docs/auth/jwt.md", "wiki_id: auth.jwt\ntitle: JWT2\nrelated: [index]\n")
    assert cmd_verify(tmp_path) == 1
    err = capsys.readouterr().err
    assert "docs/auth/jwt.md" in err
    assert "docs/index.md" not in err


def test_drift_message_names_the_last_commit(tmp_path: Path, capsys):
    _wiki_repo(tmp_path)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", "commit", "-qm", "seed"],
        cwd=tmp_path,
        check=True,
    )
    cmd_build(tmp_path)
    _node(tmp_path, "docs/auth/jwt.md", "wiki_id: auth.jwt\ntitle: JWT2\nrelated: [index]\n")
    assert cmd_verify(tmp_path) == 1
    assert "seed" in capsys.readouterr().err


def test_main_fails_open_on_internal_exception(tmp_path: Path, monkeypatch, capsys):
    # main()'s exit code IS the gate's verdict, so an exception raised anywhere in this module
    # must not block the whole repository (Invariant #1: wiki is none of the three exceptions —
    # missing dependency, unclassified commit, merge strategy).

    monkeypatch.setattr(wiki_graph, "host_root", lambda: tmp_path)

    def _boom(root):
        raise RuntimeError("boom")

    monkeypatch.setattr(wiki_graph, "load_wiki_config", _boom)
    assert wiki_graph.main(["--verify"]) == 0
    assert "boom" in capsys.readouterr().err


def test_main_routes_an_empty_neighbors_id_to_the_lookup(tmp_path: Path, monkeypatch, capsys):
    # Branching on truthiness let `--neighbors ""` fall through to cmd_verify: the caller read
    # an empty lookup while graph verification was actually running, and drift returned 1,
    # which looked like a failed lookup. Both exit 1, so only stderr tells them apart.

    _wiki_repo(tmp_path)  # no graph.yaml was built, so leaking into verify would fail on drift
    monkeypatch.setattr(wiki_graph, "host_root", lambda: tmp_path)
    assert wiki_graph.main(["--neighbors", ""]) == 1
    err = capsys.readouterr().err
    assert "알 수 없는 id" in err
    assert "검증 실패" not in err


def test_main_argparse_error_still_exits_nonzero():
    # An argparse usage error is a SystemExit and must pass straight through finding 5's
    # `except Exception` guard. The gate composes this command itself so it cannot happen in
    # practice, but this pins the regression where the guard swallows SystemExit too.
    import pytest

    with pytest.raises(SystemExit) as exc:
        wiki_graph.main([])
    assert exc.value.code == 2


def _git_repo_with_source(tmp_path: Path, sha_slot: str) -> str:
    (tmp_path / "docs").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    # Special case: "null" should remain unquoted so YAML parses it as Python None
    if sha_slot == "null":
        front = f"wiki_id: a.x\ntitle: A\nsources:\n  src/a.py: {sha_slot}\n"
    else:
        front = f'wiki_id: a.x\ntitle: A\nsources:\n  src/a.py: "{sha_slot}"\n'
    _node(tmp_path, "docs/a.md", front)
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", "commit", "-qm", "seed"],
        cwd=tmp_path,
        check=True,
    )
    # Returns the working-tree BLOB hash — the fresh value under cmd_stale's blob semantics.
    return subprocess.run(
        ["git", "hash-object", "--", "src/a.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()


def test_empty_recorded_sha_is_still_reported_stale(tmp_path: Path, capsys):
    # `src/a.py: ""` — what a hand-edit (or an LLM meaning "unknown") produces instead of null.
    # `current.startswith("")` is unconditionally true, so the node reported fresh forever and
    # doc-sync Mode W, which runs entirely off --stale, never revisited it again.
    _git_repo_with_source(tmp_path, "")
    assert cmd_stale(tmp_path) == 0
    rep = json.loads(capsys.readouterr().out)
    assert [e["id"] for e in rep] == ["a.x"]
    assert rep[0]["recorded"] is None


def test_yaml_coerced_sha_is_reported_not_silently_compared(tmp_path: Path):
    # `commit: 0123456` is YAML 1.1 octal → int 42798. Left uncaught, the message names a number
    # the author never typed ("commit '42798' 은 hex 7~40자가 아닙니다") and the fix is
    # undiscoverable; as a sources value it makes the node stale forever.
    import yaml as _yaml

    assert _yaml.safe_load("commit: 0123456") == {"commit": 42798}  # the coercion is real
    (tmp_path / "docs").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/a.md", "wiki_id: a.x\ntitle: A\nsources:\n  src/a.py: 0123456\n")
    wiki = load_wiki_config(tmp_path)
    nodes = collect_nodes(tmp_path, wiki)
    problems = validate_structure(tmp_path, wiki, nodes, build_graph(nodes))
    assert any("따옴표" in p and "int" in p for p in problems)


def test_yaml_coerced_title_is_not_reported_as_missing(tmp_path: Path):
    # `title: no` parses to False. Truthiness read that as absent and blocked with
    # "필수 필드 title 이 없습니다" on a document whose title is right there.
    node = {"id": "a.x", "path": "docs/a.md", "front": {"wiki_id": "a.x", "title": False}}
    node["line_count"] = 3
    problems = _check(tmp_path, [node])
    assert not any("title 이 없습니다" in p for p in problems)
    assert any("따옴표" in p and "bool" in p for p in problems)


def test_missing_source_path_is_flagged_in_stale(tmp_path: Path, capsys):
    # git log answers for a deleted path, so a moved file used to read as an ordinary sha drift:
    # doc-sync stamped the new sha and --verify's "sources 경로 … 가 없습니다" block stayed.
    _git_repo_with_source(tmp_path, "null")
    subprocess.run(["git", "mv", "src/a.py", "src/b.py"], cwd=tmp_path, check=True)
    assert cmd_stale(tmp_path) == 0
    (entry,) = json.loads(capsys.readouterr().out)
    assert entry["missing"] is True and entry["current"] is None


def test_matching_sha_is_not_stale(tmp_path: Path, capsys):
    sha = _git_repo_with_source(tmp_path, "PLACEHOLDER")
    _node(tmp_path, "docs/a.md", f'wiki_id: a.x\ntitle: A\nsources:\n  src/a.py: "{sha}"\n')
    assert cmd_stale(tmp_path) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_short_sha_prefix_matches(tmp_path: Path, capsys):
    sha = _git_repo_with_source(tmp_path, "PLACEHOLDER")
    _node(tmp_path, "docs/a.md", f'wiki_id: a.x\ntitle: A\nsources:\n  src/a.py: "{sha[:7]}"\n')
    assert cmd_stale(tmp_path) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_outdated_sha_is_stale(tmp_path: Path, capsys):
    _git_repo_with_source(tmp_path, "0000000")
    assert cmd_stale(tmp_path) == 0
    (entry,) = json.loads(capsys.readouterr().out)
    assert entry["id"] == "a.x" and entry["source"] == "src/a.py"
    assert entry["recorded"] == "0000000"


def test_null_sha_is_stale_as_a_new_source(tmp_path: Path, capsys):
    _git_repo_with_source(tmp_path, "null")
    assert cmd_stale(tmp_path) == 0
    (entry,) = json.loads(capsys.readouterr().out)
    assert entry["recorded"] is None


def _blob_of(root: Path, rel: str) -> str:
    return subprocess.run(
        ["git", "hash-object", "--", rel], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_stale_blob_recorded_fresh_and_stale(tmp_path: Path, capsys):
    # Recorded value == the working-tree blob means fresh. Change the file's content (no commit
    # needed) and it is stale: the verdict rides on content, not on commit history, so a
    # squash/rebase promotion cannot manufacture a false stale.
    _git_repo_with_source(tmp_path, "PLACEHOLDER")
    blob = _blob_of(tmp_path, "src/a.py")
    _node(tmp_path, "docs/a.md", f'wiki_id: a.x\ntitle: A\nsources:\n  src/a.py: "{blob}"\n')
    assert cmd_stale(tmp_path) == 0
    assert json.loads(capsys.readouterr().out) == []
    (tmp_path / "src" / "a.py").write_text("changed = True\n", encoding="utf-8")
    assert cmd_stale(tmp_path) == 0
    (entry,) = json.loads(capsys.readouterr().out)
    assert entry["recorded"] == blob and entry["current"] != blob
    assert "migrated" not in entry


def test_stale_commit_recorded_offers_migration(tmp_path: Path, capsys):
    # A legacy record (a commit sha) migrates to `git rev-parse <commit>:<path>` — the blob as
    # of that commit. The entry is reported even with the content unchanged, so doc-sync can
    # rewrite the marker alone and let the repository converge.
    _git_repo_with_source(tmp_path, "PLACEHOLDER")
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=tmp_path, capture_output=True, text=True, check=True
    ).stdout.strip()
    want = subprocess.run(
        ["git", "rev-parse", f"{head}:src/a.py"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    _node(tmp_path, "docs/a.md", f'wiki_id: a.x\ntitle: A\nsources:\n  src/a.py: "{head}"\n')
    assert cmd_stale(tmp_path) == 0
    (entry,) = json.loads(capsys.readouterr().out)
    assert entry["migrated"] == want


def test_stale_vanished_commit_migrates_to_null(tmp_path: Path, capsys):
    # A commit lost to GC (its type cannot be queried) migrates to null: ordinary stale, to be
    # resolved by syncing the body.
    _git_repo_with_source(tmp_path, "f" * 40)
    assert cmd_stale(tmp_path) == 0
    (entry,) = json.loads(capsys.readouterr().out)
    assert entry["migrated"] is None


def _stamp_repo(tmp_path: Path) -> Path:
    """A repo with one committed node (sources holding the working-tree blob) and a matching
    graph.yaml."""
    root = tmp_path
    (root / "src").mkdir()
    (root / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    (root / "docs").mkdir()
    _write_config(root, "wiki:\n  enable: true\n  root: docs/\n")
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    blob = _blob_of(root, "src/a.py")
    _node(root, "docs/index.md", "wiki_id: index\ntitle: Index\nrelated: [a]\n")
    _node(root, "docs/a.md", f"wiki_id: a\ntitle: A\nsources:\n  src/a.py: '{blob}'\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", "commit", "-qm", "seed"],
        cwd=root,
        check=True,
    )
    # A second commit so HEAD~1 exists and already holds the documents — the ordinary state of
    # a repository. On a root commit the stamp check has no parent to compare against and
    # fails open, which would make every fixture below silently untested.
    (root / "README.md").write_text("seed\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", "commit", "-qm", "seed readme"],
        cwd=root,
        check=True,
    )
    return root


def _sha_in(doc: Path) -> str:
    m = re.search(r"'([0-9a-f]{7,40})'", doc.read_text(encoding="utf-8"))
    assert m is not None
    return m.group(1)


def test_stamp_only_change_blocks(tmp_path: Path, capsys):
    root = _stamp_repo(tmp_path)
    doc = root / "docs" / "a.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(_sha_in(doc), "b" * 40), encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0  # graph agrees, leaving only the stamp violation
    assert cmd_verify(root) == 1
    assert "본문 변경이 없습니다" in capsys.readouterr().err


def test_stamp_with_body_edit_passes(tmp_path: Path):
    root = _stamp_repo(tmp_path)
    doc = root / "docs" / "a.md"
    text = doc.read_text(encoding="utf-8").replace(_sha_in(doc), "b" * 40)
    doc.write_text(text + "\n갱신된 설명.\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    assert cmd_verify(root) == 0


def test_stamp_migration_rewrite_passes(tmp_path: Path):
    # old is a commit sha and new == `git rev-parse <old>:<src>`: a meaning-preserving rewrite,
    # which is allowed (spec §2).
    root = _stamp_repo(tmp_path)
    head = subprocess.run(
        ["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()
    doc = root / "docs" / "a.md"
    doc.write_text(doc.read_text(encoding="utf-8").replace(_sha_in(doc), head), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", "commit", "-qm", "legacy marker"],
        cwd=root,
        check=True,
    )
    blob_at_head = subprocess.run(
        ["git", "rev-parse", f"{head}:src/a.py"],
        cwd=root,
        capture_output=True,
        text=True,
        check=True,
    ).stdout.strip()
    doc.write_text(doc.read_text(encoding="utf-8").replace(head, blob_at_head), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    assert cmd_verify(root) == 0


def _commit(root: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", "commit", "-qm", message],
        cwd=root,
        check=True,
    )


def test_stamp_allowed_when_head_carries_the_body_edit(tmp_path: Path):
    # Exactly the amend path the block message recommends: with the body sync already committed,
    # HEAD holds that body and the only delta left is the sha. Blocking it makes the advice
    # unfollowable, and a split commit (body first, stamp second) has the same shape, so it
    # opens with it.
    root = _stamp_repo(tmp_path)
    doc = root / "docs" / "a.md"
    (root / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
    doc.write_text(
        doc.read_text(encoding="utf-8").replace("본문", "코드에 맞춰 갱신한 본문"),
        encoding="utf-8",
    )
    _commit(root, "docs: sync the body, stamp not yet applied")
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(_sha_in(doc), _blob_of(root, "src/a.py")),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    assert cmd_verify(root) == 0


def test_stamp_still_blocks_when_head_body_is_unchanged(tmp_path: Path):
    # That the allowance above does not open the check wholesale: if the previous commit did not
    # touch that document's body, a stamp-only commit is still blocked.
    root = _stamp_repo(tmp_path)
    (root / "other.txt").write_text("무관한 변경\n", encoding="utf-8")
    _commit(root, "chore: touch an unrelated file")
    doc = root / "docs" / "a.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(_sha_in(doc), "b" * 40), encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    assert cmd_verify(root) == 1


def test_stamp_fails_open_when_git_cannot_answer(tmp_path: Path):
    # rev-parse failing to answer (a timeout, say) is an internal error, not a verdict, and
    # Invariant #1 requires letting such a commit through. It has to stay distinct from the
    # legitimate nonzero that means "no such object", so it opens only when the git liveness
    # probe fails.
    root = _stamp_repo(tmp_path)
    doc = root / "docs" / "a.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(_sha_in(doc), "b" * 40), encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    wiki = load_wiki_config(root)
    nodes = collect_nodes(root, wiki)
    assert validate_stamps(root, wiki, nodes)  # blocks under normal conditions

    real = wiki_graph._git

    def dying_git(args, cwd):
        if args[0] in ("rev-parse", "cat-file"):
            return None  # git no longer answers
        return real(args, cwd)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(wiki_graph, "_git", dying_git)
        assert validate_stamps(root, wiki, nodes) == []


def test_stamp_fails_open_on_a_root_commit(tmp_path: Path):
    # With no parent there is no way to ask whether the previous commit synced this body, and
    # what cannot be decided passes.
    root = _stamp_repo(tmp_path)
    subprocess.run(["git", "reset", "-q", "--soft", "HEAD~1"], cwd=root, check=True)
    doc = root / "docs" / "a.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(_sha_in(doc), "b" * 40), encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    assert cmd_verify(root) == 0


def test_nodes_for_finds_a_directory_source_from_a_file(tmp_path: Path, capsys):
    # /flow hands over changed file paths. A node documenting a directory dropping out of that
    # lookup returns an empty line, which the caller reads as "undocumented".
    root = _nodes_for_repo(tmp_path)
    _node(root, "docs/authdir.md", "wiki_id: auth.dir\ntitle: D\nsources:\n  src/auth: null\n")
    assert wiki_graph.cmd_nodes_for(root, ["src/auth/jwt.py"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert sorted(out) == ["src/auth/jwt.py\tauth.dir", "src/auth/jwt.py\tauth.jwt"]


def test_nodes_for_directory_source_keeps_the_segment_boundary(tmp_path: Path, capsys):
    # The segment boundary has to survive in the new direction of the symmetric match too: a
    # `src/auth` node matching a file in the sibling `src/auth-x/` pulls somebody else's
    # document into the lookup.
    root = _nodes_for_repo(tmp_path)
    _node(root, "docs/authdir.md", "wiki_id: auth.dir\ntitle: D\nsources:\n  src/auth: null\n")
    assert wiki_graph.cmd_nodes_for(root, ["src/auth-x/jwt.py"]) == 0
    assert capsys.readouterr().out == ""


def test_stamp_still_blocks_a_document_introduced_by_head(tmp_path: Path):
    # HEAD~1 reads fine and only that document is absent, which means HEAD created it. A
    # creating commit already carries its own stamp, so the next commit swapping the sha is not
    # a sync — the block stands.
    root = _stamp_repo(tmp_path)
    blob = _blob_of(root, "src/a.py")
    _node(
        root,
        "docs/b.md",
        f"wiki_id: b\ntitle: B\nrelated: [index]\nsources:\n  src/a.py: '{blob}'\n",
    )
    _commit(root, "docs: add a second node")
    doc = root / "docs" / "b.md"
    doc.write_text(doc.read_text(encoding="utf-8").replace(blob, "b" * 40), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    assert cmd_verify(root) == 1


def test_stamp_allows_a_rename_synced_in_head(tmp_path: Path):
    # With the rename and the body sync in one commit and the stamp in the next (or an amend),
    # the new path is absent from HEAD~1. Calling that a creation misses the sync and blocks the
    # very amend / rebase / fixup the block message recommends. diff -M traces the old path back
    # so the body comparison can continue.
    root = _stamp_repo(tmp_path)
    (root / "src" / "a.py").write_text("x = 2\n", encoding="utf-8")
    subprocess.run(["git", "mv", "docs/a.md", "docs/alpha.md"], cwd=root, check=True)
    doc = root / "docs" / "alpha.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace("본문", "코드에 맞춰 갱신한 본문"),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    _commit(root, "docs: rename and sync the body, stamp deferred")
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(_sha_in(doc), _blob_of(root, "src/a.py")),
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_verify(root) == 0


def test_stamp_still_blocks_a_pure_rename_with_sha_swap(tmp_path: Path):
    # A move on its own syncs no source: the rename allowance must not become a laundering route
    # for a sha.
    root = _stamp_repo(tmp_path)
    subprocess.run(["git", "mv", "docs/a.md", "docs/alpha.md"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    _commit(root, "docs: pure rename, nothing synced")
    doc = root / "docs" / "alpha.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(_sha_in(doc), "b" * 40), encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_verify(root) == 1


def test_stamp_fails_open_when_the_parent_read_flakes(tmp_path: Path):
    # Reading the HEAD~1:<path> body fails (a timeout, say) while the object lookup still
    # answers. That is not a verdict of "the parent has no such document", so carrying it into
    # the blocking path violates Invariant #1.
    root = _stamp_repo(tmp_path)
    (root / "other.txt").write_text("무관한 변경\n", encoding="utf-8")
    _commit(root, "chore: touch an unrelated file")
    doc = root / "docs" / "a.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(_sha_in(doc), "b" * 40), encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    wiki = load_wiki_config(root)
    nodes = collect_nodes(root, wiki)
    assert validate_stamps(root, wiki, nodes)  # blocks under normal conditions

    real = wiki_graph._git
    target = "HEAD~1:docs/a.md"

    def flaky_parent_read(args, cwd):
        if args[-1] == target and args != ["rev-parse", "--verify", target]:
            return None  # only the body read (show/cat-file) dies; the object lookup still answers
        return real(args, cwd)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(wiki_graph, "_git", flaky_parent_read)
        assert validate_stamps(root, wiki, nodes) == []


def test_stamp_fails_open_when_the_rename_lookup_fails(tmp_path: Path):
    # The path is absent from the parent so a rename has to be asked about, and a diff that
    # cannot answer leaves creation and rename indistinguishable — undecidable passes
    # (Invariant #1).
    root = _stamp_repo(tmp_path)
    subprocess.run(["git", "mv", "docs/a.md", "docs/alpha.md"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    _commit(root, "docs: pure rename")
    doc = root / "docs" / "alpha.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(_sha_in(doc), "b" * 40), encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    wiki = load_wiki_config(root)
    nodes = collect_nodes(root, wiki)

    real = wiki_graph._git

    def no_rename_answer(args, cwd):
        if args[0] == "diff" and "HEAD~1" in args:
            return None
        return real(args, cwd)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(wiki_graph, "_git", no_rename_answer)
        assert validate_stamps(root, wiki, nodes) == []


def test_stamp_fails_open_when_the_parent_path_was_a_tree(tmp_path: Path):
    # If the same path was a directory in the parent commit, `git show` prints a tree listing
    # and exits 0, which is misread as "the body differs". cat-file blob fails on a tree, and
    # the object-existence probe separates that failure from "the parent has no such document"
    # and lets it through (Invariant #1).
    # Judged on the outcome alone the old `show` path also passes, for a different reason, so
    # what this test pins is not the result but the QUERY taken — the object-existence probe has
    # to actually happen.
    root = _stamp_repo(tmp_path)
    d = root / "docs" / "x.md"
    d.mkdir()
    (d / "inner.txt").write_text("i\n", encoding="utf-8")
    _commit(root, "docs: x.md is a directory here")
    shutil.rmtree(d)
    blob = _blob_of(root, "src/a.py")
    _node(
        root,
        "docs/x.md",
        f"wiki_id: x\ntitle: X\nrelated: [index]\nsources:\n  src/a.py: '{blob}'\n",
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    _commit(root, "docs: x.md becomes a node")
    doc = root / "docs" / "x.md"
    doc.write_text(doc.read_text(encoding="utf-8").replace(blob, "b" * 40), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    wiki = load_wiki_config(root)
    nodes = collect_nodes(root, wiki)

    real = wiki_graph._git
    seen: list[list[str]] = []

    def recording(args, cwd):
        seen.append(args)
        return real(args, cwd)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(wiki_graph, "_git", recording)
        assert validate_stamps(root, wiki, nodes) == []
    assert ["cat-file", "blob", "HEAD~1:docs/x.md"] in seen
    assert ["rev-parse", "--verify", "HEAD~1:docs/x.md"] in seen


def test_stamp_probes_head_liveness_once(tmp_path: Path):
    # Re-running the same HEAD liveness probe per swap on the blocking path wastes spawns in
    # proportion to the source count (40 documents times 3 sources is 120 of them); once per
    # call is enough.
    root = _stamp_repo(tmp_path)
    (root / "src" / "b.py").write_text("y = 1\n", encoding="utf-8")
    doc = root / "docs" / "a.md"
    a_blob, b_blob = _sha_in(doc), _blob_of(root, "src/b.py")
    doc.write_text(
        f"---\nwiki_id: a\ntitle: A\nsources:\n  src/a.py: '{a_blob}'\n  src/b.py: '{b_blob}'\n"
        "---\n\n본문\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    _commit(root, "docs: two sources")
    (root / "other.txt").write_text("무관한 변경\n", encoding="utf-8")
    _commit(root, "chore: unrelated")
    text = doc.read_text(encoding="utf-8")
    doc.write_text(text.replace(a_blob, "b" * 40).replace(b_blob, "c" * 40), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    wiki = load_wiki_config(root)
    nodes = collect_nodes(root, wiki)

    real = wiki_graph._git
    probes: list[list[str]] = []

    def counting(args, cwd):
        if args == ["rev-parse", "--verify", "HEAD"]:
            probes.append(args)
        return real(args, cwd)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(wiki_graph, "_git", counting)
        problems = validate_stamps(root, wiki, nodes)
    assert len(problems) == 2  # one problem per swap; the block itself stands
    assert len(probes) == 1


def _renamed_nodes_repo(tmp_path: Path, count: int) -> Path:
    """A commit renaming all `count` nodes, then a working tree that swaps only the shas."""
    root = _stamp_repo(tmp_path)
    blob = _blob_of(root, "src/a.py")
    ids = [f"n{i}" for i in range(count)]
    related = ", ".join(ids)
    _node(root, "docs/index.md", f"wiki_id: index\ntitle: Index\nrelated: [a, {related}]\n")
    for i in ids:
        _node(root, f"docs/{i}.md", f"wiki_id: {i}\ntitle: {i}\nsources:\n  src/a.py: '{blob}'\n")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    _commit(root, "docs: add nodes")
    for i in ids:
        subprocess.run(["git", "mv", f"docs/{i}.md", f"docs/r{i}.md"], cwd=root, check=True)
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    _commit(root, "docs: rename them all")
    for i in ids:
        doc = root / "docs" / f"r{i}.md"
        doc.write_text(doc.read_text(encoding="utf-8").replace(blob, "b" * 40), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    return root


def _count_git(root: Path, wiki, nodes, match) -> tuple[int, list[str]]:
    real = wiki_graph._git
    hits = {"n": 0}

    def counting(args, cwd):
        if match(args):
            hits["n"] += 1
        return real(args, cwd)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(wiki_graph, "_git", counting)
        problems = validate_stamps(root, wiki, nodes)
    return hits["n"], problems


def test_stamp_looks_up_renames_once_even_when_git_cannot_answer(tmp_path: Path):
    # Using a single None for renames to mean both "not looked up yet" and "looked up, no
    # answer" repeats a failed lookup for every node that reaches the rename branch. `diff -M`
    # is the most expensive query this gate issues and _git's timeout is 5s, so the worst case
    # is N times 5s sitting inside the commit hook.
    root = _renamed_nodes_repo(tmp_path, 5)
    wiki = load_wiki_config(root)
    nodes = collect_nodes(root, wiki)
    real = wiki_graph._git

    def dead_rename_lookup(args, cwd):
        if args[0] == "diff" and "-M" in args:
            return None
        return real(args, cwd)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(wiki_graph, "_git", dead_rename_lookup)
        count, problems = _count_git(root, wiki, nodes, lambda a: a[0] == "diff" and "-M" in a)
    assert problems == []  # no answer was obtained, so there is no verdict either (Invariant #1)
    assert count == 1


def test_stamp_probes_the_parent_commit_once(tmp_path: Path):
    # The answer to `rev-parse --verify HEAD~1` is a constant for the repository: asking it per
    # node leaves exactly the waste the HEAD probe removed.
    root = _renamed_nodes_repo(tmp_path, 5)
    wiki = load_wiki_config(root)
    nodes = collect_nodes(root, wiki)
    count, problems = _count_git(
        root, wiki, nodes, lambda a: a == ["rev-parse", "--verify", "HEAD~1"]
    )
    assert len(problems) == 5  # a pure rename, so the block stands
    assert count == 1


def test_head_renames_fails_open_on_a_truncated_record(tmp_path: Path):
    # Skipping a truncated record yields {}, and {} is a VERDICT of "no renames" that can drive
    # a legitimate rename-plus-sync into a block. Output that cannot be read is not a verdict.
    # Well-formed output always ends in a NUL (A/D/M/T/R alike, including paths with spaces or
    # Hangul): `_git`'s .strip() does not remove NUL ('\0'.isspace() is False), so the
    # terminator survives.
    # The case table is an ordered list, not a map. A dict literal would get duplicate-key
    # detection free from ruff F601 and a list has no such net, so the assertion below restores
    # the protection a list gives up.
    cases = [
        ("R100\0docs/old.md\0docs/new.md\0", {"docs/new.md": "docs/old.md"}),
        ("M\0docs/a.md\0R100\0docs/old.md\0docs/new.md\0", {"docs/new.md": "docs/old.md"}),
        ("M\0docs/a.md\0", {}),  # complete output: a legitimate verdict of no renames
        ("", {}),  # nothing changed
        ("R100\0docs/old.md", None),  # the record is missing entirely
        ("M\0docs/a", None),  # truncated mid-field, and the length still looks right
        ("R100\0docs/old.md\0", None),  # cut at a NUL, new path empty
        ("M\0docs/a.md\0R100\0", None),  # the front is intact and only the last record is short
        ("M\0", None),  # the same for a two-field record: the path slot is the terminator
        ("M\0docs/a.md\0D\0", None),  # only the last two-field record lost its path
        # An empty status is only well-formed at the very end, as the terminator. In the middle
        # it means corrupted output, and stopping there drops the renames that follow — another
        # route to a "no renames" verdict.
        ("M\0docs/a.md\0\0R100\0docs/o.md\0docs/n.md\0", None),
    ]
    assert len({out for out, _ in cases}) == len(cases)  # a duplicated input is a lost case
    real = wiki_graph._git
    with pytest.MonkeyPatch.context() as mp:
        for out, expected in cases:
            mp.setattr(wiki_graph, "_git", lambda a, c, _o=out: _o)
            assert wiki_graph._head_renames(tmp_path, "docs") == expected, repr(out)
    assert wiki_graph._git is real


def test_head_renames_ignores_a_copy_record(tmp_path: Path):
    # C leaves the original in place. A document whose stamp was deferred follows the MOVED
    # original, so reading a copy as a rename compares against the body of a file that never
    # went anywhere. git will not emit C here because only `-M` is passed (an explicit `-M`
    # overrides `diff.renames=copies` down to renames-only — without `-M` that setting alone can
    # produce C — and with `-M` given, the only way back to copy detection is a command-line
    # `-C` / `--find-copies-harder`; measured on git 2.47.1). The parser does not lean on that
    # guarantee.
    real = wiki_graph._git
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(wiki_graph, "_git", lambda a, c: "C100\0docs/src.md\0docs/copy.md\0")
        assert wiki_graph._head_renames(tmp_path, "docs") == {}
        # Consuming three fields is itself correct; otherwise the records that follow shift.
        mp.setattr(
            wiki_graph,
            "_git",
            lambda a, c: "C100\0docs/src.md\0docs/copy.md\0R100\0docs/o.md\0docs/n.md\0",
        )
        assert wiki_graph._head_renames(tmp_path, "docs") == {"docs/n.md": "docs/o.md"}
    assert wiki_graph._git is real


def test_stamp_new_file_passes(tmp_path: Path):
    # The first stamp on a document absent from HEAD is free — authoring it IS the sync.
    root = _stamp_repo(tmp_path)
    _node(
        root,
        "docs/b.md",
        "wiki_id: b\ntitle: B\nrelated: [index]\nsources:\n  src/a.py: '" + "c" * 40 + "'\n",
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    assert cmd_verify(root) == 0


def test_stamp_check_sees_non_ascii_paths(tmp_path: Path, capsys):
    # Under the default core.quotePath, `git diff --name-only` returns a Hangul path C-escaped
    # and quoted: without -z such a document drops out of the stamp check silently (the same
    # footgun as _candidate_files' "-z is mandatory").
    root = _stamp_repo(tmp_path)
    doc = root / "docs" / "한글노트.md"
    blob = _blob_of(root, "src/a.py")
    _node(
        root,
        "docs/한글노트.md",
        f"wiki_id: ko\ntitle: K\nrelated: [index]\nsources:\n  src/a.py: '{blob}'\n",
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", "commit", "-qm", "ko node"],
        cwd=root,
        check=True,
    )
    doc.write_text(doc.read_text(encoding="utf-8").replace(blob, "b" * 40), encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    assert cmd_verify(root) == 1
    assert "한글노트" in capsys.readouterr().err


def test_stamp_allows_entry_add_remove_and_null_fill(tmp_path: Path):
    # Resolving a missing path by dropping the entry, adding a new source, and the first
    # null-to-sha registration are all legitimate without a body edit; losing this guard
    # false-blocks a legitimate commit.
    root = _stamp_repo(tmp_path)
    doc = root / "docs" / "a.md"
    blob = _sha_in(doc)
    (root / "src" / "b.py").write_text("y = 1\n", encoding="utf-8")
    front = f"---\nwiki_id: a\ntitle: A\nsources:\n  src/a.py: '{blob}'\n  src/b.py: null\n"
    doc.write_text(front + "---\n\n본문\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    assert cmd_verify(root) == 0  # entry added (registered as null)
    b_blob = _blob_of(root, "src/b.py")
    doc.write_text(doc.read_text(encoding="utf-8").replace("null", f"'{b_blob}'"), encoding="utf-8")
    assert cmd_verify(root) == 0  # first null-to-sha (keys only in the graph, so no rebuild)
    doc.write_text(
        f"---\nwiki_id: a\ntitle: A\nsources:\n  src/a.py: '{blob}'\n---\n\n본문\n",
        encoding="utf-8",
    )
    assert cmd_build(root) == 0  # the key set shrank, so the graph is rebuilt
    assert cmd_verify(root) == 0  # entry removed


def test_stale_batches_hash_object(tmp_path: Path, monkeypatch):
    # Spawning a process is costliest on Windows: however many paths there are, hash-object
    # runs once.
    _git_repo_with_source(tmp_path, "null")
    (tmp_path / "src" / "b.py").write_text("y = 1\n", encoding="utf-8")
    (tmp_path / "src" / "c.py").write_text("z = 1\n", encoding="utf-8")
    _node(
        tmp_path,
        "docs/a.md",
        "wiki_id: a.x\ntitle: A\nsources:\n  src/a.py: null\n  src/b.py: null\n  src/c.py: null\n",
    )
    calls: list[str] = []
    real = wiki_graph._git

    def spy(args, cwd):
        calls.append(args[0])
        return real(args, cwd)

    monkeypatch.setattr(wiki_graph, "_git", spy)
    assert cmd_stale(tmp_path) == 0
    assert calls.count("hash-object") == 1


def _nodes_for_repo(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/index.md", "wiki_id: index\ntitle: I\nrelated: [auth.jwt]\n")
    _node(
        tmp_path,
        "docs/jwt.md",
        "wiki_id: auth.jwt\ntitle: JWT\nsources:\n  src/auth/jwt.py: null\n",
    )
    return tmp_path


def test_nodes_for_exact_match(tmp_path: Path, capsys):
    root = _nodes_for_repo(tmp_path)
    assert wiki_graph.cmd_nodes_for(root, ["src/auth/jwt.py"]) == 0
    assert capsys.readouterr().out.splitlines() == ["src/auth/jwt.py\tauth.jwt"]


def test_nodes_for_directory_prefix_is_segment_bounded(tmp_path: Path, capsys):
    root = _nodes_for_repo(tmp_path)
    assert wiki_graph.cmd_nodes_for(root, ["src/auth", "src/auth-x"]) == 0
    # Covers `src/auth` and not the sibling `src/auth-x` (the same footgun as Invariant #6)
    assert capsys.readouterr().out.splitlines() == ["src/auth\tauth.jwt"]


def test_nodes_for_multiple_nodes_multiple_lines(tmp_path: Path, capsys):
    root = _nodes_for_repo(tmp_path)
    _node(
        root,
        "docs/session.md",
        "wiki_id: auth.session\ntitle: Session\nsources:\n  src/auth/jwt.py: null\n",
    )
    assert wiki_graph.cmd_nodes_for(root, ["src/auth/jwt.py"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert sorted(out) == [
        "src/auth/jwt.py\tauth.jwt",
        "src/auth/jwt.py\tauth.session",
    ]


def test_nodes_for_undocumented_path_is_silent_success(tmp_path: Path, capsys):
    root = _nodes_for_repo(tmp_path)
    assert wiki_graph.cmd_nodes_for(root, ["src/nowhere.py"]) == 0
    # Undocumented is a normal answer — a different contract from --neighbors' exit 1 on an
    # unknown id
    assert capsys.readouterr().out == ""


def test_nodes_for_without_wiki_is_noop(tmp_path: Path, capsys):
    assert wiki_graph.cmd_nodes_for(tmp_path, ["src/a.py"]) == 0
    assert capsys.readouterr().out == ""


def test_stale_is_noop_without_wiki(tmp_path: Path, capsys):
    assert cmd_stale(tmp_path) == 0
    assert json.loads(capsys.readouterr().out) == []


def test_stale_handles_mixed_key_types_in_sources(tmp_path: Path, capsys):
    """Mixed key types (int and str) in sources dict must be handled without crashing."""
    (tmp_path / "docs").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("x = 1\n", encoding="utf-8")
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    # Create a node with mixed key types: string path and numeric key (hand-written YAML slip)
    _node(
        tmp_path,
        "docs/a.md",
        'wiki_id: a.x\ntitle: A\nsources:\n  src/a.py: "abc1234"\n  42: "xyz9876"\n',
    )
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", "commit", "-qm", "seed"],
        cwd=tmp_path,
        check=True,
    )
    # Should not crash; should return 0 and process the valid key
    assert cmd_stale(tmp_path) == 0
    out_list = json.loads(capsys.readouterr().out)
    # Should have at least one entry (src/a.py is outdated; numeric key 42 is invalid path)
    assert len(out_list) >= 1
    assert any(e["source"] == "src/a.py" for e in out_list)


def test_broken_front_matter_with_marker_blocks_and_names_the_file(tmp_path: Path):
    # One missing quote kills the YAML. This document wrote a wiki_id, so it plainly meant to be
    # a node: letting it vanish silently makes --verify report exit 0 and turns /wiki-init §8's
    # "verify passes means the wiki is enforced" into a falsehood.
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/broken.md", "wiki_id: broken\ntitle: New: Doc\n")
    nodes = collect_nodes(tmp_path, load_wiki_config(tmp_path))
    problems = _check(tmp_path, nodes)
    assert any("docs/broken.md" in p and "읽지 못했습니다" in p for p in problems)


def test_broken_front_matter_without_marker_warns_but_never_blocks(tmp_path: Path):
    # With the parse dead, YAML cannot say whether a wiki_id was there. Absent a marker line in
    # the raw text the document may belong to someone else, so it does not block — the same
    # principle as Task 1.
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/theirs.md", "title: New: Doc\nsidebar_position: 1\n")
    wiki = load_wiki_config(tmp_path)
    nodes = collect_nodes(tmp_path, wiki)
    assert _check(tmp_path, nodes) == []
    warns = collect_warnings(wiki, nodes, build_graph(nodes), tmp_path)
    assert any("docs/theirs.md" in w and "읽지 못해" in w for w in warns)


def test_plain_markdown_is_not_reported_as_broken(tmp_path: Path):
    # A file with no opening `---`, or no closing one, has no front matter. A horizontal rule or
    # a setext underline on the first line is common, and counting those as broken turns the
    # warning into noise.
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    (tmp_path / "docs" / "plain.md").write_text("# 제목\n\n본문\n", encoding="utf-8")
    (tmp_path / "docs" / "rule.md").write_text("---\n\n본문만 있고 닫히지 않음\n", encoding="utf-8")
    wiki = load_wiki_config(tmp_path)
    nodes = collect_nodes(tmp_path, wiki)
    assert nodes == []
    assert collect_warnings(wiki, nodes, build_graph(nodes), tmp_path) == []


def test_empty_front_matter_is_not_reported_as_broken(tmp_path: Path):
    # An empty block, common Jekyll practice. safe_load returns None, but it is not broken —
    # simply not a node. Warning on it makes an ordinary doc tree noisy all over again.
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    (tmp_path / "docs" / "empty.md").write_text("---\n---\n\n본문\n", encoding="utf-8")
    (tmp_path / "docs" / "comment.md").write_text("---\n# 주석뿐\n---\n\n본문\n", encoding="utf-8")
    wiki = load_wiki_config(tmp_path)
    nodes = collect_nodes(tmp_path, wiki)
    assert nodes == []
    assert collect_warnings(wiki, nodes, build_graph(nodes), tmp_path) == []


def test_non_map_front_matter_is_still_reported_broken(tmp_path: Path):
    # None (empty block) is not broken, but a non-None non-map — a bare YAML list, here — still
    # is. Pins the `if front is None or isinstance(front, dict)` guard so it cannot be loosened
    # into skipping every non-dict yield, which would silently re-admit the exact "front matter
    # that parses to something other than a node" case this task exists to surface.
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/listy.md", "- a\n- b\n")
    wiki = load_wiki_config(tmp_path)
    nodes = collect_nodes(tmp_path, wiki)
    assert _check(tmp_path, nodes) == []  # no wiki_id line in the raw text -> warn, not block
    warns = collect_warnings(wiki, nodes, build_graph(nodes), tmp_path)
    assert any("docs/listy.md" in w and "읽지 못해" in w for w in warns)


def test_verify_no_longer_passes_silently_on_a_broken_node(tmp_path: Path):
    # The reproduced scenario: --build writing a graph without the broken document first
    # disables drift detection as well, and --verify then exits 0. Removing that silence is what
    # this test holds.
    _wiki_repo(tmp_path)
    _node(tmp_path, "docs/broken.md", "wiki_id: broken\ntitle: New: Doc\n")
    assert cmd_build(tmp_path) == 0
    assert cmd_verify(tmp_path) == 1


def test_structural_problem_output_is_capped(tmp_path: Path, capsys):
    # This output becomes the precommit deny reason verbatim (flow_gate_check.wiki_check_output).
    # Without a cap, 300 violating documents make a 300-line deny reason.
    _wiki_repo(tmp_path)
    for i in range(12):
        _node(tmp_path, f"docs/bad{i}.md", f"wiki_id: Bad_{i}\ntitle: T\n")
    assert cmd_build(tmp_path) == 0
    assert cmd_verify(tmp_path) == 1
    err = capsys.readouterr().err
    assert err.count("형식 위반") == 10
    assert "... 외 2건 (구조 위반)" in err


def test_validate_structure_itself_stays_uncapped(tmp_path: Path):
    # The cap belongs to the output stage. The pure function returns all of them, which is what
    # lets a test check all of them.
    nodes = [_mk(f"Bad_{i}", path=f"docs/bad{i}.md") for i in range(12)]
    assert len([p for p in _check(tmp_path, nodes) if "형식 위반" in p]) == 12


def test_drift_reason_survives_a_full_structural_cap(tmp_path: Path, capsys):
    # Capping the merged list lets 10 structure violations push the drift reason out, and the
    # author never sees one of the two ways to resolve it (fix the front matter, or --build).
    _wiki_repo(tmp_path)
    assert cmd_build(tmp_path) == 0
    for i in range(12):
        _node(tmp_path, f"docs/bad{i}.md", f"wiki_id: Bad_{i}\ntitle: T\n")
    assert cmd_verify(tmp_path) == 1
    err = capsys.readouterr().err
    assert "graph.yaml 이 front matter 와 어긋납니다" in err


def test_structural_problem_cap_boundary(tmp_path: Path, capsys):
    # Looking at the count alone misses `if structural > PROBLEM_CAP` flipping to `>=`; that
    # regression only skews the counter line. So both boundaries are pinned separately: at
    # exactly PROBLEM_CAP there must be no counter line at all, and only at one more than that
    # must it report exactly one.
    _wiki_repo(tmp_path)
    for i in range(PROBLEM_CAP):
        _node(tmp_path, f"docs/bad{i}.md", f"wiki_id: Bad_{i}\ntitle: T\n")
    assert cmd_build(tmp_path) == 0
    assert cmd_verify(tmp_path) == 1
    err = capsys.readouterr().err
    assert err.count("형식 위반") == PROBLEM_CAP
    # The "해소(구조 위반): ..." guidance line also contains "구조 위반", so the absence of the
    # counter line is checked through the "건 (구조 위반)" suffix, which only the counter has.
    assert "건 (구조 위반)" not in err

    _node(tmp_path, f"docs/bad{PROBLEM_CAP}.md", f"wiki_id: Bad_{PROBLEM_CAP}\ntitle: T\n")
    assert cmd_build(tmp_path) == 0
    assert cmd_verify(tmp_path) == 1
    err = capsys.readouterr().err
    assert err.count("형식 위반") == PROBLEM_CAP
    assert "... 외 1건 (구조 위반)" in err


# ---------------------------------------------------------------- derive_wiki_id

# The canonical example set. `test_wiki_init_step5_table_is_parity_tested` asserts
# wiki-init §5's table EQUAL to it — one source, so the table cannot silently shrink.
_EXAMPLES = {
    "docs/code-style/python.md": "code-style.python",
    "docs/a.b.md": "a-b",
    "docs/a/b.md": "a.b",
    "docs/api_spec.md": "api-spec",
    "docs/sds/README.md": "sds.readme",
    "docs/onboarding/README.md": "onboarding.readme",
}


def test_derive_wiki_id_examples():
    for path, expected in _EXAMPLES.items():
        assert wiki_graph.derive_wiki_id(path) == expected, path


def test_derive_wiki_id_root_prefix_is_optional():
    # `--derive-id docs/a.md` and `--derive-id a.md --root docs/` are the same call.
    assert wiki_graph.derive_wiki_id("a.b.md", "docs") == "a-b"
    assert wiki_graph.derive_wiki_id("docs/a.b.md", "docs/") == "a-b"


def test_derive_wiki_id_root_prefix_matches_segment_boundary():
    # docs-old/ is not prefixed by the root docs (the same shape as Invariant 6's path-prefix
    # footgun).
    assert wiki_graph.derive_wiki_id("docs-old/a.md", "docs") == "docs-old.a"


def test_derive_wiki_id_windows_separators():
    assert wiki_graph.derive_wiki_id("docs\\sds\\README.md", "docs") == "sds.readme"


def test_derive_wiki_id_rejects_degenerate_segment():
    # A Hangul-only name has nothing left after sanitizing. Emitting one blocks commits on a
    # duplicate id from the second such document onward — the very symptom this feature exists
    # to remove — so it is refused at the source.
    with pytest.raises(ValueError, match="영문"):
        wiki_graph.derive_wiki_id("docs/온보딩.md", "docs")


def test_derive_wiki_id_rejects_root_itself_and_empty():
    with pytest.raises(ValueError):
        wiki_graph.derive_wiki_id("docs", "docs")
    with pytest.raises(ValueError):
        wiki_graph.derive_wiki_id("", "docs")


def test_wiki_root_hint_ignores_the_enable_gate(tmp_path: Path):
    # The root is honored even under enable: false, because /harness-init may run before
    # /wiki-init (harness-rules 8-2). Going through load_wiki_config returns None there and
    # derives against docs silently.
    _write_config(tmp_path, "wiki:\n  enable: false\n  root: documentation/\n")
    assert wiki_graph._wiki_root_hint(tmp_path) == "documentation"


def test_wiki_root_hint_fails_soft_to_docs(tmp_path: Path):
    assert wiki_graph._wiki_root_hint(tmp_path) == "docs"  # no config
    _write_config(tmp_path, "wiki: [broken\n")
    assert wiki_graph._wiki_root_hint(tmp_path) == "docs"  # unparsable


# ---------------------------------------------------------------- --derive-id CLI


def test_derive_id_cli_prints_tab_pairs(capsys):
    # path<TAB>id pairs, not a positional zip, so a partial failure cannot shift the lines and
    # silently mismatch them.
    rc = wiki_graph.main(["--derive-id", "docs/a/b.md", "docs/a.b.md", "--root", "docs"])
    assert rc == 0
    assert capsys.readouterr().out.splitlines() == ["docs/a/b.md\ta.b", "docs/a.b.md\ta-b"]


def test_derive_id_cli_partial_failure_names_the_path(capsys):
    rc = wiki_graph.main(["--derive-id", "docs/ok.md", "docs/온보딩.md", "--root", "docs"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "docs/ok.md\tok" in captured.out  # the successes still go out
    assert "온보딩" in captured.err  # the failure names its path


def test_derive_id_cli_reads_config_root(tmp_path: Path, monkeypatch, capsys):
    _write_config(tmp_path, "wiki:\n  enable: false\n  root: documentation/\n")
    monkeypatch.setattr(wiki_graph, "host_root", lambda: tmp_path)
    rc = wiki_graph.main(["--derive-id", "documentation/api_spec.md"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "documentation/api_spec.md\tapi-spec"


def test_derive_id_cli_respects_an_explicit_empty_root(tmp_path: Path, monkeypatch, capsys):
    # `--root ""` is an explicit choice the caller typed, not "no --root given". Branching
    # on truthiness would silently fall back to the config/default root instead — the same
    # footgun `main()` already guards against for `--neighbors ""` (`is not None` there too).
    # With no root to strip, "docs/a.md" derives as "docs.a", not the "a" a default root
    # of "docs" would produce — that difference is what proves the empty root was honored.
    monkeypatch.setattr(wiki_graph, "host_root", lambda: tmp_path)
    rc = wiki_graph.main(["--derive-id", "docs/a.md", "--root", ""])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "docs/a.md\tdocs.a"


def test_derive_id_is_not_swallowed_by_fail_open(monkeypatch):
    # --derive-id is not a gate command. An internal exception failing open into exit 0 is a
    # "success with no output", and the caller falls back to deriving by hand — the failure mode
    # this command exists to remove.
    def _boom(paths, root_arg):
        raise RuntimeError("boom")

    monkeypatch.setattr(wiki_graph, "cmd_derive_id", _boom)
    with pytest.raises(RuntimeError):
        wiki_graph.main(["--derive-id", "docs/a.md"])


# ---------------------------------------------------------------- prose ↔ code parity

_REPO = Path(__file__).resolve().parents[1]
_TABLE_ROW_RE = re.compile(r"^\s*\|\s*`([^`]+\.md)`\s*\|\s*`([^`]+)`\s*\|", re.MULTILINE)
_ARROW_EXAMPLE_RE = re.compile(r"\b(docs/[^\s`]+?\.md)\s*(?:->|→)\s*([a-z0-9.-]+)")


# Only one file is read — wiki-init's SKILL.md — but this covers in advance the conventions of
# the other skills/ prose (indented fences, four backticks wrapping three: skills/flow,
# flow-init) and the `~~~` CommonMark allows. The opening fence comes back as a backreference,
# so inner three backticks cannot close a four-backtick block. A closing indent is accepted only
# at an absolute 0–3 columns or at the opener's +0–3: a fence inside a list measures its indent
# against the container, so the absolute branch alone cannot close its own pair, and an unbounded
# one terminates early on a deeper delimiter line inside the block. With no closer accepted, `\Z`
# swallows to end of file. Stripping too little leaks table rows; stripping too much removes the
# table and the assertions below fail loudly. The behaviour of each clause above, and the
# remaining divergence from CommonMark, are pinned to values by `_FENCE_CASES`.
_FENCE_RE = re.compile(
    r"^([ \t]*)(`{3,}|~{3,}).*?(?:^(?:[ ]{0,3}|\1[ ]{0,3})\2|\Z)", re.MULTILINE | re.DOTALL
)


def _step5_section(text: str) -> str:
    """wiki-init SKILL.md's §5 body, with fenced code blocks stripped out.

    Letting the table regex loose on the whole file drags in the same shape from other sections,
    the duplicate assertion below fires on a false positive, and the message misleads about the
    cause (that path is not duplicated in §5's table). Narrowing to the section is not enough: a
    fence is an example rather than prose, so a fence inside §5 quoting a table-row shape is the
    same false positive, and a fence line beginning `## 5.` at column 0 throws off the heading
    split as well.

    One cost on the stripping side: a row that sits BELOW the table behind an unpaired fence is
    stripped wholesale and never becomes a case. It is the one place where wiki-init SKILL.md
    §5's "adding a row adds a case" does not hold."""
    blocks = [
        b
        for b in re.split(r"^## ", _FENCE_RE.sub("", text), flags=re.MULTILINE)
        if b.startswith("5.")
    ]
    assert len(blocks) == 1, f"wiki-init SKILL.md 의 §5 블록이 {len(blocks)} 개다 (1 이어야)"
    return blocks[0]


def test_wiki_init_step5_table_is_parity_tested():
    # The table IS the case set: a prose example drifting from the implementation, or the table
    # quietly shrinking, is caught here.
    text = (_REPO / "skills" / "wiki-init" / "SKILL.md").read_text(encoding="utf-8")
    rows = _TABLE_ROW_RE.findall(_step5_section(text))
    # One unpaired fence and the non-greedy pairing marries it to the next section's opener,
    # swallowing the table in between, while the `## 5.` heading survives and the block guard
    # above stays silent. An empty table then passes the duplicate assertion below vacuously and
    # the failure shows up only on the last line, reading as "the table drifted".
    assert rows, "§5 표를 못 찾았다 — 펜스 짝을 확인하라"
    # Counted before folding into a dict: the same path on two rows leaves no trace once folded,
    # so the case set stays put while the table looks like it grew. SKILL.md is Markdown, with no
    # linter to catch a duplicate row.
    assert len({path for path, _ in rows}) == len(rows), "§5 표에 경로가 중복된 행이 있다"
    assert dict(rows) == _EXAMPLES


_STEP5_CALL_RE = re.compile(r"`python3\s+\S*wiki_graph\.py\s+([^`]+)`")


def test_wiki_init_step5_example_call_pins_the_root(tmp_path: Path, monkeypatch, capsys):
    # Step 5 derives ids before Step 7 has written wiki.root anywhere, so a call without
    # --root falls back to "docs": a user who chose website/docs gets website.docs.auth.jwt,
    # which is well-formed and unique, keeps --verify green forever, and is immutable. The
    # documented argv is RUN against a config naming another root — a substring assertion
    # would pass on a --root the CLI never honored, and on ids nobody checked.
    text = (_REPO / "skills" / "wiki-init" / "SKILL.md").read_text(encoding="utf-8")
    call = _STEP5_CALL_RE.search(_step5_section(text))
    assert call, "the --derive-id example call is gone from section 5"
    argv = call.group(1).split()

    _write_config(tmp_path, "wiki:\n  enable: true\n  root: documentation/\n")
    monkeypatch.setattr(wiki_graph, "host_root", lambda: tmp_path)
    assert wiki_graph.main(argv) == 0
    pairs = dict(line.split("\t") for line in capsys.readouterr().out.splitlines())
    assert pairs, "the example call derived no ids at all"
    assert pairs == {p: _EXAMPLES[p] for p in pairs}


# The test above does not exercise `_FENCE_RE`: its only input is wiki-init's SKILL.md, whose
# fences are a column-0 three-backtick pair outside §5, so it still passes with rows=6 even with
# the strip removed entirely. The shapes the regex claims to handle are exercised only here, so
# blocking a new shape means adding a case with it. Each case breaks if one clause of the regex
# is dropped. A "though" in a label marks a reading that diverges from CommonMark — pinned to a
# value so a change is visible — and those cases exercise clauses too, some of them the only
# guard a clause has.
_FENCE_IN = "| `docs/in.md` | `in` |"
_FENCE_KEEP = "| `docs/keep.md` | `keep` |"
_FENCE_CASES = [
    (f"   ```md\n   {_FENCE_IN}\n   ```\n\n{_FENCE_KEEP}\n", ["docs/keep.md"], "indented fence"),
    (f"~~~md\n{_FENCE_IN}\n~~~\n\n{_FENCE_KEEP}\n", ["docs/keep.md"], "tilde fence"),
    (
        f"````md\n```\n{_FENCE_IN}\n```\n````\n\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "four-backtick wrapper",
    ),
    (
        f"```text\n    ```\n{_FENCE_IN}\n```\n\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "a delimiter indented 4 inside a fence does not close it",
    ),
    # Wrapping in a list is what makes the label match the machinery: at top level CommonMark
    # does not read an opener indented 4+ as a fence at all (after a blank line it is an indented
    # code block, after a paragraph a lazy continuation), so there is nothing to "close".
    (
        f"- item\n\n     ```bash\n     {_FENCE_IN}\n     ```\n\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "a list-nested block indented past 3 closes itself",
    ),
    (
        f"  ```bash\n  {_FENCE_IN}\n```\n\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "an indented block closes at column 0",
    ),
    # The closer sits at an absolute 3 columns, which the relative branch (wanting 5) cannot
    # accept, so this exercises the top of the absolute window. The bottom is covered by the
    # column-0 case above.
    (
        f"- item\n\n     ```bash\n     {_FENCE_IN}\n   ```\n\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "a list-nested block closes at a shallower absolute indent",
    ),
    # The row-level answers agree by coincidence: the block becomes indented code and the rows
    # fall outside the prose, not because a fence closed. Move only the closer to column 0 and
    # the two readings become disjoint.
    (
        f"\t```md\n\t{_FENCE_IN}\n\t```\n\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "a tab-indented fence opens, though CommonMark reads it as an indented code block",
    ),
    (
        f"```md\n{_FENCE_IN}\n\t```\n\n{_FENCE_KEEP}\n",
        [],
        "a tab-indented delimiter does not close a space-opened fence",
    ),
    (
        f"prose ``` prose\n\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "a backtick run away from line start opens nothing",
    ),
    (
        f"``a`` inline\n\n{_FENCE_KEEP}\n\n``b`` inline\n",
        ["docs/keep.md"],
        "an inline double-backtick run opens nothing",
    ),
    (
        f"~~struck~~ text\n\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "a strikethrough run opens nothing",
    ),
    (
        f"````md\n```\n{_FENCE_IN}\n```\n\n{_FENCE_KEEP}\n",
        [],
        "an unclosed fence swallows to end of input, following rows included",
    ),
    (
        f"1. item\n\n   ```text\n   {_FENCE_IN}\n      ```\n\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "a list-nested fence closes within 3 past its opening indent",
    ),
    # The same absolute coordinates as just above diverge from CommonMark once they are at top
    # level: the regex knows nothing of containers, so it closes both.
    (
        f"{_FENCE_KEEP}\n\n   ```text\n   | `docs/body.md` | `body` |\n      ```\n{_FENCE_IN}\n",
        ["docs/keep.md", "docs/in.md"],
        "a closer within 3 of the opening indent closes, though CommonMark reads it as content",
    ),
    (
        f"```md\n{_FENCE_IN}\n``` xyz\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "a closer with trailing text closes, though CommonMark reads on",
    ),
]
# The same input arriving twice makes one side's coverage imaginary however the labels differ,
# and there is a genuinely one-line-apart pair above (the four-backtick wrapper against its
# unclosed variant).
assert len({doc for doc, _, _ in _FENCE_CASES}) == len(_FENCE_CASES)


@pytest.mark.parametrize(
    ("doc", "expected"),
    [(doc, expected) for doc, expected, _ in _FENCE_CASES],
    ids=[label for _, _, label in _FENCE_CASES],
)
def test_fence_stripping_leaves_exactly_the_rows_outside_fences(doc, expected):
    assert [path for path, _ in _TABLE_ROW_RE.findall(_FENCE_RE.sub("", doc))] == expected


# A template that does not use {{ID}} carries its wiki_id literally, and drifts silently when
# the derivation rule changes. Each is compared against the value derived from its canonical
# output path (from its own comment and the harness-authoring convention).
_LITERAL_ID_TEMPLATES = {
    "docs-readme.template.md": "docs/README.md",
    "onboarding.template.md": "docs/onboarding/README.md",
}


def test_template_literal_ids_are_parity_tested():
    # The map is DERIVED FROM THE TEMPLATE SET rather than held by hand, so a new literal-id
    # template is caught here first — the same failure mode the comment test just below guards
    # against.
    tpl_dir = _REPO / "skills" / "harness-authoring" / "templates"
    literal = {}
    for tpl in sorted(tpl_dir.glob("*.template.md")):
        m = re.search(r"^wiki_id: (\S+)$", tpl.read_text(encoding="utf-8"), re.MULTILINE)
        if m is not None and m.group(1) != "{{ID}}":
            literal[tpl.name] = m.group(1)
    assert set(literal) == set(_LITERAL_ID_TEMPLATES), (
        f"리터럴 wiki_id 템플릿 집합이 바뀌었다 — 출력 경로를 맵에 등록하라: {sorted(literal)}"
    )
    for name, wid in literal.items():
        assert wiki_graph.derive_wiki_id(_LITERAL_ID_TEMPLATES[name], "docs") == wid, name


def test_template_comment_examples_are_parity_tested():
    # The worked examples in the harness-authoring templates' YAML comments (docs/x.md -> id, or
    # written with →) follow the same rule. Asserted per template: a floor on the total lets one
    # {{ID}} template lose its example while another template's count fills the floor back in
    # (reproduced by changing only the sds template's `->` to `→`, which under the old regex took
    # the total from 3 to 2 — still above a floor of 2).
    tpl_dir = _REPO / "skills" / "harness-authoring" / "templates"
    id_templates = [
        tpl
        for tpl in sorted(tpl_dir.glob("*.template.md"))
        if "{{ID}}" in tpl.read_text(encoding="utf-8")
    ]
    assert id_templates, "{{ID}} 를 쓰는 템플릿이 없다"
    for tpl in id_templates:
        matches = _ARROW_EXAMPLE_RE.findall(tpl.read_text(encoding="utf-8"))
        assert matches, f"{tpl.name}: wiki_id 워크드 예제가 사라졌다"
        for path, expected in matches:
            assert wiki_graph.derive_wiki_id(path, "docs") == expected, tpl.name
