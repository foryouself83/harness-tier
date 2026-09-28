"""Codex reads the deny JSON, not exit 2 (Windows pwsh rewrites 2 to 1), so the wrapper turns the runner's 2 into 0."""  # noqa: E501

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from tests.invalidate_gate_markers._helpers import BASH  # repo-visible bash (Git Bash on Windows)

REPO = Path(__file__).resolve().parents[3]
WRAP_SH = REPO / "scripts" / "harness" / "codex" / "gate.sh"
WRAP_CMD = REPO / "scripts" / "harness" / "codex" / "gate.cmd"
DENY = {
    "hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": "fake",
    }
}


def _host(tmp_path: Path, runner_exit: int) -> Path:
    scripts = tmp_path / "scripts"
    (scripts / "harness" / "codex").mkdir(parents=True)
    shutil.copyfile(WRAP_SH, scripts / "harness" / "codex" / "gate.sh")
    shutil.copyfile(WRAP_CMD, scripts / "harness" / "codex" / "gate.cmd")
    body = f"cat > /dev/null\nprintf '%s\\n' '{json.dumps(DENY)}'\nexit {runner_exit}\n"
    (scripts / "precommit-runner.sh").write_text(body, encoding="utf-8", newline="\n")
    return scripts / "harness" / "codex"


@pytest.mark.skipif(BASH is None, reason="a repo-visible bash is required")
@pytest.mark.parametrize("runner_exit,want", [(2, 0), (0, 0), (1, 1)])
def test_sh_maps_only_exit_2(tmp_path, runner_exit, want):
    where = _host(tmp_path, runner_exit)
    run = subprocess.run([BASH, (where / "gate.sh").as_posix()], input=b"{}", capture_output=True)
    assert run.returncode == want
    assert json.loads(run.stdout.decode().strip()) == DENY


@pytest.mark.skipif(sys.platform != "win32", reason="cmd wrapper is Windows-only")
@pytest.mark.parametrize("runner_exit,want", [(2, 0), (0, 0), (1, 1)])
def test_cmd_blocks_through_git_bash(tmp_path, runner_exit, want):
    # Parametrized like test_sh_maps_only_exit_2: gate.cmd must propagate gate.sh's own exit
    # code (which already remaps only 2->0) unchanged for every other value. A same-line
    # `& exit /b %errorlevel%` expands %errorlevel% at parse time, before gate.sh runs, so it
    # always reports the leftover 0 from the detection logic above regardless of the real
    # result — this (1, 1) case is the one that catches that bug; (2, 0) alone cannot, since
    # the buggy leftover and the correct mapped answer are coincidentally the same number.
    where = _host(tmp_path, runner_exit)
    run = subprocess.run(
        ["cmd", "/d", "/c", str(where / "gate.cmd")],
        input=b'{"tool_input":{"command":"git commit"}}',
        capture_output=True,
    )
    assert run.returncode == want
    assert json.loads(run.stdout.decode().strip()) == DENY


SYSWOW64_CMD = Path(r"C:\Windows\SysWOW64\cmd.exe")
X86_GIT_BASH = Path(r"C:\Program Files (x86)\Git\bin\bash.exe")


@pytest.mark.skipif(sys.platform != "win32", reason="cmd wrapper is Windows-only")
@pytest.mark.skipif(not SYSWOW64_CMD.exists(), reason="requires the 32-bit cmd.exe under SysWOW64")
@pytest.mark.skipif(
    X86_GIT_BASH.exists(),
    reason="Git Bash is installed under Program Files (x86) here too, so the 32-bit "
    "ProgramFiles redirection this test relies on would still find it",
)
def test_cmd_without_git_bash_denies_commit_words_only(tmp_path):
    # ProgramFiles cannot be spoofed via env= for a 64-bit cmd.exe child (measured: Windows
    # re-derives it from HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment
    # regardless of what CreateProcess's environment block supplies), so a 64-bit gate.cmd
    # invocation always finds the real "C:\Program Files\Git\bin\bash.exe" on any machine that
    # has Git installed the normal way. But ProgramFiles redirection is genuinely per-process
    # bitness (WOW64): the 32-bit cmd.exe under SysWOW64 sees the real, OS-provided
    # "C:\Program Files (x86)" — not a spoof — where Git for Windows' 64-bit-only default
    # install never places a copy. Combined with a PATH that drops Git's own directory (so
    # `where git` also fails), both of gate.cmd's detection paths genuinely miss, without
    # touching the real Program Files install at all.
    where = _host(tmp_path, 0)
    env = {k: v for k, v in os.environ.items() if k.upper() != "PATH"}
    env["PATH"] = r"C:\Windows\System32;C:\Windows\SysWOW64"
    commit = subprocess.run(
        [str(SYSWOW64_CMD), "/d", "/c", str(where / "gate.cmd")],
        env=env,
        input=b'{"tool_input":{"command":"git commit -m x"}}',
        capture_output=True,
    )
    other = subprocess.run(
        [str(SYSWOW64_CMD), "/d", "/c", str(where / "gate.cmd")],
        env=env,
        input=b'{"tool_input":{"command":"ls"}}',
        capture_output=True,
    )
    assert commit.returncode == 0 and "deny" in commit.stdout.decode()
    assert other.returncode == 0 and other.stdout.strip() == b""


