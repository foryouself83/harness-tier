import json
import os
import subprocess
import sys
from pathlib import Path

import yaml as _yaml

from scripts.vdev_init_setup import (
    CLAUDE_MD_BEGIN,
    GATE_COMMAND,
    GATE_MARKER,
    GITIGNORE_LINES,
    GITIGNORE_UNIGNORE,
    append_gitignore,
    check_precommit,
    copy_artifacts,
    load_contract_config,
    main,
    migrate_legacy_paths,
    missing_config_slots,
    register_gate,
    register_marketplace,
    remove_claude_md_block,
    remove_gitignore_lines,
    remove_vway_dir,
    render_workflow,
    report_missing_config_slots,
    run_setup,
    unignore_shared,
    unregister_gate,
    unregister_marketplace,
    untrack_vdev_evidence,
)

PLUGIN = Path(__file__).resolve().parent.parent  # repo root == 플러그인 루트


def _gate_commands(settings: Path) -> list[str]:
    data = json.loads(settings.read_text(encoding="utf-8"))
    return [h["command"] for e in data["hooks"]["PreToolUse"] for h in e["hooks"]]


def test_register_gate_creates(tmp_path: Path):
    msg = register_gate(tmp_path)
    assert "등록" in msg
    cmds = _gate_commands(tmp_path / ".claude" / "settings.json")
    assert any(GATE_MARKER in c for c in cmds)


def test_register_gate_idempotent(tmp_path: Path):
    register_gate(tmp_path)
    msg = register_gate(tmp_path)
    assert "이미" in msg
    # 중복 등록되지 않는다
    cmds = _gate_commands(tmp_path / ".claude" / "settings.json")
    assert sum(GATE_MARKER in c for c in cmds) == 1


def test_register_gate_preserves_existing(tmp_path: Path):
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    other = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo other"}]}
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [other]}}), encoding="utf-8")
    register_gate(tmp_path)
    cmds = _gate_commands(settings)
    assert "echo other" in cmds
    assert any(GATE_MARKER in c for c in cmds)


def test_append_gitignore_creates_and_idempotent(tmp_path: Path):
    first = append_gitignore(tmp_path)
    assert any("+=" in line for line in first)
    content = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    for line in GITIGNORE_LINES:
        assert line in content
    second = append_gitignore(tmp_path)
    assert any("이미 최신" in line for line in second)
    # vdev-config.yaml 은 팀 공유라 무시 목록에서 제외 — 추가되지 않는다.
    assert "vdev-config.yaml" not in content
    assert content.count(".claude/vway-kit/.vdev/") == 1


def test_append_gitignore_preserves_existing(tmp_path: Path):
    gi = tmp_path / ".gitignore"
    gi.write_text("node_modules/\n", encoding="utf-8")
    append_gitignore(tmp_path)
    content = gi.read_text(encoding="utf-8")
    assert "node_modules/" in content
    assert ".claude/vway-kit/.vdev/" in content


def test_unignore_shared_removes_stale_line(tmp_path: Path):
    # 예전 설치: vdev-config.yaml 이 .gitignore 에 있음 → 능동 제거(팀 공유 전환).
    gi = tmp_path / ".gitignore"
    gi.write_text("node_modules/\nvdev-config.yaml\n.claude/vway-kit/.vdev/\n", encoding="utf-8")
    out = unignore_shared(tmp_path)
    assert any("공유 전환" in line for line in out)
    content = gi.read_text(encoding="utf-8")
    assert "vdev-config.yaml" not in content
    assert "node_modules/" in content  # 다른 라인 보존
    assert ".claude/vway-kit/.vdev/" in content


def test_unignore_shared_idempotent_when_absent(tmp_path: Path):
    gi = tmp_path / ".gitignore"
    gi.write_text("node_modules/\n", encoding="utf-8")
    assert unignore_shared(tmp_path) == []  # 제거할 게 없으면 빈 결과
    assert gi.read_text(encoding="utf-8") == "node_modules/\n"  # 무변
    # GITIGNORE_UNIGNORE 가 GITIGNORE_LINES 와 겹치지 않아야(추가하면서 제거하는 모순 방지).
    assert not (set(GITIGNORE_UNIGNORE) & set(GITIGNORE_LINES))


