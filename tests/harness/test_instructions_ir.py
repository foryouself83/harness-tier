"""The harness-neutral instruction model read from a host's Claude Code instruction files."""

from pathlib import Path

import pytest

from scripts.harness import instructions as ir


def _write(host: Path, rel: str, text: str, newline: str = "\n") -> Path:
    path = host / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(text.replace("\n", newline).encode("utf-8"))
    return path


def test_empty_host_yields_nothing(tmp_path):
    assert ir.collect(tmp_path) == []


def test_root_rule_and_module_kinds(tmp_path):
    _write(tmp_path, "CLAUDE.md", "# Root\nbe terse\n")
    _write(tmp_path, ".claude/rules/py.md", "---\npaths:\n  - '**/*.py'\n---\nuse ruff\n")
    _write(tmp_path, "services/api/CLAUDE.md", "api notes\n")
    docs = ir.collect(tmp_path)
    assert [(d.kind, d.source, d.scope_dir) for d in docs] == [
        ("root", "CLAUDE.md", ""),
        ("rule", ".claude/rules/py.md", ""),
        ("module", "services/api/CLAUDE.md", "services/api"),
    ]
    assert docs[0].body == "# Root\nbe terse\n"
    assert docs[1].paths == ("**/*.py",)
    assert docs[1].body == "use ruff\n"
    assert docs[2].paths == ()


def test_frontmatter_paths_string_and_absent(tmp_path):
    _write(tmp_path, ".claude/rules/a.md", "---\npaths: 'src/**/*.{ts,tsx}, lib/*.ts'\n---\nA\n")
    _write(tmp_path, ".claude/rules/b.md", "---\ndescription: x\n---\nB\n")
    _write(tmp_path, ".claude/rules/c.md", "no frontmatter\n")
    a, b, c = ir.collect(tmp_path)
    assert a.paths == ("src/**/*.{ts,tsx}", "lib/*.ts")
    assert b.paths == () and b.body == "B\n"
    assert c.paths == () and c.body == "no frontmatter\n"


def test_crlf_sources_are_lf_normalized(tmp_path):
    _write(tmp_path, "CLAUDE.md", "one\ntwo\n@inc.md\n", newline="\r\n")
    _write(tmp_path, "inc.md", "included\n", newline="\r\n")
    _write(tmp_path, ".claude/rules/r.md", "---\npaths: ['*.py']\n---\nR\n", newline="\r\n")
    root, rule = ir.collect(tmp_path)
    assert root.body == "one\ntwo\nincluded\n"
    assert rule.paths == ("*.py",) and rule.body == "R\n"
    assert "\r" not in root.body + rule.body


def test_import_expands_relative_to_the_importing_file(tmp_path):
    _write(tmp_path, "CLAUDE.md", "top\n@docs/a.md\nend\n")
    _write(tmp_path, "docs/a.md", "---\nx: 1\n---\nA says\n@b.md\n")
    _write(tmp_path, "docs/b.md", "B says\n")
    (root,) = ir.collect(tmp_path)
    assert root.body == "top\nA says\nB says\nend\n"


def test_missing_home_outside_and_cyclic_imports_stay_literal(tmp_path):
    outside = tmp_path / "outside.md"
    outside.write_text("secret\n", encoding="utf-8")
    host = tmp_path / "host"
    _write(host, "CLAUDE.md", "@nope.md\n@~/x.md\n@../outside.md\n@loop.md\n")
    _write(host, "loop.md", "loop body\n@CLAUDE.md\n")
    (root,) = ir.collect(host)
    lines = root.body.splitlines()
    assert lines[:3] == ["@nope.md", "@~/x.md", "@../outside.md"]
    assert "secret" not in root.body
    assert lines[3:] == ["loop body", "@CLAUDE.md"]


