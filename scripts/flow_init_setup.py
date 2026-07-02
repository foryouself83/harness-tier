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
import json
import shutil
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

EXAMPLE_CONFIG = "flow-config.example.yaml"  # plugin SOURCE (basis for config-slot diff)

# Gate scripts to copy to .claude/harness-tier/scripts/ (SOURCE → HOST). _harness_paths.py is a
# shared module the copied scripts import, so it must travel with them (sibling import holds in the
# single-file-copy environment). The policy file flow-tiers.yaml is copied separately to config/
# (copy_artifacts).
COPY_FILES = [
    "scripts/_harness_paths.py",
    "scripts/precommit-runner.sh",
    "scripts/flow_gate_check.py",
    "scripts/teams_alert.py",
    "scripts/notify-push.sh",
    "scripts/check-deps.sh",
    "scripts/check-token-write.sh",
    "scripts/finalize_prerelease.py",
]

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
GATE_MARKER = "precommit-runner.sh"  # path-independent match
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
    dest_dir.mkdir(parents=True, exist_ok=True)
    report: list[str] = []
    for rel in COPY_FILES:
        src = plugin / rel
        if not src.is_file():
            report.append(f"  [!] 소스 없음, skip: {rel}")
            continue
        shutil.copyfile(src, dest_dir / Path(rel).name)
        report.append(f"  [+] 복사: {Path(rel).name}")
    # The policy file goes to config/ (a host-owned dir, but this file alone is plugin-owned·SSOT).
    cfg_dir = host / CONFIG_DIR
    cfg_dir.mkdir(parents=True, exist_ok=True)
    tiers_src = plugin / TIERS_FILENAME
    if tiers_src.is_file():
        shutil.copyfile(tiers_src, cfg_dir / TIERS_FILENAME)
        report.append(f"  [+] 복사: {TIERS_FILENAME} → config/")
    else:
        report.append(f"  [!] 소스 없음, skip: {TIERS_FILENAME}")
    return report


def _load_settings(host: Path) -> tuple[Path, dict | None, str | None]:
    """Return the settings.json path·parse result. On parse failure, (path, None, error message)."""
    settings = host / ".claude" / "settings.json"
    settings.parent.mkdir(parents=True, exist_ok=True)
    if not settings.is_file():
        return settings, {}, None
    try:
        return settings, json.loads(settings.read_text(encoding="utf-8")) or {}, None
    except json.JSONDecodeError:
        return settings, None, "  [!] settings.json 파싱 실패 — 수동 확인 필요"


def _write_json(path: Path, data: dict) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def register_gate(host: Path) -> str:
    """Register the commit gate in .claude/settings.json. Skip if already present; if the registered
    command/statusMessage differs from the current value, fix it up (for plugin updates)."""
    settings, data, err = _load_settings(host)
    if data is None:
        return err or "  [!] settings.json 파싱 실패"
    pre = data.setdefault("hooks", {}).setdefault("PreToolUse", [])
    if not isinstance(pre, list):
        return "  [!] hooks.PreToolUse 형식 비정상 — 게이트 미등록(수동 확인)"
    gate_hooks = [
        hook
        for entry in pre
        for hook in (entry or {}).get("hooks", []) or []
        if GATE_MARKER in (hook.get("command") or "")
    ]
    if not gate_hooks:
        pre.append(GATE_ENTRY)
        _write_json(settings, data)
        return "  [+] 커밋 게이트 등록 (settings.json)"
    # Already registered — a plugin update may have changed command/statusMessage, so fix up
    # **every** entry that diverges from the current value (fixing only the first would leave a
    # duplicate stale entry pointing at a deleted path forever).
    stale = [
        h
        for h in gate_hooks
        if h.get("command") != GATE_COMMAND or h.get("statusMessage") != GATE_STATUS
    ]
    if not stale:
        return "  [=] 커밋 게이트 이미 등록됨 (skip)"
    for hook in stale:
        hook["command"] = GATE_COMMAND
        hook["statusMessage"] = GATE_STATUS
    _write_json(settings, data)
    return f"  [+] 커밋 게이트 보정 (settings.json, {len(stale)}건)"


def register_marketplace(host: Path) -> str:
    """Register the harness-tier marketplace in .claude/settings.json extraKnownMarketplaces with
    autoUpdate=true (add if absent, fix only autoUpdate if present, skip if already true).
    Source is preserved."""
    settings, data, err = _load_settings(host)
    if data is None:
        return err or "  [!] settings.json 파싱 실패"
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
    _write_json(settings, data)
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


def _entry_has_gate(entry: dict) -> bool:
    """True if a hook command in the PreToolUse entry contains the gate marker."""
    hooks = (entry or {}).get("hooks", []) or []
    return any(GATE_MARKER in (h.get("command") or "") for h in hooks)