def _git(repo: Path, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def _init_repo(repo: Path) -> None:
    _git(repo, "init")
    _git(repo, "config", "user.email", "t@t")
    _git(repo, "config", "user.name", "t")


def test_untrack_vdev_evidence_removes_tracked(tmp_path: Path):
    # 예전 설치(또는 init 전 vdev): .vdev 증거가 이미 git 에 추적 중 → 인덱스에서 제거,
    # 작업 트리 파일은 보존(.gitignore 라인만으론 이미 추적된 파일이 안 빠지는 footgun 복구).
    _init_repo(tmp_path)
    vdev = tmp_path / ".claude" / "vway-kit" / ".vdev"
    vdev.mkdir(parents=True)
    (vdev / "tier").write_text("dev:master", encoding="utf-8")
    (vdev / "doc-sync.done").touch()
    _git(tmp_path, "add", "-A")  # .gitignore 없으니 증거가 추적됨
    assert ".claude/vway-kit/.vdev/tier" in _git(tmp_path, "ls-files").stdout

    out = untrack_vdev_evidence(tmp_path)
    assert any("추적 해제" in line for line in out)
    assert ".claude/vway-kit/.vdev/" not in _git(tmp_path, "ls-files").stdout  # 인덱스에서 빠짐
    assert (vdev / "tier").is_file()  # 작업 트리 파일 보존


def test_untrack_vdev_evidence_idempotent_when_untracked(tmp_path: Path):
    # 추적된 적 없으면(정상 흐름: .gitignore 가 선제 차단) 아무것도 안 한다.
    _init_repo(tmp_path)
    assert untrack_vdev_evidence(tmp_path) == []


def test_untrack_vdev_evidence_failopen_without_git_repo(tmp_path: Path):
    # git 저장소가 아니어도(또는 git 부재) 게이트 셋업을 막지 않는다 — FAIL-OPEN.
    assert untrack_vdev_evidence(tmp_path) == []


def test_untrack_vdev_evidence_reports_rm_failure(tmp_path: Path, monkeypatch):
    # ls-files 는 성공(추적분 있음)인데 rm 만 실패하면, 거짓 성공이 아니라 [!] 를 보고한다.
    import scripts.vdev_init_setup as mod

    _init_repo(tmp_path)
    vdev = tmp_path / ".claude" / "vway-kit" / ".vdev"
    vdev.mkdir(parents=True)
    (vdev / "tier").write_text("dev:master", encoding="utf-8")
    _git(tmp_path, "add", "-A")

    real_run = subprocess.run

    def fake_run(args, **kwargs):
        if "rm" in args:  # rm 단계만 실패로 위조
            return subprocess.CompletedProcess(args, 1, "", "permission denied")
        return real_run(args, **kwargs)

    monkeypatch.setattr(mod.subprocess, "run", fake_run)
    out = untrack_vdev_evidence(tmp_path)
    assert any("실패" in line for line in out)
    assert not any("[-]" in line for line in out)  # 거짓 성공 메시지 없음


def test_migrate_legacy_moves_root_files(tmp_path: Path):
    # 구버전 루트 분산 config → config/, .claude/.vdev → vway-kit/.vdev 로 무손실 이전
    (tmp_path / "vdev-config.yaml").write_text("branches: {}\n", encoding="utf-8")
    vdev = tmp_path / ".claude" / ".vdev"
    vdev.mkdir(parents=True)
    (vdev / "tier").write_text("dev:", encoding="utf-8")
    report = migrate_legacy_paths(tmp_path)
    assert any("이전" in line for line in report)
    vd = tmp_path / ".claude" / "vway-kit"
    assert (vd / "config" / "vdev-config.yaml").read_text(encoding="utf-8") == "branches: {}\n"
    assert (vd / ".vdev" / "tier").is_file()
    assert not (tmp_path / "vdev-config.yaml").exists()  # 옛 경로 제거됨
    assert not (tmp_path / ".claude" / ".vdev").exists()


def test_migrate_legacy_removes_flat_scripts(tmp_path: Path):
    # 구버전 평면 스크립트(.claude/vway-kit/ 직속)는 scripts/ 로 옮겨지므로 잔재 제거
    flat = tmp_path / ".claude" / "vway-kit"
    flat.mkdir(parents=True)
    (flat / "precommit-runner.sh").write_text("#!/bin/bash\n", encoding="utf-8")
    (flat / "vdev-tiers.yaml").write_text("tiers: {}\n", encoding="utf-8")
    report = migrate_legacy_paths(tmp_path)
    assert any("평면 스크립트 제거" in line for line in report)
    assert not (flat / "precommit-runner.sh").exists()
    assert not (flat / "vdev-tiers.yaml").exists()


def test_migrate_relocates_scripts_tiers_to_config(tmp_path: Path):
    # scripts/→config/ 재배치: 옛 scripts/vdev-tiers.yaml 잔재를 제거한다.
    # (config/ 에는 copy_artifacts 가 새로 넣으므로 옛 위치는 잔재.)
    sd = tmp_path / ".claude" / "vway-kit" / "scripts"
    sd.mkdir(parents=True)
    (sd / "vdev-tiers.yaml").write_text("tiers: {}\n", encoding="utf-8")
    report = migrate_legacy_paths(tmp_path)
    assert not (sd / "vdev-tiers.yaml").exists()
    assert any("재배치 잔재" in line for line in report)


def test_migrate_legacy_idempotent_and_no_clobber(tmp_path: Path):
    # 신규 설치(옛 경로 없음) → skip; 새 경로가 이미 있으면 옛 것을 덮지 않음
    assert any("없음" in line for line in migrate_legacy_paths(tmp_path))
    vd = tmp_path / ".claude" / "vway-kit"
    (vd / "config").mkdir(parents=True, exist_ok=True)
    (vd / "config" / "vdev-config.yaml").write_text("new\n", encoding="utf-8")
    (tmp_path / "vdev-config.yaml").write_text("old\n", encoding="utf-8")
    migrate_legacy_paths(tmp_path)
    assert (vd / "config" / "vdev-config.yaml").read_text(encoding="utf-8") == "new\n"  # 보존
    assert (tmp_path / "vdev-config.yaml").read_text(encoding="utf-8") == "old\n"  # 미이전


def test_migrate_flow_config_to_vdev_config(tmp_path: Path):
    # flow→vdev 재명명 마이그레이션: config/flow-config.yaml → config/vdev-config.yaml (무손실)
    cfg_dir = tmp_path / ".claude" / "vway-kit" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "flow-config.yaml").write_text("branches:\n  integration: dev\n", encoding="utf-8")
    report = migrate_legacy_paths(tmp_path)
    assert (cfg_dir / "vdev-config.yaml").read_text(encoding="utf-8") == (
        "branches:\n  integration: dev\n"
    )
    assert not (cfg_dir / "flow-config.yaml").exists()
    assert any("vdev-config.yaml" in line for line in report)


