"""Spellings of a merge git accepts that the strategy verdict has to read the way git does: an
abbreviated long option, the last of two opposing options, a `-c merge.ff` override, a source
named by its full ref, a subcommand split by quoting, and a merge `git pull` performs."""

from pathlib import Path

import pytest

import scripts.flow_gate_check as fgc
from tests.flow_gate._helpers import _init_repo, _rg, _run_runner, requires_bash_git
from tests.flow_gate.test_merge_check import _run_merge_check


def _policy(tmp_path: Path) -> Path:
    cfg = tmp_path / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-tiers.yaml").write_text(
        "tiers:\n  dev:\n    gates: [review]\n"
        "merge_strategy:\n"
        '  - source: "feature/*"\n    target: integration\n    require: "--squash"\n'
        '  - source: staging\n    target: production\n    require: "--no-ff"\n'
        '  - source: "fix/*"\n    target: integration\n    forbid: "--no-ff"\n',
        encoding="utf-8",
    )
    (cfg / "flow-config.yaml").write_text(
        "branches:\n  integration: dev\n  staging: stage\n  production: main\n",
        encoding="utf-8",
    )
    return tmp_path


# ── what git does with each flag spelling (verified against git 2.43's parse-options) ──


@pytest.mark.parametrize(
    "command,flag,present",
    [
        ("git merge --no-f fix/x", "--no-ff", True),
        ("git merge --squas feature/x", "--squash", True),
        ("git merge --sq feature/x", "--squash", True),
        # the last of two opposing options wins
        ("git merge --squash --no-squash feature/x", "--squash", False),
        ("git merge --no-squash --squash feature/x", "--squash", True),
        ("git merge --no-ff --ff fix/x", "--no-ff", False),
        ("git merge --no-ff --ff-only fix/x", "--no-ff", False),
        ("git merge --ff --no-ff fix/x", "--no-ff", True),
        # `--ff` is an option of its own, never an abbreviation of `--ff-only`
        ("git merge --ff fix/x", "--ff-only", False),
        # a config override stands in for the flag unless an explicit flag follows
        ("git -c merge.ff=false merge fix/x", "--no-ff", True),
        ("git -c Merge.FF=no merge fix/x", "--no-ff", True),
        ("git -c merge.ff=false merge --ff fix/x", "--no-ff", False),
        ("git -c merge.ff=true merge fix/x", "--no-ff", False),
        ("git -c merge.ff=only merge fix/x", "--ff-only", True),
    ],
)
def test_a_flag_is_read_the_way_git_reads_it(command, flag, present):
    merges = fgc.parse_merge_commands(command)
    assert merges, command
    assert (flag in merges[0][0]) is present, (command, merges)


@pytest.mark.parametrize(
    "command,source",
    [
        ("git mer''ge --no-ff fix/x", "fix/x"),
        ('git mer""ge --no-ff fix/x', "fix/x"),
        ("git m\\erge --no-ff fix/x", "fix/x"),
        ("git -C /tmp/wt mer''ge --no-ff fix/x", "fix/x"),
    ],
)
def test_a_quote_split_merge_is_parsed(command, source):
    merges = fgc.parse_merge_commands(command)
    assert merges and merges[0][1] == source, (command, merges)
    assert "--no-ff" in merges[0][0]


@pytest.mark.parametrize(
    "source",
    ["refs/heads/feature/x", "refs/remotes/origin/feature/x", "remotes/origin/feature/x"],
)
def test_a_full_ref_matches_its_branch_rule(source):
    assert fgc._branch_matches("feature/*", source, {})


def test_a_full_ref_matches_a_configured_branch():
    assert fgc._branch_matches("integration", "refs/heads/dev", {"integration": "dev"})


