# Codex CLI 지원 설계

## 목표

harness-tier 플러그인을 Claude Code 와 OpenAI Codex CLI 양쪽에서 동작하게 함. Claude Code 가 primary.
Antigravity 는 자리(인터페이스·stub)만 두고 등록은 후속 사이클.

성공 기준:

- Codex 세션에서 플러그인 설치 → risk-tiers 규칙 주입 → `/flow` 호출 → 미분류 commit 차단.
- skill 의 사용자 질문·skill 호출·subagent 파견이 Codex 에서도 수행됨(도구 부재 시 fallback).
- 기존 Claude 소비자: 동작·산출물 byte-identical. `/flow-init` 재실행 없이도 깨지지 않음.
- Sonnet eval(invocation·outcome) 회귀 없음. Codex eval 은 범위 밖.

## 조사 근거

- Codex 공식 문서(learn.chatgpt.com/docs: hooks · build-skills · plugins · subagents · agents-md) 및
  openai/codex 소스(`request_user_input_spec.rs`, `multi_agents_spec.rs`, `plan_spec.rs`,
  `catalog_prompt.rs`, `DISCOVERABLE_PLUGIN_MANIFEST_PATHS`).
- 멀티 하네스 플러그인 조사: obra/superpowers(최근접 선례), EveryInc/compound-engineering-plugin,
  github/spec-kit, BMAD-METHOD, rulesync, ruler, agent-os.
- superpowers RELEASE-NOTES · `docs/porting-to-a-new-harness.md` 대조(G1–G7).

### Codex 사실 (설계가 기대는 것)

| 항목 | 내용 |
|---|---|
| 플러그인 manifest | `.codex-plugin/plugin.json` (`.claude-plugin/plugin.json` 은 fallback 탐색) |
| marketplace | `.agents/plugins/marketplace.json` 필수 (Claude 파일만으론 설치 불가) |
| 플러그인 hook | manifest `hooks` 필드. 부재·`[]` → `hooks/hooks.json` 자동 탐색 |
| hook 형식 | Claude 와 동일 (`PreToolUse` · `Bash` matcher · `permissionDecision` · `additionalContext`). 단 Windows 에선 exit 2 무시 |
| 편집 도구 | `apply_patch` (payload 에 `file_path` 없음) |
| 환경 변수 | 플러그인 hook: `PLUGIN_ROOT` + 호환 `CLAUDE_PLUGIN_ROOT`. 프로젝트 hook: 없음. `CLAUDE_PROJECT_DIR` 없음 |
| trust | 프로젝트 trust 없으면 `.codex/` 전체 무시. 비관리 hook 은 `/hooks` 승인 필요 |
| 질문 도구 | `request_user_input`: Plan 모드 전용, Default 는 개발 중 플래그·non-blocking, exec 거부, multiSelect 없음 |
| skill 호출 | 전용 도구 없음 — SKILL.md 직접 읽기 |
| subagent | `spawn_agent` (`agent_type`, `fork_turns`), V1/V2 스키마 상이 |
| todo | `update_plan` (0.152+ 기본 off) |
| skill frontmatter | `disable-model-invocation` · `context` 무시. 대체: `agents/openai.yaml` `policy.allow_implicit_invocation: false` |

## 구조 — 하이브리드

- **A. skill 층**: 공유 본문(행동 어휘 IR) + 하네스별 매핑 문서. 빌드 없음.
- **B-lite. 설치 층**: `/flow-init` 이 canonical gate 정의를 하네스별 설정으로 렌더.
- **C. hook 층**: 공유 스크립트 + `--harness` 명시 인자로 하네스별 입력 차이 흡수.

### 레이아웃

