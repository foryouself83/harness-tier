# LLM Wiki 보강 (읽기 경로 · blob-hash stale · 게이트 통합) 설계

- 날짜: 2026-08-13
- 브랜치: `feature/wiki-hardening`
- 티어: DEV (gates: precommit · review · doc-sync · wiki)
- 선행 분석: 이 세션의 LLM Wiki 문제점 분석 15건. 근거 설계는
  [2026-08-06-llm-wiki-design.md](2026-08-06-llm-wiki-design.md)

## 배경과 목표

wiki 구현 자체는 견고하나 구조 레벨 문제가 남았다: 읽기 소비자가 없어 비용-가치가
비대칭이고, squash 승격마다 가짜 stale이 나고, sha 도장 정직성이 프롬프트 규율에만
의존하며, 터미널/CI 커밋 공백을 메울 CI 검증이 없다. 이번 작업은 그 전부를 한
브랜치에서 해소한다. 아래 결정은 모두 사용자 확인을 거쳤다.

| 항목 | 결정 |
|---|---|
| 읽기 경로 | 포함 — `--nodes-for` 역조회 + `/flow` Dev 단계 조회 지시 |
| stale 기준 | 커밋 sha → **blob hash** (`git hash-object`) 전환, `--stale`이 마이그레이션 값 제공 |
| 도장 검증 | `--verify`에서 **block**, 의미보존 재작성(마이그레이션)은 허용 |
| orphan | index 전 노드 열거 강제 **완화** — 실제 edge 연결 요구 (코드 무변경) |
| 게이트 프로세스 | `--wiki-check`를 `main()`에 흡수, runner 스테이지 2 삭제, spawn 2→1 |
| CI | 신규 `github/wiki-verify.workflow.example.yml`, `/flow-init` 무조건 렌더 + 자체 도그푸드 |
| graph.yaml 충돌 | 텍스트 안내만 (merge driver 기계화는 silent 오해소를 유발해 배제) |

## 1. 읽기 경로 — `--nodes-for` + /flow 조회 단계

wiki의 첫 실소비자. 지금 `--neighbors`의 유일한 호출자는 doc-sync Mode W이고, 개발
작업이 위키를 읽는 경로가 없다.

### `wiki_graph.py --nodes-for <경로...>`

- 각 인자 경로에 대해, 그 경로를 `sources` 키로 문서화한 노드를 `경로<TAB>id`로
  stdout에 출력한다 (한 경로에 노드 여럿이면 여러 줄).
- 매칭은 정확 일치 + **세그먼트 경계 포함(양방향)**: `src/auth` 와
  `src/auth/jwt.py` 는 서로 매칭되고 `src/auth-x/…` 는 아니다 (`derive_wiki_id`
  root 절단과 같은 경계 규칙). 양방향인 이유는 어느 쪽이든 굵은 경로일 수 있기
  때문이다 — 호출자는 바꿀 **파일**을 넘기는데 노드의 `sources` 는 그 파일을 담은
  **디렉터리**를 문서화할 수 있고, 한 방향만 보면 그 노드가 실제로 오는 유일한
  질의에서 영영 안 잡힌다. 구분자는 `_norm_rel`로 정규화한다.
- 다만 **디렉터리 키는 staleness 추적 대상이 아니다** — 판정이 파일 내용의 blob
  hash라 디렉터리에는 붙지 않는다(`_blob_hashes`가 `is_file()`로 거른다). 즉 조회에는
  걸리되 `--stale`에는 영영 안 나오고 마커도 갱신되지 않는다. wiki-init Step 5가 이
  비대칭을 저작 지침으로 싣는다.
- 조회 전용: 항상 exit 0, wiki 미설치면 무출력. 못 찾은 경로는 조용히 건너뛴다 —
  "이 코드는 문서화 안 됨"이 정상 답이기 때문이다 (`--neighbors`의 없는-id exit 1과
  다른 이유: 저긴 id 오타, 여긴 정당한 부재).
