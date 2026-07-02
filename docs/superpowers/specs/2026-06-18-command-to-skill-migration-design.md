# Command-to-Skill Migration — vway-kit 진입점 일원화

**Date:** 2026-06-18
**Branch:** `feature/command-to-skill` (로컬 master `0390057` 기반)
**Status:** Design (브레인스토밍 산출물 — 구현 전 사용자 리뷰 대기)

## 배경

Claude Code에서 **커스텀 커맨드는 스킬로 통합**됐다(공식 문서 [skills.md](https://code.claude.com/docs/en/skills.md)):
`commands/<name>.md` 와 `skills/<name>/SKILL.md` 는 둘 다 `/name` 을 만들고 동일하게 동작한다.
다만 `skills/` 형식만 세 가지를 추가로 제공한다 — 지원 파일 디렉토리, **누가 호출할지 제어하는 frontmatter**
(`disable-model-invocation` 등), **모델 자동발동**.

현재 vway-kit 진입점은 `commands/` 5개(`flow`·`flow-init`·`task-import`·`task-sync`·`harness-init`)와
`skills/` 2개(`doc-sync`·`harness-authoring`)로 이원화돼 있고, 다음 세 가지 문제를 안고 있다.

1. **`task-import.md`·`task-sync.md` 에 frontmatter가 없다.** `description` 이 빈약해 모델이 *언제·누가
   부를지* 판단하지 못한다 → `flow` 가 위임할 때 `Skill` 도구로 인지하지 못하고, **정의 파일을 Read해서
   절차를 손으로 재현(흉내내기)** 한다. (실측: task-id 진입 트랜스크립트에서 `task-import.md` 가 Read됨.)
2. **`flow` 가 커맨드라 모델 자동발동이 안 된다.** task-id 단독 입력 시 진입하지 못한다. task-id→`task-import`
   라우팅 규칙이 `flow.md` 본문 안에만 있어, `flow` 가 로드되지 않으면 규칙도 컨텍스트에 없다(닭-달걀).
3. **`flow-init`·`harness-init` 은 1회성 셋업인데** 자동발동되면 위험하다(특히 `harness-init` 은 description이
   매력적이라 모델이 멋대로 부를 유혹이 있다).

## 목표

- **task-id 단독 입력 → `flow` 자동 진입.**
- `flow` 의 내부 위임(`task-import`·`task-sync`·`doc-sync`)이 Read-후-흉내가 아니라 **실제 `Skill` 발동**.
- 셋업 커맨드(`flow-init`·`harness-init`)는 **사용자 명시 호출만** 허용.

## 설계

### 1. 디렉토리 구조

`commands/` 5개를 `skills/<name>/SKILL.md` 로 이전하고 `commands/` 디렉토리를 제거한다.
기존 `skills/doc-sync`·`skills/harness-authoring` 은 그대로 둔다.
`plugin.json`·`marketplace.json` 은 컴포넌트 경로를 선언하지 않으므로(자동 발견) **매니페스트는 수정하지 않는다.**

```
commands/flow.md         → skills/flow/SKILL.md
commands/task-import.md  → skills/task-import/SKILL.md
commands/task-sync.md    → skills/task-sync/SKILL.md
commands/flow-init.md    → skills/flow-init/SKILL.md
commands/harness-init.md → skills/harness-init/SKILL.md
```

### 2. frontmatter 정책 (핵심)

**원리: 위임 대상은 자동발동을 켜야 하고, 셋업은 꺼야 한다.**

| 스킬 | 모델 자동발동 | frontmatter 요지 |
|---|:---:|---|
| `flow` | **허용** | `description` = task-id/작업 요청 진입점(task-id 패턴 강조), 기존 `allowed-tools`·`argument-hint` 유지 |
| `task-import` | **허용** | `description` = "`flow` 워크플로가 호출하는 Teamer import+scaffold 하위 단계", `allowed-tools`(Bash·Read·Write·Task), `argument-hint: [task_id]` |
| `task-sync` | **허용** | `description` = "`flow` 종료 후 Teamer 동기화 하위 단계", `allowed-tools`, `argument-hint: [task_id]` |
| `flow-init` | **`disable-model-invocation: true`** | 기존 frontmatter 유지 + 이 필드 추가 |
| `harness-init` | **`disable-model-invocation: true`** | 기존 frontmatter 유지 + 이 필드 추가 |

> ⚠️ **위임 대상에 `disable-model-invocation: true` 를 켜면 안 된다.** 그러면 모델이 `Skill` 도구로 못 불러
> 흉내내기로 회귀한다. `task-import`·`task-sync` 는 반드시 자동발동을 허용한다.

**over-trigger 방어**: `task-import`·`task-sync` 는 발동 가능하되 `description` 을 "하위 단계"로 좁히고
`when_to_use` 를 비워, task-id 입력 시 모델이 **`flow` 를 우선** 켜도록 유도한다. `flow` 의 `description` 이
task-id 진입점을 명확히 가져간다. (완벽 보장은 어려우므로 적용 후 트리거를 관찰·미세조정한다.)

### 3. 내부 위임 명시화

`flow` 본문의 `run /task-import` 류 표현을 **"invoke the `task-import` skill (via the Skill tool)"** 로
못박아, Read-후-흉내가 아니라 발동임을 강제한다. `doc-sync`·`superpowers` 위임 표현도 같은 기준으로 점검한다.

### 4. 참조 갱신 (약 15곳)

`task-import`/`task-sync` 를 참조하는 파일들(`flow.md`·`rules/risk-tiers.md`·`README.md`·`USAGE.md`·
`flow-config.example.yaml`·`agents/*`·handoff 문서 등)의 링크 경로(`task-import.md` → 스킬 경로)와 호출명
표기를 갱신한다. `CLAUDE.md` 의 폴더 구조 설명(`commands/` 목록)도 갱신한다.

### 5. 호출명 영향

플러그인 `skills/` 는 `/<plugin>:<name>` 네임스페이스가 붙어 정식 호출명은 `/vway-kit:flow` 등이 된다.
단축 `/flow` 는 네임스페이스 충돌이 없으면 유지될 가능성이 있다 → **적용 후 실측**해 `README`·`USAGE` 에
정확히 반영한다.

### 6. 호스트(ras_llm) 정리 — 별 저장소, 범위 한정

`c:\Work\llm_ai\ras_llm\.claude\commands\task-plan.md` (옛 진입점 잔재) **파일만 제거**한다.
이전 대화에서 모델이 task-id 진입을 옛 `task-plan` 으로 오인한 혼선 요인이었다.

## 비범위 (YAGNI)

- **ras_llm 메모리 교정** — 사용자가 이미 완료. 이번 묶음에서 다루지 않는다.
- **handoff 작업** — 별 작업. 로컬 master `0390057` 에 이미 반영돼 이 브랜치에 포함되지만, 추가 작업은 안 한다.
- **트리거를 hook으로 결정론적 강제** — 우선 `description` 튜닝으로 충분한지 관찰. 과하면 도입하지 않는다.

## 위험 / 완화

| 위험 | 완화 |
|---|---|
| `task-import` 가 task-id 입력에 `flow` 보다 먼저 켜짐(over-trigger) | `description` 을 하위 단계로 좁힘 + `flow` 가 진입점 우선. 적용 후 관찰·튜닝 |
| 단축 `/flow` 호출명이 깨짐 | 적용 후 실측, `README`/`USAGE` 갱신. 정식 `/vway-kit:flow` 는 항상 동작 |
| 참조 누락으로 깨진 링크 | 갱신 후 `task-import`·`task-sync` 전수 grep으로 잔존 참조 확인 |

## 검증

- 각 `SKILL.md` frontmatter가 [skills.md](https://code.claude.com/docs/en/skills.md) 스펙에 맞는지(필드명·형식).
- `task-import`·`task-sync` 참조 grep — 깨진 링크/구 경로 0건.
- 기존 테스트(`uv run pytest`)·린트(`ruff`)는 스크립트 무변경이라 영향 없어야 함 — 회귀 확인.
- (수동·적용 후) 호스트에서 task-id 입력 시 `flow` 발동, `flow`→`task-import` 발동 실측.
