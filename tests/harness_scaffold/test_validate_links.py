import scripts.harness_scaffold as hs
from tests.harness_scaffold._helpers import _baseline_entry


def _conv_entry(content):
    return {"path": ".claude/rules/x-conventions.md", "action": "create", "content": content}


def test_validate_ops_line_limit_ok(tmp_path):
    body = (
        "<!-- ops-conventions -->\n"
        "- 에러: RFC-9457 → docs/code-style/x.md#err\n"
        "- 로깅: 레벨 → docs/code-style/x.md#log\n"
    )
    rep = hs.validate_plan(tmp_path, {"files": [_baseline_entry(), _conv_entry(body)]})
    assert not [i for i in rep["issues"] if i["kind"] == "ops-line-limit"]


def test_validate_ops_line_limit_violation(tmp_path):
    body = "<!-- ops-conventions -->\n- 에러: 1\n  2\n  3\n  4\n"
    rep = hs.validate_plan(tmp_path, {"files": [_baseline_entry(), _conv_entry(body)]})
    hits = [i for i in rep["issues"] if i["kind"] == "ops-line-limit"]
    assert len(hits) == 1 and hits[0]["severity"] == "high"
    assert not rep["ok"]


def test_ops_blocks_none_without_anchor():
    assert hs._ops_directive_blocks("- a\n- b\n") == []


def test_ops_blocks_splits_top_level_items():
    body = "<!-- ops-conventions -->\n- 에러: RFC-9457 → docs#err\n- 로깅: 레벨 규칙 → docs#log\n"
    blocks = hs._ops_directive_blocks(body)
    assert len(blocks) == 2
    assert blocks[0][0].startswith("- 에러")


def test_ops_blocks_collects_wrapped_continuation():
    body = "<!-- ops-conventions -->\n- 에러: 1\n  cont2\n  cont3\n  cont4\n\n- 로깅: ok\n"
    blocks = hs._ops_directive_blocks(body)
    assert len(blocks[0]) == 4  # the `- 에러` line + 3 continuation lines
    assert len(blocks[1]) == 1


