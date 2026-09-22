"""`--templates` runs first in every skill: a consumer-edited template that breaks here
must name the file, the place and the fix, and every break must come out in one pass."""

from pathlib import Path

from scripts.design_doc_check import DOCS, check_doc, check_templates, load_settings
from tests.design_docs._helpers import write

TDIR = ".claude/harness-tier/templates/design-docs"

GOOD = {
    "srs": "---\ndoc: srs\ntitle: SRS\nstandard: 29148\nsources: [docs/srs/*.md]\n---\n",
    "sds": "---\ndoc: sds\ntitle: SDS\nstandard: 1016\nsources: [docs/sds/*.md]\n---\n",
    "architecture": "---\ndoc: architecture\ntitle: A\nstandard: s\nid_prefix: [CMP, IF]\n"
    "refs: [FR, NFR]\n---\n## 1. 개요\n",
    "api": "---\ndoc: api\ntitle: B\nstandard: s\nid_prefix: [API]\nrefs: [FR, CMP]\n"
    "inventory: 부록 A\n---\n## 1. 개요\n## 부록 A\n",
    "erd": "---\ndoc: erd\ntitle: E\nstandard: s\nid_prefix: [ENT]\nrefs: [FR]\n---\n## 1. 개요\n",
    "table": "---\ndoc: table\ntitle: T\nstandard: s\nid_prefix: [TBL]\nrefs: [FR, ENT]\n---\n"
    "## 1. 개요\n## 2. 상세\n<!-- repeat: TBL -->\n### {{TBL-ID}}\n\n"
    "| 컬럼명 | 타입 |\n|---|---|\n",
}


def seed(root: Path, **override: str) -> Path:
    write(root, "docs/srs/README.md", "# SRS\n")
    write(root, "docs/sds/README.md", "# SDS\n")
    for name in DOCS:
        text = override.get(name, GOOD[name])
        if text is not None:
            write(root, f"{TDIR}/{name}.template.md", text)
    return root / TDIR


def codes(vs):
    return sorted(v.code for v in vs)


def test_shipped_shape_is_clean(tmp_path):
    assert check_templates(seed(tmp_path), tmp_path) == []


def test_missing_directory_and_file(tmp_path):
    assert codes(check_templates(tmp_path / TDIR, tmp_path)) == ["T-MISSING"]
    tdir = seed(tmp_path)
    (tdir / "sds.template.md").unlink()
    vs = check_templates(tdir, tmp_path)
    assert codes(vs) == ["T-MISSING"] and vs[0].file == "sds.template.md"


def test_front_rules(tmp_path):
    tdir = seed(
        tmp_path,
        erd="---\ndoc: erdx\ntitle: E\nid_prefix: [ENT]\ncolour: red\n---\n",
    )
    msgs = [v.message for v in check_templates(tdir, tmp_path) if v.code == "T-FRONT"]
    assert any("standard" in m for m in msgs)
    assert any("colour" in m for m in msgs)
    assert any("erdx" in m for m in msgs)


def test_prefix_and_refs(tmp_path):
    tdir = seed(
        tmp_path,
        erd="---\ndoc: erd\ntitle: E\nstandard: s\nid_prefix: [TBL, fr]\nrefs: [XYZ]\n---\n",
    )
    vs = check_templates(tdir, tmp_path)
    assert codes(vs).count("T-PREFIX") == 2  # TBL duplicated, 'fr' malformed
    assert "T-REFS" in codes(vs)


def test_heading_table_repeat(tmp_path):
    tdir = seed(
        tmp_path,
        erd="---\ndoc: erd\ntitle: E\nstandard: s\nid_prefix: [ENT]\n---\n"
        "## 1. 개요\n## 1. 개요\n\n| a | a |\n|---|---|\n<!-- repeat: TBL -->\n",
    )
    got = codes(check_templates(tdir, tmp_path))
    assert got == ["T-HEADING", "T-REPEAT", "T-REPEAT", "T-TABLE"]


def test_sources_must_be_a_non_empty_list_at_templates(tmp_path):
    tdir = seed(tmp_path, sds="---\ndoc: sds\ntitle: S\nstandard: s\nsources: []\n---\n")
    assert codes(check_templates(tdir, tmp_path)) == ["T-SOURCES"]
    tdir = seed(tmp_path, sds="---\ndoc: sds\ntitle: S\nstandard: s\nsources: nope\n---\n")
    assert codes(check_templates(tdir, tmp_path)) == ["T-SOURCES"]


def test_sources_no_match_is_reported_at_doc_not_templates(tmp_path):
    seed(tmp_path, sds="---\ndoc: sds\ntitle: S\nstandard: s\nsources: [docs/none/*.md]\n---\n")
    assert check_templates(tmp_path / TDIR, tmp_path) == []
    vs, _ = check_doc(tmp_path, load_settings(tmp_path), "sds")
    assert codes(vs) == ["T-SOURCES"]


def test_inventory_must_name_a_heading(tmp_path):
    tdir = seed(tmp_path, api=GOOD["api"].replace("## 부록 A\n", ""))
    assert codes(check_templates(tdir, tmp_path)) == ["T-FRONT"]


def test_labels_key_and_value_rules(tmp_path):
    tdir = seed(
        tmp_path,
        erd="---\ndoc: erd\ntitle: E\nstandard: s\nid_prefix: [ENT]\n"
        "labels: {revisions: 개정 이력, colour: red, version: 1}\n---\n",
    )
    msgs = [v.message for v in check_templates(tdir, tmp_path) if v.code == "T-FRONT"]
    assert any("colour" in m for m in msgs)
    assert any("version" in m for m in msgs)


def test_labels_must_be_a_mapping(tmp_path):
    tdir = seed(
        tmp_path,
        erd="---\ndoc: erd\ntitle: E\nstandard: s\nid_prefix: [ENT]\nlabels: [revisions]\n---\n",
    )
    assert codes(check_templates(tdir, tmp_path)) == ["T-FRONT"]


def test_settings_defaults_and_override(tmp_path):
    assert load_settings(tmp_path)["docs"] == "docs/deliverables"
    write(
        tmp_path,
        ".claude/harness-tier/config/flow-config.yaml",
        "design_docs:\n  docs: out/md\n  renderer: http://kroki.local\n",
    )
    s = load_settings(tmp_path)
    assert s["docs"] == "out/md" and s["renderer"] == "http://kroki.local"
    assert s["output"] == "docs/deliverables/results"
