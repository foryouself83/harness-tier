import json
import os
import subprocess
import tempfile
from pathlib import Path

from tests.merge_ruleset._helpers import ACTOR, BASH, SCRIPT, _actor, _ruleset


def _body(rs) -> str:
    # a plain str value is emitted verbatim, so a test can serve a body that is not JSON
    return rs if isinstance(rs, str) else json.dumps(rs)


# A failing `gh api` writes the API's error JSON to STDOUT and exits nonzero. A stub that
# merely exits nonzero cannot expose a caller that lets that body reach its own stdout.
GH_ERROR_BODY = """printf '%s' '{"message":"Not Found","status":"404"}'; exit 1"""


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
        + (f"{GH_ERROR_BODY} ;;" if rs is None else f"printf '%s' '{_body(rs)}' ;;")
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
        # endpoints were reached — an exit code alone cannot tell "fetched id 2 and
        # found a gap" apart from "gave up at id 1"
        'if [ -n "${GH_STUB_LOG:-}" ]; then printf "%s\\n" "$2" >> "$GH_STUB_LOG"; fi\n'
        'if [ "$1" = "api" ]; then\n'
        '  case "$2" in\n'
        f"{repo_cases}\n"
        f"{org_cases}\n"
        f"    repos/*/rulesets) printf '{ids_out}\\n' ;;\n"
        # last among the repos/* patterns: it would otherwise swallow the rulesets paths
        f"{repo_meta}"
        f"    *) {GH_ERROR_BODY} ;;\n"
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
    # An integration ruleset needs a bypass actor as much as a promotion one does, for a
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
    # the merge methods are correct, so no method guidance should be printed…
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


def test_an_error_body_shaped_like_json_is_undetermined_not_a_match():
    # gh writes its error body to stdout, and one carrying the text "id" passes the fetch
    # loop's shape test — so the verdict has to be taken on the PARSED object. Reading such a
    # body as a ruleset lets the second, correct ruleset satisfy the branch on its own and
    # reports "match" for an id nobody read: the wrong-0 the 0/10/20 contract forbids. The
    # body is served with exit 0, which is the only way this route is reachable at all.
    r = _run_dispatch(
        {
            1: '{"message":"Validation Failed","errors":[{"resource":"Ruleset","field":"id"}]}',
            2: _ruleset("~ALL", ["merge"], bypass_actors=ACTOR),
        },
        ["promotion"],
        {"HARNESS_BRANCH_STAGING": "stage", "HARNESS_BRANCH_PRODUCTION": "main"},
    )
    assert r.returncode == 20
    assert "match" not in r.stderr.lower()


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
    # distinguishes the two: whether id 2 was ever fetched.
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
