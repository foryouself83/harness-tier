import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check-merge-ruleset.sh"
# On Windows a bare "bash" resolves via System32 first (the WSL stub), which mangles
# backslash paths; shutil.which walks PATH in order and finds Git Bash. Same rationale as
# tests/test_check_token_write.py.
BASH = shutil.which("bash") or "bash"


def _ruleset(
    ref: str,
    methods: list[str] | None,
    enforcement: str = "active",
    bypass_actors: list[dict] | None = None,
    exclude: list[str] | None = None,
) -> dict:
    """One ruleset object as GET /repos/{o}/{r}/rulesets/{id} returns it.

    `bypass_actors=None` omits the key entirely — an older/likely payload shape, and the
    one the merge-method tests below do not care about either way.
    """
    rules = []
    if methods is not None:
        rules.append({"type": "pull_request", "parameters": {"allowed_merge_methods": methods}})
    rs = {
        "id": 1,
        "name": "x",
        "target": "branch",
        "enforcement": enforcement,
        "conditions": {"ref_name": {"include": [ref], "exclude": exclude or []}},
        "rules": rules,
    }
    if bypass_actors is not None:
        rs["bypass_actors"] = bypass_actors
    return rs


ACTOR = [{"actor_id": 1, "actor_type": "Integration", "bypass_mode": "always"}]


def _actor(mode: str | None) -> dict:
    """One bypass actor. `mode=None` omits `bypass_mode` entirely."""
    a = {"actor_id": 1, "actor_type": "Integration"}
    if mode is not None:
        a["bypass_mode"] = mode
    return a


