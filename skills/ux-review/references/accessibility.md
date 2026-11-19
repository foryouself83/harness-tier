# Accessibility: Judgement Items (WCAG 2.2 AA)

`@axe-core/playwright` checks what a rule engine can decide: contrast ratios, missing names
and labels, ARIA validity, landmark structure. This file holds the WCAG 2.2 AA success
criteria that need a judgement axe cannot make. The auditor checks these and skips anything
already in the screen's `axe.json`.

| Id | Criterion | Violation signal | Fix direction |
|----|-----------|------------------|---------------|
| A1 | 1.3.2 Meaningful Sequence (A) | The `aria.txt` order differs from the visual reading order; a label reads after its field | DOM order follows the visual order |
| A2 | 1.3.3 Sensory Characteristics (A) | Instructions rely on shape, colour or position alone ("click the green button", "see right") | Name the control as well |
| A3 | 1.4.1 Use of Color (A) | Errors, required fields or status shown by colour only | Add text or an icon with a text alternative |
| A4 | 2.4.3 Focus Order (A) | Tab order jumps across regions or into hidden content | Focus follows the task order |
| A5 | 2.4.6 Headings and Labels (AA) | Headings or labels exist but do not describe the content or purpose ("Details", "Click here") | Specific, descriptive text |
| A6 | 2.4.7 Focus Visible (AA) | Focus outline removed or invisible against the background | A visible focus indicator on every focusable control |
| A7 | 2.4.11 Focus Not Obscured (Minimum) (AA) | A sticky header, footer or banner covers the focused control | Scroll padding, or move the overlay |
| A8 | 2.5.3 Label in Name (A) | The accessible name does not contain the visible label text | Accessible name starts with the visible label |
| A9 | 2.5.7 Dragging Movements (AA) | A drag (reorder, slider, map pan) has no single-pointer alternative | Buttons or inputs that do the same |
| A10 | 2.5.8 Target Size (Minimum) (AA) | Pointer targets smaller than 24×24 CSS px without enough spacing | Enlarge to 24×24 or space them apart |
| A11 | 3.2.2 On Input (A) | Changing a field submits, navigates or opens something unannounced | Change context only on an explicit action |
| A12 | 3.2.6 Consistent Help (A) | Help or contact appears in different places across screens | Same relative position on every screen |
| A13 | 3.3.1 Error Identification (A) | An error is shown without saying which field or what is wrong | Name the field and the problem in text |
| A14 | 3.3.3 Error Suggestion (AA) | The fix is known (a format, a range) but not suggested | State the expected format or value |
| A15 | 3.3.7 Redundant Entry (A) | The flow asks again for information already given in it | Prefill or offer to reuse |
| A16 | 3.3.8 Accessible Authentication (Minimum) (AA) | Login needs a memory or transcription test; paste blocked in password or code fields | Allow paste and password managers; offer an alternative |

## Sources

- https://www.w3.org/TR/WCAG22/
- https://www.w3.org/WAI/WCAG22/Understanding/
- https://github.com/dequelabs/axe-core/blob/develop/doc/rule-descriptions.md
