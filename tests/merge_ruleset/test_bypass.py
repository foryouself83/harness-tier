import subprocess

from tests.merge_ruleset._helpers import ACTOR, BASH, SCRIPT, _actor, _decode_bypass, _ruleset

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
