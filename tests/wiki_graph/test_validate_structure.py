from pathlib import Path

from scripts.wiki_graph import (
    build_graph,
    collect_nodes,
    collect_warnings,
    load_wiki_config,
    validate_defects,
)
from tests.wiki_graph._helpers import _check, _mk, _node, _write_config


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
    # YAML with a numeric key like `sources: { 42: abc1234 }` parses to `{42: 'abc1234'}`.
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
