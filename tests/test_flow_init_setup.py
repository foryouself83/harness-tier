import json
import os
import subprocess
import sys
from pathlib import Path

import yaml as _yaml

from scripts.flow_init_setup import (
    CLAUDE_MD_BEGIN,
    GATE_COMMAND,
    GATE_MARKER,
    GITIGNORE_LINES,
    append_gitignore,
    check_precommit,
    copy_artifacts,
    load_contract_config,
    main,
    missing_config_slots,
    register_gate,
    register_marketplace,
    remove_claude_md_block,
    remove_gitignore_lines,
    remove_harness_dir,
    render_workflow,
    report_missing_config_slots,
    run_setup,
    unregister_gate,
    unregister_marketplace,
)

PLUGIN = Path(__file__).resolve().parent.parent  # repo root == plugin root


def _gate_commands(settings: Path) -> list[str]:
    data = json.loads(settings.read_text(encoding="utf-8"))
    return [h["command"] for e in data["hooks"]["PreToolUse"] for h in e["hooks"]]


def test_register_gate_creates(tmp_path: Path):
    msg = register_gate(tmp_path)
    assert "등록" in msg
    cmds = _gate_commands(tmp_path / ".claude" / "settings.json")
    assert any(GATE_MARKER in c for c in cmds)


def test_register_gate_idempotent(tmp_path: Path):
    register_gate(tmp_path)
    msg = register_gate(tmp_path)
    assert "이미" in msg
    # not registered twice
    cmds = _gate_commands(tmp_path / ".claude" / "settings.json")
    assert sum(GATE_MARKER in c for c in cmds) == 1


def test_register_gate_preserves_existing(tmp_path: Path):
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    other = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo other"}]}
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [other]}}), encoding="utf-8")
    register_gate(tmp_path)
    cmds = _gate_commands(settings)
    assert "echo other" in cmds
    assert any(GATE_MARKER in c for c in cmds)


def test_append_gitignore_creates_and_idempotent(tmp_path: Path):
    first = append_gitignore(tmp_path)
    assert any("+=" in line for line in first)
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    for line in GITIGNORE_LINES:
        assert line in content
    second = append_gitignore(tmp_path)
    assert any("이미 최신" in line for line in second)
    # flow-config.yaml is team-shared, so it is excluded from the ignore list — not added.
    assert "flow-config.yaml" not in content
    assert content.count(".claude/harness-tier/.flow/") == 1


def test_append_gitignore_preserves_existing(tmp_path: Path):
    gi = tmp_path / ".gitignore"
    gi.write_text("node_modules/\n", encoding="utf-8")
    append_gitignore(tmp_path)
    content = gi.read_text(encoding="utf-8")
    assert "node_modules/" in content
    assert ".claude/harness-tier/.flow/" in content


def test_register_gate_refreshes_stale_status_message(tmp_path: Path):
    # when command is current but only statusMessage differs, repair it (not skip)
    from scripts.flow_init_setup import GATE_COMMAND, GATE_STATUS

    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    old = {
        "matcher": "Bash",
        "hooks": [
            {
                "type": "command",
                "command": GATE_COMMAND,
                "statusMessage": "harness-tier: flow 게이트 검사 중…",
            }
        ],
    }
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [old]}}), encoding="utf-8")
    msg = register_gate(tmp_path)
    assert "보정" in msg
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["hooks"]["PreToolUse"][0]["hooks"][0]["statusMessage"] == GATE_STATUS


def test_register_gate_repairs_stale_command(tmp_path: Path):
    # when a plugin update changed command, repair the registered stale command to the current path
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    # path different from current
    old_cmd = 'bash ".../.claude/harness-tier/other-path/precommit-runner.sh"'
    stale = {"matcher": "Bash", "hooks": [{"type": "command", "command": old_cmd}]}
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [stale]}}), encoding="utf-8")
    msg = register_gate(tmp_path)
    assert "보정" in msg
    cmds = _gate_commands(settings)
    # the single entry is repaired to the current path (no duplicate added)
    assert cmds == [GATE_COMMAND]


