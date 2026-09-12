# SRS/SDS 를 요구·설계 텍스트의 SSOT 로 승격

## 배경

SRS 는 지금 greenfield 전용이고, 있어도 `/harness-init` 이 한 번 만든 뒤 갱신 경로가
없어 t=0 스냅샷으로 굳는다. `/flow` 에서 SRS 는 읽기 전용 입력일 뿐, 새 요구가 SRS 로
돌아오는 경로가 없다. SDS 는 `doc-sync` 가 코드 뒤를 따라가는 경로를 이미 갖지만,
설계 결정이 코드 *전에* 기록되는 경로는 없다.

요구·설계 **텍스트**의 정본을 repo 문서로 못박고, 그 정본이 증분으로 갱신되는 경로를
만든다. 외부 트래커 연동은 이번 범위 밖.

## 결정 요약

| 축 | 결정 |
|---|---|
| SRS 분할 | `README.md` = §1·§2·§3·§4·§6·§7 + 영역 인덱스 · `<영역>.md` = §5 FR |
| 채번 | 영역에 사는 것만 영역 접두. 번호는 `srs_check.py --next-id` 가 발급 |
| §7 DR·§8 EIR | 삭제. DR → FR, EIR → §7 CON |
| NFR 축 키 | 기존 앵커 stem 재사용. 섹션 앵커 유지 + 항목 앵커 추가 |
| 증분 | `/flow` Dev 티어에만. SRS 증분 = 티어 확정 직후, SDS 증분 = plan 직후 |
| 판정 | 커밋 게이트 아님(FAIL-OPEN). `srs-verify` CI 가 `--verify` 로 판정 |
| CI 렌더 | 무조건 아님. `AskUserQuestion` 으로 거절 비용을 밝히고 선택 |

## A. 문서 레이아웃

```
docs/srs/README.md     §1 개요 · §2 목표/비목표 · §3 사용자/역할
                       §4 고객요구 · §6 NFR · §7 제약 · ## Areas 인덱스
docs/srs/<영역>.md     §5 기능요구
```

`docs/srs/README.md` 경로는 없애지 않는다. `rules/harness-rules.md` · `skills/flow/SKILL.md`
· `skills/harness-authoring/SKILL.md` · `tests/harness_scaffold/_helpers.py` ·
`tests/wiki_graph/` 가 이 경로를 갖고 있고, 소비자의 기존 설치도 마찬가지다.

영역 파일이 §5 만 갖는 이유: §5 가 유일하게 프로젝트 크기에 비례해 자라는 절이고,
동시 브랜치가 충돌하는 지점도 여기다. 나머지 절은 프로젝트당 한 벌이다.

### §7 DR · §8 EIR 삭제

두 절은 이미 SDS 의 그림자다. `srs.template.md` 가 DR 을 "NOT the schema/ERD (that is
SDS Data Design)", EIR 을 "NOT the internal integration design (that is SDS Integration
Points)" 로 정의한다. 소유 데이터와 통합 지점 계약이 SDS 모듈 개요에 이미 있으므로,
SRS 쪽 절은 같은 사실의 두 번째 자리다 — `harness-rules` 7(SSOT) 위반.

옮길 곳이 갈린다. DR 은 측정 가능한 기능 요구로 떨어진다 — "PII 는 계정 삭제 90일 후
파기. 수락기준: 90일 초과 행 0" 은 그대로 FR 이다. EIR 은 아니다 — "레거시 X 의 SOAP
v1.2 로 연동해야 한다" 는 시스템이 수행하는 것이 아니라 외부가 부과한 것이므로 §7 CON
이다. FR 로 밀면 수락기준을 쓸 수 없는 FR 이 생긴다.

삭제 파급은 작다: `#dr-`·`#eir-` 앵커를 거는 SDS 링크가 현재 0개다.

§9 제약/가정은 §7 로 번호를 당긴다.

## B. 채번

```
FR-<영역>-NNN     <영역>.md §5      영역 = 파일 stem 대문자
C-NNN             README §4
NFR-<축>-NNN      README §6         축 = §6.x 섹션 앵커 stem
CON-NNN           README §7
ROLE-NNN          README §3.1
```

