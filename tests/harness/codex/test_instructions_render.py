"""The Codex renderer: one managed block in the host's root AGENTS.md, built from the IR."""

import subprocess
import sys

import pytest

from scripts.harness.codex import instructions as codex
from tests.harness.codex._instructions import BEGIN, END, SCRIPT, _agents, _sample, _write


def test_markers_are_pinned():
    assert codex.BEGIN == BEGIN
    assert codex.END == END
    assert codex.MAX_BYTES == 32768


def test_new_file_holds_only_the_block_in_order(tmp_path):
    _sample(tmp_path)
    lines = codex.render(tmp_path)
    assert any("[+]" in line for line in lines)
    assert _agents(tmp_path).decode("utf-8") == (
        f"{BEGIN}\n"
        "# Project\nroot rule\n\n"
        "### Rule: .claude/rules/all.md\nApplies to: all files\n\nalways true\n\n"
        "### Rule: .claude/rules/py.md\nApplies to: **/*.py, tests/**\n\nuse ruff\n\n"
        "### Directory instructions\n"
        "Before working under `services/api/`, read `services/api/CLAUDE.md`.\n"
        f"{END}\n"
    )


def test_render_twice_is_byte_identical(tmp_path):
    _sample(tmp_path)
    codex.render(tmp_path)
    first = _agents(tmp_path)
    lines = codex.render(tmp_path)
    assert _agents(tmp_path) == first
    assert any("[=]" in line for line in lines)


def test_outside_text_survives_byte_for_byte_with_crlf(tmp_path):
    _sample(tmp_path)
    head = b"# Team notes\r\n\r\nkeep me\r\n"
    (tmp_path / "AGENTS.md").write_bytes(head)
    codex.render(tmp_path)
    data = _agents(tmp_path)
    assert data.startswith(head)
    block = data[len(head) :]
    assert b"\n" not in block.replace(b"\r\n", b"")
    assert block.startswith(b"\r\n" + BEGIN.encode("utf-8") + b"\r\n")
    assert block.endswith(END.encode("utf-8") + b"\r\n")


def test_block_is_replaced_in_place(tmp_path):
    _sample(tmp_path)
    tail = "\n## After\ntrailing user text\n"
    (tmp_path / "AGENTS.md").write_bytes(f"top\n\n{BEGIN}\nstale\n{END}\n{tail}".encode())
    codex.render(tmp_path)
    text = _agents(tmp_path).decode("utf-8")
    assert text.startswith(f"top\n\n{BEGIN}\n# Project\n")
    assert text.endswith(f"{END}\n{tail}")
    assert "stale" not in text


def test_claude_artifacts_are_never_modified(tmp_path):
    _sample(tmp_path)
    sources = [tmp_path / "CLAUDE.md", *sorted((tmp_path / ".claude").rglob("*.md"))]
    sources.append(tmp_path / "services/api/CLAUDE.md")
    before = {p: p.read_bytes() for p in sources}
    codex.render(tmp_path)
    codex.check(tmp_path)
    codex.remove(tmp_path)
    assert {p: p.read_bytes() for p in sources} == before


def test_claude_md_importing_agents_md_stays_idempotent(tmp_path):
    _write(tmp_path, "CLAUDE.md", "@AGENTS.md\nclaude only\n")
    _write(tmp_path, "AGENTS.md", "shared text\n")
    codex.render(tmp_path)
    first = _agents(tmp_path)
    codex.render(tmp_path)
    assert _agents(tmp_path) == first
    assert first.count(b"shared text") == 1


def test_over_budget_degrades_rules_to_index_lines(tmp_path):
    _write(tmp_path, "CLAUDE.md", "root\n")
    _write(tmp_path, ".claude/rules/big.md", "---\npaths: ['src/**']\n---\n" + "x" * 40000 + "\n")
    _write(tmp_path, ".claude/rules/any.md", "small\n")
    lines = codex.render(tmp_path)
    text = _agents(tmp_path).decode("utf-8")
    assert len(text.encode("utf-8")) <= codex.MAX_BYTES
    assert "xxxx" not in text and "small" not in text
    assert "Before editing files matching `src/**`, read `.claude/rules/big.md`." in text
    assert "Before editing any file, read `.claude/rules/any.md`." in text
    assert not any("[!]" in line for line in lines)


