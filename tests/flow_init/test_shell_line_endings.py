"""Every shipped script checks out in its interpreter's line ending, whatever `core.autocrlf` is.

The plugin cache is a git checkout on the consumer's machine, and `/flow-init` copies its
scripts byte-for-byte. Git Bash tolerates a CRLF script; Linux bash fails on it — and a gate
hook that dies on a syntax error exits neither 0 nor 2, so the gate fails open. `cmd.exe`
mis-parses labels and `goto` in an LF batch file.
"""

import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _git(*args: str, stdin: str | None = None) -> str:
    return subprocess.run(
        ["git", *args], cwd=ROOT, input=stdin, capture_output=True, text=True, check=True
    ).stdout


@pytest.mark.parametrize(("pattern", "want"), [("*.sh", "lf"), ("*.cmd", "crlf")])
def test_every_tracked_script_checks_out_its_interpreters_eol(pattern, want):
    scripts = [s for s in _git("ls-files", "-z", "--", pattern).split("\0") if s]
    assert scripts, f"no tracked {pattern} — the pattern no longer matches the tree"
    attrs = _git("check-attr", "-z", "--stdin", "eol", stdin="\0".join(scripts) + "\0")
    fields = attrs.split("\0")
    eol = {fields[i]: fields[i + 2] for i in range(0, len(fields) - 2, 3)}
    wrong = sorted(path for path in scripts if eol.get(path) != want)
    assert not wrong, f"{pattern} without eol={want} in .gitattributes: {wrong}"
