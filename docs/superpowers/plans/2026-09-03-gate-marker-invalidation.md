# 게이트 마커 자동 무효화 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 파일 편집이 일어나면 `review.done`·`doc-sync.done` 증거 마커가 자동으로 사라져, 리뷰/문서 통과 **이후**의 수정이 낡은 마커를 타고 커밋되지 못하게 한다.

**Architecture:** 플러그인 소유 `PostToolUse` 훅(`Edit|Write|MultiEdit|NotebookEdit`)이 편집 시점에 두 마커를 지운다. 차단은 기존 "마커 없음 → exit 2" 경로가 그대로 수행하므로 게이트 판정 로직은 손대지 않는다. review/doc-sync 는 서로를 무효화하는 게이트라 **둘 다** 지워야 고정점이 성립하고("두 마커를 딴 뒤 편집 0회"), 흔한 경우 1패스로 수렴하도록 Dev 티어 순서를 doc-sync → review 로 바꾼다.

**Tech Stack:** bash (훅 런타임은 Windows Git Bash·Linux CI 양쪽) · pytest · 플러그인 `hooks/hooks.json`

**Spec:** 이 문서 §설계 근거 (대화에서 확정: 편집 시점 삭제, 두 마커 동시, 순서 교체)

## 설계 근거 (spec)

- **삭제 트리거는 편집 그 자체.** "리뷰 시작 시 삭제"는 통과 *이후*의 수정을 못 잡아 현재 구멍이 그대로 남는다.
- **삭제 방향이 안전한 방향.** 남겨야 할 마커를 지우면 재실행 비용이고, 지워야 할 마커를 남기면 검토받지 않은 커밋이 통과한다. 그래서 판단이 불확실한 모든 경우는 **삭제**하고, 훅 자체의 실패는 마커를 **그대로 둔다**(FAIL-OPEN: 게이트는 직전의 더 엄격한 답을 유지).
- **호스트 `settings.json` 이 아니라 플러그인 `hooks/hooks.json`.** 커밋 게이트가 settings.json 에 사는 이유는 deny 강제의 신뢰성과 그 파일에서 `${CLAUDE_PLUGIN_ROOT}` 가 해석되지 않는다는 점이다. 이 훅은 deny 하지 않고 파일 하나를 지울 뿐이며, hooks.json 에서는 플러그인 루트가 해석되므로 호스트 복사·설치·해제 배선이 통째로 불필요하다(reuse-before-build: 새 배선 대신 이미 있는 채널).
- **범위 가드.** 프로젝트 밖 편집(스크래치패드·다른 저장소)은 마커를 건드리지 않는다. 증거 디렉터리 자신에 대한 쓰기도 제외한다.

## Global Constraints

