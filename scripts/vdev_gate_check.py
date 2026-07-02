"""vdev-config 기반 게이트 검사 헬퍼.

호스트 저장소 경로는 CLAUDE_PROJECT_DIR 환경변수로만 접근하며,
내부 오류 시 게이트를 막지 않는다 (fail-open).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# 호스트 루트 해석·인코딩 방어·게이트 계약 상수(차단 exit code·런타임 게이트 키·티어
# 라벨)는 공용 SSOT(_vway_paths)에서 가져온다(중복 정의 금지 — rule-dry-constants).
# vdev_gate_check 는 호스트로 복사돼 직접 실행되거나(형제 import) 테스트에서 패키지로
# import 된다 — _vway_paths 모듈 docstring 의 양립 관용구 참조.
try:
    from _vway_paths import (
        BLOCK_EXIT_CODE,
        CONFIG_DIR,
        RELEASE_TIER,
        RUNTIME_GATES,
        STAGING_TIER,
        TIERS_FILENAME,
        config_path,
        force_utf8_io,
        host_root,
        vdev_dir,
    )
except ImportError:
    from scripts._vway_paths import (
        BLOCK_EXIT_CODE,
        CONFIG_DIR,
        RELEASE_TIER,
        RUNTIME_GATES,
        STAGING_TIER,
        TIERS_FILENAME,
        config_path,
        force_utf8_io,
        host_root,
        vdev_dir,
    )


def load_lifecycle_branches(config_path: Path) -> dict[str, str]:
    """vdev-config.yaml의 branches 섹션을 읽어 {브랜치명: 티어} 매핑을 반환한다.

    - staging 키 → "staging" 티어
    - production 키 → "release" 티어
    - 파일이 없거나 파싱 오류 시 {} 반환 (fail-open)
    """
    if not config_path.is_file():
        return {}
    try:
        import yaml

        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    branches = data.get("branches") or {}
    out: dict[str, str] = {}
    if staging := branches.get("staging"):
        out[str(staging)] = STAGING_TIER
    if production := branches.get("production"):
        out[str(production)] = RELEASE_TIER
    return out


def required_gates(tiers_path: Path, tier: str) -> list[str] | None:
    """vdev-tiers.yaml에서 특정 tier의 gates 목록을 반환한다.

    - tier가 없으면 None 반환
    - 파일이 없거나 파싱 오류 시 None 반환 (fail-open)
    """
    if not tiers_path.is_file():
        return None
    try:
        import yaml

        data = yaml.safe_load(tiers_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    node = (data.get("tiers") or {}).get(tier)
    return list(node.get("gates", [])) if node else None


def policy_parseable(tiers_path: Path) -> bool:
    """vdev-tiers.yaml 이 정상 로드되고 tiers 섹션을 가지는가(정책 신뢰성).

    미분류 fail-closed 차단은 게이트가 *정상 작동 중*일 때만 적용해야 한다(Invariant #1:
    깨진/부재 정책이 커밋을 영구 차단하지 않음). 파일 부재·파싱 실패·빈 tiers 는 모두
    "신뢰할 수 없음"으로 False — 차단 대신 FAIL-OPEN 으로 떨어진다.
    """
    if not tiers_path.is_file():
        return False
    try:
        import yaml

        data = yaml.safe_load(tiers_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return False
    return bool(data.get("tiers"))


def config_intact(config_path: Path) -> bool:
    """vdev-config.yaml 이 부재(정상)이거나 정상 로드되는가.

    부재는 정상이다(feature 작업·vdev-init 이전엔 config 가 없을 수 있다) → True.
    존재하는데 파싱 실패면 내부 오류 → False: lifecycle(staging/release) 판정이
    무력화된 상태이므로 promotion 커밋을 "미분류"로 오차단하지 않게 차단을 보류한다.
    """
    if not config_path.is_file():
        return True
    try:
        import yaml

        yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return True


def missing_gates(vdev_dir: Path, gates: list[str]) -> list[str]:
    """RUNTIME_GATES(훅이 직접 실행하는 게이트)를 제외하고 <gate>.done 이 없는 게이트."""
    return [g for g in gates if g not in RUNTIME_GATES and not (vdev_dir / f"{g}.done").is_file()]


def _current_branch(root: Path) -> str | None:
    """현재 git 브랜치명을 반환한다. 실패 시 None."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return None


