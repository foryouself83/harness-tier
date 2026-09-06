import os
import subprocess

from tests.merge_ruleset._helpers import BASH, SCRIPT, _decode, _ruleset


def _cp949_env() -> dict:
    """The environment CLAUDE.md Invariant #2 describes: a host whose python I/O is not UTF-8.

    `PYTHONIOENCODING` is what pins it deterministically on every platform — the real cp949
    Windows host reaches the same state through its ANSI code page, and it outranks even
    UTF-8 mode, so passing it proves the decode does not depend on the environment at all.
    """
    env = dict(os.environ)
    env.pop("PYTHONUTF8", None)
    env["PYTHONIOENCODING"] = "cp949"
    return env


def test_non_ascii_ruleset_name_still_decodes():
    # Invariant #2. A ruleset `name` is free user text — Korean here — and the API answers
    # UTF-8. Decoding it with the locale codec raises UnicodeDecodeError, which `except
    # Exception` turns into exit 20, which must not collapse into "your ruleset
    # differs": a correctly configured repo reported as misconfigured.
    sets = [_ruleset("refs/heads/stage", ["merge"])]
    sets[0]["name"] = "릴리스 보호"
    assert _decode(sets, "stage", "merge", env=_cp949_env()) == 0


def test_script_forces_utf8_io():
    # The env-var half of the same guard, in the form the sibling scripts use
    # (check-deps.sh:10, precommit-runner.sh:31) — it covers any python added here later.
    assert "export PYTHONUTF8=1" in SCRIPT.read_text(encoding="utf-8")


def test_malformed_json_exits_20():
    r = subprocess.run(
        [BASH, str(SCRIPT), "--decode", "stage", "merge"],
        input="{not json",
        text=True,
        capture_output=True,
    )
    assert r.returncode == 20


def test_null_json_exits_20():
    # valid JSON, wrong shape: `null` is not iterable — must not crash past exit 20
    r = subprocess.run(
        [BASH, str(SCRIPT), "--decode", "stage", "merge"],
        input="null",
        text=True,
        capture_output=True,
    )
    assert r.returncode == 20


def test_non_dict_array_elements_exits_20():
    # valid JSON array, wrong element type: ints have no .get() — must not crash past exit 20
    r = subprocess.run(
        [BASH, str(SCRIPT), "--decode", "stage", "merge"],
        input="[1,2,3]",
        text=True,
        capture_output=True,
    )
    assert r.returncode == 20


def test_object_instead_of_array_exits_20():
    # valid JSON, wrong top-level shape: `{}` must not read as "no ruleset matched"
    # (exit 10, i.e. "your config is wrong") when the truth is "we couldn't read this at all"
    r = subprocess.run(
        [BASH, str(SCRIPT), "--decode", "stage", "merge"],
        input="{}",
        text=True,
        capture_output=True,
    )
    assert r.returncode == 20
