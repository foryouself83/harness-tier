from pathlib import Path

from scripts.wiki_graph import (
    build_graph,
    collect_nodes,
    collect_warnings,
    dump_graph,
    load_wiki_config,
)
from tests.wiki_graph._helpers import _node, _write_config


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
