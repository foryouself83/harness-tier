# flow-upgrade 를 flow-init 으로 통합 — 설계

작성일: 2026-06-27
대상: `/flow-init`, `/flow-upgrade` 스킬

## 배경 · 문제

vway-kit 은 호스트 셋업을 두 스킬로 나눠 두었다:

- **flow-init** — 최초 설치 + 재설정(대화형: config 값·webhook·teams 블록·teamer).
- **flow-upgrade** — 플러그인 업데이트 후 호스트 배선 재동기화(비대화, config 무손상).

그러나 둘은 **같은 `flow_init_setup.py` 를 공유**하며, 차이는 SKILL.md 의 대화형 단계
유무뿐이다. flow-init 의 Step 2 가 이미 `flow_init_setup.py` 를 돌려 재동기화(스크립트
재복사·게이트 경로 보정·legacy 이전)를 수행하므로, **flow-init 은 이미 flow-upgrade 의
상위집합**이다.

이 분리는 사용자에게 혼란을 준다: 최초엔 `init`, 이후엔 `upgrade` 를 떠올리지만,
정작 `upgrade` 는 값을 보존한 재설정을 못 하고(비대화·무손상), 재설정하려면 다시
`init` 을 쳐야 한다 — 이름과 기능이 어긋난다.

## 목표

`/flow-upgrade` 를 삭제하고 `/flow-init` 을 **유일한 멱등 진입점**으로 만든다. init 은
config 존재 여부로 분기한다:

- **config 없음(최초)** — 현행 전체 수집(Step 0~4 그대로).
- **config 있음(재실행)** — 재동기화 자동 → 빠진 슬롯 보충 제안 → 재설정 섹션 선택
  (기본: 아무것도 안 함). 아무것도 고르지 않으면 옛 `upgrade` 와 동일한 "재동기화만".

비목표:
- `flow_init_setup.py`(기계적 셋업) 로직 변경 — 이미 공유·재동기화를 수행하므로 그대로 둔다.
- 새 별칭 스킬 생성(예: `/flow-upgrade` 를 init 으로 포워딩) — YAGNI. 문서 안내로 갈음.
- `flow-uninstall` 변경 — 무관(별개 정리 스킬).

## 핵심 동작 — init 재실행 UX

upgrade 의 가치("대화 없이 재동기화만")를 보존한다. init 이 config 존재를 감지하면:

```
config 없음 (최초)   → 현행 전체 수집 (Step 0~4)
config 있음 (재실행) → ① 재동기화 자동 (flow_init_setup.py, 비대화 — 항상)
                      ② 빠진 슬롯 보충 제안 (Step 2.5 — 빠진 게 있을 때만)
                      ③ "재설정할 항목?" 섹션 다중선택 (기본: 없음)
                         → 고른 섹션만 대화형 재설정:
                           - config 값 (branches·test·teamer·review_checklist·doc_sync·contract_test)
                           - Teams webhook URL
                           - CLAUDE.md teams 블록
                           - Teamer 자격증명 안내
```

재실행 시 **재동기화는 질문 없이 끝나고**, 재설정은 opt-in 이다. 현재 Step 1 의
"reconfigure? (default keep)" 단일 질문을 이 섹션 다중선택 메뉴로 확장한다. 아무것도
선택하지 않으면 재동기화 + (해당 시) 슬롯 보충만 수행하고 종료 — 옛 upgrade 와 동일.

## 컴포넌트 변경

### 1. 삭제: `skills/flow-upgrade/SKILL.md`

스킬 파일 제거. `flow_init_setup.py` 는 init 이 계속 쓰므로 유지.

### 2. `skills/flow-init/SKILL.md` 개정

- frontmatter `description` — "최초 설치 + 재실행(재동기화·슬롯 보충·재설정)" 을 모두
  반영하도록 갱신.
- 본문에 **재실행 분기**를 명시: config 존재 시 재동기화 자동 → 슬롯 보충 → 재설정 섹션
  선택(기본 없음). Step 1 의 reconfigure 단일 질문을 섹션 다중선택으로 확장.
- "재설정하려면 `/flow-init`" 같은 자기 참조 문구는 유지(이제 init 이 그 일을 한다).

### 3. 참조 정리 (살아있는 문서만 — 과거 spec/plan 은 historical 이라 제외)

`/flow-upgrade` 를 가리키는 운영 문서를 init 으로 정리한다:

- `README.md` — "플러그인 업데이트 후 `/flow-upgrade`" → "`/flow-init` 재실행". 더불어
  "`/flow-upgrade` 는 `/flow-init` 에 통합됨" 마이그레이션 한 줄.
- `USAGE.md` — 동일.
- `CLAUDE.md` — "플러그인 갱신 후 호스트 사본 동기화는 `/flow-upgrade`" 서술을
  "`/flow-init` 재실행" 으로.
- `scripts/flow_init_setup.py` — docstring 의 upgrade 언급 정리.
- `github/api-contract.workflow.example.yml` — 주석에 언급이 있으면 정리.

## 데이터 흐름 (재실행)

```
/flow-init
  └─ config 존재 감지
        ├─ flow_init_setup.py 실행 (재동기화 — 비대화, 항상)
        │     └─ [config 슬롯 점검] 출력
        ├─ 빠진 슬롯 있으면 → AskUserQuestion(추가?) → verbatim Edit 삽입
        └─ AskUserQuestion("재설정할 항목?", 다중선택, 기본 없음)
              └─ 고른 섹션만 대화형 재설정
```

## 테스트 · 검증

이 변경은 주로 **문서(SKILL.md·운영 문서) + 스킬 파일 삭제**이며, `flow_init_setup.py`
로직은 건드리지 않으므로 기존 `tests/test_flow_init_setup.py` 가 그대로 통과해야 한다
(회귀 가드). 추가 단위 테스트는 불필요(로직 신설 없음).

검증:
- `grep -rn "flow-upgrade" --include=*.md --include=*.py --include=*.yml`
  → 살아있는 문서엔 출력 없음(과거 spec/plan 의 historical 언급만 남음).
- `uv run pytest -q` → 기존 전체 통과.
- `uv run ruff check && uv run ruff format --check` → clean.

## 영향 범위

- 삭제: `skills/flow-upgrade/SKILL.md`
- 개정: `skills/flow-init/SKILL.md`(description + 재실행 분기), `README.md`, `USAGE.md`,
  `CLAUDE.md`, `scripts/flow_init_setup.py`(docstring),
  `github/api-contract.workflow.example.yml`(주석, 있으면)
- 무변경: `flow_init_setup.py` 로직, `flow-uninstall`, `tests/`

## 위험 · 완화

- **기존 사용자가 `/flow-upgrade` 를 침** — 스킬이 없어 동작 안 함. README/USAGE 의
  마이그레이션 한 줄로 안내(별칭 스킬은 YAGNI 로 만들지 않음).
- **재실행 시 재동기화가 빠지는 회귀** — flow_init_setup.py 는 init Step 2 에서 이미
  무조건 실행되므로 보존됨. SKILL 문구에서 "재동기화는 항상 먼저, 비대화" 를 명시해
  대화 단계에 가려지지 않게 한다.
