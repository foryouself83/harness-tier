from pathlib import Path

import yaml

import scripts.flow_gate_check as fgc
from scripts.flow_gate_check import missing_gates
from tests.flow_gate._helpers import (
    _classify_worktree_module,
    _init_repo,
    _rg,
    _run_runner,
    requires_bash_git,
)

# ── merge gate (git merge branches before the `git status` early-exit) ────────────
# Relies on this repo's own shipped flow-tiers.yaml merge_strategy — both promotion rows
# (integration → staging and staging → production require --no-ff; see risk-tiers.md Merge
# strategy) — since _run_runner points CLAUDE_PLUGIN_ROOT at this repo, and tiers_path()
# prefers CLAUDE_PLUGIN_ROOT/flow-tiers.yaml over any host config copy (dogfooding the real
# policy end-to-end).


@requires_bash_git
def test_runner_merge_gate_survives_clean_tree(tmp_path: Path):
    # Regression for the `git status` early-exit pitfall: a merge runs on a CLEAN working tree
    # by definition, so if the merge branch were placed after (or were missing before) that
    # early-exit, this would silently exit 0 with no output at all instead of blocking.
    main = tmp_path / "main"
    _init_repo(main)  # branch "main", clean tree
    cfg = main / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-config.yaml").write_text(
        "branches:\n  staging: stage\n  production: main\n", encoding="utf-8"
    )
    # Commit the config so the tree is genuinely clean before the merge (as it would be for a
    # real team — flow-config.yaml is git-tracked, per /flow-init). Leaving it untracked would
    # make the tree dirty and let an unrelated gate block first, masking whether the merge
    # branch runs before the `git status` early-exit.
    _rg(["add", "-A"], main)
    _rg(["commit", "-m", "cfg"], main)
    r = _run_runner(main, "git merge origin/stage")  # missing the required --no-ff
    assert r.returncode == fgc.BLOCK_EXIT_CODE
    assert "--no-ff" in (r.stdout + r.stderr)


@requires_bash_git
def test_runner_merge_gate_blocks_ff_promotion_to_staging(tmp_path: Path):
    # integration → staging must be a --no-ff merge. A bare `git merge <integration>` would
    # fast-forward and land staging's `[skip ci]` rc commit as HEAD, so release.yml's
    # `!contains(head_commit.message, '[skip ci]')` guard would skip the release entirely.
    main = tmp_path / "main"
    _init_repo(main)  # branch "main"
    _rg(["switch", "-c", "stage"], main)  # HEAD = staging branch → target resolves to staging
    cfg = main / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-config.yaml").write_text(
        "branches:\n  integration: dev\n  staging: stage\n  production: main\n",
        encoding="utf-8",
    )
    _rg(["add", "-A"], main)
    _rg(["commit", "-m", "cfg"], main)
    r = _run_runner(main, "git merge dev")  # missing the required --no-ff
    assert r.returncode == fgc.BLOCK_EXIT_CODE
    assert "--no-ff" in (r.stdout + r.stderr)


@requires_bash_git
def test_runner_merge_gate_reads_switch_target_from_command(tmp_path: Path):
    # `git switch <integration> && git merge feature/x` — the exact three-step idiom risk-tiers'
    # "Merging feature/* → integration" prescribes, which Claude Code sends as ONE Bash call. At
    # hook time HEAD is still feature/x, so reading the target from HEAD matches no rule and the
    # policy's own documented idiom would walk straight through the gate (exit 0).
    main = tmp_path / "main"
    _init_repo(main)
    _rg(["checkout", "-b", "feature/x"], main)
    cfg = main / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-config.yaml").write_text("branches:\n  integration: dev\n", encoding="utf-8")
    _rg(["add", "-A"], main)  # clean tree, as a real merge would have (flow-config is tracked)
    _rg(["commit", "-m", "cfg"], main)
    r = _run_runner(main, "git switch dev && git merge feature/x")  # missing --squash
    assert r.returncode == fgc.BLOCK_EXIT_CODE
    assert "--squash" in (r.stdout + r.stderr)


