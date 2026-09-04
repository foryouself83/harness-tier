import json
import os
import re
import shutil
import struct
import subprocess
import sys
from pathlib import Path

import pytest
import yaml as _yaml

from scripts.flow_init_setup import (
    CLAUDE_MD_BEGIN,
    GATE_COMMAND,
    GITIGNORE_LINES,
    _is_gate_hook,
    append_gitignore,
    check_precommit,
    copy_artifacts,
    load_contract_config,
    load_unit_test_config,
    main,
    missing_config_slots,
    register_gate,
    register_marketplace,
    remove_claude_md_block,
    remove_gitignore_lines,
    remove_harness_dir,
    render_unit_test_workflow,
    render_wiki_verify_workflow,
    render_workflow,
    report_missing_config_slots,
    run_setup,
    run_uninstall,
    unregister_gate,
    unregister_marketplace,
)

PLUGIN = Path(__file__).resolve().parent.parent  # repo root == plugin root
ACCESS_ENTRIES = "system.posix_acl_access"
# Same resolution as tests/test_check_merge_ruleset.py: a bare "bash" hits the System32
# WSL stub first on Windows, which mangles backslash paths.
BASH = shutil.which("bash") or "bash"


def _is_gate(command: str) -> bool:
    """Ask the installer's own predicate. A test that spells the marker itself stops asking
    the code what it counts as the gate, which is the half that decides whose hook it takes."""
    return _is_gate_hook({"type": "command", "command": command})


def _gate_is_in(settings: Path) -> bool:
    """Whether the gate reached this host's file, read in a way every malformed shape
    survives — the shapes this is asked about are exactly the ones with no healthy layout."""
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    hooks = data.get("hooks") if isinstance(data, dict) else None
    entries = hooks.get("PreToolUse") if isinstance(hooks, dict) else None
    return any(
        _is_gate(h["command"])
        for e in (entries if isinstance(entries, list) else [])
        if isinstance(e, dict) and isinstance(e.get("hooks"), list)
        for h in e["hooks"]
        if isinstance(h, dict) and isinstance(h.get("command"), str)
    )


def _gate_commands(settings: Path) -> list[str]:
    data = json.loads(settings.read_text(encoding="utf-8"))
    return [h["command"] for e in data["hooks"]["PreToolUse"] for h in e["hooks"]]


def test_register_gate_creates(tmp_path: Path):
    msg = register_gate(tmp_path)
    assert "등록" in msg
    cmds = _gate_commands(tmp_path / ".claude" / "settings.json")
    assert any(_is_gate(c) for c in cmds)


def test_register_gate_idempotent(tmp_path: Path):
    register_gate(tmp_path)
    msg = register_gate(tmp_path)
    assert "이미" in msg
    # not registered twice
    cmds = _gate_commands(tmp_path / ".claude" / "settings.json")
    assert sum(_is_gate(c) for c in cmds) == 1


def test_register_gate_preserves_existing(tmp_path: Path):
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    other = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo other"}]}
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [other]}}), encoding="utf-8")
    register_gate(tmp_path)
    cmds = _gate_commands(settings)
    assert "echo other" in cmds
    assert any(_is_gate(c) for c in cmds)


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
    assert cmds == [GATE_COMMAND, GATE_COMMAND]  # both repaired (not only the first)


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
    assert any(_is_gate(c) for c in _gate_commands(settings))
    # --uninstall dispatch → inverse operation
    monkeypatch.setattr(sys, "argv", ["flow_init_setup.py", "--uninstall"])
    main()
    assert not vd.exists()
    assert not any(_is_gate(c) for c in _gate_commands(settings))


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
    assert result.returncode == 0, f"the two import paths stopped coexisting: {result.stderr}"


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
    assert not any(_is_gate(c) for c in _gate_commands(tmp_path / ".claude" / "settings.json"))
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


def test_uninstall_names_the_workflows_that_break(tmp_path: Path, capsys):
    # uninstall removes .claude/harness-tier/scripts/, and wiki-verify.yml is what runs
    # those scripts. Its own guard keeps it green; the gitversion and jreleaser release
    # renders call the same path unguarded and do turn every push red. Guidance names both.
    run_uninstall(tmp_path)
    out = capsys.readouterr().out
    assert "wiki-verify.yml" in out
    # Not the bare word "release" — the guidance before this one contained it too, and
    # "python-semantic-release" contains it as a substring.
    assert "gitversion" in out
    assert "jreleaser" in out


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
    assert not any(_is_gate(c) for c in cmds)


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


def test_copy_files_includes_new_scripts():
    from scripts.flow_init_setup import COPY_FILES

    assert "scripts/check-token-write.sh" in COPY_FILES
    assert "scripts/finalize_prerelease.py" in COPY_FILES


def test_wiki_graph_is_copied_to_the_host():
    from scripts.flow_init_setup import COPY_FILES

    assert "scripts/wiki_graph.py" in COPY_FILES


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


def test_render_wiki_verify_workflow_unconditional(tmp_path: Path):
    # Rendered whether or not flow-config exists and whether or not the wiki is enabled:
    # the script guarantees a no-op green, which is what frees /flow-init from depending on
    # /wiki-init having run.
    out = render_wiki_verify_workflow(tmp_path, PLUGIN)
    assert any("생성" in line for line in out)
    dest = tmp_path / ".github" / "workflows" / "wiki-verify.yml"
    text = dest.read_text(encoding="utf-8")
    assert "__HARNESS_" not in text
    data = _yaml.safe_load(text)
    assert data["jobs"]["wiki-verify"]["timeout-minutes"] == 5


def _wiki_verify_step(host: Path) -> str:
    data = _yaml.safe_load(
        (host / ".github" / "workflows" / "wiki-verify.yml").read_text(encoding="utf-8")
    )
    steps = data["jobs"]["wiki-verify"]["steps"]
    return next(s["run"] for s in steps if s.get("name") == "Verify wiki graph")


def test_wiki_verify_step_is_green_without_the_script(tmp_path: Path):
    # The unconditional render reaches repos that gitignore .claude/, where the checkout holds
    # no script and an unguarded python3 exits 2 — a red push for a repo that never opted into
    # a wiki. The step's shell is executed rather than pattern-matched: a guard that reads
    # right and short-circuits wrong is what a substring assertion cannot tell apart.
    render_wiki_verify_workflow(tmp_path, PLUGIN)
    step = tmp_path / "step.sh"
    step.write_text(_wiki_verify_step(tmp_path), encoding="utf-8", newline="\n")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # python3 is stubbed rather than assumed: the second arm has to prove the guard falls
    # THROUGH to the verify call, and an exit code the runner's own interpreter chose would
    # not tell that apart from a short circuit.
    stub = bin_dir / "python3"
    stub.write_text("#!/usr/bin/env bash\nexit 3\n", encoding="utf-8", newline="\n")
    stub.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")

    absent = subprocess.run(
        [BASH, "-e", str(step)], cwd=tmp_path, env=env, capture_output=True, text=True
    )
    assert absent.returncode == 0, absent.stderr

    script = tmp_path / ".claude" / "harness-tier" / "scripts" / "wiki_graph.py"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")
    present = subprocess.run(
        [BASH, "-e", str(step)], cwd=tmp_path, env=env, capture_output=True, text=True
    )
    assert present.returncode == 3, "the guard swallowed the verify call"


def test_render_wiki_verify_workflow_preserves_existing(tmp_path: Path):
    dest = tmp_path / ".github" / "workflows" / "wiki-verify.yml"
    dest.parent.mkdir(parents=True)
    dest.write_text("# custom\n", encoding="utf-8")
    out = render_wiki_verify_workflow(tmp_path, PLUGIN)
    assert any("이미" in line for line in out)
    assert dest.read_text(encoding="utf-8") == "# custom\n"


def test_run_setup_renders_wiki_verify(tmp_path: Path, capsys):
    run_setup(tmp_path, PLUGIN)
    assert (tmp_path / ".github" / "workflows" / "wiki-verify.yml").is_file()
    assert "wiki 검증" in capsys.readouterr().out


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


def test_release_templates_source_files_exist():
    from scripts.flow_init_setup import _RELEASE_TEMPLATES

    for tool, rel_path in _RELEASE_TEMPLATES.items():
        assert (PLUGIN / rel_path).is_file(), f"{tool}: missing template {rel_path}"


def _write_fake_release_template(plugin: Path, rel_path: str) -> None:
    dest = plugin / rel_path
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(
        "on:\n  push:\n    branches: [__HARNESS_STABLE__, __HARNESS_PRERELEASE__]\n",
        encoding="utf-8",
    )


def test_render_versioning_new_tools_case_insensitive(tmp_path):
    from scripts import flow_init_setup as m
    from scripts.flow_init_setup import _RELEASE_TEMPLATES

    for tool in ("jreleaser", "gitversion", "cargo-release"):
        plugin = tmp_path / tool / "plugin"
        host = tmp_path / tool / "host"
        _write_fake_release_template(plugin, _RELEASE_TEMPLATES[tool])
        (host / ".claude" / "harness-tier" / "config").mkdir(parents=True)
        # Proper-noun casing (as a researcher might propose it) must still resolve.
        (host / ".claude" / "harness-tier" / "config" / "flow-config.yaml").write_text(
            f"versioning:\n  enable: true\n  release_tool: {tool.upper()}\n"
            "  branches: {stable: main, prerelease: stage}\n",
            encoding="utf-8",
        )
        m.render_versioning_workflows(host, plugin)
        rel = host / ".github" / "workflows" / "release.yml"
        assert rel.is_file(), f"{tool}: release.yml not rendered"
        assert "__HARNESS_" not in rel.read_text(encoding="utf-8")


def test_render_versioning_unknown_tool_skips(tmp_path):
    from scripts import flow_init_setup as m

    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    (host / ".claude" / "harness-tier" / "config").mkdir(parents=True)
    (host / ".claude" / "harness-tier" / "config" / "flow-config.yaml").write_text(
        "versioning:\n  enable: true\n  release_tool: some-made-up-tool\n"
        "  branches: {stable: main, prerelease: stage}\n",
        encoding="utf-8",
    )
    out = m.render_versioning_workflows(host, plugin)
    assert not (host / ".github" / "workflows" / "release.yml").exists()
    assert any("알 수 없는 release_tool" in line for line in out)


# ── unit_test workflow rendering ────────────────────────────────────────────────


