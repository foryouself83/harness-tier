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
import os  # noqa: F401 — `fis.os` is the monkeypatch target the jsonfile helpers share
import shutil
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

# _ACCESS_ENTRIES·_access_entries·_write_json are unused in this module's own body — their
# caller is scripts/harness/claude/install.py — and re-exported so `flow_init_setup.<name>`
# stays a valid attribute path for its tests.
try:
    from harness.jsonfile import ACCESS_ENTRIES as _ACCESS_ENTRIES  # noqa: F401
    from harness.jsonfile import access_entries as _access_entries  # noqa: F401
    from harness.jsonfile import confine as _confine
    from harness.jsonfile import why as _why
    from harness.jsonfile import write_json as _write_json  # noqa: F401
except ImportError:
    from scripts.harness.jsonfile import ACCESS_ENTRIES as _ACCESS_ENTRIES  # noqa: F401
    from scripts.harness.jsonfile import access_entries as _access_entries  # noqa: F401
    from scripts.harness.jsonfile import confine as _confine
    from scripts.harness.jsonfile import why as _why
    from scripts.harness.jsonfile import write_json as _write_json  # noqa: F401

# The Claude settings.json gate/marketplace code lives in scripts/harness/claude/install.py,
# re-exported below under this module's names for its callers and tests.
try:
    from harness.claude import install as _claude
except ImportError:
    from scripts.harness.claude import install as _claude

# The registry of every harness this plugin knows how to gate (scripts/harness/__init__.py) —
# `load_harnesses`/`register_gates`/`_gate_problems` dispatch to it for every non-Claude name.
try:
    import harness
except ImportError:
    from scripts import harness

WORKFLOW_TEMPLATE = "github/api-contract.workflow.example.yml"  # SOURCE (plugin-owned)
WORKFLOW_DEST = ".github/workflows/api-contract.yml"  # host (GitHub-forced — HARNESS_DIR exception)

UNIT_TEST_TEMPLATE = "github/unit-test.workflow.example.yml"  # SOURCE (plugin-owned)
UNIT_TEST_DEST = ".github/workflows/unit-test.yml"  # host (GitHub-forced — HARNESS_DIR exception)

WIKI_VERIFY_TEMPLATE = "github/wiki-verify.workflow.example.yml"  # SOURCE (plugin-owned)
WIKI_VERIFY_DEST = ".github/workflows/wiki-verify.yml"  # host (GitHub-forced — HARNESS_DIR exc.)
DOC_STYLE_TEMPLATE = "github/doc-style.workflow.example.yml"  # SOURCE (plugin-owned)
DOC_STYLE_DEST = ".github/workflows/doc-style.yml"  # host (GitHub-forced — HARNESS_DIR exc.)
E2E_TEMPLATE = "github/e2e.workflow.example.yml"  # SOURCE (plugin-owned)
E2E_DEST = ".github/workflows/e2e.yml"  # host (GitHub-forced — HARNESS_DIR exception)
SRS_VERIFY_TEMPLATE = "github/srs-verify.workflow.example.yml"  # SOURCE (plugin-owned)
SRS_VERIFY_DEST = ".github/workflows/srs-verify.yml"  # host (GitHub-forced — HARNESS_DIR exc.)
# per-job wall-clock cap (minutes) when unit_test.timeout_minutes is unset
UNIT_TEST_DEFAULT_TIMEOUT = 10
# Languages the unit-test template runs an official setup-* action for (its `if: matrix.language ==`
# gates, lowercase literals). A value outside this set is a legitimate escape hatch (the job's own
# `setup` command preps the runtime), but a *case variant* of one of these (e.g. "Python") almost
# certainly means the setup step will be silently skipped — flagged as a warning at render time.
# Copied from the template, so tests/flow_init/ asserts the two stay equal.
SUPPORTED_SETUP_LANGUAGES = frozenset({"python", "node", "java", "go", "rust"})

EXAMPLE_CONFIG = "flow-config.example.yaml"  # plugin SOURCE (basis for config-slot diff)

