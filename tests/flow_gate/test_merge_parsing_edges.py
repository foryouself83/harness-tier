import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.flow_gate_check as fgc
from tests.flow_gate._helpers import (
    _doc_style_host,
    _init_repo,
    _rg,
    _run_runner,
    requires_bash_git,
)


def test_merge_parsing_anchors_on_the_git_that_owns_the_subcommand():
    # splitting at the first " merge" anywhere lands inside a quoted argument, so the operand
    # region starts mid-string and shlex raises — the merge-strategy verdict then never runs,
    # and that verdict is one of the three fail-CLOSED exceptions (Invariant #1 Exception 3).
    command = 'echo "starting the merge" && git merge --no-ff origin/stage'
    assert fgc.parse_merge_command(command) == ({"--no-ff"}, "origin/stage")


QUOTED_MERGE = 'echo "run git -C /evil merge feature/x" && git -C /wt merge --no-ff origin/stage'


def test_merge_parsing_ignores_a_git_merge_quoted_inside_an_argument():
    # a full invocation quoted in a message is text, not a merge. Read against the raw string it
    # is found first, so the operand region starts mid-quote and shlex raises "No closing
    # quotation" — and the strategy verdict, one of the three fail-CLOSED exceptions, never runs.
    assert fgc.parse_merge_command(QUOTED_MERGE) == ({"--no-ff"}, "origin/stage")


def test_merge_dash_c_reads_the_real_invocation_not_a_quoted_one():
    # the directory decides whether the merge is judged against THIS root at all, so taking it
    # from anywhere but the real invocation's own options region switches the gate off for a
    # merge that is happening right here (`_points_elsewhere` → exit 0).
    assert fgc._merge_dash_c(QUOTED_MERGE) == "/wt"
    assert fgc._merge_dash_c("git merge --no-ff dev") is None


def test_merge_dash_c_ignores_a_dash_c_inside_a_quoted_option_value():
    # `-C` is a directory only as git's own option. Taking one out of a quoted VALUE makes
    # _points_elsewhere call this root foreign and skip the merge-strategy verdict — one of the
    # three fail-CLOSED exceptions, switched off by a pager setting.
    assert fgc._merge_dash_c('git -c core.pager="less -C /tmp" merge --no-ff origin/stage') is None
    assert fgc._merge_dash_c('git -c core.pager="less -C /tmp" -C /wt merge --no-ff x') == "/wt"


def test_points_elsewhere_prefers_dash_c_over_a_leading_cd():
    # git's own -C overrides the cwd, so a command that does both runs the merge in the -C tree.
    root = Path("/a")
    assert fgc._points_elsewhere("cd /a && git -C /b merge --no-ff x", root) is True
    assert fgc._points_elsewhere("cd /b && git -C /a merge --no-ff x", root) is False


def test_target_from_command_ignores_a_switch_that_is_only_text():
    # a `git switch` quoted in a message, written in a comment, or sitting in a heredoc body is
    # not a switch. Adopting its branch judges the merge against a flow nobody ran, and the
    # merge-strategy verdict is fail-CLOSED.
    assert (
        fgc._target_from_command("git commit -F - <<EOF\ngit switch main\nEOF\ngit merge x") is None
    )
    assert fgc._target_from_command("# git switch main\ngit merge --no-ff feature/x") is None
    assert fgc._target_from_command("git switch dev && git merge --no-ff feature/x") == "dev"


def test_target_from_command_reads_a_quoted_switch_operand():
    # the operand is sliced from the raw string, not the mask — a quoted branch name must survive
    # its quotes, or the target is a run of NULs that matches no rule and the merge walks through.
    assert (
        fgc._target_from_command("git checkout 'release/1.0' && git merge --no-ff x")
        == "release/1.0"
    )
    assert fgc._target_from_command('git switch "my branch" && git merge --no-ff x') == "my branch"


@requires_bash_git
def test_runner_lets_a_command_that_only_mentions_committing_through(tmp_path: Path):
    """The tree is dirty and unclassified, so a real commit here is denied — which is what makes
    this a test rather than a tautology. The gate reads the command, finds no invocation, and
    says so; the runner must act on that answer rather than on the pre-filter that spawned it."""
    main = tmp_path / "main"
    _init_repo(main)
    (main / ".claude" / "harness-tier" / "config").mkdir(parents=True)
    (main / ".claude" / "harness-tier" / "config" / "flow-config.yaml").write_text(
        "modules: []\n", encoding="utf-8"
    )
    assert _run_runner(main, "git commit -m x").returncode == 2  # the control
    for mention in (
        'git log --oneline && echo "now commit"',
        'grep -rn "git commit" scripts/',
        "git log -1 --format=%s  # merge check",
    ):
        r = _run_runner(main, mention)
        assert r.returncode == 0, (mention, r.returncode, r.stdout, r.stderr)


