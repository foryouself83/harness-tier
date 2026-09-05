import re
from pathlib import Path

import pytest

from scripts import wiki_graph
from tests.wiki_graph._helpers import _EXAMPLES, _write_config

# ---------------------------------------------------------------- prose ↔ code parity

_REPO = Path(__file__).resolve().parent.parents[1]
_TABLE_ROW_RE = re.compile(r"^\s*\|\s*`([^`]+\.md)`\s*\|\s*`([^`]+)`\s*\|", re.MULTILINE)
_ARROW_EXAMPLE_RE = re.compile(r"\b(docs/[^\s`]+?\.md)\s*(?:->|→)\s*([a-z0-9.-]+)")
# Only one file is read — wiki-init's SKILL.md — but this covers in advance the conventions of
# the other skills/ prose (indented fences, four backticks wrapping three: skills/flow,
# flow-init) and the `~~~` CommonMark allows. The opening fence comes back as a backreference,
# so inner three backticks cannot close a four-backtick block. A closing indent is accepted only
# at an absolute 0–3 columns or at the opener's +0–3: a fence inside a list measures its indent
# against the container, so the absolute branch alone cannot close its own pair, and an unbounded
# one terminates early on a deeper delimiter line inside the block. With no closer accepted, `\Z`
# swallows to end of file. Stripping too little leaks table rows; stripping too much removes the
# table and the assertions below fail loudly. The behaviour of each clause above, and the
# remaining divergence from CommonMark, are pinned to values by `_FENCE_CASES`.
_FENCE_RE = re.compile(
    r"^([ \t]*)(`{3,}|~{3,}).*?(?:^(?:[ ]{0,3}|\1[ ]{0,3})\2|\Z)", re.MULTILINE | re.DOTALL
)


def _step5_section(text: str) -> str:
    """wiki-init SKILL.md's §5 body, with fenced code blocks stripped out.

    Letting the table regex loose on the whole file drags in the same shape from other sections,
    the duplicate assertion below fires on a false positive, and the message misleads about the
    cause (that path is not duplicated in §5's table). Narrowing to the section is not enough: a
    fence is an example rather than prose, so a fence inside §5 quoting a table-row shape is the
    same false positive, and a fence line beginning `## 5.` at column 0 throws off the heading
    split as well.

    One cost on the stripping side: a row that sits BELOW the table behind an unpaired fence is
    stripped wholesale and never becomes a case. It is the one place where wiki-init SKILL.md
    §5's "adding a row adds a case" does not hold."""
    blocks = [
        b
        for b in re.split(r"^## ", _FENCE_RE.sub("", text), flags=re.MULTILINE)
        if b.startswith("5.")
    ]
    assert len(blocks) == 1, f"wiki-init SKILL.md has {len(blocks)} section-5 blocks, want 1"
    return blocks[0]


def test_wiki_init_step5_table_is_parity_tested():
    # The table IS the case set: a prose example drifting from the implementation, or the table
    # quietly shrinking, is caught here.
    text = (_REPO / "skills" / "wiki-init" / "SKILL.md").read_text(encoding="utf-8")
    rows = _TABLE_ROW_RE.findall(_step5_section(text))
    # One unpaired fence and the non-greedy pairing marries it to the next section's opener,
    # swallowing the table in between, while the `## 5.` heading survives and the block guard
    # above stays silent. An empty table then passes the duplicate assertion below vacuously and
    # the failure shows up only on the last line, reading as "the table drifted".
    assert rows, "section 5's table was not found - check the fence pairing"
    # Counted before folding into a dict: the same path on two rows leaves no trace once folded,
    # so the case set stays put while the table looks like it grew. SKILL.md is Markdown, with no
    # linter to catch a duplicate row.
    assert len({path for path, _ in rows}) == len(rows), (
        "section 5's table repeats a path across rows"
    )
    assert dict(rows) == _EXAMPLES


_STEP5_CALL_RE = re.compile(r"`python3\s+\S*wiki_graph\.py\s+([^`]+)`")