- 훅 런타임 OS = Windows(Git Bash) + Linux CI. 경로 비교는 `\`/`/` 혼용과 대소문자 차이를 모두 흡수해야 한다.
- `*.sh` 는 ShellCheck 통과 필수. POSIX 전용 동작(파일 모드·소유자)은 WSL 에서 확인한다.
- 저장소 산출물 언어는 영어(주석·docstring·테스트 assert 메시지). 한국어는 게이트/CLI 출력과 그 출력을 비교하는 기대 문자열에만.
- 소비자에게 가는 `.md`(rules/·skills/) 변경은 커밋 타입 `feat`/`fix` (`docs` 는 전파되지 않음).
- 마커 경로는 `${CLAUDE_PROJECT_DIR}/.claude/harness-tier/.flow/` — 플러그인 디렉터리에는 아무것도 쓰지 않는다.

---

### Task 1: 무효화 훅 스크립트

**Files:**
- Create: `hooks/invalidate-gate-markers.sh`
- Test: `tests/test_invalidate_gate_markers.py`

**Interfaces:**
- Consumes: stdin 으로 오는 PostToolUse 훅 페이로드(JSON), 환경변수 `CLAUDE_PROJECT_DIR`
- Produces: `<project>/.claude/harness-tier/.flow/review.done`·`doc-sync.done` 삭제. 실제로 하나라도 지웠을 때만 stdout 에 `{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"…"}}` 를 낸다. 종료 코드는 항상 0.

- [ ] **Step 1: Write the failing test**

`tests/test_invalidate_gate_markers.py`:

```python
"""The PostToolUse hook that voids the review/doc-sync evidence on an edit.

Deleting is the safe direction: a marker that should have survived costs a re-run, while one
that should have gone lets an unreviewed commit through. So every case this hook cannot decide
deletes, and only a positively-outside path is spared. Everything about the hook itself is
FAIL-OPEN — no project dir, no evidence dir, an unreadable payload: exit 0, markers untouched,
the gate keeps whatever answer it already had.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPT = REPO / "hooks" / "invalidate-gate-markers.sh"
# Windows resolves a bare "bash" via System32 first (the WSL stub), which cannot see C:/… paths.
BASH = shutil.which("bash") or "bash"

MARKERS = ("review.done", "doc-sync.done")
KEPT = ("bump.done", "security.done")


def payload(file_path: str | None) -> str:
    body: dict[str, object] = {"hook_event_name": "PostToolUse", "tool_name": "Edit"}
    if file_path is not None:
        body["tool_input"] = {"file_path": file_path}
    return json.dumps(body)


@pytest.fixture
def project(tmp_path: Path) -> Path:
    flow = tmp_path / "project" / ".claude" / "harness-tier" / ".flow"
    flow.mkdir(parents=True)
    for name in (*MARKERS, *KEPT):
        (flow / name).touch()
    return tmp_path / "project"


def run(project: Path | None, stdin: str) -> subprocess.CompletedProcess[str]:
    env = {"PATH": "/usr/bin:/bin"}
    if project is not None:
        env["CLAUDE_PROJECT_DIR"] = str(project)
    return subprocess.run(
        [BASH, str(SCRIPT)],
        input=stdin,
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def flow(project: Path) -> Path:
    return project / ".claude" / "harness-tier" / ".flow"


def test_edit_inside_the_project_voids_both_markers(project: Path):
    out = run(project, payload(str(project / "src" / "app.py")))
    assert out.returncode == 0, out.stderr
    for name in MARKERS:
        assert not (flow(project) / name).exists(), (
            f"{name} survived an edit — a fix made after the gate passed would commit on it"
        )


def test_the_other_gates_markers_are_left_alone(project: Path):
    run(project, payload(str(project / "src" / "app.py")))
    for name in KEPT:
        assert (flow(project) / name).exists(), (
            f"{name} was deleted: bump/security are promotion-time decisions on a clean tree, "
            f"and re-asking for them is friction this hook never earns"
        )


def test_an_edit_outside_the_project_is_not_an_edit_to_this_repo(project: Path, tmp_path: Path):
    run(project, payload(str(tmp_path / "scratchpad" / "note.md")))
    for name in MARKERS:
        assert (flow(project) / name).exists(), (
            f"{name} was voided by a scratchpad write — every temp file would cost a re-review"
        )


def test_a_write_into_the_evidence_dir_does_not_void_the_evidence(project: Path):
    run(project, payload(str(flow(project) / "tier")))
    for name in MARKERS:
        assert (flow(project) / name).exists(), f"{name} was voided by a write to the evidence dir"


def test_a_payload_without_a_path_voids(project: Path):
    """Cannot tell where the edit landed → delete. The alternative keeps a marker over an edit
    nobody has seen, which is the one direction this hook may never fail in."""
    run(project, payload(None))
    for name in MARKERS:
        assert not (flow(project) / name).exists(), f"{name} survived an undecidable payload"


def test_an_unparseable_payload_voids(project: Path):
    run(project, "not json at all")
    for name in MARKERS:
        assert not (flow(project) / name).exists(), f"{name} survived an unparseable payload"


def test_a_windows_spelled_path_is_read_as_inside(project: Path):
    """The payload carries the OS's own spelling: on Windows a backslash path, JSON-escaped."""
    win = str(project).replace("/", "\\") + "\\src\\app.py"
    run(project, json.dumps({"tool_input": {"file_path": win}}))
    for name in MARKERS:
        assert not (flow(project) / name).exists(), f"{name} survived a backslash-spelled path"


def test_no_project_dir_is_quiet(tmp_path: Path):
    out = run(None, payload(str(tmp_path / "a.py")))
    assert out.returncode == 0 and out.stdout.strip() == ""


def test_no_evidence_dir_is_quiet(tmp_path: Path):
    (tmp_path / "bare").mkdir()
    out = run(tmp_path / "bare", payload(str(tmp_path / "bare" / "a.py")))
    assert out.returncode == 0 and out.stdout.strip() == ""


