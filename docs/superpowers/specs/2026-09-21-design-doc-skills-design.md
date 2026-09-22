# 설계 산출물 스킬 (SRS · SDS · 아키텍처 설계서 · API 명세서 · ERD · 테이블 명세서)

## 목적

소비자 호스트의 SDLC 산출물 6종을 `.docx`로 생성함. 원문은 전부 Markdown이고, docx는 코드가
원문과 템플릿으로 만드는 변환본임. SRS·SDS는 기존 md를 그대로 변환하고, 나머지 4종은 모델(sonnet)이
SRS·SDS·코드를 읽어 md를 작성한 뒤 변환함. ID 누락·미존재 참조·템플릿 불일치는 기계 검증으로 잡음.

## 결정 사항

| 항목 | 결정 |
|---|---|
| 호출 | 사용자 호출 전용 (`disable-model-invocation: true`), `model: sonnet` 고정 |
| 스킬 | 문서별 1개: `design-srs` · `design-sds` · `design-architecture` · `design-api` · `design-erd` · `design-table` |
| 원문 형식 | 6종 모두 Markdown. docx는 파생물 |
| 내용 원천 | SRS·SDS: 기존 `docs/srs/`·`docs/sds/`. 나머지: SRS/SDS(요구사항·추적성) + 실제 코드(라우트·ORM 모델·마이그레이션). 코드 없으면 SRS/SDS만, 빈 정보는 `확인 필요` |
| 변환 | md → docx 단일 변환기 (markdown-it-py 파싱 + python-docx 생성) |
| 도식 | ` ```mermaid ` · ` ```d2 ` 블록을 Kroki(`https://kroki.io` 기본, config로 교체)에서 SVG로 렌더해 `.docx`에 삽입(Word 2016 이상 표시, 이전 버전은 대체 이미지) — 렌더러 호출에 User-Agent 헤더 전송 |
| 표준 | SRS: ISO/IEC/IEEE 29148. SDS: IEEE 1016. 아키텍처: ISO/IEC/IEEE 42010 관점 + IEEE 1016. API: OpenAPI 항목. ERD·테이블: 국내 SI 산출물 관행. 본문 한국어 |
| ID | SRS와 같은 앵커 체계 `<a id="api-001"></a>**API-001**`, 6종 공통 파서 |
| 템플릿 | 플러그인 원본 `templates/design-docs/*.template.md` → `/flow-init`이 호스트에 시딩(없을 때만) → 이후 호스트 사본이 유일한 기준 |
| 검증 시점 | 각 스킬 시작 시 1회. 편집 훅·커밋 게이트 연동 없음 |

## 1. 구성·배치

```text
templates/design-docs/                 플러그인 원본 (배포, 시딩 전용)
  srs.template.md  sds.template.md                         front matter만 (본문은 원문 md)
  architecture.template.md  api.template.md  erd.template.md  table.template.md
scripts/
  design_doc_check.py                  템플릿·산출 md 검증 (COPY_FILES)
  design_doc_render.py                 md + 템플릿 메타 → docx (COPY_FILES)
skills/
  design-srs/ design-sds/ design-architecture/ design-api/ design-erd/ design-table/
rules/design-docs.md                   6개 스킬 공통 절차 (on-demand)
```

호스트 config (`flow-config.yaml`), 경로는 모두 사람이 지정:

```yaml
design_docs:
  templates: .claude/harness-tier/templates/design-docs
  docs: docs/deliverables              # <doc>.md, 모델이 작성, 커밋 대상 (SRS·SDS는 제외)
  output: docs/deliverables/results    # <doc>.docx
  renderer: https://kroki.io
  base_docx: null                      # 회사 양식 .docx 경로(선택). null이면 python-docx 기본 + 코드 스타일
  gitignore_output: false              # true → /flow-init이 output을 .gitignore에 추가
```

- 검사기·변환기는 config의 `templates` 경로만 읽음. 사용자가 템플릿의 헤딩·표 헤더·ID 접두어를
  바꾸면 산출 md 검증 기준과 docx 구조가 그대로 따름. 플러그인 원본은 시딩에만 쓰임.
- `/flow-init`: 템플릿 시딩은 파일 단위 match-then-skip(Invariant 5) — 호스트 사본은 절대
  덮어쓰지 않음. `design_docs` 블록 추가도 match-then-skip. `output` 경로의 `.gitignore` 등록
  여부는 AskUserQuestion으로 소비자가 선택, 이미 등록돼 있으면 묻지 않음 → `gitignore_output`
  값으로 기록, 스크립트가 반영.
