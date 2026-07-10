# harness-deployments 스킬 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development(권장) 또는
> superpowers:executing-plans 로 이 계획을 task 단위로 구현하라. 스텝은 체크박스(`- [ ]`)로 추적한다.

**Goal:** harness-tier에 배포 계층을 추가한다 — `/harness-deployments` 대화형 스킬 + `github/` 정적 deploy
템플릿 + `flow-config`의 `deploy:` 블록으로, 릴리스가 만든 태그를 소비해 산출물을 레지스트리/이미지/앱으로
배포하는 CI 워크플로우를 생성한다.

**Architecture:** 결정적 렌더(플레이스홀더 치환·멱등 쓰기)는 기존 `scripts/flow_init_setup.py`를 확장해
재사용하고(`_render_one` 재사용), 대화형 판단(감지·Q&A·앱 배포 저작·문서)은 `skills/harness-deployments/`
스킬이 담당한다. 배포 워크플로우는 기본적으로 `workflow_run`(릴리스 완료 후) + `workflow_dispatch`로 트리거해
기본 `GITHUB_TOKEN`에서 무설정 동작하며, 릴리스와 분리된 별도 파일(`deploy-<name>.yml`)이다.

**Tech Stack:** Python 3.8+(stdlib + PyYAML), pytest, GitHub Actions YAML, Claude Code 스킬(SKILL.md).

## Global Constraints

- **플러그인 디렉터리엔 절대 쓰지 않는다.** 읽기=`${CLAUDE_PLUGIN_ROOT}`, 호스트 쓰기=`${CLAUDE_PROJECT_DIR}`.
  호스트 쓰기는 `.github/workflows/`·`.claude/harness-tier/config/`·`docs/`로만.
- **모든 렌더 job은 `timeout-minutes` 캡을 가진다** (기존 CI 워크플로우 전체 관례).
- **렌더는 멱등·비파괴·FAIL-OPEN**: dest가 이미 있으면 자동 병합하지 않고 skip(주석/커스텀 보존), `OSError`는
  raise가 아니라 보고(게이트를 막지 않음) — `flow_init_setup.py`의 `render_workflow`/`render_versioning_workflows`와 동일.
- **파일 IO는 항상 `encoding="utf-8"`**, Python은 `force_utf8_io()` 방어(cp949 로케일 대비 — Invariant #2).
- **커밋은 이 repo의 `/flow` 게이트를 통과한다** (미분류 커밋은 차단됨). 본 기능은 소비자 동작에 영향을 주므로
  (호스트로 렌더링되는 새 스킬·템플릿) 커밋 메시지는 Conventional Commits **`feat:`** 를 쓴다(semantic-release
  전파 — risk-tiers Commit Discipline). 각 task의 "Commit" 스텝은 `/flow`(Dev 티어)로 분류 후 커밋한다.
- **템플릿 플레이스홀더**는 기존 스타일(`__HARNESS_*__`)을 따른다.
- 신규 stack/타깃 CI는 harness-tier 자체 CI에도 반영(dogfood) 여지가 있으나, 이번 반복 범위는 소비자 템플릿 +
  스킬까지. (harness-tier 자체 배포는 별도 판단.)

---

## 파일 구조

**생성:**
- `github/deploy.pypi.workflow.example.yml` — PyPI 발행(registry/python)
- `github/deploy.npm.workflow.example.yml` — npm 발행(registry/node)
- `github/deploy.maven-central.workflow.example.yml` — Maven Central(registry/java|kotlin)
- `github/deploy.nuget.workflow.example.yml` — NuGet(registry/c#)
- `github/deploy.cratesio.workflow.example.yml` — crates.io(registry/rust)
- `github/deploy.ghcr.workflow.example.yml` — GHCR 이미지(image/docker)
- `github/deploy.dockerhub.workflow.example.yml` — Docker Hub 이미지(image/docker)
- `skills/harness-deployments/SKILL.md` — 대화형 스킬(감지→Q&A→생성)
- `skills/harness-deployments/references/registry-publish/{python-pypi,node-npm,java-maven-central,dotnet-nuget,rust-cratesio}.md`
- `skills/harness-deployments/references/container-image/{docker-ghcr,docker-hub}.md`
- `skills/harness-deployments/references/app-deploy/{ssh-server,kubernetes,cloud-run,ecs}.md`
- `skills/harness-deployments/references/_trigger-and-secrets.md`
- `tests/test_deploy_render.py` — 렌더/스키마/멱등성/timeout-cap 테스트

**수정:**
- `flow-config.example.yaml` — `deploy:` 블록 추가(문서화)
- `scripts/flow_init_setup.py` — `load_deploy_config` / `render_deploy_workflows` / `DEPLOY_TEMPLATE_BY_KIND_STACK`
  추가 + `main()` setup 경로에 배선 + `--render-deploy` 플래그
- `CLAUDE.md` — 폴더 구조/아키텍처에 배포 계층 한 줄 추가
- `USAGE.md`·`USAGE.ko.md` — `/harness-deployments` 사용 절 추가

---

## Task 1: flow-config `deploy:` 스키마 + 로더

**Files:**
- Modify: `flow-config.example.yaml` (versioning/contract_test 블록 뒤에 `deploy:` 추가)
- Modify: `scripts/flow_init_setup.py` (`load_deploy_config` 추가 — `load_versioning_config` 옆)
- Test: `tests/test_deploy_render.py`

**Interfaces:**
- Produces: `load_deploy_config(host: Path) -> dict | None` — flow-config.yaml에서 `deploy` dict 반환
  (부재/파싱 실패/타입 불일치 시 `None` — FAIL-OPEN, `load_versioning_config`과 동일 시그니처).

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_deploy_render.py`

```python
from pathlib import Path

import pytest

from scripts.flow_init_setup import load_deploy_config


def _write_config(host: Path, body: str) -> None:
    cfg = host / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "flow-config.yaml").write_text(body, encoding="utf-8")


def test_load_deploy_config_absent_returns_none(tmp_path: Path):
    _write_config(tmp_path, "versioning:\n  enable: true\n")
    assert load_deploy_config(tmp_path) is None


def test_load_deploy_config_returns_dict(tmp_path: Path):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  trigger: workflow_run\n  targets:\n"
        "    - name: pypi\n      kind: registry\n      stack: python\n",
    )
    cfg = load_deploy_config(tmp_path)
    assert cfg is not None
    assert cfg["enable"] is True
    assert cfg["targets"][0]["name"] == "pypi"


