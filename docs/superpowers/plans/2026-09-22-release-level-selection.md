# Staging 릴리스 level 선택 재설계 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** staging 승격의 level 선택을 "대기 rc 유무"에 따라 결정적으로 계산하고, 잘못된 선택은 조용히 넘어가지 않고 실패시킴.

**Architecture:** 다음 버전 계산은 `scripts/bump_version.py next` 하나가 담당함(태그 목록 + HEAD 커밋 메시지 → `auto` 또는 확정 버전). 다섯 release 템플릿과 이 repo `release.yml` 은 그것을 부르는 **동일한 셸 블록**을 가지며, 강제 level 은 도구 플래그가 아니라 계산된 버전을 결정적으로 적용함(finalize 스텝과 같은 방식). `auto` 만 도구에 맡김.

**Tech Stack:** Python 3.8+ stdlib, bash, GitHub Actions YAML, pytest, python-semantic-release 10.x.

**Spec:** 이 대화에서 사용자가 확정한 규칙(아래 Global Constraints 에 원문 그대로).

## Global Constraints

- 대기 rc 가 없으면: 마지막 정식 태그에서 patch/minor/major 만큼 올리고 `-rc.1` 을 붙임. `auto`(커밋 타입으로 결정)도 선택지.
- 대기 rc 가 있으면(재승격): 그 rc 의 base 기준으로 계산. `v1.1.0-rc.2` 에서 continue → `v1.1.0-rc.3`, patch → `v1.1.1-rc.1`, minor → `v1.2.0-rc.1`, major → `v2.0.0-rc.1`.
- rc 가 없는데 `continue` → 실패(exit ≠ 0 + stderr 사유).
- 대기 rc 판정은 `git describe` 가 아니라 **태그 목록**: "같은 base 의 정식 태그가 없는 최고 rc". FF 거부로 staging back-merge 가 skip 된 브랜치에서도 정식화된 rc 를 대기로 오판하지 않음.
- 잘못된 트레일러 값(`Release-Level: pach`) → 실패. auto·skip 으로 떨어지지 않음.
- 다섯 템플릿 + 이 repo `release.yml` 이 같은 "다음 버전 계산" 셸 블록을 씀. 테스트가 그 블록을 실제 git 픽스처에서 돌림.
- 강제 level 은 결정적으로 적용. `auto` 만 도구에 맡김.
- `workflow_dispatch` 는 추가하지 않음 — trailer 경로 하나.
- 재승격은 staging → integration back-merge(FF, 안 되면 `--no-ff`) 후 level 을 다시 물음.
- CLAUDE.md: repo 산출물 영어, CRLF 정규화, `*.sh`·셸 블록은 WSL ShellCheck, 수정은 mutation test.

---

## File Structure

| 파일 | 책임 |
|---|---|
| `scripts/bump_version.py` | `next` subcommand 추가: trailer 파싱·검증, 태그 목록 → 대기 rc·마지막 정식, 다음 버전 계산 |
| `scripts/finalize_prerelease.py` | `--set VERSION` 모드 추가: pyproject·plugin.json 에 임의 버전 기록(plugin.json 없으면 skip) |
| `github/release.*.workflow.example.yml` (5) | 공유 블록 삽입 + 도구별 적용 |
| `.github/workflows/release.yml` | dogfood — PSR 템플릿과 같은 변경 |
| `tests/release_level/` (신규 폴더, `__init__.py`) | `test_next_version.py`(순수 함수·CLI), `test_shared_block.py`(블록 동일성 + git 픽스처 실행) |
| `tests/flow_init/test_render_versioning.py` | `_AUTO_ONLY_TOOLS` 비움, Node 도 trailer 읽음 |
| `tests/test_release_workflow.py` | `--as-prerelease` 단언 → 결정적 적용 단언으로 교체 |
| `skills/release-commit/SKILL.md`, `skills/commit/SKILL.md`, `rules/promotion.md`, `rules/merge-strategy.md`, `docs/usage/*` | 절차·규칙 |

---

### Task 1: `bump_version.py next` — 계산 코어

**Files:**
- Modify: `scripts/bump_version.py`
- Create: `tests/release_level/__init__.py`, `tests/release_level/test_next_version.py`

