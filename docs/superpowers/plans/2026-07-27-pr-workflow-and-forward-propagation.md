# PR 워크플로 선택 + 순방향 전파 체인 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 릴리스 후 전파를 `dev → stage → main` 순방향 체인으로 정리하고(백머지는 `main → dev` 하나), PR 사용 여부를 `/flow-init` 시점의 host 설정 선택으로 빼낸다.

**Architecture:** 정책은 `flow-tiers.yaml`(플러그인 소유, 불변)에, 환경 선택은 `flow-config.yaml`(host 소유)에 둔다. PR 모드에서 사라지는 유일한 강제력인 머지 전략은 GitHub Ruleset 이 대신하며, 플러그인은 그 상태를 **읽어서 보고만** 한다(저장소 설정을 바꾸지 않는다). 커밋 규율(gitlint · 티어 게이트)은 커밋이 여전히 로컬이므로 두 모드에서 동일하게 유지된다.

**Tech Stack:** Python 3.12 + PyYAML (게이트 스크립트) · bash (보조 스크립트) · pytest · GitHub REST API `2022-11-28`

**설계 SSOT:** [`docs/superpowers/specs/2026-07-27-pr-workflow-and-forward-propagation-design.md`](../specs/2026-07-27-pr-workflow-and-forward-propagation-design.md)

## Global Constraints

