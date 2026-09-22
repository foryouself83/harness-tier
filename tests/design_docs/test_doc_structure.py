"""Structure rules compare the written Markdown to the consumer's template, so an edited
template moves what they demand; each case edits one side and expects one code."""

from pathlib import Path

from scripts._design_md import parse
from scripts.design_doc_check import check_structure, load_templates
from tests.design_docs._fixture import DOCS_MD, TDIR, TEMPLATES, make_host
from tests.design_docs._helpers import write


def run(root: Path, name: str):
    templates = load_templates(root / TDIR)
    rel = f"docs/deliverables/{name}.md"
    doc = parse((root / rel).read_text(encoding="utf-8"))
    return check_structure(root, rel, doc, templates[name], templates)


def codes(vs):
    return sorted(v.code for v in vs)


def test_fixture_is_clean(tmp_path):
    make_host(tmp_path)
    for name in DOCS_MD:
        assert run(tmp_path, name) == [], name


def test_front_matter_rules(tmp_path):
    make_host(tmp_path)
    text = (
        DOCS_MD["erd"]
        .replace("wiki_id: deliverables.erd", "wiki_id: erd")
        .replace("related: [srs.readme]", "related: [srs.nowhere]")
    )
    write(tmp_path, "docs/deliverables/erd.md", text)
    msgs = [v.message for v in run(tmp_path, "erd")]
    assert codes(run(tmp_path, "erd")) == ["S-FRONT", "S-FRONT"]
    assert any("deliverables.erd" in m for m in msgs) and any("srs.nowhere" in m for m in msgs)


def test_missing_front_matter(tmp_path):
    make_host(tmp_path)
    body = DOCS_MD["erd"].split("---\n", 2)[2]
    write(tmp_path, "docs/deliverables/erd.md", body)
    assert "S-FRONT" in codes(run(tmp_path, "erd"))


def test_heading_missing_and_out_of_order(tmp_path):
    make_host(tmp_path)
    text = DOCS_MD["erd"].replace("## 1. 개요\n", "")
    write(tmp_path, "docs/deliverables/erd.md", text)
    assert codes(run(tmp_path, "erd")) == ["S-HEADING"]
    text = DOCS_MD["erd"].replace("## 1. 개요\n## 2. 엔터티\n", "## 2. 엔터티\n## 1. 개요\n")
    write(tmp_path, "docs/deliverables/erd.md", text)
    assert "S-HEADING" in codes(run(tmp_path, "erd"))


def test_template_edit_moves_the_demand(tmp_path):
    make_host(tmp_path)
    write(
        tmp_path,
        f"{TDIR}/erd.template.md",
        TEMPLATES["erd"].replace(
            "| 엔터티ID | 이름 |\n|---|---|", "| 엔터티ID | 이름 | 설명 |\n|---|---|---|"
        ),
    )
    vs = run(tmp_path, "erd")
    assert codes(vs) == ["S-TABLE"] and "설명" in vs[0].message


def test_repeat_block_table_and_id(tmp_path):
    make_host(tmp_path)
    text = DOCS_MD["table"].replace("| 컬럼명 | 타입 | FK |", "| 컬럼명 | 형식 | FK |")
    write(tmp_path, "docs/deliverables/table.md", text)
    assert codes(run(tmp_path, "table")) == ["S-TABLE"]
    text = DOCS_MD["table"].replace('### <a id="tbl-001"></a>TBL-001 payment', "### payment")
    write(tmp_path, "docs/deliverables/table.md", text)
    assert "S-HEADING" in codes(run(tmp_path, "table"))


def test_placeholder_left(tmp_path):
    make_host(tmp_path)
    write(
        tmp_path, "docs/deliverables/erd.md", DOCS_MD["erd"].replace("payment (FR", "{{이름}} (FR")
    )
    assert codes(run(tmp_path, "erd")) == ["S-PLACEHOLDER"]


def test_id_rules(tmp_path):
    make_host(tmp_path)
    text = DOCS_MD["erd"].replace(
        "| 엔터티ID | 이름 |\n|---|---|\n",
        '| 엔터티ID | 이름 |\n|---|---|\n| <a id="ent-001"></a>ENT-001 | dup |\n'
        '| <a id="ent-1"></a>ENT-1 | short |\n| <a id="tbl-009"></a>TBL-009 | foreign |\n',
    )
    write(tmp_path, "docs/deliverables/erd.md", text)
    msgs = [v.message for v in run(tmp_path, "erd") if v.code == "S-ID"]
    assert len(msgs) == 3
    assert any("duplicate" in m for m in msgs)
    assert any("ent-1" in m for m in msgs)
    assert any("table" in m for m in msgs)
