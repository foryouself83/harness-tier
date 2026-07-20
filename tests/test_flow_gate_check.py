import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.flow_gate_check as fgc
from scripts.flow_gate_check import (
    _branch_matches,
    _target_from_command,
    load_lifecycle_branches,
    load_merge_strategy,
    match_merge_rule,
    missing_gates,
    parse_merge_command,
    required_gates,
    tiers_path,
)


def test_lifecycle_branches_from_config(tmp_path: Path):
    cfg = tmp_path / "flow-config.yaml"
    cfg.write_text("branches:\n  staging: stage\n  production: main\n", encoding="utf-8")
    assert load_lifecycle_branches(cfg) == {"stage": "staging", "main": "release"}


def test_lifecycle_branches_custom_names(tmp_path: Path):
    cfg = tmp_path / "flow-config.yaml"
    cfg.write_text("branches:\n  staging: qa\n  production: release\n", encoding="utf-8")
    assert load_lifecycle_branches(cfg) == {"qa": "staging", "release": "release"}


def test_lifecycle_branches_missing_file(tmp_path: Path):
    assert load_lifecycle_branches(tmp_path / "absent.yaml") == {}


def test_required_gates_dev(tmp_path: Path):
    tiers = tmp_path / "flow-tiers.yaml"
    tiers.write_text(
        "tiers:\n  dev:\n    gates: [review, doc-sync]\n",
        encoding="utf-8",
    )
    assert required_gates(tiers, "dev") == ["review", "doc-sync"]


def test_required_gates_unknown_tier(tmp_path: Path):
    tiers = tmp_path / "flow-tiers.yaml"
    tiers.write_text("tiers:\n  docs:\n    gates: [doc-sync]\n", encoding="utf-8")
    assert required_gates(tiers, "nope") is None


def test_security_scan_is_runtime_gate_no_marker(tmp_path: Path):
    # security-scan belongs to RUNTIME_GATES, so it is not counted as missing
    # even without a .done marker.
    from scripts._harness_paths import RUNTIME_GATES

    assert "security-scan" in RUNTIME_GATES
    # among release gates, security-scan is not subject to the .done check
    flow = tmp_path / ".flow"
    flow.mkdir()
    # neither review.done nor security-scan.done exists, but security-scan is runtime → excluded
    result = missing_gates(flow, ["review", "security-scan", "security"])
    assert "security-scan" not in result
    assert "review" in result
    assert "security" in result


def test_precommit_is_runtime_gate_no_marker(tmp_path: Path):
    # precommit also belongs to RUNTIME_GATES, so it is not counted as missing
    # even without a .done marker.
    from scripts._harness_paths import RUNTIME_GATES

    assert "precommit" in RUNTIME_GATES
    flow = tmp_path / ".flow"
    flow.mkdir()
    result = missing_gates(flow, ["precommit", "review", "doc-sync"])
    assert "precommit" not in result
    assert "review" in result
    assert "doc-sync" in result


def test_missing_gates_skips_runtime_gates(tmp_path: Path):
    # every RUNTIME_GATES member is excluded from missing_gates even without a .done marker.
    flow = tmp_path / ".flow"
    flow.mkdir()
    (flow / "doc-sync.done").touch()
    # security-scan is a runtime gate → excluded
    assert missing_gates(flow, ["security-scan", "review", "doc-sync"]) == ["review"]


