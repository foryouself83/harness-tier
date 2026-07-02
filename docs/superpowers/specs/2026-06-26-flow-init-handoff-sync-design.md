# flow-init handoff 종류 동기화 — 설계 문서

- 작성일: 2026-06-26
- 브랜치: `feature/flow-init-handoff-sync`
- 상태: 설계 승인됨, 구현 계획 대기

## 배경

플러그인의 `flow-config.example.yaml` 에 새 handoff 종류(예: `done_flag`·`done_date`)가
추가돼도, **이미 `/flow-init` 을 적용한 기존 호스트에는 반영되지 않는다.** 근본 원인은
`flow-config.yaml` 이 **호스트 소유·팀 공유** 파일이라 플러그인이 함부로 덮어쓰지
못하게 설계된 데 있다. 그 보호 원칙이 두 경로 모두에서 "새 종류를 채울지 묻는 중간
단계"를 없앴다:

- **flow-init** Step 1 ([flow-init/SKILL.md](../../../skills/flow-init/SKILL.md) 93-94):
  config 가 이미 있으면 "**전체** reconfigure 할래?"만 묻고, keep 이면 Step 2 로 skip.
  "전부 재설정" 아니면 "아무것도 안 함"의 이분법 — 빠진 종류만 추가하는 경로가 없다.
- **flow-upgrade** ([flow-upgrade/SKILL.md](../../../skills/flow-upgrade/SKILL.md)):
  config 를 **절대 안 건드림**(critical rule). `allowed-tools` 도 Bash/Read 뿐이라
  AskUserQuestion 자체가 불가.

그 결과 새 handoff 종류가 example 에 생겨도 **"이거 추가할까?"라고 물어볼 지점이
아예 없다.** (참고: `value`/`append` 같은 **기능 코드**는 플러그인이라 flow-upgrade 로
전파된다. 안 따라오는 것은 example 의 새 handoff 종류를 호스트 config 에 반영하는
것뿐이다.)

## 목표

example 에만 있고 호스트 config 에 없는 handoff 종류를 감지해:

