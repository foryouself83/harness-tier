import json
import subprocess
import sys
from pathlib import Path

from tests._non_utf8 import ansi_locale_env
from tests.flow_gate._helpers import requires_git

REPO = Path(__file__).resolve().parent.parent.parent


@requires_git
def test_host_root_reads_a_non_ascii_toplevel_without_utf8_mode(tmp_path: Path):
    # Invariant #2. A skill runs these scripts with no CLAUDE_PROJECT_DIR, so git's UTF-8 path
    # names the host, and force_utf8_io's PYTHONUTF8 reaches child processes only — never the
    # pipe this process decodes. Misread, the root is some other directory.
    repo = tmp_path / "작업"
    (repo / "sub").mkdir(parents=True)
    subprocess.run(["git", "init", "-q"], cwd=repo, check=True)
    env = ansi_locale_env(PYTHONPATH=str(REPO))
    env.pop("CLAUDE_PROJECT_DIR", None)
    code = "import json, scripts._harness_paths as p; print(json.dumps(str(p.host_root())))"
    r = subprocess.run([sys.executable, "-c", code], cwd=repo / "sub", env=env, capture_output=True)
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert Path(json.loads(r.stdout)).resolve() == repo.resolve()
