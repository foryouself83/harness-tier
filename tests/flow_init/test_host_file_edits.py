"""What /flow-init leaves in a host file it creates or edits in place: a workflow the host wrote
itself survives, a copied script stays runnable, an edited file keeps its line endings, and an
ignore rule the host already spelled differently is not added twice."""

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.flow_init_setup import (
    append_gitignore,
    copy_artifacts,
    integrate_release_deploy,
    remove_claude_md_block,
    remove_gitignore_lines,
    render_deploy_workflows,
)
from tests.flow_init._helpers import PLUGIN

DEPLOY_CONFIG = (
    "deploy:\n  enable: true\n  targets:\n"
    "    - name: {name}\n      target: pypi\n      auth: oidc\n"
)


def _config(host: Path, body: str) -> None:
    cfg = host / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "flow-config.yaml").write_text(body, encoding="utf-8")


# ── F1: deploy.yml ────────────────────────────────────────────────────────────


def test_a_hand_written_deploy_yml_is_never_overwritten(tmp_path):
    _config(tmp_path, DEPLOY_CONFIG.format(name="pypi"))
    wf = tmp_path / ".github" / "workflows" / "deploy.yml"
    wf.parent.mkdir(parents=True)
    wf.write_text("name: my own deploy\non: push\n", encoding="utf-8")
    report = render_deploy_workflows(tmp_path, PLUGIN)
    assert wf.read_text(encoding="utf-8") == "name: my own deploy\non: push\n"
    assert any("deploy.yml" in line and "[!]" in line for line in report)


def test_release_is_not_wired_to_a_hand_written_deploy_yml(tmp_path):
    """The call job passes `tag` to a reusable workflow; a host file without that input makes
    GitHub reject release.yml as a whole."""
    _config(tmp_path, DEPLOY_CONFIG.format(name="pypi"))
    wf = tmp_path / ".github" / "workflows"
    wf.mkdir(parents=True)
    (wf / "deploy.yml").write_text("name: my own deploy\non: push\n", encoding="utf-8")
    release = "jobs:\n  # __HARNESS_DEPLOY_BEGIN__\n  # __HARNESS_DEPLOY_END__\n"
    (wf / "release.yml").write_text(release, encoding="utf-8")
    report = render_deploy_workflows(tmp_path, PLUGIN)
    assert (wf / "release.yml").read_text(encoding="utf-8") == release
    assert any("release.yml" in line and "[!]" in line for line in report)


def test_a_deploy_yml_that_is_not_utf8_is_reported_not_raised(tmp_path):
    _config(tmp_path, DEPLOY_CONFIG.format(name="pypi"))
    wf = tmp_path / ".github" / "workflows" / "deploy.yml"
    wf.parent.mkdir(parents=True)
    wf.write_bytes(b"name: \xff\n")
    report = render_deploy_workflows(tmp_path, PLUGIN)
    assert wf.read_bytes() == b"name: \xff\n"
    assert any("deploy.yml" in line and "[!]" in line for line in report)


def test_a_generated_deploy_yml_saved_with_a_bom_is_still_generated(tmp_path):
    _config(tmp_path, DEPLOY_CONFIG.format(name="first"))
    render_deploy_workflows(tmp_path, PLUGIN)
    wf = tmp_path / ".github" / "workflows" / "deploy.yml"
    wf.write_bytes(b"\xef\xbb\xbf" + wf.read_bytes())
    _config(tmp_path, DEPLOY_CONFIG.format(name="second"))
    render_deploy_workflows(tmp_path, PLUGIN)
    assert "deploy-second.yml" in wf.read_text(encoding="utf-8")


def test_a_generated_deploy_yml_is_regenerated(tmp_path):
    _config(tmp_path, DEPLOY_CONFIG.format(name="first"))
    render_deploy_workflows(tmp_path, PLUGIN)
    _config(tmp_path, DEPLOY_CONFIG.format(name="second"))
    render_deploy_workflows(tmp_path, PLUGIN)
    text = (tmp_path / ".github" / "workflows" / "deploy.yml").read_text(encoding="utf-8")
    assert "deploy-second.yml" in text and "deploy-first.yml" not in text


# ── F2: executable bit ────────────────────────────────────────────────────────


@pytest.mark.skipif(sys.platform == "win32", reason="no POSIX mode bits on Windows")
def test_copied_shell_scripts_are_executable(tmp_path):
    copy_artifacts(PLUGIN, tmp_path, ["claude", "codex"])
    scripts = tmp_path / ".claude" / "harness-tier" / "scripts"
    shells = sorted(scripts.rglob("*.sh"))
    assert shells, "no .sh copied — the test asks nothing"
    for sh in shells:
        assert sh.stat().st_mode & stat.S_IXUSR, f"{sh.name} is not executable"


@pytest.mark.skipif(sys.platform == "win32", reason="no POSIX mode bits on Windows")
def test_a_re_sync_restores_a_lost_executable_bit(tmp_path):
    copy_artifacts(PLUGIN, tmp_path)
    runner = tmp_path / ".claude" / "harness-tier" / "scripts" / "precommit-runner.sh"
    os.chmod(runner, 0o644)
    copy_artifacts(PLUGIN, tmp_path)
    assert runner.stat().st_mode & stat.S_IXUSR