@requires_bash_git
def test_runner_merge_gate_reads_a_newline_separated_switch_target(tmp_path: Path):
    # The same idiom as above, written the way risk-tiers prints it: three LINES, no `&&`.
    # End-to-end because the unit test alone proved insufficient once — the whole merge suite was
    # written with `&&`, so a separator class missing `\n` passed 653 tests while every
    # newline-separated merge walked through the gate. Here the `--squash` the policy requires is
    # missing, so silence (exit 0) means the gate never saw the merge.
    main = tmp_path / "main"
    _init_repo(main)
    _rg(["checkout", "-b", "feature/x"], main)
    cfg = main / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-config.yaml").write_text("branches:\n  integration: dev\n", encoding="utf-8")
    # A merge runs on a clean tree by definition; commit the config or an unrelated gate blocks
    # first and masks the merge verdict (this branch has been caught by it).
    _rg(["add", "-A"], main)
    _rg(["commit", "-m", "cfg"], main)
    r = _run_runner(main, "git switch dev\ngit pull --ff-only origin dev\ngit merge feature/x")
    assert r.returncode == fgc.BLOCK_EXIT_CODE
    assert "--squash" in (r.stdout + r.stderr)


@requires_bash_git
def test_runner_merge_gate_fires_when_command_also_commits(tmp_path: Path):
    # `git merge X && git commit -m …` (the squash-merge idiom): the merge check must not be
    # skipped merely because the command also commits. Gated as a commit only, this exits 0 —
    # the merge verdict is never asked for, and the commit path early-exits on the clean tree.
    main = tmp_path / "main"
    _init_repo(main)
    cfg = main / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-config.yaml").write_text(
        "branches:\n  staging: stage\n  production: main\n", encoding="utf-8"
    )
    _rg(["add", "-A"], main)
    _rg(["commit", "-m", "cfg"], main)
    r = _run_runner(main, 'git merge origin/stage && git commit -m "x"')  # missing --no-ff
    assert r.returncode == fgc.BLOCK_EXIT_CODE
    assert "--no-ff" in (r.stdout + r.stderr)


@requires_bash_git
def test_runner_merge_and_commit_both_reach_the_commit_gate(tmp_path: Path):
    # The other half of the same fix: a merge that does NOT violate the policy must fall THROUGH
    # to the commit gate, not exit 0 out of the merge branch. Here no rule matches the merge
    # (no branches configured → fail-open), so the commit path must still run the module
    # pre-check — `echo LINT_RAN` proves it was reached.
    main = tmp_path / "main"
    _init_repo(main)
    _rg(["checkout", "-b", "feature/x"], main)
    _classify_worktree_module(main)  # tier marker + evidence + one module, staged file
    r = _run_runner(main, 'git merge feature/y && git commit -m "x"')
    assert "echo LINT_RAN" in (r.stdout + r.stderr)


def _merge_repo(tmp_path: Path, *, branch: str | None, config: str) -> Path:
    """A clean repo carrying `config` as flow-config.yaml, optionally on a fresh `branch`.

    A merge runs on a clean tree by definition, so flow-config must be COMMITTED (it is
    git-tracked per /flow-init) — leaving it untracked makes the tree dirty and an unrelated
    gate blocks first, masking the merge verdict.
    """
    root = tmp_path / "main"
    _init_repo(root)
    if branch:
        _rg(["checkout", "-b", branch], root)
    cfg = root / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-config.yaml").write_text(config, encoding="utf-8")
    _rg(["add", "-A"], root)
    _rg(["commit", "-m", "cfg"], root)
    return root


@requires_bash_git
def test_runner_merge_gate_ignores_a_checkout_pathspec(tmp_path: Path):
    # `git checkout <branch> -- <path>` restores a FILE; HEAD never moves. Reading `dev` out of
    # it as the merge target invents a `feature/* → integration` flow that is not happening and
    # blocks a legitimate command (exit 2 demanding --squash). The operand form must be judged
    # unclear so the hook-time branch (feature/x) stands, where no rule matches → exit 0.
    main = _merge_repo(tmp_path, branch="feature/x", config="branches:\n  integration: dev\n")
    r = _run_runner(main, "git checkout dev -- README.md && git merge feature/x")
    assert r.returncode == 0
    assert "--squash" not in (r.stdout + r.stderr)


