import json
from pathlib import Path

import pytest

from tests.flow_init._helpers import MALFORMED, _gate_hook, _planted


def test_the_gate_answerer_is_copied_before_the_runner_that_asks_it():
    """precommit-runner.sh routes on what flow_gate_check.py --classify answers, so a sync that
    lands the runner first leaves a window where the new runner asks a script that does not know
    the question — it reads no verdict and gates nothing. The other order is harmless: an old
    runner's question goes unanswered and ROOT stays on main, which is the documented FAIL-OPEN.
    """
    from scripts.flow_init_setup import COPY_FILES

    files = COPY_FILES
    # The whole chain, not one link: flow_gate_check.py imports _harness_paths, so landing
    # it first beside a stale module answers every question with ModuleNotFoundError.
    for earlier, later in (
        ("scripts/_harness_paths.py", "scripts/flow_gate_check.py"),
        ("scripts/flow_gate_check.py", "scripts/precommit-runner.sh"),
    ):
        assert files.index(earlier) < files.index(later), (earlier, later)


def test_a_gate_entry_under_another_tool_is_repaired(tmp_path: Path):
    """The matcher is the gate's identity too. An entry naming this script under another
    tool is a hook that never fires on a commit, and counting it as the gate leaves the
    host reporting a gate it does not have."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    planted = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Read",
                    "hooks": [
                        {
                            "type": "command",
                            "shell": "bash",
                            "command": fis.GATE_COMMAND,
                            "timeout": 600,
                            "statusMessage": fis.GATE_STATUS,
                        }
                    ],
                }
            ]
        }
    }
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text(json.dumps(planted), encoding="utf-8")
    fis.register_gate(tmp_path)
    after = json.loads(settings.read_text(encoding="utf-8"))
    firing = [
        e
        for e in after["hooks"]["PreToolUse"]
        if any(fis._is_gate_hook(h) for h in e.get("hooks") or [])
    ]
    assert [e["matcher"] for e in firing] == ["Bash"], after["hooks"]["PreToolUse"]


def test_a_hook_the_host_wrote_stays_where_the_host_put_it(tmp_path: Path):
    """An entry is a container for several hooks, and it is the HOST's. Rewriting its matcher
    to reach our hook re-points every other hook in it at another tool — the host's audit hook
    would start firing on Bash, which is a change to config this plugin does not own."""
    import scripts.flow_init_setup as fis

    theirs = {"type": "command", "command": "my-audit.sh"}
    settings = _planted(tmp_path, [{"matcher": "Read", "hooks": [_gate_hook(), theirs]}])
    fis.register_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    survivors = [e for e in pre if theirs in (e.get("hooks") or [])]
    assert [e["matcher"] for e in survivors] == ["Read"], pre
    assert any(
        e.get("matcher") == "Bash" and any(fis._is_gate_hook(h) for h in e.get("hooks") or [])
        for e in pre
    ), pre


def test_a_matcher_that_already_covers_bash_is_left_alone(tmp_path: Path):
    """`Bash|Write` fires on a commit, so it is the gate. Narrowing it to `Bash` would silently
    drop the Write coverage the host asked for, and nothing about the gate needs it gone."""
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": "Bash|Write", "hooks": [_gate_hook()]}])
    out = fis.register_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert [e["matcher"] for e in pre] == ["Bash|Write"], pre
    assert "skip" in out, out


# Spellings the hooks reference defines as one tool name or a `|` list of them, in the one form
# every host version reads the same way. Each fires on a commit, so the gate is already
# registered under it and touching the entry would drop coverage the host asked for.
COVERS_BASH = [
    "Bash",
    "Bash|Write",
    "Bash|",
    "|Bash",
    "Bash||Write",
    "Bash| Write",
    "Bash|code-reviewer",
    "Write|Read|Bash",
    "Bash|tool_2",
    "*",
    "",
]
# Spellings that name no tool a commit arrives through. Both readings agree, so the gate hook
# comes out of the entry and the entry keeps everything else.
COVERS_NOTHING = ["Read", "bash", "Write|Edit", "Write, Edit"]
# Spellings this script cannot decide. A matcher outside the name alphabet is a JavaScript
# regular expression and Python's dialect disagrees with it (`(?i)` and `\Z` are Python's
# alone); the comma separator and the whitespace around a name are newer than the oldest host
# this runs on, which reads the same text as a pattern. Undecided leaves the entry exactly as
# the host wrote it AND gives the gate an entry of its own, so the gate exists either way.
CANNOT_DECIDE = [
    ["Bash"],
    7,
    False,
    0,
    {"tool": "Bash"},
    "Bash, Write",
    "Bash,Write",
    "ash|x-y",
    "Bash | Write",
    "Bash ",
    "Write, Bash",
    "^Bash$",
    ".*",
    "Bash|.*",
    "Bash|mcp__x.y",
    "^Notebook",
    "mcp__.*",
    "Bash[",
    "(?i)bash",
    "Bash" + chr(92) + "Z",
]


def _firing(pre: list) -> list:
    import scripts.flow_init_setup as fis

    return [e for e in pre if any(fis._is_gate_hook(h) for h in e.get("hooks") or [])]


@pytest.mark.parametrize("matcher", COVERS_BASH, ids=[repr(m) for m in COVERS_BASH])
def test_a_matcher_that_already_names_bash_is_the_gate(tmp_path: Path, matcher):
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": matcher, "hooks": [_gate_hook()]}])
    out = fis.register_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert "skip" in out, out
    assert [e["matcher"] for e in pre] == [matcher], pre


def test_a_matcher_left_out_entirely_is_every_tool(tmp_path: Path):
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"hooks": [_gate_hook()]}])
    out = fis.register_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert "skip" in out, out
    assert len(pre) == 1, pre


@pytest.mark.parametrize("matcher", COVERS_NOTHING, ids=[repr(m) for m in COVERS_NOTHING])
def test_a_matcher_naming_no_tool_the_gate_uses_gives_the_hook_up(tmp_path: Path, matcher):
    import scripts.flow_init_setup as fis

    settings = _planted(
        tmp_path, [{"matcher": matcher, "team_note": "ours", "hooks": [_gate_hook()]}]
    )
    fis.register_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert [e.get("matcher") for e in _firing(pre)] == ["Bash"], pre
    assert pre[0] == {"matcher": matcher, "team_note": "ours", "hooks": []}, pre


@pytest.mark.parametrize("matcher", CANNOT_DECIDE, ids=[repr(m) for m in CANNOT_DECIDE])
def test_a_matcher_this_script_cannot_decide_is_left_as_written(tmp_path: Path, matcher):
    """Acted on as "does not fire", a `^Bash$` the host anchored on purpose loses the hook it
    was holding and the report says the entry never fired. Both are false, and the entry is the
    host's, so the only thing this script may do about it is add one of its own."""
    import scripts.flow_init_setup as fis

    planted = {"matcher": matcher, "team_note": "ours", "hooks": [_gate_hook()]}
    settings = _planted(tmp_path, [dict(planted)])
    fis.register_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert pre[0] == planted, pre
    assert "Bash" in [e.get("matcher") for e in _firing(pre)], pre