- **SOURCE 만 수정한다.** `scripts/` · `flow-tiers.yaml` 은 SOURCE 이며, host 복사본(`.claude/harness-tier/`)은 절대 직접 편집하지 않는다.
- **소비자 대상 `.md`(`rules/`·`skills/`)는 `feat`/`fix` 커밋.** `docs`/`chore` 는 버전 범프를 트리거하지 않아 소비자에게 전파되지 않는다. `docs/superpowers/**` 만 `docs:` 로 둔다.
- **커밋 메시지는 50/72.** 제목 ≤50자, 본문 각 줄 ≤72자. 영어. 머지 커밋 제목은 대문자 `Merge` 로 시작.
- **`check-merge-ruleset.sh` 는 읽기 전용.** 어떤 경로에서도 쓰기 API(`POST`/`PUT`/`PATCH`/`DELETE`)를 호출하지 않는다.
- **FAIL-OPEN.** 새 보조 스크립트는 도구 부재·인증 없음·API 실패 어느 경우에도 `/flow-init` 을 중단시키지 않는다. 종료 코드 `0`=일치 / `10`=불일치 / `20`=판정 불가.
- **`merge_workflow.pull_request` 기본값은 `[]`.** `/flow-init` Step 2.5 가 example 블록을 verbatim 삽입하므로, example 의 값이 곧 기존 host 가 받는 값이다. `[]` 가 아니면 슬롯 백필만으로 팀 워크플로가 조용히 바뀐다.
- **Windows cp949 방어**(Invariant #2): 새 Python 코드의 파일 IO 는 `encoding="utf-8"` 명시.
- **GitHub REST 필드명은 공식 문서가 SSOT.** 이 계획에 적힌 값은 2026-07-27 기준 [docs.github.com/en/rest/repos/rules](https://docs.github.com/en/rest/repos/rules?apiVersion=2022-11-28) 에서 확인한 것이다: ruleset 최상위 `id`·`name`·`target`·`enforcement`·`conditions`·`rules`·`bypass_actors`, `conditions.ref_name.include`(문자열 배열), `pull_request` 규칙의 `parameters.allowed_merge_methods`(`merge`|`squash`|`rebase`), `bypass_actors[]`의 `actor_id`·`actor_type`(`Integration`|`OrganizationAdmin`|`RepositoryRole`|`Team`|`DeployKey`|`User`)·`bypass_mode`(`always`|`pull_request`|`exempt`).

---

## File Structure

| 파일 | 신규/수정 | 책임 |
|---|---|---|
| `flow-tiers.yaml` | 수정 | `integration → staging` merge_strategy 행 신설 (정책 SSOT) |
| `rules/risk-tiers.md` | 수정 | 머지 전략표 1행 · Back-merge 절 · PR workflow 절 · `direct merge` 2곳 (규율 SSOT) |
| `flow-config.example.yaml` | 수정 | `merge_workflow.pull_request` 슬롯 (환경 설정 템플릿) |
| `scripts/check-merge-ruleset.sh` | **신규** | ruleset 상태를 읽어 요구값과 대조하고 보고 (읽기 전용) |
| `skills/flow-init/SKILL.md` | 수정 | Step 1 슬롯 질문 · Step 2.7 ruleset 점검 |
| `skills/flow/SKILL.md` | 수정 | Phase 3 · Promotion 의 두 모드 분기 |
| `tests/test_flow_gate_check.py` | 수정 | 배포 정책 단언 + 러너 통합 차단 검증 |
| `tests/test_check_merge_ruleset.py` | **신규** | `--decode` 분기 + 쓰기 API 미호출 구조 단언 |

---

## Task 1: 순방향 전파 체인 — 정책 + 규율 문서

**Files:**
- Modify: `flow-tiers.yaml` (merge_strategy 목록)
- Modify: `rules/risk-tiers.md:355` (머지 전략표) · `:437-460` (Back-merge 절)
- Test: `tests/test_flow_gate_check.py`

**Interfaces:**
- Consumes: 없음 (첫 태스크)
- Produces: `flow-tiers.yaml` 의 `merge_strategy` 에 `{source: integration, target: staging, require: "--no-ff"}` 행. Task 3 의 risk-tiers.md PR workflow 절이 이 행을 "PR 모드에서는 발동하지 않는 규칙"으로 참조한다.

- [ ] **Step 1: 실패하는 정책 단언 테스트를 쓴다**

`tests/test_flow_gate_check.py` 의 `test_shipped_policy_staging_has_bump` (약 :698) **바로 아래**에 추가:

```python
def test_shipped_policy_integration_to_staging_requires_no_ff():
    # the shipped policy is the SSOT the gate reads. integration → staging must be a merge
    # commit: the rc self-heal (main → dev back-merge only) relies on the release commits
    # reaching staging through a descendant merge. A rebase promotion replays them under new
    # SHAs, so the stable tag leaves staging's ancestry and semantic-release miscomputes.
    import yaml

    root = Path(__file__).resolve().parent.parent
    data = yaml.safe_load((root / "flow-tiers.yaml").read_text(encoding="utf-8"))
    rows = [
        r
        for r in data["merge_strategy"]
        if r.get("source") == "integration" and r.get("target") == "staging"
    ]
    assert len(rows) == 1, "exactly one integration → staging rule"
    assert rows[0]["require"] == "--no-ff"
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/test_flow_gate_check.py::test_shipped_policy_integration_to_staging_requires_no_ff -v`
Expected: FAIL — `AssertionError: exactly one integration → staging rule` (행이 아직 없어 `rows == []`)

- [ ] **Step 3: 정책 행을 추가한다**

`flow-tiers.yaml` 의 `merge_strategy` 에서 `- source: staging` 행 **바로 앞**에 삽입 (흐름 순서대로 읽히도록):

```yaml
  - source: integration
    target: staging
    require: "--no-ff"
```

삽입 후 `merge_strategy` 전체는 다음과 같아야 한다:

```yaml
merge_strategy:
  - source: "feature/*"
    target: integration
    require: "--squash"
    warn_unless_rebased: true
  - source: "hotfix/*"
    target: production
    require: "--squash"
  - source: integration
    target: staging
    require: "--no-ff"
  - source: staging
    target: production
    require: "--no-ff"
  - source: "fix/*"
    target: integration
    forbid: "--no-ff"
```

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run pytest tests/test_flow_gate_check.py::test_shipped_policy_integration_to_staging_requires_no_ff -v`
Expected: PASS

- [ ] **Step 5: 러너 통합 차단 테스트를 쓴다**

같은 파일의 `test_runner_merge_gate_survives_clean_tree` (약 :510) **아래**에 추가. 이 테스트는 실제 배포되는 `flow-tiers.yaml` 을 도그푸딩한다(:503-506 주석 참조):

```python
@requires_bash_git
def test_runner_merge_gate_blocks_ff_promotion_to_staging(tmp_path: Path):
    # integration → staging must be a --no-ff merge. A bare `git merge <integration>` would
    # fast-forward and land staging's `[skip ci]` rc commit as HEAD, so release.yml's
    # `!contains(head_commit.message, '[skip ci]')` guard would skip the release entirely.
    main = tmp_path / "main"
    _init_repo(main)  # branch "main"
    _rg(["switch", "-c", "stage"], main)  # HEAD = staging branch → target resolves to staging
    cfg = main / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-config.yaml").write_text(
        "branches:\n  integration: dev\n  staging: stage\n  production: main\n",
        encoding="utf-8",
    )
    _rg(["add", "-A"], main)
    _rg(["commit", "-m", "cfg"], main)
    r = _run_runner(main, "git merge dev")  # missing the required --no-ff
    assert r.returncode == fgc.BLOCK_EXIT_CODE
    assert "--no-ff" in (r.stdout + r.stderr)
```

- [ ] **Step 6: 두 테스트를 함께 돌린다**

Run: `uv run pytest tests/test_flow_gate_check.py -v -k "integration_to_staging or ff_promotion"`
Expected: 둘 다 PASS

> 이 테스트가 이빨이 있는지 확인하려면 `flow-tiers.yaml` 의 새 행에서 `require: "--no-ff"` 줄을 잠시 지우고 다시 돌려 **둘 다 FAIL** 하는지 본 뒤 되돌린다. 지운 편집이 실제로 적용됐는지 먼저 확인할 것 — no-op 편집은 통과로 읽힌다.

- [ ] **Step 7: 머지 전략표를 고친다**

`rules/risk-tiers.md:355` 의 행을 교체.

기존:

```markdown
| integration → staging | **Rebase** or **Merge** | — |
```

신규:

```markdown
| integration → staging | **`--no-ff` Merge** | ✅ enforced |
```

이 수정으로 같은 파일 :423 의 "integration → staging makes a `--no-ff` merge commit" 과의 모순이 해소된다.

- [ ] **Step 8: Back-merge 절을 재작성한다**

`rules/risk-tiers.md` 의 `### Back-merge after release (production → integration)` 절(약 :437-460) 전체를 아래로 교체:

```markdown
### Back-merge after release (production → integration)

semantic-release writes the version bump (`plugin.json` / `pyproject`)
and the marketplace sha pin **only on `production`** (as `[skip ci]`
`chore(release)` commits). They never reach integration on their own,
so integration's `plugin.json` drifts to a stale version.

After every production release, **back-merge production → integration**
— one merge, nothing else:

```bash
git fetch origin
git switch <integration> && git merge --ff-only origin/<production>
git push origin <integration>
```

Fast-forward when the branch is strictly behind; else `--no-ff` Merge.
This one is **not optional**: without it the released tag is unreachable
from integration and semantic-release miscomputes the next version. It is
needed because Explicit-version gating forces the version into a
**committed file** (not a tag-only release, which would never drift).

**staging needs no back-merge** — the next `integration → staging`
promotion carries the release commits forward on its own. The chain is
`integration → staging → production`, and it closes: staging's rc bump
reaches production through the promotion merge, and production's release
commits reach integration through the back-merge above. staging therefore
stays an **ancestor of integration**, so the next promotion is a
descendant merge and the version file cannot conflict.

Measured 2026-07-27 (0.1.12): the 0.1.11 back-merge to staging was
skipped, so `v0.1.11` was **unreachable** from staging (nearest reachable
tag: `v0.1.11-rc.1`). The `integration → staging` merge pulled it into
ancestry and the rc came out correct — `0.1.12-rc.1`.

This holds **only because the promotion is a merge.** A rebase promotion
would replay the release commits under new SHAs, dropping the stable tag
out of staging's ancestry — which is why the Merge strategy table above
enforces `--no-ff` on that row.
```

- [ ] **Step 9: 전체 테스트 + 린트**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check`
Expected: 전부 통과

- [ ] **Step 10: 커밋**

```bash
git add flow-tiers.yaml rules/risk-tiers.md tests/test_flow_gate_check.py
git commit -m "fix(flow): make release propagation a forward-only chain" -m "- Back-merge to staging was redundant: the promotion merge
  carries the release commits, so staging stays an ancestor.
- Measured on 0.1.12 — the skipped 0.1.11 back-merge still
  produced a correct rc.
- Self-heal needs a merge, so integration -> staging is now
  --no-ff and gate-enforced."
```

---

## Task 2: `check-merge-ruleset.sh` — 읽기 전용 ruleset 점검

**Files:**
- Create: `scripts/check-merge-ruleset.sh`
- Test: `tests/test_check_merge_ruleset.py` (신규)

**Interfaces:**
- Consumes: Task 1 의 정책 (문서 참조만)
- Produces: `scripts/check-merge-ruleset.sh`. 호출 규약 두 가지 —
  `check-merge-ruleset.sh --decode <branch> <methods-csv>` (stdin 으로 ruleset 객체 **배열**을 받아 종료 코드만 반환) 와
  `check-merge-ruleset.sh <flow>...` (`daily`|`promotion`; `gh` 로 조회 후 보고).
  Task 3 의 `/flow-init` Step 2.7 이 후자를 호출한다.

- [ ] **Step 1: 실패하는 테스트를 쓴다**

`tests/test_check_merge_ruleset.py` 를 새로 만든다. `--decode` 는 stdin 만 읽으므로 **네트워크도 `gh` 스텁도 불필요**하다 (`test_check_token_write.py` 와 같은 구조):

```python
import json
import shutil
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check-merge-ruleset.sh"
# On Windows a bare "bash" resolves via System32 first (the WSL stub), which mangles
# backslash paths; shutil.which walks PATH in order and finds Git Bash. Same rationale as
# tests/test_check_token_write.py.
BASH = shutil.which("bash") or "bash"


def _ruleset(ref: str, methods: list[str] | None, enforcement: str = "active") -> dict:
    """One ruleset object as GET /repos/{o}/{r}/rulesets/{id} returns it."""
    rules = []
    if methods is not None:
        rules.append({"type": "pull_request", "parameters": {"allowed_merge_methods": methods}})
    return {
        "id": 1,
        "name": "x",
        "target": "branch",
        "enforcement": enforcement,
        "conditions": {"ref_name": {"include": [ref], "exclude": []}},
        "rules": rules,
    }


def _decode(sets: list[dict], branch: str, want: str) -> int:
    return subprocess.run(
        [BASH, str(SCRIPT), "--decode", branch, want],
        input=json.dumps(sets),
        text=True,
        capture_output=True,
    ).returncode


def test_exact_match_exits_0():
    assert _decode([_ruleset("refs/heads/stage", ["merge"])], "stage", "merge") == 0


def test_extra_method_allowed_exits_10():
    # allowing squash on a promotion branch is exactly the rebase/squash footgun we guard
    assert _decode([_ruleset("refs/heads/stage", ["merge", "squash"])], "stage", "merge") == 10


def test_missing_method_exits_10():
    assert _decode([_ruleset("refs/heads/dev", ["squash"])], "dev", "rebase,squash") == 10


def test_no_ruleset_for_branch_exits_10():
    assert _decode([_ruleset("refs/heads/other", ["merge"])], "stage", "merge") == 10


def test_empty_ruleset_list_exits_10():
    assert _decode([], "stage", "merge") == 10


def test_inactive_ruleset_is_ignored_exits_10():
    sets = [_ruleset("refs/heads/stage", ["merge"], enforcement="evaluate")]
    assert _decode(sets, "stage", "merge") == 10


def test_all_refs_wildcard_matches():
    assert _decode([_ruleset("~ALL", ["merge"])], "stage", "merge") == 0


def test_multiple_rulesets_intersect():
    # GitHub applies the intersection when several rulesets match the same ref
    sets = [
        _ruleset("refs/heads/dev", ["squash", "rebase", "merge"]),
        _ruleset("refs/heads/dev", ["squash", "rebase"]),
    ]
    assert _decode(sets, "dev", "rebase,squash") == 0


def test_malformed_json_exits_20():
    r = subprocess.run(
        [BASH, str(SCRIPT), "--decode", "stage", "merge"],
        input="{not json",
        text=True,
        capture_output=True,
    )
    assert r.returncode == 20


def test_script_never_calls_a_write_api():
    # The whole point of this script is that it reads. A method flag on a gh/curl call is the
    # only way it could write, so its absence is the structural guarantee.
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--method" not in text
    assert "-X " not in text
    for verb in ("POST", "PUT", "PATCH", "DELETE"):
        assert verb not in text
```

- [ ] **Step 2: 실패를 확인한다**

Run: `uv run pytest tests/test_check_merge_ruleset.py -v`
Expected: 전부 FAIL — 스크립트 파일이 없어 bash 가 `No such file or directory` 로 종료 (반환 코드 127)

- [ ] **Step 3: 스크립트를 구현한다**

`scripts/check-merge-ruleset.sh` 를 만든다:

```bash
#!/usr/bin/env bash
# Report whether the repo's GitHub rulesets match what flow-config.merge_workflow requires.
#
# READ-ONLY. It never creates or changes a ruleset — it reads, compares, and prints what to
# apply. Same posture as flow_init_setup.check_precommit (reports missing hooks instead of
# merging) and the workflow renderers (never overwrite). Applying a PR-required ruleset to a
# promotion branch is high blast radius — a missing bypass actor stops the release pipeline —
# so that decision stays with the repo owner.
#
# Usage:
#   check-merge-ruleset.sh <flow> [<flow>...]        # flow = daily | promotion
#   check-merge-ruleset.sh --decode <branch> <methods-csv>   # stdin = JSON array of rulesets
#
# Env: HARNESS_REPO (else GITHUB_REPOSITORY)
#      HARNESS_BRANCH_INTEGRATION / _STAGING / _PRODUCTION (else dev / stage / main)
# Exit: 0 matches | 10 differs (guidance printed) | 20 undetermined (no tool/repo/parse).
set -u

decode() {  # $1=branch $2=methods-csv; stdin=JSON array → 0 match / 10 differs / 20 unparsable
  command -v python3 >/dev/null 2>&1 || return 20
  python3 -c 'import json,sys
branch, want = sys.argv[1], set(sys.argv[2].split(","))
try:
    sets = json.load(sys.stdin)
except Exception:
    sys.exit(20)
ref = "refs/heads/" + branch
got = None
for rs in sets:
    if rs.get("enforcement") != "active":
        continue
    inc = ((rs.get("conditions") or {}).get("ref_name") or {}).get("include") or []
    if ref not in inc and "~ALL" not in inc:
        continue
    for rule in rs.get("rules") or []:
        if rule.get("type") != "pull_request":
            continue
        methods = (rule.get("parameters") or {}).get("allowed_merge_methods")
        if methods is None:
            continue
        # GitHub applies the INTERSECTION when several rulesets match the same ref.
        got = set(methods) if got is None else (got & set(methods))
sys.exit(0 if got == want else 10)' "$1" "$2"
}

guide() {  # $1=branch $2=methods-csv — printed on a mismatch; no command is executed
  echo "  [!] $1: allowed merge methods must be exactly: $2" >&2
  echo "      Settings -> Rules -> Rulesets -> New branch ruleset" >&2
  echo "      target ref: refs/heads/$1 | enforcement: active" >&2
  echo "      rule: Require a pull request before merging" >&2
  echo "            Allowed merge methods = $2" >&2
  echo "      docs: https://docs.github.com/en/rest/repos/rules" >&2
}

warn_bypass() {
  echo "  [!] promotion branches: add a BYPASS ACTOR for the release automation." >&2
  echo "      Without it, semantic-release's direct chore(release) push is blocked" >&2
  echo "      and every release stops. The actor is whoever pushes: the RELEASE_TOKEN" >&2
  echo "      owner/app if that secret is set, else the github-actions app." >&2
}

if [ "${1:-}" = "--decode" ]; then
  decode "${2:-}" "${3:-}"
  exit $?
fi

integration="${HARNESS_BRANCH_INTEGRATION:-dev}"
staging="${HARNESS_BRANCH_STAGING:-stage}"
production="${HARNESS_BRANCH_PRODUCTION:-main}"
repo="${HARNESS_REPO:-${GITHUB_REPOSITORY:-}}"

if [ -z "$repo" ] || ! command -v gh >/dev/null 2>&1 || ! command -v python3 >/dev/null 2>&1; then
  echo "  [=] gh/python3/repo unavailable — skipping ruleset check" >&2
  exit 20
fi

# Full ruleset objects: the list endpoint omits `rules`, so each id is fetched individually.
sets="$(
  ids="$(gh api "/repos/$repo/rulesets" --jq '.[].id' 2>/dev/null)" || exit 1
  printf '['
  first=1
  for id in $ids; do
    [ "$first" = 1 ] || printf ','
    first=0
    gh api "/repos/$repo/rulesets/$id" 2>/dev/null || exit 1
  done
  printf ']'
)" || { echo "  [=] could not read rulesets — skipping" >&2; exit 20; }

