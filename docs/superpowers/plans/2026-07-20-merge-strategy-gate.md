# 머지 전략 게이트 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `git merge`가 브랜치 flow별 머지 전략을 지키는지 PreToolUse 훅에서 검사해, 플래그 형태 위반을 차단하고 rebase 미선행을 경고한다.

**Architecture:** 기존 PreToolUse:Bash 훅(`precommit-runner.sh`)의 self-filter를 `git merge`까지 넓혀 분기시킨다. 정책은 `flow-tiers.yaml`의 최상위 `merge_strategy:` 리스트 키에 두고, 판정은 `flow_gate_check.py --merge-check`가 수행한다. 판정 재료는 명령어 플래그·소스 브랜치·현재 브랜치 셋뿐이라 `origin` ref 신선도에 의존하지 않는다.

**Tech Stack:** Python 3.8+ (PyYAML) · bash (ShellCheck 검증) · pytest

## Global Constraints

- **Invariant #1 (FAIL-OPEN)**: 새 fail-closed는 "require 플래그 누락"·"forbid 플래그 존재" 둘뿐. 키 부재·YAML 파싱 실패·매칭 규칙 없음·detached HEAD·모든 예외는 `exit 0`.
- **Invariant #2 (Windows 인코딩)**: 모든 출력 경로에서 `force_utf8_io()` 선행, 파일 IO는 `encoding="utf-8"`.
- **Invariant #3 (차단 규약)**: 차단 = `exit 2`(=`BLOCK_EXIT_CODE`) + stderr 사유. 셸 쪽은 기존 `deny()` 재사용.
- **Invariant #4**: `settings.json`에 `if` 필드 추가 금지 — self-filter 방식 유지.
- **Invariant #6**: worktree 재지정(`--resolve-worktree`)은 merge 경로에서 호출하지 않는다.
- **경로 규약**: `${CLAUDE_PLUGIN_ROOT}`=읽기, `${CLAUDE_PROJECT_DIR}`=쓰기. 플러그인 디렉터리에 쓰지 않는다.
- **단방향 전파**: SOURCE(`scripts/`·`flow-tiers.yaml`)만 수정. 호스트 사본은 건드리지 않는다.
- **재사용 우선**: `BLOCK_EXIT_CODE`·`force_utf8_io()`·`host_root()`·`config_path()`·`tiers_path()`·`_current_branch()`를 재사용하고 새로 만들지 않는다.
- **커밋**: Conventional Commits 50/72, 타입은 `feat`(소비자 행동에 영향 → `docs`/`chore`는 전파 안 됨).
- **Bash 도구에서 PowerShell here-string(`@'...'@`) 금지** — heredoc 사용.

---

### Task 1: 정책 스키마 + 로더

**Files:**
- Modify: `flow-tiers.yaml` (최상위 `merge_strategy:` 키 추가)
- Modify: `scripts/flow_gate_check.py` (`load_merge_strategy` 추가)
- Test: `tests/test_flow_gate_check.py`

**Interfaces:**
- Produces: `load_merge_strategy(tiers_path: Path) -> list[dict]` — 규칙 리스트. 파일 없음·파싱 실패·키 부재·리스트 아님 → `[]` (FAIL-OPEN).

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_flow_gate_check.py` 끝에 추가:

```python
from scripts.flow_gate_check import load_merge_strategy


def test_merge_strategy_loads_rules(tmp_path: Path):
    tiers = tmp_path / "flow-tiers.yaml"
    tiers.write_text(
        "tiers:\n  dev:\n    gates: [review]\n"
        "merge_strategy:\n"
        '  - source: "feature/*"\n'
        "    target: integration\n"
        '    require: "--squash"\n'
        "    warn_unless_rebased: true\n",
        encoding="utf-8",
    )
    rules = load_merge_strategy(tiers)
    assert len(rules) == 1
    assert rules[0]["source"] == "feature/*"
    assert rules[0]["require"] == "--squash"
    assert rules[0]["warn_unless_rebased"] is True


def test_merge_strategy_absent_key_is_empty(tmp_path: Path):
    tiers = tmp_path / "flow-tiers.yaml"
    tiers.write_text("tiers:\n  dev:\n    gates: [review]\n", encoding="utf-8")
    assert load_merge_strategy(tiers) == []


def test_merge_strategy_missing_file_is_empty(tmp_path: Path):
    assert load_merge_strategy(tmp_path / "absent.yaml") == []


def test_merge_strategy_parse_error_is_empty(tmp_path: Path):
    tiers = tmp_path / "flow-tiers.yaml"
    tiers.write_text("merge_strategy: [unclosed\n", encoding="utf-8")
    assert load_merge_strategy(tiers) == []


