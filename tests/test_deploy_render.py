import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts.flow_init_setup import load_deploy_config, render_deploy_workflows

PLUGIN = Path(__file__).resolve().parents[1]  # repo root (plugin source)


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
        "deploy:\n  enable: true\n  targets:\n"
        "    - name: pypi\n      target: pypi\n      auth: oidc\n",
    )
    cfg = load_deploy_config(tmp_path)
    assert cfg is not None
    assert cfg["enable"] is True
    assert cfg["targets"][0]["name"] == "pypi"
    assert cfg["targets"][0]["target"] == "pypi"


def test_load_deploy_config_broken_yaml_returns_none(tmp_path: Path):
    _write_config(tmp_path, "deploy: : : broken\n")
    assert load_deploy_config(tmp_path) is None


def test_load_deploy_config_maven_and_custom_targets(tmp_path: Path):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  targets:\n"
        "    - name: central\n      target: maven-central\n"
        "      build_tool: gradle\n"
        '      publish: "./gradlew publishAndReleaseToMavenCentral --no-configuration-cache"\n'
        "    - name: ecs\n      target: custom\n"
        "      workflow: ./.github/workflows/deploy-ecs.yml\n"
        "      permissions:\n        contents: read\n        id-token: write\n",
    )
    cfg = load_deploy_config(tmp_path)
    assert cfg is not None
    maven, custom = cfg["targets"]
    assert maven["target"] == "maven-central"
    assert maven["build_tool"] == "gradle"
    assert maven["publish"] == "./gradlew publishAndReleaseToMavenCentral --no-configuration-cache"
    assert custom["target"] == "custom"
    assert custom["permissions"] == {"contents": "read", "id-token": "write"}


def test_render_pypi_produces_workflow(tmp_path: Path):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        '    - name: pypi\n      target: pypi\n      build: "uv build"\n',
    )
    render_deploy_workflows(tmp_path, PLUGIN)
    wf = tmp_path / ".github" / "workflows" / "deploy-pypi.yml"
    text = wf.read_text(encoding="utf-8")
    assert "__HARNESS_" not in text  # 모든 플레이스홀더 치환됨
    assert "timeout-minutes: 15" in text
    assert "workflow_call:" in text
    assert "inputs:" in text and "tag:" in text
    assert "workflow_dispatch:" in text
    assert "ref: ${{ inputs.tag }}" in text
    assert "workflow_run:" not in text
    assert "git describe" not in text
    assert "uv build" in text


def test_render_disabled_skips(tmp_path: Path):
    _write_config(tmp_path, "deploy:\n  enable: false\n  targets: []\n")
    out = render_deploy_workflows(tmp_path, PLUGIN)
    assert not (tmp_path / ".github" / "workflows" / "deploy-pypi.yml").exists()
    assert any("enable=false" in line for line in out)


def test_render_deploy_idempotent_nondestructive(tmp_path: Path):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        '    - name: pypi\n      target: pypi\n      build: "uv build"\n',
    )
    render_deploy_workflows(tmp_path, PLUGIN)
    wf = tmp_path / ".github" / "workflows" / "deploy-pypi.yml"
    wf.write_text("# hand-edited\n", encoding="utf-8")  # 사용자 커스텀
    render_deploy_workflows(tmp_path, PLUGIN)  # 재실행
    assert wf.read_text(encoding="utf-8") == "# hand-edited\n"  # 덮어쓰지 않음


@pytest.mark.parametrize(
    "name,target,build,needle",
    [
        ("npm", "npm", "npm ci && npm run build", "npm publish"),
        (
            "maven-central",
            "maven-central",
            "mvn -B -DskipTests package",
            "mvn -B -DskipTests deploy",
        ),
        ("nuget", "nuget", "dotnet pack -c Release", "dotnet nuget push"),
        ("cratesio", "cratesio", "cargo build --release", "cargo publish"),
    ],
)
def test_render_registry_targets(tmp_path: Path, name, target, build, needle):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        f"    - name: {name}\n      target: {target}\n"
        f'      build: "{build}"\n',
    )
    render_deploy_workflows(tmp_path, PLUGIN)
    wf = tmp_path / ".github" / "workflows" / f"deploy-{name}.yml"
    text = wf.read_text(encoding="utf-8")
    assert "__HARNESS_" not in text
    assert "timeout-minutes: 15" in text
    assert needle in text


def test_render_ghcr_image(tmp_path: Path):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: ghcr\n      target: ghcr\n"
        '      image: "ghcr.io/acme/app"\n',
    )
    render_deploy_workflows(tmp_path, PLUGIN)
    text = (tmp_path / ".github" / "workflows" / "deploy-ghcr.yml").read_text(encoding="utf-8")
    assert "__HARNESS_" not in text
    assert "ghcr.io/acme/app" in text
    assert "packages: write" in text  # GHCR uses GITHUB_TOKEN + packages:write
    assert "docker/build-push-action" in text
    assert "context:" in text
    assert "file: ./Dockerfile" in text  # default context "." → "./Dockerfile", never empty
    assert "${{ inputs.tag }}" in text


