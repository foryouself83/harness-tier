# SRS·SDS 추적성 (sources 표면화 · 진입 fallback · FR 앵커 검증) 설계

- 날짜: 2026-09-07
- 브랜치: `feature/srs-sds-traceability`
- 티어: DEV (gates: precommit · review · doc-sync · wiki · doc-style)
- 선행 근거: [2026-08-13-wiki-hardening-design.md](2026-08-13-wiki-hardening-design.md)
  가 만든 읽기 경로(`--nodes-for` → `/flow` Dev 단계)를 SRS·SDS까지 잇는다.

## 배경과 목표

`/harness-init`이 SRS·SDS를 정성껏 만들지만, 이후 개발에서 아무도 읽지 않고
드리프트도 잡히지 않는다. 세 지점이 각각 끊겨 있다.

- **`sources` 없는 SDS 노드는 영구 비가시** — `--stale`은 `sources`가 dict가 아니면
  건너뛰고, `--nodes-for`는 `sources` 없이는 절대 반환하지 않으며, `collect_warnings`
  에는 "sources 자체가 없음"이라는 항목이 없다. 세 경로 모두에서 조용히 빠진다.
- **`/flow` Dev 진입이 요구·설계를 안 읽는다** — 유일한 읽기 경로가 `--nodes-for`
  인데 `wiki.enable` 기본값이 `false`다. wiki 없는 프로젝트는 계획 단계에서 SDS를
  한 줄도 보지 않는다.
- **FR 앵커 무결성에 검증이 없다** — `Requirements Coverage`는 이미 SDS 템플릿의
  저작 의무인데, `validate_plan`의 dead-link 검사가 `#fragment`를 정규식에서 버려
  대상 파일 존재만 본다. 죽은 FR 앵커가 생성 시점에도 통과한다.

| 항목 | 결정 |
|---|---|
| `sources` 필수화 | **배제** — 저작 시점 강제는 가짜 경로를 부른다. 대신 wiki가 붙는 시점에 경고로 표면화 |
| 경고 대상 | `tags: [sds]` 노드 한정. 전 노드는 영구 소음 |
| 경고 조건 | `sources` 키가 **없거나 값이 아예 없을 때**만. 빈 맵 `sources: {}` 는 "아직 매핑 없음"이라는 진술이므로 침묵 |
| 경고 등급 | warn (차단 아님) — 기존 "없는 sources 경로"와 동급 |
| backfill 주체 | `doc-sync` Mode W. `sha: null`로 채우고 정상 stamp 흐름에 넘긴다 |
| 진입 fallback | `/flow` Dev step 1에만. Docs 티어 제외 |
| FR 앵커 검증 | `validate_plan` 링크 검사 확장. 신규 스크립트 없음 |
| SRS `sources` | **배제** — blob sha는 "코드가 바뀜"만 말한다. 요구 추적엔 방향이 반대 |

## 1. `sds` 노드 `sources` 누락 경고

`scripts/wiki_graph.py` `collect_warnings()`에 항목 하나를 추가한다.

- 조건: 노드가 wiki 노드(`id` 있음)이고, `tags`에 `sds`가 있고, `sources` 가 **키 부재이거나
  YAML null**(`sources:` 뒤에 아무것도 없음). 후자는 쓰다 만 편집이지 진술이 아니다.
  빈 맵 `sources: {}` 는 침묵 — 아직 매핑할 코드가 없다는 저자의 진술이고, 템플릿이
  그것을 싣는다. 비어 있음까지 경고하면 생성된 greenfield SDS 가 전부 영구히 울리고
  해소 수단이 없다(doc-sync 5단계가 경로 날조를 금지하므로). 리스트형 `sources` 도
  침묵 — `validate_structure` 가 이미 자기 메시지로 차단하고 `--nodes-for` 는 리스트를
  읽으므로, 경고 문구가 거짓이 되고 한 실수가 두 줄로 보고된다.
- 차단하지 않는다. 기존 "없는 sources 경로" 경고와 같은 이유 — 코드만 바꾼 커밋까지
  얼어붙게 만들 근거가 없고, 수리처는 doc-sync다.
- `_capped`로 3건 + 건수 요약, 다른 경고와 동일.

**왜 `sds` 태그 한정인가.** 온보딩·인덱스·SRS는 코드 매핑이 정당하게 없다. 전 노드에
걸면 marker 경고를 억제한 것과 같은 이유로 영구 소음이 되어 아무도 안 읽는다. SDS는
정의상 코드에 관한 문서라 예외가 없고, 태그는 `sds.template.md`가 이미 찍는다.

**왜 SRS는 대상이 아닌가.** 요구는 코드 경로에 1:1로 붙지 않는다. 붙인다 해도 blob
sha가 말하는 것은 "그 코드가 바뀌었다"뿐이라 "요구가 바뀌었다"를 대신하지 못한다.
SRS 추적은 §4의 앵커 검증이 담당한다.

## 2. doc-sync backfill

`skills/doc-sync/SKILL.md` Mode W에 backfill 책임을 명시한다.

- `--verify`가 §1 경고를 내면, SDS의 Module Overview를 읽어 모듈→실제 코드 경로를
  `sources`에 채운다. `sha`는 `null`.
- `null`은 `--stale`에서 stale로 잡히므로 다음 본문 동기화 때 자연히 도장이 찍힌다.
  자기 해소형이라 별도 정리 단계가 필요 없다.

**왜 지금 빠져 있나.** Mode W step 4는 **신규** `.md`만 front matter를 부여하고,
step 3은 **본문을 바꾼** 노드만 sha를 찍는다. 기존의 `sources` 없는 노드를 채우는
경로가 어디에도 없어서, `/wiki-init`이 한 번 훑고 놓친 문서는 영구 누락이다.

