"""Numbering and integrity for docs/srs — the requirement text's SSOT.

Its own entry point because nothing else reads a hand-edited SRS: `_has_anchor` runs only
inside `validate_plan`, which sees generated plans; `doc_invariants` counts links without
resolving them; `wiki_graph --verify` reads front-matter edges. The dead anchors that
incremental editing produces have no reader today.

Not a gate. An absent docs/srs is exit 0 with no output, and every check reports rather
than blocks — the verdict is the srs-verify workflow's.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    from _harness_paths import force_utf8_io
except ImportError:
    from scripts._harness_paths import force_utf8_io

try:
    from _md_anchors import _CODE_FENCE_RE, _has_anchor
except ImportError:
    from scripts._md_anchors import _CODE_FENCE_RE, _has_anchor

SRS_REL = "docs/srs"
INDEX_STEM = "README"
_H1_RE = re.compile(r"^[ \t]{0,3}#[ \t]+(.+)$", re.MULTILINE)
_FRONT_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)
_ANCHOR_RE = re.compile(r'<a\s[^>]*\bid\s*=\s*["\']([^"\']+)["\']', re.IGNORECASE)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)


def srs_dir(root: Path) -> Path | None:
    d = root / SRS_REL
    return d if d.is_dir() else None


def _title(text: str) -> str:
    body = _FRONT_RE.sub("", text)
    m = _H1_RE.search(body)
    return m.group(1).strip() if m else ""


def area_files(root: Path) -> list[Path]:
    d = srs_dir(root)
    if d is None:
        return []
    return sorted(p for p in d.glob("*.md") if p.stem != INDEX_STEM)


def areas(root: Path) -> list[tuple[str, str]]:
    return [(p.stem, _title(p.read_text(encoding="utf-8"))) for p in area_files(root)]


def _strip_examples(text: str) -> str:
    """Fenced code and HTML comments removed — what a worked authoring example lives inside.

    Shared by `_anchors` (definitions) and `_check_links` (this file's own outgoing
    links), so an example anchor and an example link inside the same comment are both
    excluded the same way. `_md_anchors._HTML_TAG_RE` is not reused: it also strips real
    `<a>` tags, which is wrong for a definition scan.
    """
    return _HTML_COMMENT_RE.sub("", _CODE_FENCE_RE.sub("", text))


def _anchors(text: str) -> list[str]:
    """Anchors this file DEFINES.

    Deliberately asymmetric with `_has_anchor` (resolves a link's TARGET, in
    `_check_links`): a real anchor defined only inside the DESTINATION file's comment
    still resolves as a valid link target, since `_has_anchor` never strips comments and
    the forgiving direction is the safer one there. This file's own definitions and its
    own outgoing links (`_strip_examples`) are the strict side.
    """
    return [a.lower() for a in _ANCHOR_RE.findall(_strip_examples(text))]


def _default_scope(path: Path) -> str | None:
    """An area file scopes by its own stem; the index scopes by nothing.

    The file decides, not the kind — which is what keeps the KIND set open.
    """
    return None if path.stem == INDEX_STEM else path.stem


class ScopeRequired(Exception):
    """`kind` already carries an axis in this file, so an unscoped call is ambiguous."""


def _scope_established(text: str, kind: str) -> bool:
    """True when `text` already anchors `kind` under an axis, not a bare number.

    Read off the file's own anchors, never off `kind` itself, so the KIND set stays
    open: a kind with no scoped history is free to start flat. A `<a id="kind-axis">`
    section anchor counts on its own, before any numbered item exists under it — that
    is exactly what a scaffolded, still-empty axis looks like.
    """
    prefix = f"{kind.lower()}-"
    return any(a.startswith(prefix) and not a[len(prefix) :].isdigit() for a in _anchors(text))


def next_id(path: Path, kind: str, scope: str | None = None) -> str | None:
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8")
    if scope is None:
        scope = _default_scope(path)
    if scope is None and _scope_established(text, kind):
        raise ScopeRequired(f"{path}: existing {kind} anchors carry an axis — pass --scope")
    prefix = f"{kind}-{scope}-" if scope else f"{kind}-"
    pat = re.compile(rf"^{re.escape(prefix.lower())}(\d+)$")
    used = [int(m.group(1)) for a in _anchors(text) if (m := pat.match(a))]
    return f"{prefix.upper()}{max(used, default=0) + 1:03d}"


# A link into another SRS document, or a bare fragment in this one. Images (`![…]`) are
# excluded: they carry no anchor. The optional title (`"…"`) after the target/fragment
# mirrors `harness_scaffold._MD_LINK_RE` — without it, a titled link doesn't match at all
# and its anchor goes unchecked.
_LINK_RE = re.compile(
    r"(?<!!)\[[^\]]*\]\(\s*([^)\s#]*)(?:#([^)\s]*))?(?:\s+[\"'][^\")]*[\"'])?\s*\)"
)


def _files(root: Path, paths: list[Path] | None) -> list[Path]:
    d = srs_dir(root)
    if d is None:
        return []
    if paths:
        return [p for p in paths if p.is_file()]
    return sorted(d.glob("*.md"))


def _check_duplicates(texts: dict[Path, str]) -> list[str]:
    out, seen = [], {}
    for path, text in texts.items():
        local = set()
        for anchor in _anchors(text):
            if anchor in local:
                out.append(f"{path}: duplicate anchor '{anchor}' in this file")
            local.add(anchor)
            if anchor in seen and seen[anchor] != path:
                out.append(f"{path}: anchor '{anchor}' also defined in {seen[anchor]}")
            seen.setdefault(anchor, path)
    return out


def _check_prefix(path: Path, text: str) -> list[str]:
    """An area file's ids carry its stem. The index's ids carry no area at all."""
    if path.stem == INDEX_STEM:
        return []
    want = path.stem.lower()
    out = []
    for anchor in _anchors(text):
        parts = anchor.rsplit("-", 1)
        if len(parts) != 2 or not parts[1].isdigit():
            continue
        head = parts[0]
        if "-" not in head or not head.split("-", 1)[1] == want:
            out.append(f"{path}: anchor '{anchor}' does not carry the area prefix '{want}'")
    return out


def _check_links(path: Path, text: str, texts: dict[Path, str]) -> list[str]:
    out = []
    for target, frag in _LINK_RE.findall(_strip_examples(text)):
        if not frag or target.startswith(("http://", "https://", "/", "\\")):
            continue
        # Keyed by resolved path, this file included — a bare `#frag` targets itself.
        dest = path.resolve() if not target else (path.parent / target).resolve()
        body = texts.get(dest)
        if body is None:
            continue  # outside docs/srs — another checker's subject
        if not _has_anchor(body, frag):
            shown = f"{target}#{frag}" if target else f"#{frag}"
            out.append(f"{path}: dead link '{shown}'")
    return out


def verify(root: Path, paths: list[Path] | None = None) -> list[str]:
    report_files = _files(root, paths)
    if not report_files:
        return []
    # A link target resolves against the whole directory even when `paths` narrows what
    # gets reported — otherwise a target this call was not asked about reads as "outside
    # docs/srs" and a dead link into it goes silently unchecked. Duplicate and prefix
    # checks stay narrowed: a defect living entirely between two files this call did not
    # name is not this call's business.
    link_files = _files(root, None)
    texts = {p.resolve(): p.read_text(encoding="utf-8") for p in {*link_files, *report_files}}
    report_texts = {p: texts[p.resolve()] for p in report_files}
    out = _check_duplicates(report_texts)
    for path, body in report_texts.items():
        out += _check_prefix(path, body)
        out += _check_links(path, body, texts)
    return out


def main(argv: list[str] | None = None) -> int:
    force_utf8_io()
    parser = argparse.ArgumentParser(description="docs/srs numbering and integrity")
    parser.add_argument("--root", default=".", help="repository root (default: cwd)")
    parser.add_argument("--next-id", metavar="FILE", help="issue the next id for --kind")
    parser.add_argument("--kind", help="id kind (FR, C, NFR, CON, ROLE, …) — an open set")
    parser.add_argument("--scope", help="counter scope within the file (an NFR axis stem)")
    parser.add_argument("--areas", action="store_true", help="list area stem and title")
    parser.add_argument(
        "--verify",
        nargs="*",
        metavar="PATH",
        default=None,
        help="check anchors and links under docs/srs (default: all of them)",
    )
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.next_id:
        if not args.kind:
            parser.error("--next-id requires --kind")
        try:
            got = next_id(Path(args.next_id), args.kind, args.scope)
        except ScopeRequired as exc:
            parser.error(str(exc))
        if got:
            print(got)
        return 0
    if args.areas:
        for stem, title in areas(root):
            print(f"{stem}\t{title}")
    if args.verify is not None:
        problems = verify(root, [Path(p) for p in args.verify] or None)
        for line in problems:
            print(line, file=sys.stderr)
        return 1 if problems else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
