# DRY / Extract Magic Values into Constants (injection block)

- **Do not repeat magic numbers, magic strings, or magic codes.** Extract them into
  meaningfully named constants defined in a single place.
- **Do not copy-paste the same logic or the same value (DRY).** If it appears more than once, factor it out.
- However, do not violate YAGNI — do not pre-abstract one-off code that is used only once.
