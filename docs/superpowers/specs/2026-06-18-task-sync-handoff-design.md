# 설계: /task-sync handoff 기능

**날짜:** 2026-06-18
**위험도:** Standard (커맨드·에이전트 로직 변경) → `/flow`로 진행
**상태:** 설계 승인 완료, 구현 계획(writing-plans) 대기

## 1. 목표

`/task-sync` 실행 시, 사람이 작성하거나 AI가 대필한 "인수인계(handoff)" 내용을 설정된 Teamer 필드에 전달한다. config 토글로 켜고 끈다(환경변수처럼). 기존 AI 요약 기능도 handoff의 한 종류로 일반화하여, 동일 메커니즘으로 처리한다.

핵심 설계 원칙:

- **일반화**: 기존 item_content AI 요약 = `handoff.summary` 종류. 특수 예약 코드 분기 없음.
- **두 축 분리**: `instruction`(무엇을 담을지)과 `template`(어떤 구조로 출력할지)을 분리.
- **하위호환**: 기존 `flow-config.yaml` 사용자 무중단.
- **이중 경로 아키텍처 준수**: 템플릿은 플러그인 소유 읽기 자원, 호스트가 오버라이드 가능.

## 2. config 스키마

`flow-config.yaml`(호스트 소유·gitignored) 에 `handoff` 트리를 추가한다. `flow-tiers.yaml`(정책·불변)이 아니라 환경값이다.

```yaml
handoff:
  summary:                         # 기존 AI 요약 — template만 있는 종류
    enable: true
    author: AI
    AskUserQuestion: false
    field: item_content            # append
    template: handoff/summary.html # 기존 3섹션 요약 구조를 파일로 추출
  qa:                              # 신규 종류 (확장 지점: 추후 ops/security 동일 패턴)
    enable: true
    author: AI
    AskUserQuestion: true
    field: col22                   # colXX → replace
    instruction: "QA 인수인계 — 테스트 범위, 재현 절차, 리스크 포인트"
    template: handoff/qa.html      # 선택 (없으면 일반 HTML div 래핑)
```

### 필드 정의

| 필드 | 필수 | 의미 |
|------|------|------|
| `enable` | O | 종류 토글. `false`/미정의 시 처리하지 않음 |
| `author` | O | `AI`/`LLM`/`Agent`(대소문자 무시) 중 하나면 "AI 주체"(대필), 그 외는 사람 이름(메타데이터) |
| `AskUserQuestion` | O | 최우선 토글. `true`면 실행 시점에 AskUserQuestion으로 입력/지침을 받음 |
| `field` | O | 작성 대상 Teamer 필드. `item_content`면 append, `colXX`면 replace |
| `instruction` | 선택 | 내용 지침(겸용). 아래 "출처 결정 로직" 참조 |
| `template` | 선택 | 출력 형식/구조 정의 파일. 아래 "템플릿 경로 해석" 참조 |

- `instruction`·`template`은 둘 다 선택적이며 종류마다 자유 조합한다.
- 특수 예약 종류명 분기는 없다. `summary`는 단지 "template만 있는 종류"이다.

## 3. 출처 결정 로직

`author`가 `AI`/`LLM`/`Agent`(대소문자 무시) 중 하나면 "AI 주체", 아니면 "사람 이름"으로 본다. `AskUserQuestion`이 최우선 토글이다. 종류마다 독립 적용한다.

| author | AskUserQuestion | 내용 출처 |
|--------|----------------|----------|
| AI | true | AskUserQuestion으로 **작성 지침**을 묻고, AI가 task 문서 + config(`instruction`·`template`) + 받은 지침으로 작성 |
| AI | false | AI가 task 문서 기반 **자동 생성**, config(`instruction`·`template`) 적용 — 기존 summary 동작(template만 있는 종류) |
| 사람 | true | AskUserQuestion **즉석 입력 내용을 그대로** content에 |
| 사람 | false | task 문서 `## Handoff (<종류>)`의 **Content를 그대로** 읽음 |

`instruction`·`template`은 둘 다 선택적이다. AI 대필 시 `instruction`만 있으면 내용 지침으로, `template`만 있으면(예: summary) 그 구조로 task 문서를 작성, 둘 다 있으면 함께 적용한다.

### instruction / template의 역할

| 필드 | author=AI일 때 | author=사람일 때 |
|------|---------------|-----------------|
| `instruction` | 대필 프롬프트로 전달 | task 문서 섹션 안내 주석(`<!-- ... -->`)으로 재활용 |
| `template` | 이 파일 구조대로 작성 | (참고용 형식 가이드) |

## 4. 템플릿 경로 해석 (이중 경로 준수)

- 내장 템플릿(summary 등)은 플러그인 SOURCE `templates/handoff/`에 동봉하고 `${CLAUDE_PLUGIN_ROOT}`에서 읽는다.
- config `template` 값:
  - **생략** → `templates/handoff/<종류명>.html` 자동 탐색(내장 종류면 히트), 없으면 일반 HTML div fallback.
  - **명시** → 호스트(`${CLAUDE_PROJECT_DIR}`) 우선 탐색 후 플러그인 fallback → 호스트가 커스텀/오버라이드 가능.
