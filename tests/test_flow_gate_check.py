import os
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
