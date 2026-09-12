# 주석 규율 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 주석을 쓰기 전에 Fail-Fast 를 먼저 시도하게 하고, 불가할 때만 `CRITICAL TRAP` 고정 3줄을 쓰게 하며, 기계로 판정 가능한 세 위반(라인번호 앵커·이력/작성자 필드·형식 깨진 TRAP 박스)을 `--lint` 가 잡게 한다.

**Architecture:** 규칙은 `rules/doc-style.md`(소비자에게 ship), 기계 절반은 `scripts/doc_style_check.py` 의 `BANNED` 표에 새 코드 셋, 판단 절반은 새 스킬 `skills/prose-review/` 가 맡고 `doc-sync` 가 내부 호출한다. 최초 작성 시점 도달은 `hooks/inject-risk-tiers.sh` 가 risk-tiers 블록 **뒤에** 별도 블록으로 요약을 주입해 얻는다.

**Tech Stack:** Python 3.8+ (표준 라이브러리 `re`·`ast`·`tokenize`), pytest, bash, PyYAML

**Spec:** [2026-09-12-comment-discipline-design.md](../specs/2026-09-12-comment-discipline-design.md)

## Global Constraints

- **파이썬 하한은 3.8.** `scripts/doc_style_check.py` 는 게이트가 spawn 하는 프로세스이고, 여기서 `TypeError` 가 나면 `flow_gate_check.py` 가 같이 죽어 **FAIL-OPEN** 한다. 모듈 레벨에서 `tuple[...]` 같은 3.9 문법을 평가하지 않는다(기존 `TYPE_CHECKING` 가드 유지).
- **저장소 언어는 영어** — 문서·주석·docstring·테스트 단언 메시지. `docs/superpowers/` 만 한국어.
- **박스 키 셋은 언어 불변 리터럴**: `CRITICAL TRAP:` · `Trigger:` · `Symptom:`. 번역하지 않는다.
- **커밋은 하나로 접는다.** Task 1 이 `Skill: commit` 으로 커밋을 만들고, 이후 Task 는 `git add <파일들> && git commit --amend --no-edit` 로 같은 커밋에 접는다. 마지막에 메시지를 한 번 다듬는다.
- **소비자에게 가는 `.md` 변경은 `feat`** — `docs`·`chore` 는 릴리스에 전파되지 않는다.
- **훅 파일은 한 바이트만 바뀌어도** `doc-sync`·`flow`·`commit`·`release-commit` 네 스킬의 `description_sha` 가 바뀐다(`evals/scores.py` 의 `INJECTED`). Task 7 이 그 비용을 진다.
- 테스트 실행은 `uv run pytest`, 린트는 `uv run ruff check && uv run ruff format --check`.

---

### Task 1: `ANCHOR` — 라인번호 앵커

**Files:**
- Modify: `scripts/doc_style_check.py`
- Modify: `scripts/check-merge-ruleset.sh`
- Test: `tests/doc_style/test_prose_rules.py`

**Interfaces:**
- Consumes: 없음
- Produces: `MASK_MODE: dict[str, str]` (코드→마스크 모드), `_mask(line: str, mode: str = "default") -> str`. Task 3 이 `lint_text` 의 같은 자리를 고치므로 이 이름들이 그대로 쓰인다.

라인 앵커는 거의 언제나 백틱 안이나 링크 텍스트에 쓰인다. 기존 `_mask` 는 인라인 코드를 지우므로 그대로 쓰면 이 규칙은 아무것도 잡지 못한다. `ANCHOR` 만 **인라인 코드를 남기고 URL·링크 타깃을 지운** 라인을 읽는다.

- [ ] **Step 1: Write the failing test**

`tests/doc_style/test_prose_rules.py` 의 `test_banned_prose_is_an_error` 파라미터 목록 끝에 추가:

```python
        ("Same guard as `precommit-runner.sh:31`.", "ANCHOR"),
        ("See scripts/check-deps.sh:10 for the other half.", "ANCHOR"),
        ("The failure lands in flow_gate_check.py: 12.", "ANCHOR"),
```

그리고 같은 파일 끝에 비적중 케이스를 추가:

