"""Save real session transcripts as candidates for the committed stream fixtures."""

import json
import os
import threading
from pathlib import Path

import evals.stream as stream
from evals.runner import config


def reduce_capture(text: str) -> str:
    """Strip a transcript down to what `stream.observe` reads.

    Kept whole, never re-serialised: the fixtures earn their place by being real CLI bytes, and
    dumping the parsed dict back out would normalise key order, spacing and escapes — leaving a
    rendering of a capture, which can no longer catch a parser assumption. So this drops entire
    lines and touches no surviving one.

    What goes: `hook_*`, `thinking_tokens`, `task_*`, `user` — 83% of the original 332KB and
    never parsed. A line that is not JSON goes too (a killed process ends mid-line; the
    truncation test appends its own rather than relying on one being there)."""
    kept = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("subtype") == "init" or event.get("type") in (
            "assistant",
            "rate_limit_event",
            "result",
        ):
            kept.append(line)
    return "\n".join(kept)


def fixture_role(obs: stream.Observation, skill: str) -> str | None:
    """Which committed fixture this session could stand in for, if any.

    The conditions are the assertions the current fixtures satisfy, read back as requirements —
    a candidate failing one would replace a working fixture with a broken one. `errored` is
    excluded because a failed session is not a clean observation of anything; empty `available`
    means the plugin never loaded, which is the case the fixtures exist to tell apart from a
    real miss.

    `skill` is load-bearing rather than decorative: the suite asserts on a *named* skill
    (`"integration" in obs.fired`), so a session where a different skill fired satisfies every
    structural condition and still produces a fixture the suite rejects."""
    if obs.errored or skill not in obs.available or not obs.tool_calls:
        return None
    if skill in obs.fired and obs.turns_exhausted:
        return "stream-invoked"
    # `not turns_exhausted` matters: the pair's value is that they end differently — one at the
    # turn cap, one on a clean `success`. A capped session that happened not to fire meets every
    # other quiet condition, so without this the two could drift into two turn caps and the
    # success path would stop being covered.
    if not obs.fired and obs.completed and not obs.turns_exhausted:
        return "stream-quiet"
    return None


# The skill `--capture-fixtures` is capturing for, or None when it is off — a name rather than
# a flag because `fixture_role` needs it and `run_session` has no other way to learn it. A
# normal measurement run leaves this None and never touches the fixtures. Set on the module
# rather than threaded through run_session's signature, which every test monkeypatches `_one`
# around.
CAPTURE_FOR: str | None = None
CAPTURED: set[str] = set()
# True once a rate limit cut the run short: workers may still be inside
# maybe_capture when the report prints, so the count is not final.
CAPTURE_PROVISIONAL = False
_CAPTURE_LOCK = threading.Lock()
FIXTURE_ROLES = ("stream-invoked", "stream-quiet")
FIXTURES_DIR = config.REPO / "evals/fixtures"


def _reset_capture_state(skill: str | None = None) -> None:
    """Set every capture global, in one place, always together.

    Four review rounds found the same shape four times: a module global written on one path
    and not another. `CAPTURE_FOR` inherited across calls; `CAPTURE_PROVISIONAL` was added by
    the very commit that fixed `CAPTURE_FOR` and inherited the same way; the autouse test
    fixture reset all three while production reset two — the test was more correct than the
    code it guarded.

    Individually those are one-line fixes, which is why they kept coming back. One function is
    the structural answer: adding a fourth global without resetting it is no longer possible
    without editing this body, and the tests call it rather than reimplementing it."""
    global CAPTURE_FOR, CAPTURE_PROVISIONAL
    CAPTURE_FOR = skill
    CAPTURE_PROVISIONAL = False
    CAPTURED.clear()


def maybe_capture(obs: stream.Observation, out: str, dest_dir: Path | None = None) -> None:
    """Save the first session that could stand in for each committed fixture.

    Writes `<name>.jsonl.new` beside the committed file, never over it. `fixture_role` encodes
    the conditions it knows about; the committed fixtures satisfy seven assertions, so a
    candidate that clears the former is a candidate, not a replacement — swapping stays human.

    First-wins: a later match is not a better one, and rewriting on every hit would make the
    file depend on which of a run's sessions finished last. A leftover `.new` from an earlier
    run wins over this run's sessions, which is worth saying out loud — a rate-limited run
    leaves exactly that state behind."""
    if not CAPTURE_FOR:
        return
    role = fixture_role(obs, CAPTURE_FOR)
    if not role:
        return
    # `dest_dir` resolves here rather than in the signature: a default bound at def time points
    # at the real fixtures directory forever, so a test that reaches this without passing one
    # writes into the repo.
    dest = (dest_dir or FIXTURES_DIR) / f"{role}.jsonl.new"
    # One lock around decide-and-write. Sessions run eight at a time, and check-then-write let
    # three workers past `exists()` at once — observed, three "written" lines for one file and
    # interleaved content. It also keeps the messages below to one per role instead of one per
    # matching session (~25 of the 35 match `stream-quiet`).
    with _CAPTURE_LOCK:
        if role in CAPTURED:
            return
        if dest.exists():
            # Recorded as captured: the file IS the candidate for this role, so reporting it
            # missing afterwards would contradict this line within the same run.
            CAPTURED.add(role)
            print(
                f"  [i] {dest.name} exists from an earlier run — keeping it. Delete it first "
                f"if you want this run's session instead.",
                flush=True,
            )
            return
        # Write to a temp name and rename: `write_text` straight to `dest` can interleave two
        # workers' bytes, and the loser of that race leaves a file that parses as neither.
        # No discriminator in the name — the lock above is what serialises writers, and a
        # pid would imply cross-process protection this does not have.
        tmp = dest.with_name(dest.name + ".tmp")
        tmp.write_text(reduce_capture(out) + "\n", encoding="utf-8")
        os.replace(tmp, dest)
        CAPTURED.add(role)
        print(f"  [+] fixture candidate written: {dest.name}", flush=True)


def report_capture(provisional: bool = False) -> None:
    """Say which fixtures a capture run did NOT get. Silence would read as success.

    `stream-invoked` needs a firing that also spent the turn cap, and MAX_TURNS=6 exists
    precisely to make truncation rare — so the common outcome of a capture run is the quiet
    fixture alone. A run that spends its rate-limit budget and returns half of what was asked
    for should say so.

    `provisional` is for the rate-limit path: `pool.shutdown(wait=False)` cancels only the
    sessions that had not started, so up to `jobs` are still inside `maybe_capture` when this
    runs. Reporting "none" there and then finding a file on disk is worse than saying the count
    is not final yet."""
    if not CAPTURE_FOR:
        return
    missing = [r for r in FIXTURE_ROLES if r not in CAPTURED]
    if not missing:
        return
    tail = (
        " Sessions were still finishing when this printed, so check the directory before "
        "believing it."
        if provisional
        # Only advise a re-run when the count is final — and say the part that makes the advice
        # actionable, since a leftover candidate makes the next run skip that role entirely.
        else " Re-run to try again; delete any leftover .jsonl.new first or it will be kept."
    )
    print(
        f"  [!] no candidate for {', '.join(missing)} — this run's sessions did not meet the "
        f"conditions (stream-invoked needs a firing that also hit the turn cap, which "
        f"MAX_TURNS={config.MAX_TURNS} makes uncommon).{tail}",
        flush=True,
    )
