import json
import subprocess
from pathlib import Path

from scripts import wiki_graph
from scripts.wiki_graph import cmd_stale
from tests.wiki_graph._helpers import _node, _nodes_for_repo, _write_config


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
