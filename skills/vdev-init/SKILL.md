---
name: vdev-init
description: Idempotent setup & update wizard for a host repo — first run installs deps and gathers config; re-runs re-sync the host gate scripts, backfill new config slots, and optionally reconfigure values/webhooks/credentials (absorbs the former /vdev-upgrade)
allowed-tools: Bash, Read, Write, Edit, AskUserQuestion, Glob, Grep
argument-hint: (none)
disable-model-invocation: true
---

# Vdev-Init — vway-kit Setup Wizard

Run after installing the vway-kit plugin in a host repository — or re-run any time
to re-sync the host scripts and optionally reconfigure. It writes the host-side
config and wiring that the plugin's runtime pieces (`/vdev`, `vdev_gate_check.py`,
`precommit-runner.sh`, `teams_alert.py`) depend on.

**Split of labor**: the deterministic, error-prone wiring (file copies, idempotent
`settings.json` / pre-commit / `.gitignore` merges, auto-update auth detection) is done by
**`scripts/vdev_init_setup.py`** so it is repeatable and unit-tested. This command
(Claude) only does the **interactive / judgment** parts — gathering config,
collecting webhook URLs, writing the language-matched CLAUDE.md block — and
orchestrates by calling the scripts and relaying their reports.

**Idempotent**: safe to re-run. The setup script skips entries that already exist
(never double-appends); the interactive steps confirm before overwriting.

## Path conventions

- **Read from the plugin** (templates/scripts): `${CLAUDE_PLUGIN_ROOT}/...`
- **Write to the host repo** (config/wiring): `${CLAUDE_PROJECT_DIR}/...`
- **All host-side vway-kit artifacts live under `${CLAUDE_PROJECT_DIR}/.claude/vway-kit/`**,
  classified by purpose (no root scatter):
  - `scripts/` — copied gate scripts (plugin-owned, git-tracked)
  - `config/` — `vdev-config.yaml`, `vdev-tiers.yaml` (the tier→gates policy —
    plugin-owned, overwritten on every install, do not edit), `teams-webhooks.json`,
    `.teams-webhooks.local.json` (host-owned)
  - `.vdev/` — gate evidence (gitignored)

  The only host files that stay elsewhere are the ones external tools pin:
  `.gitignore` (git), `.pre-commit-config.yaml` (pre-commit), `.claude/settings.json`
  (Claude Code).
- The commit gate runs as a **host** `settings.json` hook, where
  `${CLAUDE_PLUGIN_ROOT}` may not resolve — so the setup script **copies** the gate
  scripts into `${CLAUDE_PROJECT_DIR}/.claude/vway-kit/scripts/` and references them by
  host path.

```bash
ROOT="${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}"
PLUGIN="${CLAUDE_PLUGIN_ROOT}"
```

## Execution

### Execution modes — first run vs re-run

`/vdev-init` is the single idempotent entry point. Branch on whether the host
config already exists (`${ROOT}/.claude/vway-kit/config/vdev-config.yaml`):

- **First run (config absent)** — run Step 0 → Step 4 in order, gathering
  everything (the full wizard below).
- **Re-run (config present)** — the goal is *update without clobbering*:
  1. **Re-sync (always, non-interactive):** run Step 2's
     `vdev_init_setup.py`. This re-copies the gate scripts/policy, repairs
     the `settings.json` gate path, migrates any legacy layout, and prints
     the `[config 슬롯 점검]` block. This must happen before any prompt, so a
     user who only wants fresh scripts is never blocked by questions.
  2. **Slot backfill (if any):** if the report lists missing slots, do Step
     2.5 (offer to insert them verbatim).
  3. **Reconfigure (opt-in):** `AskUserQuestion` — "재설정할 항목을 고르세요"
     (multi-select; default: nothing). Options map to the existing steps,
     and you run **only the selected** ones against current values:
     - `vdev-config.yaml` 값 → Step 1's slot prompts (existing values shown as defaults)
     - Teams webhook URL → Step 3's webhook prompts
     - CLAUDE.md teams 블록 → Step 3's managed-block step
     - Teamer 자격증명 → Step 4's guidance
     If the user selects nothing, stop after re-sync + backfill.

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

