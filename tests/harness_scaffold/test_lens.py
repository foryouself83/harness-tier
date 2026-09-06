import json

import pytest

import scripts.harness_scaffold as hs
from tests.harness_scaffold._helpers import _baseline_entry


def test_lens_marker_id_format():
    assert hs.lens_marker_id("typescript-react", "ux") == "code-style:lens:typescript-react:ux"


def test_lens_order_canonical():
    assert hs.LENS_ORDER == (
        "correctness",
        "ux",
        "a11y",
        "performance",
        "security",
        "maintainability",
        "cross-cutting",
        "i18n",
    )


def test_managed_block_wraps_body_with_markers():
    block = hs._managed_block("code-style:lens:go:performance", "### Performance\n- x")
    assert block.startswith("<!-- code-style:lens:go:performance BEGIN")
    assert block.rstrip().endswith("<!-- code-style:lens:go:performance END -->")
    assert "### Performance\n- x" in block


_FLAT = "# React Code Style\n\n## Best Practices\n- keep components small\n\n## Toolchain\n- vite\n"


def _lens_doc(stack):
    return (
        "# X\n\n## Best Practices (by quality lens)\n"
        + hs._managed_block(hs.lens_marker_id(stack, "ux"), "### UX\n- guard")
        + "\n## Toolchain\n- x\n"
    )


def test_find_bp_section_spans_heading_to_next_h2():
    s, e = hs.find_bp_section(_FLAT)
    assert _FLAT[s:e].startswith("## Best Practices")
    assert "## Toolchain" not in _FLAT[s:e]


def test_find_bp_section_none_when_absent():
    assert hs.find_bp_section("# X\n\n## Toolchain\n- x\n") is None


def test_find_bp_section_h3_does_not_terminate():
    # A '### sub' heading inside Best Practices must NOT end the section;
    # only a top-level '## ' heading (or EOF) does. Content after the first
    # '###' must remain inside the span.
    doc = (
        "# X\n\n## Best Practices (by quality lens)\n"
        "### UX\n- guard\n"
        "### Performance\n- cache\n"
        "\n## Toolchain\n- vite\n"
    )
    s, e = hs.find_bp_section(doc)
    span = doc[s:e]
    assert "### Performance" in span  # content after the first ### stays inside
    assert "- cache" in span
    assert "## Toolchain" not in span  # only the real h2 terminates


def test_scan_flat_doc():
    r = hs.scan_code_style(_FLAT, "typescript-react")
    assert r == {"has_bp": True, "state": "flat", "present": []}


def test_scan_lens_doc_reports_present():
    r = hs.scan_code_style(_lens_doc("go"), "go")
    assert r["state"] == "lens"
    assert r["present"] == ["ux"]


def test_scan_no_bp_heading_is_none_state():
    r = hs.scan_code_style("# X\n\n## Toolchain\n- x\n", "go")
    assert r == {"has_bp": False, "state": None, "present": []}


def test_scan_recognizes_by_quality_lens_suffix_heading():
    # heading variant must still be found
    assert hs.find_bp_section(_lens_doc("go")) is not None


def test_upsert_lens_block_inserts_in_canonical_order():
    # doc already has 'ux'; inserting 'correctness' (earlier) must land BEFORE ux
    doc = _lens_doc("go")
    out = hs.upsert_lens_block(doc, "go", "correctness", "### Correctness\n- c")
    i_corr = out.index("code-style:lens:go:correctness BEGIN")
    i_ux = out.index("code-style:lens:go:ux BEGIN")
    assert i_corr < i_ux
    assert "## Toolchain" in out  # sibling section preserved


def test_upsert_lens_block_replaces_existing():
    doc = _lens_doc("go")
    out = hs.upsert_lens_block(doc, "go", "ux", "### UX\n- NEW")
    assert "- NEW" in out
    assert out.count("code-style:lens:go:ux BEGIN") == 1  # not duplicated


def test_upsert_lens_block_inserts_at_end_when_no_later_lens():
    # 'i18n' is last in LENS_ORDER; the doc's only lens is 'ux' (earlier), so there is
    # no later-ordered lens present -> i18n must be inserted at the END of the Best
    # Practices section, still BEFORE the '## Toolchain' sibling (not appended to EOF).
    doc = _lens_doc("go")
    out = hs.upsert_lens_block(doc, "go", "i18n", "### i18n\n- locale")
    i_i18n = out.index("code-style:lens:go:i18n BEGIN")
    i_tool = out.index("## Toolchain")
    i_ux = out.index("code-style:lens:go:ux BEGIN")
    assert i_ux < i_i18n < i_tool