def _write_unit_test_config(host: Path, unit_test: dict) -> None:
    cfg_dir = host / ".claude" / "harness-tier" / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "flow-config.yaml").write_text(
        _yaml.safe_dump({"unit_test": unit_test}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


_UNIT_TEST_SAMPLE = {
    "enable": True,
    "branches": ["dev", "stage", "main"],
    "timeout_minutes": 25,
    "jobs": [
        {
            "name": "api",
            "language": "python",
            "version": "3.12",
            "setup": "pip install uv && uv sync",
            "test": "uv run pytest",
        },
        {
            "name": "web",
            "language": "node",
            "version": "20",
            "setup": "npm ci",
            "test": "npm test",
        },
    ],
}


def test_render_unit_test_creates_and_substitutes(tmp_path: Path):
    _write_unit_test_config(tmp_path, _UNIT_TEST_SAMPLE)
    out = render_unit_test_workflow(tmp_path, PLUGIN)
    assert any("생성" in line for line in out)
    dest = tmp_path / ".github" / "workflows" / "unit-test.yml"
    text = dest.read_text(encoding="utf-8")
    # all tokens substituted
    assert "__HARNESS_" not in text
    # config-driven timeout applied to the job
    assert "timeout-minutes: 25" in text
    # branch substitution
    assert "branches: [dev, stage, main]" in text
    # the whole rendered document is valid YAML, and the variable-length jobs[] became a valid
    # matrix.include list of mappings (this is the "matrix include valid YAML" guard).
    data = _yaml.safe_load(text)
    include = data["jobs"]["unit-test"]["strategy"]["matrix"]["include"]
    assert [j["name"] for j in include] == ["api", "web"]
    assert data["jobs"]["unit-test"]["timeout-minutes"] == 25
    # every declared field survives the flow-style round-trip
    api = include[0]
    assert api["language"] == "python" and api["version"] == "3.12"
    assert api["setup"] == "pip install uv && uv sync" and api["test"] == "uv run pytest"


def test_supported_setup_languages_matches_the_template_gates():
    # One fact in three places: the template's `if: matrix.language == '<lang>'` steps, the
    # constant that copies them, and the list flow-config.example advertises to hosts. A copy
    # drifts silently — adding a setup-* step without the constant makes that language warn as a
    # typo, dropping one lets the real typo through, and a stale example teaches the wrong value.
    # Read all three back out of their files so none can diverge unnoticed.
    from scripts.flow_init_setup import (
        EXAMPLE_CONFIG,
        SUPPORTED_SETUP_LANGUAGES,
        UNIT_TEST_TEMPLATE,
    )

    template = (PLUGIN / UNIT_TEST_TEMPLATE).read_text(encoding="utf-8")
    gates = set(re.findall(r"matrix\.language == '([^']+)'", template))
    assert gates == set(SUPPORTED_SETUP_LANGUAGES)

    # Split on the bare pipe and strip, so respacing the list is a formatting edit rather than a
    # failure that reads like a real divergence. Both asserts carry a message for the same reason.
    example = (PLUGIN / EXAMPLE_CONFIG).read_text(encoding="utf-8")
    documented = re.search(r"#\s+language:\s+([a-z |]+?)\s+→", example)
    assert documented, "flow-config.example's `language:` slot line moved or was rewrapped"
    listed = {word.strip() for word in documented.group(1).split("|")}
    assert listed == set(SUPPORTED_SETUP_LANGUAGES), f"example documents {sorted(listed)}"


def test_unit_test_language_warnings_flags_case_variant_only():
    # only a case variant of a supported language (near-certain typo) warns; an exact match and a
    # genuinely custom language (the escape hatch flow-config.example documents) do not, and a job
    # without `language` is ignored.
    from scripts.flow_init_setup import _unit_test_language_warnings

    warnings = _unit_test_language_warnings(
        [
            {"name": "api", "language": "Python"},  # case variant → warn
            {"name": "web", "language": "node"},  # exact supported → no warn
            {"name": "edge", "language": "deno"},  # custom runtime → escape hatch, no warn
            {"name": "nolang"},  # no language key → no warn
        ]
    )
    assert len(warnings) == 1
    assert "'api'" in warnings[0] and "'Python'" in warnings[0]


def test_render_unit_test_surfaces_language_warning(tmp_path: Path):
    # the case-variant warning must reach the render log, and rendering still succeeds (non-fatal).
    _write_unit_test_config(
        tmp_path,
        {"enable": True, "jobs": [{"name": "api", "language": "GO", "test": "go test ./..."}]},
    )
    out = render_unit_test_workflow(tmp_path, PLUGIN)
    assert any("'GO'" in line and "매칭" in line for line in out)
    assert any("생성" in line for line in out)


def test_render_unit_test_default_timeout(tmp_path: Path):
    # timeout_minutes omitted → falls back to UNIT_TEST_DEFAULT_TIMEOUT (10). Locks the default so
    # a drift between the constant and the docs that quote it is caught.
    from scripts.flow_init_setup import UNIT_TEST_DEFAULT_TIMEOUT

    _write_unit_test_config(
        tmp_path,
        {"enable": True, "jobs": [{"name": "api", "language": "python", "test": "pytest"}]},
    )
    render_unit_test_workflow(tmp_path, PLUGIN)
    text = (tmp_path / ".github" / "workflows" / "unit-test.yml").read_text(encoding="utf-8")
    assert f"timeout-minutes: {UNIT_TEST_DEFAULT_TIMEOUT}" in text
    assert UNIT_TEST_DEFAULT_TIMEOUT == 10


def test_render_unit_test_null_timeout_falls_back(tmp_path: Path):
    # timeout_minutes present but blank (null) must fall back to the default, NOT render
    # `timeout-minutes: None` (yaml.safe_load accepts the string so a naive check misses it,
    # but GitHub Actions rejects a non-integer cap → CLAUDE.md "every job caps timeout" broken).
    from scripts.flow_init_setup import UNIT_TEST_DEFAULT_TIMEOUT

    _write_unit_test_config(
        tmp_path,
        {"enable": True, "timeout_minutes": None, "jobs": [{"name": "api", "test": "pytest"}]},
    )
    render_unit_test_workflow(tmp_path, PLUGIN)
    text = (tmp_path / ".github" / "workflows" / "unit-test.yml").read_text(encoding="utf-8")
    assert "timeout-minutes: None" not in text
    assert f"timeout-minutes: {UNIT_TEST_DEFAULT_TIMEOUT}" in text


def test_render_unit_test_disabled(tmp_path: Path):
    _write_unit_test_config(tmp_path, {"enable": False, "jobs": [{"name": "x", "test": "t"}]})
    out = render_unit_test_workflow(tmp_path, PLUGIN)
    assert any("enable=false" in line for line in out)
    cfg = {"enable": False, "jobs": [{"name": "x", "test": "t"}]}
    assert load_unit_test_config(tmp_path) == cfg
    assert not (tmp_path / ".github" / "workflows" / "unit-test.yml").exists()


def test_render_unit_test_absent_section(tmp_path: Path):
    # flow-config absent → unconfigured → skip (FAIL-OPEN, non-destructive)
    out = render_unit_test_workflow(tmp_path, PLUGIN)
    assert any("미설정" in line for line in out)
    assert load_unit_test_config(tmp_path) is None
    assert not (tmp_path / ".github" / "workflows" / "unit-test.yml").exists()


def test_render_unit_test_empty_jobs_skips(tmp_path: Path):
    # enabled but no jobs → nothing to render → skip (do not emit an empty matrix)
    _write_unit_test_config(tmp_path, {"enable": True, "jobs": []})
    out = render_unit_test_workflow(tmp_path, PLUGIN)
    assert any("jobs" in line for line in out)
    assert not (tmp_path / ".github" / "workflows" / "unit-test.yml").exists()


def test_render_unit_test_idempotent_reports_only(tmp_path: Path):
    _write_unit_test_config(tmp_path, _UNIT_TEST_SAMPLE)
    render_unit_test_workflow(tmp_path, PLUGIN)  # first render (create)
    dest = tmp_path / ".github" / "workflows" / "unit-test.yml"
    sentinel = dest.read_text(encoding="utf-8") + "\n# user edit\n"
    dest.write_text(sentinel, encoding="utf-8")  # simulate a user edit
    out = render_unit_test_workflow(tmp_path, PLUGIN)  # second render — report only
    assert any("이미 있어" in line for line in out)
    assert dest.read_text(encoding="utf-8") == sentinel  # not overwritten


def test_run_setup_renders_unit_test(tmp_path: Path, capsys):
    _write_unit_test_config(tmp_path, _UNIT_TEST_SAMPLE)
    run_setup(tmp_path, PLUGIN)
    captured = capsys.readouterr().out
    assert "유닛 테스트" in captured
    assert (tmp_path / ".github" / "workflows" / "unit-test.yml").is_file()


def test_all_github_workflow_templates_have_timeout():
    # every rendered/copied workflow template must cap wall-clock via timeout-minutes (a hung
    # runner otherwise burns the full 6h default). Guards against a new template omitting it.
    templates = sorted(PLUGIN.glob("github/*.workflow.example.yml"))
    assert templates, "no workflow templates found"
    missing = [t.name for t in templates if "timeout-minutes" not in t.read_text(encoding="utf-8")]
    assert not missing, f"templates missing timeout-minutes: {missing}"


def test_release_workflows_do_not_pin_the_checkout_ref():
    # Covers the shipped templates and this repo's own release workflow in one sweep, for the
    # reason the run-block sweep above gives: keeping both halves under one assertion is what
    # stops them drifting apart. A release triggers on push, where actions/checkout already
    # attaches HEAD to the triggering branch (`git checkout --force -B <branch>
    # refs/remotes/origin/<branch>`, the remote ref fetched at the event's sha). Pinning `ref:`
    # re-resolves the branch *tip*, so a commit that landed after the trigger is released without
    # having been tested. Deploy templates are excluded on purpose: they are workflow_call'd with
    # an explicit tag, and a tag cannot move under them.
    offenders = []
    for t in sorted(PLUGIN.glob("github/release.*.workflow.example.yml")) + [
        PLUGIN / ".github" / "workflows" / "release.yml"
    ]:
        data = _yaml.safe_load(t.read_text(encoding="utf-8")) or {}
        for job in (data.get("jobs") or {}).values():
            for step in (job or {}).get("steps") or []:
                if str(step.get("uses", "")).startswith("actions/checkout"):
                    ref = (step.get("with") or {}).get("ref")
                    if ref is not None:
                        offenders.append(f"{t.name}: ref: {ref}")
    assert not offenders, f"a push-triggered release checkout must not pin ref: {offenders}"


def test_all_github_workflow_templates_are_valid_yaml():
    # the SOURCE templates are YAML files tracked in this repo, so check-yaml (pre-commit) parses
    # them. A __HARNESS_*__ token placed at a spot that breaks the *pre-render* parse (e.g. a bare
    # scalar at column 0) would fail CI even though the rendered output is fine. Every token must
    # sit at a valid scalar / list-item position so the template parses before substitution.
    for t in sorted(PLUGIN.glob("github/*.workflow.example.yml")):
        _yaml.safe_load(t.read_text(encoding="utf-8"))  # raises on malformed YAML


def test_merge_strategy_policy_reaches_host(tmp_path: Path):
    """copy_artifacts must carry the merge_strategy policy into the host config dir."""
    import yaml

    from scripts.flow_init_setup import copy_artifacts

    plugin = Path(__file__).resolve().parents[1]
    host = tmp_path / "host"
    host.mkdir()
    copy_artifacts(plugin, host)
    dest = host / ".claude" / "harness-tier" / "config" / "flow-tiers.yaml"
    data = yaml.safe_load(dest.read_text(encoding="utf-8"))
    assert isinstance(data.get("merge_strategy"), list)
    assert any(r.get("require") == "--squash" for r in data["merge_strategy"])


# A `${{ }}` expression inside a `run:` block is substituted textually before the shell ever
# sees the script, so a value carrying shell metacharacters becomes code rather than data.
# `github.ref_name` is the live one: git only forbids whitespace and `~^:?*[\` in a ref, so
# `$(...)`, backticks and `;` are all legal branch names. Today every release template triggers
# on a fixed two-branch list, which is the only reason this is not already exploitable — the
# defence sits in the trigger, not in the code. Templates get edited (a tag push, a `release/**`
# glob) and the defence disappears with no diff to the step that consumes it. `env:` + `"$VAR"`
# moves the defence into the step itself, where the edit cannot reach it.
#
# An allow-list, deliberately, not a deny-list of the contexts known to be dangerous. `matrix.*`
# IS the command the host configured (unit-test renders flow-config `jobs[]` into it) and
# `steps.*` is, with one exception noted below, a literal the workflow itself echoed into
# `$GITHUB_OUTPUT`. Everything else fails here — including values that look inert, like
# `github.run_number`. Judging each context on whether it happens to be an integer today is
# precisely how five templates ended up split across two patterns while every individual file
# read as fine.
#
# The exception, recorded rather than special-cased: `steps.gitversion.outputs.semVer` in
# release.gitversion comes from a third-party action, not from this workflow's own echo, and
# GitVersion derives it from the branch name. It stays allowed because semver output is
# constrained to `[0-9A-Za-z.-]` and the step is an informational `continue-on-error` echo —
# but the blanket "steps.* is our own literal" claim is not true of it.
WORKFLOW_CONTEXTS = frozenset(
    {
        "github",
        "env",
        "vars",
        "job",
        "jobs",
        "steps",
        "runner",
        "secrets",
        "strategy",
        "matrix",
        "needs",
        "inputs",
    }
)
WORKFLOW_RUN_CONTEXTS_ALLOWED = frozenset({"matrix", "steps"})


def _disallowed_contexts(expr: str) -> set[str]:
    """Which contexts one `${{ }}` expression reaches for that must not touch a shell.

    Every reference in the expression, not the leading one. A prefix test answers "does this
    start with something allowed", which is a different question: `${{ steps.a.outputs.b ||
    github.event.head_commit.message }}` starts with `steps.` and carries a commit message.
    The `||` fallback is ordinary workflow idiom — this repo already writes
    `secrets.RELEASE_TOKEN || secrets.GITHUB_TOKEN` — so that shape arrives by normal editing
    rather than by anyone attacking the check.

    The rule is "an identifier with no dot in front of it", not "an identifier with a dot after
    it". Requiring the trailing dot missed every reference that is not a property dereference —
    `toJSON(github)`, `github['event']['message']` (index syntax is interchangeable with the dot
    form) and `GITHUB.actor` (the evaluator is case-insensitive). Leading-dot exclusion is also
    what keeps a *segment* from reading as a context, in both directions: `outputs` in
    `steps.x.outputs.y` is not the outputs context, and a step whose id is `env` is still a step.

    Known-list filtering means an unrecognised name passes, so a context GitHub adds later is
    fail-open here until this set is updated."""
    identifiers = {m.lower() for m in re.findall(r"(?<![.\w])([A-Za-z_][A-Za-z0-9_-]*)", expr)}
    return (identifiers & WORKFLOW_CONTEXTS) - WORKFLOW_RUN_CONTEXTS_ALLOWED


def _run_block_expressions(text: str) -> list[tuple[str, str]]:
    """Every `${{ }}` that lands inside a `run:` script, as (step label, expression).

    Takes the YAML text rather than a path so that generated workflows — which exist only as a
    Python string until a consumer renders them — go through the identical parse."""
    data = _yaml.safe_load(text)
    found = []
    for job_name, job in (data.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            # A step is a mapping; `uses:`-only steps carry no `run:` and are skipped by the
            # isinstance check below rather than by guessing at the schema.
            if not isinstance(step, dict) or not isinstance(step.get("run"), str):
                continue
            for expr in re.findall(r"\$\{\{(.*?)\}\}", step["run"], re.DOTALL):
                found.append((str(step.get("name", job_name)), expr.strip()))
    return found


def test_the_run_block_check_reads_every_context_in_an_expression_not_just_the_first():
    """Locks the hole a prefix test left: an allowed context in front, a forbidden one behind."""
    assert _disallowed_contexts("steps.a.outputs.b || github.event.head_commit.message") == {
        "github"
    }
    assert _disallowed_contexts("matrix.x && github.actor || ''") == {"github"}
    assert _disallowed_contexts("inputs.tag") == {"inputs"}
    # Allowed stays allowed, and `outputs` — a segment, not a context — is not mistaken for one.
    assert _disallowed_contexts("steps.sr.outputs.released") == set()
    assert _disallowed_contexts("matrix.setup") == set()


def test_the_run_block_check_reads_contexts_that_are_not_followed_by_a_dot():
    """A reference does not have to be `name.field`, and matching on the dot missed three shapes.

    `toJSON(github)` is the one that matters: dumping a whole context is the standard way people
    debug a workflow, so it arrives by ordinary editing rather than by anyone evading the check —
    and it inlines the entire `github` context, `event.head_commit.message` included, into the
    script. Index syntax is interchangeable with property dereference in GitHub expressions, and
    the expression evaluator is case-insensitive, so both of those are valid too."""
    assert _disallowed_contexts("toJSON(github)") == {"github"}
    assert _disallowed_contexts("fromJSON(inputs.config).name") == {"inputs"}
    assert _disallowed_contexts("github['event']['head_commit']['message']") == {"github"}
    assert _disallowed_contexts("GITHUB.actor") == {"github"}
    # The mirror of the same fix: only an identifier NOT preceded by a dot is a context, so a
    # step whose id happens to be `env` stays a step reference rather than reading as env.*.
    assert _disallowed_contexts("steps.env.outputs.x") == set()
    assert _disallowed_contexts("secrets.RELEASE_TOKEN || secrets.GITHUB_TOKEN") == {"secrets"}


def test_no_workflow_interpolates_a_context_value_into_a_run_block():
    """Covers the shipped templates and this repo's own workflows in one sweep.

    Both halves matter. The templates are what `/flow-init` renders into a consumer repo, so a
    bad pattern there is shipped; this repo's own `.github/workflows/` is where the good pattern
    was worked out first, and keeping both under one assertion is what stops the two from
    drifting apart again."""
    offenders = []
    for path in sorted(PLUGIN.glob("github/*.yml")) + sorted(
        PLUGIN.glob(".github/workflows/*.yml")
    ):
        for step, expr in _run_block_expressions(path.read_text(encoding="utf-8")):
            if _disallowed_contexts(expr):
                offenders.append(f"{path.name}: step {step!r} interpolates ${{{{ {expr} }}}}")
    assert not offenders, (
        "a run: block interpolates a context value directly into the shell — bind it to env: "
        'and read it as "$VAR" instead:\n  ' + "\n  ".join(offenders)
    )


def test_the_generated_deploy_orchestrator_keeps_contexts_out_of_its_run_block():
    """The sweep above globs files, and `deploy.yml` is not one — `_orchestrator_yaml` assembles
    it from Python string literals, so it stayed invisible to a check written in terms of paths
    while shipping to every consumer that runs `/harness-deployments`.

    It is also the worst place to leave the pattern. The release templates' `github.ref_name` is
    held safe by a fixed two-branch trigger; this workflow's `inputs.tag` is a `required: false,
    type: string` **workflow_dispatch** input, which GitHub does not constrain, and the jobs it
    feeds run with `secrets: inherit`. Nothing stands between that input and the shell."""
    from scripts.flow_init_setup import _orchestrator_yaml

    rendered = _orchestrator_yaml(
        [{"name": "pypi", "target": "pypi"}, {"name": "ghcr", "target": "ghcr"}], ["pypi", "ghcr"]
    )
    offenders = [
        f"step {step!r} interpolates ${{{{ {expr} }}}} ({', '.join(sorted(bad))})"
        for step, expr in _run_block_expressions(rendered)
        if (bad := _disallowed_contexts(expr))
    ]
    assert not offenders, (
        "the generated deploy.yml interpolates a context value into the shell:\n  "
        + "\n  ".join(offenders)
    )


def test_the_gate_answerer_is_copied_before_the_runner_that_asks_it():
    """precommit-runner.sh routes on what flow_gate_check.py --classify answers, so a sync that
    lands the runner first leaves a window where the new runner asks a script that does not know
    the question — it reads no verdict and gates nothing. The other order is harmless: an old
    runner's question goes unanswered and ROOT stays on main, which is the documented FAIL-OPEN.
    """
    from scripts.flow_init_setup import COPY_FILES

    files = COPY_FILES
    # The whole chain, not one link: flow_gate_check.py imports _harness_paths, so landing
    # it first beside a stale module answers every question with ModuleNotFoundError.
    for earlier, later in (
        ("scripts/_harness_paths.py", "scripts/flow_gate_check.py"),
        ("scripts/flow_gate_check.py", "scripts/precommit-runner.sh"),
    ):
        assert files.index(earlier) < files.index(later), (earlier, later)


def test_a_gate_entry_under_another_tool_is_repaired(tmp_path: Path):
    """The matcher is the gate's identity too. An entry naming this script under another
    tool is a hook that never fires on a commit, and counting it as the gate leaves the
    host reporting a gate it does not have."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    planted = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Read",
                    "hooks": [
                        {
                            "type": "command",
                            "shell": "bash",
                            "command": fis.GATE_COMMAND,
                            "timeout": 600,
                            "statusMessage": fis.GATE_STATUS,
                        }
                    ],
                }
            ]
        }
    }
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text(json.dumps(planted), encoding="utf-8")
    fis.register_gate(tmp_path)
    after = json.loads(settings.read_text(encoding="utf-8"))
    firing = [
        e
        for e in after["hooks"]["PreToolUse"]
        if any(fis._is_gate_hook(h) for h in e.get("hooks") or [])
    ]
    assert [e["matcher"] for e in firing] == ["Bash"], after["hooks"]["PreToolUse"]


def _planted(tmp_path: Path, entries: list) -> Path:
    (tmp_path / ".claude").mkdir(parents=True)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text(json.dumps({"hooks": {"PreToolUse": entries}}), encoding="utf-8")
    return settings


def _gate_hook() -> dict:
    import scripts.flow_init_setup as fis

    return {
        "type": "command",
        "shell": "bash",
        "command": fis.GATE_COMMAND,
        "timeout": 600,
        "statusMessage": fis.GATE_STATUS,
    }


def test_a_hook_the_host_wrote_stays_where_the_host_put_it(tmp_path: Path):
    """An entry is a container for several hooks, and it is the HOST's. Rewriting its matcher
    to reach our hook re-points every other hook in it at another tool — the host's audit hook
    would start firing on Bash, which is a change to config this plugin does not own."""
    import scripts.flow_init_setup as fis

    theirs = {"type": "command", "command": "my-audit.sh"}
    settings = _planted(tmp_path, [{"matcher": "Read", "hooks": [_gate_hook(), theirs]}])
    fis.register_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    survivors = [e for e in pre if theirs in (e.get("hooks") or [])]
    assert [e["matcher"] for e in survivors] == ["Read"], pre
    assert any(
        e.get("matcher") == "Bash" and any(fis._is_gate_hook(h) for h in e.get("hooks") or [])
        for e in pre
    ), pre


def test_a_matcher_that_already_covers_bash_is_left_alone(tmp_path: Path):
    """`Bash|Write` fires on a commit, so it is the gate. Narrowing it to `Bash` would silently
    drop the Write coverage the host asked for, and nothing about the gate needs it gone."""
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": "Bash|Write", "hooks": [_gate_hook()]}])
    out = fis.register_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert [e["matcher"] for e in pre] == ["Bash|Write"], pre
    assert "skip" in out, out


# Spellings the hooks reference defines as one tool name or a `|` list of them, in the one form
# every host version reads the same way. Each fires on a commit, so the gate is already
# registered under it and touching the entry would drop coverage the host asked for.
COVERS_BASH = [
    "Bash",
    "Bash|Write",
    "Bash|",
    "|Bash",
    "Bash||Write",
    "Bash| Write",
    "Bash|code-reviewer",
    "Write|Read|Bash",
    "Bash|tool_2",
    "*",
    "",
]
# Spellings that name no tool a commit arrives through. Both readings agree, so the gate hook
# comes out of the entry and the entry keeps everything else.
COVERS_NOTHING = ["Read", "bash", "Write|Edit", "Write, Edit"]
# Spellings this script cannot decide. A matcher outside the name alphabet is a JavaScript
# regular expression and Python's dialect disagrees with it (`(?i)` and `\Z` are Python's
# alone); the comma separator and the whitespace around a name are newer than the oldest host
# this runs on, which reads the same text as a pattern. Undecided leaves the entry exactly as
# the host wrote it AND gives the gate an entry of its own, so the gate exists either way.
CANNOT_DECIDE = [
    ["Bash"],
    7,
    False,
    0,
    {"tool": "Bash"},
    "Bash, Write",
    "Bash,Write",
    "ash|x-y",
    "Bash | Write",
    "Bash ",
    "Write, Bash",
    "^Bash$",
    ".*",
    "Bash|.*",
    "Bash|mcp__x.y",
    "^Notebook",
    "mcp__.*",
    "Bash[",
    "(?i)bash",
    "Bash" + chr(92) + "Z",
]


def _firing(pre: list) -> list:
    import scripts.flow_init_setup as fis

    return [e for e in pre if any(fis._is_gate_hook(h) for h in e.get("hooks") or [])]


@pytest.mark.parametrize("matcher", COVERS_BASH, ids=[repr(m) for m in COVERS_BASH])
def test_a_matcher_that_already_names_bash_is_the_gate(tmp_path: Path, matcher):
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": matcher, "hooks": [_gate_hook()]}])
    out = fis.register_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert "skip" in out, out
    assert [e["matcher"] for e in pre] == [matcher], pre


def test_a_matcher_left_out_entirely_is_every_tool(tmp_path: Path):
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"hooks": [_gate_hook()]}])
    out = fis.register_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert "skip" in out, out
    assert len(pre) == 1, pre


@pytest.mark.parametrize("matcher", COVERS_NOTHING, ids=[repr(m) for m in COVERS_NOTHING])
def test_a_matcher_naming_no_tool_the_gate_uses_gives_the_hook_up(tmp_path: Path, matcher):
    import scripts.flow_init_setup as fis

    settings = _planted(
        tmp_path, [{"matcher": matcher, "team_note": "ours", "hooks": [_gate_hook()]}]
    )
    fis.register_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert [e.get("matcher") for e in _firing(pre)] == ["Bash"], pre
    assert pre[0] == {"matcher": matcher, "team_note": "ours", "hooks": []}, pre


@pytest.mark.parametrize("matcher", CANNOT_DECIDE, ids=[repr(m) for m in CANNOT_DECIDE])
def test_a_matcher_this_script_cannot_decide_is_left_as_written(tmp_path: Path, matcher):
    """Acted on as "does not fire", a `^Bash$` the host anchored on purpose loses the hook it
    was holding and the report says the entry never fired. Both are false, and the entry is the
    host's, so the only thing this script may do about it is add one of its own."""
    import scripts.flow_init_setup as fis

    planted = {"matcher": matcher, "team_note": "ours", "hooks": [_gate_hook()]}
    settings = _planted(tmp_path, [dict(planted)])
    fis.register_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert pre[0] == planted, pre
    assert "Bash" in [e.get("matcher") for e in _firing(pre)], pre


def test_registering_twice_over_a_matcher_that_cannot_be_decided_settles(tmp_path: Path):
    """The added entry has to be recognised as the gate on the next run, or every /flow-init
    adds another one beside a hook it will not touch."""
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": "^Bash$", "hooks": [_gate_hook()]}])
    fis.register_gate(tmp_path)
    first = settings.read_text(encoding="utf-8")
    assert "skip" in fis.register_gate(tmp_path)
    assert settings.read_text(encoding="utf-8") == first


def test_an_emptied_host_entry_keeps_what_the_host_wrote(tmp_path: Path):
    """Taking the gate hook out of an entry does not make the entry ours. Its matcher and the
    keys beside `hooks` are configuration this plugin never wrote."""
    import scripts.flow_init_setup as fis

    settings = _planted(
        tmp_path, [{"matcher": "Read", "team_note": "ours", "hooks": [_gate_hook()]}]
    )
    out = fis.register_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert "skip" not in out, out
    assert pre[0] == {"matcher": "Read", "team_note": "ours", "hooks": []}, pre


# A settings.json the host hand-edited into a shape the schema does not describe. /flow-init
# runs unguarded, so an exception here takes the marketplace, pre-commit, .gitignore and the
# rendered workflows down with the gate.
MALFORMED = [
    ("hooks is a list", {"hooks": []}),
    ("hooks is null", {"hooks": None}),
    ("hooks is a string", {"hooks": "x"}),
    ("the document is a list", [1, 2]),
    ("PreToolUse is a dict", {"hooks": {"PreToolUse": {}}}),
    ("an entry is a string", {"hooks": {"PreToolUse": ["x"]}}),
    ("entry hooks is a number", {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": 5}]}}),
    ("entry hooks is true", {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": True}]}}),
    (
        "a foreign entry's hooks is a number",
        {"hooks": {"PreToolUse": [{"matcher": "Read", "hooks": 5}]}},
    ),
    (
        "a foreign entry's hooks is a string",
        {"hooks": {"PreToolUse": [{"matcher": "Read", "hooks": "x"}]}},
    ),
    (
        "a hook command is a number",
        {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"command": 7}]}]}},
    ),
    (
        "a hook command is true",
        {"hooks": {"PreToolUse": [{"matcher": "Read", "hooks": [{"command": True}]}]}},
    ),
    (
        "a hook is a string",
        {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": ["theirs.sh"]}]}},
    ),
    ("the document is a string", "x"),
    ("the document is a number", 7),
    ("the document is true", True),
]


@pytest.mark.parametrize("label,payload", MALFORMED, ids=[label for label, _ in MALFORMED])
def test_a_settings_shape_the_schema_does_not_describe_is_reported(
    tmp_path: Path, label: str, payload
):
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text(json.dumps(payload), encoding="utf-8")
    before = settings.read_bytes()
    outs = [fis.register_gate(tmp_path), fis.unregister_gate(tmp_path)]
    for out in outs:
        assert out[:5] in ("  [!]", "  [=]", "  [+]", "  [-]"), (label, out)
    if outs[0].startswith("  [!]"):
        # Refused: the document itself is the shape that cannot be read, so nothing was written.
        assert settings.read_bytes() == before, label
        return
    # Accepted: the junk sits below the level this reads, so the gate installs around it and
    # every entry the host wrote is still there afterwards.
    planted = (payload.get("hooks") or {}).get("PreToolUse")
    kept = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert all(entry in kept for entry in planted), (label, kept)


def test_a_byte_order_mark_is_not_a_broken_settings_file(tmp_path: Path):
    """An editor on this host writes one. Read as a parse failure it leaves the gate
    uninstalled, with a message that names the wrong problem."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text("\ufeff{}", encoding="utf-8")
    assert "등록" in fis.register_gate(tmp_path)


def test_uninstall_leaves_a_host_hook_that_shares_the_gate_entry(tmp_path: Path):
    """The gate hook stays inside a host entry whenever that entry already fires on Bash, so
    removing the entry on the way out takes hooks the host wrote."""
    import scripts.flow_init_setup as fis

    fis.register_gate(tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    data = json.loads(settings.read_text(encoding="utf-8"))
    theirs = {"type": "command", "command": "my-audit.sh"}
    data["hooks"]["PreToolUse"][0]["hooks"].append(theirs)
    settings.write_text(json.dumps(data), encoding="utf-8")

    assert "skip" in fis.register_gate(tmp_path)
    fis.unregister_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    hooks = [h for e in pre for h in e.get("hooks") or []]
    assert theirs in hooks, pre
    assert not [h for h in hooks if fis._is_gate_hook(h)], pre


def test_uninstall_keeps_a_host_entry_it_only_emptied(tmp_path: Path):
    import scripts.flow_init_setup as fis

    settings = _planted(
        tmp_path, [{"matcher": "Read", "team_note": "ours", "hooks": [_gate_hook()]}]
    )
    fis.register_gate(tmp_path)
    fis.unregister_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert {"matcher": "Read", "team_note": "ours", "hooks": []} in pre, pre


def test_uninstall_drops_the_entry_it_wrote_itself(tmp_path: Path):
    import scripts.flow_init_setup as fis

    fis.register_gate(tmp_path)
    fis.unregister_gate(tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    assert json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"] == []


def test_a_gate_that_runs_more_than_once_says_so(tmp_path: Path):
    """Two gate hooks the host can reach are two gate runs per commit. Removing one would take
    a hook this plugin may not have written; not saying so reports a gate state that is not the
    one the host has."""
    import scripts.flow_init_setup as fis

    _planted(tmp_path, [{"matcher": "Bash", "hooks": [_gate_hook(), _gate_hook()]}])
    assert "2개" in fis.register_gate(tmp_path)


def test_moving_a_hook_is_written_even_when_the_gate_is_already_there(tmp_path: Path):
    """A move with nothing else to do still changes the file, so reporting it as a skip leaves
    the host with a gate hook under a matcher that does not fire and no record of it."""
    import scripts.flow_init_setup as fis

    settings = _planted(
        tmp_path,
        [
            {"matcher": "Bash", "hooks": [_gate_hook()]},
            {"matcher": "Read", "hooks": [_gate_hook()]},
        ],
    )
    out = fis.register_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert "skip" not in out and "1건" in out, out
    assert pre[1]["hooks"] == [], pre


def test_the_repair_count_covers_the_hooks_it_moved(tmp_path: Path):
    import scripts.flow_init_setup as fis

    # The path a release before the scripts/ subdirectory installed to. It still says
    # harness-tier, which is what separates this from a hook the host wrote.
    stale = dict(
        _gate_hook(),
        command='bash "${CLAUDE_PROJECT_DIR:-.}/.claude/harness-tier/precommit-runner.sh"',
    )
    _planted(
        tmp_path,
        [
            {"matcher": "Bash", "hooks": [stale]},
            {"matcher": "Read", "hooks": [_gate_hook()]},
        ],
    )
    assert "2건" in fis.register_gate(tmp_path)


def test_uninstall_keeps_the_keys_the_host_put_beside_the_gate(tmp_path: Path):
    """The entry carries the gate's own matcher, so only its key set says whether the host
    wrote anything into it."""
    import scripts.flow_init_setup as fis

    settings = _planted(
        tmp_path, [{"matcher": "Bash", "team_note": "ours", "hooks": [_gate_hook()]}]
    )
    fis.unregister_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert pre == [{"matcher": "Bash", "team_note": "ours", "hooks": []}], pre


def test_uninstall_keeps_a_host_entry_that_only_looks_like_the_gates(tmp_path: Path):
    """Same keys, same emptiness — the matcher is the only thing left that says whose entry it
    is, and dropping it here takes an entry the host wrote."""
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": "Read", "hooks": [_gate_hook()]}])
    fis.register_gate(tmp_path)
    fis.unregister_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert pre == [{"matcher": "Read", "hooks": []}], pre


def test_uninstall_with_no_gate_present_writes_nothing(tmp_path: Path):
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": "Bash", "hooks": [{"command": "theirs.sh"}]}])
    before = settings.read_text(encoding="utf-8")
    assert "skip" in fis.unregister_gate(tmp_path)
    assert settings.read_text(encoding="utf-8") == before


@pytest.mark.parametrize("label,payload", MALFORMED, ids=[label for label, _ in MALFORMED])
def test_setup_finishes_its_other_steps_on_a_settings_shape_it_cannot_use(
    tmp_path: Path, label: str, payload, monkeypatch, capsys
):
    """/flow-init prints each step's result unguarded, so one raise takes the marketplace
    registration, the pre-commit check, the .gitignore lines and every rendered workflow down
    with the gate — and a guard in the gate alone only moves the raise to the next step.

    Finishing is not succeeding, though: a gate that did not register is the install's whole
    point missing, and its one `[!]` scrolls past among forty other lines. So the last line and
    the exit code have to agree with the gate, whichever way it went."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text(json.dumps(payload), encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN))
    monkeypatch.setattr(sys, "argv", ["flow_init_setup.py"])
    code = 0
    try:
        fis.main()
    except SystemExit as exc:
        code = exc.code
    out = capsys.readouterr().out
    # Asked of the output, the question answers itself: a build that never prints the
    # line agrees with itself about there being nothing wrong. The host's file knows.
    registered = _gate_is_in(tmp_path / ".claude" / "settings.json")
    assert (code == 0) is registered, (label, code, out)
    assert ("기계적 셋업 완료" in out) is registered, (label, out)
    assert (tmp_path / ".gitignore").is_file()
    assert (tmp_path / ".claude" / "harness-tier" / "scripts" / "precommit-runner.sh").is_file()


def test_a_settings_file_that_is_not_utf8_is_reported(tmp_path: Path):
    """The host this gate was written for runs a cp949 console, so a settings.json with a
    Korean comment in the local code page is an ordinary file there, not a corrupt one."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_bytes('{"note": "한글"}'.encode("cp949"))
    assert "UTF-8" in fis.register_gate(tmp_path)
    assert "UTF-8" in fis.unregister_gate(tmp_path)


def test_a_settings_path_that_cannot_be_written_is_reported(tmp_path: Path):
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude" / "settings.json").mkdir(parents=True)
    out = fis.register_gate(tmp_path)
    assert out.startswith("  [!]"), out


def test_a_document_that_is_not_an_object_is_left_alone(tmp_path: Path):
    """Reported, not overwritten. The guard is only worth having if the file survives it."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text('["the host\'s own array-shaped config", {"keep": "me"}]', encoding="utf-8")
    before = settings.read_text(encoding="utf-8")
    assert fis.register_gate(tmp_path).startswith("  [!]")
    assert settings.read_text(encoding="utf-8") == before


def test_the_move_count_is_hooks_not_entries(tmp_path: Path):
    """One entry can hold several gate hooks, and the number the host reads has to be the
    number that moved."""
    import scripts.flow_init_setup as fis

    _planted(
        tmp_path,
        [{"matcher": "Read", "hooks": [_gate_hook(), _gate_hook(), _gate_hook()]}],
    )
    assert "3건" in fis.register_gate(tmp_path)


def test_a_stale_hook_under_an_undecidable_matcher_is_still_brought_forward(tmp_path: Path):
    """The entry stays as the host wrote it; the gate's own hook inside it does not, because
    a path this plugin no longer installs to is a hook that runs nothing."""
    import scripts.flow_init_setup as fis

    # The path a release before the scripts/ subdirectory installed to. It still says
    # harness-tier, which is what separates this from a hook the host wrote.
    stale = dict(
        _gate_hook(),
        command='bash "${CLAUDE_PROJECT_DIR:-.}/.claude/harness-tier/precommit-runner.sh"',
    )
    settings = _planted(tmp_path, [{"matcher": "^Bash$", "hooks": [stale]}])
    fis.register_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert pre[0]["matcher"] == "^Bash$", pre
    assert pre[0]["hooks"][0]["command"] == fis.GATE_COMMAND, pre


def test_a_hook_under_an_undecidable_matcher_is_reported_as_a_maybe(tmp_path: Path):
    """It may fire and it may not — saying it does is the same false statement about the
    host's configuration that reading the matcher wrongly makes."""
    import scripts.flow_init_setup as fis

    out = fis.register_gate(
        _host_with(tmp_path, [{"matcher": "^Notebook", "hooks": [_gate_hook()]}])
    )
    assert "판정할 수 없는" in out and "1개" in out, out
    assert "발화하는 게이트 훅" not in out, out


def _host_with(tmp_path: Path, entries: list) -> Path:
    _planted(tmp_path, entries)
    return tmp_path


def test_a_settings_file_that_cannot_be_read_is_reported(tmp_path: Path, monkeypatch):
    """The file exists and the read still fails — a lock, a permission, a device. Every other
    step of the setup runs after this one."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text("{}", encoding="utf-8")
    real = Path.read_text

    def refuse(self, *a, **kw):
        if self.name == "settings.json":
            raise OSError(13, "Permission denied")
        return real(self, *a, **kw)

    monkeypatch.setattr(Path, "read_text", refuse)
    assert "읽지 못했습니다" in fis.register_gate(tmp_path)
    assert "읽지 못했습니다" in fis.unregister_gate(tmp_path)


def test_a_settings_file_holding_null_is_an_empty_one(tmp_path: Path):
    """`null` parses, and it is not an object; read as one the gate refuses a file that says
    nothing at all rather than registering into it."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text("null", encoding="utf-8")
    assert "등록" in fis.register_gate(tmp_path)


def test_one_gate_hook_is_not_reported_as_several(tmp_path: Path):
    import scripts.flow_init_setup as fis

    assert "게이트 훅" not in fis.register_gate(tmp_path)
    assert "게이트 훅" not in fis.register_gate(tmp_path)


def test_the_undecided_note_counts_hooks_not_entries(tmp_path: Path):
    import scripts.flow_init_setup as fis

    _planted(tmp_path, [{"matcher": "^Bash$", "hooks": [_gate_hook(), _gate_hook()]}])
    out = fis.register_gate(tmp_path)
    assert "판정할 수 없는" in out and "2개" in out, out


def test_a_write_that_fails_leaves_the_host_file_as_it_was(tmp_path: Path):
    """Opening for writing truncates before it writes, so a failure partway through is the
    host's settings gone — and the report line would call that "could not write"."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash"]}}), encoding="utf-8")
    before = settings.read_text(encoding="utf-8")
    # A lone surrogate parses as JSON and encodes as nothing.
    settings.write_text(
        json.dumps({"permissions": {"allow": ["Bash"]}, "n": "\ud800"}), encoding="utf-8"
    )
    poisoned = settings.read_text(encoding="utf-8")
    out = fis.register_gate(tmp_path)
    assert out.startswith("  [!]"), out
    assert settings.read_text(encoding="utf-8") == poisoned
    assert before != poisoned
    assert not list((tmp_path / ".claude").glob("settings.json.*")), "the temporary file stayed"


def test_a_claude_directory_that_is_a_file_is_reported(tmp_path: Path):
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").write_text("not a directory", encoding="utf-8")
    assert fis.register_gate(tmp_path).startswith("  [!]")
    assert fis.unregister_gate(tmp_path).startswith("  [!]")
    assert fis.register_marketplace(tmp_path).startswith("  [!]")


def test_a_settings_file_too_deep_to_parse_is_reported(tmp_path: Path):
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text(
        "[" * 100000 + "]" * 100000, encoding="utf-8"
    )
    assert "파싱 실패" in fis.register_gate(tmp_path)


def test_the_undecided_note_counts_only_the_gates_own_hooks(tmp_path: Path):
    """The host's hooks under an undecidable matcher are the host's, and counting them as gate
    runs tells them their commit does something it does not."""
    import scripts.flow_init_setup as fis

    _planted(
        tmp_path,
        [{"matcher": "^Bash$", "hooks": [{"command": "my-audit.sh"}, {"command": "lint.sh"}]}],
    )
    out = fis.register_gate(tmp_path)
    assert "게이트 훅" not in out, out


def test_a_settings_file_the_host_keeps_as_a_link_is_written_through(tmp_path: Path):
    """A rename replaces the name, so the link became a plain file and the dotfiles copy the
    host manages kept the old content — which their next sync puts back, gate and
    all."""
    import scripts.flow_init_setup as fis

    managed = tmp_path / "dotfiles-settings.json"
    managed.write_text(json.dumps({"permissions": {"allow": ["Bash"]}}), encoding="utf-8")
    (tmp_path / ".claude").mkdir()
    link = tmp_path / ".claude" / "settings.json"
    try:
        link.symlink_to(managed)
    except OSError as exc:  # a host without the privilege to make one
        pytest.skip(str(exc))
    assert "등록" in fis.register_gate(tmp_path)
    assert link.is_symlink()
    assert _is_gate(_gate_commands(managed)[0])


def test_a_temporary_file_does_not_consume_one_the_host_already_had(tmp_path: Path):
    """The name beside settings.json was fixed, and whatever the host had there went with the
    rename."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    victim = tmp_path / ".claude" / "settings.json.harness-new"
    victim.write_text("the host wrote this", encoding="utf-8")
    fis.register_gate(tmp_path)
    assert victim.read_text(encoding="utf-8") == "the host wrote this"


@pytest.mark.parametrize("field", [{"if": "Bash(rm *)"}, {"async": True}, {"type": "prompt"}])
def test_a_gate_hook_the_host_switched_off_is_not_the_gate(tmp_path: Path, field: dict):
    """Each of these leaves the hook registered and firing on nothing: `if` suppresses it per
    build (Invariant 4), `async` puts it where it cannot deny, and another `type` runs
    something else. Reported as already registered, the commit gate is off in silence."""
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": "Bash", "hooks": [dict(_gate_hook(), **field)]}])
    assert "보정" in fis.register_gate(tmp_path)
    hook = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"][0]["hooks"][0]
    assert hook == fis.GATE_ENTRY["hooks"][0], hook


def test_a_hook_of_the_hosts_that_merely_shares_the_script_name_is_left_alone(tmp_path: Path):
    """`precommit-runner.sh` is a name a host writes for itself. Claimed as this gate's, theirs
    was rewritten to this path under a firing matcher and deleted under one that does not
    fire."""
    import scripts.flow_init_setup as fis

    theirs = {"type": "command", "command": "bash ./tools/precommit-runner.sh --their-flags"}
    for matcher in ("Bash", "Edit"):
        host = tmp_path / matcher
        settings = _planted(host, [{"matcher": matcher, "hooks": [dict(theirs)]}])
        fis.register_gate(host)
        cmds = _gate_commands(settings)
        assert theirs["command"] in cmds, (matcher, cmds)
        assert any(_is_gate(c) for c in cmds), (matcher, cmds)


@pytest.mark.parametrize("document", ["false", "0", '""', "[]", "0.0"])
def test_a_falsy_document_is_data_not_an_empty_one(tmp_path: Path, document: str):
    """`json.loads(...) or {}` ran before the shape check, so every falsy value reached the
    writer as an empty object and was overwritten under a clean registration line. `null`
    alone is the host's own spelling for nothing set yet."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text(document, encoding="utf-8")
    assert fis.register_gate(tmp_path).startswith("  [!]")
    assert settings.read_text(encoding="utf-8") == document


def test_a_settings_file_holding_only_null_still_takes_the_gate(tmp_path: Path):
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text("null", encoding="utf-8")
    assert "등록" in fis.register_gate(tmp_path)
    assert any(_is_gate(c) for c in _gate_commands(settings))


def test_hooks_turned_off_wholesale_is_said_out_loud(tmp_path: Path):
    """Registering into a settings.json that disables every hook reported a clean install of a
    gate that cannot run."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps({"disableAllHooks": True}), encoding="utf-8"
    )
    assert "disableAllHooks" in fis.register_gate(tmp_path)


def test_a_reason_survives_an_error_that_carries_no_strerror():
    import scripts.flow_init_setup as fis

    assert fis._why(OSError()) == "OSError"
    assert fis._why(ValueError("surrogates not allowed")) == "surrogates not allowed"
    assert fis._why(OSError(2, "no such file")) == "no such file"


def test_uninstall_leaves_a_hook_of_the_hosts_that_shares_the_script_name(tmp_path: Path):
    """The install side stopped claiming it; the removal side takes hooks by the same
    predicate, and a host hook deleted by an uninstall is gone for good."""
    import scripts.flow_init_setup as fis

    theirs = {"type": "command", "command": "bash ./tools/precommit-runner.sh --their-flags"}
    settings = _planted(tmp_path, [{"matcher": "Bash", "hooks": [dict(theirs), _gate_hook()]}])
    assert "해제" in fis.unregister_gate(tmp_path)
    cmds = _gate_commands(settings)
    assert cmds == [theirs["command"]], cmds


def test_the_mode_the_host_gave_settings_json_survives_a_write(tmp_path: Path):
    """A rename carries the temporary file's mode, and mkstemp makes one only its owner can
    read. On a build machine where another uid reads .claude/settings.json that is the config
    gone, and git tracks no mode but the exec bit, so nothing shows it."""
    import stat

    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash"]}}), encoding="utf-8")
    settings.chmod(0o644)
    before = stat.S_IMODE(settings.stat().st_mode)
    if before != 0o644:  # a host whose filesystem does not carry the bits
        pytest.skip(f"mode not honoured here: {before:o}")
    assert "등록" in fis.register_gate(tmp_path)
    assert stat.S_IMODE(settings.stat().st_mode) == before


def test_a_settings_file_the_host_locked_is_not_replaced(tmp_path: Path):
    """A rename asks the DIRECTORY for permission, not the file, so read-only stopped meaning
    anything the moment the write went through a temporary file."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash"]}}), encoding="utf-8")
    before = settings.read_text(encoding="utf-8")
    settings.chmod(0o444)
    try:
        if os.access(settings, os.W_OK):  # a host where the bit does not deny the owner
            pytest.skip("read-only is not enforced here")
        assert fis.register_gate(tmp_path).startswith("  [!]")
        assert settings.read_text(encoding="utf-8") == before
    finally:
        settings.chmod(0o644)


def test_the_temporary_file_is_made_beside_the_file_it_replaces(tmp_path: Path, monkeypatch):
    """A rename cannot cross a filesystem. Made anywhere but next to the target, the write
    fails on exactly the hosts that keep their project on another volume."""
    import scripts.flow_init_setup as fis

    seen = []
    real = fis.tempfile.mkstemp

    def spy(*args, **kwargs):
        seen.append(kwargs.get("dir"))
        return real(*args, **kwargs)

    monkeypatch.setattr(fis.tempfile, "mkstemp", spy)
    fis.register_gate(tmp_path)
    assert seen == [tmp_path / ".claude"], seen


@pytest.mark.parametrize(
    "failure",
    [
        PermissionError(13, "Permission denied"),
        OSError(28, "No space left on device"),
        OSError(122, "Disk quota exceeded"),
    ],
    ids=["no permission", "full disk", "over quota"],
)
def test_a_write_that_cannot_make_a_temporary_file_leaves_the_host_alone(
    tmp_path: Path, monkeypatch, failure
):
    """Writing in place instead would be the truncation the temporary file exists to prevent,
    and `mkstemp` fails for more than a directory it may not write — a full disk and exhausted
    inodes reach the same call, with the host's own file perfectly writable."""
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": "Read", "hooks": []}])
    before = settings.read_bytes()

    def refuse(*_args, **_kwargs):
        raise failure

    monkeypatch.setattr(fis.tempfile, "mkstemp", refuse)
    assert fis.register_gate(tmp_path).startswith("  [!]")
    assert settings.read_bytes() == before
    assert not list((tmp_path / ".claude").glob("settings.json.*"))


def test_hooks_turned_off_wholesale_is_not_a_finished_setup(tmp_path: Path, monkeypatch, capsys):
    """It is the one input that says outright the gate will never fire, and it was the one
    that ended `기계적 셋업 완료.` with exit 0."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text(
        json.dumps({"disableAllHooks": True}), encoding="utf-8"
    )
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN))
    monkeypatch.setattr(sys, "argv", ["flow_init_setup.py"])
    with pytest.raises(SystemExit) as raised:
        fis.main()
    assert raised.value.code == 1
    out = capsys.readouterr().out
    assert "기계적 셋업 완료" not in out
    assert "disableAllHooks" in out


def test_an_uninstall_that_leaves_the_hook_behind_says_so(tmp_path: Path, monkeypatch, capsys):
    """The scripts the hook names are deleted by the same run, so a settings.json it could not
    write leaves every Bash command in that host running a file that is not there."""
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": "Bash", "hooks": [_gate_hook()]}])
    settings.chmod(0o444)
    try:
        if os.access(settings, os.W_OK):  # a host where the bit does not deny the owner
            pytest.skip("read-only is not enforced here")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN))
        monkeypatch.setattr(sys, "argv", ["flow_init_setup.py", "--uninstall"])
        with pytest.raises(SystemExit) as raised:
            fis.main()
        assert raised.value.code == 1
        out = capsys.readouterr().out
        assert "정리 완료" not in out
        assert "남았습니다" in out
        assert any(_is_gate(c) for c in _gate_commands(settings))
    finally:
        settings.chmod(0o644)


def test_the_access_entries_and_owner_are_carried_over(tmp_path: Path, monkeypatch):
    """Neither survives a rename, and neither shows up in a diff — `st_mode` reports the ACL
    MASK in its group bits, so putting that back as a plain mode is what gave group write to a
    file whose owner had granted one named user, and the new inode is the writer's own. The
    host running Windows has no way to observe either, so what is held here is that the calls
    are made with the values that were read."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text(json.dumps({"permissions": {"allow": ["Bash"]}}), encoding="utf-8")
    entries = b"entries the host set"
    chowned, xattred = [], []
    monkeypatch.setattr(fis, "_access_entries", lambda _p: entries)
    monkeypatch.setattr(
        fis.os, "setxattr", lambda p, name, value: xattred.append((name, value)), raising=False
    )
    monkeypatch.setattr(fis.os, "getuid", lambda: 4242, raising=False)
    monkeypatch.setattr(fis.os, "getgid", lambda: 4242, raising=False)
    monkeypatch.setattr(
        fis.os, "chown", lambda p, uid, gid: chowned.append((uid, gid)), raising=False
    )
    before = settings.stat()
    assert "등록" in fis.register_gate(tmp_path)
    assert xattred == [(fis._ACCESS_ENTRIES, entries)], xattred
    assert chowned == [(before.st_uid, before.st_gid)], chowned


def test_a_marketplace_write_that_fails_is_reported(tmp_path: Path, monkeypatch):
    """Every step that writes settings.json has to say so — the setup's verdict reads the
    file, but the step's own line is what names the failing write."""
    import scripts.flow_init_setup as fis

    _planted(tmp_path, [{"matcher": "Bash", "hooks": [_gate_hook()]}])

    def refuse(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(fis.tempfile, "mkstemp", refuse)
    assert fis.register_marketplace(tmp_path).startswith("  [!]")


def test_a_gate_that_is_there_and_firing_is_a_finished_setup(tmp_path: Path, monkeypatch, capsys):
    """The registration line said something was wrong — a gate hook it wanted to move out of a
    non-firing entry, and a settings.json it could not write to do it. The gate itself was
    registered and firing the whole time, and the setup's verdict is about the gate."""
    import scripts.flow_init_setup as fis

    settings = _planted(
        tmp_path,
        [
            {"matcher": "Bash", "hooks": [_gate_hook()]},
            {"matcher": "Read", "hooks": [_gate_hook()]},
        ],
    )
    settings.chmod(0o444)
    try:
        if os.access(settings, os.W_OK):  # a host where the bit does not deny the owner
            pytest.skip("read-only is not enforced here")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN))
        monkeypatch.setattr(sys, "argv", ["flow_init_setup.py"])
        fis.main()
        out = capsys.readouterr().out
        assert "기계적 셋업 완료" in out
        assert "커밋 게이트가 settings.json 에 없습니다" not in out
    finally:
        settings.chmod(0o644)


