import subprocess
from dataclasses import fields, replace
from pathlib import Path

import evals.outcome as outcome
import evals.run as run
import scripts.skill_sandbox as sandbox


class _CapturingSubprocess:
    """Records the argv and communicate timeout without spawning claude. A test that needs to
    inspect the command overrides the autouse no_real_sessions guard with an instance of this."""

    DEVNULL = subprocess.DEVNULL
    PIPE = subprocess.PIPE
    TimeoutExpired = subprocess.TimeoutExpired

    def __init__(self):
        self.captured = {}

    def Popen(self, cmd, **kwargs):
        self.captured["cmd"] = cmd
        cap = self.captured

        class _Proc:
            def communicate(self, timeout=None):
                cap["timeout"] = timeout
                return (b"", b"")

        return _Proc()


def test_claude_stream_defaults_reproduce_the_scored_command(monkeypatch):
    fake = _CapturingSubprocess()
    monkeypatch.setattr(run, "subprocess", fake)
    run._claude_stream("p", None, Path("."), Path("cfg"))
    cmd = fake.captured["cmd"]
    assert cmd[cmd.index("--max-turns") + 1] == str(run.MAX_TURNS)
    assert "--permission-mode" not in cmd
    assert "--add-dir" not in cmd
    assert fake.captured["timeout"] == run.SESSION_TIMEOUT


def test_claude_stream_threads_the_outcome_flags(monkeypatch):
    fake = _CapturingSubprocess()
    monkeypatch.setattr(run, "subprocess", fake)
    run._claude_stream(
        "p",
        None,
        Path("."),
        Path("cfg"),
        permission_mode="bypassPermissions",
        add_dirs=(run.REPO,),
        max_turns=25,
        timeout=300,
    )
    cmd = fake.captured["cmd"]
    assert cmd[cmd.index("--permission-mode") + 1] == "bypassPermissions"
    assert cmd[cmd.index("--add-dir") + 1] == str(run.REPO)
    assert cmd[cmd.index("--max-turns") + 1] == "25"
    assert fake.captured["timeout"] == 300


def test_outcome_sha_is_sensitive_to_body_fixture_and_golden():
    s = sandbox.BY_NAME["doc-sync-drift"]
    base = outcome.outcome_sha("doc-sync", s)
    assert outcome.outcome_sha("doc-sync", s) == base  # stable when nothing changes
    moved_golden = replace(s, outcome={**s.outcome, "README.md": {"must_contain": ["7070"]}})
    assert outcome.outcome_sha("doc-sync", moved_golden) != base
    moved_files = replace(s, files={**s.files, "README.md": "port 1234\n"})
    assert outcome.outcome_sha("doc-sync", moved_files) != base
    # The prompt drives what the agent does, so it is part of the outcome's validity.
    moved_prompt = replace(s, prompt="Do something else entirely.")
    assert outcome.outcome_sha("doc-sync", moved_prompt) != base
    # A different skill's SKILL.md is a different body.
    assert outcome.outcome_sha("integration", s) != base
    # The fixture is more than `files`: a copied-in gate script and the git seeding are
    # both state the run depends on, so a baseline must go stale when either changes.
    w = sandbox.BY_NAME["wiki-init-migration"]
    w_base = outcome.outcome_sha("wiki-init", w)
    assert outcome.outcome_sha("wiki-init", replace(w, copy_from_repo={})) != w_base
    assert outcome.outcome_sha("wiki-init", replace(w, git=False)) != w_base


def test_outcome_sha_moves_when_a_copied_file_changes(tmp_path: Path, monkeypatch):
    # copy_from_repo names files the run executes against, and its mapping reads identically
    # whether or not they were edited: a fingerprint over the mapping alone reports fresh for
    # a fixture whose behaviour has already changed. The scenario here is held fixed and only
    # the bytes on disk move, which is the case no field-level mutation can reach.
    s = sandbox.BY_NAME["wiki-init-migration"]
    assert s.copy_from_repo, "the scenario stopped copying anything in"
    skill_md = tmp_path / "skills" / "wiki-init" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("body\n", encoding="utf-8")
    for src in s.copy_from_repo.values():
        stand_in = tmp_path / src
        stand_in.parent.mkdir(parents=True, exist_ok=True)
        stand_in.write_text("original\n", encoding="utf-8")
    monkeypatch.setattr(outcome, "REPO", tmp_path)

    base = outcome.outcome_sha("wiki-init", s)
    edited = tmp_path / next(iter(s.copy_from_repo.values()))
    edited.write_text("changed\n", encoding="utf-8")
    assert outcome.outcome_sha("wiki-init", s) != base


