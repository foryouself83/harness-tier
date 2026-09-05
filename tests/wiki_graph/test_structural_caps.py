from pathlib import Path

from scripts.wiki_graph import (
    PROBLEM_CAP,
    build_graph,
    cmd_build,
    cmd_verify,
    collect_nodes,
    collect_warnings,
    load_wiki_config,
)
from tests.wiki_graph._helpers import _check, _mk, _node, _wiki_repo, _write_config


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
    # not a node at all. Warning on it makes an ordinary doc tree noisy all over again.
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