```python
def test_a_url_port_is_not_a_line_anchor():
    """`ANCHOR` reads inline code, so the URL masking is the only thing keeping a port out."""
    assert _codes(Path("doc.md"), "Serve it at http://localhost:8000/openapi.json\n") == []


def test_a_github_line_link_target_is_not_a_line_anchor():
    """The target is a permalink; the claim would be in the link TEXT, which stays readable."""
    assert _codes(Path("doc.md"), "See [the guard](scripts/check-deps.sh#L10).\n") == []


def test_a_bare_filename_is_allowed():
    assert _codes(Path("doc.md"), "The guard lives in `precommit-runner.sh`.\n") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/doc_style/test_prose_rules.py -k "anchor or banned_prose" -v`
Expected: FAIL — `ANCHOR` 가 `BANNED` 에 없어 `_codes` 가 빈 목록을 돌려줌

- [ ] **Step 3: Write minimal implementation**

`scripts/doc_style_check.py` 의 `SHA = re.compile(...)` 아래에 패턴을 추가한다:

```python
# A filename followed by a line number. The extension whitelist is the rule: without it
# `12:30`, `localhost:8000` and a YAML `key: 3` all read as anchors.
ANCHOR = re.compile(
    r"[\w.\-/\\]*[\w\-]\."
    r"(?:py|sh|bash|md|ya?ml|json|toml|ts|tsx|js|jsx|go|rs|java|rb|kt|"
    r"c|h|cc|cpp|hpp|cs|php|sql)"
    r"\s*:\s*\d+"
)
```

`_mask` 를 모드 세 개로 바꾼다:

```python
def _mask(line: str, mode: str = "default") -> str:
    """Blank out spans a prose rule must never read: code, URLs, and link targets.

    Three modes, because two rules need to see what the default hides. ``links`` serves
    PLAN: a backticked ``docs/superpowers/plans/`` NAMES the banned pattern, where a link
    to one IS the pointer the rule bans. ``code`` serves ANCHOR: a line anchor is nearly
    always written inside backticks, so blanking code would switch that rule off.
    """
    patterns = {
        "default": (INLINE_CODE, LINK_TARGET, URL),
        "links": (INLINE_CODE, URL),
        "code": (LINK_TARGET, URL),
    }[mode]
    for pattern in patterns:
        line = pattern.sub(lambda m: " " * len(m.group(0)), line)
    return line
```

`BANNED` 표의 `CLAIM` 뒤에 항목을 추가한다:

```python
    (
        "ANCHOR",
        "error",
        ANCHOR,
        "line-number anchor — name the file; the number is false after the next insert",
    ),
```

`READS_LINK_TARGETS = ("PLAN",)` 를 지우고 그 자리에 매핑을 둔다:

```python
# Which spans each rule reads. Anything unlisted takes the default mask (see :func:`_mask`).
MASK_MODE = {"PLAN": "links", "ANCHOR": "code"}
```

`lint_text` 의 본문을 바꾼다:

```python
def lint_text(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for lineno, raw in prose_of(path, text):
        if not raw.strip():
            continue
        masked = {mode: _mask(raw, mode) for mode in ("default", "links", "code")}
        for code, severity, pattern, message in BANNED:
            m = pattern.search(masked[MASK_MODE.get(code, "default")])
            if m:
                hit = m.group(0).strip() or masked["default"].strip()
                findings.append((severity, lineno, code, f"{message} — {hit!r}"))
        line = masked["default"]
        if len(line) > MAX_LINE and "|" not in line:
            findings.append(
                ("warning", lineno, "LONG", f"prose line is {len(line)} chars (cap {MAX_LINE})")
            )
    return findings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/doc_style/ -v`
Expected: PASS 전부

- [ ] **Step 5: 이 저장소의 위반 두 건을 고친다**

`scripts/check-merge-ruleset.sh` 의 주석에서 줄 번호만 지운다:

```bash
# CLAUDE.md Invariant #2 — the host/hook locale is cp949 (or cp1252), so a child python's
# default I/O encoding is NOT UTF-8. Same guard, same place, as check-deps.sh and
# precommit-runner.sh.
```

- [ ] **Step 6: 저장소 전량으로 회귀 확인**

Run:
```bash
git ls-files '*.md' 'scripts/*.py' 'scripts/*.sh' 'hooks/*.sh' 'evals/*.py' 'tests/*.py' \
  | grep -v '^docs/superpowers/' | grep -v '^\.superpowers/' | grep -v '^CHANGELOG\.md$' \
  | xargs uv run python scripts/doc_style_check.py --root . --lint
```
Expected: `ANCHOR` 위반 0건

