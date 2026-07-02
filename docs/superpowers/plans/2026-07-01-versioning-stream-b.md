# 의미기반 버전 관리 일반화 (Stream B) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stream A가 vway-kit 자체에 세운 의미기반 커밋/버전/릴리스 체계를, harness-init(스택 리서치·문서) + vdev-init(워크플로 렌더)로 **다운스트림 프로젝트가 스택에 맞게 받도록 일반화**하고, vdev-init에 **버전 감지 + 마이그레이션 훅 골격**을 추가한다.

**Architecture:** 다운스트림은 마켓플레이스 플러그인이 아니라 **일반 패키지(pip/npm)** — 그래서 vway-kit의 marketplace-sha 핀은 이식 대상이 아니고, 렌더되는 release.yml은 **표준 semantic-release**(version_files bump + tag + GitHub Release). vdev-init이 `vdev-config.versioning`을 읽어 release(도구별)·branch-naming·entropy 워크플로를 `.github/workflows/`로 멱등 렌더(api-contract 패턴 동일). harness-init은 스택 릴리스도구를 리서치해 `versioning.release_tool`을 채우고 commit-versioning-guide 문서를 생성. vdev-init은 호스트에 적용된 vway-kit 버전을 기록·비교해 버전 구간별 마이그레이션 스텝(레지스트리, 지금은 빈 골격)을 실행.

**Tech Stack:** Python 3.12/uv, GitHub Actions, python-semantic-release / semantic-release(node), 기존 `scripts/vdev_init_setup.py` 렌더 인프라, `scripts/harness_scaffold.py`·harness-init/authoring 스킬.

## Global Constraints

