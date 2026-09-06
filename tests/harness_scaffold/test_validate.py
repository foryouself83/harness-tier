import json

import scripts.harness_scaffold as hs
from tests.harness_scaffold._helpers import _baseline_entry, _write_component


def test_validate_ok_minimal(tmp_path):
    plan = {"files": [_baseline_entry()]}
    rep = hs.validate_plan(tmp_path, plan)
    assert rep["ok"] is True and rep["issues"] == []


def test_validate_missing_rule_anchor(tmp_path):
    e = _baseline_entry()
    e["content"] = e["content"].replace("<!-- rule:reuse-first -->\n", "")
    rep = hs.validate_plan(tmp_path, {"files": [e]})
    assert rep["ok"] is False
    assert any(i["kind"] == "rule-load" and "reuse-first" in i["detail"] for i in rep["issues"])


def test_validate_flags_command_generation(tmp_path):
    plan = {
        "files": [
            _baseline_entry(),
            {"path": ".claude/commands/x.md", "action": "create", "content": "y"},
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert any(i["kind"] == "command" for i in rep["issues"]) and rep["ok"] is False


def test_validate_frontmatter_missing(tmp_path):
    plan = {
        "files": [
            _baseline_entry(),
            {
                "path": ".claude/agents/a.md",
                "action": "create",
                "content": "---\nname: \n---\nbody",
            },
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert any(i["kind"] == "frontmatter" for i in rep["issues"])


def test_validate_dedup_collision_with_existing(tmp_path):
    _write_component(tmp_path / ".claude" / "agents" / "dup.md", "dup", "Existing")
    plan = {
        "files": [
            _baseline_entry(),
            {
                "path": ".claude/agents/new.md",
                "action": "create",
                "content": "---\nname: dup\ndescription: New\n---\nbody",
            },
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert any(i["kind"] == "dedup" for i in rep["issues"])


def test_validate_dead_link(tmp_path):
    plan = {
        "files": [
            _baseline_entry(),
            {
                "path": ".claude/agents/a.md",
                "action": "create",
                "content": "---\nname: a\ndescription: d\n---\nsee [x](./missing.md)",
            },
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert any(i["kind"] == "dead-link" for i in rep["issues"])


def test_validate_dead_link_satisfied_by_plan(tmp_path):
    plan = {
        "files": [
            _baseline_entry(),
            {
                "path": ".claude/agents/a.md",
                "action": "create",
                "content": "---\nname: a\ndescription: d\n---\nsee [b](./b.md)",
            },
            {
                "path": ".claude/agents/b.md",
                "action": "create",
                "content": "---\nname: b\ndescription: d\n---\nx",
            },
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert not any(i["kind"] == "dead-link" for i in rep["issues"])


def test_validate_no_baseline_marker(tmp_path):
    rep = hs.validate_plan(tmp_path, {"files": []})
    assert any(i["kind"] == "rule-load" for i in rep["issues"])


def test_main_validate_outputs_json_exit0(tmp_path, capsys):
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(json.dumps({"files": [_baseline_entry()]}), encoding="utf-8")
    rc = hs.main(["validate", "--root", str(tmp_path), "--plan", str(plan_file)])
    assert rc == 0  # FAIL-OPEN: a diagnostic, not a gate
    out = json.loads(capsys.readouterr().out)
    assert "ok" in out and "issues" in out


def test_validate_name_non_string_no_crash(tmp_path):
    # even if name is a YAML list/dict, do not die with an add() TypeError; treat it as
    # missing frontmatter (FAIL-OPEN).
    plan = {
        "files": [
            _baseline_entry(),
            {
                "path": ".claude/agents/a.md",
                "action": "create",
                "content": "---\nname: [a, b]\ndescription: d\n---\nbody",
            },
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)  # must return without exception
    assert any(i["kind"] == "frontmatter" for i in rep["issues"])


def test_validate_nested_component_path_checked(tmp_path):
    # subdirectory components must also be subject to frontmatter validation.
    plan = {
        "files": [
            _baseline_entry(),
            {
                "path": ".claude/agents/sub/a.md",
                "action": "create",
                "content": "no frontmatter here",
            },
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert any(i["kind"] == "frontmatter" for i in rep["issues"])


def test_validate_dead_link_satisfied_by_noncanonical_plan_path(tmp_path):
    # even if the plan path is non-canonical ('./'), it must match after normalization so
    # there is no dead-link false positive.
    plan = {
        "files": [
            _baseline_entry(),
            {
                "path": ".claude/agents/a.md",
                "action": "create",
                "content": "---\nname: a\ndescription: d\n---\nsee [b](./b.md)",
            },
            {
                "path": ".claude/agents/./b.md",
                "action": "create",
                "content": "---\nname: b\ndescription: d\n---\nx",
            },
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert not any(i["kind"] == "dead-link" for i in rep["issues"])


def test_validate_flags_command_with_dot_prefix(tmp_path):
    # a command path prefixed with './' must also be caught by the guard after normalization.
    plan = {
        "files": [
            _baseline_entry(),
            {"path": "./.claude/commands/x.md", "action": "create", "content": "y"},
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert any(i["kind"] == "command" for i in rep["issues"]) and rep["ok"] is False


def test_validate_flags_marker_lines_in_content(tmp_path):
    # content that copies the template BEGIN/END wholesale gets nested by apply re-wrapping,
    # so it is high.
    e = _baseline_entry()
    begin, end = hs._marker_begin("harness:baseline"), hs._marker_end("harness:baseline")
    e["content"] = begin + "\n" + e["content"] + "\n" + end
    rep = hs.validate_plan(tmp_path, {"files": [e]})
    assert any(i["kind"] == "marker" and "body" in i["detail"] for i in rep["issues"])
    assert rep["ok"] is False


def test_validate_dedup_allows_same_path_update(tmp_path):
    # re-emitting (updating) an existing component at the same path is not a conflict.
    _write_component(tmp_path / ".claude" / "agents" / "reviewer.md", "reviewer", "Old")
    plan = {
        "files": [
            _baseline_entry(),
            {
                "path": ".claude/agents/reviewer.md",
                "action": "create",
                "content": "---\nname: reviewer\ndescription: New\n---\nbody",
            },
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert not any(i["kind"] == "dedup" for i in rep["issues"])


def test_validate_anchor_whitespace_tolerant(tmp_path):
    # HTML-comment whitespace variants (<!--rule:x-->) must also be recognized as anchors.
    e = _baseline_entry()
    e["content"] = e["content"].replace("<!-- rule:karpathy -->", "<!--rule:karpathy-->")
    rep = hs.validate_plan(tmp_path, {"files": [e]})
    assert not any(i["kind"] == "rule-load" for i in rep["issues"])
