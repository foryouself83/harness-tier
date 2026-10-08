"""The merge check's notice reaches the user through the runner, as the one JSON object a hook
may print."""

import json
from pathlib import Path

import scripts.flow_gate_check as fgc
from tests.flow_gate._helpers import _init_repo, _rg, _run_runner, requires_bash_git

_STUB = (
    "import json, os, sys\n"
    "if '--merge-check' in sys.argv:\n"
    "    sys.stdin.read()\n"
    "    print(json.dumps({'systemMessage': 'MERGE-NOTE'}))\n"
    "    sys.exit(0)\n"
    "if '--classify' in sys.argv:\n"
    "    commit = int('commit' in json.loads(sys.stdin.read())['tool_input']['command'])\n"
    "    sys.stdout.write(f'ok=1\\ncommit={commit}\\nmerge=1\\nworktree=\\n')\n"
    "    sys.exit(0)\n"
    "if len(sys.argv) == 1:\n"
    "    held = json.loads(os.environ.get('HARNESS_MERGE_NOTE') or '{}').get('systemMessage')\n"
    "    if held:\n"
    "        print(json.dumps({'systemMessage': 'COMMIT+' + held}))\n"
)


def _host(tmp_path: Path) -> tuple[Path, Path]:
    main = tmp_path / "main"
    _init_repo(main)
    (main / ".claude" / "harness-tier" / "config").mkdir(parents=True)
    (main / ".claude" / "harness-tier" / "config" / "flow-config.yaml").write_text(
        "modules: []\n", encoding="utf-8"
    )
    _rg(["add", "-A"], main)
    _rg(["commit", "-m", "config"], main)
    plugin = tmp_path / "plugin"
    (plugin / "scripts").mkdir(parents=True)
    (plugin / "scripts" / "flow_gate_check.py").write_text(_STUB, encoding="utf-8")
    return main, plugin


def _one_object(stdout: str) -> str:
    lines = [line for line in stdout.splitlines() if line.strip()]
    assert len(lines) == 1, stdout
    return json.loads(lines[0])["systemMessage"]


@requires_bash_git
def test_a_merge_notice_reaches_the_user(tmp_path):
    main, plugin = _host(tmp_path)
    r = _run_runner(main, "git merge --squash dev", plugin_root=plugin)
    assert r.returncode == 0, r.stderr
    assert _one_object(r.stdout) == "MERGE-NOTE"


@requires_bash_git
def test_a_merge_notice_rides_in_the_commit_notice(tmp_path):
    main, plugin = _host(tmp_path)
    (main / "a.txt").write_text("x", encoding="utf-8")
    _rg(["add", "a.txt"], main)
    r = _run_runner(main, "git merge --squash dev && git commit -m x", plugin_root=plugin)
    assert r.returncode == 0, r.stderr
    assert _one_object(r.stdout) == "COMMIT+MERGE-NOTE"


@requires_bash_git
def test_a_merge_notice_survives_a_clean_tree(tmp_path):
    main, plugin = _host(tmp_path)
    r = _run_runner(main, "git merge --squash dev && git commit -m x", plugin_root=plugin)
    assert r.returncode == 0, r.stderr
    assert _one_object(r.stdout) == "MERGE-NOTE"


def test_the_flow_stage_carries_the_held_merge_notice(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("HARNESS_PRECOMMIT_DRYRUN", "1")
    monkeypatch.setenv("HARNESS_MERGE_NOTE", json.dumps({"systemMessage": "HELD"}))
    fgc._runtime_notices(tmp_path, None)
    assert json.loads(capsys.readouterr().out)["systemMessage"] == "HELD"
