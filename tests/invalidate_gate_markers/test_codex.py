"""Codex edits arrive as apply_patch (or a patch run through Bash); both void the evidence,
a plain Bash does not."""

import json
import os
import subprocess
from pathlib import Path

import pytest

from tests.invalidate_gate_markers._helpers import BASH, MARKERS, SCRIPT, repo, worktree_of

pytestmark = pytest.mark.skipif(BASH is None, reason="a repo-visible bash is required")


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    flow = repo / ".claude/harness-tier/.flow"
    flow.mkdir(parents=True)
    for m in MARKERS:
        (flow / m).write_text("", encoding="utf-8")
    return repo


def _run(repo: Path, tool: str, command: str) -> subprocess.CompletedProcess:
    payload = {
        "cwd": str(repo),
        "hook_event_name": "PostToolUse",
        "tool_name": tool,
        "tool_input": {"command": command},
    }
    return subprocess.run(
        [BASH, SCRIPT.as_posix(), "--harness", "codex"],
        input=json.dumps(payload).encode(),
        capture_output=True,
        env={"PATH": os.environ["PATH"]},
    )


def test_apply_patch_voids(tmp_path):
    repo = _repo(tmp_path)
    _run(repo, "apply_patch", "*** Begin Patch\n*** Update File: a.txt\n*** End Patch")
    assert not any((repo / ".claude/harness-tier/.flow" / m).exists() for m in MARKERS)


def test_bash_patch_voids(tmp_path):
    repo = _repo(tmp_path)
    command = "apply_patch <<'EOF'\n*** Begin Patch\n*** Update File: a.txt\n*** End Patch\nEOF"
    _run(repo, "Bash", command)
    assert not any((repo / ".claude/harness-tier/.flow" / m).exists() for m in MARKERS)


def test_plain_bash_keeps_evidence(tmp_path):
    repo = _repo(tmp_path)
    _run(repo, "Bash", "git add -A")
    assert all((repo / ".claude/harness-tier/.flow" / m).exists() for m in MARKERS)


def test_evidence_dir_edit_is_ignored(tmp_path):
    repo = _repo(tmp_path)
    command = "*** Begin Patch\n*** Add File: .claude/harness-tier/.flow/x\n*** End Patch"
    _run(repo, "apply_patch", command)
    assert all((repo / ".claude/harness-tier/.flow" / m).exists() for m in MARKERS)


def test_oversized_payload_still_voids_via_the_cwd_fallback(tmp_path):
    """Past the shared 64 KB `head -c` cap the payload arrives truncated, so hook_io.py's JSON
    parse fails and it emits nothing — `cwd` sits ahead of `tool_input` in every measured Codex
    payload and survives the cut, so the codex branch falls back to voiding that repo whole."""
    repo = _repo(tmp_path)
    padding = "x" * 100_000
    command = f"*** Begin Patch\n*** Update File: a.txt\n+{padding}\n*** End Patch"
    run = _run(repo, "apply_patch", command)
    assert len(json.dumps({"tool_input": {"command": command}})) > 65536
    assert run.returncode == 0
    assert not any((repo / ".claude/harness-tier/.flow" / m).exists() for m in MARKERS)


def test_spaced_json_voids_too(tmp_path):
    """`json.dumps(indent=2)` puts a space after every colon — the prefilter must not depend
    on the compact spelling a hand-built payload happens to use."""
    repo = _repo(tmp_path)
    payload = {
        "cwd": str(repo),
        "hook_event_name": "PostToolUse",
        "tool_name": "apply_patch",
        "tool_input": {"command": "*** Begin Patch\n*** Update File: a.txt\n*** End Patch"},
    }
    subprocess.run(
        [BASH, SCRIPT.as_posix(), "--harness", "codex"],
        input=json.dumps(payload, indent=2).encode(),
        capture_output=True,
        env={"PATH": os.environ["PATH"]},
    )
    assert not any((repo / ".claude/harness-tier/.flow" / m).exists() for m in MARKERS)


