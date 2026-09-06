"""The prose gate: what --lint refuses, and what --verify proves a rewrite kept.

Two contracts, tested apart. --lint reads prose only — a banned word inside a fenced block or a
backtick span is data, and a rule that read it would make the rule file itself unlintable.
--verify is the other direction: it never judges prose, only that a rewrite dropped none of the
structure a reader navigates by (headings, fences, URLs, inline code) and none of the code under
a comment pass.
"""
