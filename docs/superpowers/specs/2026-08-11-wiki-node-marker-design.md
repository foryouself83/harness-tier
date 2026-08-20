# Wiki 노드 마커 분리와 게이트 오탐/무음 제거 설계

- 날짜: 2026-08-11
- 브랜치: `feature/wiki-init-outcome-eval`
- 티어: DEV (gates: precommit · review · doc-sync · wiki)
- 선행: [2026-08-06 LLM Wiki 설계](2026-08-06-llm-wiki-design.md) — 이 문서가 그 2절·3절의
  노드 판별 규칙을 대체한다. 원 설계문서는 제자리 갱신하고, 원 계획서
  (`plans/2026-08-06-llm-wiki.md`)는 실행 완료된 기록이므로 동결한다.

## 배경

`c2a0d3f`(feat(wiki): add LLM wiki with graph verify gate)의 게이트를 실측한 결과 결함 4건이
재현됐다. 넷 다 원인이 다르지만 증상은 두 갈래다 — **막지 말아야 할 것을 막거나**, **막아야
할 것을 조용히 통과시킨다.**

| # | 심각도 | 결함 |
|---|---|---|
| 1 | High | 남의 `id:` Front Matter를 wiki 노드로 오인 → 저장소 전체 커밋 차단 |
| 2 | High | 차단 사유(`problems`)에 개수 캡이 없어 위반 300건이면 deny 사유 300줄 |
| 3 | Medium | Front Matter YAML 파싱 실패 시 노드가 경고 한 줄 없이 사라지고 `--verify`가 exit 0 |
| 4 | 부수 | dangling edge 메시지가 진범이 아니라 참조자를 지목 |

### 1번의 재현

`ID_RE`(`^[a-z0-9-]+(\.[a-z0-9-]+)*$`)는 wiki가 정한 id 형식이다. 그런데 `id`는 Docusaurus의
문서화된 1급 Front Matter 필드이기도 하고, `wiki.root` 기본값과 Docusaurus 기본 문서 경로는
둘 다 `docs/`다. 그래서 아래 문서 하나가 저장소의 **모든** 커밋을 막는다 (`wiki` 게이트는
`docs` 티어를 포함한 전 티어에 걸려 있다).

```yaml
---
id: Getting_Started        # Docusaurus의 것
sidebar_position: 1
---
```

```
docs/getting-started.md: id 'Getting_Started' 형식 위반 (허용: ^[a-z0-9-]+(\.[a-z0-9-]+)*$)
verify exit=1
```

`validate_structure`의 docstring은 이미 "정적 사이트 생성기의 메타데이터와 id를 빠뜨린 노드는
기계적으로 구별되지 않는다"고 선언하고 **id가 없는** 경우만 방어했다. id가 있는데 형식이 다른
경우가 무방비였다.

### 3번의 재현

`title: New: Doc`(따옴표 누락) 하나면 `parse_front_matter`가 `None`을 반환하고 `collect_nodes`가
그 파일을 조용히 버린다. 신규 문서이고 다른 노드가 Front Matter로 가리키지 않으면 `--verify`는
exit 0을 보고한다. `/wiki-init` 8절은 "verify 통과"를 wiki가 강제되고 있다는 증거로 읽는데,
그 전제가 거짓이 된다. 게다가 8절이 `--build` → `--verify` 순서라 build가 깨진 문서를 뺀
그래프를 먼저 써버려, 기존 노드였다면 잡혔을 drift 탐지까지 무력화된다.

## 전제: 미출시

`v0.1.13`은 wiki를 포함하지 않는다. `c2a0d3f`는 `origin/main` · `origin/stage` · `origin/dev`
어디에도 없고 작업 브랜치는 push조차 되지 않았다. 따라서 `id:`로 마킹된 노드를 가진 소비자가
존재하지 않는다 — **마이그레이션 표면이 0이다.** 하위호환 shim · deprecation 창 · 이중 키 읽기를
전부 생략하고 키를 통째로 교체한다.

