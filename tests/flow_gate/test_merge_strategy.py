from pathlib import Path

import pytest

import scripts.flow_gate_check as fgc
from scripts.flow_gate_check import (
    _branch_matches,
    _target_from_command,
    load_merge_strategy,
    match_merge_rule,
    parse_merge_command,
)


def test_merge_strategy_loads_rules(tmp_path: Path):
    tiers = tmp_path / "flow-tiers.yaml"
    tiers.write_text(
        "tiers:\n  dev:\n    gates: [review]\n"
        "merge_strategy:\n"
        '  - source: "feature/*"\n'
        "    target: integration\n"
        '    require: "--squash"\n'
        "    warn_unless_rebased: true\n",
        encoding="utf-8",
    )
    rules = load_merge_strategy(tiers)
    assert len(rules) == 1
    assert rules[0]["source"] == "feature/*"
    assert rules[0]["require"] == "--squash"
    assert rules[0]["warn_unless_rebased"] is True


def test_merge_strategy_absent_key_is_empty(tmp_path: Path):
    tiers = tmp_path / "flow-tiers.yaml"
    tiers.write_text("tiers:\n  dev:\n    gates: [review]\n", encoding="utf-8")
    assert load_merge_strategy(tiers) == []


def test_merge_strategy_missing_file_is_empty(tmp_path: Path):
    assert load_merge_strategy(tmp_path / "absent.yaml") == []


def test_merge_strategy_parse_error_is_empty(tmp_path: Path):
    tiers = tmp_path / "flow-tiers.yaml"
    tiers.write_text("merge_strategy: [unclosed\n", encoding="utf-8")
    assert load_merge_strategy(tiers) == []


def test_merge_strategy_non_list_is_empty(tmp_path: Path):
    tiers = tmp_path / "flow-tiers.yaml"
    tiers.write_text("merge_strategy:\n  feature: squash\n", encoding="utf-8")
    assert load_merge_strategy(tiers) == []


def test_parse_merge_plain():
    assert parse_merge_command("git merge feature/x") == (set(), "feature/x")


def test_parse_merge_squash():
    flags, src = parse_merge_command("git merge --squash feature/x")
    assert flags == {"--squash"}
    assert src == "feature/x"


def test_parse_merge_worktree_dash_c():
    # `git -C <dir> merge X` — the -C argument must not be taken as the source
    flags, src = parse_merge_command("git -C /tmp/wt merge --squash feature/x")
    assert flags == {"--squash"}
    assert src == "feature/x"


@pytest.mark.parametrize("prefix", ["/usr/bin/", "/usr/local/bin/", "C:/Git/bin/"])
def test_parse_merge_path_qualified_git(prefix: str):
    """The merge verdict is one of the three fail-CLOSED exceptions, so a spelling this half
    stops recognising does not degrade — it stops enforcing merge strategy in silence, while
    the runner's unanchored self-filter still engages the hook. Invariant #1 exception 3."""
    flags, src = parse_merge_command(f"{prefix}git merge --no-ff dev")
    assert flags == {"--no-ff"}
    assert src == "dev"


def test_parse_merge_message_arg_not_source():
    # -m's quoted argument must not be mistaken for the source branch
    flags, src = parse_merge_command('git merge --no-ff -m "Merge stage: headline" origin/stage')
    assert flags == {"--no-ff"}
    assert src == "origin/stage"


def test_parse_merge_gpg_sign_keeps_source():
    # git takes the keyid ATTACHED (-Skeyid / --gpg-sign=keyid), never as a separate token. If
    # -S/--gpg-sign are treated as taking the next token, they swallow the source branch and the
    # whole check silently fails open for every signed merge.
    assert parse_merge_command("git merge -S feature/x") == ({"-S"}, "feature/x")
    assert parse_merge_command("git merge --gpg-sign feature/x")[1] == "feature/x"
    assert parse_merge_command("git merge -Skeyid feature/x")[1] == "feature/x"
    assert parse_merge_command("git merge --gpg-sign=keyid feature/x")[1] == "feature/x"


def test_parse_merge_strategy_flags_still_take_an_argument():
    # the flags that genuinely consume the next token must keep doing so (guard against
    # over-correcting the -S fix into "no flag takes an argument")
    assert parse_merge_command("git merge -s ours feature/x")[1] == "feature/x"
    assert parse_merge_command("git merge -X theirs feature/x")[1] == "feature/x"


