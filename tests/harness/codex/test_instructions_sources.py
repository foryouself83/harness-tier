"""The Codex renderer against its sources: a file shared with AGENTS.md through a link is
never written, and a malformed source never crashes render, check or remove."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.harness.codex import instructions as codex
from tests.harness.codex._instructions import SCRIPT, _write


def _link(link: Path, target: str) -> None:
    try:
        link.symlink_to(Path(target))  # native separators, or Windows makes a dangling link
    except (OSError, NotImplementedError):
        pytest.skip("symlinks cannot be created here")


def _one_file_cases(host: Path, layout: str) -> Path:
    """Lay AGENTS.md and some other file out as one file (a link either way, or a hard link);
    return the file that holds the text. Every layout but `agents-links-rule` (whose shared file
    already IS `.claude/rules/all.md`) also gets that rule file, so there is real content a
    render would otherwise have written."""
    if layout == "agents-links-claude":
        real = _write(host, "CLAUDE.md", "# Project\nroot rule\n")
        _link(host / "AGENTS.md", "CLAUDE.md")
    elif layout == "claude-links-agents":
        real = _write(host, "AGENTS.md", "# Project\nroot rule\n")
        _link(host / "CLAUDE.md", "AGENTS.md")
    elif layout == "agents-links-dot-claude":
        real = _write(host, ".claude/CLAUDE.md", "# Project\nroot rule\n")
        _link(host / "AGENTS.md", ".claude/CLAUDE.md")
    elif layout == "agents-links-rule":
        real = _write(host, ".claude/rules/all.md", "always true\n")
        _link(host / "AGENTS.md", ".claude/rules/all.md")
        return real
    elif layout == "agents-links-module-claude":
        real = _write(host, "pkg/CLAUDE.md", "module notes\n")
        _link(host / "AGENTS.md", "pkg/CLAUDE.md")
    elif layout == "hardlink-module":
        real = _write(host, "pkg/CLAUDE.md", "module notes\n")
        try:
            (host / "AGENTS.md").hardlink_to(real)
        except (OSError, NotImplementedError, AttributeError):
            pytest.skip("hard links cannot be created here")
    else:
        real = _write(host, "CLAUDE.md", "# Project\nroot rule\n")
        try:
            (host / "AGENTS.md").hardlink_to(real)
        except (OSError, NotImplementedError, AttributeError):
            pytest.skip("hard links cannot be created here")
    _write(host, ".claude/rules/all.md", "always true\n")
    return real


@pytest.mark.parametrize(
    "layout",
    [
        "agents-links-claude",
        "claude-links-agents",
        "agents-links-dot-claude",
        "agents-links-rule",
        "agents-links-module-claude",
        "hardlink-module",
        "hardlink",
    ],
)
def test_one_file_for_both_harnesses_is_never_written(tmp_path, layout):
    real = _one_file_cases(tmp_path, layout)
    before = real.read_bytes()
    for _ in range(3):
        lines = codex.render(tmp_path)
        assert len(lines) == 1 and "[!]" in lines[0], lines
    ok, reason = codex.check(tmp_path)
    assert ok and "[!]" in reason, (ok, reason)
    assert "[=]" in codex.remove(tmp_path)
    assert real.read_bytes() == before
    cmd = [sys.executable, str(SCRIPT), "render", "--check", "--host", str(tmp_path)]
    assert subprocess.run(cmd, capture_output=True).returncode == 0


def test_a_dangling_agents_link_into_claude_md_is_not_followed(tmp_path):
    _link(tmp_path / "AGENTS.md", "CLAUDE.md")
    _write(tmp_path, ".claude/rules/all.md", "always true\n")
    lines = codex.render(tmp_path)
    assert len(lines) == 1 and "[!]" in lines[0], lines
    assert not (tmp_path / "CLAUDE.md").exists()


def test_a_rule_file_linking_to_agents_md_is_never_written(tmp_path):
    """The reverse of the forward-direction cases above: here AGENTS.md is the real file and a
    *rule* under `.claude/rules/` is the one linking to it — writing AGENTS.md's own bytes would
    rewrite that rule too, since underneath they are the same file."""
    real = _write(tmp_path, "AGENTS.md", "shared text\n")
    before = real.read_bytes()
    (tmp_path / ".claude" / "rules").mkdir(parents=True)
    _link(tmp_path / ".claude/rules/x.md", "../../AGENTS.md")
    linked = tmp_path / ".claude/rules/x.md"
    for _ in range(3):
        lines = codex.render(tmp_path)
        assert len(lines) == 1 and "[!]" in lines[0], lines
    ok, reason = codex.check(tmp_path)
    assert ok and "[!]" in reason, (ok, reason)
    assert "[=]" in codex.remove(tmp_path)
    assert real.read_bytes() == before
    assert linked.read_bytes() == before


def test_a_module_claude_md_linking_to_agents_md_is_never_written(tmp_path):
    """Same reverse direction, but the link is a module `CLAUDE.md` instead of a rule."""
    real = _write(tmp_path, "AGENTS.md", "shared text\n")
    before = real.read_bytes()
    (tmp_path / "pkg").mkdir(parents=True)
    _link(tmp_path / "pkg/CLAUDE.md", "../AGENTS.md")
    linked = tmp_path / "pkg/CLAUDE.md"
    for _ in range(3):
        lines = codex.render(tmp_path)
        assert len(lines) == 1 and "[!]" in lines[0], lines
    ok, reason = codex.check(tmp_path)
    assert ok and "[!]" in reason, (ok, reason)
    assert "[=]" in codex.remove(tmp_path)
    assert real.read_bytes() == before
    assert linked.read_bytes() == before


def test_an_undecodable_source_does_not_hide_a_link_to_agents_md(tmp_path):
    """A rule linking to AGENTS.md, made after the render, beside a rule that cannot be
    decoded: the link check compares file identity only, so it still finds the link and
    leaves AGENTS.md alone."""
    _write(tmp_path, "CLAUDE.md", "# Project\nroot rule\n")
    assert any("[+]" in line for line in codex.render(tmp_path))
    before = (tmp_path / "AGENTS.md").read_bytes()
    link = tmp_path / ".claude/rules/link.md"
    link.parent.mkdir(parents=True)
    _link(link, "../../AGENTS.md")
    (tmp_path / ".claude/rules/bad.md").write_bytes(b"\x80\n")
    result = codex.remove(tmp_path)
    assert result.startswith("  [=]") and "link.md" in result, result
    assert (tmp_path / "AGENTS.md").read_bytes() == before and link.is_file()


def test_remove_without_pyyaml_still_deletes_an_emptied_agents_md(tmp_path, monkeypatch):
    import scripts.harness as package

    _write(tmp_path, "CLAUDE.md", "# Project\nroot rule\n")
    codex.render(tmp_path)
    monkeypatch.setattr(package, "instructions", package.instructions)
    monkeypatch.delitem(sys.modules, "scripts.harness.instructions", raising=False)
    monkeypatch.setitem(sys.modules, "yaml", None)
    assert "삭제" in codex.remove(tmp_path)
    assert not (tmp_path / "AGENTS.md").exists()


def test_remove_still_deletes_an_emptied_agents_md_when_every_source_was_read(tmp_path):
    _write(tmp_path, "CLAUDE.md", "# Project\nroot rule\n")
    codex.render(tmp_path)
    assert "삭제" in codex.remove(tmp_path)
    assert not (tmp_path / "AGENTS.md").exists()


def test_a_dangling_module_claude_md_is_skipped_like_a_dangling_rule(tmp_path):
    from scripts.harness import instructions as model

    _write(tmp_path, "CLAUDE.md", "# Project\nroot rule\n")
    (tmp_path / "pkg").mkdir()
    _link(tmp_path / "pkg/CLAUDE.md", "missing.md")
    assert [d.source for d in model.collect(tmp_path)] == ["CLAUDE.md"]
    lines = codex.render(tmp_path)
    assert len(lines) == 1 and "[+]" in lines[0], lines
    assert codex.check(tmp_path) == (True, "")


# --- Regression battery: a malformed source must never crash render/check/remove -----------
#
# render/check parse every source in `_plan`. A source that cannot be read or decoded must
# degrade to a one-line `[!] ... 실패(...)` report — never a raw traceback — and must never
# stop `remove`, which reads no source's content.
#
# Two of these five shapes (invalid UTF-8, unreadable) reach `_collect`'s error boundary; the
# other three (invalid YAML, a directory named like a rule file, a dangling symlink rule) are
# already excluded earlier by unrelated existing guards (`_split_frontmatter`'s own YAML-error
# handling, and the `is_file()` filters in `harness/instructions.py`'s `sources`). Both groups
# are pinned here: silent exclusion is still a claim this battery holds to.
_COLLECT_ERROR_KINDS = frozenset({"invalid-utf8", "unreadable"})


def _malformed_rule(host: Path, kind: str) -> None:
    """Lay out one malformed `.claude/rules/bad.md` (or a dangling-symlink variant). Skips the
    test outright when this platform cannot produce the intended condition: a `PermissionError`
    is not guaranteed for a file's own owner (notably on Windows, where `chmod` does not restrict
    read access the way it does on POSIX), and symlinks may require a privilege the host lacks.
    """
    rules = host / ".claude" / "rules"
    rules.mkdir(parents=True, exist_ok=True)
    if kind == "invalid-utf8":
        (rules / "bad.md").write_bytes(b'---\npaths: ["**/*.py"]\n---\n\x80\n')
    elif kind == "invalid-yaml":
        (rules / "bad.md").write_bytes(b"---\npaths: [oops\n---\nbody\n")
    elif kind == "unreadable":
        p = rules / "bad.md"
        p.write_bytes(b"normal content\n")
        try:
            os.chmod(p, 0o000)
        except OSError:
            pytest.skip("cannot restrict this file's permissions on this filesystem")
        try:
            p.read_bytes()
        except PermissionError:
            pass
        else:
            os.chmod(p, 0o644)
            pytest.skip("the file's own owner can still read it despite chmod 000 here")
    elif kind == "directory-rule":
        (rules / "bad.md").mkdir()
    elif kind == "dangling-rule":
        _link(rules / "dangling.md", "missing-target.md")
    else:
        raise AssertionError(kind)


@pytest.mark.parametrize(
    "kind", ["invalid-utf8", "invalid-yaml", "unreadable", "directory-rule", "dangling-rule"]
)
def test_a_malformed_source_never_crashes_render_check_or_remove(tmp_path, kind):
    outside = b"# Team notes\nkeep me\n"
    (tmp_path / "AGENTS.md").write_bytes(outside)
    _write(tmp_path, "CLAUDE.md", "# Project\nroot rule\n")
    lines = codex.render(tmp_path)
    assert any("[+]" in line for line in lines), lines
    before = (tmp_path / "AGENTS.md").read_bytes()
    assert before.startswith(outside)

    try:
        _malformed_rule(tmp_path, kind)

        # render: no traceback ever; a genuine collect error also writes nothing at all.
        lines = codex.render(tmp_path)
        assert len(lines) == 1, lines
        if kind in _COLLECT_ERROR_KINDS:
            assert "[!]" in lines[0], lines
            assert (tmp_path / "AGENTS.md").read_bytes() == before
        after_render = (tmp_path / "AGENTS.md").read_bytes()
        assert after_render.startswith(outside)

        # check: no traceback; `ok` tracks whether the source could be collected at all, and
        # check never writes either way.
        ok, reason = codex.check(tmp_path)
        if kind in _COLLECT_ERROR_KINDS:
            assert ok is False and reason, (ok, reason)
        assert (tmp_path / "AGENTS.md").read_bytes() == after_render

        # remove: must always succeed at stripping our own block, regardless of the rule's
        # state — removal reads only AGENTS.md's own bytes below the (best-effort) reverse
        # check, never a rule/module's content.
        result = codex.remove(tmp_path)
        assert "[!]" not in result, result
        assert (tmp_path / "AGENTS.md").read_bytes() == outside

        # The standalone CLI (what doc-sync/harness-init invoke directly) must show the same:
        # one clean line and a documented exit code, never a Python traceback on stderr.
        cmd = [sys.executable, str(SCRIPT), "render", "--check", "--host", str(tmp_path)]
        cli = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
        assert cli.returncode in (0, 1), cli
        assert "Traceback" not in cli.stderr, cli.stderr
        assert "Traceback" not in cli.stdout, cli.stdout
    finally:
        bad = tmp_path / ".claude" / "rules" / "bad.md"
        if bad.exists():
            try:
                os.chmod(bad, 0o644)
            except OSError:
                pass