# ── git pull ──────────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "command,source,squash",
    [
        ("git pull origin feature/x", "feature/x", False),
        ("git pull --squash origin feature/x", "feature/x", True),
        ("git pull --no-rebase origin feature/x", "feature/x", False),
        ("git pull --rebase=false origin feature/x", "feature/x", False),
        ("git pull origin +feature/x:feature/x", "feature/x", False),
        ("git pull -s ort origin feature/x", "feature/x", False),
    ],
)
def test_a_pull_naming_a_branch_is_a_merge_of_it(command, source, squash):
    pulls = fgc.parse_pull_commands(command)
    assert pulls and pulls[0][1] == source, (command, pulls)
    assert ("--squash" in pulls[0][0]) is squash


@pytest.mark.parametrize(
    "command",
    [
        "git pull",
        "git pull --ff-only",
        "git pull origin",
        "git pull --rebase origin feature/x",
        "git pull --reb origin feature/x",
        "git pull -r origin feature/x",
        "git pull --rebase=interactive origin feature/x",
    ],
)
def test_a_pull_that_names_no_branch_or_rebases_is_not_judged(command):
    assert fgc.parse_pull_commands(command) == []


# ── the verdict ───────────────────────────────────────────────────────────────


@requires_bash_git
@pytest.mark.parametrize(
    "command",
    [
        "git pull origin stage",
        "git merge --no-f origin/stage --ff",
        "git mer''ge refs/heads/stage",
    ],
)
def test_the_runner_hands_every_spelling_to_the_verdict(tmp_path, command):
    """Through the real runner: the pre-filter has to spawn the classifier on a pull, and the
    classifier has to answer merge for it. The shipped policy requires --no-ff into main."""
    main = tmp_path / "main"
    _init_repo(main)
    cfg = main / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-config.yaml").write_text(
        "branches:\n  integration: dev\n  staging: stage\n  production: main\n", encoding="utf-8"
    )
    _rg(["add", "-A"], main)
    _rg(["commit", "-m", "cfg"], main)
    r = _run_runner(main, command)
    assert r.returncode == fgc.BLOCK_EXIT_CODE, (r.returncode, r.stdout, r.stderr)
    assert "--no-ff" in r.stdout + r.stderr


@pytest.mark.parametrize(
    "command,branch,blocked",
    [
        ("git merge --no-f fix/x", "dev", True),
        ("git -c merge.ff=false merge fix/x", "dev", True),
        ("git mer''ge --no-ff fix/x", "dev", True),
        ("git merge --no-ff --ff fix/x", "dev", False),
        ("git merge --squash --no-squash feature/x", "dev", True),
        ("git merge --squas feature/x", "dev", False),
        ("git merge refs/heads/feature/x", "dev", True),
        ("git merge --squash refs/heads/feature/x", "dev", False),
        ("git pull origin feature/x", "dev", True),
        ("git pull --squash origin feature/x", "dev", False),
        ("git pull --no-ff origin fix/x", "dev", True),
        ("git pull --rebase origin feature/x", "dev", False),
        ("git switch dev && git pull origin feature/x", "feature/x", True),
        ("git pull --ff-only", "dev", False),
        # another worktree's branch is unknowable from here, so its pull is not judged
        ("git -C /elsewhere pull origin feature/x", "dev", False),
    ],
)
def test_the_strategy_verdict_reads_every_spelling(monkeypatch, tmp_path, command, branch, blocked):
    _policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, command, branch)
    assert (code == fgc.BLOCK_EXIT_CODE) is blocked, (command, code)


@pytest.mark.parametrize("command", ["git pull origin feature/x", "git pu''ll origin feature/x"])
def test_a_pull_reaches_the_gate_and_is_read_as_a_merge(command):
    from tests.skills.test_gate_reachability import reaches_the_gate

    assert reaches_the_gate(command)
    assert fgc.parse_pull_commands(command)


# ── review round 1: what the readers above must not do ─────────────────────────

COMMIT_SKILL_BODY = (
    "msg=$(cat <<'EOF'\nfix: x\n\n- then git merge feature/x\nEOF\n)\n"
    "printf '%s\n' \"$msg\" | git commit -F -"
)


