"""flow-init mechanical setup / --uninstall cleanup — idempotent.
(The interactive part is handled by Claude in the /flow-init command.)

All host-side harness-tier artifacts are collected under .claude/harness-tier/ in one
place, subdivided by purpose:
  - .claude/harness-tier/scripts/  copied gate scripts (plugin-owned·git-tracked)
  - .claude/harness-tier/config/   flow-config.yaml·flow-tiers.yaml(policy)·webhooks
  - .claude/harness-tier/.flow/    gate evidence (gitignored)

setup (default) idempotently applies the following:
  - Copy the gate scripts to .claude/harness-tier/scripts/, the policy flow-tiers.yaml to config/
  - Register the commit gate in hooks.PreToolUse of .claude/settings.json (fix up if path changes)
  - Static-analysis hooks: create .pre-commit-config.yaml if absent, else report missing items
  - Add missing lines to .gitignore (skip if duplicated)

uninstall (--uninstall) is the inverse of setup (host cleanup):
  - Unregister the commit gate / harness-tier marketplace in settings.json
  - Remove harness-tier lines from .gitignore, remove the teams management block from CLAUDE.md
  - Delete the .claude/harness-tier/ directory (including scripts·config·evidence·webhooks)
  - .pre-commit-config.yaml hooks·git hooks are only reported (high risk; removed by hand)

Paths: host=CLAUDE_PROJECT_DIR (else git toplevel), plugin=CLAUDE_PLUGIN_ROOT
(else this script's parent). Results are printed to stdout as a human-readable summary.

Each function takes paths as arguments and returns its result, making it unit-testable.
"""

from __future__ import annotations

import argparse
import copy
import json
import os
import re
import shutil
import stat
import tempfile
from collections.abc import Callable
from pathlib import Path

# Path segments·fallback helpers·encoding defense come from the shared SSOT (_harness_paths)
# (no duplicate definitions — rule-dry-constants). flow_init_setup runs from the plugin location,
# so sibling import is the default; in a package (test) it falls back to scripts._harness_paths.
try:
    from _harness_paths import (
        CONFIG_DIR,
        FLOW_DIR,
        HARNESS_DIR,
        SCRIPTS_DIR,
        TIERS_FILENAME,
        config_path,
        force_utf8_io,
        host_root,
        plugin_root,
    )
except ImportError:
    from scripts._harness_paths import (
        CONFIG_DIR,
        FLOW_DIR,
        HARNESS_DIR,
        SCRIPTS_DIR,
        TIERS_FILENAME,
        config_path,
        force_utf8_io,
        host_root,
        plugin_root,
    )

WORKFLOW_TEMPLATE = "github/api-contract.workflow.example.yml"  # SOURCE (plugin-owned)
WORKFLOW_DEST = ".github/workflows/api-contract.yml"  # host (GitHub-forced — HARNESS_DIR exception)

UNIT_TEST_TEMPLATE = "github/unit-test.workflow.example.yml"  # SOURCE (plugin-owned)
UNIT_TEST_DEST = ".github/workflows/unit-test.yml"  # host (GitHub-forced — HARNESS_DIR exception)

WIKI_VERIFY_TEMPLATE = "github/wiki-verify.workflow.example.yml"  # SOURCE (plugin-owned)
WIKI_VERIFY_DEST = ".github/workflows/wiki-verify.yml"  # host (GitHub-forced — HARNESS_DIR exc.)
# per-job wall-clock cap (minutes) when unit_test.timeout_minutes is unset
UNIT_TEST_DEFAULT_TIMEOUT = 10
# Languages the unit-test template runs an official setup-* action for (its `if: matrix.language ==`
# gates, lowercase literals). A value outside this set is a legitimate escape hatch (the job's own
# `setup` command preps the runtime), but a *case variant* of one of these (e.g. "Python") almost
# certainly means the setup step will be silently skipped — flagged as a warning at render time.
# Copied from the template, so test_flow_init_setup.py asserts the two stay equal.
SUPPORTED_SETUP_LANGUAGES = frozenset({"python", "node", "java", "go", "rust"})

EXAMPLE_CONFIG = "flow-config.example.yaml"  # plugin SOURCE (basis for config-slot diff)

# Gate scripts to copy to .claude/harness-tier/scripts/ (SOURCE → HOST). _harness_paths.py is a
# shared module the copied scripts import, so it must travel with them (sibling import holds in the
# single-file-copy environment). The policy file flow-tiers.yaml is copied separately to config/
# (copy_artifacts).
# Order matters where one file asks another a question. precommit-runner.sh routes on what
# flow_gate_check.py --classify answers, so the answerer is copied FIRST: mid-sync the host
# then holds an old runner and a new script, where the old runner's question goes unanswered
# and ROOT simply stays on main. The other order leaves a new runner asking an old script,
# which answers nothing it recognises — and a runner that reads no verdict gates nothing.
COPY_FILES = [
    "scripts/_harness_paths.py",
    "scripts/flow_gate_check.py",
    "scripts/precommit-runner.sh",
    "scripts/wiki_graph.py",
    "scripts/teams_alert.py",
    "scripts/notify-push.sh",
    "scripts/check-deps.sh",
    "scripts/check-token-write.sh",
    "scripts/finalize_prerelease.py",
    "scripts/bump_version.py",
]

# What the GATE needs on the host, out of everything this installs: the hook names the
# runner, the runner spawns the check, the check imports the paths module — and it reads
# the policy, without which nothing classifies and the unclassified-commit deny never
# fires. Measured: with no flow-tiers.yaml the runner exits 0 on a real commit. They are
# asked of the host at the end of a setup, because a hook is a line of text naming a
# file and a copy step that failed leaves it naming nothing.
# Each as (where it lands, what it is copied FROM), because existence is not the question:
# a copy that fails after creating or truncating the destination leaves the name behind,
# and a full volume installs four empty files that `bash` and PyYAML both read without
# complaint. Measured: the runner exits 0 on a real commit over those.
GATE_FILES = (
    (f"{SCRIPTS_DIR}/precommit-runner.sh", "scripts/precommit-runner.sh"),
    (f"{SCRIPTS_DIR}/flow_gate_check.py", "scripts/flow_gate_check.py"),
    (f"{SCRIPTS_DIR}/_harness_paths.py", "scripts/_harness_paths.py"),
    (f"{CONFIG_DIR}/{TIERS_FILENAME}", TIERS_FILENAME),
)

# Lines to add to .gitignore. The personal webhook is kept as a **bare pattern** (matches at any
# depth) — narrowing the path would be a security footgun that leaves root-residual files not yet
# moved to config/ exposed (add, don't narrow). The evidence directory is anchored (fixed location).
# flow-config.yaml is team-shared config (branches·modules — not secret), so it is **tracked**
# (excluded from the ignore list — same grain as teams-webhooks.json·scripts/).
GITIGNORE_LINES = [
    ".teams-webhooks.local.json",
    f"{FLOW_DIR}/",
]

# The pre-commit hook id owned by harness-tier (a fixed hook, not a per-language replacement).
# When a plugin update moves a script's location, the existing .pre-commit-config.yaml entry no
# longer matches the current path, so the drift is reported.
OWNED_HOOK_ID = "teams-notify-push"

# The commit gate to register in settings.json (runs the HOST copy via the host path). The `if`
# field is not included — precommit-runner.sh self-filters via stdin (avoiding per-build diffs).
# What makes a hook command the gate's own. The script name alone is not enough — a host
# with its own `tools/precommit-runner.sh` hook had it rewritten to this one's path, and
# moved out of its entry, as if this plugin had written it. Both words together keep the
# match independent of where under the host the scripts sit.
GATE_MARKER = ("harness-tier", "precommit-runner.sh")
GATE_COMMAND = f'bash "${{CLAUDE_PROJECT_DIR:-.}}/{SCRIPTS_DIR}/precommit-runner.sh"'
GATE_STATUS = "harness-tier: flow 게이트 + 테스트 검사 중…"  # register_gate fixes this up on rename
GATE_ENTRY = {
    "matcher": "Bash",
    "hooks": [
        {
            "type": "command",
            "shell": "bash",
            "command": GATE_COMMAND,
            "timeout": 600,
            "statusMessage": GATE_STATUS,
        }
    ],
}