번호는 사람도 모델도 짓지 않는다. `srs_check.py --next-id` 가 발급한다.

**KIND 는 열린 집합이다.** 스크립트 어디에도 KIND 목록이 없다 — 대상 파일의
`<a id="{kind}-…">` 앵커를 스캔해 max+1 을 낸다. 새 KIND 는 문서에 앵커 하나를 쓰는
것으로 성립하고, 코드 변경을 부르지 않는다.

### NFR 축 키

축 키는 새로 짓지 않고 **현재 섹션 앵커의 stem** 을 쓴다 — `perf` · `security` ·
`availability` · `scalability` · `accessibility` · `maintainability` · `compatibility`.
매핑표가 0개가 되고, §6.8 로 새 축이 붙으면 `NFR-<새stem>-NNN` 이 자동으로 성립한다.

섹션 앵커 `<a id="nfr-perf">` 는 **지우지 않고** 그 아래에 항목 앵커
`<a id="nfr-perf-001">` 을 추가한다. `sds.template.md` 의 `#nfr-perf` 링크와
`tech-doc-guide.md` 의 같은 참조가 살아 있어야 하기 때문이다. 섹션 앵커 = 축,
항목 앵커 = 개별 요구.

### 파일 간 백링크

C 가 README 에 살고 FR 이 영역 파일에 살므로, FR→C 백링크가 파일을 넘는다:

```markdown
- <a id="fr-payment-001"></a>**FR-PAYMENT-001** [P0] (← [C-003](README.md#c-003)) …
```

`--verify` 의 죽은 링크 검사는 파일 간 링크까지 봐야 한다. 같은 기계가 ROLE 링크에도
쓰인다.

### ROLE 링크는 조건부

§5 의 2차 분류축은 `srs.template.md` 기준 "user role **or sub-area**" 다. 역할이 아닌
하위 영역에 ROLE 링크를 강제하면 없는 역할이 생긴다 — 2차축이 역할일 때만 링크한다.

### 동시 채번 충돌

중앙 채번 없이는 막을 수 없다. 회피가 아니라 검출 + 재채번으로 간다 — `--verify` 가
중복 앵커를 잡는다. 영역 분할이 FR 의 충돌 빈도를 낮추지만, C·NFR·CON·ROLE 은 README
한 파일로 모이므로 그쪽 경합은 남는다.

## C. `scripts/_md_anchors.py` · `scripts/srs_check.py`

### `_md_anchors.py`

`harness_scaffold.py` 의 `_slugify` · `_has_anchor` 를 옮겨 담는다. `harness_scaffold.py`
는 거기서 import 한다 — 한 사실 한 곳. 두 함수는 `<a id>` · 헤딩 슬러그 · GitHub 중복
슬러그 `-1`/`-2` · 퍼센트 인코딩 · front matter/코드펜스 제거를 이미 처리한다. 새로
짜지 않는다.

sibling → package import fallback 은 `harness_scaffold.py` 의 기존 패턴을 따른다:
플러그인 위치에서 직접 돌 때는 sibling, 테스트에서는 `scripts.` 패키지.

**순수 이동이다.** `harness_scaffold` 의 기존 테스트가 한 줄도 바뀌지 않고 통과해야
한다.

### `srs_check.py`

`docs/srs/` 부재 = exit 0, 무출력. 모든 하위 명령에 공통.

```
--next-id <파일> --kind <KIND> [--scope <토큰>]
```

대상 파일에서 `<a id="{kind}-(?:(.+)-)?(\d+)">` 를 스캔해 scope 별 max+1 을 stdout 한
줄로 낸다. scope 기본값은 영역 파일이면 파일 stem, README 면 없음. NFR 만 `--scope perf`
처럼 섹션 앵커 stem 을 받는다. 기존 앵커가 없으면 001.

```
--verify [경로…]
```

- 중복 앵커 (같은 파일 안, 그리고 `docs/srs/` 전체에서 같은 FR id)
- 죽은 링크 — 파일 안 프래그먼트와 파일 간 링크(`README.md#c-003`) 둘 다
- 접두 불일치 — 영역 파일의 FR stem 이 파일 stem 과 다른 경우

