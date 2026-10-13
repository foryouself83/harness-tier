# Defect document template

A defect record is a failure-case database entry, not a diary. It exists to feed prompt
fixes, new rules, and regression tests. Copy the block below, fill every section, and fill
or **delete** each commented-out field — a placeholder left in place is not "optional", it
is a validation failure that blocks every commit until someone removes the line.

Quote every sha. Unquoted, `0123456` is YAML 1.1 octal and parses as the number 42798.

```markdown
---
wiki_id: defect.<slug>
title: <one line, what broke>
tags: [<area>]
affects: [<wiki id of the doc this breaks>]
# Optional — uncomment the ones that apply, delete the rest entirely.
# commit: "<sha of the commit that introduced it>"
# regression_test: <path::test_name>
# promoted_to_rule: <rules/*.md — only once actually promoted>
---

## Input
What went in — request, payload, state.

## Output
What came out, and what should have.

## Defect
The observable failure. Quote the exact error.

## Root Cause
Why it happened. One level deeper than the symptom.

## Fix
What changed, and why that closes the cause rather than the symptom.
```

`used_by` and `defects` are generated fields — never write them by hand.
Rule promotion is a human call: the threshold only raises a warning.
