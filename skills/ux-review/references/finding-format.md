# Finding Format

Every outsider returns Markdown in this shape and nothing else. The owner merges the lists by
the key `(screen, element, heuristic)`.

## Customer: blockers

The customer has no rubric, so it reports what stopped it, not which rule broke.

```markdown
## Understanding
- <screen>: <what the customer thinks this screen is for, one line>

## Path
- <screen>: <what the customer would press or type next to do the task>

## Blockers
- screen: <screen name from the file path>
  element: <visible label or description of the element>
  reason: <why the customer hesitated, guessed or stopped, in the customer's words>
```

An empty `Blockers` list is a valid answer. The owner compares `Path` with the intended path
and turns each divergence into a blocker with `reason: path diverged`.

## Auditor: findings

```markdown
- id: <screen>-<n>
  screen: <screen name from the file path>
  element: <selector from axe.json or aria.txt, else the visible label>
  heuristic: <checklist id, e.g. H9, F6, A6>
  severity: <2|3|4>
  evidence: <what in the capture shows it: a quote from aria.txt or a described region>
  suggestion: <the fix direction, one line>
```

At most 8 findings per auditor, highest severity first. Severity follows
[heuristics.md](heuristics.md#severity-04).

## Owner: report

The owner writes `report.md` in the run directory. Each finding carries the auditor fields
plus:

- `source`: `axe`, `customer` or `auditor`
- `status`: `accept`, `contest` (with the design-system or product reason) or `needs-human`
- `fixed`: the finding is in the user's chosen set and the change is applied

The report header records `mode` (`capture` or `static`), `customer` (`ran` or
`not run (static mode)`), `outsiders` (`ran` or `skipped`), the flows, and the run directory.