`max_lines` 는 **보지 않는다.** SRS 문서는 front matter 를 달아 wiki 노드가 되므로
`wiki_graph.py --verify` 가 이미 초과를 경고한다 — 한 사실 한 곳. 덕분에 `srs_check.py`
는 설정을 전혀 읽지 않고, `wiki_graph.py` 를 수정할 일도 없다(그 파일은 outcome eval 의
`copy_from_repo` 소스라 한 바이트만 바뀌어도 생측정을 문다).

```
--areas
```

영역 파일 stem + §5 title 을 낸다. 증분 단계의 라우팅 후보.

### 왜 새 진입점인가

`_has_anchor` 는 `validate_plan` 안에서만 돌아 `/harness-init` 생성 시점 전용이다.
`doc_invariants` 의 링크 검사는 세기만 하고 해석하지 않는다. `wiki_graph --verify` 는
front matter edge 만 본다. 증분 편집이 만드는 죽은 앵커를 보는 주체가 지금 없다.

## D. `/flow` 증분 단계 (Dev 티어 전용)

`skills/flow/SKILL.md` Dev 절 순서:

```
1.  wiki 컨텍스트 로드            (기존)
1b. SRS 증분                      ← 신규
2.  superpowers                   brainstorm → plan
3.  오버레이 — 구현 최소화 · SDS 증분 ← 신규 · 선택적 TDD · doc-sync · 도메인 리뷰
4.  commit → merge                (기존)
```

**SRS 증분**은 티어 확정 직후, 계획 전이다. 요청이 새 고객 요구면 `--areas` 로 영역을
고르고 `--next-id` 로 번호를 받아 해당 영역 파일에 FR 을, README §4 에 C 를 추가한다.
기존 요구의 구현·버그·리팩터면 건너뛴다. `docs/srs/` 부재면 건너뛴다.

**SDS 증분**은 plan 직후, 코드 전이다 — `구현 최소화` 오버레이와 같은 지점. 새 모듈 ·
통합 지점 계약 · 구조 변경을 SDS 에 기록한다.

순서는 고정이다. SDS 증분이 `doc-sync` 뒤로 밀리면 `PostToolUse` 훅이 `doc-sync.done`
과 `review.done` 을 지워 재실행 루프가 생긴다.

Docs 티어엔 넣지 않는다. Docs 는 wiki 컨텍스트 로드조차 건너뛰는 설계이고, 문단 하나
고치려 설계 문서를 읽는 것이 티어가 막으려는 바로 그 불일치다.

모델이 판정하는 것은 "새 요구인가" 와 "어느 영역인가" 둘뿐이다. 번호는 `--next-id`,
무결성은 `--verify` 가 준다.

`flow-tiers.yaml` 과 `flow_gate_check.py` 는 손대지 않는다. `skills/flow/SKILL.md` 의
`description` 도 건드리지 않으므로 invocation eval 재측정이 없다.

## E. brownfield SRS 개방

`harness-rules` 8(greenfield 전용) · 8-1(brownfield 게이트 스킵) · `tech-doc-guide` 의
"SRS 는 greenfield 전용" · `harness-authoring/SKILL.md` · `harness-init/SKILL.md` ·
`srs.template.md` 머리말을 푼다.

brownfield 는 `/harness-init` 이 골격만 만든다 — 미수집 표기. **코드에서 FR 을 역산하지
않는다.** 코드는 "무엇을 하는가"지 "무엇을 원했는가"가 아니고, 역산 FR 은 요구가 아니라
현재 동작의 서술이라 `harness-rules` 4(추측 금지) 위반이다. 요구는 사람이 말할 때
증분으로 들어온다.

8-1 의 범위 명확화 게이트(`AskUserQuestion` 으로 측정 가능·단일 해석까지)는 brownfield
에도 적용한다.

## F. SDS 역추적 · doc-sync 경계 · SSOT 축

### brownfield SDS 의 FR 역추적 링크

