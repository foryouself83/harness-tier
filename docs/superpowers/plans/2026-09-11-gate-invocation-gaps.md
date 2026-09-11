# 커밋 게이트 호출 판정 결함 수정 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use
> checkbox (`- [ ]`) syntax for tracking.

**Goal:** `scripts/_harness_paths.py`가 놓치던 커밋 호출 6종을 보이게 하고, 워크트리 hook cwd에서
`cd $MAIN; git commit`을 과잉 차단하던 1종을 없앤다 — CLAUDE.md Invariant 6·7 준수.

**Architecture:** 두 축의 수정. (1) 호출 탐지(`is_invocation` 경로): 실행 플래그가 붙는 판독기의
면제를 제한하고, heredoc 본문 판정을 허용목록 기반으로 뒤집고, 프로세스 치환을 요소 분리에서
보호하고, xargs/parallel을 호출로 본다. (2) 디렉터리 해석(`_dir_from_command`·
`commit_tree_unresolved`): `.` 정규화를 공유하고, 선두 `cd X;`를 읽고, 따라갈 수 없는 디렉터리
변경과 전개되지 않은 `-C`를 unresolved로 표시한다. 게이트의 나머지(runner·flow_gate_check)는
`unresolved=1`을 이미 소비하므로 로직 변경 없음.

**Tech Stack:** Python 3.8+(표준 라이브러리 `re`·`shlex`·`os.path`만), pytest, WSL(bash 동작
검증·mutation), git worktree(e2e).

**Spec:** `docs/superpowers/specs/2026-09-11-gate-invocation-gaps-design.md` — 이 계획은 spec에서
논증한다. 실행자는 둘을 함께 읽는다.

## Global Constraints

- **한 방향 규칙(Invariant 7)**: 놓친 커밋은 이 게이트가 절대 실패해선 안 되는 방향. 면제에서
  빼는 판단이 애매하면 과잉 차단 쪽으로 튼다. `tests/skills/`는 실제 호출과 단순 언급을 둘 다 고정.
- **재지정은 새로 차단 금지(Invariant 6)**: unresolved 표시로 생기는 새 차단은 해석된 트리가
  깨끗한 경우뿐이고, 그 경우 이전 동작은 게이트 전체를 건너뛰는 것이었다. 불확실 집합은 작게.
- **단일 권위**: `git` 호출이 무엇인지는 `_harness_paths`가 한 곳에서 정한다. 프로그램 위치를 읽는
  두 번째 판독기를 만들지 않는다 — `_program_spans` 걷기 하나를 확장해 모두 쓴다.
- **공유 토큰 불변**: `_PATH_TOKEN`은 merge 경로(`_MERGE_CD_PREFIX_RE`)와 공유하므로 건드리지
  않는다. 커밋 경로 전용 토큰을 따로 둔다.
- **`_SUBSTITUTION_RE` 불변**: `<(…)`의 출력은 파일 이름이지 명령이 아니므로 `_reads_only`의
  치환 검사는 그대로. 요소 분리 기준인 `_substitutions`만 `<(`·`>(`를 안다.
- **CRLF·cp949 방어(Invariant 2)**: 새 정규식/문자열은 CR을 흘리지 않는다. 기존 방어 유지.
- **환경**: dev host는 Windows, CI는 ubuntu. POSIX 동작·mutation은 WSL에서 검증.
- **커밋**: 소비자에게 배포되는 게이트 스크립트라 최종 커밋은 `fix(gate):`, 한 커밋으로 amend.

---

## File Structure

| 파일 | 책임 | 작업 |
|---|---|---|
| `scripts/_harness_paths.py` | 호출 판정·디렉터리 해석의 단일 권위 | 8개 변경(§1 a–d, §2 a–d) |
| `tests/harness_paths/test_invocation_corpus.py` | 실제 호출/단순 언급 corpus | 행 추가, 4건 과잉차단 이동, 주석 정정 |
| `tests/harness_paths/test_invocation_net.py` | 인터프리터 net | `NET_MUST_NOT_FIRE` 이동 |
| `tests/harness_paths/test_exemptions.py` | `_programs`/`_reads_only` 단위 | 플래그 면제·spans 단위 테스트 추가 |
| `tests/harness_paths/test_dir_from_command.py` | 디렉터리 해석 단위 | D3/D4/D7/D8/D9 케이스, line 232 테스트 이름·사례 갱신 |
| `tests/skills/test_gate_reachability.py` | pre-filter↔grammar 정합 | `NON_INVOCATIONS`의 heredoc 언급 이동 |
| `tests/flow_gate/test_runner_commit.py` | runner rc end-to-end | D3/D4a/D7/D8 rc 고정 |
| `scripts/flow_gate_check.py` | (주석만) | `_PATH_TOKEN` 공유 주석 확인 |
| `CLAUDE.md` | Invariant 6 문구 | 예외 범위 갱신 |

`_harness_paths.py`는 host에 파일 단위로 복사되므로 새 헬퍼도 이 모듈 안에 둔다(외부 import 금지).

---

## Task 1: `_program_spans` — 위치를 돌려주는 단일 걷기 (§1(a) 기반)

`_programs`가 이름만 돌려줘서 §1(a)(실행 플래그)·§2(c)(cd 위치)가 위치를 못 얻는다. 걷기를 하나로
유지하려면 위치까지 돌려주는 `_program_spans`를 만들고 `_programs`를 그 위의 얇은 래퍼로 둔다.

**Files:**
- Modify: `scripts/_harness_paths.py` — `_programs`(line 379–449) 리팩터
- Test: `tests/harness_paths/test_exemptions.py`

**Interfaces:**
- Produces: `_program_spans(element: str) -> list[tuple[str | None, int, int]]` — 마스크된
  `element`의 각 명령 위치마다 `(프로그램 이름 또는 None, 인자 시작, 인자 끝)`. 인자 시작 =
  프로그램 토큰 끝, 인자 끝 = 그 뒤 첫 `_SEPARATOR_RE`(`[;&|)\n\r]`) 또는 `len(element)`.
- Produces: `_programs(element) == [n for n, _s, _e in _program_spans(element)]` (기존 API 유지).

- [ ] **Step 1: 실패 테스트 — spans가 이름과 위치를 함께 돌려준다**

`test_exemptions.py`에 추가:

```python
def test_program_spans_carry_name_and_arg_range():
    # 파이프 구성원 각각이 자기 인자 범위를 갖는다 — `-v`가 어느 프로그램의 것인지 위치로 가른다.
    spans = vp._program_spans("printf -v x | rg -v y")
    assert [n for n, _s, _e in spans] == ["printf", "rg"]
    printf_s, printf_e = spans[0][1], spans[0][2]
    rg_s, rg_e = spans[1][1], spans[1][2]
    assert "printf -v x | rg -v y"[printf_s:printf_e].strip() == "-v x"
    assert "printf -v x | rg -v y"[rg_s:rg_e].strip() == "-v y"
    # 이름 목록 래퍼는 그대로
    assert vp._programs("printf -v x | rg -v y") == ["printf", "rg"]
```