- [ ] **Step 7: Commit**

```bash
uv run ruff check && uv run ruff format --check
```
그 다음 `Skill: commit` 을 티어(dev)와 변경 내용으로 호출해 커밋을 만든다. 이후 Task 는 이 커밋에 접는다.

---

### Task 2: `META` — 이력·날짜·작성자 필드

**Files:**
- Modify: `scripts/doc_style_check.py`
- Test: `tests/doc_style/test_prose_rules.py`

**Interfaces:**
- Consumes: Task 1 의 `BANNED` 표 위치와 `MASK_MODE`(META 는 기본 모드라 등록하지 않는다)
- Produces: 없음

날짜 하나만으로는 이력인지 계약인지 구분할 수 없다. 그 판정은 `prose-review` 의 몫이고, 여기서는 **필드 라벨**만 잡는다.

- [ ] **Step 1: Write the failing test**

`test_banned_prose_is_an_error` 파라미터에 추가:

```python
        ("@author jdoe", "META"),
        ("Author: J. Doe", "META"),
        ("Last updated: 2026-09-12", "META"),
        ("작성자: 홍길동", "META"),
        ("수정이력: 인코딩 가드 추가", "META"),
```

비적중 케이스도 추가:

```python
def test_a_bare_date_is_not_a_metadata_field():
    """A date can be a contract (a cutoff, a deprecation). Only a field label is banned."""
    assert _codes(Path("doc.md"), "The pin expires 2026-12-31.\n") == []


def test_the_word_author_inside_a_sentence_is_not_a_field():
    assert _codes(Path("doc.md"), "The skill will author the workflow file.\n") == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/doc_style/test_prose_rules.py -k "meta or author or date" -v`
Expected: FAIL — `META` 미구현

- [ ] **Step 3: Write minimal implementation**

`BANNED` 표의 `ANCHOR` 뒤에 추가한다:

```python
    (
        "META",
        "error",
        re.compile(
            # `@author` and friends anywhere; a field LABEL only at the head of the line.
            # `python_prose`/`shell_prose` hand over the comment body already stripped, but
            # `markdown_prose` hands over the raw line, so the leading-space allowance stays.
            r"@(author|since|date)\b"
            r"|^\s*(author|created|modified|updated|last updated|revision|history|"
            r"changelog)\s*:"
            r"|작성자|작성일|수정일|변경\s*이력|수정\s*이력",
            re.IGNORECASE | re.MULTILINE,
        ),
        "revision metadata — git holds the history, the date and the name",
    ),
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/doc_style/ -v`
Expected: PASS 전부

- [ ] **Step 5: 저장소 전량 확인**

Run:
```bash
git ls-files '*.md' 'scripts/*.py' 'scripts/*.sh' 'hooks/*.sh' 'evals/*.py' 'tests/*.py' \
  | grep -v '^docs/superpowers/' | grep -v '^\.superpowers/' | grep -v '^CHANGELOG\.md$' \
  | xargs uv run python scripts/doc_style_check.py --root . --lint
```
Expected: `META` 위반 0건 — 구현 전 측정에서 이 저장소의 적중은 0이었다

- [ ] **Step 6: Commit**

```bash
uv run ruff check && uv run ruff format --check
git add scripts/doc_style_check.py tests/doc_style/test_prose_rules.py
git commit --amend --no-edit
```

---

### Task 3: `TRAP` — 박스 형식 강제

**Files:**
- Modify: `scripts/doc_style_check.py`
- Test: `tests/doc_style/test_prose_rules.py`

**Interfaces:**
- Consumes: Task 1 이 고친 `lint_text`
- Produces: `_blocks(prose: list) -> list[list]` — 연속 산문 줄의 묶음. 다른 Task 는 쓰지 않는다.

세 규칙 중 이것만 줄 하나로 판정할 수 없다. `CRITICAL TRAP` 마커가 있는 블록에 `Trigger:` 와 `Symptom:` 이 둘 다 있어야 한다. **마커가 없는 다중 줄 주석은 잡지 않는다** — 잡으면 이 저장소 주석 상당수가 위반이 되고, 그 주석들은 잘라내면 사실이 사라지는 것들이다.

- [ ] **Step 1: Write the failing test**

