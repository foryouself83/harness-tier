# release-commit 스킬 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development
> (recommended) or superpowers:executing-plans to implement this plan task-by-task.
> Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 릴리스 승격 절차를 자율 발동하는 `release-commit` 스킬로 분리하고, 호스트의
bump 전달 방식을 실제 산출물(`.github/workflows/release.yml`)에서 읽게 만든다.

**Architecture:** 신규 스킬 1개가 승격 전체를 소유한다. `flow/SKILL.md` 의 Promotion
섹션(88줄)은 포인터 1문단으로 줄고, `description` 에서 승격 문구가 빠져 두 스킬의 경합이
사라진다. 모델 판별은 스크립트가 아니라 렌더된 워크플로에 grep 1회 — `_RELEASE_TEMPLATES`
와 템플릿이 이미 고정한 사실을 재유도하지 않는다.

**Tech Stack:** Markdown(SKILL.md · rules) · YAML(evals/cases.yaml) · pytest

**Spec:** [docs/superpowers/specs/2026-09-08-release-commit-skill-design.md](../specs/2026-09-08-release-commit-skill-design.md)

## Global Constraints

이 절의 값은 모든 태스크의 요구사항에 암묵적으로 포함된다.

- `SKILL.md` 는 **500줄 이하** (`tests/skills/test_frontmatter.py` `SKILL_LINE_CAP = 500`)
- `description` 은 **1024자 이하**이고 `\bUse (when|for)\b` 에 매치하거나 `MANDATORY` 로 시작
  (`DESCRIPTION_CAP = 1024`)
- **스킬 본문은 영어.** 한글은 `tests/skills/_helpers.py` 의
  `KOREAN_DATA_LITERAL_ALLOWLIST` 에 등록된 데이터 리터럴에서만 허용
- `allowed-tools` 규칙은 **하나하나가 스킬이 실제로 내는 명령과 매치**돼야 한다
  (`test_every_allowed_tools_rule_matches_a_command_the_skill_issues`)
- `allowed-tools` 규칙에 `/` 뒤의 `*` 금지 (`test_no_allowed_tools_rule_ends_in_a_path_glob`)
- `${CLAUDE_PLUGIN_ROOT}` 는 `allowed-tools` 에서 **치환되지 않는다**
- 스킬이 내는 `git commit`·`git merge` 는 **플래그를 리터럴로** 적어야 게이트가 읽는다
  (CLAUDE.md Invariant 7)
- `docs/superpowers/specs/`·`plans/` 는 한글, 그 외 저장소 산출물은 영어 (CLAUDE.md Conventions)
- 최종 커밋 type 은 **`feat`** — consumer-facing `skills/`·`rules/` 변경이라 `docs`/`chore`
  는 버전을 안 올려 소비자에게 전파되지 않는다

**커밋 전략**: 태스크마다 커밋하지 않는다. Task 1-5 는 편집만 하고 각자 자기 검증을 돌린다.
Task 6(doc-sync) · Task 7(review) · Task 8(단일 커밋) 이 게이트 순서다 — `review`·`doc-sync`
마커는 **어떤 편집에도 무효화**되므로(PostToolUse 훅) 통과는 고정점이어야 한다.

**티어 마커**: 이 저장소는 vway-kit 게이트를 쓴다. 경로는
`.claude/vway-kit/.vdev/tier` 이며 `dev:feature/release-commit-skill` 로 이미 기록돼 있다.
`.claude/harness-tier/.flow/` 는 **이 저장소에 존재하지 않는다** — 그 경로를 쓰면 자매
저장소 혼동이고, 이 작업이 고치려는 오류와 같은 계열이다.

---

## File Structure

| 파일 | 책임 | 태스크 |
|---|---|---|
| `tests/flow_init/test_render_versioning.py` | 릴리스 템플릿 불변식 (trailer 또는 auto-only, dispatch level 금지) | 1 |
| `skills/release-commit/SKILL.md` | 승격 절차 전체 (신규) | 2 |
| `skills/flow/SKILL.md` | Promotion 섹션 → 포인터, description 에서 승격 제거 | 3 |
| `rules/risk-tiers.md` | `/release-commit` 이름 2곳 | 3 |
| `tests/skills/test_gate_reachability.py` | `MUST_STILL_PROMPT` 에 release-commit | 4 |
| `tests/skills/_helpers.py` | 한글 트리거 데이터 리터럴 등록 | 2 |
| `evals/cases.yaml` | release-commit 항목 신규 + flow happy/negative 이동 | 5 |
| `evals/scores.json` | 측정 결과 (손으로 쓰지 않음) | 6 |

---

## Task 1: 릴리스 템플릿 불변식 테스트

이 계획에서 **유일한 실로직**이다. 0.3.1 을 깬 divergence(트레일러 모델 vs
`workflow_dispatch` 레벨)를 미래 템플릿이 조용히 재도입하는 것을 막는다.

**Files:**
- Modify: `tests/flow_init/test_render_versioning.py` (현재 106줄, 끝에 추가)

**Interfaces:**
- Consumes: `tests.flow_init._helpers.PLUGIN` (= 저장소 루트),
  `scripts.flow_init_setup._RELEASE_TEMPLATES` (dict: tool 이름 → 템플릿 상대 경로)
- Produces: 없음 (테스트 전용)

- [ ] **Step 1: 현재 사실을 측정해 두기**

먼저 지금 값이 무엇인지 눈으로 본다. 테스트가 이 값을 굳힌다.

```bash
uv run python -c "
from pathlib import Path
for f in sorted(Path('github').glob('release.*.workflow.example.yml')):
    t = f.read_text(encoding='utf-8')
    print(f.name, 'trailer' if 'Release-Level' in t else 'AUTO-ONLY',
          'DISPATCH' if 'workflow_dispatch' in t else '')
"
```