# Markers of the Teams management block in the host CLAUDE.md (inserted by /flow-init Step 3).
# uninstall removes everything between these markers (inclusive).
CLAUDE_MD_BEGIN = "<!-- harness-tier:teams BEGIN"
CLAUDE_MD_END = "<!-- harness-tier:teams END"

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


def copy_artifacts(plugin: Path, host: Path) -> list[str]:
    """Copy deployment artifacts (always overwrite — SOURCE is the SSOT). Gate scripts go to
    scripts/, and the plugin policy flow-tiers.yaml goes to config/ (same place as flow-config)."""
    dest_dir = host / SCRIPTS_DIR
    try:
        dest_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # First of the steps, and unguarded it took every later one down with it — the
        # workflows and the .gitignore are worth having even where this is not.
        return [f"  [!] {SCRIPTS_DIR} 를 만들지 못했습니다({_why(exc)}) — 수동 확인 필요"]
    report: list[str] = []
    for rel in COPY_FILES:
        src = plugin / rel
        if not src.is_file():
            report.append(f"  [!] 소스 없음, skip: {rel}")
            continue
        try:
            shutil.copyfile(src, dest_dir / Path(rel).name)
        except OSError as exc:
            # One file the host holds open or keeps read-only is one file, not the whole run.
            report.append(f"  [!] 복사 실패({_why(exc)}): {Path(rel).name}")
            continue
        report.append(f"  [+] 복사: {Path(rel).name}")
    # The policy file goes to config/ (a host-owned dir, but this file alone is plugin-owned·SSOT).
    tiers_src = plugin / TIERS_FILENAME
    try:
        # The directory is made either way: `/flow-init` puts the host's own flow-config
        # beside this file, and a missing SOURCE is no reason to withhold the place for it.
        cfg_dir = host / CONFIG_DIR
        cfg_dir.mkdir(parents=True, exist_ok=True)
        if not tiers_src.is_file():
            report.append(f"  [!] 소스 없음, skip: {TIERS_FILENAME}")
            return report
        shutil.copyfile(tiers_src, cfg_dir / TIERS_FILENAME)
    except OSError as exc:
        report.append(f"  [!] {TIERS_FILENAME} 복사 실패({_why(exc)}) — 수동 확인 필요")
        return report
    report.append(f"  [+] 복사: {TIERS_FILENAME} → config/")
    return report


def _load_settings(host: Path) -> tuple[Path, dict | None, str | None]:
    """Return the settings.json path·parse result. On parse failure, (path, None, error message)."""
    settings = host / ".claude" / "settings.json"
    try:
        settings.parent.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return settings, None, f"  [!] .claude 를 만들지 못했습니다({_why(exc)}) — 수동 확인 필요"
    try:
        exists = settings.is_file()
    except OSError as exc:  # a `.claude` the host closed; `is_file` does not swallow this
        return (
            settings,
            None,
            f"  [!] settings.json 을 읽지 못했습니다({_why(exc)}) — 수동 확인 필요",
        )
    if not exists:
        return settings, {}, None
    try:
        data = json.loads(settings.read_text(encoding="utf-8-sig"))
    except UnicodeDecodeError:
        return settings, None, "  [!] settings.json 이 UTF-8 이 아닙니다 — 수동 확인 필요"
    except (json.JSONDecodeError, RecursionError):
        return settings, None, "  [!] settings.json 파싱 실패 — 수동 확인 필요"
    except OSError as exc:
        return (
            settings,
            None,
            f"  [!] settings.json 을 읽지 못했습니다({_why(exc)}) — 수동 확인 필요",
        )
    # `null` is what a host's own tooling writes for "nothing set yet". Every other value that
    # happens to be falsy — `0`, `[]`, an empty string — is data, and reading it as an empty
    # object overwrote it while reporting a clean registration.
    if data is None:
        data = {}
    if not isinstance(data, dict):
        return settings, None, "  [!] settings.json 이 객체가 아닙니다 — 수동 확인 필요"
    return settings, data, None


def _why(exc: BaseException) -> str:
    """What to put in a report line. An OSError raised without an errno has no `strerror`."""
    return getattr(exc, "strerror", None) or str(exc) or type(exc).__name__


def _installed(host: Path, plugin: Path, rel: str, source: str) -> bool:
    """Whether the host carries the file this installs, byte for byte.

    Asked as `is_file`, a destination the copy created and could not fill answered yes:
    an empty `precommit-runner.sh` exits 0, an empty policy parses as nothing, and the
    gate that reported itself installed denied no commit. A partial write is the same
    case one step along, which is why this compares rather than measures. A source it
    cannot read is not a confirmation either, and neither is a host directory this may not
    enter: `read_bytes` RAISES there where it answers False for a name that is simply not
    taken, and unanswered it took the run down before its verdict."""
    try:
        want = (plugin / source).read_bytes()
    except OSError:
        return False
    try:
        return (host / rel).read_bytes() == want
    except OSError:
        return False


_ACCESS_ENTRIES = "system.posix_acl_access"


def _access_entries(path: Path) -> bytes | None:
    """The file's POSIX access entries, where the host has any. Read before the rename,
    because after it the inode they belong to is gone."""
    try:
        return os.getxattr(path, _ACCESS_ENTRIES)
    except (AttributeError, OSError):
        return None


def _default_mode(tmp: Path) -> None:
    """What a file this CREATES should be. `mkstemp` makes one only its owner can read,
    and a rename carries that: on a build machine where the session runs as another uid,
    a settings.json installed at 0600 is a gate that never loads."""
    try:
        mask = os.umask(0)
        os.umask(mask)
        os.chmod(tmp, 0o666 & ~mask)
    except OSError:
        pass


def _carry_over(before: os.stat_result, acl: bytes | None, tmp: Path) -> None:
    """Put back on `tmp` what a rename does not carry. Best effort: a host whose filesystem
    holds none of this, or a process not allowed to give a file away, keeps what it had."""
    try:
        os.chmod(tmp, stat.S_IMODE(before.st_mode))
    except OSError:
        pass
    if acl is not None:
        try:
            os.setxattr(tmp, _ACCESS_ENTRIES, acl)
        except (AttributeError, OSError):
            pass
    try:
        if before.st_uid != os.getuid() or before.st_gid != os.getgid():
            os.chown(tmp, before.st_uid, before.st_gid)
    except (AttributeError, OSError):
        pass


def _write_json(path: Path, data: dict) -> str | None:
    """Write, or return the line to report instead.

    Through a temporary file and one rename, because opening for writing truncates first: a
    full disk, a dropped share or a lone surrogate in the host's own data would otherwise
    leave their settings a fragment that no longer parses — and this runs partway through a
    setup whose remaining steps are unguarded. Every way the write can fail is caught, not
    the ones that have been seen: the encode raises ValueError, the rest raise OSError.

    A rename replaces the NAME, so a settings.json a host keeps as a symlink into their
    dotfiles came back a plain file while their managed copy kept the old content — and the
    next sync put a gate-less settings back. The rename lands on what the link points AT for
    that reason. The temporary file is unique because a fixed name beside it was a file of
    the host's own that this silently consumed.

    What a rename does not carry is the file it replaces. Its mode, its owner and its access
    entries all come from the temporary file, which is the writer's alone: a `sudo /flow-init`
    left the host's settings owned by root, and `st_mode` reports the ACL MASK in its group
    bits, so putting that back as a plain mode gave group write to a file whose owner had
    granted one named user. All three come across, the entries before the mode would reset
    their mask. A file the host locked read-only is refused — except to root, whom the write
    bit does not stop. What a new inode cannot keep is kept by nobody: a second hard link,
    the timestamps, a `user.*` attribute, and the setuid bit where the owner has to be given
    back. The link a dotfiles manager makes is a symlink, and that one survives.
    """
    target = Path(os.path.realpath(path)) if path.is_symlink() else path
    if target.is_file() and not os.access(target, os.W_OK):
        return f"  [!] {path.name} 이 쓰기 금지 상태입니다 — 수동 확인 필요"
    payload = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
    try:
        before = target.stat() if target.is_file() else None
    except OSError:  # gone between the question and the answer
        before = None
    acl = _access_entries(target) if before is not None else None
    tmp = None
    try:
        fd, name = tempfile.mkstemp(dir=target.parent, prefix=target.name + ".", suffix=".new")
        tmp = Path(name)  # named before the descriptor closes: the cleanup reads `tmp`
        os.close(fd)
        tmp.write_text(payload, encoding="utf-8")
        if before is not None:
            _carry_over(before, acl, tmp)
        else:
            _default_mode(tmp)
        os.replace(tmp, target)
        tmp = None
    except (OSError, ValueError) as exc:
        return f"  [!] {path.name} 을 쓰지 못했습니다({_why(exc)}) — 수동 확인 필요"
    finally:
        # Not only the two the write raises: an interrupt through here leaves the file
        # in the host's `.claude/`, which is ground they track.
        if tmp is not None:
            try:
                tmp.unlink()
            except OSError:
                pass
    return None