`feature/*` → integration은 `flow-tiers.yaml`이 `--squash`를 강제하므로 이 브랜치의 커밋은
integration에서 하나로 접힌다. 아무도 겪지 않은 결함에 대한 `fix:` 체인지로그 항목은 생기지
않는다.

## 확정된 설계 결정

| 항목 | 결정 |
|---|---|
| 노드 마커 | `id` → **`wiki_id` 전용 키**. 충돌 원천 제거 |
| 형식 위반 `wiki_id` | 계속 **차단** (전용 키 = 노드로 의도했다는 뜻, 더 이상 모호하지 않다) |
| 마커 누락 경고 | 전수 경고 폐기. **wiki 전용 필드가 있을 때만** 경고 |
| 파싱 실패 | 원문에 `wiki_id:` 줄이 있으면 **차단**, 없으면 **경고** |
| `problems` 캡 | 출력 단계에서만 `PROBLEM_CAP = 10` |
| `/wiki-init` 7·8절 순서 | 유지 + 8절에 롤백 지시 추가 |

## 1. 노드 마커를 `wiki_id`로 분리

`front.get("wiki_id")` 하나가 노드 자격을 결정한다. `id`를 읽는 코드는 남기지 않는다.

원 설계 2절의 규칙이 다음으로 바뀐다: wiki root 안의 `.md` 중 **`wiki_id`를 가진 파일만**
wiki 노드다. `wiki_id`가 없는 `.md`는 — Front Matter가 있든 없든, 그 안에 `id`가 있든 —
wiki 밖이며 검증 대상이 아니다. 예외는 `wiki.index`가 가리키는 파일로, 이것은 반드시 노드여야
한다(그렇지 않으면 orphan 검사가 통째로 꺼지고, 그 사실은 경고로 보고된다).

바뀌지 **않는** 것:

- `ID_RE`의 패턴과 `DEFECT_PREFIX = "defect."`, `--neighbors <id>` CLI 인자. 이것들은 노드 id의
  *값* 규칙이지 Front Matter 키 이름이 아니다. 상수명만 `WIKI_ID_RE`로 개명한다.
- `_TEXT_FIELDS`의 YAML 1.1 방어. 전용 키라도 `wiki_id: 0123456`은 octal로 읽혀 정수 42798이
  되고, 그 문자열화 `"42798"`은 `ID_RE`를 통과해 "아무도 쓰지 않은 유효해 보이는 id"가 된다.
  `"id"` 항목을 `"wiki_id"`로 바꿔 그대로 유지한다.

교체 대상: `scripts/wiki_graph.py` · `skills/wiki-init/SKILL.md`(2·3·5·6·8절) ·
`skills/wiki-init/references/defect-template.md` · `skills/doc-sync/SKILL.md`(Mode W 2·4단계) ·
`rules/harness-rules.md` 8-2 · `skills/harness-authoring/templates/`의 sds · srs · code-style
3종 · `specs/2026-08-06-llm-wiki-design.md` · `tests/test_wiki_graph.py` ·
`scripts/skill_sandbox.py`.

## 2. 마커 누락 경고를 좁힌다

전용 키로 바꾸면 "Front Matter는 있는데 노드가 아니다"가 **정상 상태**다. Docusaurus 저장소에서
전수 경고는 매 커밋 영구 노이즈가 된다.

대신 wiki 전용 필드를 신호로 쓴다:

```python
WIKI_ONLY_FIELDS = ("related", "depends_on", "affects", "sources")
```

이 중 하나라도 있는데 `wiki_id`가 없으면 경고한다. `related:`를 손으로 썼다는 건 노드로 쓰려던
의도가 분명하다는 뜻이다. `tags`는 Jekyll · Docusaurus도 쓰므로 신호에서 제외한다. 기존
`WARN_CAP = 3` 캡을 그대로 따른다.

## 3. 파싱 실패를 표면화한다

`collect_nodes`가 파싱 실패 문서를 버리지 않고 표식 노드로 담는다:

```python
{"id": None, "path": ..., "line_count": ..., "front": {}, "broken": True, "marker_seen": bool}
```

