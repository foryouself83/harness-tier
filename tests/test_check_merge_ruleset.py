import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check-merge-ruleset.sh"
# On Windows a bare "bash" resolves via System32 first (the WSL stub), which mangles
# backslash paths; shutil.which walks PATH in order and finds Git Bash. Same rationale as
# tests/test_check_token_write.py.
BASH = shutil.which("bash") or "bash"


def _ruleset(ref: str, methods: list[str] | None, enforcement: str = "active") -> dict:
    """One ruleset object as GET /repos/{o}/{r}/rulesets/{id} returns it."""
    rules = []
    if methods is not None:
        rules.append({"type": "pull_request", "parameters": {"allowed_merge_methods": methods}})
    return {
        "id": 1,
        "name": "x",
        "target": "branch",
        "enforcement": enforcement,
        "conditions": {"ref_name": {"include": [ref], "exclude": []}},
        "rules": rules,
    }


def _decode(sets: list[dict], branch: str, want: str, env: dict | None = None) -> int:
    return subprocess.run(
        [BASH, str(SCRIPT), "--decode", branch, want],
        input=json.dumps(sets, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        env=env,
    ).returncode


def test_exact_match_exits_0():
    assert _decode([_ruleset("refs/heads/stage", ["merge"])], "stage", "merge") == 0


def test_extra_method_allowed_exits_10():
    # allowing squash on a promotion branch is exactly the rebase/squash footgun we guard
    assert _decode([_ruleset("refs/heads/stage", ["merge", "squash"])], "stage", "merge") == 10


def test_missing_method_exits_10():
    assert _decode([_ruleset("refs/heads/dev", ["squash"])], "dev", "rebase,squash") == 10


def test_no_ruleset_for_branch_exits_10():
    assert _decode([_ruleset("refs/heads/other", ["merge"])], "stage", "merge") == 10


def test_empty_ruleset_list_exits_10():
    assert _decode([], "stage", "merge") == 10


def test_inactive_ruleset_is_ignored_exits_10():
    sets = [_ruleset("refs/heads/stage", ["merge"], enforcement="evaluate")]
    assert _decode(sets, "stage", "merge") == 10


def test_all_refs_wildcard_matches():
    assert _decode([_ruleset("~ALL", ["merge"])], "stage", "merge") == 0


def test_multiple_rulesets_intersect():
    # GitHub applies the intersection when several rulesets match the same ref
    sets = [
        _ruleset("refs/heads/dev", ["squash", "rebase", "merge"]),
        _ruleset("refs/heads/dev", ["squash", "rebase"]),
    ]
    assert _decode(sets, "dev", "rebase,squash") == 0


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
    # Exception` turns into exit 20 and the dispatch used to collapse into "your ruleset
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
    # valid JSON, wrong top-level shape: `{}` used to silently read as "no ruleset matched"
    # (exit 10, i.e. "your config is wrong") when the truth is "we couldn't read this at all"
    r = subprocess.run(
        [BASH, str(SCRIPT), "--decode", "stage", "merge"],
        input="{}",
        text=True,
        capture_output=True,
    )
    assert r.returncode == 20


def _gh_stub_script(rulesets_by_id: dict) -> str:
    """A fake `gh` placed on PATH so the non-`--decode` dispatch path (list ids, then
    fetch each ruleset) can be driven without a real `gh` install or network access.
    Serves `gh api /repos/.../rulesets` (the id list) and `gh api /repos/.../rulesets/<id>`
    (one full ruleset object each) from a fixed table.
    """
    ids_out = "\n".join(str(rid) for rid in rulesets_by_id)
    cases = "\n".join(
        # a plain str value is emitted verbatim, so a test can serve a body that is not JSON
        f"    */rulesets/{rid}) printf '%s' '{rs if isinstance(rs, str) else json.dumps(rs)}' ;;"
        for rid, rs in rulesets_by_id.items()
    )
    return (
        "#!/usr/bin/env bash\n"
        'if [ "$1" = "api" ]; then\n'
        '  case "$2" in\n'
        f"    */rulesets) printf '{ids_out}\\n' ;;\n"
        f"{cases}\n"
        "    *) exit 1 ;;\n"
        "  esac\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n"
    )


def _run_dispatch(
    rulesets_by_id: dict, flows: list[str], branch_env: dict
) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as d:
        gh_path = Path(d) / "gh"
        gh_path.write_text(_gh_stub_script(rulesets_by_id), encoding="utf-8")
        gh_path.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = str(d) + os.pathsep + env.get("PATH", "")
        env["HARNESS_REPO"] = "test/repo"
        env.update(branch_env)
        return subprocess.run(
            [BASH, str(SCRIPT), *flows],
            capture_output=True,
            text=True,
            env=env,
        )


def test_release_bypass_warning_only_fires_for_promotion_failure():
    # Regression: the release-automation bypass warning must key off the promotion checks'
    # own outcome, not whatever `rc` happens to hold afterwards. A daily-only mismatch (dev
    # ruleset missing "rebase") with a fully-correct promotion setup (stage/main both exactly
    # "merge") must not print release-bypass guidance that has nothing to do with the actual
    # problem — the daily arm has its own, different bypass reason (see below).
    rulesets = {
        1: _ruleset("refs/heads/dev", ["squash"]),
        2: _ruleset("refs/heads/stage", ["merge"]),
        3: _ruleset("refs/heads/main", ["merge"]),
    }
    r = _run_dispatch(
        rulesets,
        ["daily", "promotion"],
        {
            "HARNESS_BRANCH_INTEGRATION": "dev",
            "HARNESS_BRANCH_STAGING": "stage",
            "HARNESS_BRANCH_PRODUCTION": "main",
        },
    )
    assert r.returncode == 10  # the daily mismatch still fails the overall run
    assert "dev: allowed merge methods" in r.stderr  # daily guidance is present
    # promotion passed → its bypass reason (and only its) must be absent
    assert "BYPASS ACTOR for the release automation" not in r.stderr
    assert "chore(release)" not in r.stderr


def test_daily_mismatch_warns_about_the_back_merge_bypass():
    # An integration ruleset needs a bypass actor just as much as a promotion one, for a
    # different reason: "require a PR" also rejects `git push origin <integration>`, which is
    # how the post-release back-merge lands (risk-tiers.md calls it not optional). Reporting
    # the merge-method gap without that warning walks a `daily`-only team straight into a
    # blocked back-merge, a drifting plugin.json, and a miscomputed next version.
    rulesets = {1: _ruleset("refs/heads/dev", ["squash"])}
    r = _run_dispatch(rulesets, ["daily"], {"HARNESS_BRANCH_INTEGRATION": "dev"})
    assert r.returncode == 10
    assert "dev: allowed merge methods" in r.stderr
    assert "BYPASS ACTOR" in r.stderr
    assert "back-merge" in r.stderr


def test_bypass_warning_fires_for_promotion_failure():
    # Sanity check for the fix above: when promotion itself is the thing that's wrong,
    # the bypass guidance must still appear (it isn't disabled outright).
    rulesets = {
        1: _ruleset("refs/heads/dev", ["rebase", "squash"]),
        2: _ruleset("refs/heads/stage", ["merge", "squash"]),
        3: _ruleset("refs/heads/main", ["merge"]),
    }
    r = _run_dispatch(
        rulesets,
        ["daily", "promotion"],
        {
            "HARNESS_BRANCH_INTEGRATION": "dev",
            "HARNESS_BRANCH_STAGING": "stage",
            "HARNESS_BRANCH_PRODUCTION": "main",
        },
    )
    assert r.returncode == 10
    assert "stage: allowed merge methods" in r.stderr
    assert "BYPASS ACTOR" in r.stderr


def test_undecodable_response_reports_undetermined_not_a_mismatch():
    # `decode`'s 20 must survive the dispatch. Collapsing it into rc=10 tells a repo its
    # ruleset "must be exactly: rebase,squash" — a verdict about a ruleset that was never
    # read — and adds a bypass warning to match. 20 (undetermined) is the honest answer, and
    # /flow-init Step 2.7 continues on 10 and 20 alike, so nothing is blocked either way.
    r = _run_dispatch({1: "{not json"}, ["daily"], {"HARNESS_BRANCH_INTEGRATION": "dev"})
    assert r.returncode == 20
    assert "allowed merge methods must be exactly" not in r.stderr
    assert "BYPASS ACTOR" not in r.stderr
    assert "undetermined" in r.stderr


def test_zero_flow_args_does_not_report_match():
    # Regression: an empty flow list must never fall through to "match" (exit 0) — that
    # would report a check that never ran as if it had passed.
    r = _run_dispatch({}, [], {})
    assert r.returncode == 20
    assert "match" not in r.stderr.lower()


def test_unrecognized_flow_only_does_not_report_match():
    # Same failure mode, reached a different way: every arg falls into the `*)` unknown-flow
    # arm, which never sets `rc` — so "nothing checked" must still win over "match".
    r = _run_dispatch({}, ["bogus"], {})
    assert r.returncode == 20
    assert "unknown flow: bogus" in r.stderr
    assert "match" not in r.stderr.lower()


def test_script_never_calls_a_write_api():
    # The whole point of this script is that it reads. A method flag on a gh/curl call is the
    # only way it could write, so its absence is the structural guarantee.
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--method" not in text
    assert "-X " not in text
    for verb in ("POST", "PUT", "PATCH", "DELETE"):
        assert verb not in text
