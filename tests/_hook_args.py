"""Hook-entry arguments both hooks must treat as mistyped; one list so a case reaches both."""

BAD_HARNESS_ARGS = [
    ("--harness", "Codex"),
    ("--harness", "cdx"),
    ("--harness",),
    ("--harness", "codex", "extra"),
]