기대 출력 — 4개 `trailer`, `release.semantic-release.workflow.example.yml` 만
`AUTO-ONLY`, `DISPATCH` 는 **하나도 없음**.

- [ ] **Step 2: import 와 모듈 수준 헬퍼 추가**

파일 첫 줄은 현재 `from pathlib import Path` 이고 `from tests.flow_init._helpers import PLUGIN`
가 이미 있다. 그 아래에 붙인다. `parametrize` 가 collection 시점에 키를 필요로 하므로
`_RELEASE_TEMPLATES` 를 함수 안에서 import 하는 기존 스타일을 헬퍼로 감싼다.

```python
import pytest
import yaml


def _release_tools():
    from scripts.flow_init_setup import _RELEASE_TEMPLATES

    return sorted(_RELEASE_TEMPLATES)


# The one release template whose tool cannot be handed a level: Node semantic-release derives
# the bump from commit types and reads no trailer. Listed rather than detected — a new
# auto-only template has to be a decision, and an unlisted one fails the test below.
_AUTO_ONLY_TOOLS = {"semantic-release"}
```

- [ ] **Step 3: 테스트 2개 추가**

파일 맨 끝에 붙인다. 기존 `test_release_templates_source_files_exist` 가 이미
`_RELEASE_TEMPLATES` 를 순회하므로 같은 패턴이다.

```python
@pytest.mark.parametrize("tool", _release_tools())
def test_a_release_template_either_reads_the_trailer_or_is_declared_auto_only(tool: str):
    """0.3.1 shipped no release candidate because the promotion followed a sister plugin's
    `workflow_dispatch` level model while this repo's workflow reads a `Release-Level:` commit
    trailer. The two agree on `auto`, so six releases passed before a forced level broke it.

    `release-commit` greps the rendered workflow for the trailer and treats a miss as "the
    level cannot be forced". That reading is only safe while every template is one of the two
    known kinds, which is what this pins."""
    from scripts.flow_init_setup import _RELEASE_TEMPLATES

    body = (PLUGIN / _RELEASE_TEMPLATES[tool]).read_text(encoding="utf-8")
    reads_trailer = "Release-Level" in body
    if tool in _AUTO_ONLY_TOOLS:
        assert not reads_trailer, (
            f"{tool}: declared auto-only but the template now reads the Release-Level trailer "
            f"— drop it from _AUTO_ONLY_TOOLS so the skill stops telling users the level "
            f"cannot be forced here."
        )
    else:
        assert reads_trailer, (
            f"{tool}: reads no Release-Level trailer and is not in _AUTO_ONLY_TOOLS. "
            f"release-commit would silently report 'the level cannot be forced' for this "
            f"stack. Add the trailer to the template, or list the tool as auto-only."
        )


@pytest.mark.parametrize("tool", _release_tools())
def test_no_release_template_takes_the_bump_level_from_a_workflow_dispatch(tool: str):
    """The sister plugin vway-kit forces the level through `workflow_dispatch: inputs: level`.
    No template here does, and `release-commit` says so outright — a template that grew one
    would make that statement false while every existing test stayed green."""
    from scripts.flow_init_setup import _RELEASE_TEMPLATES

    body = (PLUGIN / _RELEASE_TEMPLATES[tool]).read_text(encoding="utf-8")
    # YAML 1.1 reads a bare `on` key as the boolean True, so ask for both spellings.
    doc = yaml.safe_load(body) or {}
    on = doc.get("on", doc.get(True)) or {}
    dispatch = (on.get("workflow_dispatch") or {}) if isinstance(on, dict) else {}
    inputs = (dispatch.get("inputs") or {}) if isinstance(dispatch, dict) else {}
    assert "level" not in inputs, (
        f"{tool}: takes a bump level from workflow_dispatch. release-commit states that no "
        f"template here does and never triggers one — update the skill before adding this."
    )
```

- [ ] **Step 4: 통과 확인**

```bash
uv run pytest tests/flow_init/test_render_versioning.py -v
```

기대: 실패 0. 기존 테스트에 더해 `_RELEASE_TEMPLATES` 항목 수 × 2 개가 새로 통과한다.
이 테스트는 현재 사실을 굳히는 characterization 테스트라 red 단계가 없다.

- [ ] **Step 5: 뮤테이션 1 — 트레일러를 없애면 무는가**

특성화 테스트는 통과부터 하므로, 무는지 증명하지 않으면 아무것도 검증하지 않은 것과 같다.
`sed -i` 를 쓰지 말고 Python 으로 read-modify-write 하며 **적용됐음을 assert** 한다
(CLAUDE.md "Mutation-test a fix"). `git checkout --` 는 트리가 더러우므로 쓰지 않는다.

```bash
uv run python -c "
import pathlib, shutil
p = pathlib.Path('github/release.jreleaser.workflow.example.yml')
shutil.copy(p, p.with_name(p.name + '.snapshot'))
t = p.read_text(encoding='utf-8')
old = 'Release-Level'
assert old in t, 'mutation target missing — the template moved'
p.write_text(t.replace(old, 'Release-Lvl'), encoding='utf-8')
print('mutation applied')
"
uv run pytest tests/flow_init/test_render_versioning.py -k trailer -q
```

기대: **FAIL** — `jreleaser: reads no Release-Level trailer and is not in _AUTO_ONLY_TOOLS`.

- [ ] **Step 6: 복원 + 바이트 동일 검증**

```bash
uv run python -c "
import pathlib, shutil
p = pathlib.Path('github/release.jreleaser.workflow.example.yml')
s = p.with_name(p.name + '.snapshot')
shutil.copy(s, p); s.unlink()
"
git diff --stat github/
```

