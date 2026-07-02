# handoff 필드 값 채우기 — `value`/`append` 확장 설계 문서

- 작성일: 2026-06-26
- 브랜치: `feature/handoff-append-flag`
- 상태: 설계 승인됨, 구현 계획 대기

## 배경

`flow-config.yaml` 의 `handoff` 트리는 종류별로 "어떤 Teamer 필드에 / 무슨 값을"
넣을지 선언한다. `/task-sync` 가 enable 된 모든 종류의 내용을 생성해 **한 번의 PUT**
으로 Teamer 아이템에 반영한다(이 "모든 항목 동시 반영"은 이미 동작한다 —
[task-sync/SKILL.md](../../../skills/task-sync/SKILL.md) 3·4·5·8단계).

값에는 **독립된 두 축**이 있는데, 현재는 둘 다 사용자가 제어할 수 없다.

1. **무슨 값을 넣나(source)** — 지금은 AI 생성 / 사용자 입력 / 문서 발췌뿐이다.
   "완료" 같은 **고정 리터럴**이나 **오늘 날짜** 같은 자동값을 넣을 수단이 없다.
   AI 가 "완료"를 만들 이유가 없고, 매번 사용자에게 입력받는 것은 번거롭다.
2. **어떻게 넣나(mode)** — write_mode 가 `field` 종류에 자동으로 묶여 있다
   (`item_content`→append, `colXX`→replace). 같은 필드라도 누적/교체를 선택할 수
   없고, colXX 누적은 불가능하다. `scripts/handoff_resolve.py` 의
   `resolve_write_mode(field)` 가 이 고정 규칙을 구현한다.

## 목표

handoff 각 종류에 두 키를 추가한다:

- **`value`** (선택) — 고정 리터럴 또는 자동 날짜 토큰. 있으면 그 값을 **그대로**
  해당 필드에 쓴다(AI·template·입력 불필요).
- **`append`** (선택, 불리언) — 누적(true)/교체(false)를 명시 선택. 모든 필드에
  일관 적용.

기존 config 는 변경 없이 그대로 동작한다(하위호환).

비목표(YAGNI — 이번 범위 제외):

- 워크플로 상태 칸(`itemWorkflowStatusNo`) 전이의 handoff 통합 — 이름→번호 변환이
  필요한 특수 케이스라 분리. "특정 colXX 필드에 '완료' 텍스트 넣기"(value)와는
  다르다. 필요해지면 별도 spec.
- `${today}` 외 날짜 토큰(`${now}`, 형식 지정 등)·산술 토큰. 우선 `${today}`
  (YYYY-MM-DD) 하나만.
- 한 필드에 여러 종류가 매핑될 때의 정교한 병합 정책(아래 "엣지 케이스" 참조 —
  단순 규칙만 둔다).

## 설계

### config 모양

```yaml
handoff:
  summary:                 # 기존 — AI 생성 + template 포장 (변화 없음)
    enable: true
    field: item_content
    author: AI
    template: handoff/summary.html
    append: true           # 누적 (명시)
  qa:                      # 기존 — 사용자 입력, colXX 교체
    enable: true
    field: col22
    author: AI
    AskUserQuestion: true
    append: false          # 교체 (명시)
  done_flag:               # 신규 — 고정 리터럴
    enable: true
    field: col31
    value: "완료"          # 그대로, 래핑·template 없음
    append: false
  done_date:               # 신규 — 자동 날짜
    enable: true
    field: col30
    value: "${today}"      # 실행일(YYYY-MM-DD)로 치환
    append: false
  progress_log:            # 신규 — colXX 누적
    enable: true
    field: col33
    append: true           # colXX 에 누적 ← 신규 지원
```

### 동작 규칙

**source — 무슨 값을 넣나**

- `value` 가 있으면 그 종류의 source 는 **고정값(literal)** 이 된다.
  - `author`/`AskUserQuestion`/`template`/`instruction` 은 **무시**된다.
  - **HTML 래핑(Author div)을 하지 않는다** — 날짜·플래그 필드에 마크업이 섞이면
    Teamer 필드 타입이 깨진다. 순수 값만 들어간다.
  - **토큰 치환**: `${today}` → 실행일 `YYYY-MM-DD`. 그 외 문자열은 리터럴 그대로.
- `value` 가 없으면 기존 source_mode (`ai_auto`/`ai_guided`/`human_ask`/`human_doc`)
  를 그대로 따른다 — template 포장 + Author div 래핑.

**mode — 어떻게 넣나**

- `append: true` → 기존 값(GET 으로 읽은 현재 칸) 뒤에 이어붙임
- `append: false` → 통째로 교체
- **미지정 시 기본값** → `field == item_content` 면 `true`, 그 외(colXX) 면 `false`
  (= 현재 동작 보존)
- value 종류에도 동일 적용(보통 날짜·플래그는 `append: false`).

**불변**: enable 된 모든 종류가 한 PUT 에 함께 반영되는 동작은 유지.

### 변경 지점

#### 1. `scripts/handoff_resolve.py`

- `resolve_source_mode` 를 확장: spec 에 `value` 가 있으면 다른 무엇보다 우선해
  `"literal"` 을 반환한다(author/AskUserQuestion 무시).
- `resolve_write_mode` 를 확장: spec 의 `append` 플래그를 받아 명시되면 그 값
  (`true→append`, `false→replace`), 없으면 field 기반 폴백(`item_content→append`,
  else→replace).
