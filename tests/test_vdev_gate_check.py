import os
import subprocess
import sys
from pathlib import Path

import pytest

import scripts.vdev_gate_check as fgc
from scripts.vdev_gate_check import (
    load_lifecycle_branches,
    missing_gates,
    required_gates,
    tiers_path,
)


def test_lifecycle_branches_from_config(tmp_path: Path):
    cfg = tmp_path / "vdev-config.yaml"
    cfg.write_text("branches:\n  staging: stage\n  production: main\n", encoding="utf-8")
    assert load_lifecycle_branches(cfg) == {"stage": "staging", "main": "release"}


def test_lifecycle_branches_custom_names(tmp_path: Path):
    cfg = tmp_path / "vdev-config.yaml"
    cfg.write_text("branches:\n  staging: qa\n  production: release\n", encoding="utf-8")
    assert load_lifecycle_branches(cfg) == {"qa": "staging", "release": "release"}


def test_lifecycle_branches_missing_file(tmp_path: Path):
    assert load_lifecycle_branches(tmp_path / "absent.yaml") == {}


def test_required_gates_dev(tmp_path: Path):
    tiers = tmp_path / "vdev-tiers.yaml"
    tiers.write_text(
        "tiers:\n  dev:\n    gates: [review, doc-sync]\n",
        encoding="utf-8",
    )
    assert required_gates(tiers, "dev") == ["review", "doc-sync"]


def test_required_gates_unknown_tier(tmp_path: Path):
    tiers = tmp_path / "vdev-tiers.yaml"
    tiers.write_text("tiers:\n  docs:\n    gates: [doc-sync]\n", encoding="utf-8")
    assert required_gates(tiers, "nope") is None


def test_security_scan_is_runtime_gate_no_marker(tmp_path: Path):
    # security-scan 은 RUNTIME_GATES 에 속하므로 .done 마커 없이도 미충족에 들어가지 않는다.
    from scripts._vway_paths import RUNTIME_GATES

    assert "security-scan" in RUNTIME_GATES
    # release gates 중 security-scan 은 .done 검사 대상이 아니다
    vdev = tmp_path / ".vdev"
    vdev.mkdir()
    # review.done 은 없고 security-scan.done 도 없지만 security-scan 은 런타임 → 제외
    result = missing_gates(vdev, ["review", "security-scan", "security"])
    assert "security-scan" not in result
    assert "review" in result
    assert "security" in result


def test_precommit_is_runtime_gate_no_marker(tmp_path: Path):
    # precommit 도 RUNTIME_GATES 에 속하므로 .done 마커 없이도 미충족에 들어가지 않는다.
    from scripts._vway_paths import RUNTIME_GATES

    assert "precommit" in RUNTIME_GATES
    vdev = tmp_path / ".vdev"
    vdev.mkdir()
    result = missing_gates(vdev, ["precommit", "review", "doc-sync"])
    assert "precommit" not in result
    assert "review" in result
    assert "doc-sync" in result


def test_missing_gates_skips_runtime_gates(tmp_path: Path):
    # 모든 RUNTIME_GATES 멤버는 .done 마커 없이도 missing_gates 에서 제외된다.
    vdev = tmp_path / ".vdev"
    vdev.mkdir()
    (vdev / "doc-sync.done").touch()
    # security-scan 은 런타임 게이트 → 제외됨
    assert missing_gates(vdev, ["security-scan", "review", "doc-sync"]) == ["review"]


def test_tiers_path_prefers_plugin_root(tmp_path: Path, monkeypatch):
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    (plugin / "vdev-tiers.yaml").write_text("tiers: {}\n", encoding="utf-8")
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(plugin))
    assert tiers_path(tmp_path / "host") == plugin / "vdev-tiers.yaml"