- [ ] **Step 2: 실패 확인** — `pytest tests/harness_paths/test_exemptions.py::test_program_spans_carry_name_and_arg_range -v` → FAIL (`_program_spans` 없음)

- [ ] **Step 3: 구현** — 기존 `_programs` 본문을 `_program_spans`로 옮기고, `found.append(name)`
  자리에서 `found.append((name, args_start, args_end))`를 기록. `args_start`는 프로그램 토큰의
  끝(`name.end()`), None 위치는 그 명령 시작 다음(`i`). `args_end`는 그 위치에서
  `_SEPARATOR_RE.search(element, args_start)`가 있으면 `.start()`, 없으면 `len(element)`. 걷기·
  reserved word·assignment·`.exe` 처리 로직은 그대로 옮긴다. 끝에 얇은 래퍼:

```python
def _programs(element: str) -> list[str | None]:
    """The program name at every command position (thin wrapper over _program_spans)."""
    return [name for name, _s, _e in _program_spans(element)]
```

  `_program_spans`의 각 `found.append(...)` 지점(이름 발견·None·assignment)마다
  `_SEPARATOR_RE`로 `args_end`를 계산해 튜플로 기록. reserved word가 명령을 재도입하는 `continue`
  경로는 append하지 않으므로 영향 없음.

- [ ] **Step 4: 통과 확인** — 위 테스트 + 기존 `test_exemptions.py` 전부 PASS
  (`pytest tests/harness_paths/test_exemptions.py -v`). 기존 `_programs == [...]` 단언은 래퍼로
  그대로 통과해야 한다(리팩터의 핵심 안전망).

- [ ] **Step 5: 커밋** — `git add scripts/_harness_paths.py tests/harness_paths/test_exemptions.py`,
  메시지 `refactor(gate): program walk returns positions` (임시, 최종 amend 예정)

---

## Task 2: §1(a) 실행 플래그 검사 — P1·P2

`printf`·`rg`·`sort`는 이름으로 면제되지만 `-v`·`--pre`·`--compress-program`이 붙으면 인자로 받은
프로그램을 실행한다. 이 세 프로그램은 실행 플래그가 없을 때만 면제한다.

**Files:**
- Modify: `scripts/_harness_paths.py` — `is_invocation`(line 936–971), 새 헬퍼
- Test: `tests/harness_paths/test_invocation_corpus.py`, `test_exemptions.py`

**Interfaces:**
- Consumes: `_program_spans`(Task 1)
- Produces: `_runs_by_flag(raw_element: str, masked_element: str) -> bool` — 요소가 표의 프로그램을
  실행 플래그와 함께 실행하면 True.

- [ ] **Step 1: 실패 테스트 — corpus에 P1·P2 호출 행, 언급 유지 행**

`RUNS_A_COMMIT`(호출로 읽혀야 함)에 추가:

```python
    # a reader with an exec-capable flag runs the program named in its own arguments; here the
    # commit text sits where the grammar sees it adjacent (inside $() or the printf string)
    ("printf -v 'a[$(git commit -qm x)]' 1", "commit"),
    ("printf -vx 'a[$(git commit -qm x)]'", "commit"),
    ("printf 'git commit -m x\\n' | sort --compress-program=bash", "commit"),
```

(참고: `rg --pre git x commit`는 `git`·`commit`이 rg의 별개 인자라 grammar가 인접으로 못 봐 §1(d)
독립 토큰 검사가 필요하다 → **Task 5의 corpus로 이동**. `--pre=git` 형은 git이 `=`에 붙어 독립
토큰도 아니므로 corpus에서 제외한다 — `_runs_by_flag`의 `--pre=` 탐지는 유지하되 그 철자의 호출
포착은 별도 후속. `sort --compress-program bash f`는 `git commit` 텍스트가 없어 호출이 아니므로
제외.)

`RUNS_NO_COMMIT`(언급으로 남아야 함)에 추가:

```python
    # the exec-flag value cannot be a program name (holds whitespace), so nothing runs
    "sort --compress-program='git commit -m x' f",
    "rg --pre 'git commit' pattern .",
    # --pre-glob is not --pre, and -v after a NON-reader belongs to that reader
    "rg --pre-glob '*.md' 'git commit' .",
    "printf x | rg -v 'git commit'",
```

주석 정정(line 213 근처): 기존
`# a tool that runs a program by PATH rather than a shell string spells no command`
를
`# an exec-flag whose value cannot be a program name (missing, or holding whitespace) runs nothing`
로 교체.

- [ ] **Step 2: 실패 확인** — `pytest tests/harness_paths/test_invocation_corpus.py -v` → 새 `--pre`/
  `printf -v` 호출 행이 FAIL(아직 면제됨), 언급 행은 이미 PASS일 수 있음.

- [ ] **Step 3: 구현 — 플래그 표와 헬퍼**

모듈 상단(`_READS_ONLY` 근처)에:

```python
# Readers on _READS_ONLY that lose the exemption when handed an exec-capable flag: the flag's
# value is a program run by PATH, so a value that IS a program (present, no whitespace) means
# something runs. Measured per pipe member on its own arg range (§1(a)).
_EXEC_FLAG_READERS = {
    # program: (predicate over one shlex token → does this token turn the exemption off?)
    "printf": lambda t: t.startswith("-v"),          # bash printf -v NAME assigns; -vNAME too
    "rg": lambda t: t == "--pre" or t.startswith("--pre="),   # not --pre-glob
    "sort": lambda t: t.startswith("--co"),          # GNU --co… abbreviates --compress-program
}
# A value that can name a program: present and whitespace-free. rg/sort take the value as the
# next token or after `=`; missing or whitespace-bearing → no such program → exemption kept.
_EXEC_FLAG_VALUE_PROGRAMS = ("rg", "sort")
```

**핵심(최소 변경)**: Task 2에서는 `view` 기계(`plain`/`scripted`/`runs_text`)를 그대로 두고,
면제(=`continue`) 가드에만 `_runs_by_flag`를 끼운다. `scripted` 항상읽기 전환은 Task 3의 몫:

```python
    for a, b in _list_elements(command, masked):
        if _reads_only(masked[a:b]) and not _runs_by_flag(command[a:b], masked[a:b]):
            continue
        runs_text = _INTERPRETER_RE.search(masked[a:b]) or _SUBSTITUTION_RE.search(masked[a:b])
        view = scripted if runs_text else plain      # Task 3에서 제거됨
        if pattern.search(view[a:b]):
            return True
```

(`printf -v 'a[$(git commit)]'`은 `$()` 안에 온전한 `git commit`이 있어 `_SUBSTITUTION_RE`가
`runs_text`를 켜고 `scripted` view에서 grammar가 잡는다 — Task 2 단독으로 통과. `sort
--compress-program=bash`는 `printf` 문자열 쪽 `git commit`을 grammar가 인접으로 본다.)

