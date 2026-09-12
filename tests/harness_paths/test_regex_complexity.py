"""A scan that is quadratic in command length neutralizes the gate, it does not slow it.

The hook carries a timeout; past it there is no verdict, and Invariant #1 turns no verdict
into a commit that passes ungated. So a shape that costs seconds on a command an agent can
plausibly write is a hole, not a performance note. The bounds below are wall clock and
therefore loose — they separate linear from quadratic by orders of magnitude, not one
runner from another.
"""

import re
import time
from pathlib import Path

import pytest

import scripts._harness_paths as vp
import scripts.flow_gate_check as fgc

REPO = Path(__file__).resolve().parents[2]
# Generous enough that a slow shared runner still clears it, small enough that the quadratic
# scan this replaced — which took tens of seconds on the same input — cannot.
BUDGET_SECONDS = 2.0
# Big enough that every quadratic shape this file pins clears the budget: at a quarter of
# it the unanchored `cd` prefix costs 0.32s and reads as fine.
PROBE_UNITS = 64000
ANCHORED = (("_CD_PREFIX_RE", vp), ("_MERGE_CD_PREFIX_RE", fgc))


def test_a_long_escape_run_does_not_stall_the_gate():
    r"""`printf` feeding xargs is a real shape, and its `\n` escapes are what the token
    boundary has to read. Every start position re-scanning the rest of the command is the
    failure this pins: the verdict was already False, so the cost bought nothing."""
    command = "printf '" + ("row" + chr(92) + "n") * 20000 + "' | xargs -n1 echo"
    start = time.perf_counter()
    verdict = vp.is_invocation(command, "commit")
    elapsed = time.perf_counter() - start
    assert verdict is False
    assert elapsed < BUDGET_SECONDS, f"{len(command)} chars took {elapsed:.2f}s"


@pytest.mark.parametrize("name,module", ANCHORED, ids=[n for n, _ in ANCHORED])
def test_the_cd_prefixes_carry_their_anchor(name: str, module):
    r"""`match` anchors the call, not the pattern. The anchor in the pattern is what keeps the
    next caller — one that reaches for `search` — from inheriting the leading `\s*`'s retry at
    every start position."""
    pattern = getattr(module, name).pattern
    assert pattern.startswith(chr(92) + "A"), f"{name} is anchored only by its callers"


@pytest.mark.parametrize("name,module", ANCHORED, ids=[n for n, _ in ANCHORED])
def test_an_anchored_prefix_is_cheap_to_scan(name: str, module):
    start = time.perf_counter()
    getattr(module, name).search(" " * 64000)
    elapsed = time.perf_counter() - start
    assert elapsed < BUDGET_SECONDS, f"{name} scan took {elapsed:.2f}s"


def test_the_position_matched_pattern_is_never_scanned():
    r"""`_COMMAND_PREFIX_RE` is matched at a position, so it cannot carry `\A`, and its own
    leading run is quadratic under a scan. The constraint lives in how it is called, which is
    exactly the kind of rule that decays silently — so it is pinned here."""
    for path in sorted((REPO / "scripts").glob("*.py")):
        source = path.read_text(encoding="utf-8")
        assert "_COMMAND_PREFIX_RE.search(" not in source, path.name
        assert "_COMMAND_PREFIX_RE.finditer(" not in source, path.name


def test_no_pattern_is_quadratic_on_a_repeated_token():
    """A sweep rather than a list: the shapes fixed here were found this way, and one added
    later would be found the same way. `_COMMAND_PREFIX_RE` is excused by the test above, which
    pins the call convention that keeps it safe.

    PROBE_UNITS is what decides whether the sweep sees anything. At a quarter of it, an
    unanchored `cd` prefix costs 0.32s and passes a 2.0s budget while still being quadratic;
    here it costs 5.66s. The shipped patterns stay at 0.0061s, so the room bought is free.

    `_standalone_word` builds its pattern per call, so `vars(module)` cannot see it — and it
    shares `_TOKEN_BOUNDARY`, the alternation behind the defect this file pins.
    """
    backslash = chr(92)
    probes = {
        "escapes": (backslash + "n") * PROBE_UNITS,
        "spaces": " " * PROBE_UNITS,
        "quotes": "'" * PROBE_UNITS,
        "slashes": "/a" * PROBE_UNITS,
        "backslashes": (backslash + "a") * PROBE_UNITS,
    }
    scans = [
        (f"{module.__name__}.{name}", value.search)
        for module in (vp, fgc)
        for name, value in vars(module).items()
        if isinstance(value, re.Pattern) and name != "_COMMAND_PREFIX_RE"
    ]
    scans.append(("_standalone_word", lambda probe: vp._standalone_word(probe, "commit")))
    slow = []
    for who, scan in scans:
        for label, probe in probes.items():
            start = time.perf_counter()
            scan(probe)
            elapsed = time.perf_counter() - start
            if elapsed > BUDGET_SECONDS:
                slow.append(f"{who} on {label}: {elapsed:.2f}s")
    assert not slow, slow
