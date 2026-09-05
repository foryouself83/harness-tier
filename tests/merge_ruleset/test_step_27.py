import os
import re
import subprocess
import sys
from pathlib import Path

from tests.merge_ruleset._helpers import BASH, SCRIPT

SKILL = Path(__file__).resolve().parent.parent.parent / "skills" / "flow-init" / "SKILL.md"
PLUGIN_ROOT = Path(__file__).resolve().parent.parent.parent


def _step_27_block() -> str:
    """The Step 2.7 shell block, lifted verbatim out of the skill so it can be RUN.

    Asserting on the block's *text* is not enough: the pre-fix hard error can be restored on
    a line of its own and still satisfy any grep-shaped check. Only executing it proves the
    behavior.
    """
    blocks = re.findall(r"```bash\n(.*?)```", SKILL.read_text(encoding="utf-8"), re.DOTALL)
    hits = [b for b in blocks if "check-merge-ruleset.sh" in b]
    assert len(hits) == 1, f"expected exactly one Step 2.7 bash block, found {len(hits)}"
    return hits[0]


def _write_config(root: Path, body: str) -> None:
    cfgdir = root / ".claude" / "harness-tier" / "config"
    cfgdir.mkdir(parents=True)
    (cfgdir / "flow-config.yaml").write_text(body, encoding="utf-8")


FULL_CONFIG = (
    "branches:\n"
    "  integration: dev\n"
    "  staging: stage\n"
    "  production: main\n"
    "merge_workflow:\n"
    "  pull_request: [promotion]\n"
)


def _shim_dir(tmp: Path, gh_stub: str | None) -> Path:
    """A PATH containing `python3` and nothing else (plus `gh` when a stub is asked for).

    `python3` is shimmed onto the venv interpreter because the block imports PyYAML and the
    system python3 generally has not got it. Both shims use an ABSOLUTE `/bin/sh` shebang,
    never `/usr/bin/env bash` — the whole point of this directory is to be the entire PATH,
    so nothing may be resolved through it.
    """
    shim = tmp / "bin"
    shim.mkdir()
    (shim / "python3").write_text(f'#!/bin/sh\nexec "{sys.executable}" "$@"\n', encoding="utf-8")
    (shim / "python3").chmod(0o755)
    if gh_stub is not None:
        (shim / "gh").write_text(gh_stub, encoding="utf-8")
        (shim / "gh").chmod(0o755)
    return shim


def _run_step_27(tmp: Path, gh_stub: str | None, config: str = FULL_CONFIG):
    """Run the extracted block with `gh` absent or failing.

    PATH is the shim directory ALONE. An earlier version instead dropped every PATH entry
    that carried a `gh`, which on a Linux runner deletes `/usr/bin` — taking `bash` with it
    — so the test passed on Windows only by accident of where `gh` happens to live. Making
    PATH exhaustive removes the guesswork: `command -v gh` cannot find what is not there.
    The block exits at the `gh` probe, before the line that needs `bash` on PATH.
    """
    root = tmp / "host"
    _write_config(root, config)
    env = dict(os.environ)
    env["PATH"] = str(_shim_dir(tmp, gh_stub))
    env["ROOT"] = str(root)
    env["PLUGIN"] = str(PLUGIN_ROOT)

    script = tmp / "step27.sh"
    script.write_text(_step_27_block(), encoding="utf-8")
    return subprocess.run([BASH, str(script)], capture_output=True, text=True, env=env)


def test_step_27_skips_instead_of_dying_when_gh_is_absent(tmp_path: Path):
    """The caller must not be stricter than the script it calls.

    `check-merge-ruleset.sh` degrades a missing/unauthenticated `gh` to exit 20 ("skipping"),
    and Step 2.7 documents continuing on 10 and 20 alike. But the block reached the script
    through `REPO="$(gh repo view …)" || exit 1`, so on a host without `gh` the step died
    with a hard error before the graceful path could ever run — stopping `/flow-init` for a
    team whose only sin was not having the GitHub CLI installed.
    """
    r = _run_step_27(tmp_path, gh_stub=None)
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    assert "skipping" in (r.stdout + r.stderr)


def test_step_27_skips_when_gh_cannot_resolve_a_repo(tmp_path: Path):
    # `gh` installed but unauthenticated, or a repo with no GitHub remote: also not a config
    # defect, also not a reason to stop /flow-init.
    r = _run_step_27(tmp_path, gh_stub="#!/bin/sh\nexit 1\n")
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    assert "skipping" in (r.stdout + r.stderr)


def test_step_27_still_stops_on_a_broken_branches_config(tmp_path: Path):
    # The other half of the distinction: a config error must still be fatal. Without this,
    # "skip on anything that fails" would pass both tests above and silence real defects.
    # `gh` is present and working here, so the run reaches the config error on its merits.
    r = _run_step_27(
        tmp_path,
        gh_stub="#!/bin/sh\necho owner/repo\n",
        config="branches:\n  integration: dev\nmerge_workflow:\n  pull_request: [promotion]\n",
    )
    assert r.returncode == 1
    assert "branches.staging" in r.stderr


def test_script_never_calls_a_write_api():
    # The whole point of this script is that it reads. A method flag on a gh/curl call is the
    # only way it could write, so its absence is the structural guarantee.
    text = SCRIPT.read_text(encoding="utf-8")
    assert "--method" not in text
    assert "-X " not in text
    for verb in ("POST", "PUT", "PATCH", "DELETE"):
        assert verb not in text
