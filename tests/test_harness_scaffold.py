import json
from pathlib import Path

import pytest

import scripts.harness_scaffold as hs


def test_detect_state_greenfield(tmp_path):
    (tmp_path / "README.md").write_text("# hi", encoding="utf-8")
    (tmp_path / "package.json").write_text("{}", encoding="utf-8")
    assert hs.detect_state(tmp_path) == "greenfield"


def test_detect_state_brownfield_when_source_present(tmp_path):
    (tmp_path / "app.py").write_text("print(1)\n", encoding="utf-8")
    assert hs.detect_state(tmp_path) == "brownfield"


def test_detect_state_ignores_vendored_dirs(tmp_path):
    nm = tmp_path / "node_modules" / "x"
    nm.mkdir(parents=True)
    (nm / "index.js").write_text("//x", encoding="utf-8")
    (tmp_path / "README.md").write_text("# hi", encoding="utf-8")
    assert hs.detect_state(tmp_path) == "greenfield"


def test_detect_frameworks_package_json(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps({"dependencies": {"next": "15.0.1", "react": "19.0.0"}}),
        encoding="utf-8",
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("next.js") == "15.0.1"


def test_detect_frameworks_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["fastapi==0.118.0", "uvicorn"]\n', encoding="utf-8"
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("fastapi") == "0.118.0"


def test_detect_frameworks_pyproject_poetry(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[tool.poetry.dependencies]\nfastapi = "^0.118.0"\ndjango = "^5.0"\n',
        encoding="utf-8",
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("fastapi") == "0.118.0"
    assert found.get("django") == "5.0"


def test_detect_frameworks_requirements_txt(tmp_path):
    (tmp_path / "requirements.txt").write_text(
        "# comment\nflask==3.0.0\nrequests>=2.0\n", encoding="utf-8"
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("flask") == "3.0.0"


def test_detect_frameworks_requirements_dedup_with_pyproject(tmp_path):
    (tmp_path / "pyproject.toml").write_text(
        '[project]\ndependencies = ["flask==3.0.0"]\n', encoding="utf-8"
    )
    (tmp_path / "requirements.txt").write_text("flask==3.0.0\n", encoding="utf-8")
    names = [f["name"] for f in hs.detect_frameworks(tmp_path)]
    assert names.count("flask") == 1  # 매니페스트 둘에 걸쳐도 name 기준 dedup


def test_detect_frameworks_dedup_same_label(tmp_path):
    (tmp_path / "package.json").write_text(
        json.dumps(
            {"dependencies": {"nestjs": "10.0.0", "@nestjs/core": "10.0.0", "next": "15.0.1"}}
        ),
        encoding="utf-8",
    )
    names = [f["name"] for f in hs.detect_frameworks(tmp_path)]
    assert names.count("nestjs") == 1
    assert len(names) == len(set(names))


def _write_component(path: Path, name: str, desc: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\nname: {name}\ndescription: {desc}\n---\n\nbody\n", encoding="utf-8")


def test_scan_components_reads_name_and_description(tmp_path):
    cdir = tmp_path / ".claude"
    _write_component(cdir / "commands" / "deploy.md", "deploy", "Deploy the app")
    _write_component(cdir / "agents" / "reviewer.md", "reviewer", "Reviews code")
    _write_component(cdir / "skills" / "lint" / "SKILL.md", "lint", "Lint sources")
    result = hs.scan_components(cdir)
    expected = {
        "name": "deploy",
        "description": "Deploy the app",
        "path": str(cdir / "commands" / "deploy.md"),
    }
    assert expected in result["commands"]
    assert result["agents"][0]["name"] == "reviewer"
    assert result["skills"][0]["description"] == "Lint sources"


def test_scan_components_missing_dirs_returns_empty(tmp_path):
    result = hs.scan_components(tmp_path / ".claude")
    assert result == {"skills": [], "commands": [], "agents": []}


def test_marker_created_when_file_absent(tmp_path):
    p = tmp_path / "CLAUDE.md"
    assert hs.upsert_marker_block(p, "harness:baseline", "RULE A") == "created"
    text = p.read_text(encoding="utf-8")
    assert "harness:baseline BEGIN" in text and "RULE A" in text and "harness:baseline END" in text


def test_marker_inserted_when_no_marker(tmp_path):
    p = tmp_path / "CLAUDE.md"
    p.write_text("# Existing\n\nuser content\n", encoding="utf-8")
    assert hs.upsert_marker_block(p, "harness:baseline", "RULE A") == "inserted"
    text = p.read_text(encoding="utf-8")
    assert "user content" in text and "RULE A" in text


def test_marker_replaced_in_place_preserves_outside(tmp_path):
    p = tmp_path / "CLAUDE.md"
    hs.upsert_marker_block(p, "harness:baseline", "OLD")
    p.write_text("PRE\n" + p.read_text(encoding="utf-8") + "POST\n", encoding="utf-8")
    assert hs.upsert_marker_block(p, "harness:baseline", "NEW") == "replaced"
    text = p.read_text(encoding="utf-8")
    assert "NEW" in text and "OLD" not in text
    assert text.startswith("PRE") and text.rstrip().endswith("POST")


def test_marker_idempotent_same_content(tmp_path):
    p = tmp_path / "CLAUDE.md"
    hs.upsert_marker_block(p, "harness:baseline", "RULE A")
    before = p.read_text(encoding="utf-8")
    hs.upsert_marker_block(p, "harness:baseline", "RULE A")
    assert p.read_text(encoding="utf-8") == before


def test_marker_begin_without_end_raises(tmp_path):
    p = tmp_path / "CLAUDE.md"
    p.write_text(
        "PRE\n<!-- harness:baseline BEGIN (managed by /harness-init "
        "— edits inside are overwritten) -->\nOLD body without end\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        hs.upsert_marker_block(p, "harness:baseline", "NEW")


def test_apply_creates_when_absent(tmp_path):
    plan = {
        "files": [{"path": ".claude/rules/baseline.md", "action": "create", "content": "RULES"}]
    }
    report = hs.apply_plan(tmp_path, plan)
    assert report["created"] == [".claude/rules/baseline.md"]
    assert (tmp_path / ".claude/rules/baseline.md").read_text(encoding="utf-8") == "RULES"


def test_apply_never_overwrites_existing_create(tmp_path):
    target = tmp_path / "CLAUDE.md"
    target.write_text("ORIGINAL", encoding="utf-8")
    plan = {"files": [{"path": "CLAUDE.md", "action": "create", "content": "NEW"}]}
    report = hs.apply_plan(tmp_path, plan)
    assert report["conflicts"] == ["CLAUDE.md"]
    assert report["created"] == []
    assert target.read_text(encoding="utf-8") == "ORIGINAL"  # 불변식


def test_apply_marker_upsert_updates(tmp_path):
    plan = {
        "files": [
            {
                "path": "CLAUDE.md",
                "action": "marker_upsert",
                "marker_id": "harness:baseline",
                "content": "B",
            }
        ]
    }
    report = hs.apply_plan(tmp_path, plan)
    assert report["updated"] == ["CLAUDE.md"]
    assert "harness:baseline BEGIN" in (tmp_path / "CLAUDE.md").read_text(encoding="utf-8")


def test_apply_idempotent_rerun(tmp_path):
    plan = {
        "files": [
            {"path": ".claude/rules/baseline.md", "action": "create", "content": "RULES"},
            {
                "path": "CLAUDE.md",
                "action": "marker_upsert",
                "marker_id": "harness:baseline",
                "content": "B",
            },
        ]
    }
    hs.apply_plan(tmp_path, plan)
    snapshot = {p: p.read_text(encoding="utf-8") for p in tmp_path.rglob("*") if p.is_file()}
    report2 = hs.apply_plan(tmp_path, plan)
    assert report2["created"] == [] and report2["conflicts"] == [".claude/rules/baseline.md"]
    after = {p: p.read_text(encoding="utf-8") for p in tmp_path.rglob("*") if p.is_file()}
    assert snapshot == after  # 재실행해도 내용 동일


def test_main_detect_outputs_json(tmp_path, capsys):
    (tmp_path / "app.py").write_text("x=1\n", encoding="utf-8")
    rc = hs.main(["detect", "--root", str(tmp_path)])
    assert rc == 0
    out = json.loads(capsys.readouterr().out)
    assert out["state"] == "brownfield"
    assert "frameworks" in out and "existing" in out


def test_main_apply_reads_plan_file(tmp_path, capsys):
    plan_file = tmp_path / "plan.json"
    plan_file.write_text(
        json.dumps({"files": [{"path": "a.md", "action": "create", "content": "X"}]}),
        encoding="utf-8",
    )
    rc = hs.main(["apply", "--root", str(tmp_path), "--plan", str(plan_file)])
    assert rc == 0
    report = json.loads(capsys.readouterr().out)
    assert report["created"] == ["a.md"]


def _baseline_entry(extra_body=""):
    anchors = "".join(
        f"<!-- rule:{k} -->\n"
        for k in ("karpathy", "dry-constants", "version-pinning", "security", "reuse-first")
    )
    return {
        "path": "CLAUDE.md",
        "action": "marker_upsert",
        "marker_id": "harness:baseline",
        "content": anchors + extra_body,
    }


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
    assert rc == 0  # FAIL-OPEN: 진단이지 게이트 아님
    out = json.loads(capsys.readouterr().out)
    assert "ok" in out and "issues" in out


def test_validate_name_non_string_no_crash(tmp_path):
    # name 이 YAML 리스트/딕트여도 add() TypeError 로 죽지 않고 frontmatter 누락 처리(FAIL-OPEN).
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
    rep = hs.validate_plan(tmp_path, plan)  # 예외 없이 반환되어야 함
    assert any(i["kind"] == "frontmatter" for i in rep["issues"])


def test_validate_nested_component_path_checked(tmp_path):
    # 하위 디렉터리 컴포넌트도 frontmatter 검증 대상이어야 한다.
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
    # plan path 가 비정규('./')여도 정규화 후 매칭되어 dead-link 오탐이 없어야 한다.
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
    # './' 접두가 붙은 커맨드 경로도 정규화 후 가드에 걸려야 한다.
    plan = {
        "files": [
            _baseline_entry(),
            {"path": "./.claude/commands/x.md", "action": "create", "content": "y"},
        ]
    }
    rep = hs.validate_plan(tmp_path, plan)
    assert any(i["kind"] == "command" for i in rep["issues"]) and rep["ok"] is False


def test_validate_flags_marker_lines_in_content(tmp_path):
    # 템플릿 BEGIN/END 를 통째로 복사한 content 는 apply 재래핑으로 중첩되므로 high.
    e = _baseline_entry()
    begin, end = hs._marker_begin("harness:baseline"), hs._marker_end("harness:baseline")
    e["content"] = begin + "\n" + e["content"] + "\n" + end
    rep = hs.validate_plan(tmp_path, {"files": [e]})
    assert any(i["kind"] == "marker" and "body" in i["detail"] for i in rep["issues"])
    assert rep["ok"] is False


def test_validate_dedup_allows_same_path_update(tmp_path):
    # 기존 컴포넌트를 같은 경로로 재emit(갱신)하는 것은 충돌이 아니다.
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
    # HTML 주석 공백 변형(<!--rule:x-->)도 앵커로 인정해야 한다.
    e = _baseline_entry()
    e["content"] = e["content"].replace("<!-- rule:karpathy -->", "<!--rule:karpathy-->")
    rep = hs.validate_plan(tmp_path, {"files": [e]})
    assert not any(i["kind"] == "rule-load" for i in rep["issues"])


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
    assert len(blocks[0]) == 4  # `- 에러` + 3 continuation
    assert len(blocks[1]) == 1


def test_validate_dead_link_ignores_image(tmp_path):
    # 이미지 임베드 ![..](..) 는 dead-link 검사 대상이 아니다.
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
    # frontmatter(description) 안의 링크는 본문 스캔 대상이 아니다.
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
    # cp949 호스트의 기존 파일이 utf-8 디코드 불가여도 마커(ASCII) corrupt 는 검출해야 한다.
    cm = tmp_path / "CLAUDE.md"
    begin = hs._marker_begin("harness:baseline").encode("utf-8")
    bad = "필수 룰\n".encode("cp949")  # utf-8 로는 디코드 불가한 바이트
    cm.write_bytes(begin + b"\n" + bad)  # BEGIN 만 있고 END 없음 → corrupt
    rep = hs.validate_plan(tmp_path, {"files": [_baseline_entry()]})
    assert any(i["kind"] == "marker" and "corrupt" in i["detail"] for i in rep["issues"])


def test_validate_dead_link_ignores_inline_code(tmp_path):
    # 인라인 코드 안의 링크 예시는 dead-link 가 아니다.
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
    # 코드 펜스 블록 안의 링크는 dead-link 가 아니다.
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
    # yaml 부재 폴백에서도 블록 스칼라(>) 멀티라인 description 을 보존한다.
    monkeypatch.setattr(hs, "yaml", None)
    text = "---\nname: a\ndescription: >\n  line one\n  line two\n---\nbody"
    fm = hs._parse_frontmatter(text)
    assert fm["name"] == "a"
    assert fm["description"] == "line one line two"


def test_cleanup_removes_research_copies_but_preserves_evidence(tmp_path):
    harness = tmp_path / ".claude" / "vway-kit" / ".harness"
    research = harness / "research"
    research.mkdir(parents=True)
    (research / "researcher_nextjs.md").write_text("조사 내용", encoding="utf-8")
    (research / "code-analyzer.md").write_text("스캔 내용", encoding="utf-8")
    # 보존돼야 하는 감사용 증거
    for name in ("plan.json", "manifest.json", "critic-report.json", "rationale.md"):
        (harness / name).write_text("{}", encoding="utf-8")

    report = hs.cleanup_harness(harness, tmp_path)

    # research 사본은 제거(docs가 .harness를 참조하지 않으므로)
    assert not research.exists() or not any(research.iterdir())
    assert any("researcher_nextjs.md" in r for r in report["removed"])
    assert report["link_warnings"] == []
    # 증거 메타는 보존
    for name in ("plan.json", "manifest.json", "critic-report.json", "rationale.md"):
        assert (harness / name).exists()
    assert sorted(report["preserved"]) == sorted(
        ["critic-report.json", "manifest.json", "plan.json", "rationale.md"]
    )


def test_cleanup_is_safe_when_no_research_dir(tmp_path):
    harness = tmp_path / ".claude" / "vway-kit" / ".harness"
    harness.mkdir(parents=True)
    (harness / "plan.json").write_text("{}", encoding="utf-8")
    report = hs.cleanup_harness(harness, tmp_path)
    assert report["removed"] == []
    assert report["preserved"] == ["plan.json"]


def test_cleanup_does_not_touch_non_research_non_preserve(tmp_path):
    # 보존 화이트리스트도 아니고 research/ 도 아닌 파일은 건드리지 않는다(보수적).
    harness = tmp_path / ".claude" / "vway-kit" / ".harness"
    harness.mkdir(parents=True)
    (harness / "stray.txt").write_text("x", encoding="utf-8")
    hs.cleanup_harness(harness, tmp_path)
    assert (harness / "stray.txt").exists()


def test_cleanup_holds_when_docs_link_into_harness(tmp_path):
    # 링크 가드(FAIL-SAFE): docs가 .harness/research 를 참조하면 제거를 보류한다.
    harness = tmp_path / ".claude" / "vway-kit" / ".harness"
    research = harness / "research"
    research.mkdir(parents=True)
    (research / "researcher_nextjs.md").write_text("조사", encoding="utf-8")
    arch = tmp_path / "docs" / "sds"
    arch.mkdir(parents=True)
    (arch / "README.md").write_text(
        "출처: [조사](../../.claude/vway-kit/.harness/research/researcher_nextjs.md)",
        encoding="utf-8",
    )
    report = hs.cleanup_harness(harness, tmp_path)
    assert (research / "researcher_nextjs.md").exists()  # 보류로 보존
    assert report["removed"] == []
    assert any("sds/README.md" in w for w in report["link_warnings"])
