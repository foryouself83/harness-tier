---
name: harness-init
description: 프레임워크를 감지하고 다중 서브에이전트로 최신 컨벤션·무료 기성솔루션을 리서치해 AI 하네스(.md 기본, 실설정 opt-in)를 생성하는 마법사 — 감지→인터뷰→리서치(fan-out)→사유→생성→비판/검증→미리보기→확정→쓰기, 덮어쓰기 없음, 커맨드 미생성
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion, Glob, Grep, Agent, SendMessage, WebSearch, WebFetch, Skill
argument-hint: (none)
disable-model-invocation: true
---

# Harness-Init — AI 하네스 생성 마법사

대상 프로젝트에 맞는 Claude Code 하네스를 다중 에이전트로 생성한다. 산출물은 **.md 기본**이며
실설정(보안 스캐너·CI·폴더 스캐폴딩 등)은 **물어보고 동의 시에만** 적용한다. **커맨드는 생성하지 않는다.**
**규율 SSOT**: [harness-rules.md](../../rules/harness-rules.md) — 읽고 따른다(중복 금지).

## 경로
```bash
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
PLUGIN="${CLAUDE_PLUGIN_ROOT}"
HARNESS_DIR="${ROOT}/.claude/vway-kit/.harness"   # 증거(research/rationale/plan/critic/manifest), gitignored
```
증거는 vway-kit 규약대로 `.claude/vway-kit/.harness/` 한 곳에 모은다(루트 분산 금지):
`research/<agent>_<topic>.md` · `rationale.md` · `plan.json` · `critic-report.json` · `manifest.json`.
첫 쓰기 전 `.gitignore` 에 `.claude/vway-kit/.harness/` 를 **멱등 추가**(이미 있으면 skip).
harness-init 은 vdev 와 독립이므로 자기 증거는 자기가 ignore(vdev-init 의존 금지).

## Step 0 — 검증/감지 (스크립트)
```bash
python3 "${PLUGIN}/scripts/harness_scaffold.py" detect --root "${ROOT}"
```
결과(state/frameworks/existing)를 사용자에게 **표로** 보여준다. vdev 설치
(.claude/vway-kit/config/vdev-config.yaml) 여부도 보고.

## Step 1 — 인터뷰 (AskUserQuestion, 최소하되 범위는 명확히)
0. **개발 범위 명확화 (greenfield/SRS 게이트 — 추측 금지)**: detect 가 greenfield 이거나 SRS 산출물이
   선택되면, **Step 2 리서치·Step 4 SRS 작성 전에** 받은 프롬프트를 파싱해 개발 범위를 확정한다.
   **SRS 필수 슬롯의 공백 + 모호한 항목을 모두** `AskUserQuestion` 으로 묻는다 — **모호 = 측정 불가·복수
   해석·범위 불분명**(예: "빠르게"·"사용자 친화적"). **측정 가능하고 단일 해석이 될 때까지** 묻되 이미
   명확한 건 되묻지 않음(과생성·심문 금지). 필수 슬롯 = 목적 · 목표/비목표(YAGNI 경계) ·
   핵심 기능 요구사항 · 대상 사용자/시나리오 · 핵심 제약(규모·성능·보안·배포 환경). 추가로 **분류 축**
   (도메인 1차·사용자권한/하위영역 2차)과 **깊이(2~3차)** 가 무엇인지도 확정한다(적용 안 되는 축은 SRS 에
   "해당 없음 — 사유"로 남김 — 자세한 규율·구조는 harness-rules 8-1·`tech-doc-guide.md` SRS 절·`srs.template.md`).
   - **게이트**: 범위 공백·모호가 남은 채로 Step 2·Step 4 로 진행하지 않는다. 질문 후에도 미상인 슬롯은
     SRS 에 **"확인 필요"로 명시**하고 절대 지어내지 않는다(harness-rules 4·8-1).
   - 산출 = **범위 요약(scope summary)** → research·rationale·SRS 의 단일 입력원(downstream 단일 출처).
   - **brownfield(SRS 미생성)는 이 게이트를 건너뛴다** — 범위는 code-analyzer 코드 분석으로 삼고, 코드로
     해소되지 않는 의도(목표/비목표 등)만 선택적으로 묻는다.
