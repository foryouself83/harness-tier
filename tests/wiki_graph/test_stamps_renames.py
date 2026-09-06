import subprocess
from pathlib import Path

import pytest

from scripts import wiki_graph
from scripts.wiki_graph import (
    cmd_build,
    cmd_stale,
    cmd_verify,
    collect_nodes,
    load_wiki_config,
    validate_stamps,
)
from tests.wiki_graph._helpers import (
    _blob_of,
    _commit,
    _git_repo_with_source,
    _node,
    _sha_in,
    _stamp_repo,
)


def _renamed_nodes_repo(tmp_path: Path, count: int) -> Path:
    """A commit renaming all `count` nodes, then a working tree that swaps only the shas."""
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
    # Using a single None for renames to mean both "not looked up yet" and "looked up, no
    # answer" repeats a failed lookup for every node that reaches the rename branch. `diff -M`
    # is the most expensive query this gate issues and _git's timeout is 5s, so the worst case
    # is N times 5s sitting inside the commit hook.
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
    assert problems == []  # no answer was obtained, so there is no verdict either (Invariant #1)
    assert count == 1


def test_stamp_probes_the_parent_commit_once(tmp_path: Path):
    # The answer to `rev-parse --verify HEAD~1` is a constant for the repository: asking it per
    # node leaves exactly the waste the HEAD probe removed.
    root = _renamed_nodes_repo(tmp_path, 5)
    wiki = load_wiki_config(root)
    nodes = collect_nodes(root, wiki)
    count, problems = _count_git(
        root, wiki, nodes, lambda a: a == ["rev-parse", "--verify", "HEAD~1"]
    )
    assert len(problems) == 5  # a pure rename, so the block stands
    assert count == 1


def test_head_renames_fails_open_on_a_truncated_record(tmp_path: Path):
    # Skipping a truncated record yields {}, and {} is a VERDICT of "no renames" that can drive
    # a legitimate rename-plus-sync into a block. Output that cannot be read is not a verdict.
    # Well-formed output always ends in a NUL (A/D/M/T/R alike, including paths with spaces or
    # Hangul): `_git`'s .strip() does not remove NUL ('\0'.isspace() is False), so the
    # terminator survives.
    # The case table is an ordered list, not a map. A dict literal would get duplicate-key
    # detection free from ruff F601 and a list has no such net, so the assertion below restores
    # the protection a list gives up.
    cases = [
        ("R100\0docs/old.md\0docs/new.md\0", {"docs/new.md": "docs/old.md"}),
        ("M\0docs/a.md\0R100\0docs/old.md\0docs/new.md\0", {"docs/new.md": "docs/old.md"}),
        ("M\0docs/a.md\0", {}),  # complete output: a legitimate verdict of no renames
        ("", {}),  # nothing changed
        ("R100\0docs/old.md", None),  # the record is missing entirely
        ("M\0docs/a", None),  # truncated mid-field, and the length still looks right
        ("R100\0docs/old.md\0", None),  # cut at a NUL, new path empty
        ("M\0docs/a.md\0R100\0", None),  # the front is intact and only the last record is short
        ("M\0", None),  # the same for a two-field record: the path slot is the terminator
        ("M\0docs/a.md\0D\0", None),  # only the last two-field record lost its path
        # An empty status is only well-formed at the very end, as the terminator. In the middle
        # it means corrupted output, and stopping there drops the renames that follow — another
        # route to a "no renames" verdict.
        ("M\0docs/a.md\0\0R100\0docs/o.md\0docs/n.md\0", None),
    ]
    assert len({out for out, _ in cases}) == len(cases)  # a duplicated input is a lost case
    real = wiki_graph._git
    with pytest.MonkeyPatch.context() as mp:
        for out, expected in cases:
            mp.setattr(wiki_graph, "_git", lambda a, c, _o=out: _o)
            assert wiki_graph._head_renames(tmp_path, "docs") == expected, repr(out)
    assert wiki_graph._git is real


def test_head_renames_ignores_a_copy_record(tmp_path: Path):
    # C leaves the original in place. A document whose stamp was deferred follows the MOVED
    # original, so reading a copy as a rename compares against the body of a file that never
    # went anywhere. git will not emit C here because only `-M` is passed (an explicit `-M`
    # overrides `diff.renames=copies` down to renames-only — without `-M` that setting alone can
    # produce C — and with `-M` given, the only way back to copy detection is a command-line
    # `-C` / `--find-copies-harder`; measured on git 2.47.1). The parser does not lean on that
    # guarantee.
    real = wiki_graph._git
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(wiki_graph, "_git", lambda a, c: "C100\0docs/src.md\0docs/copy.md\0")
        assert wiki_graph._head_renames(tmp_path, "docs") == {}
        # Consuming three fields is itself correct; otherwise the records that follow shift.
        mp.setattr(
            wiki_graph,
            "_git",
            lambda a, c: "C100\0docs/src.md\0docs/copy.md\0R100\0docs/o.md\0docs/n.md\0",
        )
        assert wiki_graph._head_renames(tmp_path, "docs") == {"docs/n.md": "docs/o.md"}
    assert wiki_graph._git is real


def test_stamp_new_file_passes(tmp_path: Path):
    # The first stamp on a document absent from HEAD is free — authoring it IS the sync.
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
    # Under the default core.quotePath, `git diff --name-only` returns a Hangul path C-escaped
    # and quoted: without -z such a document drops out of the stamp check silently (the same
    # footgun as _candidate_files' "-z is mandatory").
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
    # Resolving a missing path by dropping the entry, adding a new source, and the first
    # null-to-sha registration are all legitimate without a body edit; losing this guard
    # false-blocks a legitimate commit.
    root = _stamp_repo(tmp_path)
    doc = root / "docs" / "a.md"
    blob = _sha_in(doc)
    (root / "src" / "b.py").write_text("y = 1\n", encoding="utf-8")
    front = f"---\nwiki_id: a\ntitle: A\nsources:\n  src/a.py: '{blob}'\n  src/b.py: null\n"
    doc.write_text(front + "---\n\n본문\n", encoding="utf-8")
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    assert cmd_verify(root) == 0  # entry added (registered as null)
    b_blob = _blob_of(root, "src/b.py")
    doc.write_text(doc.read_text(encoding="utf-8").replace("null", f"'{b_blob}'"), encoding="utf-8")
    assert cmd_verify(root) == 0  # first null-to-sha (keys only in the graph, so no rebuild)
    doc.write_text(
        f"---\nwiki_id: a\ntitle: A\nsources:\n  src/a.py: '{blob}'\n---\n\n본문\n",
        encoding="utf-8",
    )
    assert cmd_build(root) == 0  # the key set shrank, so the graph is rebuilt
    assert cmd_verify(root) == 0  # entry removed


def test_stale_batches_hash_object(tmp_path: Path, monkeypatch):
    # Spawning a process is costliest on Windows: however many paths there are, hash-object
    # runs once.
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