def test_still_over_budget_renders_and_warns(tmp_path):
    _write(tmp_path, "CLAUDE.md", "y" * 40000 + "\n")
    lines = codex.render(tmp_path)
    size = len(_agents(tmp_path))
    assert size > codex.MAX_BYTES
    assert any("[!]" in line and str(size) in line for line in lines)


def test_check_reports_drift_and_writes_nothing(tmp_path):
    _sample(tmp_path)
    ok, reason = codex.check(tmp_path)
    assert not ok and reason and not (tmp_path / "AGENTS.md").exists()
    codex.render(tmp_path)
    assert codex.check(tmp_path) == (True, "")
    _write(tmp_path, ".claude/rules/new.md", "new rule\n")
    before = _agents(tmp_path)
    ok, reason = codex.check(tmp_path)
    assert not ok and "\n" not in reason
    assert _agents(tmp_path) == before


def test_cli_check_exit_codes(tmp_path):
    _sample(tmp_path)
    cmd = [sys.executable, str(SCRIPT), "render", "--check", "--host", str(tmp_path)]
    drift = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert drift.returncode == 1 and drift.stdout.strip()
    render = [sys.executable, str(SCRIPT), "render", "--host", str(tmp_path)]
    assert subprocess.run(render, capture_output=True).returncode == 0
    clean = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    assert clean.returncode == 0, clean.stdout + clean.stderr


def test_remove_keeps_user_text_and_deletes_an_emptied_file(tmp_path):
    _sample(tmp_path)
    (tmp_path / "AGENTS.md").write_bytes(b"user text\r\n")
    codex.render(tmp_path)
    codex.remove(tmp_path)
    assert _agents(tmp_path) == b"user text\r\n"
    (tmp_path / "AGENTS.md").unlink()
    codex.render(tmp_path)
    codex.remove(tmp_path)
    assert not (tmp_path / "AGENTS.md").exists()


@pytest.mark.parametrize(
    "begin",
    [
        "<!-- harness-tier:codex-instructions-extra BEGIN -->",
        "<!-- harness-tier:teams BEGIN -->",
        " <!-- harness-tier:codex-instructions BEGIN -->",
    ],
)
def test_remove_ignores_a_begin_line_without_our_prefix(tmp_path, begin):
    body = f"{begin}\nhand made\n{END}\n".encode()
    (tmp_path / "AGENTS.md").write_bytes(body)
    assert "[=]" in codex.remove(tmp_path)
    assert _agents(tmp_path) == body


def test_a_marker_quoted_mid_line_is_not_a_block(tmp_path):
    body = f"Never edit `{BEGIN}` by hand.\n".encode()
    (tmp_path / "AGENTS.md").write_bytes(body)
    assert "[=]" in codex.remove(tmp_path)
    assert _agents(tmp_path) == body


def test_nothing_to_render_removes_block_and_creates_nothing(tmp_path):
    codex.render(tmp_path)
    assert not (tmp_path / "AGENTS.md").exists()
    (tmp_path / "AGENTS.md").write_bytes(f"mine\n\n{BEGIN}\nold\n{END}\n".encode())
    codex.render(tmp_path)
    assert _agents(tmp_path) == b"mine\n"


def test_begin_without_end_is_left_alone(tmp_path):
    _sample(tmp_path)
    body = f"mine\n{BEGIN}\nno end marker\n".encode()
    (tmp_path / "AGENTS.md").write_bytes(body)
    lines = codex.render(tmp_path) + [codex.remove(tmp_path)]
    assert _agents(tmp_path) == body
    assert any("[!]" in line for line in lines)


def test_the_begin_marker_fits_a_prose_line():
    assert len(BEGIN) <= 100


