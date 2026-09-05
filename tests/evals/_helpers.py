import subprocess
from pathlib import Path

import yaml

import evals.scores as scores

REPO = Path(__file__).resolve().parent.parent.parent
CASES = yaml.safe_load((REPO / "evals/cases.yaml").read_text(encoding="utf-8"))
SKILLS = sorted(CASES["skills"])


class _NoRealSessions:
    """Stands in for the `subprocess` module inside `evals.run`, refusing the two spawn
    entry points (`Popen` carries the sessions since the tree-kill change; `run` is the
    taskkill helper and the historical spawn path — refusing both keeps the guard ahead
    of refactors between them).

    Everything else — DEVNULL, TimeoutExpired — is delegated, because `run_session`
    references those too and a bare object would fail with an AttributeError that says
    nothing about why."""

    @staticmethod
    def run(*_args, **_kwargs):
        raise AssertionError(
            "this test tried to spawn a real `claude` session. Every test here must be "
            "model-free: monkeypatch `evals.run._one` to return (stream.Observation(...), "
            "stderr) instead of letting it reach run_session. If a real session is genuinely "
            "what you want, it belongs in `evals/run.py`, not in the suite."
        )

    Popen = run

    def __getattr__(self, attr):
        return getattr(subprocess, attr)


# Real captured `claude -p --output-format stream-json` transcripts, not hand-written JSON —
# which is the point of them, and the reason they are reduced by dropping whole events rather
# than by editing any event's contents. `stream.observe` reads exactly four kinds (`init`,
# `assistant`, `rate_limit_event`, `result`); the captures also carried `hook_response`,
# `hook_started`, `hook_progress`, `thinking_tokens`, `task_*` and `user` events, 83% of the
# 332KB, none of it ever parsed. Those are gone; every surviving event is byte-identical to
# what the CLI emitted.
#
# What survives that reduction is the `init` event, kept whole: it is the source of `available`
# and cannot be trimmed without rewriting a captured event into fiction. These two were captured
# under the isolated config dir `evals.run.isolated_config_dir` builds, so `init` lists
# `harness-tier@inline` as its only plugin — the earlier captures carried the whole machine
# instead (18 plugins with absolute paths, one of them private, plus the home directory), and
# that is gone. What the isolation cannot strip stays: the account-level claude.ai MCP connectors
# still appear by name (no tokens — `apiKeySource` is `none`), because they are scoped to the
# account, not the config dir.
# Both were captured at the current `MAX_TURNS` = 6, so there is no capture-date ambiguity to
# reason around: `stream-invoked` is a real turn-cap firing (`error_max_turns`, num_turns 7) and
# `stream-quiet` a clean `success` (num_turns 9). The pair is read for tool calls per turn, which
# is what `test_a_spent_turn_cap_cannot_be_ambiguous_at_this_budget` uses it for.
FIXTURES = REPO / "evals/fixtures"
OK = {
    "description_sha": "x",
    "model": scores.MODEL,
    "invoke_rate": 0.93,
    "invoke_hits": 14,
    "invoke_n": 15,
    "false_fire": 0.0,
    "false_hits": 0,
    "false_n": 15,
}
# The declared expectation and family size `check` is exercised with. It takes both explicitly
# rather than reading cases.yaml, so a unit test can vary them without a fixture. 0.80 against
# OK's 14/15 clears the significance bar; 7 is the shipped skill-family size.
EXPECT = 0.80
N_SKILLS = 7