def test_import_depth_is_capped(tmp_path):
    _write(tmp_path, "CLAUDE.md", "@d1.md\n")
    for i in range(1, 8):
        _write(tmp_path, f"d{i}.md", f"level {i}\n@d{i + 1}.md\n")
    (root,) = ir.collect(tmp_path)
    expanded = [f"level {i}" for i in range(1, ir.MAX_IMPORT_DEPTH + 1)]
    assert root.body.splitlines() == [*expanded, f"@d{ir.MAX_IMPORT_DEPTH + 1}.md"]


def test_import_inside_a_fence_is_not_expanded(tmp_path):
    _write(tmp_path, "CLAUDE.md", "```\n@inc.md\n```\n")
    _write(tmp_path, "inc.md", "X\n")
    (root,) = ir.collect(tmp_path)
    assert root.body == "```\n@inc.md\n```\n"


def test_kept_imports_stay_literal(tmp_path):
    _write(tmp_path, "CLAUDE.md", "@AGENTS.md\nrest\n")
    _write(tmp_path, "AGENTS.md", "agents text\n")
    (root,) = ir.collect(tmp_path, keep_imports={tmp_path / "AGENTS.md"})
    assert root.body == "@AGENTS.md\nrest\n"


def test_ordering_is_deterministic(tmp_path):
    for rel in ("z/CLAUDE.md", "a/b/CLAUDE.md", "a/CLAUDE.md"):
        _write(tmp_path, rel, "m\n")
    for rel in (".claude/rules/z.md", ".claude/rules/sub/a.md", ".claude/rules/b.md"):
        _write(tmp_path, rel, "r\n")
    _write(tmp_path, "CLAUDE.md", "root\n")
    assert [d.source for d in ir.collect(tmp_path)] == [
        "CLAUDE.md",
        ".claude/rules/b.md",
        ".claude/rules/sub/a.md",
        ".claude/rules/z.md",
        "a/CLAUDE.md",
        "a/b/CLAUDE.md",
        "z/CLAUDE.md",
    ]


def test_skip_dirs_and_non_rule_files(tmp_path):
    for rel in (
        ".git/CLAUDE.md",
        "node_modules/pkg/CLAUDE.md",
        ".venv/CLAUDE.md",
        ".claude/harness-tier/CLAUDE.md",
        ".claude/rules/notes.txt",
    ):
        _write(tmp_path, rel, "skip\n")
    assert ir.collect(tmp_path) == []


def test_git_ignored_module_is_skipped(tmp_path):
    import shutil
    import subprocess

    if not shutil.which("git"):
        pytest.skip("git not on PATH")
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    _write(tmp_path, ".gitignore", "build/\n")
    _write(tmp_path, "build/CLAUDE.md", "generated\n")
    _write(tmp_path, "src/CLAUDE.md", "kept\n")
    assert [d.source for d in ir.collect(tmp_path)] == ["src/CLAUDE.md"]


def test_frontmatter_with_bom_is_recognized(tmp_path):
    _write(tmp_path, ".claude/rules/r.md", "\ufeff---\npaths: ['*.py']\n---\nR\n")
    (rule,) = ir.collect(tmp_path)
    assert rule.paths == ("*.py",) and rule.body == "R\n"


def test_frontmatter_closed_at_eof_without_newline(tmp_path):
    _write(tmp_path, ".claude/rules/r.md", "---\npaths: ['*.py']\n---")
    (rule,) = ir.collect(tmp_path)
    assert rule.paths == ("*.py",) and rule.body == ""


def test_dot_claude_claude_md_is_a_root_source_after_the_root_file(tmp_path):
    _write(tmp_path, ".claude/CLAUDE.md", "project memory\n")
    _write(tmp_path, "CLAUDE.md", "root\n")
    docs = ir.collect(tmp_path)
    assert [(d.kind, d.source, d.scope_dir) for d in docs] == [
        ("root", "CLAUDE.md", ""),
        ("root", ".claude/CLAUDE.md", ""),
    ]
