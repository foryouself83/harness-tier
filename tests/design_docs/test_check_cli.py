from scripts.design_doc_check import main
from scripts.wiki_graph import derive_wiki_id
from tests.design_docs._fixture import DOCS_MD, make_host
from tests.design_docs._helpers import write


def test_clean_exits_zero(tmp_path, capsys):
    make_host(tmp_path)
    assert main(["--root", str(tmp_path), "--templates"]) == 0
    assert main(["--root", str(tmp_path), "--doc", "table"]) == 0
    assert "0 violation(s)" in capsys.readouterr().out


def test_every_violation_is_printed_in_one_run(tmp_path, capsys):
    make_host(tmp_path)
    text = (
        DOCS_MD["erd"]
        .replace("## 1. 개요\n", "")
        .replace("payment (FR-PAY-001)", "{{x}} FR-PAY-099")
    )
    write(tmp_path, "docs/deliverables/erd.md", text)
    assert main(["--root", str(tmp_path), "--doc", "erd"]) == 1
    out = capsys.readouterr().out
    for code in ("S-HEADING", "S-PLACEHOLDER", "S-DANGLING"):
        assert code in out
    assert "3 violation(s)" in out


def test_paths_prints_resolved_settings(tmp_path, capsys):
    assert main(["--root", str(tmp_path), "--paths"]) == 0
    out = capsys.readouterr().out
    assert "docs\tdocs/deliverables" in out and "output\tdocs/deliverables/results" in out


def test_wiki_id_uses_the_default_docs_prefix(tmp_path, capsys):
    make_host(tmp_path)
    assert main(["--root", str(tmp_path), "--wiki-id", "erd"]) == 0
    assert capsys.readouterr().out.strip() == "deliverables.erd"


def test_wiki_id_follows_a_custom_docs_setting(tmp_path, capsys):
    make_host(tmp_path)
    cfg = ".claude/harness-tier/config/flow-config.yaml"
    write(tmp_path, cfg, "design_docs:\n  docs: out/md\n")
    assert main(["--root", str(tmp_path), "--wiki-id", "erd"]) == 0
    # The wiki root itself (flow-config wiki.root, default "docs") is untouched by this
    # config, so out/md/erd.md keeps every segment — derive_wiki_id is the one authority
    # for that, never a hand-computed string here.
    assert capsys.readouterr().out.strip() == derive_wiki_id("out/md/erd.md", "docs")


def test_wiki_id_matches_what_s_front_demands(tmp_path, capsys):
    """A document written with the id `--wiki-id` printed must raise no S-FRONT wiki_id
    violation — the two computations share expected_wiki_id() so they cannot drift apart."""
    make_host(tmp_path)
    assert main(["--root", str(tmp_path), "--wiki-id", "erd"]) == 0
    wiki_id = capsys.readouterr().out.strip()
    write(tmp_path, "docs/deliverables/erd.md", DOCS_MD["erd"].replace("deliverables.erd", wiki_id))
    assert main(["--root", str(tmp_path), "--doc", "erd"]) == 0
    assert "S-FRONT" not in capsys.readouterr().out
