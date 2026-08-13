import json
import re
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
    # 노드 경로는 relative_to(root).as_posix() 로 만들어진다. root 를 날것으로 두면
    # './docs/' 는 index 경로 './docs/index.md' 를 낳고 어떤 노드 경로와도 같아질 수 없어,
    # orphan 검사가 저장소 전체에서 조용히 꺼진다.
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
    assert node["line_count"] == 8  # --- id title --- 빈줄 가 나 다
    assert node["front"]["title"] == "JWT"


def test_collect_nodes_strips_utf8_bom(tmp_path: Path):
    # Windows 에디터가 남기는 BOM(﻿)이 "---" 앞에 붙으면 plain utf-8 로는 그대로
    # 살아남아 parse_front_matter 의 startswith 검사를 조용히 깨뜨린다 — 노드가 경고 없이
    # graph 에서 사라진다 (Invariant #2, Windows 에서만 재현·permissive 방향으로 틀림).
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/index.md", "wiki_id: index\ntitle: Index\n")
    bommed = tmp_path / "docs" / "auth.md"
    fm = "---\nwiki_id: auth.jwt\ntitle: JWT\n---\n\n본문\n"
    bommed.write_bytes(b"\xef\xbb\xbf" + fm.encode())
    nodes = collect_nodes(tmp_path, load_wiki_config(tmp_path))
    assert sorted(n["id"] for n in nodes) == ["auth.jwt", "index"]


def test_collect_nodes_keeps_document_missing_marker(tmp_path: Path):
    # id 누락은 여기서 거르지 않는다 — 노드는 아니지만 경고로 보이게 해야 하므로 실어 보낸다.
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
    # Front Matter 는 경로→sha map, graph 는 경로 리스트. sha 만 바뀐 동기화가
    # graph drift 로 오인되지 않게 하는 것이 목적이다.
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
    # 전용 키를 썼다는 건 노드로 의도했다는 뜻이므로 더 이상 모호하지 않다 — 차단이 옳다.
    assert any("형식" in p and "wiki_id" in p for p in _check(tmp_path, [_mk("Auth.JWT")]))


def test_foreign_id_front_matter_is_not_a_node_and_never_blocks(tmp_path: Path):
    # Docusaurus 의 `id:` 는 문서화된 1급 front matter 필드이고, wiki.root 기본값과
    # Docusaurus 기본 문서 경로는 둘 다 docs/ 다. 이것을 노드로 보면 형식 위반으로 판정되어
    # 저장소의 모든 커밋이 영구히 막힌다 — wiki 게이트는 docs 티어에도 걸려 있다.
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/getting-started.md", "id: Getting_Started\nsidebar_position: 1\n")
    nodes = collect_nodes(tmp_path, load_wiki_config(tmp_path))
    assert [n["id"] for n in nodes] == [None]
    assert _check(tmp_path, nodes) == []


def test_non_string_wiki_id_blocks(tmp_path: Path):
    # YAML 1.1 은 전용 키라도 문다: `wiki_id: 0123456` 은 octal 이라 정수 42798 이 되고,
    # 그 문자열화 "42798" 은 WIKI_ID_RE 를 통과해 아무도 쓰지 않은 유효해 보이는 id 가 된다.
    node = {
        "id": "42798",
        "path": "docs/a.md",
        "line_count": 3,
        "front": {"wiki_id": 42798, "title": "T"},
    }
    assert any("wiki_id" in p and "문자열" in p for p in _check(tmp_path, [node]))


def test_front_matter_without_id_warns_capped(tmp_path: Path):
    # "related" 는 WIKI_ONLY_FIELDS 라 노드로 의도했다는 신호가 있다 — 그래야 경고가 뜬다.
    nodes = [
        {"id": None, "path": f"docs/f{i}.md", "line_count": 3, "front": {"related": ["x"]}}
        for i in range(5)
    ]
    warns = collect_warnings({"index": "docs/index.md"}, nodes, build_graph(nodes))
    assert sum(1 for w in warns if "wiki_id 가 없어" in w) == 3  # 3건만 나열
    assert any("외 2건" in w for w in warns)  # 나머지는 건수로