기대: `git diff --stat github/` 가 **빈 출력**. 아니면 복원이 실패한 것이니 멈춘다.

- [ ] **Step 7: 뮤테이션 2 — dispatch level 을 심으면 무는가**

```bash
uv run python -c "
import pathlib, shutil
p = pathlib.Path('github/release.gitversion.workflow.example.yml')
shutil.copy(p, p.with_name(p.name + '.snapshot'))
t = p.read_text(encoding='utf-8')
old = 'on:\n'
assert old in t, 'mutation target missing'
new = 'on:\n  workflow_dispatch:\n    inputs:\n      level:\n        type: string\n'
p.write_text(t.replace(old, new, 1), encoding='utf-8')
print('mutation applied')
"
uv run pytest tests/flow_init/test_render_versioning.py -k workflow_dispatch -q
```

기대: **FAIL** — `gitversion: takes a bump level from workflow_dispatch`.

- [ ] **Step 8: 복원 + 회귀 확인**

```bash
uv run python -c "
import pathlib, shutil
p = pathlib.Path('github/release.gitversion.workflow.example.yml')
s = p.with_name(p.name + '.snapshot')
shutil.copy(s, p); s.unlink()
"
git diff --stat github/
uv run pytest tests/flow_init/ -q
```

기대: `git diff --stat github/` 빈 출력, `tests/flow_init/` 전부 통과.

---

## Task 2: `skills/release-commit/SKILL.md` 작성

**Files:**
- Create: `skills/release-commit/SKILL.md`
- Modify: `tests/skills/_helpers.py` (`KOREAN_DATA_LITERAL_ALLOWLIST`)

**Interfaces:**
- Consumes: Task 1 이 굳힌 사실 — 템플릿은 trailer 아니면 auto-only, dispatch level 은 없음
- Produces: `/release-commit` 이라는 이름. Task 3 의 `flow/SKILL.md` 포인터와
  `rules/risk-tiers.md` 가 이 이름을 그대로 쓴다. Task 5 의 `evals/cases.yaml` 키도 같다.
  본문이 내는 `git merge --no-ff origin/<staging>` 문자열을 Task 4 의 probe 가 참조한다.

- [ ] **Step 1: frontmatter 작성**

```yaml
---
name: release-commit
description: >-
  Use when promoting integration to staging or staging to production, cutting a release
  candidate, or finalizing a release — including bare asks like "stage로 올려줘", "릴리즈 해",
  "main 승격", "promote to main", "cut an rc". Reads the host's rendered
  .github/workflows/release.yml to learn whether the bump level can be forced, then runs the
  promotion's gates, commit and merge in the order the release CI requires. Also use when a
  promotion produced no release candidate and you need to know why.
argument-hint: "[staging | release]"
# Every rule below matches a command spelled out in the body — a rule matching nothing grants
# nothing (tests/skills/test_gate_reachability.py). Exact marker paths, no trailing glob: a
# glob's `*` crosses path separators including `..`. `git commit` and `git merge` are
# deliberately absent — the commit prompt is the mechanical backstop behind the gate, and this
# skill's whole subject is which merge shape the release CI needs.
allowed-tools: Bash(grep -c Release-Level .github/workflows/release.yml) Bash(git fetch origin) Bash(mkdir -p .claude/harness-tier/.flow) Bash(touch .claude/harness-tier/.flow/review.done) Bash(touch .claude/harness-tier/.flow/bump.done) Bash(touch .claude/harness-tier/.flow/security.done)
---
```

description 의 한글 트리거는 **데이터 리터럴**이다 — Step 5 에서 등록해야
`tests/skills/test_links_and_language.py` 를 통과한다.

- [ ] **Step 2: Step 0 (모델 판별) 본문**

````markdown
## Step 0 — Read the host's release model

The bump level reaches CI one of two ways, and the wrong assumption cuts no release candidate
at all. Ask the rendered workflow, not a template list:

```bash
grep -c Release-Level .github/workflows/release.yml
```

**`grep -c` exits 1 on zero matches.** That non-zero exit is the answer "no trailer", not a
failure — do not report it as an error.

- **count >= 1** — the level can be forced. The staging commit carries
  `Release-Level: <level>` and CI forces the bump.
- **count 0** — Node `semantic-release`. The level **cannot** be forced; the bump comes from
  the commit types alone. Say so and skip the level question.
- **no such file** — no release CI is installed. Stop and tell the user to run `/flow-init`.

Whether the file was rendered from a template is not the question — a hand-written
`release.yml` gets the same answer from the same grep, because the subject is the artifact
that actually runs.

**Cross-check the host commit guide.** `flow-config.commit_guide` (ships as
`docs/operations/commit-versioning-guide.md`) already records which kind the host is on. Read
it when it exists. If it disagrees with the grep, **the workflow wins** — and report the
disagreement in one line, because it means the guide has gone stale. No guide is a normal
answer, not a failure.

**No workflow here takes the level from a `workflow_dispatch`.** The sister plugin vway-kit
does; this one does not. Never trigger one to force a level — it forces nothing and the
promotion silently produces no rc.
````

- [ ] **Step 3: Staging / Release / PR 모드 / 종료 상태 / 실패 모드 본문**

`skills/flow/SKILL.md` 의 Promotion 섹션(195-283행)을 옮겨오되 스펙 §4-2 의 순서를 따른다.
아래를 **전부** 담아야 한다.