### Step 1 — Generate `vdev-config.yaml` (interactive — Claude)

1. **When this step runs:** on a first run (config absent), build the file from
   scratch via items 2-4 below. On a re-run, this step runs **only if the user
   selected "vdev-config.yaml 값"** in the reconfigure menu (see Execution modes)
   — then edit only the specific values the user wants, showing current values as
   defaults; never a full re-entry, never a blind rewrite. (Missing-slot backfill
   is handled separately in Step 2.5.)

2. If the file is **absent** (first-time setup), build it:

   2a. Read `${PLUGIN}/vdev-config.example.yaml` as the template (slots + format comments).
   2b. Ask for each slot via `AskUserQuestion`, showing the example value as default:
       - **branches**: `integration` / `staging` / `production` / `feature_prefix`
       - **teamer** (REQUIRED — no hardcoded fallback): `project_no` / `workitem_no`
         / `workflow_no`. If the user cannot provide them, stop and explain they are
         mandatory for `/task-import` · `/task-sync`.
       - **review_checklist**: keep the generic categories; let the team append.
       - **doc_sync**: `index` / `dirs` / `service_docs` (empty if no per-service docs).
       - **contract_test** (REST API 계약 테스트 — CI 전용): 먼저 `AskUserQuestion`으로
         "이 repo에 REST API가 있습니까?"를 묻는다. **아니오** → `enable: false`로 쓰고
         이하 슬롯은 생략. **예** → `branches`(기본값으로 `vdev-config.branches`의
         integration/staging/production 값을 제안하되 독립 편집 가능), `schema`(OpenAPI
         스펙 URL/경로), `base_url`, `server.compose_file`/`health_url`/`health_timeout`을
         수집한다.
         - **도구 pin (셋업 시 1회)**: `harness-researcher` 에이전트로 OpenAPI 계약 테스트
           도구 후보의 **최신 유지보수 상태**를 웹 확인 → 추천(기본 `schemathesis` +
           `schemathesis/action@v3`)을 제시하고, 선택을 `tool`/`action_ref`에 **고정(pin)**한다.
           이후 CI는 이 고정값으로 결정적으로 실행된다(매 CI마다 웹 확인하지 않음).
       - **modules** (모노레포 모듈 단위 사전검사 — 호스트 소유, config 아래 위치):
         첫 실행 시에는 값을 수집하지 않는다. Step 2.6 에서 harness SSOT 를 참고해
         초안을 작성하거나 사용자 입력을 받는다.
   2c. Write the filled `${ROOT}/.claude/vway-kit/config/vdev-config.yaml` (create the
       `.claude/vway-kit/config/` directory if absent).

### Step 2 — Run the mechanical setup (idempotent script)

The deterministic wiring is done by a script so it is repeatable and tested — do
**not** hand-merge JSON/YAML:

```bash
python3 "${PLUGIN}/scripts/vdev_init_setup.py"
```

It performs, idempotently, and prints a report to relay:
- **Copies** `precommit-runner.sh`, `vdev_gate_check.py`, `teams_alert.py`,
  `notify-push.sh`, and `check-deps.sh` into `.claude/vway-kit/scripts/`, and the
  `vdev-tiers.yaml` policy into `.claude/vway-kit/config/` (copied — not symlinked —
  so a host `settings.json` hook can run the scripts by `${CLAUDE_PROJECT_DIR}` path;
  the gate resolves `vdev-tiers.yaml` from its sibling `config/` directory).
- **Migrates** any legacy layout into the new classification: root-scattered config →
  `config/` (`vdev-config.yaml`, `teams-webhooks.json`,
  `.teams-webhooks.local.json`), `.claude/.vdev/` → `.claude/vway-kit/.vdev/`, and flat
  scripts → `scripts/`. It also relocates a legacy `scripts/vdev-tiers.yaml` to
  `config/` (the policy moved there; the old copy is removed since `copy_artifacts`
  rewrites `config/`). Idempotent — moves only when the old path exists and the new
  one does not, so fresh installs and already-migrated repos are skipped.
