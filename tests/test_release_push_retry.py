"""The post-release pushes survive a remote that moved after checkout."""

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent


def _release_text() -> str:
    return (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")


_RETRIED_PUSH_STEPS = ("Pin marketplace sha", "Sync uv.lock")


def _push_loop(step_prefix: str) -> str:
    steps = yaml.safe_load(_release_text())["jobs"]["release"]["steps"]
    run = next(s["run"] for s in steps if s.get("name", "").startswith(step_prefix))
    m = re.search(r"^ *for attempt in .*?^ *done$", run, re.M | re.S)
    assert m, f"{step_prefix}: no retry loop around its push"
    assert run.count("git push") == m.group(0).count("git push") == 1, (
        f"{step_prefix}: a push outside the retry loop fails the release on one rejection"
    )
    return m.group(0)


@pytest.mark.parametrize("step", _RETRIED_PUSH_STEPS)
def test_post_release_push_retries_over_a_moved_remote(step, tmp_path):
    """The remote moving between checkout and push rejects the push once; the loop rebases
    onto it and lands the commit instead of failing the release."""
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("no bash")
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main"]
    remote, work, other = tmp_path / "remote.git", tmp_path / "work", tmp_path / "other"
    subprocess.run([*git, "init", "-q", "--bare", str(remote)], check=True)
    subprocess.run([*git, "clone", "-q", str(remote), str(work)], check=True)
    for name in ("base", "ours"):
        (work / name).write_text(name, encoding="utf-8")
        subprocess.run([*git, "-C", str(work), "add", name], check=True)
        subprocess.run([*git, "-C", str(work), "commit", "-qm", name], check=True)
        if name == "base":
            subprocess.run([*git, "-C", str(work), "push", "-q", "origin", "HEAD:main"], check=True)
    subprocess.run([*git, "clone", "-q", str(remote), str(other)], check=True)
    (other / "theirs").write_text("theirs", encoding="utf-8")
    subprocess.run([*git, "-C", str(other), "add", "theirs"], check=True)
    subprocess.run([*git, "-C", str(other), "commit", "-qm", "theirs"], check=True)
    subprocess.run([*git, "-C", str(other), "push", "-q", "origin", "HEAD:main"], check=True)

    loop = _push_loop(step).replace("sleep ", ": ")
    env = {
        **os.environ,
        "GITHUB_REF_NAME": "main",
        "GIT_AUTHOR_NAME": "t",
        "GIT_AUTHOR_EMAIL": "t@t",
        "GIT_COMMITTER_NAME": "t",
        "GIT_COMMITTER_EMAIL": "t@t",
    }
    result = subprocess.run(
        [bash, "-ec", loop], cwd=work, env=env, capture_output=True, text=True, timeout=60
    )
    assert result.returncode == 0, result.stderr
    log = subprocess.run(
        ["git", "-C", str(remote), "log", "--format=%s", "main"],
        capture_output=True, text=True, check=True,
    ).stdout.split()
    assert log[:2] == ["ours", "theirs"], log


_RELEASE_WORKFLOWS = (
    ".github/workflows/release.yml",
    "github/release.python-semantic-release.workflow.example.yml",
    "github/release.semantic-release.workflow.example.yml",
    "github/release.gitversion.workflow.example.yml",
)
_LOOP_RE = re.compile(r"^ *for attempt in .*?^ *done$", re.M | re.S)
_TAG_RE = re.compile(r'"v\$')


def _loops(rel: str) -> list[str]:
    return _LOOP_RE.findall((ROOT / rel).read_text(encoding="utf-8"))


def _release_loops() -> list[tuple[str, str]]:
    return [(rel, loop) for rel in _RELEASE_WORKFLOWS for loop in _loops(rel) if _TAG_RE.search(loop)]


@pytest.mark.parametrize("rel", _RELEASE_WORKFLOWS)
def test_every_release_push_is_retried_without_rebase(rel):
    """A transient failure on the release commit or tag push leaves the branch released and
    the tag missing, and the next run recomputes the same version. Each push retries; a tag's
    loop never rebases, since the version and notes were computed from the pre-push tree."""
    text = (ROOT / rel).read_text(encoding="utf-8")
    spans = [m.span() for m in _LOOP_RE.finditer(text)]
    # Anywhere on a line, not at its start: `git tag "v$X"; git push …` hides one mid-line.
    for m in re.finditer(r"^(?! *#).*?\bgit push\b.*$", text, re.M):
        assert any(a <= m.start() < b for a, b in spans), f"{rel}: unretried {m.group(0).strip()}"
    tag_loops = [loop for loop in _loops(rel) if _TAG_RE.search(loop)]
    assert tag_loops, f"{rel}: no retried tag push"
    for loop in tag_loops:
        assert "--rebase" not in loop, f"{rel}: a tag push loop rebases the release commit"
        if "HEAD:" in loop:
            assert "--atomic" in loop, f"{rel}: branch and tag can land apart without --atomic"


def _seed(tmp_path, reject_first: bool):
    git = ["git", "-c", "user.name=t", "-c", "user.email=t@t", "-c", "init.defaultBranch=main"]
    remote, work = tmp_path / "remote.git", tmp_path / "work"
    subprocess.run([*git, "init", "-q", "--bare", str(remote)], check=True)
    subprocess.run([*git, "clone", "-q", str(remote), str(work)], check=True)
    for name in ("base", "release"):
        (work / name).write_text(name, encoding="utf-8")
        subprocess.run([*git, "-C", str(work), "add", name], check=True)
        subprocess.run([*git, "-C", str(work), "commit", "-qm", name], check=True)
        if name == "base":
            subprocess.run([*git, "-C", str(work), "push", "-q", "origin", "HEAD:main"], check=True)
    subprocess.run([*git, "-C", str(work), "tag", "v1.0.0"], check=True)
    if reject_first:
        hook = remote / "hooks" / "pre-receive"
        hook.write_text(
            '#!/bin/sh\n[ -f "$GIT_DIR/rejected" ] && exit 0\ntouch "$GIT_DIR/rejected"\nexit 1\n',
            encoding="utf-8", newline="\n",
        )
        hook.chmod(0o755)
    return git, remote, work


def _run_loop(loop: str, work):
    bash = shutil.which("bash")
    if not bash:
        pytest.skip("no bash")
    script = loop.replace("sleep ", ": ").replace("__HARNESS_STABLE__", "main")
    env = {**os.environ, "REF_NAME": "main", "NEXT": "1.0.0", "STABLE": "1.0.0"}
    return subprocess.run(
        [bash, "-ec", script], cwd=work, env=env, capture_output=True, text=True, timeout=60
    )


def _remote_refs(remote) -> set[str]:
    out = subprocess.run(
        ["git", "-C", str(remote), "for-each-ref", "--format=%(refname)"],
        capture_output=True, text=True, check=True,
    ).stdout
    return set(out.split())


@pytest.mark.parametrize(("rel", "loop"), _release_loops())
def test_release_push_survives_one_rejection(rel, loop, tmp_path):
    _, remote, work = _seed(tmp_path, reject_first=True)
    result = _run_loop(loop, work)
    assert result.returncode == 0, f"{rel}: {result.stderr}"
    assert "refs/tags/v1.0.0" in _remote_refs(remote), rel


@pytest.mark.parametrize(("rel", "loop"), [r for r in _release_loops() if "HEAD:" in r[1]])
def test_release_push_over_a_moved_remote_fails_and_lands_nothing(rel, loop, tmp_path):
    """A remote that moved since checkout is not transient: the release was computed without
    its commits. The loop gives up, and --atomic keeps the tag off the remote with the branch."""
    git, remote, work = _seed(tmp_path, reject_first=False)
    other = tmp_path / "other"
    subprocess.run([*git, "clone", "-q", str(remote), str(other)], check=True)
    (other / "theirs").write_text("theirs", encoding="utf-8")
    subprocess.run([*git, "-C", str(other), "add", "theirs"], check=True)
    subprocess.run([*git, "-C", str(other), "commit", "-qm", "theirs"], check=True)
    subprocess.run([*git, "-C", str(other), "push", "-q", "origin", "HEAD:main"], check=True)
    result = _run_loop(loop, work)
    assert result.returncode != 0, rel
    assert "refs/tags/v1.0.0" not in _remote_refs(remote), f"{rel}: tag landed without its branch"
