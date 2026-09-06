import subprocess
from pathlib import Path

import pytest

from scripts import wiki_graph
from scripts.wiki_graph import (
    DERIVED_EDGES,
    EDGE_KEYS,
    MANUAL_EDGES,
    build_graph,
    cmd_build,
    cmd_verify,
    collect_warnings,
    graph_path,
    load_wiki_config,
)
from tests.wiki_graph._helpers import _check, _mk, _node, _wiki_repo, _write_config


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
    # its own ORDER (it is the --neighbors budget priority), so it cannot be derived.
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
    # an empty lookup while graph verification was running, and drift returned 1,
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

    with pytest.raises(SystemExit) as exc:
        wiki_graph.main([])
    assert exc.value.code == 2
