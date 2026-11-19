# Visual Hierarchy

Rules for judging a screenshot: what the eye lands on first, what reads as a group, and
whether the screen looks like one product.

| Id | Rule | Violation signal | Fix direction |
|----|------|------------------|---------------|
| V1 | One primary action per view | Two or more filled buttons of equal weight; the primary action below the fold on desktop | One filled primary; secondary actions outlined or text |
| V2 | Proximity groups | A label closer to the neighbouring field than to its own; equal spacing everywhere | Less space inside a group than between groups |
| V3 | Similarity signals sameness | Items that behave alike look different, or different items look alike | One style per role |
| V4 | Common region | Related controls float with no container or divider | A card, panel or divider around the group |
| V5 | Type scale | More than a few font sizes; headings barely larger than body | A small fixed scale (display, headline, title, body, label) |
| V6 | Readable text | Body text smaller than 16 px on mobile; lines longer than about 80 characters | Body at 16 px or more; constrain line length |
| V7 | Spacing system | Arbitrary gaps (13 px, 22 px) with no rhythm | Spacing from one scale (a 4 or 8 px grid) |
| V8 | Alignment | Edges that almost line up; mixed alignment inside one group | Align to a shared grid edge |
| V9 | Emphasis budget | Colour, bold, icons and badges used everywhere | Reserve emphasis for what needs attention |
| V10 | State is visible | Disabled, selected and hover states look alike | Distinct styles per state, not by colour alone |
| V11 | Mobile layout holds | Horizontal scroll, clipped text or overlapping elements at 390 px | Reflow into one column; wrap text |
| V12 | Design-system fit | A component or token on this screen differs from the rest of the product | Use the existing component or token |

The owner judges V12; outsiders never see the design system. A V12 finding from the owner
outranks an outsider's general preference on the same element.

## Sources

- https://www.nngroup.com/articles/visual-hierarchy-ux-definition/
- https://www.nngroup.com/articles/gestalt-proximity/
- https://m3.material.io/styles/typography/type-scale-tokens
- https://m3.material.io/foundations/layout/understanding-layout/spacing