- 노드 집합은 `_load()` 재사용 (in-memory build, git 인덱스 기반).

### /flow Dev 단계 지시

`skills/flow/SKILL.md` Dev 경로에, superpowers 착수 **전** 조회 단계를 추가한다:
wiki가 켜져 있으면 변경 예정 파일 경로로 `--nodes-for` → 얻은 id마다 `--neighbors`
→ 나온 문서를 읽고 작업 컨텍스트로 삼는다. wiki 미설치면 두 명령 다 무출력/무해라
분기 설명은 한 줄이면 된다. `allowed-tools` 사전 승인은 두지 않는다 — 인자가
가변이라 유한 열거가 불가능하고, 끝을 `*`로 여는 규칙은 skill-frontmatter 규율
위반이다 (doc-sync가 `--neighbors`를 열거하지 않는 것과 같은 근거).

## 2. stale 기준 blob-hash 전환

### 의미 변경

`sources[path]`의 기록 값 의미를 "마지막 동기화 **커밋** sha" → "동기화 시점에 읽은
파일 **내용**의 blob hash"로 바꾼다. 도장은 `git hash-object -- <path>` (working
tree 내용 — doc-sync가 실제로 읽은 것), 판정은 기록 blob vs 현재 working tree blob
비교다.

- squash/rebase/amend 등 히스토리 재작성에 완전 면역 — 내용이 같으면 hash가 같다.
  daily 플로우의 feature=Squash 승격마다 나던 가짜 stale이 소멸한다.
- `git log -1` per-path 호출이 사라진다. `git hash-object`는 인자 여러 개를 받아
  줄 단위로 답하므로 **spawn 1회**로 전 경로를 처리한다 (Windows spawn 비용 —
  기존 head_cache 주석의 문제의식 그대로).
- `--stale` JSON의 `recorded`/`current`가 blob hash가 된다. `missing` 의미 불변.
- defect 노드의 `commit` 필드는 그대로 커밋 sha다 (다른 필드, 형식 검사만).
- prefix 비교(`current.startswith(recorded)`)와 `_SHA_RE`는 유지 — hex 40자 동일.

### 마이그레이션 — `--stale`이 값을 제공

기존 기록은 커밋 sha라 blob과 절대 일치하지 않는다. 재독해 없는 기계 변환이
가능하다: "커밋 X에서 동기화" ≡ "X 시점 그 경로 내용과 동기화" 이므로
`git rev-parse <기록>:<경로>` 가 의미보존 변환이다. 내용이 그 후 안 변했으면 새
기준으로도 fresh, 변했으면 여전히 stale — 판정이 정확히 보존된다.

- `cmd_stale`은 기록 값이 커밋을 가리키면(`git cat-file -t` == `commit`) JSON
  항목에 `"migrated": "<rev-parse 결과>"` 를 추가한다. doc-sync는 그 값으로 front
  matter를 재작성하면 된다 — 본문 재독해 불필요.
- 커밋이 소멸했으면(GC 등) `"migrated": null` — 일반 stale로 처리한다 (doc-sync가
  코드를 읽고 본문 동기화 후 새 blob으로 도장).
- `cat-file`/`rev-parse` 실패는 FAIL-OPEN으로 해당 항목만 일반 stale 취급.

doc-sync Mode W의 도장 지시를 blob hash(`git hash-object`)로, 마이그레이션 항목
처리를 1단계에 추가한다.

## 3. 도장 정직성 검증 — `--verify`에서 block

"본문을 고친 노드만 sha를 갱신한다"는 지금 순수 프롬프트 규율이다. 기계 검증을
`cmd_verify`에 편입한다 — doc-sync의 자체 `--verify`가 세션 안에서 먼저 잡고,
같은 검사가 커밋 게이트에서도 돈다.

### 판정 규칙

노드 파일별로 `git show HEAD:<경로>` 원문과 현재 원문을 확보해 **파싱 결과로**
비교한다 (diff 헌크 파싱 아님 — drift 비교를 바이트가 아닌 파싱으로 하는 기존
원칙과 동일):