def test_wiki_init_step5_example_call_pins_the_root(tmp_path: Path, monkeypatch, capsys):
    # Step 5 derives ids before Step 7 has written wiki.root anywhere, so a call without
    # --root falls back to "docs": a user who chose website/docs gets website.docs.auth.jwt,
    # which is well-formed and unique, keeps --verify green forever, and is immutable. The
    # documented argv is RUN against a config naming another root — a substring assertion
    # would pass on a --root the CLI never honored, and on ids nobody checked.
    text = (_REPO / "skills" / "wiki-init" / "SKILL.md").read_text(encoding="utf-8")
    call = _STEP5_CALL_RE.search(_step5_section(text))
    assert call, "the --derive-id example call is gone from section 5"
    argv = call.group(1).split()

    _write_config(tmp_path, "wiki:\n  enable: true\n  root: documentation/\n")
    monkeypatch.setattr(wiki_graph, "host_root", lambda: tmp_path)
    assert wiki_graph.main(argv) == 0
    pairs = dict(line.split("\t") for line in capsys.readouterr().out.splitlines())
    assert pairs, "the example call derived no ids at all"
    assert pairs == {p: _EXAMPLES[p] for p in pairs}


# The test above does not exercise `_FENCE_RE`: its only input is wiki-init's SKILL.md, whose
# fences are a column-0 three-backtick pair outside §5, so it still passes with rows=6 even with
# the strip removed entirely. The shapes the regex claims to handle are exercised only here, so
# blocking a new shape means adding a case with it. Each case breaks if one clause of the regex
# is dropped. A "though" in a label marks a reading that diverges from CommonMark — pinned to a
# value so a change is visible — and those cases exercise clauses too, some of them the only
# guard a clause has.
_FENCE_IN = "| `docs/in.md` | `in` |"
_FENCE_KEEP = "| `docs/keep.md` | `keep` |"
_FENCE_CASES = [
    (f"   ```md\n   {_FENCE_IN}\n   ```\n\n{_FENCE_KEEP}\n", ["docs/keep.md"], "indented fence"),
    (f"~~~md\n{_FENCE_IN}\n~~~\n\n{_FENCE_KEEP}\n", ["docs/keep.md"], "tilde fence"),
    (
        f"````md\n```\n{_FENCE_IN}\n```\n````\n\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "four-backtick wrapper",
    ),
    (
        f"```text\n    ```\n{_FENCE_IN}\n```\n\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "a delimiter indented 4 inside a fence does not close it",
    ),
    # Wrapping in a list is what makes the label match the machinery: at top level CommonMark
    # does not read an opener indented 4+ as a fence at all (after a blank line it is an indented
    # code block, after a paragraph a lazy continuation), so there is nothing to "close".
    (
        f"- item\n\n     ```bash\n     {_FENCE_IN}\n     ```\n\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "a list-nested block indented past 3 closes itself",
    ),
    (
        f"  ```bash\n  {_FENCE_IN}\n```\n\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "an indented block closes at column 0",
    ),
    # The closer sits at an absolute 3 columns, which the relative branch (wanting 5) cannot
    # accept, so this exercises the top of the absolute window. The bottom is covered by the
    # column-0 case above.
    (
        f"- item\n\n     ```bash\n     {_FENCE_IN}\n   ```\n\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "a list-nested block closes at a shallower absolute indent",
    ),
    # The row-level answers agree by coincidence: the block becomes indented code and the rows
    # fall outside the prose, not because a fence closed. Move only the closer to column 0 and
    # the two readings become disjoint.
    (
        f"\t```md\n\t{_FENCE_IN}\n\t```\n\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "a tab-indented fence opens, though CommonMark reads it as an indented code block",
    ),
    (
        f"```md\n{_FENCE_IN}\n\t```\n\n{_FENCE_KEEP}\n",
        [],
        "a tab-indented delimiter does not close a space-opened fence",
    ),
    (
        f"prose ``` prose\n\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "a backtick run away from line start opens nothing",
    ),
    (
        f"``a`` inline\n\n{_FENCE_KEEP}\n\n``b`` inline\n",
        ["docs/keep.md"],
        "an inline double-backtick run opens nothing",
    ),
    (
        f"~~struck~~ text\n\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "a strikethrough run opens nothing",
    ),
    (
        f"````md\n```\n{_FENCE_IN}\n```\n\n{_FENCE_KEEP}\n",
        [],
        "an unclosed fence swallows to end of input, following rows included",
    ),
    (
        f"1. item\n\n   ```text\n   {_FENCE_IN}\n      ```\n\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "a list-nested fence closes within 3 past its opening indent",
    ),
    # The same absolute coordinates as above diverge from CommonMark once they are at top
    # level: the regex knows nothing of containers, so it closes both.
    (
        f"{_FENCE_KEEP}\n\n   ```text\n   | `docs/body.md` | `body` |\n      ```\n{_FENCE_IN}\n",
        ["docs/keep.md", "docs/in.md"],
        "a closer within 3 of the opening indent closes, though CommonMark reads it as content",
    ),
    (
        f"```md\n{_FENCE_IN}\n``` xyz\n{_FENCE_KEEP}\n",
        ["docs/keep.md"],
        "a closer with trailing text closes, though CommonMark reads on",
    ),
]
# The same input arriving twice makes one side's coverage imaginary however the labels differ,
# and there is a genuinely one-line-apart pair above (the four-backtick wrapper against its
# unclosed variant).
assert len({doc for doc, _, _ in _FENCE_CASES}) == len(_FENCE_CASES)


