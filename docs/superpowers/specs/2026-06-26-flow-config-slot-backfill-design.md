# flow-config 슬롯 보충 (slot backfill) — 설계

작성일: 2026-06-26
대상: `/flow-init` 의 flow-config.yaml 재설정 경로

## 배경 · 문제

`flow-config.yaml` 은 호스트 소유·팀 공유 설정이다. 플러그인이 진화하면
`flow-config.example.yaml`(SSOT)에 새 슬롯이 추가되는데, 기존 호스트가 그 값을
**기존 값·주석을 보존한 채** 받을 경로가 사실상 없다:

- **flow-upgrade** — 설계상 config 무손상. handoff 새 종류조차 "보고만" 한다.
- **flow-init Step 1** — host config 가 있으면 `keep` vs `reconfigure` 이분법이고,
  `reconfigure` 는 모든 슬롯을 **처음부터 다시 입력**해 기존 값이 날아갈 위험이 있다.

유일한 부분 머지는 handoff 종류 동기화(Step 2.5)뿐이며, 이 "없는 것만 채우기"
패턴이 `handoff:` 섹션에만 적용되고 `test.coverage_threshold`·`contract_test` 같은
다른 슬롯에는 없다.

PyYAML 라운드트립은 팀 주석/포맷을 파괴하므로(코드 전반의 경고) 자동 덤프 머지는
쓸 수 없다 — handoff 동기화가 Edit 기반 verbatim 삽입을 쓰는 이유다.

## 목표

`/flow-init` 재설정 시 flow-config 를 **전체 재구성하지 않고**, example 과 재귀
비교해 **호스트에 빠진 슬롯만** example verbatim(주석·기본값째) 삽입한다. 기존
handoff 동기화를 이 일반 메커니즘으로 흡수한다.

비목표:
- flow-upgrade 가 config 를 쓰게 만들지 않는다(여전히 보고만, 무손상).
- 기존 값 변경(reconfigure)은 별개 동작으로 남긴다(전체 재입력 옵션 유지).
- ruamel.yaml 등 새 의존성을 추가하지 않는다.

## 핵심 동작 재정의

flow-init Step 1(host config 존재 시)은 keep/reconfigure 이분법을 유지한다:

1. host config 가 있으면 keep vs reconfigure 만 묻는다. keep → Step 2 로 건너뜀(파일
   재작성 없음). reconfigure → 사용자가 원하는 슬롯 값만 편집(전체 재입력 아님).
2. **빠진 슬롯 보충은 Step 2.5** — Step 2 스크립트가 `[config 슬롯 점검]` 블록으로
   빠진 슬롯을 식별한 뒤, Claude 가 AskUserQuestion → example verbatim Edit 삽입.
3. "빠짐" 판단 = 키 부재만. 값이 비어 있어도 키가 존재하면 건드리지 않는다.

**"빠짐" 판단 = 키 부재만.** 값이 비어 있어도(예: `service_docs: ""`) 키가 존재하면
사용자가 의도적으로 비운 것으로 보고 건드리지 않는다. 키 자체가 없을 때만 빠진 슬롯이다.

## 컴포넌트

### 1. `missing_config_slots(host, plugin) -> list[dict]` (flow_init_setup.py 신규)

- `_load_yaml_safe` 로 example·host 를 읽어(읽기 전용) **재귀 비교**.
- 각 빠진 슬롯을 **삽입 단위**로 반환 — host 에 부모는 있으나 해당 키가 없는 가장
  얕은 지점:
  - host 에 `contract_test` 없음 → `{"path": ["contract_test"], "parent": []}`
    (최상위 섹션 통째)
  - host 에 `test:` 있고 `coverage_threshold` 없음 →
    `{"path": ["test", "coverage_threshold"], "parent": ["test"]}`
- 반환 항목 필드: `path`(키 경로 리스트), `parent`(삽입 앵커 경로), `label`(표시용
  점 경로 문자열, 예 `test.coverage_threshold`).
- example 등장 순서를 보존한다(재현 가능한 보고/삽입 순서).

재귀 규칙: 양쪽이 dict 인 키는 더 내려가고, host 에 없는 키를 만나면 그 지점을 삽입
단위로 기록(그 하위는 더 내려가지 않음 — 부모 블록 통째로 들어가므로). host 쪽이
dict 가 아니면(스칼라/리스트) 더 내려가지 않는다.

### 2. handoff 흡수