- 이중 경로: `${CLAUDE_PLUGIN_ROOT}`=읽기(SOURCE 템플릿), `${CLAUDE_PROJECT_DIR}`=쓰기(호스트 산출물). 렌더 결과는 호스트 `.github/workflows/`(GitHub 강제 위치 — VWAY_DIR 예외).
- **멱등**(Invariant #5): 워크플로 렌더는 dest 존재 시 skip(자동 병합 금지, api-contract와 동일). 마이그레이션 버전 기록도 match-then-write.
- **FAIL-OPEN**: config 미설정·파싱 실패·enable:false → 조용히 skip(에러로 흐름 막지 않음).
- 다운스트림 release.yml은 **표준 semantic-release** — marketplace-sha 핀 없음(그건 vway-kit 고유).
- 렌더된 release는 스택별 도구가 다르므로 **도구별 SOURCE 템플릿**(python-semantic-release, semantic-release) — 하나의 치환 템플릿으로 통합하지 않는다.
- 커밋: Conventional Commits, gitlint 강제(title ≤50, **body 필수 B6, body 줄 ≤72 B1**). `--no-verify` 금지.
- 이 작업은 `/vdev` **Dev** 티어. feature/stream-b 에서 작업.
- 마이그레이션은 **골격만**(감지 + 레지스트리 + 실행 루프) — 실제 마이그레이션 스텝은 지금 넣지 않는다(YAGNI; 첫 마이그레이션 필요 시 추가).

---

### Task 1: vdev-config `versioning:` 슬롯

**Files:**
- Modify: `vdev-config.example.yaml` (contract_test 블록 뒤에 추가)

**Interfaces:**
- Produces: `versioning:` 설정 스키마 — 후속 Task가 이 키들을 읽는다: `enable`, `release_tool`, `version_files[]`, `branches.{stable,prerelease}`, `branch_naming.enable`, `entropy.{enable,schedule,paths[]}`.

- [ ] **Step 1: 슬롯 추가**

`vdev-config.example.yaml` 끝에 추가:

```yaml
# 의미기반 버전/릴리스 (다운스트림 = 일반 패키지). /vdev-init 이 이 값으로
# .github/workflows/ 를 렌더한다(api-contract 와 동일 패턴). 안 쓰면 enable:false → 미설치.
# release_tool 은 harness-init 리서치가 스택에 맞게 채운다.
versioning:
  enable: true
  # 스택별 릴리스 도구. 지원: python-semantic-release | semantic-release(node)
  release_tool: python-semantic-release
  # 버전 bump 대상 file:field (스택별). python: pyproject.toml:project.version / node: package.json:version
  version_files: ["pyproject.toml:project.version"]
  branches:
    stable: main        # 정식 릴리스
    prerelease: stage   # rc 프리릴리스 (없으면 빈 문자열)
  branch_naming:
    enable: true
  entropy:
    enable: true
    schedule: "0 0 * * 5"   # 주간 cron (UTC)
    paths: ["src/"]          # 복잡도/파일크기 측정 경로
```

- [ ] **Step 2: 검증**

Run: `python -c "import yaml;d=yaml.safe_load(open('vdev-config.example.yaml',encoding='utf-8'));assert d['versioning']['release_tool']=='python-semantic-release';print('ok')"`
Expected: `ok`

- [ ] **Step 3: 커밋**

```bash
git add vdev-config.example.yaml
git commit -m "feat(vdev): add versioning config slot" \
  -m "다운스트림 릴리스/branch-naming/entropy 렌더용 versioning 블록 추가(release_tool·version_files·branches·entropy)."
```

---

### Task 2: github/ SOURCE 워크플로 템플릿 4종

**Files:**
- Create: `github/release.python-semantic-release.workflow.example.yml`
- Create: `github/release.semantic-release.workflow.example.yml`
- Create: `github/branch-naming.workflow.example.yml`
- Create: `github/entropy-check.workflow.example.yml`

**Interfaces:**
- Consumes: Task 1 config 값(치환).
- Produces: `__VWAY_STABLE__`·`__VWAY_PRERELEASE__`·`__VWAY_ENTROPY_SCHEDULE__`·`__VWAY_ENTROPY_PATHS__` 플레이스홀더를 가진 템플릿. Task 3 이 치환.

- [ ] **Step 1: Python 릴리스 템플릿**

`github/release.python-semantic-release.workflow.example.yml`:

```yaml
# 의미기반 릴리스 (Python/python-semantic-release) — /vdev-init 이 vdev-config.versioning 으로 렌더.
# 표준 semantic-release: version bump + tag + GitHub Release. release 커밋은 [skip ci].
# 전제: repo Settings → Actions → Workflow permissions = "Read and write".
# semantic-release 상세 설정([tool.semantic_release])은 프로젝트 pyproject 에 둔다(commit-versioning-guide 참고).
name: release

on:
  push:
    branches: [__VWAY_STABLE__, __VWAY_PRERELEASE__]

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
        run: pip install "python-semantic-release>=10,<11"
      - name: Configure Git
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"
      - name: Semantic release
        id: sr
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          BEFORE="$(git rev-parse HEAD)"
          semantic-release version --commit --tag --push --changelog
          AFTER="$(git rev-parse HEAD)"
          if [ "$BEFORE" != "$AFTER" ]; then echo "released=true" >> "$GITHUB_OUTPUT"; fi
      - name: Create GitHub Release
        if: ${{ steps.sr.outputs.released == 'true' }}
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          REF_NAME: ${{ github.ref_name }}
        run: |
          TAG="$(git describe --tags --abbrev=0)"
          PRERELEASE=""
          [ "$REF_NAME" = "__VWAY_PRERELEASE__" ] && PRERELEASE="--prerelease"
          gh release create "$TAG" --title "$TAG" --generate-notes $PRERELEASE
```

- [ ] **Step 2: Node 릴리스 템플릿**

`github/release.semantic-release.workflow.example.yml`:

```yaml
# 의미기반 릴리스 (Node/semantic-release) — /vdev-init 이 vdev-config.versioning 으로 렌더.
# 표준 semantic-release(@semantic-release/*). 상세 설정은 프로젝트 .releaserc 에 둔다.
# 전제: repo Settings → Actions → Workflow permissions = "Read and write".
name: release

on:
  push:
    branches: [__VWAY_STABLE__, __VWAY_PRERELEASE__]

concurrency:
  group: release-${{ github.ref }}
  cancel-in-progress: false

permissions:
  contents: write
  issues: write
  pull-requests: write

jobs:
  release:
    runs-on: ubuntu-latest
    if: ${{ !contains(github.event.head_commit.message, '[skip ci]') }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          token: ${{ secrets.GITHUB_TOKEN }}
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
      - name: Semantic release
        env:
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: npx --yes semantic-release
```

- [ ] **Step 3: branch-naming 템플릿 (generic)**

`github/branch-naming.workflow.example.yml`:

```yaml
# 브랜치 네이밍 검증 (Git-flow). /vdev-init 이 렌더. push 트리거(PR 미사용 프로젝트 호환).
name: branch-naming

on:
  push:

jobs:
  validate:
    runs-on: ubuntu-latest
    steps:
      - name: Check branch name
        env:
          BRANCH: ${{ github.ref_name }}
        run: |
          echo "Checking: $BRANCH"
          PATTERNS=(
            "^__VWAY_STABLE__$" "^__VWAY_PRERELEASE__$" "^dev$"
            "^feature/[a-zA-Z0-9][a-zA-Z0-9._/-]*$"
            "^fix/[a-zA-Z0-9][a-zA-Z0-9._/-]*$"
            "^docs/[a-zA-Z0-9][a-zA-Z0-9._/-]*$"
            "^hotfix/[0-9]+\.[0-9]+\.[0-9]+$"
            "^release/[0-9]+\.[0-9]+\.[0-9]+$"
          )
          for p in "${PATTERNS[@]}"; do
            if [[ "$BRANCH" =~ $p ]]; then echo "matches: $p"; exit 0; fi
          done
          echo "Invalid branch name: $BRANCH"; exit 1
```

- [ ] **Step 4: entropy-check 템플릿 (generic)**

`github/entropy-check.workflow.example.yml`:

```yaml
# 코드 엔트로피 주간 점검 (informational — 전 step continue-on-error). /vdev-init 이 렌더.
name: entropy-check

on:
  schedule:
    - cron: "__VWAY_ENTROPY_SCHEDULE__"
  workflow_dispatch: {}

jobs:
  entropy:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: File size audit (>500 lines)
        continue-on-error: true
        run: |
          echo "## Files exceeding 500 lines"
          find __VWAY_ENTROPY_PATHS__ -type f -not -path "*/.git/*" \
            | xargs wc -l 2>/dev/null \
            | awk '$1 > 500 && $2 != "total" { print }' | sort -rn | head -50
```

- [ ] **Step 5: YAML 유효성 (플레이스홀더 포함 상태로도 파싱되는지)**

Run: `for f in github/release.python-semantic-release.workflow.example.yml github/release.semantic-release.workflow.example.yml github/branch-naming.workflow.example.yml github/entropy-check.workflow.example.yml; do python -c "import yaml,sys;yaml.safe_load(open('$f',encoding='utf-8'));print('ok $f')"; done`
Expected: 4× `ok`

- [ ] **Step 6: 커밋**

```bash
git add github/release.python-semantic-release.workflow.example.yml github/release.semantic-release.workflow.example.yml github/branch-naming.workflow.example.yml github/entropy-check.workflow.example.yml
git commit -m "feat(vdev): add versioning workflow templates" \
  -m "python/node 릴리스 + branch-naming + entropy SOURCE 템플릿(__VWAY_*__ 치환)."
```

---

### Task 3: vdev-init 렌더 로직 + 테스트

**Files:**
- Modify: `scripts/vdev_init_setup.py` (`render_workflow` 옆에 `render_versioning_workflows` 추가, `run_setup`에서 호출)
- Modify: `tests/test_vdev_init_setup.py`

**Interfaces:**
- Consumes: Task 1 config, Task 2 템플릿.
- Produces: `load_versioning_config(host) -> dict | None`, `render_versioning_workflows(host, plugin) -> list[str]`. run_setup가 호출. 멱등(dest 존재 시 skip).

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_vdev_init_setup.py`에 추가(기존 테스트의 fixture 패턴 따름 — plugin/host tmp dir):

```python
def test_render_versioning_python(tmp_path):
    from scripts import vdev_init_setup as m
    plugin = tmp_path / "plugin"; host = tmp_path / "host"
    # SOURCE 템플릿 배치
    (plugin / "github").mkdir(parents=True)
    (plugin / "github" / "release.python-semantic-release.workflow.example.yml").write_text(
        "on:\n  push:\n    branches: [__VWAY_STABLE__, __VWAY_PRERELEASE__]\n", encoding="utf-8")
    (plugin / "github" / "branch-naming.workflow.example.yml").write_text("name: branch-naming\n", encoding="utf-8")
    (plugin / "github" / "entropy-check.workflow.example.yml").write_text(
        'on:\n  schedule:\n    - cron: "__VWAY_ENTROPY_SCHEDULE__"\npaths: __VWAY_ENTROPY_PATHS__\n', encoding="utf-8")
    (host / ".claude" / "vway-kit" / "config").mkdir(parents=True)
    (host / ".claude" / "vway-kit" / "config" / "vdev-config.yaml").write_text(
        'versioning:\n  enable: true\n  release_tool: python-semantic-release\n'
        '  branches: {stable: main, prerelease: stage}\n'
        '  branch_naming: {enable: true}\n'
        '  entropy: {enable: true, schedule: "0 0 * * 5", paths: ["src/"]}\n', encoding="utf-8")
    msgs = m.render_versioning_workflows(host, plugin)
    rel = (host / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert "[main, stage]" in rel and "__VWAY_" not in rel
    assert (host / ".github" / "workflows" / "branch-naming.yml").exists()
    ent = (host / ".github" / "workflows" / "entropy-check.yml").read_text(encoding="utf-8")
    assert "0 0 * * 5" in ent and "src/" in ent


def test_render_versioning_disabled(tmp_path):
    from scripts import vdev_init_setup as m
    plugin = tmp_path / "plugin"; host = tmp_path / "host"
    (host / ".claude" / "vway-kit" / "config").mkdir(parents=True)
    (host / ".claude" / "vway-kit" / "config" / "vdev-config.yaml").write_text(
        "versioning:\n  enable: false\n", encoding="utf-8")
    msgs = m.render_versioning_workflows(host, plugin)
    assert not (host / ".github" / "workflows" / "release.yml").exists()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_vdev_init_setup.py -k versioning -v`
Expected: FAIL (`render_versioning_workflows` 미정의)

- [ ] **Step 3: 구현**

`scripts/vdev_init_setup.py`에 추가(기존 `render_workflow`/`load_contract_config` 스타일 따름):

```python
def load_versioning_config(host: Path) -> dict | None:
    """vdev-config.yaml 의 versioning dict 반환(없거나 파싱 실패 시 None — FAIL-OPEN)."""
    cfg = host / VWAY_DIR / "config" / "vdev-config.yaml"
    try:
        data = _load_yaml_safe(cfg)
    except Exception:
        return None
    v = data.get("versioning")
    return v if isinstance(v, dict) else None


_RELEASE_TEMPLATES = {
    "python-semantic-release": "github/release.python-semantic-release.workflow.example.yml",
    "semantic-release": "github/release.semantic-release.workflow.example.yml",
}


def render_versioning_workflows(host: Path, plugin: Path) -> list[str]:
    v = load_versioning_config(host)
    if not v:
        return ["  [=] versioning 미설정 — 워크플로 skip"]
    if not v.get("enable", False):
        return ["  [=] versioning.enable=false — 워크플로 미설치"]
    out: list[str] = []
    branches = v.get("branches", {}) or {}
    stable = str(branches.get("stable", "main"))
    prerelease = str(branches.get("prerelease", "") or "")
    subs = {"__VWAY_STABLE__": stable, "__VWAY_PRERELEASE__": prerelease}
    wf_dir = host / ".github" / "workflows"

    # release (도구별)
    tool = str(v.get("release_tool", ""))
    tmpl = _RELEASE_TEMPLATES.get(tool)
    if tmpl:
        out += _render_one(plugin / tmpl, wf_dir / "release.yml", subs)
    else:
        out.append(f"  [!] 알 수 없는 release_tool={tool!r} — release.yml skip")

    # branch-naming
    if (v.get("branch_naming", {}) or {}).get("enable", False):
        out += _render_one(plugin / "github/branch-naming.workflow.example.yml",
                           wf_dir / "branch-naming.yml", subs)

    # entropy
    ent = v.get("entropy", {}) or {}
    if ent.get("enable", False):
        esub = dict(subs)
        esub["__VWAY_ENTROPY_SCHEDULE__"] = str(ent.get("schedule", "0 0 * * 5"))
        esub["__VWAY_ENTROPY_PATHS__"] = " ".join(str(p) for p in (ent.get("paths") or ["src/"]))
        out += _render_one(plugin / "github/entropy-check.workflow.example.yml",
                           wf_dir / "entropy-check.yml", esub)
    return out


def _render_one(src: Path, dest: Path, subs: dict) -> list[str]:
    if not src.exists():
        return [f"  [!] 템플릿 없음: {src.name} — skip"]
    if dest.exists():
        return [f"  [i] {dest.name} 이미 있어 자동 병합 안 함(커스텀 보존)."]
    text = src.read_text(encoding="utf-8")
    for k, val in subs.items():
        text = text.replace(k, val)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return [f"  [+] .github/workflows/{dest.name} 생성 (versioning 렌더)"]
```

그리고 `run_setup`의 `render_workflow` 호출 뒤에 추가:
```python
    for line in render_versioning_workflows(host, plugin):
        print(line)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_vdev_init_setup.py -k versioning -v && uv run pytest tests/test_vdev_init_setup.py -q`
Expected: 신규 2개 PASS + 기존 테스트 회귀 없음

- [ ] **Step 5: 커밋**

```bash
git add scripts/vdev_init_setup.py tests/test_vdev_init_setup.py
git commit -m "feat(vdev): render versioning workflows on init" \
  -m "versioning config 로 release(도구별)/branch-naming/entropy 를 멱등 렌더. FAIL-OPEN·dest 존재 시 skip."
```

---

### Task 4: 마이그레이션 골격 (버전 감지 + 레지스트리)

**Files:**
- Modify: `scripts/vdev_init_setup.py` (`apply_migrations` + 버전 기록)
- Modify: `tests/test_vdev_init_setup.py`

**Interfaces:**
- Produces: `plugin_version(plugin) -> str`, `applied_version(host) -> str | None`, `apply_migrations(host, plugin, registry=MIGRATIONS) -> list[str]`. `MIGRATIONS: dict[str, callable]`(지금 비어 있음). run_setup 끝에서 호출해 버전 마커를 기록. 멱등.

- [ ] **Step 1: 실패 테스트 작성**

```python
def test_apply_migrations_records_version(tmp_path):
    from scripts import vdev_init_setup as m
    plugin = tmp_path / "plugin"; host = tmp_path / "host"
    (plugin / ".claude-plugin").mkdir(parents=True)
    (plugin / ".claude-plugin" / "plugin.json").write_text('{"name":"vway-kit","version":"0.2.0"}', encoding="utf-8")
    (host / ".claude" / "vway-kit" / "config").mkdir(parents=True)
    ran = []
    reg = {"0.2.0": lambda h, p: ran.append("mig-0.2.0")}
    # 최초: applied 없음 → 등록된 0.2.0 마이그레이션 실행 + 버전 기록
    m.apply_migrations(host, plugin, registry=reg)
    assert ran == ["mig-0.2.0"]
    assert m.applied_version(host) == "0.2.0"
    # 재실행: 같은 버전 → 마이그레이션 재실행 안 함(멱등)
    m.apply_migrations(host, plugin, registry=reg)
    assert ran == ["mig-0.2.0"]
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/test_vdev_init_setup.py -k migrations -v`
Expected: FAIL (`apply_migrations` 미정의)

- [ ] **Step 3: 구현**

`scripts/vdev_init_setup.py`에 추가:

```python
import json as _json
from packaging.version import Version  # 이미 의존성에 있으면 사용; 없으면 tuple 파싱 폴백

VERSION_MARKER = ".claude/vway-kit/config/.vway-version"  # 호스트 적용 버전(평문)

# 버전 구간별 마이그레이션. key=이 버전으로 올라올 때 실행. 지금은 비어 있음(골격).
MIGRATIONS: dict = {}


def plugin_version(plugin: Path) -> str:
    try:
        data = _json.loads((plugin / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))
        return str(data.get("version", "")) or "0.0.0"
    except Exception:
        return "0.0.0"


def applied_version(host: Path) -> str | None:
    f = host / VERSION_MARKER
    return f.read_text(encoding="utf-8").strip() if f.exists() else None


def _vkey(s: str):
    try:
        return Version(s)
    except Exception:
        return tuple(int(x) for x in re.findall(r"\d+", s)) or (0,)


def apply_migrations(host: Path, plugin: Path, registry: dict | None = None) -> list[str]:
    """호스트 적용 버전 → 현재 plugin 버전 사이의 마이그레이션을 순서대로 실행하고
    버전 마커를 갱신한다. FAIL-OPEN(마이그레이션 예외는 경고만, 흐름 유지)."""
    reg = MIGRATIONS if registry is None else registry
    cur = plugin_version(plugin)
    prev = applied_version(host)
    out: list[str] = []
    if prev == cur:
        return [f"  [=] vway-kit {cur} 이미 적용됨 — 마이그레이션 없음"]
    # prev(제외) < v <= cur 구간의 등록 마이그레이션을 버전 오름차순 실행
    todo = sorted((v for v in reg if (prev is None or _vkey(prev) < _vkey(v)) and _vkey(v) <= _vkey(cur)), key=_vkey)
    for v in todo:
        try:
            reg[v](host, plugin)
            out.append(f"  [+] 마이그레이션 적용: {v}")
        except Exception as e:  # noqa: BLE001 — FAIL-OPEN
            out.append(f"  [!] 마이그레이션 {v} 실패(무시): {e}")
    marker = host / VERSION_MARKER
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(cur + "\n", encoding="utf-8")
    out.append(f"  [i] 적용 버전 기록: {prev or '(없음)'} → {cur}")
    return out
```

`run_setup` 끝에 추가:
```python
    for line in apply_migrations(host, plugin):
        print(line)
```
(`re` import 이미 있는지 확인, 없으면 추가. `packaging`은 uv 환경에 보통 존재 — 없으면 tuple 폴백으로 충분.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_vdev_init_setup.py -k migrations -v && uv run pytest -q`
Expected: 신규 PASS + 전체 회귀 없음

- [ ] **Step 5: 커밋**

```bash
git add scripts/vdev_init_setup.py tests/test_vdev_init_setup.py
git commit -m "feat(vdev): version-gated migration skeleton" \
  -m "호스트 적용 vway-kit 버전을 기록·비교해 버전 구간별 마이그레이션 레지스트리를 멱등 실행(지금은 빈 골격). FAIL-OPEN."
```

---

### Task 5: harness-init 확장 (버전/릴리스 리서치 + 가이드 문서)

**Files:**
- Modify: `rules/harness-rules.md` (버전/릴리스 리서치 규율 절 추가)
- Modify: `skills/harness-authoring/SKILL.md` 또는 references (commit-versioning-guide 템플릿·작성 지침)
- Modify: `skills/harness-init/SKILL.md` (Step 2 리서치·Step 4 authoring에 릴리스 도구·가이드 추가 노트)

**Interfaces:**
- Consumes: 없음(문서/규율).
- Produces: harness-init이 스택 릴리스도구를 리서치해 `vdev-config.versioning.release_tool`을 제안하고, `docs/` 분류에 commit-versioning-guide를 생성하도록 하는 규율/지침. 규율 SSOT는 risk-tiers로 defer(중복 emit 금지).

- [ ] **Step 1: harness-rules.md에 절 추가**

`rules/harness-rules.md`에 "버전/릴리스 컨벤션 리서치" 절 추가(요지):
- 감지 스택의 표준 릴리스 도구를 리서치(Python→python-semantic-release, Node→semantic-release, Rust→cargo-release 등)해 `vdev-config.versioning.release_tool`·`version_files`를 제안한다.
- Conventional Commits + SemVer(0.x는 `major_on_zero=false` 권장)를 `commit-versioning-guide` 기술문서로 생성하되, **티어/커밋 규율 자체는 risk-tiers로 defer**(자체 규율 emit 금지, Stream A와 동일).
- vdev 미감지 프로젝트에서만 릴리스 도구 설정을 opt-in 제안(vdev 감지 시 vdev-init이 렌더).

- [ ] **Step 2: commit-versioning-guide 템플릿/지침 추가**

`skills/harness-authoring/` references에 `commit-versioning-guide` 작성 지침(스택별 릴리스 도구 설정·버전 확인 명령·0.x 정책) 추가. authoring이 확정 스택으로 `docs/operations/commit-versioning-guide.md`를 생성하도록.

- [ ] **Step 3: harness-init SKILL 노트**

`skills/harness-init/SKILL.md` Step 2(리서치)·Step 4(authoring)에 "버전/릴리스 도구·commit-versioning-guide" 산출물을 한 줄씩 추가(기존 산출물 목록에 편입).

- [ ] **Step 4: 정합성 확인**

Run: `grep -rn "commit-versioning-guide\|release_tool" rules/harness-rules.md skills/harness-init/SKILL.md skills/harness-authoring/`
Expected: 세 곳이 일관되게 참조.

- [ ] **Step 5: 커밋**

```bash
git add rules/harness-rules.md skills/harness-init/SKILL.md skills/harness-authoring/
git commit -m "feat(harness): research release tooling + guide" \
  -m "harness-init 이 스택 릴리스도구를 리서치해 versioning.release_tool 제안 + commit-versioning-guide 생성(규율은 risk-tiers defer)."
```

---

### Task 6: 문서 동기화 (CLAUDE.md 폴더 구조 + 스펙)

**Files:**
- Modify: `CLAUDE.md` (folder structure의 `github/` 라인에 신규 템플릿 반영)
- Modify: `docs/superpowers/specs/2026-07-01-semantic-versioning-sha-design.md` (Stream B 확정 설계 반영)

- [ ] **Step 1: CLAUDE.md folder structure 갱신**

`github/` 라인을 신규 4종 템플릿(release 도구별·branch-naming·entropy) + api-contract 로 갱신.

- [ ] **Step 2: 스펙 Stream B 확정 반영**

스펙 B1~B4를 이 계획의 확정 결정(도구별 템플릿·마이그레이션 골격·config 스키마)으로 갱신.

- [ ] **Step 3: 커밋**

```bash
git add CLAUDE.md docs/superpowers/specs/2026-07-01-semantic-versioning-sha-design.md
git commit -m "docs: reflect stream B versioning generalization" \
  -m "CLAUDE.md 구조에 versioning 템플릿 반영, 스펙 Stream B 를 확정 설계로 갱신."
```

---

## Self-Review

**Spec coverage (스펙 B):** B1 config→Task 1 ✓ / B2 템플릿→Task 2 ✓ / B3 렌더→Task 3 ✓ / B4 harness-init→Task 5 ✓ / 마이그레이션(사용자 강조)→Task 4 ✓ / 문서→Task 6 ✓.

**Placeholder scan:** 코드/템플릿/명령 모두 실체 포함. (Task 5는 문서·규율이라 산문 지침 — 구현 시 harness-authoring 기존 references 스타일 따름.)

**Type consistency:** `render_versioning_workflows(host, plugin)`·`load_versioning_config(host)`·`apply_migrations(host, plugin, registry)`·`plugin_version(plugin)`·`applied_version(host)` — Task 3/B4에서 정의, run_setup가 호출. 치환 키 `__VWAY_STABLE__/__VWAY_PRERELEASE__/__VWAY_ENTROPY_SCHEDULE__/__VWAY_ENTROPY_PATHS__` 템플릿(B2)↔렌더(B3) 일치.

**주의:** B5(harness-init)는 에이전트 행동/문서라 결정적 테스트가 없다 — harness-critic 리뷰로 정합성 확인(harness-init 자체 파이프라인). vdev-init 도그푸딩 아님 — 커밋 게이트 미설치.
