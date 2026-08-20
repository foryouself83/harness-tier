# wiki_id 파생의 실행화 (derive_wiki_id + --derive-id)

## 배경

`wiki_id` 파생 규칙은 산문으로만 존재한다 (`skills/wiki-init/SKILL.md` §5).
`skills/harness-authoring/references/authoring-spec.md` 가 그 규칙을 재서술하다 단계
순서를 뒤집었고 (`.` join 후 정규화 — `docs/a.b.md` 와 `docs/a/b.md` 가 같은 id 로
붕괴), 몇 달간 아무것도 이를 잡지 못했다. `wiki_graph.py` 의 `WIKI_ID_RE` 는 모양만
검증하므로 틀린 순서의 산물도 통과하고, 증상은 나중에 duplicate-id `--verify` 블록으로
나타난다 — 그 시점엔 모든 커밋이 막힌다.

근본 원인: 규칙이 실행 가능하지 않아 (a) 재서술할 유인이 있고 (b) 재서술이 틀려도
검출이 없다.

## 목표

파생 규칙의 SSOT 를 코드(`derive_wiki_id`)로 내리고, 산문은 근거(왜)와
패리티-테스트되는 예제 표만 남긴다. 산문·구현·플랜 어느 쪽이 어긋나도 pytest 또는
validate_plan 이 지목한다.

## 비목표

- 기존 파일의 wiki_id 드리프트 감사 — 중복·형식은 `--verify` 가 이미 잡는다 (YAGNI).
- vway-kit 반영 — 두 repo 는 자동 전파가 없어 별도 작업.
- `allowed-tools` 변경 — `--derive-id` 는 인자가 값이라 이를 덮는 규칙이 `*` 로 끝날
  수밖에 없고, 그건 `--neighbors` 가 이미 의도적으로 포기한 footgun
  (`.claude/rules/skill-frontmatter.md`). 프롬프트가 비용이다.
- CI·게이트 변경 — 파생은 커밋 훅 어디서도 돌지 않는다.

## 설계

### A. `derive_wiki_id(path, root="docs") -> str` — `scripts/wiki_graph.py`

`WIKI_ID_RE` 인근에 배치. 절차 (순서가 규칙의 일부):

