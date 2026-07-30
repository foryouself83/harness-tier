# PR 워크플로 선택 + 순방향 전파 체인 설계

> 서로 독립적인 두 변경을 한 사이클로 묶는다.
> **(1)** 릴리스 후 전파를 `dev → stage → main` 순방향 체인으로 정리하고, 그 전제인
> "승격은 merge"를 게이트로 강제한다.
> **(2)** direct merge / PR 중 무엇을 쓸지를 플러그인이 정하지 않고 **init 시점 선택**으로
> 빼내며, PR 모드에서 잃는 유일한 강제력(머지 전략)을 GitHub Ruleset 으로 되찾는다.

## 배경 / 목적

### (1) 전파 체인 — 근거가 반증된 규칙

현행 [`rules/risk-tiers.md`](../../../rules/risk-tiers.md) "Back-merge after release"는
production → integration **과** staging 양쪽 백머지를 필수로 규정하고, 양쪽에 동일한 근거를
단다: *"안 하면 semantic-release 가 다음 버전을 오산한다(릴리스 태그가 도달 불가)."*

0.1.12 승격이 이 근거를 **stage 에 대해 반증**했다(실측, 재론 불필요):

- 0.1.11 릴리스 후 `main → dev` 백머지(`017e62e`)만 수행되고 `main → stage` 는 누락됐다.
- 결과: 승격 직전 stage(`91ffa99`)에서 `v0.1.11` 태그가 **도달 불가**했고, 그 시점 최근
  도달 태그는 `v0.1.11-rc.1` 이었다.
- 그 상태로 `dev → stage` 승격 머지(`54d75bd`)를 수행 → `v0.1.11` 이 조상으로 편입됐다.
- 릴리스 CI 산출 rc = **`0.1.12-rc.1`** — 오산이 발생하지 않았다.

성립 메커니즘: 승격 때 stage 에 생긴 rc 범프 커밋은 `stage → main` 머지로 main 에 실리고,
`main → dev` 백머지로 다시 dev 에 실린다. 따라서 **stage 는 항상 dev 의 조상으로 유지**되며,
다음 `dev → stage` 는 후손 머지가 되어 버전 파일 충돌이 원리적으로 발생하지 않는다.
`main → dev` 백머지 하나가 체인 전체를 지탱한다.

단, 이 self-heal 은 **승격이 merge 일 때만** 성립한다. rebase 승격이면 릴리스 커밋이 새 SHA 로
재생되어 태그(원본 SHA)가 조상에서 이탈한다. 그런데 현행 머지 전략표(:355)는
`integration → staging` 을 "**Rebase** or Merge"로 열어두고, **같은 파일** :423 은
"integration → staging makes a `--no-ff` merge commit"이라 단정한다 — 내부 모순이며,
이번 변경이 그 모순을 해소한다.

### (2) PR 선택 — 플러그인이 정할 값이 아니다

현행은 direct merge 가 :225 · :264 에 하드코딩되어 있다. 소비자 팀의 git 문화는 갈리는데
플러그인이 한쪽을 강제하고 있다. 이 값은 **host 환경 설정**(`flow-config.yaml`)에 속한다 —
[CLAUDE.md](../../../CLAUDE.md) 의 "Policy vs. environment" 구분 그대로다.

## 스코프

**포함**

- `flow-config` 신규 슬롯 `merge_workflow.pull_request` (리스트: `daily` · `promotion`)
- `/flow-init` 의 슬롯 질문 + GitHub Ruleset **점검·안내** 단계 (읽기 전용)
- `rules/risk-tiers.md`: 머지 전략표 1행 수정 · `### PR workflow` 절 신설 · Back-merge 절 재작성
- `flow-tiers.yaml`: `integration → staging` merge_strategy 행 신설
- `skills/flow/SKILL.md`: 두 모드 분기
- 위 변경에 대한 테스트

**제외 (후속)**

- commit-lint CI 잡 (터미널 커밋까지 덮는 별개 개선 — 아래 "후속")
- `merge_workflow` 이외의 신규 설정 노브

## 무손상 불변식 (반드시 지킬 것)

