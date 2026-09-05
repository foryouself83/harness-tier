import shutil
import subprocess
from pathlib import Path

import pytest

from scripts import wiki_graph
from scripts.wiki_graph import (
    cmd_build,
    cmd_verify,
    collect_nodes,
    load_wiki_config,
    validate_stamps,
)
from tests.wiki_graph._helpers import (
    _blob_of,
    _commit,
    _node,
    _nodes_for_repo,
    _sha_in,
    _stamp_repo,
)


def test_stamp_only_change_blocks(tmp_path: Path, capsys):
    root = _stamp_repo(tmp_path)
    doc = root / "docs" / "a.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(_sha_in(doc), "b" * 40), encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0  # graph agrees, leaving only the stamp violation
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
    # old is a commit sha and new == `git rev-parse <old>:<src>`: a meaning-preserving rewrite,
    # which is allowed (spec §2).
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


def test_stamp_allowed_when_head_carries_the_body_edit(tmp_path: Path):
    # Exactly the amend path the block message recommends: with the body sync already committed,
    # HEAD holds that body and the only delta left is the sha. Blocking it makes the advice
    # unfollowable, and a split commit (body first, stamp second) has the same shape, so it
    # opens with it.
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
    # That the allowance above does not open the check wholesale: if the previous commit did not
    # touch that document's body, a stamp-only commit is still blocked.
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
    # rev-parse failing to answer (a timeout, say) is an internal error, not a verdict, and
    # Invariant #1 requires letting such a commit through. It has to stay distinct from the
    # legitimate nonzero that means "no such object", so it opens only when the git liveness
    # probe fails.
    root = _stamp_repo(tmp_path)
    doc = root / "docs" / "a.md"
    doc.write_text(
        doc.read_text(encoding="utf-8").replace(_sha_in(doc), "b" * 40), encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    assert cmd_build(root) == 0
    wiki = load_wiki_config(root)
    nodes = collect_nodes(root, wiki)
    assert validate_stamps(root, wiki, nodes)  # blocks under normal conditions

    real = wiki_graph._git

    def dying_git(args, cwd):
        if args[0] in ("rev-parse", "cat-file"):
            return None  # git no longer answers
        return real(args, cwd)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(wiki_graph, "_git", dying_git)
        assert validate_stamps(root, wiki, nodes) == []


def test_stamp_fails_open_on_a_root_commit(tmp_path: Path):
    # With no parent there is no way to ask whether the previous commit synced this body, and
    # what cannot be decided passes.
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
    # /flow hands over changed file paths. A node documenting a directory dropping out of that
    # lookup returns an empty line, which the caller reads as "undocumented".
    root = _nodes_for_repo(tmp_path)
    _node(root, "docs/authdir.md", "wiki_id: auth.dir\ntitle: D\nsources:\n  src/auth: null\n")
    assert wiki_graph.cmd_nodes_for(root, ["src/auth/jwt.py"]) == 0
    out = capsys.readouterr().out.splitlines()
    assert sorted(out) == ["src/auth/jwt.py\tauth.dir", "src/auth/jwt.py\tauth.jwt"]


def test_nodes_for_directory_source_keeps_the_segment_boundary(tmp_path: Path, capsys):
    # The segment boundary has to survive in the new direction of the symmetric match too: a
    # `src/auth` node matching a file in the sibling `src/auth-x/` pulls somebody else's
    # document into the lookup.
    root = _nodes_for_repo(tmp_path)
    _node(root, "docs/authdir.md", "wiki_id: auth.dir\ntitle: D\nsources:\n  src/auth: null\n")
    assert wiki_graph.cmd_nodes_for(root, ["src/auth-x/jwt.py"]) == 0
    assert capsys.readouterr().out == ""


def test_stamp_still_blocks_a_document_introduced_by_head(tmp_path: Path):
    # HEAD~1 reads fine and only that document is absent, which means HEAD created it. A
    # creating commit already carries its own stamp, so the next commit swapping the sha is not
    # a sync — the block stands.
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
    # With the rename and the body sync in one commit and the stamp in the next (or an amend),
    # the new path is absent from HEAD~1. Calling that a creation misses the sync and blocks the
    # very amend / rebase / fixup the block message recommends. diff -M traces the old path back
    # so the body comparison can continue.
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
    # A move on its own syncs no source: the rename allowance must not become a laundering route
    # for a sha.
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
    # Reading the HEAD~1:<path> body fails (a timeout, say) while the object lookup still
    # answers. That is not a verdict of "the parent has no such document", so carrying it into
    # the blocking path violates Invariant #1.
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
    assert validate_stamps(root, wiki, nodes)  # blocks under normal conditions

    real = wiki_graph._git
    target = "HEAD~1:docs/a.md"

    def flaky_parent_read(args, cwd):
        if args[-1] == target and args != ["rev-parse", "--verify", target]:
            return None  # only the body read (show/cat-file) dies; the object lookup still answers
        return real(args, cwd)

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(wiki_graph, "_git", flaky_parent_read)
        assert validate_stamps(root, wiki, nodes) == []


def test_stamp_fails_open_when_the_rename_lookup_fails(tmp_path: Path):
    # The path is absent from the parent so a rename has to be asked about, and a diff that
    # cannot answer leaves creation and rename indistinguishable — undecidable passes
    # (Invariant #1).
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
    # If the same path was a directory in the parent commit, `git show` prints a tree listing
    # and exits 0, which is misread as "the body differs". cat-file blob fails on a tree, and
    # the object-existence probe separates that failure from "the parent has no such document"
    # and lets it through (Invariant #1).
    # Judged on the outcome alone the old `show` path also passes, for a different reason, so
    # what this test pins is not the result but the QUERY taken — the object-existence probe has
    # to happen at all.
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
    # Re-running the same HEAD liveness probe per swap on the blocking path wastes spawns in
    # proportion to the source count (40 documents times 3 sources is 120 of them); once per
    # call is enough.
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
    assert len(problems) == 2  # one problem per swap; the block itself stands
    assert len(probes) == 1