rc=0
for flow in "$@"; do
  case "$flow" in
    daily)
      # feature/* is Squash and fix/* is Rebase, so integration allows both and bars a
      # merge commit. Narrowing to squash alone would block the fix/* path.
      printf '%s' "$sets" | decode "$integration" "rebase,squash" || { guide "$integration" "rebase,squash"; rc=10; }
      ;;
    promotion)
      for b in "$staging" "$production"; do
        printf '%s' "$sets" | decode "$b" "merge" || { guide "$b" "merge"; rc=10; }
      done
      [ "$rc" = 10 ] && warn_bypass
      ;;
    *) echo "  [!] unknown flow: $flow" >&2 ;;
  esac
done
[ "$rc" = 0 ] && echo "  [=] merge rulesets match the required methods" >&2
exit "$rc"
```

- [ ] **Step 4: 통과를 확인한다**

Run: `uv run pytest tests/test_check_merge_ruleset.py -v`
Expected: 11개 전부 PASS

- [ ] **Step 5: ShellCheck 로 검증한다**

Run: `uv run pre-commit run --all-files`
Expected: 통과. (훅 런타임이 Windows 라 shell 버그는 FAIL-OPEN 으로 숨는다 — CLAUDE.md Invariants. `*.sh` 수정 시 ShellCheck 검증은 선택이 아니다.)

- [ ] **Step 6: 커밋**

```bash
git add scripts/check-merge-ruleset.sh tests/test_check_merge_ruleset.py
git commit -m "feat(flow): add a read-only merge-ruleset check" -m "- PR mode drops the local merge gate; a branch ruleset takes
  its place and covers every path, not just Claude sessions.