def test_migrate_flow_evidence_dir_to_vdev(tmp_path: Path):
    # .claude/vway-kit/.flow/ → .claude/vway-kit/.vdev/ (게이트 증거 디렉터리 재명명)
    old = tmp_path / ".claude" / "vway-kit" / ".flow"
    old.mkdir(parents=True)
    (old / "tier").write_text("dev:", encoding="utf-8")
    migrate_legacy_paths(tmp_path)
    assert (tmp_path / ".claude" / "vway-kit" / ".vdev" / "tier").is_file()
    assert not old.exists()


def test_migrate_removes_renamed_orphan_scripts(tmp_path: Path):
    # 옛 이름 스크립트 사본(flow_gate_check.py·flow-tiers.yaml)을 scripts/ 에서 제거
    sd = tmp_path / ".claude" / "vway-kit" / "scripts"
    sd.mkdir(parents=True)
    (sd / "flow_gate_check.py").write_text("# old", encoding="utf-8")
    (sd / "flow-tiers.yaml").write_text("tiers: {}\n", encoding="utf-8")
    report = migrate_legacy_paths(tmp_path)
    assert not (sd / "flow_gate_check.py").exists()
    assert not (sd / "flow-tiers.yaml").exists()
    assert any("flow_gate_check.py" in line for line in report)


def test_migrate_flow_config_no_clobber(tmp_path: Path):
    # 새 vdev-config.yaml 이 이미 있으면 옛 flow-config.yaml 로 덮지 않는다(설정 보존)
    cfg_dir = tmp_path / ".claude" / "vway-kit" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "vdev-config.yaml").write_text("new\n", encoding="utf-8")
    (cfg_dir / "flow-config.yaml").write_text("old\n", encoding="utf-8")
    migrate_legacy_paths(tmp_path)
    assert (cfg_dir / "vdev-config.yaml").read_text(encoding="utf-8") == "new\n"
    assert (cfg_dir / "flow-config.yaml").read_text(encoding="utf-8") == "old\n"


def test_migrate_prefers_config_flow_over_root_flow(tmp_path: Path):
    # #1: config/flow-config.yaml(정규 팀 설정)이 root flow-config.yaml(stale)보다 우선해야 한다
    cfg_dir = tmp_path / ".claude" / "vway-kit" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "flow-config.yaml").write_text("REAL\n", encoding="utf-8")  # 정규 위치
    (tmp_path / "flow-config.yaml").write_text("STALE\n", encoding="utf-8")  # 옛 루트 flat
    migrate_legacy_paths(tmp_path)
    assert (cfg_dir / "vdev-config.yaml").read_text(encoding="utf-8") == "REAL\n"


def test_migrate_translates_standard_tier_marker(tmp_path: Path):
    # #3: 옛 standard tier 마커를 dev 로 번역(미번역 시 unknown tier → FAIL-OPEN 게이트 우회)
    flow = tmp_path / ".claude" / "vway-kit" / ".flow"
    flow.mkdir(parents=True)
    (flow / "tier").write_text("standard:feature/x", encoding="utf-8")
    migrate_legacy_paths(tmp_path)
    assert (tmp_path / ".claude" / "vway-kit" / ".vdev" / "tier").read_text(
        encoding="utf-8"
    ) == "dev:feature/x"


def test_migrate_translates_fast_tier_marker(tmp_path: Path):
    flow = tmp_path / ".claude" / "vway-kit" / ".flow"
    flow.mkdir(parents=True)
    (flow / "tier").write_text("fast:", encoding="utf-8")
    migrate_legacy_paths(tmp_path)
    assert (tmp_path / ".claude" / "vway-kit" / ".vdev" / "tier").read_text(
        encoding="utf-8"
    ) == "docs:"


def test_register_gate_refreshes_stale_status_message(tmp_path: Path):
    # #5: command 는 최신인데 옛 statusMessage('flow 게이트')가 남아 있으면 보정한다(skip 아님)
    from scripts.vdev_init_setup import GATE_COMMAND, GATE_STATUS

    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    old = {
        "matcher": "Bash",
        "hooks": [
            {
                "type": "command",
                "command": GATE_COMMAND,
                "statusMessage": "vway-kit: flow 게이트 검사 중…",
            }
        ],
    }
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [old]}}), encoding="utf-8")
    msg = register_gate(tmp_path)
    assert "보정" in msg
    data = json.loads(settings.read_text(encoding="utf-8"))
    assert data["hooks"]["PreToolUse"][0]["hooks"][0]["statusMessage"] == GATE_STATUS


def test_prune_stale_gitignore_removes_flow_line(tmp_path: Path):
    # #6: 옛 .claude/vway-kit/.flow/ gitignore 죽은 라인 제거(다른 라인 보존)
    from scripts.vdev_init_setup import prune_stale_gitignore

    gi = tmp_path / ".gitignore"
    gi.write_text(
        "node_modules/\n.claude/vway-kit/.flow/\n.claude/vway-kit/.vdev/\n", encoding="utf-8"
    )
    prune_stale_gitignore(tmp_path)
    content = gi.read_text(encoding="utf-8")
    assert ".claude/vway-kit/.flow/" not in content
    assert "node_modules/" in content
    assert ".claude/vway-kit/.vdev/" in content