**Interfaces:**
- Produces:
  - `LEVELS = ("auto", "continue", "patch", "minor", "major")`
  - `parse_level(message: str) -> str` — `^Release-Level\s*:` 줄이 없으면 `"auto"`; 값이 `LEVELS` 밖이거나 비었거나 서로 다른 값이 둘 이상이면 `ValueError`.
  - `pending_rc(tags: list[str], token: str = "rc") -> tuple[str, int] | None` — `(base, N)`.
  - `last_stable(tags: list[str]) -> str` — 없으면 `"0.0.0"`.
  - `next_version(message: str, tags: list[str], token: str = "rc", auto_level: str | None = None) -> str` — `"auto"` 또는 `X.Y.Z-rc.N`. `continue` + 대기 rc 없음 → `ValueError`. `auto_level` 이 주어지면 `auto` 를 "대기 rc 있으면 continue, 없으면 `auto_level`" 로 바꿔 계산(스스로 level 을 못 정하는 도구용).
  - CLI: `bump_version.py next --message M --tags T [--token rc] [--auto-level patch]` — 성공: 한 줄 출력, exit 0. `ValueError`: stderr `bump_version: <사유>`, exit 2.
  - 태그 파싱: `v?` 접두사 허용, `X.Y.Z` 또는 `X.Y.Z-<token>.N` 외 태그는 무시.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/release_level/test_next_version.py`

```python
import pytest

from scripts.bump_version import last_stable, main, next_version, parse_level, pending_rc

TAGS_PENDING = ["v1.0.0", "v1.1.0-rc.1", "v1.1.0-rc.2"]
TAGS_RELEASED = ["v1.0.0", "v1.1.0-rc.1", "v1.1.0-rc.2", "v1.1.0"]


def msg(level: str | None) -> str:
    body = "Merge dev: headline\n\n- item\n"
    return body if level is None else body + f"\nRelease-Level: {level}\n"


@pytest.mark.parametrize(
    "level, expected",
    [
        ("continue", "1.1.0-rc.3"),
        ("patch", "1.1.1-rc.1"),
        ("minor", "1.2.0-rc.1"),
        ("major", "2.0.0-rc.1"),
    ],
)
def test_re_promotion_computes_from_the_pending_rc_base(level, expected):
    assert next_version(msg(level), TAGS_PENDING) == expected


@pytest.mark.parametrize(
    "level, expected",
    [("patch", "1.1.1-rc.1"), ("minor", "1.2.0-rc.1"), ("major", "2.0.0-rc.1")],
)
def test_first_promotion_bumps_the_last_stable_tag(level, expected):
    assert next_version(msg(level), TAGS_RELEASED) == expected


def test_continue_without_a_pending_rc_fails():
    with pytest.raises(ValueError, match="no pending"):
        next_version(msg("continue"), TAGS_RELEASED)


@pytest.mark.parametrize("message", [msg(None), msg("auto")])
def test_auto_is_left_to_the_tool(message):
    assert next_version(message, TAGS_PENDING) == "auto"


@pytest.mark.parametrize("value", ["pach", "", "Minor", "patch minor"])
def test_an_invalid_trailer_value_fails(value):
    with pytest.raises(ValueError, match="Release-Level"):
        parse_level(msg(value))


def test_two_different_trailers_fail():
    with pytest.raises(ValueError, match="Release-Level"):
        parse_level(msg("patch") + "Release-Level: minor\n")


def test_a_released_rc_is_not_pending_even_when_it_is_the_newest_tag():
    # Staging's back-merge was skipped (FF refused): describe on staging still reaches the rc,
    # but the tag list carries its stable twin.
    assert pending_rc(["v1.1.0-rc.2", "v1.1.0"]) is None


def test_pending_rc_is_the_highest_unreleased_one():
    assert pending_rc(["v1.0.0-rc.1", "v1.0.0", "v1.1.0-rc.1", "v1.1.0-rc.10", "v1.1.0-rc.9"]) == (
        "1.1.0",
        10,
    )


def test_unrelated_tags_are_ignored():
    assert last_stable(["v1.0.0", "latest", "v2.0.0-beta.1", "nightly-3"]) == "1.0.0"
    assert last_stable([]) == "0.0.0"


def test_auto_level_turns_auto_into_continue_or_the_fallback_level():
    assert next_version(msg(None), TAGS_PENDING, auto_level="patch") == "1.1.0-rc.3"
    assert next_version(msg(None), TAGS_RELEASED, auto_level="patch") == "1.1.1-rc.1"