def test_tiers_path_prefers_plugin_root(tmp_path: Path, monkeypatch):
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "flow-tiers.yaml").write_text("tiers: {}\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin))
    assert tiers_path(tmp_path / "host") == plugin / "flow-tiers.yaml"


def test_tiers_path_falls_back_to_host_root(tmp_path: Path, monkeypatch):
    # plugin root unset + no config/ copy → fall back to the host root
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    host = tmp_path / "host"
    host.mkdir()
    assert tiers_path(host) == host / "flow-tiers.yaml"


def _run_main(root: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root), "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, "scripts/flow_gate_check.py"],
        cwd=Path(__file__).resolve().parent.parent,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_main_allows_when_no_flow(tmp_path: Path):
    # an environment without even the policy file (flow-tiers.yaml) = install/environment
    # indeterminate → fail-OPEN.
    (tmp_path / ".claude").mkdir()
    assert _run_main(tmp_path).returncode == 0


def test_main_blocks_unclassified_with_policy(tmp_path: Path):
    # policy file is fine but there is no tier marker at all = flow not entered
    # (unclassified) → fail-CLOSED block.
    (tmp_path / "flow-tiers.yaml").write_text(
        "tiers:\n  dev:\n    gates: [review, doc-sync]\n", encoding="utf-8"
    )
    (tmp_path / ".claude").mkdir()
    assert _run_main(tmp_path).returncode == 2


def test_main_allows_when_policy_unparseable(tmp_path: Path):
    # flow-tiers.yaml exists but fails to parse (internal error) + unclassified
    # → FAIL-OPEN (no block). Invariant #1: a broken policy file is not "working
    # normally", so it is not a fail-closed target.
    (tmp_path / "flow-tiers.yaml").write_text("tiers: [unclosed\n", encoding="utf-8")
    (tmp_path / ".claude").mkdir()
    assert _run_main(tmp_path).returncode == 0


def test_main_allows_when_config_corrupt(tmp_path: Path):
    # policy fine + unclassified + flow-config.yaml exists but fails to parse (internal
    # error) → FAIL-OPEN. a config parse failure disables the lifecycle (staging/release)
    # decision, so hold the block to avoid mis-blocking a promotion commit as
    # "unclassified" (Invariant #1).
    (tmp_path / "flow-tiers.yaml").write_text(
        "tiers:\n  dev:\n    gates: [review]\n", encoding="utf-8"
    )
    cfg_dir = tmp_path / ".claude" / "harness-tier" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "flow-config.yaml").write_text("branches: [unclosed\n", encoding="utf-8")
    assert _run_main(tmp_path).returncode == 0


def test_main_allows_stale_marker_other_branch(tmp_path: Path, monkeypatch):
    # the tier marker exists but belongs to another branch (branch-bound stale) → does not
    # block current work (fail-OPEN). judging another branch needs the actual branch name,
    # so patch _current_branch and call in-process.
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.setattr(fgc, "_current_branch", lambda _root: "branch-b")
    (tmp_path / "flow-tiers.yaml").write_text(
        "tiers:\n  dev:\n    gates: [review, doc-sync]\n", encoding="utf-8"
    )
    flow = tmp_path / ".claude" / "harness-tier" / ".flow"
    flow.mkdir(parents=True)
    (flow / "tier").write_text("dev:branch-a", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        fgc.main()
    assert exc.value.code == 0


def test_main_blocks_missing_dev_gate(tmp_path: Path):
    (tmp_path / "flow-tiers.yaml").write_text(
        "tiers:\n  dev:\n    gates: [review, doc-sync]\n", encoding="utf-8"
    )
    flow = tmp_path / ".claude" / "harness-tier" / ".flow"
    flow.mkdir(parents=True)
    (flow / "tier").write_text("dev:", encoding="utf-8")
    result = _run_main(tmp_path)
    assert result.returncode == 2
    assert "review" in result.stdout


_MODCFG = (
    "branches:\n  production: main\n"
    "modules:\n"
    "  - name: api\n    path: services/api/\n"
    "    checks:\n"
    "      lint: 'ruff check services/api'\n"
    "      test: 'pytest services/api'\n"
    "      security: 'bandit -r services/api'\n"
    "  - name: web\n    path: services/web/\n"
    "    checks:\n      lint: 'eslint web'\n"
)


def _write_modcfg(tmp_path: Path) -> None:
    cfg = tmp_path / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-config.yaml").write_text(_MODCFG, encoding="utf-8")


def test_module_commands_dev_runs_changed_non_security(tmp_path: Path, monkeypatch):
    _write_modcfg(tmp_path)
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/x.py"])
    cmds, report = fgc.module_commands(tmp_path, "dev", ["precommit", "review", "doc-sync"])
    # api changed → api's non-security (lint, test). web unchanged → excluded. security excluded.
    assert cmds == ["ruff check services/api", "pytest services/api"]
    assert report == []


def test_module_commands_dev_gate_removed_skips_non_security(tmp_path: Path, monkeypatch):
    # if precommit is dropped from gates, pre-checks are not run even when there are changed modules
    # (the gates list is the real switch — the tier label alone does not run them).
    _write_modcfg(tmp_path)
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/x.py"])
    cmds, report = fgc.module_commands(tmp_path, "dev", ["review", "doc-sync"])
    assert cmds == []
    assert report == []


def test_module_commands_release_adds_full_security(tmp_path: Path, monkeypatch):
    _write_modcfg(tmp_path)
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/x.py"])
    cmds, _ = fgc.module_commands(
        tmp_path, "release", ["precommit", "review", "security-scan", "security"]
    )
    # changed-module non-security + all-module security (only api has security → bandit).
    assert cmds == ["ruff check services/api", "pytest services/api", "bandit -r services/api"]


def test_module_commands_release_gate_removed_skips_security(tmp_path: Path, monkeypatch):
    # if security-scan is dropped from gates, all-module security is not run even on release.
    _write_modcfg(tmp_path)
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/x.py"])
    cmds, _ = fgc.module_commands(tmp_path, "release", ["precommit", "review", "security"])
    assert cmds == ["ruff check services/api", "pytest services/api"]
    assert "bandit -r services/api" not in cmds


def test_module_commands_docs_empty(tmp_path: Path):
    assert fgc.module_commands(tmp_path, "docs", ["doc-sync"]) == ([], [])
    assert fgc.module_commands(tmp_path, None, None) == ([], [])


def test_module_commands_uncovered_reported_not_blocked(tmp_path: Path, monkeypatch):
    _write_modcfg(tmp_path)
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["scripts/build.py", "services/api/y.py"])
    cmds, report = fgc.module_commands(tmp_path, "dev", ["precommit", "review", "doc-sync"])
    assert "ruff check services/api" in cmds  # covered modules run
    assert any("scripts/build.py" in line for line in report)  # uncovered only via report