def test_register_gate_repairs_legacy_command(tmp_path: Path):
    # 구버전 평면 경로로 등록된 게이트 command 를 최신 scripts/ 경로로 보정
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    old_cmd = 'bash ".../.claude/vway-kit/precommit-runner.sh"'  # 구버전 평면 경로
    legacy = {"matcher": "Bash", "hooks": [{"type": "command", "command": old_cmd}]}
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [legacy]}}), encoding="utf-8")
    msg = register_gate(tmp_path)
    assert "보정" in msg
    cmds = _gate_commands(settings)
    assert cmds == [GATE_COMMAND]  # 단일 엔트리가 최신 경로로 보정됨(중복 추가 X)


def test_register_gate_repairs_all_stale_entries(tmp_path: Path):
    # 중복으로 등록된 구버전(평면 경로) 게이트 엔트리를 모두 최신 경로로 보정
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    old = 'bash ".../.claude/vway-kit/precommit-runner.sh"'  # 구버전 평면 경로
    dup = [
        {"matcher": "Bash", "hooks": [{"type": "command", "command": old}]},
        {"matcher": "Bash", "hooks": [{"type": "command", "command": old}]},
    ]
    settings.write_text(json.dumps({"hooks": {"PreToolUse": dup}}), encoding="utf-8")
    msg = register_gate(tmp_path)
    assert "보정" in msg
    cmds = _gate_commands(settings)
    assert cmds == [GATE_COMMAND, GATE_COMMAND]  # 둘 다 보정(첫 것만 X)


def test_check_precommit_reports_stale_owned_entry(tmp_path: Path):
    # vway-kit 소유 훅(teams-notify-push)의 entry 가 옛 경로면 drift 보고
    dest = tmp_path / ".pre-commit-config.yaml"
    dest.write_text(
        "repos:\n"
        "  - repo: local\n"
        "    hooks:\n"
        "      - id: teams-notify-push\n"
        "        name: x\n"
        "        entry: scripts/notify-push.sh\n"  # 옛 경로(이동 전)
        "        language: script\n",
        encoding="utf-8",
    )
    report = check_precommit(PLUGIN, tmp_path)
    assert any("entry 가 옛 경로" in line for line in report)


def test_main_setup_then_uninstall_dispatch(tmp_path: Path, monkeypatch):
    # argparse 분기 + run_setup 순서(copy→register→migrate) end-to-end
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(PLUGIN))
    monkeypatch.setattr(sys, "argv", ["vdev_init_setup.py"])
    main()
    vd = tmp_path / ".claude" / "vway-kit"
    settings = tmp_path / ".claude" / "settings.json"
    assert (vd / "scripts" / "precommit-runner.sh").is_file()
    assert (vd / "config" / "vdev-tiers.yaml").is_file()
    assert any(GATE_MARKER in c for c in _gate_commands(settings))
    # --uninstall 분기 → 역연산
    monkeypatch.setattr(sys, "argv", ["vdev_init_setup.py", "--uninstall"])
    main()
    assert not vd.exists()
    assert not any(GATE_MARKER in c for c in _gate_commands(settings))


def test_copy_artifacts_includes_shared_helper(tmp_path: Path):
    # _vway_paths.py 가 COPY_FILES 에서 빠지면 호스트로 복사된 게이트 스크립트가
    # 형제 import 실패(ImportError)로 조용히 무력화된다. 누락 회귀 방지.
    copy_artifacts(PLUGIN, tmp_path)
    scripts_dir = tmp_path / ".claude" / "vway-kit" / "scripts"
    assert (scripts_dir / "_vway_paths.py").is_file()


