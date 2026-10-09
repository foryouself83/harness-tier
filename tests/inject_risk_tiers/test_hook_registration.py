"""Which session events reach the plugin's hooks, for Claude and for Codex."""

import json
from pathlib import Path

import pytest

import scripts.teams_alert as ta

ROOT = Path(__file__).resolve().parents[2]
CLAUDE = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))["hooks"]
CODEX = json.loads((ROOT / "hooks" / "codex" / "hooks.json").read_text(encoding="utf-8"))["hooks"]


@pytest.mark.parametrize("hooks", [CLAUDE, CODEX], ids=["claude", "codex"])
def test_every_session_source_receives_the_rule(hooks):
    """A resumed or forked session starts without the rule unless SessionStart fires for it."""
    (entry,) = hooks["SessionStart"]
    assert set(entry["matcher"].split("|")) == {"startup", "resume", "clear", "compact", "fork"}


def test_only_a_wait_for_the_user_posts_the_waiting_card():
    """Unmatched, every notification (`auth_success`, `agent_completed`…) posts "waiting for
    input" and spawns python on each."""
    (entry,) = CLAUDE["Notification"]
    assert set(entry["matcher"].split("|")) == {
        "permission_prompt",
        "idle_prompt",
        "elicitation_dialog",
        "elicitation_url_dialog",
        "agent_needs_input",
    }


def test_the_post_fits_inside_the_notification_hook_timeout():
    """Past the hook's timeout the process is killed and the card is never sent."""
    (entry,) = CLAUDE["Notification"]
    (hook,) = entry["hooks"]
    assert ta.GIT_TIMEOUT + ta.POST_TIMEOUT < hook["timeout"]