def test_a_hotfix_that_shipped_the_rc_base_moves_the_next_rc_past_it():
    # stage waits on 1.1.1-rc.1, a hotfix shipped 1.1.1 straight to production.
    tags = ["v1.1.0", "v1.1.1-rc.1", "v1.1.1"]
    assert pending_rc(tags) is None
    assert next_version(msg("patch"), tags) == "1.1.2-rc.1"
    with pytest.raises(ValueError, match="no pending"):
        next_version(msg("continue"), tags)


def test_cli_prints_the_version(capsys):
    assert main(["next", "--message", msg("minor"), "--tags", "\n".join(TAGS_PENDING)]) == 0
    assert capsys.readouterr().out.strip() == "1.2.0-rc.1"


def test_cli_exits_2_with_a_reason(capsys):
    assert main(["next", "--message", msg("pach"), "--tags", ""]) == 2
    assert "Release-Level" in capsys.readouterr().err
```

- [ ] **Step 2: 실패 확인** — `uv run pytest tests/release_level -q` → ImportError (`next_version` 없음)

- [ ] **Step 3: 구현** — `scripts/bump_version.py` 에 추가

```python
LEVELS = ("auto", "continue", "patch", "minor", "major")
_TRAILER = re.compile(r"^Release-Level\s*:(.*)$", re.MULTILINE)
_TAG = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)(?:-([0-9A-Za-z]+)\.(\d+))?$")


def parse_level(message: str) -> str:
    values = {v.strip() for v in _TRAILER.findall(message)}
    if not values:
        return "auto"
    if len(values) > 1:
        raise ValueError(f"conflicting Release-Level trailers: {sorted(values)}")
    (value,) = values
    if value not in LEVELS:
        raise ValueError(f"Release-Level {value!r} is not one of {', '.join(LEVELS)}")
    return value


def _parse_tags(tags, token):
    stable, rcs = set(), []
    for t in tags:
        m = _TAG.match(t.strip())
        if not m:
            continue
        core = tuple(int(x) for x in m.group(1, 2, 3))
        if m.group(4) is None:
            stable.add(core)
        elif m.group(4) == token:
            rcs.append((core, int(m.group(5))))
    return stable, rcs


def _fmt(core):
    return ".".join(str(x) for x in core)


def pending_rc(tags, token="rc"):
    stable, rcs = _parse_tags(tags, token)
    open_rcs = [rc for rc in rcs if rc[0] not in stable]
    if not open_rcs:
        return None
    core, n = max(open_rcs)
    return _fmt(core), n


def last_stable(tags):
    stable, _ = _parse_tags(tags, "rc")
    return _fmt(max(stable)) if stable else "0.0.0"


def next_version(message, tags, token="rc", auto_level=None):
    level = parse_level(message)
    pending = pending_rc(tags, token)
    if level == "auto":
        if auto_level is None:
            return "auto"
        level = "continue" if pending else auto_level
    if level == "continue":
        if pending is None:
            raise ValueError("Release-Level: continue, but there is no pending rc to continue")
        base, n = pending
        return f"{base}-{token}.{n + 1}"
    base = pending[0] if pending else last_stable(tags)
    return bump(base, level, prerelease=f"{token}.1")
```

`main` 에 subparser 추가:

```python
    n = sub.add_parser("next")
    n.add_argument("--message", required=True)
    n.add_argument("--tags", required=True)
    n.add_argument("--token", default="rc")
    n.add_argument("--auto-level", choices=["patch", "minor", "major"], default=None)
