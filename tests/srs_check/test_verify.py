"""What incremental editing breaks, and nothing else currently reads.

The cross-file case is the one the split introduced: a C lives in README while the FR
citing it lives in an area file, so a same-file fragment check would pass a dead link.
"""

import re
from pathlib import Path

from tests.srs_check._helpers import REPO, run, write

_TEMPLATE_PATH = REPO / "skills/harness-authoring/templates/srs-area.template.md"
_FORMAT_COMMENT_RE = re.compile(r"<!-- Format —.*?-->", re.DOTALL)


def _index(body: str = "") -> str:
    return "# SRS\n" + body


def _template_format_comment() -> str:
    """The template's own "Format —" worked example, read fresh from disk.

    Not retyped: a copy drifts silently from the template it is supposed to track, which
    is exactly the bug this file exists to catch.
    """
    text = _TEMPLATE_PATH.read_text(encoding="utf-8")
    m = _FORMAT_COMMENT_RE.search(text)
    assert m, f"no 'Format —' comment found in {_TEMPLATE_PATH}"
    return m.group(0) + "\n"


def test_clean_tree_is_silent_success(tmp_path: Path, capsys):
    write(tmp_path, "docs/srs/README.md", _index('<a id="c-001"></a>C-001 Cards.\n'))
    write(
        tmp_path,
        "docs/srs/payment.md",
        '# Payment\n<a id="fr-payment-001"></a>**FR-PAYMENT-001** '
        "(← [C-001](README.md#c-001)) Pay.\n",
    )
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 0
    assert out == ""


def test_dead_cross_file_link(tmp_path: Path, capsys):
    write(tmp_path, "docs/srs/README.md", _index('<a id="c-001"></a>C-001 Cards.\n'))
    write(
        tmp_path,
        "docs/srs/payment.md",
        '# Payment\n<a id="fr-payment-001"></a>(← [C-009](README.md#c-009))\n',
    )
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 1
    assert "README.md#c-009" in out
    assert "payment.md" in out


def test_dead_same_file_fragment(tmp_path: Path, capsys):
    write(tmp_path, "docs/srs/README.md", _index("[gone](#nfr-perf-004)\n"))
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 1
    assert "#nfr-perf-004" in out


def test_duplicate_anchor_in_one_file(tmp_path: Path, capsys):
    write(
        tmp_path,
        "docs/srs/payment.md",
        '# Payment\n<a id="fr-payment-001"></a>\n<a id="fr-payment-001"></a>\n',
    )
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 1
    assert "fr-payment-001" in out


def test_duplicate_anchor_across_area_files(tmp_path: Path, capsys):
    """Two branches issuing the same number is detected, not prevented."""
    write(tmp_path, "docs/srs/payment.md", '# Payment\n<a id="fr-payment-001"></a>\n')
    write(tmp_path, "docs/srs/refund.md", '# Refund\n<a id="fr-payment-001"></a>\n')
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 1
    assert "fr-payment-001" in out


def test_prefix_mismatch_in_an_area_file(tmp_path: Path, capsys):
    write(tmp_path, "docs/srs/payment.md", '# Payment\n<a id="fr-refund-001"></a>\n')
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 1
    assert "fr-refund-001" in out
    assert "payment" in out


def test_index_anchors_take_no_prefix_check(tmp_path: Path, capsys):
    write(
        tmp_path,
        "docs/srs/README.md",
        _index('<a id="c-001"></a>\n<a id="nfr-perf-001"></a>\n<a id="role-001"></a>\n'),
    )
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 0
    assert out == ""


def test_external_and_absolute_links_are_out_of_scope(tmp_path: Path, capsys):
    write(
        tmp_path,
        "docs/srs/README.md",
        _index("[x](https://example.com#frag)\n[y](../sds/README.md#mod)\n"),
    )
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 0
    assert out == ""


def test_no_srs_dir_is_silent_success(tmp_path: Path, capsys):
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 0
    assert out == ""


def test_titled_link_to_dead_anchor_is_caught(tmp_path: Path, capsys):
    write(
        tmp_path,
        "docs/srs/README.md",
        _index('[C-999](README.md#c-999 "customer requirement")\n'),
    )
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 1
    assert "c-999" in out


def test_titled_link_to_live_anchor_is_not_flagged(tmp_path: Path, capsys):
    write(
        tmp_path,
        "docs/srs/README.md",
        _index('<a id="c-001"></a>C-001 Cards.\n[C-001](README.md#c-001 "customer requirement")\n'),
    )
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 0
    assert out == ""


def test_anchor_in_code_fence_is_not_a_definition(tmp_path: Path, capsys):
    """An example anchor fenced as code must not collide with the real one below it."""
    write(
        tmp_path,
        "docs/srs/payment.md",
        '# Payment\n```\n<a id="fr-payment-001"></a>\n```\n<a id="fr-payment-001"></a>\n',
    )
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 0
    assert out == ""


def test_template_format_comment_anchor_is_not_a_definition(tmp_path: Path, capsys):
    write(
        tmp_path,
        "docs/srs/payment.md",
        "# Payment\n"
        + _template_format_comment()
        + '<a id="fr-payment-001"></a>**FR-PAYMENT-001** Pay.\n',
    )
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 0
    assert out == ""


def test_template_format_comment_link_to_undefined_id_does_not_fail(tmp_path: Path, capsys):
    """The comment's own worked example — `[C-003](README.md#c-003)` — cites an id a
    document following the template need not have defined yet; it must not fail CI."""
    write(tmp_path, "docs/srs/README.md", _index('<a id="c-001"></a>C-001 Cards.\n'))
    write(tmp_path, "docs/srs/payment.md", "# Payment\n" + _template_format_comment())
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 0
    assert out == ""


def test_real_dead_link_still_reported_beside_the_template_comment(tmp_path: Path, capsys):
    """Stripping the comment's own link must not blind the checker to a real one."""
    write(tmp_path, "docs/srs/README.md", _index('<a id="c-001"></a>C-001 Cards.\n'))
    write(
        tmp_path,
        "docs/srs/payment.md",
        "# Payment\n"
        + _template_format_comment()
        + '<a id="fr-payment-001"></a>(← [C-999](README.md#c-999))\n',
    )
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 1
    assert "README.md#c-999" in out


def test_duplicate_survives_alongside_a_commented_example(tmp_path: Path, capsys):
    """The comment/code-fence exclusion must not swallow a genuine duplicate."""
    write(
        tmp_path,
        "docs/srs/payment.md",
        "# Payment\n"
        '<!-- example: <a id="fr-payment-999"></a> -->\n'
        '<a id="fr-payment-001"></a>\n'
        '<a id="fr-payment-001"></a>\n',
    )
    code, out = run(["--root", str(tmp_path), "--verify"], capsys)
    assert code == 1
    assert "fr-payment-001" in out
