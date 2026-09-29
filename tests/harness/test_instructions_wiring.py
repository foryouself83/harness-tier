"""/flow-init's setup and uninstall render and remove the Codex instructions block — and leave a
Claude-only host's files alone."""

from pathlib import Path

import pytest

import scripts.flow_init_setup as fis
from scripts.harness.codex import instructions as codex
from tests.flow_init._helpers import PLUGIN

CFG = Path(".claude/harness-tier/config/flow-config.yaml")
HOST_SCRIPTS = Path(".claude/harness-tier/scripts")


@pytest.fixture(autouse=True)
def _hermetic_codex_home(tmp_path, monkeypatch):
    home = tmp_path / "codexhome"
    home.mkdir()
    monkeypatch.setenv("CODEX_HOME", str(home))


def _host(tmp_path: Path, harnesses: str | None) -> Path:
    host = tmp_path / "host"
    (host / CFG).parent.mkdir(parents=True)
    if harnesses is not None:
        (host / CFG).write_text(f"harnesses: {harnesses}\n", encoding="utf-8")
    (host / "CLAUDE.md").write_bytes(b"# Host\r\nbe careful\r\n")
    return host


def test_claude_only_setup_and_uninstall_never_touch_agents_md(tmp_path):
    host = _host(tmp_path, None)
    fis.run_setup(host, PLUGIN)
    assert not (host / "AGENTS.md").exists()
    (host / "AGENTS.md").write_bytes(b"mine\r\n")
    fis.run_setup(host, PLUGIN)
    fis.run_uninstall(host)
    assert (host / "AGENTS.md").read_bytes() == b"mine\r\n"


def test_codex_setup_renders_the_block(tmp_path, capsys):
    host = _host(tmp_path, "[claude, codex]")
    claude_md = (host / "CLAUDE.md").read_bytes()
    assert fis.run_setup(host, PLUGIN)
    assert "[Codex 지침 렌더]" in capsys.readouterr().out
    text = (host / "AGENTS.md").read_text(encoding="utf-8")
    assert codex.BEGIN in text and "be careful" in text
    assert (host / "CLAUDE.md").read_bytes() == claude_md


def test_uninstall_removes_the_block_and_keeps_user_text(tmp_path):
    host = _host(tmp_path, "[claude, codex]")
    (host / "AGENTS.md").write_bytes(b"user text\n")
    fis.run_setup(host, PLUGIN)
    assert codex.BEGIN.encode("utf-8") in (host / "AGENTS.md").read_bytes()
    fis.run_uninstall(host)
    assert (host / "AGENTS.md").read_bytes() == b"user text\n"


def test_codex_host_copy_carries_the_renderer(tmp_path):
    fis.copy_artifacts(PLUGIN, tmp_path, harnesses=("claude", "codex"))
    for rel in (
        "harness/__init__.py",
        "harness/instructions.py",
        "harness/codex/__init__.py",
        "harness/codex/instructions.py",
    ):
        assert (tmp_path / HOST_SCRIPTS / rel).is_file(), rel


def test_the_host_copy_runs_on_its_own(tmp_path):
    """Run from the host copy with the plugin out of reach: every import it needs travelled."""
    import subprocess
    import sys

    host = _host(tmp_path, "[claude, codex]")
    fis.copy_artifacts(PLUGIN, host, harnesses=("claude", "codex"))
    script = host / HOST_SCRIPTS / "harness/codex/instructions.py"
    cmd = [sys.executable, "-I", str(script), "render", "--host", str(host)]
    run = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", cwd=tmp_path)
    assert run.returncode == 0, run.stderr
    assert codex.BEGIN in (host / "AGENTS.md").read_text(encoding="utf-8")


def test_the_host_copy_names_a_missing_pyyaml(tmp_path):
    """The host copy imports through its sibling path, which the in-repo tests never reach."""
    import subprocess
    import sys

    host = _host(tmp_path, "[claude, codex]")
    fis.copy_artifacts(PLUGIN, host, harnesses=("claude", "codex"))
    script = host / HOST_SCRIPTS / "harness/codex/instructions.py"
    code = (
        "import runpy, sys; sys.modules['yaml'] = None; "
        f"sys.argv = [{str(script)!r}, 'render', '--check', '--host', {str(host)!r}]; "
        f"runpy.run_path({str(script)!r}, run_name='__main__')"
    )
    run = subprocess.run(
        [sys.executable, "-I", "-c", code], capture_output=True, text=True, encoding="utf-8"
    )
    assert run.returncode == 1, run.stderr
    assert "PyYAML" in run.stdout and "Traceback" not in run.stderr


def test_renderer_modules_are_not_gate_files():
    gate = {source for _, source in fis.gate_files(("claude", "codex"))}
    assert not any(source.endswith("instructions.py") for source in gate)
