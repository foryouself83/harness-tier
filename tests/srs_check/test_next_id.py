"""Numbers are issued, never chosen — by a human or a model.

The KIND set is open: nothing here enumerates it. A kind is whatever a document already
anchors, so adding one is writing an anchor, not editing this script.
"""

from pathlib import Path

from tests.srs_check._helpers import run, write


def test_first_id_in_an_empty_area_file(tmp_path: Path, capsys):
    f = write(tmp_path, "docs/srs/payment.md", "# Payment\n")
    code, out = run(["--root", str(tmp_path), "--next-id", str(f), "--kind", "FR"], capsys)
    assert code == 0
    assert out.strip() == "FR-PAYMENT-001"


def test_continues_from_the_highest_existing(tmp_path: Path, capsys):
    f = write(
        tmp_path,
        "docs/srs/payment.md",
        '# Payment\n<a id="fr-payment-001"></a>\n<a id="fr-payment-007"></a>\n',
    )
    code, out = run(["--root", str(tmp_path), "--next-id", str(f), "--kind", "FR"], capsys)
    assert out.strip() == "FR-PAYMENT-008"


def test_area_prefix_comes_from_the_file_stem(tmp_path: Path, capsys):
    f = write(tmp_path, "docs/srs/user-auth.md", "# User Auth\n")
    code, out = run(["--root", str(tmp_path), "--next-id", str(f), "--kind", "FR"], capsys)
    assert out.strip() == "FR-USER-AUTH-001"


def test_readme_takes_no_area_prefix(tmp_path: Path, capsys):
    f = write(tmp_path, "docs/srs/README.md", '# SRS\n<a id="c-003"></a>\n')
    code, out = run(["--root", str(tmp_path), "--next-id", str(f), "--kind", "C"], capsys)
    assert out.strip() == "C-004"


def test_scope_separates_counters_in_one_file(tmp_path: Path, capsys):
    f = write(
        tmp_path,
        "docs/srs/README.md",
        '# SRS\n<a id="nfr-perf-001"></a>\n<a id="nfr-security-001"></a>\n'
        '<a id="nfr-security-002"></a>\n',
    )
    _, perf = run(
        ["--root", str(tmp_path), "--next-id", str(f), "--kind", "NFR", "--scope", "perf"],
        capsys,
    )
    assert perf.strip() == "NFR-PERF-002"
    _, sec = run(
        ["--root", str(tmp_path), "--next-id", str(f), "--kind", "NFR", "--scope", "security"],
        capsys,
    )
    assert sec.strip() == "NFR-SECURITY-003"


def test_an_unlisted_kind_needs_no_code_change(tmp_path: Path, capsys):
    f = write(tmp_path, "docs/srs/README.md", '# SRS\n<a id="risk-002"></a>\n')
    code, out = run(["--root", str(tmp_path), "--next-id", str(f), "--kind", "RISK"], capsys)
    assert code == 0
    assert out.strip() == "RISK-003"


def test_a_scoped_kind_ignores_an_unscoped_one(tmp_path: Path, capsys):
    """`c-003` must not feed the `C-PAYMENT-nnn` counter, nor the reverse."""
    f = write(
        tmp_path,
        "docs/srs/payment.md",
        '# Payment\n<a id="fr-001"></a>\n<a id="fr-payment-002"></a>\n',
    )
    _, out = run(["--root", str(tmp_path), "--next-id", str(f), "--kind", "FR"], capsys)
    assert out.strip() == "FR-PAYMENT-003"


def test_missing_file_is_silent_success(tmp_path: Path, capsys):
    f = tmp_path / "docs" / "srs" / "gone.md"
    code, out = run(["--root", str(tmp_path), "--next-id", str(f), "--kind", "FR"], capsys)
    assert code == 0
    assert out == ""


def test_unscoped_next_id_is_rejected_once_the_kind_is_axis_scoped(tmp_path: Path, capsys):
    f = write(tmp_path, "docs/srs/README.md", '# SRS\n<a id="nfr-perf-001"></a>\n')
    code, out = run(["--root", str(tmp_path), "--next-id", str(f), "--kind", "NFR"], capsys)
    assert code != 0
    assert "NFR-001" not in out
    assert "--scope" in out


def test_unscoped_next_id_is_rejected_by_a_bare_section_anchor_too(tmp_path: Path, capsys):
    """A freshly scaffolded axis carries only its section anchor, no item yet."""
    f = write(tmp_path, "docs/srs/README.md", '# SRS\n<a id="nfr-perf"></a>Performance\n')
    code, out = run(["--root", str(tmp_path), "--next-id", str(f), "--kind", "NFR"], capsys)
    assert code != 0
    assert "--scope" in out


def test_unscoped_next_id_still_works_for_a_kind_with_no_scoped_history(tmp_path: Path, capsys):
    """Not special-cased by name: NFR itself stays open until a document scopes it."""
    f = write(tmp_path, "docs/srs/README.md", '# SRS\n<a id="nfr-003"></a>\n')
    code, out = run(["--root", str(tmp_path), "--next-id", str(f), "--kind", "NFR"], capsys)
    assert code == 0
    assert out.strip() == "NFR-004"


def test_explicit_scope_still_works_once_the_kind_is_axis_scoped(tmp_path: Path, capsys):
    f = write(tmp_path, "docs/srs/README.md", '# SRS\n<a id="nfr-perf-001"></a>\n')
    code, out = run(
        ["--root", str(tmp_path), "--next-id", str(f), "--kind", "NFR", "--scope", "perf"],
        capsys,
    )
    assert code == 0
    assert out.strip() == "NFR-PERF-002"