`tests/doc_style/test_prose_rules.py` 끝에 추가:

```python
TRAP_OK = (
    "# CRITICAL TRAP: the gate passes a commit it should block\n"
    "# Trigger: a cp949 host with a Korean reason string\n"
    "# Symptom: exit 0, empty stderr, the commit lands unreviewed\n"
    "x = 1\n"
)

TRAP_NO_KEYS = (
    "# CRITICAL TRAP: the gate passes a commit it should block\n"
    "# it happens when the host locale is cp949\n"
    "x = 1\n"
)

TRAP_SPLIT = (
    "# CRITICAL TRAP: the gate passes a commit it should block\n"
    "\n"
    "# Trigger: a cp949 host\n"
    "# Symptom: the commit lands unreviewed\n"
    "x = 1\n"
)


def test_a_complete_trap_box_passes():
    assert "TRAP" not in _codes(Path("m.py"), TRAP_OK)


def test_a_trap_box_without_its_keys_is_an_error():
    assert "TRAP" in _codes(Path("m.py"), TRAP_NO_KEYS)


def test_a_blank_line_ends_the_box():
    """The keys have to sit in the marker's own block — a later comment is a later comment."""
    assert "TRAP" in _codes(Path("m.py"), TRAP_SPLIT)


def test_a_multi_line_comment_without_the_marker_is_not_checked():
    body = "# the locale is cp949 here\n# so the child python needs PYTHONUTF8\nx = 1\n"
    assert "TRAP" not in _codes(Path("m.py"), body)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/doc_style/test_prose_rules.py -k trap -v`
Expected: FAIL — `test_a_trap_box_without_its_keys_is_an_error` 와 `test_a_blank_line_ends_the_box` 가 실패

- [ ] **Step 3: Write minimal implementation**

`MASK_MODE` 아래에 패턴과 블록 헬퍼를 둔다:

```python
TRAP_MARKER = re.compile(r"CRITICAL TRAP\s*:")
TRAP_KEYS = (("Trigger:", re.compile(r"^\s*Trigger\s*:", re.M)),
             ("Symptom:", re.compile(r"^\s*Symptom\s*:", re.M)))


def _blocks(prose: list) -> list:
    """Runs of consecutive non-blank prose lines.

    A blank line ends a run, and so does a gap in the numbering: one comment and the next
    are two boxes, and reading them as one would let a marker borrow the keys below it.
    """
    out: list = []
    for lineno, raw in prose:
        if not raw.strip():
            continue
        if out and lineno == out[-1][-1][0] + 1:
            out[-1].append((lineno, raw))
        else:
            out.append([(lineno, raw)])
    return out


def _trap_findings(prose: list) -> list:
    """The one rule a single line cannot answer: the box is three lines or it is not a box."""
    findings = []
    for block in _blocks(prose):
        marker = next((ln for ln, raw in block if TRAP_MARKER.search(raw)), None)
        if marker is None:
            continue
        body = "\n".join(raw for _, raw in block)
        missing = [name for name, pattern in TRAP_KEYS if not pattern.search(body)]
        if missing:
            findings.append(
                ("error", marker, "TRAP", f"CRITICAL TRAP box is missing {' and '.join(missing)}")
            )
    return findings
```

`lint_text` 에서 줄 루프를 돌기 전에 산문을 한 번만 뽑고, 루프 뒤에 블록 검사를 더한다:

```python
def lint_text(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    prose = prose_of(path, text)
    for lineno, raw in prose:
        if not raw.strip():
            continue
        masked = {mode: _mask(raw, mode) for mode in ("default", "links", "code")}
        for code, severity, pattern, message in BANNED:
            m = pattern.search(masked[MASK_MODE.get(code, "default")])
            if m:
                hit = m.group(0).strip() or masked["default"].strip()
                findings.append((severity, lineno, code, f"{message} — {hit!r}"))
        line = masked["default"]
        if len(line) > MAX_LINE and "|" not in line:
            findings.append(
                ("warning", lineno, "LONG", f"prose line is {len(line)} chars (cap {MAX_LINE})")
            )
    findings.extend(_trap_findings(prose))
    return findings
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/doc_style/ -v`
Expected: PASS 전부

- [ ] **Step 5: Commit**