Staging (integration → staging):
1. 회귀 `review` — 독립 `general-purpose` 에이전트. `git fetch origin` 후 이 승격의 쌍으로
   파일 목록: `git diff --name-only "origin/<staging>..origin/<integration>"`.
   fetch 한 `origin/` 참조를 쓴다 — stale 로컬 참조는 검토 집합을 줄인다.
2. 추천 레벨 계산. 근거 2개: (a) 커밋 타입 파생값, (b) 호스트 커밋 가이드의 0.x 정책
   (`major_on_zero=false`, 1.0.0 은 명시적 결정으로만). 가이드가 없으면 (a)만.
3. `AskUserQuestion` major/minor/patch — 기본값은 추천값이지만 **질문은 항상 한다**.
   0.x 에서 `major` 를 고르면 1.0.0 으로 점프한다고 경고한다.
4. `check-token-write.sh` best-effort 경고 (exit 10 → 안내, exit 20/도구 없음 → 조용히 skip,
   절대 차단하지 않음).
5. 마커 2개를 **각각 한 줄씩** 적는다 — 중괄호 형태는 allowed-tools 규칙과 매치되지 않고
   무엇이 실행되는지도 안 읽힌다:
   ```bash
   touch .claude/harness-tier/.flow/review.done
   touch .claude/harness-tier/.flow/bump.done
   ```
6. **먼저 병합한다**: `git merge --no-ff --no-commit origin/<integration>`.
7. `Skill: commit` 에 **레벨을 인자로** 넘겨 그 머지 커밋을 쓴다 — `bump.done` 은 빈 마커라
   디스크의 무엇도 레벨을 싣지 않는다. 트레일러 `Release-Level: <level>` 이 붙고, subject 는
   risk-tiers 의 `Merge <integration>: <headline>` 형식이다.
   **순서가 뒤바뀌면 트레일러를 잃는다** — CI 는 `git log -1 --pretty=%B` 로 HEAD 하나만 읽으므로
   (`release.yml:81`), 커밋 후 병합하면 HEAD 가 머지 커밋이 되어 트레일러가 안 보인다.
   실측: 이 저장소의 `Release-Level:` 트레일러는 전부 머지 커밋에 있다.

Release (staging → production):
1. `git fetch origin` 선행. staging 이 `X.Y.Z-rc.N` 에 있는지 확인한다 — 이르게 병합하면
   finalize 가 pending rc 를 못 보고 평범한 계산으로 되돌아가 레벨 override 를 잃는다.
2. 회귀 `review` — **자체** 쌍 `git diff --name-only "origin/<production>..origin/<staging>"`.
   Staging 의 쌍을 재사용하면 실패가 조용하다: staging 은 rc bump 만큼 integration 보다
   앞서 있어 그럴듯한 릴리스 배관 몇 개를 돌려주고 실질 변경을 전부 가린다.
3. `/code-review` ultra + `/security-review` → `touch .claude/harness-tier/.flow/security.done`
4. `git merge --no-ff --no-commit origin/<staging>`.
5. `Skill: commit` — **레벨 없음**. finalize 는 결정적이다. 병합이 먼저인 이유는 Staging 과 같다.

PR 모드 (`merge_workflow.pull_request` 가 `promotion` 포함):
- 게이트 기록은 동일. 대상 브랜치 직접 커밋 대신 PR 을 연다.
- **반드시 머지 커밋** — rebase 는 릴리스를 멈추고 squash 는 히스토리를 파괴한다.
- 레벨 강제 시 병합 명령에 트레일러를 박는다. `PR` 은 리터럴 숫자다 — `<n>` 을 쓰면 bash 가
  `<n` 을 리다이렉션으로 읽고 다음 단어를 먹는다.
- `hotfix/*` → production 도 이 모드에서는 PR 이다.

`wiki` 게이트가 승격 커밋을 막을 때:
- `doc-sync` 는 승격 게이트가 아니라 `graph.yaml` 을 재빌드하는 유일한 주체가 없다. 터미널
  커밋으로 들어온 graph 드리프트가 여기서 처음 드러난다.
- `wiki_graph.py --build` 후 재생성된 `graph.yaml` 을 승격 커밋에 스테이징한다.
- 구조 위반(`wiki_id` 형식·중복 · `title` 누락 · 매달린 `depends_on` · 순환 · `wiki_id` 를
  달고 파싱 실패한 front matter)은 `--build` 로 안 고쳐지고 front matter 를 고쳐야 한다.

종료 상태:
- production → integration back-merge **필수**: `git fetch origin` 후
  `git merge --ff-only origin/<production>`, 안 되면 `--no-ff`. 빠뜨리면 릴리스된 태그가
  integration 에서 도달 불가가 되어 다음 버전이 잘못 계산된다.
- **staging 은 back-merge 하지 않는다** — 다음 integration → staging 승격이 릴리스 커밋을
  스스로 실어 나른다. 이것이 그 행이 `--no-ff` 로 강제되는 이유다.
- 승격 증거 마커를 지운다: `review.done` · `bump.done` · `security.done`.

실패 모드 (전부 이 저장소에서 0.3.1 때 실제로 일어난 일):
1. 승격 병합에 `[skip ci]` → 릴리스 job 자체가 안 돌아 rc 가 없다. **근본 원인.**
2. fetch 안 한 로컬 staging 병합 → finalize 가 pending rc 를 못 봄 → 버전 오산.
3. production → integration back-merge 누락 → 태그 도달 불가 → 다음 버전 오산.
4. staging 을 머지 커밋으로 back-merge → 문서가 금지한다.
5. `finalize_prerelease.py` 는 **파일을 쓴다** — `pyproject.toml` 과
   `.claude-plugin/plugin.json` 둘뿐이다(`uv.lock` 은 CI 의 별도
   `chore(release): sync uv.lock` 이 쓴다). 읽기 전용이 아니다. 로컬에서 돌리지 않는다.