def test_parse_merge_ff_only():
    flags, src = parse_merge_command("git merge --ff-only origin/main")
    assert flags == {"--ff-only"}
    assert src == "origin/main"


def test_parse_merge_base_is_not_a_merge():
    # `git merge-base` / `git merge-file` must not be detected as a merge
    assert parse_merge_command("git merge-base --is-ancestor a b") == (set(), None)
    assert parse_merge_command("git merge-file a b c") == (set(), None)


def test_parse_merge_not_a_merge_command():
    assert parse_merge_command("git commit -m 'x'") == (set(), None)


def test_parse_merge_unbalanced_quote_fails_open():
    assert parse_merge_command('git merge -m "unclosed feature/x') == (set(), None)


def test_parse_merge_no_source():
    # `git merge` with no argument (continue an in-progress merge)
    assert parse_merge_command("git merge") == (set(), None)


BRANCHES = {
    "integration": "dev",
    "staging": "stage",
    "production": "main",
    "feature_prefix": "feature/",
}
# Mirrors the shipped flow-tiers.yaml `merge_strategy`, row for row and in order. It is a
# fixture, not the contract (test_shipped_policy_* owns that) — but a fixture that drifts from
# the policy silently tests a shape nobody ships, and a missing row reads as a row that may be
# deleted. The one flow deliberately absent here is absent there too: the back-merge
# (production → integration) states a choice, so there is nothing to enforce.
RULES = [
    {
        "source": "feature/*",
        "target": "integration",
        "require": "--squash",
        "warn_unless_rebased": True,
    },
    {"source": "hotfix/*", "target": "production", "require": "--squash"},
    {"source": "integration", "target": "staging", "require": "--no-ff"},
    {"source": "staging", "target": "production", "require": "--no-ff"},
    {"source": "fix/*", "target": "integration", "forbid": "--no-ff"},
]


def test_branch_matches_prefix_glob():
    assert _branch_matches("feature/*", "feature/merge-gate", BRANCHES) is True
    assert _branch_matches("feature/*", "fix/typo", BRANCHES) is False


def test_branch_matches_config_key():
    assert _branch_matches("integration", "dev", BRANCHES) is True
    assert _branch_matches("integration", "stage", BRANCHES) is False
    assert _branch_matches("production", "main", BRANCHES) is True


def test_branch_matches_strips_origin_prefix():
    assert _branch_matches("staging", "origin/stage", BRANCHES) is True


def test_branch_matches_unknown_key_is_false():
    assert _branch_matches("nonesuch", "dev", BRANCHES) is False


def test_target_from_command_switch_and_checkout():
    assert _target_from_command("git switch dev && git merge feature/x") == "dev"
    assert _target_from_command("git checkout dev && git merge feature/x") == "dev"
    # the documented three-step block, verbatim
    assert (
        _target_from_command("git switch dev && git pull --ff-only && git merge --squash feature/x")
        == "dev"
    )


def test_target_from_command_takes_the_last_switch_before_the_merge():
    cmd = "git switch stage && git switch dev && git merge feature/x"
    assert _target_from_command(cmd) == "dev"


def test_target_from_command_ignores_a_switch_after_the_merge():
    assert _target_from_command("git merge feature/x && git switch main") is None


def test_target_from_command_none_when_unclear():
    # no switch at all, and forms whose operand is not plainly a branch → keep the hook-time
    # branch (FAIL-OPEN: never invent a target)
    assert _target_from_command("git merge feature/x") is None
    assert _target_from_command("git switch -c feature/y && git merge feature/x") is None
    assert _target_from_command("git checkout -- some/file && git merge feature/x") is None


def test_target_from_command_checkout_with_a_pathspec_is_unclear():
    # `git checkout <branch> -- <path>` restores a file from that branch; HEAD stays where it is.
    # A token rule that only rejects a leading `-` reads `dev` here and blocks a merge into a
    # branch the command never entered.
    assert _target_from_command("git checkout dev -- a/b.py && git merge feature/x") is None


def test_target_from_command_one_unclear_switch_voids_the_whole_chain():
    # HEAD ends on feature/y. Scanning for the last *matching* switch skips the unclear
    # `-c` form and adopts the stale `dev`, so the rule for a flow that is not happening fires.
    cmd = "git switch dev && git switch -c feature/y && git merge feature/x"
    assert _target_from_command(cmd) is None
    # …and the same in the other order: an unclear switch BEFORE a clear one is still unclear,
    # because the clear one may itself be conditioned on the first having run.
    assert _target_from_command("git switch --detach && git switch dev && git merge f/x") is None


