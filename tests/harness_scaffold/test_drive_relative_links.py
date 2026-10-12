"""A link carrying a drive letter is outside root, and the link check never reads it."""

import pytest

import scripts.harness_scaffold as hs
from tests.harness_scaffold._helpers import _baseline_entry


def test_a_drive_relative_link_is_never_read(tmp_path):
    # `C:..\..\outside.md` carries no separator after the colon. `Path(rel).parent / link`
    # keeps it whole, and `root / target` on the same drive joins it under root, so the
    # `..` runs climb out to a real file.
    outside = tmp_path / "outside.md"
    outside.write_text("# Secret Heading\n", encoding="utf-8")
    drive = str(tmp_path).split(":", 1)[0]
    if len(drive) != 1:
        pytest.skip("drive-relative paths are a Windows shape")
    entry = {
        "path": ".claude/rules/x-conventions.md",
        "action": "create",
        # A fragment the outside file does NOT carry, so a read reports it as dead.
        "content": f"[x]({drive}:../../outside.md#not-in-that-file)\n",
    }
    rep = hs.validate_plan(tmp_path / "a" / "root", {"files": [_baseline_entry(), entry]})
    assert not [i for i in rep["issues"] if i["kind"] in ("dead-link", "dead-anchor")]


@pytest.mark.parametrize("link", ["C:x.md", "c:docs/x.md", "D:../x.md"])
def test_any_drive_prefix_reads_as_outside_root(link):
    assert hs._WIN_ABS_RE.match(link)
