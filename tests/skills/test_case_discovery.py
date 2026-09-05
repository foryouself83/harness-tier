import re
import shutil
import subprocess
from pathlib import Path

import pytest

from tests.skills._helpers import REPO, body

# -------------------------------------------------------------------------- behavioural
#
# The case-discovery command decides "does this project already have tests?". A wrong
# answer scaffolds a starter smoke over a suite that already exists. These tests run
# the command the skills ship.

CASE_DISCOVERY_FILES = [
    "skills/integration/SKILL.md",
    "skills/integration/references/web-playwright.md",
    "skills/playwright-scaffold/SKILL.md",
]


def case_discovery_command(rel: str) -> str:
    """Pull the shipped `testDir` resolution + guarded `find` out of a skill.

    All three lines must be identical everywhere: they decide which directory is
    searched, what counts as a case, and — via the `[ -d ]` guard — whether an empty
    result means "no cases" or "that directory is not there".
    """
    text = (REPO / rel).read_text(encoding="utf-8")
    resolve = re.search(r"^TESTDIR=\$\(grep .*$", text, re.M)
    default = re.search(r'^TESTDIR="\$\{TESTDIR:-.*$', text, re.M)
    search = re.search(r'^if \[ -d "\$TESTDIR" \]; then find .*fi$', text, re.M)
    assert resolve and default and search, f"{rel}: no guarded testDir discovery command found"
    # Strip only a trailing consumer. Splitting on "|" would cut the `(spec|test)`
    # alternation inside the regex and hand bash a syntax error.
    core = re.sub(r"\s*\|\s*(wc -l|head -\d+)\s*$", "", search.group(0))
    return "\n".join([resolve.group(0), default.group(0), core.strip()])


def make_project(root: Path, test_dir: str | None, cases: list[str] | None) -> None:
    """`cases=None` means the test directory itself is absent — the state the `[ -d ]`
    guard exists to tell apart from an empty one."""
    config = (
        f'export default {{ testDir: "{test_dir}" }};\n' if test_dir else "export default {};\n"
    )
    (root / "playwright.config.ts").write_text(config, encoding="utf-8", newline="")
    if cases is None:
        return
    target = root / (test_dir or "tests")
    target.mkdir(parents=True, exist_ok=True)
    for name in cases:
        (target / name).write_text("// case\n", encoding="utf-8", newline="")


def run_discovery(rel: str, cwd: Path) -> list[str]:
    """Run the skill's own command in a throwaway project and return the cases it found.

    Two Windows hazards corrupt the script before bash ever sees it and would otherwise be
    misread as a bug in the skill — a third, which `bash` runs at all, is marked below:

    * the script goes in on stdin (`bash -s`), not as a `-c` argument — CreateProcess
      escapes the embedded double quotes and Git Bash reads them back as literal
      backslashes;
    * it goes in as **bytes** — `text=True` wraps stdin in a TextIOWrapper whose default
      newline translation rewrites every ``\\n`` to ``\\r\\n``, and bash then treats the
      stray ``\\r`` as part of the command.
    """
    proc = subprocess.run(
        # Resolved, never a bare "bash": CreateProcess searches its own PATH and finds the
        # System32 WSL stub first, which then hangs forever on the piped stdin below.
        [shutil.which("bash") or "bash", "-s"],
        input=case_discovery_command(rel).encode("utf-8"),
        cwd=cwd,
        capture_output=True,
        check=False,
    )
    stderr = proc.stderr.decode("utf-8", "replace")
    assert proc.returncode == 0, f"{rel}: command failed (rc={proc.returncode}) → {stderr}"
    return [ln for ln in proc.stdout.decode("utf-8", "replace").splitlines() if ln.strip()]


def test_all_three_files_agree_on_the_discovery_command():
    """integration, its reference, and playwright-scaffold each decide what counts as
    an existing case. Disagreement means one of them scaffolds over a real suite."""
    commands = {rel: case_discovery_command(rel) for rel in CASE_DISCOVERY_FILES}
    assert len(set(commands.values())) == 1, f"discovery commands diverge: {commands}"