@requires_bash_git
def test_runner_merge_gate_bails_when_a_later_switch_is_unclear(tmp_path: Path):
    # `git switch dev && git switch -c feature/y && git merge feature/x` ends with HEAD on
    # feature/y, which no rule covers. Taking the last *matching* switch adopts the stale `dev`
    # and blocks a merge the policy never governs — one unclear switch must void the whole chain.
    main = _merge_repo(tmp_path, branch="feature/x", config="branches:\n  integration: dev\n")
    r = _run_runner(main, "git switch dev && git switch -c feature/y && git merge feature/x")
    assert r.returncode == 0
    assert "--squash" not in (r.stdout + r.stderr)


@requires_bash_git
def test_runner_merge_gate_fails_open_on_a_cd_into_another_worktree(tmp_path: Path):
    # `cd <worktree> && git merge X` is the other half of `git -C <worktree> merge X`: the source
    # comes from the command but the target would be read from THIS root, naming a flow that is
    # not happening. Closing only the `-C` form left this one blocking (exit 2 demanding
    # --squash) — the merge path may not re-designate the worktree (Invariant #6), so it must
    # fail open.
    main = _merge_repo(tmp_path, branch="dev", config="branches:\n  integration: dev\n")
    wt = tmp_path / "wt"
    _rg(["worktree", "add", "-b", "stage", str(wt)], main)
    r = _run_runner(main, f"cd {wt} && git merge feature/x")
    assert r.returncode == 0
    assert "--squash" not in (r.stdout + r.stderr)


@requires_bash_git
def test_runner_merge_gate_survives_an_unrelated_dash_c(tmp_path: Path):
    # `-C` names a directory only as git's OWN global option. Matched anywhere in the command,
    # any unrelated `-C` (grep context lines, gcc, …) resolves to a foreign directory and switches
    # the entire merge gate off — a one-token bypass of the whole policy.
    main = _merge_repo(
        tmp_path, branch=None, config="branches:\n  staging: stage\n  production: main\n"
    )
    r = _run_runner(main, "grep -C 3 foo README.md && git merge origin/stage")  # missing --no-ff
    assert r.returncode == fgc.BLOCK_EXIT_CODE
    assert "--no-ff" in (r.stdout + r.stderr)


@requires_bash_git
def test_runner_ignores_non_commit_non_merge_command(tmp_path: Path):
    # `git status` is neither a commit nor a merge — must pass through untouched (exit 0, no
    # gate output), proving the two-flag self-filter (Step 1) did not broaden what fires.
    main = tmp_path / "main"
    _init_repo(main)
    r = _run_runner(main, "git status")
    assert r.returncode == 0
    assert r.stdout.strip() == ""
    assert r.stderr.strip() == ""


def test_staging_requires_bump_marker(tmp_path: Path):
    flow = tmp_path / ".flow"
    flow.mkdir()
    (flow / "review.done").touch()  # security-scan is runtime; review present
    gates = ["precommit", "review", "security-scan", "bump"]
    assert missing_gates(flow, gates) == ["bump"]  # bump blocks until its marker exists
    (flow / "bump.done").touch()
    assert missing_gates(flow, gates) == []


def test_shipped_policy_staging_has_bump():
    # the shipped policy is the SSOT the gate reads; staging must carry bump.

    root = Path(__file__).resolve().parent.parent.parent
    data = yaml.safe_load((root / "flow-tiers.yaml").read_text(encoding="utf-8"))
    assert "bump" in data["tiers"]["staging"]["gates"]
    assert "bump" not in data["tiers"]["release"]["gates"]  # asked at staging only


def test_shipped_policy_integration_to_staging_requires_no_ff():
    # the shipped policy is the SSOT the gate reads. integration → staging must be a merge
    # commit: the rc self-heal (main → dev back-merge only) relies on the release commits
    # reaching staging through a descendant merge. A rebase promotion replays them under new
    # SHAs, so the stable tag leaves staging's ancestry and semantic-release miscomputes.

    root = Path(__file__).resolve().parent.parent.parent
    data = yaml.safe_load((root / "flow-tiers.yaml").read_text(encoding="utf-8"))
    rows = [
        r
        for r in data["merge_strategy"]
        if r.get("source") == "integration" and r.get("target") == "staging"
    ]
    assert len(rows) == 1, "exactly one integration → staging rule"
    assert rows[0]["require"] == "--no-ff"
