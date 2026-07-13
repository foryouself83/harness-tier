from pathlib import Path

import yaml

from scripts.flow_init_setup import (
    _deploy_union_permissions,
    integrate_release_deploy,
    report_legacy_release_workflow,
)

PLUGIN = Path(__file__).resolve().parents[1]  # repo root (plugin source)

_REL_WITH_MARKERS = (
    "name: release\n"
    "on:\n  push:\n    branches: [main]\n"
    "jobs:\n"
    "  release:\n"
    "    runs-on: ubuntu-latest\n"
    "    timeout-minutes: 15\n"
    "    outputs:\n      tag: ${{ steps.exposetag.outputs.tag }}\n"
    "    steps:\n      - run: echo hi\n"
    "  # __HARNESS_DEPLOY_BEGIN__ (managed)\n"
    "  # __HARNESS_DEPLOY_END__\n"
)

_REL_LEGACY_NO_MARKERS = (
    "name: release\n"
    "on:\n  push:\n    branches: [main]\n"
    "jobs:\n"
    "  release:\n"
    "    runs-on: ubuntu-latest\n"
    "    timeout-minutes: 15\n"
    "    steps:\n      - run: echo hi\n"
)


def _write_config(host: Path, body: str) -> None:
    cfg = host / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "flow-config.yaml").write_text(body, encoding="utf-8")


def _write_release(host: Path, body: str) -> Path:
    wf = host / ".github" / "workflows"
    wf.mkdir(parents=True, exist_ok=True)
    dest = wf / "release.yml"
    dest.write_text(body, encoding="utf-8")
    return dest


# --- union permissions -----------------------------------------------------------------


def test_deploy_union_permissions():
    targets = [
        {"name": "pypi", "target": "pypi"},  # auth omitted -> oidc default -> id-token: write
        {"name": "ghcr", "target": "ghcr"},  # packages: write
        {
            "name": "ecs",
            "target": "custom",
            "permissions": {"contents": "read", "id-token": "write"},
        },
    ]
    perms = _deploy_union_permissions(targets)
    assert perms == {"contents": "read", "id-token": "write", "packages": "write"}


# --- enable -> block filled --------------------------------------------------------------


def test_integrate_release_deploy_enable_fills_block(tmp_path: Path):
    _write_release(tmp_path, _REL_WITH_MARKERS)
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: pypi\n      target: pypi\n"
        "    - name: ghcr\n      target: ghcr\n",
    )
    out = integrate_release_deploy(tmp_path, PLUGIN)
    assert any("[+]" in line for line in out)
    text = (tmp_path / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    deploy = data["jobs"]["deploy"]
    assert deploy["needs"] == ["release"]
    assert deploy["if"] == "${{ needs.release.outputs.tag != '' }}"
    assert deploy["permissions"]["id-token"] == "write"
    assert deploy["permissions"]["packages"] == "write"
    assert deploy["uses"] == "./.github/workflows/deploy.yml"
    assert deploy["with"]["tag"] == "${{ needs.release.outputs.tag }}"
    assert deploy["secrets"] == "inherit"
    assert "timeout-minutes" not in deploy


# --- disable -> block emptied, markers kept -----------------------------------------------


def test_integrate_release_deploy_disable_empties_block(tmp_path: Path):
    _write_release(tmp_path, _REL_WITH_MARKERS)
    _write_config(tmp_path, "deploy:\n  enable: false\n  targets: []\n")
    out = integrate_release_deploy(tmp_path, PLUGIN)
    assert any("[=]" in line for line in out)
    text = (tmp_path / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert "deploy" not in data["jobs"]
    assert "__HARNESS_DEPLOY_BEGIN__" in text
    assert "__HARNESS_DEPLOY_END__" in text


# --- idempotent ------------------------------------------------------------------------


def test_integrate_release_deploy_idempotent(tmp_path: Path):
    _write_release(tmp_path, _REL_WITH_MARKERS)
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: pypi\n      target: pypi\n",
    )
    integrate_release_deploy(tmp_path, PLUGIN)
    integrate_release_deploy(tmp_path, PLUGIN)
    text = (tmp_path / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert text.count("deploy:") == 1
    data = yaml.safe_load(text)  # parses ok
    assert data["jobs"]["deploy"]["uses"] == "./.github/workflows/deploy.yml"


# --- M1: only wired targets get a release deploy job ----------------------------------------


def test_integrate_release_deploy_no_wired_targets_empties_block(tmp_path: Path):
    """enable:true but the only target is mapped-but-skipped (maven-central+gradle, no
    publish) -> no wired targets -> the managed block stays empty (no dangling deploy job)."""
    _write_release(tmp_path, _REL_WITH_MARKERS)
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: central\n      target: maven-central\n      build_tool: gradle\n",
    )
    out = integrate_release_deploy(tmp_path, PLUGIN)
    assert any("[=]" in line for line in out)
    text = (tmp_path / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert "deploy" not in data["jobs"]
    assert "__HARNESS_DEPLOY_BEGIN__" in text
    assert "__HARNESS_DEPLOY_END__" in text


def test_integrate_release_deploy_empty_targets_empties_block(tmp_path: Path):
    """enable:true + targets: [] -> also an empty block (no wired targets at all)."""
    _write_release(tmp_path, _REL_WITH_MARKERS)
    _write_config(tmp_path, "deploy:\n  enable: true\n  targets: []\n")
    out = integrate_release_deploy(tmp_path, PLUGIN)
    assert any("[=]" in line for line in out)
    text = (tmp_path / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    assert "deploy" not in data["jobs"]


# --- legacy/foreign refusal ---------------------------------------------------------------


def test_integrate_release_deploy_refuses_legacy(tmp_path: Path):
    _write_release(tmp_path, _REL_LEGACY_NO_MARKERS)
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: pypi\n      target: pypi\n",
    )
    before = (tmp_path / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    out = integrate_release_deploy(tmp_path, PLUGIN)
    joined = "\n".join(out)
    assert "[!]" in joined
    assert "복구 A" in joined
    assert "복구 B" in joined
    after = (tmp_path / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    assert after == before  # untouched


def test_report_legacy_release_workflow_deploy_disabled():
    out = report_legacy_release_workflow(False)
    assert not any("[!]" in line for line in out)
    assert any("[=]" in line for line in out)


# --- no release.yml ----------------------------------------------------------------------


def test_integrate_release_deploy_no_release_file(tmp_path: Path):
    _write_config(
        tmp_path,
        "deploy:\n  enable: true\n  timeout_minutes: 15\n  targets:\n"
        "    - name: pypi\n      target: pypi\n",
    )
    out = integrate_release_deploy(tmp_path, PLUGIN)  # should not raise
    assert any("[=]" in line for line in out)


# --- template smoke ------------------------------------------------------------------------


def test_all_release_templates_have_markers_and_outputs():
    import yaml as _yaml

    for t in sorted(PLUGIN.glob("github/release.*.workflow.example.yml")):
        text = t.read_text(encoding="utf-8")
        assert "__HARNESS_DEPLOY_BEGIN__" in text, t.name
        assert "__HARNESS_DEPLOY_END__" in text, t.name
        assert "steps.exposetag.outputs.tag" in text, t.name
        assert "outputs:" in text, t.name
        _yaml.safe_load(text)  # still parses pre-render