@pytest.mark.parametrize("rel", CASE_DISCOVERY_FILES, ids=lambda r: Path(r).parent.name)
def test_discovery_finds_cases_under_a_custom_testdir(rel: str, tmp_path: Path):
    """The regression this file was written for: a hardcoded `./tests` reported zero
    cases for a `testDir: './e2e'` project, so the agent scaffolded over the suite."""
    make_project(tmp_path, "./e2e", ["checkout.spec.ts", "auth.test.tsx"])
    assert len(run_discovery(rel, tmp_path)) == 2


@pytest.mark.parametrize("rel", CASE_DISCOVERY_FILES, ids=lambda r: Path(r).parent.name)
def test_discovery_falls_back_to_the_playwright_default(rel: str, tmp_path: Path):
    make_project(tmp_path, None, ["smoke.spec.js"])
    assert len(run_discovery(rel, tmp_path)) == 1


@pytest.mark.parametrize("rel", CASE_DISCOVERY_FILES, ids=lambda r: Path(r).parent.name)
def test_discovery_ignores_files_that_are_not_playwright_cases(rel: str, tmp_path: Path):
    """`testMatch` defaults to `**/*.@(spec|test).?(c|m)[jt]s?(x)` — a broader glob
    would count `notes.spec.md` and report a suite that does not exist."""
    make_project(tmp_path, "./e2e", ["notes.spec.md", "readme.test.txt"])
    assert run_discovery(rel, tmp_path) == []


def test_integration_does_not_read_an_empty_result_as_an_empty_directory():
    """An empty result means "no Playwright cases", never "this directory is empty" — a
    `tests/` full of pytest or vitest files produces exactly the same silence. The two
    diverge in any repo that keeps unit tests under the same roof (this one included:
    running the command here against `./tests` returns nothing beside 13 Python files).
    The scaffold action stays right either way; the *stated reason* is what misleads."""
    text = body(REPO / "skills/integration/SKILL.md")
    row = re.search(r"^\| nothing \| (.+?) \|", text, re.M)
    assert row, "integration: the discovery outcome table lost its empty-result row"
    meaning = row.group(1)
    assert "no Playwright cases" in meaning, (
        f"the empty-result row explains itself as {meaning!r}; it must say the directory "
        f"holds no Playwright cases, not that the directory is empty"
    )


@pytest.mark.parametrize("rel", CASE_DISCOVERY_FILES, ids=lambda r: Path(r).parent.name)
def test_discovery_reports_empty_for_a_genuinely_empty_project(rel: str, tmp_path: Path):
    """Zero must stay reachable — it is what legitimately triggers the starter smoke."""
    make_project(tmp_path, "./e2e", [])
    assert run_discovery(rel, tmp_path) == []


def test_discovery_sees_a_previous_runs_smoke_as_an_existing_case(tmp_path: Path):
    """playwright-scaffold is idempotent only if its own output counts as a case."""
    make_project(tmp_path, "./e2e", ["main.smoke.spec.ts"])
    assert len(run_discovery("skills/playwright-scaffold/SKILL.md", tmp_path)) == 1


@pytest.mark.parametrize("rel", CASE_DISCOVERY_FILES, ids=lambda r: Path(r).parent.name)
def test_discovery_distinguishes_a_missing_testdir_from_an_empty_one(rel: str, tmp_path: Path):
    """`find … 2>/dev/null` renders "that directory does not exist" as an empty result —
    identical to "the directory is there and holds no cases". The empty result is what
    authorises scaffolding, so a config pointing at a directory that is not there would
    read as a licence to scaffold. The `[ -d ]` guard makes the two states nameable.

    A control agent on the guardless skill diagnosed it unprompted:
    `이 0은 케이스가 없다는 뜻이 아닙니다 … 2>/dev/null이 이를 '케이스 0건'으로 위장시켰습니다.`
    """
    make_project(tmp_path, "./e2e", None)  # config says ./e2e; the directory is absent
    assert run_discovery(rel, tmp_path) == ["MISSING: ./e2e"]


@pytest.mark.parametrize("rel", CASE_DISCOVERY_FILES, ids=lambda r: Path(r).parent.name)
def test_discovery_names_the_default_when_a_fresh_project_has_no_test_dir(rel: str, tmp_path: Path):
    """No `testDir` in the config and no `./tests`: a project that never had tests. The
    output still names which directory was looked for, so the agent can tell this apart
    from a config that points somewhere wrong."""
    make_project(tmp_path, None, None)
    assert run_discovery(rel, tmp_path) == ["MISSING: ./tests"]
