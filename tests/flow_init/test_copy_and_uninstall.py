import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.flow_init_setup import (
    CLAUDE_MD_BEGIN,
    GITIGNORE_LINES,
    RULES_DEST,
    append_gitignore,
    check_precommit,
    copy_artifacts,
    register_gate,
    register_marketplace,
    remove_claude_md_block,
    remove_gitignore_lines,
    remove_harness_dir,
    remove_rules,
    run_setup,
    run_uninstall,
    unregister_gate,
    unregister_marketplace,
)
from tests.flow_init._helpers import PLUGIN, _gate_commands, _is_gate


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

    assert not (tmp_path / ".claude" / "settings.json").exists()
    gi = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert [line for line in GITIGNORE_LINES if line in gi] == [".teams-webhooks.local.json"]
    assert not vd.exists()


def test_uninstall_idempotent(tmp_path: Path):
    # when nothing exists, uninstall safely skips
    assert "skip" in unregister_gate(tmp_path)
    assert "skip" in unregister_marketplace(tmp_path)
    assert "skip" in remove_gitignore_lines(tmp_path)
    assert "skip" in remove_harness_dir(tmp_path)


def _workflow(host: Path, name: str, body: str) -> None:
    wf = host / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    (wf / name).write_text(body, encoding="utf-8")


@pytest.mark.parametrize(
    "tool",
    ["cargo-release", "semantic-release", "python-semantic-release", "gitversion", "jreleaser"],
)
def test_uninstall_names_a_release_workflow_that_calls_the_deleted_scripts(
    tmp_path: Path, capsys, tool
):
    """Every release render calls bump_version.py from the directory this run deletes, so the
    release.yml in the host is what the guidance has to name — whichever tool rendered it."""
    template = (PLUGIN / "github" / f"release.{tool}.workflow.example.yml").read_text(
        encoding="utf-8"
    )
    _workflow(tmp_path, "release.yml", template)
    run_uninstall(tmp_path)
    out = capsys.readouterr().out
    broken = next(ln for ln in out.splitlines() if "release.yml" in ln)
    assert "실패" in broken, out


def test_uninstall_tells_a_guarded_check_from_a_failing_one(tmp_path: Path, capsys):
    _workflow(tmp_path, "wiki-verify.yml", "run: python3 .claude/harness-tier/scripts/x.py\n")
    _workflow(tmp_path, "release.yml", "run: python3 .claude/harness-tier/scripts/y.py\n")
    run_uninstall(tmp_path)
    lines = capsys.readouterr().out.splitlines()
    guarded = next(ln for ln in lines if "wiki-verify.yml" in ln)
    assert "release.yml" not in guarded and "exit 0" in guarded, lines


def test_uninstall_names_the_rendered_workflows_that_keep_running(tmp_path: Path, capsys):
    """A self-contained render references nothing this run deletes, so it keeps spending a
    runner on every push; a workflow of the host's own is none of this run's business."""
    for name in ("branch-naming.yml", "entropy-check.yml", "unit-test.yml", "deploy-pypi.yml"):
        _workflow(tmp_path, name, "on: push\n")
    _workflow(tmp_path, "ci.yml", "on: push\n")
    run_uninstall(tmp_path)
    out = capsys.readouterr().out
    keeps = next(ln for ln in out.splitlines() if "branch-naming.yml" in ln)
    for name in ("entropy-check.yml", "unit-test.yml", "deploy-pypi.yml"):
        assert name in keeps, out
    assert "ci.yml" not in out


def test_uninstall_still_reaches_its_verdict_when_the_workflow_listing_raises(
    tmp_path: Path, capsys, monkeypatch
):
    import scripts.flow_init_setup as fis

    def boom(_host):
        raise RuntimeError("unreadable")

    monkeypatch.setattr(fis, "report_workflows", boom)
    assert fis.run_uninstall(tmp_path) is True
    out = capsys.readouterr().out
    assert "워크플로를 직접 확인" in out and "정리 완료." in out


