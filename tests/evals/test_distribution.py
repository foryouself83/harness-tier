import json
from pathlib import Path

import pytest

import evals.run as run
import evals.stream as stream
from tests.evals._helpers import REPO

MANIFESTS = [".claude-plugin/plugin.json", ".claude-plugin/marketplace.json"]


@pytest.mark.parametrize("manifest", MANIFESTS)
def test_the_eval_harness_is_never_distributed_to_consumers(manifest: str):
    """`evals/` is dev tooling — cases, a baseline, and a runner that spends this developer's
    rate-limit budget. This plugin installs from a GitHub source, so anything a manifest names
    ships to every consumer. It was the one Global Constraint in the plan with nothing
    enforcing it, which is the kind that holds right up until someone adds a `files` key."""
    text = (REPO / manifest).read_text(encoding="utf-8")
    assert "evals" not in text, f"{manifest} references evals/ — it must not ship to consumers"

    # The raw scan above is the real assertion and it is total. This walks the parsed shape
    # as well so the test keeps meaning something if a manifest ever grows nested component
    # paths: today neither file has a path list at all (plugin.json is four metadata keys,
    # marketplace.json adds a `source` pointing at the repo), and both rely on components
    # being auto-discovered from their default locations — which is precisely why `evals/`
    # is safe today and why nothing was stopping someone from listing it tomorrow.
    def strings(node):
        if isinstance(node, dict):
            for key, value in node.items():
                yield key
                yield from strings(value)
        elif isinstance(node, list):
            for item in node:
                yield from strings(item)
        elif isinstance(node, str):
            yield node

    named = [s for s in strings(json.loads(text)) if "evals" in s]
    assert not named, f"{manifest} names {named} — the eval harness must not ship"


def test_a_session_that_never_reached_init_is_unusable_not_a_miss(monkeypatch):
    """An empty Observation — a dead spawn, or a process that never produced a stream — has
    completed=False and tool_calls=0, so scoring it reads as a miss *and* as truncated. The
    old guard only asked whether *any* session in the run saw the plugin, so 14 of 15 dead
    sessions still produced a published number. The judgement has to be per session, and it
    has to abort rather than warn: there is no rate to record."""
    name = "integration"
    entry = {"happy": ["h0", "h1"], "negative": ["n0"]}
    healthy = stream.Observation(available=[name], completed=True, tool_calls=5)
    dead = stream.Observation()  # what observe("") returns

    def fake_one(prompt, fixture, config_dir, restricted):
        return (dead, "claude: command not found\n") if prompt == "h1" else (healthy, "")

    monkeypatch.setattr(run, "_one", fake_one)
    with pytest.raises(SystemExit) as e:
        run.measure(name, entry, reps=1, config_dir=Path("."), jobs=1)
    assert "never reached the init event" in str(e.value)
    # The cause is the only thing that makes the abort actionable, and it lives in stderr.
    # Capturing stderr and never reading it is how the reason for a dead session got lost.
    assert "command not found" in str(e.value)


def test_stderr_reaches_the_failure_message_without_reaching_observe(monkeypatch):
    """`stream.observe` answers questions about the transcript; stderr is a fact about the
    process. The tail belongs in the runner's error path only — if it ever became an
    Observation field, the parser would be reading something it cannot see."""
    assert "stderr" not in stream.Observation().__dict__
    assert run._tail("a\nb\nc\nd\ne\nf\ng\n", lines=2).splitlines()[-1].strip() == "g"
    assert run._tail("   \n  \n") == ""
