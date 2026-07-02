"""vdev-init 의 기계적 셋업 / --uninstall 정리 — 멱등.
(대화형 부분은 /vdev-init 커맨드의 Claude 담당)

호스트 측 vway-kit 산출물은 모두 .claude/vway-kit/ 한 곳에 모이고, 용도별로
하위 분류된다:
  - .claude/vway-kit/scripts/  복사 게이트 스크립트 (플러그인 소유·git추적)
  - .claude/vway-kit/config/   vdev-config.yaml·vdev-tiers.yaml(정책)·계정·웹훅
  - .claude/vway-kit/.vdev/    게이트 증거 (gitignored)

setup(기본) 은 다음을 멱등하게 적용한다:
  - 게이트 스크립트를 .claude/vway-kit/scripts/, 정책 vdev-tiers.yaml 을 config/ 로 복사
  - 구버전(루트 분산·평면) config/증거/스크립트를 새 분류 위치로 이전 (신규 설치는 skip)
  - 커밋 게이트를 .claude/settings.json 의 hooks.PreToolUse 에 등록(경로 바뀌면 보정)
  - 정적분석 훅: 없으면 .pre-commit-config.yaml 생성, 있으면 빠진 항목 보고(자동 병합 X)
  - .gitignore 에 누락 라인 추가 (중복 시 skip) + 이미 추적 중인 .vdev 증거는
    git rm --cached 로 추적 해제 (라인만으론 기존 추적분이 안 빠지는 footgun 복구)
  - 비공개 마켓 자동 갱신 인증 점검 — GITHUB_TOKEN·insteadOf 충돌 (안내만, 적용하지 않음)

uninstall(--uninstall) 은 setup 의 역연산이다(호스트 정리):
  - settings.json 의 커밋 게이트 / vway 마켓 등록 해제
  - .gitignore 의 vway-kit 라인 제거, CLAUDE.md 의 teams 관리 블록 제거
  - .claude/vway-kit/ 디렉터리 삭제 (스크립트·config·증거·웹훅 포함)
  - .pre-commit-config.yaml 훅·git 훅은 파괴 위험이 커 보고만(수동 제거 안내)

경로: 호스트=CLAUDE_PROJECT_DIR(없으면 git toplevel), 플러그인=CLAUDE_PLUGIN_ROOT
(없으면 이 스크립트의 상위). 결과는 사람이 읽을 요약으로 stdout 에 출력한다.

각 함수는 경로를 인자로 받아 결과를 반환하므로 단위 테스트가 가능하다.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from pathlib import Path

# 경로 세그먼트·폴백 헬퍼·인코딩 방어는 공용 SSOT(_vway_paths)에서 가져온다(중복 정의
# 금지 — rule-dry-constants). vdev_init_setup 은 플러그인 위치에서 실행되므로 형제
# import 가 기본이고, 패키지(테스트)에서는 scripts._vway_paths 로 떨어진다.
try:
    from _vway_paths import (
        CONFIG_DIR,
        SCRIPTS_DIR,
        TIERS_FILENAME,
        VDEV_DIR,
        VWAY_DIR,
        config_path,
        force_utf8_io,
        host_root,
        plugin_root,
    )
except ImportError:
    from scripts._vway_paths import (
        CONFIG_DIR,
        SCRIPTS_DIR,
        TIERS_FILENAME,
        VDEV_DIR,
        VWAY_DIR,
        config_path,
        force_utf8_io,
        host_root,
        plugin_root,
    )

WORKFLOW_TEMPLATE = "github/api-contract.workflow.example.yml"  # SOURCE(플러그인 소유)
WORKFLOW_DEST = ".github/workflows/api-contract.yml"  # 호스트(GitHub 강제 위치 — VWAY_DIR 예외)

EXAMPLE_CONFIG = "vdev-config.example.yaml"  # 플러그인 SOURCE(handoff 종류 SSOT)

# .claude/vway-kit/scripts/ 로 복사할 게이트 스크립트(SOURCE → HOST). _vway_paths.py 는
# 복사 스크립트들이 import 하는 공용 모듈이라 함께 따라가야 한다(단일파일 복사 환경에서
# 형제 import 성립). 정책 파일 vdev-tiers.yaml 은 config/ 로 따로 복사한다(copy_artifacts).
COPY_FILES = [
    "scripts/_vway_paths.py",
    "scripts/precommit-runner.sh",
    "scripts/vdev_gate_check.py",
    "scripts/teams_alert.py",
    "scripts/notify-push.sh",
    "scripts/check-deps.sh",
]

# .gitignore 에 추가할 라인. 자격증명·개인 웹훅은 **bare 패턴**(어느 깊이든 매칭)으로
# 둔다 — 경로를 좁히면 아직 config/ 로 이전되지 않은 루트 잔여 파일이 무방비로 노출되는
# 보안 footgun 이 된다(좁히지 말고 더한다). 증거 디렉터리는 위치가 고정이라 anchored.
# vdev-config.yaml 은 팀 공유 설정(브랜치·test.command·teamer 번호 — 비밀 아님, 자격증명은
# keyring)이라 **추적**한다(무시 목록 제외 — teams-webhooks.json·scripts/ 와 같은 결).
GITIGNORE_LINES = [
    "teamer_account.md",
    ".teams-webhooks.local.json",
    f"{VDEV_DIR}/",
]

# 팀 공유로 전환된 파일. 예전 설치는 vdev-config.yaml 을 무시했으므로, 같은 저장소를
# 공유하는 개발자가 모두 동일 설정을 쓰도록 setup 시 .gitignore 의 stale 라인을 능동 제거한다.
GITIGNORE_UNIGNORE = ("vdev-config.yaml",)

# 구버전(루트 분산) → 신버전(분류) config/증거 이전 + flow→vdev 재명명 이전 대상.
# vdev-init 재실행 시 기존 호스트를 무손실로 업그레이드한다(migrate_legacy_paths).
# 옛 경로 존재 ∧ 새 경로 부재일 때만 이동(멱등·no-clobber). flow→vdev 항목은 구
# flow-init 설치 호스트의 팀 설정·증거를 새 이름으로 옮긴다(클린 교체의 일회성 마이그레이션).
LEGACY_MOVES = [
    ("vdev-config.yaml", f"{CONFIG_DIR}/vdev-config.yaml"),
    # flow→vdev: config/ 의 정규 팀 설정을 **먼저** 이전한다(root flat 보다 우선 —
    # first-match-wins 라 순서가 곧 우선순위. 역순이면 stale 한 루트 파일이 active config 가 됨).
    (f"{CONFIG_DIR}/flow-config.yaml", f"{CONFIG_DIR}/vdev-config.yaml"),  # flow→vdev: config/ 정규
    ("flow-config.yaml", f"{CONFIG_DIR}/vdev-config.yaml"),  # flow→vdev: 옛 루트 flat(차선)
    ("teams-webhooks.json", f"{CONFIG_DIR}/teams-webhooks.json"),
    (".teams-webhooks.local.json", f"{CONFIG_DIR}/.teams-webhooks.local.json"),
    (".claude/.vdev", VDEV_DIR),
    (".claude/.flow", VDEV_DIR),  # flow→vdev: 옛 flat 증거
    (f"{VWAY_DIR}/.flow", VDEV_DIR),  # flow→vdev: 분류 위치 증거 .flow→.vdev
]

# flow→vdev 재명명으로 옛 이름이 된 호스트 scripts/ 사본(재실행 시 잔재 제거 — 새 이름
# vdev_gate_check.py·vdev-tiers.yaml 은 copy_artifacts 가 이미 넣었으므로 옛 사본은 불용).
RENAMED_SCRIPT_ORPHANS = ("flow_gate_check.py", "flow_init_setup.py", "flow-tiers.yaml")

# flow→vdev 재명명으로 옛 tier 마커 값(fast/standard)을 신 정책 키(docs/dev)로 번역한다.
# 미번역 시 unknown tier → required_gates None → FAIL-OPEN 으로 진행 중 커밋이 게이트를
# 우회할 수 있다(.flow→.vdev 이전이 마커를 그대로 옮기므로 값을 함께 고친다).
TIER_RENAME = {"fast": "docs", "standard": "dev"}

# flow→vdev 재명명으로 죽은 .gitignore 라인(옛 증거 경로). setup 시 능동 제거(멱등).
STALE_GITIGNORE_LINES = (f"{VWAY_DIR}/.flow/",)

# vway-kit 가 소유한 pre-commit 훅 id(언어별 교체 대상이 아닌 고정 훅). 스크립트 위치가
# 바뀌면 기존 .pre-commit-config.yaml 의 entry 가 옛 경로를 가리키므로 drift 를 보고한다.
OWNED_HOOK_ID = "teams-notify-push"

# settings.json 에 등록할 커밋 게이트(호스트 경로로 HOST 사본 실행). `if` 필드는
# 넣지 않는다 — precommit-runner.sh 가 stdin 으로 self-filter 한다(빌드별 차이 회피).
GATE_MARKER = "precommit-runner.sh"  # 경로 무관 매칭(구버전 평면 경로도 잡음)
GATE_COMMAND = f'bash "${{CLAUDE_PROJECT_DIR:-.}}/{SCRIPTS_DIR}/precommit-runner.sh"'
GATE_STATUS = "vway-kit: vdev 게이트 + 테스트 검사 중…"  # 재명명 시 register_gate 가 보정
GATE_ENTRY = {
    "matcher": "Bash",
    "hooks": [
        {
            "type": "command",
            "shell": "bash",
            "command": GATE_COMMAND,
            "timeout": 600,
            "statusMessage": GATE_STATUS,
        }
    ],
}

# 호스트 CLAUDE.md 의 Teams 관리 블록 마커(/vdev-init Step 3 이 삽입). uninstall 이
# 이 마커 사이(포함)를 제거한다.
CLAUDE_MD_BEGIN = "<!-- vway-kit:teams BEGIN"
CLAUDE_MD_END = "<!-- vway-kit:teams END"

# vway 마켓을 호스트 settings.json 의 extraKnownMarketplaces 에 autoUpdate=true 로
# 등록한다. 배포자는 marketplace.json 으로 자동 업데이트를 강제할 수 없는 보안 경계라
# (서드파티가 동의 없이 코드를 자동 fetch+실행하게 막음), 호스트가 명시적으로 켜는 이
# 경로가 유일하다. 호스트 repo 에 커밋되면 팀원 모두 auto-update 를 켠 채 마켓을
# 등록받는다. source 는 `github`+repo 로 둔다(`git`+url 은 자동갱신 신뢰성이 낮음 —
# 표준/권장 형식이자 plugin.json source 와 일치). 비공개 repo 백그라운드 fetch 는 결국
# git clone/fetch 로 동작하는데 git 은 GITHUB_TOKEN 을 직접 읽지 않으므로, env 토큰을
# 넘기는 github.com 자격증명 헬퍼가 필요하다 — detect_autoupdate_auth 가 토큰·자격증명
# 헬퍼·insteadOf 충돌을 점검·안내한다.
MARKETPLACE_NAME = "vway"
MARKETPLACE_REPO = "Developments-3/vway-kit"
MARKETPLACE_URL = f"https://github.com/{MARKETPLACE_REPO}"  # insteadOf 예외 안내용(.git 없이)
MARKETPLACE_ENTRY = {
    "source": {"source": "github", "repo": MARKETPLACE_REPO},
    "autoUpdate": True,
}


def copy_artifacts(plugin: Path, host: Path) -> list[str]:
    """배포 산출물 복사(항상 덮어씀 — SOURCE 가 SSOT). 게이트 스크립트는
    scripts/ 로, 플러그인 정책 vdev-tiers.yaml 은 config/ 로(vdev-config 과 한곳)."""
    dest_dir = host / SCRIPTS_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    report: list[str] = []
    for rel in COPY_FILES:
        src = plugin / rel
        if not src.is_file():
            report.append(f"  [!] 소스 없음, skip: {rel}")
            continue
        shutil.copyfile(src, dest_dir / Path(rel).name)
        report.append(f"  [+] 복사: {Path(rel).name}")
    # 정책 파일은 config/ 로(호스트 소유 디렉터리지만 이 파일만은 플러그인 소유·SSOT).
    cfg_dir = host / CONFIG_DIR
    cfg_dir.mkdir(parents=True, exist_ok=True)
    tiers_src = plugin / TIERS_FILENAME
    if tiers_src.is_file():
        shutil.copyfile(tiers_src, cfg_dir / TIERS_FILENAME)
        report.append(f"  [+] 복사: {TIERS_FILENAME} → config/")
    else:
        report.append(f"  [!] 소스 없음, skip: {TIERS_FILENAME}")
    return report


def migrate_legacy_paths(host: Path) -> list[str]:
    """구버전(루트 분산·평면) 산출물을 새 분류 위치로 이전(멱등).

    1) 루트 분산 config/증거 → config/·.vdev/ 로 이동(옛 경로 존재 ∧ 새 경로 부재일
       때만 — 신규 설치이거나 이미 이전됐으면 skip).
    2) 구버전 평면 스크립트(.claude/vway-kit/ 직속) 제거 — 이제 scripts/ 로 복사되므로
       평면 사본은 잔재다(copy_artifacts 가 먼저 scripts/ 에 새로 넣은 뒤 호출).
    host 소유 파일만 다루므로 이전이 실패해도 게이트엔 영향 없다(보고만)."""
    report: list[str] = []
    (host / CONFIG_DIR).mkdir(parents=True, exist_ok=True)
    for old_rel, new_rel in LEGACY_MOVES:
        old = host / old_rel
        new = host / new_rel
        if not old.exists() or new.exists():
            continue  # 신규 설치이거나 이미 이전됨
        try:
            new.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old), str(new))
            report.append(f"  [+] 이전: {old_rel} → {new_rel}")
        except OSError as exc:
            report.append(f"  [!] 이전 실패(수동 확인): {old_rel} → {new_rel} ({exc})")

    # flow→vdev: 옛 tier 마커 값(fast/standard)을 docs/dev 로 번역한다(미번역 시 unknown
    # tier → FAIL-OPEN 게이트 우회). .flow→.vdev 이전이 마커를 그대로 옮기므로 값을 고친다.
    tier_file = host / VDEV_DIR / "tier"
    if tier_file.is_file():
        try:
            label, sep, rest = tier_file.read_text(encoding="utf-8").strip().partition(":")
            new_label = TIER_RENAME.get(label.strip().lower())
            if new_label:
                tier_file.write_text(f"{new_label}:{rest}" if sep else new_label, encoding="utf-8")
                report.append(f"  [+] tier 마커 번역: {label} → {new_label}")
        except OSError as exc:
            report.append(f"  [!] tier 마커 번역 실패: {exc}")

    # 구버전 평면 스크립트 잔재 정리(scripts/ 로 옮겨졌으므로 평면 사본 제거)
    flat_dir = host / VWAY_DIR
    for rel in COPY_FILES:
        flat = flat_dir / Path(rel).name
        if flat.is_file():
            try:
                flat.unlink()
                report.append(f"  [+] 구버전 평면 스크립트 제거: {Path(rel).name}")
            except OSError as exc:
                report.append(f"  [!] 평면 스크립트 제거 실패: {Path(rel).name} ({exc})")

    # flow→vdev 재명명 잔재: scripts/ 의 옛 이름 사본 제거(새 이름은 copy_artifacts 가 이미 넣음)
    scripts_dir = host / SCRIPTS_DIR
    for name in RENAMED_SCRIPT_ORPHANS:
        orphan = scripts_dir / name
        if orphan.is_file():
            try:
                orphan.unlink()
                report.append(f"  [+] 재명명 잔재 제거: {name}")
            except OSError as exc:
                report.append(f"  [!] 재명명 잔재 제거 실패: {name} ({exc})")

    # vdev-tiers.yaml 재배치(scripts/→config/): 옛 위치 사본 제거. config/ 에는
    # copy_artifacts 가 새로 넣으므로(SSOT) 옛 위치(scripts/·구버전 평면)는 잔재다.
    for old_dir in (host / SCRIPTS_DIR, host / VWAY_DIR):
        orphan = old_dir / TIERS_FILENAME
        if orphan.is_file():
            try:
                orphan.unlink()
                report.append(f"  [+] 재배치 잔재 제거: {old_dir.name}/{TIERS_FILENAME}")
            except OSError as exc:
                report.append(f"  [!] 재배치 잔재 제거 실패: {TIERS_FILENAME} ({exc})")

    if not report:
        report.append("  [=] 이전할 구버전 경로 없음 (skip)")
    return report


def _load_settings(host: Path) -> tuple[Path, dict | None, str | None]:
    """settings.json 경로·파싱결과를 반환. 파싱 실패 시 (path, None, 에러메시지)."""
    settings = host / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    if not settings.is_file():
        return settings, {}, None
    try:
        return settings, json.loads(settings.read_text(encoding="utf-8")) or {}, None
    except json.JSONDecodeError:
        return settings, None, "  [!] settings.json 파싱 실패 — 수동 확인 필요"


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def register_gate(host: Path) -> str:
    """커밋 게이트를 .claude/settings.json 에 등록. 이미 있으면 skip, 명령 경로가
    구버전이면 최신 경로로 보정(평면→scripts/ 이전 시 깨지지 않게)."""
    settings, data, err = _load_settings(host)
    if data is None:
        return err or "  [!] settings.json 파싱 실패"
    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
    if not isinstance(pre, list):
        return "  [!] hooks.PreToolUse 형식 비정상 — 게이트 미등록(수동 확인)"
    gate_hooks = [
        hook
        for entry in pre
        for hook in (entry or {}).get("hooks", []) or []
        if GATE_MARKER in (hook.get("command") or "")
    ]
    if not gate_hooks:
        pre.append(GATE_ENTRY)
        _write_json(settings, data)
        return "  [+] 커밋 게이트 등록 (settings.json)"
    # 이미 등록됨 — 구버전 경로를 가리키는 **모든** 엔트리를 최신 경로로 보정한다
    # (첫 엔트리만 고치면 중복 stale 엔트리가 삭제된 flat 경로를 영구히 가리킴).
    # command(경로) 또는 statusMessage(재명명 시 옛 'flow 게이트' 텍스트)가 어긋나면 보정한다.
    stale = [
        h
        for h in gate_hooks
        if h.get("command") != GATE_COMMAND or h.get("statusMessage") != GATE_STATUS
    ]
    if not stale:
        return "  [=] 커밋 게이트 이미 등록됨 (skip)"
    for hook in stale:
        hook["command"] = GATE_COMMAND
        hook["statusMessage"] = GATE_STATUS
    _write_json(settings, data)
    return f"  [+] 커밋 게이트 보정 (settings.json, {len(stale)}건)"


def register_marketplace(host: Path) -> str:
    """vway 마켓을 .claude/settings.json extraKnownMarketplaces 에 autoUpdate=true 로
    등록(없으면 추가, 있으면 autoUpdate 만 보정, 이미 true 면 skip). 소스는 보존한다."""
    settings, data, err = _load_settings(host)
    if data is None:
        return err or "  [!] settings.json 파싱 실패"
    mkts = data.setdefault("extraKnownMarketplaces", {})
    if not isinstance(mkts, dict):
        return "  [!] extraKnownMarketplaces 형식 비정상 — 마켓 미등록(수동 확인)"
    existing = mkts.get(MARKETPLACE_NAME)
    if isinstance(existing, dict):
        if existing.get("autoUpdate") is True:
            return "  [=] vway 마켓 autoUpdate 이미 켜짐 (skip)"
        existing["autoUpdate"] = True  # 소스는 보존, autoUpdate 만 보정
        msg = "  [+] vway 마켓 autoUpdate=true 보정"
    else:
        mkts[MARKETPLACE_NAME] = dict(MARKETPLACE_ENTRY)
        msg = "  [+] vway 마켓 등록 + autoUpdate=true"
    _write_json(settings, data)
    return msg


def append_gitignore(host: Path) -> list[str]:
    """.gitignore 에 누락 라인만 추가(중복 없이). 모두 있으면 skip."""
    gi = host / ".gitignore"
    text = gi.read_text(encoding="utf-8") if gi.is_file() else ""
    existing = {ln.strip() for ln in text.splitlines()}
    missing = [ln for ln in GITIGNORE_LINES if ln not in existing]
    if not missing:
        return ["  [=] .gitignore 이미 최신 (skip)"]
    if text and not text.endswith("\n"):
        text += "\n"
    text += "".join(ln + "\n" for ln in missing)
    gi.write_text(text, encoding="utf-8")
    return [f"  [+] .gitignore += {ln}" for ln in missing]


def prune_stale_gitignore(host: Path) -> list[str]:
    """flow→vdev 재명명으로 죽은 .gitignore 라인(STALE_GITIGNORE_LINES)을 제거(멱등).

    옛 증거 경로 `.claude/vway-kit/.flow/` 는 `.vdev/` 로 바뀌어 더는 무시 대상이 아니다.
    setup 시 능동 제거해 마이그레이션된 호스트에 죽은 라인이 누적되지 않게 한다.
    """
    gi = host / ".gitignore"
    if not gi.is_file():
        return []
    lines = gi.read_text(encoding="utf-8").splitlines()
    kept = [ln for ln in lines if ln.strip() not in STALE_GITIGNORE_LINES]
    if len(kept) == len(lines):
        return []
    text = "\n".join(kept)
    if text:
        text += "\n"
    gi.write_text(text, encoding="utf-8")
    removed = sorted({ln.strip() for ln in lines} & set(STALE_GITIGNORE_LINES))
    return [f"  [-] .gitignore 죽은 라인 제거: {ln}" for ln in removed]


def unignore_shared(host: Path) -> list[str]:
    """팀 공유로 전환된 파일(GITIGNORE_UNIGNORE)이 .gitignore 에 남아 있으면 제거한다.

    예전 설치는 vdev-config.yaml 을 무시했다 — 같은 저장소를 공유하는 개발자가 모두
    동일 설정을 쓰려면 추적되어야 하므로, setup 시 stale ignore 라인을 능동 제거한다.
    멱등(이미 없으면 빈 결과). 다른 라인은 보존한다.
    """
    gi = host / ".gitignore"
    if not gi.is_file():
        return []
    lines = gi.read_text(encoding="utf-8").splitlines()
    kept = [ln for ln in lines if ln.strip() not in GITIGNORE_UNIGNORE]
    if len(kept) == len(lines):
        return []
    text = "\n".join(kept)
    if text:
        text += "\n"
    gi.write_text(text, encoding="utf-8")
    removed = sorted({ln.strip() for ln in lines} & set(GITIGNORE_UNIGNORE))
    return [f"  [-] .gitignore 공유 전환(추적) 제거: {ln}" for ln in removed]


def untrack_vdev_evidence(host: Path) -> list[str]:
    """이미 git 에 추적 중인 .vdev 증거를 인덱스에서 제거(작업 트리 파일은 보존).

    `.gitignore` 라인은 *아직 추적되지 않은* 파일만 무시한다 — 예전 설치나 라인 추가
    이전에 `git add` 된 증거는 무시 규칙을 더해도 계속 추적된다(흔한 footgun). setup 시
    한 번 인덱스에서 빼 무시가 실제로 적용되게 한다(멱등 — 추적분 없으면 빈 결과). git
    부재·비저장소·기타 내부 오류는 FAIL-OPEN(빈 결과) — 게이트 셋업을 막지 않는다.
    """
    try:
        tracked = subprocess.run(
            ["git", "-C", str(host), "ls-files", "--", VDEV_DIR],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if tracked.returncode != 0 or not tracked.stdout.strip():
            return []
        removed = subprocess.run(
            ["git", "-C", str(host), "rm", "-r", "--cached", "--quiet", "--", VDEV_DIR],
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        if removed.returncode != 0:
            # rm 만 실패(권한·인덱스 잠금 등) — 추적이 안 빠졌는데 빠졌다고 거짓 보고하지
            # 않는다. 게이트 셋업은 막지 않되(FAIL-OPEN) 수동 확인을 명시한다.
            return [f"  [!] .vdev 추적 해제 실패 — 수동 확인 필요 (git rm --cached): {VDEV_DIR}"]
        return [f"  [-] .vdev 추적 해제 (git rm --cached): {VDEV_DIR}"]
    except Exception:
        return []


def _find_hook_entry(cfg: dict, hook_id: str) -> str | None:
    """pre-commit config dict 에서 주어진 hook id 의 `entry` 값을 찾는다(없으면 None)."""
    for repo in cfg.get("repos") or []:
        if not isinstance(repo, dict):
            continue
        for hook in repo.get("hooks") or []:
            if isinstance(hook, dict) and hook.get("id") == hook_id:
                return hook.get("entry")
    return None


def check_precommit(plugin: Path, host: Path) -> list[str]:
    """정적분석 훅 처리. 파일이 없으면 예시를 복사(생성)한다. **이미 있으면 자동
    병합하지 않는다** — PyYAML 라운드트립이 기존 주석/포맷을 정규화(파괴)하기 때문.
    대신 빠진 repo/hook 을 감지해 보고만 하고, 사용자가 직접 추가하게 한다.
    """
    import yaml

    example = plugin / "pre-commit-hooks.example.yaml"
    dest = host / ".pre-commit-config.yaml"
    if not example.is_file():
        return ["  [!] pre-commit-hooks.example.yaml 없음 — skip"]
    if not dest.is_file():
        shutil.copyfile(example, dest)
        return ["  [+] .pre-commit-config.yaml 생성 (예시 복사 — local 훅은 팀 언어로 교체)"]
    try:
        ex = yaml.safe_load(example.read_text(encoding="utf-8")) or {}
        cur = yaml.safe_load(dest.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return ["  [!] .pre-commit-config.yaml 파싱 실패 — 수동 확인 필요"]
    by_url = {r.get("repo"): r for r in (cur.get("repos") or []) if isinstance(r, dict)}
    missing: list[str] = []
    for exrepo in ex.get("repos", []):
        url = exrepo.get("repo")
        target = by_url.get(url)
        if target is None:
            missing.append(f"repo {url} (전체)")
            continue
        have = {h.get("id") for h in (target.get("hooks") or []) if isinstance(h, dict)}
        missing += [
            f"{url}#{h.get('id')}" for h in exrepo.get("hooks", []) if h.get("id") not in have
        ]
    # vway-kit 소유 훅의 entry 경로 drift — 스크립트 위치가 바뀌면 기존 entry 가 옛
    # 경로를 가리켜 pre-push 가 깨진다. 자동 수정하지 않고(주석/포맷 보존) 보고만 한다.
    ex_entry = _find_hook_entry(ex, OWNED_HOOK_ID)
    cur_entry = _find_hook_entry(cur, OWNED_HOOK_ID)
    stale: list[str] = []
    if ex_entry and cur_entry and ex_entry != cur_entry:
        stale = [
            f"  [!] '{OWNED_HOOK_ID}' entry 가 옛 경로입니다: {cur_entry}",
            f"        → '{ex_entry}' 로 직접 수정하세요(스크립트 위치 변경).",
        ]
    if not missing:
        return ["  [=] pre-commit 훅 이미 충족 (변경 없음)", *stale]
    out = [
        "  [i] .pre-commit-config.yaml 가 이미 있어 자동 병합하지 않음(주석/포맷 보존).",
        "  [i] 아래 빠진 항목을 pre-commit-hooks.example.yaml 참고해 직접 추가하세요:",
    ]
    out += [f"        - {m}" for m in missing]
    return out + stale


def _git_config(*args: str) -> str | None:
    """`git config --global <args>` 의 stdout 반환(조회 실패 시 None)."""
    try:
        return subprocess.run(
            ["git", "config", "--global", *args], capture_output=True, text=True
        ).stdout
    except Exception:
        return None


def detect_autoupdate_auth() -> list[str]:
    """비공개 마켓 백그라운드 자동 갱신 인증 점검(적용하지 않고 안내만).

    백그라운드 자동 갱신은 결국 git clone/fetch 로 동작하고, git 은 GITHUB_TOKEN 을
    직접 읽지 않는다. 비공개 repo 가 무인 인증되려면 세 가지가 필요하다:
    (1) GITHUB_TOKEN env, (2) 그 토큰을 비대화형으로 넘기는 github.com 자격증명 헬퍼,
    (3) 전역 https→ssh insteadOf 가 있으면 마켓 repo 만 HTTPS 로 두는 예외(SSH 는 백그라운드
    에서 agent 가 없어 실패하므로 HTTPS 를 유지해야 헬퍼가 동작).
    """
    out: list[str] = []

    # (1) 토큰
    if os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"):
        out.append("  [=] GITHUB_TOKEN/GH_TOKEN 환경변수 감지됨")
    else:
        out.append(
            "  [i] 토큰 미설정 — fine-grained PAT(Contents:read)를 발급해\n"
            "      GITHUB_TOKEN 환경변수로 설정하세요(아래 자격증명 헬퍼가 이 값을 읽음)."
        )

    helper = _git_config("--get-all", "credential.https://github.com.helper")
    rules = _git_config("--get-regexp", r"^url\..*\.insteadof$")
    if helper is None or rules is None:
        out.append("  [i] git config 조회 실패 — 자격증명 헬퍼·insteadOf 확인 생략")
        return out

    # (2) github.com 비대화형 자격증명 헬퍼
    if helper.strip():
        out.append("  [=] github.com 자격증명 헬퍼 설정됨(비대화형 인증)")
    else:
        out.append(
            "  [!] github.com 자격증명 헬퍼 없음 — git 은 GITHUB_TOKEN 을 직접 안 읽어\n"
            "      비공개 마켓 백그라운드 fetch 가 막힙니다. env 토큰을 넘기는 헬퍼 설치:\n"
            '      git config --global credential.https://github.com.helper ""\n'
            "      git config --global --add credential.https://github.com.helper \\\n"
            '        \'!f() { test "$1" = get && echo username=x-access-token'
            ' && echo "password=$GITHUB_TOKEN"; }; f\''
        )

    # (3) 광범위 insteadOf 충돌
    lines = [ln.strip().lower() for ln in rules.splitlines() if ln.strip()]
    broad = any(ln.endswith(" https://github.com/") for ln in lines)  # 전역 https→ssh
    surgical = any(MARKETPLACE_URL.lower() in ln for ln in lines)  # 마켓 repo 예외
    if broad and not surgical:
        out.append(
            "  [!] 전역 https→ssh insteadOf 감지 — 토큰(HTTPS)이 SSH 로 치환돼 자동\n"
            "      갱신이 깨집니다. 마켓 repo 만 HTTPS 로 예외 처리하세요(직접 실행):\n"
            f'      git config --global url."{MARKETPLACE_URL}".insteadOf "{MARKETPLACE_URL}"'
        )
    elif broad:
        out.append("  [=] insteadOf 예외(마켓 repo HTTPS 유지) 이미 설정됨")
    else:
        out.append("  [=] 광범위 insteadOf 없음 — 토큰 HTTPS 경로에 충돌 없음")
    return out


# ── uninstall(정리) — setup 의 역연산 ──────────────────────────────────────────


def _entry_has_gate(entry: dict) -> bool:
    """PreToolUse 엔트리의 훅 명령에 게이트 마커가 들어 있으면 True."""
    hooks = (entry or {}).get("hooks", []) or []
    return any(GATE_MARKER in (h.get("command") or "") for h in hooks)


def unregister_gate(host: Path) -> str:
    """settings.json 의 커밋 게이트 훅(엔트리)을 제거(없으면 skip)."""
    settings, data, err = _load_settings(host)
    if data is None:
        return err or "  [!] settings.json 파싱 실패"
    pre = (data.get("hooks") or {}).get("PreToolUse")
    if not isinstance(pre, list):
        return "  [=] 게이트 훅 없음 (skip)"
    kept = [e for e in pre if not _entry_has_gate(e)]
    if len(kept) == len(pre):
        return "  [=] 게이트 훅 없음 (skip)"
    data["hooks"]["PreToolUse"] = kept
    _write_json(settings, data)
    return "  [-] 커밋 게이트 해제 (settings.json)"


def unregister_marketplace(host: Path) -> str:
    """settings.json extraKnownMarketplaces 에서 vway 마켓 등록을 제거(없으면 skip)."""
    settings, data, err = _load_settings(host)
    if data is None:
        return err or "  [!] settings.json 파싱 실패"
    mkts = data.get("extraKnownMarketplaces")
    if not isinstance(mkts, dict) or MARKETPLACE_NAME not in mkts:
        return "  [=] vway 마켓 등록 없음 (skip)"
    del mkts[MARKETPLACE_NAME]
    _write_json(settings, data)
    return "  [-] vway 마켓 등록 해제 (settings.json)"


def remove_gitignore_lines(host: Path) -> str:
    """.gitignore 에서 vway-kit 가 추가한 라인만 제거(다른 라인은 보존)."""
    gi = host / ".gitignore"
    if not gi.is_file():
        return "  [=] .gitignore 없음 (skip)"
    targets = set(GITIGNORE_LINES) | set(STALE_GITIGNORE_LINES)
    lines = gi.read_text(encoding="utf-8").splitlines()
    kept = [ln for ln in lines if ln.strip() not in targets]
    removed = len(lines) - len(kept)
    if removed == 0:
        return "  [=] .gitignore 에 vway-kit 라인 없음 (skip)"
    text = "\n".join(kept)
    if text and not text.endswith("\n"):
        text += "\n"
    gi.write_text(text, encoding="utf-8")
    return f"  [-] .gitignore vway-kit 라인 {removed}개 제거"


def remove_claude_md_block(host: Path) -> str:
    """호스트 CLAUDE.md 의 vway-kit:teams 관리 블록(마커 포함)을 제거(없으면 skip)."""
    cm = host / "CLAUDE.md"
    if not cm.is_file():
        return "  [=] CLAUDE.md 없음 (skip)"
    lines = cm.read_text(encoding="utf-8").splitlines(keepends=True)
    begin = end = None
    for i, ln in enumerate(lines):
        if begin is None and CLAUDE_MD_BEGIN in ln:
            begin = i
        elif begin is not None and CLAUDE_MD_END in ln:
            end = i
            break
    if begin is None or end is None:
        return "  [=] CLAUDE.md teams 블록 없음 (skip)"
    del lines[begin : end + 1]
    cm.write_text("".join(lines), encoding="utf-8")
    return "  [-] CLAUDE.md teams 블록 제거"


def remove_vway_dir(host: Path) -> str:
    """.claude/vway-kit/ 디렉터리를 통째 삭제(스크립트·config·증거·웹훅 포함)."""
    d = host / VWAY_DIR
    if not d.is_dir():
        return "  [=] .claude/vway-kit/ 없음 (skip)"
    shutil.rmtree(d)
    return "  [-] .claude/vway-kit/ 삭제 (스크립트·config·증거·웹훅 포함)"


def _load_yaml_safe(path: Path) -> dict:
    """YAML 파일을 dict 로 읽는다. 부재·파싱 실패·비dict 는 {}(FAIL-OPEN)."""
    import yaml

    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _diff_missing(ex: dict, cur: dict, prefix: list[str]) -> list[dict]:
    """example 에 있고 host(cur)에 없는 키를 삽입 단위로 재귀 수집(example 순서).

    - cur 에 키가 없으면 그 지점을 삽입 단위로 기록(하위로 더 내려가지 않음 —
      부모 블록째 verbatim 삽입되므로).
    - 양쪽 dict 면 더 내려간다. cur 쪽이 dict 가 아니면(스칼라/리스트/빈값) 멈춘다.
    - example 값이 dict 인데 host 값이 dict 가 아니면(스칼라/리스트) 재귀를 멈추고
      해당 서브트리는 무보고로 남긴다(host 가 커스텀 타입으로 설정한 것으로 간주).
    """
    out: list[dict] = []
    for key, ex_val in ex.items():
        if key not in cur:
            path = prefix + [key]
            out.append({"path": path, "parent": list(prefix), "label": ".".join(path)})
        elif isinstance(ex_val, dict) and isinstance(cur.get(key), dict):
            out.extend(_diff_missing(ex_val, cur[key], prefix + [key]))
    return out


def missing_config_slots(host: Path, plugin: Path) -> list[dict]:
    """example 에 있고 host config 에 없는 슬롯을 삽입 단위로 반환(example 등장 순).

    각 항목 {"path", "parent", "label"}. '빠짐' 은 키 부재만(값이 비어도 키 있으면
    제외 — 의도적 빈 값 보존). host config 부재·빈 config·파싱 실패 시에는 example
    최상위 슬롯 전부를 반환한다(신규 설치와 동등). 이 함수는 vdev-init 이 host config
    존재 시에만 호출한다(신규 설치는 별도 전체 생성 경로). example 부재 → [].
    vdev-init 이 이 목록으로 example 블록을 verbatim 삽입한다(주석 보존).
    """
    ex = _load_yaml_safe(plugin / EXAMPLE_CONFIG)
    if not ex:
        return []
    cur = _load_yaml_safe(config_path(host))
    return _diff_missing(ex, cur, [])


def report_missing_config_slots(host: Path, plugin: Path) -> list[str]:
    """run_setup 보고용: 빠진 config 슬롯을 사람이 읽을 줄로. 없으면 skip 한 줄."""
    slots = missing_config_slots(host, plugin)
    if not slots:
        return ["  [=] config 슬롯 최신 (skip)"]
    labels = ", ".join(s["label"] for s in slots)
    return [
        f"  [i] example 에 새 config 슬롯 {len(slots)}개: {labels}",
        "      → /vdev-init 으로 호스트 config 에 추가를 검토하세요.",
    ]


def load_contract_config(host: Path) -> dict | None:
    """vdev-config.yaml 의 contract_test dict 를 반환(없거나 파싱 실패 시 None — FAIL-OPEN)."""
    import yaml

    cfg = config_path(host)
    if not cfg.is_file():
        return None
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return None
    ct = data.get("contract_test")
    return ct if isinstance(ct, dict) else None


def render_workflow(host: Path, plugin: Path) -> list[str]:
    """contract_test 설정으로 .github/workflows/api-contract.yml 을 렌더링한다.

    멱등·비파괴: enable=false/섹션부재면 미설치, 대상 파일이 이미 있으면 보고만
    (자동 병합·덮어쓰기 X — .pre-commit-config.yaml 과 동일 패턴). GitHub 이 위치를
    강제하므로 .github/workflows/ 는 VWAY_DIR 규칙의 예외다.
    """
    ct = load_contract_config(host)
    if ct is None:
        return ["  [=] contract_test 미설정 — 워크플로우 skip"]
    if not ct.get("enable"):
        return ["  [=] contract_test.enable=false — 워크플로우 미설치"]
    template = plugin / WORKFLOW_TEMPLATE
    if not template.is_file():
        return ["  [!] 워크플로우 템플릿 없음 — skip"]
    dest = host / WORKFLOW_DEST
    if dest.is_file():
        return [
            "  [i] .github/workflows/api-contract.yml 이미 있어 자동 병합 안 함(주석/커스텀 보존).",
            "  [i] 갱신하려면 기존 파일을 지우고 /vdev-init 을 재실행하거나 직접 수정하세요.",
        ]
    branches = ct.get("branches") or ["dev", "stage", "main"]
    server = ct.get("server") or {}
    replacements = {
        "__VWAY_BRANCHES__": ", ".join(str(b) for b in branches),
        "__VWAY_ACTION_REF__": str(ct.get("action_ref", "schemathesis/action@v3")),
        "__VWAY_SCHEMA__": str(ct.get("schema", "")),
        "__VWAY_BASE_URL__": str(ct.get("base_url", "")),
        "__VWAY_COMPOSE_FILE__": str(server.get("compose_file", "docker-compose.yml")),
        "__VWAY_HEALTH_URL__": str(server.get("health_url", "")),
        "__VWAY_HEALTH_TIMEOUT__": str(server.get("health_timeout", 60)),
    }
    try:
        text = template.read_text(encoding="utf-8")
        for token, value in replacements.items():
            text = text.replace(token, value)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    except OSError as exc:
        return [f"  [!] 워크플로우 렌더링 실패(수동 확인): {exc}"]
    return ["  [+] .github/workflows/api-contract.yml 생성 (contract_test 렌더링)"]


def load_versioning_config(host: Path) -> dict | None:
    """vdev-config.yaml 의 versioning dict 반환(없거나 파싱 실패 시 None — FAIL-OPEN)."""
    cfg = host / VWAY_DIR / "config" / "vdev-config.yaml"
    try:
        data = _load_yaml_safe(cfg)
    except Exception:
        return None
    v = data.get("versioning")
    return v if isinstance(v, dict) else None


_RELEASE_TEMPLATES = {
    "python-semantic-release": "github/release.python-semantic-release.workflow.example.yml",
    "semantic-release": "github/release.semantic-release.workflow.example.yml",
}


def _render_one(src: Path, dest: Path, subs: dict) -> list[str]:
    if not src.exists():
        return [f"  [!] 템플릿 없음: {src.name} — skip"]
    if dest.exists():
        return [f"  [i] {dest.name} 이미 있어 자동 병합 안 함(커스텀 보존)."]
    text = src.read_text(encoding="utf-8")
    for k, val in subs.items():
        text = text.replace(k, val)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return [f"  [+] .github/workflows/{dest.name} 생성 (versioning 렌더)"]


def render_versioning_workflows(host: Path, plugin: Path) -> list[str]:
    """versioning 설정으로 release/branch-naming/entropy 워크플로우를 렌더링한다.

    멱등·비파괴: enable=false/섹션부재면 미설치, 대상 파일이 이미 있으면 보고만
    (자동 병합·덮어쓰기 X). FAIL-OPEN — 예외는 통과(게이트를 막지 않음).
    """
    v = load_versioning_config(host)
    if not v:
        return ["  [=] versioning 미설정 — 워크플로 skip"]
    if not v.get("enable", False):
        return ["  [=] versioning.enable=false — 워크플로 미설치"]
    out: list[str] = []
    branches = v.get("branches", {}) or {}
    stable = str(branches.get("stable", "main"))
    prerelease = str(branches.get("prerelease", "") or "")
    subs = {"__VWAY_STABLE__": stable, "__VWAY_PRERELEASE__": prerelease}
    wf_dir = host / ".github" / "workflows"

    # release (도구별)
    tool = str(v.get("release_tool", ""))
    tmpl = _RELEASE_TEMPLATES.get(tool)
    if tmpl:
        out += _render_one(plugin / tmpl, wf_dir / "release.yml", subs)
    else:
        out.append(f"  [!] 알 수 없는 release_tool={tool!r} — release.yml skip")

    # branch-naming
    if (v.get("branch_naming", {}) or {}).get("enable", False):
        out += _render_one(
            plugin / "github/branch-naming.workflow.example.yml",
            wf_dir / "branch-naming.yml",
            subs,
        )

    # entropy
    ent = v.get("entropy", {}) or {}
    if ent.get("enable", False):
        esub = dict(subs)
        esub["__VWAY_ENTROPY_SCHEDULE__"] = str(ent.get("schedule", "0 0 * * 5"))
        esub["__VWAY_ENTROPY_PATHS__"] = " ".join(str(p) for p in (ent.get("paths") or ["src/"]))
        out += _render_one(
            plugin / "github/entropy-check.workflow.example.yml",
            wf_dir / "entropy-check.yml",
            esub,
        )
    return out


# ── 버전 감지 + 마이그레이션 레지스트리 ──────────────────────────────────────────

# 호스트 적용 버전 마커: gitignored 경로(.vway-kit/ 직속, config/ 밖 — config/ 는 git-tracked).
# GITIGNORE_LINES 에 추가해 setup 시 자동으로 gitignore 등록한다.
VERSION_MARKER_PATH = f"{VWAY_DIR}/.applied-version"

# .gitignore 에 VERSION_MARKER_PATH 추가 — GITIGNORE_LINES 를 직접 수정하는 대신
# append_gitignore 가 GITIGNORE_LINES 를 읽으므로 리스트에 포함한다.
# (아래 선언 시점에 GITIGNORE_LINES 가 이미 정의돼 있으므로 append 로 추가한다.)
GITIGNORE_LINES.append(VERSION_MARKER_PATH)


def _vkey(s: str) -> tuple:
    """SemVer 문자열을 비교 가능한 정수 tuple 로 파싱한다(stdlib-only, packaging 불필요)."""
    return tuple(int(x) for x in re.findall(r"\d+", s)) or (0,)


# 버전 구간별 마이그레이션. key=이 버전으로 올라올 때 실행. 지금은 비어 있음(골격).
MIGRATIONS: dict = {}


def plugin_version(plugin: Path) -> str:
    """플러그인 plugin.json 의 version 값을 반환(읽기 실패 시 '0.0.0')."""
    try:
        data = json.loads((plugin / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        return str(data.get("version", "")) or "0.0.0"
    except Exception:
        return "0.0.0"


def applied_version(host: Path) -> str | None:
    """호스트에 기록된 적용 vway-kit 버전을 반환(마커 없으면 None)."""
    f = host / VERSION_MARKER_PATH
    return f.read_text(encoding="utf-8").strip() if f.exists() else None


def apply_migrations(host: Path, plugin: Path, registry: dict | None = None) -> list[str]:
    """호스트 적용 버전 → 현재 plugin 버전 사이의 마이그레이션을 순서대로 실행하고
    버전 마커를 갱신한다. FAIL-OPEN(마이그레이션 예외는 경고만, 흐름 유지)."""
    reg = MIGRATIONS if registry is None else registry
    cur = plugin_version(plugin)
    prev = applied_version(host)
    out: list[str] = []
    if prev == cur:
        return [f"  [=] vway-kit {cur} 이미 적용됨 — 마이그레이션 없음"]
    # prev(제외) < v <= cur 구간의 등록 마이그레이션을 버전 오름차순 실행
    todo = sorted(
        (v for v in reg if (prev is None or _vkey(prev) < _vkey(v)) and _vkey(v) <= _vkey(cur)),
        key=_vkey,
    )
    for v in todo:
        try:
            reg[v](host, plugin)
            out.append(f"  [+] 마이그레이션 적용: {v}")
        except Exception as e:  # noqa: BLE001 — FAIL-OPEN
            out.append(f"  [!] 마이그레이션 {v} 실패(무시): {e}")
    marker = host / VERSION_MARKER_PATH
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(cur + "\n", encoding="utf-8")
    out.append(f"  [i] 적용 버전 기록: {prev or '(없음)'} → {cur}")
    return out


def run_setup(host: Path, plugin: Path) -> None:
    print(f"vdev-init 기계적 셋업 — host={host}")
    print("[복사]")
    for line in copy_artifacts(plugin, host):
        print(line)
    # 등록(게이트 command 보정)을 flat 스크립트 삭제(migrate)보다 먼저 한다 — copy 가
    # 새 scripts/ 사본을 이미 만들었으므로, command 를 새 경로로 보정한 뒤 옛 flat 을
    # 지워야 중단되더라도 게이트가 삭제된 경로를 가리키는 창이 생기지 않는다.
    print("[커밋 게이트]")
    print(register_gate(host))
    print("[마켓 자동 업데이트]")
    print(register_marketplace(host))
    print("[구버전 경로 이전]")
    for line in migrate_legacy_paths(host):
        print(line)
    print("[pre-commit 점검]")
    for line in check_precommit(plugin, host):
        print(line)
    print("[gitignore]")
    for line in append_gitignore(host):
        print(line)
    for line in untrack_vdev_evidence(host):
        print(line)
    for line in unignore_shared(host):
        print(line)
    for line in prune_stale_gitignore(host):
        print(line)
    print("[계약 테스트 워크플로우]")
    for line in render_workflow(host, plugin):
        print(line)
    print("[버저닝 워크플로우]")
    for line in render_versioning_workflows(host, plugin):
        print(line)
    print("[config 슬롯 점검]")
    for line in report_missing_config_slots(host, plugin):
        print(line)
    print("[자동 업데이트 인증]")
    for line in detect_autoupdate_auth():
        print(line)
    print("[마이그레이션]")
    for line in apply_migrations(host, plugin):
        print(line)
    print("기계적 셋업 완료.")


def run_uninstall(host: Path) -> None:
    print(f"vway-kit 정리(uninstall) — host={host}")
    print("[커밋 게이트 해제]")
    print(unregister_gate(host))
    print("[마켓 등록 해제]")
    print(unregister_marketplace(host))
    print("[gitignore 정리]")
    print(remove_gitignore_lines(host))
    print("[CLAUDE.md teams 블록 제거]")
    print(remove_claude_md_block(host))
    print("[vway-kit 디렉터리 삭제]")
    print(remove_vway_dir(host))
    print("[남는 항목 — 수동 처리 안내]")
    print("  - .pre-commit-config.yaml 의 teams-notify-push 훅/정적분석 훅은 자동 제거하지")
    print("    않습니다(주석·팀 커스텀 보존). 필요 시 직접 제거하세요.")
    print("  - .github/workflows/api-contract.yml 은 자동 삭제하지 않습니다(팀 커스텀 보존).")
    print("    계약 테스트를 끄려면 직접 제거하세요.")
    print("  - 설치했던 git 훅 비활성화:")
    print("      pre-commit uninstall --hook-type pre-commit --hook-type commit-msg \\")
    print("        --hook-type pre-push")
    print("  - .claude/vway-kit/ 의 git 추적 파일 삭제는 커밋해야 반영됩니다.")
    print("정리 완료.")


def main() -> None:
    force_utf8_io()
    parser = argparse.ArgumentParser(description="vdev-init 기계적 셋업 / --uninstall 정리")
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="호스트에서 vway-kit 배선을 제거(setup 의 역연산)",
    )
    args = parser.parse_args()
    host = host_root()
    if args.uninstall:
        run_uninstall(host)
    else:
        run_setup(host, plugin_root())


if __name__ == "__main__":
    main()
