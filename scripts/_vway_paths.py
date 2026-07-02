"""vway-kit 게이트/스크립트 공용 상수·경로 헬퍼 (매직값 SSOT).

이 repo 의 [rule-dry-constants] 규율(매직 넘버·문자열은 한 곳에서 정의)을 게이트
스크립트 자신에게 적용하는 단일 출처다. 경로 세그먼트·파일명·차단 exit code·런타임
게이트 키·라이프사이클 티어 라벨을 여기서만 정의하고, 다른 스크립트는 import 한다.

**왜 모듈인가(import 양립)**: 플러그인 스크립트는 호스트로 *단일 파일씩* 복사되어
실행되므로(`from vdev_init_setup import ...` 할 동료가 없다) 이 모듈을 vdev_init_setup
의 COPY_FILES 에 포함시켜 게이트 스크립트와 함께 복사한다. 그러면 두 실행 모드 모두에서
import 가 성립한다:
  - 직접 실행(`python3 .../scripts/vdev_gate_check.py`): sys.path[0]=scripts/ →
    형제 `import _vway_paths` 성립.
  - 패키지 import(pytest 의 `from scripts.vdev_gate_check import ...`):
    `from scripts._vway_paths import ...` 성립.
호출측은 아래 관용구로 둘을 양립시킨다(부트스트랩이라 추상화 불가):

    try:
        from _vway_paths import host_root, force_utf8_io  # 직접 실행(형제)
    except ImportError:
        from scripts._vway_paths import host_root, force_utf8_io  # 패키지(테스트/개발)

**외부 계약값은 여기 두지 않는다**: 훅 이벤트명(PreToolUse/SessionStart)·환경변수
키(CLAUDE_PROJECT_DIR 등)는 Claude Code 런타임/SDK 가 강제하므로 키 문자열 자체는
불변이고 JSON/셸과 교차 공유가 불가능하다. 단 그 키를 *읽는 폴백 헬퍼*(host_root/
plugin_root)는 변종이 갈라지기 쉬워 여기로 모은다.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# ── 호스트 쓰기 루트 아래 경로 세그먼트(루트 기준 상대경로 문자열) ──────────────
# CLAUDE.md: 모든 호스트 쓰기는 .claude/vway-kit/ 한 곳에 모은다. vdev_init_setup 이
# `host / SCRIPTS_DIR` 처럼 호스트 루트와 join 하므로 문자열 상대경로로 노출한다.
VWAY_DIR = ".claude/vway-kit"  # 호스트 측 산출물 루트
SCRIPTS_DIR = f"{VWAY_DIR}/scripts"  # 복사 게이트 스크립트 (플러그인 소유·git추적)
CONFIG_DIR = f"{VWAY_DIR}/config"  # vdev-config·vdev-tiers(정책)·계정·웹훅
VDEV_DIR = f"{VWAY_DIR}/.vdev"  # 게이트 증거 (gitignored)

# ── config 디렉터리 하위 파일명 ────────────────────────────────────────────────
# 둘 다 config/ 에 위치하나 소유권이 다르다: vdev-config 는 호스트 환경값(사람이 편집),
# vdev-tiers 는 플러그인 정책(tier→gates, 불변·SSOT — config/ 에 있으나 편집 금지).
CONFIG_FILENAME = "vdev-config.yaml"  # 호스트 환경값(브랜치·modules·teamer·handoff)
TIERS_FILENAME = "vdev-tiers.yaml"  # 플러그인 정책(tier→gates, 불변·SSOT)

# ── 게이트 계약 상수 ───────────────────────────────────────────────────────────
# Invariant #3: PreToolUse 차단은 exit 2 가 실제 차단 수단. 생산자(vdev_gate_check)는
# 이 상수로 차단하고, 소비자(precommit-runner.sh)·테스트는 같은 값을 byte-match 한다.
BLOCK_EXIT_CODE = 2
# 마커 없이 훅이 직접 실행하는 런타임 게이트 집합 — vdev_gate_check 의 .done 검사에서
# 제외한다. vdev-tiers.yaml gates 리스트의 동일 키와 정확히 일치해야 한다(desync 시
# missing_gates 가 해당 게이트를 미충족으로 잘못 보고함 — rename 시 동기화 필수).
# gates 리스트가 실제 스위치다: module_commands 가 하드코딩된 tier 분기 대신 이 키의
# 멤버십으로 실행 여부를 가른다 — gates 에서 빼면 그 검사가 꺼진다.
# - precommit: precommit-runner.sh 가 직접 실행(변경 모듈 lint/static/import_lint/test, 매 커밋).
# - security-scan: precommit-runner.sh 가 직접 실행(staging/release 승격 시 전체 모듈 security).
RUNTIME_GATES = ("precommit", "security-scan")
# 라이프사이클 브랜치 → 티어 라벨. vdev-tiers.yaml tiers: 키와 byte-match 해야 게이트가
# 강제된다(desync 시 required_gates 가 None → FAIL-OPEN 으로 게이트 silent skip).
STAGING_TIER = "staging"
RELEASE_TIER = "release"


# ── 호스트 루트 기준 절대 경로(Path) 헬퍼 ──────────────────────────────────────
def vway_dir(root: Path) -> Path:
    """host_root 아래 .claude/vway-kit/ 절대 경로."""
    return root / ".claude" / "vway-kit"


def config_dir(root: Path) -> Path:
    """.claude/vway-kit/config/ — 호스트 소유 설정(vdev-config·웹훅·계정)."""
    return vway_dir(root) / "config"


def vdev_dir(root: Path) -> Path:
    """.claude/vway-kit/.vdev/ — 게이트 증거(<gate>.done·tier 마커)."""
    return vway_dir(root) / ".vdev"


def config_path(root: Path) -> Path:
    """.claude/vway-kit/config/vdev-config.yaml — 호스트 환경값 설정 파일."""
    return config_dir(root) / CONFIG_FILENAME


# ── 환경변수 폴백 헬퍼(키 자체는 외부 계약·불변, 폴백 로직만 단일화) ────────────
def host_root() -> Path:
    """호스트 저장소 루트. CLAUDE_PROJECT_DIR → git toplevel → .claude 마커 역산 → cwd.

    가장 견고한 폴백을 표준으로 둔다(이전 teams_alert._host_root). CLAUDE_PROJECT_DIR
    은 훅 실행 시에만 자동 주입되고 pre-push·수동 호출엔 비어 있을 수 있어, git
    toplevel 로 폴백하고 git 마저 실패하면 호스트 사본 위치(.claude/vway-kit/scripts/)
    에서 `.claude` 의 부모를 역산한다(고정 인덱스 대신 마커 탐색 — 설치 깊이 무관).
    마커가 없으면(SOURCE/standalone) cwd 로 떨어진다.
    """
    env = os.environ.get("CLAUDE_PROJECT_DIR")
    if env:
        return Path(env).resolve()
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            timeout=3,
        )
        top = out.stdout.strip()
        if top:
            return Path(top)
    except Exception:
        pass
    here = Path(__file__).resolve()
    for parent in here.parents:
        if parent.name == ".claude":
            return parent.parent
    return Path.cwd()


def plugin_root() -> Path:
    """플러그인 루트. CLAUDE_PLUGIN_ROOT 우선, 없으면 이 스크립트의 상위(scripts/..)."""
    env = os.environ.get("CLAUDE_PLUGIN_ROOT")
    return Path(env) if env else Path(__file__).resolve().parent.parent


def force_utf8_io() -> None:
    """stdout/stderr 를 UTF-8 로 재구성한다(Invariant #2).

    Windows 훅 환경(cp1252/cp949)에서 한글 사유 print() 가 UnicodeEncodeError 로
    깨지면 fail-open 되어 게이트가 무력화된다. PYTHONUTF8 도 설정해 자식 python
    프로세스까지 UTF-8 을 상속시킨다(standalone 호출 대비).
    """
    os.environ.setdefault("PYTHONUTF8", "1")
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            try:
                reconfigure(encoding="utf-8")
            except (ValueError, OSError):  # 이미 닫혔거나 재구성 불가 → 무시
                pass