- 본문(front matter 블록 이후 전체)이 동일하고, front matter 차이가 **`sources`
  값 교체뿐**인 파일만 검사 대상이다. 본문이 바뀌었거나 다른 필드도 바뀐 파일,
  HEAD에 없는 새 파일은 자유 (신규 문서의 최초 도장은 저작 자체가 동기화다).
- 본문 편집이 **HEAD 안에** 있는 경우도 자유다: `HEAD~1`의 본문과 HEAD의 본문이
  다르면 직전 커밋이 그 문서를 동기화한 것이므로, 지금 도장을 찍는 것도 그것을
  amend 로 합치는 것도 정직하다. 이 분기가 없으면 차단 메시지가 권하는 amend 를
  검사가 스스로 막는다 (amend 시점 HEAD 는 이미 본문 편집을 담고 있어 남은 델타가
  sha 뿐이기 때문). `HEAD~1` 자체가 없으면(루트 커밋·git 실패) 판정 불가로 통과한다.
  `HEAD~1`은 읽히는데 그 경로만 없으면 **신설 또는 개명**이다: `git diff HEAD~1 HEAD
  -M --name-status -z` 로 이전 경로를 되짚어, 개명이면 이전 경로의 본문과 비교를
  이어간다 (rename+동기화 커밋 뒤로 도장을 미룬 경우도 위 amend 분기와 같은 모양이
  되도록 — 이 역추적이 없으면 그 도장과 amend 가 둘 다 막히고, 커밋이 하나뿐이라
  rebase/fixup 권고도 무의미하다). rename 기록이 없으면 신설 — 신설 커밋은 자기
  도장을 이미 들고 있으므로 동기화가 아니고, 검사를 계속한다 (본문 무변경의 순수
  rename 뒤 sha 교체도 같은 이유로 차단 유지 — 이동은 아무것도 동기화하지 않는다).
  잔여 오탐 셋은 남긴다. ① -M 은 유사도 기반이라 개명과 대규모 재작성이 한 커밋에
  겹치면 신설로 읽힌다. ② rename 조회를 위키 root 로 제한하므로 **root 밖에서 안으로**
  들여온 이동도 신설로 읽힌다(root 밖 문서는 애초에 노드가 아니라 도장 이력이 없다).
  ③ `diff.renameLimit` 초과로 git 이 유사도 탐지를 **생략**하면 출력이 D+A 로 떨어지고
  그 경고는 stderr 로만 나와 `_git` 이 버리므로, "개명 없음"과 구별되지 않는다. 정확
  개명(내용 동일)은 해시 매칭이라 limit 밖이지만, 이 게이트가 다루는 모양은 정확히
  개명+본문 동기화 = 유사도 탐지 대상이다. 셋 다 해소는 차단 문면대로 sha 되돌림
  또는 본문 커밋 분리다.
- 검사는 **같은 키의 non-null 값 교체 (old → new)만** 본다: `new == git rev-parse
  <old>:<경로>` (2절 마이그레이션)이면 허용, 아니면 **block**. `null → sha`(최초
  등록 — falsify할 기존 주장이 없다)와 항목 추가/삭제(missing-path 해소의 정당한
  편집)는 자유다. 키 삭제+재추가로 우회할 수는 있으나, 이 검사의 목적은 악의
  차단이 아니라 성실한 세션이 무심코 하는 일괄 재도장의 차단이다.
- 차단 사유는 해소를 문면에 싣는다: 본문을 실제 동기화했으면 그 편집과 같은
  커밋에서 찍고, 아니면 sha 줄을 되돌리라는 안내.

### FAIL-OPEN 경계

