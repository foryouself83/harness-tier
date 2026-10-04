# 갱신과 제거

[English](update-and-removal.md) · **한국어** · [사용 설명서](../../USAGE.ko.md)

## `/flow-init` 재실행 — 플러그인 갱신 후 동기화

세션은 갱신이 기다리고 있을 때 알려줌. 시작 시 훅이 로드한 빌드와 마켓플레이스가
게시한 버전을 비교해, 마켓플레이스가 앞서 있으면 한 줄로 알림. 두 숫자 모두 로컬
파일에서 옴 — Claude Code 가 설치 캐시 옆에 두는 마켓플레이스 클론 — 그래서 네트워크
요청이 없고, 갱신되지 않은 클론은 아무 말도 하지 않음. 게시된 것보다 앞선 릴리스
후보를 돌리고 있으면 알림이 뜨지 않음.

`/plugin` 으로 갱신을 받은 뒤 `/flow-init` 을 다시 돌림. 갱신만으로는 저장소가
바뀌지 않음 — 게이트 스크립트와 정책은 사본이기 때문.

`flow-config.yaml` 이 있는 재실행:

1. **재동기화** — 묻지 않고 곧바로 게이트 스크립트와 `flow-tiers.yaml` 을 다시 복사하고
   게이트 등록을 복구함.
2. **백필** — 파일에 없는 슬롯을 플러그인 예시에서 채울지 제안함.
3. **재설정** — 무엇을 바꿀지 물음. 아무것도 고르지 않으면 재동기화로 남음. 설정과
   웹훅은 보존됨.
4. **재렌더** — 재설정에서 `enable` 플래그를 바꿨을 때만 함.

렌더링된 워크플로는 없을 때만 생성됨. `.github/workflows/` 에 이미 있는 워크플로는
보고만 되고 그대로 남음 — 새 플러그인의 템플릿 수정이 닿지 않으므로, 새 템플릿을
받으려면 파일을 지우고 `/flow-init` 을 다시 돌림. `.pre-commit-config.yaml` 도
마찬가지로 빠진 훅을 보고만 함. 예외는 `deploy.yml` 오케스트레이터와 `release.yml`
안의 관리 배포 블록 — 이 둘은 매 실행마다 다시 생성됨. 생성 헤더로 시작하지 않는
`deploy.yml` 은 호스트가 직접 쓴 것으로 보고, 보고만 하고 그대로 두며, `release.yml` 배선도
함께 보류함 — 호출 잡이 넘기는 `tag` 입력을 손으로 쓴 `deploy.yml` 이 받지 않을 수 있음.

## `/flow-uninstall` — 호스트 배선 제거

```text
/flow-uninstall   # 인자 없음; 확인 필요, 기본값은 아니오
```

