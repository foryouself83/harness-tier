# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

이 repo는 **Claude Code 플러그인 자체**다(소비자가 아님). 사용법은 [README.md](README.md)·[USAGE.md](USAGE.md).
컴포넌트 작성 스펙(command/agent/hook/skill frontmatter)은 모델 지식이 아니라 공식 문서를 SSOT로 확인할 것:
[plugins-reference](https://code.claude.com/docs/en/plugins-reference.md) · [hooks](https://code.claude.com/docs/en/hooks.md) · [skills](https://code.claude.com/docs/en/skills.md).

## Commands

게이트 스크립트는 Python, 도구는 `uv`로 실행한다.

```bash
uv sync                                                  # 의존성 설치
uv run pytest                                            # 전체 테스트
uv run pytest tests/test_vdev_gate_check.py::<name>      # 단일 테스트
uv run ruff check && uv run ruff format --check          # 린트 + 포맷 검사
uv run pre-commit run --all-files                        # 정적 분석 전체
```

`*.sh` 수정 시 ShellCheck로 검증(훅 런타임이 Windows라 버그가 FAIL-OPEN으로 숨음 — Invariants 참조).

## Folder structure

`agents/`·`hooks/hooks.json`·`skills/`는 매니페스트에 경로 미선언 — **기본 위치에서 자동 발견**된다(컴포넌트 추가 = 파일만 추가).

```text
.claude-plugin/
  plugin.json              플러그인 매니페스트 (최소 — name/description/version/author)
  marketplace.json         마켓플레이스 매니페스트 (vway-kit 자기 노출; plugin source=github+불변 sha 핀)
agents/     harness-researcher · harness-code-analyzer · harness-critic   (하네스 리서치/분석/비판)
hooks/      hooks.json (SessionStart 룰주입 + Notification) · inject-risk-tiers.sh
skills/     vdev · vdev-init · vdev-uninstall · task-import · task-sync · harness-init · doc-sync · harness-authoring · harness-insight
            playwright-scaffold · integration · performance   (/슬래시 = 스킬)
rules/      risk-tiers.md  ← 티어 분류·커밋 규율의 SSOT (자동로드 X, 훅이 주입)
            harness-rules.md  ← 하네스 생성 규율 SSOT (harness-init 스킬이 로드)
scripts/    vdev_gate_check.py · precommit-runner.sh · teams_alert.py · notify-push.sh
            check-deps.sh(의존성 점검·안내) · vdev_init_setup.py(vdev-init 셋업/재실행 + --uninstall 정리)
            handoff_resolve.py(task-sync handoff 종류 해석) · harness_scaffold.py(harness-init 스캐폴드 생성) · teamer_api.py(keyring 자격증명 + Teamer API 클라이언트)
            harness_insight.py(harness-insight 트랜스크립트 집계 — 프로젝트 비종속, 임시 txt 출력)
github/     api-contract.workflow.example.yml   계약 테스트 SOURCE(/vdev-init 이 vdev-config.contract_test 로 렌더링)
            release.python-semantic-release.workflow.example.yml · release.semantic-release.workflow.example.yml
            branch-naming.workflow.example.yml · entropy-check.workflow.example.yml
            (위 4종은 /vdev-init 이 vdev-config.versioning 으로 렌더링 — release 는 release_tool 로 택1)
.github/    workflows/(release·branch-naming·entropy-check — vway-kit 자체 CI) · scripts/pin-marketplace-sha.py(릴리스 시 marketplace sha 핀)
vdev-tiers.yaml            tier→gates 정책 (플러그인 소유, 불변)
vdev-config.example.yaml   호스트 환경값 슬롯 (실파일은 호스트 .claude/vway-kit/config/vdev-config.yaml, 팀 공유·git추적)
tests/      test_vdev_gate_check.py · test_vdev_init_setup.py · test_handoff_resolve.py · test_harness_scaffold.py · test_harness_insight.py
```

## Architecture (must-know)

- **플러그인은 호스트 밖(캐시)에 설치된다 → 이중 경로.** `${CLAUDE_PLUGIN_ROOT}`=읽기(템플릿/정책), `${CLAUDE_PROJECT_DIR}`=쓰기(호스트 설정/증거). **플러그인 디렉터리에 쓰지 말 것.**
- **호스트 쓰기는 `${CLAUDE_PROJECT_DIR}/.claude/vway-kit/` 아래 용도별로 모은다**(루트 분산 금지): `scripts/`(복사 게이트 스크립트, 플러그인 소유·git추적) · `config/`(vdev-config.yaml(팀 공유·git추적 — 같은 저장소 개발자가 동일 설정 사용)·vdev-tiers.yaml(tier→gates 정책 — 플러그인 소유·매 설치 덮어씀·편집 금지)·teamer_account.md(평문 — setup 이전 후 삭제, 자격증명은 keyring 소유)·웹훅, 호스트 소유) · `.vdev/`(게이트 증거, gitignored). 예외는 외부 도구가 위치를 강제하는 `.gitignore`(git)·`.pre-commit-config.yaml`(pre-commit)·`.claude/settings.json`(Claude Code)·`.github/workflows/`(GitHub Actions)뿐.
- **커밋 게이트는 호스트 `settings.json`에 등록된다**(플러그인 hooks.json 아님). deny 강제 신뢰성 + `${CLAUDE_PLUGIN_ROOT}` 미해석 때문. `/vdev-init`이 게이트 스크립트를 호스트 `.claude/vway-kit/scripts/`로, 정책 `vdev-tiers.yaml`을 `.claude/vway-kit/config/`로 **복사**한다.
- **스크립트 전파는 단방향**: `scripts/`·`vdev-tiers.yaml`(SOURCE·SSOT) → 캐시(재설치) → `<host>/.claude/vway-kit/scripts/`(게이트 스크립트)·`config/vdev-tiers.yaml`(정책 실행 사본). 고칠 땐 SOURCE만, 호스트 사본 직접 수정 금지(재설치 시 덮어써짐). 플러그인 갱신 후 호스트 사본 동기화는 `/vdev-init` 재실행(config 무손상), 호스트 정리는 `/vdev-uninstall`.
- **정책 vs 환경값**: `vdev-tiers.yaml`(tier→gates, 불변·플러그인 소유·편집 금지) vs `vdev-config.yaml`(브랜치·modules·teamer, 호스트 소유·팀 공유·git추적, 사람이 편집). 둘 다 `.claude/vway-kit/config/`에 위치하나 소유권이 다르다.
- **티어 규율 SSOT = `rules/risk-tiers.md`** — `vdev.md`·`vdev-tiers.yaml`·게이트가 여기 defer. 규율 변경은 여기서, 어긋난 쪽을 맞춘다.
- **버전·릴리스(강결합)**: vway-kit 배포는 plugin.json `version` 이 업데이트를 게이팅한다(Claude Code Explicit-version — 매니페스트에 version 이 있으면 sha 변경만으론 전파 안 되고 version bump 시에만 재설치). `.github/workflows/release.yml`(python-semantic-release)이 main/stage push 의 Conventional Commits(feat/fix)를 파싱해 pyproject+plugin.json version 을 bump·tag(`vX.Y.Z`)하고, main 은 `pin-marketplace-sha.py` 로 marketplace `source.sha` 를 릴리스 커밋에 **불변 핀**(pin-to-parent — 태그 ref 금지, 공급망 무결성)한다. 그래서 소비자 동작에 영향 주는 `.md`(rules/skills) 변경은 `docs` 가 아니라 `feat`/`fix` 로 커밋해야 전파된다(risk-tiers Commit Discipline). 브랜치: `feature/*` → dev → stage → main. (버전별 마이그레이션은 vdev-init/harness-init 가 호스트 적용 버전 기준으로 수행 — 별도 작업.)
- **플러그인 `rules/`는 자동로드 안 됨** → `hooks/inject-risk-tiers.sh`가 SessionStart에 `additionalContext`로 주입(호스트별 출력 키 다름).
- **검증 3레이어**(독립): 정적 분석·위생 = 호스트 `.pre-commit-config.yaml`(git-native — gitlint(commit-msg)·teams-notify-push(pre-push)·언어무관 위생; 모듈별 lint/static/import_lint/test 는 레이어2로 이동) / vdev 게이트 = `precommit-runner.sh`(**Claude 세션 커밋에만** — PreToolUse, `git commit`만 self-filter; 터미널 직접 커밋·CI 는 거치지 않음 — 미분류 차단 + tier 의 `gates`(`vdev-tiers.yaml`)에 켜진 항목만 실행: `precommit`=**변경 모듈의 lint/static/import_lint/test(모든 커밋)**, `security-scan`=staging/release 승격 시 전체 모듈 `security` 스캔 — 둘 다 RUNTIME_GATES 라 마커 없이 훅이 직접 실행하고, 해당 tier 의 `gates` 에서 빼면 그 검사만 꺼진다) / **계약 테스트 = `.github/workflows/api-contract.yml`(GitHub Actions, 협업/promotion 브랜치만 — schemathesis, `/vdev-init`이 `vdev-config.contract_test`로 렌더링)**.

## Invariants (깨면 게이트가 조용히 무력화됨)

게이트 스크립트(`scripts/*`, `hooks/*.sh`) 수정 시 반드시 보존:

1. **FAIL-OPEN, 단 의존성 부재·미분류는 fail-CLOSED** — 전이적 내부 오류는 게이트를 막지 않고 통과시킨다(깨진 게이트가 커밋을 영구 차단하지 않게). **예외 1**: 필수 도구(`python3`≥3.8·`PyYAML`) 부재/구버전은 `precommit-runner.sh`가 **커밋을 차단**한다(조용한 미강제 방지; 프로젝트 언어 무관). python3 없이도 커밋을 탐지하려고 raw stdin을 폴백으로 grep한다. **예외 2**: 정책(`vdev-tiers.yaml`)·설정(`vdev-config.yaml`)이 정상 파싱되는데 `tier` 마커가 없는 **미분류 커밋**은 `vdev_gate_check`가 **차단**한다(`/vdev` 우회로 게이트가 조용히 무력화되는 것 방지). 단 판정 기준은 "파일 존재"가 아니라 "**파싱 성공**(=신뢰성 있게 작동)" — 정책/설정이 깨지면 내부 오류로 보고 fail-open 한다. (superpowers는 셸에서 감지 불가 → `/vdev`·`/vdev-init`에서 가드.)
2. **Windows 인코딩** — 훅 Python은 cp949 로캘. 한글 `print()`/UTF-8 `open()`이 인코딩 오류로 FAIL-OPEN되어 *차단해야 할 커밋을 통과*시킨다. `PYTHONUTF8=1`·`force_utf8_io()`·`encoding="utf-8"` 방어를 빠뜨리지 말 것.
3. **차단 = exit 2 + stderr 사유** (JSON `permissionDecision`도 같이 내되 실제 차단 수단은 exit 2).
4. **settings.json 게이트 훅에 `if` 필드 금지** — 빌드별로 훅 발화를 막음. 필터는 `precommit-runner.sh` stdin self-filter로.
5. **`/vdev-init` 멱등** — settings.json 훅·pre-commit id·.gitignore 라인 중복 추가 금지(match-then-skip).
6. **Teamer 자격증명은 keyring에서 스크립트가 읽는다** — 평문 파일·모델 컨텍스트·트랜스크립트에 id/pw/token 노출 금지(에러도 redact). `scripts/teamer_api.py`(stdlib + keyring)가 인증·검색·GET·PUT을 프로세스 내부에서 수행하고 최소 JSON만 출력한다. PUT은 multipart/form-data·UTF-8(**Python urllib**, curl/Node 아님), GET non-null colXX 전부 보존·status name→no 해석은 스크립트 내부. Teamer 번호는 `vdev-config.teamer`에서 읽어 인자로 넘긴다(하드코딩 폴백 금지). 자격증명 세팅은 사용자가 터미널에서 `teamer_api.py setup`(getpass)으로만 한다(AskUserQuestion 금지).