def test_missing_marker_warns_only_when_wiki_fields_are_present(tmp_path: Path):
    # 전용 키로 바꾸면 "front matter 는 있는데 노드가 아니다" 가 정상 상태다. Docusaurus
    # 저장소에서 전수 경고는 매 커밋 영구 노이즈가 된다. related 를 손으로 썼다는 것만이
    # 노드로 쓰려던 의도의 증거다.
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
    # related 는 양방향 수동이므로 서로 가리키는 것이 정상이다. 순환 검사 대상이 아니다.
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
    # 설계(§2)가 명시적으로 거부한 모양 — sources 는 map 이어야 한다. 리스트로 손으로 쓰는
    # 것이 가장 그럴듯한 실수이므로, 없는 경로 검사와 별개로 형태 자체를 block 해야 한다.
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
    # 기존 문구는 참조자만 지목해서, 저자가 멀쩡한 index.md 를 들여다보게 만들었다.
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
    # 실존하지 않는 id 를 인접에 실으면, 같은 오타를 가리키는 두 노드가 orphan 판정에서
    # 서로 연결된 것으로 세어진다 — index 에서 도달 불가인 노드가 도달 가능으로 보인다.
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
    # index 가 노드로 해석되지 않으면 개별 노드를 orphan 이라고 오판해서는 안 된다 —
    # 도달 가능성 자체를 계산할 기준점이 없기 때문이다.
    nodes = [
        _mk("a.x", path="docs/a.md"),
        _mk("b.x", path="docs/b.md"),
    ]
    warns = collect_warnings(_wiki(index="docs/missing.md"), nodes, build_graph(nodes))
    assert not any("'a.x'" in w or "'b.x'" in w for w in warns)


def test_index_not_a_node_warns_the_check_is_off():
    # wiki 가 켜진 상태에서 index 가 노드로 해석되지 않으면, orphan 검사 자체가 조용히
    # 꺼져 있다는 것을 운영자에게 알려야 한다 (block 이 아니라 warn).
    nodes = [_mk("a.x", path="docs/a.md")]
    warns = collect_warnings(_wiki(index="docs/missing.md"), nodes, build_graph(nodes))
    assert any("docs/missing.md" in w for w in warns)


def test_index_not_a_node_is_silent_when_there_are_no_nodes():
    # 노드가 아예 없으면 검사할 것도 없다 — 빈 wiki 에 노이즈를 내지 않는다.
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
    # 0 + 빈 stdout 이면 "이웃 없음"과 구별되지 않아, 호출자가 조회 실패를
    # '조화시킬 문서가 없음'으로 읽고 그냥 넘어간다. 게이트는 --neighbors 를 부르지 않으므로
    # 여기서 1 을 내도 커밋을 막지 않는다.

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
    # 재현된 구체 시나리오: index.md 가 BOM 을 달고 있으면 index 자신이 노드에서 빠져
    # _index_id 가 None 을 반환하고, orphan 검사가 저장소 전체에서 조용히 꺼진다.
    _wiki_repo(tmp_path)
    idx = tmp_path / "docs" / "index.md"
    idx.write_bytes(b"\xef\xbb\xbf" + idx.read_bytes())
    assert cmd_build(tmp_path) == 0
    gp = graph_path(tmp_path, load_wiki_config(tmp_path))
    import yaml as _yaml

    graph = _yaml.safe_load(gp.read_text(encoding="utf-8"))
    assert len(graph["nodes"]) == 2  # BOM 이전과 동일 — index 노드가 사라지지 않는다


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
    # 게이트의 런타임 하한은 python 3.8 (check-deps.sh / precommit-runner.sh) 인데
    # Path.write_text(newline=…) 는 3.10 에 생겼다. 3.9 호스트에서는 TypeError 가 나고
    # main() 의 FAIL-OPEN 이 그것을 exit 0 으로 삼켜, --build 가 아무것도 안 쓴 채
    # 성공한 것처럼 보인다 — 그 뒤 --verify 는 영원히 모든 커밋을 막는다.
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
    # PyYAML 은 버전마다 emitter 출력이 미묘하게 다르다. 바이트로 비교하면 의미가 같은
    # graph.yaml 이 drift 로 읽혀, A 가 커밋하면 B 가 막히고 B 가 다시 빌드하면 A 가
    # 막히는 왕복이 된다. 판정 기준은 파싱 결과여야 한다.
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
    assert gp.read_bytes() != canonical  # 바이트는 다르다
    assert cmd_verify(tmp_path) == 0  # 의미는 같으므로 통과


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
    # --verify 는 읽기 전용이다 — 커밋 게이트가 부르는 쪽이 graph.yaml 을 쓰기 시작하면
    # doc-sync 만 build 를 부른다는 설계 전제가 깨진다.
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
    # 파싱은 되지만 map 이 아니거나 nodes/edges 가 map 이 아닌 형태 — _drifted_paths 가
    # AttributeError 를 내면 안 된다. 판별은 못 해도(빈 목록) drift 판정 자체는 유지된다.
    _wiki_repo(tmp_path)
    cmd_build(tmp_path)
    gp = graph_path(tmp_path, load_wiki_config(tmp_path))
    for bad in ("- a\n- b\n", "just text\n", "nodes: [a, b]\n", "edges: [x]\n"):
        gp.write_text(bad, encoding="utf-8")
        assert cmd_verify(tmp_path) == 1, f"crashed or passed on: {bad!r}"


