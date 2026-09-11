---
name: flow-init
description: Set up harness-tier in this repo, or re-sync it after a plugin update. Idempotent — safe to re-run.
disable-model-invocation: true
---

# Flow-Init — harness-tier Setup Wizard

Run after installing the harness-tier plugin in a host repository — or re-run any time
to re-sync the host scripts and optionally reconfigure. It writes the host-side
config and wiring that the plugin's runtime pieces (`/flow`, `flow_gate_check.py`,
`precommit-runner.sh`, `teams_alert.py`) depend on.

**Split of labor**: the deterministic, error-prone wiring (file copies, idempotent
`settings.json` / pre-commit / `.gitignore` merges) is done by
**`scripts/flow_init_setup.py`** so it is repeatable and unit-tested. This skill
(Claude) only does the **interactive / judgment** parts — gathering config,
collecting webhook URLs, writing the language-matched CLAUDE.md block — and
orchestrates by calling the scripts and relaying their reports.

**Idempotent**: safe to re-run. The setup script skips entries that already exist
(never double-appends); the interactive steps confirm before overwriting.

## Path conventions

- **Read from the plugin** (templates/scripts): `${CLAUDE_PLUGIN_ROOT}/...`
- **Write to the host repo** (config/wiring): `${CLAUDE_PROJECT_DIR}/...`
- **All host-side harness-tier artifacts live under `${CLAUDE_PROJECT_DIR}/.claude/harness-tier/`**,
  classified by purpose (no root scatter):
  - `scripts/` — copied gate scripts (plugin-owned, git-tracked)
  - `config/` — `flow-config.yaml`, `flow-tiers.yaml` (the tier→gates policy —
    plugin-owned, overwritten on every install, do not edit), `teams-webhooks.json`,
    `.teams-webhooks.local.json` (host-owned)
  - `.flow/` — gate evidence (gitignored)

  The only host files that stay elsewhere are the ones external tools pin:
  `.gitignore` (git), `.pre-commit-config.yaml` (pre-commit), `.claude/settings.json`
  (Claude Code).
- The commit gate runs as a **host** `settings.json` hook, where
  `${CLAUDE_PLUGIN_ROOT}` may not resolve — so the setup script **copies** the gate
  scripts into `${CLAUDE_PROJECT_DIR}/.claude/harness-tier/scripts/` and references them by
  host path.

```bash
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
PLUGIN="${CLAUDE_PLUGIN_ROOT}"
```

## Execution

### Execution modes — first run vs re-run

`/flow-init` is the single idempotent entry point. Branch on whether the host
config already exists (`${ROOT}/.claude/harness-tier/config/flow-config.yaml`):

- **First run (config absent)** — run Step 0 → Step 4 in order, gathering
  everything (the full wizard below).
- **Re-run (config present)** — the goal is *update without clobbering*:
  1. **Re-sync (always, non-interactive):** run Step 2's
     `flow_init_setup.py`. This re-copies the gate scripts/policy, repairs
     the `settings.json` gate path, and prints the `[config 슬롯 점검]` block.
     This must happen before any prompt, so a user who only wants fresh
     scripts is never blocked by questions.
  2. **Slot backfill (if any):** if the report lists missing slots, do Step
     2.5 (offer to insert them verbatim).
  3. **Reconfigure (opt-in):** `AskUserQuestion` — "Select the items to reconfigure"
     (multi-select; default: nothing). Options map to the existing steps,
     and you run **only the selected** ones against current values:
     - `flow-config.yaml` values → Step 1's slot prompts (existing values shown as defaults)
     - Teams webhook URL → Step 3's webhook prompts
     - CLAUDE.md teams block → Step 3's managed-block step
     If the user selects nothing, stop after re-sync + backfill.
  4. **Re-render (only if Reconfigure above changed a render flag):**
     `doc_style.enable`, `unit_test.enable`, `contract_test.enable` and
     `e2e.enable` decide whether a workflow is written, and the re-sync in
     item 1 ran before those questions were asked. Run
     `flow_init_setup.py` once more when one of them changed — otherwise the
     host carries `enable: true` with no workflow, which for `doc_style` means
     the rule is enforced in neither layer while the user believes it is on.

  Re-run never re-gathers everything and never overwrites host-owned config
  without the user selecting that section.

### Step 0 — Dependencies: detect (script), then install-with-consent (you)

Detection is mechanical → a script. Choosing **how** to install for *this*
environment, and doing it, is judgment → you (the host AI). Never install without
consent; never mutate machine-wide state.

