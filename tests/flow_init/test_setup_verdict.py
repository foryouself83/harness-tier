import os
from pathlib import Path

import pytest

from scripts.flow_init_setup import run_setup
from tests.flow_init._helpers import PLUGIN, _gate_hook, _planted


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