def test_unreadable_graph_yaml_is_drift_not_crash(tmp_path: Path, capsys):
    # UnicodeDecodeError 를 내는 graph.yaml — 못 읽는 파일은 "최신"의 증거가 아니므로
    # 조용히 건너뛰지 않고 drift 로 보고해 block 해야 한다.
    _wiki_repo(tmp_path)
    cmd_build(tmp_path)
    gp = graph_path(tmp_path, load_wiki_config(tmp_path))
    gp.write_bytes(b"\xff\xfe\xfd\xfc not valid utf-8")
    assert cmd_verify(tmp_path) == 1
    err = capsys.readouterr().err
    assert "graph.yaml" in err and "읽을 수 없습니다" in err


def test_verify_blocks_on_structure_violation(tmp_path: Path, capsys):
    # bad.md 를 build 뒤에 추가하기만 하면 drift 만으로 이미 exit 1 이 강제되어, 이 테스트는
    # validate_structure 호출을 지워도 통과해 버린다 — bad.md 를 넣은 채로 rebuild 해서
    # drift 를 없앤 뒤에야 '구조 위반 때문에' 막혔다고 주장할 수 있다.
    _wiki_repo(tmp_path)
    _node(tmp_path, "docs/bad.md", "wiki_id: BAD\ntitle: Bad\n")
    _node(tmp_path, "docs/defects/skew.md", "wiki_id: defect.skew\ntitle: Skew\n")
    cmd_build(tmp_path)
    assert cmd_verify(tmp_path) == 1
    err = capsys.readouterr().err
    assert "BAD" in err and "형식" in err
    # validate_structure 는 validate_defects 를 이미 내부에서 구성한다 — cmd_verify 가 둘
    # 다 부르면 defect 위반이 두 번 보고된다.
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
    # '어긋났다'가 아니라 '어느 문서가 어긋났다'를 말해야 한다. 아무 노드나 집으면
    # 무관한 파일을 지목해 오히려 오해를 키운다.
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
    # main() 의 exit code 가 곧 게이트의 판정이다 — 이 모듈 어디서든 나는 예외가 저장소를
    # 통째로 막으면 안 된다 (Invariant #1: wiki 는 missing-dependency·unclassified-commit·
    # merge-strategy 세 예외에 속하지 않는다).

    monkeypatch.setattr(wiki_graph, "host_root", lambda: tmp_path)

    def _boom(root):
        raise RuntimeError("boom")

    monkeypatch.setattr(wiki_graph, "load_wiki_config", _boom)
    assert wiki_graph.main(["--verify"]) == 0
    assert "boom" in capsys.readouterr().err


def test_main_routes_an_empty_neighbors_id_to_the_lookup(tmp_path: Path, monkeypatch, capsys):
    # 진위값으로 갈랐더니 `--neighbors ""` 가 조용히 cmd_verify 로 떨어졌다: 호출자는
    # 조회 결과가 비었다고 읽는 동안 실제로는 그래프 검증이 돌고 있었고, drift 면 1 을
    # 돌려줘 조회 실패로 보였다. 종료 코드는 양쪽 다 1 이라 stderr 로만 구별된다.

    _wiki_repo(tmp_path)  # graph.yaml 을 만들지 않았으므로 verify 로 새면 drift 로 실패한다
    monkeypatch.setattr(wiki_graph, "host_root", lambda: tmp_path)
    assert wiki_graph.main(["--neighbors", ""]) == 1
    err = capsys.readouterr().err
    assert "알 수 없는 id" in err
    assert "검증 실패" not in err


