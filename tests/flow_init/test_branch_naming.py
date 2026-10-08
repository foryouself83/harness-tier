"""The rendered branch-naming workflow, run against the branch names a host pushes."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from scripts import flow_init_setup as m

PLUGIN = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")


def _render(tmp_path: Path, config: str) -> dict:
    host = tmp_path / "host"
    cfg = host / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-config.yaml").write_text(config, encoding="utf-8")
    m.render_versioning_workflows(host, PLUGIN)
    text = (host / ".github" / "workflows" / "branch-naming.yml").read_text(encoding="utf-8")
    assert "__HARNESS_" not in text
    return yaml.safe_load(text)


_CONFIG = (
    "branches: {integration: develop, staging: qa, production: trunk}\n"
    "versioning:\n  enable: true\n  release_tool: python-semantic-release\n"
    "  branches: {stable: trunk, prerelease: qa}\n"
    "  branch_naming: {enable: true}\n"
)


def test_a_tag_push_never_runs_the_check(tmp_path):
    doc = _render(tmp_path, _CONFIG)
    push = doc[True]["push"]  # PyYAML reads the bare key `on` as True
    assert push == {"branches": ["**"]}


@pytest.mark.skipif(sys.platform == "win32" or not BASH, reason="runs the step under bash")
@pytest.mark.parametrize(
    "branch, ok",
    [
        ("develop", True),
        ("qa", True),
        ("trunk", True),
        ("dev", False),
        ("hotfix/login-crash", True),
        ("hotfix/1.2.3", True),
        ("dependabot/npm_and_yarn/lodash-4.17.21", True),
        ("renovate/pin-deps", True),
        ("feature/x", True),
        ("hotfix/", False),
        ("wip", False),
    ],
)
def test_the_configured_branches_and_tool_branches_pass(tmp_path, branch, ok):
    doc = _render(tmp_path, _CONFIG)
    run = doc["jobs"]["validate"]["steps"][0]["run"]
    result = subprocess.run(
        [BASH, "-e", "-c", run],
        env={"BRANCH": branch, "PATH": "/usr/bin:/bin"},
        capture_output=True,
    )
    assert (result.returncode == 0) is ok, result.stdout


def test_integration_defaults_to_dev(tmp_path):
    assert m.load_integration_branch(tmp_path) == "dev"
