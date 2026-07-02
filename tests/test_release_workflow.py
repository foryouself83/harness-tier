import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _release_text() -> str:
    return (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")


def test_release_parses_and_has_jobs():
    data = yaml.safe_load(_release_text())
    assert "release" in data["jobs"]


def test_stage_forces_level_from_trailer():
    text = _release_text()
    assert "Release-Level:" in text
    assert "--as-prerelease" in text


def test_main_uses_deterministic_finalize():
    text = _release_text()
    assert "finalize_prerelease.py" in text


def test_consumer_template_has_force_and_finalize():
    tmpl = (ROOT / "github" / "release.python-semantic-release.workflow.example.yml").read_text(
        encoding="utf-8"
    )
    assert "Release-Level:" in tmpl
    assert "--as-prerelease" in tmpl
    assert "finalize_prerelease.py" in tmpl
    assert "__HARNESS_STABLE__" in tmpl and "__HARNESS_PRERELEASE__" in tmpl


def test_release_uses_release_token_and_preflight():
    text = _release_text()
    assert "secrets.RELEASE_TOKEN" in text
    assert "check-token-write.sh" in text
    assert "GITHUB_STEP_SUMMARY" in text
    assert "secrets.RELEASE_TOKEN || secrets.GITHUB_TOKEN" in text


def _ids_and_output_refs(text: str):
    import yaml

    data = yaml.safe_load(text)
    ids = set()
    for job in (data.get("jobs") or {}).values():
        for step in job.get("steps") or []:
            if isinstance(step, dict) and step.get("id"):
                ids.add(step["id"])
    refs = set(re.findall(r"steps\.([A-Za-z0-9_-]+)\.outputs", text))
    return ids, refs


def test_workflow_step_output_refs_resolve():
    for rel in (
        ".github/workflows/release.yml",
        "github/release.python-semantic-release.workflow.example.yml",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        ids, refs = _ids_and_output_refs(text)
        assert refs, f"{rel}: expected steps.X.outputs references"
        assert refs <= ids, f"{rel}: orphaned step refs {refs - ids} (not a declared id:)"
