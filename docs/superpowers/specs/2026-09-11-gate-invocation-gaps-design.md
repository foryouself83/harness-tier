# 커밋 게이트 호출 판정 결함 수정 설계

- 날짜: 2026-09-11
- 브랜치: `fix/gate-invocation-gaps` (Dev tier)
- 대상: `scripts/_harness_paths.py` (필요 시 `scripts/flow_gate_check.py` 주석)
- 관련 불변식: CLAUDE.md Invariant 6(워크트리 재지정), Invariant 7(git 호출 판정의 단일 권위)

## 배경

CLAUDE.md 축약 리뷰(3·4라운드)가 코드 대조 probe로 게이트가 커밋을 놓치는 경우를 찾음. 릴리스 태그
v0.3.2와 현재 HEAD를 같은 명령 행렬로 A/B 비교한 결과 두 버전의 판정이 전부 동일함 — 모두 릴리스
이전부터 있던 결함이며 이번 변경의 회귀가 아님.

재현 도구: 단위 probe(`is_invocation`·`_commit_dir_answers`·`_dir_from_command`·
`commit_tree_unresolved`)와, 실제 `precommit-runner.sh`를 워크트리 둘을 가진 임시 저장소에 돌리는 WSL
e2e probe. P1·P5a·P5b·P6·X1은 실제 bash에서 커밋이 생기는 것까지 확인함.

## 결함 목록

| ID | 명령 | 증상 | 원인 |
|---|---|---|---|
| P1 | `printf -v 'a[$(git commit …)]' 1` | 누락 | `printf`가 이름만으로 읽기 전용 면제. `-v`의 배열 첨자 평가가 `$(…)`를 실행 |
| P2 | `rg --pre git x commit` / `sort --compress-program=bash` | 누락 | 같은 이유. `--pre`·`--compress-program`은 인자로 받은 프로그램을 실행 |
| P5a | `awk -f - <<EOF` + `system("git commit …")` | 누락 | heredoc 본문은 `_RUNS_TEXT` 인터프리터가 보일 때만 스크립트로 읽음 — 목록에 없는 실행기면 게이트가 꺼짐 |
| P5b | `. /dev/stdin <<EOF` | 누락 | 같은 이유(`.`가 목록에 없음) |
| P6 | `bash <(echo; echo "git commit …")` | 누락 | `_substitutions`가 `<(`를 몰라 안쪽 `;`에서 요소가 잘리고, 잘린 꼬리가 `echo`만의 요소로 면제 |
| X1 | `echo commit -m x \| xargs git` | 누락 | xargs가 하위 명령을 표준 입력으로 받아 인자 순서가 뒤바뀜 — 문법이 `git … commit`을 못 봄 |
| D3 | `cd $WT && git -C . commit … && git commit --amend` | 누락 | `.` 정규화가 `commit_tree_unresolved`에만 있고 `_dir_from_command`에는 없음 → 두 판정이 엇갈려 선두 `cd`를 안 읽고 깨끗한 main을 검사 |
| D4a | `cd $WT1 && git commit; cd $WT2 && git commit` | 누락 | resolver는 선두 `cd X &&`만 따라감. 뒤따르는 `cd`는 unresolved로도 표시 안 됨 |
| D4b | `for d in …; do git -C "$d" commit; done` | 누락 | 전개되지 않은 `-C` 값을 디렉터리로 취급 → 해석 실패 후 hook cwd로 |
| D8 | `(cd $WT && git commit)` | 누락 | 서브셸 `cd`는 선두 prefix가 아니라 읽히지도, 표시되지도 않음 |
| D9 | `git -C ~/wt commit` | 누락(단위) | `~`를 펼치지 않아 해석 실패 |
| D7 | 워크트리 hook cwd에서 `cd $MAIN; git commit` | 과잉 차단 | `;` 형태 선두 `cd`를 안 읽어 hook cwd(워크트리) 기준으로 미분류 차단 |

## 설계 결정

| 질문 | 채택 | 기각안과 이유 |
|---|---|---|
| Q1 실행 플래그가 붙는 판독기 | 플래그 검사로 면제 제한 | 목록에서 제거: `rg "git commit" …` 같은 흔한 검색이 미분류 세션에서 차단되고 언급으로 고정된 사례 11건(corpus 7, net 4)이 뒤집힘 |
| Q2 heredoc 본문 | 허용 목록으로 판정 뒤집기 | 인터프리터 목록 확장: 목록에 없는 새 실행기가 나오면 다시 게이트가 꺼지는 구조가 남음 |
| Q3 디렉터리 변경 | unresolved 표시 + 선두 `cd X;` 읽기 | 표시만: D7이 남음. 불확실하면 main: 워크트리 세션의 `(cd sub && git commit)`이 main 기준으로 판정돼 새 과잉 차단 |
| Q4 xargs·parallel | 이번에 포함 | 후속으로 미룸: 같은 종류의 커밋 누락이고 변경이 작음 |

