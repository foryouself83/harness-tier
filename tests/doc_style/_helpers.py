"""Shared scaffolding for the prose gate: the code extractor, the scoped-config
builder and the tree it writes."""

import sys
from pathlib import Path

Q = chr(34)
S = chr(39)

REPO = Path(__file__).resolve().parent.parent.parent  # tests/<pkg>/_helpers.py
sys.path.insert(0, str(REPO))

from scripts.doc_style_check import (  # noqa: E402
    code_blocks,
    config_paths,
    git_head_text,
    in_scope,
    lint_text,
    main,
    markdown_prose,
    python_prose,
    shell_prose,
    strip_prose,
    verify,
)

__all__ = [
    "Q",
    "REPO",
    "S",
    "TREE",
    "_codes",
    "_rels",
    "_scoped",
    "code_blocks",
    "config_paths",
    "git_head_text",
    "in_scope",
    "lint_text",
    "main",
    "markdown_prose",
    "python_prose",
    "shell_prose",
    "strip_prose",
    "verify",
]


def _codes(path: Path, text: str, severity: str = "error") -> list[str]:
    return [code for level, _, code, _ in lint_text(path, text) if level == severity]


# ---------- Config scope: one reader for both arms ----------


def _scoped(tmp_path: Path, config: str, rels: list[str]) -> Path:
    cfg = tmp_path / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-config.yaml").write_text(config, encoding="utf-8")
    for rel in rels:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("body\n", encoding="utf-8")
    return tmp_path


TREE = [
    "a.md",
    "docs/keep.md",
    "docs/legacy/old.md",
    "docs/legacy/sub/older.md",
    "node_modules/direct.md",
    "node_modules/pkg/deep/README.md",
    ".venv/lib/p/README.md",
    "vendor/x/y/z.md",
]


def _rels(root: Path, paths) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in paths)
