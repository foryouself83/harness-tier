# 머지 전략 게이트 — 설계

- **Date**: 2026-07-20
- **Status**: Approved (brainstorming) → pending implementation plan
- **Scope**: harness-tier 플러그인(`flow-tiers.yaml` 정책 · `precommit-runner.sh` · `flow_gate_check.py` ·
  `rules/risk-tiers.md`) — 강제 범위는 기존 layer-2 flow 게이트와 동일(Claude 세션만)

## 1. 목표

`git merge`가 브랜치 flow별 머지 전략을 지키는지 **게이트로 검사**한다. 지금은 전략이
`risk-tiers.md` 문서에만 있고 어떤 코드도 이를 검사하지 않는다.

## 2. 배경 — 사고와 3중 원인

소비자 저장소에서 AI가 integration 브랜치에 rebase 없이 평범한 merge를 수행했다. 원인 분석:

1. **머지 전략은 게이트가 아니다** — `scripts/` 전체에 `rebase|squash|merge` 매치 0건.
   게이트는 `.done` 마커 존재만 검사한다.
2. **절차서가 "merge" 한 단어** — 자매 저장소 vway-kit의 `vdev/SKILL.md` 3단계가
   `Commit → merge.` 이고 전략표로 가는 링크조차 없다. harness-tier는 커밋 `118a9d4`로
   포인터를 추가했으나 vway-kit에는 미반영(§11 참조).
3. **커밋 게이트는 `git commit`에만 걸린다** — 정확히는 *심사 지점이 없는* 것이 아니라,
   PreToolUse:Bash 훅이 모든 Bash를 보면서 [`precommit-runner.sh:62`](../../../scripts/precommit-runner.sh)
   에서 **스스로 `git commit`만 남기고 버린다**. 신규 인프라 없이 필터 확장으로 접근 가능.

## 3. 결정 사항 (brainstorming)

| 질문 | 결정 |
|------|------|
| 정책 위치 | **`flow-tiers.yaml`의 최상위 `merge_strategy:` 키**(`tiers:`와 형제). 머지 전략은 브랜치 flow의 함수라 티어별 `gates` 리스트와 축이 다르다 |
| `flow-config.yaml`은? | **쓰지 않는다.** `deploy` 블록이 명시한 원칙 "config holds only NON-DERIVABLE values"에 따라, 머지 전략은 브랜치 flow에서 파생되는 정책이라 환경값이 아니다 |
| 옵트아웃 스위치 | **두지 않는다.** [`flow_gate_check.py:376`](../../../scripts/flow_gate_check.py)의 기존 판단 *"we don't put an escape hatch in the code — if we did, the model could use that bypass on its own"* 을 따른다. 이 게이트가 막으려는 주체는 사람이 아니라 **AI**이고, config 스위치는 AI가 쓸 수 있는 우회로가 된다 |
| 끄는 방법 | `merge_strategy` 키 전체를 지우면 검사가 fail-open으로 꺼진다(단 `/flow-init` 재실행 시 부활). 영구 옵트아웃은 `/flow-uninstall` |
| 마이그레이션 | **불필요.** [`flow_init_setup.py:157-160`](../../../scripts/flow_init_setup.py)의 `copy_artifacts`가 `flow-tiers.yaml`을 존재 확인 없이 `shutil.copyfile`로 덮어쓴다. 게이트 스크립트도 같은 함수가 같이 옮기므로 셋이 한 몸으로 움직인다 |
| 판정 엄격도 | **형태 차단 + rebase 경고**(C안). 명령어 문자열로 결정되는 것만 차단하고, 저장소 상태에 의존하는 판정은 경고에 그친다 |
| 차단 메시지 | 위반 **플래그**는 YAML에서 읽어 표시(파생값, 중복 아님), **절차**는 risk-tiers SSOT 섹션명을 가리킨다. 파일 경로는 쓰지 않는다(호스트에 실물이 없고 SessionStart로 주입되므로) |

## 4. 정책 스키마

```yaml
# flow-tiers.yaml — tiers: 와 형제인 최상위 키
# Merge strategy enforcement (branch flow → required/forbidden `git merge` flags).
# Target/source names resolve from flow-config.branches; `*/` patterns match branch prefixes.
# Remove this whole key to disable the check (the gate then fails open).
merge_strategy:
  - source: "feature/*"        # flow-config.branches.feature_prefix
    target: integration
    require: "--squash"
    warn_unless_rebased: true  # 경고만 — 차단하지 않음
  - source: "hotfix/*"
    target: production
    require: "--squash"
  - source: staging            # branches 키로 해석
    target: production
    require: "--no-ff"
  - source: "fix/*"
    target: integration
    forbid: "--no-ff"
```