def unregister_gate(host: Path) -> str:
    """Remove the commit gate hook (entry) from settings.json (skip if absent)."""
    settings, data, err = _load_settings(host)
    if data is None:
        return err or "  [!] settings.json 파싱 실패"
    pre = (data.get("hooks") or {}).get("PreToolUse")
    if not isinstance(pre, list):
        return "  [=] 게이트 훅 없음 (skip)"
    kept = [e for e in pre if not _entry_has_gate(e)]
    if len(kept) == len(pre):
        return "  [=] 게이트 훅 없음 (skip)"
    data["hooks"]["PreToolUse"] = kept
    _write_json(settings, data)
    return "  [-] 커밋 게이트 해제 (settings.json)"


def unregister_marketplace(host: Path) -> str:
    """Remove the harness-tier marketplace from settings.json (skip if absent)."""
    settings, data, err = _load_settings(host)
    if data is None:
        return err or "  [!] settings.json 파싱 실패"
    mkts = data.get("extraKnownMarketplaces")
    if not isinstance(mkts, dict) or MARKETPLACE_NAME not in mkts:
        return "  [=] harness-tier 마켓 등록 없음 (skip)"
    del mkts[MARKETPLACE_NAME]
    _write_json(settings, data)
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


_RELEASE_TEMPLATES = {
    "python-semantic-release": "github/release.python-semantic-release.workflow.example.yml",
    "semantic-release": "github/release.semantic-release.workflow.example.yml",
}


def _render_one(src: Path, dest: Path, subs: dict) -> list[str]:
    if not src.exists():
        return [f"  [!] 템플릿 없음: {src.name} — skip"]
    if dest.exists():
        return [f"  [i] {dest.name} 이미 있어 자동 병합 안 함(커스텀 보존)."]
    text = src.read_text(encoding="utf-8")
    for k, val in subs.items():
        text = text.replace(k, val)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(text, encoding="utf-8")
    return [f"  [+] .github/workflows/{dest.name} 생성 (versioning 렌더)"]


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

    # release (per tool)
    tool = str(v.get("release_tool", ""))
    tmpl = _RELEASE_TEMPLATES.get(tool)
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
    return out


def run_setup(host: Path, plugin: Path) -> None:
    print(f"flow-init 기계적 셋업 — host={host}")
    print("[복사]")
    for line in copy_artifacts(plugin, host):
        print(line)
    print("[커밋 게이트]")
    print(register_gate(host))
    print("[마켓 자동 업데이트]")
    print(register_marketplace(host))
    print("[pre-commit 점검]")
    for line in check_precommit(plugin, host):
        print(line)
    print("[gitignore]")
    for line in append_gitignore(host):
        print(line)
    print("[계약 테스트 워크플로우]")
    for line in render_workflow(host, plugin):
        print(line)
    print("[버저닝 워크플로우]")
    for line in render_versioning_workflows(host, plugin):
        print(line)
    print("[config 슬롯 점검]")
    for line in report_missing_config_slots(host, plugin):
        print(line)
    print("기계적 셋업 완료.")


def run_uninstall(host: Path) -> None:
    print(f"harness-tier 정리(uninstall) — host={host}")
    print("[커밋 게이트 해제]")
    print(unregister_gate(host))
    print("[마켓 등록 해제]")
    print(unregister_marketplace(host))
    print("[gitignore 정리]")
    print(remove_gitignore_lines(host))
    print("[CLAUDE.md teams 블록 제거]")
    print(remove_claude_md_block(host))
    print("[harness-tier 디렉터리 삭제]")
    print(remove_harness_dir(host))
    print("[남는 항목 — 수동 처리 안내]")
    print("  - .pre-commit-config.yaml 의 teams-notify-push 훅/정적분석 훅은 자동 제거하지")
    print("    않습니다(주석·팀 커스텀 보존). 필요 시 직접 제거하세요.")
    print("  - .github/workflows/api-contract.yml 은 자동 삭제하지 않습니다(팀 커스텀 보존).")
    print("    계약 테스트를 끄려면 직접 제거하세요.")
    print("  - 설치했던 git 훅 비활성화:")
    print("      pre-commit uninstall --hook-type pre-commit --hook-type commit-msg \\")
    print("        --hook-type pre-push")
    print("  - .claude/harness-tier/ 의 git 추적 파일 삭제는 커밋해야 반영됩니다.")
    print("정리 완료.")


def main() -> None:
    force_utf8_io()
    parser = argparse.ArgumentParser(description="flow-init 기계적 셋업 / --uninstall 정리")
    parser.add_argument(
        "--uninstall",
        action="store_true",
        help="호스트에서 harness-tier 배선을 제거(setup 의 역연산)",
    )
    args = parser.parse_args()
    host = host_root()
    if args.uninstall:
        run_uninstall(host)
    else:
        run_setup(host, plugin_root())


if __name__ == "__main__":
    main()
