"""Behavior spec for the Node semantic-release template's tag-only release paths.

Each case runs a run step lifted from the template against a real git repo with a bare
`origin` and a stub `gh`, so what the step decides — tag-only release or semantic-release — is
read from its outputs and from what reached `origin`.
"""

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent.parent
BASH = shutil.which("bash")
TEMPLATE = ROOT / "github" / "release.semantic-release.workflow.example.yml"
MARK = "release {tag} (Release-Level)"

pytestmark = pytest.mark.skipif(
    sys.platform == "win32" or not BASH,
    reason="needs a real bash + python3; CI (ubuntu) and WSL are the authority, not Windows",
)


def _run_body(step_id: str) -> str:
    doc = yaml.safe_load(TEMPLATE.read_text(encoding="utf-8"))
    for step in doc["jobs"]["release"]["steps"]:
        if step.get("id") == step_id:
            return step["run"]
    raise AssertionError(f"no step with id {step_id!r} in {TEMPLATE.name}")


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-c", "user.email=t@t", "-c", "user.name=T", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def _commit(repo: Path, message: str) -> None:
    _git(repo, "commit", "-q", "--allow-empty", "-m", message)


def _forced_tag(repo: Path, tag: str) -> None:
    _git(repo, "tag", "-a", tag, "-m", MARK.format(tag=tag))


class Fixture:
    def __init__(self, tmp_path: Path):
        self.repo = tmp_path / "repo"
        self.origin = tmp_path / "origin.git"
        self.out = tmp_path / "github_output"
        self.gh_log = tmp_path / "gh.log"
        self.bin = tmp_path / "bin"
        self.repo.mkdir()
        _git(self.repo, "init", "-q", "-b", "main")
        _commit(self.repo, "chore: seed")
        _git(self.repo, "tag", "v1.0.0")
        self.bin.mkdir()
        gh = self.bin / "gh"
        gh.write_text('#!/bin/sh\necho "$*" >> "$GH_LOG"\nexit "${GH_EXIT:-0}"\n', "utf-8")
        gh.chmod(gh.stat().st_mode | stat.S_IEXEC)

    def publish(self) -> None:
        """Mirror every local ref into a fresh bare `origin`."""
        if self.origin.exists():
            shutil.rmtree(self.origin)
        _git(self.repo.parent, "clone", "-q", "--bare", str(self.repo), str(self.origin))
        remotes = _git(self.repo, "remote").split()
        if "origin" not in remotes:
            _git(self.repo, "remote", "add", "origin", str(self.origin))

    def run(self, step_id: str, message: str = "feat: x", **env: str):
        _commit(self.repo, message)
        self.publish()
        self.out.write_text("", encoding="utf-8")
        full_env = {
            **os.environ,
            "PATH": f"{self.bin}{os.pathsep}{os.environ['PATH']}",
            "HARNESS_SCRIPTS": str(ROOT / "scripts"),
            "AUTO_LEVEL": "",
            "GITHUB_OUTPUT": str(self.out),
            "GH_LOG": str(self.gh_log),
            **env,
        }
        result = subprocess.run(
            [BASH, "-e", "-c", _run_body(step_id)],
            cwd=self.repo,
            env=full_env,
            capture_output=True,
            text=True,
        )
        outputs = dict(
            line.split("=", 1) for line in self.out.read_text("utf-8").splitlines() if line
        )
        gh = self.gh_log.read_text("utf-8") if self.gh_log.exists() else ""
        return result, outputs, gh

    def origin_tags(self) -> set[str]:
        return set(_git(self.origin, "tag", "--list").split())


@pytest.fixture
def fx(tmp_path):
    return Fixture(tmp_path)


# --- stable: finalize ---------------------------------------------------------------------


def test_finalize_tags_a_forced_rc_merged_into_head(fx):
    _commit(fx.repo, "feat: a")
    _forced_tag(fx.repo, "v1.2.0-rc.1")
    result, outputs, gh = fx.run("finalize")
    assert result.returncode == 0, result.stderr
    assert outputs == {"released": "true", "tag": "v1.2.0"}
    head = _git(fx.repo, "rev-parse", "HEAD").strip()
    assert f"release create v1.2.0 --target {head} " in gh, gh