def test_it_says_so_only_when_it_actually_voided_something(project: Path):
    """Context on every edit would be noise; context on none leaves the agent re-running a gate
    it does not know it lost."""
    first = run(project, payload(str(project / "src" / "app.py")))
    assert "review" in json.loads(first.stdout)["hookSpecificOutput"]["additionalContext"]
    second = run(project, payload(str(project / "src" / "app.py")))
    assert second.stdout.strip() == "", "spoke again with no marker left to void"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_invalidate_gate_markers.py -v`
Expected: 전부 FAIL — `hooks/invalidate-gate-markers.sh` 가 없어 bash 가 `No such file or directory` 로 종료(returncode 127).

- [ ] **Step 3: Write minimal implementation**

`hooks/invalidate-gate-markers.sh`:

```bash
#!/usr/bin/env bash
# PostToolUse hook — an edit voids the review and doc-sync evidence.
#
# Those two gates judge the working tree, and their markers are branch-bound: they outlive the
# commit that used them. Left in place, a fix made after either passed commits against a marker
# earned over code no reviewer and no doc pass ever saw. They come in a pair because they
# invalidate each other — a review finding is fixed after doc-sync ran, and the fix is then
# undocumented — so the only stable state is "both recorded, nothing edited since".
#
# Deleting is the safe direction: a marker that should have survived costs a re-run, one that
# should have gone lets an unreviewed commit through. Hence every undecidable case deletes, and
# every failure of this hook leaves the markers alone (FAIL-OPEN — the gate keeps the stricter
# answer it already had).

set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-}"
[ -n "$root" ] || exit 0
root="${root%/}"
flow="${root}/.claude/harness-tier/.flow"
[ -d "$flow" ] || exit 0

# One spelling to compare in: JSON's escaped separators, the OS's own, and Windows' case
# insensitivity all reach here, and a path that merely LOOKS outside is a marker kept over an
# unreviewed edit.
norm() {
  local s="${1//\\\\//}"
  s="${s//\\//}"
  s="${s%/}"
  printf '%s' "${s,,}"
}

payload="$(cat 2>/dev/null)" || payload=""
path="$(printf '%s' "$payload" |
  sed -n 's/.*"file_path"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' | head -n 1)"