```text
.claude-plugin/                  Claude manifest (유지)
.codex-plugin/plugin.json        NEW  skills "./skills/", hooks "./hooks/codex/hooks.json"
.agents/plugins/marketplace.json NEW  Codex marketplace (source url "./")

hooks/
  hooks.json                     Claude 등록 (유지 — Claude 기본 탐색 경로)
  codex/hooks.json               NEW  Codex 등록
  codex/run-hook.cmd             NEW  Windows: Git Bash 탐색 후 공유 스크립트 실행
  antigravity/                   NEW  자리만
  inject-risk-tiers.sh           공유 (+ --harness 인자)
  invalidate-gate-markers.sh     공유 (+ --harness 인자)

scripts/
  precommit-runner.sh            진입점 — 수정 없음 (host settings.json 계약, 예외 1 bash deny)
  flow_gate_check.py             분류기 — 수정 없음 (불변식 7)
  _harness_paths.py              코어 공용
  flow_init_setup.py             오케스트레이션. 하네스별 등록은 harness/<name>/install 위임, 기존 이름 re-export
  harness/
    __init__.py
    jsonfile.py                  JSON 파일 안전 읽기·쓰기 (flow_init_setup 에서 이동, 두 installer 공유)
    gate_spec.py                 canonical gate IR: GateSpec · GATE
    claude/  __init__.py · install.py              (← flow_init_setup 의 settings.json 코드 이동)
    codex/   __init__.py · hook_io.py · install.py   (apply_patch 경로 추출 · .codex/hooks.json 등록)
             gate.sh · gate.cmd                     (host 복사, exit 2 → 0 변환 wrapper)
    antigravity/ __init__.py     stub — 호출 시 unsupported → FAIL-OPEN

rules/harness-tools/
  vocabulary.md                  행동 어휘 SSOT
  codex.md                       Codex 고유 매핑만
  antigravity.md                 stub

tests/harness/                   claude/ · codex/ 하위, fixture·계약 테스트
```

하네스 패키지 계약(모든 `harness/<name>/` 동일):

- `install.register(host)` · `install.unregister(host)` · `install.problems(host)` · `install.hook_remains(host)`.
- `hook_io` 는 입력이 Claude 와 다른 하네스만 가짐(Codex: `edited_paths`). Claude 입력 처리는 기존 bash 그대로.

gate 입출력(PreToolUse stdin, deny JSON)은 Claude·Codex 동일 → `hook_io` 대상 아님. exit code 차이(Windows 에서 exit 2
무시)는 러너가 아니라 Codex 등록 명령의 wrapper(`harness/codex/gate.*`)가 흡수.
`precommit-runner.sh` 의 bash `deny()` 는 python3 부재 시 fail-closed 경로(불변식 1 예외 1)라 이동 금지.

## 행동 어휘 IR (skill 층)

| 행동 (본문 표기) | Claude Code | Codex (`codex.md`) |
|---|---|---|
| Ask the user (structured choice) | AskUserQuestion (모델 자체 매핑, 문서 없음) | `request_user_input` 있으면 사용, 없으면 번호 선택지 채팅 + 턴 종료 대기. multi-select 는 번호 복수 응답 |
| Invoke skill `<name>` | Skill 도구 | 플러그인 `skills/<name>/SKILL.md` 전체 읽고 따름 |
| Dispatch subagent `<role>` | Agent (`subagent_type`) | `spawn_agent` (`fork_turns:"none"`), message = `agents/<role>.md` 본문 + 과제. 도구 부재 → inline |
| Track steps | TodoWrite | `update_plan` 있으면, 없으면 채팅 체크리스트 |
| Agent team | TeamCreate 등 | Dispatch subagent 로 대체 |
| Plugin root (`${CLAUDE_PLUGIN_ROOT}` 표기 유지) | 치환됨 | SKILL.md 기준 두 단계 위 디렉터리 |

- Claude 매핑 문서·Claude SessionStart 주입 변경 없음(G1 — 모델이 행동 어휘를 자체 매핑).
- frontmatter: `disable-model-invocation: true` skill 마다 `agents/openai.yaml` 짝 생성. `allowed-tools` 는
  Codex 미강제 — `codex.md` 에 명시. `context: fork`(doc-sync) 는 Codex 에서 inline.
- `agents/*.md` → `.codex/agents/*.toml` 생성 안 함. 역할 본문을 프롬프트로 전달.
- 치환 범위는 도구 이름 목록 한정. `git commit`/`git merge` 리터럴(불변식 7) 불변.

## hook·gate

- 하네스는 판별하지 않고 명시: hook 명령에 `--harness codex`. 인자 없음 = `claude` → 기존 경로 byte-identical.
- Codex 플러그인 hook (`hooks/codex/hooks.json`, 경로 변수 `${PLUGIN_ROOT}`):
  - `SessionStart` → `inject-risk-tiers.sh --harness codex`: risk-tiers + `codex.md` 주입.
  - `PostToolUse` matcher `apply_patch|Bash` → `invalidate-gate-markers.sh --harness codex` (Bash 는 patch 포함 시만).
