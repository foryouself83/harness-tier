import json
import subprocess
import sys
from pathlib import Path

from tests._non_utf8 import ansi_locale_env, cp949_stdio_env
from tests.flow_gate._helpers import _init_repo, _rg, requires_git

REPO = Path(__file__).resolve().parent.parent.parent


def test_merge_check_blocks_under_a_cp949_stdin(tmp_path: Path):
    # Invariant #1 Exception 3, on the host Invariant #2 describes. PYTHONIOENCODING outranks
    # the runner's PYTHONUTF8=1 on stdin, and a payload that fails to decode is allowed by the
    # FAIL-OPEN except — a merge missing its required flag goes through.
    cfg = tmp_path / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-tiers.yaml").write_text(
        "tiers:\n  dev:\n    gates: [review]\n"
        "merge_strategy:\n"
        '  - source: "feature/*"\n'
        "    target: integration\n"
        '    require: "--squash"\n',
        encoding="utf-8",
    )
    (cfg / "flow-config.yaml").write_text(
        "branches:\n  integration: dev\n  staging: stage\n  production: main\n"
        '  feature_prefix: "feature/"\n',
        encoding="utf-8",
    )
    command = 'git switch dev && git merge feature/x -m "기능 추가"'
    r = subprocess.run(
        [sys.executable, "scripts/flow_gate_check.py", "--merge-check"],
        cwd=REPO,
        env=cp949_stdio_env(CLAUDE_PROJECT_DIR=str(tmp_path), PYTHONUTF8="1"),
        input=json.dumps({"tool_input": {"command": command}}, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
    )
    assert r.returncode == 2, r.stderr.decode("utf-8", "replace")
    assert b"--squash" in r.stderr


@requires_git
def test_current_branch_reads_a_korean_name_without_utf8_mode(tmp_path: Path):
    # Invariant #2. The tier marker's branch is matched against this name: misread, a
    # classified commit reads as unclassified, which Exception 2 blocks.
    repo = tmp_path / "repo"
    _init_repo(repo)
    _rg(["switch", "-q", "-c", "feature/한글"], repo)
    code = (
        "import json, sys, pathlib, scripts.flow_gate_check as f;"
        " print(json.dumps(f._current_branch(pathlib.Path(sys.argv[1]))))"
    )
    r = subprocess.run(
        [sys.executable, "-c", code, str(repo)],
        env=ansi_locale_env(PYTHONPATH=str(REPO)),
        capture_output=True,
    )
    assert r.returncode == 0, r.stderr.decode("utf-8", "replace")
    assert json.loads(r.stdout) == "feature/한글"