1. **Detect** — run the checker (detection only; it does not install):
   ```bash
   bash "${PLUGIN}/scripts/check-deps.sh"
   ```
   It reports each dep as present/absent: **python3 ≥ 3.8** (required),
   **PyYAML** (required), **pre-commit** (recommended), **superpowers** plugin
   (required for Dev+). Its printed install commands are a *baseline hint* —
   you may find a better method for the actual environment.

2. **Install what you can — only after consent.** For each missing **pip-installable**
   dep (PyYAML, pre-commit):
   - Inspect the environment to choose the method: is `python3 -m pip` available?
     is it externally-managed (PEP 668)? Look up the right approach if unsure. The
     package **must land in the bare `python3` the commit hook calls** — prefer
     `python3 -m pip install <pkg>` (or `--user` when externally-managed), **not**
     `uv add` / a project venv the hook can't see.
   - **Ask first** (`AskUserQuestion`): show the exact command you intend to run;
     let the user **approve / pick an alternative / decline (install themselves)**.
   - On approval, run it, then re-run `check-deps.sh` to confirm. If it fails,
     diagnose and propose a better method (venv, pipx, OS package) — don't silently
     give up.

3. **Guide what you cannot install** (relay clearly; offer the command but let the
   user run it):
   - **python3 / version upgrade** — OS-level (Homebrew / apt / winget / choco),
     often needs admin. Offer the command for the detected OS.
   - **superpowers plugin** — installed via the host tool's *user-invoked* plugin
     command (`/plugin install superpowers@…`); you cannot run it. Guide the
     marketplace-add + install steps.

4. If a **required** dep (python3 ≥ 3.8, PyYAML) is still missing after this,
   **stop** and tell the user — the commit gate fails closed on every commit until
   it is present.

### Step 1 — Generate `flow-config.yaml` (interactive — Claude)

1. **When this step runs:** on a first run (config absent), build the file from
   scratch via item 2 below. On a re-run, this step runs **only if the user
   selected "flow-config.yaml values"** in the reconfigure menu (see Execution modes)
   — then edit only the specific values the user wants, showing current values as
   defaults; never a full re-entry, never a blind rewrite. (Missing-slot backfill
   is handled separately in Step 2.5.)

2. If the file is **absent** (first-time setup), build it:

   2a. Read `${PLUGIN}/flow-config.example.yaml` as the template (slots + format comments).
   2b. Ask for each slot via `AskUserQuestion`, showing the example value as default:
       - **branches**: `integration` / `staging` / `production` / `feature_prefix`
       - **merge_workflow**: `AskUserQuestion` (**multiSelect**) "Which flows go through a
         pull request?" — options `daily (feature/* · fix/* → integration)` and
         `promotion (integration → staging → production)`. Nothing selected →
         `pull_request: []` (all direct merges — the existing behaviour). The **promotion
         option's description MUST state**: a promotion PR merges only as "Create a merge
         commit" (a rebase leaves a `[skip ci]` rc commit as the head so the release never
         runs; a squash destroys the release history); a forced bump level needs the
         `Release-Level:` trailer in the merge commit body; and a ruleset without a
         release-automation bypass actor halts releases.
       - **review_checklist**: keep the generic categories; let the team append.
       - **doc_sync**: `index` / `dirs` / `service_docs` (empty if no per-service docs).
       - **contract_test** (REST API contract testing — CI only): first ask via
         `AskUserQuestion` "Does this repo have a REST API?". **No** → write
         `enable: false` and skip the slots below. **Yes** → collect `branches`
         (propose `flow-config.branches`' integration/staging/production values as
         defaults, but independently editable), `schema` (OpenAPI spec URL/path),
         `base_url`, and `server.compose_file`/`health_url`/`health_timeout`.
         - **Tool pin (once, at setup)**: use the `harness-researcher` agent to
           web-check the **current maintenance status** of OpenAPI contract-testing
           tool candidates → present a recommendation (default `schemathesis` +
           `schemathesis/action@v3`) and **pin** the choice into `tool`/`action_ref`.
           CI then runs deterministically on this pinned value (no per-CI web check).
       - **unit_test** (unit-test CI safety net — CI only): first ask via
         `AskUserQuestion` "Run unit tests in CI too?". The local flow gate (layer 2)
         only runs unit tests on Claude-session commits — direct/terminal/CI/GitHub
         commits bypass it, so this is the CI-side net. **No** → write `enable: false`
         and skip the slots below. **Yes** → collect `branches` (propose
         `flow-config.branches`' integration/staging/production values as defaults,
         independently editable), `timeout_minutes` (per-job wall-clock cap; default
         10), and one `jobs[]` entry per language/module to test — each
         `name` / `language` / `version` / `setup` / `test`. A `language` of
         python/node/java/go/rust selects that official setup action; any other value
         means the `setup` command prepares the runtime. Not derived from `modules[]`
         — the local gate and CI run in different execution contexts, so the CI job set
         is declared independently (self-contained `jobs[]`).
       - **doc_style** (prose discipline — `rules/doc-style.md`): ask via `AskUserQuestion`
         "Enforce the prose discipline?". **State the cost of "no" in the options
         themselves**: the commit-time stage only ever *warns*, so
         `.github/workflows/doc-style.yml` is the single place this rule is ever enforced —
         declining does not leave a lighter check, it leaves none. **Yes** → `enable: true`,
         then `paths` and `exclude` (offer the example's `["**/*.md"]` /
         `["CHANGELOG.md", "docs/superpowers/**", ".superpowers/**"]` as defaults, and
         mention `**/*.py`·`**/*.sh` cover comments and docstrings).
         **No** → `enable: false`; Step 2 then renders no workflow. The flag also drives the
         commit-time stage, so it is one answer for both layers, and flipping it later
         silences an already-rendered workflow without deleting it.
       - **modules** (per-module monorepo pre-checks — host-owned, lives under config):
         do not collect values on the first run. In Step 2.6, draft them by consulting
         the harness SSOT or by taking user input.
   2c. Write the filled `${ROOT}/.claude/harness-tier/config/flow-config.yaml` (create the
       `.claude/harness-tier/config/` directory if absent).