`tech-doc-guide` 의 "brownfield(SRS 미생성)는 이 필드를 생략" 과 `sds.template.md` 의
같은 문구를 푼다. 안 풀면 SRS 는 생기는데 SDS 가 안 가리켜 Requirements Matrix 가
반쪽이 된다. NFR Realization 과 Requirements Coverage 의 brownfield 생략도 함께 푼다.

인프라·횡단 모듈의 "FR 매핑 없음"은 그대로 유지한다 — 억지 매핑 금지.

### doc-sync 경계

`doc-sync/SKILL.md` 본문에 한 곳으로 못박는다.

- **코드 전(증분 단계) = 구조** — 모듈 개요 · Mermaid 노드 · 통합 지점 계약 · FR 역추적 링크
- **코드 후(doc-sync Mode W) = 정합** — sources sha · stale 해소 · 분할 · orphan

여기에 한 줄을 더한다: **SRS 문서는 기계 분할 대상이 아니다.** Mode W 6단계의 H2 분할이
SRS 에 걸리면 SDS 가 거는 `#nfr-perf` · `#c-003` 링크가 죽는다. 커지면 §6 을
`docs/srs/nfr.md` 로 통째 승격하고 링크를 같이 고치는 명시적 이주로 간다.

### SSOT 축 분리

`harness-rules` **7-1** 로 넣는다 — 룰 7 이 이미 "one fact, one place" SSOT 룰이다.

> 요구·설계 **텍스트** = repo 문서. **상태·승인·담당자** = 외부 트래커.
> 축마다 정본을 하나만 지목한다. 양방향 자동 머지는 만들지 않는다.

`risk-tiers.md` 가 아닌 이유: 그 파일은 세션마다 주입되는 유일한 룰이라 바이트가 eval
입력이다. `hook_assisted` 4개 스킬이 생측정을 물고, CLAUDE.md 기록상 mandate 옆 두 줄로
0.82 → 0.55 가 난 전력이 있다. `harness-rules.md` 는 주입되지 않으므로 eval 비용이 0
이면서 소비자에게 그대로 나간다.

## G. CI · 호스트 복사

### `srs-verify`

`github/srs-verify.workflow.example.yml` 신설. `flow_init_setup.py --render-srs-verify`
가 렌더한다 — `render_wiki_verify_workflow` 대칭.

**무조건 렌더가 아니다.** `AskUserQuestion` 으로 묻고, 옵션 설명 자체가 거절 비용을 진다:
커밋 게이트는 SRS 를 보지 않으므로 이 워크플로가 죽은 앵커와 중복 번호를 보는 유일한
곳이고, 거절은 가벼운 검사가 아니라 검사 없음이다. 기존 `srs-verify.yml` 은 보고만 하고
덮지 않는다.

제안 위치는 `/flow-init` Step 2.7 옆, `docs/srs/` 존재를 가드로 둔다. `/harness-init` 이
방금 `docs/srs/` 를 만든 경우는 보고 마지막 줄에서 `/flow-init` 재실행을 가리킨다.

이 저장소 자체 `.github/workflows/srs-verify.yml` 도 함께 만든다(CLAUDE.md Dogfood new
CI). `docs/srs/` 가 없으므로 no-op-green 계약을 검증하는 역할이다 — `wiki-verify.yml` 과
같은 처지. `timeout-minutes` 를 단다.

### `COPY_FILES`

`scripts/srs_check.py` 와 `scripts/_md_anchors.py` 를 `flow_init_setup.py` 의
`COPY_FILES` 에 등록한다. 빠뜨리면 증분 단계가 호스트에서 스크립트를 못 찾아 조용히
무력화되고, 소비자 CI 도 `--verify` 를 돌릴 수 없다.

`COPY_FILES` 는 flat 복사(`dest_dir / Path(rel).name`)다. `srs_check.py` 가
`harness_scaffold` 를 import 하면 호스트에 그 파일이 없어 `ImportError` 로 죽으므로,
`_md_anchors.py` 추출이 선택이 아니라 전제다.

## H. 테스트

`tests/srs_check/` — 500줄을 넘으면 폴더, 넘지 않으면 평면 파일 하나.

