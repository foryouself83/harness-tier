import subprocess
import sys
from pathlib import Path

import scripts.skill_sandbox as sandbox
from tests._non_utf8 import cp949_stdio_env

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "skill_sandbox.py"


def test_prints_a_scenario_in_utf8_on_a_cp949_host(tmp_path: Path):
    # Invariant #2. Scenario prose carries em dashes, which cp949 cannot encode, and the
    # printed prompt is read through a pipe, where stdout takes the locale codec. `why` is
    # prose free to reword without a re-measure, so the case reads it rather than a copy.
    why = sandbox.BY_NAME["custom-testdir"].why
    assert not why.isascii(), "the case needs a character outside ASCII to print"
    r = subprocess.run(
        [sys.executable, str(SCRIPT), "custom-testdir", "--out-dir", str(tmp_path)],
        env=cp949_stdio_env(),
        capture_output=True,
    )
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert why.encode() in r.stdout