def test_main_argparse_error_still_exits_nonzero():
    # argparse 사용법 오류는 SystemExit 이라 finding 5 의 `except Exception` 가드를 그대로
    # 통과해야 한다 — 게이트가 이 커맨드를 직접 구성하므로 실무에서는 발생하지 않지만,
    # 가드가 SystemExit 까지 삼켜버리는 회귀를 잡아 둔다.
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
    return subprocess.run(
        ["git", "log", "-1", "--format=%H", "--", "src/a.py"],
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
    # 따옴표 하나 빠지면 YAML 이 죽는다. 이 문서는 wiki_id 를 썼으니 노드로 의도한 것이
    # 명백하다 — 조용히 사라지면 --verify 가 exit 0 을 보고하고, /wiki-init 8절의
    # "verify 통과 = wiki 강제됨" 이 거짓이 된다.
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/broken.md", "wiki_id: broken\ntitle: New: Doc\n")
    nodes = collect_nodes(tmp_path, load_wiki_config(tmp_path))
    problems = _check(tmp_path, nodes)
    assert any("docs/broken.md" in p and "읽지 못했습니다" in p for p in problems)


def test_broken_front_matter_without_marker_warns_but_never_blocks(tmp_path: Path):
    # 파싱이 죽었으니 wiki_id 가 있었는지 YAML 로는 알 수 없다. 원문에 마커 줄이 없으면
    # 남의 문서일 수 있으므로 차단하지 않는다 — Task 1 과 같은 원칙이다.
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/theirs.md", "title: New: Doc\nsidebar_position: 1\n")
    wiki = load_wiki_config(tmp_path)
    nodes = collect_nodes(tmp_path, wiki)
    assert _check(tmp_path, nodes) == []
    warns = collect_warnings(wiki, nodes, build_graph(nodes), tmp_path)
    assert any("docs/theirs.md" in w and "읽지 못해" in w for w in warns)


def test_plain_markdown_is_not_reported_as_broken(tmp_path: Path):
    # 여는 `---` 가 없거나 닫는 `---` 가 없는 파일은 front matter 가 아니다. 문서 첫 줄의
    # 수평선·setext 밑줄이 흔하고, 이것까지 깨진 것으로 세면 경고가 노이즈가 된다.
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    (tmp_path / "docs" / "plain.md").write_text("# 제목\n\n본문\n", encoding="utf-8")
    (tmp_path / "docs" / "rule.md").write_text("---\n\n본문만 있고 닫히지 않음\n", encoding="utf-8")
    wiki = load_wiki_config(tmp_path)
    nodes = collect_nodes(tmp_path, wiki)
    assert nodes == []
    assert collect_warnings(wiki, nodes, build_graph(nodes), tmp_path) == []


def test_empty_front_matter_is_not_reported_as_broken(tmp_path: Path):
    # Jekyll 관례로 흔한 빈 블록이다. safe_load 가 None 을 돌려주지만 깨진 것이 아니라
    # 그냥 노드가 아니다 — 이걸 경고하면 평범한 문서 트리 전체가 다시 노이즈가 된다.
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
    # 재현된 시나리오: --build 가 깨진 문서를 뺀 그래프를 먼저 쓰면 drift 탐지도 무력화되어
    # --verify 가 exit 0 을 낸다. 그 무음을 없앤 것이 이 테스트의 대상이다.
    _wiki_repo(tmp_path)
    _node(tmp_path, "docs/broken.md", "wiki_id: broken\ntitle: New: Doc\n")
    assert cmd_build(tmp_path) == 0
    assert cmd_verify(tmp_path) == 1


def test_structural_problem_output_is_capped(tmp_path: Path, capsys):
    # 이 출력이 그대로 precommit deny 사유가 된다 (flow_gate_check.wiki_check_output).
    # 캡이 없으면 문서 300 개가 위반일 때 deny 사유가 300 줄이다.
    _wiki_repo(tmp_path)
    for i in range(12):
        _node(tmp_path, f"docs/bad{i}.md", f"wiki_id: Bad_{i}\ntitle: T\n")
    assert cmd_build(tmp_path) == 0
    assert cmd_verify(tmp_path) == 1
    err = capsys.readouterr().err
    assert err.count("형식 위반") == 10
    assert "... 외 2건 (구조 위반)" in err


def test_validate_structure_itself_stays_uncapped(tmp_path: Path):
    # 캡은 출력 단계의 것이다. 순수 함수는 전수를 돌려줘야 테스트가 전수를 확인할 수 있다.
    nodes = [_mk(f"Bad_{i}", path=f"docs/bad{i}.md") for i in range(12)]
    assert len([p for p in _check(tmp_path, nodes) if "형식 위반" in p]) == 12


def test_drift_reason_survives_a_full_structural_cap(tmp_path: Path, capsys):
    # 합쳐진 리스트에 캡을 걸면 구조 위반 10 건이 drift 사유를 밀어내고, 저자는 두 해소
    # 경로(front matter 수정 / --build) 중 하나를 보지 못한다.
    _wiki_repo(tmp_path)
    assert cmd_build(tmp_path) == 0
    for i in range(12):
        _node(tmp_path, f"docs/bad{i}.md", f"wiki_id: Bad_{i}\ntitle: T\n")
    assert cmd_verify(tmp_path) == 1
    err = capsys.readouterr().err
    assert "graph.yaml 이 front matter 와 어긋납니다" in err


def test_structural_problem_cap_boundary(tmp_path: Path, capsys):
    # count 만 보면 `if structural > PROBLEM_CAP`이 `>=` 로 뒤집혀도 안 걸린다 — 그 회귀는
    # 카운터 문구만 어긋나게 만든다. 그래서 여기서는 두 경계를 각각 고정한다: 정확히
    # PROBLEM_CAP 건에서는 카운터 줄 자체가 없어야 하고, 그보다 하나 많을 때만 정확히
    # 1건을 보고해야 한다.
    _wiki_repo(tmp_path)
    for i in range(PROBLEM_CAP):
        _node(tmp_path, f"docs/bad{i}.md", f"wiki_id: Bad_{i}\ntitle: T\n")
    assert cmd_build(tmp_path) == 0
    assert cmd_verify(tmp_path) == 1
    err = capsys.readouterr().err
    assert err.count("형식 위반") == PROBLEM_CAP
    # "해소(구조 위반): ..." 안내문에도 "구조 위반"이 들어 있으므로, 카운터 줄에만 있는
    # "건 (구조 위반)" 접미사로 좁혀서 카운터 줄의 부재를 확인한다.
    assert "건 (구조 위반)" not in err

    _node(tmp_path, f"docs/bad{PROBLEM_CAP}.md", f"wiki_id: Bad_{PROBLEM_CAP}\ntitle: T\n")
    assert cmd_build(tmp_path) == 0
    assert cmd_verify(tmp_path) == 1
    err = capsys.readouterr().err
    assert err.count("형식 위반") == PROBLEM_CAP
    assert "... 외 1건 (구조 위반)" in err


# ---------------------------------------------------------------- derive_wiki_id

# The canonical example set. wiki-init §5's table is asserted EQUAL to this by the
# parity test a later task adds — one source, so the table cannot silently shrink.
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
    # `--derive-id docs/a.md` 와 `--derive-id a.md --root docs/` 는 같은 호출이다.
    assert wiki_graph.derive_wiki_id("a.b.md", "docs") == "a-b"
    assert wiki_graph.derive_wiki_id("docs/a.b.md", "docs/") == "a-b"


def test_derive_wiki_id_root_prefix_matches_segment_boundary():
    # docs-old/ 는 root docs 의 접두가 아니다 (불변식 6 의 path-prefix footgun 과 동형).
    assert wiki_graph.derive_wiki_id("docs-old/a.md", "docs") == "docs-old.a"


def test_derive_wiki_id_windows_separators():
    assert wiki_graph.derive_wiki_id("docs\\sds\\README.md", "docs") == "sds.readme"


def test_derive_wiki_id_rejects_degenerate_segment():
    # 한글만인 이름은 정규화 후 남는 글자가 없다 — 방출하면 한글 문서 둘부터
    # duplicate-id 로 커밋이 막히므로 (이 기능이 없애려는 증상) 원천 거부.
    with pytest.raises(ValueError, match="영문"):
        wiki_graph.derive_wiki_id("docs/온보딩.md", "docs")


def test_derive_wiki_id_rejects_root_itself_and_empty():
    with pytest.raises(ValueError):
        wiki_graph.derive_wiki_id("docs", "docs")
    with pytest.raises(ValueError):
        wiki_graph.derive_wiki_id("", "docs")


def test_wiki_root_hint_ignores_the_enable_gate(tmp_path: Path):
    # enable: false 여도 root 는 존중 — /harness-init 은 /wiki-init 전에 돌 수 있다
    # (harness-rules 8-2). load_wiki_config 를 거치면 None 이라 조용히 docs 로 파생한다.
    _write_config(tmp_path, "wiki:\n  enable: false\n  root: documentation/\n")
    assert wiki_graph._wiki_root_hint(tmp_path) == "documentation"


def test_wiki_root_hint_fails_soft_to_docs(tmp_path: Path):
    assert wiki_graph._wiki_root_hint(tmp_path) == "docs"  # config 없음
    _write_config(tmp_path, "wiki: [broken\n")
    assert wiki_graph._wiki_root_hint(tmp_path) == "docs"  # 파싱 불가


# ---------------------------------------------------------------- --derive-id CLI


def test_derive_id_cli_prints_tab_pairs(capsys):
    # 위치 zip 이 아니라 경로<TAB>id 쌍 — 부분 실패 시 줄 밀림으로 조용히 어긋나지 않게.
    rc = wiki_graph.main(["--derive-id", "docs/a/b.md", "docs/a.b.md", "--root", "docs"])
    assert rc == 0
    assert capsys.readouterr().out.splitlines() == ["docs/a/b.md\ta.b", "docs/a.b.md\ta-b"]


def test_derive_id_cli_partial_failure_names_the_path(capsys):
    rc = wiki_graph.main(["--derive-id", "docs/ok.md", "docs/온보딩.md", "--root", "docs"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "docs/ok.md\tok" in captured.out  # 성공분은 그대로 나간다
    assert "온보딩" in captured.err  # 실패분은 경로를 지목한다


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
    # --derive-id 는 게이트 명령이 아니다 — 내부 예외가 fail-open 으로 exit 0 이 되면
    # "출력 없는 성공"이고, 호출자는 손 파생으로 회귀한다 (이 명령이 없애려는 실패 모드).
    def _boom(paths, root_arg):
        raise RuntimeError("boom")

    monkeypatch.setattr(wiki_graph, "cmd_derive_id", _boom)
    with pytest.raises(RuntimeError):
        wiki_graph.main(["--derive-id", "docs/a.md"])


# ---------------------------------------------------------------- prose ↔ code parity

_REPO = Path(__file__).resolve().parents[1]
_TABLE_ROW_RE = re.compile(r"^\s*\|\s*`([^`]+\.md)`\s*\|\s*`([^`]+)`\s*\|", re.MULTILINE)
_ARROW_EXAMPLE_RE = re.compile(r"\b(docs/[^\s`]+?\.md)\s*(?:->|→)\s*([a-z0-9.-]+)")


def test_wiki_init_step5_table_is_parity_tested():
    # 표가 곧 테스트 케이스다 — 산문 예제가 구현과 어긋나거나 표가 조용히 줄면 여기서 걸린다.
    text = (_REPO / "skills" / "wiki-init" / "SKILL.md").read_text(encoding="utf-8")
    assert dict(_TABLE_ROW_RE.findall(text)) == _EXAMPLES


def test_template_comment_examples_are_parity_tested():
    # harness-authoring 템플릿 YAML 주석의 워크드 예제 (docs/x.md -> id 또는 → 표기)도 같은
    # 규칙. 템플릿별로 개별 단언한다 — 합계에 바닥값만 걸면, {{ID}} 를 쓰는 템플릿 중 하나가
    # 예제를 잃어도 다른 템플릿의 예제 수가 바닥을 채워 조용히 통과한다(재현: sds 템플릿의
    # `->` 를 `→` 로만 바꿔도 예전 정규식으로는 합계가 3→2 로 줄어 바닥값 2를 여전히 넘긴다).
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
