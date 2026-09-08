# release-commit 스킬 설계

- 날짜: 2026-09-08
- 분류: architectural (신규 스킬 · 기존 스킬 축소 · evals 재측정)
- 티어: DEV / 브랜치 `feature/release-commit-skill`

## 1. 배경

0.3.1 릴리스에서 승격 절차 오류 5건이 났다. 근본 원인 1개:
**이 저장소에서 자매 플러그인 vway-kit 의 `/vdev` 를 돌렸다.**

vway-kit 릴리스 템플릿은 `workflow_dispatch: inputs: level` 모델이고,
harness-tier 는 `Release-Level:` 커밋 트레일러 모델이다. `/vdev` 지시대로
`[skip ci]` 병합을 하니 릴리스 job 이 통째로 스킵돼 rc 가 안 끊겼다.
`auto` 레벨에서는 두 모델이 우연히 일치해 6개 릴리스 동안 안 드러났고,
레벨을 강제한 첫 순간 깨졌다.

나머지 4건(back-merge 누락 · stage 를 머지 커밋으로 back-merge ·
로컬 stage 미갱신 상태로 main 병합 · `finalize_prerelease.py` 를
읽기 전용으로 오인)도 전부 같은 뿌리다 — 옳은 절차가
[`skills/flow/SKILL.md`](../../../skills/flow/SKILL.md) 에 있는데
**릴리스 의도로는 그 스킬이 안 걸린다.**

## 2. 측정 사실

`github/release.*.workflow.example.yml` 5개 전수:

| 템플릿 | `Release-Level` | `workflow_dispatch` level | `[skip ci]` 가드 |
|---|---|---|---|
| cargo-release | 있음 | **없음** | 있음 |
| gitversion | 있음 | **없음** | 있음 |
| jreleaser | 있음 | **없음** | 있음 |
| python-semantic-release | 있음 | **없음** | 있음 |
| semantic-release (Node) | **없음** | **없음** | 있음 |

결론 3개:

1. `workflow_dispatch` 레벨 입력은 harness-tier 에 **0개**. dispatch 모델은
   vway-kit 것이고 이 저장소에 리더가 없다.