def test_register_gate_repairs_all_stale_entries(tmp_path: Path):
    # repair all duplicated stale gate entries to the current path
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    # path different from current
    old = 'bash ".../.claude/harness-tier/other-path/precommit-runner.sh"'
    dup = [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": old}]},
        {"matcher": "Bash", "hooks": [{"type": "command", "command": old}]},
    ]
    settings.write_text(json.dumps({"hooks": {"PreToolUse": dup}}), encoding="utf-8")
    msg = register_gate(tmp_path)
    assert "보정" in msg
    cmds = _gate_commands(settings)
    assert cmds == [GATE_COMMAND, GATE_COMMAND]  # both repaired (not just the first)


def test_check_precommit_reports_stale_owned_entry(tmp_path: Path):
    # report drift when the entry of a harness-tier-owned hook (teams-notify-push)
    # differs from the current path
    dest = tmp_path / ".pre-commit-config.yaml"
    dest.write_text(
        "repos:\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: teams-notify-push\n"
        "        name: x\n"
        "        entry: scripts/notify-push.sh\n"  # path different from current
        "        language: script\n",
        encoding="utf-8",
    )
    report = check_precommit(PLUGIN, tmp_path)
    assert any("entry 가 현재 경로와 다릅니다" in line for line in report)


def test_main_setup_then_uninstall_dispatch(tmp_path: Path, monkeypatch):
    # argparse dispatch + run_setup order (copy→register) end-to-end
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN))
    monkeypatch.setattr(sys, "argv", ["flow_init_setup.py"])
    main()
    vd = tmp_path / ".claude" / "harness-tier"
    settings = tmp_path / ".claude" / "settings.json"
    assert (vd / "scripts" / "precommit-runner.sh").is_file()
    assert (vd / "config" / "flow-tiers.yaml").is_file()
    assert any(GATE_MARKER in c for c in _gate_commands(settings))
    # --uninstall dispatch → inverse operation
    monkeypatch.setattr(sys, "argv", ["flow_init_setup.py", "--uninstall"])
    main()
    assert not vd.exists()
    assert not any(GATE_MARKER in c for c in _gate_commands(settings))


def test_copy_artifacts_includes_shared_helper(tmp_path: Path):
    # if _harness_paths.py is missing from COPY_FILES, the gate script copied to the host
    # is silently disabled by a sibling import failure (ImportError). Prevents this
    # omission regression.
    copy_artifacts(PLUGIN, tmp_path)
    scripts_dir = tmp_path / ".claude" / "harness-tier" / "scripts"
    assert (scripts_dir / "_harness_paths.py").is_file()


def test_copied_gate_imports_shared_helper(tmp_path: Path):
    # host single-file copy environment end-to-end: running flow_gate_check.py directly from
    # the copied scripts/ must import the sibling _harness_paths.py and work. If the import-
    # compatibility block breaks, it is caught immediately as an ImportError crash (returncode
    # 1 + stderr Traceback). The gate decision itself is not this test's concern, so to avoid
    # tripping the unclassified fail-closed block (policy present + tier marker absent → exit 2),
    # place a docs tier + evidence so it passes normally (exit 0), verifying only import
    # compatibility.
    copy_artifacts(PLUGIN, tmp_path)
    (tmp_path / ".claude").mkdir(exist_ok=True)
    flow = tmp_path / ".claude" / "harness-tier" / ".flow"
    flow.mkdir(parents=True)
    (flow / "tier").write_text("docs:", encoding="utf-8")
    (flow / "doc-sync.done").touch()
    scripts_dir = tmp_path / ".claude" / "harness-tier" / "scripts"
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path), "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, str(scripts_dir / "flow_gate_check.py")],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, f"import 양립 실패 의심: {result.stderr}"


def test_copied_gate_reads_tiers_from_config(tmp_path: Path):
    # host copy environment end-to-end: the __file__ of the copied scripts/flow_gate_check.py
    # is tmp/.claude/harness-tier/scripts/ → it must resolve the sibling config/'s flow-tiers.yaml.
    # This path breaks on a config/→scripts/ regression (if sibling lookup sees the old scripts/).
    copy_artifacts(PLUGIN, tmp_path)
    scripts_dir = tmp_path / ".claude" / "harness-tier" / "scripts"
    config_tiers = tmp_path / ".claude" / "harness-tier" / "config" / "flow-tiers.yaml"
    assert config_tiers.is_file()  # copy placed it in config/
    code = (
        "from pathlib import Path;"
        "from flow_gate_check import tiers_path;"
        "import sys; sys.stdout.write(str(tiers_path(Path(sys.argv[1]))))"
    )
    env = {**os.environ, "PYTHONPATH": str(scripts_dir), "PYTHONIOENCODING": "utf-8"}
    env.pop("CLAUDE_PLUGIN_ROOT", None)  # ① disable dispatch → ② verify config/ lookup
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(config_tiers)