def test_validate_dead_link_ignores_image(tmp_path):
    # image embeds ![..](..) are not subject to the dead-link check.
    plan = {
        "files": [
            _baseline_entry(),
            {
                "path": ".claude/agents/a.md",
                "action": "create",
                "content": "---\nname: a\ndescription: d\n---\n![diagram](./pic.md)",
            },
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert not any(i["kind"] == "dead-link" for i in rep["issues"])


def test_validate_dead_link_ignores_frontmatter(tmp_path):
    # links inside frontmatter (description) are not subject to the body scan.
    plan = {
        "files": [
            _baseline_entry(),
            {
                "path": ".claude/agents/a.md",
                "action": "create",
                "content": "---\nname: a\ndescription: see [x](./missing.md)\n---\nbody",
            },
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert not any(i["kind"] == "dead-link" for i in rep["issues"])


def test_validate_corrupt_marker_detected_despite_bad_encoding(tmp_path):
    # even if an existing file on a cp949 host cannot be utf-8 decoded, marker (ASCII)
    # corruption must be detected.
    cm = tmp_path / "CLAUDE.md"
    begin = hs._marker_begin("harness:baseline").encode("utf-8")
    bad = "필수 룰\n".encode("cp949")  # bytes that cannot be decoded as utf-8
    cm.write_bytes(begin + b"\n" + bad)  # only BEGIN, no END → corrupt
    rep = hs.validate_plan(tmp_path, {"files": [_baseline_entry()]})
    assert any(i["kind"] == "marker" and "corrupt" in i["detail"] for i in rep["issues"])


def test_validate_dead_link_ignores_inline_code(tmp_path):
    # a link example inside inline code is not a dead-link.
    plan = {
        "files": [
            _baseline_entry(),
            {
                "path": ".claude/agents/a.md",
                "action": "create",
                "content": "---\nname: a\ndescription: d\n---\n쓰지 말 것: `[x](./gone.md)`",
            },
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert not any(i["kind"] == "dead-link" for i in rep["issues"])


def test_validate_dead_link_ignores_code_fence(tmp_path):
    # a link inside a code-fence block is not a dead-link.
    plan = {
        "files": [
            _baseline_entry(),
            {
                "path": ".claude/agents/a.md",
                "action": "create",
                "content": "---\nname: a\ndescription: d\n---\n```\n[x](./gone.md)\n```",
            },
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert not any(i["kind"] == "dead-link" for i in rep["issues"])


def test_parse_frontmatter_block_scalar_fallback(monkeypatch):
    # even in the yaml-absent fallback, preserve a block-scalar (>) multi-line description.
    monkeypatch.setattr(hs, "yaml", None)
    text = "---\nname: a\ndescription: >\n  line one\n  line two\n---\nbody"
    fm = hs._parse_frontmatter(text)
    assert fm["name"] == "a"
    assert fm["description"] == "line one line two"


def _linking_plan(target_content, link):
    return {
        "files": [
            _baseline_entry(),
            {"path": "docs/sds/README.md", "action": "create", "content": f"[FR]({link})"},
            {"path": "docs/srs/README.md", "action": "create", "content": target_content},
        ]
    }


def _anchor_issues(tmp_path, target_content, link):
    rep = hs.validate_plan(tmp_path, _linking_plan(target_content, link))
    return [i for i in rep["issues"] if i["kind"] == "dead-anchor"]


def test_dead_anchor_warns(tmp_path):
    hits = _anchor_issues(tmp_path, '<a id="fr-001"></a>FR-001\n', "../srs/README.md#fr-999")
    assert len(hits) == 1 and hits[0]["severity"] == "warn"


def test_explicit_anchor_resolves(tmp_path):
    assert _anchor_issues(tmp_path, '<a id="fr-001"></a>FR-001\n', "../srs/README.md#fr-001") == []


def test_heading_slug_resolves(tmp_path):
    # An <a id> lookup alone would flag every heading link in this repo's own docs.
    assert (
        _anchor_issues(
            tmp_path, "## Requirements Coverage\n", "../srs/README.md#requirements-coverage"
        )
        == []
    )


def test_hangul_heading_slug_resolves(tmp_path):
    # GitHub keeps unicode letters in a slug; an ASCII-only strip makes every Korean
    # heading link a false positive.
    assert _anchor_issues(tmp_path, "## 요구 추적\n", "../srs/README.md#요구-추적") == []


def test_link_without_fragment_is_not_checked(tmp_path):
    assert _anchor_issues(tmp_path, "no anchors here\n", "../srs/README.md") == []


def test_anchor_check_skips_an_unresolvable_target(tmp_path):
    # A target that is neither in the plan nor on disk is already a dead-link; adding a
    # second issue for the same cause is noise.
    plan = {
        "files": [
            _baseline_entry(),
            {
                "path": "docs/sds/README.md",
                "action": "create",
                "content": "[FR](../nope/README.md#fr-001)",
            },
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert not [i for i in rep["issues"] if i["kind"] == "dead-anchor"]


def test_slugify_strips_inline_markup():
    assert hs._slugify("`code` and **bold**") == "code-and-bold"


def test_slugify_unwraps_a_link():
    assert hs._slugify("[FR-001](../srs/README.md) 매핑") == "fr-001-매핑"


def test_github_line_fragment_is_not_an_anchor(tmp_path):
    # `#L42` and `#L42-L51` are GitHub line references, not document anchors — this repo's
    # own CLAUDE.md mandates that form for code citations. Treating them as anchors flags
    # every such link.
    assert _anchor_issues(tmp_path, "no anchors here\n", "../srs/README.md#L153") == []
    assert _anchor_issues(tmp_path, "no anchors here\n", "../srs/README.md#L42-L51") == []


def test_slugify_keeps_underscores():
    # github-slugger's strip class holds neither `-` nor `_`, so `## flow_gate_check` anchors
    # as `flow_gate_check`. Dropping `_` reports every snake_case heading link as dead.
    assert hs._slugify("flow_gate_check") == "flow_gate_check"


def test_slugify_replaces_each_space_separately():
    # Punctuation is removed BEFORE spaces become hyphens, so an em dash leaves the two
    # spaces that surrounded it — GitHub yields a double hyphen. Collapsing runs of
    # whitespace disagrees with GitHub on this repo's dominant heading style.
    assert hs._slugify("Step 1 — Classify the task") == "step-1--classify-the-task"


def test_duplicate_heading_gets_a_counter_suffix(tmp_path):
    # GitHub disambiguates a repeated slug with -1, -2. A set of slugs would call this dead.
    body = "## Overview\n\n## Overview\n"
    assert _anchor_issues(tmp_path, body, "../srs/README.md#overview-1") == []


def test_heading_inside_a_code_fence_is_not_an_anchor(tmp_path):
    body = "```bash\n# Probe the branch point\n```\n"
    hits = _anchor_issues(tmp_path, body, "../srs/README.md#probe-the-branch-point")
    assert len(hits) == 1


def test_setext_heading_resolves(tmp_path):
    body = "Requirements Coverage\n=====\n"
    assert _anchor_issues(tmp_path, body, "../srs/README.md#requirements-coverage") == []


def test_percent_encoded_fragment_resolves(tmp_path):
    # What GitHub puts in a copied anchor URL for a Korean heading.
    link = "../srs/README.md#%EC%9A%94%EA%B5%AC-%EC%B6%94%EC%A0%81"
    assert _anchor_issues(tmp_path, "## 요구 추적\n", link) == []


def test_data_id_is_not_an_explicit_anchor(tmp_path):
    body = '<a href="x" data-id="fr-001"></a>\n'
    hits = _anchor_issues(tmp_path, body, "../srs/README.md#fr-001")
    assert len(hits) == 1


def test_lens_upsert_target_is_read_from_disk(tmp_path):
    # A lens_upsert entry carries `stack`/`lenses` and no `content` at all, and edits a file
    # that already exists. Letting `.get("content", "")` stand in for the file makes every
    # anchor in it report dead.
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "bp.md").write_text("## Security\n", encoding="utf-8")
    plan = {
        "files": [
            _baseline_entry(),
            {"path": "docs/sds.md", "action": "create", "content": "[BP](bp.md#security)"},
            {
                "path": "docs/bp.md",
                "action": "lens_upsert",
                "stack": "go",
                "lenses": [{"lens": "security", "body": "### Security\n- x"}],
            },
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert not [i for i in rep["issues"] if i["kind"] == "dead-anchor"]


def test_marker_upsert_target_is_read_from_disk(tmp_path):
    # Same failure through the other partial action: its `content` is the marker body only.
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "idx.md").write_text("## Rules\n", encoding="utf-8")
    plan = {
        "files": [
            _baseline_entry(),
            {"path": "docs/sds.md", "action": "create", "content": "[R](idx.md#rules)"},
            {
                "path": "docs/idx.md",
                "action": "marker_upsert",
                "marker_id": "harness:baseline",
                "content": "body only\n",
            },
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert not [i for i in rep["issues"] if i["kind"] == "dead-anchor"]


def test_bom_target_resolves_its_first_heading(tmp_path):
    # A BOM stays glued to the leading `#` and U+FEFF is not `\s`, so a utf-8 (non-sig) read
    # makes the first heading unmatchable — a Windows-only false positive.
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "t.md").write_text("## Overview\n", encoding="utf-8-sig")
    plan = {
        "files": [
            _baseline_entry(),
            {"path": "docs/sds.md", "action": "create", "content": "[O](t.md#overview)"},
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert not [i for i in rep["issues"] if i["kind"] == "dead-anchor"]


def test_inline_code_heading_resolves(tmp_path):
    # GitHub slugs the RENDERED heading, so the backticked identifier survives. Stripping the
    # inline span before slugging reports this live link dead — and this is the dominant
    # heading style in this repo and in what it generates. `_slugify` alone is NOT enough of
    # a test: it never sees the body preprocessing, which is where that bug lived.
    body = "## `flow_gate_check` resolution\n"
    link = "../srs/README.md#flow_gate_check-resolution"
    assert _anchor_issues(tmp_path, body, link) == []


def test_html_entity_heading_resolves(tmp_path):
    # `&amp;` renders as `&`, which the strip then drops — leaving the two spaces around it.
    assert _anchor_issues(tmp_path, "## Tips &amp; Tricks\n", "../srs/README.md#tips--tricks") == []


def test_html_tag_in_heading_is_not_slugged(tmp_path):
    assert _anchor_issues(tmp_path, "## <code>x</code> y\n", "../srs/README.md#x-y") == []


def test_target_front_matter_is_not_a_heading(tmp_path):
    # A `#` comment line inside front matter is a comment, not a heading. Counting it both
    # resolves an anchor that does not exist and shifts the duplicate counter after it —
    # `sds.template.md` ships five such lines.
    body = "---\n# sources: the code paths\nwiki_id: x\n---\n\n## Real\n"
    hits = _anchor_issues(tmp_path, body, "../srs/README.md#sources-the-code-paths")
    assert len(hits) == 1


def test_front_matter_does_not_shift_the_duplicate_counter(tmp_path):
    body = "---\n# Overview\nwiki_id: x\n---\n\n## Overview\n\n## Overview\n"
    assert _anchor_issues(tmp_path, body, "../srs/README.md#overview-1") == []


def test_entry_without_an_action_key_is_whole_file_content(tmp_path):
    # `apply_plan` defaults a missing `action` to "create", so its `content` IS the file.
    # Excluding it sends the lookup to a disk file that does not exist yet — unchecked.
    plan = {
        "files": [
            _baseline_entry(),
            {"path": "docs/sds.md", "action": "create", "content": "[R](t.md#gone)"},
            {"path": "docs/t.md", "content": "## Present\n"},
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert len([i for i in rep["issues"] if i["kind"] == "dead-anchor"]) == 1


def test_plan_content_keys_are_normalized(tmp_path):
    plan = {
        "files": [
            _baseline_entry(),
            {"path": "docs/sds.md", "action": "create", "content": "[R](t.md#gone)"},
            {"path": "./docs/t.md", "action": "create", "content": "## Present\n"},
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    # Assert the target is CHECKED, not merely that nothing was reported: an unnormalized key
    # misses the lookup, falls through to a disk file that does not exist, and reports
    # nothing — indistinguishable from a clean pass unless the anchor is genuinely dead.
    assert len([i for i in rep["issues"] if i["kind"] == "dead-anchor"]) == 1


def test_atx_closing_hashes_are_trimmed(tmp_path):
    assert _anchor_issues(tmp_path, "## Overview ##\n", "../srs/README.md#overview") == []


def test_a_heading_followed_by_a_rule_is_not_a_setext(tmp_path):
    # Without the `(?!\s{0,3}#)` guard the `---` turns the ATX line into a second, phantom
    # heading whose slug starts with the hashes.
    hits = _anchor_issues(tmp_path, "## A\n---\n", "../srs/README.md#-a")
    assert len(hits) == 1


def test_existing_disk_target_wins_over_plan_content(tmp_path):
    # `apply_plan`'s `create` does NOT overwrite an existing file — it records a conflict and
    # leaves it. Reading the plan's content as the target's future makes every anchor in a
    # conflicted file report dead, which is the shape a brownfield /harness-init re-run takes.
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "srs.md").write_text("## Requirements Coverage\n", encoding="utf-8")
    plan = {
        "files": [
            _baseline_entry(),
            {
                "path": "docs/sds.md",
                "action": "create",
                "content": "[FR](srs.md#requirements-coverage)",
            },
            {"path": "docs/srs.md", "action": "create", "content": "## Something Else\n"},
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert not [i for i in rep["issues"] if i["kind"] == "dead-anchor"]


def test_create_entry_without_content_key_is_not_authoritative(tmp_path):
    # `.get("content", "")` on an entry with no `content` yields "", and "" answers
    # "no anchors here" for anything asked of it. The target must be ABSENT from disk, or
    # the disk-wins branch answers first and this boundary is never reached.
    plan = {
        "files": [
            _baseline_entry(),
            {"path": "docs/sds.md", "action": "create", "content": "[R](t.md#present)"},
            {"path": "docs/t.md", "action": "create"},
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert not [i for i in rep["issues"] if i["kind"] == "dead-anchor"]


def test_slugify_keeps_a_generic_type_heading():
    # `<K,V>` is not a well-formed tag, so no renderer removes it — GitHub yields `mapkv`.
    # A loose `<[^>]+>` strip yields `map` and reports every generics heading link dead.
    assert hs._slugify("Map<K,V>") == "mapkv"
    assert hs._slugify("Result<T, E>") == "resultt-e"
    assert hs._slugify("2 < 3 and 4 > 5") == "2--3-and-4--5"


def test_slugify_strips_a_real_html_tag():
    assert hs._slugify("<code>x</code> y") == "x-y"


def test_slugify_decodes_an_escaped_tag_without_eating_it():
    # `&lt;script&gt;` renders as the TEXT `<script>`, which the punctuation strip then
    # removes — but the word survives. Decoding before the tag strip loses it entirely.
    assert hs._slugify("&lt;script&gt; handling") == "script-handling"


def test_slugify_leaves_a_semicolonless_entity_alone():
    # CommonMark requires the semicolon; `html.unescape` does not. `## Notes &amp` anchors
    # as `notes-amp` on GitHub.
    assert hs._slugify("Notes &amp") == "notes-amp"
    assert hs._slugify("A &copy B") == "a-copy-b"


def test_explicit_anchor_inside_a_code_fence_is_not_an_anchor(tmp_path):
    body = '```html\n<a id="ghost"></a>\n```\n'
    hits = _anchor_issues(tmp_path, body, "../srs/README.md#ghost")
    assert len(hits) == 1


def test_slugify_drops_an_html_comment():
    # `srs.template.md` ships headings with a trailing `<!-- ... -->`.
    assert hs._slugify("A <!-- x --> B") == "a--b"


def test_percent_encoded_fragment_resolves_an_explicit_anchor(tmp_path):
    link = "../srs/README.md#%EC%9A%94%EA%B5%AC"
    assert _anchor_issues(tmp_path, '<a id="요구"></a>\n', link) == []
