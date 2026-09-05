import json
import shutil
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent.parent / "scripts" / "check-merge-ruleset.sh"
# On Windows a bare "bash" resolves via System32 first (the WSL stub), which mangles
# backslash paths; shutil.which walks PATH in order and finds Git Bash. Same rationale as
# tests/test_check_token_write.py.
BASH = shutil.which("bash") or "bash"


def _ruleset(
    ref: str,
    methods: list[str] | None,
    enforcement: str = "active",
    bypass_actors: list[dict] | None = None,
    exclude: list[str] | None = None,
) -> dict:
    """One ruleset object as GET /repos/{o}/{r}/rulesets/{id} returns it.

    `bypass_actors=None` omits the key entirely — an older/likely payload shape, and the
    one the merge-method tests do not care about either way.
    """
    rules = []
    if methods is not None:
        rules.append({"type": "pull_request", "parameters": {"allowed_merge_methods": methods}})
    rs = {
        "id": 1,
        "name": "x",
        "target": "branch",
        "enforcement": enforcement,
        "conditions": {"ref_name": {"include": [ref], "exclude": exclude or []}},
        "rules": rules,
    }
    if bypass_actors is not None:
        rs["bypass_actors"] = bypass_actors
    return rs


ACTOR = [{"actor_id": 1, "actor_type": "Integration", "bypass_mode": "always"}]


def _actor(mode: str | None) -> dict:
    """One bypass actor. `mode=None` omits `bypass_mode` entirely."""
    a = {"actor_id": 1, "actor_type": "Integration"}
    if mode is not None:
        a["bypass_mode"] = mode
    return a


def _decode(
    sets: list[dict],
    branch: str,
    want: str,
    env: dict | None = None,
    default_branch: str | None = None,
) -> int:
    argv = [BASH, str(SCRIPT), "--decode", branch, want]
    if default_branch is not None:
        argv.append(default_branch)
    return subprocess.run(
        argv,
        input=json.dumps(sets, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        env=env,
    ).returncode


def _decode_bypass(
    sets: list[dict],
    branch: str,
    env: dict | None = None,
    default_branch: str | None = None,
) -> int:
    argv = [BASH, str(SCRIPT), "--decode-bypass", branch]
    if default_branch is not None:
        argv.append(default_branch)
    return subprocess.run(
        argv,
        input=json.dumps(sets, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        env=env,
    ).returncode
