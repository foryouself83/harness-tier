"""`changelog_section.py`: the stable section a release folds its rc sections into."""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import changelog_section as cs
from scripts.changelog_section import extract, fold, pending_sections

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "changelog_section.py"

PSR = """# CHANGELOG

<!-- version list -->

## v0.5.0-rc.1 (2026-09-23)

### Features

- **release**: Fold rc sections

## v0.4.1-rc.1 (2026-09-22)

### Bug Fixes

- **gate**: Read the worktree


## v0.4.0-rc.1 (2026-09-12)

### Features

- **docs**: Split USAGE
"""
TAGS = ["v0.4.0-rc.1", "v0.4.0", "v0.4.1-rc.1", "v0.5.0-rc.1"]


def headings(text: str) -> list[str]:
    return [line for line in text.splitlines() if line.startswith("## ")]


def test_pending_sections_are_the_rc_sections_above_the_last_stable_tag():
    got = pending_sections(PSR, TAGS)
    assert [s.splitlines()[0] for s in got] == [
        "## v0.5.0-rc.1 (2026-09-23)",
        "## v0.4.1-rc.1 (2026-09-22)",
    ]


def test_fold_replaces_every_pending_rc_section_with_one_stable_section():
    out = fold(
        PSR, "0.5.0", "### Features\n\n- **release**: Fold rc sections\n", TAGS, "2026-09-24"
    )
    assert headings(out) == ["## v0.5.0 (2026-09-24)", "## v0.4.0-rc.1 (2026-09-12)"]
    assert out.startswith("# CHANGELOG\n\n<!-- version list -->\n\n## v0.5.0 (2026-09-24)\n\n")
    assert "Read the worktree" not in out
    assert "- **docs**: Split USAGE" in out


def test_fold_keeps_the_rc_history_of_released_versions():
    # v0.4.0 shipped, so its rc section is history, not something this release folds in.
    out = fold(PSR, "0.5.0", "- x\n", TAGS, "2026-09-24")
    assert "## v0.4.0-rc.1 (2026-09-12)" in out


def test_fold_refuses_a_version_that_already_has_a_stable_section():
    text = fold(PSR, "0.5.0", "- x\n", TAGS, "2026-09-24")
    with pytest.raises(ValueError, match="already has"):
        fold(text, "0.5.0", "- y\n", TAGS, "2026-09-24")


def test_fold_refuses_an_empty_body():
    with pytest.raises(ValueError, match="empty"):
        fold(PSR, "0.5.0", "  \n", TAGS, "2026-09-24")


def test_fold_creates_a_changelog_psr_can_keep_updating():
    out = fold("", "1.0.0", "- first\n", [], "2026-09-24")
    assert out == "# CHANGELOG\n\n<!-- version list -->\n\n## v1.0.0 (2026-09-24)\n\n- first\n"


def test_extract_prints_the_stable_section_body_only():
    text = fold(PSR, "0.5.0", "### Features\n\n- a\n", TAGS, "2026-09-24")
    assert extract(text, "0.5.0") == "### Features\n\n- a"


def test_extract_ignores_rc_sections_of_the_same_base():
    assert extract(PSR, "0.5.0") is None
    assert extract(PSR, "0.4.0") is None


def test_extract_reads_a_node_style_heading():
    text = "# Changelog\n\n## [1.2.0](https://x/compare/v1.1.0...v1.2.0) (2026-09-24)\n\n- n\n"
    assert extract(text, "1.2.0") == "- n"


def run(*args, cwd):
    env = {**os.environ, "PYTHONUTF8": "0", "PYTHONIOENCODING": "cp949"}
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=cwd, capture_output=True, env=env
    )


def test_cli_fold_then_extract_round_trips_through_crlf(tmp_path):
    (tmp_path / "CHANGELOG.md").write_bytes(PSR.replace("\n", "\r\n").encode("utf-8"))
    (tmp_path / "notes.md").write_text("- 요약 — 한 줄\n", encoding="utf-8")
    tags = "\n".join(TAGS)
    r = run("fold", "--version", "0.5.0", "--body-file", "notes.md", "--tags", tags, cwd=tmp_path)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    raw = (tmp_path / "CHANGELOG.md").read_bytes()
    assert b"\r\n" in raw and b"\n" not in raw.replace(b"\r\n", b"")
    r = run("extract", "--version", "0.5.0", cwd=tmp_path)
    assert r.returncode == 0
    assert r.stdout.decode("utf-8").strip() == "- 요약 — 한 줄"


