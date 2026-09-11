# CLAUDE.md

This repo is the **Claude Code plugin itself**, not a consumer of it. Usage:
[README.md](README.md)·[USAGE.md](USAGE.md), each with a Korean twin that `doc-sync` keeps in
step. Component authoring specs (agent/hook/skill frontmatter) come from the official docs as
SSOT, never model knowledge: [skills](https://code.claude.com/docs/en/skills.md) ·
[plugins-reference](https://code.claude.com/docs/en/plugins-reference.md) ·
[hooks](https://code.claude.com/docs/en/hooks.md) ·
[permissions](https://code.claude.com/docs/en/permissions.md).
`allowed-tools` pre-approves tools, it does not restrict — enforced at point of use by
[`.claude/rules/skill-frontmatter.md`](.claude/rules/skill-frontmatter.md) and `tests/skills/`.

`vway-kit` is the internal sister repo — not a consumer install and not an older name: the same
disciplines and gate scripts, maintained separately, propagating in neither direction. A session
here runs the **installed vway-kit**, so a discipline fixed here does not govern the work that
fixed it, and reflecting a fix there is its own task.

## Commands

```bash
uv run python -m evals.run --dry-run --all     # session count + wall-clock, no model calls
uv run python -m evals.run                     # measure skills whose description changed
uv run python -m evals.outcome                 # measure the outcome arm
```

A falling eval number re-measures that skill to confirm it, doubling its sessions over what
`--dry-run` advertised. ShellCheck every `*.sh` change **in WSL**: a shell bug hides as FAIL-OPEN
on the Windows hook runtime, and the CRLF worktree floods ShellCheck with CR errors.

## Conventions

- **English in the repo** — docs, commit messages, comments/docstrings, test assertion messages.
  Korean stays only where load-bearing: text the repo quotes rather than authors, the strings a
  test compares against it, and fixtures whose non-ASCII bytes ARE the case — translated, the
  test stays green and stops exercising anything. Internal `docs/superpowers/` stays Korean.
- **Write only what the code can't say** — [`rules/doc-style.md`](rules/doc-style.md); for a
  commit body, [`rules/risk-tiers.md`](rules/risk-tiers.md) Commit Discipline; for generated
  harness artifacts, [`rules/harness-rules.md`](rules/harness-rules.md) 5-2.
- **Dogfood new CI** — a workflow-rendering feature also lands in this repo's own
  `.github/workflows/`, every job with a tight `timeout-minutes`. Exempt: a template whose
  subject does not exist here (a REST service, a browser front end, a deployment target).
- **A test file past 500 lines becomes a folder** `tests/<what it covers>/`, every file under
  the cap, with an `__init__.py` — without it, the day two packages share a basename, pytest
  **aborts the session**. A file under the cap stays flat.
- **The dev host is Windows, CI is ubuntu** — `core.autocrlf=true` and no `.gitattributes`:
  every tracked text file is CRLF in the worktree, LF in the blob. **Never digest a tracked
  file's raw bytes** (local `pytest` green, CI red, in silence); normalize CRLF inside every new
  digest. Check shell, PATH, shebangs, file modes and path separators in **WSL** before a push.
  `/flow-init` copies byte-for-byte: consumers get CRLF `.sh` until the checkout is renormalized.
- **Mutation-test a fix, and assert the mutation applied** — a no-op edit reads as verified.
  Apply it in Python with `assert old in text`, never `sed -i`; revert with `git checkout --` from
  an already-clean tree. Assert the baseline is green where the battery runs, or every mutation
  reports as caught; a battery that carries rows forward says which it dropped for a moved
  anchor, since the edit under review moves them and the rest still sweeps clean. Mutate
  POSIX-only guards in **WSL**, and diff collected node ids around a mechanical test edit. A/B a
  claim that a gate over- or under-blocks against the released tag, over a command matrix,
  before acting on it.

## Folder structure

`agents/`, `hooks/hooks.json`, `skills/` are **auto-discovered**: adding a component is a new file.

```text
.claude-plugin/  plugin manifest · self-exposed marketplace entry (immutable sha pin)
.claude/         dev-only rules for this repo: authoring guidance, and what loads rules/ here — never ships
agents/          subagents the skills dispatch
hooks/           SessionStart · PostToolUse · Notification hooks — the commit gate is not one
skills/          one directory per slash command
rules/           shipped SSOTs: tier discipline (+ on-demand parts), harness generation, prose
scripts/         gate + setup scripts; the host copy list is flow_init_setup.py COPY_FILES
github/          consumer workflow templates /flow-init and /wiki-init render
.github/         this repo's own CI
tests/           pytest over scripts/ and over the shipped skill and rule files
evals/           skill measurement (invocation, outcome) — NOT shipped: commit as test:/chore:
docs/            internal design records (Korean, never shipped) · reference notes
```

## Architecture

- **Installed outside the host (in a cache) → dual paths.** `${CLAUDE_PLUGIN_ROOT}` reads,
  `${CLAUDE_PROJECT_DIR}` writes. **Never write into the plugin directory.** Host writes group
  under `.claude/harness-tier/`, except files whose location an external tool forces.
- **The commit gate is registered in the host's `settings.json`, not the plugin's hooks.json**,
  for deny-enforcement reliability. `settings.json` cannot resolve `${CLAUDE_PLUGIN_ROOT}`, so
  `/flow-init` copies the gate scripts and policy into the host.
- **Script propagation is one-way** — SOURCE (`scripts/`, `flow-tiers.yaml`) → cache → host
  copies. **Fix only the SOURCE** — `/flow-init` overwrites a host copy on its next re-sync.
- **Policy stays environment-free** — `flow-tiers.yaml` is plugin-owned and immutable in a host,
  and its `merge_strategy` names flows only by `flow-config.branches` **key**.
- **A consumer-facing `.md` change (rules, skills) commits as `feat`/`fix`** — `docs`/`chore`
  trigger no release, and only a `plugin.json` version bump reaches a consumer.
- **[`rules/risk-tiers.md`](rules/risk-tiers.md) is the tier-discipline SSOT**, the only rule
  injected at SessionStart; the files split from it are read on demand. Editing it or the hook
  that injects it costs every `hook_assisted` skill a live re-measure. A rate moves with *where*
  text sits beside `## Principle`'s mandate, not with how much, even on a byte-identical
  description: leave that section alone, move whole sections, and leave no "moved to X" stub —
  a pointer-only section can cost more than the text it replaced. Compare a rate only to a
  baseline of the same model and `--reps` — a plain `--all` already matches.
- **Three verification layers**, independent: the host's `.pre-commit-config.yaml`; the flow gate
  (PreToolUse, **Claude-session commits and merges only** — terminal commits and CI bypass it);
  and CI, which closes that blind spot. Per-gate mechanism: the risk-tiers glossary. PR mode takes
  a flow's merge out of the hook's sight ([`rules/promotion.md`](rules/promotion.md) PR workflow).
- **Ask a review agent for a literal `VERDICT: PASS` / `VERDICT: FAIL` line** — an ambiguous
  report reads as a pass, and the marker then records a review that never happened.
- **Skills are measured** — `tests/skills/` checks the file is well-formed, [`evals/`](evals/)
  that it is *reached* and, in the outcome arm, *executed*, whose fingerprint covers the body and
  every fixture input: a body edit costs a re-measure the description check never shows.

## Invariants (break these and the gate is silently neutralized)

Preserve these in `scripts/*` and `hooks/*.sh`; code, tests and skills cite them by number.

1. **FAIL-OPEN** — a transient internal error lets the gate pass, so a broken gate never
   permanently blocks commits. Three fail-closed exceptions:
   - **Exception 1**: `python3` ≥ 3.8 or PyYAML missing or outdated → the runner **blocks**.
   - **Exception 2**: the policy loads with its `tiers`, the config loads or is absent, no `tier`
     marker exists, and the config names the branch neither staging nor production →
     `flow_gate_check` blocks the **unclassified commit**. A missing or broken policy, or a broken
     config, fails open: the test is "works reliably", not "the file exists".
   - **Exception 3**: a `git merge` whose flags violate its flow's `merge_strategy` row — a
     missing `require` flag or a present `forbid` flag, nothing else — is blocked, decided from
     the command string alone, so no internal error can misfire it. Anything uncertain fails
     open, as does a command whose merges all run elsewhere; one merge naming no directory
     beside one that does keeps the whole command judged, behind a `cd` a deliberate over-block.
2. **Windows encoding** — the hook's Python runs in a cp949 locale, where a Korean `print()` or a
   UTF-8 `open()` can FAIL-OPEN and let a commit that should be blocked through. Keep the
   `PYTHONUTF8=1` · `force_utf8_io()` · `encoding="utf-8"` defenses.
3. **Block = exit 2 + a reason on stderr** — emit the JSON `permissionDecision` too, but exit 2
   is the mechanism.
4. **No `if` field on the settings.json gate hook** — it suppresses the hook per build. Filter in
   the runner's stdin self-filter instead.
5. **`/flow-init` is idempotent** — match-then-skip on every addition it makes to a host file.
6. **Worktree re-designation stays FAIL-OPEN** — the commit path re-points `ROOT` to the worktree
   the commit runs in, read from the command, then from the hook's own cwd; anything uncertain
   falls back to main, the resolver never guesses between directories the command's invocations
   name, and re-designation must never newly block. One declared exception: a command whose
   commit tree cannot be pinned to one place is gated anyway, since whichever tree it resolves
   to, its being clean says nothing — invocations naming different directories, an untrackable
   `cd`/`pushd`/`popd` hop (a subshell counts) before a bare commit other than the leading
   prefix, or a `-C` value still carrying shell expansion or a glob. Same-repo identity is
   `--git-common-dir` equality, never a path prefix. Keep the uncertain set small. Cases:
   `scripts/_harness_paths.py`.
7. **One authority for what a `git` invocation is** — the classifier decides; the runner's stdin
   filter only decides whether to spawn it, and stays coarser: a spelling one of them alone
   accepts is the gate off in silence. Quoting, escapes, comments and heredoc bodies are read in
   one place, and every rule is located on that mask (the anchored `cd` prefix excepted). Quoted
   text and heredoc bodies are data only until something runs them: any exemption from reading
   them as a command must err toward over-gating, and `git` never earns one. A missed commit is
   the one direction this may never fail in; `tests/skills/` pins real invocations **and** mere
   mentions. Skills spell `git commit` and `git merge` flags **literally** — the hook reads them
   unexpanded. Exemption and heredoc rules: `scripts/_harness_paths.py`.