```bash
uv run ruff check && uv run ruff format --check
git add scripts/doc_style_check.py tests/doc_style/test_prose_rules.py
git commit --amend --no-edit
```

---

### Task 4: 규칙 본문 — `rules/doc-style.md`

**Files:**
- Modify: `rules/doc-style.md`

**Interfaces:**
- Consumes: Task 1~3 의 코드 이름 `ANCHOR`·`META`·`TRAP`
- Produces: 새 절 제목 `## A comment is the last resort` — Task 5·6·7 이 이 제목으로 링크한다.

- [ ] **Step 1: "Banned outright" 표에 세 줄을 더한다**

기존 표의 `ENDING` 행 아래:

```markdown
| `ANCHOR` | A line number: `precommit-runner.sh:31` | The filename alone — the number is false after the next insert |
| `META` | A revision field: `@author` · `Author:` · `Last updated:` · `작성자` | Nothing. Git holds the history, the date and the name |
| `TRAP` | A `CRITICAL TRAP` box missing `Trigger:` or `Symptom:` | All three lines, or no box |
```

- [ ] **Step 2: "Per artifact" 앞에 새 절을 넣는다**

```markdown
## A comment is the last resort

Before writing one, try to delete the need for it.

1. **Never explain how.** The code says how. A comment that paraphrases the next line ages
   into a lie the moment that line changes, and a reader who trusts it is worse off than one
   who read the code.
2. **Make the code raise instead.** A constraint a reader could violate is a check, not a
   sentence: an `assert`, a raised error, a validated bound, a type. Prose asks to be
   believed; a failing call cannot be ignored.
3. **When it cannot raise, use the box.** Some traps have no runtime moment to fire at — a
   locale that silently changes an encoding, an ordering nothing observes until it is wrong.
   Those get exactly this shape, and nothing else earns three lines:

   ```
   # CRITICAL TRAP: <what breaks, silently>
   # Trigger: <the condition that reaches it>
   # Symptom: <what a reader sees when it does>
   ```

4. **No history, date, or name.** Git holds all three, and holds them correctly.
5. **A filename, never a line number.** `precommit-runner.sh` survives an edit;
   `precommit-runner.sh:31` is false the next time anyone inserts a line above it.
6. **Nothing self-evident.** A comment restating the identifier it sits on is noise that
   costs the reader a line and teaches them to skim the next one.

Everything left over is a reason or a constraint, and it fits on one line.

The three box keys are literals the checker parses, so they stay as written in every
project. What follows each key is prose: write it in the language the project's comments
are written in.
```

`ANCHOR` 는 인라인 코드를 읽으므로 규칙 5 의 `` `precommit-runner.sh:31` `` 이 **스스로 걸린다**. 그 줄만 백틱을 빼고 쓰거나, 예시를 펜스 블록으로 내린다. Step 4 의 자기 린트가 이것을 잡는다.

- [ ] **Step 3: "Per artifact" 의 주석 항목을 포인터로 줄인다**

```markdown
- **Comments and docstrings** — see "A comment is the last resort" above.
```

- [ ] **Step 4: 규칙 파일 스스로를 린트한다**

Run: `uv run python scripts/doc_style_check.py --root . --lint rules/doc-style.md`
Expected: 위반 0건. `ANCHOR` 가 걸리면 Step 2 의 안내대로 예시를 고친다.

- [ ] **Step 5: Commit**

```bash
git add rules/doc-style.md
git commit --amend --no-edit
```

---

### Task 5: `skills/prose-review/` 신설

**Files:**
- Create: `skills/prose-review/SKILL.md`
- Test: `tests/skills/` (기존 파라미터 테스트가 새 디렉터리를 자동으로 집는다)

**Interfaces:**
- Consumes: Task 4 의 절 제목, Task 1~3 의 코드 이름
- Produces: 스킬 이름 `prose-review` — Task 6 의 `doc-sync` 와 Task 8 의 `evals/cases.yaml` 이 이 이름을 쓴다.

`allowed-tools` 는 **넣지 않는다.** 이 스킬이 부르는 명령은 전부 경로 인자를 받고, 경로 인자를 사전 승인하려면 규칙이 `*` 로 끝나야 하며, 끝의 `*` 는 접두 일치라 `… && <무엇이든>` 까지 승인된다. `tests/skills/test_gate_reachability.py::test_no_allowed_tools_rule_ends_in_a_path_glob` 가 이것을 이미 강제한다.