`_runs_by_flag`:

```python
def _runs_by_flag(raw_element: str, masked_element: str) -> bool:
    """Whether a reader in `raw_element` is handed an exec-capable flag (§1(a)).

    Checked per pipe member on its own arg range so `printf x | rg -v y`'s `-v` is rg's. The
    program token is read on the MASK (one authority for positions); the arg text is shlex-split
    from the RAW element so a quoted value's whitespace and any `$`/backtick expansion are seen.
    A ValueError from shlex, or a `$`/backtick in the arg range, loses the exemption — an
    expansion could become a flag. Erring toward over-gating (Invariant 7).
    """
    import shlex

    for name, s, e in _program_spans(masked_element):
        pred = _EXEC_FLAG_READERS.get(name)
        if pred is None:
            continue
        arg_raw = raw_element[s:e]
        if "$" in arg_raw or BT_CH in arg_raw:
            return True
        try:
            toks = shlex.split(arg_raw)
        except ValueError:
            return True
        for idx, t in enumerate(toks):
            if not pred(t):
                continue
            if name not in _EXEC_FLAG_VALUE_PROGRAMS:
                return True  # printf -v: the flag alone runs (assignment evaluates the subscript)
            # rg/sort: the value is `--flag=VAL` or the next token. A program name iff present
            # and whitespace-free (a value with a space cannot be a program).
            val = t.split("=", 1)[1] if "=" in t else (toks[idx + 1] if idx + 1 < len(toks) else "")
            if val and not any(c.isspace() for c in val):
                return True
    return False
```

- [ ] **Step 4: 통과 확인** — `pytest tests/harness_paths/test_invocation_corpus.py -v` PASS.
  `printf -v 'a[$(git commit)]'`은 `$`가 arg_raw에 있어 면제 상실 → `runs_text`가 켜져 scripted
  view에서 `git_subcommand_re`가 `$(git commit)` 안의 인접한 `git commit`을 봄. `sort
  --compress-program=bash`는 `printf 'git commit …'` 문자열 쪽 인접 `git commit`을 grammar가 봄.
  RUNS_NO_COMMIT 행(값에 공백 있는 `--pre 'git commit'`·`--compress-program='git commit …'`,
  `--pre-glob`, `printf x | rg -v 'git commit'`)은 면제 유지로 언급으로 남음.
  (`rg --pre git x commit`은 `git`·`commit`이 rg의 별개 인자라 grammar가 인접으로 못 본다 — §1(d)
  독립 토큰 검사가 필요하므로 **Task 5의 corpus·구현으로 넘긴다**. 이 태스크에는 넣지 않는다.)

- [ ] **Step 5: 커밋** — `fix(gate): deny exemption to readers given an exec flag` (임시)

---

## Task 3: §1(b) heredoc 판정 뒤집기 — P5

heredoc 본문은 지금 `_RUNS_TEXT` 인터프리터나 `$()`가 보일 때만 스크립트로 읽는다 — 목록에 없는
실행기(`awk`, `.`)면 게이트가 꺼진다. 읽기 전용 요소가 아니면 본문을 항상 스크립트로 읽도록 뒤집는다.

**Files:**
- Modify: `scripts/_harness_paths.py` — `is_invocation`(line 962–971), `_INTERPRETER_RE`(486–489) 제거
- Test: `test_invocation_corpus.py`, `test_invocation_net.py`, `tests/skills/test_gate_reachability.py`

- [ ] **Step 1: 실패 테스트 — P5a·P5b 호출, 과잉차단 4건 이동**

`RUNS_A_COMMIT`에 추가:

```python
    # a heredoc body handed to a NON-reader is a script, even for an interpreter the list never
    # named — the inversion (§1(b)): the missing entry over-gates instead of turning the gate off
    ("awk -f - <<'EOF'\nBEGIN { system(\"git commit -qm x\") }\nEOF", "commit"),
    (". /dev/stdin <<'EOF'\ngit commit -qm x\nEOF", "commit"),
    ("sed -f - <<'EOF'\n1e git merge --no-ff dev\nEOF", "merge"),
    # accepted cost: a non-reader whose heredoc body merely MENTIONS a commit is now gated
    ("nodemon <<EOF\ngit commit -m x\nEOF", "commit"),
    ("bashful <<EOF\ngit commit -m x\nEOF", "commit"),
    ("rebash <<EOF\ngit commit -m x\nEOF", "commit"),
    ("git log -1 --format=%s <<'EOF'\ngit -C /wt commit -m x\nEOF", "commit"),
```

`RUNS_NO_COMMIT`에서 **삭제**: `nodemon <<EOF…`, `bashful <<EOF…`, `rebash <<EOF…`(위로 이동).
`test_invocation_net.py`의 `NET_MUST_NOT_FIRE`에서 **삭제**:
`"git log -1 --format=%s <<'EOF'\ngit -C /wt commit -m x\nEOF"` 와
`"git log -1 --format=%s <<'EOF'\ngit -C /wt commit -m x\nEOF\npython3 -V"`(둘 다 이제 과잉차단;
후자는 corpus로 옮기거나 삭제 — corpus에 앞 항목이 있으므로 삭제).
`tests/skills/test_gate_reachability.py`의 `NON_INVOCATIONS`(line 215)에서 동일 항목 삭제.

- [ ] **Step 2: 실패 확인** — `pytest tests/harness_paths/test_invocation_corpus.py
  tests/harness_paths/test_invocation_net.py tests/skills/test_gate_reachability.py -v` → awk/dot
  호출 행 FAIL(아직 본문 안 읽음), 이동된 nodemon류는 RUNS_A_COMMIT에서 FAIL.

- [ ] **Step 3: 구현 — plain view와 `_INTERPRETER_RE` 제거**

`is_invocation`(line 962–971)을:

```python
    scripted = _unquoted_view(command, keep_heredoc=True)
    for a, b in _list_elements(command, masked):
        if _reads_only(masked[a:b]) and not _runs_by_flag(command[a:b], masked[a:b]):
            continue
        if pattern.search(scripted[a:b]):
            return True
    return False
```

`plain = _unquoted_view(command)`와 `runs_text = _INTERPRETER_RE.search(...) or ...` 삭제.
`_INTERPRETER_RE` 정의(486–489) 삭제. `_RUNS_TEXT`는 `_EXECUTES_NEXT_RE`(527–535)가 여전히 쓰므로
**유지**. `_SUBSTITUTION_RE`는 `_reads_only`가 쓰므로 **유지**.

docstring(is_invocation, 944–956) 갱신: "두 readings" 설명을 "마스크 위 grammar가 먼저; 그 뒤
읽기 전용이 아닌 각 요소는 heredoc 본문을 포함한 스크립트 보기로 다시 읽는다"로. `_INTERPRETER_RE`
윗 주석(478–485) 삭제.