- 의존성 `python-docx` · `markdown-it-py` 부재 시 스킬이 설치 여부를 물음 → 동의 시
  `python3 -m pip install python-docx markdown-it-py` 실행 후 진행, 거부 시 중단. Kroki 호출은
  stdlib `urllib`만 사용. 복사되는 스크립트는 Python 3.8+ 호환.

## 2. 템플릿·산출 md·ID

### 템플릿 형식

front matter = 문서 메타와 ID 규칙, 본문 = 산출 md의 골격.

```markdown
---
doc: table
title: 테이블 명세서
standard: "국내 SI 산출물 관행 (테이블 정의서)"
id_prefix: [TBL]
refs: [FR, ENT]
---

## 1. 개요

## 2. 테이블 목록

| 테이블ID | 물리명 | 논리명 | 엔터티 | 요구사항 |
|---|---|---|---|---|

## 3. 테이블 상세

<!-- repeat: TBL -->
### {{TBL-ID}} {{물리명}}

| 컬럼명 | 타입 | 길이 | NULL | PK | FK | 기본값 | 설명 |
|---|---|---|---|---|---|---|---|

## 4. 요구사항 추적표

| 요구사항 | 테이블 |
|---|---|

## 부록 A. 코드 인벤토리
```

- 헤딩 = 산출 md의 필수 헤딩(순서 포함). 표 헤더 행 = 그 섹션 표의 필수 컬럼.
- `<!-- repeat: TBL -->` = 바로 아래 헤딩이 발급 ID 하나당 한 번 반복되는 블록. 블록 안 표 헤더도
  반복마다 검사.
- `{{...}}` = 모델이 채울 자리. 산출 md에 남으면 위반.
- `srs.template.md`·`sds.template.md`: front matter만 둠(`title`, `standard`, `sources:` 원문 파일
  순서). 본문 구조는 harness-authoring의 SRS/SDS 템플릿이 이미 결정함.
- 공통 전반부는 변환기가 자동 생성: 표지 · 개정 이력 · 목차(TOC 필드, `updateFields` 설정).
  개정 이력은 산출 md front matter의 `revisions`에서 읽음(SRS/SDS는 git 로그가 아니라 템플릿
  front matter의 `revisions`). 제공 `srs.template.md`·`sds.template.md`는 `revisions` 키를 아예
  비워 둠(자리표시자 날짜를 그대로 찍어내는 행 없음) — design-srs/design-sds 스킬이 새 버전을
  렌더링할 때 사용자에게 한 행 추가를 안내함. 변환기는 `revisions`가 없는 템플릿도 처리함(빈
  버전/날짜로 표지 렌더).
- 고정 섹션 이름(표지 부제·개정 이력 표 헤더·목차 제목)은 템플릿 front matter의 `labels`
  맵으로 재정의함. 기본값은 영어이고, 제공 템플릿 6종은 모두 한국어 `labels`를 채워 둠.

### 산출 md

`<docs>/<doc>.md`. 규칙:

- ID 발급: `<a id="tbl-001"></a>**TBL-001**`. 재실행 시 기존 ID 유지, 새 항목만 다음 번호,
  front matter `revisions`에 1행 추가.
- 참조: 링크 형식 `[FR-PAYMENT-001](../srs/payment.md#fr-payment-001)`,
  `[ENT-003](erd.md#ent-003)`. docx에서 같은 문서 안 링크는 책갈피 하이퍼링크, 다른 문서 링크는
  ID 텍스트로 남음.
- 코드 근거: 항목별 `근거` 컬럼 또는 줄에 경로.
- 부록 A 코드 인벤토리(API·ERD·테이블): 추출 명령 1줄 + 표 `| 대상 | 근거 | 문서 ID 또는 N/A: 사유 |`.
- wiki front matter 필수 (harness-rules 8-2, wiki 활성 여부와 무관):

  ```yaml
  ---
  wiki_id: deliverables.table        # design_doc_check.py --wiki-id table 결과, 손으로 쓰지 않음
  title: 테이블 명세서
  tags: [deliverable, table]
  related: [deliverables.erd, srs.readme]   # front matter 가진 노드만 — 없는 노드로의 엣지는 --verify 차단
  sources: {}                        # 코드 근거 경로 매핑 (wiki sources 형식)
  revisions:
    - {version: "1.0", date: 2026-09-21, summary: 최초 작성}
  ---
  ```

  `used_by`·`defects`는 쓰지 않음(8-2). 호스트 wiki 활성 시 작성 후 `wiki_graph.py --build`로
  graph 재생성, 스킬 결과 보고에 `graph.yaml` 스테이징 필요 안내.

### ID