def test_copied_gate_imports_shared_helper(tmp_path: Path):
    # 호스트 단일파일 복사 환경 end-to-end: 복사된 scripts/ 에서 vdev_gate_check.py 를
    # 직접 실행하면 형제 _vway_paths.py 를 import 해 정상 동작해야 한다. import 양립
    # 블록이 깨지면 ImportError 크래시(returncode 1 + stderr Traceback)로 즉시 잡힌다.
    # 게이트 판정 자체는 이 테스트의 관심사가 아니므로, 미분류 fail-closed 차단(정책
    # 존재 + tier 마커 부재 → exit 2)에 걸리지 않게 docs 티어 + 증거를 두어 정상 통과
    # (exit 0) 경로로 import 양립만 확인한다.
    copy_artifacts(PLUGIN, tmp_path)
    (tmp_path / ".claude").mkdir(exist_ok=True)
    vdev = tmp_path / ".claude" / "vway-kit" / ".vdev"
    vdev.mkdir(parents=True)
    (vdev / "tier").write_text("docs:", encoding="utf-8")
    (vdev / "doc-sync.done").touch()
    scripts_dir = tmp_path / ".claude" / "vway-kit" / "scripts"
    env = {**os.environ, "CLAUDE_PROJECT_DIR": str(tmp_path), "PYTHONIOENCODING": "utf-8"}
    result = subprocess.run(
        [sys.executable, str(scripts_dir / "vdev_gate_check.py")],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, f"import 양립 실패 의심: {result.stderr}"


def test_copied_gate_reads_tiers_from_config(tmp_path: Path):
    # 호스트 복사 환경 end-to-end: 복사된 scripts/vdev_gate_check.py 의 __file__ 은
    # tmp/.claude/vway-kit/scripts/ → 형제 config/ 의 vdev-tiers.yaml 을 해석해야 한다.
    # config/→scripts/ 회귀(형제 탐색이 옛 scripts/ 를 보면) 시 이 경로가 깨진다.
    copy_artifacts(PLUGIN, tmp_path)
    scripts_dir = tmp_path / ".claude" / "vway-kit" / "scripts"
    config_tiers = tmp_path / ".claude" / "vway-kit" / "config" / "vdev-tiers.yaml"
    assert config_tiers.is_file()  # copy 가 config/ 에 넣었다
    code = (
        "from pathlib import Path;"
        "from vdev_gate_check import tiers_path;"
        "import sys; sys.stdout.write(str(tiers_path(Path(sys.argv[1]))))"
    )
    env = {**os.environ, "PYTHONPATH": str(scripts_dir), "PYTHONIOENCODING": "utf-8"}
    env.pop("CLAUDE_PLUGIN_ROOT", None)  # ① 분기 비활성화 → ② config/ 탐색 검증
    result = subprocess.run(
        [sys.executable, "-c", code, str(tmp_path)],
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(config_tiers)


def test_uninstall_round_trip(tmp_path: Path):
    # setup 등록물을 uninstall 이 모두 되돌린다
    register_gate(tmp_path)
    register_marketplace(tmp_path)
    append_gitignore(tmp_path)
    vd = tmp_path / ".claude" / "vway-kit"
    (vd / "scripts").mkdir(parents=True)
    (vd / "scripts" / "precommit-runner.sh").write_text("x", encoding="utf-8")

    assert "해제" in unregister_gate(tmp_path)
    assert "해제" in unregister_marketplace(tmp_path)
    assert "제거" in remove_gitignore_lines(tmp_path)
    assert "삭제" in remove_vway_dir(tmp_path)

    data = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    assert not any(GATE_MARKER in c for c in _gate_commands(tmp_path / ".claude" / "settings.json"))
    assert "vway" not in (data.get("extraKnownMarketplaces") or {})
    gi = (tmp_path / ".gitignore").read_text(encoding="utf-8")
    assert all(line not in gi for line in GITIGNORE_LINES)
    assert not vd.exists()


def test_uninstall_idempotent(tmp_path: Path):
    # 아무것도 없을 때 uninstall 은 안전하게 skip
    assert "skip" in unregister_gate(tmp_path)
    assert "skip" in unregister_marketplace(tmp_path)
    assert "skip" in remove_gitignore_lines(tmp_path)
    assert "skip" in remove_vway_dir(tmp_path)


def test_uninstall_preserves_other_settings(tmp_path: Path):
    # 게이트 외 다른 PreToolUse 훅은 보존
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    other = {"matcher": "Bash", "hooks": [{"type": "command", "command": "echo other"}]}
    settings.write_text(json.dumps({"hooks": {"PreToolUse": [other]}}), encoding="utf-8")
    register_gate(tmp_path)
    unregister_gate(tmp_path)
    cmds = _gate_commands(settings)
    assert "echo other" in cmds
    assert not any(GATE_MARKER in c for c in cmds)


def test_remove_claude_md_block(tmp_path: Path):
    cm = tmp_path / "CLAUDE.md"
    cm.write_text(
        f"# Host\n\nkeep before\n\n{CLAUDE_MD_BEGIN} (managed) -->\nmanaged body\n"
        "<!-- vway-kit:teams END -->\n\nkeep after\n",
        encoding="utf-8",
    )
    assert "제거" in remove_claude_md_block(tmp_path)
    text = cm.read_text(encoding="utf-8")
    assert "keep before" in text and "keep after" in text
    assert "managed body" not in text and CLAUDE_MD_BEGIN not in text
    assert "skip" in remove_claude_md_block(tmp_path)  # 멱등(이미 없음)


def test_check_precommit_creates_when_absent(tmp_path: Path):
    report = check_precommit(PLUGIN, tmp_path)
    assert (tmp_path / ".pre-commit-config.yaml").is_file()
    assert any("생성" in line for line in report)


def test_check_precommit_creates_never_reports_module_hooks(tmp_path: Path):
    # 모듈 훅은 레이어2로 이동 → modules 선언돼도 pre-commit 에 모듈 훅을 보고하지 않는다.
    cfg_dir = tmp_path / ".claude" / "vway-kit" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "vdev-config.yaml").write_text(
        "modules:\n  - name: api\n    path: services/api/\n"
        "    checks:\n      lint: 'ruff check services/api'\n",
        encoding="utf-8",
    )
    report = check_precommit(PLUGIN, tmp_path)
    assert (tmp_path / ".pre-commit-config.yaml").is_file()
    assert any("생성" in line for line in report)
    assert not any("모듈 훅" in line for line in report)


def test_check_precommit_all_present(tmp_path: Path):
    check_precommit(PLUGIN, tmp_path)  # 생성(예시 전체 복사)
    report = check_precommit(PLUGIN, tmp_path)  # 모든 항목 존재
    assert any("이미 충족" in line for line in report)


def test_check_precommit_reports_missing_without_modifying(tmp_path: Path):
    # 이미 있는 config 는 절대 수정하지 않고(주석/포맷 보존), 빠진 항목만 보고한다
    dest = tmp_path / ".pre-commit-config.yaml"
    original = "# 팀 주석 — 보존되어야 함\nrepos: []\n"
    dest.write_text(original, encoding="utf-8")
    report = check_precommit(PLUGIN, tmp_path)
    assert any("병합하지 않음" in line for line in report)
    assert dest.read_text(encoding="utf-8") == original  # 파일 불변


def test_register_marketplace_creates(tmp_path: Path):
    msg = register_marketplace(tmp_path)
    assert "autoUpdate" in msg
    data = json.loads((tmp_path / ".claude" / "settings.json").read_text(encoding="utf-8"))
    vway = data["extraKnownMarketplaces"]["vway"]
    assert vway["autoUpdate"] is True
    assert vway["source"]["source"] == "github"
    assert vway["source"]["repo"] == "Developments-3/vway-kit"


def test_register_marketplace_idempotent(tmp_path: Path):
    register_marketplace(tmp_path)
    msg = register_marketplace(tmp_path)
    assert "이미" in msg


def test_register_marketplace_repairs_flag_preserving_source(tmp_path: Path):
    settings = tmp_path / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True)
    payload = {"extraKnownMarketplaces": {"vway": {"source": {"source": "git", "url": "keep-me"}}}}
    settings.write_text(json.dumps(payload), encoding="utf-8")
    msg = register_marketplace(tmp_path)
    assert "보정" in msg
    vway = json.loads(settings.read_text(encoding="utf-8"))["extraKnownMarketplaces"]["vway"]
    assert vway["autoUpdate"] is True
    assert vway["source"]["url"] == "keep-me"  # 소스 보존