- **flow-upgrade**(비대화형): 감지 결과를 **안내만** 한다("N개 있음 — `/flow-init`
  으로 추가 검토"). config 무접촉 규율 유지.
- **flow-init**(대화형): 빠진 종류가 있으면 **AskUserQuestion 으로 추가 여부를 묻고**,
  동의 시 example 블록을 호스트 config 에 삽입한다(주석·`enable:false` 보존).

비목표(YAGNI — 이번 범위 제외):

- handoff 외 섹션(branches·test·review_checklist 등)의 일반 동기화.
- 기존 종류 **내부**의 새 키(value·append 등) 동기화 — 종류(top-level kind) 단위만.
- 자동 활성화: 삽입은 항상 `enable:false` 로(사용자가 검토 후 켠다). 자동으로 켜면
  사용자가 모르는 채 Teamer 에 새 필드가 써질 위험.
- 스크립트가 YAML 을 파싱→재작성하는 자동 병합(주석/포맷 파괴 — vway 원칙 위반).

## 설계

### 컴포넌트 역할 분담

```
flow_init_setup.py  (스크립트, 읽기 전용 비교)
  └─ missing_handoff_kinds(plugin, host) → ["done_flag", "done_date", ...]
  └─ run_setup 보고에 "[handoff 종류 점검]" 블록 추가

flow-upgrade  (비대화형, Bash/Read)
  └─ run_setup 보고를 relay → 빠진 종류 있으면 "/flow-init 으로 추가 검토" 안내

flow-init  (대화형, Write/Edit/AskUserQuestion)
  └─ 빠진 종류 감지 시 AskUserQuestion("추가할까?")
  └─ 동의 시 example 블록을 호스트 flow-config.yaml 의 handoff: 에 Edit 삽입
```

### 1. 비교 함수 (스크립트, 순수 함수)

`scripts/flow_init_setup.py` 에 추가:

```python
def missing_handoff_kinds(plugin: Path, host: Path) -> list[str]:
    """example 에 있고 호스트 config 에 없는 handoff 종류 키를 반환.
    호스트에 handoff 섹션이 없으면 example 종류 전부. 파싱 실패/파일 부재는
    빈 목록(FAIL-OPEN — 안내를 막지 않는다)."""
```

- example = `plugin / "flow-config.example.yaml"`, host = `config_path(host)`.
- 둘 다 PyYAML 로 **읽기만**(비교용 — 쓰기 아님이라 주석 파괴 무관).
- example 의 `handoff` dict 키 − 호스트 `handoff` dict 키. 순서는 example 등장 순 보존.
- 어느 쪽이든 파싱 실패·파일 부재·`handoff` 부재는 안전하게 처리(example 없음/빈 → [],
  host handoff 없음 → example 종류 전부).

`run_setup` 에 보고 블록 추가(`render_workflow` 뒤 등 적절한 위치):

```python
    print("[handoff 종류 점검]")
    for line in report_missing_handoff(host, plugin):
        print(line)
```

`report_missing_handoff` 는 `missing_handoff_kinds` 를 호출해 사람이 읽을 보고를
만든다 — 빠진 종류가 없으면 `[=] ...최신(skip)`, 있으면 `[i] example 에 새 종류 N개:
<목록> → /flow-init 으로 추가 검토` 형태.

### 2. flow-upgrade — 안내만

별도 코드 변경 없음. `run_setup` 의 새 보고 블록이 자동으로 출력되므로, flow-upgrade
SKILL 의 보고 relay 설명에 "handoff 종류 점검(새 종류 안내)" 항목을 한 줄 추가하고,
critical rule 의 "config 무접촉"은 그대로 둔다(감지·안내는 무접촉).

### 3. flow-init — 동의 후 삽입

flow-init SKILL 의 **Step 2 직후**에 새 하위 단계를 추가한다(빠진 종류는 Step 2 의
스크립트 보고로 알게 되므로 그 다음이 자연스럽다):

- Step 2 의 `[handoff 종류 점검]` 보고에 빠진 handoff 종류가 있으면:
  1. `AskUserQuestion`: "example 에 새 handoff 종류 N개(<목록>)가 있습니다. 호스트
     config 에 추가할까요?"(다중 선택으로 종류별 선택 허용 가능, 기본은 전체).
  2. 동의한 종류에 대해, `${PLUGIN}/flow-config.example.yaml` 에서 해당 종류 블록을
     읽어 **그대로**(주석·`enable:false` 포함) 호스트 `flow-config.yaml` 의 `handoff:`
     섹션에 **Edit 로 삽입**. 호스트에 `handoff:` 섹션이 없으면 섹션째 추가.
  3. 삽입 후 "값(field/value 등)을 환경에 맞게 조정하고 `enable:true` 로 켜라"고 안내.
- 삽입은 **flow-init 의 Claude 가 Edit** 로 한다(위치·들여쓰기 판단, 주석 보존). 스크립트
  자동 재작성 아님.

## 데이터 흐름

```
flow-config.example.yaml (handoff.*)   호스트 flow-config.yaml (handoff.*)
        │                                       │
        └──────────► missing_handoff_kinds ◄────┘
                          │
            ┌─────────────┴──────────────┐
       flow-upgrade                  flow-init
       (보고 relay·안내)         (AskUserQuestion → 동의 종류
                                  example 블록 Edit 삽입, enable:false)
```

## 엣지 케이스

- **호스트 config 파싱 실패/부재**: `missing_handoff_kinds` → [](FAIL-OPEN). 점검이
  설치를 막지 않는다.
- **호스트에 handoff 섹션 없음**(구버전 config): example 종류 전부 missing 으로 보고.
  flow-init 삽입 시 `handoff:` 섹션째 추가.
- **example 에 handoff 없음/빈**: missing = [] → "최신(skip)".
- **빠진 종류 0개**: 보고는 skip 한 줄, flow-init 은 AskUserQuestion 띄우지 않음.
- **사용자가 일부만 선택**: 선택한 종류만 삽입, 나머지는 다음 실행에서 다시 안내됨(멱등).
- **이미 같은 종류가 호스트에 있음**: missing 에 안 잡히므로 중복 삽입 없음.

## 테스트

- `tests/test_flow_init_setup.py`
  - `missing_handoff_kinds`: example 에만 있는 종류를 반환(등장 순 보존)
  - 호스트에 handoff 섹션 없음 → example 종류 전부 반환
  - 호스트가 모든 종류 보유 → [] 반환
  - host/example 파싱 실패·부재 → [](FAIL-OPEN)
  - example 에 handoff 없음 → [] 반환
- (`report_missing_handoff` 가 분리되면) 빠짐 있음/없음 보고 문자열 분기

## 하위호환

- 빠진 종류가 0이면 보고 한 줄 외 동작 변화 없음(기존 flow-init·flow-upgrade 흐름 유지).
- config 무접촉 규율: flow-upgrade 는 여전히 호스트 config 를 쓰지 않는다(감지만).
- 삽입은 flow-init 에서 **사용자 동의가 있을 때만**, `enable:false` 로(자동 활성화 없음).
