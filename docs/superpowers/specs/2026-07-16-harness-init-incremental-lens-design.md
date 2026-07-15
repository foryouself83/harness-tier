# harness-init 증분 렌즈 업데이트(code-style 렌즈 갭 채우기) — 설계

- **Date**: 2026-07-16
- **Status**: Approved (brainstorming) → pending implementation plan
- **Scope**: harness-tier 플러그인(소비자에 배포되는 저작 파이프라인·scaffold). 커밋을 강제하지 않음(하네스 산출물 생성 경로).

## 1. 목표

기존 하네스에 **신규 품질 렌즈 BP**(harness-rules [9-7·9-8](../../../rules/harness-rules.md))를
**안전하고 저비용으로** 반영한다. 세 축을 동시에 만족한다:

- **안전** — 사용자가 손댄 문서를 함부로 깨지 않음(현재 no-overwrite 정신 유지).
- **저비용** — 비싼 web research를 "실제로 채울 갭"에만 씀(연타로 전량 재생성 방지).
- **증분** — first-run이든 재실행이든 "빠진 렌즈만" 자연히 채움.

핵심 문제: `docs/code-style/<stack>.md`는 지금 `create` 산출물이라 **존재하면 재실행 시 갱신되지 않는다**
([harness_scaffold.py:839-841](../../../scripts/harness_scaffold.py#L839)) → 렌즈 기능 도입(`ac558e0`) 이전에
하네스를 만든 사용자는 `/harness-init` 재실행만으로는 렌즈를 **받지 못한다**.

## 2. 배경 — 현재 상태

- **렌즈 taxonomy는 방금 도입됨**(`ac558e0`). `code-style/<stack>.md`의 Best Practices를 렌즈로 조직화하되,
  현 템플릿([code-style.template.md](../../../skills/harness-authoring/templates/code-style.template.md))은
  렌즈를 **마커 없는 자유 산문 sub-section**으로 emit한다.
- **apply 동작 두 종류**([apply_plan](../../../scripts/harness_scaffold.py#L830)):
  - `create` — 대상이 **존재하면 conflict(덮어쓰기 없음)**. code-style 독립 문서가 이 방식.
  - `marker_upsert`([upsert_marker_block](../../../scripts/harness_scaffold.py#L547)) — 파일 없으면 create,
    `BEGIN…END` 마커 있으면 **그 사이를 교체**, 마커 없으면 **파일 끝에 append**. CLAUDE.md baseline·
    `<framework>-conventions.md` ops 블록이 이 방식("edits inside are overwritten").
- **manifest.json은 편집감지 SSOT로 부적합** — `.claude/harness-tier/.harness/`(gitignored, per-machine)에
  **harness-init 스킬이** 쓴다([SKILL.md:153](../../../skills/harness-init/SKILL.md#L153)). code-style 문서는
  커밋되지만 manifest는 안 되니, 다른 개발자/클론엔 해시가 없어 편집 비교가 깨진다.

## 3. 결정 사항 (brainstorming)

| 질문 | 결정 |
|------|------|
| 트리거 모델 | **통합 갭 모델** — first-run/재실행 구분 없음. 항상 `갭 = 적용 렌즈 − 현재 present 렌즈`. 첫 실행은 현재=∅이라 갭=전부(=지금 동작). 별도 모드/플래그·취약한 "재실행 판별" 없음 |
| 블록 단위 | **렌즈별 관리 블록** — 렌즈 하나 = 마커 블록 하나. 빠진 렌즈 추가 = 새 블록 insert(기존 블록 무접촉·순수 additive) |
| 편집감지 | **없음(드롭)** — code-style 문서는 git 관리 대상이라 교체가 **git diff에 그대로 드러나고** harness-init은 preview→confirm이라 사용자가 검토·revert. → manifest/마커 sha 둘 다 불필요 |
| flat 레거시 처리 | **`## Best Practices` 섹션 통째 교체** — 옛 자유 산문을 렌즈 블록 구조로 대체(옛 내용은 git 히스토리에 잔존) |
| 스코핑 granularity | **자연 분기** — flat 레거시=**스택 단위**(적용 렌즈 전부 마이그레이션), 렌즈 문서=**렌즈 단위**(빠진 것 add) |
| 스코핑 시점 | **research 전** — 토큰 절약 게이트. 사용자가 고른 것만 dispatch |
| 적용 렌즈 판정 | **경량 인라인 판단**(harness-init 리더) — "이 스택에 어떤 렌즈가 해당되나"(9-2)는 모델 상식으로 싸게. 비싼 research는 **내용 채우기에만** |

## 4. 데이터 모델 — 렌즈별 관리 블록

`docs/code-style/<stack>.md`의 Best Practices를 렌즈별 마커 블록으로 emit한다.

```markdown
## Best Practices (by quality lens)
<!-- code-style:lens:<stack>:performance BEGIN (managed by /harness-init — edits inside are overwritten) -->
### Performance
- ... (source: URL)
<!-- code-style:lens:<stack>:performance END -->
<!-- code-style:lens:<stack>:ux BEGIN (managed by /harness-init — edits inside are overwritten) -->
### UX & user-facing behavior
- 중복 조작 가드: 제출 시 비활성화 + 서버 멱등성(→ Cross-cutting) ... (source: URL)
<!-- code-style:lens:<stack>:ux END -->
```

- `marker_id` = `code-style:lens:<stack>:<lens>` (예: `code-style:lens:typescript-react:ux`). 스택·렌즈로
  유일 → 병렬/재실행에서 충돌 없음.
- 블록 순서 = **9-7 표준 렌즈 순서**(correctness · UX · a11y · performance · security · maintainability ·
  cross-cutting · i18n) → insert 위치 결정적.
- 렌즈 **내용**은 블록 안, `## Best Practices` 헤딩은 블록 밖(고정). 사용자 자유 메모는 블록 밖에 두면 보존.

## 5. 흐름

### 5-1. 탐지 (로컬 스캔 · 토큰 0)

`<stack>.md`를 읽어 문서 상태를 3분류하고 present 렌즈를 마커로 집계:

| 상태 | 판별 | 갭 |
|------|------|-----|
| **없음** (first-run) | 파일 부재 | 적용 렌즈 전부 |
| **flat 레거시** | `## Best Practices` 섹션은 있으나 `code-style:lens:` 마커 없음 | 적용 렌즈 전부(마이그레이션) |
| **렌즈 문서** | `code-style:lens:<stack>:*` 마커 존재 | 적용 렌즈 − present 렌즈 |

- present 판정은 **마커 기준**(헤딩 텍스트 아님). 사용자가 마커 없이 손으로 `### 사용자경험`을 썼다면 스캔은
  UX를 "빠짐"으로 본다 → §5-3 질문에서 사용자가 "이미 있음, 스킵"으로 거른다(불완전 탐지를 human이 흡수).

### 5-2. 적용 렌즈 판정 (경량 · research 아님)

harness-init 리더가 스택 성격으로 적용 렌즈 집합을 인라인 결정(UI 스택→UX·a11y 포함, headless 백엔드→제외
등, 9-2). **web research 팬아웃이 아니다** — 판정은 모델 상식, 비용은 내용 채우기에만.

### 5-3. 업프론트 스코핑 질문 (research 전 · 토큰 게이트)

갭 요약을 표로 제시하고 `AskUserQuestion`으로 무엇을 (재)생성할지 확정:

- **flat 레거시** → **스택 단위** 선택. 고른 스택은 적용 렌즈 전부 대상(부분 선택 불가 — 부분 교체 시 나머지
  렌즈를 다루던 옛 프로즈가 대체 없이 사라지므로 all-or-nothing).
- **렌즈 문서** → **렌즈 단위** 선택(기본=빠진 렌즈; 원하면 기존 렌즈 refresh도 선택 가능).

### 5-4. 스코프드 research

사용자가 확정한 `(stack, lens)`만 harness-researcher(그린필드/웹)·harness-code-analyzer(브라운필드/코드)에
dispatch. 미선택 렌즈는 research도 upsert도 안 함.

### 5-5. 적용 (harness_scaffold 신규 능력)

- **렌즈 문서 · 렌즈 블록 upsert** — 없으면 **`## Best Practices` 섹션 안 9-7 순서 위치에 insert**(파일 끝
  append 아님), refresh면 그 블록만 교체.
- **flat 레거시 · 섹션 통째 교체** — `## Best Practices` 헤딩부터 다음 `##`(또는 EOF) 직전까지를 렌즈 블록
  구조로 대체.

### 5-6. 안전망 — git diff (manifest/sha 제거)

교체·마이그레이션은 harness-init **preview→confirm** + 커밋 시 **git diff + 리뷰 게이트**로 검토한다. 워킹
트리에서 덮여도 git 히스토리에 잔존 → 사용자가 확인·revert 가능. 별도 편집감지 서브시스템 없음.

## 6. 오류 처리 & 엣지 케이스

- **A. flat 부분 선택 금지** — §5-3. flat 문서는 스택 단위 all-lenses만(부분 교체 시 미선택 렌즈의 옛 프로즈
  유실). 렌즈 문서는 additive라 부분 선택 안전.
- **B. `## Best Practices` 헤딩 변이** — `## Best Practices` / `## Best Practices (by quality lens)` 모두를
  **접두 매칭**으로 인식. 그런 헤딩이 아예 없는 비표준 문서 → **스킵 + 경고**(추측 금지, rule 4).
- **C. 불완전 탐지(마커 없는 수기 렌즈)** — §5-1. 마커 기준이라 과대 보고 가능하나, research 전 사용자 확인이
  흡수(과대 보고분은 스킵 선택 → research·쓰기 안 함, 토큰도 절약).
- **D. 블록 밖 사용자 렌즈 산문과 중복** — 사용자가 블록 밖에 자기 성능 메모를 썼는데 Performance 블록도 생기면
  중복. git diff로 노출 → 사용자가 정리(자동 dedup 안 함, YAGNI).
- **E. 마커 손상(`BEGIN` 있고 `END` 없음)** — 기존 upsert가 `ValueError`로 차단(§ [L561-564](../../../scripts/harness_scaffold.py#L561)).
  신규 로직도 동일하게 실패-차단(조용한 오작동 금지).
- **F. no-overwrite 정책과의 관계** — 렌즈 블록은 `marker_upsert`(관리 영역)라 `create`의 no-overwrite와 층이
  다르다. rule 2("Existing files get only marker-block upserts")와 정합 — 문서 자체는 안 덮고 관리 블록만 upsert.
- **G. Invariant 보존** — cp949 UTF-8 방어(`encoding="utf-8"` 유지), preview→confirm→write(rule 1) 불변.
- **H. 렌즈 제거는 비목표** — 적용에서 빠진(더는 해당 없는) 렌즈 블록의 자동 삭제는 안 함(add/refresh만). YAGNI.

## 7. 컴포넌트 & 변경

| # | 파일 | 변경 | 종류 |
|---|------|------|------|
| 1 | [code-style.template.md](../../../skills/harness-authoring/templates/code-style.template.md) | Best Practices를 **렌즈별 관리 블록**으로(방금 머지한 자유산문 렌즈를 마커 블록 형태로 진화). 마커 형식·9-7 순서 명시 | 템플릿 |
| 2 | [harness_scaffold.py](../../../scripts/harness_scaffold.py) | ① 렌즈 마커 스캔·문서 3분류 함수(순수) ② 위치 인식 렌즈 블록 insert(섹션 내 9-7 순서) + flat `## Best Practices` 섹션 통째 교체. 신규 apply action(예: `lens_upsert`) 또는 기존 `marker_upsert` 확장 | 코드 |
| 3 | [harness-init/SKILL.md](../../../skills/harness-init/SKILL.md) | 로컬 스캔 → 적용렌즈 판정(경량) → 갭 스코핑 질문(자연 분기) → 스코프드 dispatch → 렌즈 블록 적용. 통합 갭 모델 서술 | 스킬 |
| 4 | [tech-doc-guide.md](../../../skills/harness-authoring/references/tech-doc-guide.md) | code-style 섹션에 "렌즈 BP = 렌즈별 관리 블록(마커 형식)" 반영 — 저작 스펙이 블록 형태를 알아야 템플릿과 정합 | 저작 가이드 |
| 5 | [test_harness_scaffold.py](../../../tests/test_harness_scaffold.py) | 스캔/3분류, 위치 인식 insert(순서), flat 섹션 통째 교체, 헤딩 변이·비표준 스킵, 마커 손상 차단 | 테스트 |
| — | ~~manifest.json~~ | **변경 없음** — 편집감지 드롭으로 원래 범위에서 제거 | — |
| — | (선택·후속) [critique-guide.md](../../../skills/harness-authoring/references/critique-guide.md) | critic이 렌즈 블록 마커 존재를 확인하도록 — 가벼운 후속, 본 스펙 범위 밖 | — |

- `flow_init_setup.py`: 게이트 스크립트 복사 목록 무관(harness 산출 경로). 변경 불필요.

## 8. 테스트 전략 (selective TDD)

핵심 로직은 `harness_scaffold.py`의 순수 함수라 여기에 단위 테스트를 집중한다(harness-init/템플릿 `.md`는
런타임 코드 아님 → TDD 대상 아님).

1. **스캔·3분류** — 파일 부재/flat(`## Best Practices` 있고 마커 없음)/렌즈문서(마커 존재) 각각 올바른 상태·
   present 렌즈 집합.
2. **위치 인식 insert** — 렌즈 문서에 빠진 렌즈 블록을 **9-7 순서 자리**에 insert(파일 끝 아님), 기존 블록 무변경.
3. **flat 섹션 통째 교체** — `## Best Practices`~다음 `##` 구간만 렌즈 블록으로 대체, 다른 섹션 보존.
4. **헤딩 변이/비표준** — `(by quality lens)` 접미 인식, Best Practices 헤딩 없는 문서 스킵+경고.
5. **마커 손상 차단** — `BEGIN`만 있는 문서에서 `ValueError`.
6. **결정성** — 동일 입력 → 동일 출력(순서·바이트).
7. **정적 분석** — `uv run pytest` 그린, `ruff check && ruff format --check`, `pre-commit` 통과.

## 9. 롤아웃 / 전파

이 레포는 플러그인 자체 → 변경이 자동으로 라이브가 아니다.

1. **`feat`로 릴리스** — consumer의 하네스 생성 동작을 바꾸므로 risk-tiers Commit Discipline상 `feat` 필수
   (`docs`/`chore`는 `plugin.json` version 범프 없어 전파 안 됨).
2. **소비자는 `/harness-init` 재실행** — 이 기능의 사용처 그 자체. 통합 갭 모델이라 기존 하네스에서 재실행하면
   빠진 렌즈를 스코핑 질문 후 채운다.
3. **하위호환** — flat 레거시 문서는 §5 마이그레이션 경로로 흡수. 렌즈 문서는 additive.

## 10. 오픈 항목 / 후속

- **기존 렌즈 내용 refresh 자동화** — 지금은 사용자가 렌즈 문서에서 명시 선택해야 refresh. "낡은 렌즈 자동
  최신화"는 비목표(YAGNI). 필요 시 후속.
- **블록 밖 중복 자동 정리**(§6-D) — 자동 dedup 안 함. 사용자가 git diff로 처리.
- **렌즈 제거**(§6-H) — 더는 해당 없는 렌즈 블록 자동 삭제 미지원.
- **critic 렌즈 블록 검증**(§7 선택) — 가벼운 후속.