def test_uninstall_reads_an_uppercase_workflow_extension(tmp_path: Path, capsys):
    _workflow(tmp_path, "release.YML", "run: python3 .claude/harness-tier/scripts/y.py\n")
    run_uninstall(tmp_path)
    assert "release.YML" in capsys.readouterr().out


def test_an_emptied_settings_file_that_cannot_be_deleted_is_reported(tmp_path: Path, monkeypatch):
    register_gate(tmp_path)

    def refuse(self, *_args, **_kwargs):
        raise OSError(13, "Permission denied")

    monkeypatch.setattr(Path, "unlink", refuse)
    assert unregister_gate(tmp_path).startswith("  [!] settings.json 삭제 실패")


def test_uninstall_names_no_workflow_when_the_host_has_none(tmp_path: Path, capsys):
    run_uninstall(tmp_path)
    assert ".yml" not in capsys.readouterr().out


def test_uninstall_keeps_the_ignore_line_that_guards_the_webhook_secret(tmp_path: Path):
    """The bare webhook pattern matches at any depth, so it may guard a secret outside the
    directory this run deletes — and the host may have had it before /flow-init did."""
    (tmp_path / ".gitignore").write_text(".teams-webhooks.local.json\nnode_modules/\n")
    append_gitignore(tmp_path)
    report = remove_gitignore_lines(tmp_path)
    gi = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert gi == [".teams-webhooks.local.json", "node_modules/"], gi
    assert ".teams-webhooks.local.json" in report


def test_uninstall_says_it_deletes_the_design_templates(tmp_path: Path):
    """The seeded templates are the host's to edit; deleting them unannounced loses the edits."""
    templates = tmp_path / ".claude" / "harness-tier" / "templates" / "design-docs"
    templates.mkdir(parents=True)
    (templates / "sds.template.md").write_text("edited\n", encoding="utf-8")
    assert "템플릿" in remove_harness_dir(tmp_path)


def test_uninstall_deletes_the_settings_file_it_emptied(tmp_path: Path):
    register_gate(tmp_path)
    register_marketplace(tmp_path)
    unregister_gate(tmp_path)
    assert "삭제" in unregister_marketplace(tmp_path)
    assert not (tmp_path / ".claude" / "settings.json").exists()


def test_uninstall_leaves_only_the_hosts_own_settings(tmp_path: Path):
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    settings.write_text(json.dumps({"model": "opus"}), encoding="utf-8")
    register_gate(tmp_path)
    register_marketplace(tmp_path)
    unregister_gate(tmp_path)
    unregister_marketplace(tmp_path)
    assert json.loads(settings.read_text(encoding="utf-8")) == {"model": "opus"}


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


def test_a_gate_script_that_did_not_copy_withholds_the_policy(tmp_path: Path, monkeypatch):
    """A new policy over an older module is the one pairing that fails CLOSED: the check asks
    for evidence the module cannot produce and denies every commit in every tier, with a reason
    no `/flow` step satisfies. The reverse pairing only under-gates, so the copy that survives
    a partial run is the module's, never the policy's."""
    real = shutil.copyfile

    def refuse_the_paths_module(src, dst, *args, **kwargs):
        if Path(src).name == "_harness_paths.py":
            raise OSError(13, "held open by the host")
        return real(src, dst, *args, **kwargs)

    monkeypatch.setattr(shutil, "copyfile", refuse_the_paths_module)
    report = copy_artifacts(PLUGIN, tmp_path)
    harness = tmp_path / ".claude" / "harness-tier"
    assert not (harness / "config" / "flow-tiers.yaml").exists()
    assert any("보류" in line for line in report)
    # The directory still gets made — the host's own flow-config lands beside it either way.
    assert (harness / "config").is_dir()


