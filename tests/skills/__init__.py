"""Guards for the plugin's own skills — the artefacts that *are* the product.

A `SKILL.md` edit changes what every consumer's agent does, yet until now nothing in
this suite read one. That gap is exactly how command-era frontmatter (`allowed-tools`
on 9 skills) and a hardcoded `./tests` search survived unnoticed: `uv run pytest`
stayed green the whole time because no test ever opened these files.

Two layers:

* **structural** — frontmatter parses and conforms to the official spec, links and
  section references resolve, no shipped command carries an un-runnable placeholder.
* **behavioural** — the case-discovery command is extracted *from the shipped skill*
  and run against real fixture projects. Testing the artefact rather than a copy is
  the point: a copy drifts, and drift is the bug class this package exists to catch.

Spec reference (verify against the docs, not model knowledge — see CLAUDE.md):
https://code.claude.com/docs/en/skills.md
"""
