import re
import subprocess
from pathlib import Path

from scripts.wiki_graph import build_graph, cmd_build, validate_structure


def _write_config(root: Path, body: str) -> None:
    cfg = root / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "flow-config.yaml").write_text(body, encoding="utf-8")


def _node(root: Path, rel: str, front: str, body: str = "본문\n") -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(f"---\n{front}---\n\n{body}", encoding="utf-8")
    return p


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


def _wiki_repo(tmp_path: Path) -> Path:
    (tmp_path / "docs").mkdir()
    _write_config(tmp_path, "wiki:\n  enable: true\n  root: docs/\n")
    _node(tmp_path, "docs/index.md", "wiki_id: index\ntitle: Index\nrelated: [auth.jwt]\n")
    _node(tmp_path, "docs/auth/jwt.md", "wiki_id: auth.jwt\ntitle: JWT\nrelated: [index]\n")
    return tmp_path


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


def _blob_of(root: Path, rel: str) -> str:
    return subprocess.run(
        ["git", "hash-object", "--", rel], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()


def _stamp_repo(tmp_path: Path) -> Path:
    """A repo with one committed node (sources holding the working-tree blob) and a matching
    graph.yaml."""
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


def _commit(root: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=root, check=True)
    subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", "commit", "-qm", message],
        cwd=root,
        check=True,
    )


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