def test_outcome_sha_does_not_depend_on_line_endings(tmp_path: Path, monkeypatch):
    # This repo checks out CRLF on Windows and LF on the ubuntu runner, so a digest taken over
    # raw bytes gives the two platforms different fingerprints for identical content: whichever
    # one measures, the other reads the committed baseline as stale, and re-measuring to fix it
    # breaks the first. Every other fingerprint input arrives through read_text, which
    # normalizes, so the copied sources have to as well.
    s = sandbox.BY_NAME["wiki-init-migration"]
    assert s.copy_from_repo, "the scenario stopped copying anything in"
    skill_md = tmp_path / "skills" / "wiki-init" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("body\n", encoding="utf-8")
    monkeypatch.setattr(outcome, "REPO", tmp_path)

    def _write(newline: str) -> str:
        for src in s.copy_from_repo.values():
            stand_in = tmp_path / src
            stand_in.parent.mkdir(parents=True, exist_ok=True)
            stand_in.write_bytes(f"one{newline}two{newline}".encode())
        return outcome.outcome_sha("wiki-init", s)

    assert _write("\n") == _write("\r\n")


def test_outcome_sha_survives_a_copy_source_that_is_not_a_usable_path(monkeypatch):
    # A path that cannot even be joined or opened is the same situation as one that is not
    # there: the scenario is broken and build() is where that gets said. OSError alone leaves
    # a non-str value and an embedded NUL to escape as a crash out of the fingerprint.
    s = sandbox.BY_NAME["wiki-init-migration"]
    for bad in (3, "a" + chr(0) + "b"):
        broken = replace(s, copy_from_repo={"dest": bad})
        assert outcome.outcome_sha("wiki-init", broken)


def test_outcome_sha_survives_a_copy_source_that_is_not_there(tmp_path: Path, monkeypatch):
    # A scenario naming a path that does not exist is broken, and build() is where that is
    # reported. Fingerprinting it must not raise: outcome_sha is also walked field by field
    # by the coverage test above, whose generic dict mutation invents exactly such a path.
    s = sandbox.BY_NAME["wiki-init-migration"]
    skill_md = tmp_path / "skills" / "wiki-init" / "SKILL.md"
    skill_md.parent.mkdir(parents=True)
    skill_md.write_text("body\n", encoding="utf-8")
    monkeypatch.setattr(outcome, "REPO", tmp_path)
    assert outcome.outcome_sha("wiki-init", s)


def _other_value(current):
    """Some value of the same shape that differs from `current` — for mutating one field of
    a Scenario without knowing which field it is."""
    if isinstance(current, bool):
        return not current
    if isinstance(current, dict):
        return {**current, "__sentinel__": "x"}
    if isinstance(current, list):
        return [*current, "__sentinel__"]
    raise AssertionError(f"unhandled Scenario field type {type(current)!r} — extend this helper")


def test_outcome_sha_covers_every_scenario_field_without_being_told():
    """A field added to Scenario must land in the fingerprint on its own.

    The version that listed fields by hand shipped `copy_from_repo` and `git` outside the
    payload: the fixture could change while every baseline still reported fresh, which is
    the one thing the fingerprint exists to prevent. An allowlist cannot catch the field
    nobody remembered to add to it — only reading the whole scenario can. This test is the
    guard for the *next* field, so it must not name today's.

    The exemptions are asserted in the same loop rather than skipped: an entry quietly added
    to SHA_EXEMPT reopens the same hole by another route, so each has to be a field that
    genuinely cannot change what the run does."""
    s = sandbox.BY_NAME["wiki-init-migration"]
    base = outcome.outcome_sha("wiki-init", s)
    for f in fields(sandbox.Scenario):
        current = getattr(s, f.name)
        mutated = "sentinel" if isinstance(current, str) else _other_value(current)
        moved = outcome.outcome_sha("wiki-init", replace(s, **{f.name: mutated}))
        if f.name in outcome.SHA_EXEMPT:
            assert moved == base, (
                f"Scenario.{f.name} is exempt, but changing it moved the fingerprint — the "
                f"exemption claims it cannot affect the run"
            )
        else:
            assert moved != base, (
                f"Scenario.{f.name} is outside outcome_sha — the fixture can change under a "
                f"baseline that still reports fresh"
            )
    assert outcome.SHA_EXEMPT == frozenset({"why", "expect", "reject"}), (
        "SHA_EXEMPT grew: every entry must be prose that build() and check_outcome never read"
    )
