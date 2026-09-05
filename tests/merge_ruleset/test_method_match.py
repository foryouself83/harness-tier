from tests.merge_ruleset._helpers import _decode, _decode_bypass, _ruleset


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
# protected. Failing to count one that does apply is only noise.


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