def test_module_commands_failopen_no_config(tmp_path: Path):
    assert fgc.module_commands(tmp_path, "dev", ["precommit"]) == ([], [])


def test_match_modules_prefix_and_empty_path():
    mods = [{"name": "api", "path": "services/api/"}, {"name": "app", "path": ""}]
    # an empty path matches everything (single-stack single-module). An explicit path
    # matches first if it matches.
    matched, uncovered = fgc._match_modules(["services/api/a.py", "README.md"], mods)
    assert {m["name"] for m in matched} == {"api", "app"}
    assert uncovered == []


def test_module_commands_output_splits_streams(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    _write_modcfg(tmp_path)
    (tmp_path / "flow-tiers.yaml").write_text(
        "tiers:\n  dev:\n    gates: [precommit, review]\n", encoding="utf-8"
    )
    flow = tmp_path / ".claude" / "harness-tier" / ".flow"
    flow.mkdir(parents=True)
    (flow / "tier").write_text("dev:feature/x", encoding="utf-8")
    monkeypatch.setattr(fgc, "_current_branch", lambda _r: "feature/x")
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["scripts/x.py", "services/api/y.py"])
    fgc.module_commands_output()
    out = capsys.readouterr()
    assert "ruff check services/api" in out.out  # commands → stdout
    assert "scripts/x.py" in out.err  # uncovered → stderr


def test_module_commands_output_empty_when_precommit_gate_removed(
    tmp_path: Path, monkeypatch, capsys
):
    # if precommit is absent from tiers.yaml dev gates, no commands are emitted even with
    # changed modules.
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    _write_modcfg(tmp_path)
    (tmp_path / "flow-tiers.yaml").write_text(
        "tiers:\n  dev:\n    gates: [review]\n", encoding="utf-8"
    )
    flow = tmp_path / ".claude" / "harness-tier" / ".flow"
    flow.mkdir(parents=True)
    (flow / "tier").write_text("dev:feature/x", encoding="utf-8")
    monkeypatch.setattr(fgc, "_current_branch", lambda _r: "feature/x")
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/y.py"])
    fgc.module_commands_output()
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err == ""