def test_oversized_non_ascii_payload_is_measured_in_bytes(tmp_path):
    """Codex sends raw UTF-8, and under a UTF-8 locale `${#var}` counts characters: a patch of
    Korean text far past the 64 KB byte cap holds fewer than 65536 characters, and a character
    count reads it as whole."""
    repo = _repo(tmp_path)
    command = f"*** Begin Patch\n*** Update File: a.txt\n+{'가' * 30_000}\n*** End Patch"
    payload = {
        "cwd": str(repo),
        "hook_event_name": "PostToolUse",
        "tool_name": "apply_patch",
        "tool_input": {"command": command},
    }
    raw = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    assert len(raw) > 65536 > len(raw.decode("utf-8"))
    run = subprocess.run(
        [BASH, SCRIPT.as_posix(), "--harness", "codex"],
        input=raw,
        capture_output=True,
        # C.UTF-8 exists on both Git Bash and a stock Ubuntu; en_US.UTF-8 is not always generated.
        env={"PATH": os.environ["PATH"], "LANG": "C.UTF-8", "LC_ALL": "C.UTF-8"},
    )
    assert run.returncode == 0, run.stderr
    assert not any((repo / ".claude/harness-tier/.flow" / m).exists() for m in MARKERS)


def _run_raw(raw: bytes) -> subprocess.CompletedProcess:
    return subprocess.run(
        [BASH, SCRIPT.as_posix(), "--harness", "codex"],
        input=raw,
        capture_output=True,
        env={"PATH": os.environ["PATH"]},
    )


def test_a_patch_payload_without_tool_input_command_voids_via_the_cwd_fallback(tmp_path):
    """hook_io.py reads only `tool_input.command`; a patch under any other key names no path."""
    repo = _repo(tmp_path)
    payload = {
        "cwd": str(repo),
        "hook_event_name": "PostToolUse",
        "tool_name": "apply_patch",
        "tool_input": {"input": "*** Begin Patch\n*** Update File: a.txt\n*** End Patch"},
    }
    run = _run_raw(json.dumps(payload).encode())
    assert run.returncode == 0, run.stderr
    assert not any((repo / ".claude/harness-tier/.flow" / m).exists() for m in MARKERS)


def test_an_undecodable_patch_payload_under_the_cap_voids_via_the_cwd_fallback(tmp_path):
    repo = _repo(tmp_path)
    raw = json.dumps({"cwd": str(repo), "tool_name": "apply_patch"}).encode()[:-1] + b", oops"
    run = _run_raw(raw)
    assert run.returncode == 0, run.stderr
    assert not any((repo / ".claude/harness-tier/.flow" / m).exists() for m in MARKERS)


def test_a_placed_patch_outside_any_repo_does_not_fall_back_to_cwd(tmp_path):
    """The fallback is for a patch with no path; one whose path lies outside every repo was
    placed, and the cwd's evidence is not what it edited."""
    repo = _repo(tmp_path)
    outside = (tmp_path / "scratch" / "a.txt").as_posix()
    _run(repo, "apply_patch", f"*** Begin Patch\n*** Update File: {outside}\n*** End Patch")
    assert all((repo / ".claude/harness-tier/.flow" / m).exists() for m in MARKERS)


def _voided(repo: Path) -> bool:
    return not any((repo / ".claude/harness-tier/.flow" / m).exists() for m in MARKERS)


def _run_payload(repo: Path, payload: dict, script: Path = SCRIPT) -> None:
    run = subprocess.run(
        [BASH, script.as_posix(), "--harness", "codex"],
        input=json.dumps({"cwd": str(repo), "hook_event_name": "PostToolUse", **payload}).encode(),
        capture_output=True,
        env={"PATH": os.environ["PATH"]},
    )
    assert run.returncode == 0, run.stderr


ENVELOPE = "*** Begin Patch\n*** Update File: a.txt\n@@\n-a\n+b\n*** End Patch"


def test_a_bash_read_whose_output_holds_a_patch_keeps_evidence(tmp_path):
    """Codex reads files through Bash: `git diff` over a file holding a patch is not an edit, and
    voiding here would make review and doc-sync void each other on every read."""
    repo = _repo(tmp_path)
    _run_payload(
        repo,
        {
            "tool_name": "Bash",
            "tool_input": {"command": "git diff HEAD"},
            "tool_response": f"+{ENVELOPE}",
        },
    )
    assert not _voided(repo)