- Codex gate: `/flow-init` 이 `<host>/.codex/hooks.json` `PreToolUse` 에 `matcher: "Bash"` 로 match-then-skip.
  명령은 러너가 아니라 `harness/codex/gate.sh`·`gate.cmd` wrapper(확정 사항 참조). `if` 필드 없음(불변식 4).
- Codex 규칙 전달은 SessionStart hook (결정). trust·`/hooks` 승인 전엔 규칙·gate 모두 비활성 — 승인 한 번에
  둘 다 켜짐. `/flow-init` 이 승인 필요 안내.
- Teams `Notification` hook: Codex 에 해당 이벤트 없음 → Codex 미지원으로 문서화.

## `/flow-init`

- `flow-config` `harnesses:` 키. 부재 = `[claude]`. example 에 주석 슬롯.
- 대화 단계: 호스트에 `.codex/` 존재 또는 사용자 요청 시에만 Codex 추가 제안.
- `[커밋 게이트]` 단계: `harnesses` 순회 → `harness/<name>/install.register`.
- 검증: 기존 `_gate_problems` + Codex 는 `~/.codex/config.toml` `[projects."<host>"] trust_level` 읽기 전용
  확인 → 미충족 시 경고(실패 아님). 사용자 home 쓰기 금지.
- 쓰지 않는 것: `.codex/agents/*.toml`, `.codex/config.toml`. AGENTS.md 는 아래 지침 렌더의 관리 블록만.

## 지침 파일 IR (사용자 결정으로 추가)

- Codex 는 CLAUDE.md·`.claude/rules/` 를 읽지 않고, cwd 와 그 상위의 AGENTS.md 만(합계 32 KiB, 초과 시 조용히 절단) 읽음.
  root 세션이 기본이라 실질적으로 root AGENTS.md 하나만 확실히 로드됨.
- IR 원본 = Claude 산출물(root CLAUDE.md, `.claude/rules/*.md` `paths:`, 모듈 CLAUDE.md). 소비자가 손으로 고친 host-owned
  파일이라 새 원본 포맷·이관 없음. `scripts/harness/instructions.py` 가 `InstructionDoc` 로 파싱(`@import` 전개).
- Codex 렌더러(`scripts/harness/codex/instructions.py`) 가 root `AGENTS.md` 에 관리 블록 하나: root 본문 → 규칙(적용 경로
  라벨) → 모듈 색인. 예산 초과 시 규칙도 색인으로 축약하고 경고. 블록 밖 텍스트 보존, idempotent, `--check` drift 검사.
- 실행: `/flow-init`(codex 활성 시), `doc-sync`·`harness-init` 이 CLAUDE.md 계열을 바꾼 뒤. uninstall 이 블록 제거.
- Claude 산출물은 절대 수정 안 함 — Claude 전용 호스트 불변.
- uninstall: config 무관 전 하네스 등록 제거. `.codex/hooks.json` 은 자기 항목만 제거, 빈 구조 + 자기가 만든
  파일일 때만 파일 삭제. idempotent(불변식 5).

## 기존 소비자 호환성

| # | 위험 | 대응 |
|---|---|---|
| R1 | `copy_artifacts` 가 `Path(rel).name` 평탄 복사 → 하위 동명 파일 충돌 | 상대 경로 보존 복사. 기존 평탄 목적지 불변 테스트 |
| R2 | 부분 복사로 신·구 혼재 | 러너 수정 없음, 러너는 `harness/` import 안 함. `harness/` 사용은 `/flow-init` 설치·검증만 |
| R3 | 플러그인 업데이트 후 host 복사본은 재동기화 전 구버전 | host 복사 script CLI·동작 불변. skill 본문이 새 host script 참조 금지 |
| R4 | `register_gate` 계열 이동 → import 깨짐 | `flow_init_setup` re-export. `tests/flow_init/` 무수정 green |
| R5 | Claude 전용 호스트에 새 파일 | opt-in. 기본 `[claude]` 산출물 byte-identical |
| R6 | 무효화 hook Claude 경로 변화 | 인자 없으면 기존 경로 그대로 |
| R7 | Codex 에서 plugin root 공백 → 조용한 FAIL-OPEN | `${PLUGIN_ROOT}` (Codex 직접 치환, 소스 확정) |
| R8 | Codex hook cwd 가 하위 디렉터리, Windows 는 pwsh 실행·exit 2 무시·`bash`=WSL | git toplevel 경로 + `commandWindows` + exit 2→0 wrapper + Git Bash 명시 탐색 |
| R9 | 본문 행동 어휘화로 Claude 가 평문 질문 회귀 | 재작성 전 baseline 확보, 재측정으로 AskUserQuestion 사용률 비교 |
| R10 | 본문 치환 중 불변식 7 파손 | 치환 대상 도구 이름 한정, `tests/skills` 리터럴 pin green |
| R11 | manifest 버전 불일치 | parity 테스트 + 이 repo release 단계 동기화. host 복사 `bump_version.py` 수정 금지 |
| R12 | 새 marketplace 경로 | Claude Code 미사용 경로 — 영향 없음 |

