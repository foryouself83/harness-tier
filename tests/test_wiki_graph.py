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


def test_front_matter_ruler_first_line_is_not_a_block():
    # `----` 는 여는 구분자가 아니다 — find("\n---") 시절 hr 로 시작하는 문서가
    # "깨진 front matter" 경고로 잡히던 케이스.
    assert wiki_graph._front_matter_block("----\n제목\n----\n본문\n") is None


def test_front_matter_crlf_closing_line():
    text = "---\r\nwiki_id: a\r\ntitle: T\r\n---\r\n\r\n본문\r\n"
    assert parse_front_matter(text) == {"wiki_id": "a", "title": "T"}


def test_front_matter_closing_line_tolerates_trailing_blanks():
    text = "---\nwiki_id: a\ntitle: T\n---  \n본문\n"
    assert parse_front_matter(text) == {"wiki_id": "a", "title": "T"}


def test_front_matter_body_dashes_line_does_not_close_early():
    # 블록 안 열 0 의 `--- note` 줄은 닫는 구분자가 아니다. 조기 종결은 wiki_id 를
    # 조용히 블록 밖으로 밀어내 노드가 소리 없이 사라지게 했다.
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
    # 기록 값 = working tree blob → fresh. 파일 내용이 바뀌면(커밋 불필요) stale — 판정이
    # 커밋 이력이 아니라 내용에 붙는다 (squash/rebase 승격이 가짜 stale 을 못 만든다).
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
    # 구형 기록(커밋 sha) → migrated == `git rev-parse <커밋>:<경로>` (그 시점 blob).
    # 내용 무변경이어도 항목이 나온다 — doc-sync 가 마커만 재작성해 저장소가 수렴하도록.
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
    # GC 로 사라진 커밋(타입 조회 불가) → migrated: null — 일반 stale 로 본문 동기화 대상.
    _git_repo_with_source(tmp_path, "f" * 40)
    assert cmd_stale(tmp_path) == 0
    (entry,) = json.loads(capsys.readouterr().out)
    assert entry["migrated"] is None


def _stamp_repo(tmp_path: Path) -> Path:
    """repo + 커밋된 노드 1개(sources 에 working-tree blob 기록) + 매칭 graph.yaml."""
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
    assert cmd_build(root) == 0  # graph 는 일치시켜 도장 위반만 남긴다
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
    # old 가 커밋 sha, new == `git rev-parse <old>:<src>` → 의미보존 재작성 허용 (spec §2).
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
    # 차단 메시지가 권하는 amend 경로 그 자체 — 본문 동기화를 이미 커밋했다면 HEAD 는 그
    # 본문을 들고 있으므로 남은 델타는 sha 뿐이다. 이것을 막으면 권고안이 실행 불가가 되고,
    # split-commit(본문 커밋 → 도장 커밋)도 같은 모양이라 함께 열린다.
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
    # 위 허용이 검사를 통째로 열어버리지 않는지 — 직전 커밋이 그 문서의 본문을 건드리지
    # 않았다면 도장만 찍는 커밋은 여전히 차단이다.
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
    # rev-parse 가 답하지 못하는 상황(타임아웃 등)은 판정이 아니라 내부 오류다 — Invariant #1
    # 은 그런 커밋을 통과시키라고 요구한다. "객체가 없다"는 정당한 nonzero 와 구별해야 하므로
    # git 생존 확인이 실패할 때에만 열린다.
    root = _stamp_repo(tmp_path)
    doc = root / "docs" / "a.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(_sha_in(doc), "b" * 40), encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    wiki = load_wiki_config(root)
    nodes = collect_nodes(root, wiki)
    assert validate_stamps(root, wiki, nodes)  # 평시에는 차단

    real = wiki_graph._git

    def dying_git(args, cwd):
        if args[0] in ("rev-parse", "cat-file"):
            return None  # git 이 더 이상 답하지 못한다
        return real(args, cwd)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(wiki_graph, "_git", dying_git)
        assert validate_stamps(root, wiki, nodes) == []