@pytest.mark.parametrize(
    ("doc", "expected"),
    [(doc, expected) for doc, expected, _ in _FENCE_CASES],
    ids=[label for _, _, label in _FENCE_CASES],
)
def test_fence_stripping_leaves_exactly_the_rows_outside_fences(doc, expected):
    assert [path for path, _ in _TABLE_ROW_RE.findall(_FENCE_RE.sub("", doc))] == expected


# A template that does not use {{ID}} carries its wiki_id literally, and drifts silently when
# the derivation rule changes. Each is compared against the value derived from its canonical
# output path (from its own comment and the harness-authoring convention).
_LITERAL_ID_TEMPLATES = {
    "docs-readme.template.md": "docs/README.md",
    "onboarding.template.md": "docs/onboarding/README.md",
}


def test_template_literal_ids_are_parity_tested():
    # The map is DERIVED FROM THE TEMPLATE SET rather than held by hand, so a new literal-id
    # template is caught here first — the same failure mode the comment test below guards
    # against.
    tpl_dir = _REPO / "skills" / "harness-authoring" / "templates"
    literal = {}
    for tpl in sorted(tpl_dir.glob("*.template.md")):
        m = re.search(r"^wiki_id: (\S+)$", tpl.read_text(encoding="utf-8"), re.MULTILINE)
        if m is not None and m.group(1) != "{{ID}}":
            literal[tpl.name] = m.group(1)
    assert set(literal) == set(_LITERAL_ID_TEMPLATES), (
        f"the literal wiki_id template set changed - register its output path: {sorted(literal)}"
    )
    for name, wid in literal.items():
        assert wiki_graph.derive_wiki_id(_LITERAL_ID_TEMPLATES[name], "docs") == wid, name


def test_template_comment_examples_are_parity_tested():
    # The worked examples in the harness-authoring templates' YAML comments (docs/x.md -> id, or
    # written with →) follow the same rule. Asserted per template: a floor on the total lets one
    # {{ID}} template lose its example while another template's count fills the floor back in
    # (reproduced by changing only the sds template's `->` to `→`, which under the old regex took
    # the total from 3 to 2 — still above a floor of 2).
    tpl_dir = _REPO / "skills" / "harness-authoring" / "templates"
    id_templates = [
        tpl
        for tpl in sorted(tpl_dir.glob("*.template.md"))
        if "{{ID}}" in tpl.read_text(encoding="utf-8")
    ]
    assert id_templates, "no template uses {{ID}} any more"
    for tpl in id_templates:
        matches = _ARROW_EXAMPLE_RE.findall(tpl.read_text(encoding="utf-8"))
        assert matches, f"{tpl.name}: the worked wiki_id example is gone"
        for path, expected in matches:
            assert wiki_graph.derive_wiki_id(path, "docs") == expected, tpl.name
