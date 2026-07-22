# Skill Invocation Eval Harness Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Score whether each model-invoked skill actually fires when it should (and stays quiet when it shouldn't), and block a merge that lowers that score.

**Architecture:** `evals/run.py` drives `claude -p --plugin-dir <repo> --output-format stream-json` sessions over prompts in `evals/cases.yaml`, reads which skill fired from the stream, and writes rates to `evals/scores.json`. Measuring needs a model; **checking does not** — `tests/test_evals.py` only reads that JSON and hashes descriptions, so the gate runs in `uv run pytest` locally and in `unit-test.yml` at merge with no API key.

**Tech Stack:** Python 3.12, pytest, PyYAML, the `claude` CLI (headless `-p` mode).

> **Superseded — gate redesign (`fix/eval-gate-statistics`).** The `MIN_INVOKE` floor and the
> `RATCHET_DELTA` width described throughout this plan were both removed. The floor was circular
> (calibrated on the very distribution it then judged) and a global constant is wrong across
> skills whose proper firing rates differ by design; the fixed δ ignored that binomial noise
> scales with p (at n=15 it was 0.78–0.87σ, a 19.5–22.7% per-run false alarm). They are replaced
> by a per-skill `expect_invoke`/`expect_why` declaration in `cases.yaml` (a shortfall *warns*)
> and an exact-binomial ratchet in `scores.py` against a Jeffreys-shrunk baseline at a
> family-wise α (a regression *fails*, after a confirmation re-measure; new per-run false alarm
> 2.9–5.8%, sub-1% family-wise). `check`/`may_write` now take `expect` and `n_skills`;
> `scores.json` gained `invoke_hits`/`invoke_n`/`false_hits`/`false_n`. Read `evals/scores.py`
> and spec §6 for the current design — the constants and signatures restated below are the
> pre-redesign draft.

## Global Constraints

