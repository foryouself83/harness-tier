"""flow-config-based gate check helpers.

The host repository path is accessed only via the CLAUDE_PROJECT_DIR environment
variable, and internal errors do not block the gate (fail-open).
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Host-root resolution, encoding defenses, and gate contract constants (blocking exit
# code·runtime gate keys·tier labels) come from the shared SSOT (_harness_paths)
# (no duplicate definitions — rule-dry-constants).
# flow_gate_check is copied to the host and run directly (sibling import) or imported as a package
# in tests — see the compatibility idiom in the _harness_paths module docstring.
try:
    from _harness_paths import (
        BLOCK_EXIT_CODE,
        CONFIG_DIR,
        RELEASE_TIER,
        RUNTIME_GATES,
        STAGING_TIER,
        TIERS_FILENAME,
        config_path,
        flow_dir,
        force_utf8_io,
        host_root,
    )
except ImportError:
    from scripts._harness_paths import (
        BLOCK_EXIT_CODE,
        CONFIG_DIR,
        RELEASE_TIER,
        RUNTIME_GATES,
        STAGING_TIER,
        TIERS_FILENAME,
        config_path,
        flow_dir,
        force_utf8_io,
        host_root,
    )


def load_lifecycle_branches(config_path: Path) -> dict[str, str]:
    """Read the branches section of flow-config.yaml and return a {branch name: tier} mapping.

    - staging key → "staging" tier
    - production key → "release" tier
    - Returns {} if the file is missing or on parse error (fail-open)
    """
    if not config_path.is_file():
        return {}
    try:
        import yaml

        data = yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return {}
    branches = data.get("branches") or {}
    out: dict[str, str] = {}
    if staging := branches.get("staging"):
        out[str(staging)] = STAGING_TIER
    if production := branches.get("production"):
        out[str(production)] = RELEASE_TIER
    return out


def required_gates(tiers_path: Path, tier: str) -> list[str] | None:
    """Return the gates list for a given tier from flow-tiers.yaml.

    - Returns None if the tier does not exist
    - Returns None if the file is missing or on parse error (fail-open)
    """
    if not tiers_path.is_file():
        return None
    try:
        import yaml

        data = yaml.safe_load(tiers_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return None
    node = (data.get("tiers") or {}).get(tier)
    return list(node.get("gates", [])) if node else None


def policy_parseable(tiers_path: Path) -> bool:
    """Whether flow-tiers.yaml loads correctly and has a tiers section (policy reliability).

    The unclassified fail-closed block must be applied only when the gate is *working normally*
    (Invariant #1: a broken/absent policy must not permanently block commits). A missing file·parse
    failure·empty tiers are all treated as "unreliable" → False — falling back to FAIL-OPEN
    instead of blocking.
    """
    if not tiers_path.is_file():
        return False
    try:
        import yaml

        data = yaml.safe_load(tiers_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return False
    return bool(data.get("tiers"))


def config_intact(config_path: Path) -> bool:
    """Whether flow-config.yaml is absent (normal) or loads correctly.

    Absence is normal (config may not exist during feature work·before flow-init) → True.
    If it exists but fails to parse, that is an internal error → False: since lifecycle
    (staging/release) determination is disabled, blocking is withheld so promotion commits
    are not wrongly blocked as "unclassified".
    """
    if not config_path.is_file():
        return True
    try:
        import yaml

        yaml.safe_load(config_path.read_text(encoding="utf-8"))
    except Exception:
        return False
    return True


def missing_gates(flow_dir: Path, gates: list[str]) -> list[str]:
    """Gates without a <gate>.done file, excluding RUNTIME_GATES (gates the hook runs directly)."""
    return [g for g in gates if g not in RUNTIME_GATES and not (flow_dir / f"{g}.done").is_file()]


def _current_branch(root: Path) -> str | None:
    """Return the current git branch name. None on failure."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=root,
            capture_output=True,
            text=True,
            check=True,
        )
        return out.stdout.strip()
    except Exception:
        return None


