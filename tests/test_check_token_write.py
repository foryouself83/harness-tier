import shutil
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check-token-write.sh"
# On Windows, a bare "bash" is resolved by the OS process-creation search order, which
# checks System32 *before* PATH — so on machines with WSL installed, it silently picks up
# the WSL launcher stub (System32\bash.exe) instead of Git Bash, even though Git Bash comes
# first in PATH. The stub also mangles Windows-style backslash paths, breaking the script
# invocation. shutil.which() walks PATH in order (no such System32-first special-case), so
# it reliably resolves to Git Bash where available; falls back to "bash" (e.g. on Linux CI).
BASH = shutil.which("bash") or "bash"


def _decode(json_text: str) -> int:
    return subprocess.run(
        [BASH, str(SCRIPT), "--decode"],
        input=json_text,
        text=True,
        capture_output=True,
    ).returncode


def test_push_true_exits_0():
    assert _decode('{"permissions":{"admin":false,"push":true,"pull":true}}') == 0


def test_push_false_exits_10():
    assert _decode('{"permissions":{"admin":false,"push":false,"pull":true}}') == 10


def test_no_push_key_exits_20():
    assert _decode('{"full_name":"x/y"}') == 20


def test_reads_permissions_push_not_nested():
    # a nested object's push must not be read instead of the top-level permissions.push
    assert _decode('{"parent":{"push":true},"permissions":{"push":false,"pull":true}}') == 10