- [ ] **Step 1: SKILL.md 를 쓴다**

```markdown
---
name: prose-review
description: Use when comments, docstrings or documents need checking against the prose rules — before writing them, or to clean up what is already there. Takes paths; with none, it reads the changed files. The doc-sync gate calls it.
argument-hint: "[paths… | empty = changed files]"
---

# prose-review

Half of the prose rules are patterns and half are judgement.
[`doc-style.md`](../../rules/doc-style.md) is the rule; this skill runs both halves over
files you name.

Report every violation in the language the user is writing in. The rule file is English;
the reader may not be.

## 1. The machine half

```bash
python3 .claude/harness-tier/scripts/doc_style_check.py --lint <paths>
```

`ANCHOR` · `META` · `TRAP` · `HIST` · `SHA` · `PLAN` · `FILLER` · `ENDING` are decided
here, and a repo without the script skips this step and keeps the judgement half.

## 2. The judgement half

No pattern answers these. Read each comment, docstring and paragraph the paths carry:

- **Does it explain how?** A paraphrase of the code beneath it goes, whatever it costs.
- **Could the code raise instead?** A constraint stated in prose that an `assert`, a
  validated bound or a type could carry is a comment that should not exist. Propose the
  check, not a better sentence.
- **Is it self-evident?** A comment restating its own identifier is noise.
- **Is a number a measurement or a contract?** Anything else is a guess wearing a figure —
  give the direction instead.
- **Is it as short as it can be?** Nominal endings, no connective padding.

## 3. Fix

Show each violation with the replacement, grouped by file. Apply what the user accepts.

## 4. Prove nothing was lost

```bash
python3 .claude/harness-tier/scripts/doc_style_check.py --verify-git <paths>
```

A rewrite that drops a heading, a fenced block, a URL or an inline-code span is a rewrite
that lost the fact. Restore it, or say in the report why the removal was the point.
```

- [ ] **Step 2: 스킬 테스트를 돌린다**

Run: `uv run pytest tests/skills/ -v`
Expected: PASS 전부. 실패하면 단언 메시지가 이유를 말한다(프론트매터 필드·설명 길이·링크 해석·`allowed-tools` 범위).

- [ ] **Step 3: 스킬 파일 스스로를 린트한다**

Run: `uv run python scripts/doc_style_check.py --root . --lint skills/prose-review/SKILL.md`
Expected: 위반 0건

- [ ] **Step 4: Commit**

```bash
git add skills/prose-review/SKILL.md
git commit --amend --no-edit
```

---

### Task 6: `doc-sync` 가 호출하게 한다

**Files:**
- Modify: `skills/doc-sync/SKILL.md` (1b 절 끝, `## 2. Gate marker` 직전)

**Interfaces:**
- Consumes: Task 5 의 스킬 이름 `prose-review`
- Produces: 없음

마커 **이전**이어야 한다. 마커 뒤에 두면 통과가 고정점이 아니게 되고, `PostToolUse` 훅이 그 편집으로 `doc-sync.done` 을 지운다.

- [ ] **Step 1: 1b 끝의 산문 문단을 호출로 바꾼다**

기존:

```markdown
Prose itself follows [`doc-style.md`](../../rules/doc-style.md): no history narration, no
pointer to a plan record, no filler, and Korean documents take nominal endings.
```

바꾼 뒤:

```markdown
Prose itself follows [`doc-style.md`](../../rules/doc-style.md). Half of that rule is
patterns and half is judgement, so run both over the files this run touched — invoke
`Skill: prose-review` with those paths. It reports what it would change; apply what
survives review before the marker, since an edit after the marker voids it.
```

- [ ] **Step 2: 링크 테스트를 돌린다**

Run: `uv run pytest tests/skills/ -v`
Expected: PASS 전부

- [ ] **Step 3: Commit**

```bash
git add skills/doc-sync/SKILL.md
git commit --amend --no-edit
```

---

### Task 7: SessionStart 주입

**Files:**
- Modify: `hooks/inject-risk-tiers.sh`
- Test: `tests/test_inject_risk_tiers.py`

**Interfaces:**
- Consumes: 없음
- Produces: 주입 태그 `<harness-tier-prose>` — 테스트가 이 이름으로 찾는다.

두 제약이 이 Task 의 모양을 정한다.