def test_a_bash_command_quoting_the_marker_keeps_evidence(tmp_path):
    repo = _repo(tmp_path)
    command = 'grep -n "*** Begin Patch" hooks/invalidate-gate-markers.sh'
    _run_payload(repo, {"tool_name": "Bash", "tool_input": {"command": command}})
    assert not _voided(repo)


def test_a_bash_patch_envelope_without_a_parsable_header_voids(tmp_path):
    repo = _repo(tmp_path)
    command = "apply_patch <<'EOF'\n*** Begin Patch\n*** Frobnicate: a.txt\n*** End Patch\nEOF"
    _run_payload(repo, {"tool_name": "Bash", "tool_input": {"command": command}})
    assert _voided(repo)


def test_an_apply_patch_with_no_headers_voids(tmp_path):
    repo = _repo(tmp_path)
    command = "*** Begin Patch\n*** End Patch"
    _run_payload(repo, {"tool_name": "apply_patch", "tool_input": {"command": command}})
    assert _voided(repo)


def _hook_without_hook_io(tmp_path: Path) -> Path:
    """The hook alone in a tree that holds no hook_io.py: python3 runs and fails to open it."""
    hooks = tmp_path / "bare" / "hooks"
    hooks.mkdir(parents=True)
    copy = hooks / SCRIPT.name
    copy.write_bytes(SCRIPT.read_bytes())
    return copy


def test_an_unavailable_hook_io_voids_a_prefiltered_payload(tmp_path):
    repo = _repo(tmp_path)
    command = "*** Begin Patch\n*** Update File: a.txt\n*** End Patch"
    payload = {"tool_name": "apply_patch", "tool_input": {"command": command}}
    _run_payload(repo, payload, _hook_without_hook_io(tmp_path))
    assert _voided(repo)


def test_an_unavailable_hook_io_leaves_a_payload_the_prefilter_rejects(tmp_path):
    repo = _repo(tmp_path)
    payload = {"tool_name": "Bash", "tool_input": {"command": "git add -A"}}
    _run_payload(repo, payload, _hook_without_hook_io(tmp_path))
    assert not _voided(repo)


def test_an_oversized_bash_patch_cut_before_its_end_keeps_evidence(tmp_path):
    """Cut at the read cap, a Bash command's surviving text holds no whole envelope, and that
    cannot be told from a command quoting the marker — so Bash keeps, apply_patch voids."""
    repo = _repo(tmp_path)
    command = "apply_patch <<'EOF'\n*** Begin Patch\n*** Update File: a.txt\n+" + "x" * 100_000
    command += "\n*** End Patch\nEOF"
    _run_payload(repo, {"tool_name": "Bash", "tool_input": {"command": command}})
    assert not _voided(repo)


def test_a_worktree_edit_also_voids_the_session_cwd_view_of_the_same_repo(tmp_path):
    """The gate falls back to the session's tree when it cannot name a commit's worktree, so an
    edit in a linked worktree voids the cwd root's evidence too, as the Claude path does."""
    main = repo(tmp_path / "main")
    wt = worktree_of(main, tmp_path / "wt")
    edited = (wt / "a.txt").as_posix()
    command = f"*** Begin Patch\n*** Update File: {edited}\n*** End Patch"
    _run_payload(main, {"tool_name": "apply_patch", "tool_input": {"command": command}})
    assert _voided(wt) and _voided(main)


def test_a_worktree_edit_voids_the_repo_of_a_subdirectory_cwd(tmp_path):
    main = repo(tmp_path / "main")
    sub = main / "sub" / "deep"
    sub.mkdir(parents=True)
    wt = worktree_of(main, tmp_path / "wt")
    edited = (wt / "a.txt").as_posix()
    command = f"*** Begin Patch\n*** Update File: {edited}\n*** End Patch"
    _run_payload(sub, {"tool_name": "apply_patch", "tool_input": {"command": command}})
    assert _voided(wt) and _voided(main)


def test_an_edit_in_another_repo_keeps_the_session_cwd_evidence(tmp_path):
    main = repo(tmp_path / "main")
    other = repo(tmp_path / "other")
    edited = (other / "a.txt").as_posix()
    command = f"*** Begin Patch\n*** Update File: {edited}\n*** End Patch"
    _run_payload(main, {"tool_name": "apply_patch", "tool_input": {"command": command}})
    assert _voided(other) and not _voided(main)