| 문서 | 발급 ID | 구성 |
|---|---|---|
| SRS | 기존 `C-` · `FR-<AREA>-` · `NFR-<AXIS>-` · `CON-` · `TERM-` · `ROLE-` | 원문 그대로 |
| SDS | 없음 (모듈은 FR 링크로 추적) | 원문 그대로 |
| 아키텍처 설계서 | `CMP-NNN` 컴포넌트, `IF-NNN` 인터페이스 | 컨텍스트 · 논리 · 배치 · 데이터 흐름 관점, 품질 속성(NFR) 실현, 추적표 |
| API 명세서 | `API-NNN` | 메서드 · 경로 · 파라미터 · 요청/응답 · 오류코드 · 인증, 추적표, 인벤토리 |
| ERD | `ENT-NNN` | 개념/논리 모델, 관계·카디널리티, Mermaid `erDiagram`, 추적표, 인벤토리 |
| 테이블 명세서 | `TBL-NNN` | 테이블 목록, 컬럼·제약·인덱스, 추적표, 인벤토리 |

앵커 추출은 `srs_check.py`·`_md_anchors.py`의 파서를 재사용함(코드 펜스·HTML 주석 제외).

## 3. 기계 검증 (`design_doc_check.py`)

- 첫 오류에서 멈추지 않음. 전 위반 수집 후 보고, 위반 있으면 exit 1.
- 위반 1건 = 파일 · 위치(헤딩 경로 또는 행) · 규칙 코드 · 수정 방법. 예:
  `table.md  3. 테이블 상세 > TBL-002  S-TABLE  column '길이' missing — template header: 컬럼명|타입|길이|...`

### `--templates` (템플릿 자체)

| 코드 | 검사 |
|---|---|
| T-MISSING | 템플릿 디렉터리 자체가 없음(`/flow-init` 재실행 안내), 또는 개별 `<doc>.template.md`가 없음(플러그인 원본에서 복원 안내) |
| T-FRONT | front matter 필수 키(`doc`·`title`·`standard`) 누락, 모르는 키, `doc`이 파일명과 불일치 |
| T-PREFIX | `id_prefix` 형식 위반, 템플릿 간 중복 |
| T-REFS | `refs`가 SRS 종류·다른 템플릿 `id_prefix` 어디에도 없음 |
| T-HEADING | 헤딩 중복, 빈 헤딩 |
| T-TABLE | 표 헤더 빈 칸·중복 컬럼 |
| T-REPEAT | repeat 마커 뒤 헤딩 없음, 마커의 접두어가 `id_prefix`에 없음 |
| T-SOURCES | SRS/SDS 템플릿의 `sources`가 비었거나 리스트가 아님. 매칭 파일 없음은 `--doc srs\|sds`에서 보고(호스트에 `docs/sds` 등이 아직 없어도 나머지 5개 스킬이 막히지 않게 함) |

### `--doc <doc>` (산출 md 또는 SRS/SDS 원문)

| 코드 | 검사 |
|---|---|
| S-MISSING | 산출 md가 아직 작성되지 않음 — 먼저 작성하라는 안내 |
| S-HEADING | 템플릿 필수 헤딩 누락·순서 뒤바뀜 |
| S-TABLE | 표 헤더가 템플릿과 불일치(누락 컬럼·다른 이름) |
| S-PLACEHOLDER | `{{...}}` 잔존 |
| S-ID | 형식 위반, 중복, 발급 접두어 외 ID 발급 |
| S-DANGLING | 참조 ID 미존재 — 링크 대상 앵커, 링크 없이 쓴 알려진 접두어 ID 토큰 모두 |
| S-COVER | 누락. 아키텍처: 모든 FR·NFR 항목 매핑. SDS: 모든 FR이 어떤 모듈의 구현 요구사항에 등장(명시적 "FR 매핑 없음" 허용). API·ERD·테이블: 인벤토리 전 항목에 문서 ID 또는 `N/A: 사유` |
| S-CROSS | ENT↔TBL 대응(모든 ENT에 TBL ≥1, TBL의 엔터티가 존재하는 ENT), FK 대상 테이블 존재, API→CMP 참조. 상대 문서 부재 시 "건너뜀" 안내(위반 아님) |
| S-SOURCE | 근거 경로 미존재(표의 `근거` 열 셀, 또는 front matter `sources` 맵의 키 — 값의 sha/null이 아니라 키가 경로) |
| S-DIAGRAM | mermaid/d2 블록 비어 있음, `%%...` 지시자·`---`...`---` 타이틀 블록을 건너뛴 뒤에도 Mermaid 다이어그램 타입 헤더 없음 |
| S-FRONT | 산출 md wiki front matter 누락, `wiki_id`가 `design_doc_check.py --wiki-id <doc>` 값과 불일치, `title`·`tags` 누락, `related`가 front matter 없는 문서를 가리킴, `sources`가 맵(`path: null`)이 아님 |
| SRS-VERIFY | `doc` 이 `srs`일 때만: 기존 `srs_check.py --verify`(중복 앵커·영역 접두어·깨진 링크)가 낸 위반 1줄씩 |