def test_target_from_command_origin_ref_is_unclear():
    # `git checkout origin/dev` lands on a DETACHED HEAD, not on dev — but _branch_matches strips
    # `origin/`, so adopting it as the target matches the integration rule and blocks.
    assert _target_from_command("git checkout origin/dev && git merge feature/x") is None


# Every merge test above writes its chain with `&&`, and a shell separates commands as well
# with a newline or a `;`. That blind spot let an operand cut missing `\n` ship green: the
# operand region ran past the end of the line, every switch read as unclear, and all
# newline-separated merges fell back to HEAD — through the gate. The separator is therefore an
# explicit axis here, not a formatting choice of whoever wrote the case.
_SEPS = pytest.mark.parametrize("sep", [" && ", "\n", "; "], ids=["and", "newline", "semicolon"])
# risk-tiers' "Merging feature/* → integration" block, verbatim: three newline-separated lines.
_DOC_IDIOM = ["git switch dev", "git pull --ff-only origin dev", "git merge --squash feature/x"]


@_SEPS
def test_target_from_command_reads_the_documented_block_under_any_separator(sep):
    # The idiom the policy itself prescribes. Claude Code sends it as ONE Bash call, and the
    # natural rendering of a three-step block is three LINES — the shape that must resolve to the
    # integration branch, or the documented procedure is exactly what walks through the gate.
    assert _target_from_command(sep.join(_DOC_IDIOM)) == "dev"
    assert _target_from_command(sep.join(["git switch dev", "git merge feature/x"])) == "dev"


# ── a command's operands stop where the next command starts ─────────────────────
# The operand region must stop at the command boundary: run it to end of input and anything
# later in the chain joins this
# merge's flags. Both directions are policy failures: a `require` row satisfied by a word the
# merge never carried lets a forbidden merge through, and a `forbid` row tripped by a word from
# another command blocks one the policy allows.


def test_parse_merge_ignores_a_flag_written_in_a_trailing_comment():
    assert parse_merge_command("git merge feature/x   # policy requires --squash") == (
        set(),
        "feature/x",
    )


def test_parse_merge_ignores_the_flags_of_the_next_command_in_the_chain():
    assert parse_merge_command("git merge --no-ff dev && rm -rf /tmp/x") == ({"--no-ff"}, "dev")


def test_parse_merge_ignores_a_switch_that_follows_it():
    # `git switch -` returns to the previous branch; its `-` is not a merge flag.
    assert parse_merge_command("git merge --no-ff stage && git switch -") == (
        {"--no-ff"},
        "stage",
    )


def test_parse_merge_keeps_a_flag_inside_its_own_quoted_message():
    # the operand cut must not fire inside a literal: `-m` still consumes its argument.
    assert parse_merge_command('git merge -m "please --squash it" feature/x') == (
        set(),
        "feature/x",
    )


def test_parse_merge_keeps_a_separator_that_sits_inside_its_message():
    """The cut is located on the MASK. Searched on the raw string, the `&&` inside a merge
    subject ends the operands before the source branch, `shlex` sees no operand at all, and
    the strategy verdict never runs — fail-CLOSED turned off by a commit message."""
    assert parse_merge_command('git merge --no-ff -m "Merge stage: a && b" origin/stage') == (
        {"--no-ff"},
        "origin/stage",
    )
    assert parse_merge_command('git merge -m "wip; done" feature/x') == (set(), "feature/x")


def test_target_from_command_reads_a_path_qualified_switch():
    # the switch shares the one invocation grammar now; its own spelling admitted no directory
    # prefix, so this chain named no target and the merge was judged against whatever HEAD was.
    assert _target_from_command("/usr/bin/git switch dev && git merge --no-ff stage") == "dev"


def test_target_from_command_reads_a_switch_followed_by_a_comment():
    # a comment ends the switch's operands; read past it the region holds three words, the switch
    # reads as unclear, and one unclear switch voids the whole chain.
    assert _target_from_command("git switch dev # go\ngit merge --no-ff stage") == "dev"


def test_target_from_command_reads_the_documented_block_with_crlf():
    # A Windows-authored heredoc carries `\r\n`. `\r` left out of the separator class strands the
    # operand as `dev\r`, which is one token and parses "clear" — so this would not fail loudly,
    # it would silently name a branch no rule matches and fall through.
    assert _target_from_command("\r\n".join(_DOC_IDIOM)) == "dev"


