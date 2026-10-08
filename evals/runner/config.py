"""Constants the runner modules and both CLIs share."""

from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
CASES = REPO / "evals/cases.yaml"

# Measured under isolation, 5 happy samples of `integration`:
#   3 turns -> invoke_rate 0.2, truncated 0.80   (the score was measuring this constant)
#   6 turns -> invoke_rate 0.2, truncated 0.20   (budget adequate; the rate is real)
MAX_TURNS = 6

# The pinned model lives in scores.MODEL: the gate validates each entry's fingerprint
# against it, so the pin and the check cannot drift apart. It is a full model ID — the
# "opus" alias that held this slot retargeted with every Opus release, silently changing
# what the baseline described (measured spread on one case: 0/4 vs 4/4 across models).

# A hang guard, not a measurement bound. `MAX_TURNS` already ends a session; this only stops
# one that has stopped making progress from holding a worker forever.
#
# A cap short enough to cut a session off measures the cap, not the skill: under eight-way
# load the mean session runs 58s, and at 30s three quarters of every miss is a session stopped
# before it could decide. Sessions run to their natural end.
SESSION_TIMEOUT = 180
JOBS = 8
# The run default a per-skill `reps:` in cases.yaml overrides. Named so the suite can pin
# the override against it rather than restating the number.
DEFAULT_REPS = 3

# Measured under eight-way load: 35 sessions finished in 252s. Solo they run ~45s — running
# eight at once stretches each one. This drives the estimate only; SESSION_TIMEOUT is a guard,
# and multiplying by it instead reported 92 minutes for a 30-minute run.
SECONDS_PER_SESSION = 58

# Observed ceiling on how late a firing arrives: across every capture, a skill that fires has
# fired by the third tool call. A session cut before that never got its chance and is genuinely
# ambiguous; one cut after five tool calls without firing had its chance and declined. Counting
# every cut session as ambiguous instead pinned the warning permanently on at 0.80 while
# `invoke_rate` sat unmoved at 0.20 across three timeouts — and a warning that always fires is
# not a signal.
FIRE_BY_TOOL_CALL = 3