- **Not shipped to consumers.** `evals/` is not a plugin component — only `agents/`, `skills/`, `hooks/` are auto-discovered and distributed. Never add `evals/` to a manifest.
- **Never write into the plugin directory at runtime** — but `evals/` is a *development* artefact of this repo, not a runtime write. This constraint governs the shipped gate scripts, not this harness.
- **Scope = the 7 model-invoked skills**: `flow`, `doc-sync`, `integration`, `performance`, `playwright-scaffold`, `harness-insight`, `harness-authoring`. The 4 with `disable-model-invocation: true` (`flow-init`, `flow-uninstall`, `harness-init`, `harness-deployments`) are out of scope — their descriptions never reach the model, so "invocation failure" is not a thing that can happen to them.
- **Thresholds:** there is no invoke-rate floor any more (see the redesign banner above). Each skill declares `expect_invoke`/`expect_why` in `cases.yaml`, a significant shortfall *warns*, an undeclared skill *fails*, an all-zero baseline *fails*, and the ratchet enforces no regression via an exact binomial at `alpha_single(n_skills)`. `false_fire <= 0.20` (`MAX_FALSE_FIRE`) is unchanged. Read `evals/scores.py` for the current predicate rather than restating numbers here, because a copy in a plan is what a stale threshold looks like. **Reps:** 3 per case → 15 samples per arm. It was 5, cut to 3 for rate-limit budget: serially, 5 reps ran ~5.3h against a five-hour window, so every full measurement was guaranteed to be interrupted at least once. Eight-way concurrency has since removed that constraint (245 sessions in ~30 min; 5 reps would be ~46 min) — what keeps the default at 3 now is provenance and a predictable budget (the committed baseline's n), NOT sample-size safety: the exact-binomial ratchet compares k/n to k/n and is valid when n_new != n_base, which is exactly why cases.yaml supports a per-skill `reps:` override (see run.py's --reps comment; an earlier revision of this sentence claimed the mixing itself was unsound, contradicting the spec's own retraction). **Cases:** 5 happy + 5 negative per skill.
- **Style:** `ruff.toml` sets `line-length = 100`, `target-version = "py312"`, `select = ["E", "F", "I", "UP"]`. Every commit must pass `uv run ruff check && uv run ruff format --check`.
- **Commit type:** these files are development tooling, not consumer behaviour, so `test:`/`chore:` is correct — **not** `feat`/`fix`. The Plugin propagation discipline in `rules/risk-tiers.md` requires `feat`/`fix` only for changes that must reach consumers, and nothing here does.
- **Commit discipline:** this working copy has **no commit gate installed** (`.claude/settings.json` is absent), so commit directly with Conventional Commits. Never `--no-verify`. Work happens on `feature/skill-invocation-eval`, never on `dev`.
- **Sessions run in an isolated config dir.** `CLAUDE_CONFIG_DIR` points at an empty directory so the only plugin loaded is this one. This machine has a second installed plugin exposing seven identically-named skills; without isolation the baseline would encode one developer's plugin set rather than these descriptions.
- **Budget is rate limit, not money.** Sessions run on a subscription (`apiKeySource: "none"`), so `total_cost_usd` is a valuation, not a charge. `overageStatus: "rejected"` means hitting the five-hour cap **fails requests**. Any code that spends sessions must be resumable and must stop on a rate-limit event rather than recording the failure as a score.
- **The code is the SSOT, not this plan.** Every code block below is the *draft* that was written before implementation; where one disagrees with the file it names, the file is right and this plan is a record of intent. This applies in particular to the gate: the `MIN_INVOKE` floor, `RATCHET_DELTA` width and the sample-size arithmetic behind them were replaced by the declaration + exact-binomial ratchet (redesign banner above) — `evals/scores.py` (`ALPHA_FAMILY`, `alpha_single`, `binom_cdf`, `ratchet_trips`) is authoritative.
- **Encoding:** all `open()`/`read_text()`/`write_text()` calls pass `encoding="utf-8"`. The runtime here is Windows with a cp949 locale; omitting it corrupts the Korean in `cases.yaml` comments and silently changes hashes.

---

## Measured facts this plan is built on

Recorded 2026-07-18 by running the real CLI. Do not re-derive; do not assume beyond these.

| Fact | Evidence |
|---|---|
| `--plugin-dir <repo>` loads the working tree with no install | `init` event lists `harness-tier@inline` at the repo path |
| The `init` event enumerates available skills | `skills: [... "harness-tier:integration", ...]` — 11 entries |
| Without `--plugin-dir`, they are all absent | 95 skills listed, `harness-tier` entries: `[]`, plugin absent from `plugins` |
| Invocation is observable as a real event | `tool_use` block, `name: "Skill"`, `input: {"skill": "harness-tier:integration"}` |
| **The Skill call is NOT always the first tool_use** | In an empty cwd the agent ran `Bash(ls -la)` first; in a populated cwd `Skill` was first |
| A capped run exits 1 with `result.subtype == "error_max_turns"` | the stream still carries every event that happened |
| **Sessions are not billed** | `apiKeySource: "none"` — the CLI's `total_cost_usd` is a token valuation, not a charge |
| **The real limit is the rate-limit window** | `{"rateLimitType": "five_hour", "overageStatus": "rejected"}` — at the cap, requests *fail* |
| A session costs ~55s / 26k cache-write / 2.1k output | averaged over the two captured fixtures |
| **The isolated config dir does not disable permissions — it inherits `permissionMode: default`, which allows Bash but denies writes** | Measured 2026-07-19, one session, `CLAUDE_CONFIG_DIR` built by `isolated_config_dir` (contents: `['.credentials.json']`, no `settings.json`). `init` reports `permissionMode = default`. `Bash(ls -a)` returned `is_error=False` with real output; `Write(probe.txt)` returned `is_error=True`, `"Claude requested permissions to write to …, but you haven't granted it yet."` The session then ended `subtype=success is_error=False` — a denial does **not** abort the run, it costs one turn and the agent reports it. |
| **Invocation is noisy** | one happy prompt fired 6/10 (`p = 0.60`). At the shipped reps of 3 the arm is 15 samples, so `sd = sqrt(0.6*0.4/15) = 0.126`. (The `0.098` quoted elsewhere in this plan is the same `p` at the abandoned 25-sample size — see the reps 5→3 note in Global Constraints.) |
| **Eight-way load stretches a session to 58s** | 35 sessions took 252s at 8 concurrent; solo they ran ~45s |
| **`integration` fires at 0.20** | unchanged across a 3-turn cap, 6 turns, 30s, 45s and no timeout, before and after isolation |
| **A skill must stay model-invoked to be reachable from another skill** | `disable-model-invocation` leaves a skill reachable only by the user typing its name, so `harness-authoring`'s description exists for `harness-init/SKILL.md:110` first |
| **A skill that fires does so by the 3rd tool call** | at a 6-turn budget: 2 of 4 runs fired at call 3, the other 2 never fired and did the work by hand |
| **An empty `CLAUDE_CONFIG_DIR` isolates the plugin set** | 106 skills → 26, `plugins: ['harness-tier']`, the twin plugin absent |
| **A second installed plugin duplicates 7 of our skill names** | `vway-kit` 0.7.3 ships `doc-sync`, `harness-authoring`, `harness-init`, `harness-insight`, `integration`, `performance`, `playwright-scaffold` |
| **The plugin's own SessionStart hook fires inside eval sessions and argues for one of the seven** | `hooks/hooks.json` runs `inject-risk-tiers.sh` on `startup`, which injects `rules/risk-tiers.md` as `additionalContext`. That file names `flow` 39 times and instructs the agent to enter `/flow` as its first action. Isolating `CLAUDE_CONFIG_DIR` does not suppress it — the hook ships with the plugin under test, so `--plugin-dir` loads it. |
| **`CLAUDE_CONFIG_DIR` does not isolate MCP servers** | 30 `mcp__claude_ai_*` tools appeared in `init` despite the empty config dir |

**Three corrections follow, all folded into the spec by Task 1:**

- Spec §2 claimed "어떤 스킬이 불렸는지는 첫 tool_use에서 이미 결정된다." False — the runner scans **every** `tool_use` at a **3**-turn budget.
- Spec §7 was framed in dollars. It is now framed in sessions, wall-clock and rate-limit windows. A full run is **~8 hours serial**, not the "~50분" originally estimated.
- Spec §6's single-shot ratchet at a measured `δ = 3σ = 0.29` would **never fire** — tripping it requires `baseline > 1.09` once the `0.80` absolute threshold is applied. The ratchet is now `δ = 0.10` **plus a confirmation re-measure**: two independent drops are required, which cuts the false-alarm rate from `0.15` to `0.15² ≈ 0.02` without inflating δ.

---

## File Structure

| File | Responsibility |
|---|---|
| `evals/__init__.py` | Package marker, matching `scripts/__init__.py`. It is what makes `python -m evals.run` work: `pythonpath = ["."]` in `pyproject.toml` is a **pytest** setting only, so `python evals/run.py` would put `evals/` on `sys.path` instead of the repo root and `import evals.scores` would fail. Every invocation in this plan uses `-m`. |
| `evals/cases.yaml` | Data only: per-skill happy/negative prompts and the fixture each runs in |
| `evals/stream.py` | Read a stream-json transcript → what was *available* and what *fired*. No I/O beyond the string. |
| `evals/scores.py` | The baseline file's schema, `description_sha`, and the gate predicate. Imported by both the runner and the test. Only `check`/`may_write` are pure — `load` and `description_sha` read `scores.json` and every `skills/*/SKILL.md`. What the split guarantees is that nothing here spawns a session or reaches the network, not that nothing touches disk. |
| `evals/run.py` | The impure half: build fixtures, spawn `claude`, aggregate rates, enforce the ratchet on write |
| `evals/scores.json` | The committed baseline |
| `evals/fixtures/*.jsonl` | Real captured streams, so the parser is tested against the CLI's actual output |
| `tests/test_evals.py` | The gate: cases.yaml schema + thresholds + freshness, all model-free |
| `tests/test_skills.py` | Gains one test: SKILL.md length cap |

`scores.py` holds the gate predicate rather than `test_evals.py` because the runner needs the same predicate to decide whether a fresh measurement may be written. One definition, two callers.

---

### Task 1: Lock the measured mechanics and pick the ratchet tolerance

The two numbers this harness gates on — the turn budget and δ — are currently guesses. Everything downstream reads them, so they get measured first.

**Files:**
- Create: `evals/fixtures/stream-invoked.jsonl`
- Create: `evals/fixtures/stream-quiet.jsonl`
- Modify: `docs/superpowers/specs/2026-07-18-skill-invocation-eval-design.md`

**Interfaces:**
- Produces: two stream fixtures Task 4 parses; a measured `RATCHET_DELTA` value Task 5 hard-codes.

- [ ] **Step 1: Capture a stream where a plugin skill fires**

```bash
mkdir -p /tmp/evalcap && cd /tmp/evalcap
printf '{"name":"probe","scripts":{"dev":"vite"}}\n' > package.json
claude -p "run this project's integration tests" \
  --output-format stream-json --verbose --max-turns 3 \
  --plugin-dir /c/Work/llm_ai/harness-tier > invoked.jsonl < /dev/null
```

Expected: exit 1 (turn cap). Confirm the capture is usable — note the check looks for a
`tool_use` block, **not** for the string `harness-tier:integration`. That string is in every
stream regardless, because the `init` event lists the skill as *available*:

```bash
cat > hit.py <<'PY'
import json, sys

fired = []
for line in sys.stdin:
    try:
        event = json.loads(line)
    except json.JSONDecodeError:
        continue
    if event.get("type") == "assistant":
        for block in event.get("message", {}).get("content", []):
            if block.get("name") == "Skill":
                fired.append((block.get("input") or {}).get("skill"))
print(1 if "harness-tier:integration" in fired else 0)
PY
python hit.py < invoked.jsonl
```

Expected: `1`. Step 4 reuses this script.

- [ ] **Step 2: Capture a stream where nothing fires**

```bash
cd /tmp/evalcap
claude -p "Explain the difference between a Python list and a tuple." \
  --output-format stream-json --verbose --max-turns 3 \
  --plugin-dir /c/Work/llm_ai/harness-tier > quiet.jsonl < /dev/null
grep -c '"name":"Skill"' quiet.jsonl          # expect 0
grep -c 'harness-tier:' quiet.jsonl           # expect >= 1 — the init event still lists them
```

That second count is the point of this fixture: available-but-silent must be distinguishable from not-available.

- [ ] **Step 3: Copy both into the repo**

```bash
mkdir -p /c/Work/llm_ai/harness-tier/evals/fixtures
cp /tmp/evalcap/invoked.jsonl /c/Work/llm_ai/harness-tier/evals/fixtures/stream-invoked.jsonl
cp /tmp/evalcap/quiet.jsonl   /c/Work/llm_ai/harness-tier/evals/fixtures/stream-quiet.jsonl
```

- [ ] **Step 4: Measure run-to-run variance on one case**

Run the same happy prompt 10 times and count how often the skill actually fires. This is the only way to know whether δ = 0.10 is a real tolerance or noise.

```bash
cd /tmp/evalcap
for i in $(seq 1 10); do
  claude -p "run this project's integration tests" \
    --output-format stream-json --verbose --max-turns 3 \
    --plugin-dir /c/Work/llm_ai/harness-tier < /dev/null 2>/dev/null \
  | python hit.py
done | tee hits.txt
```

Spends 10 sessions, ~9 minutes. No money — see Global Constraints.

The parsing matters here: `grep -c 'harness-tier:integration'` would return 1 on **every**
run, because the `init` event lists the skill as available whether or not it is ever
invoked. That would measure p = 1.00 and a δ of zero variance — a confidently wrong number.

- [ ] **Step 5: Compute δ from the measurement**

```bash
cd /tmp/evalcap && python -c "
import statistics
hits=[int(x) for x in open('hits.txt').read().split()]
p=sum(hits)/len(hits)
sd_run=statistics.pstdev(hits)                 # per-session
sd_25=(p*(1-p)/25)**0.5 if 0<p<1 else 0.0      # of a 25-sample rate
print(f'p={p:.2f} per-session sd={sd_run:.3f} sd of a 25-sample rate={sd_25:.3f}')
print(f'delta = max(0.10, {3*sd_25:.3f}) = {max(0.10, round(3*sd_25,2)):.2f}')
"
```

**Outcome (recorded 2026-07-18, commit `104a553`):** `hits = 1,1,0,0,1,1,0,1,1,0` → `p = 0.60`, per-session `sd = 0.490`. At the 25-sample arm assumed then, the rate `sd = 0.098` and `3σ = 0.29`; at the shipped 15-sample arm (reps 3) it is `sd = 0.126` and `3σ ≈ 0.38`.

**That result rejected the single-shot design rather than parameterising it** — but the reason it gave has since expired, and the replacement matters more than the original. As written, the argument was that a wide `δ` is *shadowed*: tripping it needs `measured < baseline − 0.29` while passing the absolute threshold needs `measured ≥ 0.80`, together requiring `baseline > 1.09`. That held only while the threshold was the invented 0.80. With the floor calibrated to `scores.MIN_INVOKE`, the same arithmetic gives `baseline > MIN_INVOKE + 0.38`, which **five of the seven measured skills satisfy** — so a wide `δ` is no longer shadowed, it is simply *blind*: a skill could fall from 0.67 to 0.28, clear the floor, and never trip the ratchet.

The conclusion (`δ = 0.10` plus a confirmation re-measure) survives, on the noise argument alone: at 15 samples `δ = 0.10` is ~0.8σ, so a single reading that low is noise ~21% of the time and two independent ones ~4.5%. **Do not re-derive a wider `δ` from the shadowing argument above — it is recorded here as history, not as justification.**

The resolution keeps `δ = 0.10` and adds a **confirmation re-measure** — on a drop past δ, that one skill is measured again, and only a second drop fails. `δ = 0.10` is ≈ 1σ, so a single false alarm has probability `0.15`; requiring two independent drops gives `0.15² ≈ 0.02`. Task 5 hard-codes `RATCHET_DELTA = 0.10`; Task 6 implements the confirmation pass.

- [ ] **Step 6: Fold the corrections into the spec**

In `docs/superpowers/specs/2026-07-18-skill-invocation-eval-design.md`, replace the §2 paragraph that begins `**세션은 반드시 \`--max-turns 1\`로 잘라야 한다.**` with:

```markdown
**세션은 `--max-turns 3`으로 자른다.** 무제한이면 에이전트가 스킬을 로드한 뒤 실제 작업을
이어가 13턴까지 돌지만, 1턴은 반대로 **너무 짧다** — 빈 디렉터리에서는 에이전트가 `ls`부터
하고 스킬은 그다음에 부른다(2026-07-18 실측). 따라서 러너는 첫 tool_use만 보지 않고
**스트림의 모든 tool_use를 훑는다**. 1턴으로 자르면 발동했을 스킬을 미발동으로 기록하는
거짓 음성이 생기고, 그 오염은 invoke_rate에 그대로 남는다.

**`init` 이벤트가 사용 가능한 스킬 목록을 준다.** 이것이 애블레이션 OFF 팔의 검증 수단이자
"플러그인이 아예 안 실렸다"를 "description이 발동을 못 시켰다"와 구별하는 수단이다. 둘 다
점수는 0.0이지만 원인이 전혀 다르다.

| 팔 | `init.skills`의 `harness-tier:*` | 실측 |
|---|---|---|
| ON (`--plugin-dir`) | 11개 | 확인 |
| OFF (`--plugin-dir` 없음) | 0개 (전체 95개 중) | 확인 |
```

Then replace the cost table rows in §2 with the measured 3-turn numbers.

> Superseded after execution: §7 was subsequently rewritten from dollars to sessions,
> wall-clock and rate-limit windows — see the Measured facts section above.

- [ ] **Step 7: Commit**

```bash
git add evals/fixtures docs/superpowers/specs/2026-07-18-skill-invocation-eval-design.md
git commit -m "test: capture real eval streams and correct the measured mechanics

--max-turns 1 cuts the session before the Skill call when the cwd is empty,
so the runner scans every tool_use at a 3-turn budget instead. The init event
enumerates available skills, which is what separates a description regression
from a plugin that never loaded."
```

---

### Task 2: Cap SKILL.md length

Independent of the eval harness and small. Landing it first keeps it out of the way.

**Files:**
- Modify: `tests/test_skills.py`

**Interfaces:**
- Consumes: `SKILLS`, `SKILL_IDS` (already defined at the top of the file)
- Produces: nothing other tasks use

- [ ] **Step 1: Write the failing test**

Append to `tests/test_skills.py`, directly after `test_description_fits_the_listing_cap`:

```python
# A skill that outgrows this stops being read and starts being skimmed — including by the
# agent running it. 500 is the practical ceiling; the longest here is flow-init at 349.
SKILL_LINE_CAP = 500


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_skill_stays_short_enough_to_be_read(skill: Path):
    lines = len(skill.read_text(encoding="utf-8").splitlines())
    assert lines <= SKILL_LINE_CAP, (
        f"{skill.parent.name}: {lines} lines exceeds {SKILL_LINE_CAP}. Disclose reference "
        f"material into references/ and link it rather than growing SKILL.md"
    )
```

- [ ] **Step 2: Run it and confirm it passes, then prove it can fail**

```bash
uv run pytest tests/test_skills.py -k stays_short -q
```

Expected: `11 passed`.

A test that has never been red proves nothing. Force it:

```bash
python - <<'PY'
import re, pathlib
p = pathlib.Path("tests/test_skills.py")
t = p.read_text(encoding="utf-8")
p.write_text(t.replace("SKILL_LINE_CAP = 500", "SKILL_LINE_CAP = 100"), encoding="utf-8")
PY
uv run pytest tests/test_skills.py -k stays_short -q
```

Expected: failures naming `flow-init: 349 lines exceeds 100`. Restore:

```bash
python - <<'PY'
import pathlib
p = pathlib.Path("tests/test_skills.py")
p.write_text(p.read_text(encoding="utf-8").replace("SKILL_LINE_CAP = 100", "SKILL_LINE_CAP = 500"), encoding="utf-8")
PY
uv run pytest tests/test_skills.py -k stays_short -q
```

Expected: `11 passed`.

- [ ] **Step 3: Lint and commit**

```bash
uv run ruff check && uv run ruff format --check
git add tests/test_skills.py
git commit -m "test: cap SKILL.md at 500 lines"
```

---

### Task 3: Write the case file

**Files:**
- Create: `evals/__init__.py`
- Create: `evals/cases.yaml`
- Create: `tests/test_evals.py`

**Interfaces:**
- Produces: `evals/cases.yaml` with top-level keys `version` (int) and `skills` (mapping). Each skill maps to `{fixture: str|null, happy: [str|{prompt,fixture}], negative: [...]}`. Tasks 5 and 6 read it; the skill set here is the single source of truth for which skills the gate covers.

- [ ] **Step 1: Create the package marker**

```bash
printf '' > evals/__init__.py
```

(`scripts/__init__.py` is empty too — the repo's tests import `scripts.foo`, and `pythonpath = ["."]` in `pyproject.toml` makes `evals.foo` resolve the same way.)

- [ ] **Step 2: Write `evals/cases.yaml`**

`fixture` names a scenario in `scripts/skill_sandbox.py` (`--list` shows them); `null` means an empty directory. A per-case `fixture:` overrides the skill's default when a prompt presumes a different project shape.

```yaml
# Prompts that decide whether each model-invoked skill fires. Data only — evals/run.py
# supplies the mechanics.
#
# Negative cases carry the skill's own vocabulary and then ask for something else, because
# that is where over-firing actually happens. "Explain Python decorators" catches nothing —
# no description was ever going to fire on it, so a false_fire of 0.00 against prompts like
# that measures the test's weakness rather than the skill's precision. Each skill keeps at
# most one deliberately far-field case, which checks the opposite failure: a description so
# broad it fires on anything.
#
# The 4 skills with `disable-model-invocation: true` are absent on purpose. Their
# descriptions never enter the model's context, so there is no invocation to measure and a
# case file entry would report coverage that does not exist.
version: 1

skills:
  integration:
    fixture: custom-testdir
    happy:
      - Run the end-to-end tests for this project and tell me what fails.
      - I need to verify this app works end to end — there is no automation yet.
      - Check that the whole flow works in a real browser, not just unit tests.
      - Can you do integration verification on this repo?
      - Set up e2e coverage for this project.
    negative:
      - This endpoint takes 900ms under load — find out why.
      - Add a data-testid attribute to the checkout button so tests can target it.
      - Write a unit test for the date parser in src/util.js.
      - What does the --headed flag do in Playwright?
      - Bump the vite dependency to the latest minor.

  performance:
    fixture: perf-n-plus-one
    happy:
      - This list endpoint is slow — profile it and tell me what is wrong.
      - Check this codebase for N+1 query patterns.
      - I need to load-test the API against a 200ms p95 SLO.
      - The React table re-renders constantly. Find the cause.
      - Is this algorithm going to hold up at 10x the data?
    negative:
      - Run the integration suite.
      - The build takes four minutes. Speed it up.
      - Add a new field to the user model.
      - Rename the slow_query helper to fetch_orders.
      - Set up the first Playwright test for this app.

  doc-sync:
    fixture: doc-sync-drift
    happy:
      - I renamed the config keys in src/settings.py — check the docs still match.
      - Are the docs in this repo consistent with each other?
      - This module has no local CLAUDE.md.
      - I edited the README; make sure nothing else contradicts it now.
      - Check for documentation drift after my last change.
    negative:
      - Run the e2e tests.
      - Profile the slow endpoint.
      - Write a new README section explaining the install steps.
      - Translate CONTRIBUTING.md into Korean.
      - Rename the variable foo to bar in one file.

  playwright-scaffold:
    fixture: empty-web
    happy:
      - This web app has no tests at all — get the first one in place.
      - Set up the first Playwright case for this project.
      - There are zero e2e cases here. Create a smoke test.
      - Bootstrap browser testing for this frontend.
      - Add an initial Playwright smoke test that checks the app loads.
    negative:
      # The one anti-trigger its description names outright — an existing suite.
      - prompt: Add a checkout scenario to the existing Playwright suite.
        fixture: custom-testdir
      - prompt: Run the Playwright tests.
        fixture: custom-testdir
      - Why would a Playwright test be flaky?
      - Install Playwright in this project.
      - Write a unit test for the reducer.

  flow:
    fixture: null
    happy:
      - Add a --verbose flag to the CLI.
      - Fix the crash when the config file is missing.
      - Commit these changes.
      - Promote dev to stage.
      - Refactor the parser into its own module.
    negative:
      # flow's description claims ALL development work, so its negatives are the read-only
      # questions that sit closest to that claim without being a change.
      - What does the error ENOTEMPTY mean?
      - Explain the difference between rebase and merge.
      - Which Python version is this project on?
      - Summarize what this repository does.
      - List the files in src/.

  harness-insight:
    fixture: null
    happy:
      - Give me insights for the last 7 days.
      - Summarize what I worked on this week.
      - Pull out harness candidates from the last two weeks.
      - Clean up the project memory.
      - What patterns showed up in my sessions over the last month?
    negative:
      # Both of the first two share a surface feature with the happy set — "summarize" and
      # a time window — while pointing at something other than the session transcript.
      - Summarize what this file does.
      - Show me the git log for the last week.
      - What did we decide about the retry policy yesterday?
      - What did the last commit change?
      - Delete the stale notes in docs/scratch/.

  harness-authoring:
    # Reached two ways: directly, and via /harness-init's subagent fan-out. Only the direct
    # path is measurable in one session, so that is what these cases cover.
    fixture: null
    happy:
      - Write a skill for this project that runs the deploy checklist.
      - Author a CLAUDE.md for this repo.
      - Create an agent definition for reviewing migrations.
      - I need a rules file that fires when someone edits the schema.
      - Draft the technical docs for this service's harness.
    negative:
      - Write a Python function that parses ISO dates.
      - Write the README for this library.
      - Explain what a Claude Code skill is.
      - Fix the failing test.
      - Add type hints to this module.
```

- [ ] **Step 3: Write the failing schema test**

Create `tests/test_evals.py`:

```python
"""The model-free half of the eval harness.

Measuring spends hours of rate-limit budget; checking spends nothing. Keeping the check
here means `uv run pytest` and `unit-test.yml` both enforce it with no new wiring.
"""

import re
from pathlib import Path

import pytest
import yaml

import scripts.skill_sandbox as sandbox

REPO = Path(__file__).resolve().parent.parent
CASES = yaml.safe_load((REPO / "evals/cases.yaml").read_text(encoding="utf-8"))
SKILLS = sorted(CASES["skills"])

HAPPY_CASES = 5
NEGATIVE_CASES = 5


def frontmatter(name: str) -> dict:
    text = (REPO / f"skills/{name}/SKILL.md").read_text(encoding="utf-8")
    return yaml.safe_load(re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL).group(1))


def test_cases_cover_every_model_invoked_skill_and_nothing_else():
    """A skill with `disable-model-invocation` never puts its description in front of the
    model, so it cannot fail to be invoked — a case for it would report coverage that does
    not exist. The reverse gap is worse: a model-invoked skill with no cases is unmeasured
    while the suite is green."""
    invocable = {
        p.parent.name
        for p in REPO.glob("skills/*/SKILL.md")
        if not frontmatter(p.parent.name).get("disable-model-invocation")
    }
    assert set(SKILLS) == invocable, (
        f"cases.yaml covers {sorted(SKILLS)} but the model-invoked skills are "
        f"{sorted(invocable)}"
    )


@pytest.mark.parametrize("name", SKILLS)
def test_each_skill_has_the_full_case_set(name: str):
    entry = CASES["skills"][name]
    assert len(entry["happy"]) == HAPPY_CASES, f"{name}: expected {HAPPY_CASES} happy cases"
    assert len(entry["negative"]) == NEGATIVE_CASES, (
        f"{name}: expected {NEGATIVE_CASES} negative cases"
    )


@pytest.mark.parametrize("name", SKILLS)
def test_case_fixtures_name_a_real_sandbox_scenario(name: str):
    """A typo'd fixture name would silently fall back to an empty directory and the run
    would still produce a number — a wrong one, indistinguishable from a real score."""
    entry = CASES["skills"][name]
    fixtures = {entry.get("fixture")}
    for case in entry["happy"] + entry["negative"]:
        if isinstance(case, dict):
            fixtures.add(case.get("fixture"))
    for f in fixtures - {None}:
        assert f in sandbox.BY_NAME, f"{name}: unknown fixture {f!r}"
```

- [ ] **Step 4: Run the tests**

```bash
uv run pytest tests/test_evals.py -q
```

Expected: `15 passed` (1 + 7 + 7).

- [ ] **Step 5: Prove the coverage test can fail**

```bash
python - <<'PY'
import pathlib
p = pathlib.Path("evals/cases.yaml")
t = p.read_text(encoding="utf-8")
p.write_text(t.replace("\n  performance:", "\n  performance-typo:"), encoding="utf-8")
PY
uv run pytest tests/test_evals.py -q
```

Expected: `test_cases_cover_every_model_invoked_skill_and_nothing_else` FAILS. Then `git checkout evals/cases.yaml` and re-run — `15 passed`.

- [ ] **Step 6: Commit**

```bash
uv run ruff check && uv run ruff format --check
git add evals/__init__.py evals/cases.yaml tests/test_evals.py
git commit -m "test: add the eval case file and its schema guards"
```

---

### Task 4: Read what a session actually did

**Files:**
- Create: `evals/stream.py`
- Modify: `tests/test_evals.py`

**Interfaces:**
- Consumes: `evals/fixtures/stream-invoked.jsonl`, `evals/fixtures/stream-quiet.jsonl` (Task 1)
- Produces: `observe(stream: str) -> Observation`, where `Observation` has `available: list[str]`, `fired: list[str]` (both plugin-local names, prefix stripped), `turns_exhausted: bool` and `rate_limited: bool`

- [ ] **Step 1: Write the failing test**

First add the import to the **top** import block of `tests/test_evals.py`, beside
`import scripts.skill_sandbox as sandbox` — ruff's `E402` rejects a module-level import
placed further down, so appending it with the tests would fail `ruff check`:

```python
import evals.stream as stream
```

Then append the tests:

```python
FIXTURES = REPO / "evals/fixtures"


def test_observe_sees_a_skill_that_fired():
    obs = stream.observe((FIXTURES / "stream-invoked.jsonl").read_text(encoding="utf-8"))
    assert "integration" in obs.fired
    assert "integration" in obs.available


def test_observe_separates_available_from_fired():
    """Both a broken --plugin-dir and a description that stopped working score 0.0. Only
    the availability list tells them apart, and confusing the two would have the harness
    report a regression every time the path was wrong."""
    obs = stream.observe((FIXTURES / "stream-quiet.jsonl").read_text(encoding="utf-8"))
    assert obs.fired == []
    assert "integration" in obs.available


def test_observe_survives_a_truncated_final_line():
    text = (FIXTURES / "stream-invoked.jsonl").read_text(encoding="utf-8")
    obs = stream.observe(text + '{"type":"assis')
    assert "integration" in obs.fired


def test_observe_tells_an_outright_failure_from_a_turn_cap():
    """Both report is_error. Only the subtype separates them, and conflating the two would
    either abort every capped run or silently score an unauthenticated session as a miss."""
    capped = (FIXTURES / "stream-invoked.jsonl").read_text(encoding="utf-8")
    assert stream.observe(capped).turns_exhausted
    assert not stream.observe(capped).errored
    failed = json.dumps({"type": "result", "subtype": "success", "is_error": True})
    assert stream.observe(failed).errored


def test_observe_reports_a_rate_limited_session():
    """A full run outlasts the five-hour window and `overageStatus` is `rejected`, so
    sessions will start failing mid-measurement. A refused session that gets recorded as
    "the skill did not fire" writes a fabricated score into the baseline."""
    healthy = (FIXTURES / "stream-invoked.jsonl").read_text(encoding="utf-8")
    assert not stream.observe(healthy).rate_limited
    blocked = healthy + json.dumps(
        {"type": "rate_limit_event", "rate_limit_info": {"status": "rejected"}}
    )
    assert stream.observe(blocked).rate_limited
```

`json` joins the top import block.

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_evals.py -k observe -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'evals.stream'`.

- [ ] **Step 3: Write the implementation**

Create `evals/stream.py`:

```python
"""Read a `claude -p --output-format stream-json` transcript.

Two questions, both answered from events rather than from anything the model says about
itself: which plugin skills the session was *offered* (the `init` event) and which ones it
actually *invoked* (`tool_use` blocks named `Skill`).
"""

import json
from dataclasses import dataclass, field

PLUGIN = "harness-tier"
_PREFIX = f"{PLUGIN}:"


@dataclass
class Observation:
    available: list[str] = field(default_factory=list)
    fired: list[str] = field(default_factory=list)
    turns_exhausted: bool = False
    rate_limited: bool = False
    errored: bool = False
    completed: bool = False
    tool_calls: int = 0


def _local(name: str) -> str | None:
    return name[len(_PREFIX) :] if name.startswith(_PREFIX) else None


def observe(text: str) -> Observation:
    obs = Observation()
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            # A partial trailing line is how a killed process ends. Everything before it
            # already happened, so dropping the run over it would lose a real result.
            continue
        if event.get("subtype") == "init":
            obs.available = [s for n in event.get("skills") or [] if (s := _local(n))]
        elif event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") != "tool_use":
                    continue
                # How far the session got before it was cut. A kill after several tool calls
                # is a session that had its chance and did not take it; a kill after none is
                # a session that never got to say.
                obs.tool_calls += 1
                if block.get("name") == "Skill":
                    name = _local((block.get("input") or {}).get("skill", ""))
                    if name:
                        obs.fired.append(name)
        elif event.get("type") == "rate_limit_event":
            status = (event.get("rate_limit_info") or {}).get("status")
            if status and status != "allowed":
                obs.rate_limited = True
        elif event.get("type") == "result":
            obs.turns_exhausted = event.get("subtype") == "error_max_turns"
            # A turn cap reports is_error too, so the cap has to be excluded before the flag
            # means anything. What is left is a session that failed outright — above all an
            # unauthenticated config dir, which still emits a well-formed init event and
            # would otherwise be scored as "the skill did not fire".
            obs.errored = event.get("subtype") == "success" and bool(event.get("is_error"))
            # Sessions are killed on a timeout, and a killed one carries no result event at
            # all. Without this the runner cannot tell "the skill did not fire" from "the
            # session never got far enough to say".
            obs.completed = True
    return obs
```

- [ ] **Step 4: Run to verify it passes**

```bash
uv run pytest tests/test_evals.py -q
```

Expected: `20 passed`.

- [ ] **Step 5: Commit**

```bash
uv run ruff check && uv run ruff format --check
git add evals/stream.py tests/test_evals.py
git commit -m "test: read invocation and availability out of a stream-json session"
```

---

### Task 5: The baseline file and the gate predicate

**Files:**
- Create: `evals/scores.py`
- Create: `evals/scores.json`
- Modify: `tests/test_evals.py`

**Interfaces:**
- Consumes: `evals/cases.yaml` (skill list)
- Produces:
  - `description_sha(name: str) -> str`
  - `load(path: Path | None = None) -> dict`
  - `Verdict` — `NamedTuple(level: str, message: str)`, `level` one of `"ok" | "warn" | "confirm" | "fail"`
  - (post-redesign) `check(name, entry, sha, expect: float | None, n_skills: int) -> Verdict`
  - (post-redesign) `may_write(name, new, old, accepted, confirmed=False, *, n_skills) -> Verdict`
  - (post-redesign) `alpha_single(n_skills)`, `binom_cdf(k, n, p)`, `ratchet_trips(k_new, n_new, k_base, n_base, alpha)`; constants `MAX_FALSE_FIRE = 0.20`, `ALPHA_FAMILY = 0.05` (the `MIN_INVOKE`/`RATCHET_DELTA` in the draft below are removed)

- [ ] **Step 1: Write the failing test**

Add to the **top** import block of `tests/test_evals.py` (same `E402` reason as Task 4):

```python
import evals.scores as scores
```

Then append the tests:

```python
OK = {"description_sha": "x", "invoke_rate": 0.92, "false_fire": 0.08}


def test_unmeasured_skill_warns_rather_than_failing():
    """Failing here would paint `uv run pytest` red from the day the harness lands, and a
    suite that is red by default stops being read as a signal at all. The same holds for
    every newly added skill."""
    assert scores.check("integration", None, "x").level == "warn"


def test_the_gate_surfaces_a_warning_rather_than_passing_in_silence():
    """A warn that prints nothing is a pass, and an unmeasured skill would look measured."""
    with pytest.warns(UserWarning, match="not measured"):
        gate("integration", None, "x")


def test_a_healthy_measurement_passes():
    assert scores.check("integration", OK, "x").level == "ok"


def test_a_stale_measurement_fails():
    """Without this the harness is decorative: edit the description, keep the old green
    number, merge. The score would no longer describe the skill it is attached to."""
    v = scores.check("integration", OK, "different-sha")
    assert v.level == "fail"
    assert "re-measure" in v.message


@pytest.mark.parametrize(
    "entry,reason",
    [
        ({**OK, "invoke_rate": 0.24}, "invoke_rate"),
        ({**OK, "false_fire": 0.21}, "false_fire"),
    ],
)
def test_absolute_thresholds_fail(entry: dict, reason: str):
    v = scores.check("integration", entry, "x")
    assert v.level == "fail"
    assert reason in v.message


def test_a_score_on_the_floor_passes():
    """0.25 is the floor, not the first failing value — an off-by-one here would quietly
    fail every skill sitting exactly on the line."""
    assert scores.check("integration", {**OK, "invoke_rate": 0.25}, "x").level == "ok"


def test_an_accepted_drop_needs_a_recorded_reason():
    entry = {**OK, "lowered_from": 0.95}
    assert scores.check("integration", entry, "x").level == "fail"
    entry["lowered_reason"] = "traded for a lower false_fire"
    assert scores.check("integration", entry, "x").level == "ok"


def test_a_first_drop_asks_for_confirmation_rather_than_failing():
    """25 samples cannot separate a 0.10 drop from noise — measured sd is 0.098. Failing on
    one reading would either cry wolf at delta=0.10 or, at the 3-sigma delta of 0.29, never
    fire at all because the 0.80 absolute threshold already shadows it."""
    old = {"invoke_rate": 0.95, "false_fire": 0.05}
    new = {"invoke_rate": 0.95 - scores.RATCHET_DELTA - 0.01, "false_fire": 0.05}
    assert scores.may_write("integration", new, old, accepted=False).level == "confirm"


def test_a_confirmed_drop_fails_and_acceptance_overrides_it():
    old = {"invoke_rate": 0.95, "false_fire": 0.05}
    new = {"invoke_rate": 0.95 - scores.RATCHET_DELTA - 0.01, "false_fire": 0.05}
    assert scores.may_write("integration", new, old, accepted=False, confirmed=True).level == "fail"
    assert scores.may_write("integration", new, old, accepted=True).level == "ok"


def test_the_ratchet_tolerates_noise_and_welcomes_a_rise():
    old = {"invoke_rate": 0.95, "false_fire": 0.05}
    within = {"invoke_rate": 0.95 - scores.RATCHET_DELTA, "false_fire": 0.05}
    higher = {"invoke_rate": 1.0, "false_fire": 0.0}
    assert scores.may_write("integration", within, old, accepted=False).level == "ok"
    assert scores.may_write("integration", higher, old, accepted=False).level == "ok"


def gate(name: str, entry: dict | None, sha: str) -> None:
    """Apply a verdict: fail loudly, warn visibly, pass quietly."""
    v = scores.check(name, entry, sha)
    if v.level == "fail":
        pytest.fail(v.message)
    if v.level == "warn":
        warnings.warn(v.message, stacklevel=2)


@pytest.mark.parametrize("name", SKILLS)
def test_the_committed_baseline_passes_the_gate(name: str):
    """The gate itself. Everything above tests the predicate; this applies it to the file
    that is actually committed."""
    baseline = scores.load()
    gate(name, baseline.get("skills", {}).get(name), scores.description_sha(name))
```

`warnings` joins the top import block too.

- [ ] **Step 2: Run to verify it fails**

```bash
uv run pytest tests/test_evals.py -k "scores or baseline or ratchet or threshold or measurement or accepted or unmeasured" -q
```

Expected: FAIL — `ModuleNotFoundError: No module named 'evals.scores'`.

- [ ] **Step 3: Write the implementation**

Create `evals/scores.py`. `RATCHET_DELTA = 0.10` is settled — see Task 1 Step 5 for why the measured 3σ value of 0.29 was rejected in favour of δ = 0.10 plus a confirmation re-measure.

```python
"""The eval baseline and the predicate that guards it.

Split from `run.py` because the two halves have opposite costs: producing a score spends
hours of rate-limit budget across hundreds of real CLI sessions, while judging one needs a
JSON file and a hash. Only the cheap half belongs in `pytest`.
"""

import hashlib
import json
import re
from pathlib import Path
from typing import NamedTuple

import yaml

REPO = Path(__file__).resolve().parent.parent
SCORES = REPO / "evals/scores.json"

# Calibrated 2026-07-19 from the first trustworthy run of all seven skills, which came in at
# [0.13, 0.27, 0.53, 0.60, 0.67, 1.00, 1.00]. The 0.80 originally written here was a guess and
# five of seven would have failed it.
#
# 0.25 is a floor of meaning rather than of ambition: below one firing in four, having the
# skill is hard to tell from not having it. It also sits clear of the middle of the
# distribution, where 15 samples cannot separate 0.53 from 0.67 (sd ~0.13) and any line drawn
# would be arbitrary. Raising the bar for the skills that clear it is the ratchet's job.
MIN_INVOKE = 0.25
# This one stays live. Whatever the right firing rate turns out to be, a skill that grabs more
# than a fifth of the prompts meant for its neighbours is wrong at any calibration.
MAX_FALSE_FIRE = 0.20

# About one standard deviation of a 25-sample rate (measured sd = 0.098). A single reading
# this far below baseline is noise 15% of the time, which is why a drop asks for a second
# measurement instead of failing: two independent drops land at 0.15^2. Widening delta to
# 3 sigma (0.29) instead would silence the ratchet completely — the 0.80 absolute threshold
# already catches everything a 0.29 drop could.
RATCHET_DELTA = 0.10


class Verdict(NamedTuple):
    level: str  # "ok" | "warn" | "confirm" | "fail"
    message: str


def description_sha(name: str) -> str:
    """Hash the description *only*. Invocation is decided by the description, so demanding
    a re-measurement after every body edit would make the freshness check pure noise — and
    a noisy gate is one people learn to skip."""
    text = (REPO / f"skills/{name}/SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if m is None:
        # Without a guard this is an AttributeError on None, which reads like a bug in the
        # harness rather than what it is: a skill whose frontmatter stopped parsing.
        raise ValueError(f"skills/{name}/SKILL.md has no frontmatter block")
    front = yaml.safe_load(m.group(1))
    return hashlib.sha256(front["description"].encode("utf-8")).hexdigest()[:12]


def load(path: Path | None = None) -> dict:
    path = path or SCORES
    if not path.exists():
        return {"skills": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def check(name: str, entry: dict | None, sha: str, exempt_floor: bool = False) -> Verdict:
    if entry is None:
        return Verdict("warn", f"{name}: not measured yet — run python -m evals.run")
    if entry.get("description_sha") != sha:
        return Verdict("fail", f"{name}: description changed since the score — re-measure")
    # `exempt_floor` is for a skill whose primary reach is another skill invoking it. Its
    # autonomous rate is a measurement of the secondary path, so the floor would judge the
    # wrong thing. The ratchet is unaffected — a drop from today's number still fails.
    if not exempt_floor and entry["invoke_rate"] < MIN_INVOKE:
        return Verdict("fail", f"{name}: invoke_rate {entry['invoke_rate']:.2f} < {MIN_INVOKE}")
    if entry["false_fire"] > MAX_FALSE_FIRE:
        return Verdict("fail", f"{name}: false_fire {entry['false_fire']:.2f} > {MAX_FALSE_FIRE}")
    if "lowered_from" in entry and not entry.get("lowered_reason"):
        return Verdict("fail", f"{name}: lowered_from recorded with no lowered_reason")
    return Verdict("ok", f"{name}: ok")


def may_write(
    name: str, new: dict, old: dict | None, accepted: bool, confirmed: bool = False
) -> Verdict:
    """The ratchet, enforced where the comparison exists — at write time. Once a score has
    been reached it becomes the floor; going below it is a deliberate act that leaves a
    record in the diff.

    A first drop returns `confirm`, not `fail`: the caller re-measures that one skill and
    calls again with `confirmed=True`. That is what lets delta stay at one sigma without the
    gate crying wolf.

    The escape hatch exists because a drop is not always a regression: narrowing a
    description to cut `false_fire` can cost a little `invoke_rate` and still be an
    improvement. A hard ratchet blocks that and ends with the gate disabled."""
    if old is None or accepted:
        return Verdict("ok", f"{name}: writing")
    drop = old["invoke_rate"] - new["invoke_rate"]
    if drop <= RATCHET_DELTA:
        return Verdict("ok", f"{name}: writing")
    move = (
        f"{old['invoke_rate']:.2f} -> {new['invoke_rate']:.2f} "
        f"(drop {drop:.2f} > {RATCHET_DELTA})"
    )
    if not confirmed:
        return Verdict("confirm", f"{name}: invoke_rate {move} — re-measuring to confirm")
    return Verdict(
        "fail",
        f"{name}: invoke_rate {move}, confirmed by a second measurement. Fix the "
        f"description, or accept it with --accept {name} --reason '...'",
    )
```

- [ ] **Step 4: Create the empty baseline**

```bash
cat > evals/scores.json <<'JSON'
{
  "measured_at": null,
  "reps": 5,
  "skills": {}
}
JSON
```

The empty file is the first-time state, and the gate is designed to pass it with warnings. Committing it now means Task 7 changes one file rather than adding one.

- [ ] **Step 5: Run to verify it passes**

```bash
uv run pytest tests/test_evals.py -q
```

Expected: `37 passed` — the 7 baseline-gate cases pass on warnings.

- [ ] **Step 6: Prove the freshness check bites**

```bash
python - <<'PY'
import json, pathlib
import evals.scores as s
p = pathlib.Path("evals/scores.json")
d = json.loads(p.read_text(encoding="utf-8"))
d["skills"]["integration"] = {
    "description_sha": s.description_sha("integration"),
    "invoke_rate": 0.92, "false_fire": 0.08,
}
p.write_text(json.dumps(d, indent=2) + "\n", encoding="utf-8")
PY
uv run pytest tests/test_evals.py -k baseline -q     # expect 7 passed
```

Now edit the description and watch it go red:

```bash
python - <<'PY'
import pathlib
p = pathlib.Path("skills/integration/SKILL.md")
t = p.read_text(encoding="utf-8")
p.write_text(t.replace("description: Use when integration", "description: Use whenever integration", 1), encoding="utf-8")
PY
uv run pytest tests/test_evals.py -k baseline -q
```

Expected: `integration` FAILS with `description changed since the score — re-measure`.

Restore both:

```bash
git checkout skills/integration/SKILL.md evals/scores.json
uv run pytest tests/test_evals.py -q          # 37 passed
```

- [ ] **Step 7: Commit**

```bash
uv run ruff check && uv run ruff format --check
git add evals/scores.py evals/scores.json tests/test_evals.py
git commit -m "test: gate skill scores on thresholds, freshness and a baseline ratchet"
```

---

### Task 6: The runner

**Files:**
- Create: `evals/run.py`

**Interfaces:**
- Consumes: `evals.stream.observe`, `evals.scores.{load, description_sha, may_write, RATCHET_DELTA}`, `scripts.skill_sandbox.{BY_NAME, build}`, `evals/cases.yaml`
- Produces: a CLI. No other task imports it.

- [ ] **Step 1: Write the implementation**

Create `evals/run.py`:

```python
"""Measure whether each model-invoked skill fires when it should.

Runs every case as a real headless `claude` session against the working tree
(`--plugin-dir`, so unreleased changes are measurable) and records the rate at which the
right skill fired.

Three things keep the number about *these descriptions* rather than about the machine that
produced them. An empty `CLAUDE_CONFIG_DIR` drops every installed plugin — this machine has
a second one shipping seven identically-named skills. The model is pinned, because an
inherited one moved `integration` between 0.0 and 1.0 across tiers. And the tool set is left
alone, because restricting it would remove the very choice being measured: whether the agent
reaches for the skill instead of doing the work itself.

    uv run python -m evals.run                 # only skills whose description changed
    uv run python -m evals.run --all --reps 3  # the calibration run
    uv run python -m evals.run --all --dry-run # session count + wall-clock, no model calls
    uv run python -m evals.run --skill doc-sync --accept --reason "traded for false_fire"
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import yaml

import evals.scores as scores
import evals.stream as stream
import scripts.skill_sandbox as sandbox

REPO = Path(__file__).resolve().parent.parent
CASES = REPO / "evals/cases.yaml"

# Measured under isolation, 5 happy samples of `integration`:
#   3 turns -> invoke_rate 0.2, truncated 0.80   (the score was measuring this constant)
#   6 turns -> invoke_rate 0.2, truncated 0.20   (budget adequate; the rate is real)
MAX_TURNS = 6

# Whichever model is pinned here is what the baseline describes. Measured on the same case:
# sonnet-5 fired 4/4, opus-4-8 fired 0/4. Inheriting the caller's model would make the
# committed score a fact about one developer's session rather than about the skills.
MODEL = "opus"

# A hang guard, not a measurement bound. `MAX_TURNS` already ends a session; this only stops
# one that has stopped making progress from holding a worker forever.
#
# It was 30s for a while, chosen from a solo session where a firing landed 0.3-1.0s after the
# model started responding. That generalised across environments and should not have: under
# eight-way load the mean session runs 58s, not 45s, and at a 30s cap 75-100% of every miss
# turned out to be a session stopped before it could decide. The score was measuring this
# constant. Sessions now run to their natural end.
SESSION_TIMEOUT = 180
JOBS = 8

# Measured under eight-way load: 35 sessions finished in 252s. Solo they run ~45s — running
# eight at once stretches each one. This drives the estimate only; SESSION_TIMEOUT is a guard,
# and multiplying by it instead reported 92 minutes for a 30-minute run.
SECONDS_PER_SESSION = 58

# Observed ceiling on how late a firing arrives: across every capture, a skill that fires has
# fired by the third tool call. A session cut before that never got its chance and is genuinely
# ambiguous; one cut after five tool calls without firing had its chance and declined. Counting
# every cut session as ambiguous instead pinned the warning permanently on at 0.80 while
# `invoke_rate` sat unmoved at 0.20 across three timeouts — and a warning that always fires is
# not a signal.
FIRE_BY_TOOL_CALL = 3


class RateLimited(RuntimeError):
    """The five-hour window is exhausted. Overage is rejected on this account, so the CLI
    starts failing rather than billing — and a failed session recorded as "the skill did not
    fire" is a fabricated score. Everything measured before this point is already on disk."""


def cases_for(entry: dict, arm: str) -> list[tuple[str, str | None]]:
    """Normalise both `- "prompt"` and `- {prompt:, fixture:}` into (prompt, fixture)."""
    out = []
    for case in entry[arm]:
        if isinstance(case, dict):
            out.append((case["prompt"], case.get("fixture", entry.get("fixture"))))
        else:
            out.append((case, entry.get("fixture")))
    return out


def isolated_config_dir(root: Path) -> Path:
    """A config dir holding credentials and nothing else.

    Isolation is what makes the score about *these* descriptions. This machine has a second
    installed plugin shipping seven of the same skill names, and a twin winning the
    invocation reads as our skill not firing — a property of one developer's setup, not of
    the description, and not reproducible by anyone else.

    The credentials are the one thing that has to survive the isolation. An empty config dir
    still produces a well-formed `init` event and then answers "Not logged in", so every
    session would score 0.0 for a reason that has nothing to do with any skill. Measured: ten
    such sessions read invoke_rate 0.00 before this was found.
    """
    cfg = root / "cfg"
    cfg.mkdir(exist_ok=True)
    src = Path.home() / ".claude" / ".credentials.json"
    if not src.exists():
        raise SystemExit(f"no credentials at {src} — isolated sessions cannot authenticate")
    shutil.copy2(src, cfg / src.name)
    return cfg


def run_session(
    prompt: str, fixture: str | None, workdir: Path, config_dir: Path, restricted: bool = False
) -> stream.Observation:
    if fixture:
        # build() creates workdir/<scenario> and returns it — run *there*. Staying in the
        # parent would put the agent in a directory holding a single subdirectory, which is
        # the empty-cwd condition that makes it explore before it reaches for a skill, and
        # every fixture-backed skill would score low for a reason that is not its description.
        workdir = sandbox.build(sandbox.BY_NAME[fixture], workdir)
    cmd = ["claude", "-p", prompt, "--output-format", "stream-json", "--verbose",
           "--max-turns", str(MAX_TURNS), "--model", MODEL, "--plugin-dir", str(REPO)]
    if restricted:
        # The diagnostic arm. With no other tool on offer the agent cannot quietly do the
        # work itself, so what is left is whether the prompt matches the description at all.
        # It answers a different question from the scored arms and is never gated.
        cmd += ["--allowedTools", "Skill"]
    env = {**os.environ, "CLAUDE_CONFIG_DIR": str(config_dir)}
    try:
        out = subprocess.run(
            cmd, cwd=workdir, env=env, stdin=subprocess.DEVNULL,
            capture_output=True, check=False, timeout=SESSION_TIMEOUT,
        ).stdout
    except subprocess.TimeoutExpired as e:
        out = e.stdout or b""
    # The turn cap exits 1 with the stream fully written, and a timeout kill leaves no exit
    # code worth reading either. Parse, then judge.
    return stream.observe(out.decode("utf-8", errors="replace"))


def _one(prompt: str, fixture: str | None, config_dir: Path, restricted: bool):
    with tempfile.TemporaryDirectory() as tmp:
        return run_session(prompt, fixture, Path(tmp), config_dir, restricted)


def measure(name: str, entry: dict, reps: int, config_dir: Path, jobs: int) -> dict:
    happy = cases_for(entry, "happy")
    negative = cases_for(entry, "negative")

    plan = [("happy", p, f, False) for p, f in happy for _ in range(reps)]
    plan += [("negative", p, f, False) for p, f in negative for _ in range(reps)]
    plan += [("restricted", p, f, True) for p, f in happy]

    # Sessions share nothing — each gets its own temp dir and prompt, and the config dir is
    # read-only to them. Serial was an unexamined default; 8 at a time measured 8 sessions
    # per ~30s against 45s each on their own.
    seen: list = [None] * len(plan)
    with ThreadPoolExecutor(max_workers=jobs) as pool:
        futures = {
            pool.submit(_one, prompt, fixture, config_dir, restricted): i
            for i, (_arm, prompt, fixture, restricted) in enumerate(plan)
        }
        for done, fut in enumerate(as_completed(futures), 1):
            seen[futures[fut]] = fut.result()
            print(f"\r  {name}: {done}/{len(plan)} sessions", end="", flush=True)
    print()

    hits = misses = fires = quiet = truncated = truncated_quiet = 0
    restricted_hits = restricted_total = saw_plugin = 0
    for (arm, _p, _f, _r), obs in zip(plan, seen):
        if obs.rate_limited:
            raise RateLimited(f"{name}: rate limit reached mid-measurement")
        if obs.errored:
            raise SystemExit(
                f"{name}: a session failed outright rather than hitting the turn cap — most "
                f"likely the isolated config dir lost authentication. Refusing to record a "
                f"0.0 that is not about the description."
            )
        # A session killed on the timeout may never have reached the init event, so an empty
        # availability list means "could not tell", not "the plugin was missing".
        if obs.available:
            saw_plugin += 1
            if name not in obs.available:
                raise SystemExit(
                    f"{name}: the plugin loaded but this skill was not among its skills — "
                    f"the frontmatter probably failed to parse."
                )
        fired = name in obs.fired
        # Stopped before it had a real chance to reach for the skill — the one outcome this
        # design cannot tell from a deliberate miss.
        cut_early = not obs.completed and obs.tool_calls < FIRE_BY_TOOL_CALL
        if arm == "restricted":
            restricted_hits += fired
            restricted_total += 1
        elif arm == "happy":
            hits += fired
            misses += not fired
            # The one outcome this design cannot tell from a genuine miss: the session was
            # stopped before it had a real chance to reach for the skill.
            truncated += (obs.turns_exhausted or cut_early) and not fired
        else:
            fires += fired
            quiet += not fired
            # The same cut flatters `false_fire` exactly as it depresses `invoke_rate`: a
            # negative sample stopped before the agent could over-fire is recorded as
            # correctly quiet. Tracking it on only one arm would leave the ceiling passing
            # on evidence nobody checked.
            truncated_quiet += cut_early and not fired

    if not saw_plugin:
        raise SystemExit(
            f"{name}: no session got far enough to list the loaded plugins — --plugin-dir "
            f"{REPO} may be wrong, or SESSION_TIMEOUT too short to reach the init event. "
            f"Refusing to record a score built on nothing."
        )

    result = {
        "description_sha": scores.description_sha(name),
        "invoke_rate": round(hits / (hits + misses), 2),
        "false_fire": round(fires / (fires + quiet), 2),
        # Both diagnostics, never gated. `truncated` says how much of the verdict rests on a
        # session being cut short. `restricted` says what the rate looks like when the agent
        # has no way to do the work itself — a high `restricted` beside a low `invoke_rate`
        # means the wording is fine and the skill is simply losing to direct action.
        #
        # `restricted` reads low for a skill whose trigger has to be discovered.
        # playwright-scaffold measured 1.00 unrestricted and 0.20 restricted: it fires on
        # "no test cases exist yet", and with no tools the agent cannot look and find that
        # out. A low `restricted` is therefore only evidence about the wording when the
        # trigger is visible in the prompt itself.
        "truncated": round(truncated / (hits + misses), 2),
        "truncated_quiet": round(truncated_quiet / (fires + quiet), 2),
        "restricted": round(restricted_hits / restricted_total, 2),
    }
    for metric, share, of in (
        ("invoke_rate", result["truncated"], "happy"),
        ("false_fire", result["truncated_quiet"], "negative"),
    ):
        if share > 0.20:
            print(
                f"  [!] {name}: {share:.0%} of {of} samples were cut short — {metric} is "
                f"reporting SESSION_TIMEOUT or MAX_TURNS rather than the description",
                flush=True,
            )
    return result


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--all", action="store_true", help="re-measure every skill")
    ap.add_argument("--skill", help="measure one skill")
    ap.add_argument("--reps", type=int, default=5)
    ap.add_argument("--jobs", type=int, default=JOBS, help="sessions in flight at once")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    ap.add_argument("--accept", action="store_true", help="allow a score below the baseline")
    ap.add_argument("--reason", help="why the drop is acceptable (required with --accept)")
    args = ap.parse_args()

    if args.accept and not args.reason:
        ap.error("--accept requires --reason: an unexplained drop is indistinguishable "
                 "from an unnoticed one")

    data = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    baseline = scores.load()
    old_skills = baseline.get("skills", {})

    if args.skill:
        if args.skill not in data["skills"]:
            ap.error(f"unknown skill {args.skill!r}; cases.yaml has {sorted(data['skills'])}")
        targets = [args.skill]
    elif args.all:
        targets = sorted(data["skills"])
    else:
        # The default is incremental. A harness nobody can afford to run is one whose
        # freshness gate blocks every merge.
        targets = [
            n for n in sorted(data["skills"])
            if old_skills.get(n, {}).get("description_sha") != scores.description_sha(n)
        ]
        if not targets:
            print("every score is current — nothing to measure")
            return 0

    sessions = sum(
        (len(data["skills"][n]["happy"]) + len(data["skills"][n]["negative"])) * args.reps
        + len(data["skills"][n]["happy"])
        for n in targets
    )
    minutes = sessions / args.jobs * SECONDS_PER_SESSION / 60
    print(
        f"{len(targets)} skill(s), {sessions} sessions, "
        f"{args.jobs} at a time, ~{minutes:.0f} min"
    )
    if args.dry_run:
        return 0

    def save() -> None:
        """Persist after every skill. Writing once at the end loses the whole run to a single
        rate-limit refusal."""
        baseline["skills"] = old_skills
        baseline["measured_at"] = date.today().isoformat()
        baseline["reps"] = args.reps
        scores.SCORES.write_text(
            json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    with tempfile.TemporaryDirectory() as cfg_root:
        config_dir = isolated_config_dir(Path(cfg_root))
        measured = 0
        for name in targets:
            print(f"measuring {name}")
            try:
                result = measure(name, data["skills"][name], args.reps, config_dir, args.jobs)
                verdict = scores.may_write(name, result, old_skills.get(name), args.accept)
                print(f"  {result}")
                if verdict.level == "confirm":
                    # One reading cannot tell a real 0.10 drop from noise at this sample size.
                    # Rather than widening the tolerance until the ratchet never fires, spend
                    # a second measurement: two independent drops are ~0.02 likely by chance,
                    # one is 0.15.
                    print(f"  {verdict.message}")
                    result = measure(name, data["skills"][name], args.reps, config_dir, args.jobs)
                    print(f"  {result}")
                    verdict = scores.may_write(
                        name, result, old_skills.get(name), args.accept, confirmed=True
                    )
            except RateLimited as e:
                save()
                print(f"\n{e}", file=sys.stderr)
                print(f"{measured}/{len(targets)} skills measured and saved. When the window "
                      f"resets, re-run WITHOUT --all — the incremental default skips every "
                      f"skill whose description_sha already matches.", file=sys.stderr)
                return 1
            if verdict.level == "fail":
                print(verdict.message, file=sys.stderr)
                return 1
            if args.accept and name in old_skills:
                result["lowered_from"] = old_skills[name]["invoke_rate"]
                result["lowered_reason"] = args.reason
            old_skills[name] = result
            measured += 1
            save()

        print(f"wrote {scores.SCORES}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())

```

- [ ] **Step 2: Verify the CLI without spending anything**

```bash
uv run python -m evals.run --dry-run --all
```

Expected: `7 skill(s), 245 sessions, 8 at a time, ~30 min`.

```bash
uv run python -m evals.run --accept
```

Expected: exit 2, `--accept requires --reason`.

```bash
uv run python -m evals.run --dry-run
```

Expected: `7 skill(s), 245 sessions` — with an empty `scores.json` every skill is stale, which is the correct first-time answer.

- [ ] **Step 3: Verify one real session end to end**

```bash
uv run python -m evals.run --skill integration --reps 1
```

Expected: 10 lines of `integration happy rep1 FIRED` / `integration negative rep1 quiet`, then a result dict and `wrote .../evals/scores.json`. 10 sessions, ~9 minutes.

Then discard it — Task 7 produces the baseline that gets committed:

```bash
git checkout evals/scores.json
```

- [ ] **Step 4: Commit**

```bash
uv run ruff check && uv run ruff format --check
git add evals/run.py
git commit -m "test: add the skill invocation eval runner"
```

---

### Task 7: Measure the baseline and document the harness

**Files:**
- Modify: `evals/scores.json`
- Modify: `CLAUDE.md`

**Interfaces:**
- Consumes: everything above
- Produces: the committed baseline every later merge is judged against

- [ ] **Step 1: Run the full measurement**

```bash
uv run python -m evals.run --all
```

245 sessions — 7 skills x ((5 happy + 5 negative) x reps 3 + 5 restricted). At the shipped
`JOBS = 8` and `SECONDS_PER_SESSION = 58` that is **~30 minutes**, comfortably inside the
five-hour window. (The "350 sessions, ~5.3 hours serial" written here originally predates
both the reps 5→3 cut and eight-way concurrency; serial it would now be ~4 hours, which is
what made concurrency worth having.) A rate-limit stop is still possible on a window already
part-spent, and is still handled — the runner now stops on the first refused session rather
than finishing the plan.

When it stops on a rate limit, everything measured so far is already in `scores.json`. Wait
for the window to reset and re-run **without `--all`**:

```bash
uv run python -m evals.run
```

The incremental default skips every skill whose `description_sha` already matches, so it
resumes at the first unmeasured skill. Repeat until it completes.

- [ ] **Step 2: Read the result before committing it**

```bash
uv run pytest tests/test_evals.py -q
```

A `fail` here is a **finding, not a chore** (post-redesign there is no floor): an all-zero baseline, an undeclared skill, or a ratchet-confirmed regression all fail, and each names a real defect. Fix the description (or, for a regression, `--accept --reason` if the drop is a deliberate trade) and re-measure that skill (`--skill <name>`) rather than weakening the predicate. A significant shortfall from `expect_invoke` is a *warn*, not a fail — it says the description needs work without painting the suite red.

The declarations are the honest replacement for the invented 0.80 this plan opened with. `expect_invoke` is a design-intent claim, deliberately not tuned to the measured baseline (tuning it would collapse the very gap the warn exists to surface); if a run shows a skill persistently below its declaration, fix the description or, with review, revise the declaration in `cases.yaml` and say why in the diff — never to make a red suite green.

- [ ] **Step 3: Document it in CLAUDE.md**

> The wording actually shipped is in `CLAUDE.md` and differs from the draft below, which was
> written before both calibration and the gate redesign: there is no floor — the gate is a
> per-skill `expect_invoke` declaration (a shortfall warns) plus an exact-binomial ratchet (a
> regression fails), reps are 3 rather than 5, and the entry records the pinned model and
> isolated config dir. Read `CLAUDE.md` as the current state; the block below is original intent.

In the "Folder structure" block, insert after the `tests/` entry:

```text
evals/      cases.yaml (7 model-invoked skills × 5 happy + 5 negative prompts) · run.py (headless
            `claude -p --plugin-dir` runner — measures whether each skill actually fires; spends hours
            of rate-limit budget, local only) · scores.json (the committed baseline) · stream.py · scores.py (the gate
            predicate, model-free). Not shipped: only agents/·skills/·hooks/ reach consumers.
```

Then add to the "Commands" block, after the pytest lines:

```bash
uv run python -m evals.run --dry-run --all           # session count + wall-clock, no model calls
uv run python -m evals.run                           # measure only skills whose description changed
```

And add a bullet to "Architecture (must-know)":

```markdown
- **Skill invocation is measured, not assumed.** `tests/test_skills.py` checks that a skill
  *file* is well-formed; `evals/` checks that the skill is *reached*. Half of a model-invoked
  skill's failure modes live in its `description`, and no structural test can see them. The
  split matters: measuring needs a model and ~8 hours of rate-limit budget, checking needs
  neither — so
  `evals/run.py` runs by hand and `tests/test_evals.py` runs in every `uv run pytest` and in
  `unit-test.yml`. A description edit invalidates its score via `description_sha`, so a stale
  green is not reachable.
```

- [ ] **Step 4: Commit**

```bash
uv run ruff check && uv run ruff format --check
uv run pytest -q
git add evals/scores.json CLAUDE.md
git commit -m "test: record the skill invocation baseline"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Task |
|---|---|
| §2 measured mechanics | Task 1 (corrected: turn budget, all-tool_use scan, init availability) |
| §3 scope — 7 in, 4 out | Task 3 (`test_cases_cover_every_model_invoked_skill_and_nothing_else` enforces it) |
| §4 metrics, 5+5 cases, 5 reps | Task 3 (cases), Task 6 (`measure`) |
| §4 `ablation_delta` | **Dropped.** `obs.fired` only ever holds `harness-tier:*` names, so with the plugin unloaded the OFF arm is empty by construction and `ablation_delta` reduced to `invoke_rate - 0`. It spent 175 sessions recomputing a number already in hand. Spec §4 now records that a real retirement signal needs its own design. |
| §5 data model | Task 3 (cases.yaml), Task 5 (scores.json + sha) |
| §5 first-time state warns | Task 5 (`test_unmeasured_skill_warns_rather_than_failing`) |
| §6 absolute thresholds | Task 5, **redesigned**: the `MIN_INVOKE` floor is gone; what fails is an all-zero baseline (`test_an_all_zero_baseline_always_fails`), an undeclared skill (`test_an_undeclared_skill_fails_rather_than_defaulting`), and `test_the_false_fire_ceiling_fails`; a declaration shortfall warns (`test_a_measurement_far_below_its_declaration_warns_not_fails`) |
| §6 ratchet | Task 5, **redesigned**: fixed `δ` replaced by an exact binomial at `alpha_single(n_skills)` against a Jeffreys-shrunk baseline — `test_ratchet_trip_table`, `test_a_rise_never_trips_the_low_tail_ratchet`; `may_write` still returns `confirm` first, and Task 6's confirmation pass is unchanged |
| §6 freshness | Task 5 (`test_a_stale_measurement_fails` + the Step 6 red proof) |
| §6 no new wiring | Task 5 — `tests/test_evals.py` is picked up by `uv run pytest` and `unit-test.yml` as they stand |
| §7 incremental default | Task 6 (`targets` when neither `--all` nor `--skill`) |
| §8 SKILL.md 500-line cap | Task 2 |

**Three deviations from the spec as first written, all deliberate and all folded back into the spec:**

1. **The ratchet is enforced at write time, not check time.** `scores.json` holds exactly one number per skill, so at `pytest` time there is nothing to compare against — the comparison only exists when a fresh measurement meets the committed one, which happens inside `run.py`. `check()` covers what remains visible to the test: thresholds, freshness, and that any recorded `lowered_from` carries its `lowered_reason`.
2. **`--max-turns 3`, and every `tool_use` is scanned.** Spec §2's 1-turn claim was measured false. Task 1 Step 6 corrects the spec text.
3. **A drop asks for confirmation before it fails, and the budget is rate limit rather than money.** Both came out of Task 1's measurements: at the shipped 15-sample arm the rate has `sd = 0.126`, which makes any single-shot δ either noisy (at 0.10, ~21%) or blind (at 3σ, above the floor for most skills); and `apiKeySource: "none"` with `overageStatus: "rejected"` means a long run is limited by a five-hour window that *fails requests*, not by a bill. Task 6 therefore saves per skill and stops on a rate-limit event instead of scoring it as a miss. (The δ-noise half of this is what the later gate redesign resolved properly — replacing the fixed width with an exact binomial whose noise scales with p; the confirmation re-measure survives and now carries the family-wise α.)

**Superseding note.** The floor + fixed-δ gate this Self-Review summarises was later replaced (see the redesign banner at the top): a per-skill `expect_invoke` declaration (shortfall warns) plus an exact-binomial ratchet against a Jeffreys-shrunk baseline at a family-wise α (regression fails, after confirmation). The task-to-spec mapping above still holds structurally; only the threshold and δ mechanics changed.

**Placeholder scan:** every code step carries complete code and every command carries its expected output. No value is left to be filled in — `RATCHET_DELTA = 0.10` is now settled by Task 1's outcome rather than deferred to it.

**Type consistency:** `Observation(available, fired, turns_exhausted, rate_limited)` produced in Task 4 is consumed with those names in Task 6. `Verdict(level, message)` produced in Task 5 is consumed in Tasks 5 and 6, with `level` spanning `ok | warn | confirm | fail`. `check(name, entry, sha)` and `may_write(name, new, old, accepted, confirmed=False)` keep their signatures across both call sites. `sandbox.BY_NAME` / `sandbox.build(scenario, root)` match `scripts/skill_sandbox.py` as it exists.