def _resolve_context_tier(root: Path, flow: Path, current: str | None) -> tuple[str | None, bool]:
    """Resolve the tier label to apply from the current branch/.flow tier marker.

    Returns ``(tier, is_lifecycle)``:
    - A lifecycle branch (stage/main) → that tier and ``True``.
    - A ``.flow/tier`` marker present and applicable to the current branch → that tier, ``False``.
    - Unclassified (no marker)·a marker for a different branch → ``(None, False)``.

    The single tier-resolution point shared by the stage-1 evidence check (main) and the
    stage-2 module pre-check (module_commands) (no duplicate definitions — rule-dry-constants).
    """
    lifecycle = load_lifecycle_branches(config_path(root)).get(current or "")
    if lifecycle:
        return lifecycle, True
    tier_file = flow / "tier"
    if not tier_file.is_file():
        return None, False
    tier, _, branch = tier_file.read_text(encoding="utf-8").strip().partition(":")
    tier, branch = tier.strip().lower(), branch.strip()
    if branch and current is not None and current != branch:
        return None, False
    return tier, False


def tiers_path(root: Path) -> Path:
    """Resolve the location of flow-tiers.yaml (the plugin policy).

    The policy file is deployed to the host alongside the gate scripts, so it is searched in order:
    1. ``CLAUDE_PLUGIN_ROOT/flow-tiers.yaml`` — when run directly as a plugin hook.
    2. ``flow-tiers.yaml`` in the config directory — when copied to
       ``.claude/harness-tier/config/`` (the gate script is in the sibling ``scripts/``,
       so it points at that sibling directory's config/ relative to __file__ — unaffected
       by host_root() instability).
    3. ``flow-tiers.yaml`` at the host root — fallback (development/testing).
    """
    plugin = os.environ.get("CLAUDE_PLUGIN_ROOT")
    if plugin and (p := Path(plugin) / TIERS_FILENAME).is_file():
        return p
    config_copy = Path(__file__).resolve().parent.parent / Path(CONFIG_DIR).name / TIERS_FILENAME
    if config_copy.is_file():
        return config_copy
    return root / TIERS_FILENAME


