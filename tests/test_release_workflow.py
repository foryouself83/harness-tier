import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest
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


def test_consumer_templates_fall_back_to_github_token():
    """Both consumer release templates auth via `RELEASE_TOKEN || GITHUB_TOKEN`, so a repo
    that never sets RELEASE_TOKEN still releases on the auto-provided GITHUB_TOKEN (the PAT
    is an opt-in escalation, not a prerequisite). flow-init renders these verbatim."""
    for rel in (
        "github/release.python-semantic-release.workflow.example.yml",
        "github/release.semantic-release.workflow.example.yml",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "secrets.RELEASE_TOKEN || secrets.GITHUB_TOKEN" in text, f"{rel}: missing fallback"
        # no bare `secrets.GITHUB_TOKEN` should survive outside the fallback expression
        for line in text.splitlines():
            if "secrets.GITHUB_TOKEN" in line:
                assert "secrets.RELEASE_TOKEN || secrets.GITHUB_TOKEN" in line, (
                    f"{rel}: bare GITHUB_TOKEN not wrapped in fallback -> {line.strip()}"
                )


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


def test_release_body_uses_changelog_section():
    """release.yml + the python template build the GitHub Release body from the
    latest CHANGELOG.md section, with a --generate-notes fallback."""
    for rel in (
        ".github/workflows/release.yml",
        "github/release.python-semantic-release.workflow.example.yml",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "CHANGELOG.md" in text, f"{rel}: expected changelog extraction"
        assert "release-body.md" in text, f"{rel}: expected release-body file"
        assert "--notes-file" in text, f"{rel}: expected --notes-file (curated body)"
        assert "--generate-notes" in text, f"{rel}: expected --generate-notes fallback"


def _guard_script(inject_tag: str) -> str:
    """The real 'Create GitHub Release' run-script from release.yml with git/gh calls
    stubbed, so it can run under errexit+pipefail exactly like GitHub Actions. The two
    `gh release create` calls become branch markers so we can see which path ran."""
    data = yaml.safe_load(_release_text())
    step = next(
        s
        for s in data["jobs"]["release"]["steps"]
        if isinstance(s, dict) and s.get("name") == "Create GitHub Release"
    )
    script = step["run"]
    script = script.replace('TAG="$(git describe --tags --abbrev=0)"', f'TAG="{inject_tag}"')
    script = script.replace('gh release view "$TAG" &>/dev/null', "false")
    script = script.replace(
        'gh release create "$TAG" --title "$TAG" --notes-file release-body.md $PRERELEASE',
        "echo BRANCH=notes",
    )
    script = script.replace(
        'gh release create "$TAG" --title "$TAG" --generate-notes $PRERELEASE',
        "echo BRANCH=fallback",
    )
    return script


def _run_guard(inject_tag: str, changelog: str | None):
    """Run the stubbed guard block under `bash -eo pipefail` (GitHub Actions' default
    shell flags). Returns (returncode, stdout, release_body_or_None)."""
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash not available on PATH")
    script = _guard_script(inject_tag)
    with tempfile.TemporaryDirectory() as d:
        if changelog is not None:
            (Path(d) / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
        proc = subprocess.run(
            [bash, "-eo", "pipefail", "-c", script],
            cwd=d,
            capture_output=True,
            text=True,
            env={**os.environ, "REF_NAME": "main"},
        )
        body_path = Path(d) / "release-body.md"
        body = body_path.read_text(encoding="utf-8") if body_path.exists() else None
    return proc.returncode, proc.stdout, body


_MULTI_RC_CHANGELOG = (
    "# CHANGELOG\n\n<!-- version list -->\n\n"
    "## v0.1.1-rc.2 (2026-07-03)\n\n### Features\n\n- Second rc thing\n\n"
    "## v0.1.1-rc.1 (2026-07-02)\n\n### Bug Fixes\n\n- First rc fix\n\n"
    "## v0.1.0 (2026-07-01)\n\n### Features\n\n- Old thing\n"
)


def test_guard_missing_changelog_falls_back_not_aborts():
    # C1 regression: under errexit+pipefail a missing changelog must fall back, not abort.
    rc, out, _ = _run_guard("v0.1.1", None)
    assert rc == 0, "step must not abort when CHANGELOG.md is absent"
    assert "BRANCH=fallback" in out


def test_guard_headerless_changelog_falls_back_not_aborts():
    rc, out, _ = _run_guard("v0.1.1", "just prose\nno version headers\n")
    assert rc == 0, "step must not abort on an unparseable changelog"
    assert "BRANCH=fallback" in out


def test_guard_version_mismatch_falls_back():
    # Top section is v0.2.0 but we release v0.1.1 (stale/drift) → fallback, no wrong body.
    stale = "# CHANGELOG\n\n## v0.2.0 (d)\n\n### Features\n\n- x\n\n## v0.1.0 (d)\n\n- y\n"
    rc, out, _ = _run_guard("v0.1.1", stale)
    assert rc == 0
    assert "BRANCH=fallback" in out


def test_guard_match_uses_notes_and_merges_rc_sections():
    # I2: a stable release that went through rc.1 + rc.2 merges both sections, drops the
    # headers, and stops before the previous stable version.
    rc, out, body = _run_guard("v0.1.1", _MULTI_RC_CHANGELOG)
    assert rc == 0
    assert "BRANCH=notes" in out
    assert body is not None
    assert "- Second rc thing" in body and "- First rc fix" in body, "both rc's merged"
    assert "## v0.1.1-rc" not in body, "version headers dropped (tag is the title)"
    assert "Old thing" not in body, "must stop before the previous stable version"


def test_guard_stage_rc_tag_uses_notes():
    # On stage the tag is the rc itself (v0.1.1-rc.2); core 0.1.1 matches the top header.
    rc, out, body = _run_guard("v0.1.1-rc.2", _MULTI_RC_CHANGELOG)
    assert rc == 0
    assert "BRANCH=notes" in out
    assert body is not None and "- Second rc thing" in body


def test_release_body_has_version_match_guard():
    """Both workflows carry the errexit-safe version-match guard: TCORE, the core-aware
    awk, `|| true`, and the `[ -n "$TCORE" ]` gate."""
    for rel in (
        ".github/workflows/release.yml",
        "github/release.python-semantic-release.workflow.example.yml",
    ):
        text = (ROOT / rel).read_text(encoding="utf-8")
        assert "TCORE" in text, f"{rel}: expected TCORE"
        assert "awk -v core=" in text, f"{rel}: expected core-aware awk"
        assert "if (v!=core) exit" in text, f"{rel}: expected core-mismatch stop"
        assert '[ -n "$TCORE" ]' in text, f"{rel}: expected TCORE presence gate"
        assert "|| true" in text, f"{rel}: expected errexit-safe `|| true`"


def test_changelog_excludes_plumbing_commit_types():
    """pyproject configures PSR to drop plumbing commit types from the changelog (and
    thus the release body) — PSR ships no default exclusions."""
    import tomllib

    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = data["tool"]["semantic_release"]["changelog"]["exclude_commit_patterns"]
    joined = "\n".join(patterns)
    for kind in ("chore", "ci", "refactor", "style", "test"):
        assert kind in joined, f"exclude_commit_patterns should filter '{kind}'"