**`/plugin uninstall` 전에** 실행함: 정리 도구가 플러그인 안에 있어, 플러그인을 먼저
지우면 [수동 정리](#플러그인을-이미-지운-뒤의-수동-정리) 로만 처리할 수 있음.

지우는 것:

- `.claude/settings.json` `hooks.PreToolUse` 의 커밋 게이트 — 다른 훅은 그대로 둠;
- `extraKnownMarketplaces` 의 `harness-tier` 항목 — 그 뒤 내 설정이 하나도 남지 않으면
  파일 자체도;
- `.gitignore` 의 harness-tier 줄 — 단 `.teams-webhooks.local.json` 은 남김: 어느 깊이에서나
  일치하므로 웹훅 비밀 파일이 커밋되는 것을 아직 막고 있을 수 있음;
- `CLAUDE.md` 의 `harness-tier:teams` 블록;
- `.codex/hooks.json` 의 Codex 게이트와 `AGENTS.md` 의 관리 지침 블록 — `harnesses` 에
  `codex` 가 아직 남아있는지와 무관함;
- `.claude/harness-tier/` — 스크립트, 설정, 증거, 팀 공유 `teams-webhooks.json` 포함
  두 웹훅 파일 전부, 그리고 `templates/` 의 설계 문서 템플릿과 거기 한 편집까지 — 남기려면
  먼저 밖으로 복사해 둠;
- `.claude/rules/harness-tier/` — 이전 `/flow-init` 이 복사해 뒀을 수 있는 플러그인 규칙.
  호스트 자체 규칙은 유지됨.

남기고 안내하는 것:

- `.pre-commit-config.yaml` — `teams-notify-push` 와 정적분석 훅은 그대로 둠;
- 설치된 git 훅 —
  `pre-commit uninstall --hook-type pre-commit --hook-type commit-msg --hook-type pre-push`;
- `.github/workflows/` — 아직 남은 워크플로를 짚어 줌: 삭제된 스크립트를 부르는 것(가드가
  있는 것과 실패하는 것)과 계속 도는 렌더본. 각각 어떻게 될지는 아래 수동 정리 5단계 참고;
- 삭제 자체 — `.claude/harness-tier/` 와 `.claude/rules/harness-tier/` 는 추적 대상이었고
  `.claude/settings.json` 도 그럴 수 있으므로 커밋해야 반영됨.

`커밋 게이트 훅이 settings.json 에 남았습니다` 로 끝나면, 지우지 못한 훅이 이제 없는 스크립트를 가리킴 — 아래 2단계(두 파일 다 다룸)로 직접 지움.
`Codex 커밋 게이트 훅이 .codex/hooks.json 에 남았습니다` 는 같은 문제를 그 파일에서 가리킴. 해석하지 못하는 `.codex/hooks.json` —
파싱되지 않거나 `hooks.PreToolUse` 가 목록이 아닌 파일 — 은 게이트 표식 문자열(`harness-tier` 와 `harness/codex/gate`)이 파일에
남아 있을 때만 `.codex/hooks.json 을 해석하지 못해 Codex 커밋 게이트 훅이 지워졌는지 확인하지 못했습니다` 로 끝남 — 지워졌다고 믿기 전에 2단계와 대조해
파일을 직접 확인함. 그 문자열이 없으면 사용자 자신의 파일로 보고
`[i] .codex/hooks.json 을 해석하지 못했지만 harness-tier 게이트 표식이 없어 건드리지 않았습니다.` 를 출력한 뒤 파일을 건드리지 않고
`정리 완료.` 로 끝남.

## 플러그인을 이미 지운 뒤의 수동 정리

1. `.claude/harness-tier/` 와 `.claude/rules/harness-tier/` 를 삭제함. 남은 규칙은 매 세션
   로드되며, 1단계에서 지운 검사기를 가리킴.
2. `.claude/settings.json` 에서 명령이
   `bash "${CLAUDE_PROJECT_DIR:-.}/.claude/harness-tier/scripts/precommit-runner.sh"` 인
   `hooks.PreToolUse` 훅만 — 그것만 — 지우고, `extraKnownMarketplaces.harness-tier` 도
   지움. `.codex/hooks.json` 에서는 `command` 에 `harness-tier` 와 `harness/codex/gate` 를
   둘 다 담은 `PreToolUse` 훅만 — 그것만 — 지움. 그 결과 항목의 `hooks` 목록이 비고 항목에
   `matcher` 와 `hooks` 외의 것이 없을 때만 그 `PreToolUse` 항목을 지움. 그 뒤 `hooks` 가
   비고 파일에 다른 최상위 키가 없을 때만 파일 자체를 지움 — 다른 훅은 그대로 둠.
3. `.gitignore` 에서 `.claude/harness-tier/.flow/`, `.claude/harness-tier/scripts/**/__pycache__/`
   를 지움. `.teams-webhooks.local.json` 은 저장소에 그런 파일이 남아 있는 동안 유지함.
4. `CLAUDE.md` 에서 `harness-tier:teams` 블록을 지움.
5. 렌더링된 워크플로마다 결정함:
   - `wiki-verify.yml`, `doc-style.yml`, `srs-verify.yml` — 스크립트가 없으면 각각
     건너뛰어 초록으로 남지만 아무것도 검증하지 못하고 push 마다 러너를 씀. 지움.
   - 릴리스 워크플로 — 모든 템플릿이 가드 없이
     `.claude/harness-tier/scripts/bump_version.py` 로 rc 버전을 계산하므로 staging push 는
     모두 실패함. stable 브랜치에서는 `gitversion`·`jreleaser`·`semantic-release` 도 실패함;
     `python-semantic-release` 는 가드가 있어 plain compute 로 넘어감; `cargo-release` 는
     finalize 가드를 건너뛰고 릴리스함. 워크플로를 지우거나 버전 단계를 손으로 바꿈.
   - `branch-naming.yml`(매 push), `entropy-check.yml`(주간), `api-contract.yml`,
     `unit-test.yml`, `e2e.yml`, `deploy.yml`, `deploy-*.yml` 은 우리 것을 전혀 참조하지
     않아 계속 돌아감. 더는 원치 않으면 지움; `docs/operations/deploy-guide.md` 도
     배포 워크플로와 함께 지움.
6. 다음 명령
   `pre-commit uninstall --hook-type pre-commit --hook-type commit-msg --hook-type pre-push` 를
   실행하거나, `.pre-commit-config.yaml` 에서 `teams-notify-push` 훅을
   지움 — 그 항목은 1단계에서 지운
   `.claude/harness-tier/scripts/notify-push.sh` 를 가리킴.
7. 결과를 커밋함.
