import subprocess
from pathlib import Path

import pytest

from scripts import wiki_graph
from scripts.wiki_graph import (
    build_graph,
    cmd_build,
    cmd_verify,
    collect_nodes,
    collect_warnings,
    graph_path,
    load_wiki_config,
)
from tests.wiki_graph._helpers import _node, _wiki_repo, _write_config


def test_build_writes_graph_and_verify_passes(tmp_path: Path):
    _wiki_repo(tmp_path)
    assert cmd_build(tmp_path) == 0
    assert graph_path(tmp_path, load_wiki_config(tmp_path)).is_file()
    assert cmd_verify(tmp_path) == 0


def test_build_does_not_truncate_before_serializing(tmp_path: Path, monkeypatch):
    # `open("w")` truncates immediately, so computing the content as the write ARGUMENT means a
    # dump_graph failure leaves a 0-byte graph.yaml while main()'s FAIL-OPEN reports exit 0 —
    # --verify then blocks every commit on a file the build claimed to have written.

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