`cat-file`/`rev-parse` 실패, HEAD 부재(첫 커밋) 등 원문을 못 얻는 모든 경우는 그
파일을 건너뛴다 (Invariant #1 — 검사 불가는 위반이 아니다). 이 검사가 새로 막는
것은 "정확히 sha만 바꾼 커밋"뿐이며, 그 판정에 추정이 없다.

`_git`은 **"객체가 없다"(정당한 nonzero)와 "git이 답하지 못한다"(타임아웃·강제
종료)를 둘 다 `None`으로** 돌려주므로, `None`이라는 사실만으로 차단 흐름을 태우면
내부 오류가 커밋을 막는다. 침묵을 판정으로 승격하는 지점마다 구별 질의를 둔다:

- **부모 본문 읽기**가 `None`이면 `rev-parse --verify HEAD~1:<경로>`로 되묻는다. 객체가
  **있으면** "부모에 없다"는 판정이 아니므로 통과, 없으면 비로소 신설/개명 분기로 간다.
  실질 이득은 읽기 flake·gitlink 처럼 객체는 있는데 본문이 안 나오는 경우다. 읽기를
  `show` 대신 `cat-file blob` 으로 두는 것은 그 위의 정확성 문제 — 부모에서 그 경로가
  트리였으면 `show`는 tree 목록을 exit 0으로 내고, 그 목록이 "본문이 다르다"로 읽힌다.
  (허용이라는 결과는 우연히 같아서, 테스트는 결과가 아니라 경유 질의를 고정한다.)
- **마이그레이션 조회**가 `None`이면 저장소 안에서 반드시 성공하는 질의(`rev-parse
  --verify HEAD`)를 던져, 그것마저 실패하면 통과시킨다.
- **`_head_renames` 의 출력이 읽히지 않으면** `{}` 가 아니라 `None`. 빈 맵은 "개명이
  없다"는 판정이라 정당한 개명+동기화를 차단으로 몬다. 정상 출력은 레코드마다 NUL 로
  끝나고(변경이 없을 때만 빈 문자열) 빈 필드는 종료자 자리에만 온다 — 그래서 NUL 로 안
  끝나는 꼬리·중간의 빈 status·빈 경로·필드가 모자란 레코드가 전부 `None` 이다.
  기록 대상은 `R` 뿐이다. `C` 는 원본을 남기므로 개명이 아니고(도장을 미룬 문서는
  *이동한* 원본을 탄다), 세 필드를 소비하되 맵에는 넣지 않는다 — `-M` 만 넘기는 한 git 이
  `C` 를 낼 일은 없지만 파서가 그 보장에 기대지는 않는다.

저장소 상수인 답(부모 커밋 존재·HEAD 생존·개명 목록)은 **호출당 1회** 조회하고 재사용한다
— 되물으면 8절이 아낀 spawn 을 차단 경로에서 도로 쓴다. 문서 40개·소스 3개 기준으로 HEAD
생존은 swap 단위라 120회, 부모 커밋과 개명 목록은 노드 단위라 40회씩이다. 특히 개명 목록은 "아직 조회 안 함"과 "조회했는데 못 답함"을 별도
플래그로 가른다: `None` 하나로 겸하면 **실패한** 조회가 개명 노드마다 되풀이되고,
`-M` 은 이 게이트가 던지는 가장 비싼 질의에 `_git` 타임아웃이 5초라 최악 N×5초가 커밋
훅 안에 들어앉는다.

본문 편집을 앞 커밋에 두고 도장을 뒤 커밋으로 쪼갠 경우는 위 `HEAD~1` 분기가
정식으로 허용한다 — 초판에서 "알려진 오탐"으로 남겨두었으나, 그 오탐의 유일한
해소책이 amend 였고 amend 역시 같은 모양이라 막혔다.

`HEAD~1`은 머지 커밋에서 first parent이므로, 머지 직후 한 커밋 동안은 머지가 반대편에서
가져온 문서들이 본문 편집 없이 재도장될 수 있다. 부모 수를 세어 막지 않는 것은 의도다 —
노출이 "직전 커밋이 그 노드의 본문을 실제로 바꾼 노드"로 한정되고, 조이면 머지가 가져온
동기화에 도장을 얹는 정당한 커밋이 대신 막힌다.

## 4. CI read-only 검증 — 신규 example workflow

layer 2가 못 보는 터미널/직접 push 커밋의 drift를 layer 3에서 잡는다. 생성은
여전히 doc-sync/wiki-init 전용이고 CI는 **검증만** 한다 (기존 설계 결정 불변).

- 신규 `github/wiki-verify.workflow.example.yml`: push + pull_request 트리거,
  단일 job — checkout → setup-python → `pip install pyyaml` →
  `python3 .claude/harness-tier/scripts/wiki_graph.py --verify`.
  `timeout-minutes: 5`. `run:` 블록에 `${{ }}` 금지 (기존 저작 규칙,
  test_flow_init_setup이 강제).
- `/flow-init`이 **무조건** 렌더한다. wiki 미설치 호스트에서는 스크립트가 무출력
  exit 0이라 job이 green — 설치 순서 의존이 없다 (`/flow-init`이 `/wiki-init`보다
  먼저라는 순서 문제를 조건부 렌더 대신 no-op으로 푼다).
- 자체 도그푸드: `.github/workflows/wiki-verify.yml` — `uv run python
  scripts/wiki_graph.py --verify` (이 저장소는 호스트 설치가 없으므로 SOURCE를
  직접 실행; wiki 미설치 no-op 경로가 도는 것 자체가 계약 검증이다).
  timeout-minutes 부여.
- checkout 기본 fetch-depth(1)로 충분 — `--verify`가 쓰는 git은 `ls-files`뿐이고,
  drift 귀속용 `git log -1`은 실패 시 빈 문자열 fail-soft다.

## 5. orphan 의미 복원 (코드 무변경)

`wiki-init` Step 6의 "index `related:`에 **모든** 노드 id 열거" 강제가 그래프를
star로 퇴화시키고 orphan 검사를 "index 갱신 누락 검사"로 만든다. 도달성 로직은
이미 옳으므로 스킬 지시만 고친다:

- wiki-init Step 6: index `related:`는 **최상위 진입 노드만** 싣는다. 그 외 노드는
  의미상 관련된 노드와의 실제 edge(`related`/`depends_on`)로 index에서 도달돼야
  한다. orphan 경고의 해소 지시도 "관련 노드에 연결하라, 최상위 개념이면 index에
  추가하라"로 바꾼다.
- body 링크 목록 ↔ `related:` 전항목 상호 동기화 강제를 삭제한다 (이중 SSOT 유지
  비용만 있고 검증도 없다). index body는 사람용 랜딩으로 자유 저작.
- doc-sync Mode W 4단계의 "새 id를 index related에 추가" 지시를 같은 취지로
  수정한다.

기존에 전 노드를 열거해 둔 호스트는 그대로 유효하다 (star도 도달 가능 그래프다) —
마이그레이션 불필요, 새 문서부터 새 규율.

## 6. graph.yaml 충돌 해소 안내

생성물이 커밋되므로 병렬 브랜치 병합에서 YAML 충돌이 난다. 올바른 해소는 항상
재빌드다. wiki-init Step 8과 doc-sync Mode W 6단계에 한 단락: **충돌 마커를 손으로
고치지 말 것** — 아무 쪽이든 `git checkout --ours|--theirs`로 정리한 뒤 `--build`
재실행, 재빌드본을 문서와 함께 스테이징. merge driver(`merge=ours` 류)는 두지
않는다 — 충돌은 주의를 강제하지만 driver는 틀린 그래프를 조용히 통과시켜 다음
`--verify` 차단으로 미룬다.

## 7. front matter 파서 경계 수정

`_front_matter_block`의 닫는 구분자 탐색 `text.find("\n---")`은 `----`(hr)와
`---`로 시작하는 열 0 본문 줄에 오매칭해 블록을 조기 종결한다.

- 여는 줄: `^---[ \t]*\r?\n` (첫 줄이 정확히 `---`, 후행 공백 허용).
- 닫는 줄: 멀티라인 정규식 `^---[ \t]*\r?$` (CRLF 허용) — 줄 전체가 `---`일 때만.
- 남는 한계: 인용 멀티라인 스칼라 **안의** 정확한 `---` 단독 줄은 여전히 닫는 줄로
  읽힌다 — 구분에는 진짜 YAML 스캐너가 필요하고, 그 경우 잘린 파싱이 시끄럽게
  실패한다(marker 보이면 block) — 조용한 노드 소실은 아니다.
- 반환 계약(블록 텍스트 / None)과 두 소비자(`parse_front_matter` ·
  `_broken_front_matter`) 공유 구조는 그대로.
- 부수: 원문 front matter에 `wiki_id:` 줄이 2개 이상이면 경고 추가 (PyYAML
  last-wins가 조용히 뒤 값을 채택하는 것을 표면화; `_MARKER_LINE_RE` findall 재사용).

## 8. 게이트 프로세스 통합 — spawn 2→1

`--wiki-check` 로직을 `main()`으로 흡수한다. flow gate 판정(exit 2 단락) **통과
후** 같은 프로세스에서 `wiki_gate(root, gates)`를 실행한다 — tier/gates는 main이
이미 해석한 것을 재사용 (현재는 `wiki_check_output`이 두 번째 프로세스에서 다시
해석한다).

- 차단: 기존 채널 그대로 — 사유를 stdout에 내고 exit 2 (runner의 `flow_reason`
  경로가 이미 stdout·exit 2 계약이다).
- 통과+경고: exit 0 + `{"systemMessage": …}` JSON을 stdout으로 — 지금
  `--wiki-check`의 계약을 main이 이어받는다. runner는 exit 0이고 stdout이 비어
  있지 않으면 그것을 `wiki_note`로 잡아 `allow()`에서 흘려보낸다.
- `precommit-runner.sh` 스테이지 2(별도 `--wiki-check` 호출) 삭제.
  `HARNESS_PRECOMMIT_DRYRUN=1`일 때 wiki gate를 건너뛰는 현재 동작은 main 쪽
  분기로 보존한다.
- `--wiki-check` 플래그는 **호환 alias로 존치** (러너·스크립트가 COPY_FILES로 함께
  배포되지만, 반쯤 복사된 호스트의 skew에서 죽지 않도록 — 비용은 분기 하나다).
- stdout-only 원칙(인터프리터 오류 stderr와의 분리)은 그대로 유효하다 — runner는
  여전히 `2>/dev/null`.

## 9. 문서 수정 묶음

- **wiki-init Step 5**: "collision-free" 주장 축소 — 그 순서 규칙이 보장하는 것은
  `docs/a.b.md` vs `docs/a/b.md` 계열뿐이고, 같은 디렉터리의 `a.b.md`/`a-b.md`/
  `a_b.md`는 전부 `a-b`로 충돌한다. 충돌은 `--verify` 중복 검출이 잡고 해소는
  파일명 변경임을 명시.
- **wiki-init Step 2·4**: H2 휴리스틱 완화 — "줄 수 높고 H2 여럿 = 다개념"은
  **신호**이지 판정이 아니다. Installation/Usage/FAQ처럼 H2가 여럿이어도 단일
  개념인 문서는 분리하지 않는다 — 경계는 내용으로 판단.
- **wiki-init Step 5**: rename 규칙 명시 — `wiki_id`는 최초 파생 후 **불변**이다.
  파일을 옮기거나 개명해도 재파생하지 않는다 (id가 링크 안정성의 근거).
- **`neighbors()` docstring**: 예산 의미를 명시 — 초과 노드는 잘라내고 확장을
  계속하는 greedy다 (설계문서의 "예산 도달 시 중단" 표현과 실제 동작의 차이를
  구현 쪽 문서가 보유).
- **CLAUDE.md**: 검증 레이어 2 서술의 "자체 `--wiki-check` 스텝" 문구를 통합 후
  구조(main 흡수, alias 존치)로 갱신. layer 3 서술에 wiki-verify 렌더 추가.
- README/USAGE 및 한국어 쌍둥이는 doc-sync가 정리한다.

## 10. 테스트

**`tests/test_wiki_graph.py` 추가분**

- `--nodes-for`: 정확 일치 · 세그먼트 경계는 **양방향 모두**(질의가 디렉터리인
  `src/auth` vs `src/auth-x`, 질의가 파일인 `src/auth-x/jwt.py` 대 `src/auth` 노드) ·
  파일 질의로 디렉터리 sources 노드 조회 · 다중 노드 다중 줄 · 미문서화 경로 무출력 ·
  wiki 미설치 무출력 exit 0
- blob stale: hash-object 기반 판정 (기록==현재 blob → fresh, 다름 → stale) ·
  `missing` 불변 · 커밋형 기록의 `migrated` 값 == `rev-parse <기록>:<경로>` ·
  소멸 커밋 `migrated: null` · spawn 배치(경로 N개에 hash-object 1회)
- 도장 검증: sha만 교체 → block · 마이그레이션 값(rev-parse old:path) 교체 → 허용 ·
  본문 동반 변경 → 허용 · 새 파일 → 허용 · `git show` 실패 → fail-open ·
  직전 커밋이 본문을 동기화 → 허용 · 무관한 커밋이 직전이면 여전히 block ·
  HEAD가 신설한 문서는 계속 검사 · 루트 커밋 fail-open · rev-parse 불능 fail-open
- 파서 경계: `----` 첫 줄은 블록 아님 · 열 0 `--- note` 본문 줄은 닫는 줄 아님 ·
  닫는 줄 후행 공백/CRLF 허용 · `wiki_id:` 중복 줄 경고
- 기존 테스트 회귀: drift·구조 위반·경고 캡 전부 통과 유지

**`tests/test_flow_gate_check.py`**

- main 통합 경로: flow gate 통과 + wiki 위반 → exit 2 + 사유 stdout / 통과+경고 →
  exit 0 + systemMessage JSON / DRYRUN → wiki 생략
- `--wiki-check` alias가 기존 계약 그대로 동작

**`tests/test_flow_init_setup.py`**: wiki-verify 렌더 존재 · timeout-minutes 상한 ·
`run:` 블록 `${{ }}` 부재 검사에 신규 파일 포함

**ShellCheck**: `precommit-runner.sh` 수정분 (WSL에서 실행 검증 — Windows 훅
런타임의 FAIL-OPEN 은폐 때문).

**evals**: doc-sync·wiki-init·flow의 SKILL.md 본문 변경 → outcome 시나리오 보유
스킬은 `outcome_sha` 변경 → `uv run python -m evals.outcome` 재측정.
`description`은 어느 스킬도 바꾸지 않는다 → invocation arm 불변.

## 11. 커밋

`feat` 단일 커밋 (consumer-facing rules/skills 변경의 전파 조건 + 사용자 단일 커밋
규율). spec·plan도 같은 커밋에 싣는다 — dev 티어 게이트(review·doc-sync)가 마커를
요구하므로 중간 커밋을 두지 않는다.

## 범위 밖

- 경고 억제/베이스라인 메커니즘 (#6 경고 피로) — 반복 노이즈의 실害가 확인되면
  `wiki.warn` 류 config로 별도 작업. 지금은 YAGNI.
- 순수 `git merge`의 사전 wiki 검증 — PreToolUse는 병합 **결과**를 볼 수 없어
  원리상 불가. CI 검증(4절)이 이 공백의 실질 보완이다.
- 전문 검색 인덱스(BM25) — 여전히 진입점 탐색은 범위 밖. `--nodes-for`는 "변경
  코드에서 진입"이라는 개발 플로우의 진입점만 연다.
- 커밋당 파싱 캐시/증분화 — 수백 노드 실측 문제가 생기면 그때.