@pytest.mark.parametrize(
    "raw",
    ['{"a": 1,,}', "settings".encode("cp949").decode("latin-1"), '["a host array"]'],
    ids=["unparseable", "not utf-8", "not an object"],
)
def test_an_uninstall_that_cannot_read_settings_says_the_hook_may_remain(
    tmp_path: Path, monkeypatch, capsys, raw: str
):
    """A file it cannot read is one it cannot clear, and the same run has already deleted the
    scripts the hook names. `정리 완료.` over that is the lie this verdict exists to stop, and
    the cp949 spelling is the host this gate was written for (Invariant 2)."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text(raw, encoding="latin-1")
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN))
    monkeypatch.setattr(sys, "argv", ["flow_init_setup.py", "--uninstall"])
    with pytest.raises(SystemExit) as raised:
        fis.main()
    assert raised.value.code == 1
    out = capsys.readouterr().out
    assert "남았습니다" in out
    assert "정리 완료" not in out


def test_an_uninstall_prints_the_follow_ups_it_is_quoted_for(tmp_path: Path, capsys):
    """`/flow-uninstall` sends the user to "the manual follow-ups the script prints", and the
    only instruction for turning off a git hook that now names a deleted script is in them."""
    import scripts.flow_init_setup as fis

    _planted(tmp_path, [{"matcher": "Bash", "hooks": [_gate_hook()]}])
    assert fis.run_uninstall(tmp_path) is True
    out = capsys.readouterr().out
    assert "pre-commit uninstall" in out
    assert "정리 완료." in out


def test_a_gate_hook_under_a_matcher_that_does_not_fire_is_not_a_gate(
    tmp_path: Path, monkeypatch, capsys
):
    """The hook is in the file, so asking only whether one is there says the setup finished.
    It fires on `Read`, and a commit arrives through Bash — and the settings.json this would
    normally move it out of cannot be written."""
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": "Read", "hooks": [_gate_hook()]}])
    settings.chmod(0o444)
    try:
        if os.access(settings, os.W_OK):  # a host where the bit does not deny the owner
            pytest.skip("read-only is not enforced here")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN))
        monkeypatch.setattr(sys, "argv", ["flow_init_setup.py"])
        with pytest.raises(SystemExit) as raised:
            fis.main()
        assert raised.value.code == 1
        out = capsys.readouterr().out
        assert "커밋 게이트가 settings.json 에 없습니다" in out
        assert "기계적 셋업 완료" not in out
        assert any(_is_gate(c) for c in _gate_commands(settings)), "the hook is still there"
    finally:
        settings.chmod(0o644)


@pytest.mark.parametrize(
    "field", [{"if": "Bash(git commit:*)"}, {"async": True}, {"type": "prompt"}]
)
def test_a_gate_hook_the_repair_could_not_reach_is_not_a_finished_setup(
    tmp_path: Path, monkeypatch, capsys, field: dict
):
    """The repair that takes an `if` back off the gate hook lands only when the write lands.
    Asked whether A gate hook is under a firing matcher, a settings.json that could not be
    written reports a finished setup over a hook that fires on nothing (Invariant 4)."""
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": "Bash", "hooks": [dict(_gate_hook(), **field)]}])
    settings.chmod(0o444)
    try:
        if os.access(settings, os.W_OK):  # a host where the bit does not deny the owner
            pytest.skip("read-only is not enforced here")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN))
        monkeypatch.setattr(sys, "argv", ["flow_init_setup.py"])
        with pytest.raises(SystemExit) as raised:
            fis.main()
        assert raised.value.code == 1
        assert "기계적 셋업 완료" not in capsys.readouterr().out
    finally:
        settings.chmod(0o644)


def test_a_matcher_this_cannot_decide_is_not_a_missing_gate(tmp_path: Path, monkeypatch, capsys):
    """`^Bash$` fires. Read as a matcher that does not, a host who anchored it on purpose is
    told the gate is missing and sent to fix what is not broken."""
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": "^Bash$", "hooks": [_gate_hook()]}])
    settings.chmod(0o444)
    try:
        if os.access(settings, os.W_OK):
            pytest.skip("read-only is not enforced here")
        monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
        monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN))
        monkeypatch.setattr(sys, "argv", ["flow_init_setup.py"])
        fis.main()
        assert "기계적 셋업 완료" in capsys.readouterr().out
    finally:
        settings.chmod(0o644)


def test_a_settings_file_this_creates_is_as_open_as_the_umask_allows(tmp_path: Path):
    """`mkstemp` makes a file only its owner can read and a rename carries that, so the
    commonest path of all — a first install — left a settings.json the session's own uid may
    not be able to read. It is the failure this writer's docstring names."""
    import stat

    import scripts.flow_init_setup as fis

    assert "등록" in fis.register_gate(tmp_path)
    settings = tmp_path / ".claude" / "settings.json"
    mode = stat.S_IMODE(settings.stat().st_mode)
    mask = os.umask(0)
    os.umask(mask)
    if 0o666 & ~mask == 0o666:  # a host whose filesystem does not carry the bits
        pytest.skip(f"mode not honoured here: {mode:o}")
    assert mode == 0o666 & ~mask, oct(mode)