`front`를 `None`이 아니라 빈 dict로 두는 것이 요점이다. 기존 소비자(`build_graph` ·
`cmd_stale` · `collect_warnings`의 sources 검사)는 모두 `if not node["id"]: continue`로
걸러내므로 `None` 역참조 위험이 번지지 않는다.

"파싱 실패"의 정의를 못 박는다. `parse_front_matter`는 서로 다른 세 상황에 똑같이 `None`을
반환하므로, 그 반환값만으로는 표식을 달 수 없다:

| 원문 | 판정 |
|---|---|
| `---`로 시작하지 않음 | Front Matter 없음 — **표식 없음**(조용히 통과) |
| `---`로 시작하나 닫는 `---`가 없음 | Front Matter 아님 — **표식 없음**. 문서 첫 줄의 수평선 · setext 밑줄이 흔하고, 이것까지 깨진 것으로 세면 노이즈가 된다 |
| 열고 닫는 `---`가 있고 그 안이 YAML 예외 또는 dict 아님 | **깨진 Front Matter** — 표식을 단다 |

`marker_seen`은 **원문 정규식**이다. YAML로는 못 읽지만 원문 Front Matter 블록에 `wiki_id:`로
시작하는 줄이 있는지는 볼 수 있다. 판정은 1절의 원칙과 같다 — 명백히 wiki 안에 있을 때만
차단한다.

| 상태 | 판정 | 근거 |
|---|---|---|
| 파싱 실패 + `wiki_id:` 줄 있음 | 차단 | 노드로 의도한 것이 명백하고 깨져 있다 |
| 파싱 실패 + `wiki_id:` 줄 없음 | 경고 | 남의 문서일 수 있다 |

차단 메시지는 파일 경로와 함께 YAML 파서가 낸 이유를 싣는다. `parse_front_matter`는 예외를
삼키고 `None`만 돌려주므로 그 이유를 알 수 없다 — 시그니처를 바꾸는 대신(직접 호출하는 기존
테스트 3건이 깨진다) 사유만 돌려주는 형제 함수를 두고 `collect_nodes`의 깨진 분기에서만
호출한다. 깨진 파일에 한해 두 번 파싱하지만, 그 경우는 드물고 비용은 파일 하나다.

이 규칙으로 `/wiki-init` 8절의 "verify 통과 = wiki가 강제되고 있다"는 주장이 wiki 노드에 한해
참이 된다.

Invariant #1(FAIL-OPEN)과 충돌하지 않는다. 여기서 차단하는 것은 게이트의 내부 오류가 아니라
"검증 대상이 규칙을 어겼다"는 판정이고, 판정 근거는 저장소 상태가 아니라 문서 원문 하나뿐이다.

## 4. `problems` 출력 캡

`validate_structure`의 반환값은 무제한으로 유지한다 — 순수 함수이고 테스트가 전수를 확인한다.
캡은 `cmd_verify`의 출력 단계에서만 적용한다: `PROBLEM_CAP = 10` + `... 외 N건`.

캡은 **구조 위반 구간에만** 건다. `cmd_verify`는 구조 위반 목록 뒤에 drift 사유를 덧붙이고
그 경계를 이미 `structural = len(problems)`로 들고 있다. 합쳐진 리스트에 캡을 걸면 구조 위반
10건이 drift 사유를 밀어내 "graph.yaml이 어긋납니다"가 사라지고, 그러면 저자는 두 해소 경로 중
하나를 보지 못한다. 구조 위반 앞 10건 + 카운트, 그 뒤 drift 사유는 항상 전부 출력한다.

`WARN_CAP = 3`을 재사용하지 않는다. 경고는 표본이지만 problems는 저자가 처리해야 할 **작업
목록**이다. 3건씩 끊으면 위반 20건을 해소하는 데 `--verify`를 일곱 번 돌려야 한다. 10줄은
deny 메시지로 아직 읽힌다.

drift 노드 목록의 기존 3건 캡은 그대로 둔다 — 그쪽은 "어느 문서가 어긋났는지"의 표본이고,
해소 명령(`--build`)이 개수와 무관하게 하나다.

