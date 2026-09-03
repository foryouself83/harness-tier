# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

This repo is the **Claude Code plugin itself** (not a consumer of it). For usage, see [README.md](README.md)·[USAGE.md](USAGE.md).
Both have Korean twins ([README.ko.md](README.ko.md)·[USAGE.ko.md](USAGE.ko.md)); `doc-sync` carries a change across the pair.
For component authoring specs (agent/hook/skill frontmatter), verify against the official docs as the SSOT, not model knowledge:
[plugins-reference](https://code.claude.com/docs/en/plugins-reference.md) · [hooks](https://code.claude.com/docs/en/hooks.md) · [skills](https://code.claude.com/docs/en/skills.md) · [permissions](https://code.claude.com/docs/en/permissions.md).
(`allowed-tools` pre-approves tools, it does not restrict — enforced at point of use by
[`.claude/rules/skill-frontmatter.md`](.claude/rules/skill-frontmatter.md) and [`tests/test_skills.py`](tests/test_skills.py).)

## Commands

Gate scripts are Python; run tooling via `uv`.

```bash
uv sync                                                  # install dependencies
uv run pytest                                            # run all tests
uv run pytest tests/test_flow_gate_check.py::<name>      # run a single test
uv run ruff check && uv run ruff format --check          # lint + format check
uv run pre-commit run --all-files                        # full static analysis
uv run python -m evals.run --dry-run --all               # session count + wall-clock, no model calls
uv run python -m evals.run                               # measure only skills whose description changed
uv run python -m evals.run --skill integration --capture-fixtures   # …+ stream fixture candidates (*.jsonl.new)
uv run python -m evals.outcome                           # measure the outcome arm (end-state, reps 3)
uv run python -m evals.outcome --skill wiki-init         # …one skill only (others keep their baseline)
```

When modifying `*.sh`, verify with ShellCheck (the hook runtime is Windows, so bugs are hidden as FAIL-OPEN — see Invariants).

## Conventions

- **English in the repo** — docs · commit messages · comments/docstrings · test assertion
  messages: a developer reads all of those. Korean stays where it is load-bearing: text the
  repo quotes rather than authors (gate/CLI output, a transcript), the expected strings a test
  compares against that output, and fixtures whose non-ASCII bytes ARE the case (a cp949 blob,
  a Hangul filename). Translating one of those can leave a test green while it stops exercising
  anything. Exception: `docs/superpowers/specs/`·`plans/` — internal, never shipped, in Korean.
- **Write only what the code can't say** — comments · docstrings · `.md` · rules. No change-history
  narration, no restating the next line, no ornamental structure; a rule file holds the rule in force.
  Same discipline in a commit body ([`rules/risk-tiers.md`](rules/risk-tiers.md) Commit Discipline) and
  in generated harness artifacts ([`rules/harness-rules.md`](rules/harness-rules.md) 5-2).
- **Dogfood new CI** — a workflow-rendering feature also lands in this repo's OWN `.github/workflows/`,
  not just as a `github/*.example.yml` consumer template. Every job carries a tight `timeout-minutes`.
- **Mutation-test a fix, and assert the mutation applied** — a no-op edit runs the original code, so the
  suite passes and reads as verified (it has silently failed here twice). Read-modify-write in Python with
  `assert old in text`, never `sed -i`; revert with `git checkout --` from an already-clean tree. Assert the
  BASELINE is green where the battery runs too: a suite that already fails there reports every mutation as
  caught, and a battery run in a copy without `.git` is one `git ls-files` away from that. A guard that
  only bites on POSIX — a file mode, an owner, an access entry — is checked in **WSL**: on the dev host
  its test skips or the OS enforces the same thing anyway, so the mutation survives and the suite is green.
  A battery that carries rows forward SAYS which it dropped for an anchor that moved — the edit under
  review is what moves them, and the run still reports a clean sweep over what is left.

## Folder structure

`agents/`·`hooks/hooks.json`·`skills/` declare no path in the manifest — they are **auto-discovered from their default locations** (adding a component = just adding a file). Each entry below is folder + purpose; the per-file detail lives in the folder itself.

```text
.claude-plugin/  plugin.json (minimal manifest) · marketplace.json (self-exposed; source=github + immutable sha pin)
agents/          harness-researcher · harness-code-analyzer · harness-critic
hooks/           hooks.json (SessionStart + Notification) · inject-risk-tiers.sh (rule injection + stale-build warning)
skills/          /slash = skill — one dir each; open the dir for its SKILL.md
rules/           risk-tiers.md (SSOT: tier classification + commit discipline) · harness-rules.md (SSOT: harness-gen)
                 — both SHIP to consumers, unlike .claude/rules/ which never leaves this repo
.claude/rules/   dev-only, never ships: skill-frontmatter.md (fires on a skills/**/*.md) ·
                 claude-md-authoring.md (fires on this file)
scripts/         gate + setup scripts incl. wiki_graph.py (build/verify the LLM Wiki graph;
                 owns `derive_wiki_id`/`--derive-id`, the executable SSOT for the `wiki_id` rule) —
                 authoritative copy list = flow_init_setup.py COPY_FILES (open the dir for the rest)
github/          *.workflow.example.yml SOURCEs /flow-init renders (CI · release.<tool> · deploy.<target>);
                 authoring gotchas (timeout-minutes cap · no ${{ }} in a run: block) guarded by test_flow_init_setup.py
.github/         this repo's OWN CI (release · branch-naming · entropy-check · unit-test, all timeout-capped) · scripts/pin-marketplace-sha.py
flow-tiers.yaml            tier→gates + merge_strategy — plugin-owned, immutable
flow-config.example.yaml   host environment slots (real file → host .claude/harness-tier/config/, team-shared)
tests/           pytest over scripts/ · test_skills.py (skill FILES: frontmatter/links/refs + the git
                 commands skills and rules/ issue vs the gate's invocation grammar) · test_evals.py (model-free half of evals/)
evals/           skill measurement: invocation (cases.yaml · run.py · scores.py) + outcome (outcome.py · outcome_scores.json;
                 fixtures/goldens live in scripts/skill_sandbox.py) — NOT shipped → commit as test:/chore:
```

## Architecture (must-know)

- **Installed outside the host (in a cache) → dual paths.** `${CLAUDE_PLUGIN_ROOT}` = reads (templates/policy), `${CLAUDE_PROJECT_DIR}` = writes (host config/evidence). **Never write into the plugin directory.**
- **Host writes group under `${CLAUDE_PROJECT_DIR}/.claude/harness-tier/`**: `scripts/` (copied gate scripts, git-tracked) · `config/` (flow-config.yaml + flow-tiers.yaml) · `.flow/` (gate evidence, gitignored). The only exceptions are files whose location external tools force: `.gitignore` · `.pre-commit-config.yaml` · `.claude/settings.json` · `.github/workflows/`.
- **The commit gate is registered in the host's `settings.json`** (not the plugin's hooks.json) — for deny-enforcement reliability and because `${CLAUDE_PLUGIN_ROOT}` isn't resolved there. `/flow-init` **copies** the gate scripts + `flow-tiers.yaml` policy into the host.
- **Script propagation is one-way**: `scripts/`·`flow-tiers.yaml` (SOURCE·SSOT) → cache → host copies. **Fix only the SOURCE** — host copies are overwritten on reinstall (`/flow-init` re-syncs, `/flow-uninstall` cleans up). Never edit the host copies directly.
- **Policy vs. environment**: `flow-tiers.yaml` (tier→gates + `merge_strategy`; immutable · plugin-owned · do not edit) vs. `flow-config.yaml` (branches · modules; host-owned · team-shared · git-tracked). `merge_strategy` names flows by `flow-config.branches` **key**, so the policy stays environment-free.
- **Tier-discipline SSOT = [`rules/risk-tiers.md`](rules/risk-tiers.md)** — `flow.md` · `flow-tiers.yaml` · the gates all defer to it.
- **Versioning & release**: plugin.json `version` gates updates — a sha change alone does not propagate; reinstall happens only on a version bump. `.github/workflows/release.yml` (python-semantic-release) bumps from the Conventional Commits of pushes to main/stage; on main, `pin-marketplace-sha.py` immutably pins the marketplace `source.sha`. **Therefore consumer-facing `.md` (rules/skills) changes must be committed as `feat`/`fix`, not `docs`, to propagate.** Branches: `feature/*` → dev → stage → main.
- **The plugin's `rules/` is not auto-loaded** → `hooks/inject-risk-tiers.sh` injects it as `additionalContext` at SessionStart.
  The same hook tells a consumer when the marketplace clone beside the install cache publishes a
  newer `version` than the loaded build — the update gate is version-only, so nothing else says
  so. Local files, no network; a build AHEAD of published (a maintainer's rc) stays silent, or
  the remedy would name a reinstall that fetches the older pin. FAIL-OPEN.
- **Three verification layers**, independent (per-gate mechanism → [`rules/risk-tiers.md`](rules/risk-tiers.md) · [`flow-tiers.yaml`](flow-tiers.yaml)):
  1. **Hygiene** — the host's `.pre-commit-config.yaml` (git-native): gitlint · teams-notify-push · language-agnostic checks.
  2. **Flow gate** — `precommit-runner.sh` (PreToolUse), **Claude-session commits & merges only** (terminal commits and CI bypass it). Blocks unclassified commits, then runs the tier's `gates`; `git merge` takes a separate path judged against `merge_strategy`. When `flow-config.merge_workflow.pull_request` routes a flow through a PR instead of a direct merge, that flow's `merge_strategy` row never fires here (the hook never sees a `git merge`) — enforcement of the merge method shifts server-side to a GitHub branch ruleset, which `scripts/check-merge-ruleset.sh` (read-only) checks the state of at `/flow-init` Step 2.7, without ever writing to GitHub. **That shift is exact only for `promotion`** (one allowed method per branch); a ruleset targets the *destination* ref, so on `daily` it bars merge commits into integration but cannot separate `feature/*`=Squash from `fix/*`=Rebase, and it also makes "require a PR" govern flows nobody selected — the back-merge push and `hotfix/*` → production — which is why both need a bypass actor or a PR of their own ([`rules/risk-tiers.md`](rules/risk-tiers.md) PR workflow). Gate internals & the FAIL-OPEN rules → **Invariants** below.
  The `wiki` runtime gate runs **in-process as the flow gate's final stage** (one spawn;
  `--wiki-check` remains a compat alias) — never through the module-command channel, whose
  "any nonzero exit = failure" contract would make an internal error block every commit.
  It fires whenever `flow-config.wiki` is enabled — read-only, on every tier including docs. The graph itself is
  built by `doc-sync` or `/wiki-init`, never by the hook or CI, from **git's index** (`git add` admits a document;
  a gitignored/untracked `.md` is not a node, else the committed graph is unreproducible; a git that cannot answer
  drops back to the filesystem, which only an outside-a-repo `--build` may use — inside a repo `--build` refuses to
  write from it and `--verify` refuses to gate on it). Terminal commits bypass
  this like every layer-2 gate, so drift is caught late (at the next session commit), not lost. It reads working-tree
  **content** (the hook fires before staging) → `graph.yaml` must be staged with its documents; and no promotion gate
  rebuilds it, so a blocked promotion is resolved by running `--build` into that commit.
  3. **CI (GitHub Actions)** — `/flow-init` renders `api-contract.yml` + `unit-test.yml` + `wiki-verify.yml` (read-only graph verify — closes the wiki gate's terminal/merge blind spot; rendered unconditionally since the script no-ops green without a wiki, and the step guards on the script being in the checkout at all, which it is not in a repo that gitignores `.claude/`), closing layer 2's blind spot (it never sees direct/terminal/CI commits). Every job is timeout-capped.
- **Skill invocation is measured, not assumed** — `tests/test_skills.py` checks a skill *file* is well-formed; `evals/` checks it is actually *reached* (half a skill's failure modes live in its `description`). Gate SSOT = [`evals/scores.py`](evals/scores.py); mechanics in [`evals/`](evals/). A second **outcome arm** ([`evals/outcome.py`](evals/outcome.py)) checks a skill actually *executed* correctly — it runs the skill in a golden fixture under `bypassPermissions` and scores the end-state deterministically (SWE-bench style); baseline [`evals/outcome_scores.json`](evals/outcome_scores.json), fingerprinted separately (`outcome_sha` = SKILL.md body + the whole scenario minus `outcome.SHA_EXEMPT` prose + the newline-normalized **content digest** of every `copy_from_repo` source, since `description_sha` covers none of them — a **denylist**, so a field added to `Scenario` is fingerprinted by default. Any byte change to a copied source costs a live re-measure). A skill enters this arm by a [`scripts/skill_sandbox.py`](scripts/skill_sandbox.py) scenario declaring `outcome=` — that arm, unlike the invocation one, **does cover `disable-model-invocation` skills** (they appear in the session's skill list; only the prompt must be the slash command), which is how `/wiki-init` is measured.
- **Deployment is not a verification layer** — a release-decoupled opt-in: `/harness-deployments` writes `flow-config.deploy` and renders per-target `deploy-<name>.yml` components + a generated `deploy.yml` orchestrator; `release.yml` calls it via `workflow_call` in-run (no PAT). None of it gates a commit.

## Invariants (break these and the gate is silently neutralized)

When modifying the gate scripts (`scripts/*`, `hooks/*.sh`), these must be preserved:

1. **FAIL-OPEN, except for missing dependencies, unclassified commits, and merge-strategy violations** — transient internal errors let the gate pass rather than block (so a broken gate never permanently blocks commits). **Exception 1**: if the required tools (`python3` ≥ 3.8 · `PyYAML`) are missing or outdated, `precommit-runner.sh` **blocks the commit** (to prevent silent non-enforcement; independent of the project's language). Without python3 nothing can classify the command, so the raw-stdin filter only decides whether that deny is reached. **Exception 2**: when the policy (`flow-tiers.yaml`) and config (`flow-config.yaml`) parse correctly but the `tier` marker is absent, `flow_gate_check` **blocks** such an **unclassified commit** (to prevent the gate being silently neutralized by bypassing `/flow`). The criterion, however, is not "the file exists" but "**parsing succeeded** (= it works reliably)" — if the policy/config is broken, it is treated as an internal error and fails open. **Exception 3**: a `git merge` whose flags violate its branch flow's `merge_strategy` row is **blocked** — a missing `require` flag or a present `forbid` flag, nothing else. This one differs in kind from the other two: it is decided **from the command string alone** and reads no repository state, so no internal error can misfire it. Everything uncertain around it fails open (no policy · no matching rule · an unparseable command · a command naming another worktree · a rebase that only *warns*). A gate that cannot classify still enters this check, guarded on the script file existing — alone among the stages it reads **stderr** for its reason, where a missing file leaves the interpreter's complaint instead. (superpowers cannot be detected from the shell → guarded in `/flow`·`/flow-init`.)
2. **Windows encoding** — the hook's Python runs in a cp949 locale. A Korean `print()` / UTF-8 `open()` can FAIL-OPEN on an encoding error and *let a commit that should be blocked pass through*. Do not omit the `PYTHONUTF8=1` · `force_utf8_io()` · `encoding="utf-8"` defenses.
3. **Block = exit 2 + a reason on stderr** (emit the JSON `permissionDecision` too, but the actual blocking mechanism is exit 2).
4. **No `if` field on the settings.json gate hook** — it would suppress the hook from firing per build. Do filtering via `precommit-runner.sh`'s stdin self-filter.
5. **`/flow-init` is idempotent** — no duplicate additions of the settings.json hook · pre-commit id · .gitignore line (match-then-skip).
6. **Worktree re-designation stays FAIL-OPEN** — `CLAUDE_PROJECT_DIR` is fixed at session start, so `precommit-runner.sh` re-points `ROOT` to the worktree `flow_gate_check.py --classify` detects by branch-key (`_harness_paths.working_root`), and status/diff/tier-marker/module-lint all read it. Any uncertainty — detached HEAD · `--git-common-dir` mismatch · no worktree · parse/exception · invocations naming different directories — returns main; **never newly block**. Same-repo identity is `--git-common-dir` equality, never a path prefix (sibling `…/kit` vs `…/kit-feature` must not false-match). Keep the uncertain set small: two `git -C <same wt> commit` in one command (commit-then-amend) name one directory and must resolve to it.
7. **One authority for what a `git` invocation is** — `--classify` decides; the runner's stdin filter only decides whether to spawn it, and must stay coarse enough that it can never be narrower, since a spelling only one of them accepts is the gate off in silence rather than a narrower gate. Quoting, escapes, comments and heredoc bodies are read in exactly one place, `_harness_paths.mask_literals`, and located on its mask rather than the raw command (the anchored `cd` prefix excepted — it cannot start inside a literal). **Quoted text is data only until something runs it** — `_harness_paths.is_invocation` is the one reader, and it reads twice: the grammar over the mask, then the same grammar over each command-list element with its quoting rubbed out. The second reading is **skipped only for an element whose every program reads** (`_READS_ONLY`), asked of the program at EVERY command position — one walk, because two disagreed: the one that stepped over a `!`, a redirection or an assignment found the program behind it and the one that built the names did not, so `cat f | > /dev/null env 'git' commit` was exempted as a `cat`. A position whose program has no name — written quoted, the mask blanks it — is reported as one rather than left out, since left out it is a program the exemption was decided without. The exemption is the half that may be wrong: a reader nobody listed over-gates, which the user sees and works around, where an executor nobody listed turned the gate off with nothing reported. A name earns that list by having no way to run a command written in its own arguments OR named by its environment, which is why `awk`·`sed`·`find`·`ack`·`ag` are absent from it, why `less` left it — `LESSOPEN`, which a login profile sets on most distributions, is a command it runs — and why `git` never enters it. An element carrying an ASSIGNMENT earns no exemption either: the assignment is neither the program nor one of its arguments, it reaches inside the program the list vouched for, so that position is reported unnamed. `LESSOPEN='|git commit -m x %s' less -f f` commits, and the delta that taught the walk to step over an assignment is what first read it as a `less`. The reading itself keeps a heredoc body only for an element that NAMES an interpreter or expands a substitution, since those are where a body is a script rather than the data every other program takes it for — where it names one is not the question, because a reserved word, a prefix command, an assignment and a redirection each stood in front of `bash <<EOF` and left the body unread. Where a command may start is `_COMMAND_START`, which the program scan and the arithmetic one are built from; an element that expands a substitution anywhere earns no exemption, because the reader written inside it is not what runs — asked instead where the substitution SITS, the question needs every prefix a command may carry and `!` alone answered it wrongly, and a separator inside one is no element boundary either. A commit missed is the one direction it may never fail in, which is also why the pre-filter requires no blank before the word — the second reading treats a quote as one. `test_skills.py` pins both to a corpus of real invocations AND of commands that merely say the word; a positive list alone is satisfied by a grammar that matches everything. A skill's `git commit`/`git merge` must spell its flags **literally** for the same reason — the hook reads the command unexpanded, so a variable standing where a flag belongs is not an invocation (`test_skills.py`).