6. 승격 후 증거 마커 미정리 → 다음 승격이 남의 `bump.done`·`security.done` 을 자기 통과
   증거로 읽는다.

모노레포 / 멀티 서비스 (1문장, 스펙 §4-3):
- 승격은 **저장소 전체를 한 버전으로** 올린다. 멀티 모듈은 게이트·테스트·배포에서 1급이지만
  (`modules[]` · `unit_test.jobs[]` · 타깃별 `deploy-<name>.yml`) `versioning` 블록은 단수라
  서비스별 독립 버전을 표현할 슬롯이 없다. 백엔드+프론트 한 저장소는 lockstep 버전 +
  타깃별 배포로 정상 동작한다.
- `versioning.version_files` 를 근거로 삼지 않는다 — **어떤 스크립트도 워크플로도 읽지 않는
  슬롯**이고, 파일에 버전을 실제로 찍는 것은 릴리스 tool 자체 설정이다.

Never:
- 레벨을 `workflow_dispatch` 로 강제하지 않는다 — 읽는 워크플로가 없다.
- 승격 병합에 `[skip ci]` 를 붙이지 않는다.
- **재승격은 트레일러 없이.** `version --<level>` 은 base 를 매번 올려
  `X.Y.Z-rc.1` → `X.Y.(Z+1)-rc.1` 이 되고 `X.Y.Z` 를 stable 로 건너뛴다. 같은 목표 버전에서
  rc 를 이어가려면 트레일러를 빼고 auto-derive 경로에 맡긴다.

`git merge` 는 플래그를 **리터럴로** 적는다. 변수를 플래그 자리에 두면 게이트가 병합으로
읽지 못해 merge-strategy 강제가 통째로 꺼진다 (CLAUDE.md Invariant 7).

- [ ] **Step 4: 줄 수 확인**

```bash
wc -l skills/release-commit/SKILL.md
```

기대: **500 이하**. 넘으면 실패 모드 설명을 줄인다 — 절차 단계는 줄이지 않는다.

- [ ] **Step 5: 한글 데이터 리터럴 등록**

먼저 현재 형태를 읽는다. 키와 값의 모양을 지어내지 않는다.

```bash
uv run python -c "
from tests.skills._helpers import KOREAN_DATA_LITERAL_ALLOWLIST as A
for k, v in A.items(): print(repr(k), '->', v)
"
```

그 형태에 맞춰 `tests/skills/_helpers.py` 에 `skills/release-commit/SKILL.md` 항목을
추가한다. 값은 description 에 실제로 쓴 한글 트리거 문자열 그대로다
(`stage로 올려줘` · `릴리즈 해` · `main 승격`).

- [ ] **Step 6: 스킬 테스트 통과 확인**

```bash
uv run pytest tests/skills/ -q
```

기대: 전부 통과. 실패 시 메시지가 어느 불변식인지 지목한다 — `allowed-tools` 규칙이 명령과
매치 안 됨 / 줄 수 초과 / description 형식 / 한글 본문 / git 명령이 게이트 문법에 안 읽힘.

- [ ] **Step 7: description 제약 기계 확인**

```bash
uv run python -c "
import re, pathlib, yaml
t = pathlib.Path('skills/release-commit/SKILL.md').read_text(encoding='utf-8')
fm = yaml.safe_load(t.split('---')[1])
d = fm['description']
print('len', len(d), '<= 1024:', len(d) <= 1024)
print('form:', bool(re.search(r'\bUse (when|for)\b', d)) or d.startswith('MANDATORY'))
"
```

기대: 둘 다 `True`.

---

## Task 3: `flow/SKILL.md` 축소 + `risk-tiers.md` 이름

두 파일이 한 태스크인 이유: `flow` 의 포인터가 `reached_programmatically` 의 근거이고,
`risk-tiers` 의 이름이 `hook_assisted` 의 근거다. 하나만 하면 Task 5 의 evals 테스트가
반대 방향으로 실패한다.

**Files:**
- Modify: `skills/flow/SKILL.md` (frontmatter `description` · 195-283행 Promotion 섹션)
- Modify: `rules/risk-tiers.md:12-13`, `rules/risk-tiers.md:175`

**Interfaces:**
- Consumes: Task 2 의 스킬 이름 `release-commit` 과 파일 `skills/release-commit/SKILL.md`
- Produces: injected 텍스트에 `/release-commit` 문자열 존재. Task 5 의 `hook_assisted: true`
  가 이것에 의존한다. `flow/SKILL.md` 가 `release-commit` 을 참조한다는 사실은 Task 5 의
  `reached_programmatically` 근거다.

- [ ] **Step 1: `flow/SKILL.md` description 에서 승격 문구 제거**

현재 마지막 문장이 `Also applies when promoting integration→staging or staging→production.`
이다. 이 문장이 남으면 두 스킬이 같은 프롬프트를 두고 경합한다 — 이 계획이 제거하는 중복의
핵심이다. 그 문장만 지우고 나머지 문장은 건드리지 않는다.

- [ ] **Step 2: Promotion 섹션을 포인터로 교체**

195-283행 전체(`## Promotion —` 부터 `## Phase 4 — Finalize` 직전까지)를 아래로 바꾼다.

```markdown
## Promotion — Staging (integration → staging) / Release (staging → production)

Promotions are gated at the **commit on the target branch**, so they need no tier marker —
the branch drives it. The procedure itself lives in
[`release-commit`](../release-commit/SKILL.md): which bump-level mechanism the host's release
CI is on, the gates and their markers, the merge shape each promotion takes, and the end state
the three branches settle into. Invoke `Skill: release-commit` rather than restating any of it
here — one fact, one place.
```