- 스크립트 전파 단방향 원칙 유지: 내장 템플릿의 SSOT는 플러그인 SOURCE. 호스트 사본을 직접 고치지 않는다.
- summary 템플릿(`templates/handoff/summary.html`)은 기존 `task-sync.md`의 3섹션 요약 HTML 구조(Implementation/Verification/Notes, atomic `<li>` 규칙)를 그대로 담는다 → 회귀 위험 0.

## 5. 데이터 흐름 (`/task-sync` 단계 변경)

기존 흐름(① task 문서 → AI 요약 → ② GET → ③ PUT)에 handoff 처리를 일반화하여 삽입한다.

1. task 문서 로드
2. **handoff 처리** — `flow-config.handoff.*` 중 `enable:true`인 종류를 순회:
   - 각 종류마다 §3 매트릭스로 내용 생성 (instruction·template·출처 적용)
   - HTML div + `Author: <author> (YYYY-MM-DD)` 마커로 래핑
   - `field`로 분류: `item_content`면 **append 큐**, `colXX`면 **replace 맵**
3. teamer-api-searcher로 GET (colXX non-null 전부 보존 — Invariant #6)
4. teamer-item-updater 호출:
   - `item_content`: 기존 GET값 + (append 큐) — summary가 여기 들어감
   - `col_overrides`: `{col22: "<qa html>"}` — GET 보존값 위에 덮어쓸 필드만
5. 워크플로 상태 전이는 기존 그대로 (handoff와 독립)

## 6. teamer-item-updater 확장

- 신규 optional 파라미터 `col_overrides`(맵): GET 보존값 위에 명시 colXX를 새 값으로 **replace**.
- 기존 `item_content` append 규칙·colXX 보존·UTF-8 multipart(Node `https`)·인증·정리 전부 유지. Invariant #6 준수.
- 커맨드가 오케스트레이션(config·출처 로직), 에이전트는 순수 API 실행 — 기존 관심사 분리 패턴 유지.

## 7. /task-import 템플릿 변경

task-import가 `flow-config.handoff`를 읽어, **"문서에서 읽는 종류"**(author=사람 AND AskUserQuestion=false)에 대해서만 스켈레톤 섹션을 추가한다:

```markdown
## Handoff (QA)
**Author:** [작성 주체]
**Content:**
<!-- {instruction 값이 있으면 안내로 삽입} -->
```

- AI 대필·AskUserQuestion 종류는 문서 섹션이 불필요하므로 생략한다(YAGNI).

## 8. 하위호환 (회귀 위험 차단)

- `handoff` 섹션 또는 `handoff.summary`가 **없으면** → 기존 동작(AI 요약을 item_content에 append) 그대로. summary는 암묵 ON.
- `handoff.qa` 등 신규 종류는 명시해야만 동작(미정의 시 OFF).
- 기존 `flow-config.yaml` 사용자는 무중단.
- `flow-config.example.yaml`에 주석 포함 `handoff` 템플릿을 추가한다.

## 9. 검증

- 위험도 Standard → `/flow`로 진행.
- summary 회귀 0: 템플릿 파일이 기존 요약 구조를 그대로 담는다. 기존 산출물과 동일한지 대조 검증.
- 커맨드/에이전트는 마크다운 지침이라 직접 단위 테스트 불가 → 수동 검증 경로를 plan에 명시.
- 순수 로직(출처 분기·col_overrides 병합·경로 해석)을 Python 스크립트로 뗄지 여부는 plan에서 결정. 기존 task-sync가 순수 지침 기반이라 일관성상 지침 유지가 유력.

## 10. 영향 받는 파일

| 파일 | 변경 |
|------|------|
| `commands/task-sync.md` | handoff 순회·출처 로직·col_overrides 전달 추가 |
| `commands/task-import.md` | 사람-작성 종류 섹션 스캐폴드 |
| `agents/teamer-item-updater.md` | `col_overrides` 파라미터 추가 |
| `flow-config.example.yaml` | `handoff` 트리 템플릿 추가 |
| `templates/handoff/summary.html` (신규) | 기존 요약 구조 추출 |
| `tests/` | 순수 로직 스크립트화 시 테스트 (plan에서 결정) |

## 11. writing-plans에서 확정할 사항

- 템플릿 경로 해석의 정확한 구현(생략 시 탐색 순서, 명시 시 호스트/플러그인 fallback 규칙).
- 출처 로직·col_overrides 병합을 스크립트화할지 vs 커맨드 지침으로만 둘지.
- AskUserQuestion=true 시 실제 질문 문구(지침 받기 / 즉석 입력).
- colXX HTML 렌더링 가정 검증(Teamer가 colXX를 HTML로 렌더하는지) — 미확인 시 plan에 수동 확인 단계 포함.
- 수동 검증 경로(실제 Teamer item으로 summary 회귀 + qa replace 확인).