def test_a_claude_directory_that_cannot_be_entered_is_reported(tmp_path: Path):
    """`Path.is_file()` does not swallow a permission error, so the line after the guarded
    mkdir takes the script down where the guard was added — and the copy that runs
    first did the same, taking the workflows and the .gitignore with it."""
    import scripts.flow_init_setup as fis

    closed = tmp_path / ".claude"
    closed.mkdir()
    closed.chmod(0o000)
    try:
        if os.access(closed, os.R_OK):  # a host where the bits do not deny the owner
            pytest.skip("a closed directory is not enforced here")
        assert fis.register_gate(tmp_path).startswith("  [!]")
        assert fis.copy_artifacts(PLUGIN, tmp_path)[0].startswith("  [!]")
    finally:
        closed.chmod(0o755)


def _acl_blob(uid: int) -> bytes:
    """One POSIX access list, in the layout the kernel stores: a version word, then a tag,
    permission bits and an id per entry, ordered by tag. It has to be a real one — the blob
    a mode this test sets must not be refused as malformed, which would skip the test on
    Linux and leave
    the reader it exists to hold unheld on Windows too."""
    undefined = 0xFFFFFFFF
    out = struct.pack("<I", 2)
    for tag, perm, ident in (
        (0x01, 6, undefined),  # the owner
        (0x02, 6, uid),  # one named user — what a plain mode cannot carry
        (0x04, 4, undefined),  # the owning group
        (0x10, 6, undefined),  # the mask `st_mode` reports as group bits
        (0x20, 0, undefined),  # everyone else
    ):
        out += struct.pack("<HHI", tag, perm, ident)
    return out