- `resolve_handoff` 결과 dict 에 `value` 키(원문, 토큰 치환 전)를 추가하고,
  기존 `source_mode`·`write_mode` 키는 의미를 유지한다(소비자 호환).
- 토큰 치환은 여기서 하지 않는다 — 순수 함수 유지(날짜 의존 배제, 테스트 가능성).
  치환은 task-sync 단계 책임. keyring·HTTP 무의존.

#### 2. `scripts/teamer_api.py`

- **colXX append 지원**을 추가한다. 현재 `_build_put_fields` 는 col_override 를
  무조건 replace 한다([teamer_api.py](../../../scripts/teamer_api.py) 241-242).
  append 모드 colXX 는 GET 으로 보존한 기존 값 뒤에 새 값을 이어붙인다.
- 누적 로직은 신규 작성하지 않고 기존 `append_item_content(existing, new)` 를
  **재사용**(일반화)한다 — reuse-before-build.
- CLI 에 colXX append 용 **별도 인자** `--col-append col33=<path>` 를 추가한다
  (append). 기존 `--col-override col22=<path>` 는 replace 로 그대로 유지(하위호환).
  모드를 경로 문자열에 섞지 않는 이유: `col=path:append` 같은 형태는 Windows 경로
  `C:\Users\...` 의 콜론과 충돌해 파싱이 깨진다. 인자를 분리하면 `_parse_col_overrides`
  의 `partition("=")` 파싱을 건드리지 않고 append 맵만 따로 만든다.
- value 자체는 teamer_api 변경을 거의 요구하지 않는다 — task-sync 가 치환된 순수
  값을 임시 파일에 써서 기존 `--col-override`/`--col-append`(또는 item_content)
  경로로 그대로 넘긴다.
- 불변식 보존: UTF-8 multipart(Python urllib), 필드 보존, status 해석 내부 처리,
  비밀 redact, 입력 이상 시 안전 처리.

#### 3. `skills/task-sync/SKILL.md`

- 4단계(내용 생성)에 **literal source** 분기를 추가한다: `source_mode == "literal"`
  이면 AI·AskUserQuestion·template 을 건너뛰고 `value` 를 사용한다. `${today}` 를
  실행일(`YYYY-MM-DD`)로 치환하고, **Author div 래핑 없이** 순수 값을 그대로 둔다.
- 5단계(field/write_mode 분류)에서 각 종류의 append 결정을 update 인자
  (`--col-override` replace / `--col-append` append / item_content)로 전달한다.
- 8단계 호출 예시를 colXX append 와 value 를 표현할 수 있게 업데이트한다.

### 데이터 흐름

```
flow-config.yaml (handoff.*.{value,append})
  → handoff_resolve.py: resolve_handoff
       → [{kind, field, source_mode(value 시 "literal"), write_mode, value, ...}]
  → task-sync (커맨드):
       literal 이면 ${today} 치환·래핑 없이 value 사용 / 아니면 기존 생성·래핑
       write_mode 로 인자 조립(--col-override / --col-append / content-file)
  → teamer_api.py update: GET 보존 → 필드별 append/replace 적용 → 단일 multipart PUT
```

## 엣지 케이스

- **`value` 와 template/instruction 동시 지정**: `value` 우선(literal). 나머지 무시.
- **`value` 에 HTML/마크업 문자열**: 그대로 들어간다(래핑만 안 할 뿐, 내용 검증은
  안 함). 날짜·플래그 필드라면 사용자가 순수 값을 넣을 책임.
- **`${today}` 외 미지원 토큰**: 치환하지 않고 리터럴 그대로 둔다(관대 처리).
- **같은 field 에 여러 종류 매핑**: 단순 규칙 — resolve 순서대로 처리. append 들은
  순서대로 이어붙이고, replace 가 섞이면 마지막 값이 이긴다. 복잡한 충돌 해소는
  비목표(설정 실수로 간주).
- **append: true 인데 기존 값이 null/공백**: `append_item_content` 가 이미 처리 —
  새 값만 들어간다.
- **잘못된 append 값(불리언 아님)**: 미지정으로 간주, field 기반 기본값 폴백.

## 테스트

- `tests/test_handoff_resolve.py`
  - `value` 지정 시 `source_mode == "literal"`(author/AskUserQuestion 무시)
  - `value` 없을 때 기존 source_mode 결정 불변(회귀)
  - `append: true`/`false` 명시 시 write_mode 결정
  - `append` 미지정 시 field 기반 폴백(item_content→append, colXX→replace)
  - colXX 에 `append: true` → write_mode append
  - 결과 dict 에 `value` 키 포함
- teamer_api 관련 테스트
  - colXX append 시 GET 기존값 뒤에 누적되는지(`append_item_content` 재사용 경로)
  - 기존 `--col-override` replace 동작 불변(회귀)

## 하위호환

- `value`·`append` 키가 없는 기존 모든 config 는 동작 변화 없음.
- `resolve_handoff` 결과 dict 의 기존 키(`source_mode`·`write_mode`) 의미 불변,
  `value` 키만 추가.
- 기존 `--col-override col=path`(replace) 호출 형태 유지.
- literal source 가 아닌 종류는 template 포장·Author div 래핑 동작 그대로.