def test_uninstall_round_trip(tmp_path: Path):
    # uninstall reverts everything setup registered
    register_gate(tmp_path)
    register_marketplace(tmp_path)
    append_gitignore(tmp_path)
    vd = tmp_path / ".claude" / "harness-tier"
    (vd / "scripts").mkdir(parents=True)
    (vd / "scripts" / "precommit-runner.sh").write_text("x", encoding="utf-8")

    assert "해제" in unregister_gate(tmp_path)
    assert "해제" in unregister_marketplace(tmp_path)
    assert "제거" in remove_gitignore_lines(tmp_path)
    assert "삭제" in remove_harness_dir(tmp_path)

    data = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert not any(GATE_MARKER in c for c in _gate_commands(tmp_path / ".claude" / "settings.json"))
    assert "harness-tier" not in (data.get("extraKnownMarketplaces") or {})
    gi = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert all(line not in gi for line in GITIGNORE_LINES)
    assert not vd.exists()


def test_uninstall_idempotent(tmp_path: Path):
    # when nothing exists, uninstall safely skips
    assert "skip" in unregister_gate(tmp_path)
    assert "skip" in unregister_marketplace(tmp_path)
    assert "skip" in remove_gitignore_lines(tmp_path)
    assert "skip" in remove_harness_dir(tmp_path)


def test_uninstall_preserves_other_settings(tmp_path: Path):
    # PreToolUse hooks other than the gate are preserved
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    other = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo other"}]}
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [other]}}), encoding="utf-8")
    register_gate(tmp_path)
    unregister_gate(tmp_path)
    cmds = _gate_commands(settings)
    assert "echo other" in cmds
    assert not any(GATE_MARKER in c for c in cmds)


def test_remove_claude_md_block(tmp_path: Path):
    cm = tmp_path / "CLAUDE.md"
    cm.write_text(
        f"# Host\n\nkeep before\n\n{CLAUDE_MD_BEGIN} (managed) -->\nmanaged body\n"
        "<!-- harness-tier:teams END -->\n\nkeep after\n",
        encoding="utf-8",
    )
    assert "제거" in remove_claude_md_block(tmp_path)
    text = cm.read_text(encoding="utf-8")
    assert "keep before" in text and "keep after" in text
    assert "managed body" not in text and CLAUDE_MD_BEGIN not in text
    assert "skip" in remove_claude_md_block(tmp_path)  # idempotent (already absent)


def test_check_precommit_creates_when_absent(tmp_path: Path):
    report = check_precommit(PLUGIN, tmp_path)
    assert (tmp_path / ".pre-commit-config.yaml").is_file()
    assert any("생성" in line for line in report)


def test_check_precommit_creates_never_reports_module_hooks(tmp_path: Path):
    # module hooks moved to layer 2 → even when modules are declared, module hooks are not
    # reported to pre-commit.
    cfg_dir = tmp_path / ".claude" / "harness-tier" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "flow-config.yaml").write_text(
        "modules:\n  - name: api\n    path: services/api/\n"
        "    checks:\n      lint: 'ruff check services/api'\n",
        encoding="utf-8",
    )
    report = check_precommit(PLUGIN, tmp_path)
    assert (tmp_path / ".pre-commit-config.yaml").is_file()
    assert any("생성" in line for line in report)
    assert not any("모듈 훅" in line for line in report)


def test_check_precommit_all_present(tmp_path: Path):
    check_precommit(PLUGIN, tmp_path)  # create (copy the entire example)
    report = check_precommit(PLUGIN, tmp_path)  # all items present
    assert any("이미 충족" in line for line in report)


def test_check_precommit_reports_missing_without_modifying(tmp_path: Path):
    # never modify an existing config (preserve comments/format), only report missing items
    dest = tmp_path / ".pre-commit-config.yaml"
    original = "# 팀 주석 — 보존되어야 함\nrepos: []\n"
    dest.write_text(original, encoding="utf-8")
    report = check_precommit(PLUGIN, tmp_path)
    assert any("병합하지 않음" in line for line in report)
    assert dest.read_text(encoding="utf-8") == original  # file unchanged