- **Registers** the commit gate in `.claude/settings.json` `hooks.PreToolUse` (skips
  if already present; no `if` field — `precommit-runner.sh` self-filters on stdin).
- **Registers** the `vway` marketplace in `.claude/settings.json`
  `extraKnownMarketplaces` with `autoUpdate: true` (adds if absent, repairs the flag
  if present). Third-party marketplaces default to *no* auto-update and the author
  cannot force it via `marketplace.json` (supply-chain boundary) — so the host opts in
  here. Committed → the whole team auto-updates the plugin at startup. (Background
  auto-update authenticates only via a `GITHUB_TOKEN` env var — see the auth note below.)
- **Checks** the static-analysis hooks: **creates** `.pre-commit-config.yaml` from the
  example if absent (the `local` hooks are Python defaults to swap); if it **already
  exists, does NOT auto-merge** (a PyYAML round-trip would strip the team's
  comments/formatting) — instead **detects missing repos/hooks by `id` and reports
  them** for the user to add manually.
- **Appends** missing `.gitignore` lines, and **untracks** any `.vdev/` evidence
  already in the git index (`git rm --cached`) — a `.gitignore` line alone never
  un-tracks a file that was committed before the line existed.
- **Checks** private-repo auto-update auth and *suggests* fixes (never applies — these
  are machine-wide changes): a `GITHUB_TOKEN` env var; a **github.com credential helper**
  that feeds that token to git (git does NOT read `GITHUB_TOKEN` itself, so background
  fetch fails without it); and — if a broad `https://github.com/`→SSH `insteadOf` rewrite
  exists — a surgical identity-override exempting the marketplace repo so its HTTPS fetch
  is not rewritten to SSH. See [docs/plugins/marketplace-auto-update.md](../../docs/plugins/marketplace-auto-update.md).
- **Renders** `.github/workflows/api-contract.yml` from `vdev-config.contract_test`
  when `enable: true` (creates if absent; if it already exists, **does NOT overwrite** —
  reports for manual review). `.github/workflows/` is GitHub's enforced location — a
  documented exception to the `.claude/vway-kit/` rule. Skips entirely when
  `enable: false` or the section is absent.

Then remind the user to run `pre-commit install --hook-type commit-msg
--hook-type pre-push` (activates gitlint + the push notifier) and to swap the
language-specific `local` hooks for their stack.

### Step 2.5 — Backfill missing config slots (interactive — Claude, skippable)

The Step 2 script prints a `[config 슬롯 점검]` block listing slots present in
`${PLUGIN}/vdev-config.example.yaml` but absent from the host config (key-absence
only; handoff kinds appear as `handoff.<kind>`).