@pytest.mark.parametrize(
    "command",
    [
        COMMIT_SKILL_BODY,
        "git commit -F - <<'EOF'\nfix: x\n\n- then git merge feature/x\nEOF",
        "git commit -m x  # then git mer''ge feature/x",
    ],
)
def test_a_merge_a_commit_message_mentions_is_not_parsed(command):
    assert fgc.parse_merge_commands(command) == []


@pytest.mark.parametrize(
    "command,branch,blocked",
    [
        # the target of each merge is the switch before THAT merge
        ("git pull && git switch main && git merge stage", "dev", True),
        ("git pull && git switch dev && git merge stage", "main", False),
        ("git mer''ge dev && git switch stage", "dev", False),
        ("git pu''ll origin feature/x && git switch dev", "feature/x", False),
        ("git -C /elsewhere mer''ge --no-ff fix/x", "dev", False),
        # pull.ff outranks merge.ff for a pull
        ("git -c pull.ff=false pull origin dev", "stage", False),
        ("git -c merge.ff=false -c pull.ff=true pull origin fix/a", "dev", False),
        # an abbreviated option that takes a value consumes that value, not the next flag
        ("git pull --strategy-o theirs --no-ff origin dev", "stage", False),
        # a short bundle carrying -r rebases
        ("git pull -rmerges origin dev", "stage", False),
        ("git pull -qr origin dev", "stage", False),
        # -S takes its key attached: the r is the key, and this pull merges
        ("git pull -Sr origin stage", "main", True),
        # a pipe or a redirection glued to the last flag ends it
        ("git mer''ge dev --no-ff|cat", "stage", False),
        ("git mer''ge dev --no-ff>log", "stage", False),
        # a split merge beside a visible one, and inside a substitution, are still read
        ("git merge --squash a | git mer''ge feature/y", "dev", True),
        ("echo $(git mer''ge feature/y)", "dev", True),
        # -j takes its value attached only; --cleanup takes the next word
        ("git pull -j . feature/x", "dev", True),
        ("git merge --cleanup strip feature/x", "dev", True),
        # a config value is read as git reads it: untrimmed, and as an integer
        ("git -c 'merge.ff= false' merge fix/a", "dev", False),
        ("git -c merge.ff=00 merge fix/a", "dev", True),
    ],
)
def test_review_round_one_spellings(monkeypatch, tmp_path, command, branch, blocked):
    _policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, command, branch)
    assert (code == fgc.BLOCK_EXIT_CODE) is blocked, (command, code)


@pytest.mark.parametrize(
    "command,branch,blocked",
    [
        # a quote-split switch moves HEAD like any other, so the merge after it targets dev
        ("git sw''itch dev && git merge feature/x", "feature/x", True),
        ("git sw''itch dev && git merge --squash feature/x", "feature/x", False),
        ("git check''out dev && git merge feature/x", "feature/x", True),
        # one unclear switch still voids the chain: HEAD lands on a branch no rule names
        ("git sw''itch dev && git sw''itch -c y && git merge feature/x", "feature/x", False),
        # a remote branch detaches HEAD, so no integration rule applies to the merge
        ("git check''out origin/dev && git merge feature/x", "feature/x", False),
        # a quoted Windows path to git, with a split subcommand
        ("\"C:\\Git\\bin\\git.exe\" mer''ge --no-ff fix/x", "dev", True),
        ("C:\\\\Git\\\\bin\\\\git.exe mer''ge --no-ff fix/x", "dev", True),
        # an ANSI-C string spells the subcommand or the flag
        ("git $'\\x6derge' --no-ff fix/x", "dev", True),
        ("git merge $'--no-\\x66f' fix/x", "dev", True),
    ],
)
def test_review_round_two_spellings(monkeypatch, tmp_path, command, branch, blocked):
    _policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, command, branch)
    assert (code == fgc.BLOCK_EXIT_CODE) is blocked, (command, code)


def test_a_commit_whose_message_mentions_a_merge_is_not_blocked(monkeypatch, tmp_path):
    _policy(tmp_path)
    assert _run_merge_check(monkeypatch, tmp_path, COMMIT_SKILL_BODY, "dev") == 0