def test_bump_is_not_runtime_gate():
    from scripts._harness_paths import RUNTIME_GATES

    assert "bump" not in RUNTIME_GATES  # bump needs a .done marker (evidence gate)


# ── worktree-aware re-designation (--resolve-worktree) ────────────────────────────
# The gate assumes working tree = CLAUDE_PROJECT_DIR (fixed at session start). When a commit
# runs in a git worktree, precommit-runner.sh asks flow_gate_check.py --resolve-worktree for the
# actual worktree W (branch-key) and re-points ROOT=W. These pin that mechanism end-to-end.


def _git_ok() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


requires_git = pytest.mark.skipif(not _git_ok(), reason="git not available")


def _rg(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _rg(["init", "-b", "main"], path)
    _rg(["config", "user.email", "t@e.st"], path)
    _rg(["config", "user.name", "Test"], path)
    (path / "README.md").write_text("x", encoding="utf-8")
    _rg(["add", "-A"], path)
    _rg(["commit", "-m", "init"], path)


def _resolve_worktree(root: Path, payload: dict) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root), "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, "scripts/flow_gate_check.py", "--resolve-worktree"],
        cwd=Path(__file__).resolve().parent.parent,
        env=env,
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@requires_git
def test_resolve_worktree_detects_git_dash_c(tmp_path: Path):
    # `git -C <wt> commit` (the /flow worktree commit convention) → prints W's absolute path.
    main = tmp_path / "repo"
    _init_repo(main)
    wt = tmp_path / "repo-wt"
    _rg(["worktree", "add", "-b", "feature/x", str(wt)], main)
    payload = {"cwd": str(main), "tool_input": {"command": f'git -C {wt} commit -m "m"'}}
    r = _resolve_worktree(main, payload)
    assert r.returncode == 0
    assert r.stdout.strip() == str(wt.resolve())


@requires_git
def test_resolve_worktree_single_tree_empty(tmp_path: Path):
    # non-worktree (single tree): W == main → empty output → runner keeps ROOT=main (no change).
    main = tmp_path / "repo"
    _init_repo(main)
    payload = {"cwd": str(main), "tool_input": {"command": "git commit -m m"}}
    r = _resolve_worktree(main, payload)
    assert r.returncode == 0
    assert r.stdout.strip() == ""


@requires_git
def test_changed_files_isolated_per_worktree(tmp_path: Path):
    # the motivating defect: a worktree's staged change is invisible to main. Once ROOT=W, the
    # gate reads the worktree's staged files (and main's do not leak in).
    main = tmp_path / "repo"
    _init_repo(main)
    wt = tmp_path / "repo-wt"
    _rg(["worktree", "add", "-b", "feature/x", str(wt)], main)
    (wt / "new.py").write_text("x = 1\n", encoding="utf-8")
    _rg(["add", "new.py"], wt)  # stage inside the worktree
    assert "new.py" in fgc._changed_files(wt)  # W sees its own staged change
    assert "new.py" not in fgc._changed_files(main)  # main does not


def _repo_bash() -> str | None:
    """A bash that can actually see the repo path (Git Bash on Windows / native bash on POSIX).

    Windows PATH often resolves ``bash`` to WSL, which cannot access ``C:/…`` paths, so probe the
    candidate and fall back to known Git Bash locations. None → no usable bash (skip)."""
    repo = Path(__file__).resolve().parent.parent
    probe = f"{repo.as_posix()}/scripts/precommit-runner.sh"
    which = shutil.which("bash")
    candidates = [
        which,
        r"C:\Program Files\Git\bin\bash.exe",
        r"C:\Program Files\Git\usr\bin\bash.exe",
    ]
    for bash in candidates:
        if not bash or not (bash == which or Path(bash).exists()):
            continue
        try:
            r = subprocess.run([bash, "-c", f'test -f "{probe}"'], capture_output=True, timeout=10)
            if r.returncode == 0:
                return bash
        except Exception:
            continue
    return None


_REPO_BASH = _repo_bash()
requires_bash_git = pytest.mark.skipif(
    not (_REPO_BASH and _git_ok()), reason="a repo-visible bash + git required"
)