def test_registering_twice_over_a_matcher_that_cannot_be_decided_settles(tmp_path: Path):
    """The added entry has to be recognised as the gate on the next run, or every /flow-init
    adds another one beside a hook it will not touch."""
    import scripts.flow_init_setup as fis

    settings = _planted(tmp_path, [{"matcher": "^Bash$", "hooks": [_gate_hook()]}])
    fis.register_gate(tmp_path)
    first = settings.read_text(encoding="utf-8")
    assert "skip" in fis.register_gate(tmp_path)
    assert settings.read_text(encoding="utf-8") == first


def test_an_emptied_host_entry_keeps_what_the_host_wrote(tmp_path: Path):
    """Taking the gate hook out of an entry does not make the entry ours. Its matcher and the
    keys beside `hooks` are configuration this plugin never wrote."""
    import scripts.flow_init_setup as fis

    settings = _planted(
        tmp_path, [{"matcher": "Read", "team_note": "ours", "hooks": [_gate_hook()]}]
    )
    out = fis.register_gate(tmp_path)
    pre = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert "skip" not in out, out
    assert pre[0] == {"matcher": "Read", "team_note": "ours", "hooks": []}, pre


@pytest.mark.parametrize("label,payload", MALFORMED, ids=[label for label, _ in MALFORMED])
def test_a_settings_shape_the_schema_does_not_describe_is_reported(
    tmp_path: Path, label: str, payload
):
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text(json.dumps(payload), encoding="utf-8")
    before = settings.read_bytes()
    outs = [fis.register_gate(tmp_path), fis.unregister_gate(tmp_path)]
    for out in outs:
        assert out[:5] in ("  [!]", "  [=]", "  [+]", "  [-]"), (label, out)
    if outs[0].startswith("  [!]"):
        # Refused: the document itself is the shape that cannot be read, so nothing was written.
        assert settings.read_bytes() == before, label
        return
    # Accepted: the junk sits below the level this reads, so the gate installs around it and
    # every entry the host wrote is still there afterwards.
    planted = (payload.get("hooks") or {}).get("PreToolUse")
    kept = json.loads(settings.read_text(encoding="utf-8"))["hooks"]["PreToolUse"]
    assert all(entry in kept for entry in planted), (label, kept)


def test_a_byte_order_mark_is_not_a_broken_settings_file(tmp_path: Path):
    """An editor on this host writes one. Read as a parse failure it leaves the gate
    uninstalled, with a message that names the wrong problem."""
    import scripts.flow_init_setup as fis

    (tmp_path / ".claude").mkdir(parents=True)
    (tmp_path / ".claude" / "settings.json").write_text("\ufeff{}", encoding="utf-8")
    assert "등록" in fis.register_gate(tmp_path)