**리스트 형태를 택한 이유**: `feature_to_integration` 같은 합성 키로 하면 `fix/`·`hotfix/` 접두사가
`flow-config.branches`에 없어(거긴 `feature_prefix`만 있다) 코드에 숨은 기본값이 생긴다. 패턴을
직접 쓰면 정책이 파일 안에서 완결된다.

**`source`/`target` 해석 규칙**: 값에 `/`가 있으면 브랜치 접두사 glob, 없으면
`flow-config.branches`의 키(`integration`/`staging`/`production`)로 해석한다.

**`require`/`forbid`는 플래그 하나짜리 문자열**이다(리스트 아님). 현재 전략표의 어느 행도 플래그를
둘 이상 요구하지 않으므로 단일 값으로 충분하고, 리스트를 받으면 "전부 필요"인지 "하나만 있으면
되는지"라는 해석 문제가 생긴다. 한 규칙에 `require`와 `forbid`를 함께 쓸 수는 있다.

**`warn_unless_rebased`의 판정**은 `git merge-base --is-ancestor <target> <source>` 이다 — source가
target 위로 rebase되어 있으면 target이 source의 조상이 된다. exit 0이면 rebase 완료, non-zero면
경고. 이 명령은 **경고 경로에서만** 실행되며 결과가 차단으로 이어지지 않는다.

## 5. 커버리지 — 6행 중 3행이 결정적

[`risk-tiers.md`](../../../rules/risk-tiers.md) Merge strategy 표에 대한 판정 가능 범위:

| 브랜치 flow | 전략 | 형태 판정 |
|---|---|---|
| `feature/*` → integration | Rebase → Squash | ✅ 차단 (`--squash` 필수) |
| `staging` → production | `--no-ff` Merge | ✅ 차단 (`--no-ff` 필수) |
| `hotfix/*` → production | Squash | ✅ 차단 (`--squash` 필수) |
| `fix/*` → integration | Rebase | △ `--no-ff` 금지만 |
| integration → staging | Rebase **or** Merge | ❌ 판정 불가 |
| production → int/staging | FF **or** `--no-ff` | ❌ 판정 불가 |

**판정 불가 2행은 구현 누락이 아니라 정책의 성질**이다 — "둘 중 아무거나"인 행에는 게이트가 할 일이
없다. 정책의 모호함이 게이트를 붙이려 할 때 드러난 것으로, 나중에 조일지 판단할 근거로 남긴다.

**이번 사고 지점은 1행(✅)이므로 커버된다.**

## 6. 검사 지점 — 커밋 경로를 재사용할 수 없다

`precommit-runner.sh`의 현재 흐름에는 merge를 죽이는 지점이 둘 있다:

```
62      git commit 아니면 → exit 0            ← merge가 여기서 걸러진다
75-85   의존성 FAIL-CLOSED (python3/PyYAML)
101     worktree 재지정
108-109 git status 비었으면 → exit 0          ← 머지 직전엔 트리가 깨끗한 게 정상
113     flow 게이트 (.done 마커)
123     모듈 사전검사
```

특히 **108-109행**: 머지 직전 작업 트리는 비어 있는 것이 정상이므로, 62행 필터만 넓히면 merge는
여기서 조용히 통과한다. 따라서 **분기**가 필요하다. 분기는 의존성 체크 *뒤*에 둔다:

```
1. 명령어 추출 (기존 방식)
2. commit 도 merge 도 아니면          → exit 0
3. 의존성 FAIL-CLOSED (python3/PyYAML)  ← 두 경로 공유
4. ROOT 결정
5. ├ commit → worktree 재지정 → cd → status → 마커 게이트 → 모듈 검사   (기존 경로, 무변경)
   └ merge  → --merge-check 실행 → 종료                                (신규 경로)
```

merge 경로는 `.done` 마커도 모듈 검사도 쓰지 않는다 — 머지는 커밋 게이트를 이미 통과한 결과물을
옮기는 행위다. **의존성 FAIL-CLOSED는 3번에서 공유**한다(python3 없이는 판정 불가이고, 여기서
fail-open하면 게이트가 조용히 꺼진다). 반대로 **worktree 재지정(101행)은 merge 경로에서 쓰지
않는다**(§8).

`git merge` 감지 정규식은 기존 `_commit_re`와 같은 규약을 따른다: `git -C <wt> merge`·`git -c k=v merge`를
포함하고, `merge`를 온전한 단어로 매칭해 `git merge-base`·`git merge-file` 등이 false-positive 되지
않게 한다.

## 7. 판정 로직 (`flow_gate_check.py --merge-check`)