def test_a_non_gate_script_that_did_not_copy_still_lets_the_policy_land(
    tmp_path: Path, monkeypatch
):
    """Only the gate's own three withhold it. Withholding on any failure would turn a missing
    notifier into the fail-closed state this exists to prevent."""
    real = shutil.copyfile

    def refuse_the_notifier(src, dst, *args, **kwargs):
        if Path(src).name == "teams_alert.py":
            raise OSError(13, "held open by the host")
        return real(src, dst, *args, **kwargs)

    monkeypatch.setattr(shutil, "copyfile", refuse_the_notifier)
    copy_artifacts(PLUGIN, tmp_path)
    assert (tmp_path / ".claude" / "harness-tier" / "config" / "flow-tiers.yaml").is_file()


def test_a_step_that_raises_anything_still_reaches_the_verdict():
    """The verdict line is the only thing saying whether the gate is on, and a caller reads the
    exit code as that answer. A hand-edited config of the wrong shape raises AttributeError deep
    in a step, so catching only the filesystem's two errors reports a gate failure that is a typo
    — and says nothing about the gate, which registered fine."""
    from scripts.flow_init_setup import _step

    def raises_off_the_filesystem() -> list[str]:
        raise AttributeError("'str' object has no attribute 'get'")

    assert _step("[테스트]", raises_off_the_filesystem) is False


def test_copy_files_includes_new_scripts():
    from scripts.flow_init_setup import COPY_FILES

    assert "scripts/check-token-write.sh" in COPY_FILES
    assert "scripts/finalize_prerelease.py" in COPY_FILES


def test_wiki_graph_is_copied_to_the_host():
    from scripts.flow_init_setup import COPY_FILES

    assert "scripts/wiki_graph.py" in COPY_FILES


def test_srs_check_and_its_import_land_together(tmp_path: Path):
    """A flat copy makes the import chain the contract.

    `srs_check` imports `_md_anchors`; `harness_scaffold`, which also holds it, is not
    copied. One name without the other is an ImportError at the moment the /flow step
    runs it, and the step fails open — so the gap is invisible.
    """
    run_setup(tmp_path, PLUGIN)
    dest = tmp_path / ".claude" / "harness-tier" / "scripts"
    assert (dest / "srs_check.py").is_file()
    assert (dest / "_md_anchors.py").is_file()


def test_setup_removes_the_rule_copy_an_older_setup_left(tmp_path: Path):
    """The shipped prose rule reaches a session through the hook's short block; a copy under
    .claude/rules/ would load in full every session. Re-sync deletes ours, never the host's."""
    stale = tmp_path / RULES_DEST / "doc-style.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("old copy", encoding="utf-8")
    own = tmp_path / ".claude" / "rules" / "doc-style.md"
    own.write_text("host's own", encoding="utf-8")
    for _ in range(2):  # Invariant 5: a re-run finds nothing left to remove and still passes
        run_setup(tmp_path, PLUGIN)
    assert not (tmp_path / RULES_DEST).exists()
    assert own.read_text(encoding="utf-8") == "host's own"


def test_setup_copies_no_rule_into_a_fresh_host(tmp_path: Path):
    run_setup(tmp_path, PLUGIN)
    assert not (tmp_path / RULES_DEST).exists()


def test_uninstall_removes_only_the_rule_copy(tmp_path: Path):
    assert "skip" in remove_rules(tmp_path)
    stale = tmp_path / RULES_DEST / "doc-style.md"
    stale.parent.mkdir(parents=True)
    stale.write_text("old copy", encoding="utf-8")
    own = tmp_path / ".claude" / "rules" / "mine.md"
    own.write_text("x", encoding="utf-8")
    run_uninstall(tmp_path)
    assert not (tmp_path / RULES_DEST).exists()
    assert own.is_file()


def test_the_hook_looks_for_the_rule_where_setup_cleans_it_up():
    """Two literals, one path: if they drift, a host still holding an old copy gets that full
    rule AND the injected summary, and setup deletes a directory the hook never checks."""
    hook = (PLUGIN / "hooks" / "inject-risk-tiers.sh").read_text(encoding="utf-8")
    assert f"{RULES_DEST}/doc-style.md" in hook
