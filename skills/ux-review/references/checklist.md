# Auditor Checklist

One line per check, ids matching the full references. The auditor reads only the sections the
owner names. Skip any item already reported in the screen's `axe.json`.

## Heuristics

Full text: [heuristics.md](heuristics.md), [laws-of-ux.md](laws-of-ux.md).

- [H1] Every action gives visible feedback; waits show progress; current state is marked.
- [H2] Labels use the user's words, not internal or technical terms.
- [H3] Every mode has a visible exit; destructive actions can be undone or are confirmed.
- [H4] The same action has one name, one look and one place across screens.
- [H5] Input is constrained where possible; dangerous actions sit apart from frequent ones.
- [H6] Nothing must be remembered from a previous screen.
- [H7] Frequent tasks have defaults, recent items or bulk actions.
- [H8] Nothing competes with the primary task on the screen.
- [H9] Errors state the cause and the next step, next to the problem.
- [H10] Complex steps have help at the point of need.
- [L1] The primary target is large and near where attention ends.
- [L2] Choices are few, grouped or staged; one is recommended when it can be.
- [L4] Long values are chunked; long forms are split into steps.
- [L7] The flow ends on a clear outcome with a next step.
- [L9] Multi-step flows show progress.

## Visual

Full text: [visual-hierarchy.md](visual-hierarchy.md).

- [V1] Exactly one primary action per view, visible without scrolling on desktop.
- [V2] Spacing inside a group is smaller than between groups.
- [V3] Elements with the same role share one style.
- [V5] Few font sizes; headings clearly larger than body.
- [V6] Body text is 16 px or more on mobile; lines stay readable in length.
- [V8] Edges align to a shared grid.
- [V9] Emphasis (colour, bold, badges) is reserved for what needs attention.
- [V10] Disabled, selected and hover states are distinct, not by colour alone.
- [V11] At 390 px nothing scrolls sideways, clips or overlaps.

## Forms

Full text: [forms-and-input.md](forms-and-input.md).

- [F1] Every field has a visible label that stays while typing.
- [F3] One field per row unless the fields form one value.
- [F4] Required and optional fields are marked explicitly.
- [F5] Validation runs on leaving the field, not while first typing.
- [F6] Each error sits next to its field and says how to fix it.
- [F8] Field types open the right mobile keyboard and support autofill.
- [F9] Only fields the task needs are in the main path.
- [F11] The submit button names the outcome.
- [F12] Few options use radios; many options use a select or search.

## Microcopy

Full text: [microcopy.md](microcopy.md).

- [M1] Buttons name the outcome as verb plus object.
- [M2] Confirmations state the consequence and label buttons with actions.
- [M3] Errors give the cause and the fix, with no blame or codes.
- [M4] Empty states explain why and offer the action that fills them.
- [M5] One term per object across the product.
- [M7] Link text names the destination.
- [M8] Completed actions are confirmed.

## Accessibility (judgement only)

Full text: [accessibility.md](accessibility.md).

- [A1] The accessibility tree order matches the visual reading order.
- [A3] No status, error or requirement is shown by colour alone.
- [A5] Headings and labels describe their content specifically.
- [A6] Focus is visible on every focusable control.
- [A7] Sticky elements never cover the focused control.
- [A9] Every drag has a single-pointer alternative.
- [A10] Pointer targets are 24×24 CSS px or spaced apart.
- [A11] Changing a field never navigates or submits on its own.
- [A13] Errors name the field and the problem in text.
- [A15] The flow never asks twice for the same information.
- [A16] Login allows paste and password managers.
