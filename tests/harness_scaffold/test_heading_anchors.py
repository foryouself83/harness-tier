"""Setext headings, and what a CRLF line does to the headings the anchor checker reads.

Plan `content` is the one text reaching `_has_anchor` unnormalized: a disk read translates
`\\r\\n` to `\\n`, a JSON string does not. So a `.md` authored on Windows keeps its `\\r` when
carried in a plan, and a heading the checker cannot see reports a live link dead in the
report `/harness-init` Step 5 hands its leader.
"""

import scripts.harness_scaffold as hs
from tests.harness_scaffold._helpers import _anchor_issues


def test_setext_heading_resolves(tmp_path):
    body = "Requirements Coverage\n=====\n"
    assert _anchor_issues(tmp_path, body, "../srs/README.md#requirements-coverage") == []


def test_a_heading_followed_by_a_rule_is_not_a_setext(tmp_path):
    # Without the `(?![ \t]{0,3}#)` guard the `---` turns the ATX line into a second, phantom
    # heading whose slug starts with the hashes.
    hits = _anchor_issues(tmp_path, "## A\n---\n", "../srs/README.md#-a")
    assert len(hits) == 1


def test_crlf_setext_heading_resolves(tmp_path):
    # Two things at once, because one cannot be reached without the other. `[ \t]*$` cannot
    # cross the `\r` of `=====\r\n`, so the heading went missing entirely; and `(.+)` stops
    # at `\n`, not at `\r`, so the capture that survives ends in one — left on, it outlives
    # `_SLUG_DROP_RE` (`\r` is `\s`, not punctuation) and the slug matches nothing, which is
    # what `_has_anchor`'s `heading.rstrip()` and `_slugify`'s `text.strip()` prevent.
    body = "Requirements Coverage\r\n=====\r\n"
    assert _anchor_issues(tmp_path, body, "../srs/README.md#requirements-coverage") == []


def test_crlf_atx_heading_resolves(tmp_path):
    # The ATX pattern ends in `(.+)$`, where `.` does cross `\r` — the sibling path this
    # regression never reached, pinned so a later rewrite cannot lose it silently.
    assert _anchor_issues(tmp_path, "## 요구 추적\r\n", "../srs/README.md#요구-추적") == []


def test_a_crlf_blank_line_is_not_a_setext_heading():
    # The other half, and a different input: the blank-line lookahead carries its `\r?` for
    # its own reason. Without it `\r\n` reads as content, so a CRLF blank line before a
    # thematic break becomes a heading whose slug is empty, shifting every later
    # empty-slug setext heading's suffix by one. Masked while the tail was also
    # `\r`-blind (the underline never matched), it goes live the moment that half
    # is fixed.
    assert hs._SETEXT_RE.findall("Intro\r\n\r\n-----\r\n") == []