### Step 2 — Run the mechanical setup (idempotent script)

The deterministic wiring is done by a script so it is repeatable and tested — do
**not** hand-merge JSON/YAML:

```bash
python3 "${PLUGIN}/scripts/flow_init_setup.py"
```

**A non-zero exit means the gate is not installed** — the script says so in its own verdict
line, and it exits 1 rather than 0 so a caller that only reads the exit code cannot report a
setup that did not happen. Relay the verdict and stop; do not continue to Step 3 as if the gate
were live.

It performs the steps listed in
[`references/setup-script-actions.md`](references/setup-script-actions.md) — copies,
hook/marketplace registration, `.gitignore`, and the CI workflow renders — and prints a
report. **Relay that report; it is the authority on what was written**, not this skill's
description of it.

Then remind the user to run `pre-commit install --hook-type pre-commit --hook-type commit-msg
--hook-type pre-push` (activates gitlint, the push notifier, and the file-hygiene hooks) and
to swap the language-specific `local` hooks for their stack.

### Step 2.5 — Backfill missing config slots (interactive — Claude, skippable)

The Step 2 script prints a `[config 슬롯 점검]` block listing slots present in
`${PLUGIN}/flow-config.example.yaml` but absent from the host config (key-absence
only).

- If it lists missing slots, `AskUserQuestion` ("The example has N new config slots
  (<list>). Add them to the host config?", allow all or a subset, default all).
- For each accepted slot, read its block from `${PLUGIN}/flow-config.example.yaml` and
  **insert it verbatim** (comments and example defaults intact) into the host config at
  the parent anchor (end of the parent section; top-level slots append a new section)
  using **Edit** — never a PyYAML round-trip (preserves comments/format).
- Tell the user to adjust values for their environment; `enable`-style flags stay as in
  the example.
- Skip entirely when the report lists no missing slots.

### Step 2.6 — Module pre-check draft (when a harness is installed, skippable)

Draft `flow-config.modules[]` (the per-module monorepo pre-check settings). First
determine whether a harness is installed; the handling differs based on that.

**Harness detection**: consider the harness installed if either the
`${CLAUDE_PROJECT_DIR}/docs/code-style/` directory or any
`${CLAUDE_PROJECT_DIR}/services/*/CLAUDE.md` file exists.

**If a harness is installed** — read the SSOT and draft the modules:

1. Read the "toolchain & config" / "operational concerns" sections of
   `docs/code-style/<stack>.md` and `services/*/CLAUDE.md` (the per-module SSOT) to
   identify each module's language and tools.
2. For each module, fill in `path` and `checks`. Draft the standard keys
   (lint/static/import_lint/test/security) that exist for that language, and add any
   project-specific custom checks (license, sbom, secret-scan, …) the SSOT implies.
   Infer the test path from scaffold subfolders (`tests/`, etc.).
   - A check value is either a command string or the extended form
     `{ run: <cmd>, when: every-commit | promotion }`. Use `when` (NOT `on` — YAML
     parses a bare `on` key as boolean). Validate `when ∈ {every-commit, promotion}`;
     an unknown value falls back to every-commit with a warning, so catch typos here.
   - every-commit → runs on changed modules every commit (layer-2 flow gate).
     A string value defaults to every-commit (except `security`).
   - promotion → runs on all modules at staging/release promotion.
     A string `security` defaults to promotion (back-compat).
3. **If a tool can't be found in the SSOT or is ambiguous, confirm via
   `AskUserQuestion`** (do not guess).
4. Insert the draft into the `modules:` section of `flow-config.yaml` (Edit — no
   PyYAML round-trip; preserve format/comments). The research result is a default
   that the human edits in config; config is the final authority.

**If no harness is installed** — either take modules slot input directly via
`AskUserQuestion`, or let the user choose to leave it empty and fill it in manually
later. If the user chooses to skip, write `modules:` as an empty array (`[]`) and proceed.

### Step 2.7 — Merge ruleset check (PR mode only, skippable)

Applies only when `flow-config.merge_workflow.pull_request` is non-empty. Under PR mode the
local `git merge` disappears, so `flow-tiers.yaml`'s `merge_strategy` gate never fires — a
GitHub Ruleset has to carry that enforcement instead.

Follow [`references/merge-ruleset-check.md`](references/merge-ruleset-check.md) — it holds
the block to run and why each guard is written the way it is. Run it unconditionally: the
block detects the not-applicable case itself (the shipped `[]` default prints a skip line
and exits 0), so reading the config here to decide would only duplicate that.

### Step 2.8 — srs-verify workflow (when `docs/srs/` exists, skippable)

Applies only when `${ROOT}/docs/srs/` exists in the checkout — without one there is
nothing to point a workflow at.

Ask via `AskUserQuestion` whether to render `srs-verify.yml`. **The option descriptions
themselves carry what declining costs**, the same discipline as the `doc_style` ask above
and `/wiki-init`'s `wiki-verify` ask: the commit gate never reads an SRS, so this workflow
is the only thing that will ever see a dead anchor or a number two branches both took.
Declining does not leave a lighter check — it leaves none.

On **yes**:

```bash
python3 "${PLUGIN}/scripts/flow_init_setup.py" --render-srs-verify
```

Relay its line. An existing `srs-verify.yml` is reported and never overwritten. The
command is spelled from `${PLUGIN}`, not the host copy — `flow_init_setup.py` is not in
`COPY_FILES`, so the host holds no copy of it.

On **no**, say plainly that nothing now checks the SRS's anchors, and that re-running
`/flow-init` offers this again.

### Step 3 — Teams webhook URLs + CLAUDE.md block (interactive — Claude, skippable)

1. Ask for the **personal** webhook URL (input-wait alerts). If provided:
   `python3 "${ROOT}/.claude/harness-tier/scripts/teams_alert.py" --set personal <URL>` →
   writes `${ROOT}/.claude/harness-tier/config/.teams-webhooks.local.json` (gitignored).
2. Ask for **team branch** channels (keys = branch names, e.g. integration /
   staging / production). For each provided: `--set <branch> <URL>` → writes
   `${ROOT}/.claude/harness-tier/config/teams-webhooks.json`. Empty URLs are skipped at
   send time, so partial setup is fine.
3. **If any Teams channel was configured**, offer (via `AskUserQuestion`, default
   yes) to add a **managed Teams-usage block** to the host `CLAUDE.md` so this
   repo's Claude alerts **right before presenting `AskUserQuestion`** — which the
   Notification hook does *not* cover (it only auto-fires on permission/idle waits).
   The alert directive must be **emphasized** (e.g. `IMPORTANT`) so the host model
   does it. Insert between the idempotent markers, **written in the same
   language as the existing host `CLAUDE.md`** (the block below is the reference
   content — translate it to match the doc's language); if the markers
   already exist, **replace the block in place** (never duplicate). If
   `${ROOT}/CLAUDE.md` is absent, create it containing only this block. The script
   path is the host-installed copy `.claude/harness-tier/scripts/teams_alert.py` (not the
   plugin SOURCE). Skip entirely if no channel was set or the user declines:
   ````markdown
   <!-- harness-tier:teams BEGIN (managed by /flow-init — edits inside are overwritten) -->
   ## Teams notifications (harness-tier)

   **IMPORTANT — right before presenting `AskUserQuestion` (or any wait for user
   input), you MUST first notify the personal channel:**

   ```bash
   python3 "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}/.claude/harness-tier/scripts/teams_alert.py" \
     --channel personal --title "Waiting for input" --text "<one-line task summary>"
   ```

   - **Why manual** — `AskUserQuestion` does not trigger the Notification hook. This
     call is the only way to alert at the moment options are presented (permission/idle
     waits are handled automatically by the hook). The card automatically appends
     `project @ branch`.
   - **`CLAUDE_PROJECT_DIR` fallback recommended** — this variable is injected
     automatically **only during hook execution**. `teams_alert.py` self-heals by
     falling back to the git toplevel when it is unset, but for explicitness add the
     `:-$(git rev-parse --show-toplevel)` fallback shown above in manual calls (right
     before `AskUserQuestion`) — a safety net for when cwd is outside the repo.
   - **Webhook setup** — `personal` lives in
     `.claude/harness-tier/config/.teams-webhooks.local.json` (gitignored, per-user);
     branch channels (`dev`/`stage`/`main`, etc.) live in
     `.claude/harness-tier/config/teams-webhooks.json` (git-tracked, team-shared).
   - **Security exception** — a tracked Power Automate URL (containing a `sig=` token)
     is an intentional commit, not a leak. Because it is an incoming webhook, the worst
     case is channel-message injection (no data exfiltration or privilege escalation) —
     treat it as a secret-scanner exception.
   <!-- harness-tier:teams END -->
   ````

## Completion report

Print a summary: the **Step 0** dependency status (python3 ≥3.8 / PyYAML required —
gate fails closed if missing; pre-commit / superpowers guidance), the **Step 2**
script report (copied / registered / pre-commit checked / **contract-test, unit-test,
doc-style, e2e and srs-verify workflows rendered-or-skipped** / skipped, + any missing
pre-commit hooks to add manually),
the **Step 2.6** modules draft result (whether a harness was detected / number of modules
written / list of unconfirmed items / whether skipped), whether the
`CLAUDE.md` Teams block was added/updated/skipped, and the manual follow-ups
(`pre-commit install`, swapping language-specific hooks). **If
the Teams block was inserted and the host `CLAUDE.md` already had a hand-written
Teams-alert rule (pre-harness-tier), advise removing it — the managed block supersedes it
(never delete the user's content automatically).** Then tell the user they can run
`/flow`.

Two absences are worth naming rather than leaving to the report's silence, because in both
the layer is off and nothing says so later: a `doc_style.enable: false` means the prose rule
is written down and enforced nowhere, and `wiki-verify.yml` is not rendered here at all —
[`/wiki-init`](../wiki-init/SKILL.md) offers it once a wiki exists.

## Critical rules

1. **Install only with consent; never silently** — Step 0 detects via
   `check-deps.sh`, then installs **pip deps (PyYAML / pre-commit) only after
   `AskUserQuestion` approval**, adapting the method to the environment. python3 and
   the superpowers plugin are *guided*, not installed (OS-level / user-invoked).
   Never auto-install without asking, and never mutate machine-wide state
   (`git config --global`, `~`-level files).
2. **Idempotent** — `flow_init_setup.py` skips existing settings.json hooks and
   .gitignore lines (match-then-skip); pre-commit config is created-if-absent, else
   only **reported** (missing hooks listed, never auto-merged — preserves the team's
   comments/format); interactive steps confirm before overwrite.
3. **Secrets discipline** — the `personal` webhook stays in a gitignored file under
   `.claude/harness-tier/config/`. Branch-channel webhooks
   (`.claude/harness-tier/config/teams-webhooks.json`) are **intentionally git-tracked**
   (incoming webhooks → worst case is channel-message injection; a secret-scanner
   exception, not a leak).
4. **Host writes go through `${CLAUDE_PROJECT_DIR}`**, plugin reads through
   `${CLAUDE_PLUGIN_ROOT}` — never write into the plugin directory.
5. **CLAUDE.md edits are a managed block only** — touch only the marked
   `harness-tier:teams` region; never rewrite or reflow the user's own content.
