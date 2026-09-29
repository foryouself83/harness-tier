"""Register and unregister the commit gate and the harness-tier marketplace in a Claude Code
host's settings.json."""

from __future__ import annotations

import copy
import re
from pathlib import Path

try:
    from harness.gate_spec import GATE
except ImportError:
    from scripts.harness.gate_spec import GATE

try:
    from harness.jsonfile import load_json_object, why, write_json
except ImportError:
    from scripts.harness.jsonfile import load_json_object, why, write_json

# The commit gate to register in settings.json (runs the HOST copy via the host path). The `if`
# field is not included — precommit-runner.sh self-filters via stdin (avoiding per-build diffs).
# What makes a hook command the gate's own. The script name alone is not enough — a host
# with its own `tools/precommit-runner.sh` hook had it rewritten to this one's path, and
# moved out of its entry, as if this plugin had written it. Both words together keep the
# match independent of where under the host the scripts sit.
GATE_MARKER = ("harness-tier", "precommit-runner.sh")
GATE_COMMAND = f'bash "${{CLAUDE_PROJECT_DIR:-.}}/{GATE.runner_rel}"'
GATE_STATUS = GATE.status  # register fixes this up on rename
GATE_ENTRY = {
    "matcher": "Bash",
    "hooks": [
        {
            "type": "command",
            "shell": "bash",
            "command": GATE_COMMAND,
            "timeout": GATE.timeout,
            "statusMessage": GATE_STATUS,
        }
    ],
}

# Register the harness-tier marketplace in the host settings.json extraKnownMarketplaces with
# autoUpdate=true. Because a distributor cannot force auto-update via marketplace.json (a security
# boundary that prevents a third party from auto-fetching+running code without consent), this path
# — the host explicitly enabling it — is the only one. Once committed to the host repo, all
# teammates get the marketplace registered with auto-update on. source is set to `github`+repo
# (`git`+url has low auto-update reliability — the standard/recommended form, matching plugin.json).
MARKETPLACE_NAME = "harness-tier"
MARKETPLACE_REPO = "foryouself83/harness-tier"
MARKETPLACE_ENTRY = {
    "source": {"source": "github", "repo": MARKETPLACE_REPO},
    "autoUpdate": True,
}


def load_settings(host: Path) -> tuple[Path, dict | None, str | None]:
    """Return the settings.json path·parse result. On parse failure, (path, None, error message)."""
    settings = host / ".claude" / "settings.json"
    try:
        settings.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return settings, None, f"  [!] .claude 를 만들지 못했습니다({why(exc)}) — 수동 확인 필요"
    data, err = load_json_object(settings, "settings.json")
    return settings, data, err


def is_gate_hook(hook: object) -> bool:
    """Whether this is one of the gate's own hooks. A `command` the host wrote as something
    other than a string is not one, and asking `in` of it raises."""
    if not isinstance(hook, dict) or not isinstance(hook.get("command"), str):
        return False
    return all(word in hook["command"] for word in GATE_MARKER)


# The alphabet that keeps a matcher a name rather than a pattern, per the hooks reference.
# Inside it the two dialects agree — `|` alternates in both and everything else is literal —
# so the same string can be read both ways and the answers compared.
_EXACT_MATCHER_RE = re.compile(r"[A-Za-z0-9_\- ,|]*")


def covers_bash(matcher: object) -> bool | None:
    """Whether a PreToolUse matcher fires on Bash — the only tool a commit arrives through.
    True, False, or None where this script cannot say.

    Three readings, as the hooks reference defines them: `*`, an empty matcher and an absent
    one are every tool; a matcher spelled only with the name alphabet is one tool name or a
    `|`/`,` list of them; anything else is a JavaScript regular expression. Only the first two
    can be decided here — Python's dialect is not JavaScript's, `(?i)` and `\\Z` being Python's
    alone — and the comma separator and the whitespace around a name are newer than the oldest
    host this runs on, where the same text is read as a pattern instead. Both go undecided.

    Undecided is not "does not fire": acted on as one, a `^Bash$` the host anchored on purpose
    has the gate hook pulled out from under it and the report says the entry never fired, which
    is false. Undecided keeps the entry and its matcher and adds an entry of the gate's own, so
    the gate exists either way; a gate hook inside it is still brought to the current path,
    which is the one thing in that entry this plugin wrote.
    """
    if matcher is None or matcher in ("", "*"):
        return True
    if not isinstance(matcher, str):
        return None
    if not _EXACT_MATCHER_RE.fullmatch(matcher):
        return None
    as_list = GATE_ENTRY["matcher"] in [name.strip() for name in re.split(r"[|,]", matcher)]
    as_pattern = re.search(matcher, GATE_ENTRY["matcher"]) is not None
    return as_list if as_list == as_pattern else None


