import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.flow_gate_check as fgc
from scripts.flow_gate_check import (
    load_lifecycle_branches,
    missing_gates,
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