1. **risk-tiers 블록 안에 넣지 않는다.** 훅 자신의 주석이 그 이유를 적어 두었다 — 명령 옆의 텍스트가 스킬의 측정 호출률을 움직인다. 새 블록은 닫는 태그 **뒤**에 붙인다.
2. **`/스킬이름` 을 쓰지 않는다.** `tests/evals/test_injected_rule.py` 의
   `test_every_skill_the_injected_rule_names_declares_hook_assisted` 가 주입문이 이름을 부른 스킬에 `hook_assisted` 를 요구한다. 새 블록은 규칙만 말하고 스킬을 부르지 않는다.

- [ ] **Step 1: Write the failing test**

`tests/test_inject_risk_tiers.py` 에 추가한다. 헬퍼는 그 파일이 이미 가진 `_plugins_root`
· `_run` · `_context` 를 그대로 쓴다:

```python
def _prose_block(tmp_path) -> str:
    context = _context(_run(_plugins_root(tmp_path, published=None)))
    assert "<harness-tier-prose>" in context, "the prose summary never reached the session"
    return context.split("<harness-tier-prose>", 1)[1].split("</harness-tier-prose>", 1)[0]


def test_the_prose_block_follows_the_risk_tiers_block(tmp_path):
    """Text beside the mandate moves measured invocation rates, so the summary lives in its
    own block after the closing tag, never inside it."""
    context = _context(_run(_plugins_root(tmp_path, published=None)))
    assert context.index("</harness-tier-risk-tiers>") < context.index("<harness-tier-prose>")


@pytest.mark.parametrize("name", ["flow", "commit", "doc-sync", "release-commit", "prose-review"])
def test_the_prose_block_names_no_skill(tmp_path, name):
    """A skill named here would be forced to declare hook_assisted, folding this hook into its
    description_sha — see tests/evals/test_injected_rule.py. The path `/doc-style.md` in the
    block is why this asks about skill names rather than about any slash-word."""
    assert f"/{name}" not in _prose_block(tmp_path)


def test_the_prose_block_asks_for_the_users_language(tmp_path):
    assert "user's language" in _prose_block(tmp_path)


def test_the_prose_block_keeps_the_box_keys_untranslated(tmp_path):
    """The three keys are what the TRAP rule parses; a localized key is that rule switched
    off for that language."""
    block = _prose_block(tmp_path)
    for key in ("CRITICAL TRAP:", "Trigger:", "Symptom:"):
        assert key in block
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_inject_risk_tiers.py -k prose -v`
Expected: FAIL — `<harness-tier-prose>` 없음

- [ ] **Step 3: Write minimal implementation**

`session_context=` 대입 **아래**, `if [ -n "${CURSOR_PLUGIN_ROOT:-}" ]` **위**에 블록을 더한다:

```bash
# A separate block, after the risk-tiers one: the mandate's neighbourhood is measured, and
# text added beside it moves the skills' invocation rates. Names no skill — a slash name
# here would force `hook_assisted` onto it (tests/evals/test_injected_rule.py).
prose_block="\n\n<harness-tier-prose>\nThe rule below is guidance you apply while writing. Restate it to the user in the user's language whenever you surface it; do not quote it back in English by default.\n\nBefore writing a comment, ask whether the code can raise instead — an assert, a validated bound, a type. If it can, write that and no comment. Only a trap with no runtime moment to fire at earns the box. Never a how-explanation, a revision history, a date, an author, or a line number; filenames are fine.\n\nThe box keys are literals the checker parses and do not translate:\n  CRITICAL TRAP: / Trigger: / Symptom:\n\nFull rule: ${rules_dir_escaped}/doc-style.md\n</harness-tier-prose>"
session_context="${session_context}${prose_block}"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_inject_risk_tiers.py -v`
Expected: PASS 전부

- [ ] **Step 5: ShellCheck**

Run: `uv run pre-commit run --all-files` (또는 `shellcheck hooks/inject-risk-tiers.sh`)
Expected: 새 경고 없음. 훅 런타임은 Windows 이므로 여기서 놓친 버그는 FAIL-OPEN 으로 숨는다.

- [ ] **Step 6: 주입 결과를 눈으로 확인한다**