def test_copy_artifacts(tmp_path: Path):
    copy_artifacts(PLUGIN, tmp_path)
    vd = tmp_path / ".claude" / "vway-kit"
    assert (vd / "scripts" / "precommit-runner.sh").is_file()
    assert (vd / "scripts" / "vdev_gate_check.py").is_file()
    # 정책 파일은 config/ 로, scripts/ 에는 두지 않는다.
    assert (vd / "config" / "vdev-tiers.yaml").is_file()
    assert not (vd / "scripts" / "vdev-tiers.yaml").exists()


def _write_vdev_config(host: Path, contract: dict) -> None:
    cfg_dir = host / ".claude" / "vway-kit" / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "vdev-config.yaml").write_text(
        _yaml.safe_dump({"contract_test": contract}, allow_unicode=True), encoding="utf-8"
    )


def test_render_workflow_creates_and_substitutes(tmp_path: Path):
    _write_vdev_config(
        tmp_path,
        {
            "enable": True,
            "branches": ["dev", "stage", "main"],
            "action_ref": "schemathesis/action@v3",
            "schema": "http://localhost:8000/openapi.json",
            "base_url": "http://localhost:8000",
            "server": {
                "compose_file": "docker-compose.yml",
                "health_url": "http://localhost:8000/health",
                "health_timeout": 60,
            },
        },
    )
    out = render_workflow(tmp_path, PLUGIN)
    assert any("생성" in line for line in out)
    dest = tmp_path / ".github" / "workflows" / "api-contract.yml"
    text = dest.read_text(encoding="utf-8")
    # 토큰이 모두 치환됐다
    assert "__VWAY_" not in text
    # 렌더 결과가 유효 YAML 이다(예외 없이 파싱). 주의: GitHub Actions 의 'on:' 키는
    # PyYAML 이 boolean True 키로 파싱하므로(YAML 1.1 함정) data["on"] 접근은 KeyError.
    # 의도(브랜치/액션/스키마 치환)는 텍스트로 직접 검증한다.
    _yaml.safe_load(text)
    assert "branches: [dev, stage, main]" in text
    assert "schemathesis/action@v3" in text
    assert "http://localhost:8000/openapi.json" in text


def test_render_workflow_disabled(tmp_path: Path):
    _write_vdev_config(tmp_path, {"enable": False, "branches": ["dev"]})
    out = render_workflow(tmp_path, PLUGIN)
    assert any("enable=false" in line for line in out)
    assert load_contract_config(tmp_path) == {"enable": False, "branches": ["dev"]}
    assert not (tmp_path / ".github" / "workflows" / "api-contract.yml").exists()


def test_render_workflow_absent_section(tmp_path: Path):
    # vdev-config 자체가 없으면 미설정 — skip
    out = render_workflow(tmp_path, PLUGIN)
    assert any("미설정" in line for line in out)
    assert load_contract_config(tmp_path) is None
    assert not (tmp_path / ".github" / "workflows" / "api-contract.yml").exists()


def test_run_setup_renders_workflow(tmp_path: Path, capsys):
    from scripts.vdev_init_setup import run_setup

    _write_vdev_config(
        tmp_path,
        {
            "enable": True,
            "branches": ["dev", "stage", "main"],
            "action_ref": "schemathesis/action@v3",
            "schema": "http://localhost:8000/openapi.json",
            "base_url": "http://localhost:8000",
            "server": {
                "compose_file": "docker-compose.yml",
                "health_url": "http://localhost:8000/health",
                "health_timeout": 60,
            },
        },
    )
    run_setup(tmp_path, PLUGIN)
    captured = capsys.readouterr().out
    assert "계약 테스트" in captured
    assert (tmp_path / ".github" / "workflows" / "api-contract.yml").is_file()


def test_render_workflow_idempotent_reports_only(tmp_path: Path):
    contract = {
        "enable": True,
        "branches": ["dev", "stage", "main"],
        "action_ref": "schemathesis/action@v3",
        "schema": "http://localhost:8000/openapi.json",
        "base_url": "http://localhost:8000",
        "server": {
            "compose_file": "docker-compose.yml",
            "health_url": "http://localhost:8000/health",
            "health_timeout": 60,
        },
    }
    _write_vdev_config(tmp_path, contract)
    render_workflow(tmp_path, PLUGIN)  # 1차 생성
    dest = tmp_path / ".github" / "workflows" / "api-contract.yml"
    sentinel = dest.read_text(encoding="utf-8") + "\n# user edit\n"
    dest.write_text(sentinel, encoding="utf-8")  # 사용자 수정 흉내
    out = render_workflow(tmp_path, PLUGIN)  # 2차 — 보고만
    assert any("이미 있어" in line for line in out)
    assert dest.read_text(encoding="utf-8") == sentinel  # 덮어쓰지 않음