- [ ] **Step 4: 통과 확인** — 위 세 파일 PASS. awk/dot는 `awk`/`.`가 reads-only가 아니라 scripted
  view에 본문이 살아 `git … commit`을 봄. `cat <<EOF\n…git commit…\nEOF`(RUNS_NO_COMMIT의 cat
  케이스)는 `cat` reads-only→여전히 언급. `_INTERPRETER_RE` 삭제로 못 깨지는지 전체 harness_paths
  스위트 확인(`pytest tests/harness_paths -v`).

- [ ] **Step 5: 커밋** — `fix(gate): read a non-reader heredoc body as a script` (임시)

---

## Task 4: §1(c) 프로세스 치환 — P6

`bash <(echo; echo "git commit …")`의 `<(` 안 `;`가 요소를 잘라 꼬리가 `echo`만의 요소로 면제된다.
`_substitutions`(요소 분리 기준)가 `<(…)`·`>(…)` 구간도 돌려주게 한다.

**Files:**
- Modify: `scripts/_harness_paths.py` — `_substitutions`(line 894–907)
- Test: `test_invocation_corpus.py`, `test_exemptions.py`

- [ ] **Step 1: 실패 테스트**

`RUNS_A_COMMIT`에 추가:

```python
    # `<(…)` is a substitution span for element-splitting, so its inner `;` never cuts the element
    ('bash <(echo; echo "git commit -qm x")', "commit"),
    ('bash <(true; echo "git merge --no-ff dev")', "merge"),
```

`RUNS_NO_COMMIT`에 추가(치환 출력은 파일 이름이라 `cat`은 여전히 읽기):

```python
    "cat <(echo; echo 'git commit -m x')",
```

`test_exemptions.py`의 `test_a_substitution_is_one_element_however_it_is_spelled`에 케이스 추가:

```python
        "bash <(echo; echo x)",
        "cat >(echo; tee x)",
```

- [ ] **Step 2: 실패 확인** — `pytest tests/harness_paths/test_invocation_corpus.py::… -v` 및
  `test_exemptions.py::test_a_substitution_is_one_element_however_it_is_spelled` → `<(…;…)`가 두
  요소로 잘려 FAIL.

- [ ] **Step 3: 구현**

`_substitutions`에 `<(`·`>(` 분기 추가:

```python
def _substitutions(masked: str) -> list[tuple[int, int]]:
    """Where each `$( … )`, backtick, and process-substitution `<( … )` / `>( … )` span sits on
    the mask, outermost first. Used ONLY to keep _list_elements from splitting inside one — a
    `;` in `bash <(echo; …)` is not a list boundary. _SUBSTITUTION_RE (the reads-only check) is
    separate and unchanged: a `<(…)`'s output is a filename, not a command, so `cat <(…)` stays
    a reader."""
    spans, i, n = [], 0, len(masked)
    while i < n:
        if masked[i] == DOLLAR_CH and masked[i + 1 : i + 2] == "(":
            end = _matching(masked, i + 2, "(", ")")
        elif masked[i] in "<>" and masked[i + 1 : i + 2] == "(":
            end = _matching(masked, i + 2, "(", ")")
        elif masked[i] == BT_CH:
            end = _matching(masked, i + 1, BT_CH, BT_CH)
        else:
            i += 1
            continue
        spans.append((i, min(end, n)))
        i = min(end, n) if end > i else i + 1
    return spans
```

- [ ] **Step 4: 통과 확인** — 위 테스트 + `test_invocation_net.py`(치환 관련 회귀 없음) PASS. P6는
  한 요소가 되고 프로그램 `bash`(비판독)→scripted view에서 `<(echo; echo "git commit")`의 따옴표가
  벗겨져 `git … commit`을 본다.

- [ ] **Step 5: 커밋** — `fix(gate): keep a process substitution one element` (임시)

---

## Task 5: §1(d) xargs·parallel — X1

`echo commit | xargs git`은 xargs가 하위 명령을 표준 입력으로 받아 `git … commit` 순서가 없다.
판독기가 아닌 요소가 xargs/parallel을 실행하고 `git`·`commit`이 각각 독립 토큰이면 호출로 본다.

**Files:**
- Modify: `scripts/_harness_paths.py` — `is_invocation` 요소 루프, 새 헬퍼
- Test: `test_invocation_corpus.py`

**Interfaces:**
- Consumes: `_program_spans`(Task 1), `scripted` view(Task 3)
- Produces: `_standalone_token(view: str, word: str) -> bool` — `word`가 앞뒤 공백/따옴표/구분자/
  문자열 경계로 둘러싸인 독립 토큰으로 있으면 True.

- [ ] **Step 1: 실패 테스트**

`RUNS_A_COMMIT`에 추가:

```python
    # xargs/parallel reorder args past the grammar; a standalone git + commit token is the signal
    ("echo commit | xargs git", "commit"),
    ("echo commit -m x | xargs git", "commit"),
    ("printf 'merge\\n--no-ff\\ndev' | xargs git", "merge"),
    ("echo commit | parallel git", "commit"),
    # rg --pre git <pat> commit: rg runs `git` on the file named `commit` → a standalone git +
    # commit token, the same signal (§1(a) denied its exemption; the token check catches it here)
    ("rg --pre git x commit", "commit"),
```

`RUNS_NO_COMMIT`에 추가(독립 토큰이 아니면 발화 안 함):

```python
    # `commit.gpgsign` and `*commit*` are not standalone commit tokens
    "echo x | xargs git config commit.gpgsign false",
    "git log | xargs -I{} echo committing {}",
```

(주의: `git log | xargs -I{} echo commit {}`처럼 `git`+`commit`이 둘 다 독립 토큰이면 과잉 차단 —
spec이 수용한 비용. 위 언급 케이스는 `committing`/`commit.gpgsign`으로 독립 토큰을 피한 것.)

- [ ] **Step 2: 실패 확인** — `pytest tests/harness_paths/test_invocation_corpus.py -v` → xargs 호출
  행 FAIL.

- [ ] **Step 3: 구현**

