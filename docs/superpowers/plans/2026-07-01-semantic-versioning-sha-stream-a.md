# vway-kit 의미기반 버전 관리 (Stream A) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** vway-kit 자체 repo에 강결합(Explicit version) 릴리스 체계를 도입해 sha 대신 semantic 버전으로 배포·관리한다.

**Architecture:** plugin.json `version`이 업데이트를 게이팅(공식 권장). python-semantic-release가 main/stage push의 feat/fix를 파싱해 pyproject+plugin.json 버전을 bump하고 `vX.Y.Z` 태그를 만든다. marketplace `source`는 그 태그(`ref`)를 가리켜 소비자가 버전 단위로 업데이트를 받는다. 브랜치는 dev→stage→main.

**Tech Stack:** Python 3.12/uv, python-semantic-release v9, GitHub Actions, gitlint(기존), Claude Code plugin/marketplace manifest.

## Global Constraints

- 이 repo는 **플러그인 소스**다. 워크플로를 harness-init/vdev-init로 생성하지 않고 손으로 작성한다(이것이 Stream B의 참조 템플릿이 됨).
- 이중 경로 금지 위반 없음 — 모든 파일은 이 repo 내부(플러그인 소스 자체)에 쓴다.
- 커밋은 Conventional Commits + 50/72 (`.gitlint` 강제). 이 작업 전체는 `/vdev` **Dev** 티어.
- **gitlint B6 — 모든 로컬 커밋은 본문(body) 필수** (subject만 있으면 거부됨). 각 커밋은
  `git commit -m "<subject>" -m "<body>"` 또는 heredoc(`-F -`)으로 subject + 최소 1줄 본문(72자 wrap)을 쓴다.
  (봇 [skip ci] 커밋만 body 면제 — GITHUB_TOKEN push라 pre-commit 미경유.)
- 이 repo는 vdev 게이트(settings.json 훅)를 도그푸딩하지 않아 커밋이 게이트로 차단되진 않으나,
  gitlint(commit-msg)·ruff(pre-commit)는 활성. `--no-verify` 금지.