def _mk_example(plugin: Path, body: str) -> None:
    """tmp 플러그인에 vdev-config.example.yaml 을 쓴다(임의 본문)."""
    (plugin / "vdev-config.example.yaml").write_text(body, encoding="utf-8")


def _mk_host_config(host: Path, text: str) -> None:
    """tmp 호스트의 config_path 위치에 vdev-config.yaml 을 쓴다."""
    from scripts.vdev_init_setup import config_path

    cfg = config_path(host)
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(text, encoding="utf-8")


def test_missing_config_slots_top_level_section(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "branches:\n  integration: dev\ncontract_test:\n  enable: true\n")
    _mk_host_config(host, "branches:\n  integration: dev\n")
    assert missing_config_slots(host, plugin) == [
        {"path": ["contract_test"], "parent": [], "label": "contract_test"}
    ]


def test_missing_config_slots_nested_key(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "test:\n  command: x\n  coverage_threshold: 80\n")
    _mk_host_config(host, "test:\n  command: x\n")
    assert missing_config_slots(host, plugin) == [
        {
            "path": ["test", "coverage_threshold"],
            "parent": ["test"],
            "label": "test.coverage_threshold",
        }
    ]


def test_missing_config_slots_empty_value_preserved(tmp_path: Path):
    # host 에 키가 있고 값이 비어도(빈 문자열/null) 빠짐으로 보지 않는다.
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "doc_sync:\n  service_docs: services/*/CLAUDE.md\n")
    _mk_host_config(host, 'doc_sync:\n  service_docs: ""\n')
    assert missing_config_slots(host, plugin) == []


def test_missing_config_slots_all_present(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "test:\n  command: x\n")
    _mk_host_config(host, "test:\n  command: x\n  extra: y\n")
    assert missing_config_slots(host, plugin) == []


def test_missing_config_slots_handoff_kind_nested(tmp_path: Path):
    # handoff 흡수: 섹션은 있고 종류만 빠지면 parent=["handoff"] 슬롯.
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(
        plugin,
        "handoff:\n  summary:\n    enable: true\n  done_flag:\n    enable: false\n",
    )
    _mk_host_config(host, "handoff:\n  summary:\n    enable: true\n")
    assert missing_config_slots(host, plugin) == [
        {"path": ["handoff", "done_flag"], "parent": ["handoff"], "label": "handoff.done_flag"}
    ]


def test_missing_config_slots_section_absent_inserts_whole(tmp_path: Path):
    # host 에 handoff 섹션 자체가 없으면 섹션 통째가 삽입 단위.
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "handoff:\n  summary:\n    enable: true\n")
    _mk_host_config(host, "branches:\n  integration: dev\n")
    assert missing_config_slots(host, plugin) == [
        {"path": ["handoff"], "parent": [], "label": "handoff"}
    ]


def test_missing_config_slots_order_preserved(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "a: 1\nb: 2\nc: 3\n")
    _mk_host_config(host, "b: 2\n")
    assert [s["label"] for s in missing_config_slots(host, plugin)] == ["a", "c"]


def test_missing_config_slots_host_absent(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "branches:\n  integration: dev\nhandoff:\n  summary:\n    enable: true\n")
    # host config 파일 없음 → example 최상위 전부
    assert [s["label"] for s in missing_config_slots(host, plugin)] == ["branches", "handoff"]


def test_missing_config_slots_host_parse_fail(tmp_path: Path):
    # 망가진 host YAML → _load_yaml_safe 가 {} → example 최상위 전부(absent 와 동등).
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "branches:\n  integration: dev\ntest:\n  command: x\n")
    _mk_host_config(host, "branches:\n  integration: [unclosed\n")
    assert [s["label"] for s in missing_config_slots(host, plugin)] == ["branches", "test"]


def test_missing_config_slots_example_absent(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_host_config(host, "branches:\n  integration: dev\n")
    assert missing_config_slots(host, plugin) == []


def test_report_missing_config_slots_lists_new(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "test:\n  command: x\ncontract_test:\n  enable: true\n")
    _mk_host_config(host, "test:\n  command: x\n")
    out = report_missing_config_slots(host, plugin)
    assert any("contract_test" in line for line in out)
    assert any("/vdev-init" in line for line in out)


def test_report_missing_config_slots_skip_when_current(tmp_path: Path):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "test:\n  command: x\n")
    _mk_host_config(host, "test:\n  command: x\n")
    assert report_missing_config_slots(host, plugin) == ["  [=] config 슬롯 최신 (skip)"]


def test_run_setup_reports_config_slots(tmp_path: Path, capsys):
    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    plugin.mkdir()
    _mk_example(plugin, "test:\n  command: x\ncontract_test:\n  enable: true\n")
    _mk_host_config(host, "test:\n  command: x\n")
    run_setup(host, plugin)
    captured = capsys.readouterr().out
    assert "[config 슬롯 점검]" in captured