def register(host: Path) -> str:
    """Register the commit gate in .claude/settings.json. Skip if already present; if the registered
    command/statusMessage differs from the current value, fix it up (for plugin updates)."""
    settings, data, err = load_settings(host)
    if data is None:
        return err
    if not isinstance(data.get("hooks", {}), dict):
        return "  [!] settings.json hooks 형식 비정상 — 게이트 미등록(수동 확인)"
    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
    if not isinstance(pre, list):
        return "  [!] hooks.PreToolUse 형식 비정상 — 게이트 미등록(수동 확인)"
    entries = [e for e in pre if isinstance(e, dict)]
    # The matcher decides whether a hook fires at all, so a gate hook under one that misses Bash
    # is not the gate — counting it as one leaves the host reporting a gate it does not have.
    # The entry around it is the HOST's, though: it may carry the host's own hooks, and its
    # matcher may already name Bash among several tools. So the gate hook moves out of an entry
    # that does not fire and everything else about that entry stays — its matcher, the keys
    # beside `hooks`, and the entry itself once emptied. Rewriting or dropping it would take
    # configuration this plugin never wrote.
    moved = undecided = 0
    for entry in entries:
        hooks = entry.get("hooks")
        if not isinstance(hooks, list):
            continue
        covers = covers_bash(entry.get("matcher"))
        if covers is None:
            undecided += sum(1 for h in hooks if is_gate_hook(h))
        elif not covers:
            kept = [h for h in hooks if not is_gate_hook(h)]
            moved += len(hooks) - len(kept)
            entry["hooks"] = kept
    gate_hooks = [
        h
        for e in entries
        if isinstance(e.get("hooks"), list)
        for h in e["hooks"]
        if is_gate_hook(h)
    ]
    # Only a hook under a matcher known to fire is the gate. One under a matcher this script
    # cannot decide may be doing the job already, which is why it is left alone — and may not
    # be, which is why it does not count as the gate.
    firing = [
        h
        for e in entries
        if isinstance(e.get("hooks"), list) and covers_bash(e.get("matcher"))
        for h in e["hooks"]
        if is_gate_hook(h)
    ]
    added = not firing
    if added:
        pre.append(copy.deepcopy(GATE_ENTRY))
    # Already registered — a plugin update may have changed command/statusMessage, so fix up
    # **every** entry that diverges from the current value (fixing only the first would leave a
    # duplicate stale entry pointing at a deleted path forever).
    # Anything but the hook this plugin writes is repaired to it. The command and the status
    # line drift on a plugin update, but the fields that matter are ones the host can add: an
    # `if` on the gate hook suppresses it per build (Invariant 4), `async` puts it where it
    # cannot deny, and a `type` other than `command` runs something else — each of them a gate
    # reported as registered and firing on nothing.
    stock = GATE_ENTRY["hooks"][0]
    stale = [h for h in gate_hooks if h != stock]
    note = ""
    if data.get("disableAllHooks") is True:
        note += ", settings.json 의 disableAllHooks 로 훅이 전혀 실행되지 않습니다"
    if len(firing) > 1:
        note += f", 발화하는 게이트 훅 {len(firing)}개 — 커밋마다 그만큼 실행됩니다"
    if undecided:
        note += (
            f", 판정할 수 없는 matcher 아래 게이트 훅 {undecided}개"
            " — 발화한다면 그만큼 더 실행됩니다"
        )
    if not added and not stale and not moved:
        return f"  [=] 커밋 게이트 이미 등록됨 (skip{note})"
    for hook in stale:
        hook.clear()
        hook.update(copy.deepcopy(stock))
    failed = write_json(settings, data)
    if failed:
        return failed
    if added and moved:
        return (
            "  [+] 커밋 게이트 등록 (settings.json, Bash 에 발화하지 않는 항목에서 "
            f"{moved}건 이동{note})"
        )
    if added:
        return f"  [+] 커밋 게이트 등록 (settings.json{note})"
    return (
        f"  [+] 커밋 게이트 보정 (settings.json, {len(stale) + moved}건 — 게이트 훅은"
        f" 플러그인 원형으로 교체{note})"
    )


def register_marketplace(host: Path) -> str:
    """Register the harness-tier marketplace in .claude/settings.json extraKnownMarketplaces with
    autoUpdate=true (add if absent, fix only autoUpdate if present, skip if already true).
    Source is preserved."""
    settings, data, err = load_settings(host)
    if data is None:
        return err
    mkts = data.setdefault("extraKnownMarketplaces", {})
    if not isinstance(mkts, dict):
        return "  [!] extraKnownMarketplaces 형식 비정상 — 마켓 미등록(수동 확인)"
    existing = mkts.get(MARKETPLACE_NAME)
    if isinstance(existing, dict):
        if existing.get("autoUpdate") is True:
            return "  [=] harness-tier 마켓 autoUpdate 이미 켜짐 (skip)"
        existing["autoUpdate"] = True  # preserve the source, fix only autoUpdate
        msg = "  [+] harness-tier 마켓 autoUpdate=true 보정"
    else:
        mkts[MARKETPLACE_NAME] = dict(MARKETPLACE_ENTRY)
        msg = "  [+] harness-tier 마켓 등록 + autoUpdate=true"
    failed = write_json(settings, data)
    if failed:
        return failed
    return msg