def test_register_marketplace_creates(tmp_path: Path):
    msg = register_marketplace(tmp_path)
    assert "autoUpdate" in msg
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    mkt = data["extraKnownMarketplaces"]["harness-tier"]
    assert mkt["autoUpdate"] is True
    assert mkt["source"]["source"] == "github"
    assert mkt["source"]["repo"] == "foryouself83/harness-tier"


def test_register_marketplace_idempotent(tmp_path: Path):
    register_marketplace(tmp_path)
    msg = register_marketplace(tmp_path)
    assert "이미" in msg


def test_register_marketplace_repairs_flag_preserving_source(tmp_path: Path):
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    payload = {
        "extraKnownMarketplaces": {"harness-tier": {"source": {"source": "git", "url": "keep-me"}}}
    }
    settings.write_text(json.dumps(payload), encoding="utf-8")
    msg = register_marketplace(tmp_path)
    assert "보정" in msg
    mkt = json.loads(settings.read_text(encoding="utf-8"))["extraKnownMarketplaces"]["harness-tier"]
    assert mkt["autoUpdate"] is True
    assert mkt["source"]["url"] == "keep-me"  # source preserved


def test_copy_artifacts(tmp_path: Path):
    copy_artifacts(PLUGIN, tmp_path)
    vd = tmp_path / ".claude" / "harness-tier"
    assert (vd / "scripts" / "precommit-runner.sh").is_file()
    assert (vd / "scripts" / "flow_gate_check.py").is_file()
    # policy files go to config/, not scripts/.
    assert (vd / "config" / "flow-tiers.yaml").is_file()
    assert not (vd / "scripts" / "flow-tiers.yaml").exists()


def _write_flow_config(host: Path, contract: dict) -> None:
    cfg_dir = host / ".claude" / "harness-tier" / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "flow-config.yaml").write_text(
        _yaml.safe_dump({"contract_test": contract}, allow_unicode=True), encoding="utf-8"
    )


def test_render_workflow_creates_and_substitutes(tmp_path: Path):
    _write_flow_config(
        tmp_path,
        {
            "enable": True,
            "branches": ["dev", "stage", "main"],
            "action_ref": "schemathesis/action@v3",
            "schema": "http://localhost:8000/openapi.json",
            "base_url": "http://localhost:8000",
            "server": {
                "compose_file": "docker-compose.yml",
                "health_url": "http://localhost:8000/health",
                "health_timeout": 60,
            },
        },
    )
    out = render_workflow(tmp_path, PLUGIN)
    assert any("생성" in line for line in out)
    dest = tmp_path / ".github" / "workflows" / "api-contract.yml"
    text = dest.read_text(encoding="utf-8")
    # all tokens have been substituted
    assert "__HARNESS_" not in text
    # the render result is valid YAML (parses without exception). Note: PyYAML parses the
    # GitHub Actions 'on:' key as a boolean True key (a YAML 1.1 pitfall), so data["on"]
    # access raises KeyError. The intent (branch/action/schema substitution) is verified
    # directly against the text.
    _yaml.safe_load(text)
    assert "branches: [dev, stage, main]" in text
    assert "schemathesis/action@v3" in text
    assert "http://localhost:8000/openapi.json" in text


def test_render_workflow_disabled(tmp_path: Path):
    _write_flow_config(tmp_path, {"enable": False, "branches": ["dev"]})
    out = render_workflow(tmp_path, PLUGIN)
    assert any("enable=false" in line for line in out)
    assert load_contract_config(tmp_path) == {"enable": False, "branches": ["dev"]}
    assert not (tmp_path / ".github" / "workflows" / "api-contract.yml").exists()


def test_render_workflow_absent_section(tmp_path: Path):
    # if flow-config itself is absent, it is unconfigured — skip
    out = render_workflow(tmp_path, PLUGIN)
    assert any("미설정" in line for line in out)
    assert load_contract_config(tmp_path) is None
    assert not (tmp_path / ".github" / "workflows" / "api-contract.yml").exists()