def test_stamp_fails_open_on_a_root_commit(tmp_path: Path):
    # 부모가 없으면 "직전 커밋이 이 본문을 동기화했는가"를 물을 수 없다 — 판정 불가는 통과다.
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
    # /flow 는 바뀐 파일 경로를 넘긴다 — 디렉터리를 문서화한 노드가 그 조회에서 빠지면
    # 결과가 빈 줄이고, 호출자는 그것을 "미문서화"로 읽는다.
    root = _nodes_for_repo(tmp_path)
    _node(root, "docs/authdir.md", "wiki_id: auth.dir\ntitle: D\nsources:\n  src/auth: null\n")
    assert wiki_graph.cmd_nodes_for(root, ["src/auth/jwt.py"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert sorted(out) == ["src/auth/jwt.py\tauth.dir", "src/auth/jwt.py\tauth.jwt"]


def test_nodes_for_directory_source_keeps_the_segment_boundary(tmp_path: Path, capsys):
    # 대칭 매칭의 새 방향에도 세그먼트 경계가 살아 있어야 한다 — `src/auth` 노드가
    # 형제 디렉터리 `src/auth-x/` 의 파일에 걸리면 조회가 남의 문서를 끌어온다.
    root = _nodes_for_repo(tmp_path)
    _node(root, "docs/authdir.md", "wiki_id: auth.dir\ntitle: D\nsources:\n  src/auth: null\n")
    assert wiki_graph.cmd_nodes_for(root, ["src/auth-x/jwt.py"]) == 0
    assert capsys.readouterr().out == ""


def test_stamp_still_blocks_a_document_introduced_by_head(tmp_path: Path):
    # HEAD~1 은 읽히는데 그 문서만 없다 = HEAD 가 문서를 신설한 경우. 신설 커밋은 자기
    # 도장을 이미 들고 있으므로 그 다음 커밋의 sha 교체는 동기화가 아니다 — 차단 유지.
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
    # rename+본문 동기화가 한 커밋에 있고 도장이 다음 커밋(또는 amend)이면 HEAD~1 에는
    # 새 경로가 없다 — 그것을 "신설"로 단정하면 그 동기화를 못 보고, 차단 메시지가 권하는
    # amend·rebase/fixup 까지 막는다. diff -M 으로 이전 경로를 되짚어 본문 비교를 이어간다.
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
    # 이동만으로는 어떤 소스도 동기화되지 않는다 — rename 허용이 sha 세탁 통로가 되면 안 된다.
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
    # HEAD~1:<path> 본문 읽기만 실패하고(타임아웃 등) 객체 조회는 살아 있는 상황 — "부모에
    # 그 문서가 없다"는 판정이 아니므로 차단 흐름으로 이어지면 Invariant #1 위반이다.
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
    assert validate_stamps(root, wiki, nodes)  # 평시에는 차단

    real = wiki_graph._git
    target = "HEAD~1:docs/a.md"

    def flaky_parent_read(args, cwd):
        if args[-1] == target and args != ["rev-parse", "--verify", target]:
            return None  # 본문 읽기(show/cat-file)만 죽고 객체 조회는 답한다
        return real(args, cwd)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(wiki_graph, "_git", flaky_parent_read)
        assert validate_stamps(root, wiki, nodes) == []


def test_stamp_fails_open_when_the_rename_lookup_fails(tmp_path: Path):
    # 부모에 경로가 없어 rename 을 물어야 하는데 diff 가 답하지 못하면 신설/개명을 가를 수
    # 없다 — 판정 불가는 통과다 (Invariant #1).
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
    # 부모 커밋에서 같은 경로가 디렉터리였다면 `git show` 는 tree 목록을 exit 0 으로 내
    # "본문이 다르다"로 오독된다. cat-file blob 은 tree 에서 실패하고, 객체 존재 확인이
    # 그 실패를 "부모에 문서가 없다"와 갈라 통과시킨다 (Invariant #1).
    # 통과 여부만 보면 옛 `show` 경로도 (다른 이유로) 통과하므로, 이 테스트가 고정하는
    # 것은 결과가 아니라 **경유한 질의**다 — 객체 존재 확인이 실제로 일어나야 한다.
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
    # 차단 경로에서 swap 마다 같은 HEAD 생존 프로브를 재실행하면 spawn 이 소스 수에
    # 비례해 낭비된다(문서 40×소스 3이면 120회) — 호출당 1회면 충분하다.
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
    assert len(problems) == 2  # swap 마다 문제 1건 — 차단 자체는 유지
    assert len(probes) == 1


def _renamed_nodes_repo(tmp_path: Path, count: int) -> Path:
    """노드 count 개를 전부 개명한 커밋 + 그 다음 sha 만 교체한 작업 트리."""
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
    # renames 를 None 하나로 "아직 조회 안 함"과 "조회했는데 못 답함"에 겸용하면, 실패한
    # 조회가 rename 분기에 닿는 노드마다 되풀이된다 — `diff -M` 은 이 게이트가 던지는 가장
    # 비싼 질의이고 _git 타임아웃이 5초라 최악 N×5초가 커밋 훅 안에 들어앉는다.
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
    assert problems == []  # 답을 못 얻었으니 판정도 없다 (Invariant #1)
    assert count == 1


def test_stamp_probes_the_parent_commit_once(tmp_path: Path):
    # `rev-parse --verify HEAD~1` 의 답은 저장소 상수다 — 노드마다 되물으면 HEAD 프로브에서
    # 없앤 낭비가 그대로 남는다.
    root = _renamed_nodes_repo(tmp_path, 5)
    wiki = load_wiki_config(root)
    nodes = collect_nodes(root, wiki)
    count, problems = _count_git(
        root, wiki, nodes, lambda a: a == ["rev-parse", "--verify", "HEAD~1"]
    )
    assert len(problems) == 5  # 순수 개명이므로 차단은 그대로
    assert count == 1


def test_head_renames_fails_open_on_a_truncated_record(tmp_path: Path):
    # 잘린 레코드를 건너뛰면 결과가 {} 가 되고, 그것은 "개명이 없다"는 **판정**이라
    # 정당한 개명+동기화를 차단으로 몰 수 있다. 읽을 수 없는 출력은 판정이 아니다.
    # 정상 출력은 언제나 NUL 로 끝난다(A/D/M/T/R 전부, 공백·한글 경로 포함) — `_git` 의
    # .strip() 은 NUL 을 안 지우므로('\0'.isspace() 가 False) 종료자가 그대로 남는다.
    # 케이스 표는 순서 있는 목록이지 맵이 아니다. 다만 dict 리터럴의 중복 키는 ruff F601 이
    # 공짜로 잡아주고 리스트에는 그 그물이 없으므로, 잃는 보호를 아래 단언으로 되돌린다.
    cases = [
        ("R100\0docs/old.md\0docs/new.md\0", {"docs/new.md": "docs/old.md"}),
        ("M\0docs/a.md\0R100\0docs/old.md\0docs/new.md\0", {"docs/new.md": "docs/old.md"}),
        ("M\0docs/a.md\0", {}),  # 완결된 출력 — 개명이 없다는 정당한 판정
        ("", {}),  # 변경 없음
        ("R100\0docs/old.md", None),  # 레코드가 통째로 모자람
        ("M\0docs/a", None),  # 필드 중간에서 잘림 — 길이는 맞아 보인다
        ("R100\0docs/old.md\0", None),  # NUL 경계에서 잘려 새 경로가 빈 문자열
        ("M\0docs/a.md\0R100\0", None),  # 앞은 온전하고 마지막 레코드만 모자람
        ("M\0", None),  # 2필드 레코드도 마찬가지 — 경로 자리가 종료자다
        ("M\0docs/a.md\0D\0", None),  # 마지막 2필드 레코드만 경로를 잃었다
        # 빈 status 는 맨 끝(종료자)에서만 정상이다. 중간에 있으면 손상된 출력이고, 거기서
        # 멈추면 뒤따르는 개명을 조용히 버려 역시 "개명 없음" 판정이 된다.
        ("M\0docs/a.md\0\0R100\0docs/o.md\0docs/n.md\0", None),
    ]
    assert len({out for out, _ in cases}) == len(cases)  # 입력 중복은 케이스 소실이다
    real = wiki_graph._git
    with pytest.MonkeyPatch.context() as mp:
        for out, expected in cases:
            mp.setattr(wiki_graph, "_git", lambda a, c, _o=out: _o)
            assert wiki_graph._head_renames(tmp_path, "docs") == expected, repr(out)
    assert wiki_graph._git is real


def test_head_renames_ignores_a_copy_record(tmp_path: Path):
    # C 는 원본을 남긴다 — 도장을 미룬 문서는 *이동한* 원본을 타므로 복사를 개명으로 읽으면
    # 그대로 있는 파일의 본문과 비교하게 된다. `-M` 만 넘기므로 git 이 C 를 낼 일은 없지만
    # (명시적 `-M` 은 `diff.renames=copies` 를 renames-only 로 덮으므로 — `-M` 이 없으면 그
    # 설정만으로 C 가 나올 수 있다 — `-M` 을 준 이상 복사 탐지를 켤 길은 명령줄 `-C`/
    # `--find-copies-harder` 뿐이다. git 2.47.1 실측), 파서가 그 보장에 기대지는 않는다.
    real = wiki_graph._git
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(wiki_graph, "_git", lambda a, c: "C100\0docs/src.md\0docs/copy.md\0")
        assert wiki_graph._head_renames(tmp_path, "docs") == {}
        # 3필드를 소비하는 것 자체는 맞다 — 안 그러면 뒤 레코드가 어긋난다.
        mp.setattr(
            wiki_graph,
            "_git",
            lambda a, c: "C100\0docs/src.md\0docs/copy.md\0R100\0docs/o.md\0docs/n.md\0",
        )
        assert wiki_graph._head_renames(tmp_path, "docs") == {"docs/n.md": "docs/o.md"}
    assert wiki_graph._git is real


def test_stamp_new_file_passes(tmp_path: Path):
    # HEAD 에 없는 새 문서의 최초 도장은 자유 (저작 자체가 동기화).
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
    # 기본 core.quotePath 아래서 `git diff --name-only` 는 한글 경로를 C-escape 로 인용해
    # 반환한다 — -z 없이는 그런 문서가 도장 검사에서 조용히 빠진다 (_candidate_files 의
    # "-z is mandatory" 와 같은 footgun).
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
    # missing-path 해소(항목 삭제)·새 소스 추가·null→sha 최초 등록은 본문 편집 없이도
    # 정당하다 — 이 guard 가 사라지면 정당한 커밋이 오차단된다.
    root = _stamp_repo(tmp_path)
    doc = root / "docs" / "a.md"
    blob = _sha_in(doc)
    (root / "src" / "b.py").write_text("y = 1\n", encoding="utf-8")
    front = f"---\nwiki_id: a\ntitle: A\nsources:\n  src/a.py: '{blob}'\n  src/b.py: null\n"
    doc.write_text(front + "---\n\n본문\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    assert cmd_verify(root) == 0  # 항목 추가 (null 등록)
    b_blob = _blob_of(root, "src/b.py")
    doc.write_text(doc.read_text(encoding="utf-8").replace("null", f"'{b_blob}'"), encoding="utf-8")
    assert cmd_verify(root) == 0  # null→sha 최초 등록 (graph 는 키만 실으므로 재빌드 불필요)
    doc.write_text(
        f"---\nwiki_id: a\ntitle: A\nsources:\n  src/a.py: '{blob}'\n---\n\n본문\n",
        encoding="utf-8",
    )
    assert cmd_build(root) == 0  # 키 집합이 줄었으므로 graph 재빌드
    assert cmd_verify(root) == 0  # 항목 삭제


def test_stale_batches_hash_object(tmp_path: Path, monkeypatch):
    # Windows 에서 프로세스 spawn 이 제일 비싸다 — 경로가 몇 개든 hash-object 는 1회.
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
    # `src/auth` 는 덮고, 형제 `src/auth-x` 는 안 덮는다 (Invariant #6 과 같은 footgun)
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
    # 미문서화는 정상 답 — --neighbors 의 없는-id exit 1 과 다른 계약
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


# 읽는 파일은 wiki-init 의 SKILL.md 하나지만, 다른 skills/ 산문의 관례(들여쓴 펜스,
# 3-백틱을 감싸는 4-백틱 — skills/flow·flow-init)와 CommonMark 가 허용하는 `~~~` 까지
# 미리 덮는다. 여는 울타리를 백레퍼런스로 되받으므로 안쪽 3-백틱은 4-백틱 블록을 닫지
# 못한다. 닫는 들여쓰기는 절대 0–3 칸 또는 여는 쪽 +0–3 칸만 받는다 — 리스트 안 펜스는
# 들여쓰기를 컨테이너 기준으로 재므로 절대 갈래만으로는 자기 짝을 못 닫고, 무제한이면 블록
# 안의 더 깊은 구분자 줄에서 조기 종료한다. 받는 닫기가 없으면 `\Z` 로 파일 끝까지 삼킨다 —
# 덜 걷어내면 표 행이 새고, 과하게 걷어내면 표가 사라져 아래 assert 가 크게 터진다. 위 절들의
# 행동과 남은 CommonMark 괴리는 `_FENCE_CASES` 가 값으로 고정한다.
_FENCE_RE = re.compile(
    r"^([ \t]*)(`{3,}|~{3,}).*?(?:^(?:[ ]{0,3}|\1[ ]{0,3})\2|\Z)", re.MULTILINE | re.DOTALL
)


def _step5_section(text: str) -> str:
    """wiki-init SKILL.md 의 §5 본문, 펜스 코드블록을 걷어낸 것.

    표 정규식을 파일 전체에 풀어놓으면 다른 절의 같은 모양까지 끌어와 아래 중복 단언이
    오탐으로 터지고, 메시지는 원인을 오도한다(그 경로는 §5 표에 중복으로 있지 않다).
    절로 좁히는 것만으로는 부족하다 — 펜스는 산문이 아니라 예시이므로, §5 안의 펜스가 표
    행 모양을 인용하면 같은 오탐이 되고, 컬럼 0 에서 `## 5.` 로 시작하는 펜스 줄은 헤딩
    분할까지 어긋낸다.

    걷어내는 쪽의 비용 하나 — 표 *아래*에서 짝 없는 펜스 뒤에 붙은 행은 통째로 걷혀 케이스가
    되지 않는다. wiki-init SKILL.md §5 의 "행을 더하면 케이스가 는다"가 성립하지 않는 유일한
    자리다."""
    blocks = [
        b
        for b in re.split(r"^## ", _FENCE_RE.sub("", text), flags=re.MULTILINE)
        if b.startswith("5.")
    ]
    assert len(blocks) == 1, f"wiki-init SKILL.md 의 §5 블록이 {len(blocks)} 개다 (1 이어야)"
    return blocks[0]


def test_wiki_init_step5_table_is_parity_tested():
    # 표가 곧 테스트 케이스다 — 산문 예제가 구현과 어긋나거나 표가 조용히 줄면 여기서 걸린다.
    text = (_REPO / "skills" / "wiki-init" / "SKILL.md").read_text(encoding="utf-8")
    rows = _TABLE_ROW_RE.findall(_step5_section(text))
    # 짝이 안 맞는 펜스 하나면 비탐욕 페어링이 그것을 다음 절의 여는 펜스와 묶어 그 사이의
    # 표까지 삼키는데, `## 5.` 헤딩은 살아남아 위 블록 가드가 침묵한다. 그러면 빈 표가 아래
    # 중복 단언을 공허하게 지나고 실패는 마지막 줄에서 "표가 구현과 어긋난다"로만 드러난다.
    assert rows, "§5 표를 못 찾았다 — 펜스 짝을 확인하라"
    # dict 로 접기 전에 센다 — 같은 경로가 두 줄이면 접힌 뒤에는 흔적이 없어, 표가 늘었다고
    # 믿는 동안 케이스는 그대로다. SKILL.md 는 Markdown 이라 중복 행을 잡아줄 린터가 없다.
    assert len({path for path, _ in rows}) == len(rows), "§5 표에 경로가 중복된 행이 있다"
    assert dict(rows) == _EXAMPLES


# 위 테스트는 `_FENCE_RE` 를 태우지 않는다 — 입력이 wiki-init 의 SKILL.md 하나뿐인데 그
# 파일의 펜스는 §5 바깥의 컬럼 0 3-백틱 쌍이라, 스트립을 통째로 걷어내도 rows=6 으로 통과
# 한다. 정규식이 막는다고 선언한 형태는 여기서만 태워지므로, 새 형태를 막을 땐 케이스를 같이
# 늘려야 한다. 각 케이스는 정규식의 한 절을 떨어뜨리면 깨진다. 라벨의 though 절은 그 읽기가
# CommonMark 와 갈린다는 표시다 — 값을 고정해 둬야 바뀔 때 눈에 띄고, 그런 케이스도 절을
# 태운다(어떤 절의 유일한 가드인 것도 있다).
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
    # 리스트로 감싸야 라벨이 기계장치대로다 — 최상위의 4칸 이상 여는 줄을 CommonMark 는
    # 펜스로 읽지 않아(빈 줄 뒤면 들여쓴 코드블록, 문단 뒤면 문단 연속) "닫는" 일 자체가 없다.
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
    # 닫기가 절대 3칸 — 상대 갈래(5칸 요구)가 못 받아 절대 창의 상한을 태운다. 하한은 위
    # 컬럼 0 케이스가 잡는다.
    (
        f"- item\n\n     ```bash\n     {_FENCE_IN}\n   ```\n\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "a list-nested block closes at a shallower absolute indent",
    ),
    # 행 단위 답은 우연히 일치한다 — 그 블록이 들여쓴 코드가 되어 행이 산문 밖인 것이지,
    # 펜스로 닫혀서가 아니다. 닫기만 컬럼 0 으로 바꾸면 두 해석의 결과가 서로소다.
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
    # 바로 위와 같은 절대 좌표가 최상위에 오면 CommonMark 와 갈린다 — 정규식은 컨테이너를
    # 모르므로 둘 다 닫는다.
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
# 같은 입력이 다시 들어오면 라벨이 달라도 한쪽 커버리지는 허상이다 — 위에 한 줄 차이 쌍이
# 실제로 있다(4-백틱 래퍼 vs 그 미닫힘 변형).
assert len({doc for doc, _, _ in _FENCE_CASES}) == len(_FENCE_CASES)


@pytest.mark.parametrize(
    ("doc", "expected"),
    [(doc, expected) for doc, expected, _ in _FENCE_CASES],
    ids=[label for _, _, label in _FENCE_CASES],
)
def test_fence_stripping_leaves_exactly_the_rows_outside_fences(doc, expected):
    assert [path for path, _ in _TABLE_ROW_RE.findall(_FENCE_RE.sub("", doc))] == expected


# {{ID}} 를 안 쓰는 템플릿은 wiki_id 가 리터럴로 실려 있다 — 파생 규칙이 바뀌면 무음으로
# 표류하므로, 각 템플릿의 정본 출력 경로(주석·harness-authoring 규약)의 파생값과 대조한다.
_LITERAL_ID_TEMPLATES = {
    "docs-readme.template.md": "docs/README.md",
    "onboarding.template.md": "docs/onboarding/README.md",
}


def test_template_literal_ids_are_parity_tested():
    # 맵을 손으로 들지 않고 **템플릿 집합에서 파생**한다: 리터럴 id 템플릿이 새로 생기면
    # 여기서 먼저 걸린다 (바로 아래 주석 테스트가 경계하는 무음 표류와 같은 실패 모드).
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
