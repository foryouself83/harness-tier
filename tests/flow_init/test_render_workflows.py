import os
import subprocess
from pathlib import Path

import yaml as _yaml

from scripts.flow_init_setup import (
    load_contract_config,
    render_wiki_verify_workflow,
    render_workflow,
    run_setup,
)
from tests.flow_init._helpers import BASH, PLUGIN


def _write_flow_config(host: Path, contract: dict) -> None:
    cfg_dir = host / ".claude" / "harness-tier" / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "flow-config.yaml").write_text(
        _yaml.safe_dump({"contract_test": contract}, allow_unicode=True), encoding="utf-8"
    )


def test_render_workflow_creates_and_substitutes(tmp_path: Path):
    _write_flow_config(
        tmp_path,
        {
            "enable": True,
            "branches": ["dev", "stage", "main"],
            "action_ref": "schemathesis/action@v3",
            "schema": "http://localhost:8000/openapi.json",
            "base_url": "http://localhost:8000",
            "server": {
                "compose_file": "docker-compose.yml",
                "health_url": "http://localhost:8000/health",
                "health_timeout": 60,
            },
        },
    )
    out = render_workflow(tmp_path, PLUGIN)
    assert any("생성" in line for line in out)
    dest = tmp_path / ".github" / "workflows" / "api-contract.yml"
    text = dest.read_text(encoding="utf-8")
    # all tokens have been substituted
    assert "__HARNESS_" not in text
    # the render result is valid YAML (parses without exception). Note: PyYAML parses the
    # GitHub Actions 'on:' key as a boolean True key (a YAML 1.1 pitfall), so data["on"]
    # access raises KeyError. The intent (branch/action/schema substitution) is verified
    # directly against the text.
    _yaml.safe_load(text)
    assert "branches: [dev, stage, main]" in text
    assert "schemathesis/action@v3" in text
    assert "http://localhost:8000/openapi.json" in text


def test_render_workflow_disabled(tmp_path: Path):
    _write_flow_config(tmp_path, {"enable": False, "branches": ["dev"]})
    out = render_workflow(tmp_path, PLUGIN)
    assert any("enable=false" in line for line in out)
    assert load_contract_config(tmp_path) == {"enable": False, "branches": ["dev"]}
    assert not (tmp_path / ".github" / "workflows" / "api-contract.yml").exists()


def test_render_workflow_absent_section(tmp_path: Path):
    # if flow-config itself is absent, it is unconfigured — skip
    out = render_workflow(tmp_path, PLUGIN)
    assert any("미설정" in line for line in out)
    assert load_contract_config(tmp_path) is None
    assert not (tmp_path / ".github" / "workflows" / "api-contract.yml").exists()


def test_run_setup_renders_workflow(tmp_path: Path, capsys):
    from scripts.flow_init_setup import run_setup

    _write_flow_config(
        tmp_path,
        {
            "enable": True,
            "branches": ["dev", "stage", "main"],
            "action_ref": "schemathesis/action@v3",
            "schema": "http://localhost:8000/openapi.json",
            "base_url": "http://localhost:8000",
            "server": {
                "compose_file": "docker-compose.yml",
                "health_url": "http://localhost:8000/health",
                "health_timeout": 60,
            },
        },
    )
    run_setup(tmp_path, PLUGIN)
    captured = capsys.readouterr().out
    assert "계약 테스트" in captured
    assert (tmp_path / ".github" / "workflows" / "api-contract.yml").is_file()


def test_render_wiki_verify_workflow_unconditional(tmp_path: Path):
    # Rendered whether or not flow-config exists and whether or not the wiki is enabled:
    # the script guarantees a no-op green, which is what frees /flow-init from depending on
    # /wiki-init having run.
    out = render_wiki_verify_workflow(tmp_path, PLUGIN)
    assert any("생성" in line for line in out)
    dest = tmp_path / ".github" / "workflows" / "wiki-verify.yml"
    text = dest.read_text(encoding="utf-8")
    assert "__HARNESS_" not in text
    data = _yaml.safe_load(text)
    assert data["jobs"]["wiki-verify"]["timeout-minutes"] == 5