## §1 호출 탐지 (Invariant 7)

### (a) 실행 플래그 검사 — P1·P2

읽기 전용 목록은 유지하고, 아래 표의 프로그램은 실행 플래그가 없을 때만 면제함.

| 프로그램 | 면제를 잃는 토큰 | 근거 |
|---|---|---|
| `printf` | `-v`로 시작하는 토큰(`-v`, `-vNAME`) | bash 내장 `printf -v`는 대입이고 붙여 쓴 형태도 동작(실측) |
| `rg` | `--pre` 또는 `--pre=…`(`--pre-glob` 제외) | rg는 옵션 약어를 받지 않음(`--pr` 거부, 실측) |
| `sort` | `--co`로 시작하는 토큰 | GNU sort는 `--co`부터 `--compress-program`의 약어로 받음, `--c`는 `--check`와 모호해 거부(실측) |

- **값 판정(rg·sort)**: `--flag=VAL` 또는 다음 토큰이 VAL. VAL이 없거나 공백을 담지 않으면 실행 가능한 프로그램
  이름 → 면제 안 함. VAL에 공백이 있으면 존재할 수 없는 프로그램 이름이라 면제 유지 — corpus가 언급으로
  고정한 `rg --pre 'git commit' pattern .`, `sort --compress-program='git commit -m x' f`가 그대로 언급으로 남음.
- **전개**: 표의 프로그램 인자에 `$`나 백틱이 있으면 면제 안 함 — 전개 결과가 플래그가 될 수 있음.
- **적용 단위**: 파이프 구성원 각각(그 프로그램의 인자 범위)에서만 검사함. `printf x | rg -v y`의 `-v`는 rg의 것.
  프로그램 위치는 기존 `_programs` 한 곳에서만 읽고, 이 걷기가 위치와 인자 범위까지 돌려주도록 확장함 —
  프로그램 위치를 읽는 두 번째 판독기를 만들지 않음. 인자 범위의 끝은 `operand_end`.
- **토큰화**: 인자 범위 원문을 `shlex.split`(posix). 실패(`ValueError`)하면 면제 안 함.
- 비용: 표의 프로그램이 있는 요소에서만 토큰화하므로 다른 명령에는 추가 비용 없음.

### (b) heredoc 판정 뒤집기 — P5

- 읽기 전용 요소가 아니면 heredoc 본문을 항상 스크립트로 읽음 — 따옴표 텍스트와 같은 규칙. 누락된 항목은
  과잉 차단 쪽으로만 틀림.
- `is_invocation`의 heredoc을 지운 "plain" 보기와 `_INTERPRETER_RE`를 제거. `_RUNS_TEXT`는 `-c` 인자를
  코드 구간으로 보는 `_EXECUTES_NEXT_RE`에 계속 필요해서 유지.
- 첫 번째 판독(마스크)은 그대로 — 따옴표 구분자 heredoc 본문은 마스크에서 계속 리터럴.
- 수용한 비용: 본문에 git commit/merge를 언급하는 비판독 명령이 호출로 판정됨. 예:
  `gh pr create --body-file - <<EOF`, `tee f <<EOF`, `git log <<EOF`. 언급으로 고정된 사례 4건을 "설계상 과잉
  차단" 목록으로 옮김 — corpus `RUNS_NO_COMMIT`의 `nodemon <<EOF`·`bashful <<EOF`·`rebash <<EOF`(제거되는
  `_INTERPRETER_RE`의 이름 경계를 검사하던 사례)와 net `NET_MUST_NOT_FIRE`의
  `git log -1 --format=%s <<'EOF'`. merge로 판정되는 경우는 플래그를 마스크에서 읽으므로 전략 판정 없이
  fail-open.

### (c) 프로세스 치환 — P6