1. 구분자 정규화 (`\` → `/`), root 접두가 있으면 벗긴다 — **세그먼트 경계 기준**
   (`docs-old/a.md` 는 root `docs` 의 접두가 아니다; 불변식 6 의 prefix footgun 과
   동형). 접두가 없으면 이미 root-상대로 취급 (`--derive-id docs/a.md` 와
   `--derive-id a.md --root docs/` 가 동치).
2. 마지막 세그먼트의 최종 확장자 하나를 제거 (`a.b.md` → `a.b`).
3. 소문자화.
4. **세그먼트마다** `[a-z0-9-]` 밖의 문자를 `-` 로 치환하고 연속 `-` 를 하나로 축약.
5. 세그먼트들을 `.` 로 join.

실패 = `ValueError` + 한국어 사유:

- 빈 경로, 경로가 root 자신.
- **퇴화 세그먼트** — 정규화 후 `[a-z0-9]` 가 하나도 없는 세그먼트 (한글만인 파일명
  등). 방출하면 한글 문서 둘부터 duplicate-id 로 커밋이 막힌다 — 이 기능이 없애려는
  바로 그 증상이므로 원천 거부. 사유에 해당 세그먼트를 지목 ("파일명을 영문으로").

### B. CLI `--derive-id PATH [PATH …] [--root DIR]`

- 기존 mutually-exclusive group 에 `nargs="+"` 로 추가.
- **root 우선순위**: `--root` > flow-config `wiki.root` > `docs`. config 읽기는
  `load_wiki_config()` 를 쓰지 않는다 — 그 함수는 `enable: false` 에 `None` 을
  돌려주므로, 그대로 쓰면 `enable: false` + `root: documentation/` 인 저장소에서
  조용히 `docs` 로 파생한다. `enable` 게이트를 우회해 `wiki.root` 만 읽는 소형 헬퍼
  (`_wiki_root_hint`, 읽기 실패는 `docs` 로 fail-soft). `/harness-init` 은
  `/wiki-init` 전에 돌 수 있으므로 (harness-rules 8-2) config 부재는 에러가 아니다.
- **fail-closed, Invariant #1 범위 밖**: 파생은 게이트 명령이 아니다 — 커밋 훅
  어디서도 돌지 않는다. `main()` 의 fail-open `try` **밖**에서 디스패치한다 (인자
  파싱과 `--derive-id` 분기를 try 앞으로; 게이트 명령 디스패치는 try 안에 유지,
  argparse 의 `SystemExit` 전파는 현행 유지). 출력 없는 성공(exit 0)은 호출자(모델)가
  "조용히 손으로 파생"으로 회귀하는 길이라 금지.
- **출력**: 성공 경로마다 stdout 에 `경로<TAB>id` 한 줄. 위치 zip 을 안 쓰는 이유:
  부분 실패 시 줄이 밀려 조용히 어긋난다.
- **부분 실패**: 성공분은 그대로 내보내고 실패분만 stderr 에 경로+사유 지목, 하나라도
  실패면 exit 1. 모델이 사유를 읽고 해당 경로만 고쳐 재시도한다 — harness-init 이
  멈추는 게 아니다.

### C. wiki-init §5 재작성

절차 서술(how)을 코드 위임으로 대체. 남기는 것:

- 근거 한 단락 — 순서가 규칙의 일부인 이유, 충돌 없음 성질 (`docs/a.b.md` → `a-b` vs
  `docs/a/b.md` → `a.b`), 손 파생 금지.
- **예제 표** (패리티 테스트의 입력 — 행 추가만으로 테스트 케이스가 늘어난다):

  | 경로 (root `docs/`) | wiki_id |
  |---|---|
  | `docs/code-style/python.md` | `code-style.python` |
  | `docs/a.b.md` | `a-b` |
  | `docs/a/b.md` | `a.b` |
  | `docs/api_spec.md` | `api-spec` |
  | `docs/sds/README.md` | `sds.readme` |
  | `docs/onboarding/README.md` | `onboarding.readme` |

- 명령 호출 안내 — `--neighbors` 전례대로 복사용 펜스 블록이 아니라 인라인 서술
  (경로가 동적 인자라 플레이스홀더 펜스는 skill-frontmatter 규율 위반).

### D. 테스트 2종 — `tests/test_wiki_graph.py`

- **단위**: 표의 6쌍 + root 접두 유무 동치 + `--root` 우선순위 + 퇴화 세그먼트
  `ValueError` + CLI (TAB 출력·부분 실패 exit 1·stderr 사유).
- **패리티**: §5 표를 마크다운으로 파싱해 각 행을 `derive_wiki_id` 에 먹인다. 행 수
  하한(≥ 5)으로 "표가 사라져 0쌍 매치 → 공허한 초록"을 막는다. 템플릿 YAML 주석의
  워크드 예제(`docs/code-style/python.md -> code-style.python` 꼴)도 같은 테스트가
  파싱해 대조한다. 산문 예제가 구현과 어긋나면 pytest 가 그 줄을 지목 — impl↔test
  가 아니라 impl↔산문을 pin 하는 게 목적.

### E. doc-sync Mode W 4단계

새 `.md` 의 `wiki_id` 를 산문 파생 대신 `--derive-id` 호출로 얻도록 문구 교체.
frontmatter 의 allowed-tools 주석에 `--derive-id` 부재 사유를 `--neighbors` 와 같은
줄기로 한 줄 추가.

### F. authoring-spec.md — 링크만 (작업 트리 반영 완료)

재서술 삭제, wiki-init Step 5 + harness-rules 8-2 링크로 축소.

### G. `harness_scaffold.py validate_plan` 파생 대조

plan 의 파일 중 wiki root 아래(`_wiki_root_hint` 와 같은 해석) `.md` 이고 front
matter 에 `wiki_id` 가 있으면 `derive_wiki_id(경로)` 와 대조, 불일치 시 issue
(`kind: "wiki-id"`, 기대값을 detail 에 포함). validate_plan 은 진단용
FAIL-OPEN 이므로 커밋을 막지 않고 preview 에 뜬다 — 모델이 명령을 안 부르고 손으로
틀리게 파생한 경우를 쓰기 전에 잡는 유일한 지점. `wiki_graph` import 는 기존
`_harness_paths` 와 같은 try/except 상대-절대 이중 경로.

## 구현 순서 (selective TDD — 파생 코어)

1. D 단위 테스트 먼저 (RED) → A+B 구현 (GREEN).
2. C 표 작성 + D 패리티 테스트 (같은 커밋에서 GREEN).
3. E, G (+ `tests/test_harness_scaffold.py` 케이스).
4. **Mutation test**: `derive_wiki_id` 의 sanitize/join 순서를 Python
   read-modify-write 로 뒤집고 (`assert old in text` 로 변형 적용을 단언) 스위트가
   빨개지는지 확인, `git checkout --` 복원.
5. `uv run pytest` · `uv run ruff check` · `uv run ruff format --check`.

## 커밋·전파

`scripts/wiki_graph.py` 는 `flow_init_setup.py COPY_FILES` 에 이미 있어 호스트 복사는
자동. consumer-facing (scripts + skills) 이므로 `feat` 로 커밋 (docs 로 커밋하면
릴리스가 안 나가 전파되지 않는다).
