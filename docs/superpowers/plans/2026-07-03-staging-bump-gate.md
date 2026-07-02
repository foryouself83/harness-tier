# Staging Bump-Selection Gate + Token-Write Guard — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** At stage promotion, force the human to choose the version bump level (major/minor/patch); enforce that choice fail-closed via the flow gate, carry it to CI via a commit trailer, and make CI apply it — with main finalizing the rc deterministically. Add a token-write-permission guard around the release.

**Architecture:** `/vdev`(flow) asks the level at Staging and writes a `bump.done` marker + a `Release-Level:` commit trailer. `flow-tiers.yaml` gains a `bump` gate on `staging` (no gate-code change — `bump` is a standard evidence gate). CI (`release.yml` + consumer template) forces `semantic-release version --<level> --as-prerelease` on stage; main runs a deterministic rc-strip (`scripts/finalize_prerelease.py`) because python-semantic-release recomputes and loses an overridden level. A shared `scripts/check-token-write.sh` verifies `.permissions.push` for a CI preflight and a local best-effort warning.

**Tech Stack:** Python 3.12 (dev) / 3.8+ (deployed scripts), PyYAML, python-semantic-release ≥10<11, GitHub Actions, Bash (ShellCheck), pytest, ruff.

## Global Constraints

- Deployed gate/CI scripts must run on **python 3.8+** (walrus OK); dev tooling is 3.12. (from spec / CLAUDE.md)
- **FAIL-OPEN except unclassified/missing-deps** — never let a new check permanently block commits on internal error (Invariant #1). New `bump` gate is a normal evidence gate (fail-closed only when policy parses and no `bump.done`).
- **cp949 encoding defense** (Invariant #2) and **exit 2 = block** (Invariant #3) unchanged; new Python scripts use `encoding="utf-8"`.
- **Never write into the plugin dir at runtime**; `${CLAUDE_PLUGIN_ROOT}`=reads, `${CLAUDE_PROJECT_DIR}`=writes.
- **New `.sh` must pass ShellCheck** (hook runtime is Windows → bugs hide as FAIL-OPEN).
- **User-facing strings** (prompts, guard messages, generated docs) follow the host response-language convention (risk-tiers Language); Conventional-Commits keywords stay English.
- **Enforcement scope = Claude-session commits only** (existing flow-gate model); terminal commit-msg enforcement is out of scope.
- **Repo artifacts in English** (docs, commit messages, code comments).
- Spec: [docs/superpowers/specs/2026-07-03-staging-bump-selection-design.md](../specs/2026-07-03-staging-bump-selection-design.md).

---

# Group A — Bump-selection gate

## Task 1: [A] Add `bump` gate to staging policy + gate tests

**Files:**
- Modify: `flow-tiers.yaml` (staging.gates)
- Test: `tests/test_flow_gate_check.py`

**Interfaces:**
- Consumes: `scripts.flow_gate_check.missing_gates(flow_dir, gates)`, `required_gates(tiers_path, tier)`, `scripts._harness_paths.RUNTIME_GATES`.
- Produces: policy where `tiers.staging.gates` includes `bump`; `bump` is a non-runtime evidence gate requiring `.flow/bump.done`.

- [ ] **Step 1: Write failing tests** — append to `tests/test_flow_gate_check.py`:

```python
def test_bump_is_not_runtime_gate():
    from scripts._harness_paths import RUNTIME_GATES
    assert "bump" not in RUNTIME_GATES  # bump needs a .done marker (evidence gate)


def test_staging_requires_bump_marker(tmp_path: Path):
    flow = tmp_path / ".flow"
    flow.mkdir()
    (flow / "review.done").touch()  # security-scan is runtime; review present
    gates = ["precommit", "review", "security-scan", "bump"]
    assert missing_gates(flow, gates) == ["bump"]  # bump blocks until its marker exists
    (flow / "bump.done").touch()
    assert missing_gates(flow, gates) == []


def test_shipped_policy_staging_has_bump():
    # the shipped policy is the SSOT the gate reads; staging must carry bump.
    import yaml
    root = Path(__file__).resolve().parent.parent
    data = yaml.safe_load((root / "flow-tiers.yaml").read_text(encoding="utf-8"))
    assert "bump" in data["tiers"]["staging"]["gates"]
    assert "bump" not in data["tiers"]["release"]["gates"]  # asked at staging only
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_flow_gate_check.py::test_staging_requires_bump_marker tests/test_flow_gate_check.py::test_shipped_policy_staging_has_bump -v`
Expected: `test_staging_requires_bump_marker` PASSES already (missing_gates is generic); `test_shipped_policy_staging_has_bump` FAILS (`bump` not yet in policy).

- [ ] **Step 3: Add `bump` to staging gates** — edit `flow-tiers.yaml`, the `staging:` block:

```yaml
  staging:
    description: "QA/RC promotion (dev → stage) — security-tool pre-check + human bump-level selection"
    superpowers: true
    gates:
      - precommit
      - review
      - security-scan
      - bump
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_flow_gate_check.py -v`
Expected: PASS (all, including the two new + existing).

- [ ] **Step 5: Commit**

```bash
git add flow-tiers.yaml tests/test_flow_gate_check.py
git commit -m "feat: add bump-level gate to staging promotion"
```

## Task 2: [A] `scripts/finalize_prerelease.py` — deterministic rc-strip

**Files:**
- Create: `scripts/finalize_prerelease.py`
- Test: `tests/test_finalize_prerelease.py`

**Interfaces:**
- Produces: `finalize(root: Path) -> str | None` — if `pyproject.toml:project.version` is a prerelease `X.Y.Z-<token>.N`, writes stable `X.Y.Z` to `pyproject.toml:project.version` and `.claude-plugin/plugin.json:version` and returns `X.Y.Z`; otherwise returns `None` (no write). CLI: prints the stable version and exits 0 on strip; exits 1 (no output) when not a prerelease (caller falls back to plain semantic-release).

- [ ] **Step 1: Write failing tests** — create `tests/test_finalize_prerelease.py`:

```python
import json
from pathlib import Path

from scripts.finalize_prerelease import finalize


def _seed(tmp_path: Path, version: str) -> Path:
    (tmp_path / "pyproject.toml").write_text(
        f'[project]\nname = "x"\nversion = "{version}"\n'
        '[tool.semantic_release]\nversion_toml = ["pyproject.toml:project.version"]\n',
        encoding="utf-8",
    )
    pc = tmp_path / ".claude-plugin"
    pc.mkdir()
    (pc / "plugin.json").write_text(json.dumps({"name": "x", "version": version}) + "\n", encoding="utf-8")
    return tmp_path


def test_strips_prerelease(tmp_path: Path):
    _seed(tmp_path, "0.2.0-rc.1")
    assert finalize(tmp_path) == "0.2.0"
    assert 'version = "0.2.0"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert json.loads((tmp_path / ".claude-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"] == "0.2.0"


def test_noop_on_stable(tmp_path: Path):
    _seed(tmp_path, "0.2.0")
    assert finalize(tmp_path) is None
    assert 'version = "0.2.0"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")


def test_targets_project_version_not_sr_lines(tmp_path: Path):
    # version_toml/version_variables lines must be untouched (regex targets the bare project version)
    _seed(tmp_path, "1.2.3-rc.4")
    finalize(tmp_path)
    text = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert 'version = "1.2.3"' in text
    assert 'version_toml = ["pyproject.toml:project.version"]' in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_finalize_prerelease.py -v`
Expected: FAIL (`ModuleNotFoundError: scripts.finalize_prerelease`).

- [ ] **Step 3: Implement** — create `scripts/finalize_prerelease.py`:

```python
"""Deterministically finalize a prerelease version to its stable form.

Used by release.yml on the production branch. python-semantic-release does NOT drop
the rc token when a forced bump level was applied on stage — it recomputes the level
from commits and loses the override (verified 2026-07-03). So main strips the
prerelease suffix deterministically instead of re-running the version algorithm.

If pyproject's project.version is a prerelease (X.Y.Z-<token>.N), write the stable
X.Y.Z to pyproject.toml:project.version and .claude-plugin/plugin.json:version and
print it (exit 0). Otherwise (e.g. a hotfix straight to production with no rc) write
nothing and exit 1 so the caller falls back to plain `semantic-release version`.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# X.Y.Z-<anything> → capture X.Y.Z. Anchored to the bare `version = "..."` (the [project]
# version), so `version_toml`/`version_variables` lines never match.
_PROJECT_VERSION = re.compile(r'(?m)^version\s*=\s*"(?P<v>[^"]+)"')
_PRERELEASE = re.compile(r"^(?P<core>\d+\.\d+\.\d+)-[0-9A-Za-z.]+$")


def finalize(root: Path) -> str | None:
    pyproject = root / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    m = _PROJECT_VERSION.search(text)
    if not m:
        return None
    pm = _PRERELEASE.match(m.group("v"))
    if not pm:
        return None  # already stable (hotfix path) → caller falls back
    core = pm.group("core")
    pyproject.write_text(text[: m.start("v")] + core + text[m.end("v") :], encoding="utf-8")
    plugin = root / ".claude-plugin" / "plugin.json"
    data = json.loads(plugin.read_text(encoding="utf-8"))
    data["version"] = core
    plugin.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return core


def main() -> None:
    core = finalize(Path.cwd())
    if core is None:
        sys.exit(1)
    print(core)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_finalize_prerelease.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/finalize_prerelease.py tests/test_finalize_prerelease.py
git commit -m "feat: add deterministic prerelease rc-strip helper"
```

## Task 3: [A] harness-tier's own `release.yml` — stage force-level + main rc-strip

**Files:**
- Modify: `.github/workflows/release.yml`
- Test: `tests/test_release_workflow.py`

**Interfaces:**
- Consumes: `scripts/finalize_prerelease.py` (CLI), `git log -1 --pretty=%B` trailer.
- Produces: a workflow where the stage job forces the level from the `Release-Level:` trailer (fallback auto) and the main job finalizes via rc-strip (fallback plain compute).

- [ ] **Step 1: Write failing structure test** — create `tests/test_release_workflow.py`:

```python
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent


def _release_text() -> str:
    return (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")


def test_release_parses_and_has_jobs():
    data = yaml.safe_load(_release_text())
    assert "release" in data["jobs"]


def test_stage_forces_level_from_trailer():
    text = _release_text()
    assert "Release-Level:" in text
    assert "--as-prerelease" in text


def test_main_uses_deterministic_finalize():
    text = _release_text()
    assert "finalize_prerelease.py" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_release_workflow.py -v`
Expected: FAIL (`Release-Level:` / `finalize_prerelease.py` not present yet).

- [ ] **Step 3: Rewrite the Semantic-release step region of `.github/workflows/release.yml`.** Replace the single `Semantic release (bump + tag + push)` step with a stage step, a main-finalize step, and a main-hotfix fallback. Keep `permissions: contents: write`, checkout `fetch-depth: 0`, setup-python, install PSR, Configure Git. The new steps (Group B swaps the auth token; here keep `GITHUB_TOKEN` for now):

```yaml
      - name: Semantic release — stage rc (forced level from trailer)
        id: sr_stage
        if: ${{ github.ref_name == 'stage' }}
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          BEFORE="$(git rev-parse HEAD)"
          LEVEL="$(git log -1 --pretty=%B | sed -nE 's/^Release-Level:[[:space:]]*(major|minor|patch)[[:space:]]*$/\1/p' | head -1)"
          if [ -n "$LEVEL" ]; then
            echo "forcing $LEVEL (from Release-Level trailer)"
            semantic-release version --"$LEVEL" --as-prerelease --commit --tag --push --changelog
          else
            echo "no Release-Level trailer — auto-deriving"
            semantic-release version --commit --tag --push --changelog
          fi
          AFTER="$(git rev-parse HEAD)"
          [ "$BEFORE" != "$AFTER" ] && echo "released=true" >> "$GITHUB_OUTPUT" || echo "no release"

      - name: Release — main finalize (rc-strip) or hotfix compute
        id: sr_main
        if: ${{ github.ref_name == 'main' }}
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          BEFORE="$(git rev-parse HEAD)"
          if STABLE="$(python scripts/finalize_prerelease.py)"; then
            echo "finalizing prerelease -> $STABLE (deterministic rc-strip)"
            git add pyproject.toml .claude-plugin/plugin.json
            git commit -m "chore(release): $STABLE [skip ci]"
            git tag "v$STABLE"
            git push origin HEAD:main
            git push origin "v$STABLE"
          else
            echo "no prerelease to finalize (hotfix) — plain compute"
            semantic-release version --commit --tag --push --changelog
          fi
          AFTER="$(git rev-parse HEAD)"
          [ "$BEFORE" != "$AFTER" ] && echo "released=true" >> "$GITHUB_OUTPUT" || echo "no release"
```

Then update the later steps' `if:` guards to read from whichever job ran. Change the marketplace-pin step guard and the uv.lock/GitHub-release guards to use a combined output. Add a small aggregation step right after the two release steps:

```yaml
      - name: Aggregate release result
        id: sr
        run: |
          if [ "${{ steps.sr_stage.outputs.released }}" = "true" ] || [ "${{ steps.sr_main.outputs.released }}" = "true" ]; then
            echo "released=true" >> "$GITHUB_OUTPUT"
          fi
```

Leave the existing `Pin marketplace sha` (`github.ref_name == 'main' && steps.sr.outputs.released == 'true'`), `Sync uv.lock`, and `Create GitHub Release` steps unchanged — they already key off `steps.sr.outputs.released`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_release_workflow.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/release.yml tests/test_release_workflow.py
git commit -m "feat: force stage bump level and rc-strip on main in release CI"
```

## Task 4: [A] `/flow` (flow SKILL) + `risk-tiers.md` — staging bump-selection step

**Files:**
- Modify: `skills/flow/SKILL.md` (Promotion → Staging)
- Modify: `rules/risk-tiers.md` (Staging section + gates table + Commit Discipline note)

**Interfaces:** documentation/behavior only — the `/flow` Staging step must (1) `AskUserQuestion` major/minor/patch with the commit-derived default and a warn when `major` on a 0.x project, (2) `touch .claude/harness-tier/.flow/bump.done`, (3) insert `Release-Level: <level>` as a trailer into the staging promotion commit.

- [ ] **Step 1: Edit `skills/flow/SKILL.md`** — in the **Promotion — Staging** bullet, replace the Staging bullet body with:

```markdown
- **Staging** (integration → staging): regression `review` (independent
  `general-purpose` agent) **and bump-level selection**:
  1. Compute the commit-derived level as the default: `semantic-release version --print`
     (best-effort) — compare to the current version to suggest major/minor/patch.
  2. `AskUserQuestion`: **major / minor / patch** (default = the derived level).
     **If the choice is `major` while the current version is `0.x`, warn that it jumps
     to `1.0.0`** (explicit `--major` overrides `major_on_zero=false`).
  3. `touch .claude/harness-tier/.flow/{review,bump}.done`.
  4. Commit on the staging branch **with a trailer** `Release-Level: <level>` (blank
     line before the trailer). CI reads it to force
     `semantic-release version --<level> --as-prerelease`. main needs no level — it
     finalizes the rc deterministically.
```

- [ ] **Step 2: Edit `rules/risk-tiers.md`** — in the **Staging — integration → staging** section, append after the existing gates line:

```markdown
Staging also **forces a human bump-level choice**: `/flow` asks major/minor/patch
(default = commit-derived) and records a `bump` gate marker; the commit gate blocks
the staging commit until `bump.done` exists (fail-closed). The choice rides the
staging commit as a `Release-Level:` trailer and CI forces
`semantic-release version --<level> --as-prerelease`. main finalizes the rc by
dropping the token deterministically (an overridden level would otherwise be lost —
python-semantic-release recomputes on the stable branch). `major` on a 0.x project
jumps to `1.0.0`.
```

Then in the **When each tier applies** table row for `integration → staging`, change the Gates cell to `precommit, review, security-scan, bump`.

- [ ] **Step 3: Verify no contradiction** — grep the two files for the old staging gate list and confirm consistency:

Run: `uv run pytest tests/test_flow_gate_check.py::test_shipped_policy_staging_has_bump -v`
Expected: PASS (policy already carries `bump` from Task A1). Manually confirm the table/text mention `bump`.

- [ ] **Step 4: Commit**

```bash
git add skills/flow/SKILL.md rules/risk-tiers.md
git commit -m "feat: document staging bump-level selection gate"
```

## Task 5: [A] Consumer release template parity (python-semantic-release)

**Files:**
- Modify: `github/release.python-semantic-release.workflow.example.yml`
- Test: `tests/test_release_workflow.py` (extend)

**Interfaces:** the rendered consumer workflow uses `__HARNESS_STABLE__`/`__HARNESS_PRERELEASE__` tokens (rendered by `flow_init_setup.render_versioning_workflows`); it must carry the same stage-force + main-finalize logic, parameterized by those tokens. `finalize_prerelease.py` must also be available to consumers (shipped via COPY_FILES in Task B1) — but consumers run it from `.claude/harness-tier/scripts/`. Use that path in the template.

- [ ] **Step 1: Extend the structure test** — append to `tests/test_release_workflow.py`:

```python
def test_consumer_template_has_force_and_finalize():
    tmpl = (ROOT / "github" / "release.python-semantic-release.workflow.example.yml").read_text(encoding="utf-8")
    assert "Release-Level:" in tmpl
    assert "--as-prerelease" in tmpl
    assert "finalize_prerelease.py" in tmpl
    assert "__HARNESS_STABLE__" in tmpl and "__HARNESS_PRERELEASE__" in tmpl
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_release_workflow.py::test_consumer_template_has_force_and_finalize -v`
Expected: FAIL.

- [ ] **Step 3: Edit the template** — replace the `Semantic release` step in `github/release.python-semantic-release.workflow.example.yml` with stage/main steps mirroring Task A3, but keyed off the rendered branch tokens and calling the host-copied helper:

```yaml
      - name: Semantic release — prerelease rc (forced level from trailer)
        id: sr_pre
        if: ${{ github.ref_name == '__HARNESS_PRERELEASE__' }}
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          LEVEL="$(git log -1 --pretty=%B | sed -nE 's/^Release-Level:[[:space:]]*(major|minor|patch)[[:space:]]*$/\1/p' | head -1)"
          if [ -n "$LEVEL" ]; then
            semantic-release version --"$LEVEL" --as-prerelease --commit --tag --push --changelog
          else
            semantic-release version --commit --tag --push --changelog
          fi

      - name: Release — stable finalize (rc-strip) or hotfix compute
        id: sr_stable
        if: ${{ github.ref_name == '__HARNESS_STABLE__' }}
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          FINALIZE=".claude/harness-tier/scripts/finalize_prerelease.py"
          if [ -f "$FINALIZE" ] && STABLE="$(python "$FINALIZE")"; then
            git add pyproject.toml .claude-plugin/plugin.json 2>/dev/null || git add -A
            git commit -m "chore(release): $STABLE [skip ci]"
            git tag "v$STABLE"; git push origin HEAD:__HARNESS_STABLE__; git push origin "v$STABLE"
          else
            semantic-release version --commit --tag --push --changelog
          fi
```

Keep the header comment and the `on.push.branches: [__HARNESS_STABLE__, __HARNESS_PRERELEASE__]` unchanged. (Note: consumers whose version file is not `pyproject.toml`/`plugin.json` — the finalize helper is python/plugin-specific; document this limitation in the template header comment: "finalize_prerelease.py targets pyproject.toml + plugin.json; other stacks fall back to plain compute on the stable branch".)

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_release_workflow.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add github/release.python-semantic-release.workflow.example.yml tests/test_release_workflow.py
git commit -m "feat: mirror bump-force and rc-strip in consumer release template"
```

---

# Group B — Token-write-permission guard

## Task 6: [B] `scripts/check-token-write.sh` + tests + ship via COPY_FILES

**Files:**
- Create: `scripts/check-token-write.sh`
- Modify: `scripts/flow_init_setup.py` (COPY_FILES) — and `finalize_prerelease.py` too (for A5's consumer path)
- Test: `tests/test_check_token_write.py`, `tests/test_flow_init_setup.py` (extend)

**Interfaces:**
- `check-token-write.sh [--decode]`. Env: `HARNESS_REPO` (else `$GITHUB_REPOSITORY`), token from `$HARNESS_TOKEN` (else `$GITHUB_TOKEN`). Default mode fetches `GET /repos/<repo>` JSON (via `curl`) and decodes; `--decode` reads JSON from stdin (testable, no network). Exit codes: **0** = has push (write); **10** = confirmed no push (read-only); **20** = undetermined (no token/tool/parse). Prints a one-line human message to stderr.

- [ ] **Step 1: Write failing tests** — create `tests/test_check_token_write.py`:

```python
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check-token-write.sh"


def _decode(json_text: str) -> int:
    return subprocess.run(
        ["bash", str(SCRIPT), "--decode"],
        input=json_text, text=True, capture_output=True,
    ).returncode


def test_push_true_exits_0():
    assert _decode('{"permissions":{"admin":false,"push":true,"pull":true}}') == 0


def test_push_false_exits_10():
    assert _decode('{"permissions":{"admin":false,"push":false,"pull":true}}') == 10


def test_no_push_key_exits_20():
    assert _decode('{"full_name":"x/y"}') == 20
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_check_token_write.py -v`
Expected: FAIL (script missing).

- [ ] **Step 3: Implement** — create `scripts/check-token-write.sh`:

```bash
#!/usr/bin/env bash
# Verify a token has WRITE (push) permission on the repo, via the GitHub API field
# .permissions.push (admin-free — a live check confirmed actions/permissions/workflow
# needs Administration:read and 403s otherwise).
#
# Usage: check-token-write.sh [--decode]
#   default : fetch GET /repos/<repo> and decode .permissions.push
#   --decode: read repo JSON from stdin (unit-testable, no network)
# Env: HARNESS_REPO (else GITHUB_REPOSITORY), HARNESS_TOKEN (else GITHUB_TOKEN)
# Exit: 0 has-write | 10 read-only | 20 undetermined (no token/tool/parse).
set -u

decode() {  # reads JSON on stdin → exit 0/10/20
  local json push
  json="$(cat)"
  push="$(printf '%s' "$json" | grep -oE '"push"[[:space:]]*:[[:space:]]*(true|false)' | head -1 | grep -oE '(true|false)')"
  case "$push" in
    true)  return 0 ;;
    false) echo "token lacks write (push) permission on the repo" >&2; return 10 ;;
    *)     echo "could not determine write permission (no 'push' field)" >&2; return 20 ;;
  esac
}

if [ "${1:-}" = "--decode" ]; then
  decode
  exit $?
fi

repo="${HARNESS_REPO:-${GITHUB_REPOSITORY:-}}"
token="${HARNESS_TOKEN:-${GITHUB_TOKEN:-}}"
if [ -z "$repo" ] || [ -z "$token" ] || ! command -v curl >/dev/null 2>&1; then
  echo "token/repo/curl unavailable — skipping write-permission check" >&2
  exit 20
fi
curl -fsS -H "Authorization: Bearer $token" -H "X-GitHub-Api-Version: 2022-11-28" \
  "https://api.github.com/repos/$repo" 2>/dev/null | decode
exit $?
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_check_token_write.py -v`
Expected: PASS. Then ShellCheck: `shellcheck scripts/check-token-write.sh` → no warnings.

- [ ] **Step 5: Ship both new scripts to hosts** — edit `scripts/flow_init_setup.py` `COPY_FILES`:

```python
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
```

- [ ] **Step 6: Extend the copy test** — append to `tests/test_flow_init_setup.py` (match its existing style; a minimal assertion):

```python
def test_copy_files_includes_new_scripts():
    from scripts.flow_init_setup import COPY_FILES
    assert "scripts/check-token-write.sh" in COPY_FILES
    assert "scripts/finalize_prerelease.py" in COPY_FILES
```

- [ ] **Step 7: Run and commit**

Run: `uv run pytest tests/test_check_token_write.py tests/test_flow_init_setup.py -v`
Expected: PASS.

```bash
git add scripts/check-token-write.sh scripts/flow_init_setup.py tests/test_check_token_write.py tests/test_flow_init_setup.py
git commit -m "feat: add shared token-write-permission check script"
```

## Task 7: [B] `release.yml` — RELEASE_TOKEN auth + preflight guard

**Files:**
- Modify: `.github/workflows/release.yml`
- Test: `tests/test_release_workflow.py` (extend)

**Interfaces:** consumes `scripts/check-token-write.sh` (repo copy at `scripts/`); the workflow authenticates with `secrets.RELEASE_TOKEN` and preflights write permission before releasing.

- [ ] **Step 1: Extend the structure test**:

```python
def test_release_uses_release_token_and_preflight():
    text = _release_text()
    assert "secrets.RELEASE_TOKEN" in text
    assert "check-token-write.sh" in text
    assert "GITHUB_STEP_SUMMARY" in text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_release_workflow.py::test_release_uses_release_token_and_preflight -v`
Expected: FAIL.

- [ ] **Step 3: Edit `.github/workflows/release.yml`**:
  1. In `actions/checkout`, set `token: ${{ secrets.RELEASE_TOKEN }}`.
  2. Change the two release steps' `GH_TOKEN` env and any `git push` auth to use `RELEASE_TOKEN` (checkout already configures the remote with the token, so `git push` uses it; set `GH_TOKEN: ${{ secrets.RELEASE_TOKEN }}` on the `gh`/PSR steps).
  3. Add a preflight step right after "Configure Git":

```yaml
      - name: Preflight — token write permission
        env:
          GITHUB_REPOSITORY: ${{ github.repository }}
          GITHUB_TOKEN: ${{ secrets.RELEASE_TOKEN }}
        run: |
          set +e
          bash scripts/check-token-write.sh
          rc=$?
          if [ "$rc" = "10" ]; then
            {
              echo "## ❌ Release blocked — token lacks write permission"
              echo "Grant it: **Settings → Actions → General → Workflow permissions → Read and write**,"
              echo "or use a PAT secret \`RELEASE_TOKEN\` with Contents+Workflows: Read and write."
              echo "See USAGE.md → \"Release token write permission\"."
            } >> "$GITHUB_STEP_SUMMARY"
            echo "::error::token lacks write permission (see job summary / USAGE.md)"
            exit 1
          fi
          echo "token write preflight: rc=$rc (0=ok, 20=undetermined → trap will catch a real failure)"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_release_workflow.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add .github/workflows/release.yml tests/test_release_workflow.py
git commit -m "feat: use RELEASE_TOKEN and preflight write permission in release CI"
```

## Task 8: [B] `/flow` local best-effort token warning + consumer template auth note

**Files:**
- Modify: `skills/flow/SKILL.md` (Staging step — add local warning)
- Modify: `github/release.python-semantic-release.workflow.example.yml` (documented PAT opt-in; default stays GITHUB_TOKEN)

**Interfaces:** documentation/behavior only.

- [ ] **Step 1: Edit `skills/flow/SKILL.md`** — add to the Staging step (after the bump selection):

```markdown
- Before committing the staging promotion, **best-effort** warn if the release token
  lacks write: if `gh`/a token is available, run
  `.claude/harness-tier/scripts/check-token-write.sh` (exit 10 → warn with the
  Settings/PAT how-to; exit 20/no tool → skip silently, never block).
```

- [ ] **Step 2: Edit the consumer template header comment** — in `github/release.python-semantic-release.workflow.example.yml`, add under the prereq comment:

```yaml
# Auth: default uses GITHUB_TOKEN (ensure Settings → Actions → Workflow permissions =
# Read and write). To bypass branch protection / trigger downstream, add a PAT secret
# RELEASE_TOKEN (Contents+Workflows: RW) and set checkout `token:` + step `GH_TOKEN` to it.
# How to grant: see the generated docs/operations/commit-versioning-guide.md.
```

- [ ] **Step 3: Commit**

```bash
git add skills/flow/SKILL.md github/release.python-semantic-release.workflow.example.yml
git commit -m "feat: add local token warning and consumer PAT opt-in note"
```

## Task 9: [B] Canonical "how to grant token write permission" doc (SSOT)

**Files:**
- Modify: `USAGE.md`, `USAGE.ko.md` (add a canonical section)
- Modify: `docs/plugins/marketplace-auto-update.md` (link the one-liner to it)
- Modify: `skills/harness-authoring/references/commit-versioning-guide.md` (authoring rule so the generated guide emits the section)

**Interfaces:** documentation only. One canonical section per audience; other mentions link to it.

- [ ] **Step 1: Add the section to `USAGE.md`** — a new `## Release token write permission` section:

```markdown
## Release token write permission

The release workflow pushes the version bump/tag, so its token needs **write**.

1. **Primary** — Settings → Actions → General → **Workflow permissions** → **Read and
   write permissions** → Save.
2. **Organization override** — if an org caps Actions permissions to read-only, an org
   admin must relax it (or allow repos to configure their own).
3. **Protected branch / ruleset** — if the release branch restricts pushes, add the
   Actions bot/token to the bypass list, or use a token that can bypass.
4. **PAT / `RELEASE_TOKEN` (escalation)** — when `GITHUB_TOKEN` is insufficient (bypass
   protection, trigger downstream workflows): create a fine-grained PAT with
   `Contents: Read and write` (+ `Workflows: Read and write` if the release touches
   workflow files), store it as the repo secret `RELEASE_TOKEN`, and reference it in
   `actions/checkout` `token:` and the release step's `GH_TOKEN`.

The release preflight (`check-token-write.sh`) fails fast with this pointer when the
token is read-only.
```

- [ ] **Step 2: Mirror the section into `USAGE.ko.md`** — same content, Korean prose (keep the Settings path labels and `RELEASE_TOKEN`/permission names in English).

- [ ] **Step 3: Link the one-liner** — in `docs/plugins/marketplace-auto-update.md`, change the prerequisite line to reference the canonical section:

```markdown
- **Prerequisite**: repository Settings → Actions → Workflow permissions = **Read and write** (see [USAGE.md → Release token write permission](../../USAGE.md#release-token-write-permission)).
```

- [ ] **Step 4: Add the authoring rule** — in `skills/harness-authoring/references/commit-versioning-guide.md`, add a new document-structure section spec + authoring rule so the generated `docs/operations/commit-versioning-guide.md` carries the how-to. Insert after section "### 3. Release Tool Configuration":

```markdown
### 3b. CI Token Write Permission — how to grant
- The release CI pushes tags/commits, so its token needs **write**. Document, in order:
  primary (Settings → Actions → Workflow permissions = Read and write), org override,
  protected-branch bypass, and PAT/`RELEASE_TOKEN` escalation (Contents+Workflows: RW,
  repo secret, `actions/checkout` token + step `GH_TOKEN`).
- This is the single canonical location; guard messages link here.
```

And add authoring rule #7:

```markdown
7. **Emit the token-write-permission section** — always include §3b (single canonical
   location); the rendered release workflow's guard message links to it.
```

- [ ] **Step 5: Commit**

```bash
git add USAGE.md USAGE.ko.md docs/plugins/marketplace-auto-update.md skills/harness-authoring/references/commit-versioning-guide.md
git commit -m "docs: add canonical release token write-permission guide"
```

---

# Finalization (after all tasks)

- [ ] **Full test + lint sweep**

Run: `uv run pytest && uv run ruff check && uv run ruff format --check`
Expected: all PASS. Also `shellcheck scripts/check-token-write.sh`.

- [ ] **Verify (semantic-release scenarios)** — re-run the scratch verification (spec §6D) to confirm stage force + rc-strip still behave: forced `--minor --as-prerelease` → `X.Y.0-rc.1`; `finalize_prerelease.py` on `X.Y.0-rc.1` → `X.Y.0`.

- [ ] **Domain review** — independent `general-purpose` agent against the review checklist (regression on the gate; release-flow correctness; no plugin-dir writes). On pass → `touch .claude/harness-tier/.flow/review.done`.

- [ ] **doc-sync** — invoke the `doc-sync` skill to harmonize CLAUDE.md/USAGE/rules. On pass → `touch .claude/harness-tier/.flow/doc-sync.done`.

- [ ] **Merge** feature/staging-bump-gate → dev per risk-tiers merge strategy (rebase → integration-test human gate → squash-by-category).

## Self-Review (spec coverage)

- Bump gate policy + enforcement → A1. ✓
- rc-strip finalize (verified) → A2 + A3(main) + A5(consumer). ✓
- Stage force-level + trailer → A3(stage) + A4(flow writes trailer) + A5. ✓
- Ask + default + major/0.x warn + bump.done → A4. ✓
- Token guard (script/preflight/local/how-to) → B1–B4. ✓
- RELEASE_TOKEN (harness-tier own) → B2; consumer GITHUB_TOKEN default + PAT opt-in → B3. ✓
- Session-commit-only, node deferred → honored (no terminal commit-msg hook; node template left on plain compute via fallback). ✓
- Ship to consumers (SSOT) → A5, B1(COPY_FILES), B3, B4. ✓