def test_tiers_path_falls_back_to_host_root(tmp_path: Path, monkeypatch):
    # 플러그인 루트 미설정 + config/ 복사본 부재 → 호스트 루트로 폴백
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    host = tmp_path / "host"
    host.mkdir()
    assert tiers_path(host) == host / "vdev-tiers.yaml"


def _run_main(root: Path) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(root), "PYTHONIOENCODING": "utf-8"}
    return subprocess.run(
        [sys.executable, "scripts/vdev_gate_check.py"],
        cwd=Path(__file__).resolve().parent.parent,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def test_main_allows_when_no_vdev(tmp_path: Path):
    # 정책 파일(vdev-tiers.yaml)조차 없는 환경 = 설치/환경 불확정 → fail-OPEN.
    (tmp_path / ".claude").mkdir()
    assert _run_main(tmp_path).returncode == 0


def test_main_blocks_unclassified_with_policy(tmp_path: Path):
    # 정책 파일은 정상인데 tier 마커가 전혀 없음 = vdev 미진입(미분류) → fail-CLOSED 차단.
    (tmp_path / "vdev-tiers.yaml").write_text(
        "tiers:\n  dev:\n    gates: [review, doc-sync]\n", encoding="utf-8"
    )
    (tmp_path / ".claude").mkdir()
    assert _run_main(tmp_path).returncode == 2


def test_main_allows_when_policy_unparseable(tmp_path: Path):
    # vdev-tiers.yaml 이 존재하나 파싱 깨짐(내부 오류) + 미분류 → FAIL-OPEN(차단 안 함).
    # Invariant #1: 깨진 정책 파일은 "정상 작동"이 아니므로 fail-closed 대상이 아니다.
    (tmp_path / "vdev-tiers.yaml").write_text("tiers: [unclosed\n", encoding="utf-8")
    (tmp_path / ".claude").mkdir()
    assert _run_main(tmp_path).returncode == 0


def test_main_allows_when_config_corrupt(tmp_path: Path):
    # 정책 정상 + 미분류 + vdev-config.yaml 존재하나 파싱 깨짐(내부 오류) → FAIL-OPEN.
    # config 파싱 실패는 lifecycle(staging/release) 판정을 무력화하므로, promotion 커밋이
    # "미분류"로 오차단되지 않게 차단을 보류한다(Invariant #1).
    (tmp_path / "vdev-tiers.yaml").write_text(
        "tiers:\n  dev:\n    gates: [review]\n", encoding="utf-8"
    )
    cfg_dir = tmp_path / ".claude" / "vway-kit" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "vdev-config.yaml").write_text("branches: [unclosed\n", encoding="utf-8")
    assert _run_main(tmp_path).returncode == 0


def test_main_allows_stale_marker_other_branch(tmp_path: Path, monkeypatch):
    # tier 마커는 존재하나 다른 브랜치 것(branch-bound stale) → 현재 작업 막지 않음(fail-OPEN).
    # 다른 브랜치 판정엔 실제 브랜치명이 필요하므로 _current_branch 를 패치해 in-process 호출.
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    monkeypatch.setattr(fgc, "_current_branch", lambda _root: "branch-b")
    (tmp_path / "vdev-tiers.yaml").write_text(
        "tiers:\n  dev:\n    gates: [review, doc-sync]\n", encoding="utf-8"
    )
    vdev = tmp_path / ".claude" / "vway-kit" / ".vdev"
    vdev.mkdir(parents=True)
    (vdev / "tier").write_text("dev:branch-a", encoding="utf-8")
    with pytest.raises(SystemExit) as exc:
        fgc.main()
    assert exc.value.code == 0


def test_main_blocks_missing_dev_gate(tmp_path: Path):
    (tmp_path / "vdev-tiers.yaml").write_text(
        "tiers:\n  dev:\n    gates: [review, doc-sync]\n", encoding="utf-8"
    )
    vdev = tmp_path / ".claude" / "vway-kit" / ".vdev"
    vdev.mkdir(parents=True)
    (vdev / "tier").write_text("dev:", encoding="utf-8")
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
    cfg = tmp_path / ".claude" / "vway-kit" / "config"
    cfg.mkdir(parents=True)
    (cfg / "vdev-config.yaml").write_text(_MODCFG, encoding="utf-8")