@requires_bash_git
def test_runner_reads_every_line_of_a_multi_line_verdict(tmp_path: Path):
    """`$(…)` eats the trailing CRLF, so the LAST verdict line arrives clean and every earlier
    one carries its CR. A `case` arm compares strings: unstripped, `merge=1` on line three
    matches nothing and the merge-strategy check — one of the three fail-CLOSED exceptions —
    is never spawned. The stub stands in for flow_gate_check so the verdict is fixed and the
    merge check's deny is the only thing under test."""
    main = tmp_path / "main"
    _init_repo(main)
    (main / ".claude" / "harness-tier" / "config").mkdir(parents=True)
    (main / ".claude" / "harness-tier" / "config" / "flow-config.yaml").write_text(
        "modules: []\n", encoding="utf-8"
    )
    plugin = tmp_path / "plugin"
    (plugin / "scripts").mkdir(parents=True)
    # Written as BYTES so the CRLF is the same on every platform — a text-mode write would add
    # its own CR on Windows and none on Linux, and the test would stop being about the CR.
    verdict = b"\r\n".join([b"ok=1", b"commit=1", b"merge=1", b"worktree="]) + b"\r\n"
    (plugin / "scripts" / "flow_gate_check.py").write_text(
        "import sys\n"
        "if '--merge-check' in sys.argv:\n"
        "    sys.stderr.buffer.write('merge 전략 위반'.encode())\n"
        "    sys.exit(2)\n"
        "if '--classify' in sys.argv:\n"
        f"    sys.stdout.buffer.write({verdict!r})\n",
        encoding="utf-8",
    )
    r = _run_runner(main, "git merge --no-ff dev && git commit -m x", plugin_root=plugin)
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "merge 전략 위반" in (r.stdout + r.stderr)


@requires_bash_git
def test_a_merge_check_that_did_not_run_says_nothing(tmp_path: Path):
    """The merge stage reads STDERR for its reason, so whatever a non-zero exit leaves there
    is the interpreter's and not the gate's. Passed through it reads as a verdict, and on a
    host whose script copy is broken every commit would carry a traceback."""
    main = tmp_path / "main"
    _init_repo(main)
    (main / ".claude" / "harness-tier" / "config").mkdir(parents=True)
    (main / ".claude" / "harness-tier" / "config" / "flow-config.yaml").write_text(
        "modules: []\n", encoding="utf-8"
    )
    plugin = tmp_path / "plugin"
    (plugin / "scripts").mkdir(parents=True)
    (plugin / "scripts" / "flow_gate_check.py").write_text(
        "import sys\n"
        "if '--merge-check' in sys.argv:\n"
        "    sys.stderr.write('TRACEBACK-NOISE')\n"
        "    sys.exit(1)\n"
        "if '--classify' in sys.argv:\n"
        "    sys.exit(3)\n",
        encoding="utf-8",
    )
    r = _run_runner(main, "git merge --no-ff dev", plugin_root=plugin)
    assert "TRACEBACK-NOISE" not in (r.stdout + r.stderr), (r.stdout, r.stderr)


@requires_bash_git
@pytest.mark.parametrize(
    "command",
    ["git merge --no-ff dev", "git merge --squash dev && git commit -m x"],
    ids=["merge-only", "merge-then-commit"],
)
def test_a_gate_that_cannot_classify_still_inspects_the_merge(tmp_path: Path, command: str):
    """No verdict is an internal error, and the fallback below it treats the command as a
    commit — but a merge-strategy violation is decided from the command string alone and is one
    of the three things this gate may never fail open on. Reached only through `_is_merge`, the
    check would be skipped for exactly the command it exists to judge. The stub answers nothing
    for `--classify` and denies for `--merge-check`, so the deny is the only thing under test."""
    main = tmp_path / "main"
    _init_repo(main)
    (main / ".claude" / "harness-tier" / "config").mkdir(parents=True)
    (main / ".claude" / "harness-tier" / "config" / "flow-config.yaml").write_text(
        "modules: []\n", encoding="utf-8"
    )
    plugin = tmp_path / "plugin"
    (plugin / "scripts").mkdir(parents=True)
    (plugin / "scripts" / "flow_gate_check.py").write_text(
        "import sys\n"
        "if '--merge-check' in sys.argv:\n"
        "    sys.stderr.buffer.write('merge 전략 위반'.encode())\n"
        "    sys.exit(2)\n"
        "if '--classify' in sys.argv:\n"
        "    sys.exit(3)\n",
        encoding="utf-8",
    )
    r = _run_runner(main, command, plugin_root=plugin)
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)
    assert "merge 전략 위반" in (r.stdout + r.stderr)


