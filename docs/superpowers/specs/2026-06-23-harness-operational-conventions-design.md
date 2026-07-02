# harness-init 운영 컨벤션 생성 — 설계 spec

- 날짜: 2026-06-23
- 상태: 설계 확정(구현 계획 대기)
- 대상: `/harness-init` · `harness-authoring` · `harness-researcher`/`harness-code-analyzer`/`harness-critic` 에이전트 · `rules/harness-rules.md` · `scripts/harness_scaffold.py`

## 1. 배경 / 문제

`/harness-init` 은 대상 프로젝트의 스택을 감지해 AI 하네스(.md 룰/문서)를 생성한다.
현재는 baseline 룰 5종 + `<framework>-conventions.md` + `docs/code-style/<stack>.md`(BP·안티패턴·툴체인)
+ 기술문서를 만든다. 그러나 **서버/백엔드에서 운영에 필요한 cross-cutting 관심사**(에러 처리,
디버깅용 로깅, 시크릿/설정, 관측성 등)가 산출물에 **체계적으로·표준에 맞게** 들어간다는 보장이 없다.
특히 디버깅용 로깅 규칙처럼 "코딩할 때마다 따라야 하는" 운영 컨벤션이 누락된다.

목표: 감지된 스택에서 **운영 관심사를 누락 없이 검토**하고, 해당 스택에 존재하는 관심사는
**현재 권장 표준에 맞춰** 컨벤션으로 생성한다. 언어/프레임워크 무관.

## 2. 비판 검토 결과 (설계 제약)

적대적 비평을 거쳐 초기안의 치명/중대 결함을 반영했다. 핵심 제약:

- **표준 단정 금지 준수** — [harness-authoring SKILL](../../../skills/harness-authoring/SKILL.md) 의
  "특정 라이브러리/표준을 근거 없이 박지 않는다" 와 충돌하지 않아야 한다. → greenfield 에서 구체
  표준은 **룰이 아니라 문서**에 권장+대안으로.
- **리스크 비례 / lean 준수** — [risk-tiers.md](../../../rules/risk-tiers.md) 의 제1원칙. → "무조건 emit"
  금지. **커버리지는 필수이되 emit 은 증거 기반**.
- **새 마커블록 도입 금지** — 기존 `<framework>-conventions.md`(룰) + `docs/code-style/<stack>.md`(문서)
  로 충분. CLAUDE.md 본문 비대화·재생성 덮어쓰기 충돌을 피한다.
- **강제 착시 금지** — 룰은 게이트가 아니라 컨텍스트다. 보안성 축은 컨텍스트 한 줄로 끝내지 말고
  기존 opt-in 실설정(스캐너) 제안으로 연결한다.

## 3. 핵심 설계

### 3.1 분류 — "directive 는 룰, 살은 문서"

기존 SSOT 분리([tech-doc-guide.md](../../../skills/harness-authoring/references/tech-doc-guide.md))를
그대로 재사용한다. 새 분류 모델을 만들지 않는다.

| 위치 | 내용 | 출처 |
| --- | --- | --- |
| `.claude/rules/<framework>-conventions.md` 의 "운영 컨벤션" 절 | 운영 directive 1~3줄 + 문서 링크 | (문서를 가리킴) |
| `docs/code-style/<stack>.md` 의 "운영 관심사" 섹션 | 표준 상세·레벨/매핑·안티패턴·예제·대안 | **출처 URL 소유(SSOT)** |

예:

```
# .claude/rules/<framework>-conventions.md  (운영 컨벤션 절)
- 에러: 프로젝트 에러 표준을 따른다 → docs/code-style/<stack>.md#error-handling
- 로깅: 레벨 규칙 + 디버깅 컨텍스트를 구조적으로, 시크릿 금지 → …#logging

# docs/code-style/<stack>.md  (운영 관심사 섹션)
## error-handling
  - 채택 표준: RFC-9457 problem+json (필수 필드 type/title/status/detail/instance)
  - status 매핑 · 안티패턴(스택트레이스 노출 금지)
  - 출처: <RFC-9457 URL>   · 대안: <단순 JSON 봉투 등>
```

- 룰은 **항상 로드**(framework-conventions 는 기존 로드 경로). 살은 on-demand 문서.
- 출처는 **문서가 소유**하고 룰은 링크만(reuse-first: 스펙을 베끼지 말고 가리킨다).
- 룰↔문서 같은 사실 중복 금지(한 사실 한 곳).

### 3.2 운영 관심사 체크리스트 (커버리지 필수, 열린 목록)

`rules/harness-rules.md` 에 **SSOT 로 신규 명시**한다(하드코딩 아님 — 유지보수 가능, 언어무관 *관심사 축*).

