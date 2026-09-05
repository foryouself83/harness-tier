"""The bash floor these shipped scripts have to keep, and the backstop that holds it."""

import re
from pathlib import Path

import pytest

from tests.invalidate_gate_markers._helpers import (
    BASH,
    REPO,
    SCRIPT,
)

pytestmark = pytest.mark.skipif(BASH is None, reason="a repo-visible bash is required")


def _bash_4_offenders(scripts) -> list[str]:
    """Every bash-4-only construct found in `scripts`, as `path:line: why -- code`."""
    bash_4_only = [
        (
            r"\bread\b(?:\s+(?:-[A-Za-z]+|'[^']*'|\"[^\"]*\"|[^-\s][^\s]*))*\s+-[A-Za-z]*N",
            "read -N (4.1) - `head -c` instead",
        ),
        (r"\bmapfile\b|\breadarray\b", "4.0 - read into a variable in a loop instead"),
        (
            r"\b(?:declare|typeset|local)\s+-[A-Za-z]*A",
            "associative arrays (4.0) - parallel lists instead",
        ),
        (r"\bcoproc\b", "4.0"),
        (r"&>>", "4.0 - `>>file 2>&1` instead"),
        (r"\|&", "4.0 - `2>&1 |` instead"),
        (r"\$\{[A-Za-z_][A-Za-z0-9_]*\^", "case conversion (4.0)"),
        (r"\$\{[A-Za-z_][A-Za-z0-9_]*,", "case conversion (4.0)"),
    ]
    offenders = []
    for script in scripts:
        for line_no, line in enumerate(script.read_text(encoding="utf-8").splitlines(), 1):
            code = line.split(chr(35), 1)[0]
            for pattern, why in bash_4_only:
                if re.search(pattern, code):
                    rel = (
                        script.relative_to(REPO).as_posix()
                        if script.is_relative_to(REPO)
                        else script.name
                    )
                    offenders.append(f"{rel}:{line_no}: {why} -- {code.strip()}")
    return offenders


def test_no_shipped_shell_script_needs_a_bash_newer_than_macos_ships():
    """macOS's system bash is 3.2.57, and `check-deps.sh` tells a mac user bash is "provided by
    default" while README names no version floor. A 4.x-only builtin is not a syntax error there
    - the option fails at runtime, the value it should have set stays empty, and the hook acts on
    that emptiness. For this hook that means voiding the wrong tree's evidence on every edit,
    which is the direction it may never fail in."""
    scripts = sorted(REPO.glob("hooks/*.sh")) + sorted(REPO.glob("scripts/*.sh"))
    assert scripts, "no shipped shell scripts found - the glob stopped matching"
    offenders = _bash_4_offenders(scripts)
    assert not offenders, (
        "bash 4 constructs in shipped scripts:" + chr(10) + chr(10).join(offenders)
    )


def test_check_deps_names_the_program_the_payload_read_runs():
    """`check-deps.sh` exists because a missing shell utility does not announce itself: the
    filter goes empty and the gate passes in silence. The payload read spends the hook's one
    external process, and without that program the payload is empty, which sends the markers of
    a tree nobody edited while the edited repo keeps its own. So the two files have to name the
    same program, and the day the read changes program this fails rather than the consumer's
    next commit."""
    read_line = next(
        line
        for line in SCRIPT.read_text(encoding="utf-8").splitlines()
        if line.startswith("payload=")
    )
    program = re.search(r"\$\(\s*([A-Za-z0-9_.-]+)", read_line)
    assert program, read_line
    listed = re.search(
        r"for _u in ([^;]+); do",
        (REPO / "scripts" / "check-deps.sh").read_text(encoding="utf-8"),
    )
    assert listed, "check-deps.sh no longer spells its tool list as a `for` over names"
    assert program.group(1) in listed.group(1).split(), (
        f"{program.group(1)} runs on every edit but check-deps.sh does not check for it: "
        f"{listed.group(1).strip()}"
    )


def test_the_bash_4_denylist_reads_an_option_list_not_a_spelling(tmp_path: Path):
    """A denylist is only as good as the spellings it knows, and a backstop that misses the next
    one is a backstop nobody finds out about. Each line below is the same builtin the list
    already names, written the way a person reasonably would."""
    spellings = (
        "IFS= read -r -N 65536 payload",
        "read -N 100 x",
        "read -rN 100 x",
        "IFS= read -d '' -r -N 20 x",
        'read -d "" -N 20 x',
        "read -t 1 -N 20 x",
        "read -u 3 -N 20 x",
        "read -d , -N 20 x",
        "declare -A seen",
        "declare -gA seen",
        "declare -Ag seen",
        "local -A seen",
        "typeset -A seen",
        "mapfile -t lines < f",
        "readarray -t lines < f",
        "coproc x { cat; }",
        "printf x &>> log",
        "cat f |& tee log",
        'echo "${name^^}"',
        'echo "${name,,}"',
        'echo "${name^}"',
        'echo "${name,}"',
    )
    for spelling in spellings:
        script = tmp_path / "probe.sh"
        script.write_text(
            "#!/usr/bin/env bash" + chr(10) + spelling + chr(10), encoding="utf-8", newline=chr(10)
        )
        assert _bash_4_offenders([script]), spelling


def test_the_bash_4_denylist_leaves_the_shapes_bash_3_allows(tmp_path: Path):
    """The other half: a list that fires on ordinary 3.2 code gets switched off rather than
    fixed. Every line below is in one of the shipped scripts already."""
    for spelling in (
        "IFS= read -r line",
        "IFS= read -r -t 1 -d '' hook_stdin",
        "IFS=. read -r -a A <<< $a",
        "declare -r NAME=x",
        "printf x >> log 2>&1",
        "cat f 2>&1 | tee log",
        'echo "${name%%/*}"',
        'echo "${name//x/y}"',
    ):
        script = tmp_path / "probe.sh"
        script.write_text(
            "#!/usr/bin/env bash" + chr(10) + spelling + chr(10), encoding="utf-8", newline=chr(10)
        )
        assert not _bash_4_offenders([script]), spelling
