import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.flow_gate_check as fgc
from tests.flow_gate._helpers import _init_repo, _rg, requires_git


def test_both_import_paths_carry_the_same_names():
    """flow_gate_check is run as a sibling script on a host and imported as a package in
    tests, so it spells its imports twice. A name in one list only is a NameError on the
    other path, swallowed by the FAIL-OPEN except around the caller — the gate off in
    silence rather than anything reported."""
    src = (Path(__file__).resolve().parent.parent.parent / "scripts/flow_gate_check.py").read_text(
        encoding="utf-8"
    )
    lists = re.findall(r"import \(\n(.*?)\n\s*\)", src, re.S)
    assert len(lists) == 2, f"expected two import lists, found {len(lists)}"
    names = [sorted(n.strip().rstrip(",") for n in one.strip().splitlines()) for one in lists]
    assert names[0] == names[1], (
        f"the two _harness_paths import lists differ: {set(names[0]) ^ set(names[1])}"
    )


def _classify(root: Path, payload: dict) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root), "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, "scripts/flow_gate_check.py", "--classify"],
        cwd=Path(__file__).resolve().parent.parent.parent,
        env=env,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@requires_git
def test_classify_detects_a_commit_and_the_worktree_it_runs_in(tmp_path: Path):
    # `git -C <wt> commit` (the /flow worktree commit convention) → a commit, in W.
    main = tmp_path / "repo"
    _init_repo(main)
    wt = tmp_path / "repo-wt"
    _rg(["worktree", "add", "-b", "feature/x", str(wt)], main)
    payload = {"cwd": str(main), "tool_input": {"command": f'git -C {wt} commit -m "m"'}}
    r = _classify(main, payload)
    assert r.returncode == 0
    lines = r.stdout.split()
    assert "commit=1" in lines
    assert f"worktree={wt.resolve()}" in lines


@requires_git
def test_classify_names_no_worktree_for_a_single_tree(tmp_path: Path):
    # non-worktree (single tree): W == main → no worktree line → runner keeps ROOT=main.
    main = tmp_path / "repo"
    _init_repo(main)
    payload = {"cwd": str(main), "tool_input": {"command": "git commit -m m"}}
    r = _classify(main, payload)
    assert r.returncode == 0
    assert r.stdout.split() == ["ok=1", "commit=1"]


@requires_git
def test_classify_says_nothing_for_a_command_that_only_mentions_the_word(tmp_path: Path):
    """The runner's pre-filter is allowed to over-match; this is what stops the over-match from
    reaching the gates. Said otherwise, a read-only `git log` would be denied as an unclassified
    commit — the gate blocking work it was never meant to see."""
    main = tmp_path / "repo"
    _init_repo(main)
    payload = {
        "cwd": str(main),
        "tool_input": {"command": 'git log --oneline -5 && echo "now commit"'},
    }
    r = _classify(main, payload)
    assert r.returncode == 0
    # `ok=1` alone: the command was read, and it is neither. The runner needs that apart from
    # silence, which means the gate could not answer at all.
    assert r.stdout.split() == ["ok=1"]


@requires_git
@pytest.mark.parametrize(
    "command,expected",
    [
        ("printf 'git commit -m x' | bash", "commit=1"),
        ("bash <<< 'git commit -m x'", "commit=1"),
        ("printf 'git merge --no-ff dev' | bash", "merge=1"),
    ],
    ids=["pipe", "here-string", "merge"],
)
def test_classify_reads_a_commit_an_interpreter_is_handed(
    tmp_path: Path, command: str, expected: str
):
    """The verdict the runner routes on has to come from the same authority the grammar
    tests use. Scored here through the subprocess, because a classify that reads the mask
    alone answers `ok=1` for these and the runner then exits 0 on a real commit."""
    main = tmp_path / "repo"
    _init_repo(main)
    r = _classify(main, {"cwd": str(main), "tool_input": {"command": command}})
    assert expected in r.stdout.split(), (command, r.stdout, r.stderr)


@requires_git
def test_classify_says_nothing_when_the_payload_carries_no_command(tmp_path: Path):
    """`ok=1` says the command was READ. With no command there is nothing to read, and claiming
    otherwise answers "not a commit" — which the runner takes as leave, dropping the raw-stdin
    backstop that is the only thing left when the payload is not the shape the tool sends."""
    main = tmp_path / "repo"
    _init_repo(main)
    for payload in (
        {"tool_name": "Bash", "command": "git commit -m x"},  # command at the wrong level
        {"cwd": str(main), "tool_input": None},
        {"cwd": str(main), "tool_input": {"command": None}},
        {"cwd": str(main), "tool_input": {"command": ["git", "commit"]}},
        {"cwd": str(main), "tool_input": "git commit -m x"},
    ):
        r = _classify(main, payload)
        assert r.returncode == 0, (payload, r.stderr)
        assert r.stdout.strip() == "", (payload, r.stdout)


@requires_git
def test_classify_still_answers_for_an_empty_command(tmp_path: Path):
    # An empty string IS a command, and it is not an invocation — a verdict, not a silence.
    main = tmp_path / "repo"
    _init_repo(main)
    r = _classify(main, {"cwd": str(main), "tool_input": {"command": ""}})
    assert r.stdout.split() == ["ok=1"]


@requires_git
def test_classify_reports_a_merge_without_resolving_a_worktree(tmp_path: Path):
    """Invariant #6: only the commit path re-designates. A merge names its worktree to the merge
    check, which fails open on a foreign one, and must not move ROOT out from under it."""
    main = tmp_path / "repo"
    _init_repo(main)
    wt = tmp_path / "repo-wt"
    _rg(["worktree", "add", "-b", "feature/x", str(wt)], main)
    # The hook's own cwd is the worktree — the rung the guard stands in front of. With
    # `cwd` on main the command names no commit either way, so the guard would go unexercised.
    payload = {"cwd": str(wt), "tool_input": {"command": "git merge --no-ff dev"}}
    r = _classify(main, payload)
    assert r.returncode == 0
    assert r.stdout.split() == ["ok=1", "merge=1"]


@requires_git
def test_changed_files_isolated_per_worktree(tmp_path: Path):
    # the motivating defect: a worktree's staged change is invisible to main. Once ROOT=W, the
    # gate reads the worktree's staged files (and main's do not leak in).
    main = tmp_path / "repo"
    _init_repo(main)
    wt = tmp_path / "repo-wt"
    _rg(["worktree", "add", "-b", "feature/x", str(wt)], main)
    (wt / "new.py").write_text("x = 1\n", encoding="utf-8")
    _rg(["add", "new.py"], wt)  # stage inside the worktree
    assert "new.py" in fgc._changed_files(wt)  # W sees its own staged change
    assert "new.py" not in fgc._changed_files(main)  # main does not
