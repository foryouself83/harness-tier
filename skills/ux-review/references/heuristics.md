# Usability Heuristics and Severity

Nielsen's ten heuristics are the default lens for the auditor. Each row gives the rule, the
signal that it is broken on a screen, and the direction of the fix.

Owner/outsider split: Elephant-Goldfish Model, https://github.com/google/elephant-goldfish-model

| Id | Heuristic | Violation signal | Fix direction |
|----|-----------|------------------|---------------|
| H1 | Visibility of system status | An action gives no feedback; a load shows nothing; the current step or selection is not marked | Immediate feedback within the region acted on; progress for waits; mark the current state |
| H2 | Match between system and the real world | Internal or technical terms (`entity`, `payload`, error codes); an order that follows the data model, not the task | The user's words and the task's order |
| H3 | User control and freedom | No cancel, back or undo; a modal with no exit; a destructive action with no recovery | Undo over confirm; a visible exit from every mode |
| H4 | Consistency and standards | The same action named or placed differently across screens; a link styled as a button; a platform convention broken | One name and one look per action; follow the platform's conventions |
| H5 | Error prevention | A free-text field where a choice would do; a destructive action next to a frequent one; no constraint on invalid input | Constrain input, separate dangerous actions, set safe defaults |
| H6 | Recognition rather than recall | The user must remember a value from a previous screen; options hidden until typed | Keep needed information visible; show options |
| H7 | Flexibility and efficiency of use | A frequent task takes the same many steps every time; no shortcut, default or bulk action | Accelerators that do not burden novices: defaults, recent items, bulk actions |
| H8 | Aesthetic and minimalist design | Competing calls to action; decoration or rarely used content crowding the primary task | Remove or demote what does not serve the task on this screen |
| H9 | Help users recognize, diagnose, and recover from errors | An error with no cause or no next step; a red border with no text; an error far from its field | Plain-language cause and a concrete next step, next to the problem |
| H10 | Help and documentation | A complex step with no inline help; help that is only reachable by leaving the task | Contextual help at the point of need |

## Severity (0–4)

Severity combines frequency, impact and persistence. Rate the problem, not the fix.

| Score | Meaning | Typical signal |
|-------|---------|----------------|
| 0 | Not a usability problem | Disagreement on taste only |
| 1 | Cosmetic | Noticed, no effect on completing the task |
| 2 | Minor | Slows the user or causes a recoverable mistake |
| 3 | Major | Many users fail or need help; important to fix before release |
| 4 | Catastrophe | The task cannot be completed, or data is lost |

The auditor reports severity 2 and above. Severity 0–1 belongs in a polish list, never in the
findings that compete for the user's attention.

## Sources

- https://www.nngroup.com/articles/ten-usability-heuristics/
- https://www.nngroup.com/articles/how-to-rate-the-severity-of-usability-problems/