- [ ] **Step 3: 줄 수·링크 확인**

```bash
wc -l skills/flow/SKILL.md
uv run pytest tests/skills/ -q
```

기대: `flow/SKILL.md` 가 약 250줄로 줄고, 링크 테스트 통과
(`../release-commit/SKILL.md` 가 Task 2 에서 실제로 생성돼 있어야 한다).

- [ ] **Step 4: `risk-tiers.md` 175행 수정**

현재: ``Staging also **forces a human bump-level choice**: `/flow` asks major/minor/patch``
→ `/flow` 를 `/release-commit` 으로 바꾼다. 나머지 문장은 그대로 둔다 — 정책(기본값 =
커밋 파생, 항상 질문)은 변경 대상이 아니다.

- [ ] **Step 5: `risk-tiers.md` 12-13행 SSOT 위임 목록에 추가**

현재: ``[`/flow`](../skills/flow/SKILL.md) and [`flow-tiers.yaml`](../flow-tiers.yaml) both
defer to it``. 여기에 `/release-commit` 을 추가한다.

- [ ] **Step 6: 주입 텍스트에서 이름이 잡히는지 기계로 확인**

`hook_assisted` 검사는 정확히 이 정규식을 쓴다. 눈으로 보지 말고 돌린다.

```bash
uv run python -c "
import re, pathlib
t = '\n'.join(pathlib.Path(p).read_text(encoding='utf-8')
              for p in ('hooks/inject-risk-tiers.sh', 'rules/risk-tiers.md'))
print('found:', bool(re.search(r'/release-commit(?![\w-])', t)))
"
```

기대: `found: True`. `False` 면 이름 뒤에 단어문자나 하이픈이 붙어 있는 것이다.

- [ ] **Step 7: rules 의 git 명령이 게이트에 읽히는지 확인**

`risk-tiers.md` 는 매 세션 주입되므로 거기 적힌 `git merge` 도 검사 대상이다.

```bash
uv run pytest tests/skills/test_gate_reachability.py -q
```

기대: 통과.

---

## Task 4: `MUST_STILL_PROMPT` 에 release-commit 추가

`git merge` 가 `allowed-tools` 로 사전 승인되지 않았음을 주석이 아니라 **검사**로 만든다.
이 스킬의 주제가 병합이므로 그 구멍이 가장 비싸다.

**Files:**
- Modify: `tests/skills/test_gate_reachability.py` (`MUST_STILL_PROMPT` 딕셔너리)

**Interfaces:**
- Consumes: Task 2 의 `skills/release-commit/SKILL.md` 본문에 실제로 존재하는 merge 명령
- Produces: 없음 (테스트 전용)

- [ ] **Step 1: 스킬이 실제로 내는 merge 명령을 확인**

probe 는 스킬 본문의 실제 문구를 따라가야 한다 —
`test_must_still_prompt_literals_track_the_skill_text` 가 probe 의 **앞 두 토큰**으로
시작하는 명령이 본문에 있는지 역검증한다. 지어내면 stale 로 실패한다.

```bash
uv run python -c "
from pathlib import Path
from tests.skills.test_gate_reachability import issued_commands
for c in issued_commands(Path('skills/release-commit/SKILL.md')):
    if c.startswith('git merge'): print(repr(c))
"
```

- [ ] **Step 2: 항목 추가**

`MUST_STILL_PROMPT` 에 넣는다. 값은 Step 1 이 출력한 문자열 중 하나를 **그대로** 쓴다.

```python
    # This skill's whole subject is which merge shape the release CI needs, so a rule
    # pre-approving the merge is the most expensive hole it could carry.
    "release-commit": ["git merge --no-ff origin/<staging>"],
```

- [ ] **Step 3: 두 검사 통과 확인**

```bash
uv run pytest tests/skills/test_gate_reachability.py -q
```

기대: 통과. `test_allowed_tools_never_grants_a_command_the_user_should_decide` 가
release-commit 의 `allowed-tools` 에 그 merge 를 허가하는 규칙이 없음을 확인하고,
`test_must_still_prompt_literals_track_the_skill_text` 가 probe 가 본문을 따라감을 확인한다.

- [ ] **Step 4: 뮤테이션으로 무는지 증명**

`allowed-tools` 에 merge 규칙을 일시 추가해 첫 검사가 실패하는지 본다.

```bash
uv run python -c "
import pathlib
p = pathlib.Path('skills/release-commit/SKILL.md')
p.with_name(p.name + '.snapshot').write_text(p.read_text(encoding='utf-8'), encoding='utf-8')
t = p.read_text(encoding='utf-8')
old = 'allowed-tools: Bash(grep -c Release-Level'
assert old in t, 'frontmatter moved'
p.write_text(t.replace(old, 'allowed-tools: Bash(git merge *) Bash(grep -c Release-Level', 1), encoding='utf-8')
print('mutation applied')
"
uv run pytest tests/skills/test_gate_reachability.py -k never_grants -q
```

기대: **FAIL** — `release-commit: Bash(git merge *) pre-approves ...`.

- [ ] **Step 5: 복원 + 회귀 확인**

```bash
uv run python -c "
import pathlib
p = pathlib.Path('skills/release-commit/SKILL.md')
s = p.with_name(p.name + '.snapshot')
p.write_text(s.read_text(encoding='utf-8'), encoding='utf-8'); s.unlink()
"
git status --short skills/
uv run pytest tests/skills/ -q
```

기대: `.snapshot` 파일이 남지 않고, `tests/skills/` 전부 통과.

---

## Task 5: `evals/cases.yaml` — 신규 항목 + flow 케이스 이동