def test_upsert_lens_block_requires_bp_section():
    with pytest.raises(ValueError):
        hs.upsert_lens_block("# X\n\n## Toolchain\n- x\n", "go", "ux", "b")


def test_build_bp_section_orders_by_lens_order():
    section = hs.build_bp_section("go", [("ux", "### UX"), ("correctness", "### C")])
    assert section.startswith("## Best Practices (by quality lens)")
    assert section.index("correctness BEGIN") < section.index("ux BEGIN")


def test_replace_bp_section_swaps_flat_and_keeps_siblings():
    out = hs.replace_bp_section(_FLAT, "typescript-react", [("ux", "### UX\n- g")])
    assert "keep components small" not in out  # flat prose replaced
    assert "code-style:lens:typescript-react:ux BEGIN" in out
    assert "## Toolchain" in out and "- vite" in out  # sibling preserved


def test_replace_bp_section_requires_bp_section():
    with pytest.raises(ValueError):
        hs.replace_bp_section("# X\n\n## Toolchain\n- x\n", "go", [("ux", "### UX\n- b")])


def _plan(entry):
    return {"files": [entry]}


def test_apply_lens_upsert_creates_when_absent(tmp_path):
    entry = {
        "action": "lens_upsert",
        "path": "docs/code-style/go.md",
        "stack": "go",
        "lenses": [{"lens": "performance", "body": "### Performance\n- p"}],
    }
    rep = hs.apply_plan(tmp_path, _plan(entry))
    out = (tmp_path / "docs/code-style/go.md").read_text(encoding="utf-8")
    assert "docs/code-style/go.md" in rep["created"]
    assert "code-style:lens:go:performance BEGIN" in out


def test_apply_lens_upsert_additive_on_lens_doc(tmp_path):
    p = tmp_path / "docs/code-style/go.md"
    p.parent.mkdir(parents=True)
    p.write_text(_lens_doc("go"), encoding="utf-8")
    entry = {
        "action": "lens_upsert",
        "path": "docs/code-style/go.md",
        "stack": "go",
        "lenses": [{"lens": "performance", "body": "### Performance\n- p"}],
    }
    rep = hs.apply_plan(tmp_path, _plan(entry))
    out = p.read_text(encoding="utf-8")
    assert "code-style:lens:go:ux BEGIN" in out  # existing kept
    assert "code-style:lens:go:performance BEGIN" in out  # new added
    assert "docs/code-style/go.md" in rep["updated"]


def test_apply_lens_upsert_migrate_replaces_flat(tmp_path):
    p = tmp_path / "docs/code-style/react.md"
    p.parent.mkdir(parents=True)
    p.write_text(_FLAT, encoding="utf-8")
    entry = {
        "action": "lens_upsert",
        "path": "docs/code-style/react.md",
        "stack": "typescript-react",
        "migrate": True,
        "lenses": [{"lens": "ux", "body": "### UX\n- g"}],
    }
    rep = hs.apply_plan(tmp_path, _plan(entry))
    out = p.read_text(encoding="utf-8")
    assert "keep components small" not in out
    assert "code-style:lens:typescript-react:ux BEGIN" in out
    assert "docs/code-style/react.md" in rep["updated"]


def test_validate_plan_accepts_lens_upsert(tmp_path):
    # a lens_upsert entry (no 'content' key; 'lenses' instead) must not be falsely rejected —
    # the baseline marker_upsert entry is required for validate_plan to report ok, independent
    # of the lens_upsert entry itself.
    plan = {
        "files": [
            _baseline_entry(),
            {
                "action": "lens_upsert",
                "path": "docs/code-style/go.md",
                "stack": "go",
                "lenses": [{"lens": "ux", "body": "### UX\n- x"}],
            },
        ]
    }
    result = hs.validate_plan(tmp_path, plan)
    assert result["ok"] is True
    assert result["issues"] == []


def test_main_scan_absent_file_reports_exists_false(tmp_path, capsys):
    missing = tmp_path / "docs/code-style/go.md"
    rc = hs.main(["scan", str(missing), "go"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out == {"exists": False, "has_bp": False, "state": None, "present": []}


def test_main_scan_flat_doc_reports_state_flat(tmp_path, capsys):
    p = tmp_path / "react.md"
    p.write_text(_FLAT, encoding="utf-8")
    rc = hs.main(["scan", str(p), "typescript-react"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["exists"] is True
    assert out["state"] == "flat"
    assert out["present"] == []


def test_main_scan_lens_doc_reports_present(tmp_path, capsys):
    p = tmp_path / "go.md"
    p.write_text(_lens_doc("go"), encoding="utf-8")
    rc = hs.main(["scan", str(p), "go"])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["exists"] is True
    assert out["state"] == "lens"
    assert out["present"] == ["ux"]
