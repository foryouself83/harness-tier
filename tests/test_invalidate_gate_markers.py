"""The PostToolUse hook that voids the review/doc-sync evidence on an edit.

Deleting is the safe direction: a marker that should have survived costs a re-run, while one
that should have gone lets an unreviewed commit through. So every case this hook cannot decide
deletes, and what is spared is a path with no evidence above it. Everything about the hook itself is
FAIL-OPEN — no project dir, no evidence dir, an unreadable payload: exit 0, markers untouched,
the gate keeps whatever answer it already had.
"""

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "hooks" / "invalidate-gate-markers.sh"
GIT_BASH = (r"C:\Program Files\Git\bin\bash.exe", r"C:\Program Files\Git\usr\bin\bash.exe")


def _repo_bash() -> str | None:
    """A bash that can actually see the repo path (Git Bash on Windows / native bash on POSIX).

    PATH order is the shell's, so on Windows a bare `bash` is usually the System32 WSL stub,
    which cannot open a C:/… path — probe the candidate against a file that must exist and fall
    back to the known Git Bash locations. None → no usable bash, and these tests skip rather
    than report a green they never earned."""
    probe = f"{REPO.as_posix()}/hooks/invalidate-gate-markers.sh"
    which = shutil.which("bash")
    for bash in (which, *GIT_BASH):
        if not bash or not (bash == which or Path(bash).exists()):
            continue
        try:
            probe_run = subprocess.run(
                [bash, "-c", f'test -f "{probe}"'], capture_output=True, timeout=10
            )
            if probe_run.returncode == 0:  # captured: a WSL stub's complaint is not test output
                return bash
        except Exception:
            continue
    return None


BASH = _repo_bash()
pytestmark = pytest.mark.skipif(BASH is None, reason="a repo-visible bash is required")

MARKERS = ("review.done", "doc-sync.done")
KEPT = ("bump.done", "security.done")


def payload(file_path: str | None, key: str = "file_path") -> str:
    body: dict[str, object] = {"hook_event_name": "PostToolUse", "tool_name": "Edit"}
    if file_path is not None:
        body["tool_input"] = {key: file_path}
    return json.dumps(body)


def repo(root: Path, *, evidence: bool = True) -> Path:
    """A tree the gate would judge: a repo root, and the evidence a gate run left in it. `.git`
    is what bounds the hook's walk, so a fixture without one is not a tree at all — and
    `evidence=False` means no evidence dir at all, not an empty one: an empty one stops a walk
    that is looking for evidence dirs, which is the very thing some of these tests must see."""
    (root / ".git").mkdir(parents=True, exist_ok=True)
    if evidence:
        flow(root).mkdir(parents=True, exist_ok=True)
        for name in MARKERS:
            (flow(root) / name).touch()
    return root


def worktree_of(main: Path, root: Path, *, gitdir: str | None = None, eol: str = chr(10)) -> Path:
    """A linked worktree: its `.git` is a FILE pointing into the main repo's common dir. That
    pointer is the only thing separating two views of one repo from two repos, and the hook has
    to void both views — the gate cannot always tell which one a commit belongs to.

    `gitdir` overrides the pointer's spelling (git writes a relative one under
    `worktree.useRelativePaths`), and `eol` its ending — a file that stops without one is still
    a file git wrote through."""
    root.mkdir(parents=True, exist_ok=True)
    target = gitdir or f"{main.as_posix()}/.git/worktrees/{root.name}"
    (root / ".git").write_text(f"gitdir: {target}{eol}", encoding="utf-8")
    flow(root).mkdir(parents=True, exist_ok=True)
    for name in MARKERS:
        (flow(root) / name).touch()
    return root


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = repo(tmp_path / "project")
    for name in KEPT:
        (flow(root) / name).touch()
    return root


