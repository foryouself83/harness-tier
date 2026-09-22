"""Line-level Markdown reading for the design-doc checker and renderer.

Stdlib and PyYAML only: the checker runs before the renderer's dependencies are
installed, so a template error reaches the user before any install question.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import yaml

_FRONT_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---[ \t]*(?:\n|\Z)", re.DOTALL)
_FENCE_OPEN_RE = re.compile(r"^[ \t]{0,3}(`{3,}|~{3,})[ \t]*([\w+-]*)")
_HEADING_RE = re.compile(r"^[ \t]{0,3}(#{1,6})[ \t]+(.+)$")
_CLOSING_HASHES_RE = re.compile(r"[ \t]+#+$")
_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
ANCHOR_RE = re.compile(r'<a\s[^>]*\bid\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
# Same shape as srs_check._LINK_RE: images excluded, optional title allowed.
_LINK_RE = re.compile(
    r"(?<!!)\[[^\]]*\]\(\s*([^)\s#]*)(?:#([^)\s]*))?(?:\s+[\"'][^\")]*[\"'])?\s*\)"
)
_LINK_URL_RE = re.compile(r"\]\([^)]*\)")
_TAG_RE = re.compile(r"</?[A-Za-z][^>]*>")
_INLINE_CODE_RE = re.compile(r"`[^`]*`")
_SEP_CELL_RE = re.compile(r"^:?-+:?$")
ID_TOKEN_RE = re.compile(r"(?<![\w-])([A-Z][A-Z0-9]*(?:-[A-Z][A-Z0-9]*)*-\d{3})(?![\w-])")
PLACEHOLDER_RE = re.compile(r"\{\{[^}]*\}\}")
_REPEAT_SENTINEL = "\x00repeat:"


@dataclass
class Heading:
    level: int
    text: str
    raw: str
    line: int


@dataclass
class Table:
    path: tuple[str, ...]
    header: list[str]
    rows: list[list[str]]
    line: int


@dataclass
class Fence:
    lang: str
    body: str
    line: int


@dataclass
class Doc:
    front: dict | None
    front_error: str | None
    headings: list[Heading] = field(default_factory=list)
    tables: list[Table] = field(default_factory=list)
    fences: list[Fence] = field(default_factory=list)
    anchors: list[tuple[str, int]] = field(default_factory=list)
    links: list[tuple[str, str, int]] = field(default_factory=list)
    tokens: list[tuple[str, int]] = field(default_factory=list)
    placeholders: list[tuple[str, int]] = field(default_factory=list)
    repeats: list[tuple[str, int]] = field(default_factory=list)
    last_line: int = 0

    def section_end(self, idx: int) -> int:
        level = self.headings[idx].level
        for h in self.headings[idx + 1 :]:
            if h.level <= level:
                return h.line
        return self.last_line + 1

    def tokens_between(self, start: int, end: int) -> list[str]:
        return [t for t, n in self.tokens if start <= n < end]

    def tables_between(self, start: int, end: int) -> list[Table]:
        return [t for t in self.tables if start <= t.line < end]

    def fences_between(self, start: int, end: int) -> list[Fence]:
        return [f for f in self.fences if start <= f.line < end]


def split_front(text: str) -> tuple[dict | None, str | None, str, int]:
    text = text.replace("\r\n", "\n")
    m = _FRONT_RE.match(text)
    if not m:
        return None, None, text, 0
    offset = text[: m.end()].count("\n")
    if not text[: m.end()].endswith("\n"):
        offset += 1
    try:
        loaded = yaml.safe_load(m.group(1))
    except yaml.YAMLError as exc:
        return None, f"front matter YAML error: {str(exc).splitlines()[0]}", text[m.end() :], offset
    if not isinstance(loaded, dict):
        return None, "front matter is not a mapping", text[m.end() :], offset
    return loaded, None, text[m.end() :], offset


def plain(text: str) -> str:
    return _TAG_RE.sub("", text).replace("**", "").strip()


def split_cells(line: str) -> list[str]:
    s = line.strip()
    if s.startswith("|"):
        s = s[1:]
    if s.endswith("|") and not s.endswith("\\|"):
        s = s[:-1]
    # A pipe inside inline code is content, not a cell border.
    cells: list[str] = []
    buf = ""
    in_code = False
    for ch_idx, ch in enumerate(s):
        if ch == "`":
            in_code = not in_code
        if ch == "|" and not in_code and (ch_idx == 0 or s[ch_idx - 1] != "\\"):
            cells.append(buf.strip())
            buf = ""
            continue
        buf += ch
    cells.append(buf.strip())
    return cells


def _is_separator(line: str) -> bool:
    if "|" not in line:
        return False
    cells = split_cells(line)
    return bool(cells) and all(_SEP_CELL_RE.match(c) for c in cells)


def _strip_comments(body: str) -> str:
    """Blank every comment but keep its newlines, so line numbers survive; the repeat
    marker is a comment the checker needs, so it is swapped for a sentinel first."""
    body = re.sub(
        r"<!--[ \t]*repeat:[ \t]*([A-Z][A-Z0-9]*)[ \t]*-->",
        lambda m: _REPEAT_SENTINEL + m.group(1),
        body,
    )
    return _COMMENT_RE.sub(lambda m: "\n" * m.group(0).count("\n"), body)


def _scan_inline(doc: Doc, s: str, no: int) -> None:
    for m in ANCHOR_RE.finditer(s):
        doc.anchors.append((m.group(1).lower(), no))
    code_free = _INLINE_CODE_RE.sub("", s)
    for m in _LINK_RE.finditer(code_free):
        doc.links.append((m.group(1), m.group(2) or "", no))
    prose = _LINK_URL_RE.sub("]", _TAG_RE.sub("", code_free))
    for m in ID_TOKEN_RE.finditer(prose):
        doc.tokens.append((m.group(1), no))
    for p in PLACEHOLDER_RE.findall(s):
        doc.placeholders.append((p, no))


def _close_fence(doc: Doc, fence: tuple) -> None:
    """A fence body that is nothing but one `{{...}}` is the shipped diagram-slot
    placeholder; anything else (e.g. a mermaid hexagon node `A{{hex}}`) is content."""
    body = "\n".join(fence[3])
    stripped = body.strip()
    if PLACEHOLDER_RE.fullmatch(stripped):
        doc.placeholders.append((stripped, fence[2]))
    doc.fences.append(Fence(fence[1], body, fence[2]))


def parse(text: str) -> Doc:
    front, err, body, offset = split_front(text)
    doc = Doc(front=front, front_error=err)
    lines = _strip_comments(body).split("\n")
    doc.last_line = offset + len(lines)
    path: list[tuple[int, str]] = []
    fence: tuple[str, str, int, list[str]] | None = None
    i = 0
    while i < len(lines):
        ln = lines[i]
        no = offset + i + 1
        if fence is not None:
            stripped = ln.strip()
            marker = fence[0]
            if stripped.startswith(marker) and set(stripped) == {marker[0]}:
                _close_fence(doc, fence)
                fence = None
            else:
                fence[3].append(ln)
            i += 1
            continue
        fm = _FENCE_OPEN_RE.match(ln)
        if fm:
            fence = (fm.group(1), fm.group(2).lower(), no, [])
            i += 1
            continue
        if ln.strip().startswith(_REPEAT_SENTINEL):
            doc.repeats.append((ln.strip()[len(_REPEAT_SENTINEL) :], no))
            i += 1
            continue
        hm = _HEADING_RE.match(ln)
        if hm:
            level = len(hm.group(1))
            raw = _CLOSING_HASHES_RE.sub("", hm.group(2)).strip()
            doc.headings.append(Heading(level, plain(raw), raw, no))
            while path and path[-1][0] >= level:
                path.pop()
            path.append((level, plain(raw)))
            _scan_inline(doc, raw, no)
            i += 1
            continue
        if ln.lstrip().startswith("|") and i + 1 < len(lines) and _is_separator(lines[i + 1]):
            header = [plain(c) for c in split_cells(ln)]
            _scan_inline(doc, ln, no)
            rows: list[list[str]] = []
            j = i + 2
            while j < len(lines) and lines[j].lstrip().startswith("|"):
                rows.append(split_cells(lines[j]))
                _scan_inline(doc, lines[j], offset + j + 1)
                j += 1
            doc.tables.append(Table(tuple(t for _, t in path), header, rows, no))
            i = j
            continue
        _scan_inline(doc, ln, no)
        i += 1
    if fence is not None:
        _close_fence(doc, fence)
    return doc
