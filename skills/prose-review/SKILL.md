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

`$ARGUMENTS` names the paths, space-separated. Empty means the caller gave none — read
the changed files instead: `git diff --name-only HEAD` plus
`git ls-files --others --exclude-standard`. Keep this resolved list; step 4 reuses it.

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
