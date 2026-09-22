"""Reference rules: an id nobody issued, an FR nobody maps, an entity with no table —
the 'missing or nonexistent id' check the skills exist for."""

from scripts.design_doc_check import check_doc, load_settings
from tests.design_docs._fixture import DOCS_MD, SDS, make_host
from tests.design_docs._helpers import write


def run(root, name):
    return check_doc(root, load_settings(root), name)


def codes(vs):
    return sorted(v.code for v in vs)


def test_all_clean(tmp_path):
    make_host(tmp_path)
    for name in ("srs", "sds", "architecture", "api", "erd", "table"):
        vs, _ = run(tmp_path, name)
        assert vs == [], (name, [v.format() for v in vs])


def test_dangling_link_token_and_refs(tmp_path):
    make_host(tmp_path)
    text = DOCS_MD["erd"].replace(
        "payment (FR-PAY-001)", "payment (FR-PAY-099, CMP-001) [x](../srs/pay.md#fr-pay-777)"
    )
    write(tmp_path, "docs/deliverables/erd.md", text)
    msgs = [v.message for v in run(tmp_path, "erd")[0] if v.code == "S-DANGLING"]
    assert any("FR-PAY-099" in m for m in msgs)
    assert any("fr-pay-777" in m for m in msgs)
    assert any("CMP" in m and "refs" in m for m in msgs)


def test_cover_architecture(tmp_path):
    make_host(tmp_path)
    write(
        tmp_path,
        "docs/deliverables/architecture.md",
        DOCS_MD["architecture"].replace(", [NFR-PERF-001](../srs/README.md#nfr-perf-001)", ""),
    )
    vs, _ = run(tmp_path, "architecture")
    assert codes(vs) == ["S-COVER"] and "NFR-PERF-001" in vs[0].message


def test_cover_inventory(tmp_path):
    make_host(tmp_path)
    text = DOCS_MD["api"].replace(
        "| POST /pay | src/app.py | API-001 |",
        "| POST /pay | src/app.py | API-001 |\n| GET /x | src/app.py | |\n"
        "| GET /y | src/app.py | N/A: health |",
    )
    text = text.replace('```bash\ngrep -rn "@app.post" src\n```\n', "")
    write(tmp_path, "docs/deliverables/api.md", text)
    msgs = [v.message for v in run(tmp_path, "api")[0] if v.code == "S-COVER"]
    assert len(msgs) == 2
    assert any("GET /x" in m for m in msgs) and any("command" in m for m in msgs)


def test_cover_sds(tmp_path):
    make_host(tmp_path)
    write(
        tmp_path,
        "docs/sds/README.md",
        SDS.replace("[FR-PAY-001](../srs/pay.md#fr-pay-001)", "no FR mapping"),
    )
    vs, _ = run(tmp_path, "sds")
    assert codes(vs) == ["S-COVER"]


def test_cross_entity_without_table_and_fk(tmp_path):
    make_host(tmp_path)
    write(
        tmp_path,
        "docs/deliverables/table.md",
        DOCS_MD["table"]
        .replace("payment (ENT-001)", "payment")
        .replace("| id | int | - |", "| id | int | TBL-042 |"),
    )
    msgs = [v.message for v in run(tmp_path, "table")[0] if v.code == "S-CROSS"]
    assert any("ENT-001" in m for m in msgs)
    assert any("TBL-042" in m for m in msgs)


def test_cross_api_needs_component(tmp_path):
    make_host(tmp_path)
    write(
        tmp_path,
        "docs/deliverables/api.md",
        DOCS_MD["api"].replace("| 컴포넌트 | [CMP-001](architecture.md#cmp-001) |\n", ""),
    )
    vs, _ = run(tmp_path, "api")
    assert codes(vs) == ["S-CROSS"]


def test_cross_is_skipped_until_the_other_doc_exists(tmp_path):
    make_host(tmp_path)
    (tmp_path / "docs/deliverables/erd.md").unlink()
    write(
        tmp_path,
        "docs/deliverables/table.md",
        DOCS_MD["table"].replace("payment (ENT-001)", "payment"),
    )
    vs, notes = run(tmp_path, "table")
    assert vs == [] and any("erd" in n for n in notes)


def test_source_and_diagram(tmp_path):
    make_host(tmp_path)
    text = (
        DOCS_MD["erd"].replace("src/models.py", "src/gone.py")
        + "\n```mermaid\n\n```\n\n```mermaid\nnope\n```\n"
    )
    write(tmp_path, "docs/deliverables/erd.md", text)
    got = codes(run(tmp_path, "erd")[0])
    assert got == ["S-DIAGRAM", "S-DIAGRAM", "S-SOURCE"]


def test_srs_runs_srs_check(tmp_path):
    make_host(tmp_path)
    write(tmp_path, "docs/srs/pay.md", '# Pay\n<a id="fr-pay-001"></a>\n<a id="fr-pay-001"></a>\n')
    assert "SRS-VERIFY" in codes(run(tmp_path, "srs")[0])


def test_missing_document(tmp_path):
    make_host(tmp_path)
    (tmp_path / "docs/deliverables/erd.md").unlink()
    assert codes(run(tmp_path, "erd")[0]) == ["S-MISSING"]


def test_sources_front_matter_key_with_null_value_is_clean(tmp_path):
    make_host(tmp_path)
    text = DOCS_MD["erd"].replace("sources: {}", "sources: {src/models.py: null}")
    write(tmp_path, "docs/deliverables/erd.md", text)
    assert run(tmp_path, "erd")[0] == []


def test_sources_front_matter_key_with_sha_value_is_clean(tmp_path):
    make_host(tmp_path)
    text = DOCS_MD["erd"].replace("sources: {}", "sources: {src/models.py: 3f2a9c1}")
    write(tmp_path, "docs/deliverables/erd.md", text)
    assert run(tmp_path, "erd")[0] == []


def test_sources_front_matter_missing_key_path_is_reported(tmp_path):
    make_host(tmp_path)
    text = DOCS_MD["erd"].replace("sources: {}", "sources: {src/gone.py: null}")
    write(tmp_path, "docs/deliverables/erd.md", text)
    msgs = [v.message for v in run(tmp_path, "erd")[0] if v.code == "S-SOURCE"]
    assert any("src/gone.py" in m for m in msgs)


def test_sources_front_matter_non_mapping_is_s_front(tmp_path):
    make_host(tmp_path)
    text = DOCS_MD["erd"].replace("sources: {}", "sources: [src/models.py]")
    write(tmp_path, "docs/deliverables/erd.md", text)
    assert "S-FRONT" in codes(run(tmp_path, "erd")[0])


def test_diagram_skips_mermaid_directive_and_title_block(tmp_path):
    make_host(tmp_path)
    text = DOCS_MD["erd"] + (
        "\n```mermaid\n%%{init: {'theme': 'dark'}}%%\nerDiagram\n  A ||--o{ B : has\n```\n"
        "\n```mermaid\n---\ntitle: My Diagram\n---\nerDiagram\n  A ||--o{ B : has\n```\n"
    )
    write(tmp_path, "docs/deliverables/erd.md", text)
    assert codes(run(tmp_path, "erd")[0]) == []
