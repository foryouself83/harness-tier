import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from scripts.flow_init_setup import (
    CLAUDE_MD_BEGIN,
    GITIGNORE_LINES,
    append_gitignore,
    check_precommit,
    copy_artifacts,
    register_gate,
    register_marketplace,
    remove_claude_md_block,
    remove_gitignore_lines,
    remove_harness_dir,
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