흔한 출발 축(닫힌 floor 아님, 열린 체크리스트):

- 에러/예외 처리
- 로깅(디버깅 지향) — 레벨 규칙, 디버깅 컨텍스트, 구조적/검색가능, 시크릿/PII 금지
- 설정·시크릿·env
- 관측성(메트릭/트레이싱)
- 헬스체크/레디니스
- 그레이스풀 셧다운
- 입력 검증
- 인증·인가
- 재시도/타임아웃·서킷브레이커
- 데이터 마이그레이션/스키마 진화
- rate limiting

researcher 는 스택 특성상 더 필요한 축을 **자율 추가**한다(열린 목록).

### 3.3 emit 정책 — 커버리지 필수, emit 은 증거 기반

- researcher/code-analyzer 는 체크리스트 **전수 검토(누락 금지)**.
- 각 축은 그 스택에 **관심사가 실재할 때만 emit**(정적 사이트에 헬스체크/셧다운 강제 금지).
- 적용성 **불확실** 시 → 지어내지 말고 Step 6 미리보기에서 **사용자에게 질문**.
- 서버/백엔드 스택이면 대부분 축이 실재하므로 사실상 다 emit 된다.
- FAIL-OPEN 방향: 불확실은 "일단 생성"이 아니라 "스킵 + 질문"으로 흐른다(과생성 방지).

### 3.4 표준 선택 — 단정 회피

- **brownfield**: `harness-code-analyzer` 가 코드에서 실제 사용하는 표준을 감지 → directive(룰) +
  문서. 근거가 있으므로 구체 표준을 명시해도 단정 금지에 안 걸린다.
- **greenfield/미확정**: `harness-researcher` 가 **현재 권장 최신 표준을 검색해 자동 채택**(묻지 않음).
  단 **구체 표준명은 문서에** "권장(변경 가능) + 출처 + 대안"으로 기록하고, **룰에는 카테고리
  directive 만** 둔다 → "표준 단정 금지" 위반 회피.
- 모든 표준은 **출처 URL 필수**(없으면 "출처 미확인").
- "현재 권장 도구" 원칙(tech-doc-guide) 준수 — 학습된 과거 표준이 아니라 research 가 확인한 현재 권장.

### 3.5 보안성 축은 실설정 승격 경로로 연결

시크릿·인증/인가·입력 검증처럼 강제력이 필요한 축은 directive 한 줄로 끝내지 않는다.
[harness-init Step 1 의 실설정 opt-in](../../../skills/harness-init/SKILL.md) 을 재사용해
secret scanner·linter 등 **실제 게이트로 승격을 제안**한다(동의 시에만 적용). "정책"이라는
강제 착시를 피하고, 진짜 강제는 탐지 가능한 도구로 보낸다.

### 3.6 결정적 가드

`scripts/harness_scaffold.py` 의 `validate` 에 **운영 directive 라인 수 상한**(항목당 ≤ 3줄,
초과 시 high) 을 추가한다. "룰에 살이 새어듦"을 critic 의 주관 판정이 아니라 결정적 검사로 잡는다.

### 3.7 주 개발 언어 확정 (인터뷰 hard gate)

**문제:** 감지(detect)에만 의존하면 언어를 조용히 오판한다(예: 자바 프로젝트인데 프롬프트 누락으로
다른 언어로 산출물 생성). 언어는 모든 운영 표준·code-style·researcher 조사의 입력이라, 틀리면 전체가
어긋난다.

**규율:** Step 1 인터뷰에서 **주 개발 언어를 `AskUserQuestion` 으로 반드시 확정**한다(감지값에
무관하게 항상 질문). 감지된 언어가 있으면 **첫 옵션(권장)** 으로 제시하고, 멀티언어/미감지면 후보를
나열한다. 감지값과 사용자 선택이 다르면 **사용자 선택을 우선**한다. (보조 언어가 있으면 다중 선택
허용 — 단 주 언어는 하나로 명시.)

**주 언어 ≠ 전 계층 동일 언어:** 주 언어를 골랐다고 프런트엔드·백엔드(및 기타 컴포넌트)를 **모두 그
언어로 할 필요는 없다**. 명시적으로 다음을 따른다:

1. **계층 식별** — 프로젝트 구성을 계층(프런트엔드·백엔드·기타)으로 나눈다(detect/PRD/research 기반).
2. **계층별 스택 추천 — 프로덕션 레디·표준 우선** — 각 계층에서 **더 프로덕션 레디이고 표준에 가까운
   언어/스택을 먼저 추천**한다. 주 언어가 그 계층에 적합하면 주 언어를, 부적합하면(예: 웹 프런트엔드)
   더 적합한 언어를 **권장 1순위**로 제시한다. 추천은 가능한 한 research 근거를 달고(표준 단정 금지),
   최종은 사용자가 확정한다.
