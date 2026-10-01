"""The hook forks nothing on its common paths.

Every `$(...)` is a fork, and a fork costs tens of milliseconds on Git Bash's msys runtime:
on Git Bash 5.2 with the shipped rule, ten of them took the hook from 126 ms to 1050 ms.
Counting subshells pins the cost on every platform, where a wall-clock bound would hold only
on the one it was tuned on.
"""

import os
import subprocess

import pytest

from tests.inject_risk_tiers._helpers import BASH, SCRIPT, STARTUP, _plugins_root


def _trace(plugin, *args, path=None):
    env = {
        "PATH": os.environ.get("PATH", "") if path is None else path,
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "CLAUDE_PLUGIN_ROOT": str(plugin),
        "CLAUDE_PROJECT_DIR": str(plugin),
        "PS4": "+${BASH_SUBSHELL}| ",
    }
    return subprocess.run(
        [BASH, "-x", str(SCRIPT), *args],
        input=STARTUP,
        text=True,
        encoding="utf-8",
        capture_output=True,
        env=env,
        timeout=30,
    )


CASES = {
    "claude": ((), {"published": "1.0.0"}),
    "notice": ((), {"published": "2.0.0"}),
    "codex": (("--harness", "codex"), {"published": "1.0.0"}),
}


@pytest.mark.parametrize("case", list(CASES))
def test_no_subshell_runs(tmp_path, case):
    args, versions = CASES[case]
    result = _trace(_plugins_root(tmp_path, loaded="1.0.0", **versions), *args)
    assert result.returncode == 0, result.stderr
    # PS4's first character repeats once per level of indirection, a command substitution's too.
    traced = [line for line in result.stderr.splitlines() if line.startswith("+")]
    forked = [line for line in traced if line.startswith("++") or not line.startswith("+0|")]
    assert not forked, "\n".join(forked[:10])


@pytest.mark.parametrize("case", list(CASES))
def test_no_external_command_runs(tmp_path, case):
    """With nothing on PATH, a hook that needs no program writes exactly what it writes with one."""
    args, versions = CASES[case]
    plugin = _plugins_root(tmp_path, loaded="1.0.0", **versions)
    with_path = _trace(plugin, *args)
    without = _trace(plugin, *args, path="")
    assert (without.returncode, without.stdout) == (0, with_path.stdout)