```python
# `git` as a standalone token, spelled as the host spells the program (path prefix, `.exe`).
_GIT_TOKEN_RE = re.compile(r"(?:^|[\s;&|()'\"`])(?:[^\s;&|()'\"]*[/\\])?git(?:\.exe)?(?=$|[\s;&|()'\"`])")
_XARGS = frozenset(("xargs", "parallel"))


def _standalone_word(view: str, word: str) -> bool:
    """`word` as a whole token on `view` — bounded by whitespace, a quote, a command separator or
    the string edge. `commit.gpgsign` and `*commit*` do not qualify."""
    return re.search(rf"(?:^|[\s;&|()'\"`]){re.escape(word)}(?=$|[\s;&|()'\"`])", view) is not None
```

`is_invocation` 요소 루프의 grammar 실패 뒤에:

```python
        names = [n for n, _s, _e in _program_spans(masked[a:b])]
        if (set(names) & _XARGS) and _GIT_TOKEN_RE.search(scripted[a:b]) \
                and _standalone_word(scripted[a:b], word):
            return True
```

동시에 Task 2 Step 4에서 미룬 폴백을 연결: `_runs_by_flag` True인 요소도 이 독립 토큰 검사로
판정하도록, 같은 블록을 `(set(names) & _XARGS) or _runs_by_flag(command[a:b], masked[a:b])`로 확장.
이러면 `rg --pre git x commit`이 `git`+`commit` 독립 토큰으로 발화한다.

- [ ] **Step 4: 통과 확인** — `pytest tests/harness_paths -v` PASS. `rg --pre git x commit`도
  이제 통과(§1(a)가 면제를 거두고 이 토큰 검사가 잡음). Task 2·3의 corpus 회귀 없음.

- [ ] **Step 5: 커밋** — `fix(gate): read xargs/parallel git commit as an invocation` (임시)

---

## Task 6: §2(a) `.` 정규화 공유 — D3

`.`/`./` 정규화가 `commit_tree_unresolved`에만 있고 `_dir_from_command`에는 없어 `{'.', None}`이
엇갈린다. 정규화를 `_commit_dir_answers`로 올려 둘이 같은 답 집합을 본다.

**Files:**
- Modify: `scripts/_harness_paths.py` — `_commit_dir_answers`(1074–1080), `_dir_from_command`
  (1050–1071), `commit_tree_unresolved`(1083–1104)
- Test: `test_dir_from_command.py`

- [ ] **Step 1: 실패 테스트**

`test_dir_from_command.py`에 추가:

```python
def test_dir_from_command_reads_the_cd_prefix_when_dash_c_is_dot():
    # `.` and a bare commit are one tree, so the answer set is {None}: the cd prefix is read and
    # the commit resolves to $WT, not to a clean main (D3).
    assert vp._dir_from_command("cd /wt && git -C . commit -m a && git commit --amend") == "/wt"
    assert vp._dir_from_command("cd /wt && git -C ./ commit -m a && git commit --amend") == "/wt"
```

기존 `test_commit_tree_unresolved_only_for_a_command_naming_two_trees`(line 238–241)의 `.` 단언은
유지(여전히 False여야 함).

- [ ] **Step 2: 실패 확인** — `pytest tests/harness_paths/test_dir_from_command.py -v` → 새 테스트
  FAIL(`{'.', None}` 엇갈려 None 반환, cd prefix 안 읽음).

- [ ] **Step 3: 구현**

```python
def _norm_dir(d: str | None) -> str | None:
    """A `-C` value normalized to the answer it represents. `.`/`./` are the directory a bare
    invocation already runs in, so both are "no directory named" (None) — one answer, not two."""
    return None if d in (".", "./") else d


def _commit_dir_answers(command: str) -> set[str | None]:
    masked = mask_literals(command)
    return {
        _norm_dir(dash_c_value(command, masked, m.start(1), m.end(1)))
        for m in _GIT_COMMIT_RE.finditer(masked)
    }
```

`commit_tree_unresolved`의 내부 정규화(1101) 제거 → `answers = _commit_dir_answers(command)`.
`_dir_from_command`의 답 소비 로직은 그대로(이제 `{None}`을 받아 cd prefix 경로로 감).

- [ ] **Step 4: 통과 확인** — `pytest tests/harness_paths/test_dir_from_command.py -v` PASS. line
  238–241의 `.` 케이스 여전히 False, 새 D3 케이스 `/wt`.

- [ ] **Step 5: 커밋** — `fix(gate): share the dot normalization across dir readers` (임시)

---

## Task 7: §2(b) 선두 `cd X;` 읽기 — D7

`_CD_PREFIX_RE`가 `&&`만 읽어 워크트리 hook cwd에서 `cd $MAIN; git commit`이 hook cwd(워크트리)로
해석돼 미분류 차단된다. 선두 `cd` 뒤 `;`·줄바꿈도 읽는다. `_PATH_TOKEN`은 merge와 공유하므로
전용 토큰을 둔다.

**Files:**
- Modify: `scripts/_harness_paths.py` — `_CD_PREFIX_RE`(191), 전용 토큰
- Test: `test_dir_from_command.py`, `test_working_root.py`

- [ ] **Step 1: 실패 테스트**

`test_dir_from_command.py`에 추가:

```python
def test_dir_from_command_reads_a_leading_cd_with_a_semicolon():
    # `cd $MAIN; git commit` from a worktree hook cwd resolves to MAIN, not the worktree (D7).
    assert vp._dir_from_command("cd /main; git commit -m x") == "/main"
    assert vp._dir_from_command("cd /main\ngit commit -m x") == "/main"


def test_dir_from_command_leading_cd_path_stops_at_the_semicolon():
    # the bare path token must not swallow `;git` — `cd /x;git commit` names /x, not `/x;git`.
    assert vp._dir_from_command("cd /x;git commit -m a") == "/x"
```

- [ ] **Step 2: 실패 확인** — `pytest tests/harness_paths/test_dir_from_command.py -v` → `;`/줄바꿈
  형태 FAIL(안 읽힘).

- [ ] **Step 3: 구현**

`_PATH_TOKEN`(183) 아래에 전용 토큰과 갱신된 정규식:

```python
# The commit path's own cd-prefix path token: a bare path stops at a command separator so
# `cd /x;git commit` names `/x`, not `/x;git`. Kept separate from _PATH_TOKEN, which the merge
# path (_MERGE_CD_PREFIX_RE) shares and must not change.
_CD_PATH_TOKEN = r'"([^"]*)"|\'([^\']*)\'|([^\s;&|]+)'
# A leading `cd <dir>` before the commit, followed by `&&`, `;`, or a newline. Anchored at the
# start, so a match is necessarily BEFORE any later subcommand and re-points ROOT conservatively
# (Invariant #6). A trailing `;`/newline form re-points to the tree the commit actually lands in,
# exactly as `&&` does. Limit (see docstring): with `;`, a failed `cd` leaves the shell where it
# was while this judges against X — the over-block that fixing D7 removes is the common case.
_CD_PREFIX_RE = re.compile(rf"\s*cd\s+(?:{_CD_PATH_TOKEN})\s*(?:&&|[;\n])")
```

`_CD_PREFIX_RE` 윗 주석(184–190)의 "`&&` only, deliberately" 문단을 위 내용으로 갱신 — 이제 `;`도
읽고, merge 경로와의 위험 극성 차이는 전용 토큰으로 흡수됨을 명시.

- [ ] **Step 4: 통과 확인** — `pytest tests/harness_paths/test_dir_from_command.py
  tests/harness_paths/test_working_root.py -v` PASS. 기존 `cd /a/b && git commit` 케이스 유지.

- [ ] **Step 5: 커밋** — `fix(gate): read a leading cd terminated by a semicolon` (임시)

---

## Task 8: §2(c)·(d) 따라갈 수 없는 디렉터리 변경·전개되지 않은 `-C` — D4a·D4b·D8·D9

`cd`-hopping·서브셸 `cd`·looped `-C "$d"`가 unresolved로 표시되지 않는다. 명령 위치의 비선두 cd,
그리고 `$`/백틱/glob를 담은 `-C` 값을 unresolved로 표시하고, `~`는 펼친다.

**Files:**
- Modify: `scripts/_harness_paths.py` — `_norm_dir`(Task 6), `_dir_from_command`,
  `commit_tree_unresolved`, 새 헬퍼
- Test: `test_dir_from_command.py`

**Interfaces:**
- Consumes: `_program_spans`(Task 1), `_commit_dir_answers`·`_CD_PREFIX_RE`(Task 6·7)
- Produces: 센티넬 `_UNKNOWN_DIR`; `_cd_hop_before_bare_commit(command, masked) -> bool`

- [ ] **Step 1: 실패 테스트**

`test_dir_from_command.py`에 추가 및 line 232 테스트 갱신:

```python
def test_commit_tree_unresolved_widens_to_untrackable_dir_changes():
    # a non-leading cd/pushd before a bare commit — the leading tree, clean, would skip the gate
    assert vp.commit_tree_unresolved("cd /wt1 && git commit -m a; cd /wt2 && git commit -m b")  # D4a
    assert vp.commit_tree_unresolved("(cd /wt && git commit -m x)")                              # D8
    assert vp.commit_tree_unresolved("pushd /wt && git commit -m x")
    # an unexpanded -C value cannot be a tree this can name
    assert vp.commit_tree_unresolved('for d in /a /b; do git -C "$d" commit -m x; done')        # D4b
    assert vp.commit_tree_unresolved("git -C /wt* commit -m x")
    assert vp.commit_tree_unresolved("git -C $(pwd) commit -m x")


def test_dir_from_command_gives_up_on_an_unexpanded_dash_c():
    # `-C "$d"` names no tree the resolver can read → None (→ hook cwd rung), and unresolved gates
    assert vp._dir_from_command('for d in /a /b; do git -C "$d" commit -m x; done') is None


def test_dir_from_command_expands_a_leading_tilde():
    import os
    assert vp._dir_from_command("git -C ~/wt commit -m x") == os.path.expanduser("~/wt")


def test_commit_tree_unresolved_is_false_for_a_single_clear_tree():
    # the leading cd prefix is NOT a hop; a single -C or a bare commit stays resolved
    assert not vp.commit_tree_unresolved("cd /wt && git commit -m x")   # leading prefix, read
    assert not vp.commit_tree_unresolved("git -C /wt commit -m x")
    assert not vp.commit_tree_unresolved("git commit -m x && cd ..")    # cd AFTER the commit
```

기존 `test_commit_tree_unresolved_only_for_a_command_naming_two_trees`(line 232) 이름을
`test_commit_tree_unresolved_for_a_command_that_names_more_than_one_tree`로 바꾸고 docstring을
"두 트리 이름" → "커밋 트리를 한 곳으로 정할 수 없음(다른 디렉터리·따라갈 수 없는 cd·전개되지
않은 -C)"으로 넓힌다. 기존 단언(line 237–244)은 유지.

- [ ] **Step 2: 실패 확인** — `pytest tests/harness_paths/test_dir_from_command.py -v` → 새 D4/D8/D9
  케이스 FAIL.

- [ ] **Step 3: 구현**

`_norm_dir`(Task 6)를 확장 — `~` 펼치고 전개 문자면 센티넬:

```python
_UNKNOWN_DIR = object()  # a -C value with shell expansion or a glob — a tree this cannot name
_UNEXPANDED_RE = re.compile(r"[$`*?\[]")  # $ backtick and glob chars


def _norm_dir(d: str | None):
    """A `-C` value as the answer it represents. `.`/`./` → None (the current tree). A leading `~`
    is expanded (Invariant #6 keeps the uncertain set small). A value carrying shell expansion or
    a glob → _UNKNOWN_DIR: a tree this cannot name, so the command is unresolved."""
    if d is None or d in (".", "./"):
        return None
    if d.startswith("~"):
        d = os.path.expanduser(d)
    if _UNEXPANDED_RE.search(d):
        return _UNKNOWN_DIR
    return d
```

`_dir_from_command`: 센티넬이 답에 있으면 명령에서 디렉터리를 읽지 않음(→ 다음 rung):

```python
    answers = _commit_dir_answers(command)
    if _UNKNOWN_DIR in answers:
        return None  # a tree this cannot name — drop to hook cwd; unresolved gates it anyway
    if len(answers) == 1:
        if (only := answers.pop()) is not None:
            return only
    elif answers:
        return None
    m = _CD_PREFIX_RE.match(command)
    return next((g for g in m.groups() if g is not None), None) if m else None
```

`commit_tree_unresolved`:

```python
def commit_tree_unresolved(command: str | None) -> bool:
    if not command:
        return False
    try:
        masked = mask_literals(command)
        answers = _commit_dir_answers(command)
        if len(answers) > 1 or _UNKNOWN_DIR in answers:
            return True
        return _cd_hop_before_bare_commit(command, masked)
    except Exception:
        return False  # FAIL-OPEN
```

`_cd_hop_before_bare_commit`:

```python
def _cd_hop_before_bare_commit(command: str, masked: str) -> bool:
    """A cd/pushd/popd at a command position — other than the leading `cd X &&`/`;` prefix — that
    precedes a bare (no -C) `git commit`. The leading prefix is read (§2(b)); any later cd changes
    the tree the commit lands in without the resolver following it, so its target is a tree this
    cannot name (§2(c)). A subshell `(cd X && …)` is a hop too: `(` is a command start, not the
    leading prefix."""
    lead = _CD_PREFIX_RE.match(command)
    lead_end = lead.end() if lead else 0
    bare = [m.start() for m in _GIT_COMMIT_RE.finditer(masked)
            if _norm_dir(dash_c_value(command, masked, m.start(1), m.end(1))) is None]
    if not bare:
        return False
    for name, s, _e in _program_spans(masked):
        if name in ("cd", "pushd", "popd") and s > lead_end and any(s < c for c in bare):
            return True
    return False
```

(`_program_spans`는 이름 위치를 인자 시작 `s`로 돌려주므로 cd 위치 비교에 쓴다. cd 이름 자체의
위치가 필요하면 `s`가 cd 인자 시작이라 커밋 위치 `c`보다 앞인지로 충분하다.)

- [ ] **Step 4: 통과 확인** — `pytest tests/harness_paths/test_dir_from_command.py -v` PASS.
  `git commit -m x && cd ..`는 bare commit이 cd보다 앞(`s > c` 아님)→False. `cd /wt && git commit`
  은 선두 prefix→`s > lead_end` 아님→False.

- [ ] **Step 5: 커밋** — `fix(gate): mark untrackable dir changes unresolved` (임시)

---

## Task 9: runner rc end-to-end — D3·D4a·D7·D8

단위 판정이 실제 `precommit-runner.sh`의 rc로 이어지는지 고정한다. runner·flow_gate_check는
`unresolved=1`을 이미 소비하므로 코드 변경 없음 — 회귀 방지 테스트만 추가.

**Files:**
- Test: `tests/flow_gate/test_runner_commit.py` (기존 헬퍼 `_run_runner`·`_classify_worktree_module`
  사용)

- [ ] **Step 1: 실패 테스트** — 기존 `test_runner_commit.py` 패턴을 따라 추가:

```python
@requires_bash_git
def test_runner_gates_a_dot_dash_c_beside_a_bare_commit(tmp_path: Path):
    # D3: `cd $WT && git -C . commit && git commit --amend` resolves to $WT (dirty, unclassified),
    # not a clean main. The deny proves the gate engaged.
    main = tmp_path / "main"; _init_repo(main)
    wt = tmp_path / "wt"; _rg(["worktree", "add", "-b", "feature/x", str(wt)], main)
    (wt / "f.txt").write_text("x", encoding="utf-8"); _rg(["add", "f.txt"], wt)
    r = _run_runner(main, f"cd {wt} && git -C . commit -m a && git commit --amend --no-edit")
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)