- 버전 SSOT 우선순위: plugin.json `version`(#1) > marketplace entry `version`(안 씀) > git SHA. **marketplace entry에 `version` 넣지 않는다.**
- **marketplace 핀 = 불변 `sha`만 사용**(가변 태그 `ref` 금지 — 공급망 무결성; 보안 리뷰 반영). version 게이팅은 plugin.json `version`이 담당하며 핀 방식과 독립. 핀은 릴리스 시점에 release.yml이 `pin-marketplace-sha.py`로 수행(pin-to-parent).
- **마이그레이션은 Stream B 영역** — vdev-init/harness-init가 호스트의 마지막 적용 vway-kit 버전을 읽어 버전별 멱등 셋업/마이그레이션을 수행. Stream A는 그 비교 기준인 plugin.json `version`만 확립.
- python-semantic-release `version_variables`는 초기값이 비어있으면 치환 안 됨 → plugin.json `version`은 항상 비어있지 않은 값 유지.
- `[skip ci]`를 릴리스/핀 봇 커밋에 붙여 워크플로 무한 루프 방지.
- FAIL-OPEN 게이트 불변식·Windows 인코딩 방어(CLAUDE.md Invariants)는 건드리지 않는다.

---

### Task 1: marketplace ref 핀 스크립트

기존 `pin-marketplace-sha.py`(sha 문자열 치환)를 대체할, 릴리스 태그로 `source.ref`를 설정하고 `sha`를 제거하는 스크립트. 테스트 가능한 순수 함수로 작성.

**Files:**
- Create: `.github/scripts/pin-marketplace-ref.py`
- Test: `tests/test_pin_marketplace_ref.py`

**Interfaces:**
- Produces: `set_ref(text: str, tag: str) -> str` — marketplace.json 텍스트와 `"vX.Y.Z"` 태그를 받아, vway-kit plugin의 `source`에서 `sha`를 제거하고 `ref=tag`로 설정한 새 JSON 텍스트(2-space indent, 끝 개행)를 반환. `main(argv)` CLI 래퍼.

- [ ] **Step 1: 실패 테스트 작성**

```python
# tests/test_pin_marketplace_ref.py
import json
import importlib.util
from pathlib import Path

_spec = importlib.util.spec_from_file_location(
    "pin_marketplace_ref",
    Path(__file__).parent.parent / ".github" / "scripts" / "pin-marketplace-ref.py",
)
mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mod)


def _mk(source: dict) -> str:
    return json.dumps({"plugins": [{"name": "vway-kit", "source": source}]})


def test_set_ref_replaces_sha_with_tag():
    src = _mk({"source": "github", "repo": "Developments-3/vway-kit", "sha": "a" * 40})
    out = mod.set_ref(src, "v0.1.0")
    s = json.loads(out)["plugins"][0]["source"]
    assert s["ref"] == "v0.1.0"
    assert "sha" not in s


def test_set_ref_updates_existing_ref():
    src = _mk({"source": "github", "repo": "Developments-3/vway-kit", "ref": "v0.1.0"})
    out = mod.set_ref(src, "v0.2.0")
    assert json.loads(out)["plugins"][0]["source"]["ref"] == "v0.2.0"


def test_set_ref_ignores_other_plugins():
    txt = json.dumps({"plugins": [{"name": "other", "source": {"source": "github", "repo": "x/y", "sha": "b" * 40}}]})
    out = mod.set_ref(txt, "v0.1.0")
    s = json.loads(out)["plugins"][0]["source"]
    assert s == {"source": "github", "repo": "x/y", "sha": "b" * 40}
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_pin_marketplace_ref.py -v`
Expected: FAIL (`pin-marketplace-ref.py` 없음 / `set_ref` 미정의)

- [ ] **Step 3: 스크립트 구현**

```python
# .github/scripts/pin-marketplace-ref.py
#!/usr/bin/env python3
"""marketplace.json 의 vway-kit plugin source 를 릴리스 태그(ref)로 핀한다.

강결합 모델: plugin.json version 이 업데이트를 게이팅하고, marketplace source.ref 가
그 버전의 태그를 가리킨다. ref+sha 공존 시 sha 가 유효 핀이 되므로 sha 는 제거한다.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = "Developments-3/vway-kit"
MANIFEST = Path(".claude-plugin/marketplace.json")


def set_ref(text: str, tag: str) -> str:
    data = json.loads(text)
    for plugin in data.get("plugins", []):
        src = plugin.get("source")
        if isinstance(src, dict) and src.get("repo") == REPO:
            src.pop("sha", None)
            src["ref"] = tag
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def main(argv: list[str]) -> None:
    tag = argv[1]  # e.g. v0.1.0
    MANIFEST.write_text(set_ref(MANIFEST.read_text(encoding="utf-8"), tag), encoding="utf-8")


if __name__ == "__main__":
    main(sys.argv)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_pin_marketplace_ref.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: 커밋**

```bash
git add .github/scripts/pin-marketplace-ref.py tests/test_pin_marketplace_ref.py
git commit -m "feat(release): add marketplace ref pin script" \
  -m "릴리스 태그로 marketplace source.ref 를 설정하고 sha 를 제거하는 순수 함수 set_ref + CLI. pin-marketplace-sha 를 대체한다."
```

---

### Task 2: 버전 baseline (plugin.json / marketplace source→ref)

강결합 업데이트 게이팅을 위해 plugin.json에 `version`을 넣고, marketplace source를 태그 ref로 전환. `pyproject.toml`은 이미 `version="0.1.0"`.

**Files:**
- Modify: `.claude-plugin/plugin.json`
- Modify: `.claude-plugin/marketplace.json:12`

**Interfaces:**
- Consumes: Task 1의 `pin-marketplace-ref.py`(마켓플레이스 ref 전환은 스크립트로).
- Produces: plugin.json `version="0.1.0"`; marketplace source `{source:"github", repo, ref:"v0.1.0"}`(sha 제거).

- [ ] **Step 1: plugin.json에 version 추가**

`.claude-plugin/plugin.json`을 아래로 만든다(멱등 — 이미 version 있으면 값만 확인):

```json
{
  "name": "vway-kit",
  "version": "0.1.0",
  "description": "vway 위험도 티어 워크플로 + Teamer 연동 + Teams 알림 harness",
  "author": { "name": "vway" }
}
```

- [ ] **Step 2: marketplace source를 ref로 전환 (스크립트 사용)**

Run: `python .github/scripts/pin-marketplace-ref.py v0.1.0`
그 후 `.claude-plugin/marketplace.json`의 vway-kit `source`가 `{"source":"github","repo":"Developments-3/vway-kit","ref":"v0.1.0"}`인지 확인(`sha` 없음).

- [ ] **Step 3: 매니페스트 유효성 확인**

Run: `python -c "import json;[json.load(open(p,encoding='utf-8')) for p in ['.claude-plugin/plugin.json','.claude-plugin/marketplace.json']];print('ok')"`
Expected: `ok`

- [ ] **Step 4: (가능 시) 플러그인 매니페스트 검증**

Run: `claude plugin validate . --strict` (claude CLI 있을 때만; 없으면 skip — FAIL-OPEN)
Expected: 경고/에러 없음. `version` 필드 인식.

- [ ] **Step 5: 커밋**

```bash
git add .claude-plugin/plugin.json .claude-plugin/marketplace.json
git commit -m "feat(release): pin v0.1.0 via manifests" \
  -m "plugin.json version 을 업데이트 게이팅 SSOT 로 추가하고 marketplace source 를 태그 ref(v0.1.0)로 전환(sha 제거)."
```

---

### Task 3: python-semantic-release 설정

`pyproject.toml`에 `[tool.semantic_release]`를 추가. pyproject(version_toml) + plugin.json(version_variables)를 릴리스 커밋에 함께 bump하고, main/stage 브랜치 정책을 정의.

**Files:**
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `semantic-release version` 실행 시 pyproject `project.version` + plugin.json `version`을 bump하고 `vX.Y.Z` 태그를 만드는 설정. main=정식, stage=rc prerelease.

- [ ] **Step 1: 설정 블록 추가**

`pyproject.toml` 끝에 추가:

```toml
[tool.semantic_release]
version_toml = ["pyproject.toml:project.version"]
version_variables = [".claude-plugin/plugin.json:version"]
commit_message = "chore(release): {version} [skip ci]"
tag_format = "v{version}"
commit_parser = "conventional"

[tool.semantic_release.branches.main]
match = "main"
prerelease = false

[tool.semantic_release.branches.stage]
match = "stage"
prerelease = true
prerelease_token = "rc"

[tool.semantic_release.changelog]
default_templates.changelog_file = "CHANGELOG.md"
```

> 주의: `version_variables`의 파일 경로에 `.` 이 있어도 `path:variable` 파싱은 마지막 `:` 기준이라 안전. plugin.json `version`은 이미 비어있지 않음(Task 2) → 치환 정상.

- [ ] **Step 2: dev 의존성에 python-semantic-release 추가(로컬 dry-run용)**

`pyproject.toml`의 `[dependency-groups] dev` 리스트에 `"python-semantic-release>=9"` 추가.

- [ ] **Step 3: 설정 파싱 확인 (dry-run)**

Run: `uv sync && uv run semantic-release version --print --noop`
Expected: 다음 버전 문자열 출력(에러 없이). 태그가 아직 없으면 현재 버전(0.1.0) 기준 계산.

- [ ] **Step 4: 커밋**

```bash
git add pyproject.toml
git commit -m "build(release): configure python-semantic-release" \
  -m "version_toml(pyproject) + version_variables(plugin.json) bump, main 정식/stage rc 브랜치 정책, tag_format v{version}."
```

---

### Task 4: release.yml 워크플로

main/stage push 시 semantic-release 실행 → main이면 마켓플레이스 ref 동기화 + GitHub Release, stage면 rc 프리릴리스.

**Files:**
- Create: `.github/workflows/release.yml`

**Interfaces:**
- Consumes: Task 3 설정, 기존 `.github/scripts/pin-marketplace-sha.py`(source.sha 문자열 치환, 포맷 보존).
- Produces: 릴리스 시 `vX.Y.Z` 태그 + plugin.json/pyproject bump(태그 커밋 내) + main일 때 marketplace `source.sha`를 릴리스 커밋으로 핀하는 후속 커밋(pin-to-parent, 불변) + GitHub Release.

- [ ] **Step 1: 워크플로 작성**

```yaml
# semantic 버전 릴리스 — main(정식)/stage(rc) push 시 feat/fix 파싱해 버전 bump.
# 강결합: plugin.json version 이 업데이트 게이팅 SSOT. main 릴리스는 marketplace
# source.ref 를 새 태그로 동기화(소비자 전파). release 커밋은 [skip ci] 로 루프 방지.
# 전제: 레포 Settings → Actions → Workflow permissions = "Read and write".
name: release

on:
  push:
    branches: [main, stage]

concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: false

permissions:
  contents: write

jobs:
  release:
    runs-on: ubuntu-latest
    if: ${{ !contains(github.event.head_commit.message, '[skip ci]') }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install python-semantic-release
        run: pip install "python-semantic-release>=9"

      - name: Configure Git
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

      - name: Semantic release (bump + tag + push)
        id: release
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          semantic-release version --commit --tag --push --changelog
          echo "version=$(semantic-release version --print)" >> "$GITHUB_OUTPUT"

      - name: Pin marketplace sha to release commit (main only)
        if: ${{ github.ref_name == 'main' }}
        run: |
          RELEASE_SHA="$(git rev-parse HEAD)"   # semantic-release 가 만든 릴리스 커밋(plugin.json version 포함)
          python .github/scripts/pin-marketplace-sha.py "$RELEASE_SHA"
          git add .claude-plugin/marketplace.json
          if git diff --cached --quiet; then
            echo "marketplace sha already current"
            exit 0
          fi
          git commit -m "chore(release): pin marketplace sha [skip ci]" \
            -m "source.sha 를 방금 릴리스한 커밋(plugin.json version 반영)으로 핀한다."
          git push origin HEAD:main

      - name: Create GitHub Release
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          TAG="$(git describe --tags --abbrev=0)"
          if gh release view "$TAG" &>/dev/null; then
            gh release delete "$TAG" --yes
          fi
          PRERELEASE=""
          [ "${{ github.ref_name }}" = "stage" ] && PRERELEASE="--prerelease"
          gh release create "$TAG" --title "$TAG" --generate-notes $PRERELEASE
```

- [ ] **Step 2: YAML 유효성 확인**

Run: `python -c "import yaml;yaml.safe_load(open('.github/workflows/release.yml',encoding='utf-8'));print('ok')"`
Expected: `ok`

- [ ] **Step 3: 커밋**

```bash
git add .github/workflows/release.yml
git commit -m "feat(ci): add release workflow" \
  -m "main/stage push 시 semantic-release 로 bump+tag, main 은 marketplace ref 동기화 + GitHub Release, stage 는 rc 프리릴리스."
```

---

### Task 5: 매-push 핀 워크플로 폐기 (스크립트는 유지)

강결합에선 매 push sha 갱신이 무의미(version bump만 전파). 핀은 release.yml이 릴리스
시점에만 수행(Task 4)한다. 따라서 **매-push 워크플로만 폐기**하고, `pin-marketplace-sha.py`
**스크립트는 유지**한다(release.yml이 재사용).

**Files:**
- Delete: `.github/workflows/pin-marketplace-sha.yml`
- Keep: `.github/scripts/pin-marketplace-sha.py` (release.yml Task 4가 사용 — 삭제 금지)

**Interfaces:**
- Consumes: Task 4가 릴리스 시 핀을 수행함을 전제.

- [ ] **Step 1: 워크플로만 삭제**

```bash
git rm .github/workflows/pin-marketplace-sha.yml
```

- [ ] **Step 2: 스크립트 참조 확인**

Run: `grep -rn "pin-marketplace-sha" .github/workflows/`
Expected: `release.yml`만 스크립트를 참조(폐기된 워크플로 자기참조 없음). `.py`는 남아 있어야 함.

- [ ] **Step 3: 커밋**

```bash
git commit -m "chore(ci): retire per-push pin workflow" \
  -m "매 push sha 갱신은 강결합(version bump 만 전파)에서 무의미. 핀은 release.yml 이 릴리스 시점에 수행. pin-marketplace-sha.py 스크립트는 유지(재사용)."
```

---

### Task 6: branch-naming.yml 워크플로

Git-flow 브랜치 네이밍 검증. vway-kit은 PR 미사용 → push 트리거.

**Files:**
- Create: `.github/workflows/branch-naming.yml`

- [ ] **Step 1: 워크플로 작성**

```yaml
# 브랜치 네이밍 검증 (Git-flow). vway-kit 은 PR 미사용 → push 트리거.
# 보호 브랜치(main/stage/dev)와 작업 브랜치 접두 패턴만 허용.
name: branch-naming

on:
  push:
    branches-ignore: []

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - name: Check branch name
        run: |
          BRANCH="${{ github.ref_name }}"
          echo "Checking: $BRANCH"
          PATTERNS=(
            "^main$" "^stage$" "^dev$"
            "^feature/[a-zA-Z0-9][a-zA-Z0-9._/-]*$"
            "^fix/[a-zA-Z0-9][a-zA-Z0-9._/-]*$"
            "^docs/[a-zA-Z0-9][a-zA-Z0-9._/-]*$"
            "^hotfix/[0-9]+\.[0-9]+\.[0-9]+$"
            "^release/[0-9]+\.[0-9]+\.[0-9]+$"
          )
          for p in "${PATTERNS[@]}"; do
            if [[ "$BRANCH" =~ $p ]]; then
              echo "✅ matches: $p"; exit 0
            fi
          done
          echo "❌ Invalid branch name: $BRANCH"
          echo "허용: main/stage/dev, feature/*, fix/*, docs/*, hotfix/x.y.z, release/x.y.z"
          exit 1
```

- [ ] **Step 2: YAML 유효성 확인**

Run: `python -c "import yaml;yaml.safe_load(open('.github/workflows/branch-naming.yml',encoding='utf-8'));print('ok')"`
Expected: `ok`

- [ ] **Step 3: 커밋**

```bash
git add .github/workflows/branch-naming.yml
git commit -m "feat(ci): add branch-naming validation workflow" \
  -m "push 트리거로 main/stage/dev 및 feature/fix/docs/hotfix/release 접두 패턴을 검증한다(PR 미사용 repo)."
```

---

### Task 7: entropy-check.yml 워크플로

vway-kit 스택(Python scripts + .sh 훅)에 맞춘 주간 엔트로피 점검(informational).

**Files:**
- Create: `.github/workflows/entropy-check.yml`

- [ ] **Step 1: 워크플로 작성**

```yaml
# 코드 엔트로피 주간 점검 (informational — 전 step continue-on-error).
# vway-kit 스택: scripts/*.py 복잡도·파일크기 + *.sh ShellCheck
# (훅 런타임이 Windows 라 셸 버그가 FAIL-OPEN 으로 숨음 — CLAUDE.md Invariants).
name: entropy-check

on:
  schedule:
    - cron: "0 0 * * 5"  # 매주 금요일 00:00 UTC
  workflow_dispatch: {}

jobs:
  entropy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          ref: dev

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Install uv
        run: curl -LsSf https://astral.sh/uv/install.sh | sh

      - name: Sync deps
        run: uv sync

      - name: Cyclomatic complexity (ruff)
        continue-on-error: true
        run: uv run ruff check --extend-select C901,PLR0912,PLR0915 --statistics scripts/

      - name: File size audit (>500 lines)
        continue-on-error: true
        run: |
          echo "## Files exceeding 500 lines"
          find scripts/ -name "*.py" -not -path "*/__pycache__/*" \
            | xargs wc -l 2>/dev/null \
            | awk '$1 > 500 && $2 != "total" { print }' | sort -rn

      - name: ShellCheck (*.sh)
        continue-on-error: true
        run: |
          sudo apt-get update && sudo apt-get install -y shellcheck
          find scripts/ hooks/ -name "*.sh" -print0 | xargs -0 -r shellcheck
```

- [ ] **Step 2: YAML 유효성 확인**

Run: `python -c "import yaml;yaml.safe_load(open('.github/workflows/entropy-check.yml',encoding='utf-8'));print('ok')"`
Expected: `ok`

- [ ] **Step 3: 커밋**

```bash
git add .github/workflows/entropy-check.yml
git commit -m "feat(ci): add weekly entropy-check workflow" \
  -m "금요일 cron + 수동 트리거로 scripts/*.py 복잡도·파일크기 + *.sh ShellCheck 를 informational 로 측정(전 step continue-on-error)."
```

---

### Task 8: risk-tiers.md 커밋 규율 보강

강결합에선 `docs:`/`chore:`가 전파를 트리거하지 않으므로, 동작에 영향 주는 `.md`(rules/skills 등)는 `feat`/`fix`로 커밋해야 소비자에게 전파된다는 규율을 SSOT에 한 줄 명시.

**Files:**
- Modify: `rules/risk-tiers.md` ("Commit type → version impact" 표 아래)

- [ ] **Step 1: 규율 문장 추가**

`rules/risk-tiers.md`의 "### Commit type → version impact" 표 바로 아래에 삽입:

```markdown
> **플러그인 전파 규율** — vway-kit은 강결합(plugin.json `version`) 배포다. `docs`/
> `chore`는 버전 bump를 트리거하지 않으므로 **소비자에게 전파되지 않는다**. rules·skills
> 등 **소비자 동작에 영향을 주는 `.md` 변경은 `feat`/`fix`로 커밋**해야 릴리스에 실려
> 전파된다. 순수 내부 문서(개발자 전용, 소비자 무관)만 `docs`로 둔다.
```

- [ ] **Step 2: doc-sync 정합성 확인**

Run: doc-sync 스킬로 CLAUDE.md·rules 정합성 확인(레이어2 문서 동기화). 링크/용어 drift 없으면 통과.

- [ ] **Step 3: 커밋**

```bash
git add rules/risk-tiers.md
git commit -m "docs(rules): note feat/fix for .md changes" \
  -m "강결합 배포에선 docs/chore 가 전파를 트리거 안 하므로, 소비자 동작에 영향 주는 rules/skills .md 는 feat/fix 로 커밋해야 함을 명시."
```

---

### Task 9: 브랜치 전환 + baseline 태그 (원격 — 사용자 확인 필요)

모든 파일 작업 커밋 후 실행. master→main rename, dev/stage 파생, v0.1.0 태그, origin push, GitHub 기본 브랜치 변경. **원격 변경은 사용자 확인 후 실행.**

**Files:** (git refs only)

**Interfaces:**
- Consumes: Task 1–8의 모든 커밋이 현재 브랜치(master)에 있음.

- [ ] **Step 1: 로컬 브랜치 재구성**

```bash
git branch -m master main
git branch dev main
git branch stage main
git tag v0.1.0 main   # baseline — semantic-release 계산 기준점
```

- [ ] **Step 2: 상태 확인**

Run: `git branch && git tag --list && git log --oneline -1 main dev stage`
Expected: main/dev/stage 존재, 셋 다 동일 HEAD, `v0.1.0` 태그 존재.

- [ ] **Step 3: (사용자 확인 후) 원격 push**

STOP — 원격을 바꾸기 전 사용자에게 확인받는다(GitHub 기본 브랜치·원격 master 삭제 포함).

```bash
git push -u origin main dev stage
git push origin v0.1.0
# GitHub Settings → Branches → default branch = main (웹 UI 또는 gh)
gh repo edit --default-branch main
git push origin --delete master   # 기본 브랜치 변경 후에만
```

- [ ] **Step 4: 최종 확인**

Run: `git ls-remote --heads origin && gh repo view --json defaultBranchRef`
Expected: origin에 main/dev/stage, 기본 브랜치 main, master 없음.

---

## Self-Review

**Spec coverage (스펙 A):**
- A1 브랜치 전환 → Task 9 ✓
- A2 버전 SSOT + ref 핀 → Task 1(스크립트), Task 2(baseline) ✓
- A3 워크플로: release → Task 4, pin 폐기 → Task 5, branch-naming → Task 6, entropy → Task 7 ✓
- A4 semantic-release 설정 → Task 3 ✓
- A5 커밋 규율 보강 → Task 8 ✓

**Placeholder scan:** 없음(모든 step에 실제 코드/명령/기대값).

**Type consistency:** `set_ref(text, tag)` — Task 1 정의, Task 2/Task 4에서 동일 시그니처로 CLI 호출(`pin-marketplace-ref.py <tag>`). 태그 형식 `vX.Y.Z` 일관(`tag_format="v{version}"`).

**주의(실행 시):** 이 repo가 vdev를 도그푸딩(settings.json 게이트 + vdev-config)하는지에 따라 커밋 게이트 동작이 다르다. 실행 착수 전 `/vdev`로 Dev 티어 분류·마커 기록 후 진행한다. main은 vdev-config상 production 후보이므로, 라우틴 셋업 커밋은 전환 **전**(현 master)에서 수행한다.
