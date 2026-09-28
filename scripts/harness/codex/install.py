"""Register the commit gate in a host's .codex/hooks.json — Codex's project hook file.

Codex loads the file only in a trusted project and runs a hook only once the user has approved it
in /hooks; approval is keyed by the hook's content and position, so the command strings below are
fixed and the gate entry is appended, never inserted.
"""

from __future__ import annotations

import copy
import os
import re
from pathlib import Path

try:
    from harness.gate_spec import GATE
    from harness.jsonfile import load_json_object, why, write_json
except ImportError:
    from scripts.harness.gate_spec import GATE
    from scripts.harness.jsonfile import load_json_object, why, write_json

_WRAPPER = GATE.runner_rel.rsplit("/", 1)[0] + "/harness/codex/gate"
GATE_COMMAND = f'bash "$(git rev-parse --show-toplevel)/{_WRAPPER}.sh"'
GATE_COMMAND_WINDOWS = f'& "$(git rev-parse --show-toplevel)/{_WRAPPER}.cmd"'
GATE_HOOK = {
    "type": "command",
    "command": GATE_COMMAND,
    "commandWindows": GATE_COMMAND_WINDOWS,
    "timeout": GATE.timeout,
    "statusMessage": GATE.status,
}
GATE_ENTRY = {"matcher": "Bash", "hooks": [GATE_HOOK]}
MARKER = ("harness-tier", "harness/codex/gate")
ALLOWED_TOP = {"description", "hooks"}

# Codex's own matcher grammar (docs/superpowers/reference/claude-code-vs-codex.md §3.1, sourced
# from codex-rs): a matcher spelled only with [A-Za-z0-9_|] is an exact `|`-separated list of
# tool names; anything else — including a comma, a hyphen or a space, all valid in Claude Code's
# own matcher dialect but not this one — is a regular expression this does not evaluate. The two
# grammars differ: a Claude-style "Bash,Read" is a Codex *regex* that does not match "Bash",
# not a two-item list.
_EXACT_MATCHER_RE = re.compile(r"[A-Za-z0-9_|]*")


def _fires_on_bash(matcher: object) -> bool | None:
    """Whether a PreToolUse matcher fires on Bash. True, False, or None (cannot say)."""
    if matcher is None or matcher in ("", "*"):
        return True
    if not isinstance(matcher, str) or not _EXACT_MATCHER_RE.fullmatch(matcher):
        return None
    return "Bash" in matcher.split("|")


def _path(host: Path) -> Path:
    return host / ".codex" / "hooks.json"


def _is_gate(hook: object) -> bool:
    return (
        isinstance(hook, dict)
        and isinstance(hook.get("command"), str)
        and all(w in hook["command"] for w in MARKER)
    )


def _load(host: Path) -> tuple[dict | None, str | None]:
    data, err = load_json_object(_path(host), ".codex/hooks.json")
    if data is None:
        return None, err
    if set(data) - ALLOWED_TOP:
        return None, (
            "  [!] .codex/hooks.json 에 description·hooks 외 키가 있어 Codex 가 파일 전체를"
            " 읽지 않습니다 — 수동 확인 필요"
        )
    if not isinstance(data.get("hooks", {}), dict) or not isinstance(
        data.get("hooks", {}).get("PreToolUse", []), list
    ):
        return None, "  [!] .codex/hooks.json hooks 형식 비정상 — 게이트 미등록(수동 확인)"
    return data, None


def _entries(data: dict) -> list:
    return data.get("hooks", {}).get("PreToolUse", [])


def register(host: Path) -> str:
    """Register the commit gate in .codex/hooks.json. Skip if already present under a matcher
    that provably fires on Bash; repair a stale gate hook in place; move a gate hook out from
    under a matcher that provably does not (mirrors harness.claude.install.register, with
    Codex's own matcher grammar)."""
    data, err = _load(host)
    if data is None:
        return err
    entries = _entries(data)
    # A gate hook under a matcher this can prove misses Bash is not the gate — leaving it there
    # would report "already registered" over a hook that never runs. The entry it sits in may
    # hold the host's own hooks beside it, so only the gate hook moves; the entry, its matcher
    # and anything else in it stay, same as the Claude installer's own precedent.
    moved = 0
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
            continue
        if _fires_on_bash(entry.get("matcher")) is False:
            kept = [h for h in entry["hooks"] if not _is_gate(h)]
            moved += len(entry["hooks"]) - len(kept)
            entry["hooks"] = kept
    gate_hooks = [
        h
        for e in entries
        if isinstance(e, dict) and isinstance(e.get("hooks"), list)
        for h in e["hooks"]
        if _is_gate(h)
    ]
    # Only a hook under a matcher known to fire counts as the registered gate. One under a
    # matcher this cannot decide may already be doing the job — left alone, and not counted as
    # missing either, so it is neither repaired nor duplicated on a guess.
    firing = [
        h
        for e in entries
        if isinstance(e, dict)
        and isinstance(e.get("hooks"), list)
        and _fires_on_bash(e.get("matcher")) is True
        for h in e["hooks"]
        if _is_gate(h)
    ]
    added = not firing
    if added:
        data.setdefault("hooks", {}).setdefault("PreToolUse", []).append(copy.deepcopy(GATE_ENTRY))
    stale = [h for h in gate_hooks if h != GATE_HOOK]
    if not added and not stale and not moved:
        return "  [=] Codex 커밋 게이트 이미 등록됨 (skip)"
    for h in stale:
        h.clear()
        h.update(copy.deepcopy(GATE_HOOK))
    try:
        _path(host).parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return f"  [!] .codex 를 만들지 못했습니다({why(exc)}) — 수동 확인 필요"
    failed = write_json(_path(host), data)
    if failed:
        return failed
    if added and moved:
        return (
            "  [+] Codex 커밋 게이트 등록 (.codex/hooks.json, 발화하지 않는 matcher 항목에서"
            f" {moved}건 이동 — Codex 의 /hooks 에서 승인해야 실행)"
        )
    verb = "등록" if added else "보정"
    return (
        f"  [+] Codex 커밋 게이트 {verb} (.codex/hooks.json — Codex 의 /hooks 에서 승인해야 실행)"
    )


