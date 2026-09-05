import json
import shutil
from pathlib import Path

from scripts.flow_init_setup import _is_gate_hook

PLUGIN = Path(__file__).resolve().parent.parent.parent  # repo root == plugin root
ACCESS_ENTRIES = "system.posix_acl_access"
# Same resolution as tests/test_check_merge_ruleset.py: a bare "bash" hits the System32
# WSL stub first on Windows, which mangles backslash paths.
BASH = shutil.which("bash") or "bash"


def _is_gate(command: str) -> bool:
    """Ask the installer's own predicate. A test that spells the marker itself stops asking
    the code what it counts as the gate, which is the half that decides whose hook it takes."""
    return _is_gate_hook({"type": "command", "command": command})


def _gate_is_in(settings: Path) -> bool:
    """Whether the gate reached this host's file, read in a way every malformed shape
    survives — the shapes this is asked about are exactly the ones with no healthy layout."""
    try:
        data = json.loads(settings.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    hooks = data.get("hooks") if isinstance(data, dict) else None
    entries = hooks.get("PreToolUse") if isinstance(hooks, dict) else None
    return any(
        _is_gate(h["command"])
        for e in (entries if isinstance(entries, list) else [])
        if isinstance(e, dict) and isinstance(e.get("hooks"), list)
        for h in e["hooks"]
        if isinstance(h, dict) and isinstance(h.get("command"), str)
    )


def _gate_commands(settings: Path) -> list[str]:
    data = json.loads(settings.read_text(encoding="utf-8"))
    return [h["command"] for e in data["hooks"]["PreToolUse"] for h in e["hooks"]]


def _planted(tmp_path: Path, entries: list) -> Path:
    (tmp_path / ".claude").mkdir(parents=True)
    settings = tmp_path / ".claude" / "settings.json"
    settings.write_text(json.dumps({"hooks": {"PreToolUse": entries}}), encoding="utf-8")
    return settings


def _gate_hook() -> dict:
    import scripts.flow_init_setup as fis

    return {
        "type": "command",
        "shell": "bash",
        "command": fis.GATE_COMMAND,
        "timeout": 600,
        "statusMessage": fis.GATE_STATUS,
    }


# A settings.json the host hand-edited into a shape the schema does not describe. /flow-init
# runs unguarded, so an exception here takes the marketplace, pre-commit, .gitignore and the
# rendered workflows down with the gate.
MALFORMED = [
    ("hooks is a list", {"hooks": []}),
    ("hooks is null", {"hooks": None}),
    ("hooks is a string", {"hooks": "x"}),
    ("the document is a list", [1, 2]),
    ("PreToolUse is a dict", {"hooks": {"PreToolUse": {}}}),
    ("an entry is a string", {"hooks": {"PreToolUse": ["x"]}}),
    ("entry hooks is a number", {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": 5}]}}),
    ("entry hooks is true", {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": True}]}}),
    (
        "a foreign entry's hooks is a number",
        {"hooks": {"PreToolUse": [{"matcher": "Read", "hooks": 5}]}},
    ),
    (
        "a foreign entry's hooks is a string",
        {"hooks": {"PreToolUse": [{"matcher": "Read", "hooks": "x"}]}},
    ),
    (
        "a hook command is a number",
        {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": [{"command": 7}]}]}},
    ),
    (
        "a hook command is true",
        {"hooks": {"PreToolUse": [{"matcher": "Read", "hooks": [{"command": True}]}]}},
    ),
    (
        "a hook is a string",
        {"hooks": {"PreToolUse": [{"matcher": "Bash", "hooks": ["theirs.sh"]}]}},
    ),
    ("the document is a string", "x"),
    ("the document is a number", 7),
    ("the document is true", True),
]