def _set_acl(path: Path) -> bytes:
    """Put one on the file, or say why this host cannot hold the test."""
    if not hasattr(os, "setxattr"):
        pytest.skip("no extended attributes here")
    acl = _acl_blob(65534)  # nobody
    try:
        os.setxattr(path, ACCESS_ENTRIES, acl)
    except OSError as exc:  # a filesystem that will not take one
        pytest.skip(str(exc))
    return acl


def test_the_access_entries_are_read_from_the_file_itself(tmp_path: Path):
    """The carry-over test replaces this function, so nothing ran it — an xattr name spelled
    wrong, or a reader that always answers None, left the suite green."""
    import scripts.flow_init_setup as fis

    assert fis._ACCESS_ENTRIES == ACCESS_ENTRIES
    plain = tmp_path / "plain.json"
    plain.write_text("{}", encoding="utf-8")
    assert fis._access_entries(plain) is None  # nothing set, and nothing raised
    acl = _set_acl(plain)
    assert fis._access_entries(plain) == acl


def test_a_named_user_entry_survives_the_write(tmp_path: Path):
    """What the carry-over is for, asked of the file rather than of the calls: a rename
    lands a new inode, and the entry granting one named user is the part no mode can put
    back. The host running Windows skips this; the CI running Linux does not."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text("{}", encoding="utf-8")
    acl = _set_acl(settings)
    assert "등록" in fis.register_gate(tmp_path)
    assert os.getxattr(settings, ACCESS_ENTRIES) == acl


def test_an_uninstall_write_that_fails_is_reported(tmp_path: Path, monkeypatch):
    """Every step that writes settings.json says so. The removal side dropped its result while
    the two beside it kept theirs."""
    import scripts.flow_init_setup as fis

    _planted(tmp_path, [{"matcher": "Bash", "hooks": [_gate_hook()]}])

    def refuse(*_args, **_kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(fis.tempfile, "mkstemp", refuse)
    assert fis.unregister_gate(tmp_path).startswith("  [!]")


def test_the_gate_command_resolves_against_the_host():
    """The hook runs wherever Claude Code's shell happens to be, so the path has to be the
    host's own — spelled relative it names whatever directory the session sat in."""
    import scripts.flow_init_setup as fis

    assert "${CLAUDE_PROJECT_DIR:-.}/" in fis.GATE_COMMAND, fis.GATE_COMMAND
    assert fis.GATE_ENTRY["hooks"][0]["command"] == fis.GATE_COMMAND