def _classify_worktree_module(wt: Path) -> None:
    """Give a worktree a dev tier marker + evidence and one module covering a staged file."""
    flow = wt / ".claude" / "harness-tier" / ".flow"
    flow.mkdir(parents=True)
    (flow / "tier").write_text("dev:feature/x", encoding="utf-8")
    (flow / "review.done").touch()
    (flow / "doc-sync.done").touch()
    cfg = wt / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-config.yaml").write_text(
        "modules:\n  - name: api\n    path: services/api/\n"
        '    checks:\n      lint: "echo LINT_RAN"\n',
        encoding="utf-8",
    )
    (wt / "services" / "api").mkdir(parents=True)
    (wt / "services" / "api" / "a.py").write_text("x = 1\n", encoding="utf-8")
    _rg(["add", "services/api/a.py"], wt)


def _run_runner(main: Path, command: str) -> subprocess.CompletedProcess[str]:
    repo = Path(__file__).resolve().parent.parent
    env = {
        **os.environ,
        "CLAUDE_PROJECT_DIR": str(main),
        "CLAUDE_PLUGIN_ROOT": repo.as_posix(),
        "HARNESS_PRECOMMIT_DRYRUN": "1",
        "PYTHONIOENCODING": "utf-8",
    }
    hook = json.dumps({"cwd": str(main), "tool_input": {"command": command}})
    # bash eats backslashes in an argv path (C:\a\b → C:ab), so pass a forward-slash path.
    return subprocess.run(
        [_REPO_BASH, f"{repo.as_posix()}/scripts/precommit-runner.sh"],
        input=hook,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


@requires_bash_git
def test_runner_gates_worktree_commit_via_git_dash_c(tmp_path: Path):
    # end-to-end: `git -C <wt> commit` must (1) pass the commit self-filter despite the `-C <dir>`
    # between `git` and `commit`, then (2) re-point ROOT=W so the module pre-check reads the
    # worktree's staged files. If either breaks, W's `echo LINT_RAN` would not appear (DRYRUN).
    main = tmp_path / "main"
    _init_repo(main)
    wt = tmp_path / "wt"
    _rg(["worktree", "add", "-b", "feature/x", str(wt)], main)
    _classify_worktree_module(wt)
    r = _run_runner(main, f"git -C {wt} commit -m x")
    assert "echo LINT_RAN" in (r.stdout + r.stderr)  # gate ran against W


@requires_bash_git
def test_runner_ignores_commit_graph_subcommand(tmp_path: Path):
    # `git -C <wt> commit-graph write` is NOT a commit — the whole-word match must not fire,
    # else a non-commit git command would be gated (false block risk).
    main = tmp_path / "main"
    _init_repo(main)
    wt = tmp_path / "wt"
    _rg(["worktree", "add", "-b", "feature/x", str(wt)], main)
    _classify_worktree_module(wt)
    r = _run_runner(main, f"git -C {wt} commit-graph write")
    assert "echo LINT_RAN" not in (r.stdout + r.stderr)
    assert r.returncode == 0


# ── merge gate (git merge branches before the `git status` early-exit) ────────────
# Relies on this repo's own shipped flow-tiers.yaml merge_strategy (staging → production
# requires --no-ff — see risk-tiers.md Merge strategy), since _run_runner points
# CLAUDE_PLUGIN_ROOT at this repo, and tiers_path() prefers CLAUDE_PLUGIN_ROOT/flow-tiers.yaml
# over any host config copy (dogfooding the real policy end-to-end).


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
    # branch actually runs before the `git status` early-exit.
    _rg(["add", "-A"], main)
    _rg(["commit", "-m", "cfg"], main)
    r = _run_runner(main, "git merge origin/stage")  # missing the required --no-ff
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
    # The same idiom as above, written the way risk-tiers actually prints it: three LINES, no `&&`.
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
    # skipped just because the command also commits. Gated as a commit only, this exits 0 —
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
    # simply fail open.
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
    import yaml

    root = Path(__file__).resolve().parent.parent
    data = yaml.safe_load((root / "flow-tiers.yaml").read_text(encoding="utf-8"))
    assert "bump" in data["tiers"]["staging"]["gates"]
    assert "bump" not in data["tiers"]["release"]["gates"]  # asked at staging only


# ── per-check timing (_parse_check / _default_timing) ─────────────────────────────
def test_parse_check_plain_string_is_every_commit():
    assert fgc._parse_check("lint", "ruff .") == ("ruff .", "every-commit", None)


def test_parse_check_security_string_defaults_promotion():
    # back-compat: the reserved 'security' key stays promotion even as a plain string.
    assert fgc._parse_check("security", "bandit -r .") == ("bandit -r .", "promotion", None)


def test_parse_check_dict_when_promotion():
    assert fgc._parse_check("sbom", {"run": "syft .", "when": "promotion"}) == (
        "syft .",
        "promotion",
        None,
    )


def test_parse_check_dict_when_every_commit():
    assert fgc._parse_check("license", {"run": "make lic", "when": "every-commit"}) == (
        "make lic",
        "every-commit",
        None,
    )


def test_parse_check_dict_without_when_uses_key_default():
    # dict form without `when` → key-name default (security→promotion, else every-commit).
    assert fgc._parse_check("license", {"run": "make lic"}) == ("make lic", "every-commit", None)
    assert fgc._parse_check("security", {"run": "bandit ."}) == ("bandit .", "promotion", None)


def test_parse_check_unknown_when_failsafe_every_commit_with_warning():
    cmd, timing, warn = fgc._parse_check("license", {"run": "make lic", "when": "promo"})
    assert cmd == "make lic"
    assert timing == "every-commit"  # fail-safe: run more often, not less
    assert warn is not None and "license" in warn and "promo" in warn


def test_parse_check_dict_without_run_is_none():
    cmd, _timing, _warn = fgc._parse_check("license", {"when": "promotion"})
    assert cmd is None


def test_parse_check_empty_string_is_none():
    assert fgc._parse_check("lint", "")[0] is None


# ── per-check timing routing in module_commands ──────────────────────────────────
_CUSTOMCFG = (
    "branches:\n  production: main\n"
    "modules:\n"
    "  - name: api\n    path: services/api/\n"
    "    checks:\n"
    "      lint: 'ruff check services/api'\n"
    "      license:\n        run: 'make license'\n        when: every-commit\n"
    "      sbom:\n        run: 'syft services/api'\n        when: promotion\n"
    "      security: 'bandit -r services/api'\n"
)


def _write_customcfg(tmp_path: Path) -> None:
    cfg = tmp_path / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-config.yaml").write_text(_CUSTOMCFG, encoding="utf-8")


def test_custom_every_commit_runs_on_changed_precommit(tmp_path: Path, monkeypatch):
    _write_customcfg(tmp_path)
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/x.py"])
    cmds, report = fgc.module_commands(tmp_path, "dev", ["precommit", "review", "doc-sync"])
    # every-commit: lint + license (custom). promotion (sbom, security) excluded on dev.
    assert cmds == ["ruff check services/api", "make license"]
    assert report == []


def test_custom_promotion_runs_all_modules_on_release(tmp_path: Path, monkeypatch):
    _write_customcfg(tmp_path)
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/x.py"])
    cmds, _ = fgc.module_commands(
        tmp_path, "release", ["precommit", "review", "security-scan", "security"]
    )
    # precommit(changed): lint, license. security-scan(all): sbom + security (both promotion).
    assert cmds == [
        "ruff check services/api",
        "make license",
        "syft services/api",
        "bandit -r services/api",
    ]


def test_multiple_promotion_checks_one_module(tmp_path: Path, monkeypatch):
    # the pre-generalization limit (single `security` slot) is gone: sbom + security both emit.
    _write_customcfg(tmp_path)
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/x.py"])
    cmds, _ = fgc.module_commands(tmp_path, "staging", ["security-scan"])
    assert cmds == ["syft services/api", "bandit -r services/api"]


def test_unknown_when_warned_once_and_command_emitted(tmp_path: Path, monkeypatch):
    cfg = tmp_path / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-config.yaml").write_text(
        "modules:\n  - name: api\n    path: services/api/\n"
        "    checks:\n      lint:\n        run: 'ruff .'\n        when: bogus\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/x.py"])
    # release runs both passes → the module is seen twice, but the warning is de-duped to one line.
    cmds, report = fgc.module_commands(tmp_path, "release", ["precommit", "security-scan"])
    assert cmds == ["ruff ."]  # fail-safe every-commit
    warn_lines = [ln for ln in report if "bogus" in ln]
    assert len(warn_lines) == 1


