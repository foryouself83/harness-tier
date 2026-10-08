"""The merge path's reading of a command against what bash runs.

Each command runs under stub `git`, `ssh`, `watch` and `sudo` executables that log instead of
acting, and the gate must find the merge-path invocations bash executed — not the ones a
hand-written expectation believed it would. A substitution's output is unknown to the gate, so
an opaque word on its side and an empty one on bash's both drop out of the comparison."""

import os
import shutil
import subprocess
from collections import Counter
from pathlib import Path

import pytest

import scripts._harness_paths as hp
from tests.flow_gate.bash_corpus import CORPUS, KNOWN_GAPS

BASH = shutil.which("bash") if os.name != "nt" else None
pytestmark = pytest.mark.skipif(BASH is None, reason="the oracle runs bash on POSIX")

_STUBS = {
    "git": r"""#!/usr/bin/env bash
# one write per record: a git running in a process substitution logs at the same time
record="$(printf '%s' "${REMOTE:-0}"; printf '\x1f%s' "$@"; printf '\x1e')"
printf '%s' "$record" >>"$ORACLE_LOG"
# drain a process substitution's pipe, so whatever runs in it has logged before this exits
for arg in "$@"; do case "$arg" in /dev/fd/*) cat "$arg" >/dev/null ;; esac; done
""",
    "ssh": r"""#!/usr/bin/env bash
while [ $# -gt 0 ]; do
  case "$1" in
    -[BbcDEeFIiJLlmOoPpQRSWw]) shift 2 ;;
    -*) shift ;;
    *) break ;;
  esac
done
shift
REMOTE=1 exec bash -c "$*"
""",
    "watch": r"""#!/usr/bin/env bash
direct=0
while [ $# -gt 0 ]; do
  case "$1" in
    -x|--exec) direct=1; shift ;;
    -n|--interval|-q|--equexit) shift 2 ;;
    -[!-]*x*) direct=1; shift ;;
    -*) shift ;;
    *) break ;;
  esac
done
[ "$direct" -eq 1 ] && exec "$@"
exec sh -c "$*"
""",
    "sudo": r"""#!/usr/bin/env bash
while [ $# -gt 0 ]; do
  case "$1" in
    -[ugCDhprtTU]) shift 2 ;;
    -*) shift ;;
    *) break ;;
  esac
done
exec "$@"
""",
}


def _normalized(words) -> tuple[str, ...]:
    # a word that is all substitution output stands for nothing either side can name; one only
    # partly made of it is a word the gate read wrong, and stays
    return tuple(w for w in words if w.strip(hp.OPAQUE_CH))


def _key(word, global_opts, operands, mode):
    operands = _normalized(operands)
    if mode == "flags":
        operands = tuple(w for w in operands if w.startswith("-"))
    return (word, tuple(global_opts), operands)


def _bash_reads(command: str, tmp_path: Path, mode: str) -> Counter:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for name, body in _STUBS.items():
        stub = bin_dir / name
        stub.write_text(body, encoding="utf-8", newline="\n")
        stub.chmod(0o755)
    work = tmp_path / "work"
    work.mkdir()
    log = tmp_path / "log"
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", "ORACLE_LOG": str(log)}
    # a process substitution runs in the background: wait, or its git may log after the read
    subprocess.run(
        [BASH, "--noprofile", "--norc", "-c", command + "\nwait"],
        cwd=work,
        env=env,
        capture_output=True,
        timeout=20,
    )
    found = Counter()
    raw = log.read_bytes().decode("utf-8", "replace") if log.exists() else ""
    for record in filter(None, raw.split("\x1e")):
        remote, *argv = record.split("\x1f")
        i = 0
        while i < len(argv) and argv[i].startswith("-"):
            i += 2 if argv[i] in hp._GIT_GLOBAL_WITH_ARG else 1
        if i >= len(argv) or argv[i] not in hp.MERGE_PATH_WORDS:
            continue
        if remote == "1" and argv[i] in ("switch", "checkout"):
            continue  # it moves the remote HEAD, never this one
        found[_key(argv[i], argv[:i], argv[i + 1 :], mode)] += 1
    return found


def _gate_reads(command: str, mode: str) -> Counter:
    return Counter(
        _key(word, global_opts, operands, mode)
        for _s, word, _d, global_opts, operands, _e in hp.live_invocations(command)
    )


def _row(entry):
    return (entry, "full") if isinstance(entry, str) else entry


@pytest.mark.parametrize("command,mode", [_row(e) for e in CORPUS])
def test_the_gate_reads_what_bash_runs(tmp_path, command, mode):
    assert _gate_reads(command, mode) == _bash_reads(command, tmp_path, mode), command


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(c, marks=pytest.mark.xfail(strict=True, reason=r))
        for c, r in KNOWN_GAPS.items()
    ],
)
def test_a_known_gap_still_disagrees_with_bash(tmp_path, command):
    assert _gate_reads(command, "full") == _bash_reads(command, tmp_path, "full"), command