```

분기(`args.cmd == "next"`)는 `try: print(next_version(...)); return 0` / `except ValueError as e: print(f"bump_version: {e}", file=sys.stderr); return 2`. `--tags` 는 `splitlines()`. 빈 `--auto-level ""` 을 셸 블록이 넘길 수 있으므로 `choices` 에 `""` 도 허용하고 `or None` 으로 정규화. 모듈 docstring 을 `next` 까지 포함하도록 고침(영어, doc-style).

- [ ] **Step 4: 통과 확인** — `uv run pytest tests/release_level tests/test_bump_version.py -q` → PASS
- [ ] **Step 5: mutation** — Python 으로 `assert old in text` 후 치환: (a) `rc[0] not in stable` → `True`, (b) `len(values) > 1` → `False`, (c) `if value not in LEVELS` → `if False`. 각각 테스트 FAIL 확인 후 `git checkout -- scripts/bump_version.py`.

---

### Task 2: 공유 셸 블록 + git 픽스처 테스트

**Files:**
- Create: `tests/release_level/test_shared_block.py`
- Modify: 6개 workflow 파일(블록 삽입만 — 적용은 Task 3–5)

**Interfaces:**
- Consumes: Task 1 CLI.
- Produces: 각 workflow 의 prerelease 스텝 `run:` 안에 아래 블록이 **바이트 동일**하게 들어감(들여쓰기 제외 비교). 블록은 `NEXT` 셸 변수를 남기고, 실패 시 스텝을 끝냄. 스텝 `env:` 에 `HARNESS_SCRIPTS`(템플릿: `.claude/harness-tier/scripts`, 이 repo: `scripts`)와 `AUTO_LEVEL`(jreleaser·gitversion: `patch`, 나머지: `""`).

```bash
# >>> next-version (shared by every release workflow; tests/release_level pins it)
git fetch --tags --force --quiet origin || true
NEXT="$(python3 "$HARNESS_SCRIPTS/bump_version.py" next \
  --message "$(git log -1 --pretty=%B)" \
  --tags "$(git tag --list)" \
  --auto-level "${AUTO_LEVEL:-}")" || exit 1
echo "next version: $NEXT"
# <<< next-version
```

- [ ] **Step 1: 테스트 작성** — `test_shared_block.py`
  - `_block(path)` : 파일에서 `# >>> next-version` ~ `# <<< next-version` 줄을 뽑아 각 줄 `strip()` 후 반환. CRLF 정규화(`read_text` 후 `replace("\r\n", "\n")`).
  - `test_every_release_workflow_carries_the_same_block` : 5개 템플릿 + `.github/workflows/release.yml` 의 블록이 모두 같음, 비어 있지 않음.
  - `test_block_runs_against_a_real_repo(tmp_path, tags, level, expected)` parametrize: `git init` → 커밋 → 태그들 생성 → `Release-Level` 이 든 커밋 → 블록을 `bash -c` 로 실행(`HARNESS_SCRIPTS=<ROOT>/scripts`, `AUTO_LEVEL=""`, `git fetch` 는 origin 없음 → `|| true`) 후 `echo "$NEXT"` 캡처. 케이스: 대기 rc(continue/patch/minor/major), 정식화된 rc + continue → exit ≠ 0, `pach` → exit ≠ 0, trailer 없음 → `auto`.
  - Windows 에서 `bash` 부재 시 `pytest.skip` — CI(ubuntu)가 권위. (`shutil.which("bash")`)
- [ ] **Step 2: 실패 확인** — 블록 없음 → FAIL
- [ ] **Step 3: 6개 파일 prerelease 스텝 `run:` 맨 앞에 블록 삽입**(기존 `LEVEL=...sed...` 줄 삭제), env 두 개 추가.
- [ ] **Step 4: 통과 확인** — WSL 에서 `uv run pytest tests/release_level -q` (bash 실경로), 블록을 파일로 뽑아 `shellcheck -s bash` 무경고.

---

### Task 3: PSR — 템플릿 + 이 repo `release.yml` + `finalize_prerelease.py --set`

**Files:**
- Modify: `scripts/finalize_prerelease.py`, `github/release.python-semantic-release.workflow.example.yml`, `.github/workflows/release.yml`
- Test: `tests/test_finalize_prerelease.py`, `tests/test_release_workflow.py`

**Interfaces:**
- Produces: `set_version(root: Path, version: str) -> None` — pyproject `[project]` version + plugin.json(있을 때만) 기록. CLI `finalize_prerelease.py --set X` → 기록 후 `X` 출력.
- prerelease 스텝 적용부(블록 뒤):

```bash
if [ "$NEXT" = "auto" ]; then
  semantic-release version --commit --tag --push --changelog
else
  python "$HARNESS_SCRIPTS/finalize_prerelease.py" --set "$NEXT"
  git add pyproject.toml
  [ -f .claude-plugin/plugin.json ] && git add .claude-plugin/plugin.json
  git commit -m "chore(release): $NEXT [skip ci]"
  git tag "v$NEXT"
  semantic-release changelog || true
  if ! git diff --quiet -- CHANGELOG.md; then
    git add CHANGELOG.md && git commit --amend --no-edit && git tag -f "v$NEXT"
  fi
  git push origin HEAD:"$REF_NAME"
  git push origin "v$NEXT"
fi
```