# ── G10: bytecode ─────────────────────────────────────────────────────────────


@pytest.mark.skipif(shutil.which("git") is None, reason="git required")
@pytest.mark.parametrize("sub", ["", "harness/", "harness/codex/"])
def test_gitignore_covers_the_bytecode_the_copied_scripts_produce(tmp_path, sub):
    """Codex's renderer runs from scripts/harness/codex/, one package below the flat copies."""
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    append_gitignore(tmp_path)
    pyc = f".claude/harness-tier/scripts/{sub}__pycache__/m.cpython-312.pyc"
    (tmp_path / pyc).parent.mkdir(parents=True)
    (tmp_path / pyc).write_bytes(b"")
    r = subprocess.run(["git", "check-ignore", "-q", pyc], cwd=tmp_path)
    assert r.returncode == 0, f"{pyc} is not ignored"


def test_uninstall_removes_the_bytecode_ignore_line(tmp_path):
    append_gitignore(tmp_path)
    remove_gitignore_lines(tmp_path)
    gi = tmp_path / ".gitignore"
    assert "__pycache__" not in (gi.read_text(encoding="utf-8") if gi.exists() else "")


# ── F9: an ignore rule spelled differently ────────────────────────────────────


@pytest.mark.parametrize(
    "existing",
    [
        "/.claude/harness-tier/.flow/",
        ".claude/harness-tier/.flow",
        ".claude/harness-tier/.flow/  ",
    ],
)
def test_an_equivalent_flow_rule_is_not_added_again(tmp_path, existing):
    (tmp_path / ".gitignore").write_text(existing + "\n", encoding="utf-8")
    append_gitignore(tmp_path)
    lines = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".claude/harness-tier/.flow/" not in lines


def test_an_anchored_webhook_rule_does_not_stand_for_the_bare_one(tmp_path):
    """`/x` ignores the root file only; the bare rule exists to catch every depth."""
    (tmp_path / ".gitignore").write_text("/.teams-webhooks.local.json\n", encoding="utf-8")
    append_gitignore(tmp_path)
    lines = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".teams-webhooks.local.json" in lines


def test_a_directory_only_rule_does_not_stand_for_a_file_rule(tmp_path):
    (tmp_path / ".gitignore").write_text(".teams-webhooks.local.json/\n", encoding="utf-8")
    append_gitignore(tmp_path)
    lines = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".teams-webhooks.local.json" in lines


def test_a_negated_rule_does_not_count_as_present(tmp_path):
    (tmp_path / ".gitignore").write_text("!.claude/harness-tier/.flow/\n", encoding="utf-8")
    append_gitignore(tmp_path)
    lines = (tmp_path / ".gitignore").read_text(encoding="utf-8").splitlines()
    assert ".claude/harness-tier/.flow/" in lines


# ── F7: line endings ──────────────────────────────────────────────────────────


@pytest.mark.parametrize("eol", ["\r\n", "\n"])
def test_append_gitignore_keeps_the_files_line_endings(tmp_path, eol):
    gi = tmp_path / ".gitignore"
    gi.write_bytes(f"node_modules/{eol}dist/{eol}".encode())
    append_gitignore(tmp_path)
    raw = gi.read_bytes().decode()
    assert raw.startswith(f"node_modules/{eol}dist/{eol}")
    assert raw.count(eol) == len(raw.splitlines())
    if eol == "\n":
        assert "\r" not in raw


@pytest.mark.parametrize("eol", ["\r\n", "\n"])
def test_remove_gitignore_lines_keeps_the_files_line_endings(tmp_path, eol):
    gi = tmp_path / ".gitignore"
    gi.write_bytes(f"node_modules/{eol}.claude/harness-tier/.flow/{eol}dist/{eol}".encode())
    remove_gitignore_lines(tmp_path)
    assert gi.read_bytes().decode() == f"node_modules/{eol}dist/{eol}"


@pytest.mark.parametrize("eol", ["\r\n", "\n"])
def test_remove_claude_md_block_keeps_the_files_line_endings(tmp_path, eol):
    cm = tmp_path / "CLAUDE.md"
    body = ["# Host", "<!-- harness-tier:teams BEGIN -->", "x", "<!-- harness-tier:teams END -->"]
    cm.write_bytes((eol.join([*body, "tail"]) + eol).encode())
    remove_claude_md_block(tmp_path)
    assert cm.read_bytes().decode() == f"# Host{eol}tail{eol}"


@pytest.mark.parametrize("eol", ["\r\n", "\n"])
def test_release_deploy_wiring_keeps_the_files_line_endings(tmp_path, eol):
    _config(tmp_path, DEPLOY_CONFIG.format(name="pypi"))
    rel = tmp_path / ".github" / "workflows" / "release.yml"
    rel.parent.mkdir(parents=True)
    lines = ["name: release", "jobs:", "  # __HARNESS_DEPLOY_BEGIN__", "  # __HARNESS_DEPLOY_END__"]
    rel.write_bytes((eol.join(lines) + eol).encode())
    integrate_release_deploy(tmp_path, PLUGIN)
    raw = rel.read_bytes().decode()
    assert "uses: ./.github/workflows/deploy.yml" in raw
    assert raw.count(eol) == len(raw.splitlines())
    if eol == "\n":
        assert "\r" not in raw