Run: `CLAUDE_PLUGIN_ROOT="$PWD" bash hooks/inject-risk-tiers.sh | python -c "import json,sys; print(json.load(sys.stdin)['hookSpecificOutput']['additionalContext'][-900:])"`
Expected: JSON 이 파싱되고 꼬리에 `<harness-tier-prose>` 블록이 보인다

- [ ] **Step 7: Commit**

```bash
git add hooks/inject-risk-tiers.sh tests/test_inject_risk_tiers.py
git commit --amend --no-edit
```

---

### Task 8: 측정 케이스와 전량 확인

**Files:**
- Modify: `evals/cases.yaml`
- Test: `tests/evals/`

**Interfaces:**
- Consumes: Task 5 의 스킬 이름, Task 7 이 바꾼 훅
- Produces: 없음

새 fixture 를 만든다. `outcome_sha(skill, scenario)` 는 시나리오 단위이고 `_outcome_targets` 는 `outcome=` 를 선언한 시나리오만 모으므로, `outcome=` 없는 시나리오를 더하는 것은 기존 지문을 하나도 바꾸지 않고 비용이 0 이다. 아낄 것이 없는 자리에서 측정 타당성을 내주면 안 된다 — `doc-sync-drift` 에는 주석도 docstring 도 라인번호 참조도 작성자 태그도 없는데, happy 프롬프트 다섯 중 넷이 바로 그것들을 지목한다. 전제가 거짓인 트리에서 나온 수치는 description 의 측정이 아니다.

- [ ] **Step 1: `evals/cases.yaml` 에 항목을 더한다**

```yaml
  prose-review:
    # No `hook_assisted`: the SessionStart hook carries the prose rule but names no skill,
    # so nothing in the session tells the agent to reach for this one.
    fixture: doc-sync-drift
    expect_invoke: 0.60
    expect_why: >-
      comment and wording asks name the artifact, not the skill.
    happy:
      - These comments explain what the code already says — clean them up.
      - Check the docstrings in this module against our prose rules.
      - Are there any line-number references left in the comments?
      - This file has an author tag and a change log in its header. Fix it.
      - Review the wording of the comments I just wrote.
    negative:
      - Run the unit tests.
      - Rename the helper to fetch_orders.
      - Add a new field to the user model.
      - Why is this endpoint slow?
      - Merge my branch into dev.
```

- [ ] **Step 2: 모델 없이 케이스 구조를 확인한다**

Run: `uv run pytest tests/evals/ -v`
Expected: PASS 전부. 실패는 대개 `hook_assisted` 양방향 검사 — 주입문이 스킬 이름을 부르지 않는지 Task 7 로 돌아가 확인한다.

- [ ] **Step 3: 측정 비용을 미리 센다**

Run: `uv run python -m evals.run --dry-run --all`
Expected: 세션 수와 벽시계 시간이 출력된다. Task 7 이 훅을 바꿨으므로 `doc-sync`·`flow`·`commit`·`release-commit` 네 개가 재측정 대상으로 잡혀야 한다 — 잡히지 않으면 지문이 안 바뀐 것이므로 Task 7 을 다시 본다.

- [ ] **Step 4: 전체 스위트**

Run: `uv run pytest`
Expected: PASS 전부

Run:
```bash
git ls-files '*.md' 'scripts/*.py' 'scripts/*.sh' 'hooks/*.sh' 'evals/*.py' 'tests/*.py' \
  | grep -v '^docs/superpowers/' | grep -v '^\.superpowers/' | grep -v '^CHANGELOG\.md$' \
  | xargs uv run python scripts/doc_style_check.py --root . --lint
```
Expected: 위반 0건

- [ ] **Step 5: Commit**

```bash
uv run ruff check && uv run ruff format --check
git add evals/cases.yaml docs/superpowers/
git commit --amend --no-edit
```

메시지를 한 번 다듬는다 — 소비자에게 가는 `rules/`·`skills/` 변경이 있으므로 `feat`.

---

## 실행 후 남는 것

- **실측 재측정은 이 계획 밖이다.** `uv run python -m evals.run` 은 사용자의 Claude Code 할당량을 쓰고 17분 단위로 돈다. 언제 돌릴지는 사람이 정한다.
- **`Updated:` 오탐**은 의도한 동작이다. 소비자가 처음 켤 때 다수 위반을 볼 수 있으나 `doc-style` 게이트는 커밋에서 경고만 하고 판정은 CI 가 쥔다.