- Reports the gap and how to apply it; never writes. Applying
  one wrong stops releases, so the call stays with the owner."
```

---

## Task 3: PR 워크플로 선택 — 설정 슬롯 + 스킬 분기

**Files:**
- Modify: `flow-config.example.yaml` (`branches` 블록 뒤)
- Modify: `skills/flow-init/SKILL.md:130` (Step 1 2b 슬롯 목록) · `:259` 뒤 (Step 2.7 신설)
- Modify: `rules/risk-tiers.md` (PR workflow 절 신설 · `:225` · `:264`)
- Modify: `skills/flow/SKILL.md` (Docs/Dev 3단계 · Promotion 절)

**Interfaces:**
- Consumes: Task 2 의 `scripts/check-merge-ruleset.sh <flow>...` 호출 규약
- Produces: `flow-config.merge_workflow.pull_request` (리스트, 값 `daily`|`promotion`). `/flow` 가 이 키를 읽어 분기한다.

- [ ] **Step 1: 설정 슬롯을 추가한다**

`flow-config.example.yaml` 에서 `branches:` 블록 끝(`feature_prefix` 줄) **뒤**, `# Per-module pre-checks` 주석 **앞**에 삽입:

```yaml
# How work reaches its target branch. Only the flows listed here go through a PR; the rest
# stay direct merges. An empty list (the default) = all direct — the existing behaviour.
#   daily     — feature/* · fix/* → integration
#   promotion — integration → staging, staging → production
# A PR replaces the local `git merge`, so that flow's merge_strategy gate does not fire.
# Enforce the merge method server-side with a GitHub Ruleset instead — /flow-init reads the
# current state and reports what to apply (it never changes repo settings).
# Commit discipline (gitlint · tier gates) is unaffected: commits are still made locally.
# When promotions go through PRs the ruleset MUST carry a bypass actor for the release
# automation — without it the chore(release) push is blocked and releases stop.
merge_workflow:
  pull_request: []
```

