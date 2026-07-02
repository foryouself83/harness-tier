#!/usr/bin/env bash
# vway-kit 의존성 점검 — **검증만 하고 설치는 하지 않는다(안내만)**. 누락 시 설치
# 방법을 출력한다. 자동 설치/전역 변경을 하지 않는 이유: 권한·네트워크·환경 차이로
# 인한 사고를 피하고, 무엇을 설치하는지 사용자가 통제하게 하기 위함.
#
# /vdev-init Step 0 가 호출하거나 사람/CI 가 직접 실행한다. 종료코드: 필수
# (셸·python3≥3.8·PyYAML) 충족 시 0, 미충족 시 1 → vdev-init 이 멈춰 안내한다.
# pre-commit·superpowers 는 안내만 하며 종료코드에 영향을 주지 않는다.
set -uo pipefail
export PYTHONUTF8=1  # 자식 python 출력 인코딩 방어(이 스크립트는 한글을 bash 로만 출력)

ok()   { printf '  [OK]   %s\n' "$1"; }
need() { printf '  [필요] %s\n' "$1"; }

echo "vway-kit 의존성 점검 (검증만 — 자동 설치하지 않음)"
missing_required=0

# 0) 셸 런타임 — bash + coreutils. 게이트 훅은 bash 로 실행되고 timeout/cat 등으로
#    stdin(커밋 명령)을 읽는다. coreutils 가 없으면 게이트가 stdin 을 못 읽어 self-filter
#    가 빈값이 되어 **조용히 통과(fail-open)**한다 — 게이트가 스스로 못 잡는 구멍이라
#    여기서 미리 점검한다. (이 스크립트가 도는 것 자체가 bash 존재의 증거다.)
_missing_utils=""
for _u in timeout cat grep sed awk; do
  command -v "$_u" >/dev/null 2>&1 || _missing_utils="$_missing_utils $_u"
done
if [ -n "$_missing_utils" ]; then
  need "coreutils 누락:$_missing_utils — 게이트가 stdin 을 못 읽어 조용히 통과(fail-open)할 수 있음."
  need "    Windows: Git for Windows(git-bash) 재설치 | Linux: coreutils 패키지 | macOS: 기본 제공"
  missing_required=1
else
  ok "셸 런타임 (bash + coreutils)"
fi

# 1) python3 ≥ 3.8 (필수) — 게이트 하니스 런타임. 자동 설치 불가.
# 이 파일이 floor(3, 8)·PyYAML 설치 명령의 값 SSOT 다(부트스트랩 셸이라 _vway_paths 로
# 못 옮기고 self-contained 라 precommit-runner.sh 와 코드 공유 불가 — 값을 양쪽 동기화).
if ! command -v python3 >/dev/null 2>&1; then
  need "python3 미설치 — python 3.8+ 설치 필요:"
  need "    macOS: brew install python | Windows: https://www.python.org/downloads/ | Linux: 배포판 패키지"
  missing_required=1
elif ! python3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)"; then
  need "python 3.8+ 필요 (현재 $(python3 -V 2>&1)) — 업그레이드 후 재실행"
  missing_required=1
else
  ok "python3 $(python3 -V 2>&1 | awk '{print $2}')"
fi

# 2) PyYAML (필수) — vdev_gate_check.py 가 사용. 안내만(설치 안 함).
if command -v python3 >/dev/null 2>&1 && python3 -c "import yaml" >/dev/null 2>&1; then
  ok "PyYAML"
else
  need "PyYAML 미설치 — 설치: python3 -m pip install pyyaml"
  need "    (게이트 훅이 부르는 bare python3 환경에 설치 — uv add 는 venv 라 안 보일 수 있음)"
  missing_required=1
fi

# 3) pre-commit (권장) — 정적 분석/커밋 메시지 게이트. 안내만.
if command -v pre-commit >/dev/null 2>&1 || python3 -c "import pre_commit" >/dev/null 2>&1; then
  ok "pre-commit"
else
  need "pre-commit 미설치(권장) — 설치: python3 -m pip install pre-commit"
  need "    설치 후: pre-commit install --hook-type commit-msg --hook-type pre-push"
fi

# 3.5) keyring (Teamer 연동 시 필요) — task-import/task-sync 자격증명 저장소. 안내만.
if command -v python3 >/dev/null 2>&1 && python3 -c "import keyring" >/dev/null 2>&1; then
  ok "keyring (Teamer 연동)"
else
  need "keyring 미설치(Teamer 연동 시 필요) — 설치: python3 -m pip install keyring"
  need "    (bare python3 환경에 설치 — uv venv 아님. 설치 후 python3 .../teamer_api.py setup)"
fi

# 4) superpowers 플러그인 (Standard+ 필수) — Claude 레이어라 셸 감지 불가. 안내만.
need "superpowers 플러그인 (Standard+ 작업 필수) — Claude 에서 마켓 등록 후 설치:"
need "    /plugin marketplace add anthropics/claude-code   (또는 해당 마켓)"
need "    /plugin install superpowers@claude-plugins-official"
need "    (미설치 시 /vdev 가 Dev+ 에서 중단한다)"

if [ "$missing_required" -eq 1 ]; then
  echo "필수 의존성(셸·python3≥3.8·PyYAML) 미충족 — 위 안내대로 설치 후 다시 실행하세요."
  exit 1
fi
echo "필수 의존성 충족. (pre-commit·superpowers 는 위 안내 참고)"
