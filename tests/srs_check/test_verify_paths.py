"""`--verify` narrowed to explicit paths.

Link resolution must still see the whole `docs/srs/` directory: only reporting narrows to
what was asked about. Without this, a link into a file outside the requested set resolves
as "outside docs/srs" and a dead link goes silently unchecked — a false clean over exactly
the file a caller pointed at by hand.
"""

from pathlib import Path

from tests.srs_check._helpers import run, write


def _index(body: str = "") -> str:
    return "# SRS\n" + body


def test_explicit_path_still_catches_a_dead_cross_file_link(tmp_path: Path, capsys):
    write(tmp_path, "docs/srs/README.md", _index('<a id="c-001"></a>C-001 Cards.\n'))
    f = write(
        tmp_path,
        "docs/srs/payment.md",
        '# Payment\n<a id="fr-payment-001"></a>(← [C-009](README.md#c-009))\n',
    )
    code, out = run(["--root", str(tmp_path), "--verify", str(f)], capsys)
    assert code == 1
    assert "README.md#c-009" in out


def test_explicit_path_is_clean_over_a_live_cross_file_link(tmp_path: Path, capsys):
    write(tmp_path, "docs/srs/README.md", _index('<a id="c-001"></a>C-001 Cards.\n'))
    f = write(
        tmp_path,
        "docs/srs/payment.md",
        '# Payment\n<a id="fr-payment-001"></a>**FR-PAYMENT-001** '
        "(← [C-001](README.md#c-001)) Pay.\n",
    )
    code, out = run(["--root", str(tmp_path), "--verify", str(f)], capsys)
    assert code == 0
    assert out == ""


def test_explicit_path_does_not_report_a_duplicate_between_two_other_files(tmp_path, capsys):
    write(tmp_path, "docs/srs/payment.md", '# Payment\n<a id="fr-payment-001"></a>\n')
    write(tmp_path, "docs/srs/refund.md", '# Refund\n<a id="fr-payment-001"></a>\n')
    f = write(tmp_path, "docs/srs/shipping.md", "# Shipping\n")
    code, out = run(["--root", str(tmp_path), "--verify", str(f)], capsys)
    assert code == 0
    assert out == ""


def test_no_arguments_still_catches_what_an_explicit_path_call_catches(tmp_path, capsys):
    write(tmp_path, "docs/srs/README.md", _index('<a id="c-001"></a>C-001 Cards.\n'))
    write(
        tmp_path,
        "docs/srs/payment.md",
        '# Payment\n<a id="fr-payment-001"></a>(← [C-009](README.md#c-009))\n',
    )
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 1
    assert "README.md#c-009" in out