def unregister(host: Path) -> str:
    if not _path(host).is_file():
        return "  [=] Codex 게이트 훅 없음 (skip)"
    data, err = _load(host)
    if data is None:
        return err
    removed = 0
    kept_entries = []
    for e in _entries(data):
        if isinstance(e, dict) and isinstance(e.get("hooks"), list):
            before = len(e["hooks"])
            e["hooks"] = [h for h in e["hooks"] if not _is_gate(h)]
            removed += before - len(e["hooks"])
            if before and not e["hooks"] and set(e) == {"matcher", "hooks"}:
                continue
        kept_entries.append(e)
    if not removed:
        return "  [=] Codex 게이트 훅 없음 (skip)"
    hooks = data.setdefault("hooks", {})
    if kept_entries:
        hooks["PreToolUse"] = kept_entries
    else:
        hooks.pop("PreToolUse", None)
    if not hooks and set(data) <= {"hooks"}:
        try:
            _path(host).unlink()
        except OSError as exc:
            return f"  [!] .codex/hooks.json 삭제 실패({why(exc)}) — 수동 확인 필요"
        return "  [-] Codex 커밋 게이트 해제 (.codex/hooks.json 삭제 — 남은 훅 없음)"
    failed = write_json(_path(host), data)
    return failed or "  [-] Codex 커밋 게이트 해제 (.codex/hooks.json)"


def problems(host: Path) -> list[str]:
    data, _err = _load(host)
    if data is None:
        return [
            ".codex/hooks.json 을 읽지 못해 Codex 커밋 게이트를 확인할 수 없습니다 — 위 [!] 를"
            " 해결한 뒤 /flow-init 를 다시 실행하세요."
        ]
    # A gate hook sitting under a matcher that never reaches Bash is not the gate, regardless
    # of how faithfully its command string matches — same tri-state reading as the Claude
    # installer's matcher check: only a matcher this can prove misses Bash disqualifies it.
    firing = any(
        isinstance(e, dict)
        and _fires_on_bash(e.get("matcher")) is not False
        and isinstance(e.get("hooks"), list)
        and GATE_HOOK in e["hooks"]
        for e in _entries(data)
    )
    if firing:
        return []
    return [
        "Codex 커밋 게이트가 .codex/hooks.json 에 없습니다 — 위 [!] 를 해결한 뒤 /flow-init 를"
        " 다시 실행하세요."
    ]


def hook_remains(host: Path) -> bool:
    """Read without `_load`'s shape rules: a host's own extra top-level key makes Codex ignore
    the file, but says nothing about whether our gate hook is in it."""
    data, _err = load_json_object(_path(host), ".codex/hooks.json")
    if data is None:
        return _path(host).exists()
    hooks = data.get("hooks", {})
    entries = hooks.get("PreToolUse", []) if isinstance(hooks, dict) else None
    if not isinstance(entries, list):
        return True
    return any(
        _is_gate(h)
        for e in entries
        if isinstance(e, dict)
        for h in (e.get("hooks") if isinstance(e.get("hooks"), list) else [])
    )


def trust_notes(host: Path, codex_home: Path | None = None) -> list[str]:
    """Warnings, never failures: both remedies are the user's to apply. Reads, never writes.

    A heuristic reader, not a TOML parser (no `tomllib` on 3.8-3.10): any input this cannot
    make sense of — a missing file, a non-UTF-8 config, odd bracket nesting — falls back to
    "not trusted" rather than raising or guessing trusted.
    """
    home = codex_home or Path(os.environ.get("CODEX_HOME") or Path.home() / ".codex")
    notes = []
    key = str(host.resolve())
    try:
        text = (home / "config.toml").read_text(encoding="utf-8")
    except (OSError, ValueError):
        text = ""
    trusted = False
    for m in re.finditer(r"^\[projects\.(['\"])(.+?)\1\]\s*$([^\[]*)", text, re.M | re.S):
        name = m.group(2)
        if m.group(1) == '"':
            # A basic string escapes its backslashes; a literal (single-quoted) one does not.
            name = re.sub(r'\\([\\"])', r"\1", name)
        same = name.lower() == key.lower() if os.name == "nt" else name == key
        if same and re.search(r'^\s*trust_level\s*=\s*"trusted"', m.group(3), re.M):
            trusted = True
    if not trusted:
        notes.append(
            f"  [!] Codex 가 이 프로젝트를 trusted 로 모릅니다 — .codex/ 가 무시됩니다."
            f' Codex 에서 이 폴더를 신뢰하거나 config.toml 에 [projects."{key}"]'
            ' trust_level = "trusted"'
        )
    notes.append(
        "  [i] Codex 의 /hooks 에서 harness-tier 게이트 훅을 승인해야 실행됩니다"
        "(승인 전엔 조용히 skip)."
    )
    return notes
