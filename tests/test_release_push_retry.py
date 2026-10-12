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
