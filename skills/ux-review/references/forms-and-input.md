# Forms and Input

Forms are where most task failures happen. These rules come from large form-usability studies.

| Id | Rule | Violation signal | Fix direction |
|----|------|------------------|---------------|
| F1 | Persistent labels | Placeholder used as the only label; the label disappears on typing | A visible label above the field |
| F2 | Top-aligned labels | Labels left of fields in a mobile or long form | Labels above fields |
| F3 | Single column | Fields side by side that are not one logical value | One field per row, except tightly paired values |
| F4 | Mark the exception | Every field marked required, or none marked | Mark required and optional explicitly |
| F5 | Validate at the right time | Errors shown while the user is still typing the first time; errors only after submit on a long form | Validate on leaving the field; re-validate live once an error is shown |
| F6 | Error placement and text | Errors in a banner far from the field; generic "Invalid input" | Message next to the field: what is wrong and how to fix it |
| F7 | Keep the input | A failed submit clears the fields | Preserve every value |
| F8 | Right input type | A numeric or email field opens a text keyboard on mobile; no `autocomplete` | Matching `type`, `inputmode` and `autocomplete` |
| F9 | Ask only what is needed | Optional or derivable fields in the main path | Remove, defer or derive them |
| F10 | Format tolerance | Phone, card or date rejected for spaces or separators | Accept and normalise (see `laws-of-ux.md` L10) |
| F11 | Specific submit label | A submit button reading "Submit" or "OK" | The outcome as a verb: "Create account", "Pay $42" |
| F12 | Choice controls | A dropdown for two or three options; radio buttons for a long list | Radios for few options, a select or search for many |

## Sources

- https://baymard.com/learn/form-design
- https://www.nngroup.com/articles/web-form-design/
- https://www.nngroup.com/articles/errors-forms-design-guidelines/
- https://www.nngroup.com/articles/form-design-placeholders/