1. **주 개발 언어 확정(hard gate, harness-rules 참고)**: `AskUserQuestion` 으로 주 개발 언어를
   반드시 확정한다(감지값 무관 항상 질문). 감지 언어가 있으면 첫 옵션(권장), 멀티/미감지면 후보
   나열. 감지값과 사용자 선택이 다르면 **사용자 선택 우선**. **주 언어 ≠ 전 계층 동일 언어** —
   프로젝트를 계층(프런트/백/기타)으로 나누고, 각 계층에서 **더 프로덕션 레디·표준에 가까운
   스택을 권장 1순위**로 제시(가능 시 research 근거), **"전 계층 동일 vs 계층별 분리"를
   `AskUserQuestion` 으로 확인**한다. 결과 = **계층별 언어/스택 맵**(잠정 — Step 2.5 에서 리서치
   발견분으로 reconcile 해 **동결**; 사용자 사인오프는 Step 6; downstream 단일 출처). 아직 안 드러난
   스택을 여기서 추측해 채우지 않는다(인프라가 특히 그렇다 — 모르는 채 일찍 잠그면 누락; 리서치 후
   reconcile 에서 채운다, harness-rules 10-1).
2. 감지 프레임워크/버전 확인(틀리면 정정, 미감지면 입력 요청).
3. 생성 산출물 선택: CLAUDE.md / 룰(baseline 5종 + 프레임워크 컨벤션) / skills / agents /
   기술문서(SRS greenfield·SDS·스택별 code-style·research·onboarding·**성능/통합 SSOT 문서(`docs/performance.md`·`docs/integration.md`)**, 분류별 폴더). **커맨드 선택지 없음.**
4. **실설정 opt-in**: 보안 스캐너 설치·CI 추가·실폴더 스캐폴딩·실제 버전핀 — 각각 물어봄.
   시크릿·인증/인가·입력검증 운영 축은 directive 만으로 끝내지 말고 스캐너 opt-in 을 함께 제안(9-5).
5. 브라운필드 충돌(existing) 항목별: 스킵 / 사용자선택.

## Step 2 — 리서치 (서브에이전트 fan-out, 격리)
**표준**: `Agent`(구 `Task`, alias) 로 `harness-researcher`(웹 컨벤션·BP·안티패턴·무료 기성솔루션) + 브라운필드면
`harness-code-analyzer`(코드베이스 실제 컨벤션·안티패턴·손수구현) 를 **병렬 서브에이전트로 디스패치**한다.
각 서브에이전트는 `.harness/research/*.md` 에 저장하고, 리더가 `Read` 로 팬인해 종합한다.
- **범위 주입**: greenfield/SRS 면 Step 1-0 의 **범위 요약(scope summary)** 을 디스패치 입력에 포함해
  리서치를 실제 요구사항에 한정한다(범위를 추측으로 확장 금지 — 미상 슬롯은 "확인 필요"로 둔 채 조사).
- **운영 관심사 주입**: 리서치 디스패치 시 harness-rules 9-1 체크리스트와 **계층별 언어/스택 맵**을
  전달해, 각 (계층,스택)에서 운영 축별 최신 표준·출처·대안·적용성을 조사하게 한다(9-2~9-4).
- **버전/릴리스 도구 리서치**: 감지 스택의 표준 릴리스 도구(`release_tool`)·`version_files`·0.x 정책을 조사한다(harness-rules 13·13-1).
- **성능·통합 차원 주입**: Step 2.5 reconcile 로 스택이 확정된 뒤, harness-researcher 재디스패치 시
  확정 `stack_map` 을 함께 전달해 절차 9(성능 SSOT·통합 검증 SSOT)를 조사하도록 지시한다.
  조사 결과는 `.harness/research/` 에 저장하고 Step 4 authoring 에서 소비한다.
