"""Keep a record of every session the runner could not score as-is, so its cause outlives the run.

The temp workdir and the in-memory transcript are gone the moment a run ends; this is the only
place a timed-out or failed session's last tool call, transcript and stderr survive."""

import json
from datetime import UTC, datetime
from pathlib import Path

import evals.stream as stream
from evals.runner import config

RUNS_DIR = config.REPO / "evals/.runs"
# One directory per process: one CLI invocation is one run, so its records land together.
STAMP = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
INPUT_LIMIT = 300

TIMEOUT = "timeout"
ERRORED = "errored"
NO_INIT = "no_init"
MISSING_SKILL = "missing_skill"


def last_name(obs: stream.Observation) -> str:
    return obs.last_tool["name"] if obs.last_tool else "none"


def _clip(value: object) -> str:
    text = json.dumps(value, ensure_ascii=False)
    return text if len(text) <= INPUT_LIMIT else text[:INPUT_LIMIT] + "..."


def record(
    raw,
    obs: stream.Observation,
    *,
    skill: str,
    arm: str,
    index: int,
    prompt: str,
    fixture: str | None,
    reason: str,
    timeout: int,
) -> Path:
    """Write `<skill>-<arm>-<index>` as a `.json` summary, the `.jsonl` transcript and the
    `.stderr.txt`; return the summary's path. A second record of the same session — a ratchet
    `confirm` re-measures in the same process — gets a `.r<n>` suffix instead of overwriting."""
    out = RUNS_DIR / STAMP
    out.mkdir(parents=True, exist_ok=True)
    stem = f"{skill}-{arm}-{index}"
    attempt = 1
    while (out / f"{stem}.json").exists():
        attempt += 1
        stem = f"{skill}-{arm}-{index}.r{attempt}"
    last = obs.last_tool
    if last is not None:
        last = {"name": last["name"], "input": _clip(last["input"])}
    summary = {
        "skill": skill,
        "arm": arm,
        "index": index,
        "prompt": prompt,
        "fixture": fixture,
        "reason": reason,
        "timed_out": raw.timed_out,
        "timeout_s": timeout,
        "elapsed_s": raw.elapsed,
        "returncode": raw.returncode,
        "tool_calls": obs.tool_calls,
        "last_tool": last,
        "completed": obs.completed,
        "turns_exhausted": obs.turns_exhausted,
        "stderr_tail": [ln for ln in raw.err.strip().splitlines() if ln.strip()][-5:],
    }
    path = out / f"{stem}.json"
    path.write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    # newline="": the process's own bytes, not a Windows-translated copy of them.
    (out / f"{stem}.jsonl").write_text(raw.text, encoding="utf-8", newline="")
    (out / f"{stem}.stderr.txt").write_text(raw.err, encoding="utf-8", newline="")
    return path