> 슬롯 배관에는 코드 변경이 없다. `flow_init_setup._diff_missing`(:418-434)이 example↔host 를 재귀 비교하며 최상위 키 부재를 insertion unit 으로 기록하고, 그 테스트들은 합성 example 을 쓰므로(:490) 실제 슬롯 목록에 결합돼 있지 않다.

- [ ] **Step 2: 슬롯이 백필 대상으로 잡히는지 확인한다**

Run:

```bash
uv run python -c "
from pathlib import Path
import sys; sys.path.insert(0, 'scripts')
from flow_init_setup import _diff_missing, _load_yaml_safe
ex = _load_yaml_safe(Path('flow-config.example.yaml'))
print([s['label'] for s in _diff_missing(ex, {'branches': {}}, [])])
"
```

Expected: 출력 목록에 `merge_workflow` 가 포함된다.

- [ ] **Step 3: `/flow-init` Step 1 에 슬롯 질문을 추가한다**

`skills/flow-init/SKILL.md` 의 2b 목록에서 `- **branches**: …` 줄(:130) **바로 뒤**에 삽입:

```markdown
       - **merge_workflow**: `AskUserQuestion` (**multiSelect**) "Which flows go through a
         pull request?" — options `daily (feature/* · fix/* → integration)` and
         `promotion (integration → staging → production)`. Nothing selected →
         `pull_request: []` (all direct merges — the existing behaviour). The **promotion
         option's description MUST state**: a promotion PR merges only as "Create a merge
         commit" (a rebase leaves a `[skip ci]` rc commit as the head so the release never
         runs; a squash destroys the release history); a forced bump level needs the
         `Release-Level:` trailer in the merge commit body; and a ruleset without a
         release-automation bypass actor halts releases.
```

- [ ] **Step 4: Step 2.7 을 신설한다**

`skills/flow-init/SKILL.md` 의 `### Step 3 — Teams webhook URLs…`(:260) **바로 앞**에 삽입:

```markdown
### Step 2.7 — Merge ruleset check (PR mode only, skippable)

Runs only when `flow-config.merge_workflow.pull_request` is non-empty. Under PR mode the
local `git merge` disappears, so `flow-tiers.yaml`'s `merge_strategy` gate never fires — a
GitHub Ruleset has to carry that enforcement instead.

With the default branch names (`dev` / `stage` / `main`), run this as written. The trailing
arguments are the flows the user selected (`daily`, `promotion`, or both):

```bash
HARNESS_REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)" \
  bash "${PLUGIN}/scripts/check-merge-ruleset.sh" daily promotion
```

If `flow-config.branches` differs from the defaults, pass them explicitly. The block below
is a shape example — **substitute the three values from the config you just wrote** before
running it:

```bash
HARNESS_REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)" \
HARNESS_BRANCH_INTEGRATION=develop \
HARNESS_BRANCH_STAGING=qa \
HARNESS_BRANCH_PRODUCTION=master \
  bash "${PLUGIN}/scripts/check-merge-ruleset.sh" daily promotion
```

The script is **read-only** — it never changes repo settings. It reports the gap between the
current state and what is required, plus how to apply it (the same posture as
`check_precommit`, which reports missing hooks instead of merging them). Relay its output
**verbatim** and continue `/flow-init` on exit 10 (mismatch) and 20 (tool absent) alike.
On a re-run this step doubles as a drift check.
```

- [ ] **Step 5: risk-tiers.md 에 PR workflow 절을 신설한다**

`rules/risk-tiers.md` 의 `### Merging feature/* → integration (integration-test gate)` 절(:388) **바로 앞**에 삽입:

```markdown
### PR workflow (`flow-config.merge_workflow`)

Flows listed in `merge_workflow.pull_request` go through a **pull request** instead of a
local merge. An empty list (the default) means every flow is a direct merge and this
section does not apply.

| Value | Flows |
|---|---|
| `daily` | `feature/*` · `fix/*` → integration |
| `promotion` | integration → staging, staging → production |

**Commit discipline does not change.** Commits are still made locally under PR mode, so
gitlint (50/72 · Conventional Commits) and the tier gate (markers, unclassified block)
fire exactly as before. What moves is the **merge**, and only the merge.

The `require`/`forbid` cells in the Merge strategy table are enforced by a hook watching
`git merge`, so they **do not fire** for a flow that goes through a PR. A GitHub Ruleset
carries that enforcement instead, as allowed merge methods per branch:

| Target branch | Allowed merge methods | Source rows |
|---|---|---|
| integration | `squash` + `rebase` (no merge commit) | row 1 `feature/*`=Squash, row 2 `fix/*`=Rebase |
| staging · production | `merge` only | rows 3·4 = `--no-ff` Merge |

`/flow-init` Step 2.7 reads the current state and reports the gap; it does not change repo
settings.

> ⚠️ **Merge a promotion PR with "Create a merge commit" only.** The release workflow reads
> a single pushed **head commit** — it gates execution on `[skip ci]` and reads the
> `Release-Level:` trailer from that same message. A rebase-merge replays staging's commits
> and leaves `chore(release): … [skip ci]` as the head, so **the release never runs**; a
> squash destroys the individual release-commit history.

> ⚠️ **A promotion ruleset MUST carry a release-automation bypass actor.** Allowed merge
> methods hang off the "require a pull request before merging" rule, so applying it without
> a bypass blocks semantic-release's direct `chore(release)` version-bump push and **halts
> the release pipeline**.

With a forced bump level, pin the trailer in the merge command rather than typing it into
the web UI:

```bash
gh pr merge <n> --merge \
  --subject "Merge <staging>: release X.Y.Z" \
  --body "Release-Level: patch"
```

An automatic (commit-derived) level needs no trailer at all.
```

- [ ] **Step 6: `direct merge` 두 줄을 설정 참조로 바꾼다**

`rules/risk-tiers.md:225` — 기존:

```markdown
3. Commit (Conventional Commits, 50/72 rule — see Commit Discipline
   below) → direct merge.
```

신규:

```markdown
3. Commit (Conventional Commits, 50/72 rule — see Commit Discipline
   below) → merge per **Merge strategy**, or open a PR when
   `merge_workflow.pull_request` includes `daily` (see PR workflow).
```

`rules/risk-tiers.md:264` — 기존:

```markdown
3. Integration human gate (feature → integration branch; see Merge
   Strategy below) → commit → direct merge.
```

신규:

```markdown
3. Integration human gate (feature → integration branch; see Merge
   Strategy below) → commit → merge, or open a PR when
   `merge_workflow.pull_request` includes `daily` (see PR workflow).
```

- [ ] **Step 7: `/flow` 를 분기시킨다**

`skills/flow/SKILL.md` Docs 3단계(:127-130)의 `→ merge **applying the risk-tiers Merge strategy**` 와 Dev 3단계(:150-152)의 같은 표현 뒤에 각각 다음 문장을 덧붙인다:

```markdown
   When `flow-config.merge_workflow.pull_request` includes `daily`, open a **PR** instead
   of merging: rebase → integration-test human gate (unchanged) → push → `gh pr create` →
   hand over the PR URL and stop. Without `gh`, print the compare URL and let the user
   create it — never block.
```

Promotion 절 끝(`- **Back-merge after the production release…` 항목 **앞**)에 추가:

```markdown
- **PR-mode promotion** (`merge_workflow.pull_request` includes `promotion`) — gate
  recording is unchanged; instead of committing on the target branch, open a PR. It **must**
  be merged as a merge commit (a rebase stops the release, a squash destroys the history —
  [`risk-tiers.md`](../../rules/risk-tiers.md) PR workflow). With a forced bump level, pin
  the trailer in the merge command:

  ```bash
  gh pr merge <n> --merge --subject "Merge <staging>: release X.Y.Z" --body "Release-Level: <level>"
  ```
```

- [ ] **Step 8: Phase 4 정리 시점을 모드별로 나눈다**

`skills/flow/SKILL.md` 의 `## Phase 4 — Finalize` 절 첫 문단 끝에 추가:

```markdown
**Under PR mode, clear only after the PR is merged.** Markers are branch-bound, so a
review-feedback commit on the same branch needs its marker alive to pass the gate. Clearing
at PR-creation time leaves the follow-up commit unclassified and blocked.
```

- [ ] **Step 9: 스킬 파일 검증 + 전체 테스트**

Run: `uv run pytest tests/test_skills.py -v && uv run pytest -q && uv run ruff check`
Expected: 전부 통과. (`test_skills.py` 는 frontmatter · 내부 링크 · 참조 무결성을 검사하므로, 위에서 추가한 상대 링크가 깨졌다면 여기서 잡힌다.)

- [ ] **Step 10: 커밋**

```bash
git add flow-config.example.yaml skills/flow-init/SKILL.md skills/flow/SKILL.md rules/risk-tiers.md
git commit -m "feat(flow): make the PR workflow an init-time choice" -m "- Git culture varies per team; direct-merge was hardcoded.
- New merge_workflow.pull_request slot, default [] so an
  existing host keeps its behaviour on slot backfill.
- Commit rules are untouched: commits stay local, only the
  merge moves to the server."
```

---

## Task 4: 게이트 — doc-sync + 독립 리뷰

**Files:**
- Modify: doc-sync 가 지시하는 문서 (`CLAUDE.md` 등)
- Create: `.claude/harness-tier/.flow/doc-sync.done` · `review.done` (gitignored)

**Interfaces:**
- Consumes: Task 1-3 의 전체 변경집합
- Produces: dev 티어 게이트 증거. 이게 있어야 커밋 게이트가 열린다.

- [ ] **Step 1: doc-sync 스킬을 실행한다**

`doc-sync` 스킬을 Skill 도구로 호출한다. 이번 변경이 문서에 남긴 드리프트를 점검한다 —
특히 `CLAUDE.md` 의 "Three verification layers" 서술에 PR 모드의 강제 지점 이동을 반영할지,
`USAGE.md`/`README.md` 에 `merge_workflow` 슬롯을 노출할지.

- [ ] **Step 2: 통과 시 마커를 기록한다**

```bash
touch .claude/harness-tier/.flow/doc-sync.done
```

- [ ] **Step 3: 독립 리뷰 에이전트를 띄운다**

별도 컨텍스트의 `general-purpose` 에이전트로 `flow-config.review_checklist` 기준 리뷰.
이 변경집합에 특히 물어야 할 것:
- 새 `merge_strategy` 행이 기존 4개 행의 매칭을 바꾸지 않는가 (`match_merge_rule` 은 첫 매치를 반환)
- `check-merge-ruleset.sh` 가 어떤 경로로도 쓰기 API 를 호출하지 않는가
- `merge_workflow` 기본값 `[]` 가 기존 host 의 동작을 정말 바꾸지 않는가
- risk-tiers.md 안에서 `integration → staging` 머지 방식을 말하는 모든 문장이 일치하는가
- Invariants(FAIL-OPEN · cp949 · exit 2 · `if` 필드 부재 · 멱등성 · 워크트리) 위반이 없는가

- [ ] **Step 4: 통과 시 마커를 기록한다**

```bash
touch .claude/harness-tier/.flow/review.done
```

- [ ] **Step 5: 최종 검증**

Run: `uv run pytest -q && uv run ruff check && uv run ruff format --check && uv run pre-commit run --all-files`
Expected: 전부 통과

- [ ] **Step 6: doc-sync 가 문서를 고쳤다면 커밋한다**

```bash
git add -A
git commit -m "docs: sync docs for the PR workflow choice"
```

> 문서 변경이 **소비자 대상**(`rules/`·`skills/`)이면 `docs:` 가 아니라 `fix(flow):` 로
> 커밋해야 전파된다 (Global Constraints).

---

## 머지 (계획 범위 밖, `/flow` Phase 3.3)

`feature/*` → integration 은 3단계 게이트 흐름이다: **rebase → 통합테스트 human gate(사용자 확인 필수) → squash**. 이 브랜치의 커밋들은 카테고리별로 묶는다 — `feat(flow)` 하나, `fix(flow)` 하나, `docs` 하나(스펙·계획 문서).

```bash
git fetch origin
git rebase origin/dev
# 사용자에게 통합테스트 수행 여부를 묻고, 확인받은 뒤에만 진행
git switch dev
git pull --ff-only origin dev
git merge --squash feature/pr-choice-and-forward-propagation
```