- **교차대화(옵션)**: Agent Teams 실험 기능(`CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS=1`)이 켜진 빌드에서만
  `SendMessage` 로 교차대화 가능(code-analyzer "손수구현 X 발견" → researcher "무료 대체 조사"). 없으면
  교차대화 없이 병렬 디스패치 → 팬인으로 동작(`TeamCreate`/`TaskCreate` 등은 폐기된 도구라 쓰지 않는다).
- **FAIL-OPEN**: 네트워크/디스패치 실패 시 지어내지 말고 경고 + 「최소 일반구조로 진행 / 중단」 선택.

## Step 2.5 — 스택 인벤토리 reconcile (동결 전 수렴, harness-rules 10-1)
리서치가 드러낸 스택(researcher 자율확장·기성솔루션 후보·스택 호환성 매트릭스 — **인프라 포함**)을
Step 1 의 *잠정* stack_map 에 병합한다. 컨벤션(BP·안티패턴·운영 축)이 실재하는 스택은 컨벤션 대상으로
**승격**한다(reuse 아티팩트로만 끝내지 않음 — 9-6). **새로 승격된 스택은 1차 fan-out 에서 (계층,스택)으로
디스패치되지 않았으므로**, 그 스택만 골라 **타깃 후속 리서치**(researcher 재디스패치, 해당 스택 ops_axes
전수)를 돌려 컨벤션을 채운다. 스택 집합이 **안정될 때까지 반복**(새 승격이 없으면 종료 — 보통 1회).
추측으로 스택을 늘리지 않는다(발견 근거만, FAIL-OPEN 은 "스킵+질문"). 승격/기각 결정·사유는
**authoring(Step 4)이** `docs/sds/README.md` 에 한 줄씩 draft 하고, 다른 산출물과 함께
Step 6 미리보기에서 사용자 확정한다(draft@4 → confirm@6 → write@7; rationale 중복 아님).

## Step 3 — 사유 작성 (rationale)
detect + research + **범위 요약(Step 1-0)** 을 종합해 `${HARNESS_DIR}/rationale.md` 작성: 도메인 분석, **산출물별 생성 사유**,
채택 패턴, BP/안티패턴 요약, **운영 축별 채택 표준+출처+적용성(emit/스킵 사유 포함)**,
**reuse-before-build 권고**(무료·상용가능, 유료 제외), 출처.

## Step 4 — 생성 (authoring 스킬 + scaffold)
컨벤션 대상은 **Step 2.5 reconcile 로 확정된 스택 집합 전체**(승격 인프라 포함) — 초기 stack_map 이
아니다. 각 스택의 구조/상세 컨벤션은 9-3 분리대로 룰·`docs/code-style/<stack>.md` 양쪽에 채운다.
1. `Skill: harness-authoring` 로 templates/ 를 research+rationale+references 로 채운다.
   - 필수 룰 5블록(`references/karpathy-principles.md`·`rule-dry-constants.md`·
     `rule-version-pinning.md`·`security-rule.md`·`rule-reuse-first.md`)을 CLAUDE.md `harness:baseline`
     블록에 주입(각 룰 앵커 `<!-- rule:<key> -->` 보존).
   - 기술문서를 분류별 폴더로 채운다. **SRS 는 범위 요약(Step 1-0)을 SSOT 로** 채우고 미상 슬롯은
     "확인 필요"로 둔다(research 로 메우되 추측 금지). (SRS greenfield→research 편입→SDS(Mermaid)→스택별
     code-style→onboarding→docs/README 순, 출처 링크). research 는 `.harness/research/` 를 정제해
     `docs/research/` 로 먼저 편입하고(SDS·code-style 의 근거), 이후 문서는 출처를
     `docs/research/` 로 링크한다(`.harness/` 참조 금지). 스킬 생성 시 references/examples 보조폴더 동반.
   - vdev 감지 시 프로세스 규율은 risk-tiers defer 노트만 넣고 자체 프로세스 룰 emit 금지.
   - **성능/통합 SSOT 문서**: 확정 스택이 있는 경우에만 `docs/performance.md`·`docs/integration.md`를
     authoring 으로 생성한다. 빈 스택 절 생성 금지. 출처는 `docs/research/` 로 링크.
     (`/performance`·`/integration` 스킬이 이 문서를 우선 소비하고, 부재 시 스킬 내장 references 로 폴백.)
   - **commit-versioning-guide**: `docs/operations/commit-versioning-guide.md` 를 생성한다(Conventional Commits + SemVer + 감지 스택 릴리스 도구 설정; vdev 감지 여부 무관 — harness-rules 13-1·13-2). vdev 감지 시 릴리스 도구 실설정(CI 워크플로 등)은 중복 생성하지 않는다.