def test_shipped_example_config_custom_check_routing():
    # the shipped example must stay valid YAML and demonstrate a custom check (with `when`,
    # not the YAML-boolean-trap `on`); guards the example against drift.
    import yaml

    root = Path(__file__).resolve().parent.parent
    data = yaml.safe_load((root / "flow-config.example.yaml").read_text(encoding="utf-8"))
    api = next(m for m in data["modules"] if m["name"] == "api")
    cmd, timing, warn = fgc._parse_check("license", api["checks"]["license"])
    assert warn is None  # `when` is a valid timing (proves it was not parsed as boolean True)
    assert timing in fgc._TIMINGS
    assert cmd  # non-empty command


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

RULES = [
    {
        "source": "feature/*",
        "target": "integration",
        "require": "--squash",
        "warn_unless_rebased": True,
    },
    {"source": "hotfix/*", "target": "production", "require": "--squash"},
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
    # HEAD really ends on feature/y. Scanning for the last *matching* switch skips the unclear
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


# Every merge test above writes its chain with `&&`, and a shell separates commands just as well
# with a newline or a `;`. That blind spot let a `_SHELL_SEP_RE` missing `\n` ship green: the
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
    # not also teach it to *name* a target in the three shapes that previously produced false
    # blocks. Each must stay None under every separator, so the hook-time branch stands.
    assert _target_from_command(sep.join(steps)) is None


def test_points_elsewhere_ignores_a_non_git_dash_c(tmp_path: Path):
    # `-C` means "change directory" only as git's own global option. Unanchored, `grep -C 3`
    # resolves to the directory "3", which is foreign to root → the whole gate fails open.
    assert fgc._points_elsewhere("grep -C 3 foo f.txt && git merge feature/x", tmp_path) is False


def test_points_elsewhere_detects_a_leading_cd(tmp_path: Path):
    # `cd <dir> && git merge X` names the execution directory just as `git -C <dir>` does.
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


def test_match_rule_no_match_returns_none():
    # integration → staging has no rule (policy says "Rebase or Merge")
    assert match_merge_rule(RULES, "dev", "stage", BRANCHES) is None


def test_match_rule_empty_rules_returns_none():
    assert match_merge_rule([], "feature/x", "dev", BRANCHES) is None


def _write_policy(tmp_path: Path) -> Path:
    """Host layout: .claude/harness-tier/config/{flow-tiers,flow-config}.yaml"""
    cfg_dir = tmp_path / ".claude" / "harness-tier" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "flow-tiers.yaml").write_text(
        "tiers:\n  dev:\n    gates: [review]\n"
        "merge_strategy:\n"
        '  - source: "feature/*"\n'
        "    target: integration\n"
        '    require: "--squash"\n'
        "    warn_unless_rebased: true\n"
        "  - source: staging\n"
        "    target: production\n"
        '    require: "--no-ff"\n',
        encoding="utf-8",
    )
    (cfg_dir / "flow-config.yaml").write_text(
        "branches:\n  integration: dev\n  staging: stage\n  production: main\n"
        '  feature_prefix: "feature/"\n',
        encoding="utf-8",
    )
    return tmp_path