def test_load_deploy_config_broken_yaml_returns_none(tmp_path: Path):
    _write_config(tmp_path, "deploy: : : broken\n")
    assert load_deploy_config(tmp_path) is None
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_deploy_render.py -v`
Expected: FAIL — `ImportError: cannot import name 'load_deploy_config'`

- [ ] **Step 3: 로더 구현** — `scripts/flow_init_setup.py` 의 `load_versioning_config` 정의 바로 아래에 추가

```python
def load_deploy_config(host: Path) -> dict | None:
    """Return deploy dict from flow-config.yaml (None if absent/unparseable — FAIL-OPEN)."""
    try:
        import yaml

        cfg = config_path(host)
        if not cfg.exists():
            return None
        data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        d = data.get("deploy")
        return d if isinstance(d, dict) else None
    except Exception:
        return None
```

- [ ] **Step 4: `flow-config.example.yaml`에 `deploy:` 블록 추가** (unit_test 블록 뒤)

```yaml
# Deployment (CI only — GitHub Actions). Layered ON TOP of versioning: release mints the tag,
# deploy consumes it. Set up by /harness-deployments (detect → Q&A → render). enable:false → not installed.
# The default trigger works on the auto-provided GITHUB_TOKEN (no admin PAT). See docs/operations/deploy-guide.md.
deploy:
  enable: false
  # workflow_run — auto after the release workflow completes (recommended; fires on GITHUB_TOKEN)
  # release      — on: release: published; REQUIRES a RELEASE_TOKEN(PAT) secret or it will not fire
  trigger: workflow_run
  release_workflow: release       # upstream workflow name that workflow_run keys off
  dispatch: true                  # also add workflow_dispatch (manual re-deploy) — always fires
  timeout_minutes: 15
  # One entry per target → rendered into .github/workflows/deploy-<name>.yml
  #   kind:  registry | image | app   (app = authored from references, not templated)
  #   stack: python | node | java | c# | rust | docker
  targets:
    - name: pypi
      kind: registry
      stack: python
      build: "uv build"
      secrets: []                 # [] = OIDC trusted publishing; or e.g. [PYPI_API_TOKEN]
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/test_deploy_render.py -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit** — `/flow`로 Dev 티어 분류 후

```bash
git add flow-config.example.yaml scripts/flow_init_setup.py tests/test_deploy_render.py
git commit -m "feat(deploy): add flow-config deploy block and loader"
```

---

## Task 2: PyPI 템플릿 + `render_deploy_workflows` 렌더 코어

**Files:**
- Create: `github/deploy.pypi.workflow.example.yml`
- Modify: `scripts/flow_init_setup.py` (`DEPLOY_TEMPLATE_BY_KIND_STACK`, `render_deploy_workflows`)
- Test: `tests/test_deploy_render.py`

**Interfaces:**
- Consumes: `load_deploy_config` (Task 1), `_render_one(src: Path, dest: Path, subs: dict) -> list[str]` (기존).
- Produces: `render_deploy_workflows(host: Path, plugin: Path) -> list[str]` — 각 타깃을
  `.github/workflows/deploy-<name>.yml`로 렌더, 사람이 읽는 요약 라인 리스트 반환.
  `DEPLOY_TEMPLATE_BY_KIND_STACK: dict[tuple[str, str], str]` — `(kind, stack)` → 템플릿 경로.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_deploy_render.py`에 추가

```python
from scripts.flow_init_setup import render_deploy_workflows

PLUGIN = Path(__file__).resolve().parents[1]  # repo root (plugin source)


def test_render_pypi_produces_workflow(tmp_path: Path):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  trigger: workflow_run\n  release_workflow: release\n"
        "  dispatch: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: pypi\n      kind: registry\n      stack: python\n      build: \"uv build\"\n",
    )
    render_deploy_workflows(tmp_path, PLUGIN)
    wf = tmp_path / ".github" / "workflows" / "deploy-pypi.yml"
    text = wf.read_text(encoding="utf-8")
    assert "__HARNESS_" not in text                      # 모든 플레이스홀더 치환됨
    assert "timeout-minutes: 15" in text
    assert "workflow_run:" in text and "workflow_dispatch:" in text
    assert 'workflows: ["release"]' in text
    assert "uv build" in text


def test_render_disabled_skips(tmp_path: Path):
    _write_config(tmp_path, "deploy:\n  enable: false\n  targets: []\n")
    out = render_deploy_workflows(tmp_path, PLUGIN)
    assert not (tmp_path / ".github" / "workflows" / "deploy-pypi.yml").exists()
    assert any("enable=false" in line for line in out)


def test_render_deploy_idempotent_nondestructive(tmp_path: Path):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  trigger: workflow_run\n  release_workflow: release\n"
        "  dispatch: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: pypi\n      kind: registry\n      stack: python\n      build: \"uv build\"\n",
    )
    render_deploy_workflows(tmp_path, PLUGIN)
    wf = tmp_path / ".github" / "workflows" / "deploy-pypi.yml"
    wf.write_text("# hand-edited\n", encoding="utf-8")   # 사용자 커스텀
    render_deploy_workflows(tmp_path, PLUGIN)             # 재실행
    assert wf.read_text(encoding="utf-8") == "# hand-edited\n"  # 덮어쓰지 않음
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_deploy_render.py -k render -v`
Expected: FAIL — `ImportError: cannot import name 'render_deploy_workflows'`

- [ ] **Step 3: PyPI 템플릿 작성** — `github/deploy.pypi.workflow.example.yml`

```yaml
# Deploy (PyPI) — rendered by /flow-init & /harness-deployments from flow-config.deploy.
# Runs AFTER the release workflow completes (workflow_run) so it fires on the default GITHUB_TOKEN
# without a PAT; plus manual workflow_dispatch. Builds the sdist/wheel and publishes to PyPI.
# OIDC trusted publishing is used when no token secret is configured (id-token: write) — set up a
# PyPI "trusted publisher" for this repo, or switch to a PYPI_API_TOKEN secret. See deploy-guide.md.
name: deploy-pypi

on:
  workflow_run:
    workflows: ["__HARNESS_RELEASE_WORKFLOW__"]
    types: [completed]
  workflow_dispatch:

concurrency:
  group: deploy-pypi-${{ github.ref }}
  cancel-in-progress: false

permissions:
  contents: read
  id-token: write        # OIDC trusted publishing

jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: __HARNESS_TIMEOUT__
    # workflow_run fires on any conclusion → only deploy when the release actually succeeded.
    if: ${{ github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success' }}
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - name: Check out the released tag
        # Deploy the just-released version regardless of trigger (the release workflow made a new
        # tag; workflow_run's head_sha may predate the version-bump commit).
        run: git checkout "$(git describe --tags --abbrev=0)"
      - uses: actions/setup-python@v6
        with:
          python-version: "3.12"
      - name: Build
        run: __HARNESS_BUILD__
      - name: Publish to PyPI
        uses: pypa/gh-action-pypi-publish@release/v1
```

- [ ] **Step 4: 렌더 코어 구현** — `scripts/flow_init_setup.py` (`render_versioning_workflows` 아래)

```python
# (kind, stack) → template path (plugin-owned SOURCE). Missing pairs (e.g. any app target) are
# NOT templated — /harness-deployments authors those from references; render skips them with a note.
DEPLOY_TEMPLATE_BY_KIND_STACK = {
    ("registry", "python"): "github/deploy.pypi.workflow.example.yml",
    ("registry", "node"): "github/deploy.npm.workflow.example.yml",
    ("registry", "java"): "github/deploy.maven-central.workflow.example.yml",
    ("registry", "kotlin"): "github/deploy.maven-central.workflow.example.yml",
    ("registry", "c#"): "github/deploy.nuget.workflow.example.yml",
    ("registry", "rust"): "github/deploy.cratesio.workflow.example.yml",
    ("image", "docker"): "github/deploy.ghcr.workflow.example.yml",
}


def render_deploy_workflows(host: Path, plugin: Path) -> list[str]:
    """Render .github/workflows/deploy-<name>.yml for each configured deploy target.

    Mirrors render_versioning_workflows: idempotent·non-destructive (skips an existing dest),
    FAIL-OPEN (an OSError is reported, not raised). GitHub forces .github/workflows/ so it is an
    exception to the HARNESS_DIR rule. app-kind (or any un-templated pair) is skipped with a note —
    /harness-deployments authors those.
    """
    d = load_deploy_config(host)
    if not d:
        return ["  [=] deploy 미설정 — 워크플로 skip"]
    if not d.get("enable", False):
        return ["  [=] deploy.enable=false — 워크플로 미설치"]

    trigger = str(d.get("trigger", "workflow_run"))
    release_wf = str(d.get("release_workflow", "release"))
    timeout = str(d.get("timeout_minutes", 15))
    wf_dir = host / ".github" / "workflows"
    out: list[str] = []
    for t in d.get("targets", []) or []:
        name = str(t.get("name", "")).strip()
        kind = str(t.get("kind", "")).strip()
        stack = str(t.get("stack", "")).strip()
        if not name:
            out.append("  [!] name 없는 deploy 타깃 — skip")
            continue
        tmpl = DEPLOY_TEMPLATE_BY_KIND_STACK.get((kind, stack))
        if not tmpl:
            out.append(
                f"  [i] deploy 타깃 {name!r}(kind={kind},stack={stack}) — 템플릿 없음"
                " → /harness-deployments 저작 대상"
            )
            continue
        subs = {
            "__HARNESS_RELEASE_WORKFLOW__": release_wf,
            "__HARNESS_TIMEOUT__": timeout,
            "__HARNESS_BUILD__": str(t.get("build", "")),
            "__HARNESS_IMAGE__": str(t.get("image", "")),
            "__HARNESS_TRIGGER__": trigger,
        }
        out += _render_one(plugin / tmpl, wf_dir / f"deploy-{name}.yml", subs)
    return out
```

> NOTE: `_render_one`은 dest가 이미 있으면 skip한다(멱등·비파괴). `trigger`/`dispatch`에 따른 트리거 블록
> 분기는 Task 5에서 추가한다. 지금은 템플릿이 workflow_run+dispatch 고정이라 `__HARNESS_TRIGGER__`는 아직
> 미사용(Task 5에서 소비).

- [ ] **Step 5: 테스트 통과 확인**

Run: `uv run pytest tests/test_deploy_render.py -k render -v`
Expected: PASS (3 passed)

- [ ] **Step 6: Commit** — `/flow` 분류 후

```bash
git add github/deploy.pypi.workflow.example.yml scripts/flow_init_setup.py tests/test_deploy_render.py
git commit -m "feat(deploy): render deploy workflows from config (PyPI template)"
```

---

## Task 3: 나머지 레지스트리 템플릿 (npm · Maven Central · NuGet · crates.io)

**Files:**
- Create: `github/deploy.npm.workflow.example.yml`, `github/deploy.maven-central.workflow.example.yml`,
  `github/deploy.nuget.workflow.example.yml`, `github/deploy.cratesio.workflow.example.yml`
- Test: `tests/test_deploy_render.py`

**Interfaces:**
- Consumes: `render_deploy_workflows`, `DEPLOY_TEMPLATE_BY_KIND_STACK` (Task 2 — 매핑은 이미 4쌍 포함).

- [ ] **Step 1: 실패하는 파라미터 테스트 작성** — `tests/test_deploy_render.py`에 추가

```python
@pytest.mark.parametrize(
    "name,stack,build,needle",
    [
        ("npm", "node", "npm ci && npm run build", "npm publish"),
        ("maven-central", "java", "mvn -B -DskipTests package", "central"),
        ("nuget", "c#", "dotnet pack -c Release", "dotnet nuget push"),
        ("cratesio", "rust", "cargo build --release", "cargo publish"),
    ],
)
def test_render_registry_targets(tmp_path: Path, name, stack, build, needle):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  trigger: workflow_run\n  release_workflow: release\n"
        "  dispatch: true\n  timeout_minutes: 15\n  targets:\n"
        f"    - name: {name}\n      kind: registry\n      stack: \"{stack}\"\n      build: \"{build}\"\n",
    )
    render_deploy_workflows(tmp_path, PLUGIN)
    text = (tmp_path / ".github" / "workflows" / f"deploy-{name}.yml").read_text(encoding="utf-8")
    assert "__HARNESS_" not in text
    assert "timeout-minutes: 15" in text
    assert needle in text
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_deploy_render.py -k registry_targets -v`
Expected: FAIL — 템플릿 파일 부재로 `_render_one`이 skip/에러 → assertion 실패

- [ ] **Step 3: npm 템플릿 작성** — `github/deploy.npm.workflow.example.yml`

```yaml
# Deploy (npm) — rendered from flow-config.deploy. Runs after the release workflow (workflow_run)
# or manually. Publishes to npm with provenance. Requires an NPM_TOKEN secret (Automation token).
name: deploy-npm

on:
  workflow_run:
    workflows: ["__HARNESS_RELEASE_WORKFLOW__"]
    types: [completed]
  workflow_dispatch:

concurrency:
  group: deploy-npm-${{ github.ref }}
  cancel-in-progress: false

permissions:
  contents: read
  id-token: write        # npm provenance

jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: __HARNESS_TIMEOUT__
    if: ${{ github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success' }}
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - run: git checkout "$(git describe --tags --abbrev=0)"
      - uses: actions/setup-node@v6
        with:
          node-version: "20"
          registry-url: "https://registry.npmjs.org"
      - name: Build
        run: __HARNESS_BUILD__
      - name: Publish to npm
        run: npm publish --provenance --access public
        env:
          NODE_AUTH_TOKEN: ${{ secrets.NPM_TOKEN }}
```

- [ ] **Step 4: Maven Central 템플릿 작성** — `github/deploy.maven-central.workflow.example.yml`

```yaml
# Deploy (Maven Central) — rendered from flow-config.deploy. Runs after the release workflow or
# manually. Builds and deploys to Central. Requires MAVEN_CENTRAL_USERNAME / MAVEN_CENTRAL_PASSWORD
# (Central portal token) and, for signed artifacts, MAVEN_GPG_PRIVATE_KEY / MAVEN_GPG_PASSPHRASE.
name: deploy-maven-central

on:
  workflow_run:
    workflows: ["__HARNESS_RELEASE_WORKFLOW__"]
    types: [completed]
  workflow_dispatch:

concurrency:
  group: deploy-maven-central-${{ github.ref }}
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: __HARNESS_TIMEOUT__
    if: ${{ github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success' }}
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - run: git checkout "$(git describe --tags --abbrev=0)"
      - uses: actions/setup-java@v5
        with:
          distribution: temurin
          java-version: "21"
      - name: Build package
        run: __HARNESS_BUILD__
      - name: Deploy to Maven Central
        run: mvn -B -DskipTests deploy
        env:
          MAVEN_CENTRAL_USERNAME: ${{ secrets.MAVEN_CENTRAL_USERNAME }}
          MAVEN_CENTRAL_PASSWORD: ${{ secrets.MAVEN_CENTRAL_PASSWORD }}
```

- [ ] **Step 5: NuGet 템플릿 작성** — `github/deploy.nuget.workflow.example.yml`

```yaml
# Deploy (NuGet) — rendered from flow-config.deploy. Runs after the release workflow or manually.
# Packs and pushes to nuget.org. Requires a NUGET_API_KEY secret.
name: deploy-nuget

on:
  workflow_run:
    workflows: ["__HARNESS_RELEASE_WORKFLOW__"]
    types: [completed]
  workflow_dispatch:

concurrency:
  group: deploy-nuget-${{ github.ref }}
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: __HARNESS_TIMEOUT__
    if: ${{ github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success' }}
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - run: git checkout "$(git describe --tags --abbrev=0)"
      - uses: actions/setup-dotnet@v4
        with:
          dotnet-version: "8.0"
      - name: Pack
        run: __HARNESS_BUILD__
      - name: Push to NuGet
        run: dotnet nuget push "**/*.nupkg" --api-key "${{ secrets.NUGET_API_KEY }}" --source https://api.nuget.org/v3/index.json --skip-duplicate
```

- [ ] **Step 6: crates.io 템플릿 작성** — `github/deploy.cratesio.workflow.example.yml`

```yaml
# Deploy (crates.io) — rendered from flow-config.deploy. Runs after the release workflow or manually.
# Publishes the crate. Requires a CARGO_REGISTRY_TOKEN secret.
name: deploy-cratesio

on:
  workflow_run:
    workflows: ["__HARNESS_RELEASE_WORKFLOW__"]
    types: [completed]
  workflow_dispatch:

concurrency:
  group: deploy-cratesio-${{ github.ref }}
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: __HARNESS_TIMEOUT__
    if: ${{ github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success' }}
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - run: git checkout "$(git describe --tags --abbrev=0)"
      - uses: dtolnay/rust-toolchain@stable
      - name: Build
        run: __HARNESS_BUILD__
      - name: Publish to crates.io
        run: cargo publish --token "${{ secrets.CARGO_REGISTRY_TOKEN }}"
```

- [ ] **Step 7: 테스트 통과 확인**

Run: `uv run pytest tests/test_deploy_render.py -k registry_targets -v`
Expected: PASS (4 passed)

- [ ] **Step 8: Commit** — `/flow` 분류 후

```bash
git add github/deploy.npm.workflow.example.yml github/deploy.maven-central.workflow.example.yml github/deploy.nuget.workflow.example.yml github/deploy.cratesio.workflow.example.yml tests/test_deploy_render.py
git commit -m "feat(deploy): add npm, Maven Central, NuGet, crates.io registry templates"
```

---

## Task 4: 이미지 템플릿 (GHCR · Docker Hub)

**Files:**
- Create: `github/deploy.ghcr.workflow.example.yml`, `github/deploy.dockerhub.workflow.example.yml`
- Modify: `scripts/flow_init_setup.py` (`DEPLOY_TEMPLATE_BY_KIND_STACK`에 Docker Hub 항목 — Task 2에서
  GHCR만 매핑했으므로 Docker Hub 구분 필요)
- Test: `tests/test_deploy_render.py`

**Interfaces:**
- Consumes: `render_deploy_workflows` (Task 2).
- 매핑 갱신: `(image, docker)`는 GHCR가 기본. Docker Hub는 타깃 `name`으로 구분하지 않고, 별도 stack 값
  `docker-hub`을 쓴다 → `DEPLOY_TEMPLATE_BY_KIND_STACK[("image", "docker-hub")]`.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_deploy_render.py`에 추가

```python
def test_render_ghcr_image(tmp_path: Path):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  trigger: workflow_run\n  release_workflow: release\n"
        "  dispatch: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: ghcr\n      kind: image\n      stack: docker\n"
        "      image: \"ghcr.io/acme/app\"\n",
    )
    render_deploy_workflows(tmp_path, PLUGIN)
    text = (tmp_path / ".github" / "workflows" / "deploy-ghcr.yml").read_text(encoding="utf-8")
    assert "__HARNESS_" not in text
    assert "ghcr.io/acme/app" in text
    assert "packages: write" in text                 # GHCR uses GITHUB_TOKEN + packages:write
    assert "docker/build-push-action" in text


def test_render_dockerhub_image(tmp_path: Path):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  trigger: workflow_run\n  release_workflow: release\n"
        "  dispatch: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: dockerhub\n      kind: image\n      stack: docker-hub\n"
        "      image: \"acme/app\"\n",
    )
    render_deploy_workflows(tmp_path, PLUGIN)
    text = (tmp_path / ".github" / "workflows" / "deploy-dockerhub.yml").read_text(encoding="utf-8")
    assert "acme/app" in text
    assert "DOCKERHUB_TOKEN" in text
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_deploy_render.py -k "ghcr_image or dockerhub_image" -v`
Expected: FAIL — 템플릿 부재 / Docker Hub 매핑 없음

- [ ] **Step 3: GHCR 템플릿 작성** — `github/deploy.ghcr.workflow.example.yml`

```yaml
# Deploy (GHCR image) — rendered from flow-config.deploy. Runs after the release workflow or
# manually. Builds a container image and pushes it to GitHub Container Registry using the built-in
# GITHUB_TOKEN (no extra secret needed — just packages: write).
name: deploy-ghcr

on:
  workflow_run:
    workflows: ["__HARNESS_RELEASE_WORKFLOW__"]
    types: [completed]
  workflow_dispatch:

concurrency:
  group: deploy-ghcr-${{ github.ref }}
  cancel-in-progress: false

permissions:
  contents: read
  packages: write

jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: __HARNESS_TIMEOUT__
    if: ${{ github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success' }}
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - run: git checkout "$(git describe --tags --abbrev=0)"
      - name: Resolve released tag
        id: tag
        run: echo "tag=$(git describe --tags --abbrev=0)" >> "$GITHUB_OUTPUT"
      - uses: docker/login-action@v3
        with:
          registry: ghcr.io
          username: ${{ github.actor }}
          password: ${{ secrets.GITHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: |
            __HARNESS_IMAGE__:${{ steps.tag.outputs.tag }}
            __HARNESS_IMAGE__:latest
```

- [ ] **Step 4: Docker Hub 템플릿 작성** — `github/deploy.dockerhub.workflow.example.yml`

```yaml
# Deploy (Docker Hub image) — rendered from flow-config.deploy. Runs after the release workflow or
# manually. Requires DOCKERHUB_USERNAME and DOCKERHUB_TOKEN secrets.
name: deploy-dockerhub

on:
  workflow_run:
    workflows: ["__HARNESS_RELEASE_WORKFLOW__"]
    types: [completed]
  workflow_dispatch:

concurrency:
  group: deploy-dockerhub-${{ github.ref }}
  cancel-in-progress: false

permissions:
  contents: read

jobs:
  deploy:
    runs-on: ubuntu-latest
    timeout-minutes: __HARNESS_TIMEOUT__
    if: ${{ github.event_name == 'workflow_dispatch' || github.event.workflow_run.conclusion == 'success' }}
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - run: git checkout "$(git describe --tags --abbrev=0)"
      - name: Resolve released tag
        id: tag
        run: echo "tag=$(git describe --tags --abbrev=0)" >> "$GITHUB_OUTPUT"
      - uses: docker/login-action@v3
        with:
          username: ${{ secrets.DOCKERHUB_USERNAME }}
          password: ${{ secrets.DOCKERHUB_TOKEN }}
      - uses: docker/build-push-action@v6
        with:
          context: .
          push: true
          tags: |
            __HARNESS_IMAGE__:${{ steps.tag.outputs.tag }}
            __HARNESS_IMAGE__:latest
```

- [ ] **Step 5: Docker Hub 매핑 추가** — `scripts/flow_init_setup.py` 의 `DEPLOY_TEMPLATE_BY_KIND_STACK`에 한 줄

```python
    ("image", "docker-hub"): "github/deploy.dockerhub.workflow.example.yml",
```

- [ ] **Step 6: 테스트 통과 확인**

Run: `uv run pytest tests/test_deploy_render.py -k "ghcr_image or dockerhub_image" -v`
Expected: PASS (2 passed)

- [ ] **Step 7: Commit** — `/flow` 분류 후

```bash
git add github/deploy.ghcr.workflow.example.yml github/deploy.dockerhub.workflow.example.yml scripts/flow_init_setup.py tests/test_deploy_render.py
git commit -m "feat(deploy): add GHCR and Docker Hub image templates"
```

---

## Task 5: 트리거 분기 (`release: published` opt-in)

**Files:**
- Modify: `scripts/flow_init_setup.py` (`render_deploy_workflows` — `trigger` 값에 따라 `on:` 블록 치환)
- Modify: 모든 `github/deploy.*.workflow.example.yml` (`on:` 블록을 `__HARNESS_ON_BLOCK__` 플레이스홀더로 교체)
- Test: `tests/test_deploy_render.py`

**Interfaces:**
- Consumes: `render_deploy_workflows` (Task 2).
- 변경: `__HARNESS_RELEASE_WORKFLOW__` 를 감싸던 `on:` 블록 전체를 `__HARNESS_ON_BLOCK__` 하나로 치환하고,
  렌더 시 `trigger`(+`dispatch`)에 따라 두 형태 중 하나를 주입.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_deploy_render.py`에 추가

```python
def test_trigger_release_published(tmp_path: Path):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  trigger: release\n  release_workflow: release\n"
        "  dispatch: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: pypi\n      kind: registry\n      stack: python\n      build: \"uv build\"\n",
    )
    render_deploy_workflows(tmp_path, PLUGIN)
    text = (tmp_path / ".github" / "workflows" / "deploy-pypi.yml").read_text(encoding="utf-8")
    assert "release:" in text and "types: [published]" in text
    assert "workflow_run:" not in text
    assert "workflow_dispatch:" in text                # dispatch: true → 여전히 포함


def test_trigger_workflow_run_default(tmp_path: Path):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  trigger: workflow_run\n  release_workflow: release\n"
        "  dispatch: false\n  timeout_minutes: 15\n  targets:\n"
        "    - name: pypi\n      kind: registry\n      stack: python\n      build: \"uv build\"\n",
    )
    render_deploy_workflows(tmp_path, PLUGIN)
    text = (tmp_path / ".github" / "workflows" / "deploy-pypi.yml").read_text(encoding="utf-8")
    assert "workflow_run:" in text
    assert "workflow_dispatch:" not in text            # dispatch: false → 제외
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_deploy_render.py -k "trigger_" -v`
Expected: FAIL — 현재 템플릿은 `on:` 고정, `release` 트리거/`dispatch:false` 미반영

- [ ] **Step 3: 모든 deploy 템플릿의 `on:` 블록을 플레이스홀더로 교체**

각 `github/deploy.*.workflow.example.yml`에서 아래 블록을

```yaml
on:
  workflow_run:
    workflows: ["__HARNESS_RELEASE_WORKFLOW__"]
    types: [completed]
  workflow_dispatch:
```

다음 한 줄로 교체:

```yaml
__HARNESS_ON_BLOCK__
```

- [ ] **Step 4: `render_deploy_workflows`에 `on:` 블록 빌더 추가** — subs 구성 직전에

```python
        if trigger == "release":
            on_lines = ["on:", "  release:", "    types: [published]"]
        else:  # workflow_run (default)
            on_lines = [
                "on:",
                "  workflow_run:",
                f'    workflows: ["{release_wf}"]',
                "    types: [completed]",
            ]
        if d.get("dispatch", True):
            on_lines.append("  workflow_dispatch:")
        subs = {
            "__HARNESS_ON_BLOCK__": "\n".join(on_lines),
            "__HARNESS_TIMEOUT__": timeout,
            "__HARNESS_BUILD__": str(t.get("build", "")),
            "__HARNESS_IMAGE__": str(t.get("image", "")),
        }
```

> NOTE: `release: published`는 기본 GITHUB_TOKEN에서 안 뜬다 → RELEASE_TOKEN(PAT) 필요. 스킬(Task 7)이
> 이 선택지를 RELEASE_TOKEN 감지 시에만 제시하고 deploy-guide에 명시한다. `if:` 의
> `github.event.workflow_run.conclusion` 참조는 release 트리거일 때 `github.event_name == 'workflow_dispatch'`
> 로만 통과되고, release 이벤트에선 conclusion이 없어 항상 배포된다(published는 성공 릴리스에서만 발생하므로 안전).

- [ ] **Step 5: 전체 렌더 테스트 재실행**(기존 테스트 회귀 없음 확인)

Run: `uv run pytest tests/test_deploy_render.py -v`
Expected: PASS (전체)

- [ ] **Step 6: Commit** — `/flow` 분류 후

```bash
git add github/deploy.*.workflow.example.yml scripts/flow_init_setup.py tests/test_deploy_render.py
git commit -m "feat(deploy): support release-published trigger opt-in and dispatch toggle"
```

---

## Task 6: flow-init 배선 (setup 재동기화 + `--render-deploy` 플래그)

**Files:**
- Modify: `scripts/flow_init_setup.py` (`main()` setup 경로에 `render_deploy_workflows` 호출 + argparse 플래그)
- Test: `tests/test_deploy_render.py`

**Interfaces:**
- Consumes: `render_deploy_workflows` (Task 2), 기존 `main()` / argparse.
- Produces: `python scripts/flow_init_setup.py --render-deploy` → deploy 워크플로우만 렌더(스킬이 호출).
  기존 setup(무플래그)도 deploy를 재동기화.

- [ ] **Step 1: 실패하는 테스트 작성** — `tests/test_deploy_render.py`에 추가

```python
import subprocess
import sys


def test_render_deploy_flag_renders_only_deploy(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  trigger: workflow_run\n  release_workflow: release\n"
        "  dispatch: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: pypi\n      kind: registry\n      stack: python\n      build: \"uv build\"\n",
    )
    result = subprocess.run(
        [sys.executable, "scripts/flow_init_setup.py", "--render-deploy"],
        cwd=str(PLUGIN), capture_output=True, text=True,
    )
    assert result.returncode == 0
    assert (tmp_path / ".github" / "workflows" / "deploy-pypi.yml").exists()
```

- [ ] **Step 2: 실패 확인**

Run: `uv run pytest tests/test_deploy_render.py -k render_deploy_flag -v`
Expected: FAIL — `--render-deploy` 플래그 미인식(argparse 에러) 또는 파일 미생성

- [ ] **Step 3: argparse 플래그 + main 배선** — `scripts/flow_init_setup.py`의 argparse/main

argparse 정의에 추가:

```python
    parser.add_argument(
        "--render-deploy",
        action="store_true",
        help="Render only the deploy workflows from flow-config.deploy (called by /harness-deployments).",
    )
```

`main()`에서 `--uninstall` 분기 이전에 `--render-deploy` 단독 처리:

```python
    if args.render_deploy:
        host = host_root()
        plugin = plugin_root()
        for line in render_deploy_workflows(host, plugin):
            print(line)
        return
```

기존 setup 경로(무플래그) 끝부분, `render_versioning_workflows`/`render_unit_test_workflow` 호출 옆에 추가:

```python
    for line in render_deploy_workflows(host, plugin):
        print(line)
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/test_deploy_render.py -k render_deploy_flag -v`
Expected: PASS

- [ ] **Step 5: 전체 회귀 확인**

Run: `uv run pytest tests/test_flow_init_setup.py tests/test_deploy_render.py -v`
Expected: PASS (전체)

- [ ] **Step 6: Commit** — `/flow` 분류 후

```bash
git add scripts/flow_init_setup.py tests/test_deploy_render.py
git commit -m "feat(deploy): wire deploy render into flow-init setup and --render-deploy flag"
```

---

## Task 7: `/harness-deployments` 스킬 (SKILL.md)

**Files:**
- Create: `skills/harness-deployments/SKILL.md`

**Interfaces:**
- Consumes: `python scripts/flow_init_setup.py --render-deploy` (Task 6), references/(Task 8).
- 단위 테스트 없음(스킬 문서 — 모델 주도). 승인 기준: frontmatter 유효 + 실행 흐름 5단계 명시 + 가드/brownfield
  규칙 포함. `flow-init`/`harness-init` SKILL.md 관례를 따른다.

- [ ] **Step 1: SKILL.md 작성** — frontmatter는 `flow-init` 관례를 그대로 따름

```markdown
---
name: harness-deployments
description: Detect the host stack and add a deployment layer on top of the release workflow — interactively pick targets (registry publish / container image / app deploy), then render or author the CI deploy workflow(s), write the flow-config deploy block, and generate the ops guide. Requires /flow-init to have run first.
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion, Glob, Grep
argument-hint: (none)
disable-model-invocation: true
---

# Harness-Deployments — 배포 계층 셋업

`/flow-init` 이후에 실행한다. 릴리스(태그+노트) 위에 배포(레지스트리 발행·이미지·앱 배포)를 얹는다.
실제 배포는 CI가 실행하며, 이 스킬은 감지·질문·생성만 한다(호스트에서 직접 배포하지 않음).

## Path conventions
- 읽기(템플릿/reference): `${CLAUDE_PLUGIN_ROOT}/...`
- 호스트 쓰기: `${CLAUDE_PROJECT_DIR}/.github/workflows/`, `.../.claude/harness-tier/config/flow-config.yaml`, `.../docs/`
- **플러그인 디렉터리엔 쓰지 않는다.**

## Execution

### 0. 가드 (하드 스톱)
- `${CLAUDE_PROJECT_DIR}/.claude/harness-tier/config/flow-config.yaml` 이 없으면 →
  "먼저 `/flow-init`을 실행하라"고 안내하고 중단.

### 1. 감지
- stack: flow-config의 `versioning.release_tool` / `version_files` / `modules[].checks` 언어.
- 산출물: `Dockerfile` 존재? 패키지 라이브러리(`pyproject.toml`/`package.json`/`Cargo.toml`/`pom.xml`/`*.csproj`)?
- 기존 배포: `.github/workflows/*` 에서 이미 있는 publish/deploy 스텝(Grep).
- 시크릿: 가능하면 `gh secret list` → `RELEASE_TOKEN` 존재 여부 기록(트리거 기본값 판단).

### 2. Q&A (AskUserQuestion, 적응형)
- 감지된 후보를 제시하고 배포 타깃을 고르게 한다("Dockerfile 발견 → GHCR? pyproject → PyPI?").
- 타깃별: 인증(OIDC vs token), 브랜치/이미지명.
- 트리거: 기본 `workflow_run` + `workflow_dispatch`. `RELEASE_TOKEN` 감지 시에만 `release: published` 제시.
- brownfield: 기존 배포 발견 시 채택/증강/교체 중 선택(조용히 덮어쓰지 않음).

### 3. 생성
- `flow-config.yaml`에 `deploy:` 블록 작성/갱신(팀 공유·git 추적).
- 정적 템플릿 대상(kind registry/image + 매핑된 stack): `python "${CLAUDE_PROJECT_DIR}/.claude/harness-tier/scripts/flow_init_setup.py" --render-deploy` 를 호출해 렌더(호스트 카피 스크립트).
- 앱 배포(kind app) / 매핑 없는 조합: `references/app-deploy/*` 레시피로 `.github/workflows/deploy-<name>.yml` 를 직접 저작.
- `docs/operations/deploy-guide.md` 작성(설정할 시크릿·트리거 동작·RELEASE_TOKEN 주의·롤백 포인터).

### 4. 보고
- 생성/변경 파일, repo admin이 설정할 시크릿, 발견된 충돌을 요약.

## Reuse before build
- 각 stack은 공식 액션을 우선 사용(pypa/gh-action-pypi-publish, docker/build-push-action 등 — references 참조).
- 유료 서비스 권장 시 명시적으로 비용/라이선스를 알린다.
```

- [ ] **Step 2: frontmatter 유효성 확인** — YAML 파싱 + 필수 키

Run: `uv run python -c "import yaml,sys; d=yaml.safe_load(open('skills/harness-deployments/SKILL.md',encoding='utf-8').read().split('---')[1]); assert d['name']=='harness-deployments' and 'description' in d and d['disable-model-invocation'] is True; print('ok')"`
Expected: `ok`

- [ ] **Step 3: Commit** — `/flow` 분류 후

```bash
git add skills/harness-deployments/SKILL.md
git commit -m "feat(deploy): add /harness-deployments skill (detect, ask, generate)"
```

---

## Task 8: references 번들 (분류별 레시피)

**Files:**
- Create: `skills/harness-deployments/references/registry-publish/{python-pypi,node-npm,java-maven-central,dotnet-nuget,rust-cratesio}.md`
- Create: `skills/harness-deployments/references/container-image/{docker-ghcr,docker-hub}.md`
- Create: `skills/harness-deployments/references/app-deploy/{ssh-server,kubernetes,cloud-run,ecs}.md`
- Create: `skills/harness-deployments/references/_trigger-and-secrets.md`

**Interfaces:**
- Consumes: Task 7의 스킬이 참조. 단위 테스트 없음. 승인 기준: 각 파일이 (a) 공식 액션/명령, (b) 필요한
  시크릿, (c) OIDC 대안(해당 시), (d) 주의점을 포함. app-deploy 파일은 스킬이 저작할 워크플로우 스켈레톤 포함.

- [ ] **Step 1: 각 registry-publish 레시피 작성**

각 파일은 다음을 담는다(예: `python-pypi.md`):
- 공식 액션: `pypa/gh-action-pypi-publish@release/v1`
- 빌드 명령 예: `uv build` / `python -m build`
- 시크릿: OIDC trusted publishing(권장, `id-token: write`) 또는 `PYPI_API_TOKEN`
- 주의: trusted publisher를 PyPI 프로젝트 설정에 등록해야 OIDC 동작
- 대응 템플릿: `github/deploy.pypi.workflow.example.yml`

나머지(`node-npm`·`java-maven-central`·`dotnet-nuget`·`rust-cratesio`)도 동일 구조로, 각 stack의 공식 액션·
빌드 명령·시크릿·대응 템플릿을 명시.

- [ ] **Step 2: container-image 레시피 작성**
- `docker-ghcr.md`: `docker/login-action`(ghcr.io, GITHUB_TOKEN, `packages: write`) + `docker/build-push-action`, 시크릿 불필요.
- `docker-hub.md`: `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` 시크릿 필요.

- [ ] **Step 3: app-deploy 레시피 작성(저작용 스켈레톤 포함)**

각 파일은 **템플릿이 아니라 스킬이 저작할 워크플로우 스켈레톤 + 결정 포인트**를 담는다:
- `ssh-server.md`: `appleboy/ssh-action` 또는 rsync-over-ssh, `SSH_HOST`/`SSH_KEY` 시크릿, 무중단 배포 노트.
- `kubernetes.md`: `azure/setup-kubectl` + `kubectl set image`/`kustomize`, `KUBE_CONFIG` 시크릿, 롤백(`kubectl rollout undo`).
- `cloud-run.md`: `google-github-actions/deploy-cloudrun`, WIF(OIDC) 권장, 프로젝트/리전.
- `ecs.md`: `aws-actions/amazon-ecs-deploy-task-definition`, OIDC 역할 assume.
공통: 각 파일에 `on: __HARNESS_ON_BLOCK__ 상당`의 트리거·`timeout-minutes`·"released tag 체크아웃" 스텝을
포함하도록 지시(정적 템플릿과 동일 규약).

- [ ] **Step 4: `_trigger-and-secrets.md` 작성** — 횡단 가이드
- GITHUB_TOKEN 재귀 방지 → `release: published`는 RELEASE_TOKEN 필요; `workflow_run`/`workflow_dispatch`는
  기본 토큰에서 동작(출처 링크 2개).
- `workflow_run`은 deploy 파일이 기본 브랜치에 있어야 발생.
- OIDC를 장수 토큰보다 우선.

- [ ] **Step 5: 파일 존재/구조 스모크 체크**

Run: `uv run python -c "import pathlib; base=pathlib.Path('skills/harness-deployments/references'); need=['registry-publish/python-pypi.md','container-image/docker-ghcr.md','app-deploy/kubernetes.md','_trigger-and-secrets.md']; [print(p, base.joinpath(p).exists()) for p in need]; assert all(base.joinpath(p).exists() for p in need)"`
Expected: 모두 `True`

- [ ] **Step 6: Commit** — `/flow` 분류 후

```bash
git add skills/harness-deployments/references/
git commit -m "feat(deploy): add deployment reference recipes by category"
```

---

## Task 9: 문서 반영 (CLAUDE.md · USAGE)

**Files:**
- Modify: `CLAUDE.md` (Folder structure / Architecture — 배포 계층 한 줄)
- Modify: `USAGE.md`, `USAGE.ko.md` (`/harness-deployments` 사용 절)

**Interfaces:**
- 단위 테스트 없음. 승인 기준: 문서가 스킬의 순서(flow-init → harness-deployments)와 산출물, 트리거 기본값을
  정확히 기술.

- [ ] **Step 1: `CLAUDE.md` 갱신**
- `skills/` 목록에 `harness-deployments` 한 줄 추가.
- `github/` 설명에 `deploy.*.workflow.example.yml`(deploy SOURCE, `/harness-deployments`가 렌더) 추가.
- Architecture의 "Three verification layers" 문단 인접에 배포 계층이 릴리스와 분리된 opt-in임을 한 줄 명시.

- [ ] **Step 2: `USAGE.md`/`USAGE.ko.md` 갱신**
- 순서: `/harness-init` → `/flow-init` → **`/harness-deployments`**.
- 무설정 동작(기본 workflow_run+dispatch, GITHUB_TOKEN), `release: published`는 RELEASE_TOKEN 필요.
- 산출물: `deploy-<name>.yml` + `flow-config.deploy` + `docs/operations/deploy-guide.md`.

- [ ] **Step 3: 링크/렌더 스모크 체크** (마크다운 깨짐 없음, 상호 참조 존재)

Run: `uv run python -c "import pathlib; t=pathlib.Path('USAGE.md').read_text(encoding='utf-8'); assert 'harness-deployments' in t; print('ok')"`
Expected: `ok`

- [ ] **Step 4: Commit** — `/flow` 분류 후

```bash
git add CLAUDE.md USAGE.md USAGE.ko.md
git commit -m "feat(deploy): document /harness-deployments in CLAUDE.md and USAGE"
```

---

## Task 10: 전체 검증 & 정적 분석

**Files:** (없음 — 검증 전용)

- [ ] **Step 1: 전체 테스트**

Run: `uv run pytest`
Expected: PASS (신규 `test_deploy_render.py` 포함 전체)

- [ ] **Step 2: 린트/포맷**

Run: `uv run ruff check && uv run ruff format --check`
Expected: 통과

- [ ] **Step 3: 렌더 스모크(엔드투엔드)** — 임시 호스트에서 `--render-deploy`가 유효한 YAML을 만드는지

Run:
```bash
uv run python -c "import yaml,glob; [yaml.safe_load(open(f,encoding='utf-8').read().replace('__HARNESS_ON_BLOCK__','on:\n  workflow_dispatch:').replace('__HARNESS_TIMEOUT__','15').replace('__HARNESS_BUILD__','x').replace('__HARNESS_IMAGE__','x').replace('__HARNESS_RELEASE_WORKFLOW__','release')) for f in glob.glob('github/deploy.*.workflow.example.yml')]; print('all templates parse')"
```
Expected: `all templates parse`

- [ ] **Step 4: pre-commit 전체**

Run: `uv run pre-commit run --all-files`
Expected: 통과

- [ ] **Step 5: 최종 Commit**(변경 있으면) — `/flow` 분류 후

```bash
git add -A
git commit -m "feat(deploy): finalize harness-deployments layer"
```

---

## Self-Review 결과

- **Spec 커버리지**: §5 스키마→Task 1; §6 템플릿/파일배치→Task 2·3·4·8; §7 실행흐름→Task 7; §7A 트리거/토큰→Task 5·8;
  §8 brownfield→Task 7(감지·비파괴); §9 테스트→Task 1~6·10; §11 렌더 스크립트 위치(열린 질문)→**해소**(flow_init_setup 확장).
- **Placeholder 스캔**: 모든 코드/템플릿 스텝은 실제 내용 포함. "적절히 처리" 류 없음.
- **타입 일관성**: `load_deploy_config`·`render_deploy_workflows`·`DEPLOY_TEMPLATE_BY_KIND_STACK`·`_render_one`
  시그니처가 Task 1~6 전반에서 일치. 템플릿 플레이스홀더(`__HARNESS_ON_BLOCK__`/`_TIMEOUT_`/`_BUILD_`/`_IMAGE_`/`_RELEASE_WORKFLOW_`)가 Task 2/5 렌더 subs와 일치.
- **미테스트 구간**(app-deploy 저작·스킬/references 문서): 모델 주도라 단위 테스트 대신 승인 기준 + `harness-critic`
  리뷰로 가드(접근 3의 인정된 트레이드오프).
