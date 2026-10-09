"""Workflow-wide properties of every template and of this repo's own CI."""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")
WORKFLOWS = sorted(
    [*(ROOT / "github").glob("*.yml"), *(ROOT / ".github" / "workflows").glob("*.yml")]
)


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_every_workflow_declares_its_token_permissions(path):
    """Without a top-level `permissions:` the token takes the repository default, which is
    read-write on every scope in a repo created before GitHub flipped that default."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8").replace("__HARNESS_", "HARNESS_"))
    assert isinstance(doc.get("permissions"), dict), path.name


def test_the_contract_test_may_comment_on_its_pull_request():
    """schemathesis/action posts its coverage summary as a pull request comment."""
    text = (ROOT / "github" / "api-contract.workflow.example.yml").read_text(encoding="utf-8")
    doc = yaml.safe_load(text.replace("__HARNESS_", "HARNESS_"))
    assert doc["permissions"] == {"contents": "read", "pull-requests": "write"}


@pytest.mark.parametrize("path", WORKFLOWS, ids=lambda p: f"{p.parent.name}/{p.name}")
def test_setup_java_takes_the_input_names_of_its_pinned_major(path):
    """v6 renamed the `*-env-var` inputs; the old names survive as deprecated aliases only."""
    text = path.read_text(encoding="utf-8")
    assert "actions/setup-java@v5" not in text
    for old in ("server-username:", "server-password:", "gpg-passphrase:"):
        assert old not in text, old


@pytest.mark.skipif(sys.platform == "win32" or not BASH, reason="runs the step under bash")
def test_entropy_counts_a_file_whose_name_holds_a_space(tmp_path):
    src = tmp_path / "src"
    src.mkdir()
    (src / "big file.py").write_text("x\n" * 600, encoding="utf-8")
    (src / "small.py").write_text("x\n", encoding="utf-8")
    text = (ROOT / "github" / "entropy-check.workflow.example.yml").read_text(encoding="utf-8")
    steps = yaml.safe_load(text.replace("__HARNESS_ENTROPY_SCHEDULE__", "0 0 * * 5"))["jobs"][
        "entropy"
    ]["steps"]
    run = next(s for s in steps if s.get("name", "").startswith("File size audit"))["run"]
    out = subprocess.run(
        [BASH, "-e", "-o", "pipefail", "-c", run.replace("__HARNESS_ENTROPY_PATHS__", "src/")],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    assert "600 src/big file.py" in out
    assert "small.py" not in out