def test_module_commands_dev_runs_changed_non_security(tmp_path: Path, monkeypatch):
    _write_modcfg(tmp_path)
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/x.py"])
    cmds, report = fgc.module_commands(tmp_path, "dev", ["precommit", "review", "doc-sync"])
    # api 변경 → api 의 non-security(lint, test). web 미변경 → 제외. security 제외.
    assert cmds == ["ruff check services/api", "pytest services/api"]
    assert report == []


def test_module_commands_dev_gate_removed_skips_non_security(tmp_path: Path, monkeypatch):
    # precommit 이 gates 에서 빠지면 변경 모듈이 있어도 사전검사를 실행하지 않는다
    # (gates 리스트가 실제 스위치 — tier 라벨만으로는 실행되지 않는다).
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
    # 변경 모듈 non-security + 전체 모듈 security(api 만 security 있음 → bandit).
    assert cmds == ["ruff check services/api", "pytest services/api", "bandit -r services/api"]


def test_module_commands_release_gate_removed_skips_security(tmp_path: Path, monkeypatch):
    # security-scan 이 gates 에서 빠지면 release 여도 전체 모듈 security 는 실행하지 않는다.
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
    assert "ruff check services/api" in cmds  # 커버된 모듈은 실행
    assert any("scripts/build.py" in line for line in report)  # 미커버는 리포트로만


def test_module_commands_failopen_no_config(tmp_path: Path):
    assert fgc.module_commands(tmp_path, "dev", ["precommit"]) == ([], [])


def test_match_modules_prefix_and_empty_path():
    mods = [{"name": "api", "path": "services/api/"}, {"name": "app", "path": ""}]
    # 빈 path 는 전체 매칭(단일스택 단일모듈). 명시 path 가 먼저 매칭되면 그쪽.
    matched, uncovered = fgc._match_modules(["services/api/a.py", "README.md"], mods)
    assert {m["name"] for m in matched} == {"api", "app"}
    assert uncovered == []


def test_module_commands_output_splits_streams(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    _write_modcfg(tmp_path)
    (tmp_path / "vdev-tiers.yaml").write_text(
        "tiers:\n  dev:\n    gates: [precommit, review]\n", encoding="utf-8"
    )
    vdev = tmp_path / ".claude" / "vway-kit" / ".vdev"
    vdev.mkdir(parents=True)
    (vdev / "tier").write_text("dev:feature/x", encoding="utf-8")
    monkeypatch.setattr(fgc, "_current_branch", lambda _r: "feature/x")
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["scripts/x.py", "services/api/y.py"])
    fgc.module_commands_output()
    out = capsys.readouterr()
    assert "ruff check services/api" in out.out  # 명령 → stdout
    assert "scripts/x.py" in out.err  # 미커버 → stderr


def test_module_commands_output_empty_when_precommit_gate_removed(
    tmp_path: Path, monkeypatch, capsys
):
    # tiers.yaml dev gates 에 precommit 이 없으면 변경 모듈이 있어도 명령이 나오지 않는다.
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    _write_modcfg(tmp_path)
    (tmp_path / "vdev-tiers.yaml").write_text(
        "tiers:\n  dev:\n    gates: [review]\n", encoding="utf-8"
    )
    vdev = tmp_path / ".claude" / "vway-kit" / ".vdev"
    vdev.mkdir(parents=True)
    (vdev / "tier").write_text("dev:feature/x", encoding="utf-8")
    monkeypatch.setattr(fgc, "_current_branch", lambda _r: "feature/x")
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/y.py"])
    fgc.module_commands_output()
    out = capsys.readouterr()
    assert out.out == ""
    assert out.err == ""