def _changed_files(root: Path) -> list[str]:
    """List of changed files to be committed. staged (--cached) first, and if empty falls back to
    the working tree (HEAD diff) (the `git commit -a` case). git failure/no changes → []
    (FAIL-OPEN)."""
    for args in (["diff", "--cached", "--name-only"], ["diff", "HEAD", "--name-only"]):
        try:
            out = subprocess.run(
                ["git", *args],
                cwd=root,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
        except Exception:
            continue
        files = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
        if files:
            return files
    return []


def _match_modules(changed: list[str], modules: list[dict]) -> tuple[list[dict], list[str]]:
    """Prefix-match changed files against modules[].path.

    Returns ``(matched modules (order preserved·deduped), uncovered files)``. An empty path("")
    matches everything (single-stack single-module). A file is attributed to the first matching
    module; if it matches no path it is uncovered.
    """
    matched: list[dict] = []
    seen: set[str] = set()
    uncovered: list[str] = []
    for f in changed:
        hit: dict | None = None
        for mod in modules:
            path = str(mod.get("path") or "")
            if path == "" or f.startswith(path):
                hit = mod
                break
        if hit is None:
            uncovered.append(f)
            continue
        key = str(hit.get("name") or hit.get("path") or "")
        if key not in seen:
            seen.add(key)
            matched.append(hit)
    return matched, uncovered


def _check_cmds(mod: dict, *, security: bool) -> list[str]:
    """Module checks commands. security=True → only the security key; False → all except security
    (config authoring order preserved, empty commands skipped)."""
    checks = mod.get("checks") or {}
    if security:
        cmd = checks.get("security")
        return [str(cmd)] if cmd else []
    return [str(v) for k, v in checks.items() if k != "security" and v]


def module_commands(
    root: Path, tier: str | None, gates: list[str] | None
) -> tuple[list[str], list[str]]:
    """Build module pre-check commands only for the items enabled in the gates list (tiers.yaml
    gates is the SSOT — not hardcoded by tier label. Removing it from gates turns that check off).

    - docs/None tier, or empty gates → ([], [])
    - "precommit" in gates → the changed modules' non-security checks (+ uncovered report)
    - "security-scan" in gates → all modules' security (on promotion)
    config parse failure·absent modules → ([], []) (FAIL-OPEN — Invariant #1)."""
    if tier is None or tier == "docs" or not gates:
        return [], []
    cfg = config_path(root)
    if not cfg.is_file():
        return [], []
    try:
        import yaml

        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
    except Exception:
        return [], []
    modules = data.get("modules") or []
    if not modules:
        return [], []
    cmds: list[str] = []
    report: list[str] = []
    if "precommit" in gates:
        matched, uncovered = _match_modules(_changed_files(root), modules)
        for mod in matched:
            cmds += _check_cmds(mod, security=False)
        if uncovered:
            report.append(
                "다음 파일은 모듈 미커버라 사전검사 생략 — 새 모듈이면 "
                "flow-config.modules[] 에 등록하세요:"
            )
            report += [f"  - {f}" for f in uncovered]
    if "security-scan" in gates:
        for mod in modules:
            cmds += _check_cmds(mod, security=True)
    return cmds, report


def main() -> None:
    """flow gate check entry point. exit(BLOCK_EXIT_CODE) if a gate is unmet, exit(0) if passed."""
    force_utf8_io()
    root = host_root()
    # All host-side harness-tier artifacts are collected under .claude/harness-tier/
    # (config·evidence·copied scripts). Path assembly is unified via shared helpers.
    flow = flow_dir(root)
    tiers = tiers_path(root)
    current = _current_branch(root)

    tier, is_lifecycle = _resolve_context_tier(root, flow, current)
    if tier is None:
        # Split unresolved tier into two causes (the same None is interpreted oppositely):
        #  - Policy (flow-tiers.yaml)·config (flow-config.yaml) working normally + the tier marker
        #    file itself absent = flow not entered (unclassified) → FAIL-CLOSED block. Prevents a
        #    commit that bypassed flow from skipping the gate entirely. If enforcement is
        #    unnecessary the user can remove the gate itself with /flow-uninstall (we don't put an
        #    escape hatch in the code — if we did, the model could use that bypass on its own).
        #  - Policy absent/parse failure, config parse failure (uncertain
        #    install/environment·internal error), or a marker for a different branch (branch-bound
        #    stale) → FAIL-OPEN. Preserves Invariant #1 (a broken/absent gate must not permanently
        #    block commits)·branch-bound (a stale marker must not block unrelated branch work). The
        #    criterion is "works reliably", not "file exists".
        if (
            policy_parseable(tiers)
            and config_intact(config_path(root))
            and not (flow / "tier").is_file()
        ):
            print(
                "flow 미진입: 분류되지 않은 커밋입니다. /flow 로 작업을 분류한 뒤 "
                "커밋하세요(강제가 불필요하면 /flow-uninstall)."
            )
            sys.exit(BLOCK_EXIT_CODE)
        sys.exit(0)
    gates = required_gates(tiers, tier)
    if gates is None:  # unknown tier → FAIL-OPEN
        sys.exit(0)
    miss = missing_gates(flow, gates)
    if miss:
        if is_lifecycle:
            print(f"{tier} 게이트 (브랜치 '{current}'): {miss} 증거가 필요합니다.")
        else:
            print(f"flow 게이트: '{tier}' 티어는 {miss} 증거가 필요합니다.")
        sys.exit(BLOCK_EXIT_CODE)
    sys.exit(0)


def module_commands_output() -> None:
    """Emit the module pre-check commands enabled by the current tier's gates to stdout
    (line by line), and the uncovered report to stderr.

    If gates has precommit → changed modules' non-security; if security-scan → + all modules'
    security (the tiers.yaml gates list is the SSOT — removing it here turns that check off).
    Determination failure → empty output (FAIL-OPEN). precommit-runner.sh runs the stdout commands
    and exposes the stderr report to the user as-is."""
    force_utf8_io()
    root = host_root()
    try:
        tier, _ = _resolve_context_tier(root, flow_dir(root), _current_branch(root))
        gates = required_gates(tiers_path(root), tier) if tier else None
    except Exception:
        return  # FAIL-OPEN
    cmds, report = module_commands(root, tier, gates)
    for line in report:
        print(line, file=sys.stderr)
    for cmd in cmds:
        print(cmd)


if __name__ == "__main__":
    try:
        if "--module-commands" in sys.argv:
            module_commands_output()
        else:
            main()
    except SystemExit:
        raise
    except Exception as exc:  # FAIL-OPEN
        print(f"[flow-gate] unexpected error, allowing: {exc}", file=sys.stderr)
        sys.exit(0)