- `_substitutions`(요소 분리 기준)가 `<(…)`·`>(…)` 구간도 돌려주게 해서 그 안의 `;`로 요소를 자르지 않음.
- `_SUBSTITUTION_RE`는 바꾸지 않음: `<(…)`의 출력은 명령어가 아니라 파일 이름이라 `cat <(echo "git commit")`은
  언급으로 남아야 함. 치환 안의 프로그램은 `_programs`가 이미 명령 위치로 셈(`(`가 명령 시작).

### (d) xargs·parallel — X1

- 읽기 전용이 아닌 요소의 프로그램에 `xargs`나 `parallel`이 있고, 그 요소의 스크립트 보기에 `git` 토큰과
  `commit`(또는 `merge`) 토큰이 각각 독립 토큰으로 있으면 호출로 판정. 독립 토큰 = 앞뒤가 공백·따옴표·명령
  구분자(`;&|()`)·문자열 경계인 토큰 — `commit.gpgsign`, `*commit*`은 해당 안 됨.
- `git` 토큰은 `git_subcommand_re`의 프로그램 토큰과 같은 철자 규칙(경로 접두사, `.exe`).
- 수용한 비용: `git log | xargs -I{} echo commit {}` 같은 드문 경우의 과잉 차단.

## §2 디렉터리 해석 (Invariant 6)

해석 순서(명령 → hook cwd → main)는 그대로 둠. merge 경로(`_MERGE_CD_PREFIX_RE`·`_points_elsewhere`)는
대상 아님.

### (a) `.` 정규화 공유 — D3

`-C` 값 하나를 답으로 바꾸는 헬퍼 하나를 `_commit_dir_answers` 안에 두어 `_dir_from_command`와
`commit_tree_unresolved`가 같은 답 집합을 봄. `.`·`./`는 "디렉터리 없음"(`None`)과 같은 답.

### (b) 선두 `cd X;` 읽기 — D7

- `_CD_PREFIX_RE`가 선두 `cd <dir>` 뒤에 `&&`뿐 아니라 `;`와 줄바꿈도 받음. 명령 맨 앞에서만.
- 따옴표 없는 경로 토큰은 `;`·`&`·`|`에서 끊음 — `cd /x;git commit`이 경로를 `/x;git`으로 먹지 않게. 공유
  `_PATH_TOKEN`은 merge 경로의 `_MERGE_CD_PREFIX_RE`도 쓰므로 건드리지 않고 `_CD_PREFIX_RE` 전용 토큰을 둠.
- 한계(주석에 명시): `;` 형태에서 `cd`가 실패하면 셸은 원래 자리에 남는데 판정은 X 기준.

### (c) 따라갈 수 없는 디렉터리 변경 — D4a·D8

- 마스크 위 명령 위치의 `cd`·`pushd`·`popd`(§1(a)에서 확장한 `_programs` 걷기로 위치를 얻음) 중 하나라도
  인자 없는 커밋 호출보다 앞에 있고 (b)의 선두 prefix가 아니면 `commit_tree_unresolved`가 True.
- 서브셸 `(cd X && …)`은 `(`가 명령 시작이라 선두 prefix가 아님 → 표시됨.
- 커밋 뒤의 `cd`(`git commit && cd ..`)는 무관. 따옴표·heredoc 본문 안의 `cd`는 마스크에서 NUL이라 무관.

### (d) 전개되지 않은 `-C` — D4b·D9

- 값이 `$`·백틱·glob 문자(`*?[`)를 담으면 "알 수 없음" 답. `_dir_from_command`는 이 답이 있으면 명령에서
  디렉터리를 읽지 않음(→ hook cwd 단계), `commit_tree_unresolved`는 True.
- 선두 `~`는 `os.path.expanduser`로 펼쳐 정상 경로로 읽음 — 불확실 집합을 작게 유지.

### 불변식 영향

- Invariant 6의 선언된 예외(트리가 깨끗해도 검사)가 "호출끼리 다른 디렉터리를 가리키는 명령"에서 "커밋
  트리를 한 곳으로 정할 수 없는 명령"(다른 디렉터리를 가리키는 호출, 따라갈 수 없는 디렉터리 변경,
  전개되지 않은 `-C`)으로 넓어짐. runner는 `unresolved=1`을 이미 소비하므로 runner 변경 없음.
- unresolved 표시는 해석된 트리가 깨끗할 때만 동작을 바꿈(runner가 검사를 건너뛰지 않음). 그 경우 이전
  동작은 게이트 전체를 건너뛰는 것이었으므로, 이 표시로 생기는 새 차단은 선언된 예외 안에만 있음.