def _run_merge_check(monkeypatch, tmp_path: Path, command: str, branch: str):
    """Invoke merge_check_output with stdin/branch stubbed; return the SystemExit code."""
    import io

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(fgc, "_current_branch", lambda root: branch)
    monkeypatch.setattr(fgc, "_is_rebased", lambda root, source, target: True)
    monkeypatch.setattr(sys, "stdin", io.StringIO(json.dumps({"tool_input": {"command": command}})))
    with pytest.raises(SystemExit) as exc:
        fgc.merge_check_output()
    return exc.value.code


def test_merge_check_blocks_missing_squash(monkeypatch, tmp_path: Path, capsys):
    _write_policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, "git merge feature/x", "dev")
    assert code == fgc.BLOCK_EXIT_CODE
    assert "--squash" in capsys.readouterr().err


def test_merge_check_allows_squash(monkeypatch, tmp_path: Path):
    _write_policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, "git merge --squash feature/x", "dev")
    assert code == 0


def test_merge_check_blocks_missing_no_ff(monkeypatch, tmp_path: Path):
    _write_policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, "git merge origin/stage", "main")
    assert code == fgc.BLOCK_EXIT_CODE


def test_merge_check_allows_no_ff(monkeypatch, tmp_path: Path):
    _write_policy(tmp_path)
    code = _run_merge_check(
        monkeypatch, tmp_path, 'git merge --no-ff -m "Merge stage: x" origin/stage', "main"
    )
    assert code == 0


