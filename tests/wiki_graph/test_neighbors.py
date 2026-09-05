from pathlib import Path

from scripts.wiki_graph import (
    build_graph,
    cmd_build,
    cmd_neighbors,
    graph_path,
    load_wiki_config,
    neighbors,
)
from tests.wiki_graph._helpers import _mk, _wiki_repo


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
