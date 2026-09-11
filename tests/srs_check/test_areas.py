"""`--areas` is the routing input the /flow SRS step reads.

The absent-docs/srs contract is asserted first: every subcommand inherits it, and a
repo without an SRS must see no output at all rather than a warning it cannot act on.
"""

from pathlib import Path

from tests.srs_check._helpers import run, write


def test_no_srs_dir_is_silent_success(tmp_path: Path, capsys):
    code, out = run(["--root", str(tmp_path), "--areas"], capsys)
    assert code == 0
    assert out == ""


def test_empty_srs_dir_is_silent_success(tmp_path: Path, capsys):
    (tmp_path / "docs" / "srs").mkdir(parents=True)
    code, out = run(["--root", str(tmp_path), "--areas"], capsys)
    assert code == 0
    assert out == ""


def test_areas_lists_stem_and_title(tmp_path: Path, capsys):
    write(tmp_path, "docs/srs/README.md", "# SRS\n")
    write(tmp_path, "docs/srs/payment.md", "---\nwiki_id: srs.payment\n---\n# Payment\n")
    write(tmp_path, "docs/srs/user-auth.md", "# User Auth\n")
    code, out = run(["--root", str(tmp_path), "--areas"], capsys)
    assert code == 0
    assert out.splitlines() == ["payment\tPayment", "user-auth\tUser Auth"]


def test_readme_is_not_an_area(tmp_path: Path, capsys):
    write(tmp_path, "docs/srs/README.md", "# SRS\n")
    code, out = run(["--root", str(tmp_path), "--areas"], capsys)
    assert code == 0
    assert out == ""