- [ ] **Step 1: WSL probe 먼저** — PSR 10 에서 `semantic-release changelog` 가 수동 태그 `vX.Y.Z-rc.N` 을 섹션으로 쓰는지, 그 뒤 `auto` 실행이 그 rc 를 이어가는지(rc.N+1) 확인. 스크래치 스크립트: 앞서 쓴 `psr_probe.sh` 를 변형. **기대와 다르면 여기서 멈추고 사용자에게 보고.**
- [ ] **Step 2: 테스트** — `test_finalize_prerelease.py` 에 `set_version` 케이스(plugin.json 있음/없음), `test_release_workflow.py` 의 `--as-prerelease` 단언 두 곳을 "`finalize_prerelease.py\" --set` 존재 + `--as-prerelease` 부재" 로 교체.
- [ ] **Step 3: 구현** → **Step 4: 통과** → **Step 5: mutation**(plugin.json 존재 가드 제거 → 테스트 FAIL).

---

### Task 4: gitversion · jreleaser · cargo-release

**Files:** 세 템플릿, `tests/test_release_workflow.py`

- gitversion·jreleaser: `AUTO_LEVEL: patch`, 기존 prerelease 분기의 `bump ... --prerelease "rc.$RUN_NUMBER"` 를 `NEXT` 사용으로 교체(블록이 이미 확정 버전을 줌). stable 분기는 그대로.
- cargo-release: `AUTO_LEVEL: ""`. `NEXT=auto` → 기존 `cargo release rc`, 아니면 `cargo release "$NEXT" --execute --no-confirm --no-publish`(cargo-release 는 LEVEL 자리에 명시 버전을 받음 — 구현 전 crate-ci/cargo-release 문서로 확인, 아니면 멈추고 보고). `test_new_language_templates_use_bump_version_helper_where_needed` 의 cargo "bump_version.py 부재" 단언은 블록 때문에 깨지므로 "cargo 는 `cargo release` 로 적용" 으로 고침.
- [ ] 테스트 → 실패 → 구현 → 통과.

---

### Task 5: Node semantic-release

**Files:** `github/release.semantic-release.workflow.example.yml`, `tests/flow_init/test_render_versioning.py`

- 스텝 분리: 공유 블록 → `NEXT=auto` 면 기존 `npx semantic-release`, 아니면 태그 기반 결정적 적용: `git tag -a "v$NEXT" -m "release v$NEXT"`, `git push origin "v$NEXT"`, `gh release create "v$NEXT" --generate-notes --prerelease`, `released=true`.
- stable 브랜치 finalize: 공유 블록과 같은 규칙으로 대기 rc 를 태그 목록에서 찾음(`bump_version.py finalize-tag --tags ...` 가 base 출력, 없으면 exit 1) → 있으면 `v<base>` 태그 + 정식 Release, 없으면 `npx semantic-release`.
- **위험(사용자 보고 필수)**: semantic-release 는 채널 정보를 git notes 로 추적함. notes 없는 수동 태그를 다음 auto 실행이 어떻게 읽는지 실측 불가(이 환경에 Node 프로젝트 없음) — Task 5 끝에 명시.
- `_AUTO_ONLY_TOOLS = set()` 로 바꾸고 해당 테스트 docstring 갱신.

---

### Task 5b: finalize 가드 — 정식 태그가 이미 있으면 실패

hotfix 가 대기 rc 의 base 를 먼저 정식 출시한 뒤(`v1.1.1`) 그 rc(`1.1.1-rc.1`)를 main 으로 올리면 finalize 가 같은 `v1.1.1` 을 다시 만들려다 `git tag` 에서 사유 없이 죽음. 계산 직후, 기록·커밋 전에 막음.

**Files:** 5개 템플릿 + `.github/workflows/release.yml` 의 stable 스텝, `tests/release_level/test_finalize_guard.py`

**Interfaces:**
- Produces: stable 스텝에서 finalize 로 얻은 `STABLE`(Node 는 `finalize-tag` 결과) 직후 아래 블록 — 템플릿 간 동일, `test_shared_block.py` 와 같은 방식으로 동일성 + git 픽스처 실행을 고정.