1. **기본값 `[]` — 기존 호스트 동작 불변.** `/flow-init` Step 2.5 는 example 블록을
   **verbatim 삽입**하므로 example 에 적힌 값이 곧 기존 호스트가 받아드는 값이다.
   `[daily]` 로 두면 슬롯 백필만으로 팀의 워크플로가 조용히 바뀐다.
2. **Ruleset 스크립트는 읽기 전용이며 FAIL-OPEN.** 저장소 설정을 **바꾸지 않는다**. `gh` 부재 ·
   인증 없음 · API 실패 어느 경우에도 경고만 하고 `/flow-init` 을 진행시킨다
   ([`check-token-write.sh`](../../../scripts/check-token-write.sh) 의 exit 10/20 선례).
   읽기 전용이므로 `/flow-init` 멱등성(Invariant #5)은 자명하게 성립한다.
3. **승격 ruleset 안내에는 릴리스 자동화 bypass actor 가 필수.** `allowed_merge_methods` 는
   ruleset 의 `pull_request` 규칙에 딸린 파라미터라 "머지 전 PR 필수"가 함께 켜진다.
   bypass 없이 staging·production 에 걸면 semantic-release 가 직접 push 하는
   `chore(release)` 버전 범프 커밋이 차단되어 **릴리스 파이프라인 전체가 정지**한다.
   이 위험이 큰 만큼 적용 판단은 사람에게 남기고(불변식 2), 스크립트는 경고를 반드시 함께
   출력한다.
4. **SOURCE 만 수정.** `scripts/` · `flow-tiers.yaml` 은 SOURCE 이며 호스트 복사본은 건드리지
   않는다.
5. **소비자 대상 `.md` 는 `feat`/`fix` 커밋.** `docs:` 는 버전 범프를 트리거하지 않아
   전파되지 않는다.

## 아키텍처 — 강제 지점의 레이어 이동

PR 모드는 규율을 **없애는 게 아니라 옮긴다**. 커밋은 PR 모드에서도 로컬에서 만들어지므로
커밋 규율은 전혀 손실되지 않고, 이동하는 것은 **머지 하나**다.

| 규칙 | 강제 지점 | direct | PR |
|---|---|---|---|
| Conventional Commits + 50/72 (작업 커밋) | gitlint `commit-msg` 훅 — 레이어 1 (로컬) | 강제 | **동일하게 강제** |
| 티어 게이트 (review·doc-sync 마커, 미분류 차단) | flow gate PreToolUse on `git commit` — 레이어 2 | 강제 | **동일하게 강제** |
| 머지 전략 (`--squash` / `--no-ff`) | flow gate PreToolUse on `git merge` — 레이어 2 | 강제 (Claude 세션 한정) | **GitHub Ruleset 으로 이동** — 적용 시 전 경로 강제, 미적용 시 규율 |
| 머지 커밋 메시지 (대문자 `Merge`) | 없음 — [`.gitlint`](../../../.gitlint) 이 `ignore-merge-commits=true` | 규율 | 규율 (`gh pr merge --subject/--body` 로 확정 가능) |

3행이 핵심이다. 레이어 2 는 **Claude 세션 머지만** 보는 가장 구멍 많은 층이고, Ruleset 은 웹·CLI·
누구의 머지든 서버에서 막는다. 즉 PR 모드에서 이 규칙의 강제력은 약해지지 않고 **넓어진다**.

## 컴포넌트

### 1. `flow-config.example.yaml` — 신규 슬롯

```yaml
# 작업이 대상 브랜치에 도달하는 방식. 리스트에 든 흐름만 PR 을 거치고 나머지는 직접 머지.
# 빈 리스트(기본) = 전부 직접 머지 — 기존 동작.
#   daily     — feature/* · fix/* → integration
#   promotion — integration → staging, staging → production
# PR 은 로컬 git merge 를 대체하므로 해당 흐름의 merge_strategy 게이트는 발동하지 않는다.
# 대신 GitHub Ruleset 으로 브랜치별 허용 머지 방식을 서버에서 강제하라 — /flow-init 이 현재
# 상태를 점검해 필요한 설정을 안내한다(직접 바꾸지는 않는다).
# 커밋 규율(gitlint · 티어 게이트)은 커밋이 여전히 로컬이므로 PR 모드에서도 그대로 유지된다.
# 승격을 PR 로 돌릴 때 ruleset 에 릴리스 자동화 bypass 가 없으면 chore(release) push 가
# 막혀 릴리스가 정지한다 — 안내에 포함된 bypass 설정을 빠뜨리지 말 것.
merge_workflow:
  pull_request: []
```

슬롯 배관에는 **코드 변경이 없다.** [`flow_init_setup.py`](../../../scripts/flow_init_setup.py)
의 `_diff_missing`(:418-434)이 example↔host 를 재귀 비교하며 최상위 스칼라·리스트 키의 부재도
insertion unit 으로 기록하고, 그 테스트들은 합성 example 을 쓰므로(:490) 실제 슬롯 목록에
결합되어 있지 않다.

### 2. `skills/flow-init/SKILL.md`

**Step 1 (2b) — 슬롯 질문.** `branches` 다음 자리에 `merge_workflow` 항목 추가.
`AskUserQuestion` **multiSelect**("어느 흐름을 PR 로 리뷰받나요?" — 일상 작업 / 승격).
아무것도 고르지 않으면 `[]`. 승격 선택지 설명에 다음을 명시한다: 머지 방식이 merge commit 으로
고정된다는 점, 강제 bump 레벨 사용 시 `Release-Level:` 트레일러가 머지 커밋 본문에 있어야
한다는 점, ruleset bypass 가 함께 설정된다는 점.

**Step 2.7 (신설) — Ruleset 점검.** `merge_workflow.pull_request` 가 비어 있지 않을 때만 실행.
`scripts/check-merge-ruleset.sh` 를 호출하고, 결과 보고를 사용자에게 **그대로 전달**한다
(`check_precommit` 의 "빠진 항목을 보고하고 사람이 추가" 와 같은 자세). `/flow-init` 은 저장소
설정을 바꾸지 않는다.

### 3. `scripts/check-merge-ruleset.sh` (신규)

bash + `gh`. **읽기 전용**이다 — 저장소 설정을 바꾸지 않고, 현재 상태를 읽어 필요한 값과
대조한 뒤 **차이와 적용 방법을 보고**한다. 이 저장소의 일관된 자세를 따른다:
`check_precommit()` 는 기존 파일을 병합하지 않고 빠진 항목을 보고하고, 워크플로 렌더러는
기존 파일을 덮어쓰지 않고 보고하며, [`check-token-write.sh`](../../../scripts/check-token-write.sh)
는 비파괴 프로브로 확인만 한다.

읽기 전용으로 두는 이유는 일관성만이 아니다. 승격 브랜치에 PR 필수 ruleset 을 거는 것은
**되돌리기 어렵고 폭발 반경이 크다** — bypass 를 잘못 잡으면 릴리스 파이프라인이 즉시 정지한다
(불변식 3). 그런 변경의 판단은 저장소 소유자에게 남긴다. 부수 효과로 **드리프트 점검**을 얻는다:
누군가 나중에 ruleset 을 꺼도 다음 `/flow-init` 재실행이 그 사실을 보고한다.

- 입력: 선택된 흐름 목록 + `flow-config.branches` 의 실제 브랜치명
- 흐름별로 **요구되는** 매핑(아래)과 `gh api /repos/{o}/{r}/rulesets` 의 현재 상태를 대조

  | 선택 | 대상 브랜치 | 허용 머지 방식 | 근거 |
  |---|---|---|---|
  | `daily` | integration | `squash` + `rebase` (merge commit 금지) | 표 1행 `feature/*` = Squash, 2행 `fix/*` = Rebase(`--no-ff` 금지) 를 합친 값 — integration 에는 머지 커밋이 생기지 않는다 |
  | `promotion` | staging · production | `merge` 만 | 표 3·4행 = `--no-ff` Merge |

  `daily` 를 `squash` 만으로 좁히면 `fix/*` → integration 의 Rebase 경로가 막힌다. 두 방식을
  모두 허용하되 merge commit 을 배제하는 것이 현행 정책의 정확한 번역이다.

- 승격 ruleset 안내에는 릴리스 자동화 **bypass actor 를 반드시 포함**시킨다 (불변식 3).
  대상 신원은 실제로 push 하는 주체다: `RELEASE_TOKEN` 시크릿이 설정돼 있으면 그 토큰의
  소유자/앱, 미설정이면 fallback 인 `github-actions` 앱
  ([`release.yml`](../../../.github/workflows/release.yml) 의
  `secrets.RELEASE_TOKEN || github.token`). 스크립트는 어느 쪽인지 판별해 안내에 담는다
- 출력: 흐름별로 (a) 현재 허용 머지 방식, (b) 요구되는 값, (c) 차이가 있으면 적용용
  `gh api` 명령과 웹 UI 경로, (d) 승격의 경우 bypass 경고
- 종료 코드: 0 = 요구값과 일치 / 10 = 불일치(안내 출력) / 20 = 도구·인증 부재(조용히 skip).
  **어느 경우에도 `/flow-init` 을 중단시키지 않으며, 어느 경우에도 저장소 설정을 바꾸지 않는다.**
- REST API 필드명(`allowed_merge_methods` 등)은 구현 시점에 **공식 문서로 확인**한다 —
  CLAUDE.md 의 "모델 지식이 아니라 공식 문서를 SSOT 로" 규칙.

### 4. `rules/risk-tiers.md`

| 위치 | 변경 |
|---|---|
| 머지 전략표 :355 | `integration → staging` 을 **`--no-ff` Merge** 로 좁히고 Gate 열 ✅. :423 과의 모순 해소 |
| 신설 `### PR workflow` | 머지 전략표 **아래 조건부 절 하나**. 위 "강제 지점의 레이어 이동" 표 + 흐름별 절차 + ruleset 매핑 + bypass 경고 |
| Back-merge :437-460 | stage 행 삭제, `main → dev` 만 필수. 근거를 "다음 `dev → stage` 승격 머지가 순방향 전파하며, stage 는 그 결과 항상 dev 의 조상으로 유지된다"로 교체 |
| :225 · :264 | "direct merge" → `merge_workflow` 참조 |

**절 분리(모드별 두 벌)나 표 열 추가는 배제한다.** 전자는 승격 규칙을 두 곳에 중복시켜 단일
SSOT 원칙을 깨고, 후자는 승격 3행의 PR 열이 전부 "동일"이라 잡음만 늘린다. risk-tiers.md 는
SessionStart 에 **정적 주입**되어 호스트 설정값을 끼워 넣을 수 없으므로, 두 모드를 조건부로
서술하는 것 외에 선택지가 없다.

### 5. `flow-tiers.yaml` — merge_strategy 행 신설

```yaml
  - source: integration
    target: staging
    require: "--no-ff"
```

`source`/`target` 이 `/` 를 포함하지 않으므로 `flow-config.branches` 의 키로 해석된다
(integration → dev, staging → stage). 기존 행과 source/target 이 겹치지 않아
`match_merge_rule` 의 기존 매칭을 바꾸지 않는다.

### 6. `skills/flow/SKILL.md`

Phase 3 3단계와 Promotion 절이 `merge_workflow.pull_request` 를 읽어 분기한다.

- **direct** (해당 흐름이 리스트에 없음): 현행 그대로
- **PR**: rebase → 통합테스트 human gate(**불변**) → push → `gh pr create` → PR URL 전달 후 종료
- 승격 PR 의 머지 명령을 정확한 형태로 생성한다:

  ```bash
  gh pr merge <n> --merge \
    --subject "Merge stage: release X.Y.Z" \
    --body "Release-Level: patch"
  ```

  `--body` 로 트레일러를 확정하므로 UI 수기 입력에 의존하지 않는다. 자동(도출) 레벨이면
  트레일러 자체가 불필요하다.
- `gh` 부재 시 compare URL 출력으로 폴백 — 차단하지 않는다
- PR 모드에서 **Phase 4 상태 정리는 머지 이후로 미룬다.** 마커는 브랜치 바인딩이므로, 리뷰
  피드백 커밋이 같은 브랜치에 올라올 때 게이트를 통과하려면 마커가 살아 있어야 한다

### 7. 테스트 (선택적 TDD)

- `test_flow_gate_check.py`
  - `test_shipped_policy_integration_to_staging_requires_no_ff` — 배포되는 정책 SSOT 단언
    (`test_shipped_policy_staging_has_bump`(:698) 선례)
  - 러너 통합: staging 브랜치에서 `--no-ff` 없는 `git merge <integration>` → `BLOCK_EXIT_CODE`.
    기존 merge 게이트 테스트가 실제 `flow-tiers.yaml` 을 도그푸딩하므로(:503-506) 같은 방식
- `test_check_merge_ruleset.py` (신규) — `gh` 를 스텁으로 두고 exit 0/10/20 분기 검증 +
  승격 불일치 시 안내에 bypass 항목이 포함되는지 + **어떤 경로에서도 쓰기 API(`POST`/`PUT`/
  `PATCH`)를 호출하지 않는지**. 네트워크 호출 없음 (`test_check_token_write.py` 패턴)
- 슬롯 배관은 신규 테스트 불필요 — `_diff_missing` 테스트가 이미 일반적으로 커버

## 승격 PR 의 머지 방식이 강제되는 이유

[`release.yml`](../../../.github/workflows/release.yml) 두 줄이 규정한다.

- `:23` — `if: !contains(github.event.head_commit.message, '[skip ci]')`
- `:69` — `git log -1 --pretty=%B | sed -nE 's/^Release-Level:...'`

둘 다 **push 된 head 커밋 하나**만 본다. 따라서 승격 PR 을 GitHub 의

- **rebase-merge** 로 머지하면 staging 의 커밋들이 재생되어 head 가
  `chore(release): sync uv.lock [skip ci]` 가 된다 → **릴리스 워크플로가 실행되지 않는다**
- **squash** 로 머지하면 개별 릴리스 커밋 이력이 붕괴한다

merge commit 은 제목이 `Merge pull request #N from …` 으로 대문자 `Merge` 라 gitlint 를
통과하고, `[skip ci]` 가 없어 CI 가 발화한다. 그래서 **merge commit 외에는 선택지가 없다.**
direct 모드에서 `require: --no-ff` 가 하던 역할을 PR 모드에서는 ruleset 이 대신한다.

## 오류 처리

| 상황 | 동작 |
|---|---|
| `gh` 미설치 / 미인증 | exit 20 — 조용히 skip, `/flow-init` 계속 |
| ruleset 이 요구값과 다름 / 없음 | exit 10 — 현재값·요구값·적용 명령 안내, `/flow-init` 계속 |
| ruleset 읽기 API 실패 | 경고 출력, `/flow-init` 계속 |
| `/flow` PR 경로에서 `gh` 부재 | compare URL 출력, 사람이 수동 생성 |

## 문서 (Phase 3 doc-sync 게이트 대상)

- `CLAUDE.md` — "Three verification layers" 서술에 PR 모드의 레이어 이동을 한 줄 반영할지
  doc-sync 가 판정
- `USAGE.md` / `README.md` — `merge_workflow` 슬롯 노출 여부 판정

## 성공 기준

1. `merge_workflow.pull_request` 가 `[]` 인 기존 호스트의 동작이 **바이트 단위로 불변**이다.
2. staging 브랜치에서 `--no-ff` 없는 `git merge <integration>` 이 exit 2 로 차단된다.
3. `/flow-init` 이 PR 선택 시 ruleset 상태를 보고하고, 불일치·권한·도구 부재 어느 경우에도
   **차단 없이** 안내로 끝난다. 저장소 설정은 바뀌지 않는다.
4. 승격 ruleset 을 적용한 뒤에도 릴리스 CI 의 `chore(release)` push 가 성공한다 (bypass).
   — **자동 검증 불가**: harness-tier 자신은 direct 모드로 남으므로 PR 모드를 켠 저장소에서의
   수동 검증 항목이다. 자동 테스트는 스크립트의 **안내 문구에 bypass 항목이 포함되는지**까지만
   덮는다.
5. `rules/risk-tiers.md` 안에서 `integration → staging` 의 머지 방식을 말하는 모든 문장이
   서로 일치한다.
6. 전체 테스트 통과 · ruff clean.

## 후속 (이번 범위 외)

- **commit-lint CI 잡** — push 범위에 gitlint 를 돌려 터미널 커밋·서버 머지 등 레이어 2 를
  우회한 모든 경로를 덮는다. 이번 변경과 독립인 기존 구멍이므로 별도 사이클.
- **`evals/outcome.py` 의 `--add-dir` 워크트리 footgun** — 0.1.12 릴리스 리뷰에서 나온 별건.
