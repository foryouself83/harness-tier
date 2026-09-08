import json
import re
from unittest import mock

import evals.scores as scores
from tests.evals._helpers import CASES, REPO, SKILLS


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


def test_a_hook_assisted_skill_refingerprints_when_the_injected_text_changes(tmp_path):
    """An edit to the injected rule must invalidate a `hook_assisted` skill's recorded score.

    Measured 2026-09-08: `/flow` scored 0.82 (n=55) and 0.55 (n=65) on a byte-identical
    description, the whole difference being two lines added to `rules/risk-tiers.md`
    immediately before its "FIRST action" mandate. `description_sha` hashed the description
    alone, so the drop landed with no signal and survived four commits — the entry in
    `cases.yaml` had said to read a flow regression as description *and* hook, and nothing
    mechanical held anyone to it.

    The injected text is monkeypatched rather than edited in place: this suite has to stay
    runnable on a dirty tree, and a test that rewrites a shipped rule file to assert a hash
    is one interrupted run away from leaving it rewritten."""
    before = {n: scores.description_sha(n) for n in SKILLS}

    edited = tmp_path / "risk-tiers.md"
    edited.write_text("# not the shipped rule\n", encoding="utf-8")
    with mock.patch.object(scores, "INJECTED", (edited,)):
        after = {n: scores.description_sha(n) for n in SKILLS}

    assisted = [n for n in SKILLS if CASES["skills"][n].get("hook_assisted")]
    assert assisted, "cases.yaml declares no hook_assisted skill — this test proves nothing"
    for name in assisted:
        assert before[name] != after[name], (
            f"{name}: declares hook_assisted, but its fingerprint ignored a changed injected "
            f"rule — an edit to rules/risk-tiers.md would keep a stale score passing the gate."
        )
    for name in SKILLS:
        if name not in assisted:
            assert before[name] == after[name], (
                f"{name}: does not declare hook_assisted, yet the injected rule moved its "
                f"fingerprint — every edit to that file would force a needless re-measure."
            )


def test_a_hook_assisted_fingerprint_does_not_depend_on_line_endings(tmp_path):
    """Same injected text, two checkouts, one fingerprint.

    `INJECTED` is hashed as bytes while every other input reaches the digest through
    `read_text`, which normalizes. This repo checks out CRLF on Windows and LF on the ubuntu
    runner, so the raw-byte digest fingerprinted the checkout instead of the content: a score
    measured on Windows read as stale in CI (`commit: description changed since the score`),
    and re-measuring in CI would have broken it the other way round. `_copied_file_sha` in
    `outcome.py` had already met this and normalizes; this is the sibling that had not.

    Monkeypatched rather than rewritten in place, for the reason the test above gives."""
    assisted = [n for n in SKILLS if CASES["skills"][n].get("hook_assisted")]
    assert assisted, "cases.yaml declares no hook_assisted skill — this test proves nothing"
    stand_in = tmp_path / "risk-tiers.md"

    def _fingerprints(newline: str) -> dict[str, str]:
        stand_in.write_bytes(f"# rule{newline}mandate{newline}".encode())
        with mock.patch.object(scores, "INJECTED", (stand_in,)):
            return {n: scores.description_sha(n) for n in assisted}

    assert _fingerprints("\n") == _fingerprints("\r\n")