@pytest.mark.parametrize(
    "quote",
    [
        f"Never type `{END}` here.\n",
        f"{END}\n",
        f"{BEGIN}\n",
        f"{BEGIN}\nfake\n{END}\n",
    ],
)
def test_a_source_quoting_a_marker_cannot_break_the_block(tmp_path, quote):
    _write(tmp_path, "CLAUDE.md", f"before\n{quote}after\n")
    _write(tmp_path, ".claude/rules/r.md", quote)
    outside = b"user head\r\n"
    (tmp_path / "AGENTS.md").write_bytes(outside)
    codex.render(tmp_path)
    first = _agents(tmp_path)
    assert "[=]" in codex.render(tmp_path)[0]
    assert _agents(tmp_path) == first
    assert codex.check(tmp_path) == (True, "")
    lines = first.decode("utf-8").split("\r\n")
    assert lines.count(BEGIN) == 1 and lines.count(END) == 1
    codex.remove(tmp_path)
    assert _agents(tmp_path) == outside


def test_a_stale_block_quoting_end_inline_is_replaced_whole(tmp_path):
    _write(tmp_path, "CLAUDE.md", "fresh\n")
    stale = f"{BEGIN}\nold `{END}` quote\nmore old\n{END}\ntail\n"
    (tmp_path / "AGENTS.md").write_bytes(stale.encode("utf-8"))
    codex.render(tmp_path)
    assert _agents(tmp_path).decode("utf-8") == f"{BEGIN}\nfresh\n{END}\ntail\n"


@pytest.mark.parametrize("body", [b"", b"\n", b"  \r\n\r\n"])
def test_a_blank_agents_md_without_a_block_is_never_deleted(tmp_path, body):
    (tmp_path / "AGENTS.md").write_bytes(body)
    codex.render(tmp_path)
    assert codex.check(tmp_path) == (True, "")
    codex.remove(tmp_path)
    assert _agents(tmp_path) == body


def test_missing_pyyaml_is_one_actionable_line(tmp_path, monkeypatch, capsys):
    import scripts.harness as package

    _sample(tmp_path)
    monkeypatch.setattr(package, "instructions", package.instructions)
    monkeypatch.delitem(sys.modules, "scripts.harness.instructions", raising=False)
    monkeypatch.setitem(sys.modules, "yaml", None)
    lines = codex.render(tmp_path)
    assert len(lines) == 1 and "[!]" in lines[0] and "PyYAML" in lines[0]
    assert not (tmp_path / "AGENTS.md").exists()
    ok, reason = codex.check(tmp_path)
    assert not ok and "PyYAML" in reason and "\n" not in reason
    assert codex.main(["render", "--check", "--host", str(tmp_path)]) == 1
    out = capsys.readouterr().out.strip()
    assert "PyYAML" in out and "\n" not in out


OLD_BEGIN = (
    "<!-- harness-tier:codex-instructions BEGIN — generated from CLAUDE.md and .claude/rules;"
    " edit those, then re-run the renderer -->"
)


def test_a_block_under_an_older_begin_wording_is_still_ours(tmp_path):
    _sample(tmp_path)
    outside = b"user head\r\n"
    old = f"{OLD_BEGIN}\r\nstale\r\n{END}\r\n".encode()
    (tmp_path / "AGENTS.md").write_bytes(outside + b"\r\n" + old)
    assert not codex.check(tmp_path)[0]
    codex.render(tmp_path)
    text = _agents(tmp_path).decode("utf-8")
    assert text.count("harness-tier:codex-instructions BEGIN") == 1
    assert BEGIN in text and "stale" not in text
    assert text.startswith("user head\r\n\r\n" + BEGIN)
    assert codex.check(tmp_path) == (True, "")
    codex.remove(tmp_path)
    assert _agents(tmp_path) == outside


def test_duplicate_blocks_fail_check_collapse_on_render_and_all_go_on_remove(tmp_path):
    _sample(tmp_path)
    outside = b"user head\r\n"
    (tmp_path / "AGENTS.md").write_bytes(outside)
    codex.render(tmp_path)
    once = _agents(tmp_path)
    dup = once + b"\r\n" + f"{OLD_BEGIN}\r\nold copy\r\n{END}\r\n".encode()
    (tmp_path / "AGENTS.md").write_bytes(dup)
    ok, reason = codex.check(tmp_path)
    assert not ok and reason
    codex.render(tmp_path)
    assert _agents(tmp_path) == once
    (tmp_path / "AGENTS.md").write_bytes(dup)
    codex.remove(tmp_path)
    assert _agents(tmp_path) == outside


def test_root_sources_match_the_model():
    from scripts.harness import instructions as model

    assert codex.ROOT_SOURCES == model.ROOT_FILES