def _is_gate_hook(hook: object) -> bool:
    """Whether this is one of the gate's own hooks. A `command` the host wrote as something
    other than a string is not one, and asking `in` of it raises."""
    if not isinstance(hook, dict) or not isinstance(hook.get("command"), str):
        return False
    return all(word in hook["command"] for word in GATE_MARKER)


# The alphabet that keeps a matcher a name rather than a pattern, per the hooks reference.
# Inside it the two dialects agree — `|` alternates in both and everything else is literal —
# so the same string can be read both ways and the answers compared.
_EXACT_MATCHER_RE = re.compile(r"[A-Za-z0-9_\- ,|]*")


def _covers_bash(matcher: object) -> bool | None:
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


def register_gate(host: Path) -> str:
    """Register the commit gate in .claude/settings.json. Skip if already present; if the registered
    command/statusMessage differs from the current value, fix it up (for plugin updates)."""
    settings, data, err = _load_settings(host)
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
        covers = _covers_bash(entry.get("matcher"))
        if covers is None:
            undecided += sum(1 for h in hooks if _is_gate_hook(h))
        elif not covers:
            kept = [h for h in hooks if not _is_gate_hook(h)]
            moved += len(hooks) - len(kept)
            entry["hooks"] = kept
    gate_hooks = [
        h
        for e in entries
        if isinstance(e.get("hooks"), list)
        for h in e["hooks"]
        if _is_gate_hook(h)
    ]
    # Only a hook under a matcher known to fire is the gate. One under a matcher this script
    # cannot decide may be doing the job already, which is why it is left alone — and may not
    # be, which is why it does not count as the gate.
    firing = [
        h
        for e in entries
        if isinstance(e.get("hooks"), list) and _covers_bash(e.get("matcher"))
        for h in e["hooks"]
        if _is_gate_hook(h)
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
    failed = _write_json(settings, data)
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
    settings, data, err = _load_settings(host)
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
    failed = _write_json(settings, data)
    if failed:
        return failed
    return msg


def append_gitignore(host: Path) -> list[str]:
    """Add only the missing lines to .gitignore (without duplicates). Skip if all are present."""
    gi = host / ".gitignore"
    text = gi.read_text(encoding="utf-8") if gi.is_file() else ""
    existing = {ln.strip() for ln in text.splitlines()}
    missing = [ln for ln in GITIGNORE_LINES if ln not in existing]
    if not missing:
        return ["  [=] .gitignore 이미 최신 (skip)"]
    if text and not text.endswith("\n"):
        text += "\n"
    text += "".join(ln + "\n" for ln in missing)
    gi.write_text(text, encoding="utf-8")
    return [f"  [+] .gitignore += {ln}" for ln in missing]


def _find_hook_entry(cfg: dict, hook_id: str) -> str | None:
    """Find the `entry` value of the given hook id in the pre-commit config dict (None if none)."""
    for repo in cfg.get("repos") or []:
        if not isinstance(repo, dict):
            continue
        for hook in repo.get("hooks") or []:
            if isinstance(hook, dict) and hook.get("id") == hook_id:
                return hook.get("entry")
    return None


def check_precommit(plugin: Path, host: Path) -> list[str]:
    """Handle static-analysis hooks. If the file is absent, copy (create) the example. **If it
    already exists, do not auto-merge** — because a PyYAML round-trip would normalize (destroy)
    existing comments/formatting. Instead, detect missing repo/hooks and only report them, leaving
    the user to add them.
    """
    import yaml

    example = plugin / "pre-commit-hooks.example.yaml"
    dest = host / ".pre-commit-config.yaml"
    if not example.is_file():
        return ["  [!] pre-commit-hooks.example.yaml 없음 — skip"]
    if not dest.is_file():
        shutil.copyfile(example, dest)
        return ["  [+] .pre-commit-config.yaml 생성 (예시 복사 — local 훅은 팀 언어로 교체)"]
    try:
        ex = yaml.safe_load(example.read_text(encoding="utf-8")) or {}
        cur = yaml.safe_load(dest.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError:
        return ["  [!] .pre-commit-config.yaml 파싱 실패 — 수동 확인 필요"]
    if not isinstance(ex, dict) or not isinstance(cur, dict):
        return ["  [!] .pre-commit-config.yaml 형식이 예상과 다릅니다 — 수동 확인 필요"]
    by_url = {r.get("repo"): r for r in (cur.get("repos") or []) if isinstance(r, dict)}
    missing: list[str] = []
    for exrepo in ex.get("repos", []):
        url = exrepo.get("repo")
        target = by_url.get(url)
        if target is None:
            missing.append(f"repo {url} (전체)")
            continue
        have = {h.get("id") for h in (target.get("hooks") or []) if isinstance(h, dict)}
        missing += [
            f"{url}#{h.get('id')}" for h in exrepo.get("hooks", []) if h.get("id") not in have
        ]
    # entry-path drift of the harness-tier-owned hook — when a plugin update moves a script's
    # location, the existing entry points at a different path than the current one, so
    # pre-push breaks. Do not auto-fix (preserve comments/formatting); only report.
    ex_entry = _find_hook_entry(ex, OWNED_HOOK_ID)
    cur_entry = _find_hook_entry(cur, OWNED_HOOK_ID)
    stale: list[str] = []
    if ex_entry and cur_entry and ex_entry != cur_entry:
        stale = [
            f"  [!] '{OWNED_HOOK_ID}' entry 가 현재 경로와 다릅니다: {cur_entry}",
            f"        → '{ex_entry}' 로 직접 수정하세요(스크립트 위치 변경).",
        ]
    if not missing:
        return ["  [=] pre-commit 훅 이미 충족 (변경 없음)", *stale]
    out = [
        "  [i] .pre-commit-config.yaml 가 이미 있어 자동 병합하지 않음(주석/포맷 보존).",
        "  [i] 아래 빠진 항목을 pre-commit-hooks.example.yaml 참고해 직접 추가하세요:",
    ]
    out += [f"        - {m}" for m in missing]
    return out + stale


# ── uninstall (cleanup) — the inverse of setup ─────────────────────────────────


def _strip_gate_hooks(entry: object) -> int:
    """Remove the gate's own hooks from one entry; returns how many. The entry stays.

    `register_gate` leaves the gate hook inside a host entry whenever that entry already fires
    on Bash, so an entry holding the gate may hold the host's hooks beside it — taking the
    entry would take those with it.
    """
    if not isinstance(entry, dict) or not isinstance(entry.get("hooks"), list):
        return 0
    hooks = entry["hooks"]
    entry["hooks"] = [h for h in hooks if not _is_gate_hook(h)]
    return len(hooks) - len(entry["hooks"])


def _is_own_empty_entry(entry: object) -> bool:
    """An entry this plugin wrote and has just emptied — nothing of the host's is in it."""
    return (
        isinstance(entry, dict)
        and set(entry) == set(GATE_ENTRY)
        and entry.get("matcher") == GATE_ENTRY["matcher"]
        and entry.get("hooks") == []
    )


def unregister_gate(host: Path) -> str:
    """Remove the commit gate hook from settings.json (skip if absent)."""
    settings, data, err = _load_settings(host)
    if data is None:
        return err
    hooks = data.get("hooks") if isinstance(data, dict) else None
    pre = hooks.get("PreToolUse") if isinstance(hooks, dict) else None
    if not isinstance(pre, list):
        return "  [=] 게이트 훅 없음 (skip)"
    if not sum(_strip_gate_hooks(entry) for entry in pre):
        return "  [=] 게이트 훅 없음 (skip)"
    hooks["PreToolUse"] = [e for e in pre if not _is_own_empty_entry(e)]
    failed = _write_json(settings, data)
    if failed:
        return failed
    return "  [-] 커밋 게이트 해제 (settings.json)"


def unregister_marketplace(host: Path) -> str:
    """Remove the harness-tier marketplace from settings.json (skip if absent)."""
    settings, data, err = _load_settings(host)
    if data is None:
        return err
    mkts = data.get("extraKnownMarketplaces")
    if not isinstance(mkts, dict) or MARKETPLACE_NAME not in mkts:
        return "  [=] harness-tier 마켓 등록 없음 (skip)"
    del mkts[MARKETPLACE_NAME]
    failed = _write_json(settings, data)
    if failed:
        return failed
    return "  [-] harness-tier 마켓 등록 해제 (settings.json)"


def remove_gitignore_lines(host: Path) -> str:
    """Remove only the lines added by harness-tier from .gitignore (preserve other lines)."""
    gi = host / ".gitignore"
    if not gi.is_file():
        return "  [=] .gitignore 없음 (skip)"
    targets = set(GITIGNORE_LINES)
    lines = gi.read_text(encoding="utf-8").splitlines()
    kept = [ln for ln in lines if ln.strip() not in targets]
    removed = len(lines) - len(kept)
    if removed == 0:
        return "  [=] .gitignore 에 harness-tier 라인 없음 (skip)"
    text = "\n".join(kept)
    if text and not text.endswith("\n"):
        text += "\n"
    gi.write_text(text, encoding="utf-8")
    return f"  [-] .gitignore harness-tier 라인 {removed}개 제거"


def remove_claude_md_block(host: Path) -> str:
    """Remove the harness-tier:teams block (markers included) from CLAUDE.md (skip if absent)."""
    cm = host / "CLAUDE.md"
    if not cm.is_file():
        return "  [=] CLAUDE.md 없음 (skip)"
    lines = cm.read_text(encoding="utf-8").splitlines(keepends=True)
    begin = end = None
    for i, ln in enumerate(lines):
        if begin is None and CLAUDE_MD_BEGIN in ln:
            begin = i
        elif begin is not None and CLAUDE_MD_END in ln:
            end = i
            break
    if begin is None or end is None:
        return "  [=] CLAUDE.md teams 블록 없음 (skip)"
    del lines[begin : end + 1]
    cm.write_text("".join(lines), encoding="utf-8")
    return "  [-] CLAUDE.md teams 블록 제거"


def remove_harness_dir(host: Path) -> str:
    """Delete the entire .claude/harness-tier/ directory (scripts·config·evidence·webhooks)."""
    d = host / HARNESS_DIR
    if not d.is_dir():
        return "  [=] .claude/harness-tier/ 없음 (skip)"
    shutil.rmtree(d)
    return "  [-] .claude/harness-tier/ 삭제 (스크립트·config·증거·웹훅 포함)"


def _load_yaml_safe(path: Path) -> dict:
    """Read a YAML file as a dict. Absent·parse failure·non-dict → {} (FAIL-OPEN)."""
    import yaml

    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _diff_missing(ex: dict, cur: dict, prefix: list[str]) -> list[dict]:
    """Recursively collect keys present in example but missing in host (cur), by insertion unit.

    - If cur lacks a key, record that point as an insertion unit (do not descend further —
      the parent block is inserted verbatim).
    - If both are dicts, descend further. If the cur side is not a dict (scalar/list/empty), stop.
    - If the example value is a dict but the host value is not (scalar/list), stop the recursion and
      leave that subtree unreported (assumed the host set it to a custom type).
    """
    out: list[dict] = []
    for key, ex_val in ex.items():
        if key not in cur:
            path = prefix + [key]
            out.append({"path": path, "parent": list(prefix), "label": ".".join(path)})
        elif isinstance(ex_val, dict) and isinstance(cur.get(key), dict):
            out.extend(_diff_missing(ex_val, cur[key], prefix + [key]))
    return out


def missing_config_slots(host: Path, plugin: Path) -> list[dict]:
    """Return slots present in example but missing from the host config, by insertion unit.

    Each item {"path", "parent", "label"}. 'Missing' means key absence only (if the key is present
    even with an empty value, it is excluded — intentional empty values are preserved). If the host
    config is absent·empty·fails to parse, all top-level example slots are returned (equivalent to a
    fresh install). This function is called by flow-init only when the host config exists (a fresh
    install has a separate full-generation path). example absent → []. flow-init uses this list to
    insert example blocks verbatim (preserving comments).
    """
    ex = _load_yaml_safe(plugin / EXAMPLE_CONFIG)
    if not ex:
        return []
    cur = _load_yaml_safe(config_path(host))
    return _diff_missing(ex, cur, [])


def report_missing_config_slots(host: Path, plugin: Path) -> list[str]:
    """For run_setup reporting: missing config slots as readable lines. If none, one skip line."""
    slots = missing_config_slots(host, plugin)
    if not slots:
        return ["  [=] config 슬롯 최신 (skip)"]
    labels = ", ".join(s["label"] for s in slots)
    return [
        f"  [i] example 에 새 config 슬롯 {len(slots)}개: {labels}",
        "      → /flow-init 으로 호스트 config 에 추가를 검토하세요.",
    ]


def load_contract_config(host: Path) -> dict | None:
    """Return contract_test dict from flow-config.yaml (None if absent/unparseable — FAIL-OPEN)."""
    import yaml

    cfg = config_path(host)
    if not cfg.is_file():
        return None
    try:
        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except (yaml.YAMLError, OSError):
        return None
    if not isinstance(data, dict):
        # A host file a person edits, so a list or a scalar at the top is a spelling
        # mistake, not an impossibility — and unread it ended the run before its verdict.
        return None
    ct = data.get("contract_test")
    return ct if isinstance(ct, dict) else None


def render_workflow(host: Path, plugin: Path) -> list[str]:
    """Render .github/workflows/api-contract.yml from the contract_test configuration.

    Idempotent·non-destructive: not installed if enable=false/section absent; if the target file
    already exists, only report (no auto-merge·overwrite — same pattern as .pre-commit-config.yaml).
    Since GitHub forces the location, .github/workflows/ is an exception to the HARNESS_DIR rule.
    """
    ct = load_contract_config(host)
    if ct is None:
        return ["  [=] contract_test 미설정 — 워크플로우 skip"]
    if not ct.get("enable"):
        return ["  [=] contract_test.enable=false — 워크플로우 미설치"]
    template = plugin / WORKFLOW_TEMPLATE
    if not template.is_file():
        return ["  [!] 워크플로우 템플릿 없음 — skip"]
    dest = host / WORKFLOW_DEST
    if dest.is_file():
        return [
            "  [i] .github/workflows/api-contract.yml 이미 있어 자동 병합 안 함(주석/커스텀 보존).",
            "  [i] 갱신하려면 기존 파일을 지우고 /flow-init 을 재실행하거나 직접 수정하세요.",
        ]
    branches = ct.get("branches") or ["dev", "stage", "main"]
    server = ct.get("server") or {}
    replacements = {
        "__HARNESS_BRANCHES__": ", ".join(str(b) for b in branches),
        "__HARNESS_ACTION_REF__": str(ct.get("action_ref", "schemathesis/action@v3")),
        "__HARNESS_SCHEMA__": str(ct.get("schema", "")),
        "__HARNESS_BASE_URL__": str(ct.get("base_url", "")),
        "__HARNESS_COMPOSE_FILE__": str(server.get("compose_file", "docker-compose.yml")),
        "__HARNESS_HEALTH_URL__": str(server.get("health_url", "")),
        "__HARNESS_HEALTH_TIMEOUT__": str(server.get("health_timeout", 60)),
    }
    try:
        text = template.read_text(encoding="utf-8")
        for token, value in replacements.items():
            text = text.replace(token, value)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    except OSError as exc:
        return [f"  [!] 워크플로우 렌더링 실패(수동 확인): {exc}"]
    return ["  [+] .github/workflows/api-contract.yml 생성 (contract_test 렌더링)"]


def load_versioning_config(host: Path) -> dict | None:
    """Return versioning dict from flow-config.yaml (None if absent/unparseable — FAIL-OPEN)."""
    cfg = host / HARNESS_DIR / "config" / "flow-config.yaml"
    try:
        data = _load_yaml_safe(cfg)
    except Exception:
        return None
    v = data.get("versioning")
    return v if isinstance(v, dict) else None


def load_deploy_config(host: Path) -> dict | None:
    """Return deploy dict from flow-config.yaml (None if absent/unparseable — FAIL-OPEN)."""
    try:
        import yaml

        cfg = config_path(host)
        if not cfg.exists():
            return None
        data = yaml.safe_load(cfg.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return None
        d = data.get("deploy")
        return d if isinstance(d, dict) else None
    except Exception:
        return None


_RELEASE_TEMPLATES = {
    "python-semantic-release": "github/release.python-semantic-release.workflow.example.yml",
    "semantic-release": "github/release.semantic-release.workflow.example.yml",
    "jreleaser": "github/release.jreleaser.workflow.example.yml",
    "gitversion": "github/release.gitversion.workflow.example.yml",
    "cargo-release": "github/release.cargo-release.workflow.example.yml",
}


def _render_one(src: Path, dest: Path, subs: dict, label: str = "versioning 렌더") -> list[str]:
    if not src.exists():
        return [f"  [!] 템플릿 없음: {src.name} — skip"]
    if dest.exists():
        return [f"  [i] {dest.name} 이미 있어 자동 병합 안 함(커스텀 보존)."]
    text = src.read_text(encoding="utf-8")
    for k, val in subs.items():
        text = text.replace(k, val)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return [f"  [+] .github/workflows/{dest.name} 생성 ({label})"]


def render_versioning_workflows(host: Path, plugin: Path) -> list[str]:
    """Render the release/branch-naming/entropy workflows from the versioning configuration.

    Idempotent·non-destructive: not installed if enable=false/section absent; if the target file
    already exists, only report (no auto-merge·overwrite). FAIL-OPEN — exceptions pass through
    (do not block the gate).
    """
    v = load_versioning_config(host)
    if not v:
        return ["  [=] versioning 미설정 — 워크플로 skip"]
    if not v.get("enable", False):
        return ["  [=] versioning.enable=false — 워크플로 미설치"]
    out: list[str] = []
    branches = v.get("branches", {}) or {}
    stable = str(branches.get("stable", "main"))
    prerelease = str(branches.get("prerelease", "") or "")
    subs = {"__HARNESS_STABLE__": stable, "__HARNESS_PRERELEASE__": prerelease}
    wf_dir = host / ".github" / "workflows"

    # release (per tool) — case-insensitive: harness-init research may propose the tool's
    # proper-noun spelling (e.g. "JReleaser", "GitVersion") while the lookup keys stay lowercase.
    tool = str(v.get("release_tool", ""))
    tmpl = _RELEASE_TEMPLATES.get(tool.strip().lower())
    if tmpl:
        out += _render_one(plugin / tmpl, wf_dir / "release.yml", subs)
    else:
        out.append(f"  [!] 알 수 없는 release_tool={tool!r} — release.yml skip")

    # branch-naming
    if (v.get("branch_naming", {}) or {}).get("enable", False):
        out += _render_one(
            plugin / "github/branch-naming.workflow.example.yml",
            wf_dir / "branch-naming.yml",
            subs,
        )

    # entropy
    ent = v.get("entropy", {}) or {}
    if ent.get("enable", False):
        esub = dict(subs)
        esub["__HARNESS_ENTROPY_SCHEDULE__"] = str(ent.get("schedule", "0 0 * * 5"))
        esub["__HARNESS_ENTROPY_PATHS__"] = " ".join(str(p) for p in (ent.get("paths") or ["src/"]))
        out += _render_one(
            plugin / "github/entropy-check.workflow.example.yml",
            wf_dir / "entropy-check.yml",
            esub,
        )
    out += integrate_release_deploy(host, plugin)
    return out


# target → component template path (plugin-owned SOURCE). maven-central branches on build_tool.
# Targets with no static template (sbt, custom, unknown) are authored by /harness-deployments.
DEPLOY_TEMPLATE_BY_TARGET = {
    "pypi": "github/deploy.pypi.workflow.example.yml",
    "npm": "github/deploy.npm.workflow.example.yml",
    "nuget": "github/deploy.nuget.workflow.example.yml",
    "cratesio": "github/deploy.cratesio.workflow.example.yml",
    "ghcr": "github/deploy.ghcr.workflow.example.yml",
    "dockerhub": "github/deploy.dockerhub.workflow.example.yml",
}

_DEFAULT_VERSION_BY_TARGET = {"pypi": "3.12", "npm": "20", "nuget": "8.0", "maven-central": "21"}
_DEFAULT_BUILD_BY_TARGET = {
    "pypi": "python -m build",
    "npm": "npm ci",
    "nuget": "dotnet pack -c Release",
    "cratesio": "cargo build --release",
    "maven-central": "mvn -B -DskipTests package",
}
_DEFAULT_IMAGE_BY_TARGET = {
    "ghcr": "ghcr.io/${{ github.repository }}",
    "dockerhub": "${{ github.repository }}",
}


def _deploy_template_for(target: str, build_tool: str) -> str | None:
    """Component template for a target. maven-central branches on build_tool; None → authored
    by /harness-deployments (sbt / custom / unknown)."""
    if target == "maven-central":
        if build_tool == "gradle":
            return "github/deploy.gradle.workflow.example.yml"
        if build_tool == "sbt":
            return None  # reference-authored (base64 PGP_SECRET, different from maven/gradle)
        return "github/deploy.maven-central.workflow.example.yml"  # maven (default)
    return DEPLOY_TEMPLATE_BY_TARGET.get(target)


def _deploy_target_wired(t) -> bool:
    """True iff this target contributes a job to deploy.yml — i.e. its component workflow will
    exist. Authored targets (custom / sbt / unknown → no static template; the skill writes the
    file, or config `workflow` points at it) are wired by design. A mapped static template is
    wired only if it actually renders: maven-central+gradle needs `publish` (no default), else
    it is skipped and would dangle."""
    target = str(t.get("target", "")).strip()
    build_tool = str(t.get("build_tool", "maven")).strip()
    tmpl = _deploy_template_for(target, build_tool)
    if tmpl is None:
        return True  # custom/sbt/unknown → authored elsewhere (by design)
    publish = str(t.get("publish", "")).strip()
    if tmpl.endswith("deploy.gradle.workflow.example.yml") and not publish:
        return False  # mapped but config-invalid (gradle w/o publish) → render skipped → dangle
    return True


def render_deploy_workflows(host: Path, plugin: Path) -> list[str]:
    """Render .github/workflows/deploy-<name>.yml for each configured deploy target (rev.3).

    Components are reusable workflows (on: workflow_call + workflow_dispatch); the deploy.yml
    orchestrator wires them (see render step in flow-init). Idempotent·non-destructive (skips an
    existing dest), FAIL-OPEN. custom / sbt / unknown targets are skipped with a note —
    /harness-deployments authors those. GitHub forces .github/workflows/ (exception to HARNESS_DIR).
    """
    d = load_deploy_config(host)
    if not d:
        return ["  [=] deploy 미설정 — 워크플로 skip"]
    if not d.get("enable", False):
        return ["  [=] deploy.enable=false — 워크플로 미설치"]

    timeout = str(d.get("timeout_minutes", 15))
    wf_dir = host / ".github" / "workflows"
    out: list[str] = []
    for t in d.get("targets", []) or []:
        name = str(t.get("name", "")).strip()
        target = str(t.get("target", "")).strip()
        build_tool = str(t.get("build_tool", "maven")).strip()
        if not name:
            out.append("  [!] name 없는 deploy 타깃 — skip")
            continue
        tmpl = _deploy_template_for(target, build_tool)
        if not tmpl:
            extra = f",build_tool={build_tool}" if target == "maven-central" else ""
            out.append(
                f"  [i] deploy 타깃 {name!r}(target={target}{extra}) — 템플릿 없음"
                " → /harness-deployments 저작 대상"
            )
            continue
        publish = str(t.get("publish", "")).strip()
        if tmpl.endswith("deploy.gradle.workflow.example.yml") and not publish:
            out.append(
                f"  [!] deploy 타깃 {name!r}(maven-central/gradle) — publish 필수(무기본값) → skip"
            )
            continue
        context = str(t.get("context", "") or ".")
        dockerfile = str(t.get("dockerfile", "") or f"{context}/Dockerfile")
        subs = {
            "__HARNESS_TIMEOUT__": timeout,
            "__HARNESS_BUILD__": str(
                t.get("build", "") or _DEFAULT_BUILD_BY_TARGET.get(target, "")
            ),
            "__HARNESS_VERSION__": str(
                t.get("version", "") or _DEFAULT_VERSION_BY_TARGET.get(target, "")
            ),
            "__HARNESS_IMAGE__": str(
                t.get("image", "") or _DEFAULT_IMAGE_BY_TARGET.get(target, "")
            ),
            "__HARNESS_CONTEXT__": context,
            "__HARNESS_DOCKERFILE__": dockerfile,
            "__HARNESS_PUBLISH__": publish,
        }
        out += _render_one(plugin / tmpl, wf_dir / f"deploy-{name}.yml", subs)

    orch_targets = [t for t in (d.get("targets", []) or []) if _deploy_target_wired(t)]
    if orch_targets:
        orch = wf_dir / "deploy.yml"
        orch.parent.mkdir(parents=True, exist_ok=True)
        orch.write_text(_orchestrator_yaml(orch_targets, d.get("order")), encoding="utf-8")
        out.append("  [+] .github/workflows/deploy.yml 생성(오케스트레이터, 재생성)")
    out += integrate_release_deploy(host, plugin)
    return out


def _deploy_job_permissions(target: str, auth: str, custom_permissions) -> dict:
    """Least-privilege permissions for a target's caller job in deploy.yml (spec §6.3).
    custom → the config-declared permissions verbatim; ghcr → packages:write; oidc registry →
    id-token:write; everything else → contents:read only."""
    if target == "custom":
        return custom_permissions if isinstance(custom_permissions, dict) else {"contents": "read"}
    perms = {"contents": "read"}
    if target == "ghcr":
        perms["packages"] = "write"
    elif auth == "oidc":
        perms["id-token"] = "write"
    return perms


def _deploy_union_permissions(targets) -> dict:
    """Union of every target's caller-job permissions for the release deploy job (spec §8).
    'write' beats 'read'. custom folds its declared perms. Never a config field — always
    computed."""
    union = {"contents": "read"}
    for t in targets or []:
        target = str(t.get("target", "")).strip()
        auth = str(t.get("auth", "") or ("oidc" if target in ("pypi", "npm") else "token")).strip()
        for k, v in _deploy_job_permissions(target, auth, t.get("permissions")).items():
            if k not in union or v == "write":
                union[k] = v
    return union


def _deploy_call_job(targets) -> str:
    """The release.yml deploy job that calls the deploy.yml orchestrator (same run)."""
    perms = _deploy_union_permissions(targets)
    lines = [
        "  deploy:",
        "    needs: [release]",
        "    if: ${{ needs.release.outputs.tag != '' }}",
        "    permissions:",
        *[f"      {k}: {v}" for k, v in perms.items()],
        "    uses: ./.github/workflows/deploy.yml",
        "    with:",
        "      tag: ${{ needs.release.outputs.tag }}",
        "    secrets: inherit",
    ]
    return "\n".join(lines)


def report_legacy_release_workflow(deploy_enabled: bool) -> list[str]:
    """Report (do NOT edit) a release.yml lacking the managed markers — legacy-ours or
    truly-foreign. Loud [!] so a configured-but-unwired deploy is not silently inert; two
    recovery paths (spec §8)."""
    if not deploy_enabled:
        return ["  [=] release.yml에 deploy 관리 블록 없음(deploy 비활성 — 배선 불필요)"]
    return [
        "  [!] release.yml에 harness deploy 관리 블록(__HARNESS_DEPLOY_BEGIN/END__)이 없습니다.",
        "      → deploy가 flow-config엔 켜져 있지만 release 자동 배선이 안 됩니다(발행 0 위험).",
        "      복구 A(재생성): release.yml을 새 템플릿에서 재생성하면 스크립트가 자동 배선합니다"
        "(커스터마이즈 검토).",
        "      복구 B(의미 패치): /harness-deployments가 release job에 outputs.tag + deploy 호출"
        " job을",
        "                        올바른 위치에 삽입합니다(diff 확인 후 — outputs.tag 위치는 의미"
        " 판단).",
        "      그동안 .github/workflows/deploy.yml은 workflow_dispatch(tag 입력)로 수동 실행"
        " 가능합니다.",
    ]


def integrate_release_deploy(host: Path, plugin: Path) -> list[str]:
    """Wire release.yml → deploy.yml by replacing the managed block between the
    __HARNESS_DEPLOY_BEGIN/END__ markers with the deploy call job (deploy.enable) or nothing.
    Idempotent — re-run recomputes the union permissions. Legacy/foreign release.yml (markers
    absent) is refused via report_legacy_release_workflow; the file is NOT edited (outputs.tag
    placement is semantic — spec §8). FAIL-OPEN on exceptions."""
    try:
        rel = host / ".github" / "workflows" / "release.yml"
        if not rel.exists():
            return ["  [=] release.yml 없음 — deploy 배선 skip"]
        d = load_deploy_config(host)
        enabled = bool(d and d.get("enable", False))
        wired = [t for t in (d.get("targets") if d else None) or [] if _deploy_target_wired(t)]
        body = _deploy_call_job(wired) if (enabled and wired) else ""
        text = rel.read_text(encoding="utf-8")
        lines = text.splitlines()
        begin_marker = "# __HARNESS_DEPLOY_BEGIN__"
        end_marker = "# __HARNESS_DEPLOY_END__"
        begin = next((i for i, ln in enumerate(lines) if ln.strip().startswith(begin_marker)), None)
        end = next((i for i, ln in enumerate(lines) if ln.strip().startswith(end_marker)), None)
        if begin is None or end is None or end < begin:
            return report_legacy_release_workflow(enabled)
        new_lines = lines[: begin + 1] + ([body] if body else []) + lines[end:]
        rel.write_text(
            "\n".join(new_lines) + ("\n" if text.endswith("\n") else ""), encoding="utf-8"
        )
        return [
            "  [+] release.yml deploy 배선 갱신(관리 블록)"
            if body
            else "  [=] release.yml deploy 블록 비움(deploy.enable=false)"
        ]
    except Exception:
        return ["  [i] release.yml deploy 배선 skip(내부 오류 — FAIL-OPEN)"]


def _orchestrator_yaml(targets: list, order: list | None) -> str:
    """Build the deploy.yml orchestrator: a reusable (workflow_call) + manual (workflow_dispatch)
    workflow that resolves the tag once and calls each target's component with needs:-ordering
    and per-target permissions. FULLY GENERATED/MANAGED — regenerated on every render (do not
    hand-edit)."""
    order = [str(o) for o in (order or [])]
    L = [
        "# Generated by /harness-deployments from flow-config.deploy — DO NOT EDIT.",
        "# Change targets in flow-config.yaml and re-render (/flow-init or /harness-deployments).",
        "name: deploy",
        "on:",
        "  workflow_call:",
        "    inputs:",
        "      tag:",
        "        required: true",
        "        type: string",
        "      target:",
        "        default: all",
        "        type: string",
        "  workflow_dispatch:",
        "    inputs:",
        "      tag:",
        '        description: "배포할 태그(비우면 브랜치에서 도달 가능한 최신 태그)"',
        "        required: false",
        "        type: string",
        "      target:",
        '        description: "배포할 타깃(all 또는 특정 name)"',
        "        default: all",
        "        type: string",
        "jobs:",
        "  resolve:",
        "    runs-on: ubuntu-latest",
        "    timeout-minutes: 5",
        "    permissions:",
        "      contents: read",
        "    outputs:",
        "      tag: ${{ steps.r.outputs.tag }}",
        "    steps:",
        "      - if: ${{ github.event_name == 'workflow_dispatch' }}",
        "        uses: actions/checkout@v7",
        "        with:",
        "          ref: ${{ github.ref }}",
        "          fetch-depth: 0",
        "      - id: r",
        # `tag` is an unconstrained workflow_dispatch string and the jobs downstream run with
        # `secrets: inherit`, so it must reach the shell as data. env + "$VAR" is never re-parsed;
        # `${{ }}` here would be substituted into the script before bash sees it.
        "        env:",
        "          TAG_INPUT: ${{ inputs.tag }}",
        "        run: |",
        '          TAG="$TAG_INPUT"',
        '          [ -z "$TAG" ] && TAG="$(git describe --tags --abbrev=0)"',
        '          echo "tag=$TAG" >> "$GITHUB_OUTPUT"',
    ]
    for t in targets:
        name = str(t.get("name", "")).strip()
        target = str(t.get("target", "")).strip()
        if not name or not target:
            continue
        auth = str(t.get("auth", "") or ("oidc" if target in ("pypi", "npm") else "token")).strip()
        perms = _deploy_job_permissions(target, auth, t.get("permissions"))
        needs = ["resolve"]
        if name in order:
            idx = order.index(name)
            if idx > 0:
                needs.append(order[idx - 1])
        uses = (
            str(t.get("workflow"))
            if target == "custom"
            else f"./.github/workflows/deploy-{name}.yml"
        )
        L.append(f"  {name}:")
        L.append("    permissions:")
        for k, v in perms.items():
            L.append(f"      {k}: {v}")
        L.append("    if: " + "${{ inputs.target == 'all' || inputs.target == '" + name + "' }}")
        L.append(f"    needs: [{', '.join(needs)}]")
        L.append(f"    uses: {uses}")
        L.append("    with:")
        L.append("      tag: ${{ needs.resolve.outputs.tag }}")
        for k, v in (t.get("with") or {}).items():
            L.append(f"      {k}: {v}")
        L.append("    secrets: inherit")
    return "\n".join(L) + "\n"


def load_unit_test_config(host: Path) -> dict | None:
    """Return the unit_test dict from flow-config.yaml (None if absent/unparseable — FAIL-OPEN)."""
    ut = _load_yaml_safe(config_path(host)).get("unit_test")
    return ut if isinstance(ut, dict) else None


def _unit_test_matrix_include(jobs: list) -> str:
    """Build the strategy.matrix.include body from unit_test.jobs[].

    One flow-style YAML mapping per job. The template already supplies the first list item's
    "          - " prefix (so the pre-render template itself stays valid YAML — the token sits
    at a real list position), so the first job substitutes in place and the rest are joined with
    a fresh "\\n          - " (10-space indent under strategy.matrix.include). safe_dump handles
    quoting/escaping of arbitrary command strings, and width is very high so each job stays on a
    single line (a wrap would break the block indentation).
    """
    import yaml

    flows: list[str] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        flows.append(
            yaml.safe_dump(
                job, default_flow_style=True, sort_keys=False, allow_unicode=True, width=10**9
            ).strip()
        )
    return "\n          - ".join(flows)


def _unit_test_language_warnings(jobs: list) -> list[str]:
    """Warn on a job whose `language` is a case variant of a supported one (e.g. "Python").

    The template's setup-* steps gate on lowercase literals (`if: matrix.language == 'python'`),
    so "Python"/"GO"/… silently skip the official setup and fall through to the job's own `setup`
    command — often a false-green against the runner's default runtime. A value that isn't a
    supported language at all is left alone: that's the documented custom-runtime escape hatch, so
    we only flag values that match a supported language up to case (a near-certain typo).
    """
    warnings: list[str] = []
    for job in jobs:
        if not isinstance(job, dict):
            continue
        lang = job.get("language")
        if not isinstance(lang, str):
            continue
        if lang not in SUPPORTED_SETUP_LANGUAGES and lang.lower() in SUPPORTED_SETUP_LANGUAGES:
            name = job.get("name", "?")
            warnings.append(
                f"  [!] unit_test job '{name}' language '{lang}' — 공식 setup 스텝은 소문자 "
                f"'{lang.lower()}' 만 매칭합니다. 대소문자를 맞추세요(안 그러면 setup 스킵)."
            )
    return warnings


def render_unit_test_workflow(host: Path, plugin: Path) -> list[str]:
    """Render .github/workflows/unit-test.yml from the unit_test configuration.

    Mirrors render_workflow (contract_test): idempotent·non-destructive — not installed if
    enable=false/section absent; if the target already exists, only report (no auto-merge·
    overwrite). The variable-length jobs[] become a strategy.matrix.include (one job per line).
    FAIL-OPEN — an OSError while rendering is reported, not raised (never blocks the gate).
    Since GitHub forces the location, .github/workflows/ is an exception to the HARNESS_DIR rule.
    """
    ut = load_unit_test_config(host)
    if ut is None:
        return ["  [=] unit_test 미설정 — 워크플로 skip"]
    if not ut.get("enable"):
        return ["  [=] unit_test.enable=false — 워크플로 미설치"]
    jobs = [j for j in (ut.get("jobs") or []) if isinstance(j, dict)]
    if not jobs:
        return ["  [!] unit_test.jobs 비어 있음 — 워크플로 skip"]
    template = plugin / UNIT_TEST_TEMPLATE
    if not template.is_file():
        return ["  [!] unit-test 워크플로우 템플릿 없음 — skip"]
    dest = host / UNIT_TEST_DEST
    if dest.is_file():
        return [
            "  [i] .github/workflows/unit-test.yml 이미 있어 자동 병합 안 함(주석/커스텀 보존).",
            "  [i] 갱신하려면 기존 파일을 지우고 /flow-init 을 재실행하거나 직접 수정하세요.",
        ]
    branches = ut.get("branches") or ["dev", "stage", "main"]
    warnings = _unit_test_language_warnings(jobs)
    replacements = {
        "__HARNESS_BRANCHES__": ", ".join(str(b) for b in branches),
        "__HARNESS_TIMEOUT__": str(ut.get("timeout_minutes") or UNIT_TEST_DEFAULT_TIMEOUT),
        "__HARNESS_MATRIX_INCLUDE__": _unit_test_matrix_include(jobs),
    }
    try:
        text = template.read_text(encoding="utf-8")
        for token, value in replacements.items():
            text = text.replace(token, value)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    except OSError as exc:
        return [f"  [!] unit-test 워크플로우 렌더링 실패(수동 확인): {exc}"]
    return [*warnings, "  [+] .github/workflows/unit-test.yml 생성 (unit_test 렌더링)"]


def render_wiki_verify_workflow(host: Path, plugin: Path) -> list[str]:
    """Copy wiki-verify.yml as-is — no enable gate, no tokens. Unconditional on purpose:
    without a wiki the script no-ops green, so rendering at /flow-init time removes the
    ordering dependency on /wiki-init (which usually runs later). Idempotent·non-destructive
    (existing dest → report only), same as every other workflow render here."""
    return _render_one(
        plugin / WIKI_VERIFY_TEMPLATE, host / WIKI_VERIFY_DEST, {}, "wiki-verify 렌더"
    )


def _gate_problems(host: Path, plugin: Path) -> list[str]:
    """Why the commit gate would not run in this host, read back from what the run left.

    Asked of the line `register_gate` printed, the question answers itself: a write that
    failed in a LATER step, a matcher that does not fire, and hooks turned off wholesale
    all leave that line saying nothing is wrong — and a registration refused while the
    gate is already there and firing leaves one saying something is.

    The files it runs are asked of the filesystem, and asked whether they are what this
    installs rather than whether the name is taken. The hook is a
    line of text naming one, so a copy step that reported `[!]` and scrolled past leaves
    a registration this would otherwise call finished: `bash` answers 127 to a script
    that is not there, the policy's absence turns every classification into an internal
    error the gate fails open on, and neither is the exit 2 that denies a commit.
    """
    problems = []
    missing = [
        Path(rel).name for rel, source in GATE_FILES if not _installed(host, plugin, rel, source)
    ]
    if missing:
        problems.append(
            "커밋 게이트가 쓰는 파일이 호스트에 없거나 손상됐습니다("
            + ", ".join(missing)
            + ") — 훅이 등록되어 있어도 아무 커밋도 막지 못합니다."
            " 위 [!] 를 해결한 뒤 /flow-init 를 다시 실행하세요."
        )
    _settings, data, _err = _load_settings(host)
    if data is None:
        problems.append(
            "settings.json 을 읽지 못해 커밋 게이트를 확인할 수 없습니다 — 위 [!] 를"
            " 해결한 뒤 /flow-init 를 다시 실행하세요."
        )
        return problems
    hooks = data.get("hooks")
    pre = hooks.get("PreToolUse") if isinstance(hooks, dict) else None
    # The hook has to be the one this plugin writes, not merely one of its own: the repair
    # that takes an `if` back off lands only when the write does, and a matcher this
    # cannot decide is not one that fails to fire — a host who anchored `^Bash$` has a
    # gate, and saying otherwise sends them to fix what is not broken.
    firing = any(
        _covers_bash(entry.get("matcher")) is not False
        and any(h == GATE_ENTRY["hooks"][0] for h in entry["hooks"])
        for entry in (pre if isinstance(pre, list) else [])
        if isinstance(entry, dict) and isinstance(entry.get("hooks"), list)
    )
    if not firing:
        problems.append(
            "커밋 게이트가 settings.json 에 없습니다 — 위 [!] 를 해결한 뒤 /flow-init 를"
            " 다시 실행하세요."
        )
    if data.get("disableAllHooks") is True:
        problems.append(
            "settings.json 의 disableAllHooks 가 켜져 있어 커밋 게이트를 포함한 모든"
            " 훅이 실행되지 않습니다 — 끄세요."
        )
    return problems


def _gate_hook_remains(host: Path) -> bool:
    """Whether a gate hook may still be in the host's settings.json.

    A file this cannot read is one it cannot clear either, and the run has already deleted
    the scripts the hook names — so unreadable counts as left behind. Answering no there
    put `정리 완료.` over a hook pointing at nothing, which is the lie this exists to stop.
    """
    _settings, data, _err = _load_settings(host)
    if data is None:
        return True
    hooks = data.get("hooks")
    pre = hooks.get("PreToolUse") if isinstance(hooks, dict) else None
    return any(
        _is_gate_hook(h)
        for entry in (pre if isinstance(pre, list) else [])
        if isinstance(entry, dict) and isinstance(entry.get("hooks"), list)
        for h in entry["hooks"]
    )


def _step(title: str, produce: Callable[[], list[str]]) -> bool:
    """Print one step of the setup, and survive a host that will not let it finish.

    Each step reports its own trouble as a `[!]` line, but only the trouble it went
    looking for: a `.claude` the host closed raises out of the probe before the report
    is written, and the verdict at the end — the one line that says whether the gate
    is on — is then never reached at all. Whether it finished is the caller's to report:
    a run that ends on the word 완료 over a step that did not is the same lie in small.
    """
    print(title)
    try:
        for line in produce():
            print(line)
    except (OSError, UnicodeDecodeError) as exc:
        print(f"  [!] 이 단계를 끝내지 못했습니다({_why(exc)}) — 수동 확인 필요")
        return False
    return True


def run_setup(host: Path, plugin: Path) -> bool:
    """Run every step, and answer whether the commit gate is registered.

    Every settings.json this cannot read or write reports a line and lets the rest of
    the setup run, which is right — the workflows and the .gitignore are worth having
    either way. It also means the one step whose absence turns the gate off scrolls
    past among forty others, so it is said again at the end and in the exit code.

    A step that cannot finish at all is the same case, not a worse one: it reports a
    line and the run goes on, because the verdict is what the caller came for.
    """
    print(f"flow-init 기계적 셋업 — host={host}")
    finished = [
        _step("[복사]", lambda: copy_artifacts(plugin, host)),
        _step("[커밋 게이트]", lambda: [register_gate(host)]),
        _step("[마켓 자동 업데이트]", lambda: [register_marketplace(host)]),
        _step("[pre-commit 점검]", lambda: check_precommit(plugin, host)),
        _step("[gitignore]", lambda: append_gitignore(host)),
        _step("[계약 테스트 워크플로우]", lambda: render_workflow(host, plugin)),
        _step("[버저닝 워크플로우]", lambda: render_versioning_workflows(host, plugin)),
        _step("[유닛 테스트 워크플로우]", lambda: render_unit_test_workflow(host, plugin)),
        _step("[wiki 검증 워크플로우]", lambda: render_wiki_verify_workflow(host, plugin)),
        _step("[배포 워크플로우]", lambda: render_deploy_workflows(host, plugin)),
        _step("[config 슬롯 점검]", lambda: report_missing_config_slots(host, plugin)),
    ]
    problems = _gate_problems(host, plugin)
    if problems:
        for line in problems:
            print(line)
        return False
    if not all(finished):
        # The gate is on, which is what the answer is about — but a step that could not
        # finish left something else undone, and the word 완료 alone hides it.
        print("기계적 셋업 완료 — 다만 끝내지 못한 단계가 있습니다(위 [!] 확인).")
        return True
    print("기계적 셋업 완료.")
    return True


def run_uninstall(host: Path) -> bool:
    """Run every step, and answer whether the gate hook is gone.

    A settings.json this cannot write leaves the hook behind while the rest of the
    run deletes the scripts it names, so every Bash command in that host then runs a
    file that is not there. Saying `정리 완료.` over that is the same lie the setup
    side told about a gate it never registered. A step that cannot finish is the same
    case again: it reports its line and the run goes on, because the verdict is what
    the caller came for."""
    print(f"harness-tier 정리(uninstall) — host={host}")
    finished = [
        _step("[커밋 게이트 해제]", lambda: [unregister_gate(host)]),
        _step("[마켓 등록 해제]", lambda: [unregister_marketplace(host)]),
        _step("[gitignore 정리]", lambda: [remove_gitignore_lines(host)]),
        _step("[CLAUDE.md teams 블록 제거]", lambda: [remove_claude_md_block(host)]),
        _step("[harness-tier 디렉터리 삭제]", lambda: [remove_harness_dir(host)]),
    ]
    print("[남는 항목 — 수동 처리 안내]")
    print("  - .pre-commit-config.yaml 의 teams-notify-push 훅/정적분석 훅은 자동 제거하지")
    print("    않습니다(주석·팀 커스텀 보존). 필요 시 직접 제거하세요.")
    print("  - .github/workflows/api-contract.yml 은 자동 삭제하지 않습니다(팀 커스텀 보존).")
    print("    계약 테스트를 끄려면 직접 제거하세요.")
    print("  - .github/workflows/wiki-verify.yml 은 방금 삭제된")
    print("    .claude/harness-tier/scripts/ 의 스크립트를 실행합니다. 없는 스크립트를 가드가")
    print("    보고 exit 0 하므로 CI 가 빨개지지는 않지만 더는 아무것도 검증하지 못하니 함께")
    print("    제거하세요. 같은 경로를 쓰는 release 워크플로우는 렌더한 종류에 달렸습니다 —")
    print("    python-semantic-release 는 가드가 있고, gitversion·jreleaser 는 가드가 없어")
    print("    릴리스 브랜치 push 에서 실패합니다.")
    print("  - 설치했던 git 훅 비활성화:")
    print("      pre-commit uninstall --hook-type pre-commit --hook-type commit-msg \\")
    print("        --hook-type pre-push")
    print("  - .claude/harness-tier/ 의 git 추적 파일 삭제는 커밋해야 반영됩니다.")
    if _gate_hook_remains(host):
        print(
            "커밋 게이트 훅이 settings.json 에 남았습니다 — 방금 삭제된 스크립트를"
            " 가리키므로 직접 지우세요."
        )
        return False
    if not all(finished):
        # The hook is gone, which is what the answer is about — but a step that could
        # not finish left something behind, and the word 완료 alone hides it.
        print("정리 완료 — 다만 끝내지 못한 단계가 있습니다(위 [!] 확인).")
        return True
    print("정리 완료.")
    return True


def main() -> None:
    force_utf8_io()
    parser = argparse.ArgumentParser(description="flow-init 기계적 셋업 / --uninstall 정리")
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="호스트에서 harness-tier 배선을 제거(setup 의 역연산)",
    )
    parser.add_argument(
        "--render-deploy",
        action="store_true",
        help="flow-config.deploy 로부터 배포 워크플로우만 렌더(/harness-deployments 가 호출).",
    )
    args = parser.parse_args()
    host = host_root()
    if args.render_deploy:
        for line in render_deploy_workflows(host, plugin_root()):
            print(line)
        return
    if args.uninstall:
        if not run_uninstall(host):
            raise SystemExit(1)
    elif not run_setup(host, plugin_root()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