def test_every_file_the_gate_needs_is_one_a_finished_setup_leaves(tmp_path: Path, capsys):
    """The verdict asks the host for these by name, so a rename on one side and not the
    other is a setup that reports a gate it failed to install — or one that cries
    wolf over a gate that is fine."""
    import scripts.flow_init_setup as fis

    assert fis.run_setup(tmp_path, PLUGIN) is True
    assert "기계적 셋업 완료." in capsys.readouterr().out
    for rel, source in fis.GATE_FILES:
        assert (tmp_path / rel).read_bytes() == (PLUGIN / source).read_bytes(), rel


def test_a_gate_whose_scripts_did_not_land_is_not_a_finished_setup(
    tmp_path: Path, monkeypatch, capsys
):
    """The hook is a line of text naming a file. Registering it over a host the copy step
    could not write leaves `bash` answering 127 to every command — never the exit 2 that
    denies a commit — and the run said `기계적 셋업 완료.` over it, so the host believed
    every commit was gated while none was."""
    import scripts.flow_init_setup as fis

    real = fis.shutil.copyfile

    def refuse(src, dst, *args, **kwargs):
        if Path(dst).name == "precommit-runner.sh":
            raise PermissionError(13, "Permission denied")
        return real(src, dst, *args, **kwargs)

    monkeypatch.setattr(fis.shutil, "copyfile", refuse)
    assert fis.run_setup(tmp_path, PLUGIN) is False
    out = capsys.readouterr().out
    assert "복사 실패" in out, out
    assert "커밋 게이트가 쓰는 파일이 호스트에 없거나 손상됐습니다" in out, out
    assert "precommit-runner.sh" in out, out
    assert "기계적 셋업 완료." not in out, out
    # …and the one file it could not copy is the only one it gave up on.
    assert (tmp_path / ".claude/harness-tier/scripts/flow_gate_check.py").is_file()