def test_render_dockerhub_image(tmp_path: Path):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: dockerhub\n      target: dockerhub\n"
        '      image: "acme/app"\n',
    )
    render_deploy_workflows(tmp_path, PLUGIN)
    text = (tmp_path / ".github" / "workflows" / "deploy-dockerhub.yml").read_text(encoding="utf-8")
    assert "acme/app" in text
    assert "DOCKERHUB_TOKEN" in text
    assert "context:" in text
    assert "file: ./Dockerfile" in text
    assert "${{ inputs.tag }}" in text
    assert "__HARNESS_" not in text


def test_render_image_monorepo_context(tmp_path: Path):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: ghcr\n      target: ghcr\n"
        '      image: "ghcr.io/acme/app"\n      context: services/api\n',
    )
    render_deploy_workflows(tmp_path, PLUGIN)
    text = (tmp_path / ".github" / "workflows" / "deploy-ghcr.yml").read_text(encoding="utf-8")
    assert "context: services/api" in text
    assert "file: services/api/Dockerfile" in text  # computed default is context-relative
    assert "__HARNESS_" not in text


def test_render_version_param(tmp_path: Path):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        '    - name: pypi\n      target: pypi\n      version: "3.11"\n',
    )
    render_deploy_workflows(tmp_path, PLUGIN)
    text = (tmp_path / ".github" / "workflows" / "deploy-pypi.yml").read_text(encoding="utf-8")
    assert 'python-version: "3.11"' in text


def test_render_version_param_default(tmp_path: Path):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: pypi\n      target: pypi\n",
    )
    render_deploy_workflows(tmp_path, PLUGIN)
    text = (tmp_path / ".github" / "workflows" / "deploy-pypi.yml").read_text(encoding="utf-8")
    assert 'python-version: "3.12"' in text


def test_render_gradle_target(tmp_path: Path):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: central\n      target: maven-central\n      build_tool: gradle\n"
        '      publish: "./gradlew publishAndReleaseToMavenCentral --no-configuration-cache"\n',
    )
    render_deploy_workflows(tmp_path, PLUGIN)
    text = (tmp_path / ".github" / "workflows" / "deploy-central.yml").read_text(encoding="utf-8")
    assert "gradle/actions/setup-gradle" in text
    assert "ORG_GRADLE_PROJECT_signingInMemoryKey" in text
    assert "secrets.MAVEN_CENTRAL_USERNAME" in text
    assert "secrets.MAVEN_GPG_PRIVATE_KEY" in text
    assert "./gradlew publishAndReleaseToMavenCentral --no-configuration-cache" in text
    assert "__HARNESS_" not in text


def test_render_maven_default_build_tool(tmp_path: Path):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: central\n      target: maven-central\n",
    )
    render_deploy_workflows(tmp_path, PLUGIN)
    text = (tmp_path / ".github" / "workflows" / "deploy-central.yml").read_text(encoding="utf-8")
    assert "mvn" in text
    assert "MAVEN_CENTRAL_PASSWORD" in text
    assert "__HARNESS_" not in text


def test_render_gradle_missing_publish_skips(tmp_path: Path):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: central\n      target: maven-central\n      build_tool: gradle\n",
    )
    out = render_deploy_workflows(tmp_path, PLUGIN)
    assert not (tmp_path / ".github" / "workflows" / "deploy-central.yml").exists()
    assert any("[!]" in line and "publish" in line for line in out)


# --- orchestrator (deploy.yml) tests -----------------------------------------------------
#
# Note: PyYAML resolves the bare GitHub Actions `on:` key as the boolean `True` (a YAML 1.1
# pitfall), so `data["on"]` raises KeyError — access it as `data[True]` instead.

_ORCH_CONFIG = (
    "deploy:\n  enable: true\n  timeout_minutes: 15\n  order: [pypi, api-image]\n  targets:\n"
    "    - name: pypi\n      target: pypi\n"
    "    - name: api-image\n      target: ghcr\n"
    '      image: "ghcr.io/acme/app"\n'
)


def _render_deploy_yaml(tmp_path: Path, config_body: str) -> dict:
    _write_config(tmp_path, config_body)
    render_deploy_workflows(tmp_path, PLUGIN)
    wf = tmp_path / ".github" / "workflows" / "deploy.yml"
    return yaml.safe_load(wf.read_text(encoding="utf-8"))


def test_orchestrator_generates_valid_deploy_yml(tmp_path: Path):
    data = _render_deploy_yaml(tmp_path, _ORCH_CONFIG)
    on = data[True]
    assert on["workflow_call"]["inputs"]["target"]["default"] == "all"
    assert on["workflow_dispatch"]["inputs"]["target"]["default"] == "all"
    assert on["workflow_call"]["inputs"]["tag"]["required"] is True
    assert on["workflow_dispatch"]["inputs"]["tag"]["required"] is False


