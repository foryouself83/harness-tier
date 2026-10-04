---
name: prose-review
description: Use when comments, docstrings or documents need checking against the prose rules — before writing them, or to clean up what is already there. The doc-sync gate calls it.
argument-hint: "[paths… | empty = changed files]"
---

# prose-review

Half of the prose rules are patterns and half are judgement.
[`doc-style.md`](../../rules/doc-style.md) is the rule; this skill runs both halves over
files you name.

Report every violation in the language the user is writing in, and write what follows each
box key the same way. The three box keys — `CRITICAL TRAP:`, `Trigger:`, `Symptom:` — stay
literal in every project: the checker parses them. The rule file is English; the reader may
not be.

## 1. The machine half

`$ARGUMENTS` names the paths, space-separated. Empty means the caller gave none — take the
changed files, narrowed to the project's doc-style scope (its `paths` and `exclude`, or every
`.md`, `.py` and `.sh` where `doc_style` is off or absent), so nothing the project excluded is
rewritten. Run it from the repository root; it prints root-relative paths, one per line:

```bash
{ git diff -z --name-only HEAD; git ls-files -z --others --exclude-standard; } |
  xargs -0 python3 .claude/harness-tier/scripts/doc_style_check.py --scope
```

The lists travel NUL-separated: a path holding a space stays one argument.

An `unrecognized arguments` error means the host copy of the script predates `--scope`, and
a repo without the script has nothing to run: say so, tell the user to re-run `/flow-init`,
and take the two `git` lists unnarrowed. Never continue with an empty list the failure left.

Keep this resolved list; step 4 reuses it. Quote each path wherever a command below takes
`<paths>`.

```bash
python3 .claude/harness-tier/scripts/doc_style_check.py --lint <paths>
```

`ANCHOR` · `META` · `TRAP` · `HIST` · `SHA` · `PLAN` · `FILLER` · `ENDING` are decided
here, and a repo without the script skips this step and keeps the judgement half.

## 2. The judgement half

No pattern answers these. Read each comment, docstring and paragraph the paths carry:

- **Does it explain how?** A paraphrase of the code beneath it goes, whatever it costs.
- **Could the code raise instead?** A constraint stated in prose that an `assert`, a
  validated bound or a type could carry is a comment that should not exist. Propose the
  check, not a better sentence.
- **Is it self-evident?** A comment restating its own identifier is noise.
- **Is a number a measurement or a contract?** Anything else is a guess wearing a figure —
  give the direction instead.
- **Is it as short as it can be?** Nominal endings, no connective padding.

## 3. Fix

Show each violation with the replacement, grouped by file. Apply what the user accepts.

## 4. Prove nothing was lost

Run this over the same list step 1 resolved, not a freshly re-derived changed-file list —
the fix itself can create or rename files, and re-deriving here would verify a different set
than the one already rewritten. Skip this step when that list is empty: `--verify-git` errors
on no arguments, where `--lint` above silently no-ops on the same case.

```bash
python3 .claude/harness-tier/scripts/doc_style_check.py --verify-git <paths>
```

A rewrite that drops a heading, a fenced block, a URL or an inline-code span is a rewrite
that lost the fact. Restore it, or say in the report why the removal was the point.