- `--next-id`: 빈 파일 · 기존 앵커 · scope 분리 · 미지 KIND · 영역 파일 stem 기본값
- `--verify`: 중복 앵커 · 파일 간 죽은 링크 · 접두 불일치
- `--areas`: stem + title
- `docs/srs/` 부재 → exit 0 무출력

`tests/flow_init/` — `COPY_FILES` 등록 · `--render-srs-verify` · 기존 파일 미덮어씀.

`_md_anchors` 추출 후 `harness_scaffold` 의 기존 테스트가 그대로 통과해야 한다.

새 `.py` 는 산문 린트 대상이다 — `doc_style_check.py --lint` 통과.

수정한 뒤에는 CLAUDE.md 의 변이 테스트 규율을 적용한다: 변이가 적용됐음을 단언하고,
수집된 node id 를 편집 전후로 `comm` 한다.

## I. 위키 위생 · 400라인

새 SRS 영역 파일은 fail-closed 다. `wiki_id`(`wiki_graph.py --derive-id` 파생 —
`docs/srs/payment.md` → `srs.payment`) · `title` · edge 를 붙이고 `graph.yaml` 을 재빌드해
함께 스테이징해야 커밋 게이트의 `--verify` 가 통과한다. `srs.template.md` 의 front matter
주석이 이미 이걸 말하므로 영역 파일 문구만 맞춘다.

이 작업이 만들거나 고치는 문서는 전부 400줄 이하로 간다.

현재 400 초과인 파일은 이번 대상 밖이고, 각각 이유가 다르다:

| 파일 | 줄 | 왜 이번이 아닌가 |
|---|---|---|
| `USAGE.md` / `USAGE.ko.md` | 808 / 761 | ko 트윈을 doc-sync 가 맞물어 돌려야 하는 별건 |
| `rules/risk-tiers.md` | 437 | 분할이 4개 스킬 생측정을 물고, 포인터 스텁 분할이 0.33 을 낸 전력 |
| `CHANGELOG.md` | 425 | python-semantic-release 가 재생성 — `doc-style.yml` 도 같은 이유로 제외 |

## 범위 밖

- 외부 트래커 연동 (양방향 동기화 · 상태 전파)
- `docs/verification/*` 와 ALM 이 NFR 을 역참조하도록 잇는 것 — 연결은 나중에 붙여도
  마이그레이션이 아니지만, id 는 나중에 붙이면 이미 쓰인 문서를 고쳐야 하므로 지금
  붙인다
- 커밋 게이트에 `srs` 스테이지 추가 — 판정은 CI 가 한다
- 위 표의 400줄 초과 문서 분할

## 대상 파일

저장소에서 재계산한 결과.

**신규**

```
scripts/_md_anchors.py
scripts/srs_check.py
skills/harness-authoring/templates/srs-area.template.md
github/srs-verify.workflow.example.yml
.github/workflows/srs-verify.yml
tests/srs_check/
```

`srs.template.md` 는 README(공통 절)를 맡고, 영역 파일은 §5 만 담으므로 내용이 겹치지
않는다 — 한 템플릿을 두 용도로 쓰면 영역 파일마다 공통 절이 복제된다.

**수정**

```
scripts/harness_scaffold.py                          _slugify·_has_anchor 를 import 로
scripts/flow_init_setup.py                           COPY_FILES · --render-srs-verify
rules/harness-rules.md                               8 · 8-1 · 7-1 신설
skills/harness-authoring/templates/srs.template.md   절 재편 · 채번 · DR/EIR 삭제
skills/harness-authoring/templates/sds.template.md   FR 링크 형식 · brownfield 생략 해제
skills/harness-authoring/references/tech-doc-guide.md  위 전부
skills/harness-authoring/SKILL.md                    greenfield 표기
skills/harness-init/SKILL.md                         greenfield 게이트 · 보고 줄
skills/flow/SKILL.md                                 증분 2단계
skills/flow-init/SKILL.md                            srs-verify 제안 단계
skills/doc-sync/SKILL.md                             경계 · SRS 기계 분할 금지
tests/flow_init/                                     COPY_FILES · 렌더
```