# `git merge` reads the whole command, not the first match in it. Each of these was a
# strategy verdict that silently did not run, and that verdict is one of the three this
# gate may never fail open on.
MERGE_PARSES = [
    # the plain shape
    ("git merge feature/x", [(set(), "feature/x")]),
    # a continued line is one command; shlex reads the backslash-newline as a word otherwise
    ("git merge \\\n  feature/x", [(set(), "feature/x")]),
    # a closing paren ends the words, or it rides along in the branch name and matches no rule
    ("(git switch stage && git merge dev)", [(set(), "dev")]),
    ("git switch stage && (git merge dev)", [(set(), "dev")]),
    # the extents come from the mask, so an executed span's blanked delimiter must not reach
    # shlex in the raw slice
    ("bash -c 'git merge feature/x'", [(set(), "feature/x")]),
    # a merge naming no source in front of a real one left the rest unjudged
    ("git merge --abort && git merge feature/a", [(set(), "feature/a")]),
    # every merge, in order — the checker judges each against its own rule
    (
        "git merge --squash feature/a && git merge feature/b",
        [({"--squash"}, "feature/a"), (set(), "feature/b")],
    ),
    # the merge a builtin runs later, and the one an interpreter is handed past a `--`
    ("trap 'git merge feature/x' EXIT", [(set(), "feature/x")]),
    ('bash -c -- "git merge feature/x"', [(set(), "feature/x")]),
]


@pytest.mark.parametrize("command,expected", MERGE_PARSES, ids=[c for c, _ in MERGE_PARSES])
def test_every_merge_in_a_command_is_parsed(command: str, expected: list):
    assert fgc.parse_merge_commands(command) == expected


def test_doc_style_gate_honours_the_configured_scope(tmp_path: Path):
    """`exclude` written for CI governs the hook arm too — one reader, both arms.

    A hook that warned about a file CI never looks at would report a violation nobody can
    resolve, since the file is out of scope everywhere the verdict is issued.
    """
    root = _doc_style_host(
        tmp_path,
        "The runner used to spawn twice.\n",
        config="doc_style:\n  enable: true\n  paths: ['**/*.md']\n  exclude: ['doc.md']\n",
    )
    assert fgc.doc_style_gate(root, ["doc-style"]) is None


def test_doc_style_gate_names_the_path_not_the_basename(tmp_path: Path):
    # Every skill file is called SKILL.md; a basename cannot say which one.
    root = _doc_style_host(tmp_path, "clean\n")
    nested = root / "skills" / "flow"
    nested.mkdir(parents=True)
    (nested / "SKILL.md").write_text("The runner used to spawn twice.\n", encoding="utf-8")
    _rg(["add", "skills/flow/SKILL.md"], root)
    report = fgc.doc_style_gate(root, ["doc-style"])
    assert report and "skills/flow/SKILL.md" in report


def test_runtime_notices_are_silent_under_dryrun(tmp_path: Path, monkeypatch, capsys):
    """A dry run prints the commands it would issue and nothing else on stdout.

    The wiki stage guarded itself; doc-style did not, so a dry run in a doc_style repo wrote a
    systemMessage the runner never expects there.
    """
    root = _doc_style_host(tmp_path, "The runner used to spawn twice.\n")
    monkeypatch.setenv("HARNESS_PRECOMMIT_DRYRUN", "1")
    fgc._runtime_notices(root, ["wiki", "doc-style"])
    assert capsys.readouterr().out == ""


def test_a_sibling_that_raises_at_import_does_not_take_the_gate_down(tmp_path: Path):
    """`except ImportError` was too narrow.

    doc_style_check.py runs on the host's python, whose floor is 3.8. A module-level expression
    that python rejects raises TypeError, not ImportError — and an unguarded one aborts
    flow_gate_check.py itself, which exits 1 with an empty stdout. precommit-runner.sh denies
    only on exit 2, so the commit is allowed: Invariant #1's fail-CLOSED block on an
    unclassified commit, off in silence.
    """
    repo = Path(__file__).resolve().parent.parent.parent
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    for name in ("flow_gate_check.py", "_harness_paths.py", "wiki_graph.py"):
        shutil.copy(repo / "scripts" / name, scripts_dir / name)
    (scripts_dir / "doc_style_check.py").write_text(
        "raise TypeError('a module-level expression this python rejects')\n",
        encoding="utf-8",
    )
    host = tmp_path / "host"
    cfg = host / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    shutil.copy(repo / "flow-tiers.yaml", cfg / "flow-tiers.yaml")
    r = subprocess.run(
        [sys.executable, str(scripts_dir / "flow_gate_check.py")],
        env={**os.environ, "CLAUDE_PROJECT_DIR": str(host), "PYTHONIOENCODING": "utf-8"},
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert r.returncode == fgc.BLOCK_EXIT_CODE, f"rc={r.returncode} err={r.stderr!r}"
    assert "분류되지 않은 커밋" in r.stdout


def test_doc_style_gate_fails_open_on_a_config_that_does_not_parse(tmp_path: Path):
    """CI turns a malformed flow-config.yaml into a red job; the commit gate may not.

    doc_style_check raises a plain ValueError so this `except Exception` still catches it. A
    SystemExit would pass straight through and abort the gate script, which exits 1 with an
    empty stdout — the runner then allows an unclassified commit (Invariant #1).
    """
    root = _doc_style_host(tmp_path, "The runner used to spawn twice.\n", config="doc_style: [\n")
    assert fgc.doc_style_gate(root, ["doc-style"]) is None