## 5. dangling edge 메시지

3절이 진범(깨진 Front Matter)을 직접 차단하므로 오지목 시나리오의 대부분이 사라진다. 남는
경우는 저자가 `related:`에 없는 id를 적은 것이고, 그때는 참조자가 실제로 범인이다. 따라서 코드
구조는 그대로 두고 문구만 양쪽을 지목하도록 고친다:

```
docs/index.md: related 가 가리키는 id 'broken' 인 노드가 없습니다
  — 대상 문서의 wiki_id 를 확인하거나 이 항목을 고치세요
```

## 6. `/wiki-init` 8절 롤백 지시

`--build`는 `enable: true`를 요구한다(`load_wiki_config`가 비활성 wiki에 `None`을 반환하고
build · verify가 둘 다 no-op이 된다). 그래서 7절을 8절 뒤로 옮길 수 없고, 순서는 유지한다.

1절이 남의 문서를 검증에서 빼므로 8절의 `--verify`를 막을 수 있는 것은 마법사가 방금 쓴 문서의
저작 오류뿐이다. 게다가 9절이 "커밋하지 마라"이므로 게이트가 사람을 실제로 막는 시점은 세션이
끝난 뒤다. 남은 구멍은 8절을 끝내지 못하고 중단되는 경우 하나이고, 지시 한 문단으로 메운다:

> 이번 세션 안에서 `--verify`를 통과시킬 수 없으면 7절의 `enable`을 `false`로 되돌리고 남은
> 위반을 보고하라. 게이트를 켜 둔 채 끝내면 다음 커밋이 전부 막힌다.

## 테스트

TDD 대상은 게이트 판정 로직 전부다.

- `wiki_id` 마커: 남의 `id: Getting_Started`는 노드가 아니고 차단도 없다 / 형식 위반
  `wiki_id`는 차단된다 / `wiki_id: 0123456`은 타입 위반으로 차단된다
- 좁힌 누락 경고: `related`가 있고 `wiki_id`가 없으면 경고 / wiki 전용 필드가 없으면 침묵 /
  `tags`만으로는 경고하지 않는다
- 파싱 실패: 원문에 `wiki_id:`가 있으면 차단하고 파일명을 지목한다 / 없으면 경고하고 통과한다 /
  경고가 나가므로 더 이상 무음이 아니다
- `PROBLEM_CAP`: 위반 12건 → 10줄 + `... 외 2건`, 그리고 `validate_structure`의 반환값은
  여전히 12건
- dangling edge 메시지가 대상 id와 참조자를 모두 담는다

기존 회귀 보호: BOM 처리 · git 인덱스 기반 노드 집합 · authoritative 아닐 때의 FAIL-OPEN ·
drift 판정은 이번 변경의 영향을 받지 않아야 하며, 해당 테스트가 그대로 통과해야 한다.

## 문서와 픽스처

`scripts/skill_sandbox.py`의 `wiki-init-migration` 골든은 `must_contain: ["id:"]`를 쓴다.
`"id:"`는 `wiki_id:`의 부분문자열이라 키를 바꿔도 우연히 통과한다 — 반드시 `"wiki_id:"`로
조인다. 조이지 않으면 골든이 마커 전환을 전혀 검증하지 못한다.

`SKILL.md` 본문 · fixture · golden이 바뀌면 `outcome_sha`가 무효화되어
`evals/outcome_scores.json`의 `wiki-init` 베이스라인이 낡는다. 구현 완료 후
`uv run python -m evals.outcome --skill wiki-init`로 재측정한다 (모델 호출, reps 3).

## 범위 밖

- `wiki.exclude` 글롭. 1절이 충돌 원천을 제거하므로 필요가 없어졌다.
- `--verify`의 예행(dry-run) 플래그. 6절의 지시 한 문단이 같은 구멍을 코드 변경 없이 메운다.
- 원 계획서(`plans/2026-08-06-llm-wiki.md`) 갱신. 실행 완료된 기록이고 인용하는 코드도 없다.
