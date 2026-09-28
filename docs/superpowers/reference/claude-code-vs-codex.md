# Claude Code ↔ Codex CLI 차이 정리

내부 참고 문서 — 소비자에게 배포되지 않음. harness-tier 가 두 하네스를 함께 지원하면서 기대는 사실과 그 근거를
한곳에 모음. 하네스가 바뀌면 이 문서를 먼저 고치고, 설계·코드는 이 문서를 따라감.

## 기준과 근거 등급

- 확인 기준: Claude Code(현행) · codex-cli **0.157.1** (소스 태그 `rust-v0.157.1`) · Windows 10 실측.
- 근거 등급:
  - **실측** — 이 repo 의 `evals/codex_probe/` 로 직접 관찰.
  - **소스** — openai/codex 소스 코드(경로는 `codex-rs/` 기준).
  - **문서** — 공식 문서(learn.chatgpt.com/docs/*, code.claude.com/docs/*).
  - **이슈** — GitHub 이슈·타 플러그인 실사례. 버전 한정일 수 있음.
- 등급이 이슈뿐인 항목은 설계 근거로 쓰기 전 실측으로 승격.

## 1. 플러그인 패키징

| 항목 | Claude Code | Codex | 근거 |
|---|---|---|---|
| manifest | `.claude-plugin/plugin.json` | `.codex-plugin/plugin.json` → `.claude-plugin/plugin.json` → `.cursor-plugin/plugin.json` 순 탐색 | 소스 |
| marketplace | `.claude-plugin/marketplace.json` | `.agents/plugins/marketplace.json` 필수. `.claude-plugin/marketplace.json` 은 legacy 탐색만 — 이것만으론 설치 불가 | 소스 · superpowers |
| 설치 명령 | `/plugin marketplace add` · `/plugin install` | `codex plugin marketplace add owner/repo\|<local path>` → `codex plugin add <name>@<marketplace>` (headless 가능), 제거 `codex plugin remove` · `codex plugin marketplace remove`. TUI `/plugins` 도 가능 | 문서 · **실측** |
| 로컬 marketplace | `--plugin-dir` 로 작업 트리 직접 로드 | 로컬 경로도 **그 경로의 커밋된 HEAD 를 git clone** — 미커밋·untracked 변경은 설치본에 없음 | **실측** |
| 캐시 | `~/.claude/plugins/cache/...` | `~/.codex/plugins/cache/<marketplace>/<plugin>/<version>/` | 문서 |
| skill 위치 | 플러그인 `skills/` | manifest `skills` (`./` 경로 문자열·배열, 기본 `skills/`) | 소스 |
| hook 위치 | 플러그인 `hooks/hooks.json` | manifest `hooks`. 형태: `./` 경로 문자열 · 경로 배열 · inline 객체 · inline 배열 | 소스 |
| hook 자동 탐색 | — | `hooks` 부재·`./` 없는 경로·빈 배열·무효 타입 → `hooks/hooks.json` 자동 탐색(Claude 용 파일이 Codex 에 등록됨). `{}` 또는 유효 경로면 억제 | 소스 · superpowers v6.1 |
| 루트 `plugin.json` | 무관 | 존재 시 Agent Plugins 로더 선택 → hook 전체 조용히 비활성(#39895) | 이슈 |
| 실행 비트 | 보존 | marketplace 패키징이 제거한 사례 — 스크립트는 `bash x.sh` / `python3 x.py` 로 호출 | superpowers |

## 2. 지침 파일

| 항목 | Claude Code | Codex | 근거 |
|---|---|---|---|
| 파일 | `CLAUDE.md` 또는 `.claude/CLAUDE.md` (중첩) · `.claude/rules/` (`paths:` 범위) | 디렉터리마다 `AGENTS.override.md` → `AGENTS.md` → `project_doc_fallback_filenames` 중 **처음 찾은 1개만** | 소스 `agents_md.rs` |
| AGENTS.md | CLAUDE.md 가 없을 때만 네이티브로 읽음. CLAUDE.md 가 있으면 `@AGENTS.md` import 할 때만(중복 로드 없음) | 기본 파일 | 문서(code.claude.com memory) |
| CLAUDE.md | 기본 파일 | 기본 fallback 아님 — `project_doc_fallback_filenames = ["CLAUDE.md"]` 로 설정해야 읽음. 같은 디렉터리에 AGENTS.md 가 있으면 무시 | 소스 `config_toml.rs` |
| 탐색 범위 | root·상위 + 하위 디렉터리 파일은 그 위치 작업 시 로드 | **cwd 와 그 상위만** (project root = `.git` 마커, `project_root_markers` 로 변경). cwd 아래 하위 디렉터리 파일은 절대 안 읽음 → root 세션이면 사실상 root AGENTS.md 하나 | 소스 |
| 크기 한도 | — | `project_doc_max_bytes` 기본 32 KiB, **파일 합산**. 초과 시 **조용히 절단**(서버 로그만, 모델엔 표시 없음) | 소스 |
| import | `@path` (깊이 제한 있음) | 없음 — 파일을 순서대로 이어 붙이기만 함 | 소스 |
| `.claude/rules` 대응 | — | 없음(Codex 의 "rules" 는 execpolicy `.rules`, 다른 개념) | 소스 · 문서 |
| 재로드 | — | shell `cd` 로는 재로드 안 됨. 세션 환경(cwd) 재선택 시만 | 소스 `agents_md_manager.rs` |
| 프로젝트 설정 | — | `.codex/config.toml` 에서 `project_doc_fallback_filenames`·`project_doc_max_bytes` 설정 가능(금지 목록 밖, trusted 필요) | 소스 `loader/mod.rs` |
| symlink `CLAUDE.md → AGENTS.md` | Windows 에서 관리자 권한 필요, git 이 평문 파일로 체크아웃 — 비권장 | — | 문서 |

## 3. Hook

### 3.1 등록과 형식

| 항목 | Claude Code | Codex | 근거 |
|---|---|---|---|
| 프로젝트 hook | `.claude/settings.json` `hooks` | `.codex/hooks.json` 또는 `.codex/config.toml` `[hooks]` — **프로젝트 trusted 일 때만 로드** | 문서 · 소스 |
| 병합 | 레벨 간 병합 | 소스 간 병합(대체 아님) | 문서 |
| 파일 최상위 키 | `hooks` | `description` · `hooks` 만 허용 — 다른 키 있으면 **파일 전체 로드 실패** | 소스 |
| handler 필드 | `type` · `command` · `timeout` · `shell` · `statusMessage` · `async` · `if` | `type` · `command` · `commandWindows` · `timeout`(초, 기본 600) · `async` · `statusMessage` · `additionalContextLimit`. `shell`·`if` 없음(무시) | 소스 |
| matcher | 이름 알파벳 `[A-Za-z0-9_\- ,\|]` 이면 `\|`·`,` 목록, 그 외 JS 정규식 | `[A-Za-z0-9_\|]` 만이면 `\|` 분리 정확 일치(콤마·공백·하이픈 있으면 Rust 정규식), `""`·`*` 전체 — `"Bash,Read"` 는 Codex 에서 Bash 에 안 걸림 | 소스 |
| 이벤트 | SessionStart · PreToolUse · PostToolUse · Notification · Stop · … | SessionStart · SessionEnd · PreToolUse · PermissionRequest · PostToolUse · PreCompact · PostCompact · UserPromptSubmit · SubagentStart · SubagentStop · Stop · Interrupt. **Notification 없음** | 문서 · 소스 |

### 3.2 실행 환경

| 항목 | Claude Code | Codex | 근거 |
|---|---|---|---|
| shell (Unix) | `sh`/`bash` | 세션 셸 `-c` (없으면 `$SHELL`/`/bin/sh -lc`) | 소스 |
| shell (Windows) | `shell: "bash"` → Git Bash | `pwsh.exe -NoProfile -Command "<command>"` (pwsh 없으면 powershell, 세션 셸 없으면 `cmd /C`) | 소스 · **실측** |
| Windows `bash` | Git Bash | PowerShell 에서 `bash` = `C:\Windows\system32\bash.exe` (**WSL**) — Windows 경로 스크립트 실행 실패 | **실측** |
| Windows 별도 명령 | — | `commandWindows` 가 Windows 에서만 `command` 대체 | 소스 |
| cwd | 프로젝트 루트 | **세션 cwd**(하위 디렉터리 가능) — 경로는 `$(git rev-parse --show-toplevel)` 기준 | 소스 · **실측** |
| 플러그인 root 변수 | `${CLAUDE_PLUGIN_ROOT}` | `${PLUGIN_ROOT}` · `${PLUGIN_DATA}` + 호환 `${CLAUDE_PLUGIN_ROOT}` · `${CLAUDE_PLUGIN_DATA}`. **Codex 가 명령 문자열에서 직접 치환**(해당 소스 env 키만) + env 주입 | 소스 · PR#19705 · **실측**(Windows `commandWindows`, 플러그인 SessionStart 주입 성공) |
| 프로젝트 root 변수 | `${CLAUDE_PROJECT_DIR}` | **없음**. 프로젝트 hook 에는 추가 env 없음 | 소스 · **실측** |
| 기타 env | — | 세션 시작 시점 env 스냅샷 | 소스 |
| 캐시 교체 | — | 세션 중 marketplace 자동 업그레이드로 해석된 `${PLUGIN_ROOT}` 경로가 사라지는 사례(#31383) | 이슈 |

### 3.3 입력 payload

공통 stdin: `session_id` · `transcript_path` · `cwd` · `hook_event_name` · `model` · `permission_mode`.
턴 이벤트는 `turn_id` 추가.

| 이벤트 | Claude Code | Codex | 근거 |
|---|---|---|---|
| PreToolUse (shell) | `tool_name:"Bash"`, `tool_input.command` | 동일. `tool_name:"Bash"`, `tool_input.command` 문자열, `tool_use_id` | 소스 · **실측** |
| 파일 편집 | `Edit`/`Write`/`MultiEdit`, `tool_input.file_path` | `tool_name:"apply_patch"`, `tool_input.command` = patch 원문. 경로는 `*** Add File:` · `*** Update File:` · `*** Delete File:` · `*** Move to:` 헤더(cwd 상대). matcher `Edit`·`Write` 는 `apply_patch` 별칭 | 소스 · **실측** |
| shell 안 apply_patch | — | `exec_command` 가 가로채 **Bash hook 으로만** 발화. 헤더 경로는 그 셸 명령의 디렉터리 기준 — 앞선 `cd <dir> &&` 를 따라가야 함 | 소스 |
| PostToolUse | `tool_response` | `tool_response` (문자열) | **실측** |
| 파일 읽기 | 전용 `Read` 도구 — Bash hook 대상 아님 | 셸(`Bash`)로 읽음 → Bash PostToolUse 가 읽기마다 발화하고 `tool_response` 에 파일 내용이 담김. 편집 판정은 `tool_input.command` 만 보고, `tool_response` 의 문자열로 판정하면 오탐 | 리뷰 실측 |
| 차단된 명령 | — | PostToolUse 발화 없음 | **실측** |
| SessionStart `source` | startup · resume · clear · compact | startup · resume · clear · compact · fork. matcher 는 `source` 와 매칭 | 소스 · **실측** |
| shell tool 변형 | — | 0.157.1 은 `exec_command` 하나, Pre/Post 모두 `Bash`. `write_stdin` 은 PreToolUse 미발화 | 소스 |

### 3.4 출력과 차단

| 항목 | Claude Code | Codex | 근거 |
|---|---|---|---|
| 차단 | exit 2 + stderr, 또는 `permissionDecision:"deny"` JSON | 동일 규약. **단 Windows(pwsh 경유)에서 exit 2 가 1 로 바뀌어 차단 안 됨**(#48183) — deny JSON + **exit 0** 만 확실 | **실측** · 이슈 |
| legacy 차단 | — | `{"decision":"block","reason":...}` | 문서 |
| 입력 재작성 | `updatedInput` | `updatedInput` | 문서 |
| SessionStart 주입 | `hookSpecificOutput.additionalContext` | 동일. 최상위 `additionalContext` 는 거부(#45999). JSON 아닌 stdout 은 전체가 context. JSON 처럼 보이는 무효 출력은 실패 | 소스 · 이슈 |
| `systemMessage` | 사용자 경고 | 경고로 표시 | 소스 |
| 출력 크기 | — | 모델 노출 기본 **2,500 토큰**(≈ bytes/4). 초과 시 머리·꼬리 미리보기 + 전문 파일 경로(표시 있음, 조용하지 않음). handler `additionalContextLimit: 0` 으로 해제 — 약 5,000 토큰 전문 도달 확인 | 소스 · **실측** |
| stdout 에 JSON 둘 | — | 무효 출력 → hook 실패 처리. 한 번에 JSON 한 개 | 소스 |

### 3.5 Trust

| 항목 | Claude Code | Codex | 근거 |
|---|---|---|---|
| 승인 | 없음(settings 에 쓰면 실행) | 비관리 hook 은 `/hooks` 에서 trust 해야 실행. 미승인·변경 hook 은 **조용히 skip**. TUI 시작 시 "Hooks need review" | 소스 · 문서 |
| 저장 | — | user `config.toml` `[hooks.state."<key>"] trusted_hash`, `enabled` | 소스 |
| key | — | 프로젝트: `<hooks.json 절대경로>:<event_snake>:<group>:<handler>`. 플러그인: `<plugin_id>:<상대경로>:...` | 소스 |
| hash 대상 | — | 이벤트·matcher·플랫폼별 command·timeout·async·statusMessage·additionalContextLimit (`${PLUGIN_ROOT}` 치환 전) → **명령 문자열 변경·배열 위치 이동 = 재승인** | 소스 |
| 프로젝트 trust | — | `[projects."<path>"] trust_level = "trusted"`. Windows 는 소문자 canonical 경로, 대소문자 무시 조회. 미신뢰면 `.codex/` 전체 무시 | 소스 |
| 플러그인 hook 과 프로젝트 trust | — | 플러그인(캐시) hook 은 프로젝트 trust 와 무관 — 미신뢰 프로젝트에서도 `/hooks` 승인(또는 우회 플래그)만으로 SessionStart 주입. 대조: 우회 없이 미승인이면 미주입. 결과: 미신뢰 프로젝트는 규칙만 받고 게이트(`.codex/hooks.json`)는 꺼짐 | **실측** (Windows, 0.157.1, 격리 `CODEX_HOME`) |
| 비대화 실행 | — | `codex exec` 는 trust 검토 없음 → 미승인 hook 미실행. `--dangerously-bypass-hook-trust` 로 해당 실행만 우회 | 소스 · **실측** |
| 데스크톱 앱 | — | trust 수단 없음(TUI 만, #47283) | 이슈 |

## 4. Skill

| 항목 | Claude Code | Codex | 근거 |
|---|---|---|---|
| 형식 | SKILL.md (agentskills) | 동일. 필수 `name` · `description` | 문서 |
| 호출 | `/name`, Skill 도구 | `$name` · `/skills`, 전용 도구 없음 — 모델이 SKILL.md 를 읽음 | 소스 |
| 모델 호출 차단 | `disable-model-invocation: true` | frontmatter 무시. `skills/<name>/agents/openai.yaml` `policy.allow_implicit_invocation: false` → catalog 에서 숨김. 플러그인 skill 에도 적용, 파싱 실패 시 무시 | 소스 |
| `allowed-tools` | 사전 승인 | 파싱만, 강제 없음 | 서드파티 · 소스 |
| `context: fork` · `agent` · `model` | 지원 | 무시 | 서드파티 |
| 본문 변수 | `${CLAUDE_PLUGIN_ROOT}` · `$ARGUMENTS` 등 치환 | **치환 없음**. SKILL.md 경로는 catalog `(file: <path>)` 로 노출 | 소스 |
| 본문 크기 | — | 명시 주입 본문 **8,000 byte 절단 + 경고** → 파일 직접 읽기 필요 | 소스 |
| catalog 크기 | — | 초기 목록 약 8,000 자 | 문서 |

## 5. 도구 대응

| 행동 | Claude Code | Codex | 조건 | 근거 |
|---|---|---|---|---|
| 사용자 질문 | AskUserQuestion (1–4 질문, 2–4 선택지, multiSelect). **deferred 도구일 수 있어 도구 탐색(ToolSearch)으로 로드 후 호출**. headless `claude -p` 에는 아예 없음 | `request_user_input` (`questions[{id, header, question, options[{label, description}]}]`, 권장 질문 ≤3·선택지 2–3, multiSelect 없음, Other 자동) | **Plan 모드 전용**. Default 는 `[features] default_mode_request_user_input`(개발 중, off) + non-blocking. exec 거부. root thread 전용 | 소스 |
| 질문 fallback | — | 번호 선택지를 채팅에 쓰고 턴 종료 | 항상 동작 | superpowers · CE |
| 이식 가능한 질문 지시 | 도구 이름 대신 능력 기준 문장: "도구 목록의 blocking question tool 사용 → 미로드면 탐색으로 로드 → 없거나 실패 시 번호 선택지 + 턴 종료" | 같은 문장 | 양쪽 | compound-engineering |
| skill 호출 | Skill 도구 | SKILL.md 전체 읽기 | — | 소스 |
| subagent | Agent (`subagent_type`) | `spawn_agent` (V1: `message`·`agent_type`·`fork_context` / V2: `task_name`·`message`·`agent_type`·`fork_turns`), `wait_agent`, `send_input`/`followup_task`, `close_agent`(V1 만) | `multi_agent` 기본 on. 사용자 요청 없이 spawn 자제 | 소스 |
| 역할 정의 | `agents/*.md` | `.codex/agents/*.toml` (`name` · `description` · `developer_instructions`), 플러그인 번들 미확인 | — | 문서 |
| todo | TodoWrite | `update_plan` | 0.152+ 기본 off (`[tools.update_plan] enabled`) | 소스 |
| agent team | TeamCreate 등 | 없음 | — | — |

## 6. 비대화 실행 (eval 참고)

| 항목 | Claude Code | Codex | 근거 |
|---|---|---|---|
| 명령 | `claude -p --output-format stream-json` | `codex exec --json` | 문서 |
| 모델 | `--model` | `-m` | 문서 |
| 권한 | `--permission-mode` | `--sandbox read-only\|workspace-write\|danger-full-access`, `--dangerously-bypass-approvals-and-sandbox` | 문서 |
| 설정 격리 | `CLAUDE_CONFIG_DIR` | `--ignore-user-config` · `CODEX_HOME` · `-c key=value` | 문서 |
| hook trust | — | `--dangerously-bypass-hook-trust` | **실측** |
| 프로젝트 trust | — | `-c "projects.'<소문자 경로>'.trust_level=\"trusted\""` 로 부여 가능하나 **`~/.codex/config.toml` 에 영구 기록됨** — 실행 후 제거 필요 | **실측** |
| 질문 도구 | headless `-p` 에 AskUserQuestion 미제공 → 질문 표현 A/B 측정 불가(Sonnet 10세션 0/5·0/5, `init` tools 목록에 없음) | exec 에서 `request_user_input` 거부 | **실측** |
| 질문 단계의 비대화 실행 | Interaction 문장(질문 도구 없으면 번호 선택지 + 턴 종료) 때문에 headless 세션은 질문에서 멈춤 — 이전의 "기본값으로 진행" 동작 없음. outcome 시나리오 프롬프트가 모든 질문 단계의 답을 미리 줘야 함(wiki-init 1단계 누락 → 0/3 실측) | exec 도 동일(질문 도구 없음) | **실측** |
| 로그 | stream-json | JSONL: `thread.started` · `item.started/completed`(`command_execution` · `file_change` · `agent_message`) · `turn.completed` | **실측** |

## 7. harness-tier 설계에 미친 결정

- Codex manifest `hooks` 는 `"./hooks/codex/hooks.json"` — Claude hook 자동 등록 방지. 루트 `plugin.json` 금지.
- Codex gate 는 wrapper(`scripts/harness/codex/gate.sh` · `gate.cmd`) 경유: 러너 exit 2 → 0, deny JSON 으로 차단.
  Windows 는 `commandWindows` 로 Git Bash 명시 탐색(`where git` → `..\bin\bash.exe`).
- SessionStart handler `additionalContextLimit: 0` — risk-tiers 전문 주입.
- 편집 무효화 matcher `apply_patch|Bash`, Bash 는 `*** Begin Patch` 포함 시만.
- gate 명령 문자열·플러그인 hook 정의는 상수 — 변경은 전 소비자 재승인 비용.
- skill 본문은 도구 이름 대신 행동 어휘, Codex 고유 대응은 `rules/harness-tools/codex.md`.
- 질문하는 skill 은 `rules/harness-tools/vocabulary.md` 의 Interaction 문장(능력 기준) 을 본문에 한 번 — lint 강제.
- 지침 파일: Claude 산출물(CLAUDE.md·`.claude/rules`·모듈 CLAUDE.md) 이 IR 원본, Codex 렌더러가 root `AGENTS.md`
  관리 블록 하나로 렌더(규칙은 적용 경로 라벨, 모듈은 색인, 32 KiB 초과 시 규칙도 색인). Claude 산출물 불변.
- Codex matcher 판정은 Codex 알파벳(`[A-Za-z0-9_|]`)으로 — Claude 판정 코드를 재사용하지 않음.

## 8. 재검증 절차

`evals/codex_probe/` 에 실측 도구 보관: `probe.py`(stdin·env·부모 프로세스 기록, 차단 시나리오),
`probe.sh` + `probe.cmd`(Git Bash wrapper, exit 2 → 0).

1. scratch 디렉터리에 `git init` 한 임시 repo 생성, `.codex/hooks.json` 에 다음 등록
   (경로는 probe 파일 절대경로):
   - SessionStart `startup`: `python "<probe>/probe.py" session`, `additionalContextLimit: 0`
   - PreToolUse `Bash`: `python "<probe>/probe.py" pre` 와 `commandWindows: "& \"<probe>/probe.cmd\""`
   - PostToolUse `apply_patch` → `post_patch`, `Bash` → `post_bash`
2. 임시 repo 에서 실행. `-c` trust 는 `~/.codex/config.toml` 에 영구 기록되므로 실행 전 백업하고 끝나면 그 블록을 제거:

   ```powershell
   codex exec --json -m <model> --sandbox workspace-write --dangerously-bypass-hook-trust `
     -c "projects.'<임시 repo 소문자 경로>'.trust_level=`"trusted`"" "<지시문>"
   ```

   지시문: `echo PROBE_BLOCK_EXIT2` · `echo PROBE_BLOCK_JSON0` · `echo PROBE_BLOCK_WRAP 한글` ·
   `echo PROBE_ALLOW` 를 각각 한 번씩 실행하고, apply_patch 로 파일 하나 생성, 단계별 차단 여부와 세션
   context 가 요구한 단어를 보고.
3. 판정:
   - `PROBE_BLOCK_EXIT2` 가 실행되면 exit 2 무시(현재 Windows 상태).
   - `PROBE_BLOCK_JSON0` · `PROBE_BLOCK_WRAP` 차단 → JSON 경로 · wrapper 유효.
   - 최종 응답의 `ENDSEEN` → SessionStart 전문 도달.
   - `log/` 의 `chain` → hook shell, `stdin` → payload 형태, `env` → 변수 주입.
4. 결과가 이 문서와 다르면 해당 행과 근거 등급을 고치고 §7 결정을 재검토.

## 9. 플랫폼·테스트 함정 (구현 중 확인)

| 함정 | 증상 | 대응 | 근거 |
|---|---|---|---|
| `cmd` 한 줄의 `%errorlevel%` | `a & exit /b %errorlevel%` 는 줄 파싱 시 확장 → 항상 이전 값(보통 0) | 실행과 `exit /b %errorlevel%` 를 다른 줄로 | **실측** |
| `ProgramFiles` 재정의 | 자식 프로세스에 넘긴 값이 무시되고 레지스트리 값으로 재계산 | 32-bit `C:\Windows\SysWOW64\cmd.exe` 로 실행하면 `Program Files (x86)` 가 됨 | **실측** |
| 테스트의 bare `bash` | PATH 상 WSL stub 가 먼저 → Windows 경로 실패 | Git Bash 를 PATH 앞에 두거나 탐지 헬퍼 사용 | **실측** |
| import 시 `sys.path` 조작 | 같은 모듈이 두 객체로 로드 → 전체 스위트에서만 동일성 테스트 실패 | 스크립트 실행 경로(`__main__`) 에서만 조작 | **실측** |
| bash `${#var}` (UTF-8 로캘, 전 플랫폼) | 문자 수를 셈 → 바이트 상한(64 KB) 비교가 한국어 payload 에서 통과 | 함수 안 `local LC_ALL=C` 로 길이만 바이트로 측정(서브셸 없이) | **실측** (Git Bash `C.UTF-8`·`en_US.UTF-8`) |
| Windows `symlink_to('a/b')` | `/` 구분자 대상은 끊긴 링크로 생성(`exists()` False) → 링크 테스트가 엉뚱한 이유로 통과 | 대상을 `Path(...)` 로 넘겨 `\` 구분자 사용 | **실측** |
| `Path.is_file()` 의 `PermissionError` (Linux) | 닫힌(mode 000) 상위 디렉터리에선 False 가 아니라 raise → 가드 밖 호출이 실행 전체를 끝냄 | 호출을 `_step` 류 가드 안에 두거나 호출부에서 잡아 FAIL-OPEN | **실측** (WSL; Windows 는 skip) |
| 대소문자 무시 경로 비교를 테스트에 하드코딩 | Windows 에선 녹색, Linux CI 에선 key 불일치로 빨강 | 테스트가 플랫폼 저장 방식대로(`os.name == "nt"` 일 때만 lower) key 작성 | **실측** (WSL) |
| TOML basic-string key 의 `\\` | `"c:\\users\\…"` 원문을 그대로 비교 → Windows 에서 trusted 인데 경고 | `"` key 만 `\\`·`\"` 를 풀어서 비교(literal `'` key 는 그대로) | 코드 + 테스트 |
| `AGENTS.md` ↔ `CLAUDE.md` 가 한 파일(심볼릭·하드 링크) | 렌더가 링크를 따라 Claude 원본에 블록을 쓰고 매 실행 증식, `--check` 영구 실패 | `realpath`·`samefile` 로 같은 파일이면 쓰지 않고 `[!]` 한 줄 | **실측** (WSL 리뷰 + 테스트) |
| Git Bash here-string | `python3 … <<< "$payload"` 가 64 KB 입력에서 멈춤(20 초 timeout) | `printf '%s' "$payload" \| python3 …` 파이프 사용(약 0.5 초) | **실측** |

## 10. 미검증·후속

- Unix(Linux/macOS) Codex 의 hook 실측 — 소스상 `bash -c` · exit 2 유효, wrapper 는 JSON 경로라 무관.
- Antigravity: SessionStart 없음, 질문 도구 없음, hook payload `toolCall.name`·`toolCall.args` + `decision:"deny"`,
  플러그인 subagent 미등록 버그 — 후속 사이클에서 실측.
