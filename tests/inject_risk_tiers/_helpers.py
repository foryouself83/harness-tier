"""The SessionStart hook: rule injection plus the out-of-date-plugin notice.

The notice is for CONSUMERS: it compares the build this session loaded against the version the
marketplace publishes and speaks only when the marketplace is ahead. Everything about it is
FAIL-OPEN — every uncertain case stays silent and exits 0, because this hook runs before the
session does anything and must never delay or break session start.

Both versions come from local files (the loaded plugin's own manifest, and the marketplace clone
Claude Code keeps beside the install cache), so the check costs no network and a stale or absent
clone means no notice. It travels in the same injected context as the rule, under its own
tag: headless runs show that a hook's `systemMessage` reaches no observable channel.
"""

import json
import os
import shutil
import subprocess
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "hooks" / "inject-risk-tiers.sh"
# Windows resolves a bare "bash" via System32 first (the WSL stub), which cannot see C:/… paths.
# shutil.which() walks PATH in order, so it picks Git Bash; plain "bash" covers Linux CI.
BASH = shutil.which("bash") or "bash"

STARTUP = json.dumps({"hook_event_name": "SessionStart", "source": "startup"})
# Larger than a pipe buffer on purpose: the hook writes the whole rule to stdout, and a test
# that waits on the process without draining it would deadlock against that write rather
# than measure what it meant to.
RULE_BODY = "# rule\nthe body the hook must actually read\n" + "filler line\n" * 8000

NOTICE_OPEN = "<harness-tier-stale-build>"
NOTICE_CLOSE = "</harness-tier-stale-build>"
RELAY = "Relay this to the user before doing anything else:"

# Each output branch: the env that selects it, and where the injected context lands.
BRANCHES = {
    "claude": ({}, ("hookSpecificOutput", "additionalContext")),
    "cursor": ({"CURSOR_PLUGIN_ROOT": "x"}, ("additional_context",)),
    "sdk": ({"COPILOT_CLI": "1"}, ("additionalContext",)),
}


def _manifest(where: Path, name: str, version: str | None, indent: int | None = 2) -> None:
    """A `.claude-plugin/plugin.json`, with `author.name` after the top-level one — the real
    layout, and the one a last-match read would get backwards.

    Pretty-printed by default because the shipped manifests are: on one line a regex takes the
    leftmost match anyway, so a single-line fixture cannot tell first-match from last-match.
    """
    where.mkdir(parents=True, exist_ok=True)
    body: dict[str, object] = {"name": name}
    if version is not None:
        body["version"] = version
    body["author"] = {"name": "someone-else"}
    (where / "plugin.json").write_text(
        json.dumps(body, indent=indent), encoding="utf-8", newline=""
    )


def _plugins_root(
    tmp_path: Path,
    loaded: str | None = "1.0.0",
    published: str | None = "2.0.0",
    name: str = "harness-tier",
    market_name: str | None = None,
    market: str = "mkt",
) -> Path:
    """Claude Code's plugins directory: an install cache holding the loaded build, and the
    marketplace clones it keeps beside it. Returns the loaded plugin's root."""
    root = tmp_path / "plugins"
    plugin_root = root / "cache" / "owner" / name / (loaded or "0")
    if loaded is not None:
        _manifest(plugin_root / ".claude-plugin", name, loaded)
    (plugin_root / "rules").mkdir(parents=True, exist_ok=True)
    # newline="" stops Windows from rewriting the line endings, so the bytes the hook reads are
    # the bytes asserted on.
    (plugin_root / "rules" / "risk-tiers.md").write_text(RULE_BODY, encoding="utf-8", newline="")
    if published is not None:
        _manifest(root / "marketplaces" / market / ".claude-plugin", market_name or name, published)
    return plugin_root


def _market(plugin_root: Path) -> Path:
    """The marketplace clone's manifest directory, from the loaded plugin's root."""
    return plugin_root.parents[3] / "marketplaces" / "mkt" / ".claude-plugin"


def _run(plugin_root: Path, stdin: str = STARTUP, extra_env=None):
    env = {
        "PATH": os.environ.get("PATH", ""),
        "SYSTEMROOT": os.environ.get("SYSTEMROOT", ""),
        "CLAUDE_PLUGIN_ROOT": str(plugin_root),
    }
    env.update(extra_env or {})
    return subprocess.run(
        [BASH, str(SCRIPT)], input=stdin, text=True, capture_output=True, env=env, timeout=30
    )


def _out(result) -> dict:
    assert result.returncode == 0, (
        f"hook must always exit 0, got {result.returncode}: {result.stderr}"
    )
    return json.loads(result.stdout)


def _context(result, branch: str = "claude") -> str:
    node = _out(result)
    for key in BRANCHES[branch][1]:
        node = node[key]
    assert isinstance(node, str), f"expected a context string, got {type(node).__name__}"
    return node


def _extract(context: str) -> str | None:
    """The notice rides inside the injected context under its own tag, which is what makes a
    silent run distinguishable from the rule text that is always present."""
    if NOTICE_OPEN not in context:
        return None
    return context.split(NOTICE_OPEN, 1)[1].split(NOTICE_CLOSE, 1)[0]


def _notice(result, branch: str = "claude") -> str | None:
    return _extract(_context(result, branch))
