"""The templates /flow-init seeds must pass the check every skill starts with — a
shipped template that fails blocks every consumer on day one."""

import shutil

from scripts.design_doc_check import DOCS, check_templates
from tests.design_docs._helpers import REPO, write

SHIPPED = REPO / "templates" / "design-docs"


def test_every_doc_has_a_shipped_template():
    actual = sorted(p.name for p in SHIPPED.glob("*.template.md"))
    expected = sorted(f"{d}.template.md" for d in DOCS)
    assert actual == expected


def test_shipped_templates_pass(tmp_path):
    write(tmp_path, "docs/srs/README.md", "# SRS\n")
    write(tmp_path, "docs/sds/README.md", "# SDS\n")
    tdir = tmp_path / "t"
    shutil.copytree(SHIPPED, tdir)
    vs = check_templates(tdir, tmp_path)
    assert vs == [], [v.format() for v in vs]


def test_srs_and_sds_ship_with_no_placeholder_revisions_row():
    for name in ("srs", "sds"):
        text = (SHIPPED / f"{name}.template.md").read_text(encoding="utf-8")
        lines = text.splitlines()
        assert not any(ln.startswith("revisions:") for ln in lines)
        assert "YYYY-MM-DD" not in text