def run(project: Path | None, stdin: str) -> subprocess.CompletedProcess[str]:
    # The real environment minus the one variable under test: a hand-built env drops what bash
    # itself needs on Windows (SYSTEMROOT, TEMP), and the hook would fail for a reason no
    # assertion here is about.
    env = dict(os.environ)
    env.pop("CLAUDE_PROJECT_DIR", None)
    if project is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project)
    return subprocess.run(
        [BASH, str(SCRIPT)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def flow(project: Path) -> Path:
    return project / ".claude" / "harness-tier" / ".flow"


def test_edit_inside_the_project_voids_both_markers(project: Path):
    out = run(project, payload(str(project / "src" / "app.py")))
    assert out.returncode == 0, out.stderr
    for name in MARKERS:
        assert not (flow(project) / name).exists(), (
            f"{name} survived an edit — a fix made after the gate passed would commit on it"
        )


def test_the_other_gates_markers_are_left_alone(project: Path):
    run(project, payload(str(project / "src" / "app.py")))
    for name in KEPT:
        assert (flow(project) / name).exists(), (
            f"{name} was deleted: bump/security are promotion-time decisions on a clean tree, "
            f"and re-asking for them is friction this hook never earns"
        )


def test_an_edit_outside_the_project_is_not_an_edit_to_this_repo(project: Path, tmp_path: Path):
    """Nothing above a scratchpad file is a harness project, so there is no evidence to void."""
    run(project, payload(str(tmp_path / "scratchpad" / "note.md")))
    for name in MARKERS:
        assert (flow(project) / name).exists(), (
            f"{name} was voided by a scratchpad write — every temp file would cost a re-review"
        )


def test_a_write_into_the_evidence_dir_does_not_void_the_evidence(project: Path):
    run(project, payload(str(flow(project) / "tier")))
    for name in MARKERS:
        assert (flow(project) / name).exists(), f"{name} was voided by a write to the evidence dir"


def test_a_backslash_spelled_write_into_the_evidence_dir_is_still_exempt(project: Path):
    """The exemption is a glob, and JSON doubles every backslash: converted one for one, the path
    arrives with `//` between each segment, which the filesystem swallows and no glob matches."""
    win = str(flow(project) / "tier").replace("/", chr(92))
    run(project, json.dumps({"tool_input": {"file_path": win}}))
    for name in MARKERS:
        assert (flow(project) / name).exists(), f"{name} was voided by a write to the evidence dir"


def test_a_payload_without_a_path_voids(project: Path):
    """Cannot tell where the edit landed → delete. The alternative keeps a marker over an edit
    nobody has seen, which is the one direction this hook may never fail in."""
    run(project, payload(None))
    for name in MARKERS:
        assert not (flow(project) / name).exists(), f"{name} survived an undecidable payload"


def test_an_unparseable_payload_voids(project: Path):
    run(project, "not json at all")
    for name in MARKERS:
        assert not (flow(project) / name).exists(), f"{name} survived an unparseable payload"


def test_a_windows_spelled_path_still_names_its_own_tree(project: Path, tmp_path: Path):
    """The payload carries the OS's own spelling: on Windows a backslash path, JSON-escaped.
    Unconverted, no separator is a separator — the hook cannot place the edit, falls back to the
    session's project dir, and voids the wrong tree while the edited one keeps its evidence.
    Asserting against the project dir alone cannot see that: the fallback lands there too."""
    worktree = repo(tmp_path / "project-feature")
    wt_flow = flow(worktree)

    win = str(worktree).replace("/", chr(92)) + chr(92) + "src" + chr(92) + "app.py"
    run(project, json.dumps({"tool_input": {"file_path": win}}))

    for name in MARKERS:
        assert not (wt_flow / name).exists(), f"{name} survived a backslash-spelled path"
        assert (flow(project) / name).exists(), f"{name} died: the edit landed in the wrong tree"


def test_the_first_path_in_the_payload_is_the_one_that_was_edited(project: Path, tmp_path: Path):
    """`tool_response` echoes a path of its own after `tool_input`. Reading the last one lets a
    response field decide, and a response naming somewhere else would spare the markers."""
    body = {
        "tool_input": {"file_path": str(project / "src" / "app.py")},
        "tool_response": {"file_path": str(tmp_path / "elsewhere" / "app.py")},
    }
    run(project, json.dumps(body))
    for name in MARKERS:
        assert not (flow(project) / name).exists(), f"{name} survived: tool_response decided"


def test_an_edit_in_a_worktree_voids_the_worktree_s_own_evidence(project: Path, tmp_path: Path):
    """The gate re-points ROOT to the worktree a `git -C <wt> commit` names, so the markers it
    reads there are the worktree's. A hook that only knew CLAUDE_PROJECT_DIR would leave exactly
    those standing — the review passes in the worktree, the fix lands there, and the commit the
    skill itself prescribes goes through on evidence nobody re-earned."""
    worktree = worktree_of(project, tmp_path / "project-feature")

    run(project, payload(str(worktree / "src" / "app.py")))

    for name in MARKERS:
        assert not (flow(worktree) / name).exists(), f"{name} survived an edit in its own worktree"


def test_an_edit_in_a_worktree_also_voids_the_tree_the_gate_falls_back_to(
    project: Path, tmp_path: Path
):
    """The gate names the worktree from the branch it is on; a detached HEAD, or a branch matching
    no worktree entry, sends it back to the session's project dir instead (Invariant 6 keeps that
    uncertainty pointed at main). Both trees are therefore possible answers, and voiding only the
    edited one leaves the gate reading a marker the edit never reached."""
    worktree = worktree_of(project, tmp_path / "project-feature")

    run(project, payload(str(worktree / "src" / "app.py")))

    for name in MARKERS:
        assert not (flow(project) / name).exists(), (
            f"{name} stands in the tree the gate falls back to, over an edit made in its own repo"
        )


def test_a_sibling_directory_is_not_inside_the_project(project: Path, tmp_path: Path):
    """`…/project-feature` starts with `…/project` as a string. Prefix matching would call it
    inside and void the wrong tree's evidence."""
    sibling = repo(tmp_path / "project-feature")
    run(project, payload(str(sibling / "src" / "app.py")))
    for name in MARKERS:
        assert (flow(project) / name).exists(), f"{name} was voided by an edit in a sibling repo"


def test_a_notebook_edit_is_an_edit(project: Path, tmp_path: Path):
    """`NotebookEdit` spells it `notebook_path`. Unread, it is a payload with no path at all: the
    session's evidence dies for an edit that was not in it, and the edited tree keeps evidence
    the edit outdated — both directions wrong at once."""
    worktree = repo(tmp_path / "project-feature")

    run(project, payload(str(worktree / "nb" / "analysis.ipynb"), key="notebook_path"))

    for name in MARKERS:
        assert not (flow(worktree) / name).exists(), f"{name} survived a notebook edit"
        assert (flow(project) / name).exists(), f"{name} died: the notebook was placed elsewhere"


def test_a_nested_repo_answers_for_itself(project: Path):
    """A repo checked out inside another is its own tree with its own gate. The walk stops at the
    first root, so the outer project's evidence — which never covered these files — stands."""
    inner = repo(project / "vendor" / "sub")

    run(project, payload(str(inner / "src" / "lib.py")))

    for name in MARKERS:
        assert not (flow(inner) / name).exists(), f"{name} survived an edit in the repo it is for"
        assert (flow(project) / name).exists(), f"{name} died in the tree that never saw the file"


def test_a_project_above_this_one_keeps_its_evidence(tmp_path: Path):
    """Walking to the first evidence dir instead of the first repo root would reach out of the
    edited repo and reset a gate in a project that has nothing to do with the edit."""
    parent = repo(tmp_path / "parent")
    child = repo(tmp_path / "parent" / "child", evidence=False)

    run(child, payload(str(child / "src" / "app.py")))

    for name in MARKERS:
        assert (flow(parent) / name).exists(), f"{name} was voided from a project further up"


def test_a_tree_with_no_repo_root_voids_nothing(tmp_path: Path):
    """No root above the file, so no tree claims the edit — the gate that would read those
    markers does not exist."""
    loose = tmp_path / "loose"
    (loose / ".claude" / "harness-tier" / ".flow").mkdir(parents=True)
    for name in MARKERS:
        (loose / ".claude" / "harness-tier" / ".flow" / name).touch()

    out = run(None, payload(str(loose / "src" / "app.py")))

    assert out.returncode == 0
    for name in MARKERS:
        assert (flow(loose) / name).exists(), f"{name} was voided outside any repo"


def test_a_relative_worktree_pointer_still_names_one_repo(project: Path, tmp_path: Path):
    """`git worktree add --relative-paths` writes the pointer relative to the worktree, `..` and
    all. Compared as text it is a different repo; compared as directories it is the same one, and
    the difference decides whether the tree the gate falls back to keeps a stale marker."""
    worktree = worktree_of(
        project,
        tmp_path / "project-feature",
        gitdir=f"../{project.name}/.git/worktrees/project-feature",
    )

    run(project, payload(str(worktree / "src" / "app.py")))

    for name in MARKERS:
        assert not (flow(project) / name).exists(), (
            f"{name} stands in the fallback tree: a relative pointer read as another repo"
        )


def test_a_crlf_pointer_file_still_names_one_repo(project: Path, tmp_path: Path):
    """A pointer rewritten with CRLF leaves the path wearing a CR, so it names no directory at
    all — which proves nothing about the two roots being different, and the union has to happen
    anyway. It has to be the project's own pointer: on a worktree's, the CR sits inside the
    `/worktrees/…` the read strips off."""
    external = tmp_path / "gitdata"
    external.mkdir()
    (project / ".git").rmdir()
    (project / ".git").write_text(
        f"gitdir: {external.as_posix()}" + chr(13) + chr(10), encoding="utf-8"
    )
    worktree = worktree_of(
        project, tmp_path / "project-feature", gitdir=f"{external.as_posix()}/worktrees/wt"
    )

    run(project, payload(str(worktree / "src" / "app.py")))

    for name in MARKERS:
        assert not (flow(project) / name).exists(), f"{name} stands: a CR lost the repo"
        assert not (flow(worktree) / name).exists(), f"{name} stands in the edited tree"

    run(project, payload(str(worktree / "src" / "app.py")))

    for name in MARKERS:
        assert not (flow(project) / name).exists(), f"{name} stands: a CR lost the repo"
        assert not (flow(worktree) / name).exists(), f"{name} stands in the edited tree"

    run(project, payload(str(worktree / "src" / "app.py")))

    for name in MARKERS:
        assert not (flow(project) / name).exists(), f"{name} stands: the pointer was dropped"
        assert not (flow(worktree) / name).exists(), f"{name} stands in the edited tree"


def test_a_pointer_to_a_repo_that_moved_proves_nothing(project: Path, tmp_path: Path):
    """A worktree whose main repo was moved or renamed points at a directory that is gone until
    `git worktree repair` runs. Asking the filesystem whether two paths are the same answers no
    for a path that names nothing — and no is not a proof of difference. The gate meanwhile
    cannot resolve that worktree either, so it reads the project dir: the one tree that must not
    keep its marker."""
    worktree = worktree_of(
        project,
        tmp_path / "project-feature",
        gitdir=f"{tmp_path.as_posix()}/gone/.git/worktrees/wt",
    )

    run(project, payload(str(worktree / "src" / "app.py")))

    for name in MARKERS:
        assert not (flow(project) / name).exists(), (
            f"{name} stands: a pointer into nowhere was read as another repo"
        )


def test_a_session_opened_below_the_repo_root_is_still_this_tree(project: Path):
    """`/flow-init` installs the evidence where the session's project dir is, which need not be
    the repo root. That dir is no root, so nothing proves it a different repo — and its evidence
    is what the gate reads."""
    below = project / "services" / "api"
    flow(below).mkdir(parents=True)
    for name in MARKERS:
        (flow(below) / name).touch()

    run(below, payload(str(project / "src" / "app.py")))

    for name in MARKERS:
        assert not (flow(below) / name).exists(), f"{name} stands in the dir the gate reads"


def test_no_project_dir_is_quiet(tmp_path: Path):
    out = run(None, payload(str(tmp_path / "a.py")))
    assert out.returncode == 0 and out.stdout.strip() == ""


def test_no_evidence_dir_is_quiet(tmp_path: Path):
    (tmp_path / "bare").mkdir()
    out = run(tmp_path / "bare", payload(str(tmp_path / "bare" / "a.py")))
    assert out.returncode == 0 and out.stdout.strip() == ""


def test_it_says_so_only_when_it_actually_voided_something(project: Path):
    """Context on every edit would be noise; context on none leaves the agent re-running a gate
    it does not know it lost."""
    first = run(project, payload(str(project / "src" / "app.py")))
    assert "review" in json.loads(first.stdout)["hookSpecificOutput"]["additionalContext"]
    second = run(project, payload(str(project / "src" / "app.py")))
    assert second.stdout.strip() == "", "spoke again with no marker left to void"


HOOKS_JSON = REPO / "hooks" / "hooks.json"
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


def test_the_hook_is_registered_for_every_tool_that_edits_a_file():
    """A script nothing invokes is the gate silently off. The matcher is the whole registration:
    a tool missing from it edits files with the evidence left standing."""
    entries = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]["PostToolUse"]
    registered = [
        (e["matcher"], h["command"])
        for e in entries
        for h in e["hooks"]
        if SCRIPT.name in h["command"]
    ]
    assert registered, f"{SCRIPT.name} is registered in no PostToolUse entry"
    matcher, command = registered[0]
    named = set(matcher.split("|"))
    assert set(EDIT_TOOLS) <= named, f"{set(EDIT_TOOLS) - named} edit files but never void evidence"

    # A hook is a line of text naming a file: the name appearing in the command proves nothing
    # about the path resolving, and a command naming nothing runs nothing, silently.
    quoted = re.search(r'"([^"]*)"', command)
    assert quoted, f"the command names no quoted path: {command}"
    named_file = REPO / quoted.group(1).replace("${CLAUDE_PLUGIN_ROOT}/", "")
    assert named_file.is_file(), f"the registered command names {named_file}, which does not exist"