def _resolve_context_tier(root: Path, vdev: Path, current: str | None) -> tuple[str | None, bool]:
    """현재 브랜치/.vdev tier 마커에서 적용할 티어 라벨을 해석한다.

    반환 ``(tier, is_lifecycle)``:
    - 라이프사이클 브랜치(stage/main)면 그 티어와 ``True``.
    - ``.vdev/tier`` 마커가 있고 현재 브랜치에 적용되면 그 티어와 ``False``.
    - 미분류(마커 없음)·다른 브랜치의 마커면 ``(None, False)``.

    1단계 증거 검사(main)와 2단계 모듈 사전검사(module_commands)가 공유하는
    유일한 티어 해석 지점이다(중복 정의 금지 — rule-dry-constants).
    """
    lifecycle = load_lifecycle_branches(config_path(root)).get(current or "")
    if lifecycle:
        return lifecycle, True
    tier_file = vdev / "tier"
    if not tier_file.is_file():
        return None, False
    tier, _, branch = tier_file.read_text(encoding="utf-8").strip().partition(":")
    tier, branch = tier.strip().lower(), branch.strip()
    if branch and current is not None and current != branch:
        return None, False
    return tier, False


def tiers_path(root: Path) -> Path:
    """vdev-tiers.yaml(플러그인 정책)의 위치를 해석한다.

    정책 파일은 게이트 스크립트와 함께 호스트로 배포되므로 다음 순서로 찾는다:
    1. ``CLAUDE_PLUGIN_ROOT/vdev-tiers.yaml`` — 플러그인 hook 으로 직접 실행될 때
    2. config 디렉터리의 ``vdev-tiers.yaml`` — ``.claude/vway-kit/config/`` 로
       복사된 경우(게이트 스크립트는 형제 ``scripts/`` 에 있으므로 그 형제
       디렉터리 config/ 를 __file__ 기준으로 가리킨다 — host_root() 불안정성에
       영향받지 않는다).
    3. 호스트 루트 ``vdev-tiers.yaml`` — 폴백(개발/테스트).
    """
    plugin = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin and (p := Path(plugin) / TIERS_FILENAME).is_file():
        return p
    config_copy = Path(__file__).resolve().parent.parent / Path(CONFIG_DIR).name / TIERS_FILENAME
    if config_copy.is_file():
        return config_copy
    return root / TIERS_FILENAME


