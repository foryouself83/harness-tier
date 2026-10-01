"""JSON escaping of the rule: exact round trip, and its cost in each locale."""

import os
import re
import shutil
import subprocess
import time
from pathlib import Path

import pytest

from tests.inject_risk_tiers._helpers import (
    SCRIPT,
    _context,
    _plugins_root,
    _run,
)

NON_ASCII_LINE = '- **규칙** — "인용" \\ 백슬래시\tтаб é 漢字 → 화살표\n'


def _non_ascii_plugin(tmp_path: Path) -> Path:
    plugin = _plugins_root(tmp_path, published=None)
    body = NON_ASCII_LINE * (100 * 1024 // len(NON_ASCII_LINE.encode()))
    (plugin / "rules" / "risk-tiers.md").write_text(body, encoding="utf-8", newline="")
    return plugin


def test_a_utf8_locale_does_not_make_escaping_quadratic(tmp_path):
    """bash pattern substitution under a multibyte locale rescans the string per match, so a
    non-ASCII rule escaped there grows quadratically: 100 KB took 2951 ms against 25 ms in the C
    locale on Linux bash 5.2. Judged as a ratio on the same machine, because Git Bash spends
    seconds on this input in either locale."""
    plugin = _non_ascii_plugin(tmp_path)
    elapsed = {}
    for loc in ("C", "C.UTF-8"):
        start = time.perf_counter()
        assert "규칙" in _context(_run(plugin, extra_env={"LC_ALL": loc}))
        elapsed[loc] = time.perf_counter() - start
    assert elapsed["C.UTF-8"] < 3 * elapsed["C"] + 1, elapsed


@pytest.mark.parametrize("locale", ["C.UTF-8", "C"])
def test_a_non_ascii_rule_round_trips_through_the_escaping(tmp_path, locale):
    """The escaping is byte-wise in every locale. The escapes are ASCII and no UTF-8
    continuation byte is, so decoding the JSON gives back the rule exactly; `$(<file)` drops
    its trailing newline."""
    plugin = _non_ascii_plugin(tmp_path)
    body = (plugin / "rules" / "risk-tiers.md").read_text(encoding="utf-8")
    assert body.rstrip("\n") in _context(_run(plugin, extra_env={"LC_ALL": locale}))


AWK_CASES = [
    "",
    "plain",
    "a\nb",
    "trailing\n",
    "two trailing\n\n",
    "\n\nleading blanks",
    "tab\there\t",
    "cr\r\nline\r\n",
    'quote " and \\ backslash \\\\ \\" \\\\"',
    "\\\n\\",
    NON_ASCII_LINE * 3,
]


def _json_string_body(value: str) -> str:
    """What escape_for_json writes: these five escapes and nothing else."""
    for raw, escaped in (("\\", "\\\\"), ('"', '\\"'), ("\n", "\\n"), ("\r", "\\r"), ("\t", "\\t")):
        value = value.replace(raw, escaped)
    return value


@pytest.mark.skipif(shutil.which("awk") is None, reason="no awk on PATH")
@pytest.mark.parametrize("value", AWK_CASES, ids=range(len(AWK_CASES)))
def test_the_awk_escaper_matches_the_bash_one(tmp_path, value):
    """bash 3 escapes through awk instead (macOS /bin/bash is 3.2); CI's bash is 5:
    the awk program is run here on its own, with the hook's own sentinel handling. It goes in
    a file because msys rewrites backslashes in a Windows argv."""
    if os.name == "nt" and "\r" in value:
        pytest.skip("Git for Windows' awk reads stdin in text mode; Git Bash is bash 5")
    hook = SCRIPT.read_text(encoding="utf-8").replace("\r\n", "\n")
    program = tmp_path / "escape.awk"
    awk_text = re.search(r"^json_escape_awk='(.*?)'$", hook, re.M | re.S).group(1)
    program.write_bytes(awk_text.encode())
    out = subprocess.run(
        [shutil.which("awk"), "-f", str(program)],
        input=(value + "x").encode(),
        capture_output=True,
        env={"LC_ALL": "C"},
        check=True,
    ).stdout.decode()
    assert out.removesuffix("x") == _json_string_body(value)