2. `/flow-init` 은 `flow-config.versioning.release_tool` 로
   `.github/workflows/release.yml` **하나만** 렌더한다
   ([flow_init_setup.py:950](../../../scripts/flow_init_setup.py#L950)).
3. 따라서 `/harness-init` + `/flow-init` 만 한 호스트는 **불확실성이 0**이고,
   남는 변수는 하나다 — 레벨을 강제할 수 있나(semantic-release 만 불가).

## 3. 제거하는 중복

초안에 있던 `scripts/release_model.py` 를 **폐기한다**.

- 워크플로 YAML 을 파싱해 모델을 판정하는 것은 `_RELEASE_TEMPLATES` 와
  템플릿 자체가 이미 고정한 사실을 재유도하는 **두 번째 SSOT** 다.
- `dispatch` 판정 분기와 staging-push 타이브레이크는 읽을 워크플로가
  이 저장소에 없다. 순수 vway-kit 수입품.
- "어느 모델이냐"는 AskUserQuestion 은 답이 하나뿐인 질문.

같이 폐기: `tests/release_model/`(현재 빈 `__init__.py` 만 있음), COPY_FILES
논의 전체.

**남기는 판정**: 렌더된 `.github/workflows/release.yml` 한 파일에 grep 1회.
파싱이 아니라 실제 산출물 읽기라 SSOT 가 늘지 않는다.

## 4. `release-commit` 스킬

### 4-1. frontmatter

`description` — model-invoked. `\bUse when\b` 로 시작, 1024자 이내:

> Use when promoting integration to staging or staging to production, cutting a
> release candidate, or finalizing a release — including bare asks like "stage로
> 올려줘", "릴리즈 해", "main 승격", "cut an rc". Reads the host's rendered
> `.github/workflows/release.yml` to learn whether the bump level can be forced,
> then runs the promotion's gates, commit and merge in the order the release CI
> requires. Also use when a promotion produced no release candidate and you need
> to know why.

`allowed-tools` — 정확 규칙만, 경로 glob 로 끝나는 규칙 금지, `${CLAUDE_PLUGIN_ROOT}` 미치환:

```
Bash(grep -c Release-Level .github/workflows/release.yml)
Bash(mkdir -p .claude/harness-tier/.flow)
Bash(touch .claude/harness-tier/.flow/review.done)
Bash(touch .claude/harness-tier/.flow/bump.done)
Bash(touch .claude/harness-tier/.flow/security.done)
Bash(git fetch origin)
```

규칙 하나하나가 **스킬이 실제로 내는 명령과 매치돼야 한다** —
`test_every_allowed_tools_rule_matches_a_command_the_skill_issues` 가 스킬 본문에서
명령을 뽑아 대조한다. 따라서 위 6줄은 전부 본문 펜스 블록에 **그대로** 등장해야 하고,
매치 없는 규칙은 아무것도 허가하지 않는 오타로 실패한다.

`grep -c` 는 **매치 0건에 exit 1** 이다. 그 비영 종료가 곧 "트레일러 없음"이라는
답이고 오류가 아니라는 것을 스킬이 명시한다 — 안 적으면 다음 단계가 실패로 읽는다.

`git commit`·`git merge` 는 일부러 뺀다 — `/flow` 와 같은 이유로 커밋 프롬프트가
게이트 뒤의 기계적 백스톱이다.

### 4-2. 본문 구성

**Step 0 — 호스트 릴리스 모델 확인** (grep 1회):

- `Release-Level` 매치 → 레벨 강제 가능. staging 커밋에 트레일러를 단다.
- 매치 없음 → semantic-release(Node). **레벨 강제 불가**, 결과는 커밋 타입에서
  파생된 값뿐. bump 질문 대신 그 사실을 알리고 진행.
- 파일 없음 → 릴리스 CI 미설치. 중단하고 `/flow-init` 안내.

템플릿에서 렌더된 파일인지는 묻지 않는다. 손으로 쓴 `release.yml` 도 같은 grep 이
같은 답을 준다 — 판정 대상은 템플릿이 아니라 **실제 산출물**이다.

**호스트 커밋 가이드 대조**: `flow-config.commit_guide`
(기본 `docs/operations/commit-versioning-guide.md`)가 있으면 읽는다. 이 문서는 §3 에
**호스트가 어느 bump 전달 방식인지 이미 적게 돼 있다**
([tech-doc-guide.md](../../../skills/harness-authoring/references/tech-doc-guide.md) 섹션 3).
grep 결과와 어긋나면 **실행되는 워크플로가 이긴다** — 어긋남 자체가 가이드 stale 신호이므로
1줄 보고한다. 파일 없음은 정상 답이지 실패가 아니다(`skills/commit/SKILL.md` 와 같은 처리).

**Step 1 — Staging (integration → staging)**

`flow/SKILL.md` Promotion 의 Staging 불릿을 그대로 옮긴다. 순서:
회귀 `review`(자체 diff 쌍 `origin/<staging>..origin/<integration>`) →
추천 레벨 계산 → `AskUserQuestion` major/minor/patch(기본값 = 추천값) → `check-token-write.sh` best-effort →
마커 2개(`review.done` · `bump.done`) → **먼저 병합**
`git merge --no-ff --no-commit origin/<integration>` → `Skill: commit` 에 레벨 전달.

**순서가 뒤바뀌면 트레일러를 잃는다.** CI 는 `git log -1 --pretty=%B` 로 HEAD 하나만 읽는다
([release.yml:81](../../../.github/workflows/release.yml#L81)). 커밋 후 병합하면 HEAD 가
머지 커밋이 되어 트레일러가 안 보이고 auto-derive 로 떨어진다. 실측: 이 저장소의
`Release-Level:` 트레일러는 **전부 머지 커밋**에 있다 (`2a79dec` 부모 `ddc34fe d8b9bc9`,
`c316e36` 부모 `1c2664e 2182ab4` 등). 승격 시점에 워킹트리는 깨끗하므로 병합 전에는
커밋할 것도 없다.

`wiki` 게이트가 승격 커밋을 막으면 여기서 해소한다 — `doc-sync` 는 승격 게이트가
아니라서 터미널 커밋으로 들어온 graph 드리프트가 이 지점에 처음 드러난다.
`wiki_graph.py --build` 후 재생성된 `graph.yaml` 을 승격 커밋에 스테이징.
구조 위반(`wiki_id` 형식·중복 · `title` 누락 · 매달린 `depends_on` · 순환)은
`--build` 로 안 고쳐지고 front matter 를 고쳐야 한다.

**Step 2 — Release (staging → production)**

Staging 게이트 + `/code-review` ultra + `/security-review` → `security.done` →
`git fetch origin` → **fetch 된 `origin/<staging>`** 을 `--no-ff --no-commit` 으로 병합 →
`Skill: commit` 이 그 머지 커밋을 쓴다. 트레일러 없음(finalize 는 결정적).
병합이 먼저인 이유는 Staging 과 같다 — CI 가 HEAD 하나만 읽는다.
회귀 review 는 **자체** diff 쌍 `origin/<production>..origin/<staging>`.

**추천 레벨의 근거 2개** — 초안의 `semantic-release version --print` 단독이 아니다:

1. 커밋 타입 파생값. python-semantic-release·semantic-release 는 스스로 파생한다.
   JReleaser·GitVersion·cargo-release 는 못 하고 트레일러 레벨을 받는다 —
   `scripts/bump_version.py` 는 **주어진 레벨로 다음 버전을 계산**할 뿐 레벨을 파생하지
   않으므로, 그 스택의 추천값은 커밋 타입을 사람이 읽어 정한다.
2. 호스트 커밋 가이드의 **0.x 정책** — 가이드 §2 는 `major_on_zero=false` 와
   "1.0.0 은 명시적 결정으로만"을 싣는다. 0.x 프로젝트에서 `major` 를 고르면
   1.0.0 으로 점프한다고 경고하는 근거가 여기다.

가이드가 없으면 1번만으로 추천한다 — 정상 경로.
**추천일 뿐이고 질문은 항상 한다** (risk-tiers "default = commit-derived, 사용자에게 질문").

**Step 2-1 — PR 모드 승격**

`merge_workflow.pull_request` 가 `promotion` 을 포함하면 대상 브랜치 직접 커밋 대신
PR 을 연다. 게이트 기록은 동일. **반드시 머지 커밋으로** 병합한다 — rebase 는 릴리스를
멈추고 squash 는 히스토리를 파괴한다. 레벨을 강제할 때는 병합 명령에 트레일러를 박는다
(`PR` 은 리터럴 숫자 — `<n>` 을 쓰면 bash 가 리다이렉션으로 읽는다).
`hotfix/*` → production 도 이 모드에서는 PR 이다.

**Step 3 — 종료 상태**

- production → integration back-merge **필수**(`--ff-only`, 안 되면 `--no-ff`)
- **staging 은 back-merge 하지 않는다** — 다음 integration → staging 승격이
  릴리스 커밋을 스스로 실어 나른다 (risk-tiers "Back-merge after release")
- 세 브랜치가 같은 커밋에서 끝난다
- **승격 증거 마커를 지운다** (`review.done` · `bump.done` · `security.done`) —
  마커는 강제 장치이지 도장이라 다음 승격까지 살아남으면 안 된다

**Step 4 — 실패 모드** (0.3.1 에서 실제로 낸 5건, 각 1줄)

1. 승격 병합에 `[skip ci]` → 릴리스 job 자체가 안 돎 → rc 없음. **0.3.1 근본 원인.**
2. fetch 안 한 로컬 staging 병합 → finalize 가 pending rc 를 못 봄 → 버전 오산
3. production → integration back-merge 누락 → 태그 도달 불가 → 다음 버전 오산
4. staging 을 머지 커밋으로 back-merge → 문서가 금지
5. `finalize_prerelease.py` 는 **파일을 쓴다**(`pyproject.toml` ·
   `.claude-plugin/plugin.json`) — 읽기 전용 아님. 로컬 실행 금지.
   `uv.lock` 은 이것이 아니라 CI 의 별도 `chore(release): sync uv.lock` 이 쓴다
6. 승격 후 증거 마커 미정리 → 다음 승격이 남의 `bump.done`·`security.done` 을 자기
   통과 증거로 읽는다. **실측 2026-09-08**: 0.3.1 의 `bump`·`bump.done`·`security.done`
   이 그대로 남아 있었다. 종료 상태에 마커 삭제를 명문화한다

**Never 목록**

- 레벨을 `workflow_dispatch` 로 강제하지 않는다 — 읽는 워크플로가 없다
- 승격 병합에 `[skip ci]` 를 붙이지 않는다
- **재승격은 트레일러 없이** — `version --<level>` 은 base 를 매번 올려
  `X.Y.Z-rc.1` → `X.Y.(Z+1)-rc.1` 로 건너뛴다 (risk-tiers 178-186)

### 4-3. 모노레포 / 멀티 서비스

승격은 **저장소 전체를 한 버전으로** 올린다. 멀티 모듈은 게이트·테스트·배포에서
1급이지만(`modules[]` · `unit_test.jobs[]` · 타깃별 `deploy-<name>.yml`),
`versioning` 블록은 단수라 서비스별 독립 버전을 표현할 슬롯이 없다.
백엔드+프론트 한 저장소는 lockstep 버전 + 타깃별 배포로 정상 동작한다.
스킬은 이 사실을 1문장으로 명시하고, 독립 버전은 비목표로 둔다.

`versioning.version_files` 를 근거로 삼지 않는다 — **어떤 스크립트도 워크플로도
읽지 않는 슬롯**이고, 실제로 파일에 버전을 찍는 것은 릴리스 tool 자체 설정이다.

## 5. `flow/SKILL.md` 축소

- Promotion 섹션(195-283, 88줄) → 포인터 1문단. 남기는 것: 승격은 대상 브랜치의
  커밋에서 게이트되고 티어 마커가 필요 없다는 사실 + `Skill: release-commit` 로 넘김.
- `wiki` 게이트 해소 문단(graph.yaml 재빌드)은 **release-commit 으로 이동** —
  승격에서만 발생한다.
- **frontmatter `description` 에서 승격 문구를 뺀다**: 현재
  "Also applies when promoting integration→staging or staging→production." 가
  남아 있으면 두 스킬이 같은 프롬프트를 두고 경합한다. 이것이 이 스펙이 제거하는
  중복의 핵심이다.

## 6. `rules/risk-tiers.md` 편집

2곳만:

- 12-13행 SSOT 위임 목록에 `/release-commit` 추가 — `hook_assisted: true` 의 근거가
  되는 곳이고, `test_every_skill_the_injected_rule_names_declares_hook_assisted` 가
  이 이름을 읽는다.
- 175행 "`/flow` asks major/minor/patch" → `/release-commit`.

표기 형식이 강제된다: `test_every_skill_the_injected_rule_names_declares_hook_assisted`
가 `hooks/inject-risk-tiers.sh` + `rules/risk-tiers.md` 를 이어 붙여
`/release-commit(?![\w-])` 로 찾는다. 뒤에 단어문자나 하이픈이 붙으면 안 잡히고,
못 잡히면 `hook_assisted: true` 선언이 역방향 검사에서 실패한다.
정책(게이트 목록 · bump 정책 · Merge strategy 표 · back-merge 근거)은 그대로 둔다 —
risk-tiers 가 SSOT 이고 스킬은 절차다.

## 7. evals

**신규 항목 `release-commit`**

- `reached_programmatically: true`, `invoked_by: flow/SKILL.md` — flow 포인터가 부른다
- 자율 발동이 주 경로이므로 `expect_invoke` 목표 0.70(전문가 수준).
  실제값은 구현 시 측정해 기록한다 — 추정치를 baseline 으로 쓰지 않는다.
- `hook_assisted`: risk-tiers 가 `/release-commit` 을 명시하게 되므로 **true**.
  `test_every_skill_the_injected_rule_names_declares_hook_assisted` 가 양방향 검사.

happy (릴리스 역학 그 자체):
- Promote dev to stage.
- Merge stage into main and cut the release.
- The promotion merged but no release candidate was created — why?
- I need to re-promote stage to fold in one more fix. Does the trailer go on again?
- Does this repo force the bump level with a commit trailer or a workflow dispatch?

negative (`commit`·`flow` 와 어휘가 겹치는 것):
- Commit these changes.  ← flow 의 happy
- What Conventional Commits type should this change get?  ← commit 의 happy
- Set up the release workflow for this project.  ← flow-init 영역
- Show me the changelog for the last release.
- Explain what a release candidate is.

**flow 재측정**: description 이 바뀌므로 `evals/run.py` 가 자동으로 다시 잰다.
`Promote dev to stage.`(golden_tier: staging)를 flow 의 happy 에서 빼고
**negative 로 옮긴다** — 이제 release-commit 이 가져가야 맞다.
flow 의 `expect_invoke` 0.80 은 분모가 바뀌므로 재측정 결과로 갱신한다.

**baseline**: `evals/scores.json` 에 `release-commit` 행이 새로 생긴다 —
`evals/run.py` 가 측정하며 쓴다. 손으로 적지 않는다.

**outcome arm**: 진입하지 않는다. `skill_sandbox.py` 시나리오에 `outcome=` 를 달지
않으므로 `outcome_sha` 재측정 없음.

## 8. 테스트

`tests/flow_init/test_render_versioning.py` 에 불변식 1건:

- 모든 `github/release.*.workflow.example.yml` 은 `Release-Level:` sed 줄을 갖거나
  auto-only 명시 목록(`semantic-release`)에 있어야 한다
- 어느 템플릿도 `workflow_dispatch` 에 level 입력을 갖지 않는다

이것이 0.3.1 을 깬 divergence 를 미래 템플릿이 조용히 재도입하는 것을 막는 유일한
장치다. 목록에 없는 새 auto-only 템플릿은 테스트가 실패시켜 결정을 강제한다.

`tests/skills/test_gate_reachability.py` 의 `MUST_STILL_PROMPT` 에 `release-commit`
항목을 추가한다 — 값은 `git merge --no-ff origin/<staging>` 계열 1개.
`git merge` 가 allowed-tools 로 사전 승인되지 않았음을 **주석이 아니라 검사**로 만든다.
이 스킬의 주제가 병합이므로 그 구멍이 가장 비싸다.
같은 파일의 `test_must_still_prompt_literals_track_the_skill_text` 가 스킬 본문에
실제로 그 명령이 있는지 역검증하므로, 문구가 바뀌면 같이 실패한다.

`tests/skills/` 의 나머지는 신규 SKILL.md 를 자동으로 집는다(frontmatter · 링크 ·
영어 본문 · git 명령이 게이트 문법에 읽히는지). 별도 추가 없음.

## 9. 비목표

- 서비스별 독립 버전 — 렌더할 템플릿이 없다
- `versioning.version_files` 를 실제 소비자에 연결하는 것 — 별건
- 커밋 가이드와 렌더된 워크플로의 어긋남을 **자동 수정**하는 것 — 보고만 한다
- `dispatch` 릴리스 모델 지원 — 이 저장소에 리더가 없다
- risk-tiers 의 bump 기본값 정책 · Merge strategy 표 변경
- vway-kit 이식 — 별도 작업

## 10. 커밋

`feat` — consumer-facing `skills/`·`rules/` 변경이라 `docs`/`chore` 금지.
릴리스 게이트로 전파돼야 한다.