## superpowers 교훈 반영

| # | 교훈 | 반영 |
|---|---|---|
| G1 | 도구 매핑 표 비대화 후 정리, Claude 매핑 삭제 | Claude 매핑 없음, `codex.md` 는 고유 내용만 |
| G2 | Codex 패키저가 실행 비트 제거 → `Permission denied` | 스크립트 호출은 `bash x.sh` / `python3 x.py` 강제(테스트) |
| G3 | Codex SessionStart 제거(trust 프롬프트, 자체 트리거 충분) | 유지 — `/flow` 선행 의무는 상시 규칙, gate 가 어차피 trust 요구. 한계 문서화 |
| G4 | 다중 manifest 버전 동기화 | 버전 parity 테스트 + release 단계 |
| G5 | Windows hook 실행 이슈 다수 | Codex Windows 실측, 전까지 "미검증" 표기 |
| G6 | 새 하네스 acceptance transcript 필수 | Codex 수동 acceptance 1회 |
| G7 | 환경 변수 판별 오판(Cursor 가 `CLAUDE_PLUGIN_ROOT` 설정) | `--harness` 명시 인자 |
| — | `hooks` 필드 부재·`[]` → Claude hook 자동 재등록 | `hooks` 는 codex 파일을 명시 지정 |
| — | Codex 설치에 `.agents/plugins/marketplace.json` 필수 | 추가 |

## 테스트·측정

1. 리팩터 커밋 선행·단독: `harness/claude/` 이동 + re-export. `tests/flow_init/`·`tests/flow_gate/` 무수정 green,
   collected node id 전후 diff.
2. 계약 테스트(`tests/harness/`): manifest 버전 parity, `.codex-plugin` `hooks` 지정, marketplace 존재,
   `COPY_FILES` 하위 경로 보존 + 평탄 목적지 불변.
3. skill 계약(`tests/skills/`): 본문 도구 이름 금지(예외 `rules/harness-tools/`), `disable-model-invocation` ↔
   `agents/openai.yaml` 짝, interpreter 접두사, 불변식 7 pin.
4. Codex hook fixture: 실측 캡처 stdin(`apply_patch` · SessionStart · PreToolUse).
5. mutation test(적용 assert), `.sh` 변경 WSL ShellCheck.
6. Sonnet eval: 본문 재작성 전 baseline(AskUserQuestion 사용률 포함) → 재작성 후 재측정. `--dry-run` 으로
   세션 수·시간 먼저 보고 후 승인.
7. Codex 실측·acceptance: 설치된 codex-cli 0.157.1, 모델 `gpt-6-luna`(무료 한도 — 호출 최소화).
   `codex exec --json --dangerously-bypass-hook-trust` 로 hook stdin 캡처(영구 trust 미기록), 깨끗한 세션에서
   개발 요청 → `/flow` → 미분류 commit 차단 확인, transcript 기록.

## 범위 밖

- Codex eval arm, Antigravity 등록, Teams 알림 Codex 지원, `harness-insight` 의 Codex 세션 로그,
  AGENTS.md 생성, vway-kit 반영(별도 작업).

## 확정 사항 (소스 rust-v0.157.1 · 실측 codex-cli 0.157.1 Windows · 실사례)

근거 상세·재검증 절차: `docs/superpowers/reference/claude-code-vs-codex.md`.