def test_finalize_ignores_an_rc_not_merged_into_head(fx):
    # Staging waits on a forced rc on its own branch; a hotfix reaches production meanwhile.
    _git(fx.repo, "switch", "-q", "-c", "stage")
    _commit(fx.repo, "feat: staged")
    _forced_tag(fx.repo, "v1.2.0-rc.1")
    _git(fx.repo, "switch", "-q", "main")
    result, outputs, gh = fx.run("finalize", "fix: hotfix")
    assert result.returncode == 0, result.stderr
    assert outputs == {}, "an unmerged rc must leave the release to semantic-release"
    assert gh == ""


def test_finalize_leaves_a_semantic_release_rc_to_semantic_release(fx):
    _commit(fx.repo, "feat: a")
    _git(fx.repo, "tag", "v1.2.0-rc.1")  # lightweight, as semantic-release writes it
    result, outputs, gh = fx.run("finalize")
    assert result.returncode == 0, result.stderr
    assert outputs == {}
    assert gh == ""


def test_finalize_needs_the_exact_marker_on_an_annotated_tag(fx):
    _commit(fx.repo, "feat: a")
    _git(fx.repo, "tag", "-a", "v1.2.0-rc.1", "-m", "release v1.2.0-rc.1")
    result, outputs, gh = fx.run("finalize")
    assert result.returncode == 0, result.stderr
    assert outputs == {}
    assert gh == ""


def test_a_failed_release_leaves_no_stable_tag_behind(fx):
    # A rerun recomputes from the tag list, so a tag without its Release would lose the Release.
    _commit(fx.repo, "feat: a")
    _forced_tag(fx.repo, "v1.2.0-rc.1")
    result, outputs, _ = fx.run("finalize", GH_EXIT="1")
    assert result.returncode != 0
    assert "released" not in outputs
    assert "v1.2.0" not in fx.origin_tags()
    assert "v1.2.0" not in _git(fx.repo, "tag", "--list").split()


# --- prerelease: nextver + forced ---------------------------------------------------------


def test_a_forced_rc_is_annotated_with_the_marker(fx):
    result, outputs, gh = fx.run("forced", NEXT="1.2.0-rc.1")
    assert result.returncode == 0, result.stderr
    assert outputs == {"released": "true", "tag": "v1.2.0-rc.1"}
    assert "v1.2.0-rc.1" in fx.origin_tags()
    assert _git(fx.origin, "cat-file", "-t", "refs/tags/v1.2.0-rc.1").strip() == "tag"
    subject = _git(fx.origin, "tag", "-l", "--format=%(contents:subject)", "v1.2.0-rc.1")
    assert subject.strip() == MARK.format(tag="v1.2.0-rc.1")
    assert "--prerelease" in gh


def test_no_trailer_continues_a_forced_rc(fx):
    _forced_tag(fx.repo, "v1.2.0-rc.1")
    result, outputs, _ = fx.run("nextver", "feat: more")
    assert result.returncode == 0, result.stderr
    assert outputs == {"version": "1.2.0-rc.2"}


def test_no_trailer_leaves_a_semantic_release_rc_to_semantic_release(fx):
    _git(fx.repo, "tag", "v1.2.0-rc.1")
    result, outputs, _ = fx.run("nextver", "feat: more")
    assert result.returncode == 0, result.stderr
    assert outputs == {"version": "auto"}


def test_no_trailer_and_no_pending_rc_is_auto(fx):
    result, outputs, _ = fx.run("nextver", "feat: more")
    assert result.returncode == 0, result.stderr
    assert outputs == {"version": "auto"}


def test_a_trailer_still_wins_over_the_forced_rc(fx):
    _forced_tag(fx.repo, "v1.2.0-rc.1")
    result, outputs, _ = fx.run("nextver", "feat: more\n\nRelease-Level: major\n")
    assert result.returncode == 0, result.stderr
    assert outputs == {"version": "2.0.0-rc.1"}