- 선두 `cd X;`는 해석된 트리 자체를 바꿈. 판정은 기존 `cd X &&` 형태와 같아지고, D7처럼 커밋이 실제로
  들어가는 트리를 기준으로 판정하게 됨.

## 범위 밖

- 파일 간접 실행: `xargs git < list`, `bash script.sh`, `cat > f <<EOF … ; bash f` — 게이트는 파일 내용을
  보지 않음.
- `builtin cd`·`command cd`·`env -C` 같은 디렉터리 변경 우회 철자.
- merge 경로의 디렉터리 판정.
- vway-kit: 같은 게이트 코드를 쓰지만 별도 작업.

## §3 테스트·검증

- **TDD**: 변경 8개(§1 a–d, §2 a–d) 각각 실패하는 테스트를 먼저 씀.
  - corpus: invocation 행 추가(P1, P1b `printf -v c '…'; $c`, P2 `--pre`/`--pre=`, P2b, P5a, P5b, P6, X1
    `xargs`/`parallel`), 언급 유지 확인(`rg "git commit" f`, `rg --pre 'git commit' pattern .`,
    `sort --compress-program='git commit -m x' f`, `printf x | rg -v y`, `cat <(echo "git commit")`,
    `cat <<EOF` 본문), 과잉 차단 목록 이동 4건. `RUNS_NO_COMMIT`의 "PATH로 실행하는 도구는 명령을 쓰지
    않는다" 주석은 "실행 플래그 값이 프로그램 이름이 될 수 없으면 아무것도 실행되지 않는다"로 고침.
  - 디렉터리: `_dir_from_command`(D3 → `/wt`, D7 → `/main`, `-C ~/wt` → 펼친 경로, `-C "$d"` → None,
    `cd /x;git commit` → `/x`), `commit_tree_unresolved`(D4a·D4b·D8·`-C $(pwd)` True, D3·
    `git commit && cd ..`·기존 단언 False). `test_commit_tree_unresolved_only_for_a_command_naming_two_trees`는
    넓어진 범위에 맞게 이름과 사례를 갱신.
  - runner(`tests/flow_gate/`): D3·D4a·D7·D8의 rc를 고정.
- **e2e A/B (WSL, v0.3.2 대비)** 기대값:

  | 사례 | v0.3.2 | 수정 후 |
  |---|---|---|
  | P1·P2·P5a·P5b·P6·X1 (wt2 dirty, 마커 없음) | 0 | 2 |
  | D3·D4a·D4b·D8 (wt2 dirty, main 깨끗, 마커 없음) | 0 | 2 |
  | D7 (main dirty + docs 마커, hook cwd wt2) | 2 | 0 |
  | 대조: 일반 커밋 / `-C wt2` | 2 | 2 |
  | 대조: `rg "git commit"` 언급 / `cd MAIN &&` | 0 | 0 |

- **mutation battery**: 기준선 초록 확인 → 변경 8개를 하나씩 되돌림(Python read-modify-write, `assert old in text`로
  적용 확인) → 새 테스트가 실패하는지 확인 → 깨끗한 트리에서 복원.
- **마무리**: 전체 `uv run pytest`, `ruff`, `pre-commit`. 테스트를 목록 사이로 옮기므로 수집 node id를 변경 전후
  `comm`으로 비교. 기존 긴 명령 성능 테스트로 hook 시간 한도 이내 확인.
- **리뷰**: 독립 리뷰 에이전트(probe harness·WSL 포함)가 커밋 누락 방향, 과잉 차단 비용, "새 차단 금지"
  위반을 봄. 2라운드를 미리 잡음.

## §4 문서·후속

- 코드 주석: `_READS_ONLY`(rg·sort에 대한 틀린 설명 정정, 플래그 규칙), `_INTERPRETER_RE` 설명 삭제,
  `_CD_PREFIX_RE`(`;` 읽는 이유와 한계), `commit_tree_unresolved`·`is_invocation` docstring.
- CLAUDE.md Invariant 6 예외 범위 문구 갱신. Invariant 7은 이미 "면제는 과잉 차단 쪽으로 틀려야 함"이라 확인만.
- doc-sync 게이트.
- 커밋: 소비자에게 배포되는 게이트 스크립트라 `fix(gate): …`. 한 커밋으로 amend.
- 병합: rebase → 통합 테스트 확인 → dev squash(사용자 확인).
- 후속: vway-kit 반영(별도 작업), 메모리 `gate-invocation-gaps` 해결 상태로 갱신.
