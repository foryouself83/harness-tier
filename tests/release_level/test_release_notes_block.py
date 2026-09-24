"""The shared release-notes block: identical in every release workflow, and run for real.

The block replaces a stable release's notes with its CHANGELOG section when one exists and
leaves them alone otherwise — a missing section, a missing script and a failed `gh` all
keep the release as created.
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.release_level.test_shared_block import _WORKFLOWS

ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")
BEGIN, END = "# >>> release-notes", "# <<< release-notes"


def _block(path: Path) -> list[str]:
    lines = path.read_text(encoding="utf-8").replace("\r\n", "\n").split("\n")
    start = next(i for i, line in enumerate(lines) if line.strip().startswith(BEGIN))
    end = next(i for i, line in enumerate(lines) if line.strip().startswith(END))
    return [line.strip() for line in lines[start : end + 1]]


def test_every_release_workflow_carries_the_same_block():
    blocks = {rel: _block(ROOT / rel) for rel in _WORKFLOWS}
    first = blocks[_WORKFLOWS[0]]
    assert len(first) > 2
    for rel, block in blocks.items():
        assert block == first, f"{rel} carries a different release-notes block"


def test_every_release_workflow_runs_the_block_on_the_stable_branch_only():
    for rel in _WORKFLOWS:
        text = (ROOT / rel).read_text(encoding="utf-8").replace("\r\n", "\n")
        step = text.split("- name: Stable release notes from CHANGELOG", 1)[1].split("run: |")[0]
        stable = "'main'" if rel.startswith(".github") else "'__HARNESS_STABLE__'"
        assert f"github.ref_name == {stable}" in step, rel
        assert "HARNESS_SCRIPTS:" in step and "GH_TOKEN:" in step, rel


CHANGELOG = """# CHANGELOG

<!-- version list -->

## v1.1.0 (2026-09-24)

### Features

- **x**: One summary line


## v1.1.0-rc.1 (2026-09-20)

- raw rc line
"""


def _run(tmp_path: Path, tag: str, changelog: str | None, scripts: Path, gh_exit: int = 0):
    work = tmp_path / "work"
    work.mkdir()
    if changelog is not None:
        (work / "CHANGELOG.md").write_text(changelog, encoding="utf-8")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    log = tmp_path / "gh.log"
    gh = bin_dir / "gh"
    gh.write_text(
        f'#!/usr/bin/env bash\necho "$*" >> "{log.as_posix()}"\n'
        f'cp "${{@: -1}}" "{(tmp_path / "notes.md").as_posix()}"\nexit {gh_exit}\n',
        encoding="utf-8",
        newline="\n",
    )
    gh.chmod(0o755)
    script = "\n".join(_block(ROOT / _WORKFLOWS[0]))
    env = {
        **os.environ,
        "PATH": f"{bin_dir}{os.pathsep}{os.environ['PATH']}",
        "HARNESS_SCRIPTS": str(scripts),
        "TAG": tag,
    }
    r = subprocess.run([BASH, "-c", script], cwd=work, env=env, capture_output=True, text=True)
    calls = log.read_text(encoding="utf-8") if log.exists() else ""
    return r, calls, tmp_path / "notes.md"


needs_bash = pytest.mark.skipif(
    BASH is None or os.name == "nt", reason="needs a real bash (CI runs it on ubuntu)"
)


@needs_bash
def test_a_stable_section_replaces_the_release_notes(tmp_path):
    r, calls, notes = _run(tmp_path, "v1.1.0", CHANGELOG, ROOT / "scripts")
    assert r.returncode == 0, r.stderr
    assert calls.startswith("release edit v1.1.0 --notes-file")
    body = notes.read_text(encoding="utf-8")
    assert "One summary line" in body and "raw rc line" not in body


@needs_bash
def test_no_stable_section_keeps_the_notes(tmp_path):
    r, calls, _ = _run(tmp_path, "v1.2.0", CHANGELOG, ROOT / "scripts")
    assert r.returncode == 0
    assert calls == "" and "keeping the release notes" in r.stdout


@needs_bash
def test_no_changelog_and_no_script_keep_the_notes(tmp_path):
    r, calls, _ = _run(tmp_path, "v1.1.0", None, tmp_path / "missing")
    assert r.returncode == 0 and calls == ""


@needs_bash
def test_a_failed_edit_warns_and_passes(tmp_path):
    r, calls, _ = _run(tmp_path, "v1.1.0", CHANGELOG, ROOT / "scripts", gh_exit=1)
    assert r.returncode == 0
    assert calls and "::warning::" in r.stdout