| 항목 | 확정 | 근거 |
|---|---|---|
| 플러그인 root | `${PLUGIN_ROOT}` — Codex 가 명령 문자열에서 직접 치환(PowerShell 안전), 호환 `CLAUDE_PLUGIN_ROOT` 도 env 주입 | 소스 `discovery.rs` · PR#19705 · 실사례 |
| 프로젝트 hook env | root 변수 없음, `CLAUDE_PROJECT_DIR` 없음, cwd = 세션 cwd | 소스 · 실측 |
| hook 실행 shell | Unix: 세션 셸 `-c`. Windows: `pwsh.exe -NoProfile -Command` (없으면 powershell / cmd) | 소스 · 실측 |
| Windows `bash` | PowerShell 에서 `bash` = `C:\Windows\system32\bash.exe`(WSL) — 사용 금지 | 실측 |
| Windows exit 2 | **차단 안 됨** (pwsh 가 1 로 변환, #48183) — deny JSON + exit 0 만 유효 | 실측 · 이슈 |
| `apply_patch` | `tool_name:"apply_patch"`, `tool_input.command` = patch 원문, 경로는 `*** Add/Update/Delete File:` · `*** Move to:` 헤더(cwd 상대) | 소스 · 실측 |
| shell 안 apply_patch | `exec_command` 가 가로채 **Bash hook 으로만** 발화 | 소스 |
| SessionStart | `source` ∈ startup·resume·clear·compact·fork. 기본 2,500 토큰 초과 시 머리·꼬리만 + 파일 경로. `additionalContextLimit: 0` 으로 해제 → 전문 도달 | 소스 · 실측 |
| manifest `hooks` | `"./hooks/codex/hooks.json"` (`./` 필수). `./` 없음·빈 배열·무효 → Claude `hooks/hooks.json` 자동 탐색. 루트 `plugin.json` 존재 시 hook 전체 비활성(#39895) | 소스 · 이슈 |
| trust | hash = 이벤트·matcher·command·timeout·async·statusMessage·additionalContextLimit. 변경·배열 위치 이동 → 재승인 전까지 조용히 skip | 소스 · 문서 |
| 프로젝트 trust key | Windows 소문자 canonical 경로, 대소문자 무시 조회 | 소스 |
| SKILL.md | 변수 치환 없음. 경로는 catalog 로 노출. 명시 주입 본문 8,000 byte 절단 + 경고 | 소스 |
| `agents/openai.yaml` | `skills/<name>/agents/openai.yaml`, 플러그인 skill 에도 적용 | 소스 |
| 최상위 `HooksFile` | `description`·`hooks` 외 키 → 파일 전체 로드 실패 | 소스 |

### 확정에 따른 설계 변경

- **Codex gate wrapper** (`scripts/harness/codex/gate.sh` · `gate.cmd`, host 복사):
  러너 실행 → exit 2 를 0 으로 변환(러너는 stdout 에 deny JSON 한 개만 출력 — 확인됨). 전 플랫폼 동일 경로라
  exit code 해석 차이에 무관. `gate.cmd` 는 `where git` → `..\bin\bash.exe`, 없으면 `%ProgramFiles%\Git\bin\bash.exe`
  로 Git Bash 탐색. 못 찾으면 deny JSON 출력(예외 1 과 같은 fail-closed). label 없는 `.cmd`(LF 체크아웃 안전).
- **Codex gate 등록 명령**: `command` = `bash "$(git rev-parse --show-toplevel)/.claude/harness-tier/scripts/harness/codex/gate.sh"`,
  `commandWindows` = `& "$(git rev-parse --show-toplevel)/.claude/harness-tier/scripts/harness/codex/gate.cmd"`.
  문자열은 상수 — 바뀌면 전 소비자 재승인. 테스트로 pin.
- **플러그인 hook Windows**: `commandWindows` = `& "${PLUGIN_ROOT}/hooks/codex/run-hook.cmd" <script> --harness codex`
  (같은 Git Bash 탐색, 실패 시 FAIL-OPEN). SessionStart handler 에 `"additionalContextLimit": 0`.
- **편집 무효화**: PostToolUse matcher `apply_patch|Bash`. `apply_patch` 는 patch 헤더에서 경로 추출. `Bash` 는
  명령에 `*** Begin Patch` 가 있을 때만 같은 파싱 — 그 외 Bash 는 무효화 안 함(`git add` 뒤 marker 삭제 방지).
- **skill 8 KB 절단**: `codex.md` 에 "주입된 skill 이 잘렸다는 경고가 있으면 SKILL.md 파일을 끝까지 읽고 따름" 명시.
- **manifest 금지 사항**: 루트 `plugin.json` 금지, `hooks` 는 `./` 경로 문자열 — 계약 테스트.
- **trust 안정성**: 플러그인 hook 정의·gate 명령 문자열 변경은 소비자 재승인 비용 — 변경 시 release note 명시.
