"""Seeding is match-then-skip per file (Invariant 5): the consumer's edited template is
the one every later render follows, so a re-run must never touch it."""

from pathlib import Path

import scripts.flow_init_setup as flow_init_setup
from scripts.flow_init_setup import (
    COPY_FILES,
    GITIGNORE_LINES,
    append_gitignore,
    design_gitignore_lines,
    seed_design_templates,
)

REPO = Path(__file__).resolve().parent.parent.parent
DEST = ".claude/harness-tier/templates/design-docs"


def test_seed_copies_then_preserves_edits(tmp_path):
    report = seed_design_templates(REPO, tmp_path)
    assert len([ln for ln in report if "[+]" in ln]) == 6
    edited = tmp_path / DEST / "erd.template.md"
    edited.write_text("mine", encoding="utf-8")
    report = seed_design_templates(REPO, tmp_path)
    assert edited.read_text(encoding="utf-8") == "mine"
    assert not any("[+]" in ln for ln in report)


def test_seed_follows_configured_directory(tmp_path):
    cfg = tmp_path / ".claude/harness-tier/config/flow-config.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("design_docs:\n  templates: forms\n", encoding="utf-8")
    seed_design_templates(REPO, tmp_path)
    assert (tmp_path / "forms/table.template.md").is_file()


def test_scripts_are_in_the_copy_list():
    for rel in (
        "scripts/_design_md.py",
        "scripts/design_doc_check.py",
        "scripts/design_doc_render.py",
    ):
        assert rel in COPY_FILES


def test_output_is_ignored_only_when_chosen(tmp_path):
    cfg = tmp_path / ".claude/harness-tier/config/flow-config.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("design_docs:\n  output: out/docx\n", encoding="utf-8")
    append_gitignore(tmp_path)
    assert "out/docx/" not in (tmp_path / ".gitignore").read_text(encoding="utf-8")
    cfg.write_text("design_docs:\n  output: out/docx\n  gitignore_output: true\n", encoding="utf-8")
    append_gitignore(tmp_path)
    append_gitignore(tmp_path)
    assert (tmp_path / ".gitignore").read_text(encoding="utf-8").count("out/docx/") == 1


def test_output_stripping_to_empty_yields_no_line(tmp_path):
    cfg = tmp_path / ".claude/harness-tier/config/flow-config.yaml"
    cfg.parent.mkdir(parents=True)
    cfg.write_text("design_docs:\n  output: '/'\n  gitignore_output: true\n", encoding="utf-8")
    assert design_gitignore_lines(tmp_path) == []


def test_gitignore_survives_a_broken_design_doc_check(tmp_path, monkeypatch):
    """design_doc_check imports yaml + wiki_graph/srs_check at module scope, unlike this
    file's own deferred `import yaml`. A broken/missing design_doc_check must degrade to
    'no design line' rather than taking the base .gitignore lines down with it."""

    def _broken():
        raise ImportError("design_doc_check unavailable")

    monkeypatch.setattr(flow_init_setup, "_design_doc_check", _broken)
    cfg = tmp_path / ".claude/harness-tier/config/flow-config.yaml"
    cfg.parent.mkdir(parents=True)
    # No `output` set, so design_gitignore_lines must reach for the broken import to get
    # the default — that is the path this test proves degrades instead of raising.
    cfg.write_text("design_docs:\n  gitignore_output: true\n", encoding="utf-8")
    report = append_gitignore(tmp_path)
    text = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    for line in GITIGNORE_LINES:
        assert line in text
    assert all("[!]" not in ln for ln in report)