@requires_bash_git
def test_runner_gates_cd_hopping_across_trees(tmp_path: Path):
    # D4a: two cd-hops, leading tree clean — unresolved forces the gate.
    main = tmp_path / "main"; _init_repo(main)
    a = tmp_path / "wta"; b = tmp_path / "wtb"
    _rg(["worktree", "add", "-b", "feature/a", str(a)], main)
    _rg(["worktree", "add", "-b", "feature/b", str(b)], main)
    (b / "f.txt").write_text("x", encoding="utf-8"); _rg(["add", "f.txt"], b)
    r = _run_runner(main, f"cd {a} && git commit -m a; cd {b} && git commit -m b")
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)


@requires_bash_git
def test_runner_gates_a_subshell_cd_commit(tmp_path: Path):
    # D8: `(cd $WT && git commit)` — unresolved gates it.
    main = tmp_path / "main"; _init_repo(main)
    wt = tmp_path / "wt"; _rg(["worktree", "add", "-b", "feature/x", str(wt)], main)
    (wt / "f.txt").write_text("x", encoding="utf-8"); _rg(["add", "f.txt"], wt)
    r = _run_runner(main, f"(cd {wt} && git commit -m x)")
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)


@requires_bash_git
def test_runner_stops_over_blocking_cd_main_from_a_worktree(tmp_path: Path):
    # D7: from a worktree cwd, `cd $MAIN; git commit` now resolves to MAIN (classified) → rc 0,
    # where before it resolved to the worktree and was denied as unclassified.
    main = tmp_path / "main"; _init_repo(main)
    _classify_worktree_module(main)  # main carries a dev tier marker + evidence
    _rg(["add", "-A"], main); _rg(["commit", "-m", "classify"], main)
    (main / "f.txt").write_text("x", encoding="utf-8"); _rg(["add", "f.txt"], main)
    wt = tmp_path / "wt"; _rg(["worktree", "add", "-b", "feature/x", str(wt)], main)
    # hook cwd is the worktree; the command cd's to main
    r = _run_runner(main, f"cd {main}; git commit -m x")  # _run_runner sets hook cwd = main…
    # NOTE: _run_runner hard-codes cwd=main. For D7 the hook cwd must be the WORKTREE. Add a
    # cwd param to _run_runner (default main) OR assert via _classify with cwd=wt. See Step 3.
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)
```

- [ ] **Step 2: 실패/전제 확인** — `_run_runner`(`_helpers.py:92`)는 hook `cwd`를 `main`으로
  고정한다. D7은 hook cwd가 워크트리여야 한다. `_run_runner`에 `hook_cwd: Path | None = None`
  인자를 더해 `hook = json.dumps({"cwd": str(hook_cwd or main), …})`로 바꾼다(기존 호출 무영향).
  D7 테스트는 `_run_runner(main, f"cd {main}; git commit -m x", hook_cwd=wt)`로 호출.

- [ ] **Step 3: 구현** — `_helpers.py`의 `_run_runner`에 `hook_cwd` 인자 추가(위). runner/
  flow_gate_check 로직은 변경 없음(unresolved 이미 소비). D7이 rc 0이려면 main이 분류돼 있어야
  하므로 `_classify_worktree_module(main)`로 marker/evidence를 심고 커밋해 깨끗하게 만든 뒤 f.txt를
  더럽힌다. 워크트리 경로에 공백이 없어야 함(기존 헬퍼 관례).

- [ ] **Step 4: 통과 확인** — `pytest tests/flow_gate/test_runner_commit.py -v`(WSL 또는 repo-visible
  bash). 기존 runner 테스트 회귀 없음.

- [ ] **Step 5: 커밋** — `test(gate): pin runner rc for cd/dot/hop/subshell` (임시)

---

## Task 10: 검증 — e2e A/B(v0.3.2 대비)·mutation battery·마무리

**Files:** 코드 변경 없음. 스크래치패드 probe harness 사용
(`…/scratchpad/ab/unit_probe.py`, `e2e_ab.sh`).

- [ ] **Step 1: 단위 probe A/B** — `python unit_probe.py scripts/`로 현재 트리의 판정을 v0.3.2
  추출(`…/ab/v032/`)과 비교. 기대: P1·P1b·P2·P2b·P5a·P5b·P6·X1 `is_invocation` False→True,
  D3→`/wt`·unresolved 반영, D4a·D4b·D7·D8·D9 반영. 언급(ctl) 항목 불변.

- [ ] **Step 2: e2e A/B (WSL)** — `MSYS_NO_PATHCONV=1 wsl.exe -d Ubuntu --exec bash e2e_ab.sh cur
  scripts/ flow-tiers.yaml` 및 v0.3.2 추출로 동일 실행. 기대 rc(spec §3 표):

  | 사례 | v0.3.2 | 수정 후 |
  |---|---|---|
  | P1·P2·P5a·P5b·P6·X1 (wt2 dirty, 마커 없음) | 0 | 2 |
  | D3·D4a·D4b·D8 (wt2 dirty, main 깨끗, 마커 없음) | 0 | 2 |
  | D7 (main dirty + docs 마커, hook cwd wt2) | 2 | 0 |
  | 대조: 일반 커밋 / `-C wt2` | 2 | 2 |
  | 대조: `rg "git commit"` 언급 / `cd MAIN &&` | 0 | 0 |

  "do the missed ones really commit?" 섹션이 P1/P5a/P5b/P6/X1에 `committed=YES`를 계속 보이는지도
  확인(수정은 판정만 바꾸지 실행을 막지 않음).

- [ ] **Step 3: mutation battery** — 기준선 초록 확인
  (`uv run pytest tests/harness_paths tests/flow_gate/test_runner_commit.py -q`). 변경 8개를
  하나씩 되돌려(Python read-modify-write, `assert old in text`로 적용 확인) 관련 새 테스트가
  실패하는지 확인 후 `git checkout --`로 복원. 되돌릴 지점:
  1. §1(a) `_runs_by_flag`의 `return True`(printf 분기) → `return False`
  2. §1(a) 값 검사 `not any(c.isspace()…)` → `True` (공백 값도 프로그램 취급)
  3. §1(b) `keep_heredoc=True` → `False` (본문 다시 blank)
  4. §1(c) `_substitutions`의 `<`/`>` 분기 삭제
  5. §1(d) `_XARGS` 검사 `and` → `or`가 아니라, `set(names) & _XARGS` → `set()`
  6. §2(a) `_norm_dir`의 `(".", "./")` → `("__none__",)`
  7. §2(b) `_CD_PREFIX_RE`의 `[;\n]` 삭제(다시 `&&`만)
  8. §2(c/d) `_cd_hop_before_bare_commit`의 `s > lead_end` → `s >= 0`(선두 prefix도 hop 취급) 또는
     `_UNKNOWN_DIR in answers` → `False`
  배터리가 행을 앞으로 나르면 이동한 앵커로 드롭한 행을 보고(CLAUDE.md mutation 규칙). POSIX 가드
  변형은 WSL에서.

- [ ] **Step 4: 마무리** — `uv run pytest`(전체), `ruff check`, `pre-commit run --all-files`. 테스트를
  목록 사이로 옮겼으므로 수집 node id를 변경 전후 `comm`으로 비교:
  `git stash` 없이 baseline은 이전 커밋에서 `pytest --collect-only -q`를 뽑아 `comm -3`로 대조 —
  이동/이름변경만 있고 조용한 드롭이 없는지 확인. 기존 성능 테스트(`test_*_bounded_time`)로 hook
  시간 한도 이내 확인.

- [ ] **Step 5: 커밋 없음** — 검증 단계. 실패 시 해당 Task로 복귀.

---

## Task 11: 독립 도메인 리뷰 (2라운드) + 문서 + 최종 커밋

**Files:**
- Modify: `scripts/_harness_paths.py`(주석), `CLAUDE.md`(Invariant 6)
- Review: `general-purpose` 에이전트

- [ ] **Step 1: 코드 주석 정리** — `_READS_ONLY`의 rg·sort 설명(285–287) 정정(플래그 규칙 반영),
  `_INTERPRETER_RE` 관련 주석 잔재 삭제 확인, `_CD_PREFIX_RE`·`commit_tree_unresolved`·
  `is_invocation` docstring이 새 동작과 일치하는지 확인.

- [ ] **Step 2: CLAUDE.md Invariant 6 문구 갱신** — line 136–137의 "하나의 선언된 예외" 서술을
  넓힌다. 현재: "commit invocations disagree on the directory". 갱신: 커밋 트리를 한 곳으로 정할 수
  없는 명령(다른 디렉터리를 가리키는 호출, 따라갈 수 없는 cd, 전개되지 않은 `-C`)은 게이트한다.
  Invariant 7은 이미 "면제는 과잉 차단 쪽으로 틀려야 함"이라 확인만.

- [ ] **Step 3: doc-sync 게이트** — `doc-sync` 스킬 호출(코드↔문서 드리프트, CLAUDE.md 조화) →
  `touch .claude/vway-kit/.vdev/doc-sync.done`.

- [ ] **Step 4: 도메인 리뷰 R1** — `general-purpose` 에이전트(별도 컨텍스트, shell 실행 가능)에게:
  probe harness·WSL로 커밋 누락 방향, 과잉 차단 비용, "새 차단 금지"(Invariant 6) 위반을 보게 함.
  `git`으로 변경 파일 전부를 리뷰하고 `VERDICT: PASS`/`FAIL` 한 줄을 요구. FAIL이면 수정 후 재리뷰
  (리뷰가 요청한 수정은 이전 통과를 무효화 — doc-sync·리뷰 재실행).

- [ ] **Step 5: 도메인 리뷰 R2** — 필요 시 2라운드. 통과 시 `touch
  .claude/vway-kit/.vdev/review.done`(마지막 편집 이후 무편집이어야 fixpoint).

- [ ] **Step 6: 최종 커밋(한 커밋으로 amend)** — Task 1–9의 임시 커밋들을 하나로 접는다
  (memory `one-commit-readable-message`). 소비자 배포 스크립트라 `fix(gate):`. `commit` 스킬로:

```
fix(gate): see commits the classifier missed and stop one over-block