기존 `missing_handoff_kinds` / `report_missing_handoff` 는 이 일반 함수의 특수
케이스(`parent == ["handoff"]`)이므로 제거하고 `missing_config_slots` /
`report_missing_config_slots` 로 대체한다. `run_setup` 의 `[handoff 종류 점검]`
출력 블록은 `[config 슬롯 점검]` 으로 일반화한다.

### 3. flow-init SKILL (대화형 Claude — verbatim Edit)

Step 1 은 keep/reconfigure 이분법 유지. 슬롯 보충은 Step 2.5 로:

Step 1 (host config 존재 시):
- keep → Step 2 로 건너뜀(파일 재작성 없음).
- reconfigure → 사용자가 원하는 슬롯 값만 편집. 전체 재입력 없음.

Step 2.5 (슬롯 보충 — Step 2 스크립트 실행 후):
1. 스크립트가 `[config 슬롯 점검]` 블록으로 빠진 슬롯 목록을 출력(식별만).
2. 빠진 슬롯이 있으면 `AskUserQuestion`("새 슬롯 N개(<목록>) 추가?", 전체/일부, 기본
   전체).
3. 수락한 슬롯마다: Claude 가 `flow-config.example.yaml` 에서 해당 블록을 **주석째
   verbatim** 읽어, host config 의 **parent 앵커 위치(부모 섹션 끝)**에 **Edit 삽입**.
   parent 가 비면(최상위) 파일의 적절한 위치에 섹션을 추가한다.
4. 삽입 후 "값을 환경에 맞게 조정하라" 안내. `enable` 류는 example 그대로 둔다
   (handoff 는 `enable: false` 유지 → 사용자가 켜기 전엔 아무것도 동작하지 않음).

### 4. flow-upgrade SKILL

동작 변경 없음(여전히 보고만, config 무손상). `[handoff 종류 점검]` 보고 라벨만
`[config 슬롯 점검]` 으로 일반화(공유 report 함수 사용).

## 데이터 흐름

```
flow-init Step 1 (host config 존재)
  └─ keep → Step 2 로 건너뜀 (파일 재작성 없음)
  └─ reconfigure → 원하는 슬롯 값만 편집

flow-init Step 2 (스크립트)
  └─ python3 flow_init_setup.py  →  run_setup
        └─ [config 슬롯 점검]  ← report_missing_config_slots(missing_config_slots(...))

flow-init Step 2.5 (host config 존재 시 슬롯 보충)
  └─ Claude: 빠진 슬롯 있으면 AskUserQuestion(전체/일부)
        └─ 수락 슬롯마다 example 블록 verbatim → host config Edit 삽입(parent 앵커)
        └─ 값 조정 안내
```

## 테스트 (test_flow_init_setup.py)

`missing_config_slots` 단위 테스트:
- 최상위 섹션 빠짐 → 그 섹션을 `parent: []` 로 식별.
- 기존 섹션의 하위 키 빠짐 → 키 + `parent` 식별.
- 값이 비어도(`key: ""`/`null`) 키가 있으면 제외.
- example == host → 빈 목록.
- 깊은 중첩(handoff 종류, `parent: ["handoff"]`) 식별 — 기존 handoff 케이스 보존.
- example 등장 순서 보존.
- host config 부재·빈 config·파싱 실패 → example 최상위 전부 반환(신규 설치 동등); example 부재 → 빈 목록.

기존 handoff 관련 테스트는 일반 함수 기준으로 갱신하되 동치 케이스를 보존한다.

## 영향 범위

- `scripts/flow_init_setup.py` — `missing_config_slots` /
  `report_missing_config_slots` 신규, `missing_handoff_kinds` /
  `report_missing_handoff` 제거(흡수), `run_setup` 보고 라벨 변경.
- `skills/flow-init/SKILL.md` — Step 1 keep/reconfigure 이분법 유지, Step 2.5 → 일반 슬롯 보충 단계.
- `skills/flow-upgrade/SKILL.md` — 보고 라벨 일반화(동작 무변경).
- `tests/test_flow_init_setup.py` — 신규/갱신 테스트.

## 위험 · 완화

- **깊은(3단계+) 중첩 Edit anchoring 신뢰성** — 스크립트가 삽입 단위·parent 를
  명시하므로 1~2단계는 안정적. 더 깊은 중첩은 부모 블록 통째 삽입으로 환원되어
  anchoring 면이 줄어든다.
- **handoff 회귀** — 흡수 시 기존 동치 테스트 케이스를 보존해 회귀를 막는다.