def test_run_setup_renders_workflow(tmp_path: Path, capsys):
    from scripts.flow_init_setup import run_setup

    _write_flow_config(
        tmp_path,
        {
            "enable": True,
            "branches": ["dev", "stage", "main"],
            "action_ref": "schemathesis/action@v3",
            "schema": "http://localhost:8000/openapi.json",
            "base_url": "http://localhost:8000",
            "server": {
                "compose_file": "docker-compose.yml",
                "health_url": "http://localhost:8000/health",
                "health_timeout": 60,
            },
        },
    )
    run_setup(tmp_path, PLUGIN)
    captured = capsys.readouterr().out
    assert "계약 테스트" in captured
    assert (tmp_path / ".github" / "workflows" / "api-contract.yml").is_file()


def test_render_workflow_idempotent_reports_only(tmp_path: Path):
    contract = {
        "enable": True,
        "branches": ["dev", "stage", "main"],
        "action_ref": "schemathesis/action@v3",
        "schema": "http://localhost:8000/openapi.json",
        "base_url": "http://localhost:8000",
        "server": {
            "compose_file": "docker-compose.yml",
            "health_url": "http://localhost:8000/health",
            "health_timeout": 60,
        },
    }
    _write_flow_config(tmp_path, contract)
    render_workflow(tmp_path, PLUGIN)  # first render (create)
    dest = tmp_path / ".github" / "workflows" / "api-contract.yml"
    sentinel = dest.read_text(encoding="utf-8") + "\n# user edit\n"
    dest.write_text(sentinel, encoding="utf-8")  # simulate a user edit
    out = render_workflow(tmp_path, PLUGIN)  # second render — report only
    assert any("이미 있어" in line for line in out)
    assert dest.read_text(encoding="utf-8") == sentinel  # not overwritten


def _mk_example(plugin: Path, body: str) -> None:
    """Write flow-config.example.yaml into the tmp plugin (arbitrary body)."""
    (plugin / "flow-config.example.yaml").write_text(body, encoding="utf-8")


def _mk_host_config(host: Path, text: str) -> None:
    """Write flow-config.yaml at the tmp host's config_path location."""
    from scripts.flow_init_setup import config_path

    cfg = config_path(host)
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(text, encoding="utf-8")


def test_missing_config_slots_top_level_section(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "branches:\n  integration: dev\ncontract_test:\n  enable: true\n")
    _mk_host_config(host, "branches:\n  integration: dev\n")
    assert missing_config_slots(host, plugin) == [
        {"path": ["contract_test"], "parent": [], "label": "contract_test"}
    ]


def test_missing_config_slots_nested_key(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "test:\n  command: x\n  coverage_threshold: 80\n")
    _mk_host_config(host, "test:\n  command: x\n")
    assert missing_config_slots(host, plugin) == [
        {
            "path": ["test", "coverage_threshold"],
            "parent": ["test"],
            "label": "test.coverage_threshold",
        }
    ]


def test_missing_config_slots_empty_value_preserved(tmp_path: Path):
    # even if the host has the key with an empty value (empty string/null), it is not
    # treated as missing.
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "doc_sync:\n  service_docs: services/*/CLAUDE.md\n")
    _mk_host_config(host, 'doc_sync:\n  service_docs: ""\n')
    assert missing_config_slots(host, plugin) == []


def test_missing_config_slots_all_present(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "test:\n  command: x\n")
    _mk_host_config(host, "test:\n  command: x\n  extra: y\n")
    assert missing_config_slots(host, plugin) == []


def test_missing_config_slots_nested_child(tmp_path: Path):
    # nested absorption: if the parent section exists and only the child is missing, the
    # slot is parent=["parent"].
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(
        plugin,
        "parent:\n  childA:\n    enable: true\n  childB:\n    enable: false\n",
    )
    _mk_host_config(host, "parent:\n  childA:\n    enable: true\n")
    assert missing_config_slots(host, plugin) == [
        {"path": ["parent", "childB"], "parent": ["parent"], "label": "parent.childB"}
    ]


def test_missing_config_slots_section_absent_inserts_whole(tmp_path: Path):
    # if the host lacks the section entirely, the whole section is the insertion unit.
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "parent:\n  childA:\n    enable: true\n")
    _mk_host_config(host, "branches:\n  integration: dev\n")
    assert missing_config_slots(host, plugin) == [
        {"path": ["parent"], "parent": [], "label": "parent"}
    ]