- Deny the reads-only exemption to a reader given an exec-capable flag
  (printf -v, rg --pre, sort --compress-program).
- Read a non-reader heredoc body as a script, so an interpreter the list
  never named over-gates instead of turning the gate off.
- Keep a process substitution one element; read xargs/parallel git commit.
- Share the dot normalization; read a leading cd terminated by `;`.
- Mark untrackable dir changes and unexpanded -C unresolved.
```

- [ ] **Step 7: 병합** — rebase → 통합 테스트 확인 → dev squash(사용자 확인). memory
  `gate-invocation-gaps`를 해결 상태로 갱신. 후속: vway-kit 반영(별도 작업).

---

## Self-Review

**Spec coverage (§ 대응):**
- §1(a) → Task 1(spans)·Task 2(플래그)·Task 5(독립 토큰 폴백). §1(b) → Task 3. §1(c) → Task 4.
  §1(d) → Task 5. §2(a) → Task 6. §2(b) → Task 7. §2(c)·(d) → Task 8. runner → Task 9.
  e2e·mutation·마무리 → Task 10. 문서·리뷰·커밋 → Task 11. **모든 § 커버됨.**
- spec §3의 corpus 추가·과잉차단 4건 이동·line 232 테스트 갱신·runner rc·e2e 표·mutation 배터리·
  comm·perf → Task 2·3·8·9·10에 각각 배치됨.
- spec §4의 코드 주석·CLAUDE.md·doc-sync·`fix(gate)` 커밋·vway-kit 후속 → Task 11.

**미해결 리스크(실행 중 Step 4에서 판정):**
- Task 2의 `rg --pre git x commit`은 `git_subcommand_re`가 `git x commit`을 못 볼 수 있어 §1(d)
  독립 토큰 검사에 의존한다(Task 5에서 연결). Task 2에서 그 corpus 행은 `# needs §1(d)` 주석으로
  미루고 Task 5 뒤 PASS 확인 — 계획에 명시됨.
- Task 9 D7은 `_run_runner`가 hook cwd를 main으로 고정하므로 `hook_cwd` 인자 추가가 전제(Step 2·3).

**Type/이름 일관성:** `_program_spans`(Task 1) → Task 2·5·8이 소비. `_norm_dir`(Task 6) → Task 8이
확장. `_UNKNOWN_DIR`·`_cd_hop_before_bare_commit`(Task 8). `_runs_by_flag`(Task 2) → Task 5가
`is_invocation`에서 함께 호출. `scripted`(Task 3) → Task 5가 참조. 이름 충돌·미정의 없음.

**Placeholder:** 없음(모든 Step에 실제 테스트/코드/명령).
