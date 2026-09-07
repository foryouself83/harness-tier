import json
from pathlib import Path

from scripts import wiki_graph
from tests.wiki_graph._helpers import _node, _write_config


def _repo(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    return tmp_path


def _unmapped(root: Path, capsys) -> list[dict]:
    assert wiki_graph.cmd_unmapped(root) == 0
    return json.loads(capsys.readouterr().out)


def test_empty_map_is_listed(tmp_path: Path, capsys):
    # The case --verify is deliberately silent on. Nothing else enumerates it, which is why
    # a greenfield design's `sources: {}` never became real paths once the code landed.
    root = _repo(tmp_path)
    _node(root, "docs/sds/README.md", "wiki_id: sds.readme\ntitle: S\ntags: [sds]\nsources: {}\n")
    assert _unmapped(root, capsys) == [{"id": "sds.readme", "path": "docs/sds/README.md"}]


def test_absent_key_is_listed(tmp_path: Path, capsys):
    root = _repo(tmp_path)
    _node(root, "docs/sds/README.md", "wiki_id: sds.readme\ntitle: S\ntags: [sds]\n")
    assert [n["id"] for n in _unmapped(root, capsys)] == ["sds.readme"]


def test_valueless_key_is_listed(tmp_path: Path, capsys):
    root = _repo(tmp_path)
    _node(root, "docs/sds/README.md", "wiki_id: sds.readme\ntitle: S\ntags: [sds]\nsources:\n")
    assert [n["id"] for n in _unmapped(root, capsys)] == ["sds.readme"]


def test_a_mapped_node_is_not_listed(tmp_path: Path, capsys):
    root = _repo(tmp_path)
    _node(
        root,
        "docs/sds/README.md",
        "wiki_id: sds.readme\ntitle: S\ntags: [sds]\nsources:\n  src/a.py: null\n",
    )
    assert _unmapped(root, capsys) == []


def test_a_list_valued_sources_is_not_listed(tmp_path: Path, capsys):
    # `--nodes-for` reads a list, so the node is reachable and nothing is missing. Structure
    # validation rejects the shape separately; listing it here would name the wrong remedy.
    root = _repo(tmp_path)
    _node(
        root,
        "docs/sds/README.md",
        "wiki_id: sds.readme\ntitle: S\ntags: [sds]\nsources: [src/a.py]\n",
    )
    assert _unmapped(root, capsys) == []


def test_a_non_sds_node_is_not_listed(tmp_path: Path, capsys):
    # An SRS or an onboarding page maps to no code path legitimately.
    root = _repo(tmp_path)
    _node(root, "docs/srs/README.md", "wiki_id: srs.readme\ntitle: R\ntags: [srs]\n")
    assert _unmapped(root, capsys) == []


def test_a_substring_tag_is_not_sds(tmp_path: Path, capsys):
    # Scalar on purpose: `_as_list("sdsx")` is `["sdsx"]`, which does not contain "sds".
    # Reading the raw value makes the membership test a substring test and "sdsx" matches.
    root = _repo(tmp_path)
    _node(root, "docs/x/README.md", "wiki_id: x.readme\ntitle: X\ntags: sdsx\n")
    assert _unmapped(root, capsys) == []


def test_a_scalar_tag_still_counts(tmp_path: Path, capsys):
    root = _repo(tmp_path)
    _node(root, "docs/sds/README.md", "wiki_id: sds.readme\ntitle: S\ntags: sds\n")
    assert [n["id"] for n in _unmapped(root, capsys)] == ["sds.readme"]


def test_a_document_without_a_wiki_id_is_not_a_node(tmp_path: Path, capsys):
    root = _repo(tmp_path)
    _node(root, "docs/sds/README.md", "title: S\ntags: [sds]\n")
    assert _unmapped(root, capsys) == []


def test_no_wiki_prints_an_empty_list(tmp_path: Path, capsys):
    # doc-sync runs the command unconditionally; without a wiki it must answer, not fail.
    # The node is what makes this discriminating: an empty `docs/` answers `[]` whether the
    # no-wiki branch is read or the config is ignored and `docs/` scanned anyway.
    (tmp_path / "docs").mkdir()
    _node(tmp_path, "docs/sds/README.md", "wiki_id: sds.readme\ntitle: S\ntags: [sds]\n")
    assert _unmapped(tmp_path, capsys) == []


def test_output_is_path_sorted(tmp_path: Path, capsys):
    root = _repo(tmp_path)
    _node(root, "docs/sds/b.md", "wiki_id: sds.b\ntitle: B\ntags: [sds]\n")
    _node(root, "docs/sds/a.md", "wiki_id: sds.a\ntitle: A\ntags: [sds]\n")
    assert [n["path"] for n in _unmapped(root, capsys)] == ["docs/sds/a.md", "docs/sds/b.md"]


def test_cli_dispatches_unmapped(tmp_path: Path, capsys, monkeypatch):
    root = _repo(tmp_path)
    _node(root, "docs/sds/README.md", "wiki_id: sds.readme\ntitle: S\ntags: [sds]\n")
    monkeypatch.setattr(wiki_graph, "host_root", lambda: root)
    assert wiki_graph.main(["--unmapped"]) == 0
    assert [n["id"] for n in json.loads(capsys.readouterr().out)] == ["sds.readme"]