# Gate scripts to copy to .claude/harness-tier/scripts/ (SOURCE → HOST). _harness_paths.py is a
# shared module the copied scripts import, so it must travel with them (sibling import holds in the
# single-file-copy environment). The policy file flow-tiers.yaml is copied separately to config/
# (copy_artifacts).
# Order matters where one file asks another a question. precommit-runner.sh routes on what
# flow_gate_check.py --classify answers, so the answerer is copied FIRST: mid-sync the host
# then holds an old runner and a new script, where the old runner's question goes unanswered
# and ROOT stays on main. The other order leaves a new runner asking an old script,
# which answers nothing it recognises — and a runner that reads no verdict gates nothing.
COPY_FILES = [
    "scripts/_harness_paths.py",
    "scripts/_md_anchors.py",
    "scripts/flow_gate_check.py",
    "scripts/precommit-runner.sh",
    "scripts/wiki_graph.py",
    "scripts/doc_style_check.py",
    "scripts/srs_check.py",
    "scripts/_design_md.py",
    "scripts/design_doc_check.py",
    "scripts/design_doc_render.py",
    "scripts/teams_alert.py",
    "scripts/notify-push.sh",
    "scripts/check-deps.sh",
    "scripts/check-token-write.sh",
    "scripts/finalize_prerelease.py",
    "scripts/bump_version.py",
    "scripts/changelog_section.py",
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

# Per-harness gate scripts, beyond the Claude set above (SOURCE paths under scripts/, same
# SOURCE→HOST convention as COPY_FILES). A harness whose gate the plugin does not run through
# settings.json runs it through its own wrapper instead — for Codex, gate.sh/gate.cmd are what
# its hook invokes directly, so they are gate scripts in every sense GATE_FILES already covers.
HARNESS_GATE_FILES: dict[str, list[str]] = {
    "codex": ["scripts/harness/codex/gate.sh", "scripts/harness/codex/gate.cmd"],
}
# Everything a harness copies: its gate scripts, plus tools no gate runs (Codex's AGENTS.md
# renderer and the modules it imports), so a missing one never withholds the policy.
HARNESS_COPY_FILES: dict[str, list[str]] = {
    "codex": [
        *HARNESS_GATE_FILES["codex"],
        "scripts/harness/__init__.py",
        "scripts/harness/instructions.py",
        "scripts/harness/codex/__init__.py",
        "scripts/harness/codex/instructions.py",
    ],
}


def _dest_rel(rel: str) -> Path:
    """Where a SOURCE path under scripts/ lands under the host scripts dir.

    A flat COPY_FILES entry lands at its basename (`scripts/foo.py` -> `foo.py`);
    a per-harness entry keeps its subpath instead (`scripts/harness/codex/gate.sh` ->
    `harness/codex/gate.sh`), so two harnesses may ship a same-named file without collision.
    """
    parts = Path(rel).parts
    return Path(*parts[1:]) if parts and parts[0] == "scripts" else Path(Path(rel).name)


def gate_files(harnesses) -> tuple[tuple[str, str], ...]:
    """GATE_FILES, plus the enabled harnesses' own gate scripts (what their hooks run)."""
    extra = tuple(
        (f"{SCRIPTS_DIR}/{_dest_rel(rel).as_posix()}", rel)
        for name in harnesses
        for rel in HARNESS_GATE_FILES.get(name, [])
    )
    return GATE_FILES + extra


# Lines to add to .gitignore. The personal webhook is kept as a **bare pattern** (matches at any
# depth) — narrowing the path would be a security footgun that leaves root-residual files not yet
# moved to config/ exposed (add, don't narrow). The evidence directory is anchored (fixed location).
# flow-config.yaml is team-shared config (branches·modules — not secret), so it is **tracked**
# (excluded from the ignore list — same grain as teams-webhooks.json·scripts/).
GITIGNORE_LINES = [
    ".teams-webhooks.local.json",
    f"{FLOW_DIR}/",
    # The gate exports PYTHONDONTWRITEBYTECODE; this catches every other run of the copies,
    # Codex's renderer under scripts/harness/ included.
    f"{SCRIPTS_DIR}/**/__pycache__/",
]

# The pre-commit hook id owned by harness-tier (a fixed hook, not a per-language replacement).
# When a plugin update moves a script's location, the existing .pre-commit-config.yaml entry no
# longer matches the current path, so the drift is reported.
OWNED_HOOK_ID = "teams-notify-push"

# Markers of the Teams management block in the host CLAUDE.md (inserted by /flow-init Step 3).
# uninstall removes everything between these markers (inclusive).
CLAUDE_MD_BEGIN = "<!-- harness-tier:teams BEGIN"
CLAUDE_MD_END = "<!-- harness-tier:teams END"

# Re-exported from scripts/harness/claude/install.py (see the import above), where the
# settings.json gate/marketplace constants and functions live — one harness package per
# agent this plugin installs into.
GATE_MARKER = _claude.GATE_MARKER
GATE_COMMAND = _claude.GATE_COMMAND
GATE_STATUS = _claude.GATE_STATUS
GATE_ENTRY = _claude.GATE_ENTRY
MARKETPLACE_NAME = _claude.MARKETPLACE_NAME
MARKETPLACE_REPO = _claude.MARKETPLACE_REPO
MARKETPLACE_ENTRY = _claude.MARKETPLACE_ENTRY
_load_settings = _claude.load_settings
_is_gate_hook = _claude.is_gate_hook
_covers_bash = _claude.covers_bash
register_gate = _claude.register
unregister_gate = _claude.unregister
register_marketplace = _claude.register_marketplace
unregister_marketplace = _claude.unregister_marketplace
_strip_gate_hooks = _claude._strip_gate_hooks
_is_own_empty_entry = _claude._is_own_empty_entry
_gate_hook_remains = _claude.hook_remains


def _host_target(host: Path, dest: Path) -> Path:
    """`dest`, made safe to write. The repo is untrusted input: a symlink it commits where this
    writes would carry plugin text over any file the user owns. So a directory resolving outside
    the host is refused, and a link standing at `dest` itself is removed for the write to
    replace."""
    _confine(host, dest.parent)
    if dest.is_symlink():
        dest.unlink()
    return dest


def _read_host_text(host: Path, path: Path) -> tuple[str, str]:
    """A host file this edits in place: its text with LF line ends, and the line end it was
    written in ("\n" when it does not exist). Refused when it resolves outside the host, since
    the write that follows goes wherever a link at `path` points."""
    _confine(host, path)
    if not path.is_file():
        return "", "\n"
    raw = path.read_bytes().decode("utf-8")
    return raw.replace("\r\n", "\n"), ("\r\n" if "\r\n" in raw else "\n")


def _write_host_text(path: Path, text: str, eol: str) -> None:
    """Bytes, not text mode: text mode rewrites every line end to the platform's, so a CRLF file
    edited on Linux came back LF on every line of its diff."""
    path.write_bytes(text.replace("\n", eol).encode("utf-8"))


def _make_executable(path: Path) -> None:
    """`copyfile` creates a file with the default mode; a hook runs these as scripts."""
    mode = path.stat().st_mode
    os.chmod(path, mode | (mode & 0o444) >> 2)


def copy_artifacts(plugin: Path, host: Path, harnesses=("claude",)) -> list[str]:
    """Copy deployment artifacts (always overwrite — SOURCE is the SSOT). Gate scripts go to
    scripts/ (a flat file at its basename, a per-harness file under its subpath — `_dest_rel`),
    and the plugin policy flow-tiers.yaml goes to config/ (same place as flow-config)."""
    dest_dir = host / SCRIPTS_DIR
    try:
        _confine(host, dest_dir).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        # First of the steps, and unguarded it took every later one down with it — the
        # workflows and the .gitignore are worth having even where this is not.
        return [f"  [!] {SCRIPTS_DIR} 를 만들지 못했습니다({_why(exc)}) — 수동 확인 필요"]
    report: list[str] = []
    missed: set[str] = set()
    rels = [*COPY_FILES, *(rel for name in harnesses for rel in HARNESS_COPY_FILES.get(name, []))]
    for rel in rels:
        src = plugin / rel
        dest_rel = _dest_rel(rel)
        dest_name = dest_rel.as_posix()  # flat file: its basename, same as the pre-harness report
        if not src.is_file():
            report.append(f"  [!] 소스 없음, skip: {rel}")
            missed.add(rel)
            continue
        try:
            dest_path = _host_target(host, dest_dir / dest_rel)
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(src, dest_path)
            if dest_path.suffix == ".sh":
                _make_executable(dest_path)
        except OSError as exc:
            # One file the host holds open or keeps read-only is one file, not the whole run.
            report.append(f"  [!] 복사 실패({_why(exc)}): {dest_name}")
            missed.add(rel)
            continue
        report.append(f"  [+] 복사: {dest_name}")
    # The policy file goes to config/ (a host-owned dir, but this file alone is plugin-owned·SSOT).
    tiers_src = plugin / TIERS_FILENAME
    try:
        # The directory is made either way: `/flow-init` puts the host's own flow-config
        # beside this file, and a missing SOURCE is no reason to withhold the place for it.
        cfg_dir = _confine(host, host / CONFIG_DIR)
        cfg_dir.mkdir(parents=True, exist_ok=True)
        # The policy names the gates the scripts beside it must know how to run, so a new
        # policy over an older module is the one pairing that fails CLOSED: the check asks for
        # evidence the module cannot produce and every commit in every tier is denied, with a
        # reason no `/flow` step satisfies (Invariant 1). The reverse pairing only under-gates,
        # and the next `/flow-init` repairs it. gate_files(harnesses) folds in each enabled
        # harness's own gate scripts (e.g. Codex's gate.sh/gate.cmd, which its hook runs
        # directly) — a copy that drops one is exactly as fail-closed as dropping a Claude one.
        gate_sources = {source for _, source in gate_files(harnesses) if source != TIERS_FILENAME}
        if missed & gate_sources:
            report.append(f"  [!] 게이트 스크립트가 빠져 {TIERS_FILENAME} 보류 — 재실행 필요")
            return report
        if not tiers_src.is_file():
            report.append(f"  [!] 소스 없음, skip: {TIERS_FILENAME}")
            return report
        shutil.copyfile(tiers_src, _host_target(host, cfg_dir / TIERS_FILENAME))
    except OSError as exc:
        report.append(f"  [!] {TIERS_FILENAME} 복사 실패({_why(exc)}) — 수동 확인 필요")
        return report
    report.append(f"  [+] 복사: {TIERS_FILENAME} → config/")
    return report


# Where setups before this one copied the shipped prose rule. Claude Code loads every file under
# .claude/rules/ in full each session, so the rule now reaches a session only through the hook's
# short block, and a re-sync deletes this directory (harness-tier's own) wherever it remains.
RULES_DEST = ".claude/rules/harness-tier"


def remove_rules(host: Path) -> str:
    """Delete the rules directory an older setup copied in. A link standing there is unlinked,
    never followed, and a parent resolving outside the host is refused, so a repo that commits
    either pointing elsewhere loses nothing outside."""
    d = host / RULES_DEST
    try:
        _confine(host, d.parent)
    except OSError as exc:
        return f"  [!] {RULES_DEST} 정리 거부({_why(exc)}) — 수동 확인 필요"
    if d.is_symlink():
        d.unlink()
        return f"  [-] {RULES_DEST} 링크 제거"
    if not d.is_dir():
        return f"  [=] {RULES_DEST}/ 없음 (skip)"
    shutil.rmtree(d)
    return f"  [-] {RULES_DEST}/ 삭제"


DESIGN_TEMPLATES_SOURCE = "templates/design-docs"  # plugin SOURCE, seeding only


def _design_doc_check():
    """Import design_doc_check lazily (sibling-first, then `scripts.` fallback).

    design_doc_check imports yaml + wiki_graph/srs_check/_design_md/_md_anchors at module
    scope, unlike this file's own deferred `import yaml` inside `_load_yaml_safe` — so a
    module-level import here would let a missing/broken dependency take down every step,
    not only the design-doc one. Deferred to the two callers that need it, each inside its
    own _step().
    """
    try:
        import design_doc_check as m
    except ImportError:
        from scripts import design_doc_check as m
    return m


def seed_design_templates(plugin: Path, host: Path) -> list[str]:
    """Seed the design-doc templates once per file; the host copy is the consumer's to edit
    and every later render follows it, so an existing file is never overwritten."""
    src = plugin / DESIGN_TEMPLATES_SOURCE
    if not src.is_dir():
        return [f"  [!] 소스 없음, skip: {DESIGN_TEMPLATES_SOURCE}"]
    ddc = _design_doc_check()  # raises through to _step's own handling on failure
    block = _load_yaml_safe(config_path(host)).get("design_docs")
    rel = (
        block.get("templates")
        if isinstance(block, dict) and block.get("templates")
        else ddc.DESIGN_TEMPLATES_DIR
    )
    dest = host / rel
    try:
        _confine(host, dest).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        return [f"  [!] {rel} 을 만들지 못했습니다({_why(exc)}) — 수동 확인 필요"]
    report: list[str] = []
    for f in sorted(src.glob("*.template.md")):
        target = dest / f.name
        if target.exists():
            report.append(f"  [=] 템플릿 유지: {f.name}")
            continue
        try:
            shutil.copyfile(f, _host_target(host, target))
        except OSError as exc:
            report.append(f"  [!] 템플릿 시딩 실패({_why(exc)}): {f.name}")
            continue
        report.append(f"  [+] 템플릿 시딩: {f.name} → {rel}")
    return report


def _installed(host: Path, plugin: Path, rel: str, source: str) -> bool:
    """Whether the host carries the file this installs, byte for byte.

    Asked as `is_file`, a destination the copy created and could not fill answered yes:
    an empty `precommit-runner.sh` exits 0, an empty policy parses as nothing, and the
    gate that reported itself installed denied no commit. A partial write is the same
    case one step along, which is why this compares rather than measures. A source it
    cannot read is not a confirmation either, and neither is a host directory this may not
    enter: `read_bytes` RAISES there where it answers False for a name that is merely not
    taken, and unanswered it took the run down before its verdict."""
    try:
        want = (plugin / source).read_bytes()
    except OSError:
        return False
    try:
        return (host / rel).read_bytes() == want
    except OSError:
        return False


def design_gitignore_lines(host: Path) -> list[str]:
    """The docx output directory, only when the consumer chose to ignore it."""
    block = _load_yaml_safe(config_path(host)).get("design_docs")
    if not isinstance(block, dict) or block.get("gitignore_output") is not True:
        return []
    out = block.get("output")
    if not out:
        try:
            out = _design_doc_check().DEFAULTS["output"]
        except ImportError:
            # design_doc_check unavailable — skip only the design line; append_gitignore's
            # base GITIGNORE_LINES must still land.
            return []
    out = str(out).strip().rstrip("/")
    return [f"{out}/"] if out else []


def _ignore_rule(line: str) -> tuple[str, bool] | None:
    """What a .gitignore line matches, as (pattern, directories only); None for a blank line.
    A leading `/` is dropped where another slash anchors the rule anyway; on a bare name it
    narrows the rule to the root, so it stays."""
    s = line.rstrip()
    if not s:
        return None
    body = s.rstrip("/")
    if "/" in body.lstrip("/"):
        body = body.lstrip("/")
    return body, s.endswith("/")


def _ignored_already(line: str, rules: set[tuple[str, bool]]) -> bool:
    """A rule without the trailing `/` covers one with it; the reverse misses files."""
    body, dir_only = _ignore_rule(line)
    return (body, False) in rules or (dir_only and (body, True) in rules)


def append_gitignore(host: Path) -> list[str]:
    """Add only the missing lines to .gitignore (without duplicates). Skip if all are present."""
    gi = host / ".gitignore"
    try:
        text, eol = _read_host_text(host, gi)
    except OSError as exc:
        return [f"  [!] .gitignore 수정 거부({_why(exc)}) — 수동 확인 필요"]
    rules = {r for r in map(_ignore_rule, text.splitlines()) if r is not None}
    wanted = [*GITIGNORE_LINES, *design_gitignore_lines(host)]
    missing = [ln for ln in wanted if not _ignored_already(ln, rules)]
    if not missing:
        return ["  [=] .gitignore 이미 최신 (skip)"]
    if text and not text.endswith("\n"):
        text += "\n"
    text += "".join(ln + "\n" for ln in missing)
    _write_host_text(gi, text, eol)
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
        shutil.copyfile(example, _host_target(host, dest))
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


def remove_gitignore_lines(host: Path) -> str:
    """Remove only the lines added by harness-tier from .gitignore (preserve other lines)."""
    gi = host / ".gitignore"
    if not gi.is_file():
        return "  [=] .gitignore 없음 (skip)"
    try:
        text, eol = _read_host_text(host, gi)
    except OSError as exc:
        return f"  [!] .gitignore 수정 거부({_why(exc)}) — 수동 확인 필요"
    targets = set(GITIGNORE_LINES)
    lines = text.splitlines()
    kept = [ln for ln in lines if ln.strip() not in targets]
    removed = len(lines) - len(kept)
    if removed == 0:
        return "  [=] .gitignore 에 harness-tier 라인 없음 (skip)"
    text = "\n".join(kept)
    if text and not text.endswith("\n"):
        text += "\n"
    _write_host_text(gi, text, eol)
    return f"  [-] .gitignore harness-tier 라인 {removed}개 제거"


def remove_claude_md_block(host: Path) -> str:
    """Remove the harness-tier:teams block (markers included) from CLAUDE.md (skip if absent)."""
    cm = host / "CLAUDE.md"
    if not cm.is_file():
        return "  [=] CLAUDE.md 없음 (skip)"
    try:
        text, eol = _read_host_text(host, cm)
    except OSError as exc:
        return f"  [!] CLAUDE.md 수정 거부({_why(exc)}) — 수동 확인 필요"
    lines = text.splitlines(keepends=True)
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
    _write_host_text(cm, "".join(lines), eol)
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
        _host_target(host, dest).parent.mkdir(parents=True, exist_ok=True)
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


def _render_one(
    host: Path, src: Path, dest: Path, subs: dict, label: str = "versioning 렌더"
) -> list[str]:
    if not src.exists():
        return [f"  [!] 템플릿 없음: {src.name} — skip"]
    if dest.exists():
        return [f"  [i] {dest.name} 이미 있어 자동 병합 안 함(커스텀 보존)."]
    text = src.read_text(encoding="utf-8")
    for k, val in subs.items():
        text = text.replace(k, val)
    try:
        _host_target(host, dest).parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    except OSError as exc:
        return [f"  [!] {dest.name} 렌더링 실패({_why(exc)}) — 수동 확인 필요"]
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
        out += _render_one(host, plugin / tmpl, wf_dir / "release.yml", subs)
    else:
        out.append(f"  [!] 알 수 없는 release_tool={tool!r} — release.yml skip")

    # branch-naming
    if (v.get("branch_naming", {}) or {}).get("enable", False):
        out += _render_one(
            host,
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
            host,
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


# The orchestrator's first line, and how a re-render tells its own deploy.yml from the host's.
ORCHESTRATOR_HEADER = "# Generated by /harness-deployments from flow-config.deploy — DO NOT EDIT."


def _orchestrator_is_ours(path: Path) -> bool:
    """Whether `path` is absent or a deploy.yml this renders. Compared as bytes: a file that is
    not UTF-8 is the host's, and a BOM an editor added leaves a generated one generated."""
    if not path.is_file():
        return True
    try:
        head = path.read_bytes()
    except OSError:
        return False
    return head.lstrip(b"\xef\xbb\xbf").startswith(ORCHESTRATOR_HEADER.encode("utf-8"))


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
    wired only if it renders: maven-central+gradle needs `publish` (no default), else
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
        out += _render_one(host, plugin / tmpl, wf_dir / f"deploy-{name}.yml", subs)

    orch_targets = [t for t in (d.get("targets", []) or []) if _deploy_target_wired(t)]
    if orch_targets:
        try:
            orch = _host_target(host, wf_dir / "deploy.yml")
            if not _orchestrator_is_ours(orch):
                out.append(
                    "  [!] .github/workflows/deploy.yml 이 생성본이 아니라 덮어쓰지 않음"
                    " — 직접 병합하거나 지운 뒤 재실행하세요"
                )
            else:
                orch.parent.mkdir(parents=True, exist_ok=True)
                orch.write_text(_orchestrator_yaml(orch_targets, d.get("order")), encoding="utf-8")
                out.append("  [+] .github/workflows/deploy.yml 생성(오케스트레이터, 재생성)")
        except OSError as exc:
            out.append(f"  [!] deploy.yml 렌더링 실패({_why(exc)}) — 수동 확인 필요")
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
        try:
            text, eol = _read_host_text(host, rel)
        except OSError as exc:
            return [f"  [!] release.yml 수정 거부({_why(exc)}) — 수동 확인 필요"]
        d = load_deploy_config(host)
        enabled = bool(d and d.get("enable", False))
        wired = [t for t in (d.get("targets") if d else None) or [] if _deploy_target_wired(t)]
        body = _deploy_call_job(wired) if (enabled and wired) else ""
        if body and not _orchestrator_is_ours(rel.parent / "deploy.yml"):
            # The call job hands `tag` to a reusable workflow; GitHub rejects release.yml whole
            # when the file it calls takes no such input.
            return [
                "  [!] release.yml deploy 배선 보류 — deploy.yml 이 생성본이 아님"
                " (workflow_call 의 tag 입력을 확인한 뒤 직접 배선하세요)"
            ]
        lines = text.splitlines()
        begin_marker = "# __HARNESS_DEPLOY_BEGIN__"
        end_marker = "# __HARNESS_DEPLOY_END__"
        begin = next((i for i, ln in enumerate(lines) if ln.strip().startswith(begin_marker)), None)
        end = next((i for i, ln in enumerate(lines) if ln.strip().startswith(end_marker)), None)
        if begin is None or end is None or end < begin:
            return report_legacy_release_workflow(enabled)
        new_lines = lines[: begin + 1] + ([body] if body else []) + lines[end:]
        _write_host_text(rel, "\n".join(new_lines) + ("\n" if text.endswith("\n") else ""), eol)
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
        ORCHESTRATOR_HEADER,
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


def load_e2e_config(host: Path) -> dict | None:
    """Return the e2e dict from flow-config.yaml (None if absent/unparseable — FAIL-OPEN)."""
    e2e = _load_yaml_safe(config_path(host)).get("e2e")
    return e2e if isinstance(e2e, dict) else None


def load_doc_style_config(host: Path) -> dict | None:
    """Return the doc_style dict from flow-config.yaml (None if absent/unparseable — FAIL-OPEN)."""
    ds = _load_yaml_safe(config_path(host)).get("doc_style")
    return ds if isinstance(ds, dict) else None


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
        _host_target(host, dest).parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(text, encoding="utf-8")
    except OSError as exc:
        return [f"  [!] unit-test 워크플로우 렌더링 실패(수동 확인): {exc}"]
    return [*warnings, "  [+] .github/workflows/unit-test.yml 생성 (unit_test 렌더링)"]


def render_wiki_verify_workflow(host: Path, plugin: Path) -> list[str]:
    """Copy wiki-verify.yml as-is — no enable gate, no tokens.

    Reached from `/wiki-init`'s own step (`--render-wiki-verify`), never from run_setup:
    the workflow verifies a wiki, and at /flow-init time there is none to verify, so the
    question could only be put to a user with nothing to answer it from. By the time
    /wiki-init asks, the graph exists and `--verify` has passed on it — which is also why
    nothing is read from config here. The user's yes IS the gate.

    Idempotent·non-destructive (existing dest → report only), like every render here — so a
    host that took the earlier unconditional render keeps the file it already has.
    """
    return _render_one(
        host, plugin / WIKI_VERIFY_TEMPLATE, host / WIKI_VERIFY_DEST, {}, "wiki-verify 렌더"
    )


def render_srs_verify_workflow(host: Path, plugin: Path) -> list[str]:
    """Copy srs-verify.yml as-is — no enable gate, no tokens.

    Reached from `/flow-init`'s own step (`--render-srs-verify`), never from run_setup: the
    workflow reads docs/srs, and a host without one has nothing to point it at. The user's
    yes IS the gate, which is why nothing is read from config here.

    Idempotent·non-destructive (existing dest → report only), like every render here.
    """
    return _render_one(
        host, plugin / SRS_VERIFY_TEMPLATE, host / SRS_VERIFY_DEST, {}, "srs-verify 렌더"
    )


def render_doc_style_workflow(host: Path, plugin: Path) -> list[str]:
    """Copy doc-style.yml as-is — no tokens, gated by `doc_style.enable`.

    The flag is a RUN switch as well as a render switch, which is what separates it from
    e2e's: `doc_style_check.py` empties its own path list when `enable` is falsy, so a file
    rendered while it was true goes quiet the moment it is turned back off. Nothing has to
    be deleted to stop it.

    Gated at all because this workflow holds the only verdict the prose layer ever gives —
    the commit-time stage warns and never blocks. That is the reason to ASK rather than to
    assume: silence here is not a check that stayed green, it is a rule nothing enforces,
    and /flow-init states that where it collects the flag.

    Idempotent·non-destructive (existing dest → report only), like every render here.
    """
    ds = load_doc_style_config(host)
    if ds is None:
        return ["  [=] doc_style 미설정 — 워크플로 skip"]
    if not ds.get("enable"):
        return ["  [=] doc_style.enable=false — 워크플로 미설치"]
    return _render_one(
        host, plugin / DOC_STYLE_TEMPLATE, host / DOC_STYLE_DEST, {}, "doc-style 렌더"
    )


def render_e2e_workflow(host: Path, plugin: Path) -> list[str]:
    """Copy e2e.yml as-is — no tokens, gated by one boolean.

    The boolean is a RENDER switch, not a run switch — unlike doc_style's, which its own
    script also reads. Setting it back to false leaves an
    already-rendered file running; deleting .github/workflows/e2e.yml is what stops it. That
    asymmetry is why the report below names the scaffold rather than the flag.

    Idempotent·non-destructive (existing dest → report only), like every render here.
    """
    cfg = load_e2e_config(host)
    if cfg is None:
        return ["  [=] e2e 미설정 — 워크플로 skip"]
    if not cfg.get("enable"):
        return ["  [=] e2e.enable=false — 워크플로 미설치"]
    out = _render_one(host, plugin / E2E_TEMPLATE, host / E2E_DEST, {}, "e2e 렌더")
    # Delivery is a human trigger (D8 = the scaffold owns playwright.config.*), so the one
    # state the boolean cannot prevent is "workflow rendered, no suite anywhere". The
    # template's detect step keeps that green; this line is how it stops being permanent.
    # Root plus two levels down, matching the workflow's own `find -maxdepth 3`
    # (github/e2e.workflow.example.yml) — a config the workflow would find but this glob
    # missed prints a stale pointer at the exact monorepo path EDIT 4's own example gives
    # (apps/web/playwright.config.ts).
    config_globs = ("playwright.config.*", "*/playwright.config.*", "*/*/playwright.config.*")
    if not any(any(host.glob(pattern)) for pattern in config_globs):
        out.append("  [i] playwright.config.* 없음 — /playwright-scaffold 로 먼저 만드세요.")
    return out


def load_harnesses(host: Path) -> tuple[list[str], list[str], bool]:
    """The harnesses this host installs the gate into. Claude is always one: the plugin is a
    Claude Code plugin first, and an absent `harnesses` key is every host installed before
    Codex existed here — the same host, unchanged.

    The third element is `reliable`: False only when the raw `harnesses:` value itself could
    not be read as a list, so `names` is a guess rather than the host's real configured set.
    An unrecognized or unsupported single entry does not touch it — the rest of the list is
    still real, and `names` reflects it correctly; only the caller-visible `[!]`/`[=]` line
    is a guess-free fact about that one entry. Reporting this explicitly, rather than making
    a caller re-derive it by scanning the returned lines for `[!]`, keeps an unrelated `[!]`
    (an unknown name in an otherwise valid list) from reading as "the list itself is unknown."
    """
    cfg = _load_yaml_safe(config_path(host))
    raw = cfg.get("harnesses")
    names = ["claude"]
    lines: list[str] = []
    reliable = True
    if raw is None:
        entries: list = []
    elif isinstance(raw, list):
        entries = raw
    else:
        # A present-but-wrong-shaped value (a bare string, a mapping, …) is a typo, not the
        # same thing as an absent key — silently reading it as "no harnesses configured"
        # would tell a host who wrote `harnesses: codex` that Claude-only was ever a choice
        # they made, instead of the mistake it is.
        lines.append(
            "  [!] harnesses: 목록이어야 합니다(예: [claude, codex])"
            " — 무시하고 claude 만 사용합니다"
        )
        entries = []
        reliable = False
    for name in entries:
        if name == "claude" or name in names:
            continue
        if name in harness.SUPPORTED:
            names.append(name)
        elif name in harness.KNOWN:
            lines.append(f"  [=] harnesses: {name} 는 아직 지원하지 않습니다 (skip)")
        else:
            lines.append(f"  [!] harnesses: 알 수 없는 이름 '{name}' (skip)")
    return names, lines, reliable


def register_gates(host: Path, harnesses: list[str]) -> list[str]:
    """Register the commit gate in every enabled harness. Claude's own registration is
    settings.json's `register_gate`; every other enabled name runs through the shared
    registry (`harness.installer`) — its own hook file, plus any read-only warnings it wants
    relayed (Codex: whether the project is Codex-trusted, and that /hooks approval is still
    needed)."""
    out = [register_gate(host)]
    for name in harnesses:
        if name == "claude":
            continue
        mod = harness.installer(name)
        out.append(mod.register(host))
        if name == "codex":
            out.extend(mod.trust_notes(host))
    return out


def codex_leftovers(host: Path, harnesses: list[str]) -> list[str]:
    """A host that dropped codex from `harnesses` keeps what it installed — reported, never
    removed, since the list alone does not say the user wants the Codex gate gone."""
    if "codex" in harnesses:
        return []
    left = []
    try:
        # The marker text, not `hook_remains`: that answers "may remain" for a file it cannot
        # parse, and a Claude-only host's own broken hooks.json is not ours to report.
        hooks = (host / ".codex" / "hooks.json").read_text(encoding="utf-8")
        if all(word in hooks for word in harness.installer("codex").MARKER):
            left.append(".codex/hooks.json 게이트 훅")
    except Exception:  # noqa: BLE001 — a note, never a reason to lose the step
        pass
    try:
        agents = host / "AGENTS.md"
        if agents.is_file() and _codex_instructions()._spans(agents.read_bytes().decode("utf-8")):
            left.append("AGENTS.md 지침 블록")
    except Exception:  # noqa: BLE001 — same
        pass
    if not left:
        return []
    return [
        f"  [i] harnesses 에 codex 가 없지만 {' · '.join(left)} 이(가) 남아 있습니다 — 지우려면"
        " /flow-uninstall, 계속 쓰려면 harnesses 에 codex 를 다시 추가하세요"
    ]


def _gate_problems(host: Path, plugin: Path, harnesses=("claude",)) -> list[str]:
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
        Path(rel).name
        for rel, source in gate_files(harnesses)
        if not _installed(host, plugin, rel, source)
    ]
    if missing:
        problems.append(
            "커밋 게이트가 쓰는 파일이 호스트에 없거나 손상됐습니다("
            + ", ".join(missing)
            + ") — 훅이 등록되어 있어도 아무 커밋도 막지 못합니다."
            " 위 [!] 를 해결한 뒤 /flow-init 를 다시 실행하세요."
        )
    problems.extend(_claude.problems(host))
    if "codex" in harnesses:
        problems.extend(harness.installer("codex").problems(host))
    return problems


def _codex_instructions():
    """The Codex AGENTS.md renderer, resolved when a step runs so a packaging failure costs
    only that step."""
    try:
        from harness.codex import instructions
    except ImportError:
        from scripts.harness.codex import instructions
    return instructions


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
    except Exception as exc:  # noqa: BLE001 — the verdict is what this exists to reach
        # Every exception, not the two a host's filesystem raises: a hand-edited config whose
        # shape is wrong raises AttributeError deep in a step, and narrowing to OSError lets
        # that one escape and take the verdict line with it — the single line saying whether
        # the gate is on. A caller reads the exit code and reports a gate that never failed.
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
    try:
        names, cfg_lines, harnesses_readable = load_harnesses(host)
    except Exception as exc:  # noqa: BLE001 — a closed `.claude/` must still reach the verdict
        names = ["claude"]
        cfg_lines = [f"  [!] harnesses 를 읽지 못했습니다({_why(exc)}) — claude 만 사용합니다"]
        harnesses_readable = False
    # `codex_leftovers` reports "codex is not in harnesses" as though that were known — but
    # `harnesses_readable=False` means it is not: the `except` above, or `load_harnesses`'s
    # own not-a-list guard, both leave `names == ["claude"]` while the real config may still
    # list codex. Telling that host to /flow-uninstall its own configured gate is the wrong
    # direction. Read from the explicit flag rather than scanning `cfg_lines` for `[!]` —
    # an unrecognized single entry in an otherwise valid list also prints `[!]` there, and
    # that case leaves `names` fully trustworthy.
    print(f"flow-init 기계적 셋업 — host={host}")
    finished = [
        _step("[복사]", lambda: copy_artifacts(plugin, host, names)),
        _step(
            "[커밋 게이트]",
            lambda: (
                cfg_lines
                + register_gates(host, names)
                + (codex_leftovers(host, names) if harnesses_readable else [])
            ),
        ),
        _step("[규칙 정리]", lambda: [remove_rules(host)]),
        _step("[마켓 자동 업데이트]", lambda: [register_marketplace(host)]),
        _step("[pre-commit 점검]", lambda: check_precommit(plugin, host)),
        _step("[설계 산출물 템플릿]", lambda: seed_design_templates(plugin, host)),
        _step("[gitignore]", lambda: append_gitignore(host)),
        _step("[계약 테스트 워크플로우]", lambda: render_workflow(host, plugin)),
        _step("[버저닝 워크플로우]", lambda: render_versioning_workflows(host, plugin)),
        _step("[유닛 테스트 워크플로우]", lambda: render_unit_test_workflow(host, plugin)),
        _step("[문체 검증 워크플로우]", lambda: render_doc_style_workflow(host, plugin)),
        _step("[E2E 워크플로우]", lambda: render_e2e_workflow(host, plugin)),
        _step("[배포 워크플로우]", lambda: render_deploy_workflows(host, plugin)),
        _step("[config 슬롯 점검]", lambda: report_missing_config_slots(host, plugin)),
    ]
    if "codex" in names:
        finished.append(_step("[Codex 지침 렌더]", lambda: _codex_instructions().render(host)))
    problems = _gate_problems(host, plugin, names)
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


def _codex_hook_status(host: Path) -> str:
    """Where the Codex gate hook stands in `.codex/hooks.json`: "gone", "left", "unconfirmed"
    (the check could not run on a file that may hold the hook), or "foreign" (a file that
    does not parse, or parses into a shape other than a `PreToolUse` list, and carries no gate
    marker — the host's own, which harness-tier never wrote to).

    Resolved here rather than at import time, so a Codex packaging failure (the module
    cannot be imported) does not read as proof the hook is gone — but "cannot check" is not
    "gone" either, so it answers "unconfirmed", and only when there is a file that could be
    holding one: a host with no `.codex/hooks.json` at all had nothing to register.
    """
    path = host / ".codex" / "hooks.json"
    try:
        if not path.exists():
            return "gone"
        mod = harness.installer("codex")
        data, _err = mod.load_json_object(path, ".codex/hooks.json")
        if data is not None:
            if not mod.hook_remains(host):
                return "gone"
            hooks = data.get("hooks", {})
            if isinstance(hooks, dict) and isinstance(hooks.get("PreToolUse", []), list):
                return "left"
        raw = path.read_bytes().decode("utf-8", "replace")
        return "unconfirmed" if all(word in raw for word in mod.MARKER) else "foreign"
    except Exception:  # noqa: BLE001 — a check that could not run is not a "no", see above
        return "unconfirmed"


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
        # Always — regardless of what flow-config.yaml's `harnesses` currently says. A host
        # that dropped codex from the list after installing it still has the hook file, and
        # config is not asked here for the same reason `remove_harness_dir` below is not:
        # uninstall means gone, not "gone unless the config forgot to mention it". Resolved
        # INSIDE the step (not once above) so a Codex packaging failure costs only this one
        # step — not, uncaught, every host's Claude gate removal along with it.
        _step("[Codex 게이트 해제]", lambda: [harness.installer("codex").unregister(host)]),
        _step("[마켓 등록 해제]", lambda: [unregister_marketplace(host)]),
        _step("[gitignore 정리]", lambda: [remove_gitignore_lines(host)]),
        _step("[CLAUDE.md teams 블록 제거]", lambda: [remove_claude_md_block(host)]),
        # Always, like the gate step above; only a block whose BEGIN line carries our marker
        # prefix and closes on our END line is cut.
        _step("[Codex 지침 블록 제거]", lambda: [_codex_instructions().remove(host)]),
        _step("[harness-tier 디렉터리 삭제]", lambda: [remove_harness_dir(host)]),
        _step("[규칙 삭제]", lambda: [remove_rules(host)]),
    ]
    print("[남는 항목 — 수동 처리 안내]")
    print("  - .pre-commit-config.yaml 의 teams-notify-push 훅/정적분석 훅은 자동 제거하지")
    print("    않습니다(주석·팀 커스텀 보존). 필요 시 직접 제거하세요.")
    print("  - .github/workflows/api-contract.yml 은 자동 삭제하지 않습니다(팀 커스텀 보존).")
    print("    계약 테스트를 끄려면 직접 제거하세요.")
    print("  - .github/workflows/wiki-verify.yml·doc-style.yml·srs-verify.yml 은 방금 삭제된")
    print("    .claude/harness-tier/scripts/ 의 스크립트를 실행합니다. 없는 스크립트를 가드가")
    print("    보고 exit 0 하므로 CI 가 빨개지지는 않지만 더는 아무것도 검증하지 못하니 함께")
    print("    제거하세요. 같은 경로를 쓰는 release 워크플로우는 렌더한 종류에 달렸습니다 —")
    print("    python-semantic-release 는 가드가 있고, gitversion·jreleaser 는 가드가 없어")
    print("    릴리스 브랜치 push 에서 실패합니다.")
    print("  - 설치했던 git 훅 비활성화:")
    print("      pre-commit uninstall --hook-type pre-commit --hook-type commit-msg \\")
    print("        --hook-type pre-push")
    print("  - .claude/harness-tier/ 의 git 추적 파일 삭제는 커밋해야 반영됩니다.")
    # Named separately, not one shared line: settings.json and .codex/hooks.json are
    # different files a different step failed to clear, and a host whose Codex hook is the
    # only thing left must not be sent to settings.json, which holds nothing by then.
    claude_left = _gate_hook_remains(host)
    codex_state = _codex_hook_status(host)
    if codex_state == "foreign":
        print(
            "  [i] .codex/hooks.json 을 해석하지 못했지만 harness-tier 게이트 표식이 없어"
            " 건드리지 않았습니다."
        )
    if claude_left or codex_state in ("left", "unconfirmed"):
        if claude_left:
            print(
                "커밋 게이트 훅이 settings.json 에 남았습니다 — 방금 삭제된 스크립트를"
                " 가리키므로 직접 지우세요."
            )
        if codex_state == "left":
            print(
                "Codex 커밋 게이트 훅이 .codex/hooks.json 에 남았습니다 — 방금 삭제된"
                " 스크립트를 가리키므로 직접 지우세요."
            )
        if codex_state == "unconfirmed":
            print(
                ".codex/hooks.json 을 해석하지 못해 Codex 커밋 게이트 훅이 지워졌는지 확인하지"
                " 못했습니다 — 남았다면 방금 삭제된 스크립트를 가리키므로 직접 확인하세요."
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
    parser.add_argument(
        "--render-wiki-verify",
        action="store_true",
        help="wiki 검증 워크플로우만 렌더(/wiki-init 이 사용자 동의를 받은 뒤 호출).",
    )
    parser.add_argument(
        "--render-srs-verify",
        action="store_true",
        help="SRS 검증 워크플로우만 렌더(/flow-init 이 사용자 동의를 받은 뒤 호출).",
    )
    args = parser.parse_args()
    host = host_root()
    if args.render_deploy:
        for line in render_deploy_workflows(host, plugin_root()):
            print(line)
        return
    if args.render_wiki_verify:
        for line in render_wiki_verify_workflow(host, plugin_root()):
            print(line)
        return
    if args.render_srs_verify:
        for line in render_srs_verify_workflow(host, plugin_root()):
            print(line)
        return
    if args.uninstall:
        if not run_uninstall(host):
            raise SystemExit(1)
    elif not run_setup(host, plugin_root()):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
