import json
import re

from tests.evals._helpers import CASES, REPO


def _injected_session_text() -> str:
    """Everything the SessionStart hook puts into a session, not only the rule file.

    `hooks/inject-risk-tiers.sh` wraps `rules/risk-tiers.md` in a hardcoded preamble, and that
    preamble is the *strongest* form the help takes — it says outright that the agent's action
    MUST be to invoke /flow. Reading only the rule file would miss it, and would also report
    "the help is gone" if someone rewrote the rule file's slash forms into prose while the
    preamble kept naming the skill.

    None of it reaches a session unless `hooks.json` still registers the script for `startup`.
    Narrowing that matcher would end the help while both files still named the skills, so this
    returns "" in that case — the reverse check then reports the caveat as stale, which is what
    it would be."""
    hooks = json.loads((REPO / "hooks/hooks.json").read_text(encoding="utf-8"))
    registered = any(
        "startup" in (entry.get("matcher") or "")
        and any("inject-risk-tiers" in h.get("command", "") for h in entry.get("hooks") or [])
        for entry in hooks.get("hooks", {}).get("SessionStart") or []
    )
    if not registered:
        return ""
    return "\n".join(
        (REPO / p).read_text(encoding="utf-8")
        for p in ("hooks/inject-risk-tiers.sh", "rules/risk-tiers.md")
    )


def _skills_named_as_commands(text: str) -> set[str]:
    """Measured skills the injected text tells the agent to run, by their `/name` form.

    Intersected with the measured set rather than returned raw: a bare `/([a-z-]+)` matches
    `and/or`, `lint/static/import_lint/test` and `integration/staging/production` — 37 tokens
    in the current rule file, most of which are not invocations. Left unrestricted, reordering
    one branch-role list to `staging/integration` would force a false `hook_assisted` onto the
    `integration` skill, which the same file explicitly calls a branch role and not a skill.

    The boundary has to exclude a following hyphen, not only a following word character: `\\b`
    matches between `w` and `-`, so `/flow` would be found inside `/flow-init`,
    `/flow-uninstall` and the link `](../flow-tiers.yaml)` — leaving `flow` permanently in the
    named set and disabling the reverse stale check for it."""
    return {name for name in CASES["skills"] if re.search(rf"/{re.escape(name)}(?![\w-])", text)}


def test_the_hook_scan_does_not_match_a_longer_name_or_a_path():
    """`/flow` must not be found inside `/flow-init`, `/flow-uninstall`, or the markdown link
    `](../flow-tiers.yaml)` that the rule file already contains.

    A `\\b` boundary matches immediately before a hyphen, so it read all three as invocations —
    which would keep `flow` in the named set from a relative link alone and make the reverse
    "the help is gone" branch unable to fire for the skill it matters most for. The broader
    `/([a-z][a-z0-9-]*)` form this replaced did not have that failure (it tokenised
    `flow-tiers`); the fix has to beat both."""
    assert _skills_named_as_commands("see [flow-tiers.yaml](../flow-tiers.yaml)") == set()
    assert _skills_named_as_commands("run /flow-uninstall to remove the gate") == set()
    assert _skills_named_as_commands("`/flow-init` copies the scripts") == set()
    # …while still finding the real ones, punctuation and all.
    assert _skills_named_as_commands("enter `/flow` first") == {"flow"}
    assert _skills_named_as_commands("2. Run /doc-sync to harmonize.") == {"doc-sync"}


def test_every_skill_the_injected_rule_names_declares_hook_assisted():
    """The SessionStart hook injects its text into EVERY session, so a skill it tells the agent
    to run is measured with help that no consumer-free reading would give it. That is deliberate
    — consumers get the hook too — but it has two consequences per affected skill: its rate is
    not comparable to the others, and its ratchet is partly blind to its own description, since
    the hook can hold the number up while the description rots.

    This is checked rather than commented because the comment was wrong twice over. It sat only
    on `flow` and read "flow is the one skill measured with outside help" while the same rule
    names `/doc-sync` as a step in both the Docs and Dev workflows; the replacement note then
    put a hand-counted number on that and got it wrong too. No count is written down here — the
    check reads the text."""
    named = _skills_named_as_commands(_injected_session_text())
    measured = set(CASES["skills"])
    for name in sorted(named & measured):
        assert CASES["skills"][name].get("hook_assisted") is True, (
            f"{name}: the injected session text names /{name}, and it reaches every eval "
            f"session — declare `hook_assisted: true` in cases.yaml and say in the entry what "
            f"the hook does for it."
        )
    for name in sorted(measured):
        if CASES["skills"][name].get("hook_assisted") and name not in named:
            raise AssertionError(
                f"{name}: declares hook_assisted but nothing the SessionStart hook injects "
                f"names /{name} any more — the help is gone, so the caveat is stale and the "
                f"rate is now comparable to the unassisted skills."
            )