def _wiki_verify_step(host: Path) -> str:
    data = _yaml.safe_load(
        (host / ".github" / "workflows" / "wiki-verify.yml").read_text(encoding="utf-8")
    )
    steps = data["jobs"]["wiki-verify"]["steps"]
    return next(s["run"] for s in steps if s.get("name") == "Verify wiki graph")


def test_wiki_verify_step_is_green_without_the_script(tmp_path: Path):
    # The unconditional render reaches repos that gitignore .claude/, where the checkout holds
    # no script and an unguarded python3 exits 2 — a red push for a repo that never opted into
    # a wiki. The step's shell is executed rather than pattern-matched: a guard that reads
    # right and short-circuits wrong is what a substring assertion cannot tell apart.
    render_wiki_verify_workflow(tmp_path, PLUGIN)
    step = tmp_path / "step.sh"
    step.write_text(_wiki_verify_step(tmp_path), encoding="utf-8", newline="\n")

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    # python3 is stubbed rather than assumed: the second arm has to prove the guard falls
    # THROUGH to the verify call, and an exit code the runner's own interpreter chose would
    # not tell that apart from a short circuit.
    stub = bin_dir / "python3"
    stub.write_text("#!/usr/bin/env bash\nexit 3\n", encoding="utf-8", newline="\n")
    stub.chmod(0o755)
    env = dict(os.environ)
    env["PATH"] = str(bin_dir) + os.pathsep + env.get("PATH", "")

    absent = subprocess.run(
        [BASH, "-e", str(step)], cwd=tmp_path, env=env, capture_output=True, text=True
    )
    assert absent.returncode == 0, absent.stderr

    script = tmp_path / ".claude" / "harness-tier" / "scripts" / "wiki_graph.py"
    script.parent.mkdir(parents=True)
    script.write_text("", encoding="utf-8")
    present = subprocess.run(
        [BASH, "-e", str(step)], cwd=tmp_path, env=env, capture_output=True, text=True
    )
    assert present.returncode == 3, "the guard swallowed the verify call"


def test_render_wiki_verify_workflow_preserves_existing(tmp_path: Path):
    dest = tmp_path / ".github" / "workflows" / "wiki-verify.yml"
    dest.parent.mkdir(parents=True)
    dest.write_text("# custom\n", encoding="utf-8")
    out = render_wiki_verify_workflow(tmp_path, PLUGIN)
    assert any("이미" in line for line in out)
    assert dest.read_text(encoding="utf-8") == "# custom\n"


def test_run_setup_renders_wiki_verify(tmp_path: Path, capsys):
    run_setup(tmp_path, PLUGIN)
    assert (tmp_path / ".github" / "workflows" / "wiki-verify.yml").is_file()
    assert "wiki 검증" in capsys.readouterr().out


def test_render_workflow_idempotent_reports_only(tmp_path: Path):
    contract = {
        "enable": True,
        "branches": ["dev", "stage", "main"],
        "action_ref": "schemathesis/action@v3",
        "schema": "http://localhost:8000/openapi.json",
        "base_url": "http://localhost:8000",
        "server": {
            "compose_file": "docker-compose.yml",
            "health_url": "http://localhost:8000/health",
            "health_timeout": 60,
        },
    }
    _write_flow_config(tmp_path, contract)
    render_workflow(tmp_path, PLUGIN)  # first render (create)
    dest = tmp_path / ".github" / "workflows" / "api-contract.yml"
    sentinel = dest.read_text(encoding="utf-8") + "\n# user edit\n"
    dest.write_text(sentinel, encoding="utf-8")  # simulate a user edit
    out = render_workflow(tmp_path, PLUGIN)  # second render — report only
    assert any("이미 있어" in line for line in out)
    assert dest.read_text(encoding="utf-8") == sentinel  # not overwritten
