"""What a Codex PostToolUse payload edited: apply_patch headers, or a patch run through Bash."""

import json
import subprocess
import sys
from pathlib import Path, PureWindowsPath

from scripts.harness.codex.hook_io import edited_paths

FIX = Path(__file__).parent / "fixtures"
HOOK_IO = Path(__file__).resolve().parents[3] / "scripts" / "harness" / "codex" / "hook_io.py"


def _load(name):
    return json.loads((FIX / name).read_text(encoding="utf-8"))


def _norm(paths):
    return [PureWindowsPath(p).as_posix() for p in paths]


def test_apply_patch_headers_resolve_against_cwd():
    assert _norm(edited_paths(_load("post_apply_patch.json"))) == [
        "C:/host/repo/note.txt",
        "C:/host/repo/src/a.py",
        "C:/host/repo/src/b.py",
        "C:/host/repo/old/c.py",
    ]


def test_patch_run_through_the_shell_counts():
    assert _norm(edited_paths(_load("post_bash_patch.json"))) == ["C:/host/repo/한글/파일.md"]


def test_plain_shell_command_edits_nothing():
    assert edited_paths(_load("post_bash_plain.json")) == []


def test_garbage_is_nothing():
    assert edited_paths({}) == [] and edited_paths({"tool_input": {"command": 5}}) == []


def test_bash_without_begin_patch_ignores_header_shaped_lines():
    """A Bash command whose output happens to contain a header-shaped line (e.g. printing a
    diff, catting a file) is not itself a patch: the `*** Begin Patch` marker is what tells
    this apart from apply_patch running through the shell, and `git add -A` alone
    can't pin that distinction since it contains no header-shaped line either way."""
    payload = {
        "cwd": "C:\\host\\repo",
        "tool_name": "Bash",
        "tool_input": {"command": "cat <<'EOF'\n*** Update File: x.py\nEOF"},
    }
    assert edited_paths(payload) == []


def _bash_payload(command: str) -> dict:
    return {"cwd": "C:\\host\\repo", "tool_name": "Bash", "tool_input": {"command": command}}


def _patch(cd_prefix: str, path: str) -> str:
    body = f"*** Begin Patch\n*** Update File: {path}\n*** End Patch"
    return f"{cd_prefix} apply_patch <<'EOF'\n{body}\nEOF"


def test_cd_relative_prefix_resolves_headers_there():
    command = _patch("cd sub &&", "a.py")
    assert _norm(edited_paths(_bash_payload(command))) == ["C:/host/repo/sub/a.py"]


def test_cd_chain_of_quoted_and_bare_segments_joined_by_mixed_separators():
    command = _patch('cd "a b" ; cd c &&', "x.py")
    assert _norm(edited_paths(_bash_payload(command))) == ["C:/host/repo/a b/c/x.py"]


def test_cd_with_a_variable_falls_back_to_the_payload_cwd():
    command = _patch("cd $X &&", "a.py")
    assert _norm(edited_paths(_bash_payload(command))) == ["C:/host/repo/a.py"]


def test_cd_absolute_dir_replaces_the_cwd_entirely():
    command = _patch("cd /other/place &&", "a.py")
    assert edited_paths(_bash_payload(command)) == ["/other/place/a.py"]


def test_cli_prints_utf8_one_per_line():
    raw = (FIX / "post_bash_patch.json").read_bytes()
    run = subprocess.run(
        [sys.executable, str(HOOK_IO), "edited-paths"],
        input=raw,
        capture_output=True,
        env={"PYTHONUTF8": "0", "PATH": ""},
    )
    assert run.returncode == 0
    assert "한글/파일.md" in PureWindowsPath(run.stdout.decode("utf-8").strip()).as_posix()


def test_only_a_patch_envelope_in_the_command_makes_a_bash_edit():
    from scripts.harness.codex.hook_io import classify

    quoted = _bash_payload('grep -n "*** Begin Patch" hook.sh')
    echoed = _bash_payload("echo '*** Begin Patch'")
    output = {**_bash_payload("git diff HEAD"), "tool_response": _patch("", "a.py")}
    assert classify(quoted) == classify(echoed) == classify(output) == (False, [])
    argument = _bash_payload("apply_patch '*** Begin Patch\n*** Update File: a.py\n*** End Patch'")
    assert classify(argument)[0] is True


def test_an_edit_with_no_placeable_path_is_still_an_edit():
    from scripts.harness.codex.hook_io import classify

    assert classify({"tool_name": "apply_patch", "tool_input": {"input": "x"}}) == (True, [])
    empty = {
        "tool_name": "apply_patch",
        "tool_input": {"command": "*** Begin Patch\n*** End Patch"},
    }
    assert classify(empty) == (True, [])


def _cli(raw: bytes) -> int:
    cmd = [sys.executable, str(HOOK_IO), "edited-paths"]
    return subprocess.run(cmd, input=raw, capture_output=True).returncode


def test_cli_exit_status_separates_not_an_edit_from_an_unplaced_one():
    assert _cli(json.dumps(_bash_payload("git diff HEAD")).encode()) == 0
    empty = {
        "tool_name": "apply_patch",
        "tool_input": {"command": "*** Begin Patch\n*** End Patch"},
    }
    assert _cli(json.dumps(empty).encode()) == 3
    assert _cli(b"not json at all") == 4


def test_a_cut_payload_is_judged_by_tool_name_and_surviving_command():
    whole = json.dumps(_bash_payload(_patch("", "a.py")) | {"tool_response": "x" * 50})
    assert _cli(whole[:-20].encode()) == 3  # the command's envelope survived the cut
    cut_bash = json.dumps(_bash_payload(_patch("", "a.py" + "x" * 500)))
    assert _cli(cut_bash[: cut_bash.index("*** End Patch")].encode()) == 0
    patch = json.dumps({"tool_name": "apply_patch", "tool_input": {"command": "*** Begin"}})
    assert _cli(patch[:-10].encode()) == 3


def test_a_tab_indented_dash_heredoc_patch_counts():
    body = "\t*** Begin Patch\n\t*** Update File: a.py\n\t*** End Patch"
    command = f"apply_patch <<-'EOF'\n{body}\n\tEOF"
    assert _norm(edited_paths(_bash_payload(command))) == ["C:/host/repo/a.py"]


def test_an_ansi_c_quoted_patch_counts():
    command = r"apply_patch $'*** Begin Patch\n*** Update File: 한글.py\n*** End Patch\n'"
    assert _norm(edited_paths(_bash_payload(command))) == ["C:/host/repo/한글.py"]


def test_an_ansi_c_quoted_mention_without_an_envelope_is_not_an_edit():
    from scripts.harness.codex.hook_io import classify

    assert classify(_bash_payload(r"echo $'*** Begin Patch\nno end'")) == (False, [])


def test_a_cut_ansi_c_patch_still_reads_as_an_edit():
    command = r"apply_patch $'*** Begin Patch\n*** Update File: a.py\n*** End Patch'"
    whole = json.dumps(_bash_payload(command) | {"tool_response": "x" * 50})
    assert _cli(whole[:-20].encode()) == 3