3. **동일/분리 확인** — **프런트·백을 모두 주 언어로 할지, 계층별로 다른 언어로 할지 `AskUserQuestion`
   으로 확인**한다(추천 스택을 기본값으로).

**결과(단일 출처):** 확정된 **계층별 언어/스택 맵**이 downstream 의 입력이 된다 — researcher 는
(계층, 스택)별로 조사하고, `docs/code-style/<stack>.md` 는 스택별로 분리되며(이미 tech-doc-guide
규율), 운영 표준(§3.2~3.4)도 (계층, 스택)별로 선택된다.

## 4. 파이프라인 통합 (영향 파일)

1. `rules/harness-rules.md` — 운영 관심사 체크리스트(§3.2) + emit 규율(§3.3) + directive=룰/표준=문서
   분리(§3.1) + 표준 자동채택 규율(§3.4) 을 SSOT 로 신규 명시.
2. `harness-researcher` 에이전트(정의 위치: 플러그인 `agents/`) — 체크리스트 전수 검토 + 각 축의
   최신 표준·출처·대안·적용성 조사하도록 프롬프트 확장.
3. `harness-code-analyzer` 에이전트 — brownfield 에서 각 축의 실제 사용 표준/부재를 file:line 으로 보고.
4. `skills/harness-authoring/references/tech-doc-guide.md` — `docs/code-style/<stack>.md` 에 "운영 관심사"
   섹션 규율 추가(축별 채택표준·출처 필수·대안).
5. `skills/harness-authoring/SKILL.md` — directive(룰)/표준(문서) 분리 작성 규율 + framework-conventions
   에 "운영 컨벤션" 절을 채우는 절차.
6. `skills/harness-init/SKILL.md` — Step 1 인터뷰에 **주 개발 언어 `AskUserQuestion` 확정(hard gate,
   §3.7)** 추가, Step 2 리서치에 체크리스트 주입, Step 3 rationale 에 "축별 채택 표준+출처+적용성"
   기록, Step 6 미리보기에 "적용 불확실 축" 질문 분기, Step 5 보안축 opt-in 연결.
7. `harness-critic` 에이전트 — 검증 추가: 체크리스트 커버리지 누락 / directive 가 짧은지(전문 베끼기
   아님) / 문서 출처 유무 / 룰↔문서 중복 / 보안축 opt-in 연결 여부.
8. `scripts/harness_scaffold.py` `validate` — 운영 directive 라인 수 상한 가드(§3.6) + 관련 테스트
   (`tests/test_harness_scaffold.py`).

## 5. 안 하는 것 (YAGNI / 안전)

- 새 `harness:policies` 마커블록 ✗ — 기존 룰/문서 재사용.
- greenfield 에서 구체 표준을 관리 룰블록에 단정 ✗ — 문서에 권장+대안으로만.
- 적용성 없는 스택에 운영 축 강제 ✗.
- 게이트(`settings.json`) 변경 ✗ — 룰은 컨텍스트, 강제는 risk-tiers/pre-commit 책임.
- 커맨드 생성 ✗.

## 6. 성공 기준

- Step 1 에서 주 개발 언어가 `AskUserQuestion` 으로 확정되고, 사용자 선택이 감지값보다 우선해
  downstream 산출물 언어를 결정한다(언어 오판 재발 방지).
- 계층별(프런트/백/기타) 스택이 프로덕션 레디·표준 우선으로 추천되고, "전 계층 동일 언어 vs 계층별
  분리"가 사용자에게 확인되어 **계층별 언어/스택 맵**으로 확정된다(주 언어 강제 적용 방지).
- 서버/백엔드 스택에서 harness-init 산출물이 체크리스트 운영 축을 **누락 없이 검토**하고, 실재 축마다
  directive(룰) + 표준 상세(문서, 출처 포함)를 생성한다.
- 정적 사이트/CLI/라이브러리 등 비해당 스택에 운영 축이 강제로 박히지 않는다(불확실 시 질문).
- greenfield 산출물이 "표준 단정 금지"를 위반하지 않는다(구체 표준은 문서, 룰엔 카테고리).
- 운영 directive 룰이 항목당 ≤ 3줄로 유지된다(validate 가드).
- harness-critic 이 커버리지 누락·출처 부재·룰↔문서 중복을 잡는다.

## 7. 미해결 / 후속

- 체크리스트 축 명칭/입도의 최종 합의는 구현 시 harness-rules.md 에서 확정한다.
- 관측성(메트릭/트레이싱) 축과 에러 리포팅 축의 중복 여부는 researcher 가 스택별로 판단(중복이면 통합).