- If it lists missing slots, `AskUserQuestion` ("example 에 새 config 슬롯 N개
  (<목록>)가 있습니다. 호스트 config 에 추가할까요?", allow all or a subset, default all).
- For each accepted slot, read its block from `${PLUGIN}/vdev-config.example.yaml` and
  **insert it verbatim** (comments and example defaults intact) into the host config at
  the parent anchor (end of the parent section; top-level slots append a new section)
  using **Edit** — never a PyYAML round-trip (preserves comments/format).
- Tell the user to adjust values for their environment; `enable`-style flags stay as in
  the example (handoff kinds stay `enable: false` until opted in).
- Skip entirely when the report lists no missing slots.

### Step 2.6 — 모듈 사전검사 초안 (harness 설치 시, skippable)

`vdev-config.modules[]`(모노레포 모듈 단위 사전검사 설정)의 초안을 작성한다.
harness 설치 여부를 먼저 판단하고, 그 결과에 따라 처리 방법이 달라진다.

**harness 감지**: `${CLAUDE_PROJECT_DIR}/docs/code-style/` 디렉터리 또는
`${CLAUDE_PROJECT_DIR}/services/*/CLAUDE.md` 파일이 하나라도 존재하면 harness 설치됨으로 본다.

**harness 가 설치돼 있는 경우** — SSOT 를 읽어 modules 초안을 작성한다:

1. `docs/code-style/<stack>.md` 의 "툴체인·설정"·"운영 관심사" 섹션과
   `services/*/CLAUDE.md`(모듈별 SSOT)를 읽어 모듈별 언어·도구를 파악한다.
2. 모듈마다 `path` 와 `checks`(lint/static/import_lint/test/security 중 해당
   언어에 있는 것만)를 채운다. 스캐폴드 하위 폴더(`tests/` 등)로 test 경로를 추정한다.
   - lint/static/import_lint/test → 모든 커밋(레이어2 vdev 게이트, 변경 모듈) 시점 적용
   - security → staging·release 승격 시점 적용
3. **SSOT 에서 도구를 못 찾거나 모호하면 `AskUserQuestion` 으로 확인**(추측 금지).
4. 작성한 초안은 `vdev-config.yaml` 의 `modules:` 섹션에 삽입한다(Edit — PyYAML
   round-trip 금지, 포맷/주석 보존). 리서치 결과는 기본값이며 사람이 config 에서
   수정한다; config 가 최종 권한이다.

**기존 `test.command`(구버전) 처리**: `vdev-config.yaml` 에 `test.command` 필드가
남아 있으면 그 명령을 `modules[].checks.test` 초안의 단서로 쓴다.
`test` 필드 자체는 폐기 예정임을 안내하되, **자동 제거하지 않는다**.

**harness 가 없는 경우** — `AskUserQuestion` 으로 modules 슬롯을 직접 입력받거나,
지금은 비워 두고 나중에 수동으로 채울지 선택하게 한다.
사용자가 스킵을 선택하면 `modules:` 를 빈 배열(`[]`)로 써 두고 진행한다.

### Step 3 — Teams webhook URLs + CLAUDE.md block (interactive — Claude, skippable)

1. Ask for the **personal** webhook URL (input-wait alerts). If provided:
   `python3 "${ROOT}/.claude/vway-kit/scripts/teams_alert.py" --set personal <URL>` →
   writes `${ROOT}/.claude/vway-kit/config/.teams-webhooks.local.json` (gitignored).
2. Ask for **team branch** channels (keys = branch names, e.g. integration /
   staging / production). For each provided: `--set <branch> <URL>` → writes
   `${ROOT}/.claude/vway-kit/config/teams-webhooks.json`. Empty URLs are skipped at
   send time, so partial setup is fine.
3. **If any Teams channel was configured**, offer (via `AskUserQuestion`, default
   yes) to add a **managed Teams-usage block** to the host `CLAUDE.md` so this
   repo's Claude alerts **right before presenting `AskUserQuestion`** — which the
   Notification hook does *not* cover (it only auto-fires on permission/idle waits).
   The alert directive must be **emphasized** (`IMPORTANT`/반드시) so the host model
   actually does it. Insert between the idempotent markers, **written in the same
   language as the existing host `CLAUDE.md`** (the Korean block below is the
   reference content — translate it to match the doc's language); if the markers
   already exist, **replace the block in place** (never duplicate). If
   `${ROOT}/CLAUDE.md` is absent, create it containing only this block. The script
   path is the host-installed copy `.claude/vway-kit/scripts/teams_alert.py` (not the
   plugin SOURCE). Skip entirely if no channel was set or the user declines:
   ````markdown
   <!-- vway-kit:teams BEGIN (managed by /vdev-init — edits inside are overwritten) -->
   ## Teams 알림 (vway-kit)

   **IMPORTANT — `AskUserQuestion`(또는 사용자 입력 대기)을 띄우기 직전, 반드시 먼저
   personal 채널로 알린다:**

   ```bash
   python3 "${CLAUDE_PROJECT_DIR:-$(git rev-parse --show-toplevel)}/.claude/vway-kit/scripts/teams_alert.py" \
     --channel personal --title "입력 대기" --text "<한 줄 작업 요약>"
   ```

   - **왜 수동인가** — `AskUserQuestion`은 Notification 훅 트리거가 아니다. 옵션 제시
     시점을 알리는 길은 이 호출뿐(권한/idle 대기는 훅이 자동 처리). 카드에
     `project @ branch`가 자동으로 붙는다.
   - **`CLAUDE_PROJECT_DIR` 폴백 권장** — 이 변수는 **훅 실행 시에만** 자동 주입된다.
     `teams_alert.py`는 미설정 시 git toplevel 로 폴백해 자가 치유하지만, 명시성을
     위해 수동 호출(`AskUserQuestion` 직전)에는 위처럼
     `:-$(git rev-parse --show-toplevel)` 폴백을 붙인다(cwd 가 저장소 밖일 때의 안전망).
   - **웹훅 설정** — `personal`은 `.claude/vway-kit/config/.teams-webhooks.local.json`
     (gitignored, 사용자별), 브랜치 채널(`dev`/`stage`/`main` 등)은
     `.claude/vway-kit/config/teams-webhooks.json`(git 추적, 팀 공용).
   - **보안 예외** — 추적되는 Power Automate URL(`sig=` 토큰 포함)은 누출이 아니라
     의도된 커밋이다. incoming webhook이라 최악도 채널 메시지 주입 수준(데이터 유출·
     권한 상승 없음) — 시크릿 스캐너 예외로 취급한다.
   <!-- vway-kit:teams END -->
   ````

### Step 4 — Teamer credentials (interactive — Claude)

Guide the user to run `python "${CLAUDE_PLUGIN_ROOT}/scripts/teamer_api.py" setup` in
their terminal for `/task-import` · `/task-sync`. Credentials are stored in the OS
keyring (service `vway-kit-teamer`) — **not** a plaintext file. Setup migrates an
existing `teamer_account.md` into the keyring and deletes it, or prompts via getpass.
Do **not** collect the password yourself (never via AskUserQuestion — that would put
it in model context). `keyring` 미설치 시 `python3 -m pip install keyring`.

## Completion report

Print a summary: the **Step 0** dependency status (python3 ≥3.8 / PyYAML required —
gate fails closed if missing; pre-commit / superpowers guidance), the **Step 2**
script report (copied / registered / pre-commit checked / **contract-test
workflow rendered-or-skipped** / skipped, + any missing
pre-commit hooks to add manually, + the auto-update auth guidance if surfaced),
the **Step 2.6** modules 초안 결과(harness 감지 여부 / 작성된 modules 수 / 미확인
항목 목록 / 스킵 여부), whether the
`CLAUDE.md` Teams block was added/updated/skipped, and the manual follow-ups
(`pre-commit install`, `Teamer keyring setup (teamer_api.py setup)`, swapping language-specific hooks). **If
the Teams block was inserted and the host `CLAUDE.md` already had a hand-written
Teams-alert rule (pre-vway-kit), advise removing it — the managed block supersedes it
(never delete the user's content automatically).** Then tell the user they can run
`/vdev`.

## Critical rules

1. **Install only with consent; never silently** — Step 0 detects via
   `check-deps.sh`, then installs **pip deps (PyYAML / pre-commit) only after
   `AskUserQuestion` approval**, adapting the method to the environment. python3 and
   the superpowers plugin are *guided*, not installed (OS-level / user-invoked).
   Never auto-install without asking, and never mutate machine-wide state
   (`git config --global`, `~`-level files) — the `GITHUB_TOKEN` / `insteadOf`
   override is suggested only.
2. **Idempotent** — `vdev_init_setup.py` skips existing settings.json hooks and
   .gitignore lines (match-then-skip); pre-commit config is created-if-absent, else
   only **reported** (missing hooks listed, never auto-merged — preserves the team's
   comments/format); interactive steps confirm before overwrite.
3. **teamer is mandatory** — never fall back to a hardcoded project/workitem; stop
   and ask.
4. **Secrets discipline** — Teamer credentials and the `personal` webhook stay in
   gitignored files under `.claude/vway-kit/config/`. Branch-channel webhooks
   (`.claude/vway-kit/config/teams-webhooks.json`) are **intentionally git-tracked**
   (incoming webhooks → worst case is channel-message injection; a secret-scanner
   exception, not a leak).
5. **Host writes go through `${CLAUDE_PROJECT_DIR}`**, plugin reads through
   `${CLAUDE_PLUGIN_ROOT}` — never write into the plugin directory.
6. **CLAUDE.md edits are a managed block only** — touch just the marked
   `vway-kit:teams` region; never rewrite or reflow the user's own content.
