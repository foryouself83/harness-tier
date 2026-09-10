"""GitHub's anchor rules, as the repo's markdown consumers need them.

Its own module because two entry points need it: `harness_scaffold.validate_plan` checks
a plan's links at generation time, and `srs_check` checks a hand-edited SRS. The host
receives them as flat sibling files, so a shared helper has to be importable without
`harness_scaffold`, which is not copied there.
"""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import unquote

# Two stages, not one pattern: `<a\s(?:[^>]*\s)?id=` overlaps `[^>]*` with `\s` and goes
# quadratic on a long tag. The `(?:^|\s)` boundary is what keeps `data-id=` out.
_A_TAG_RE = re.compile(r"<a\s[^>]*>", re.IGNORECASE)
_ID_ATTR_RE = re.compile(r"(?:^|\s)id\s*=\s*[\"']([^\"']+)[\"']", re.IGNORECASE)
# The closing `#` run comes off in Python. As `\s*#*\s*$` it split one whitespace run two
# ways while the lazy `(.+?)` regrew over it — cubic, 18s on a 2.4KB heading line. `[ \t]`
# also stops `\s` from crossing a newline.
_HEADING_RE = re.compile(r"^[ \t]{0,3}#{1,6}[ \t]+(.+)$", re.MULTILINE)
# Both `\r?` are load-bearing, on different input: plan `content` arrives with its newlines
# unnormalized (a disk read translates them, a JSON string does not), and `$` sits after the
# `\r`. Without the tail one a CRLF setext heading matches nothing and every link into it
# reads dead; without the lookahead one a CRLF blank line is content, so it becomes a
# heading with an empty slug, shifting every later empty-slug setext suffix by one.
# Neither revives the split above — `\r` is outside `[ \t]`, leaving one way to match it.
_SETEXT_RE = re.compile(
    r"^(?![ \t]*\r?$)(?![ \t]{0,3}#)(.+)\n[ \t]{0,3}(?:=+|-+)[ \t]*\r?$", re.MULTILINE
)
_MD_INLINE_LINK_RE = re.compile(r"\[([^\]]*)\]\([^)]*\)")
# A well-formed tag or comment — what a renderer drops. A loose `<[^>]+>` also eats
# `Map<K,V>` and `2 < 3`, which GitHub keeps.
_HTML_TAG_RE = re.compile(r"<!--.*?-->|</?[A-Za-z][A-Za-z0-9-]*(?:\s[^>]*)?/?>", re.DOTALL)
# Complete entities only: `html.unescape` also decodes `&amp`/`&copy`, which CommonMark
# leaves literal.
_HTML_ENTITY_RE = re.compile(r"&(?:#\d+|#[xX][0-9a-fA-F]+|[A-Za-z][A-Za-z0-9]*);")
_SLUG_DROP_RE = re.compile(r"[^\w\s-]", re.UNICODE)
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`]+`")


def _slugify(text: str) -> str:
    """GitHub's heading slug, per `github-slugger`.

    Three details its rules turn on: `_` survives, each space becomes its own `-` AFTER
    punctuation is dropped (`## Step 1 — Classify` → `step-1--classify`), and `\\w` under
    re.UNICODE keeps Hangul.
    """
    text = _MD_INLINE_LINK_RE.sub(r"\1", text)
    # Rendered text is what GitHub slugs. Tags first: decoding earlier turns `&lt;script&gt;`
    # into a tag shape the strip then eats.
    text = _HTML_ENTITY_RE.sub(lambda m: unescape(m.group(0)), _HTML_TAG_RE.sub("", text))
    return _SLUG_DROP_RE.sub("", text.strip().lower()).replace(" ", "-")


def _has_anchor(text: str, frag: str) -> bool:
    """True when `frag` names an explicit <a id> or a heading in `text`.

    Headings are walked in order: GitHub suffixes a repeated slug `-1`, `-2`. Front matter
    and code fences come off both lookups — neither renders. Inline code spans stay; GitHub
    slugs the rendered text.
    """
    body = _CODE_FENCE_RE.sub("", _strip_frontmatter(text))
    # A copied GitHub anchor arrives percent-encoded.
    wanted = {frag.lower(), unquote(frag).lower()}
    explicit = (a for tag in _A_TAG_RE.findall(body) for a in _ID_ATTR_RE.findall(tag))
    if wanted & {a.lower() for a in explicit}:
        return True
    seen: dict[str, int] = {}
    for heading in _HEADING_RE.findall(body) + _SETEXT_RE.findall(body):
        # The ATX closing run, which the pattern no longer eats.
        base = _slugify(heading.rstrip().rstrip("#").rstrip())
        nth = seen.get(base, 0)
        seen[base] = nth + 1
        if (base if nth == 0 else f"{base}-{nth}") in wanted:
            return True
    return False


def _strip_frontmatter(text: str) -> str:
    """Return only the body with the frontmatter block removed (so link scans skip metadata)."""
    m = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
    return text[m.end() :] if m else text


def _strip_code(text: str) -> str:
    """Remove code fences·inline code (so link scans don't flag code examples as dead links)."""
    return _INLINE_CODE_RE.sub("", _CODE_FENCE_RE.sub("", text))