def _changed_files(root: Path) -> list[str]:
    """커밋 대상 변경 파일 목록. staged(--cached) 우선, 비면 working tree(HEAD diff)
    폴백(`git commit -a` 케이스). git 실패/변경 없음은 [] (FAIL-OPEN)."""
    for args in (["diff", "--cached", "--name-only"], ["diff", "HEAD", "--name-only"]):
        try:
            out = subprocess.run(
                ["git", *args],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
        except Exception:
            continue
        files = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
        if files:
            return files
    return []


def _match_modules(changed: list[str], modules: list[dict]) -> tuple[list[dict], list[str]]:
    """변경 파일을 modules[].path 와 prefix 매칭한다.

    반환 ``(매칭 모듈(순서 보존·중복 제거), 미커버 파일)``. 빈 path("")는 전체 매칭
    (단일스택 단일모듈). 첫 매칭 모듈에 귀속하고, 어떤 path 에도 안 걸리면 미커버.
    """
    matched: list[dict] = []
    seen: set[str] = set()
    uncovered: list[str] = []
    for f in changed:
        hit: dict | None = None
        for mod in modules:
            path = str(mod.get("path") or "")
            if path == "" or f.startswith(path):
                hit = mod
                break
        if hit is None:
            uncovered.append(f)
            continue
        key = str(hit.get("name") or hit.get("path") or "")
        if key not in seen:
            seen.add(key)
            matched.append(hit)
    return matched, uncovered


def _check_cmds(mod: dict, *, security: bool) -> list[str]:
    """모듈 checks 명령. security=True 면 security 키만, False 면 security 제외 전부
    (config 작성 순서 보존, 빈 명령 skip)."""
    checks = mod.get("checks") or {}
    if security:
        cmd = checks.get("security")
        return [str(cmd)] if cmd else []
    return [str(v) for k, v in checks.items() if k != "security" and v]


def module_commands(
    root: Path, tier: str | None, gates: list[str] | None
) -> tuple[list[str], list[str]]:
    """gates 리스트가 켜진 항목만 모듈 사전검사 명령을 만든다(tiers.yaml gates 가 SSOT
    — tier 라벨로 하드코딩하지 않는다. gates 에서 빼면 그 검사가 꺼진다).

    - docs/None tier, 또는 gates 비어있음 → ([], [])
    - "precommit" in gates → 변경 모듈의 non-security checks(+ 미커버 리포트)
    - "security-scan" in gates → 전체 모듈 security(승격 시)
    config 파싱 실패·modules 부재는 ([], []) (FAIL-OPEN — Invariant #1)."""
    if tier is None or tier == "docs" or not gates:
        return [], []
    cfg = config_path(root)
    if not cfg.is_file():
        return [], []
    try:
        import yaml

        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except Exception:
        return [], []
    modules = data.get("modules") or []
    if not modules:
        return [], []
    cmds: list[str] = []
    report: list[str] = []
    if "precommit" in gates:
        matched, uncovered = _match_modules(_changed_files(root), modules)
        for mod in matched:
            cmds += _check_cmds(mod, security=False)
        if uncovered:
            report.append(
                "다음 파일은 모듈 미커버라 사전검사 생략 — 새 모듈이면 "
                "vdev-config.modules[] 에 등록하세요:"
            )
            report += [f"  - {f}" for f in uncovered]
    if "security-scan" in gates:
        for mod in modules:
            cmds += _check_cmds(mod, security=True)
    return cmds, report


def main() -> None:
    """vdev 게이트 검사 진입점. 게이트 미충족 시 exit(BLOCK_EXIT_CODE), 통과 시 exit(0)."""
    force_utf8_io()
    root = host_root()
    # 호스트 측 vway-kit 산출물은 모두 .claude/vway-kit/ 한 곳에 모인다
    # (config·증거·복사 스크립트). 경로 조립은 공용 헬퍼로 단일화한다.
    vdev = vdev_dir(root)
    tiers = tiers_path(root)
    current = _current_branch(root)

    tier, is_lifecycle = _resolve_context_tier(root, vdev, current)
    if tier is None:
        # tier 미해석을 두 원인으로 가른다(같은 None 을 반대로 해석):
        #  - 정책(vdev-tiers.yaml)·설정(vdev-config.yaml)이 정상 작동 + tier 마커 파일
        #    자체 부재 = vdev 미진입(미분류) → FAIL-CLOSED 차단. vdev 를 우회한 커밋이
        #    게이트를 통째로 건너뛰지 못하게 한다. 강제가 불필요하면 사용자가
        #    /vdev-uninstall 로 게이트 자체를 떼면 된다(escape hatch 를 코드에 두지 않는다
        #    — 두면 그 우회로를 모델이 스스로 쓸 수 있다).
        #  - 정책 부재/파싱 실패, config 파싱 실패(설치/환경 불확정·내부 오류), 또는
        #    마커가 다른 브랜치(branch-bound stale) → FAIL-OPEN. Invariant #1(깨진/부재
        #    게이트가 커밋을 영구 차단하지 않음)·branch-bound(stale 마커가 무관한 브랜치
        #    작업을 막지 않음) 보존. "파일 존재"가 아니라 "신뢰성 있게 작동"이 기준이다.
        if (
            policy_parseable(tiers)
            and config_intact(config_path(root))
            and not (vdev / "tier").is_file()
        ):
            print(
                "vdev 미진입: 분류되지 않은 커밋입니다. /vdev 로 작업을 분류한 뒤 "
                "커밋하세요(강제가 불필요하면 /vdev-uninstall)."
            )
            sys.exit(BLOCK_EXIT_CODE)
        sys.exit(0)
    gates = required_gates(tiers, tier)
    if gates is None:  # 알 수 없는 티어 → FAIL-OPEN
        sys.exit(0)
    miss = missing_gates(vdev, gates)
    if miss:
        if is_lifecycle:
            print(f"{tier} 게이트 (브랜치 '{current}'): {miss} 증거가 필요합니다.")
        else:
            print(f"vdev 게이트: '{tier}' 티어는 {miss} 증거가 필요합니다.")
        sys.exit(BLOCK_EXIT_CODE)
    sys.exit(0)


def module_commands_output() -> None:
    """현재 tier 의 gates 로 켜진 모듈 사전검사 명령을 stdout(줄단위), 미커버 리포트를
    stderr 로 낸다.

    gates 에 precommit 있으면 변경 모듈 non-security, security-scan 있으면 +전체 모듈
    security(tiers.yaml gates 리스트가 SSOT — 여기서 제거하면 해당 검사가 꺼진다).
    판정 실패는 빈 출력(FAIL-OPEN). precommit-runner.sh 가 stdout 명령을 실행하고
    stderr 리포트는 그대로 사용자에게 노출한다."""
    force_utf8_io()
    root = host_root()
    try:
        tier, _ = _resolve_context_tier(root, vdev_dir(root), _current_branch(root))
        gates = required_gates(tiers_path(root), tier) if tier else None
    except Exception:
        return  # FAIL-OPEN
    cmds, report = module_commands(root, tier, gates)
    for line in report:
        print(line, file=sys.stderr)
    for cmd in cmds:
        print(cmd)


if __name__ == "__main__":
    try:
        if "--module-commands" in sys.argv:
            module_commands_output()
        else:
            main()
    except SystemExit:
        raise
    except Exception as exc:  # FAIL-OPEN
        print(f"[vdev-gate] unexpected error, allowing: {exc}", file=sys.stderr)
        sys.exit(0)