def test_a_step_that_cannot_finish_still_reaches_the_verdict(tmp_path: Path, monkeypatch, capsys):
    """A step reports the trouble it went looking for, and raises out of the rest. The verdict
    is the line the caller came for, so no step may end the run before it."""
    import scripts.flow_init_setup as fis

    def refuse(*_args, **_kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(fis, "render_workflow", refuse)
    assert fis.run_setup(tmp_path, PLUGIN) is True
    out = capsys.readouterr().out
    assert "이 단계를 끝내지 못했습니다" in out, out
    # The gate is on, so the answer is True — but the word 완료 alone would hide the
    # step that did not finish, which is the same lie in small.
    assert "끝내지 못한 단계가 있습니다" in out, out
    assert "기계적 셋업 완료." not in out, out


def test_a_closed_claude_directory_does_not_end_the_run(tmp_path: Path, capsys):
    """The guarded `mkdir` was one of several probes under that directory, and the next
    unguarded one raised — `load_contract_config` asks `is_file()` of a path inside it.
    The run died there, before the verdict that says whether the gate is on."""
    import scripts.flow_init_setup as fis

    closed = tmp_path / ".claude"
    closed.mkdir()
    closed.chmod(0o000)
    try:
        if os.access(closed, os.R_OK):  # a host where the bits do not deny the owner
            pytest.skip("a closed directory is not enforced here")
        assert fis.run_setup(tmp_path, PLUGIN) is False
    finally:
        closed.chmod(0o755)
    out = capsys.readouterr().out
    assert "이 단계를 끝내지 못했습니다" in out, out
    assert "커밋 게이트가 쓰는 파일이 호스트에 없거나 손상됐습니다" in out, out


def test_a_policy_that_did_not_land_is_not_a_finished_setup(tmp_path: Path, monkeypatch, capsys):
    """Without `flow-tiers.yaml` nothing parses, so the tier of a commit cannot be read and
    the unclassified-commit deny — one of the three things this gate may never fail open on —
    never fires. Measured through the runner itself: exit 0 on `git commit -m x` with no
    policy, exit 2 once it is put back. A copy failure is a report rather than a raise,
    and the run then called itself finished over a gate that denies nothing."""
    import scripts.flow_init_setup as fis

    real = fis.shutil.copyfile

    def refuse(src, dst, *args, **kwargs):
        if Path(dst).name == fis.TIERS_FILENAME:
            raise PermissionError(13, "Permission denied")
        return real(src, dst, *args, **kwargs)

    monkeypatch.setattr(fis.shutil, "copyfile", refuse)
    assert fis.run_setup(tmp_path, PLUGIN) is False
    out = capsys.readouterr().out
    assert "복사 실패" in out, out
    assert "커밋 게이트가 쓰는 파일이 호스트에 없거나 손상됐습니다" in out, out
    assert fis.TIERS_FILENAME in out, out
    assert "기계적 셋업 완료" not in out, out


def test_the_config_directory_is_made_with_no_policy_source(tmp_path: Path):
    """`/flow-init` puts the host's own flow-config beside the policy, so the directory is
    not the policy's to withhold — guarding the copy had made the source's absence skip the
    `mkdir` that ran unconditionally before."""
    import scripts.flow_init_setup as fis

    plugin = tmp_path / "plugin"
    (plugin / "scripts").mkdir(parents=True)
    host = tmp_path / "host"
    host.mkdir()
    fis.copy_artifacts(plugin, host)
    assert (host / fis.CONFIG_DIR).is_dir()


def test_an_uninstall_step_that_cannot_finish_still_reaches_the_verdict(
    tmp_path: Path, monkeypatch, capsys
):
    """The setup half got the wrapper and this one did not, so a `.claude` the host closed
    ended the run before the line saying the hook was left behind — pointing at scripts this
    same run had already deleted."""
    import scripts.flow_init_setup as fis

    _planted(tmp_path, [{"matcher": "Bash", "hooks": [_gate_hook()]}])

    def refuse(*_args, **_kwargs):
        raise PermissionError(13, "Permission denied")

    monkeypatch.setattr(fis, "remove_harness_dir", refuse)
    assert fis.run_uninstall(tmp_path) is True
    out = capsys.readouterr().out
    assert "이 단계를 끝내지 못했습니다" in out, out
    # The hook is gone, so the answer is True — but the directory the step could not
    # delete is still there, and `정리 완료.` alone says otherwise.
    assert "끝내지 못한 단계가 있습니다" in out, out
    assert "정리 완료." not in out, out


def test_the_files_the_gate_needs_are_named_exactly():
    """Spelled out rather than read off the constant, because a test that iterates the list
    cannot notice an entry LEAVING it — and each of these, removed from a host, was measured
    to make the runner exit 0 on a real commit."""
    import scripts.flow_init_setup as fis

    assert {Path(rel).name for rel, _source in fis.GATE_FILES} == {
        "precommit-runner.sh",
        "flow_gate_check.py",
        "_harness_paths.py",
        "flow-tiers.yaml",
    }


@pytest.mark.parametrize(
    "rel",
    [
        ".claude/harness-tier/scripts/precommit-runner.sh",
        ".claude/harness-tier/scripts/flow_gate_check.py",
        ".claude/harness-tier/scripts/_harness_paths.py",
        ".claude/harness-tier/config/flow-tiers.yaml",
    ],
)
def test_a_gate_file_that_landed_corrupt_is_not_a_finished_setup(tmp_path: Path, rel: str):
    """A copy that fails after creating or truncating the destination leaves the name, so
    asking whether the file is THERE answered yes over an empty one — `bash` exits 0 on it
    and PyYAML reads it as nothing, and the gate that called itself installed denied no
    commit. A partial write is the same case, which is why the host copy is compared."""
    import scripts.flow_init_setup as fis

    assert fis.run_setup(tmp_path, PLUGIN) is True
    assert fis._gate_problems(tmp_path, PLUGIN) == []
    (tmp_path / rel).write_bytes(b"")
    problems = fis._gate_problems(tmp_path, PLUGIN)
    assert problems and Path(rel).name in problems[0], (rel, problems)


def test_a_host_config_whose_shape_is_wrong_does_not_end_the_run(tmp_path: Path, capsys):
    """`flow-config.yaml` is a file a person edits, so a list or a scalar at its top is a
    spelling mistake rather than an impossibility — and read as a mapping it raised past
    the step wrapper, six steps before the verdict, with a traceback."""
    import scripts.flow_init_setup as fis

    cfg = fis.config_path(tmp_path)
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text("- a" + chr(10) + "- b" + chr(10), encoding="utf-8")
    assert fis.run_setup(tmp_path, PLUGIN) is True
    assert "기계적 셋업 완료" in capsys.readouterr().out


def test_a_pre_commit_config_whose_shape_is_wrong_is_reported(tmp_path: Path):
    """The same hand-edit, in the file the hygiene layer owns: read as a mapping it took
    the run down instead of reporting a line."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".pre-commit-config.yaml").write_text("- a" + chr(10), encoding="utf-8")
    lines = fis.check_precommit(PLUGIN, tmp_path)
    assert lines and lines[0].startswith("  [!]"), lines


def test_doc_style_check_is_copied_to_the_host():
    # The rendered workflow runs .claude/harness-tier/scripts/doc_style_check.py, and its own
    # `[ ! -f ]` guard exits 0 when it is absent — so a name that drifts out of COPY_FILES
    # leaves a job that is green forever and verifies nothing.
    from scripts.flow_init_setup import COPY_FILES

    assert "scripts/doc_style_check.py" in COPY_FILES


def test_run_setup_renders_doc_style(tmp_path: Path, capsys):
    run_setup(tmp_path, PLUGIN)
    dest = tmp_path / ".github" / "workflows" / "doc-style.yml"
    assert dest.is_file()
    assert "doc-style" in capsys.readouterr().out
    # The guard the membership test above protects, read back from what was rendered.
    assert "doc_style_check.py" in dest.read_text(encoding="utf-8")


def _is_type_checking(test) -> bool:
    """`if TYPE_CHECKING:` exactly — the one test whose body python never runs.

    A substring search over the dumped node also exempts `if not TYPE_CHECKING:` and
    `if x == "TYPE_CHECKING":`, whose bodies DO run.
    """
    import ast

    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _runtime_builtin_generics(source: str) -> list[int]:
    """Line numbers where a builtin generic is subscripted somewhere python evaluates it.

    Everything under an annotation is exempt (`from __future__ import annotations` makes those
    strings), and so is an `if TYPE_CHECKING:` body, which never runs. What is left — a type
    alias, a default argument, a class attribute, a `try:` body at module level, a call inside
    a function — is evaluated for real and needs python 3.9.
    """
    import ast

    tree = ast.parse(source)
    exempt: set[int] = set()
    for node in ast.walk(tree):
        deferred = [
            getattr(node, "annotation", None),
            getattr(node, "returns", None),
        ]
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            deferred += node.body
        for sub in (d for d in deferred if d is not None):
            exempt.update(id(n) for n in ast.walk(sub))
    builtins_ = {"list", "dict", "set", "tuple", "frozenset", "type"}
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id in builtins_
        and id(node) not in exempt
    )


def test_copied_scripts_carry_no_runtime_builtin_generic():
    """Every script the host runs has to import under python 3.8 (Invariant #1, Exception 1).

    A TypeError raised while importing one aborts whichever gate script imported it, and a gate
    that never runs blocks nothing — including the unclassified commit it exists to catch.
    """
    from scripts.flow_init_setup import COPY_FILES

    offenders = [
        f"{rel}:{line}"
        for rel in COPY_FILES
        if rel.endswith(".py")
        for line in _runtime_builtin_generics((PLUGIN / rel).read_text(encoding="utf-8"))
    ]
    assert offenders == []


@pytest.mark.parametrize(
    "source",
    [
        "Finding = tuple[str, int]\n",
        "try:\n    Finding = tuple[str, int]\nexcept TypeError:\n    pass\n",
        "class C:\n    Finding = tuple[str, int]\n",
        "def f(x=list[int]()):\n    pass\n",
        "def f():\n    return dict[str, int]()\n",
        "tuple[int]\n",
        "from typing import TYPE_CHECKING\nif not TYPE_CHECKING:\n    F = tuple[str]\n",
        'if x == "TYPE_CHECKING":\n    F = tuple[str]\n',
        "if TYPE_CHECKING_OFF:\n    F = tuple[str]\n",
    ],
)
def test_the_38_guard_sees_every_place_python_evaluates_one(source: str):
    # A guard that only reads module-level assignments passes five of these six.
    assert _runtime_builtin_generics(source)


@pytest.mark.parametrize(
    "source",
    [
        "def f(x: list[int]) -> dict[str, int]:\n    pass\n",
        "x: tuple[int, str]\n",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    F = tuple[str, int]\n",
    ],
)
def test_the_38_guard_exempts_what_python_never_evaluates(source: str):
    assert _runtime_builtin_generics(source) == []