2. `plan`(files[]) 을 만들어 `${HARNESS_DIR}/plan.json` 에 저장.

## Step 5 — 비판/검증 (경량, FAIL-OPEN)
1. **결정적 구조검사**:
   ```bash
   python3 "${PLUGIN}/scripts/harness_scaffold.py" validate --root "${ROOT}" --plan "${HARNESS_DIR}/plan.json"
   ```
   (게이트 아님 — high 이슈에도 exit 0. 리포트를 리더가 읽는다.)
2. **품질·정합성 비판**: `harness-critic` 디스패치 → `${HARNESS_DIR}/critic-report.json`.
   `verdict: revise` 면 authoring 으로 돌아가 수정 **최대 2회**. 잔여 이슈는 "미해결"로 명시.

## Step 6 — 미리보기·확정
`plan`(생성/스킵/충돌) + `rationale` + `critic-report` 를 사용자에게 보여주고 확정받는다(확정 전 쓰기 금지).
적용성이 **불확실한 운영 축**은 여기서 `AskUserQuestion` 으로 "포함할지" 확인하고(9-2), greenfield
자동채택 표준은 "권장 기본(변경 가능)"으로 노출해 확정받는다.

## Step 7 — apply (scaffold)
```bash
python3 "${PLUGIN}/scripts/harness_scaffold.py" apply --root "${ROOT}" --plan "${HARNESS_DIR}/plan.json"
```
마커 upsert/부재시 create 만. opt-in 실설정은 기존 파일 자동병합 금지 — 누락분만 안내(.pre-commit-config.yaml 등).

## Step 7.5 — cleanup (편입 사본 정리)
apply 성공 후, docs 로 편입된 중간 사본을 정리한다(재실행/업데이트 시 혼란 방지).
```bash
python3 "${PLUGIN}/scripts/harness_scaffold.py" cleanup --root "${ROOT}"
```
`.harness/research/` 등 편입 사본만 제거하고 증거 메타(`plan.json`·`manifest.json`·
`critic-report.json`·`rationale.md`)는 보존한다(감사/재실행용). **링크 가드**: docs 가
`.harness/research` 를 참조하면 제거를 보류하고 `link_warnings` 로 보고한다(링크 깨짐 방지).
FAIL-OPEN — 정리 실패는 흐름을 막지 않는다. `link_warnings` 가 있으면 보고에 노출한다.

## Step 8 — 보고
생성/스킵/사용자보류 + 출처 URL + critic 결과(`version-compat` 포함) + cleanup 결과(제거/보존) +
후속(스캐너 설치 명령 등)을 **표로** 요약.
`${HARNESS_DIR}/manifest.json` 에 생성내역·프레임워크·출처·critic 결과를 기록(감사/재실행용).
**커밋하지 않는다** — 사용자에게 `/vdev` 로 커밋하라고 안내.

## Critical rules
1. 덮어쓰기 금지 — 마커 upsert/부재시 create 만.
2. 미리보기·확정 전 쓰기 금지.
3. 호스트는 `${CLAUDE_PROJECT_DIR}`, 플러그인은 `${CLAUDE_PLUGIN_ROOT}` 읽기.
4. 커맨드 미생성 — 어떤 산출물도 `.claude/commands/` 에 만들지 않는다.
5. 커밋·머지·PR 규율은 risk-tiers 로 defer(vdev 감지 시).
6. 팀/네트워크 실패는 FAIL-OPEN(경고 + 선택), 지어내지 않는다. 모호하면 질문(Karpathy).