def test_missing_config_slots_order_preserved(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "a: 1\nb: 2\nc: 3\n")
    _mk_host_config(host, "b: 2\n")
    assert [s["label"] for s in missing_config_slots(host, plugin)] == ["a", "c"]


def test_missing_config_slots_host_absent(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "branches:\n  integration: dev\nparent:\n  childA:\n    enable: true\n")
    # no host config file → all top-level example keys
    assert [s["label"] for s in missing_config_slots(host, plugin)] == ["branches", "parent"]


def test_missing_config_slots_host_parse_fail(tmp_path: Path):
    # broken host YAML → _load_yaml_safe returns {} → all top-level example keys
    # (equivalent to absent).
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "branches:\n  integration: dev\ntest:\n  command: x\n")
    _mk_host_config(host, "branches:\n  integration: [unclosed\n")
    assert [s["label"] for s in missing_config_slots(host, plugin)] == ["branches", "test"]


def test_missing_config_slots_example_absent(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_host_config(host, "branches:\n  integration: dev\n")
    assert missing_config_slots(host, plugin) == []


def test_report_missing_config_slots_lists_new(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "test:\n  command: x\ncontract_test:\n  enable: true\n")
    _mk_host_config(host, "test:\n  command: x\n")
    out = report_missing_config_slots(host, plugin)
    assert any("contract_test" in line for line in out)
    assert any("/flow-init" in line for line in out)


def test_report_missing_config_slots_skip_when_current(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "test:\n  command: x\n")
    _mk_host_config(host, "test:\n  command: x\n")
    assert report_missing_config_slots(host, plugin) == ["  [=] config 슬롯 최신 (skip)"]


def test_run_setup_reports_config_slots(tmp_path: Path, capsys):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "test:\n  command: x\ncontract_test:\n  enable: true\n")
    _mk_host_config(host, "test:\n  command: x\n")
    run_setup(host, plugin)
    captured = capsys.readouterr().out
    assert "[config 슬롯 점검]" in captured


def test_render_versioning_python(tmp_path):
    from scripts import flow_init_setup as m

    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    # place the SOURCE template
    (plugin / "github").mkdir(parents=True)
    (plugin / "github" / "release.python-semantic-release.workflow.example.yml").write_text(
        "on:\n  push:\n    branches: [__HARNESS_STABLE__, __HARNESS_PRERELEASE__]\n",
        encoding="utf-8",
    )
    (plugin / "github" / "branch-naming.workflow.example.yml").write_text(
        "name: branch-naming\n", encoding="utf-8"
    )
    ent_tmpl = (
        'on:\n  schedule:\n    - cron: "__HARNESS_ENTROPY_SCHEDULE__"\n'
        "paths: __HARNESS_ENTROPY_PATHS__\n"
    )
    (plugin / "github" / "entropy-check.workflow.example.yml").write_text(
        ent_tmpl, encoding="utf-8"
    )
    (host / ".claude" / "harness-tier" / "config").mkdir(parents=True)
    (host / ".claude" / "harness-tier" / "config" / "flow-config.yaml").write_text(
        "versioning:\n  enable: true\n  release_tool: python-semantic-release\n"
        "  branches: {stable: main, prerelease: stage}\n"
        "  branch_naming: {enable: true}\n"
        '  entropy: {enable: true, schedule: "0 0 * * 5", paths: ["src/"]}\n',
        encoding="utf-8",
    )
    m.render_versioning_workflows(host, plugin)
    rel = (host / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "[main, stage]" in rel and "__HARNESS_" not in rel
    assert (host / ".github" / "workflows" / "branch-naming.yml").exists()
    ent = (host / ".github" / "workflows" / "entropy-check.yml").read_text(encoding="utf-8")
    assert "0 0 * * 5" in ent and "src/" in ent


def test_render_versioning_disabled(tmp_path):
    from scripts import flow_init_setup as m

    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    (host / ".claude" / "harness-tier" / "config").mkdir(parents=True)
    (host / ".claude" / "harness-tier" / "config" / "flow-config.yaml").write_text(
        "versioning:\n  enable: false\n", encoding="utf-8"
    )
    m.render_versioning_workflows(host, plugin)
    assert not (host / ".github" / "workflows" / "release.yml").exists()
