import json
import os

import evals.stream as stream
from evals.runner import diagnose
from tests.evals._helpers import raw


def _obs(**kw):
    return stream.Observation(available=["doc-sync"], tool_calls=4, **kw)


def _sibling(path, suffix):
    return path.with_name(path.name.removesuffix(".json") + suffix)


def test_record_writes_summary_transcript_and_stderr(runs_dir):
    r = raw(
        '{"type":"assistant"}\n',
        "에러 발생\nlast line\n",
        timed_out=True,
        elapsed=180.2,
        returncode=-9,
    )
    obs = _obs(last_tool={"name": "Bash", "input": {"command": "pytest -x"}})
    path = diagnose.record(
        r,
        obs,
        skill="doc-sync",
        arm="happy",
        index=3,
        prompt="문서 갱신해줘",
        fixture="doc-sync-drift",
        reason=diagnose.TIMEOUT,
        timeout=180,
    )
    assert path == runs_dir / diagnose.STAMP / "doc-sync-happy-3.json"
    summary = json.loads(path.read_text(encoding="utf-8"))
    assert summary["reason"] == "timeout"
    assert summary["timed_out"] is True
    assert summary["prompt"] == "문서 갱신해줘"
    assert summary["fixture"] == "doc-sync-drift"
    assert summary["elapsed_s"] == 180.2
    assert summary["timeout_s"] == 180
    assert summary["returncode"] == -9
    assert summary["tool_calls"] == 4
    assert summary["last_tool"] == {"name": "Bash", "input": '{"command": "pytest -x"}'}
    assert summary["stderr_tail"] == ["에러 발생", "last line"]
    # Byte-for-byte: a transcript re-encoded or newline-translated is no longer what ran.
    assert _sibling(path, ".jsonl").read_bytes() == r.text.encode("utf-8")
    assert _sibling(path, ".stderr.txt").read_bytes() == r.err.encode("utf-8")


def test_record_clips_a_long_tool_input(runs_dir):
    obs = _obs(last_tool={"name": "Write", "input": {"content": "x" * 5000}})
    path = diagnose.record(
        raw(),
        obs,
        skill="s",
        arm="negative",
        index=0,
        prompt="p",
        fixture=None,
        reason=diagnose.ERRORED,
        timeout=180,
    )
    clipped = json.loads(path.read_text(encoding="utf-8"))["last_tool"]["input"]
    assert len(clipped) == diagnose.INPUT_LIMIT + len("...")
    assert clipped.endswith("...")


def test_record_without_a_tool_call(runs_dir):
    path = diagnose.record(
        raw(),
        stream.Observation(),
        skill="s",
        arm="outcome",
        index=0,
        prompt="p",
        fixture=None,
        reason=diagnose.NO_INIT,
        timeout=300,
    )
    assert json.loads(path.read_text(encoding="utf-8"))["last_tool"] is None


def test_last_name():
    assert diagnose.last_name(stream.Observation()) == "none"
    assert diagnose.last_name(_obs(last_tool={"name": "Read", "input": {}})) == "Read"


def test_a_second_record_of_the_same_session_never_overwrites_the_first(runs_dir):
    """A ratchet `confirm` re-measures the skill in the same process, so the same
    skill-arm-index can time out twice under one STAMP; the first record must survive."""
    kw = dict(
        skill="s",
        arm="happy",
        index=4,
        prompt="p",
        fixture=None,
        reason=diagnose.TIMEOUT,
        timeout=180,
    )
    first = diagnose.record(raw("first"), stream.Observation(), **kw)
    second = diagnose.record(raw("second"), stream.Observation(), **kw)
    assert first != second
    assert _sibling(first, ".jsonl").read_text(encoding="utf-8") == "first"
    assert _sibling(second, ".jsonl").read_text(encoding="utf-8") == "second"


def test_each_process_writes_its_own_run_directory():
    """Two runs started in the same UTC second must not share a directory and race on a stem."""
    assert diagnose.STAMP.endswith(f"-{os.getpid()}")