def _strip_gate_hooks(entry: object) -> int:
    """Remove the gate's own hooks from one entry; returns how many. The entry stays.

    `register` leaves the gate hook inside a host entry whenever that entry already fires
    on Bash, so an entry holding the gate may hold the host's hooks beside it — taking the
    entry would take those with it.
    """
    if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
        return 0
    hooks = entry["hooks"]
    entry["hooks"] = [h for h in hooks if not is_gate_hook(h)]
    return len(hooks) - len(entry["hooks"])


def _is_own_empty_entry(entry: object) -> bool:
    """An entry this plugin wrote and has emptied — nothing of the host's is in it."""
    return (
        isinstance(entry, dict)
        and set(entry) == set(GATE_ENTRY)
        and entry.get("matcher") == GATE_ENTRY["matcher"]
        and entry.get("hooks") == []
    )


def unregister(host: Path) -> str:
    """Remove the commit gate hook from settings.json (skip if absent)."""
    settings, data, err = load_settings(host)
    if data is None:
        return err
    hooks = data.get("hooks") if isinstance(data, dict) else None
    pre = hooks.get("PreToolUse") if isinstance(hooks, dict) else None
    if not isinstance(pre, list):
        return "  [=] 게이트 훅 없음 (skip)"
    if not sum(_strip_gate_hooks(entry) for entry in pre):
        return "  [=] 게이트 훅 없음 (skip)"
    hooks["PreToolUse"] = [e for e in pre if not _is_own_empty_entry(e)]
    failed = write_json(settings, data)
    if failed:
        return failed
    return "  [-] 커밋 게이트 해제 (settings.json)"


def unregister_marketplace(host: Path) -> str:
    """Remove the harness-tier marketplace from settings.json (skip if absent)."""
    settings, data, err = load_settings(host)
    if data is None:
        return err
    mkts = data.get("extraKnownMarketplaces")
    if not isinstance(mkts, dict) or MARKETPLACE_NAME not in mkts:
        return "  [=] harness-tier 마켓 등록 없음 (skip)"
    del mkts[MARKETPLACE_NAME]
    failed = write_json(settings, data)
    if failed:
        return failed
    return "  [-] harness-tier 마켓 등록 해제 (settings.json)"


def problems(host: Path) -> list[str]:
    """Why the commit gate would not fire, as far as settings.json alone can say.

    Read back from what a run left: a settings.json this cannot parse; a gate hook that is
    not there, or sits under a matcher that never fires; and `disableAllHooks`, which
    silences it regardless of what else is correct. The file-existence half of the question
    — whether the scripts the hook names are on disk — is asked by the caller.
    """
    out: list[str] = []
    _settings, data, _err = load_settings(host)
    if data is None:
        out.append(
            "settings.json 을 읽지 못해 커밋 게이트를 확인할 수 없습니다 — 위 [!] 를"
            " 해결한 뒤 /flow-init 를 다시 실행하세요."
        )
        return out
    hooks = data.get("hooks")
    pre = hooks.get("PreToolUse") if isinstance(hooks, dict) else None
    # The hook has to be the one this plugin writes, not merely one of its own: the repair
    # that takes an `if` back off lands only when the write does, and a matcher this
    # cannot decide is not one that fails to fire — a host who anchored `^Bash$` has a
    # gate, and saying otherwise sends them to fix what is not broken.
    firing = any(
        covers_bash(entry.get("matcher")) is not False
        and any(h == GATE_ENTRY["hooks"][0] for h in entry["hooks"])
        for entry in (pre if isinstance(pre, list) else [])
        if isinstance(entry, dict) and isinstance(entry.get("hooks"), list)
    )
    if not firing:
        out.append(
            "커밋 게이트가 settings.json 에 없습니다 — 위 [!] 를 해결한 뒤 /flow-init 를"
            " 다시 실행하세요."
        )
    if data.get("disableAllHooks") is True:
        out.append(
            "settings.json 의 disableAllHooks 가 켜져 있어 커밋 게이트를 포함한 모든"
            " 훅이 실행되지 않습니다 — 끄세요."
        )
    return out


def hook_remains(host: Path) -> bool:
    """Whether a gate hook may still be in the host's settings.json.

    A file this cannot read is one it cannot clear either, and the run has already deleted
    the scripts the hook names — so unreadable counts as left behind. Answering no there
    put `정리 완료.` over a hook pointing at nothing, which is the lie this exists to stop.
    """
    _settings, data, _err = load_settings(host)
    if data is None:
        return True
    hooks = data.get("hooks")
    pre = hooks.get("PreToolUse") if isinstance(hooks, dict) else None
    return any(
        is_gate_hook(h)
        for entry in (pre if isinstance(pre, list) else [])
        if isinstance(entry, dict) and isinstance(entry.get("hooks"), list)
        for h in entry["hooks"]
    )