def test_orchestrator_resolve_job(tmp_path: Path):
    data = _render_deploy_yaml(tmp_path, _ORCH_CONFIG)
    resolve = data["jobs"]["resolve"]
    assert resolve["timeout-minutes"] == 5
    assert "tag" in resolve["outputs"]
    steps = resolve["steps"]
    assert any("git describe --tags --abbrev=0" in (s.get("run") or "") for s in steps)
    checkout = next(s for s in steps if str(s.get("uses", "")).startswith("actions/checkout"))
    assert "github.event_name == 'workflow_dispatch'" in checkout["if"]


def test_orchestrator_target_job_fields(tmp_path: Path):
    data = _render_deploy_yaml(tmp_path, _ORCH_CONFIG)
    pypi = data["jobs"]["pypi"]
    assert pypi["uses"] == "./.github/workflows/deploy-pypi.yml"
    assert pypi["secrets"] == "inherit"
    assert "resolve" in pypi["needs"]
    assert pypi["with"]["tag"] == "${{ needs.resolve.outputs.tag }}"
    assert "timeout-minutes" not in pypi
    assert "inputs.target == 'all'" in pypi["if"]
    assert "inputs.target == 'pypi'" in pypi["if"]


def test_orchestrator_per_target_permissions(tmp_path: Path):
    data = _render_deploy_yaml(tmp_path, _ORCH_CONFIG)
    assert data["jobs"]["pypi"]["permissions"] == {"contents": "read", "id-token": "write"}
    assert data["jobs"]["api-image"]["permissions"] == {"contents": "read", "packages": "write"}


def test_orchestrator_needs_predecessor_from_order(tmp_path: Path):
    data = _render_deploy_yaml(tmp_path, _ORCH_CONFIG)
    assert data["jobs"]["api-image"]["needs"] == ["resolve", "pypi"]


def test_orchestrator_custom_target(tmp_path: Path):
    data = _render_deploy_yaml(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: ecs\n      target: custom\n"
        "      workflow: ./.github/workflows/deploy-ecs.yml\n"
        "      permissions:\n        contents: read\n        id-token: write\n"
        "      with:\n        cluster: prod\n",
    )
    ecs = data["jobs"]["ecs"]
    assert ecs["uses"] == "./.github/workflows/deploy-ecs.yml"
    assert ecs["permissions"] == {"contents": "read", "id-token": "write"}
    assert ecs["with"]["cluster"] == "prod"
    assert "tag" in ecs["with"]


def test_orchestrator_regenerated_not_preserved(tmp_path: Path):
    """Contrast with test_render_deploy_idempotent_nondestructive: components are preserved
    (skip-if-exists), but the orchestrator is fully generated/managed and overwritten every
    render, so config changes (e.g. a new target) are always reflected."""
    _write_config(tmp_path, _ORCH_CONFIG)
    render_deploy_workflows(tmp_path, PLUGIN)
    wf = tmp_path / ".github" / "workflows" / "deploy.yml"
    wf.write_text("# stale\n", encoding="utf-8")
    render_deploy_workflows(tmp_path, PLUGIN)
    assert wf.read_text(encoding="utf-8") != "# stale\n"


# --- M1: wired-only orchestrator (mapped-but-skipped targets must not dangle) --------------


def test_orchestrator_excludes_gradle_no_publish(tmp_path: Path):
    """A mapped-but-skipped target (maven-central+gradle, no publish) must not get an
    orchestrator job pointing at a component file that was never rendered."""
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: central\n      target: maven-central\n      build_tool: gradle\n",
    )
    out = render_deploy_workflows(tmp_path, PLUGIN)
    assert not (tmp_path / ".github" / "workflows" / "deploy.yml").exists()
    assert any("[!]" in line and "publish" in line for line in out)


def test_orchestrator_mixed_wired_and_skipped(tmp_path: Path):
    """A wired target (pypi) still renders even when a sibling target is skipped
    (maven-central+gradle, no publish) — the skipped one must not appear in jobs."""
    data = _render_deploy_yaml(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: pypi\n      target: pypi\n"
        "    - name: central\n      target: maven-central\n      build_tool: gradle\n",
    )
    assert "pypi" in data["jobs"]
    assert "central" not in data["jobs"]


def test_orchestrator_custom_target_stays_wired(tmp_path: Path):
    """Authored targets (custom/sbt/unknown) have no static template and are wired by
    design — the wired filter must not exclude them."""
    data = _render_deploy_yaml(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: ecs\n      target: custom\n"
        "      workflow: ./.github/workflows/deploy-ecs.yml\n"
        "      permissions:\n        contents: read\n",
    )
    assert "ecs" in data["jobs"]


def test_render_deploy_flag_renders_only_deploy(tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        '    - name: pypi\n      target: pypi\n      build: "uv build"\n',
    )
    result = subprocess.run(
        [sys.executable, "scripts/flow_init_setup.py", "--render-deploy"],
        cwd=str(PLUGIN),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert (tmp_path / ".github" / "workflows" / "deploy-pypi.yml").exists()
