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
    assert names.count("flask") == 1  # dedup by name even across two manifests


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


def test_detect_frameworks_csproj_aspnetcore(tmp_path):
    (tmp_path / "App.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk.Web">\n'
        "  <PropertyGroup>\n"
        "    <TargetFramework>net8.0</TargetFramework>\n"
        "  </PropertyGroup>\n"
        "</Project>\n",
        encoding="utf-8",
    )
    names = [f["name"] for f in hs.detect_frameworks(tmp_path)]
    assert "aspnet-core" in names


def test_detect_frameworks_csproj_wpf_property(tmp_path):
    (tmp_path / "App.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n'
        "  <PropertyGroup>\n"
        "    <UseWPF>true</UseWPF>\n"
        "  </PropertyGroup>\n"
        "</Project>\n",
        encoding="utf-8",
    )
    names = [f["name"] for f in hs.detect_frameworks(tmp_path)]
    assert "wpf" in names


def test_detect_frameworks_csproj_package_reference(tmp_path):
    (tmp_path / "App.csproj").write_text(
        '<Project Sdk="Microsoft.NET.Sdk">\n'
        "  <ItemGroup>\n"
        '    <PackageReference Include="Microsoft.EntityFrameworkCore" Version="8.0.0" />\n'
        "  </ItemGroup>\n"
        "</Project>\n",
        encoding="utf-8",
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("entity-framework-core") == "8.0.0"


def test_detect_frameworks_pom_xml(tmp_path):
    (tmp_path / "pom.xml").write_text(
        "<project>\n"
        "  <dependencies>\n"
        "    <dependency>\n"
        "      <groupId>org.springframework.boot</groupId>\n"
        "      <artifactId>spring-boot-starter-web</artifactId>\n"
        "      <version>3.2.0</version>\n"
        "    </dependency>\n"
        "  </dependencies>\n"
        "</project>\n",
        encoding="utf-8",
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("spring-boot") == "3.2.0"


def test_detect_frameworks_gradle_kts(tmp_path):
    (tmp_path / "build.gradle.kts").write_text(
        "dependencies {\n"
        '    implementation("org.springframework.boot:spring-boot-starter-web:3.2.0")\n'
        "}\n",
        encoding="utf-8",
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("spring-boot") == "3.2.0"


def test_detect_frameworks_gradle_kotlin_ktor(tmp_path):
    (tmp_path / "build.gradle.kts").write_text(
        'implementation("io.ktor:ktor-server-core:2.3.0")\n', encoding="utf-8"
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("ktor") == "2.3.0"


def test_detect_frameworks_cmake(tmp_path):
    (tmp_path / "CMakeLists.txt").write_text(
        "cmake_minimum_required(VERSION 3.20)\nproject(myapp)\n", encoding="utf-8"
    )
    names = [f["name"] for f in hs.detect_frameworks(tmp_path)]
    assert "cmake" in names


def test_detect_frameworks_vcpkg(tmp_path):
    (tmp_path / "vcpkg.json").write_text(
        json.dumps({"name": "myapp", "dependencies": ["boost", "fmt"]}), encoding="utf-8"
    )
    names = [f["name"] for f in hs.detect_frameworks(tmp_path)]
    assert "boost" in names
    assert "fmt" in names


def test_detect_frameworks_conanfile_txt(tmp_path):
    (tmp_path / "conanfile.txt").write_text(
        "[requires]\nfmt/10.1.1\nspdlog/1.12.0\n\n[generators]\nCMakeDeps\n", encoding="utf-8"
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("fmt") == "10.1.1"
    assert found.get("spdlog") == "1.12.0"


def test_detect_frameworks_conanfile_py(tmp_path):
    (tmp_path / "conanfile.py").write_text(
        "from conan import ConanFile\n\n\nclass Pkg(ConanFile):\n"
        '    def requirements(self):\n        self.requires("boost/1.83.0")\n',
        encoding="utf-8",
    )
    names = [f["name"] for f in hs.detect_frameworks(tmp_path)]
    assert "boost" in names


def test_detect_frameworks_cargo_toml(tmp_path):
    (tmp_path / "Cargo.toml").write_text(
        '[package]\nname = "myapp"\nversion = "0.1.0"\n\n'
        '[dependencies]\naxum = "0.7.4"\ntokio = { version = "1", features = ["full"] }\n',
        encoding="utf-8",
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("axum") == "0.7.4"
    assert found.get("tokio") == "1"


def test_detect_frameworks_composer_json(tmp_path):
    (tmp_path / "composer.json").write_text(
        json.dumps({"require": {"laravel/framework": "^10.0"}}), encoding="utf-8"
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("laravel") == "10.0"


def test_detect_frameworks_gemfile(tmp_path):
    (tmp_path / "Gemfile").write_text(
        'source "https://rubygems.org"\ngem "rails", "~> 7.1.0"\n', encoding="utf-8"
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("rails") == "7.1.0"


def test_detect_frameworks_package_swift(tmp_path):
    (tmp_path / "Package.swift").write_text(
        "// swift-tools-version:5.9\n"
        "import PackageDescription\n\n"
        "let package = Package(\n"
        "  dependencies: [\n"
        '    .package(url: "https://github.com/vapor/vapor.git", from: "4.0.0")\n'
        "  ]\n"
        ")\n",
        encoding="utf-8",
    )
    names = [f["name"] for f in hs.detect_frameworks(tmp_path)]
    assert "vapor" in names


def test_detect_frameworks_xcodeproj_marker(tmp_path):
    (tmp_path / "MyApp.xcodeproj").mkdir()
    names = [f["name"] for f in hs.detect_frameworks(tmp_path)]
    assert "xcode" in names


def test_detect_frameworks_build_sbt(tmp_path):
    (tmp_path / "build.sbt").write_text(
        'libraryDependencies += "org.playframework" %% "play" % "3.0.0"\n', encoding="utf-8"
    )
    found = {f["name"]: f["version"] for f in hs.detect_frameworks(tmp_path)}
    assert found.get("play-framework") == "3.0.0"


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
    assert target.read_text(encoding="utf-8") == "ORIGINAL"  # invariant


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
    assert snapshot == after  # same content on re-run


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


def test_cleanup_removes_research_copies_but_preserves_evidence(tmp_path):
    harness = tmp_path / ".claude" / "harness-tier" / ".harness"
    research = harness / "research"
    research.mkdir(parents=True)
    (research / "researcher_nextjs.md").write_text("조사 내용", encoding="utf-8")
    (research / "code-analyzer.md").write_text("스캔 내용", encoding="utf-8")
    # audit evidence that must be preserved
    for name in ("plan.json", "manifest.json", "critic-report.json", "rationale.md"):
        (harness / name).write_text("{}", encoding="utf-8")

    report = hs.cleanup_harness(harness, tmp_path)

    # research copies are removed (since docs do not reference .harness)
    assert not research.exists() or not any(research.iterdir())
    assert any("researcher_nextjs.md" in r for r in report["removed"])
    assert report["link_warnings"] == []
    # evidence metadata is preserved
    for name in ("plan.json", "manifest.json", "critic-report.json", "rationale.md"):
        assert (harness / name).exists()
    assert sorted(report["preserved"]) == sorted(
        ["critic-report.json", "manifest.json", "plan.json", "rationale.md"]
    )


def test_cleanup_is_safe_when_no_research_dir(tmp_path):
    harness = tmp_path / ".claude" / "harness-tier" / ".harness"
    harness.mkdir(parents=True)
    (harness / "plan.json").write_text("{}", encoding="utf-8")
    report = hs.cleanup_harness(harness, tmp_path)
    assert report["removed"] == []
    assert report["preserved"] == ["plan.json"]


def test_cleanup_does_not_touch_non_research_non_preserve(tmp_path):
    # files that are neither on the preserve whitelist nor in research/ are not touched
    # (conservative).
    harness = tmp_path / ".claude" / "harness-tier" / ".harness"
    harness.mkdir(parents=True)
    (harness / "stray.txt").write_text("x", encoding="utf-8")
    hs.cleanup_harness(harness, tmp_path)
    assert (harness / "stray.txt").exists()


def test_cleanup_holds_when_docs_link_into_harness(tmp_path):
    # link guard (FAIL-SAFE): if docs reference .harness/research, hold off on removal.
    harness = tmp_path / ".claude" / "harness-tier" / ".harness"
    research = harness / "research"
    research.mkdir(parents=True)
    (research / "researcher_nextjs.md").write_text("조사", encoding="utf-8")
    arch = tmp_path / "docs" / "sds"
    arch.mkdir(parents=True)
    (arch / "README.md").write_text(
        "출처: [조사](../../.claude/harness-tier/.harness/research/researcher_nextjs.md)",
        encoding="utf-8",
    )
    report = hs.cleanup_harness(harness, tmp_path)
    assert (research / "researcher_nextjs.md").exists()  # preserved due to hold
    assert report["removed"] == []
    assert any("sds/README.md" in w for w in report["link_warnings"])


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