if [ -n "$path" ]; then
  np="$(norm "$path")"
  nr="$(norm "$root")"
  case "$np" in
    "$nr"/.claude/harness-tier/.flow/*) exit 0 ;;  # the evidence dir writes its own files
    "$nr"/*) ;;                                    # inside the project → void
    *) exit 0 ;;                                   # positively outside → not this repo's tree
  esac
fi

voided=""
for marker in review.done doc-sync.done; do
  [ -e "$flow/$marker" ] || continue
  rm -f "$flow/$marker" 2>/dev/null || continue
  voided="${voided}${voided:+, }${marker%.done}"
done
[ -n "$voided" ] || exit 0

# Only when something was actually voided: on every edit this is noise, on none the agent
# re-runs a gate it does not know it lost.
printf '{"hookSpecificOutput":{"hookEventName":"PostToolUse","additionalContext":"%s"}}\n' \
  "harness-tier: this edit voided the ${voided} gate evidence. Re-run those gates before committing."
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_invalidate_gate_markers.py -v`
Expected: PASS (11 passed)

- [ ] **Step 5: ShellCheck + WSL**

```bash
shellcheck hooks/invalidate-gate-markers.sh
wsl -e bash -c "cd /mnt/c/Work/llm_ai/harness-tier && uv run pytest tests/test_invalidate_gate_markers.py -q"
```
Expected: ShellCheck 무출력, pytest 전부 통과. (훅 런타임이 Windows 라 bash 버그는 FAIL-OPEN 으로 숨는다 — 두 곳 다 돌린다.)

---

### Task 2: 훅 등록 (플러그인 hooks.json)

**Files:**
- Modify: `hooks/hooks.json`
- Test: `tests/test_invalidate_gate_markers.py` (Task 1 파일에 등록 검증 추가)

**Interfaces:**
- Consumes: Task 1 의 `hooks/invalidate-gate-markers.sh`
- Produces: `PostToolUse` 항목 하나 — matcher `Edit|Write|MultiEdit|NotebookEdit`

- [ ] **Step 1: Write the failing test**

`tests/test_invalidate_gate_markers.py` 끝에 추가:

```python
HOOKS_JSON = REPO / "hooks" / "hooks.json"
EDIT_TOOLS = ("Edit", "Write", "MultiEdit", "NotebookEdit")


def test_the_hook_is_registered_for_every_tool_that_edits_a_file():
    """A script nothing invokes is the gate silently off. The matcher is the whole registration:
    a tool missing from it edits files with the evidence left standing."""
    entries = json.loads(HOOKS_JSON.read_text(encoding="utf-8"))["hooks"]["PostToolUse"]
    matchers = [e["matcher"] for e in entries for h in e["hooks"] if SCRIPT.name in h["command"]]
    assert matchers, f"{SCRIPT.name} is registered in no PostToolUse entry"
    named = set(matchers[0].split("|"))
    assert set(EDIT_TOOLS) <= named, f"{set(EDIT_TOOLS) - named} edit files but never void evidence"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_invalidate_gate_markers.py::test_the_hook_is_registered_for_every_tool_that_edits_a_file -v`
Expected: FAIL — `KeyError: 'PostToolUse'`

- [ ] **Step 3: Write minimal implementation**

`hooks/hooks.json` 의 `hooks` 객체에 추가(기존 `SessionStart`·`Notification` 유지):

```json
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit|NotebookEdit",
        "hooks": [
          {
            "type": "command",
            "command": "bash \"${CLAUDE_PLUGIN_ROOT}/hooks/invalidate-gate-markers.sh\"",
            "timeout": 10
          }
        ]
      }
    ]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_invalidate_gate_markers.py -v`
Expected: PASS (12 passed)

---

### Task 3: 문서 — 순서 교체와 규칙 반영

**Files:**
- Modify: `rules/risk-tiers.md` (Step 3 Dev 오버레이: doc-sync 를 Domain review 앞으로, 무효화 규칙 추가)
- Modify: `skills/flow/SKILL.md` (Dev Step 3 순서 교체 + 이번 세션에 이미 들어간 수동 `rm -f` 산문을 자동 무효화로 고쳐 씀, Critical rule 2)
- Test: `tests/test_skills.py` (기존 — 회귀 확인)

**Interfaces:**
- Consumes: Task 1·2 가 만든 훅의 동작(편집 → 두 마커 삭제)
- Produces: 없음(문서)

- [ ] **Step 1: risk-tiers.md — 순서 교체**

`rules/risk-tiers.md` Step 3 의 Dev 오버레이에서 `**`/doc-sync`** → record `doc-sync`.` 불릿을 **Domain review 불릿 앞으로** 옮기고, Domain review 불릿 첫 문장의 "the last gate before commit" 은 그대로 둔다(이제 사실이 된다).

- [ ] **Step 2: risk-tiers.md — 무효화 규칙 한 단락**

Domain review 불릿 ④ 뒤에 잇는다:

```markdown
     ⑤ 마커는 브랜치에 묶여 커밋을 넘어 살아남는다. 그래서 편집이
     일어나는 순간 `PostToolUse` 훅이 `review`·`doc-sync` 두 마커를
     지운다 — 리뷰가 요구한 수정도 예외가 아니다. 통과 상태는 "두
     마커를 기록한 뒤 편집이 0회"라는 고정점이고, 수정이 생기면
     doc-sync → review 를 다시 밟는다. 훅이 못 본 편집(터미널·다른
     도구)은 손으로 지운다:
     `rm -f .claude/harness-tier/.flow/review.done .claude/harness-tier/.flow/doc-sync.done`.
```

- [ ] **Step 3: skills/flow/SKILL.md — Dev Step 3 순서 교체 + 산문 교체**

`doc-sync` 불릿을 **Domain review 불릿 앞으로** 옮기고, 이번 세션에 들어간 수동 무효화 산문(리뷰 불릿의 "Run `rm -f …`" 문단)을 자동 무효화로 고쳐 쓴다:

```markdown
     **Every edit after that pass voids it** — the fixes the review itself asked
     for included. The `PostToolUse` hook deletes `review.done` **and**
     `doc-sync.done` the moment a file changes, so the passing state is a
     fixpoint: both recorded, nothing edited since. A fix therefore re-runs
     doc-sync and then the review. An edit the hook never saw (a terminal
     command, another tool) leaves the markers standing — delete them by hand.
```

Critical rule 2 의 문단도 같은 사실로 줄인다(수동 절차 → 훅이 하고, 손으로 지우는 건 훅이 못 본 편집뿐).

- [ ] **Step 4: 테스트**

Run: `uv run pytest tests/test_skills.py -q`
Expected: PASS. 링크·frontmatter·`allowed-tools` 회귀 없음(새 `rm -f` 는 산문 안의 인라인 명령이라 규칙을 요구하지 않는다 — 증거 삭제는 프롬프트를 유지한다).

- [ ] **Step 5: 전체 스위트**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check`
Expected: 전부 통과.

---

## 게이트 마무리 (Task 3 이후, /flow Dev 디스패치)

1. `doc-sync` 스킬 — README/USAGE 와 한국어 쌍둥이까지 훅 하나가 늘어난 사실을 반영 → `doc-sync.done`
2. 독립 `general-purpose` 도메인 리뷰 → `review.done`
3. `commit` 스킬로 단일 커밋. 타입은 `feat`(소비자에게 가는 훅·규칙 변경이라 `docs`/`chore` 는 전파되지 않는다).