def test_merge_strategy_non_list_is_empty(tmp_path: Path):
    tiers = tmp_path / "flow-tiers.yaml"
    tiers.write_text("merge_strategy:\n  feature: squash\n", encoding="utf-8")
    assert load_merge_strategy(tiers) == []
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_flow_gate_check.py -k merge_strategy -v`
Expected: FAIL — `ImportError: cannot import name 'load_merge_strategy'`

- [ ] **Step 3: 로더 구현**

`scripts/flow_gate_check.py`의 `required_gates` 함수 바로 아래에 추가:

```python
def load_merge_strategy(tiers_path: Path) -> list[dict]:
    """Return the merge_strategy rule list from flow-tiers.yaml.

    - Returns [] if the file is missing, fails to parse, has no merge_strategy key, or the
      key is not a list (FAIL-OPEN — Invariant #1). Removing the key disables the check.
    """
    if not tiers_path.is_file():
        return []
    try:
        import yaml

        data = yaml.safe_load(tiers_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    rules = data.get("merge_strategy")
    if not isinstance(rules, list):
        return []
    return [r for r in rules if isinstance(r, dict)]
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_flow_gate_check.py -k merge_strategy -v`
Expected: PASS (5 passed)

- [ ] **Step 5: 정책을 `flow-tiers.yaml`에 추가**

파일 끝(마지막 티어 정의 아래)에 빈 줄 하나를 두고 추가:

```yaml
# Merge strategy enforcement (branch flow → required/forbidden `git merge` flags).
# `source`/`target`: a value containing `/` is a branch-prefix glob; otherwise it is a key of
# flow-config.branches (integration | staging | production). `require`/`forbid` are single flag
# strings. `warn_unless_rebased` only warns — it never blocks.
# Removing this whole key disables the check (the gate then fails open).
merge_strategy:
  - source: "feature/*"
    target: integration
    require: "--squash"
    warn_unless_rebased: true
  - source: "hotfix/*"
    target: production
    require: "--squash"
  - source: staging
    target: production
    require: "--no-ff"
  - source: "fix/*"
    target: integration
    forbid: "--no-ff"
```

- [ ] **Step 6: 전체 테스트 통과 확인**

Run: `uv run pytest tests/test_flow_gate_check.py -v`
Expected: PASS (기존 케이스 전부 + 신규 5건)

- [ ] **Step 7: 커밋**

```bash
git add flow-tiers.yaml scripts/flow_gate_check.py tests/test_flow_gate_check.py
git commit -F - <<'EOF'
feat(flow): add merge_strategy policy and loader

The merge strategy lived only in risk-tiers.md prose; no code read it.
Add a top-level merge_strategy list to flow-tiers.yaml (sibling of
tiers:) and a loader that fails open on every uncertainty, so removing
the key disables the check rather than breaking commits.
EOF
```

---

### Task 2: `git merge` 명령어 파서

**Files:**
- Modify: `scripts/flow_gate_check.py` (`parse_merge_command` 추가)
- Test: `tests/test_flow_gate_check.py`

**Interfaces:**
- Consumes: 없음 (순수 함수)
- Produces: `parse_merge_command(command: str) -> tuple[set[str], str | None]` — `(플래그 집합, 소스 브랜치)`. merge 명령이 아니거나 파싱 실패 시 `(set(), None)`.

**주의 — 이 태스크의 핵심 함정:** `git merge --no-ff -m "Merge stage: headline" origin/stage`처럼 `-m` 인자가 있으면 단순 `split()`이 메시지 단어를 소스 브랜치로 오인한다. `shlex`로 토큰화하고 인자를 받는 플래그를 건너뛴다. `shlex`는 `merge` 서브커맨드 **뒤쪽만** 파싱하므로 `git -C C:\path\to\wt merge`의 Windows 경로 백슬래시 문제를 피한다.

- [ ] **Step 1: 실패하는 테스트 작성**

```python
from scripts.flow_gate_check import parse_merge_command


def test_parse_merge_plain():
    assert parse_merge_command("git merge feature/x") == (set(), "feature/x")


def test_parse_merge_squash():
    flags, src = parse_merge_command("git merge --squash feature/x")
    assert flags == {"--squash"}
    assert src == "feature/x"


def test_parse_merge_worktree_dash_c():
    # `git -C <dir> merge X` — the -C argument must not be taken as the source
    flags, src = parse_merge_command("git -C /tmp/wt merge --squash feature/x")
    assert flags == {"--squash"}
    assert src == "feature/x"


def test_parse_merge_message_arg_not_source():
    # -m's quoted argument must not be mistaken for the source branch
    flags, src = parse_merge_command('git merge --no-ff -m "Merge stage: headline" origin/stage')
    assert flags == {"--no-ff"}
    assert src == "origin/stage"


def test_parse_merge_ff_only():
    flags, src = parse_merge_command("git merge --ff-only origin/main")
    assert flags == {"--ff-only"}
    assert src == "origin/main"


def test_parse_merge_base_is_not_a_merge():
    # `git merge-base` / `git merge-file` must not be detected as a merge
    assert parse_merge_command("git merge-base --is-ancestor a b") == (set(), None)
    assert parse_merge_command("git merge-file a b c") == (set(), None)


def test_parse_merge_not_a_merge_command():
    assert parse_merge_command("git commit -m 'x'") == (set(), None)


def test_parse_merge_unbalanced_quote_fails_open():
    assert parse_merge_command('git merge -m "unclosed feature/x') == (set(), None)


def test_parse_merge_no_source():
    # `git merge` with no argument (continue an in-progress merge)
    assert parse_merge_command("git merge") == (set(), None)
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_flow_gate_check.py -k parse_merge -v`
Expected: FAIL — `ImportError: cannot import name 'parse_merge_command'`

- [ ] **Step 3: 파서 구현**

`scripts/flow_gate_check.py` 상단에 `import re`를 추가하고(이미 `import json, os, subprocess, sys`가 있으니 알파벳 순으로 `os` 뒤), `load_merge_strategy` 아래에 추가:

```python
# `merge` as a whole word — keeps `git merge-base` / `git merge-file` from false-positiving.
# Mirrors the _commit_re convention in precommit-runner.sh.
_MERGE_SPLIT_RE = re.compile(r"(?:^|\s)merge(?=$|[^\w-])")

# Flags that consume the next token as their argument. If not skipped, `-m "msg"` would leak
# the message into the source-branch slot.
_MERGE_FLAGS_WITH_ARG = frozenset(
    {"-m", "--message", "-F", "--file", "-s", "--strategy", "-X", "--strategy-option", "-S", "--gpg-sign"}
)


def parse_merge_command(command: str) -> tuple[set[str], str | None]:
    """Extract (flags, source branch) from a `git merge` invocation.

    Only the region *after* the `merge` subcommand is parsed, so `git -C <dir> merge X` never
    mistakes the -C argument for the source (and Windows backslash paths never reach shlex).
    Returns (set(), None) when this is not a merge, when there is no source operand, or on any
    parse failure (FAIL-OPEN — Invariant #1).
    """
    if not command:
        return set(), None
    parts = _MERGE_SPLIT_RE.split(command, maxsplit=1)
    if len(parts) < 2:
        return set(), None
    import shlex

    try:
        tokens = shlex.split(parts[1])
    except ValueError:  # unbalanced quotes → FAIL-OPEN
        return set(), None
    flags: set[str] = set()
    source: str | None = None
    skip_next = False
    for tok in tokens:
        if skip_next:
            skip_next = False
            continue
        if tok.startswith("-"):
            flags.add(tok.split("=", 1)[0])
            if tok in _MERGE_FLAGS_WITH_ARG:
                skip_next = True
            continue
        if source is None:
            source = tok
    return flags, source
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_flow_gate_check.py -k parse_merge -v`
Expected: PASS (9 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/flow_gate_check.py tests/test_flow_gate_check.py
git commit -F - <<'EOF'
feat(flow): parse merge flags and source branch

Parse only the region after the `merge` subcommand so `git -C <dir>
merge X` cannot mistake the -C argument for the source, and skip
argument-taking flags so `-m "Merge stage: headline"` does not leak
the message into the source slot. Unbalanced quotes fail open.
EOF
```

---

### Task 3: 규칙 매칭 (source/target 해석)

**Files:**
- Modify: `scripts/flow_gate_check.py` (`_branch_matches`, `match_merge_rule` 추가)
- Test: `tests/test_flow_gate_check.py`

**Interfaces:**
- Consumes: `load_merge_strategy` (Task 1), `load_lifecycle_branches`(기존)
- Produces:
  - `_branch_matches(pattern: str, branch: str, branches: dict) -> bool`
  - `match_merge_rule(rules: list[dict], source: str, target: str, branches: dict) -> dict | None`
  - `branches`는 `flow-config.yaml`의 `branches` 섹션 원본 dict(`{"integration": "dev", "staging": "stage", "production": "main", "feature_prefix": "feature/"}`).

**해석 규칙:** 패턴에 `/`가 있으면 브랜치 **접두사 glob**(`feature/*` → `feature/`로 시작), 없으면 `branches`의 키로 보고 그 값과 정확히 일치. 소스 브랜치의 `origin/` 접두사는 비교 전에 벗긴다(`git merge origin/stage`가 `staging` 키와 매칭되도록).

- [ ] **Step 1: 실패하는 테스트 작성**

```python
from scripts.flow_gate_check import _branch_matches, match_merge_rule

BRANCHES = {
    "integration": "dev",
    "staging": "stage",
    "production": "main",
    "feature_prefix": "feature/",
}

RULES = [
    {"source": "feature/*", "target": "integration", "require": "--squash", "warn_unless_rebased": True},
    {"source": "hotfix/*", "target": "production", "require": "--squash"},
    {"source": "staging", "target": "production", "require": "--no-ff"},
    {"source": "fix/*", "target": "integration", "forbid": "--no-ff"},
]


def test_branch_matches_prefix_glob():
    assert _branch_matches("feature/*", "feature/merge-gate", BRANCHES) is True
    assert _branch_matches("feature/*", "fix/typo", BRANCHES) is False


def test_branch_matches_config_key():
    assert _branch_matches("integration", "dev", BRANCHES) is True
    assert _branch_matches("integration", "stage", BRANCHES) is False
    assert _branch_matches("production", "main", BRANCHES) is True


def test_branch_matches_strips_origin_prefix():
    assert _branch_matches("staging", "origin/stage", BRANCHES) is True


def test_branch_matches_unknown_key_is_false():
    assert _branch_matches("nonesuch", "dev", BRANCHES) is False


def test_match_rule_feature_to_integration():
    rule = match_merge_rule(RULES, "feature/x", "dev", BRANCHES)
    assert rule is not None
    assert rule["require"] == "--squash"


def test_match_rule_staging_to_production():
    rule = match_merge_rule(RULES, "origin/stage", "main", BRANCHES)
    assert rule is not None
    assert rule["require"] == "--no-ff"


def test_match_rule_fix_to_integration():
    rule = match_merge_rule(RULES, "fix/typo", "dev", BRANCHES)
    assert rule is not None
    assert rule["forbid"] == "--no-ff"


def test_match_rule_no_match_returns_none():
    # integration → staging has no rule (policy says "Rebase or Merge")
    assert match_merge_rule(RULES, "dev", "stage", BRANCHES) is None


def test_match_rule_empty_rules_returns_none():
    assert match_merge_rule([], "feature/x", "dev", BRANCHES) is None
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_flow_gate_check.py -k "branch_matches or match_rule" -v`
Expected: FAIL — `ImportError: cannot import name '_branch_matches'`

- [ ] **Step 3: 매칭 구현**

`parse_merge_command` 아래에 추가:

```python
def _branch_matches(pattern: str, branch: str, branches: dict) -> bool:
    """Whether a branch matches a merge_strategy source/target pattern.

    A pattern containing `/` is a branch-prefix glob (`feature/*` → startswith `feature/`);
    otherwise it is a flow-config.branches key compared against that key's value. The
    `origin/` prefix is stripped from the branch first, so `git merge origin/stage` matches
    the `staging` key. An unknown key never matches (FAIL-OPEN — no rule applies).
    """
    if not pattern or not branch:
        return False
    name = branch[len("origin/") :] if branch.startswith("origin/") else branch
    if "/" in pattern:
        return name.startswith(pattern.rstrip("*"))
    configured = branches.get(pattern)
    return bool(configured) and name == str(configured)


def match_merge_rule(
    rules: list[dict], source: str, target: str, branches: dict
) -> dict | None:
    """Return the first rule whose source and target both match, else None (FAIL-OPEN)."""
    for rule in rules:
        if _branch_matches(str(rule.get("source", "")), source, branches) and _branch_matches(
            str(rule.get("target", "")), target, branches
        ):
            return rule
    return None
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_flow_gate_check.py -k "branch_matches or match_rule" -v`
Expected: PASS (9 passed)

- [ ] **Step 5: 커밋**

```bash
git add scripts/flow_gate_check.py tests/test_flow_gate_check.py
git commit -F - <<'EOF'
feat(flow): match merge rules by branch flow

Resolve a rule's source/target against flow-config.branches: a value
with `/` is a branch-prefix glob, otherwise it is a branches key. The
origin/ prefix is stripped first so `git merge origin/stage` matches
the staging key. No matching rule means no opinion — fail open.
EOF
```

---

### Task 4: 판정 + 메시지 (`--merge-check`)

**Files:**
- Modify: `scripts/flow_gate_check.py` (`_is_rebased`, `merge_check_output` 추가, `__main__` 디스패치에 분기 추가)
- Test: `tests/test_flow_gate_check.py`

**Interfaces:**
- Consumes: Task 1-3 전부, 기존 `host_root()`·`config_path()`·`tiers_path()`·`_current_branch()`·`force_utf8_io()`·`BLOCK_EXIT_CODE`
- Produces: `merge_check_output() -> None` — stdin에서 훅 JSON을 읽고 판정. 차단 시 stderr에 사유를 쓰고 `sys.exit(BLOCK_EXIT_CODE)`, 그 외 `sys.exit(0)`.

- [ ] **Step 1: 실패하는 테스트 작성**

기존 테스트가 `_current_branch`를 쓰므로 monkeypatch로 고정한다.

```python
def _write_policy(tmp_path: Path) -> Path:
    """Host layout: .claude/harness-tier/config/{flow-tiers,flow-config}.yaml"""
    cfg_dir = tmp_path / ".claude" / "harness-tier" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "flow-tiers.yaml").write_text(
        "tiers:\n  dev:\n    gates: [review]\n"
        "merge_strategy:\n"
        '  - source: "feature/*"\n'
        "    target: integration\n"
        '    require: "--squash"\n'
        "    warn_unless_rebased: true\n"
        '  - source: staging\n'
        "    target: production\n"
        '    require: "--no-ff"\n',
        encoding="utf-8",
    )
    (cfg_dir / "flow-config.yaml").write_text(
        "branches:\n  integration: dev\n  staging: stage\n  production: main\n"
        '  feature_prefix: "feature/"\n',
        encoding="utf-8",
    )
    return tmp_path


def _run_merge_check(monkeypatch, tmp_path: Path, command: str, branch: str):
    """Invoke merge_check_output with stdin/branch stubbed; return the SystemExit code."""
    import io

    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(fgc, "_current_branch", lambda root: branch)
    monkeypatch.setattr(fgc, "_is_rebased", lambda root, source, target: True)
    monkeypatch.setattr(
        sys, "stdin", io.StringIO(json.dumps({"tool_input": {"command": command}}))
    )
    with pytest.raises(SystemExit) as exc:
        fgc.merge_check_output()
    return exc.value.code


def test_merge_check_blocks_missing_squash(monkeypatch, tmp_path: Path, capsys):
    _write_policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, "git merge feature/x", "dev")
    assert code == fgc.BLOCK_EXIT_CODE
    assert "--squash" in capsys.readouterr().err


def test_merge_check_allows_squash(monkeypatch, tmp_path: Path):
    _write_policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, "git merge --squash feature/x", "dev")
    assert code == 0


def test_merge_check_blocks_missing_no_ff(monkeypatch, tmp_path: Path):
    _write_policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, "git merge origin/stage", "main")
    assert code == fgc.BLOCK_EXIT_CODE


def test_merge_check_allows_no_ff(monkeypatch, tmp_path: Path):
    _write_policy(tmp_path)
    code = _run_merge_check(
        monkeypatch, tmp_path, 'git merge --no-ff -m "Merge stage: x" origin/stage', "main"
    )
    assert code == 0


def test_merge_check_no_rule_fails_open(monkeypatch, tmp_path: Path):
    # dev → stage has no rule
    _write_policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, "git merge dev", "stage")
    assert code == 0


def test_merge_check_absent_policy_fails_open(monkeypatch, tmp_path: Path):
    cfg_dir = tmp_path / ".claude" / "harness-tier" / "config"
    cfg_dir.mkdir(parents=True)
    (cfg_dir / "flow-tiers.yaml").write_text("tiers:\n  dev:\n    gates: []\n", encoding="utf-8")
    code = _run_merge_check(monkeypatch, tmp_path, "git merge feature/x", "dev")
    assert code == 0


def test_merge_check_detached_head_fails_open(monkeypatch, tmp_path: Path):
    _write_policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, "git merge feature/x", None)
    assert code == 0


def test_merge_check_not_a_merge_fails_open(monkeypatch, tmp_path: Path):
    _write_policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, "git merge-base --is-ancestor a b", "dev")
    assert code == 0


def test_merge_check_warns_when_not_rebased(monkeypatch, tmp_path: Path, capsys):
    import io

    _write_policy(tmp_path)
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    monkeypatch.setattr(fgc, "_current_branch", lambda root: "dev")
    monkeypatch.setattr(fgc, "_is_rebased", lambda root, source, target: False)
    monkeypatch.setattr(
        sys,
        "stdin",
        io.StringIO(json.dumps({"tool_input": {"command": "git merge --squash feature/x"}})),
    )
    with pytest.raises(SystemExit) as exc:
        fgc.merge_check_output()
    assert exc.value.code == 0  # warning never blocks
    assert "rebase" in capsys.readouterr().err
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_flow_gate_check.py -k merge_check -v`
Expected: FAIL — `AttributeError`. 헬퍼가 `monkeypatch.setattr(fgc, "_is_rebased", …)`를 먼저 실행하므로 `_is_rebased` 쪽에서 먼저 터질 수 있다. 둘 중 어느 이름이 나와도 정상(둘 다 Step 3에서 정의된다).

- [ ] **Step 3: 판정 구현**

`match_merge_rule` 아래에 추가:

```python
def _is_rebased(root: Path, source: str, target: str) -> bool:
    """Whether target is an ancestor of source (i.e. source was rebased onto target).

    Used only for the warning path — a False here never blocks. Any git failure returns True
    (treated as "no complaint") so a stale/absent ref cannot produce a spurious warning.
    """
    try:
        rc = subprocess.run(
            ["git", "merge-base", "--is-ancestor", target, source],
            cwd=str(root),
            capture_output=True,
            timeout=5,
        ).returncode
    except Exception:
        return True
    return rc == 0


def merge_check_output() -> None:
    """Check a `git merge` invocation against the merge_strategy policy.

    Blocks (BLOCK_EXIT_CODE) only on two purely syntactic verdicts — a missing `require` flag or
    a present `forbid` flag. Everything else (not a merge, no source, no policy, no matching
    rule, detached HEAD, any exception) exits 0 (FAIL-OPEN — Invariant #1). The rebase check
    only warns. Invariant #2: force_utf8_io before any output.
    """
    force_utf8_io()
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)
    command = (payload.get("tool_input") or {}).get("command") or ""
    flags, source = parse_merge_command(command)
    if not source:
        sys.exit(0)

    root = host_root()
    target = _current_branch(root)
    if not target:  # detached HEAD → FAIL-OPEN
        sys.exit(0)

    try:
        import yaml

        data = yaml.safe_load(config_path(root).read_text(encoding="utf-8")) or {}
        branches = data.get("branches") or {}
    except Exception:
        branches = {}

    rule = match_merge_rule(load_merge_strategy(tiers_path(root)), source, target, branches)
    if rule is None:
        sys.exit(0)

    required = rule.get("require")
    if required and required not in flags:
        print(
            f"머지 전략 위반 — '{rule.get('source')}' → '{target}' 는 {required} 가 필요합니다. "
            f"절차는 risk-tiers 규칙의 Merge strategy 절을 따르세요.",
            file=sys.stderr,
        )
        sys.exit(BLOCK_EXIT_CODE)

    forbidden = rule.get("forbid")
    if forbidden and forbidden in flags:
        print(
            f"머지 전략 위반 — '{rule.get('source')}' → '{target}' 에는 {forbidden} 를 쓰지 않습니다. "
            f"절차는 risk-tiers 규칙의 Merge strategy 절을 따르세요.",
            file=sys.stderr,
        )
        sys.exit(BLOCK_EXIT_CODE)

    if rule.get("warn_unless_rebased") and not _is_rebased(root, source, target):
        print(
            f"[경고] 머지 전략: '{rule.get('source')}' → '{target}' 는 rebase 선행이 요구됩니다. "
            f"'{source}' 가 '{target}' 위에 rebase되어 있지 않은 것으로 보입니다"
            f"(origin ref 가 낡았다면 무시하세요).",
            file=sys.stderr,
        )
    sys.exit(0)
```

- [ ] **Step 4: `__main__` 디스패치에 분기 추가**

`scripts/flow_gate_check.py` 맨 아래 블록을 수정:

```python
if __name__ == "__main__":
    try:
        if "--module-commands" in sys.argv:
            module_commands_output()
        elif "--resolve-worktree" in sys.argv:
            resolve_worktree_output()
        elif "--merge-check" in sys.argv:
            merge_check_output()
        else:
            main()
    except SystemExit:
        raise
    except Exception as exc:  # FAIL-OPEN
        print(f"[flow-gate] unexpected error, allowing: {exc}", file=sys.stderr)
        sys.exit(0)
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/test_flow_gate_check.py -k merge_check -v`
Expected: PASS (9 passed)

- [ ] **Step 6: 전체 테스트 + 린트**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check`
Expected: 전부 PASS

- [ ] **Step 7: 커밋**

```bash
git add scripts/flow_gate_check.py tests/test_flow_gate_check.py
git commit -F - <<'EOF'
feat(flow): add --merge-check verdict and messages

Block only on two syntactic verdicts: a missing require flag or a
present forbid flag. Everything uncertain — no policy, no matching
rule, detached HEAD, unparseable command — exits 0 per Invariant #1.
The rebase check only warns, and a failed git call is treated as no
complaint so a stale ref cannot produce a spurious warning.
EOF
```

---

### Task 5: `precommit-runner.sh` 분기

**Files:**
- Modify: `scripts/precommit-runner.sh:52-62`(필터), `:106-124`(분기 삽입)

**Interfaces:**
- Consumes: `flow_gate_check.py --merge-check` (Task 4)
- Produces: 없음 (셸 진입점)

**주의:** 108-109행의 `git status` 조기 종료가 merge를 죽이므로 분기는 그 **앞**에 둔다. 의존성 FAIL-CLOSED(75-85행)는 두 경로가 공유하도록 분기를 그 **뒤**에 둔다.

- [ ] **Step 1: merge 감지 정규식 추가**

`_commit_re` 정의(61행) 바로 아래에 추가하고, 62행의 조기 종료를 교체:

```bash
# Detect `git merge` with the same convention as _commit_re: git global options (notably
# `git -C <worktree>`) may sit between `git` and the subcommand, and `merge` is matched as a
# whole word so `git merge-base` / `git merge-file` do not false-positive.
_merge_re='git([[:space:]]+-[^[:space:]]+([[:space:]]+[^[:space:]]+)?)*[[:space:]]+merge($|[^[:alnum:]-])'

_is_commit=0
_is_merge=0
[[ "${_hook_cmd:-$_hook_input}" =~ $_commit_re ]] && _is_commit=1
[[ "${_hook_cmd:-$_hook_input}" =~ $_merge_re ]] && _is_merge=1
[ "$_is_commit" -eq 1 ] || [ "$_is_merge" -eq 1 ] || exit 0
```

- [ ] **Step 2: merge 분기 삽입**

`cd "$ROOT" || exit 0`(106행) 바로 뒤, `status=` 줄(108행) **앞**에 삽입:

```bash
# merge gate — a merge runs on a clean tree, so it must branch off before the `git status`
# early-exit below. Uses neither .done markers nor module checks (the commit gate already
# vetted the content being moved) and skips worktree re-designation (Invariant #6).
if [ "$_is_merge" -eq 1 ] && [ "$_is_commit" -eq 0 ]; then
  merge_reason="$(printf '%s' "$_hook_input" | CLAUDE_PROJECT_DIR="$ROOT" \
    python3 "$PLUGIN_SCRIPTS/flow_gate_check.py" --merge-check 2>&1 >/dev/null)"
  merge_rc=$?
  if [ "$merge_rc" -eq 2 ] && [ -n "$merge_reason" ]; then
    deny "$merge_reason"
  fi
  [ -n "$merge_reason" ] && printf '%s\n' "$merge_reason" >&2   # warning passthrough
  exit 0
fi
```

- [ ] **Step 3: worktree 재지정을 commit 전용으로 제한**

94-104행의 worktree 블록을 `if [ "$_is_commit" -eq 1 ]; then … fi`로 감싼다 (Invariant #6 — merge 경로는 재지정하지 않는다):

```bash
if [ "$_is_commit" -eq 1 ]; then
  _wt="$(printf '%s' "$_hook_input" | CLAUDE_PROJECT_DIR="$ROOT" python3 "$PLUGIN_SCRIPTS/flow_gate_check.py" --resolve-worktree 2>/dev/null || true)"
  if [ -n "$_wt" ] && [ -d "$_wt" ]; then
    ROOT="$_wt"
  fi
fi
```

- [ ] **Step 4: ShellCheck 검증**

Run: `shellcheck scripts/precommit-runner.sh`
Expected: 경고 없음 (없으면 `uv run pre-commit run --all-files`로 대체 확인)

- [ ] **Step 5: 수동 동작 확인 (DRYRUN)**

Run:
```bash
echo '{"tool_input":{"command":"git merge feature/x"}}' | CLAUDE_PROJECT_DIR="$PWD" python3 scripts/flow_gate_check.py --merge-check; echo "exit=$?"
```
Expected: 이 저장소에는 호스트 config가 없으므로 `exit=0` (FAIL-OPEN 확인)

- [ ] **Step 6: 커밋**

```bash
git add scripts/precommit-runner.sh
git commit -F - <<'EOF'
feat(flow): gate git merge in the PreToolUse hook

The hook already sees every Bash call but self-filtered to `git
commit`. Detect `git merge` with the same whole-word convention and
branch before the `git status` early-exit, since a merge runs on a
clean tree. The merge path shares the dependency fail-closed check but
skips markers, module checks, and worktree re-designation.
EOF
```

---

### Task 6: 문서 표식 + 설치 테스트

**Files:**
- Modify: `rules/risk-tiers.md:345-352` (Merge strategy 표)
- Test: `tests/test_flow_init_setup.py`

**Interfaces:**
- Consumes: Task 1의 `merge_strategy` 정책

- [ ] **Step 1: 실패하는 테스트 작성**

`tests/test_flow_init_setup.py` 끝에 추가:

```python
def test_merge_strategy_policy_reaches_host(tmp_path: Path):
    """copy_artifacts must carry the merge_strategy policy into the host config dir."""
    import yaml

    from scripts.flow_init_setup import copy_artifacts

    plugin = Path(__file__).resolve().parents[1]
    host = tmp_path / "host"
    host.mkdir()
    copy_artifacts(plugin, host)
    dest = host / ".claude" / "harness-tier" / "config" / "flow-tiers.yaml"
    data = yaml.safe_load(dest.read_text(encoding="utf-8"))
    assert isinstance(data.get("merge_strategy"), list)
    assert any(r.get("require") == "--squash" for r in data["merge_strategy"])
```

- [ ] **Step 2: 테스트 실행 (이미 통과해야 정상)**

Run: `uv run pytest tests/test_flow_init_setup.py -k merge_strategy -v`
Expected: PASS — Task 1에서 정책을 추가했으므로 별도 구현 없이 통과한다. FAIL이면 Task 1의 YAML을 확인한다.

- [ ] **Step 3: risk-tiers 표에 게이트 표식 추가**

`rules/risk-tiers.md`의 Merge strategy 표를 교체(정책 내용은 그대로, 열 하나 추가):

```markdown
| Branch flow | Strategy | Gate |
|-------------|----------|------|
| `feature/*` → integration | **Rebase onto integration → integration-test gate → Squash** | ✅ enforced |
| `fix/*` / non-`feature/*` → integration | **Rebase** | ⚠️ `--no-ff` blocked |
| integration → staging | **Rebase** or **Merge** | — |
| staging → production | **`--no-ff` Merge** | ✅ enforced |
| `hotfix/*` → production | **Squash** | ✅ enforced |
| production → integration/staging (after release) | **FF / `--no-ff` Merge** (back-merge) | — |

> The **Gate** column reflects `flow-tiers.yaml`'s `merge_strategy` policy, checked by the
> PreToolUse hook on `git merge`. ✅ rows block a merge whose flags violate the strategy;
> `—` rows state a choice ("or"), so there is nothing to enforce. Enforcement covers
> **Claude-session merges only** — a terminal merge bypasses it, same as every layer-2 gate.
> The rebase step of row 1 is **warned, not blocked** (a stale `origin` ref would otherwise
> produce false positives).
```

- [ ] **Step 4: doc-sync 스킬 실행**

Dev 티어 게이트 요구사항. Run: `doc-sync` 스킬을 Skill 도구로 호출.
Expected: 문서 세트 정합성 PASS → `touch .claude/vway-kit/.vdev/doc-sync.done`

- [ ] **Step 5: 전체 검증**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check && uv run pre-commit run --all-files`
Expected: 전부 PASS

- [ ] **Step 6: 커밋**

```bash
git add rules/risk-tiers.md tests/test_flow_init_setup.py
git commit -F - <<'EOF'
feat(flow): mark enforced rows in strategy table

Add a Gate column so the table states which rows the hook actually
checks and which are advisory. The "or" rows have nothing to enforce,
and row 1's rebase step is warned rather than blocked.
EOF
```

---

## 완료 후 (플랜 밖)

- **Domain review** — 독립 `general-purpose` 리뷰 에이전트로 `flow-config.review_checklist` 대조 → `touch .claude/vway-kit/.vdev/review.done`
- **머지** — `feature/merge-strategy-gate` → `dev`는 risk-tiers Merge strategy에 따라 **rebase → 통합테스트 확인(사람) → squash**. 이 계획이 만든 게이트가 스스로에게는 적용되지 않는다(이 저장소는 `/flow-init` 미실행).
- **별건** — 자매 저장소 vway-kit에 동일 변경 반영(설계 §11).