@_SEPS
@pytest.mark.parametrize(
    "steps",
    [
        pytest.param(["git checkout dev -- README.md", "git merge feature/x"], id="N1-pathspec"),
        pytest.param(
            ["git switch dev", "git switch -c feature/y", "git merge feature/x"], id="N2-switch-c"
        ),
        pytest.param(["git checkout origin/dev", "git merge feature/x"], id="M3-origin-ref"),
    ],
)
def test_target_from_command_false_positives_stay_unclear_under_any_separator(steps, sep):
    # The other direction of the same widening: teaching the parser to see across newlines must
    # not also teach it to *name* a target in the three shapes that produce false
    # blocks. Each must stay None under every separator, so the hook-time branch stands.
    assert _target_from_command(sep.join(steps)) is None


def test_points_elsewhere_ignores_a_non_git_dash_c(tmp_path: Path):
    # `-C` means "change directory" only as git's own global option. Unanchored, `grep -C 3`
    # resolves to the directory "3", which is foreign to root → the whole gate fails open.
    assert fgc._points_elsewhere("grep -C 3 foo f.txt && git merge feature/x", tmp_path) is False


def test_points_elsewhere_detects_a_leading_cd(tmp_path: Path):
    # `cd <dir> && git merge X` names the execution directory as `git -C <dir>` does.
    other = tmp_path / "other"
    assert fgc._points_elsewhere(f"cd {other} && git merge feature/x", tmp_path) is True
    assert fgc._points_elsewhere(f"cd {tmp_path} && git merge feature/x", tmp_path) is False


@_SEPS
def test_points_elsewhere_detects_a_leading_cd_under_any_separator(tmp_path: Path, sep):
    # The fail-CLOSED half of the same separator blind spot. `cd <wt>` on its own LINE is the
    # ordinary way to write this, and recognising only `&&` reads it as no cd at all: the source
    # comes from the command while the target is read from THIS root, and the merge is blocked in
    # the name of a flow that is not happening. Detection here only ever fails OPEN.
    other = tmp_path / "other"
    assert fgc._points_elsewhere(sep.join([f"cd {other}", "git merge feature/x"]), tmp_path) is True
    # …and root itself is still not foreign, so the gate stays enforced where it should be.
    assert (
        fgc._points_elsewhere(sep.join([f"cd {tmp_path}", "git merge feature/x"]), tmp_path)
        is False
    )


def test_points_elsewhere_resolves_a_relative_dir_against_root(tmp_path: Path):
    # The merge branch runs BEFORE precommit-runner.sh's `cd "$ROOT"`, so the interpreter's cwd is
    # the hook cwd. Resolving `.` against that cwd makes `git -C .` look foreign and skips the
    # gate; it must be read against root, where it is root itself and stays enforced.
    assert fgc._points_elsewhere("git -C . merge feature/x", tmp_path) is False


def test_match_rule_feature_to_integration():
    rule = match_merge_rule(RULES, "feature/x", "dev", BRANCHES)
    assert rule is not None
    assert rule["require"] == "--squash"


def test_match_rule_staging_to_production():
    rule = match_merge_rule(RULES, "origin/stage", "main", BRANCHES)
    assert rule is not None
    assert rule["require"] == "--no-ff"


def test_match_rule_fix_to_integration():
    rule = match_merge_rule(RULES, "fix/typo", "dev", BRANCHES)
    assert rule is not None
    assert rule["forbid"] == "--no-ff"


def test_match_rule_integration_to_staging():
    # The promotion is a MERGE, not a rebase: the release commits must reach staging under
    # their original SHAs or the stable tag drops out of its ancestry (risk-tiers.md
    # "Back-merge after release"). This row is why staging needs no back-merge leg.
    rule = match_merge_rule(RULES, "dev", "stage", BRANCHES)
    assert rule is not None
    assert rule["require"] == "--no-ff"


def test_match_rule_no_match_returns_none():
    # The back-merge (production → integration) is the one flow with no rule: the policy
    # states a choice there ("FF / --no-ff Merge"), so there is nothing to enforce.
    assert match_merge_rule(RULES, "main", "dev", BRANCHES) is None


def test_match_rule_empty_rules_returns_none():
    assert match_merge_rule([], "feature/x", "dev", BRANCHES) is None