def test_cli_extract_exits_1_silently_without_a_stable_section(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text(PSR, encoding="utf-8")
    r = run("extract", "--version", "0.5.0", cwd=tmp_path)
    assert (r.returncode, r.stdout, r.stderr) == (1, b"", b"")


def test_cli_extract_exits_1_without_a_changelog(tmp_path):
    assert run("extract", "--version", "0.5.0", cwd=tmp_path).returncode == 1


def test_cli_pending_names_the_base_and_prints_the_sections(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text(PSR, encoding="utf-8")
    r = run("pending", "--tags", "\n".join(TAGS), cwd=tmp_path)
    assert r.returncode == 0
    out = r.stdout.decode("utf-8")
    assert out.splitlines()[0] == "since: v0.4.0"
    assert "## v0.5.0-rc.1" in out and "## v0.4.1-rc.1" in out
    assert "## v0.4.0-rc.1" not in out


def test_cli_pending_reads_git_tags_when_none_are_given(tmp_path, monkeypatch, capsys):
    (tmp_path / "CHANGELOG.md").write_text(PSR, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cs, "git_tags", lambda: TAGS)
    assert cs.main(["pending"]) == 0
    assert capsys.readouterr().out.splitlines()[0] == "since: v0.4.0"


def test_cli_fold_exits_2_with_a_reason(tmp_path):
    (tmp_path / "CHANGELOG.md").write_text(PSR, encoding="utf-8")
    (tmp_path / "notes.md").write_text("", encoding="utf-8")
    r = run("fold", "--version", "0.5.0", "--body-file", "notes.md", "--tags", "", cwd=tmp_path)
    assert r.returncode == 2
    assert b"changelog_section: " in r.stderr


NODE = """# Changelog

# [1.3.0-rc.2](https://x/compare/v1.3.0-rc.1...v1.3.0-rc.2) (2026-09-22)

- rc two

# [1.3.0-rc.1](https://x/compare/v1.2.1...v1.3.0-rc.1) (2026-09-21)

- rc one

## [1.2.1](https://x/compare/v1.2.0...v1.2.1) (2026-09-10)

- patch

# [1.2.0](https://x/compare/v1.1.0...v1.2.0) (2026-09-01)

- minor
"""
NODE_TAGS = ["v1.2.0", "v1.2.1", "v1.3.0-rc.1", "v1.3.0-rc.2"]


def test_node_minor_headings_are_sections_too():
    # conventional-changelog-angular writes a minor or major release as `# [x.y.z]`.
    assert len(pending_sections(NODE, NODE_TAGS)) == 2
    out = fold(NODE, "1.3.0", "- summary\n", NODE_TAGS, "2026-09-24")
    assert headings(out) == [
        "## v1.3.0 (2026-09-24)",
        "## [1.2.1](https://x/compare/v1.2.0...v1.2.1) (2026-09-10)",
    ]
    assert out.startswith("# Changelog\n\n## v1.3.0 (2026-09-24)\n\n- summary\n")
    assert "# [1.2.0]" in out and "rc one" not in out
    assert extract(NODE, "1.2.0") == "- minor"


def test_fold_refuses_a_body_that_would_end_its_own_section():
    with pytest.raises(ValueError, match="heading"):
        fold(PSR, "0.5.0", "## Features\n\n- a\n", TAGS, "2026-09-24")


def test_fold_refuses_a_version_not_above_the_last_stable_tag():
    with pytest.raises(ValueError, match="not above"):
        fold(PSR, "0.4.0", "- a\n", TAGS, "2026-09-24")


def test_an_unnumbered_prerelease_suffix_is_not_a_stable_section():
    assert extract("## v1.3.0-beta (2026-09-24)\n\n- b\n", "1.3.0") is None


def test_cli_reports_an_unreadable_changelog(tmp_path):
    (tmp_path / "CHANGELOG.md").write_bytes(b"\xff\xfe not utf-8")
    (tmp_path / "notes.md").write_text("- a\n", encoding="utf-8")
    assert run("extract", "--version", "0.5.0", cwd=tmp_path).returncode == 1
    r = run("fold", "--version", "0.5.0", "--body-file", "notes.md", "--tags", "", cwd=tmp_path)
    assert r.returncode == 2 and b"changelog_section: " in r.stderr


@pytest.mark.parametrize("version", ["1.4", "v0.5.0", "0.5.0-rc.1"])
def test_fold_refuses_a_version_that_is_not_a_bare_triple(version):
    with pytest.raises(ValueError, match="bare X.Y.Z"):
        fold(PSR, version, "- a\n", TAGS, "2026-09-24")