def test_render_versioning_python(tmp_path):
    from scripts import vdev_init_setup as m

    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    # SOURCE 템플릿 배치
    (plugin / "github").mkdir(parents=True)
    (plugin / "github" / "release.python-semantic-release.workflow.example.yml").write_text(
        "on:\n  push:\n    branches: [__VWAY_STABLE__, __VWAY_PRERELEASE__]\n",
        encoding="utf-8",
    )
    (plugin / "github" / "branch-naming.workflow.example.yml").write_text(
        "name: branch-naming\n", encoding="utf-8"
    )
    ent_tmpl = (
        'on:\n  schedule:\n    - cron: "__VWAY_ENTROPY_SCHEDULE__"\npaths: __VWAY_ENTROPY_PATHS__\n'
    )
    (plugin / "github" / "entropy-check.workflow.example.yml").write_text(
        ent_tmpl, encoding="utf-8"
    )
    (host / ".claude" / "vway-kit" / "config").mkdir(parents=True)
    (host / ".claude" / "vway-kit" / "config" / "vdev-config.yaml").write_text(
        "versioning:\n  enable: true\n  release_tool: python-semantic-release\n"
        "  branches: {stable: main, prerelease: stage}\n"
        "  branch_naming: {enable: true}\n"
        '  entropy: {enable: true, schedule: "0 0 * * 5", paths: ["src/"]}\n',
        encoding="utf-8",
    )
    m.render_versioning_workflows(host, plugin)
    rel = (host / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "[main, stage]" in rel and "__VWAY_" not in rel
    assert (host / ".github" / "workflows" / "branch-naming.yml").exists()
    ent = (host / ".github" / "workflows" / "entropy-check.yml").read_text(encoding="utf-8")
    assert "0 0 * * 5" in ent and "src/" in ent


def test_render_versioning_disabled(tmp_path):
    from scripts import vdev_init_setup as m

    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    (host / ".claude" / "vway-kit" / "config").mkdir(parents=True)
    (host / ".claude" / "vway-kit" / "config" / "vdev-config.yaml").write_text(
        "versioning:\n  enable: false\n", encoding="utf-8"
    )
    m.render_versioning_workflows(host, plugin)
    assert not (host / ".github" / "workflows" / "release.yml").exists()


# ── Task 4: 마이그레이션 골격 ───────────────────────────────────────────────────


def test_apply_migrations_records_version(tmp_path):
    from scripts import vdev_init_setup as m

    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        '{"name":"vway-kit","version":"0.2.0"}', encoding="utf-8"
    )
    (host / ".claude" / "vway-kit" / "config").mkdir(parents=True)
    ran = []
    reg = {"0.2.0": lambda h, p: ran.append("mig-0.2.0")}
    # 최초: applied 없음 → 등록된 0.2.0 마이그레이션 실행 + 버전 기록
    m.apply_migrations(host, plugin, registry=reg)
    assert ran == ["mig-0.2.0"]
    assert m.applied_version(host) == "0.2.0"
    # 버전 마커는 gitignored 경로에 기록된다(.applied-version — config/ 아님)
    marker = host / ".claude" / "vway-kit" / ".applied-version"
    assert marker.is_file()
    # 재실행: 같은 버전 → 마이그레이션 재실행 안 함(멱등)
    m.apply_migrations(host, plugin, registry=reg)
    assert ran == ["mig-0.2.0"]


def test_apply_migrations_failopen_on_migration_error(tmp_path):
    from scripts import vdev_init_setup as m

    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        '{"name":"vway-kit","version":"1.0.0"}', encoding="utf-8"
    )
    (host / ".claude" / "vway-kit" / "config").mkdir(parents=True)

    def bad_mig(h, p):
        raise RuntimeError("boom")

    reg = {"1.0.0": bad_mig}
    # 마이그레이션 예외가 발생해도 FAIL-OPEN — 예외를 전파하지 않고 버전 기록함
    result = m.apply_migrations(host, plugin, registry=reg)
    assert any("실패" in line for line in result)
    # 버전은 여전히 기록됨(FAIL-OPEN)
    assert m.applied_version(host) == "1.0.0"


def test_apply_migrations_empty_registry(tmp_path):
    from scripts import vdev_init_setup as m

    plugin = tmp_path / "plugin"
    host = tmp_path / "host"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text(
        '{"name":"vway-kit","version":"0.3.0"}', encoding="utf-8"
    )
    (host / ".claude" / "vway-kit" / "config").mkdir(parents=True)
    # 빈 레지스트리(MIGRATIONS = {})라도 버전 기록은 됨
    result = m.apply_migrations(host, plugin, registry={})
    assert m.applied_version(host) == "0.3.0"
    assert any("기록" in line for line in result)


def test_plugin_version_fallback(tmp_path):
    from scripts import vdev_init_setup as m

    # plugin.json 없음 → 0.0.0 fallback
    plugin = tmp_path / "plugin"
    plugin.mkdir()
    assert m.plugin_version(plugin) == "0.0.0"


def test_apply_migrations_marker_gitignored(tmp_path):
    # VERSION_MARKER_PATH 가 GITIGNORE_LINES 에 포함되어 있어야 한다 —
    # append_gitignore(run_setup 에서 호출)가 이 경로를 .gitignore 에 자동 추가한다.
    from scripts import vdev_init_setup as m

    assert m.VERSION_MARKER_PATH in m.GITIGNORE_LINES
    assert m.VERSION_MARKER_PATH == ".claude/vway-kit/.applied-version"

    # append_gitignore 를 호출하면 실제로 .gitignore 에 기록된다
    host = tmp_path / "host"
    (host / ".claude" / "vway-kit" / "config").mkdir(parents=True)
    m.append_gitignore(host)
    gi_content = (host / ".gitignore").read_text(encoding="utf-8")
    assert m.VERSION_MARKER_PATH in gi_content