**Files:**
- Modify: `evals/cases.yaml` (`flow:` 항목 124-172행 · 파일 끝에 새 `release-commit:` 항목)

**Interfaces:**
- Consumes: Task 2 의 스킬 이름, Task 3 이 심은 `/release-commit` 문자열과 flow 의 포인터
- Produces: `CASES["skills"]["release-commit"]` — Task 6 의 측정 대상

- [ ] **Step 1: flow 의 승격 케이스를 negative 로 옮긴다**

`flow:` 의 `happy:` 에서 아래 두 줄을 제거한다.

```yaml
      - prompt: Promote dev to stage.
        golden_tier: staging
```

같은 항목의 `negative:` 리스트 맨 앞에 주석과 함께 넣는다.

```yaml
      # release-commit's happy case. flow taking it is now the failure mode: the promotion
      # procedure — which merge shape, which bump mechanism, which end state — lives there.
      - Promote dev to stage.
```

- [ ] **Step 2: `release-commit:` 항목 추가**

`commit:` 항목 뒤(파일 끝)에 붙인다. `commit` 항목의 형태를 따른다.

```yaml
  release-commit:
    # Reached two ways. flow's Promotion pointer invokes it (reached_programmatically), and a
    # user saying "릴리즈 해" reaches it directly — that autonomous arm is why the skill exists
    # at all, so unlike `commit` this one carries a specialist's expect_invoke rather than a
    # liveness check.
    #
    # hook_assisted because rules/risk-tiers.md, injected into every session, names
    # /release-commit as the promotion procedure. Its rate is therefore not comparable to the
    # unassisted skills, and the hook can hold it up while the description rots — read a
    # regression as description *and* hook.
    hook_assisted: true
    reached_programmatically: true
    invoked_by: flow/SKILL.md
    fixture: null
    expect_invoke: 0.70
    expect_why: >-
      the promotion procedure has exactly one right shape per host and the wrong one cuts no
      release at all; a skill that misses one promotion ask in three is not owning it.
    happy:
      - Promote dev to stage.
      - Merge stage into main and cut the release.
      - The promotion merged but no release candidate was created — why?
      - I need to re-promote stage to fold in one more fix. Does the trailer go on again?
      - Does this repo force the bump level with a commit trailer or a workflow dispatch?
    negative:
      # flow's happy case — routing a day-to-day change is not a promotion.
      - Commit these changes.
      # commit's happy case: authoring one message, not running a promotion.
      - What Conventional Commits type should this change get?
      # flow-init renders the release workflow; this skill only reads it.
      - Set up the release workflow for this project.
      - Show me the changelog for the last release.
      - Explain what a release candidate is.
```

- [ ] **Step 3: 모델 없이 도는 evals 테스트 통과 확인**

```bash
uv run pytest tests/evals/ -q
```

기대: 통과. 특히 `test_every_skill_the_injected_rule_names_declares_hook_assisted` 가
**양방향**으로 통과해야 한다 — Task 3 Step 6 이 `found: True` 였다면 통과한다.
`test_scores.py` 의 `reached_programmatically` 검사도 `flow/SKILL.md` 가 실제로
`release-commit` 을 참조하는지 확인한다.

- [ ] **Step 4: dry-run 으로 세션 수·소요 확인**

```bash
uv run python -m evals.run --dry-run --all
```

기대: 모델 호출 없이 세션 수와 예상 벽시계 시간이 출력된다. 목록에 `release-commit` 이
있는지 확인한다.

---

## Task 6: evals 측정 + doc-sync

**Files:**
- Modify: `evals/scores.json` (측정이 쓴다 — 손으로 편집하지 않는다)
- Modify: doc-sync 가 지목하는 문서들

**Interfaces:**
- Consumes: Task 5 의 `cases.yaml`
- Produces: `evals/scores.json` 의 `release-commit` 행, `flow` 행 갱신

- [ ] **Step 1: 측정**

`flow` 는 description 이 바뀌었으므로 자동으로 재측정 대상이고 `release-commit` 은 신규다.
인자 없이 돌리면 description 이 바뀐 스킬만 잰다.

```bash
uv run python -m evals.run
```

- [ ] **Step 2: 결과 판독**

```bash
uv run python -c "
import json
d = json.load(open('evals/scores.json', encoding='utf-8'))['skills']
for k in ('flow', 'release-commit'):
    e = d.get(k)
    print(k, e and (e['invoke_rate'], e['false_fire'], e['measured_at']))
"
```

판단 기준:
- `release-commit` 의 `invoke_rate` 가 `expect_invoke` 0.70 에 크게 못 미치면
  **description 을 고친다.** 숫자를 낮추지 않는다 — `expect_invoke` 는 설계 의도 선언이지
  측정값에 맞추는 값이 아니다 (`evals/scores.py` 의 해당 주석).
- `false_fire` 가 0 이 아니면 어느 negative 가 물었는지 보고 description 을 좁힌다.
- `flow` 의 `invoke_rate` 가 떨어졌으면 승격 문구 제거의 대가다. 값을 기록하고,
  `expect_invoke` 0.80 을 유의하게 밑돌면 flow 의 description 을 보강한다.

description 을 고쳤으면 Step 1 로 돌아가 다시 잰다.

- [ ] **Step 3: doc-sync 실행**

```
Skill: doc-sync
```

Mode A(코드→문서) · Mode B(문서 조화)를 돌린다. 이 저장소에는 wiki 가 없으므로 Mode W 는
스킵된다. 최소한 아래를 확인해야 한다:
- `CLAUDE.md` 의 Folder structure `skills/` 줄이 새 스킬을 반영하는가
- `USAGE.md` / `USAGE.ko.md` 가 승격 절차를 `/flow` 로 안내하고 있다면 `/release-commit`
  으로 고쳐야 하는가