CLAUDE_WORDED = (
    "flow 미진입: /flow 로 분류한 뒤 커밋하세요(강제가 불필요하면 /flow-uninstall). "
    "불가하면 settings.json 의 게이트 훅을 제거. 증거: .claude/harness-tier/.flow/tier"
)


@pytest.mark.skipif(BASH is None, reason="a repo-visible bash is required")
def test_sh_rewords_the_reason_for_codex(tmp_path):
    where = _host(tmp_path, 2)
    deny = {
        "hookSpecificOutput": {
            **DENY["hookSpecificOutput"],
            "permissionDecisionReason": CLAUDE_WORDED,
        }
    }
    runner = tmp_path / "scripts" / "precommit-runner.sh"
    body = f"cat > /dev/null\nprintf '%s\n' '{json.dumps(deny, ensure_ascii=False)}'\nexit 2\n"
    runner.write_text(body, encoding="utf-8", newline="\n")
    run = subprocess.run([BASH, (where / "gate.sh").as_posix()], input=b"{}", capture_output=True)
    assert run.returncode == 0
    reason = json.loads(run.stdout.decode("utf-8"))["hookSpecificOutput"][
        "permissionDecisionReason"
    ]
    assert reason == (
        "flow 미진입: $flow 로 분류한 뒤 커밋하세요(강제가 불필요하면 $flow-uninstall). "
        "불가하면 .codex/hooks.json 의 게이트 훅을 제거. 증거: .claude/harness-tier/.flow/tier"
    )


@pytest.mark.skipif(BASH is None, reason="a repo-visible bash is required")
def test_sh_prints_nothing_when_the_runner_allows(tmp_path):
    where = _host(tmp_path, 0)
    (tmp_path / "scripts" / "precommit-runner.sh").write_text(
        "cat > /dev/null\nexit 0\n", encoding="utf-8", newline="\n"
    )
    run = subprocess.run([BASH, (where / "gate.sh").as_posix()], input=b"{}", capture_output=True)
    assert run.returncode == 0 and run.stdout == b""


@pytest.mark.skipif(BASH is None, reason="a repo-visible bash is required")
@pytest.mark.parametrize("fake_sed", ["exit 1", "cat > /dev/null; exit 0"], ids=["fails", "empty"])
def test_sh_keeps_the_deny_when_rewording_fails(tmp_path, fake_sed):
    where = _host(tmp_path, 2)
    broken = tmp_path / "broken-bin"
    broken.mkdir()
    body = f"#!/usr/bin/env bash\n{fake_sed}\n"
    (broken / "sed").write_text(body, encoding="utf-8", newline="\n")
    (broken / "sed").chmod(0o755)
    posix = broken.as_posix()
    bin_dir = f'$(cygpath -u "{posix}" 2>/dev/null || echo "{posix}")'
    gate = (where / "gate.sh").as_posix()
    # the guard proves the fake sed is the one gate.sh finds, or the test would pass vacuously
    guard = f'[ "$(command -v sed)" = "{bin_dir}/sed" ] || exit 9'
    script = f'PATH="{bin_dir}:$PATH"; {guard}; bash "{gate}"'
    run = subprocess.run([BASH, "-c", script], input=b"{}", capture_output=True)
    assert run.returncode == 0
    assert json.loads(run.stdout.decode().strip()) == DENY


@pytest.mark.skipif(sys.platform != "win32", reason="cmd wrapper is Windows-only")
@pytest.mark.parametrize("wrapper", ["gate.cmd", "run-hook.cmd"])
def test_cmd_finds_git_bash_from_a_mingw64_git(tmp_path, wrapper):
    # Git for Windows puts git.exe in cmd\ and in mingw64\bin\; the second is two levels below
    # the install root, so `..\bin\bash.exe` from it names a file that does not exist. The fake
    # bash is a renamed cmd.exe, which runs `exit 7` from stdin: 7 proves the wrapper chose the
    # bash beside this git rather than the real install under ProgramFiles.
    install = tmp_path / "Git"
    (install / "mingw64" / "bin").mkdir(parents=True)
    (install / "mingw64" / "bin" / "git.exe").write_bytes(b"")
    (install / "bin").mkdir()
    cmd_exe = Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe"
    shutil.copyfile(cmd_exe, install / "bin" / "bash.exe")
    source = WRAP_CMD if wrapper == "gate.cmd" else REPO / "hooks" / "codex" / "run-hook.cmd"
    host = tmp_path / "host"
    host.mkdir()
    shutil.copyfile(source, host / wrapper)
    env = {k: v for k, v in os.environ.items() if k.upper() != "PATH"}
    env["PATH"] = f"{install / 'mingw64' / 'bin'};{Path(os.environ['SystemRoot']) / 'System32'}"
    run = subprocess.run(
        ["cmd", "/d", "/c", str(host / wrapper), "x.sh"],
        env=env,
        input=b"exit 7\r\n",
        capture_output=True,
    )
    assert run.returncode == 7, run.stdout
