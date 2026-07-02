#!/usr/bin/env bash
# harness-tier dependency check — **verifies only, never installs (guidance only)**. On missing
# deps, prints how to install them. Why it does not auto-install / make global changes: to avoid
# accidents caused by permission/network/environment differences, and to let the user control what gets installed.
#
# Called by /flow-init Step 0, or run directly by a human/CI. Exit code: 0 when the required
# (shell·python3≥3.8·PyYAML) deps are met, 1 when unmet → flow-init halts and shows guidance.
# pre-commit·superpowers are guidance-only and do not affect the exit code.
set -uo pipefail
export PYTHONUTF8=1  # guard child python output encoding (this script prints Korean via bash only)

ok()   { printf '  [OK]   %s\n' "$1"; }
need() { printf '  [필요] %s\n' "$1"; }

echo "harness-tier 의존성 점검 (검증만 — 자동 설치하지 않음)"
missing_required=0

# 0) shell runtime — bash + coreutils. The gate hook runs under bash and reads stdin (the
#    commit command) via timeout/cat etc. Without coreutils the gate cannot read stdin, the
#    self-filter becomes empty and it **silently passes (fail-open)** — a hole the gate cannot catch
#    itself, so we check it here in advance. (This script running at all is proof bash exists.)
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

# 1) python3 ≥ 3.8 (required) — the gate harness runtime. Cannot auto-install.
# This file is the value SSOT for floor(3, 8) / the PyYAML install command (being a bootstrap shell it
# cannot be moved into _harness_paths, and being self-contained it cannot share code with
# precommit-runner.sh — keep the values synced on both sides).
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

# 2) PyYAML (required) — used by flow_gate_check.py. Guidance only (does not install).
if command -v python3 >/dev/null 2>&1 && python3 -c "import yaml" >/dev/null 2>&1; then
  ok "PyYAML"
else
  need "PyYAML 미설치 — 설치: python3 -m pip install pyyaml"
  need "    (게이트 훅이 부르는 bare python3 환경에 설치 — uv add 는 venv 라 안 보일 수 있음)"
  missing_required=1
fi

# 3) pre-commit (recommended) — static analysis / commit-message gate. Guidance only.
if command -v pre-commit >/dev/null 2>&1 || python3 -c "import pre_commit" >/dev/null 2>&1; then
  ok "pre-commit"
else
  need "pre-commit 미설치(권장) — 설치: python3 -m pip install pre-commit"
  need "    설치 후: pre-commit install --hook-type commit-msg --hook-type pre-push"
fi

# 4) superpowers plugin (required for Standard+) — a Claude layer, undetectable from the shell. Guidance only.
need "superpowers 플러그인 (Standard+ 작업 필수) — Claude 에서 마켓 등록 후 설치:"
need "    /plugin marketplace add anthropics/claude-code   (또는 해당 마켓)"
need "    /plugin install superpowers@claude-plugins-official"
need "    (미설치 시 /flow 가 Dev+ 에서 중단한다)"

if [ "$missing_required" -eq 1 ]; then
  echo "필수 의존성(셸·python3≥3.8·PyYAML) 미충족 — 위 안내대로 설치 후 다시 실행하세요."
  exit 1
fi
echo "필수 의존성 충족. (pre-commit·superpowers 는 위 안내 참고)"