한계: 인벤토리 자체의 완전성은 기계 검증 불가. 추출 명령을 부록 A에 기록하도록 강제해 리뷰어가
재실행·대조 가능하게 함.

## 4. 스킬 흐름

공통 frontmatter — `allowed-tools`의 각 항목은 실행되는 커맨드 그대로(끝에 `*` 없음): 끝에
`*`를 붙이면 `<커맨드> && <임의 명령>`까지 사전 승인하게 되기 때문. SRS·SDS(변환 전용)는
`--wiki-id`도 `wiki_graph.py --build`도 쓰지 않음 — 원문에 이미 있는 front matter를 그대로
쓸 뿐, 새로 발급하지 않으므로. 아키텍처·API·ERD·테이블(작성+변환)은 산출 md를 새로 쓰므로
`design_doc_check.py --wiki-id <doc>`로 `wiki_id`를 받고(손으로 쓰지 않음), wiki 활성 호스트에서
그래프를 재빌드함:

```yaml
# SRS · SDS
disable-model-invocation: true
model: sonnet
allowed-tools: Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --paths) Bash(python3 .claude/harness-tier/scripts/design_doc_render.py --check-deps) Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --templates) Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --doc srs) Bash(python3 .claude/harness-tier/scripts/design_doc_render.py srs)
```

```yaml
# 아키텍처 · API · ERD · 테이블 (예: table)
disable-model-invocation: true
model: sonnet
allowed-tools: Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --paths) Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --templates) Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --doc table) Bash(python3 .claude/harness-tier/scripts/design_doc_check.py --wiki-id table) Bash(python3 .claude/harness-tier/scripts/design_doc_render.py --check-deps) Bash(python3 .claude/harness-tier/scripts/design_doc_render.py table) Bash(python3 .claude/harness-tier/scripts/wiki_graph.py --build)
```

`pip install`은 사전 승인하지 않음(사용자 결정 명령).

공통 절차는 `rules/design-docs.md`, SKILL.md는 입력 대상·인벤토리 추출법만 기술.

**SRS · SDS (변환 전용):**

1. config 해석, 의존성 설치 질의.
2. `--templates` → 위반 시 보고 후 중단.
3. `--doc srs|sds` → 위반 보고. 원문은 사람이 검토한 문서라 모델이 고치지 않음. 사용자가 위반을
   안은 채 변환할지 AskUserQuestion으로 선택.
4. `design_doc_render.py srs|sds` → docx.
5. 결과 보고.

**아키텍처 · API · ERD · 테이블 (작성 + 변환):**

1. config 해석, 의존성 설치 질의.
2. `--templates` → 위반 시 보고 후 중단(템플릿은 사람이 고침).
3. SRS·SDS·코드 읽기, 인벤토리 작성(추출 명령 기록).
4. 템플릿 골격대로 산출 md 작성·갱신. `wiki_id`는 `design_doc_check.py --wiki-id <doc>`로 받음.
5. `--doc <doc>` → 모델 수정·재검사 최대 3회, 잔여 위반 보고.
6. `design_doc_render.py <doc>` → docx. Kroki 실패 시 원문 코드 블록 삽입 + 경고.
7. 결과 보고: 산출물 경로 · 검증 요약 · 경고.

권장 순서: SRS → SDS → 아키텍처 → ERD → 테이블 → API.

## 5. 테스트

- `tests/design_docs/`: 규칙 코드별 위반 fixture(템플릿·산출 md), 다중 위반 전수 수집.
- 변환 스모크: 생성 docx를 다시 읽어 헤딩·표·책갈피·이미지가 md와 일치. Kroki는 mock.
- 템플릿 수정 반영: 헤딩 추가·표 컬럼 변경 템플릿 → 검사 기준 변화.
- `/flow-init` 시딩 멱등성: 수정된 호스트 템플릿 보존, 재실행 무변경.
- `tests/skills/` 기존 계약(frontmatter · allowed-tools 도달성 · README/USAGE 등재).
- 신규 스크립트: CRLF 정규화(digest 금지 규칙), Invariant 2 인코딩 방어, Python 3.8 호환.

## 범위 밖

프레임워크별 코드 자동 추출기, 편집 시 자동 검증, 커밋 게이트 연동, docx → md 역변환.