**차단 규칙과의 관계.** `_sources_only_swaps`는 "항목 추가·삭제"와 "null→sha 최초
도장"을 둘 다 fraud shape에서 제외한다. backfill은 항목 추가이므로 `--verify`가
막지 않는다.

**템플릿 정정.** `sds.template.md`가 `sources: {}`를 **싣는다**. 주석은 누가 채우는지를
적는다 — 코드가 이미 있으면(brownfield) 실제 경로로, 없으면 빈 채로. 저작자가
`/harness-init` 시점에 없는 코드를 추측해 적는 것이 이 설계가 막으려는 실패이고, 키를
아예 빼면 §1 경고가 영구히 울린다. 빈 맵이 그 둘 사이의 답이다.

## 3. `/flow` Dev 진입 fallback

`skills/flow/SKILL.md` Dev dispatch step 1의 wiki 컨텍스트 로드에 분기를 하나 단다.

- `--nodes-for`가 아무것도 내지 않으면(wiki 없음 · 소유 노드 없음), `docs/sds/README.md`
  가 있을 때 직접 읽는다. `docs/srs/README.md`도 있으면 함께 읽는다.
- **Docs 티어에는 넣지 않는다.** 문서만 바꾸는 작업에 설계 문서를 통째로 읽히는 것은
  티어 원칙(위험도에 프로세스를 맞춘다)에 정면으로 어긋난다.
- 없으면 조용히 넘어간다. 문서가 없는 프로젝트가 정상 상태다.

경로를 하드코딩하는 것이 wiki 조회보다 열등해 보이지만, 이 분기가 도는 조건 자체가
"그래프가 답을 못 준다"이다. `harness-rules` 8이 `docs/sds/`를 고정 위치로 규정하므로
추측이 아니다.

## 4. FR 앵커 무결성 (`validate_plan`)

`scripts/harness_scaffold.py`의 링크 검사를 앵커까지 확장한다.

- `_MD_LINK_RE`가 지금 버리는 `#fragment`를 캡처한다.
- 대상 파일이 해석되면(plan 엔트리 또는 디스크) 그 본문에서 fragment를 찾는다.
  둘 중 하나면 통과: 명시 앵커 `<a id="...">`(`data-id` 는 제외), 또는 슬러그가
  일치하는 heading(ATX·setext 모두, 코드펜스 제외, 중복 슬러그는 GitHub 처럼 `-1`
  접미사). fragment 는 퍼센트 디코딩해서도 비교한다.
- 못 찾으면 `severity: warn`, `kind: dead-anchor`. dead-link와 같은 등급이다.

**heading 슬러그를 반드시 지원해야 한다.** `<a id>`만 보면 저장소 자체 문서가 쓰는
`#requirements-coverage` 류 링크가 전부 오탐이 된다. 슬러그 규칙은 GitHub 방식 —
소문자화, **구두점·기호만** 제거, 그 **뒤에** 공백을 **하나씩** 하이픈으로 바꾼다.
`_` 는 `\w` 라 남는다 — GitHub 도 남긴다. 유니코드 문자·숫자도 남으므로 한글 heading
이 보존된다. 세 가지가 전부 함정이다: `_` 를 지우면 snake_case heading 링크가,
공백 런을 합치면 `## Step 1 — Classify`(GitHub 은 `step-1--classify`) 가, ASCII 만
남기면 한글 heading 이 각각 통째로 오탐이 된다.

**대상 해석 순서 — 디스크가 먼저다.** `apply_plan` 의 `create` 는 이미 있는 파일을
덮어쓰지 않고 conflict 로 기록한 뒤 넘어간다. 그래서 plan 의 `content` 는 "그 파일의
최종 모습"이 아니고, 디스크에 있는 대상이 권위다. plan 엔트리는 **아직 디스크에 없는**
경로에만 답한다. 반대로 읽으면 conflict 난 파일의 앵커가 전부 죽었다고 보고되며, 그것이
brownfield `/harness-init` 재실행의 형태다. `content` 키가 아예 없는 엔트리도 권위가
아니다 — `.get("content", "")` 의 빈 문자열은 무엇을 물어도 "앵커 없음"이라 답한다.

**이것이 잡는 것.** `Requirements Coverage`는 "모든 FR이 ≥1 모듈에 매핑됐는지, 미매핑은
gap으로 명시"를 이미 저작 의무로 요구한다. 그 의무를 지켰는지 확인할 수단이 없어서
죽은 FR 앵커가 조용히 통과해 왔다.

**범위 밖.** "SRS에는 있는데 어느 SDS 모듈도 구현하지 않는 FR"의 역방향 검출은 넣지
않는다. `Requirements Coverage` 절이 gap을 산문으로 명시하도록 이미 요구하고 있고,
기계적 역검출은 인프라·횡단 모듈의 "no FR mapping" 면제와 충돌해 오탐이 크다.

## 검증

| 대상 | 위치 | 성격 |
|---|---|---|
| §1 경고 | `tests/wiki_graph/` | 태그 유무 · sources 형태별 분기 |
| §4 앵커 검사 | `tests/harness_scaffold/` | 슬러그 규칙이 실로직 — TDD |
| §2·§3 산문 | `tests/skills/` | 링크·언어 규약 기존 검사에 편승 |

§4만 실질 알고리즘이다. 슬러그 정규화를 먼저 실패하는 테스트로 고정하고 구현한다.

## 커밋

`feat` — 소비자에게 배포되는 `.md`와 `scripts/`를 바꾼다. `docs`·`chore`는 릴리스
게이트를 통과하지 못해 소비자에게 전파되지 않는다.