```bash
# >>> finalize-guard (shared by every release workflow; tests/release_level pins it)
if git rev-parse -q --verify "refs/tags/v$STABLE" >/dev/null; then
  echo "::error::v$STABLE already exists — a hotfix shipped this base. Re-promote staging with Release-Level: patch (or higher) before releasing." >&2
  exit 1
fi
# <<< finalize-guard
```

- cargo-release 는 `cargo release release` 가 버전을 정하므로, 그 전에 `Cargo.toml` 버전을 `bump_version.py finalize --current` 로 계산해 `STABLE` 을 만든 뒤 가드를 둠.
- PSR 은 `finalize_prerelease.py` 가 **파일을 쓰기 전에** 가드가 돌아야 함 → `finalize_prerelease.py --print-only` 추가(계산만, 기록 없음) 후 가드, 그다음 기존 호출.
- [ ] 테스트(픽스처: `v1.1.1` 태그 존재 + `STABLE=1.1.1` → exit ≠ 0 + `::error::`, 없음 → exit 0) → 실패 → 구현 → 통과 → mutation(`-q --verify` 조건 반전).

---

### Task 6b: hotfix 뒤 back-merge 절차

hotfix 는 `/release-commit` 을 거치지 않아 End state 의 back-merge 가 실행되지 않음. production 의 `chore(release)` 커밋이 integration·staging 에 없으면 다음 버전 계산과 finalize 가 어긋남.

**Files:** `skills/flow/SKILL.md`(hotfix 머지 단계), `rules/promotion.md` Back-merge 절, `rules/merge-strategy.md`(행 설명에 hotfix 포함), `docs/usage/promotion-and-release{,.ko}.md`

- `/flow` 의 hotfix → production 머지·push 뒤: release CI 완료 확인 → `release-commit` End state 와 같은 명령으로 production → integration(FF, 아니면 `--no-ff`), production → staging(`--ff-only`, 거부 시 skip 보고).
- 대기 rc 가 staging 에 있고 hotfix 가 그 base 를 출시했으면(Task 5b 조건) "staging 을 patch 이상으로 재승격" 을 안내.
- 비용: `skills/flow/SKILL.md` 본문 변경 → `evals/outcome_scores.json` 의 `flow` 항목 삭제, 재측정은 사용자 결정. `rules/risk-tiers.md` 는 건드리지 않음(주입 규칙 재측정 비용).
- [ ] `tests/skills`·`tests/docs` 통과, doc_style lint.

---

### Task 6: 스킬 · 규칙 · 문서

**Files:** `skills/release-commit/SKILL.md`, `skills/commit/SKILL.md`, `rules/promotion.md`, `rules/merge-strategy.md`, `docs/usage/promotion-and-release{,.ko}.md`, `docs/usage/daily-work{,.ko}.md`, `docs/usage/configuration{,.ko}.md`, `skills/flow-init/SKILL.md`·`skills/harness-authoring/references/tech-doc-guide.md`(trailer 언급 점검만)

- release-commit Step 0: 모든 템플릿이 trailer 를 읽음 → count 0 분기는 hand-written workflow 용으로만 남김.
- Step 1 앞: 재승격 판정(태그 목록 규칙 — 스킬도 `git tag --list` + `bump_version.py next` 로 미리 계산해 선택지 라벨에 버전을 붙임) → staging → integration back-merge.
- item 3: 대기 rc 없음 → **auto / patch / minor / major**, 있음 → **continue / patch / minor / major**(continue 권장, 강제 level 은 base 재상승 경고). 선택지 라벨 = 계산된 버전.
- item 7: 항상 명시 trailer(`Release-Level: <choice>`) — `auto` 포함. "count 0" 호스트만 trailer 없음.
- Never 절 "Re-promote without the trailer" 삭제·대체.
- commit Step 5 동일 반영. promotion.md 표는 이미 반영(작업 트리) — `auto` 행 추가. merge-strategy.md 행은 반영됨.
- `evals/outcome_scores.json` 에서 `release-commit`·`commit` 항목 삭제(본문 변경 → stale=fail).
- [ ] `doc_style_check.py --lint` 변경 파일, `tests/docs`·`tests/skills` 통과.

---

### Task 7: 전체 검증

- [ ] `uv run pytest -q` (Windows) + WSL 에서 `tests/release_level` · `tests/test_release_workflow.py`
- [ ] 6개 workflow 의 run 블록을 추출해 WSL `shellcheck`
- [ ] doc-sync → review(`general-purpose`, `VERDICT:` 줄) → commit(`feat(release): ...`)
