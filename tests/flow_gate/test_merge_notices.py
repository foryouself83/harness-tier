"""What the merge check says when it lets a merge through without a full verdict."""

import json

import scripts.flow_gate_check as fgc
from tests.flow_gate.test_merge_check import _run_merge_check
from tests.flow_gate.test_merge_spellings import _policy


def _note(capsys) -> str:
    return json.loads(capsys.readouterr().out)["systemMessage"]


def test_a_verdict_that_raises_passes_and_says_so(monkeypatch, tmp_path, capsys):
    _policy(tmp_path)
    monkeypatch.setattr(fgc, "_merges", lambda command: 1 / 0)
    assert _run_merge_check(monkeypatch, tmp_path, "git merge feature/x", "dev") == 0
    note = _note(capsys)
    assert "판정 실패" in note and "ZeroDivisionError" in note


def test_a_judged_merge_says_nothing(monkeypatch, tmp_path, capsys):
    _policy(tmp_path)
    assert _run_merge_check(monkeypatch, tmp_path, "git merge --squash feature/x", "dev") == 0
    assert capsys.readouterr().out == ""
