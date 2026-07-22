"""Read a `claude -p --output-format stream-json` transcript.

Two questions, both answered from events rather than from anything the model says about
itself: which plugin skills the session was *offered* (the `init` event) and which ones it
actually *invoked* (`tool_use` blocks named `Skill`).
"""

import json
from dataclasses import dataclass, field

PLUGIN = "harness-tier"
_PREFIX = f"{PLUGIN}:"


@dataclass
class Observation:
    available: list[str] = field(default_factory=list)
    fired: list[str] = field(default_factory=list)
    turns_exhausted: bool = False
    rate_limited: bool = False
    errored: bool = False
    completed: bool = False
    tool_calls: int = 0


def _local(name: str) -> str | None:
    return name[len(_PREFIX) :] if name.startswith(_PREFIX) else None


def observe(text: str) -> Observation:
    obs = Observation()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # A partial trailing line is how a killed process ends. Everything before it
            # already happened, so dropping the run over it would lose a real result.
            continue
        if event.get("subtype") == "init":
            obs.available = [s for n in event.get("skills") or [] if (s := _local(n))]
        elif event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") != "tool_use":
                    continue
                # How far the session got before it was cut. A kill after several tool calls
                # is a session that had its chance and did not take it; a kill after none is
                # a session that never got to say.
                obs.tool_calls += 1
                if block.get("name") == "Skill":
                    # `or ""`, not a .get default: an aborted call serializes as
                    # {"skill": null}, and .get's default only covers a *missing* key —
                    # None.startswith would kill observe() for the whole stream.
                    name = _local((block.get("input") or {}).get("skill") or "")
                    if name:
                        obs.fired.append(name)
        elif event.get("type") == "rate_limit_event":
            # Only an actual refusal stops a run. A warning-level status rides on a session
            # whose request *succeeded*; treating any non-"allowed" status as fatal made
            # every run started late in the window abort on its first session. An unknown
            # exhausted-but-not-"rejected" status still fails loudly downstream: refused
            # requests error the session and trip `errored`.
            if (event.get("rate_limit_info") or {}).get("status") == "rejected":
                obs.rate_limited = True
        elif event.get("type") == "result":
            obs.turns_exhausted = event.get("subtype") == "error_max_turns"
            # A turn cap reports is_error too, so the cap has to be excluded before the flag
            # means anything. What is left is a session that failed outright — above all an
            # unauthenticated config dir, which still emits a well-formed init event and
            # would otherwise be scored as "the skill did not fire".
            #
            # Excluding the cap by name (a blacklist) rather than admitting `success` by name
            # (a whitelist) is deliberate: the CLI also emits `error_during_execution`, and a
            # whitelist left that one with errored=False, turns_exhausted=False, completed=True
            # — a failed session tallied as a clean miss, silently. An unknown future subtype
            # must fail loudly here; the only subtype that is a legitimate observation despite
            # is_error is the turn cap, and it is the only one named.
            obs.errored = bool(event.get("is_error")) and event.get("subtype") != "error_max_turns"
            # Sessions are killed on a timeout, and a killed one carries no result event at
            # all. Without this the runner cannot tell "the skill did not fire" from "the
            # session never got far enough to say".
            obs.completed = True
    return obs