- `README.md` / `README.ko.md` 의 스킬 목록

통과 후 마커:

```bash
mkdir -p .claude/vway-kit/.vdev
touch .claude/vway-kit/.vdev/doc-sync.done
```

- [ ] **Step 4: 전체 스위트 + 린트**

```bash
uv run pytest -q
uv run ruff check && uv run ruff format --check
uv run pre-commit run --all-files
```

기대: 전부 통과.

---

## Task 7: 도메인 리뷰

**Files:** 없음 (검증 전용)

**Interfaces:**
- Consumes: Task 1-6 의 전체 변경
- Produces: `.claude/vway-kit/.vdev/review.done`

- [ ] **Step 1: 변경 파일 목록을 git 에서 뽑는다**

```bash
git status --short
git diff --name-only HEAD
git ls-files --others --exclude-standard
```

- [ ] **Step 2: 독립 리뷰 에이전트 실행**

`general-purpose` 에이전트를 별도 컨텍스트로 띄운다. **모든** 변경 파일을 검토하고 개수를
보고하게 한다. `flow-config.review_checklist` 의 일반 항목에 더해, 이 작업에 고유한 것:

- `release-commit/SKILL.md` 의 절차가 `rules/risk-tiers.md` 의 Merge strategy 표와
  Back-merge 절과 **모순되지 않는가** (risk-tiers 가 SSOT, 스킬은 절차)
- `flow/SKILL.md` 에서 지운 88줄 중 **다른 어디에도 남지 않은 사실**이 있는가 — 특히
  PR 모드 승격, wiki 게이트 해소, 서로 다른 두 개의 diff 쌍, token-write 사전 경고
- Staging 과 Release 의 diff 쌍이 스킬 안에서 실제로 다른가 (같으면 잘못된 집합을 완전히
  검토하는 실패가 조용히 재발한다)
- `git merge` 플래그가 리터럴인가 (Invariant 7)
- 실패 모드 6개가 각각 이 저장소에서 실제로 일어난 일과 맞는가
- Task 1 의 `_AUTO_ONLY_TOOLS` 가 스킬 Step 0 의 문구와 일치하는가

통과 시:

```bash
touch .claude/vway-kit/.vdev/review.done
```

- [ ] **Step 3: 리뷰 이후 편집이 있었으면 마커를 다시 얻는다**

리뷰가 요구한 수정을 포함해 **모든 편집이 통과를 무효화한다**. PostToolUse 훅이
`review.done` 과 `doc-sync.done` 을 지운다. 훅이 못 본 편집(터미널 명령 등)이 있었다면
직접 지운다:

```bash
rm -f .claude/vway-kit/.vdev/review.done .claude/vway-kit/.vdev/doc-sync.done
```

그리고 Task 6 Step 3(doc-sync) → Task 7 Step 2(review) 순서로 다시 얻는다.

---

## Task 8: 단일 커밋

**Files:** 없음 (커밋 전용)

**Interfaces:**
- Consumes: Task 6·7 의 마커
- Produces: `feature/release-commit-skill` 위의 커밋 1개

- [ ] **Step 1: 게이트 상태 확인**

```bash
ls .claude/vway-kit/.vdev/
git status --short
```

기대: `tier` · `doc-sync.done` · `review.done`. `bump.done` 이나 `security.done` 이 있으면
지난 승격의 잔재다 — 이 커밋은 승격이 아니므로 지운다. `.snapshot` 파일이 남아 있으면
Task 1·4 의 복원이 덜 된 것이니 멈추고 복원한다.

- [ ] **Step 2: `commit` 스킬로 커밋**

```
Skill: commit
```

인자로 넘길 것: Tier DEV, 브랜치 `feature/release-commit-skill`, 단일 커밋,
**type `feat`** (consumer-facing `skills/`·`rules/` 변경이라 `docs`/`chore` 는 버전을 안
올려 소비자에게 전파되지 않는다), 본문은 짧은 `-` 불릿 한 줄씩, 산문·수정라운드 로그 금지.

변경 요약:
- `skills/release-commit/SKILL.md` 신규 — 승격 절차 전체, 호스트 릴리스 모델을 렌더된
  워크플로에서 grep 으로 판별
- `skills/flow/SKILL.md` — Promotion 섹션을 포인터로 축소, description 에서 승격 문구 제거
- `rules/risk-tiers.md` — SSOT 위임 목록과 bump 문장에 `/release-commit`
- `tests/flow_init/test_render_versioning.py` — 릴리스 템플릿 불변식 2건
- `tests/skills/test_gate_reachability.py` — `MUST_STILL_PROMPT` 에 release-commit
- `tests/skills/_helpers.py` — 한글 트리거 데이터 리터럴 등록
- `evals/cases.yaml` — release-commit 항목, flow 의 승격 케이스를 negative 로 이동
- `evals/scores.json` — flow · release-commit 재측정
- `docs/superpowers/specs·plans` 각 1개 신규 (내부 문서)

- [ ] **Step 3: 커밋 확인**

```bash
git log -1 --stat
```

기대: 위 파일들이 한 커밋에 들어가고 subject 가 50자 이하, 본문 각 줄이 72자 이하.

---

## 이후 (이 계획 밖)

- `dev` 병합 → 승격은 **이 계획이 만든 `release-commit` 스킬로** 수행한다. 첫 사용이 곧
  첫 검증이다.
- vway-kit 이식 — 자매 저장소, 별도 작업. 이식할 때 vway-kit 은 `workflow_dispatch` 모델
  이므로 Step 0 의 판별이 반대 답을 내야 정상이다.