def _decode(
    sets: list[dict],
    branch: str,
    want: str,
    env: dict | None = None,
    default_branch: str | None = None,
) -> int:
    argv = [BASH, str(SCRIPT), "--decode", branch, want]
    if default_branch is not None:
        argv.append(default_branch)
    return subprocess.run(
        argv,
        input=json.dumps(sets, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        env=env,
    ).returncode


def _decode_bypass(
    sets: list[dict],
    branch: str,
    env: dict | None = None,
    default_branch: str | None = None,
) -> int:
    argv = [BASH, str(SCRIPT), "--decode-bypass", branch]
    if default_branch is not None:
        argv.append(default_branch)
    return subprocess.run(
        argv,
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


# --- which rulesets apply to a ref ---------------------------------------------------
# GitHub decides this from conditions.ref_name: `exclude` wins over `include`, and both
# accept fnmatch patterns plus the ~ALL / ~DEFAULT_BRANCH aliases. Counting a ruleset that
# does NOT apply is the unsafe direction — it reports "match" for a repo that is not
# actually protected. Failing to count one that does apply is only noise.


def test_excluded_ref_is_not_counted():
    # ~ALL include with this very branch excluded: the ruleset does not govern `dev` at all,
    # so its methods must not be intersected into the verdict. Counting it made a repo with
    # ONE such ruleset report a clean "match" for a branch it never protected.
    sets = [_ruleset("~ALL", ["merge"], exclude=["refs/heads/dev"])]
    assert _decode(sets, "dev", "merge") == 10


def test_excluded_ref_is_not_counted_on_the_bypass_axis():
    # Same predicate, other axis: an excluded ruleset imposes no PR requirement here, so
    # there is nothing to bypass and no gap to report.
    sets = [_ruleset("~ALL", ["merge"], exclude=["refs/heads/dev"], bypass_actors=[])]
    assert _decode_bypass(sets, "dev") == 0


def test_exclude_wins_over_an_explicit_include():
    # Both name the ref. GitHub applies exclude last; so must we.
    sets = [_ruleset("refs/heads/dev", ["merge"], exclude=["refs/heads/dev"])]
    assert _decode(sets, "dev", "merge") == 10


def test_glob_include_matches():
    sets = [_ruleset("refs/heads/*", ["merge"])]
    assert _decode(sets, "stage", "merge") == 0


def test_glob_star_does_not_cross_a_slash():
    # GitHub's ref patterns are path-aware: `*` matches within one segment, `**` spans them.
    # Python's fnmatch has no such rule — its `*` swallows `/` — so `refs/heads/*` would
    # count a ruleset that GitHub does not apply to `team/dev` at all. That is the unsafe
    # direction: a clean verdict for a branch nothing protects. Bites any host whose
    # flow-config branch names contain a slash.
    assert _decode([_ruleset("refs/heads/*", ["merge"])], "team/dev", "merge") == 10


def test_globstar_crosses_a_slash():
    assert _decode([_ruleset("refs/heads/**", ["merge"])], "team/dev", "merge") == 0


def test_glob_exclude_matches():
    sets = [_ruleset("~ALL", ["merge"], exclude=["refs/heads/fix/*"])]
    assert _decode(sets, "fix/thing", "merge") == 10


def test_default_branch_alias_matches_the_named_default():
    sets = [_ruleset("~DEFAULT_BRANCH", ["merge"])]
    assert _decode(sets, "main", "merge", default_branch="main") == 0


def test_default_branch_alias_does_not_match_another_branch():
    sets = [_ruleset("~DEFAULT_BRANCH", ["merge"])]
    assert _decode(sets, "dev", "merge", default_branch="main") == 10


def test_default_branch_alias_without_a_known_default_does_not_match():
    # The pure --decode path has no repo to ask. Guessing "it probably applies" would be the
    # unsafe direction (a false "match"); declining to count it is only noise.
    assert _decode([_ruleset("~DEFAULT_BRANCH", ["merge"])], "main", "merge") == 10


# --- bypass actors -----------------------------------------------------------------
# Allowed merge methods hang off "Require a pull request before merging", and that rule also
# rejects the direct pushes the release pipeline depends on. A bypass actor is therefore a
# SECOND, independent requirement — a repo can have exactly the right merge methods and still
# be broken. These decode it on its own axis, never as a by-product of the method verdict.


def test_bypass_actor_present_exits_0():
    sets = [_ruleset("refs/heads/stage", ["merge"], bypass_actors=ACTOR)]
    assert _decode_bypass(sets, "stage") == 0


def test_bypass_actor_empty_list_exits_10():
    sets = [_ruleset("refs/heads/stage", ["merge"], bypass_actors=[])]
    assert _decode_bypass(sets, "stage") == 10


def test_bypass_actors_key_absent_exits_10():
    # absent is treated as empty — the conservative reading, and the one that matches what
    # GitHub enforces (no listed actor = nobody bypasses)
    assert _decode_bypass([_ruleset("refs/heads/stage", ["merge"])], "stage") == 10


def test_bypass_not_required_without_a_pull_request_rule_exits_0():
    # no "require a pull request" rule means nothing is blocking the release push, so there
    # is nothing to bypass. Not a skipped check — a real determination.
    assert _decode_bypass([_ruleset("refs/heads/stage", None)], "stage") == 0


def test_bypass_ruleset_for_another_branch_is_ignored_exits_0():
    assert _decode_bypass([_ruleset("refs/heads/other", ["merge"])], "stage") == 0


def test_bypass_inactive_ruleset_is_ignored_exits_0():
    sets = [_ruleset("refs/heads/stage", ["merge"], enforcement="evaluate")]
    assert _decode_bypass(sets, "stage") == 0


def test_bypass_all_refs_wildcard_is_checked():
    assert _decode_bypass([_ruleset("~ALL", ["merge"])], "stage") == 10


def test_bypass_missing_on_any_matching_ruleset_exits_10():
    # bypass is per-ruleset: an actor listed on ruleset A does not exempt it from ruleset B.
    # So EVERY matching pull_request ruleset needs one — a single gap blocks the push.
    sets = [
        _ruleset("refs/heads/stage", ["merge"], bypass_actors=ACTOR),
        _ruleset("refs/heads/stage", ["merge"], bypass_actors=[]),
    ]
    assert _decode_bypass(sets, "stage") == 10


def test_bypass_mode_pull_request_does_not_count_exits_10():
    # `bypass_mode` decides WHAT the actor may bypass. A "pull_request" actor may merge a PR
    # that fails the rule — it may NOT push directly. So a ruleset whose only bypass actor is
    # in that mode still rejects semantic-release's chore(release) push and the back-merge
    # push: present-but-useless. Counting mere presence here would reproduce, one level down,
    # the same "reports fine for the config that breaks releases" bug this check exists for.
    sets = [_ruleset("refs/heads/main", ["merge"], bypass_actors=[_actor("pull_request")])]
    assert _decode_bypass(sets, "main") == 10


def test_bypass_mode_always_alongside_a_pull_request_actor_exits_0():
    # One actor that can push directly is enough; the useless one next to it is irrelevant.
    sets = [
        _ruleset(
            "refs/heads/main",
            ["merge"],
            bypass_actors=[_actor("pull_request"), _actor("always")],
        )
    ]
    assert _decode_bypass(sets, "main") == 0


def test_bypass_mode_absent_is_read_as_permissive_exits_0():
    # Payload tolerance: only "pull_request" is known to be insufficient. An actor whose mode
    # the payload omits (or names something this script has not seen) must not be called a
    # gap — that would fail a correctly configured repo on a field it could not read.
    sets = [_ruleset("refs/heads/main", ["merge"], bypass_actors=[_actor(None)])]
    assert _decode_bypass(sets, "main") == 0


def test_bypass_malformed_json_exits_20():
    r = subprocess.run(
        [BASH, str(SCRIPT), "--decode-bypass", "stage"],
        input="{not json",
        text=True,
        capture_output=True,
    )
    assert r.returncode == 20
    # 20 must come from the decoder itself. Every other route to 20 — the unknown-flow arm,
    # the "gh/python3/repo unavailable" skip — narrates on stderr first, so silence is what
    # proves `--decode-bypass` was dispatched before any of them, the way `--decode` is.
    assert r.stderr == ""


def test_bypass_object_instead_of_array_exits_20():
    # same shape contract as --decode: unreadable must never read as "no gap"
    r = subprocess.run(
        [BASH, str(SCRIPT), "--decode-bypass", "stage"],
        input="{}",
        text=True,
        capture_output=True,
    )
    assert r.returncode == 20
    assert r.stderr == ""


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


def _body(rs) -> str:
    # a plain str value is emitted verbatim, so a test can serve a body that is not JSON
    return rs if isinstance(rs, str) else json.dumps(rs)


def _gh_stub_script(
    rulesets_by_id: dict,
    org_rulesets_by_id: dict | None = None,
    default_branch: str | None = None,
) -> str:
    """A fake `gh` placed on PATH so the non-`--decode` dispatch path (list ids, then
    fetch each ruleset) can be driven without a real `gh` install or network access.

    `rulesets_by_id` is the id list AND the repo-scoped bodies. An id mapped to `None`
    serves the list but makes `repos/.../rulesets/<id>` fail — how GitHub answers for a
    ruleset inherited from the org. `org_rulesets_by_id` then serves those from
    `orgs/.../rulesets/<id>`. `default_branch` answers `repos/{owner}/{repo}`.
    """
    ids_out = "\n".join(str(rid) for rid in rulesets_by_id)
    repo_cases = "\n".join(
        f"    repos/*/rulesets/{rid}) "
        + ("exit 1 ;;" if rs is None else f"printf '%s' '{_body(rs)}' ;;")
        for rid, rs in rulesets_by_id.items()
    )
    org_cases = "\n".join(
        f"    orgs/*/rulesets/{rid}) printf '%s' '{_body(rs)}' ;;"
        for rid, rs in (org_rulesets_by_id or {}).items()
    )
    # the stub answers as the caller's `--jq` would (same convention as the id list above),
    # so this is the bare branch name, not the repo object
    repo_meta = (
        f"    repos/*) printf '{default_branch}\\n' ;;\n" if default_branch is not None else ""
    )
    return (
        "#!/usr/bin/env bash\n"
        # every api path is appended to GH_STUB_LOG when set, so a test can assert on which
        # endpoints were actually reached — an exit code alone cannot tell "fetched id 2 and
        # found a gap" apart from "gave up at id 1"
        'if [ -n "${GH_STUB_LOG:-}" ]; then printf "%s\\n" "$2" >> "$GH_STUB_LOG"; fi\n'
        'if [ "$1" = "api" ]; then\n'
        '  case "$2" in\n'
        f"{repo_cases}\n"
        f"{org_cases}\n"
        f"    repos/*/rulesets) printf '{ids_out}\\n' ;;\n"
        # last among the repos/* patterns: it would otherwise swallow the rulesets paths
        f"{repo_meta}"
        "    *) exit 1 ;;\n"
        "  esac\n"
        "  exit 0\n"
        "fi\n"
        "exit 1\n"
    )


def _run_dispatch(
    rulesets_by_id: dict,
    flows: list[str],
    branch_env: dict,
    org_rulesets_by_id: dict | None = None,
    default_branch: str | None = None,
    fetch_log: Path | None = None,
) -> subprocess.CompletedProcess:
    with tempfile.TemporaryDirectory() as d:
        gh_path = Path(d) / "gh"
        gh_path.write_text(
            _gh_stub_script(rulesets_by_id, org_rulesets_by_id, default_branch),
            encoding="utf-8",
        )
        gh_path.chmod(0o755)
        env = dict(os.environ)
        env["PATH"] = str(d) + os.pathsep + env.get("PATH", "")
        env["HARNESS_REPO"] = "test/repo"
        if fetch_log is not None:
            env["GH_STUB_LOG"] = str(fetch_log)
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
        2: _ruleset("refs/heads/stage", ["merge"], bypass_actors=ACTOR),
        3: _ruleset("refs/heads/main", ["merge"], bypass_actors=ACTOR),
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


def test_promotion_bypass_gap_is_reported_even_when_methods_match():
    # THE regression this check exists for. stage/main allow exactly "merge" — the merge-method
    # verdict is a clean pass — but neither ruleset lists a bypass actor. That is precisely the
    # configuration that breaks releases: "Require a pull request" rejects semantic-release's
    # direct chore(release) push, so the pipeline stops. Reporting "merge rulesets match" here
    # tells the repo owner everything is fine about the one setting that is not.
    rulesets = {
        1: _ruleset("refs/heads/stage", ["merge"], bypass_actors=[]),
        2: _ruleset("refs/heads/main", ["merge"], bypass_actors=[]),
    }
    r = _run_dispatch(
        rulesets,
        ["promotion"],
        {"HARNESS_BRANCH_STAGING": "stage", "HARNESS_BRANCH_PRODUCTION": "main"},
    )
    assert r.returncode == 10
    assert "BYPASS ACTOR for the release automation" in r.stderr
    assert "chore(release)" in r.stderr
    # the merge methods really are correct, so no method guidance should be printed…
    assert "allowed merge methods must be exactly" not in r.stderr
    # …and the run must not simultaneously claim the rulesets are fine
    assert "match the required methods" not in r.stderr


def test_daily_bypass_gap_is_reported_even_when_methods_match():
    # Same failure, the other flow: dev allows exactly rebase,squash but has no bypass actor,
    # so `git push origin dev` — how the post-release back-merge lands — is rejected.
    rulesets = {1: _ruleset("refs/heads/dev", ["rebase", "squash"], bypass_actors=[])}
    r = _run_dispatch(rulesets, ["daily"], {"HARNESS_BRANCH_INTEGRATION": "dev"})
    assert r.returncode == 10
    assert "BYPASS ACTOR for the post-release back-merge" in r.stderr
    assert "allowed merge methods must be exactly" not in r.stderr
    assert "match the required methods" not in r.stderr


def test_fully_correct_setup_reports_match():
    # The other half of the contract: with methods right AND a bypass actor on every branch,
    # the run passes clean. Without this, a check that always warns would also pass the test
    # above while being useless.
    rulesets = {
        1: _ruleset("refs/heads/dev", ["rebase", "squash"], bypass_actors=ACTOR),
        2: _ruleset("refs/heads/stage", ["merge"], bypass_actors=ACTOR),
        3: _ruleset("refs/heads/main", ["merge"], bypass_actors=ACTOR),
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
    assert r.returncode == 0
    assert "BYPASS ACTOR" not in r.stderr
    assert "match the required methods" in r.stderr


def test_bypass_warning_is_printed_once_when_methods_also_differ():
    # Both gaps at once on the same flow. The bypass reason is one paragraph of guidance; the
    # method check and the bypass check must not each emit their own copy.
    rulesets = {
        1: _ruleset("refs/heads/stage", ["merge", "squash"], bypass_actors=[]),
        2: _ruleset("refs/heads/main", ["merge"], bypass_actors=[]),
    }
    r = _run_dispatch(
        rulesets,
        ["promotion"],
        {"HARNESS_BRANCH_STAGING": "stage", "HARNESS_BRANCH_PRODUCTION": "main"},
    )
    assert r.returncode == 10
    assert "stage: allowed merge methods" in r.stderr
    assert r.stderr.count("BYPASS ACTOR for the release automation") == 1


def test_bypass_guidance_names_the_required_mode():
    # A repo can reach this warning WITH an actor already listed — one in "pull_request" mode,
    # which the check counts as a gap. Guidance that only says "add a bypass actor" is a dead
    # end for exactly that reader: they look, see an actor, and conclude the check is wrong.
    rulesets = {
        1: _ruleset("refs/heads/stage", ["merge"], bypass_actors=[_actor("pull_request")]),
        2: _ruleset("refs/heads/main", ["merge"], bypass_actors=[_actor("pull_request")]),
    }
    r = _run_dispatch(
        rulesets,
        ["promotion"],
        {"HARNESS_BRANCH_STAGING": "stage", "HARNESS_BRANCH_PRODUCTION": "main"},
    )
    assert r.returncode == 10
    assert "bypass_mode" in r.stderr
    assert "pull_request" in r.stderr


def test_bypass_check_undecodable_reports_undetermined_not_a_gap():
    # The bypass axis inherits the same 20-never-collapses-to-10 contract as the method axis:
    # a ruleset that could not be read must not be reported as "you are missing a bypass actor".
    r = _run_dispatch({1: "{not json"}, ["promotion"], {"HARNESS_BRANCH_STAGING": "stage"})
    assert r.returncode == 20
    assert "BYPASS ACTOR" not in r.stderr


def test_org_inherited_ruleset_is_read_from_the_org_endpoint():
    # `GET repos/{o}/{r}/rulesets` lists rulesets inherited from the org, but their CONTENT
    # is not readable at the repo-scoped id endpoint. Treating that one failure as fatal
    # turned the whole check into a permanent exit 20 for every org that manages rulesets
    # centrally — the check silently switched itself off for exactly those repos.
    r = _run_dispatch(
        {1: None},
        ["promotion"],
        {"HARNESS_BRANCH_STAGING": "stage", "HARNESS_BRANCH_PRODUCTION": "main"},
        org_rulesets_by_id={
            1: _ruleset("~ALL", ["merge"], bypass_actors=ACTOR),
        },
    )
    assert r.returncode == 0
    assert "match the required methods" in r.stderr


def test_a_ruleset_readable_from_neither_endpoint_is_undetermined():
    # When the content cannot be read at all we do not know whether that ruleset governs
    # these branches, so no verdict is honest. 20, never 0 and never 10.
    r = _run_dispatch(
        {1: None},
        ["promotion"],
        {"HARNESS_BRANCH_STAGING": "stage", "HARNESS_BRANCH_PRODUCTION": "main"},
    )
    assert r.returncode == 20
    assert "match" not in r.stderr.lower()
    assert "allowed merge methods must be exactly" not in r.stderr


def test_one_unreadable_ruleset_does_not_discard_the_readable_ones(tmp_path: Path):
    # The failure must stay scoped to its own id. The exit code cannot show that — the old
    # `|| exit 1` produced 20 here too, by abandoning the whole list — so assert on what
    # actually distinguishes the two: whether id 2 was ever fetched.
    log = tmp_path / "fetches.txt"
    r = _run_dispatch(
        {1: None, 2: _ruleset("refs/heads/stage", ["merge"], bypass_actors=ACTOR)},
        ["promotion"],
        {"HARNESS_BRANCH_STAGING": "stage", "HARNESS_BRANCH_PRODUCTION": "main"},
        fetch_log=log,
    )
    assert r.returncode == 20
    fetched = log.read_text(encoding="utf-8").split()
    assert "repos/test/repo/rulesets/1" in fetched
    assert "orgs/test/rulesets/1" in fetched, "the org fallback was not attempted"
    assert "repos/test/repo/rulesets/2" in fetched, "the loop abandoned the remaining ids"


def test_default_branch_alias_is_resolved_through_the_dispatch():
    # ~DEFAULT_BRANCH is only decidable with the repo's default branch in hand; the dispatch
    # is what resolves it and hands it to both decoders.
    r = _run_dispatch(
        {1: _ruleset("~DEFAULT_BRANCH", ["merge"], bypass_actors=ACTOR)},
        ["promotion"],
        {"HARNESS_BRANCH_STAGING": "stage", "HARNESS_BRANCH_PRODUCTION": "main"},
        default_branch="main",
    )
    # main matches the alias and is exactly "merge"; stage matches nothing, so it differs
    assert r.returncode == 10
    assert "stage: allowed merge methods" in r.stderr
    assert "main: allowed merge methods" not in r.stderr


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


SKILL = Path(__file__).resolve().parent.parent / "skills" / "flow-init" / "SKILL.md"
PLUGIN_ROOT = Path(__file__).resolve().parent.parent


def _step_27_block() -> str:
    """The Step 2.7 shell block, lifted verbatim out of the skill so it can be RUN.

    Asserting on the block's *text* is not enough: the pre-fix hard error can be restored on
    a line of its own and still satisfy any grep-shaped check. Only executing it proves the
    behavior.
    """
    blocks = re.findall(r"```bash\n(.*?)```", SKILL.read_text(encoding="utf-8"), re.DOTALL)
    hits = [b for b in blocks if "check-merge-ruleset.sh" in b]
    assert len(hits) == 1, f"expected exactly one Step 2.7 bash block, found {len(hits)}"
    return hits[0]


def _run_step_27(tmp: Path, gh_stub: str | None) -> subprocess.CompletedProcess:
    """Run the block against a real config, with `gh` absent or failing.

    `python3` is shimmed onto the venv interpreter because the block imports PyYAML, and the
    system python3 on a dev box generally has not got it.
    """
    root = tmp / "host"
    cfgdir = root / ".claude" / "harness-tier" / "config"
    cfgdir.mkdir(parents=True)
    (cfgdir / "flow-config.yaml").write_text(
        "branches:\n"
        "  integration: dev\n"
        "  staging: stage\n"
        "  production: main\n"
        "merge_workflow:\n"
        "  pull_request: [promotion]\n",
        encoding="utf-8",
    )
    shim = tmp / "bin"
    shim.mkdir()
    (shim / "python3").write_text(
        f'#!/usr/bin/env bash\nexec "{sys.executable}" "$@"\n', encoding="utf-8"
    )
    (shim / "python3").chmod(0o755)
    if gh_stub is not None:
        (shim / "gh").write_text(gh_stub, encoding="utf-8")
        (shim / "gh").chmod(0o755)

    # every PATH entry that carries a real `gh` is dropped, so "absent" really is absent
    keep = [
        d
        for d in os.environ.get("PATH", "").split(os.pathsep)
        if d and not any((Path(d) / n).exists() for n in ("gh", "gh.exe"))
    ]
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([str(shim), *keep])
    env["ROOT"] = str(root)
    env["PLUGIN"] = str(PLUGIN_ROOT)

    script = tmp / "step27.sh"
    script.write_text(_step_27_block(), encoding="utf-8")
    return subprocess.run([BASH, str(script)], capture_output=True, text=True, env=env)


def test_step_27_skips_instead_of_dying_when_gh_is_absent(tmp_path: Path):
    """The caller must not be stricter than the script it calls.

    `check-merge-ruleset.sh` degrades a missing/unauthenticated `gh` to exit 20 ("skipping"),
    and Step 2.7 documents continuing on 10 and 20 alike. But the block reached the script
    through `REPO="$(gh repo view …)" || exit 1`, so on a host without `gh` the step died
    with a hard error before the graceful path could ever run — stopping `/flow-init` for a
    team whose only sin was not having the GitHub CLI installed.
    """
    r = _run_step_27(tmp_path, gh_stub=None)
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    assert "skipping" in (r.stdout + r.stderr)


def test_step_27_skips_when_gh_cannot_resolve_a_repo(tmp_path: Path):
    # `gh` installed but unauthenticated, or a repo with no GitHub remote: also not a config
    # defect, also not a reason to stop /flow-init.
    r = _run_step_27(tmp_path, gh_stub="#!/usr/bin/env bash\nexit 1\n")
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    assert "skipping" in (r.stdout + r.stderr)


def test_step_27_still_stops_on_a_broken_branches_config(tmp_path: Path):
    # The other half of the distinction: a config error must still be fatal. Without this,
    # "skip on anything that fails" would pass both tests above and silence real defects.
    root = tmp_path / "host"
    cfgdir = root / ".claude" / "harness-tier" / "config"
    cfgdir.mkdir(parents=True)
    (cfgdir / "flow-config.yaml").write_text(
        "branches:\n  integration: dev\nmerge_workflow:\n  pull_request: [promotion]\n",
        encoding="utf-8",
    )
    shim = tmp_path / "bin"
    shim.mkdir()
    (shim / "python3").write_text(
        f'#!/usr/bin/env bash\nexec "{sys.executable}" "$@"\n', encoding="utf-8"
    )
    (shim / "python3").chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = os.pathsep.join([str(shim), env.get("PATH", "")])
    env["ROOT"] = str(root)
    env["PLUGIN"] = str(PLUGIN_ROOT)
    script = tmp_path / "step27.sh"
    script.write_text(_step_27_block(), encoding="utf-8")
    r = subprocess.run([BASH, str(script)], capture_output=True, text=True, env=env)
    assert r.returncode == 1
    assert "branches.staging" in r.stderr


def test_script_never_calls_a_write_api():
    # The whole point of this script is that it reads. A method flag on a gh/curl call is the
    # only way it could write, so its absence is the structural guarantee.
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--method" not in text
    assert "-X " not in text
    for verb in ("POST", "PUT", "PATCH", "DELETE"):
        assert verb not in text