```
1. stdin 훅 JSON → 명령어 추출 (기존 self-filter와 동일한 방식)
2. merge 감지 · 플래그 수집 · 소스 브랜치 추출
3. target = git branch --show-current
4. merge_strategy 규칙을 순회하며 (source, target) 매칭
   ├ 매칭 없음          → exit 0   (FAIL-OPEN)
   ├ require 플래그 누락 → exit 2   ← 차단
   ├ forbid 플래그 존재  → exit 2   ← 차단
   └ 통과
5. warn_unless_rebased 이고 ancestor 아님 → stderr 경고, exit 0
6. merge_strategy 키 부재 / 파싱 실패 / detached HEAD → exit 0 (FAIL-OPEN)
```

판정 재료는 셋뿐이다: **명령어 플래그**(stdin) · **소스 브랜치**(명령어 인자) · **현재 브랜치**
(`git branch --show-current`). 셋 다 `origin` ref 신선도와 무관하므로 오탐이 발생하지 않는다.

## 8. Invariant 영향

**Invariant #1에 세 번째 fail-closed 예외가 추가된다**(기존: 의존성 누락 · 미분류 커밋).
다만 기존 둘과 성질이 다르다:

- 판정 근거가 **명령어 문자열**이라 내부 오류로 오작동할 여지가 없다.
- **저장소 상태를 전혀 읽지 않는다** — ancestor 판정은 경고 경로에만 쓰이고 차단하지 않는다.

Invariant #2(UTF-8)·#3(exit 2 + stderr)은 기존 `deny()`와 `force_utf8_io()`를 그대로 쓴다.
Invariant #4(settings.json에 `if` 필드 없음)는 self-filter 방식을 유지하므로 영향 없다.
Invariant #6(worktree 재지정)은 merge 경로에서 쓰지 않는다 — 머지는 현재 브랜치 기준이고
worktree 재지정은 staged diff·마커 조회를 위한 것이라 merge 판정에는 불필요하다.

## 9. 메시지

차단:

```
harness-tier 게이트 차단: 머지 전략 위반 — 'feature/*' → 'dev' 는 --squash 가 필요합니다.
절차는 risk-tiers 규칙의 "Merging feature/* → integration (integration-test gate)" 절을 따르세요.
```

경고(exit 0 유지):

```
[경고] 머지 전략: 'feature/*' → 'dev' 는 rebase 선행이 요구됩니다.
현재 브랜치가 대상 브랜치 위에 rebase되어 있지 않은 것으로 보입니다(origin ref가 낡았다면 무시하세요).
```

앞 문장의 플래그·요구사항은 `flow-tiers.yaml`에서 읽은 **파생값**이라 정책 변경 시 자동으로 따라간다.
절차는 SSOT를 가리키기만 한다. **각 정보를 자기 SSOT에서 가져오므로 중복이 없다.**

## 10. 문서 반영

- `rules/risk-tiers.md` Merge strategy 표: **게이트가 강제하는 행에 표식 추가**. 정책 내용은
  그대로 두고 "이 행은 자동 검사됨"이라는 별개 사실만 더한다.
- `skills/flow/SKILL.md`: 변경 없음. 차단 메시지가 머지 시점에 SSOT를 가리키므로 절차서에
  명령을 인라인할 필요가 없다(중복만 늘어난다).

## 11. 비목표

- **터미널 직접 머지 차단** — layer-2 게이트는 Claude 세션만 강제한다. CI 안전망은 후속 과제.
- **판정 불가 2행의 강제** — 정책이 "or"인 한 게이트가 할 일이 없다(§5).
- **rebase 미선행 차단** — 경고까지만(§3 C안).
- **자매 저장소 vway-kit 반영** — 별건. 이 저장소와 독립적으로 유지되므로 동일 변경을 별도
  작업으로 옮긴다. 원인 ②(절차서 문구)도 vway-kit에는 아직 미반영 상태다.

## 12. 테스트

`tests/test_flow_gate_check.py`:
- **명령어 파싱**: `git merge X` · `git -C <wt> merge X` · `--squash` · `--no-ff` · `--ff-only` ·
  `git merge-base`(오탐 금지) · `git merge-file`(오탐 금지)
- **규칙 매칭**: 4개 규칙 각각의 차단/통과
- **FAIL-OPEN 경계**: `merge_strategy` 키 없음 · YAML 파싱 실패 · 매칭 규칙 없음 · detached HEAD
- **경고 경로**: rebase 미선행 시 exit 0 유지 + stderr 출력

`tests/test_flow_init_setup.py`:
- `merge_strategy`가 호스트 `config/flow-tiers.yaml`로 복사되는지 1건