def test_merge_check_blocks_switch_then_merge(monkeypatch, tmp_path: Path, capsys):
    # HEAD is still the SOURCE branch (feature/x) — the target must come from the command.
    _write_policy(tmp_path)
    code = _run_merge_check(
        monkeypatch, tmp_path, "git switch dev && git merge feature/x", "feature/x"
    )
    assert code == fgc.BLOCK_EXIT_CODE
    assert "--squash" in capsys.readouterr().err


def test_merge_check_allows_switch_then_squash_merge(monkeypatch, tmp_path: Path):
    _write_policy(tmp_path)
    code = _run_merge_check(
        monkeypatch, tmp_path, "git switch dev && git merge --squash feature/x", "feature/x"
    )
    assert code == 0


def test_merge_check_other_worktree_fails_open(monkeypatch, tmp_path: Path):
    # `git -C <wt> merge feature/x` while the worktree sits on `stage`: the source is read from
    # the command but the target would be read from THIS root (dev), inventing a feature/* → dev
    # violation for a flow (feature/* → stage) that has no rule at all. That is the one place the
    # FAIL-OPEN invariant broke in the BLOCKING direction, so an unrelated -C dir must exit 0.
    _write_policy(tmp_path)
    code = _run_merge_check(
        monkeypatch, tmp_path, f"git -C {tmp_path / 'other-wt'} merge feature/x", "dev"
    )
    assert code == 0


def test_merge_check_dash_c_on_this_root_still_enforced(monkeypatch, tmp_path: Path):
    # …but `-C` pointing at the gated root itself names no other worktree — the branch read here
    # IS the merge target, so enforcement must not be given away wholesale.
    _write_policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, f"git -C {tmp_path} merge feature/x", "dev")
    assert code == fgc.BLOCK_EXIT_CODE


def test_merge_check_no_rule_fails_open(monkeypatch, tmp_path: Path):
    # dev → stage has no rule
    _write_policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, "git merge dev", "stage")
    assert code == 0


def test_merge_check_absent_policy_fails_open(monkeypatch, tmp_path: Path):
    cfg_dir = tmp_path / ".claude" / "harness-tier" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "flow-tiers.yaml").write_text("tiers:\n  dev:\n    gates: []\n", encoding="utf-8")
    code = _run_merge_check(monkeypatch, tmp_path, "git merge feature/x", "dev")
    assert code == 0


def test_merge_check_detached_head_fails_open(monkeypatch, tmp_path: Path):
    _write_policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, "git merge feature/x", None)
    assert code == 0


def test_merge_check_not_a_merge_fails_open(monkeypatch, tmp_path: Path):
    _write_policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, "git merge-base --is-ancestor a b", "dev")
    assert code == 0


def test_merge_check_warns_when_not_rebased(monkeypatch, tmp_path: Path, capsys):
    import io

    _write_policy(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(fgc, "_current_branch", lambda root: "dev")
    monkeypatch.setattr(fgc, "_is_rebased", lambda root, source, target: False)
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps({"tool_input": {"command": "git merge --squash feature/x"}})),
    )
    with pytest.raises(SystemExit) as exc:
        fgc.merge_check_output()
    assert exc.value.code == 0  # warning never blocks
    assert "rebase" in capsys.readouterr().err
