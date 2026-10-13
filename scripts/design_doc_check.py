"""Checks behind the /design-* skills: the templates a consumer may edit, and the
Markdown each skill writes or converts.

Every rule reports and none stops the scan, so one run lists everything to fix. Not a
gate: a skill runs it at start and after writing.
"""

from __future__ import annotations

import argparse
import re
import sys
from dataclasses import dataclass
from pathlib import Path

import yaml

try:
    from _harness_paths import HARNESS_DIR, config_path, force_utf8_io, host_root
except ImportError:
    from scripts._harness_paths import HARNESS_DIR, config_path, force_utf8_io, host_root

try:
    from _design_md import ID_TOKEN_RE, Doc, parse
except ImportError:
    from scripts._design_md import ID_TOKEN_RE, Doc, parse

try:
    from wiki_graph import _wiki_root_hint, derive_wiki_id
except ImportError:
    from scripts.wiki_graph import _wiki_root_hint, derive_wiki_id

try:
    from _md_anchors import _has_anchor
except ImportError:
    from scripts._md_anchors import _has_anchor

try:
    import srs_check
except ImportError:
    import scripts.srs_check as srs_check

DESIGN_TEMPLATES_DIR = f"{HARNESS_DIR}/templates/design-docs"  # host-owned, seeded once
DEFAULTS = {
    "templates": DESIGN_TEMPLATES_DIR,
    "docs": "docs/deliverables",
    "output": "docs/deliverables/results",
    "renderer": "https://kroki.io",
    "base_docx": None,
    "gitignore_output": False,
}
DOCS = ("srs", "sds", "architecture", "api", "erd", "table")
CONVERT_ONLY = ("srs", "sds")
WRITER_DOCS = tuple(d for d in DOCS if d not in CONVERT_ONLY)  # docs --wiki-id accepts
SRS_KINDS = ("C", "FR", "NFR", "CON", "TERM", "ROLE")
FRONT_KEYS = (
    "doc",
    "title",
    "standard",
    "id_prefix",
    "refs",
    "sources",
    "inventory",
    "labels",
    "revisions",
)
REQUIRED_FRONT = ("doc", "title", "standard")
LABEL_KEYS = ("revisions", "toc", "version", "date", "summary")  # renderer's DEFAULT_LABELS keys
_PREFIX_RE = re.compile(r"^[A-Z][A-Z0-9]{1,5}$")


@dataclass(frozen=True)
class Violation:
    file: str
    where: str
    code: str
    message: str

    def format(self) -> str:
        return f"{self.file}  {self.where}  {self.code}  {self.message}"


def load_settings(root: Path) -> dict:
    settings = dict(DEFAULTS)
    try:
        cfg = yaml.safe_load(config_path(root).read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        cfg = {}
    block = cfg.get("design_docs") if isinstance(cfg, dict) else None
    if isinstance(block, dict):
        for key in DEFAULTS:
            if block.get(key) is not None:
                settings[key] = block[key]
    return settings


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8").replace("\r\n", "\n")


def template_file(tdir: Path, name: str) -> Path:
    return tdir / f"{name}.template.md"


def doc_rel(settings: dict, name: str) -> str:
    """The document path relative to root, as check_doc and --wiki-id both compute it."""
    return f"{str(settings['docs']).rstrip('/')}/{name}.md"


def load_templates(tdir: Path) -> dict[str, Doc]:
    out: dict[str, Doc] = {}
    for name in DOCS:
        path = template_file(tdir, name)
        if path.is_file():
            out[name] = parse(_read(path))
    return out


def prefixes(t: Doc) -> list[str]:
    value = (t.front or {}).get("id_prefix") or []
    if isinstance(value, str):
        return [value]
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else []


def source_files(root: Path, globs: list) -> list[Path]:
    seen: list[Path] = []
    for pattern in globs:
        if not isinstance(pattern, str):
            continue
        for match in sorted(root.glob(pattern)):
            if match.is_file() and match not in seen:
                seen.append(match)
    return seen


def repeat_headings(t: Doc) -> list[tuple[str, int]]:
    """(prefix, index into t.headings) for every repeat marker that has a heading after it."""
    out: list[tuple[str, int]] = []
    for prefix, line in t.repeats:
        for idx, h in enumerate(t.headings):
            if h.line > line:
                out.append((prefix, idx))
                break
    return out


def _check_labels(f: str, front: dict) -> list[Violation]:
    labels = front.get("labels")
    if labels is None:
        return []
    if not isinstance(labels, dict):
        return [Violation(f, "labels", "T-FRONT", "labels must be a mapping")]
    vs: list[Violation] = []
    known = ", ".join(LABEL_KEYS)
    for key, value in labels.items():
        if key not in LABEL_KEYS:
            vs.append(
                Violation(f, "labels", "T-FRONT", f"labels key '{key}' is not one of {known}")
            )
        elif not isinstance(value, str):
            vs.append(Violation(f, "labels", "T-FRONT", f"labels['{key}'] must be a string"))
    return vs


def check_templates(tdir: Path, root: Path) -> list[Violation]:
    if not tdir.is_dir():
        return [
            Violation(
                str(tdir),
                "-",
                "T-MISSING",
                "template directory not found — run /flow-init to seed it",
            )
        ]
    vs: list[Violation] = []
    templates = load_templates(tdir)
    for name in DOCS:
        if name not in templates:
            vs.append(
                Violation(
                    f"{name}.template.md",
                    "-",
                    "T-MISSING",
                    "template not found — copy it back from the plugin's templates/design-docs/",
                )
            )
    owner: dict[str, str] = {}
    for name, t in templates.items():
        f = f"{name}.template.md"
        if t.front is None:
            vs.append(
                Violation(f, "front matter", "T-FRONT", t.front_error or "front matter missing")
            )
            continue
        for key in REQUIRED_FRONT:
            if not t.front.get(key):
                vs.append(Violation(f, "front matter", "T-FRONT", f"required key '{key}' missing"))
        for key in t.front:
            if key not in FRONT_KEYS:
                vs.append(
                    Violation(
                        f,
                        "front matter",
                        "T-FRONT",
                        f"unknown key '{key}' — allowed: {', '.join(FRONT_KEYS)}",
                    )
                )
        if t.front.get("doc") and t.front["doc"] != name:
            vs.append(
                Violation(
                    f,
                    "front matter",
                    "T-FRONT",
                    f"doc '{t.front['doc']}' does not match the file name '{name}'",
                )
            )
        vs += _check_labels(f, t.front)
        if name in CONVERT_ONLY:
            src = t.front.get("sources")
            if not isinstance(src, list) or not src:
                vs.append(
                    Violation(
                        f,
                        "sources",
                        "T-SOURCES",
                        "sources must be a non-empty list of repo-relative globs",
                    )
                )
            continue
        raw = t.front.get("id_prefix")
        items = raw if isinstance(raw, list) else [raw]
        for p in items:
            if not isinstance(p, str) or not _PREFIX_RE.match(p):
                vs.append(
                    Violation(
                        f,
                        "id_prefix",
                        "T-PREFIX",
                        f"'{p}' is not an upper-case prefix of 2-6 characters",
                    )
                )
            elif p in SRS_KINDS:
                vs.append(Violation(f, "id_prefix", "T-PREFIX", f"'{p}' is an SRS id kind"))
            elif p in owner:
                vs.append(
                    Violation(
                        f,
                        "id_prefix",
                        "T-PREFIX",
                        f"'{p}' is also issued by {owner[p]}.template.md",
                    )
                )
            else:
                owner[p] = name
    known = set(SRS_KINDS) | set(owner)
    for name, t in templates.items():
        if t.front is None or name in CONVERT_ONLY:
            continue
        vs += _template_body(f"{name}.template.md", t, known)
    return vs


def _template_body(f: str, t: Doc, known: set[str]) -> list[Violation]:
    vs: list[Violation] = []
    front = t.front or {}
    refs = front.get("refs", [])
    if not isinstance(refs, list):
        vs.append(Violation(f, "refs", "T-REFS", "refs must be a list of id kinds"))
    else:
        known_list = ", ".join(sorted(known))
        for r in refs:
            if r not in known:
                msg = f"'{r}' is issued by neither the SRS nor any template — known: {known_list}"
                vs.append(Violation(f, "refs", "T-REFS", msg))
    own = prefixes(t)
    repeat_idx = {idx for _, idx in repeat_headings(t)}
    for prefix, line in t.repeats:
        if not any(h.line > line for h in t.headings):
            vs.append(
                Violation(f, f"line {line}", "T-REPEAT", "repeat marker has no heading after it")
            )
        if prefix not in own:
            vs.append(
                Violation(
                    f,
                    f"line {line}",
                    "T-REPEAT",
                    f"repeat prefix '{prefix}' is not in id_prefix {own}",
                )
            )
    seen: set[str] = set()
    for idx, h in enumerate(t.headings):
        if not h.text:
            vs.append(Violation(f, f"line {h.line}", "T-HEADING", "empty heading"))
        elif idx not in repeat_idx:
            if h.text in seen:
                vs.append(
                    Violation(f, f"line {h.line}", "T-HEADING", f"duplicate heading '{h.text}'")
                )
            seen.add(h.text)
    for table in t.tables:
        if any(not c for c in table.header):
            vs.append(
                Violation(f, f"line {table.line}", "T-TABLE", "table header has an empty column")
            )
        dup = sorted({c for c in table.header if c and table.header.count(c) > 1})
        if dup:
            vs.append(Violation(f, f"line {table.line}", "T-TABLE", f"duplicate columns {dup}"))
    inventory = front.get("inventory")
    if inventory and inventory not in seen:
        vs.append(
            Violation(
                f,
                "inventory",
                "T-FRONT",
                f"inventory names heading '{inventory}', which the template lacks",
            )
        )
    return vs


_FRONT_ONLY_RE = re.compile(r"\A---[ \t]*\n(.*?)\n---", re.DOTALL)


def known_kinds(templates: dict[str, Doc]) -> dict[str, str]:
    kinds = {k: "srs" for k in SRS_KINDS}
    for name, t in templates.items():
        for p in prefixes(t):
            kinds.setdefault(p, name)
    return kinds


def wiki_nodes(root: Path, wroot: str) -> set[str]:
    nodes: set[str] = set()
    base = root / wroot
    for path in base.rglob("*.md") if base.is_dir() else []:
        m = _FRONT_ONLY_RE.match(_read(path))
        if not m:
            continue
        try:
            front = yaml.safe_load(m.group(1))
        except yaml.YAMLError:
            continue
        if isinstance(front, dict) and isinstance(front.get("wiki_id"), str):
            nodes.add(front["wiki_id"])
    return nodes


def expected_wiki_id(root: Path, rel: str) -> str:
    """The wiki_id `_check_front` demands for `rel` — shared with `--wiki-id` so the two
    computations cannot drift apart."""
    return derive_wiki_id(rel, _wiki_root_hint(root))


def _check_front(root: Path, rel: str, doc: Doc) -> list[Violation]:
    if doc.front is None:
        return [
            Violation(
                rel,
                "front matter",
                "S-FRONT",
                doc.front_error or "wiki front matter missing (wiki_id, title, tags, revisions)",
            )
        ]
    vs: list[Violation] = []
    wroot = _wiki_root_hint(root)
    try:
        expected: str | None = expected_wiki_id(root, rel)
    except ValueError as exc:
        expected = None
        vs.append(Violation(rel, "wiki_id", "S-FRONT", f"no wiki_id derivable: {exc}"))
    if expected and doc.front.get("wiki_id") != expected:
        vs.append(
            Violation(
                rel,
                "wiki_id",
                "S-FRONT",
                f"wiki_id must be '{expected}' (design_doc_check.py --wiki-id {Path(rel).stem})",
            )
        )
    if not doc.front.get("title"):
        vs.append(Violation(rel, "title", "S-FRONT", "title missing"))
    tags = doc.front.get("tags")
    if not isinstance(tags, list) or not tags:
        vs.append(Violation(rel, "tags", "S-FRONT", "tags must be a non-empty list"))
    related = doc.front.get("related") or []
    if related:
        nodes = wiki_nodes(root, wroot)
        for r in related if isinstance(related, list) else [related]:
            if r not in nodes:
                vs.append(
                    Violation(
                        rel,
                        "related",
                        "S-FRONT",
                        f"related '{r}' is no wiki node — no document carries that wiki_id",
                    )
                )
    revs = doc.front.get("revisions")
    if (
        not isinstance(revs, list)
        or not revs
        or not all(
            isinstance(r, dict) and r.get("version") and r.get("date") and r.get("summary")
            for r in revs
        )
    ):
        vs.append(
            Violation(
                rel, "revisions", "S-FRONT", "revisions must list {version, date, summary} rows"
            )
        )
    return vs


def _find_heading(doc: Doc, text: str, start: int = 0) -> int:
    for idx in range(start, len(doc.headings)):
        if doc.headings[idx].text == text:
            return idx
    return -1


def _block_ranges(t: Doc) -> list[tuple[int, int]]:
    return [(t.headings[idx].line, t.section_end(idx)) for _, idx in repeat_headings(t)]


def _check_headings(rel: str, doc: Doc, t: Doc) -> list[Violation]:
    vs: list[Violation] = []
    repeat_idx = {idx for _, idx in repeat_headings(t)}
    blocks = _block_ranges(t)
    required = [
        h.text
        for idx, h in enumerate(t.headings)
        if idx not in repeat_idx and not any(s < h.line < e for s, e in blocks)
    ]
    pos = 0
    for text in required:
        found = _find_heading(doc, text, pos)
        if found >= 0:
            pos = found + 1
        elif _find_heading(doc, text) >= 0:
            vs.append(
                Violation(
                    rel, text, "S-HEADING", f"heading '{text}' is out of the template's order"
                )
            )
        else:
            vs.append(Violation(rel, text, "S-HEADING", f"heading '{text}' missing"))
    return vs


def _header_diff(expected: list[str], found: list[str]) -> str:
    missing = [c for c in expected if c not in found]
    extra = [c for c in found if c not in expected]
    return f"expected {' | '.join(expected)}; missing {missing}, extra {extra}"


def _check_tables(rel: str, doc: Doc, t: Doc) -> list[Violation]:
    vs: list[Violation] = []
    blocks = _block_ranges(t)
    for tt in t.tables:
        if any(s <= tt.line < e for s, e in blocks) or not tt.path:
            continue
        under = [d for d in doc.tables if d.path and d.path[-1] == tt.path[-1]]
        if not under:
            vs.append(
                Violation(
                    rel,
                    tt.path[-1],
                    "S-TABLE",
                    f"no table under '{tt.path[-1]}' — {' | '.join(tt.header)}",
                )
            )
        elif not any(d.header == tt.header for d in under):
            vs.append(
                Violation(rel, tt.path[-1], "S-TABLE", _header_diff(tt.header, under[0].header))
            )
    for prefix, idx in repeat_headings(t):
        th = t.headings[idx]
        block_tables = t.tables_between(th.line, t.section_end(idx))
        parent = next((h for h in reversed(t.headings[:idx]) if h.level < th.level), None)
        p_idx = _find_heading(doc, parent.text) if parent else -1
        if parent and p_idx < 0:
            continue  # S-HEADING already names the missing parent
        start = doc.headings[p_idx].line if p_idx >= 0 else 0
        end = doc.section_end(p_idx) if p_idx >= 0 else doc.last_line + 1
        items = [
            i for i, h in enumerate(doc.headings) if h.level == th.level and start < h.line < end
        ]
        where = parent.text if parent else "-"
        if not items:
            vs.append(Violation(rel, where, "S-HEADING", f"no {prefix} block under '{where}'"))
        for i in items:
            h = doc.headings[i]
            if not any(tok.startswith(prefix + "-") for tok, n in doc.tokens if n == h.line):
                vs.append(
                    Violation(
                        rel,
                        f"{where} > {h.text}",
                        "S-HEADING",
                        f"block heading carries no {prefix}-NNN id",
                    )
                )
            found = doc.tables_between(h.line, doc.section_end(i))
            for bt in block_tables:
                if not any(d.header == bt.header for d in found):
                    got = found[0].header if found else []
                    vs.append(
                        Violation(
                            rel, f"{where} > {h.text}", "S-TABLE", _header_diff(bt.header, got)
                        )
                    )
    return vs


def _check_ids(rel: str, doc: Doc, t: Doc, kinds: dict[str, str]) -> list[Violation]:
    vs: list[Violation] = []
    own = set(prefixes(t))
    seen: set[str] = set()
    for aid, line in doc.anchors:
        head, _, num = aid.rpartition("-")
        kind = head.upper()
        if kind in own:
            if not re.fullmatch(r"\d{3}", num):
                vs.append(
                    Violation(
                        rel, f"line {line}", "S-ID", f"'{aid}' is not {kind}-NNN (three digits)"
                    )
                )
            elif aid in seen:
                vs.append(
                    Violation(
                        rel, f"line {line}", "S-ID", f"{aid.upper()} is issued twice (duplicate)"
                    )
                )
            seen.add(aid)
        elif kind in kinds and num.isdigit():
            vs.append(
                Violation(
                    rel,
                    f"line {line}",
                    "S-ID",
                    f"{aid.upper()} is a {kind} id, which {kinds[kind]} issues"
                    " — reference it instead",
                )
            )
    return vs


def check_structure(
    root: Path, rel: str, doc: Doc, t: Doc, templates: dict[str, Doc]
) -> list[Violation]:
    vs = _check_front(root, rel, doc)
    vs += _check_headings(rel, doc, t)
    vs += _check_tables(rel, doc, t)
    vs += [
        Violation(rel, f"line {n}", "S-PLACEHOLDER", f"'{p}' was never filled")
        for p, n in doc.placeholders
    ]
    vs += _check_ids(rel, doc, t, known_kinds(templates))
    return vs


MERMAID_TYPES = (
    "graph",
    "flowchart",
    "sequenceDiagram",
    "classDiagram",
    "stateDiagram",
    "stateDiagram-v2",
    "erDiagram",
    "journey",
    "gantt",
    "pie",
    "mindmap",
    "timeline",
    "C4Context",
    "C4Container",
    "C4Component",
    "C4Deployment",
    "block-beta",
    "architecture-beta",
)
SOURCE_COLUMN = "근거"  # a template column by this name holds repo paths
FK_COLUMN = "FK"
_NFR_ITEM_RE = re.compile(r"^nfr-[a-z]+-\d{3}$")
_FR_RE = re.compile(r"^fr-.+-\d{3}$")


def _srs_anchors(root: Path) -> list[str]:
    out: list[str] = []
    for path in sorted((root / "docs" / "srs").glob("*.md")):
        out += [a for a, _ in parse(_read(path)).anchors]
    return out


def id_universe(root: Path, settings: dict, templates: dict[str, Doc]) -> set[str]:
    ids = {a.upper() for a in _srs_anchors(root)}
    for name in templates:
        if name in CONVERT_ONLY:
            continue
        path = root / settings["docs"] / f"{name}.md"
        if path.is_file():
            ids |= {a.upper() for a, _ in parse(_read(path)).anchors}
    return ids


def _check_links(
    root: Path, path: Path, rel: str, doc: Doc, cache: dict[Path, str]
) -> list[Violation]:
    vs: list[Violation] = []
    for target, frag, line in doc.links:
        if "://" in target or target.startswith("mailto:") or (not target and not frag):
            continue
        dest = (path.parent / target).resolve() if target else path
        if not dest.is_file():
            vs.append(
                Violation(rel, f"line {line}", "S-DANGLING", f"link target '{target}' not found")
            )
            continue
        if frag:
            text = cache.setdefault(dest, _read(dest))
            if not _has_anchor(text, frag):
                vs.append(
                    Violation(
                        rel,
                        f"line {line}",
                        "S-DANGLING",
                        f"anchor #{frag} not found in {target or 'this document'}",
                    )
                )
    return vs


def _check_tokens(
    rel: str, doc: Doc, t: Doc, kinds: dict[str, str], universe: set[str]
) -> list[Violation]:
    vs: list[Violation] = []
    refs = set((t.front or {}).get("refs") or []) | set(prefixes(t))
    for tok, line in doc.tokens:
        kind = tok.split("-", 1)[0]
        if kind not in kinds:
            continue
        if tok not in universe:
            vs.append(
                Violation(
                    rel, f"line {line}", "S-DANGLING", f"{tok} does not exist in any document"
                )
            )
        elif kind not in refs:
            vs.append(
                Violation(
                    rel,
                    f"line {line}",
                    "S-DANGLING",
                    f"{tok}: kind {kind} is not in the template's refs {sorted(refs)}",
                )
            )
    return vs


def _referenced(doc: Doc) -> set[str]:
    return {t for t, _ in doc.tokens} | {f.upper() for _, f, _ in doc.links if f}


def _check_inventory(rel: str, doc: Doc, t: Doc) -> list[Violation]:
    heading = (t.front or {}).get("inventory")
    idx = _find_heading(doc, heading) if heading else -1
    if idx < 0:
        return []
    start, end = doc.headings[idx].line, doc.section_end(idx)
    vs: list[Violation] = []
    if not any(
        f.lang in ("bash", "sh", "shell", "") and f.body.strip()
        for f in doc.fences_between(start, end)
    ):
        vs.append(
            Violation(
                rel, heading, "S-COVER", "inventory lacks the extraction command (a ```bash block)"
            )
        )
    tables = doc.tables_between(start, end)
    rows = tables[0].rows if tables else []
    if not rows:
        vs.append(Violation(rel, heading, "S-COVER", "inventory table is empty"))
    own_ids = {a.upper() for a, _ in doc.anchors}
    for row in rows:
        cell = row[2] if len(row) > 2 else ""
        if cell.startswith("N/A:") and cell[4:].strip():
            continue
        if not any(m.group(1) in own_ids for m in ID_TOKEN_RE.finditer(cell)):
            vs.append(
                Violation(
                    rel,
                    heading,
                    "S-COVER",
                    f"inventory row '{row[0] if row else ''}' has no document id or 'N/A: reason'",
                )
            )
    return vs


def _check_sources(root: Path, rel: str, doc: Doc) -> list[Violation]:
    vs: list[Violation] = []
    paths: list[tuple[str, str]] = []
    src = (doc.front or {}).get("sources")
    if src is not None:
        if isinstance(src, dict):
            paths += [(k, "front matter sources") for k in src if isinstance(k, str)]
        else:
            vs.append(
                Violation(
                    rel,
                    "sources",
                    "S-FRONT",
                    "sources must be a map path -> null, the wiki format",
                )
            )
    for table in doc.tables:
        if SOURCE_COLUMN in table.header:
            col = table.header.index(SOURCE_COLUMN)
            for row in table.rows:
                if col < len(row) and row[col] and row[col] != "-":
                    paths.append((row[col], f"line {table.line}"))
    for p, where in paths:
        clean = p.strip("`").split("#", 1)[0].strip()
        if clean and not (root / clean).exists():
            vs.append(Violation(rel, where, "S-SOURCE", f"source path '{clean}' does not exist"))
    return vs


_MERMAID_DIRECTIVE_RE = re.compile(r"\A%%[^\n]*\n?")
_MERMAID_TITLE_BLOCK_RE = re.compile(r"\A---\n.*?\n---[ \t]*\n?", re.DOTALL)


def _mermaid_diagram_start(body: str) -> str:
    """The diagram-type token, past any leading `%%...` directive lines and one leading
    `---`...`---` title block — either may precede the type, in any order."""
    changed = True
    while changed:
        changed = False
        m = _MERMAID_DIRECTIVE_RE.match(body)
        if m:
            body = body[m.end() :].lstrip("\n")
            changed = True
            continue
        m = _MERMAID_TITLE_BLOCK_RE.match(body)
        if m:
            body = body[m.end() :].lstrip("\n")
            changed = True
    return body.strip()


def _check_diagrams(rel: str, doc: Doc) -> list[Violation]:
    vs: list[Violation] = []
    for f in doc.fences:
        if f.lang not in ("mermaid", "d2"):
            continue
        body = f.body.strip()
        if not body:
            vs.append(Violation(rel, f"line {f.line}", "S-DIAGRAM", f"empty {f.lang} block"))
        elif f.lang == "mermaid":
            start = _mermaid_diagram_start(body)
            token = start.split()[0] if start else ""
            if token not in MERMAID_TYPES:
                vs.append(
                    Violation(
                        rel,
                        f"line {f.line}",
                        "S-DIAGRAM",
                        f"mermaid block starts with '{token}', not a diagram type",
                    )
                )
    return vs


def _other(root: Path, settings: dict, name: str) -> Doc | None:
    path = root / settings["docs"] / f"{name}.md"
    return parse(_read(path)) if path.is_file() else None


def _check_cross(
    root: Path, settings: dict, name: str, rel: str, doc: Doc
) -> tuple[list[Violation], list[str]]:
    vs: list[Violation] = []
    notes: list[str] = []
    if name in ("erd", "table"):
        other_name = "table" if name == "erd" else "erd"
        other = _other(root, settings, other_name)
        if other is None:
            notes.append(f"S-CROSS skipped: {other_name}.md not written yet")
        else:
            erd, table = (doc, other) if name == "erd" else (other, doc)
            ents = sorted({a.upper() for a, _ in erd.anchors if a.startswith("ent-")})
            mapped = {t for t, _ in table.tokens if t.startswith("ENT-")}
            for ent in ents:
                if ent not in mapped:
                    vs.append(Violation(rel, ent, "S-CROSS", f"{ent} has no table in table.md"))
    if name == "table":
        tbls = {a.upper() for a, _ in doc.anchors}
        for table in doc.tables:
            if FK_COLUMN not in table.header:
                continue
            col = table.header.index(FK_COLUMN)
            for row in table.rows:
                for m in ID_TOKEN_RE.finditer(row[col] if col < len(row) else ""):
                    if m.group(1).startswith("TBL-") and m.group(1) not in tbls:
                        vs.append(
                            Violation(
                                rel,
                                f"line {table.line}",
                                "S-CROSS",
                                f"FK target {m.group(1)} does not exist",
                            )
                        )
    if name == "api":
        if _other(root, settings, "architecture") is None:
            notes.append("S-CROSS skipped: architecture.md not written yet")
        else:
            for i, h in enumerate(doc.headings):
                api = next((t for t, n in doc.tokens if n == h.line and t.startswith("API-")), None)
                if api and not any(
                    t.startswith("CMP-") for t in doc.tokens_between(h.line, doc.section_end(i))
                ):
                    vs.append(Violation(rel, api, "S-CROSS", f"{api} names no component (CMP-NNN)"))
    return vs, notes


def _check_source_doc(root: Path, name: str, t: Doc) -> list[Violation]:
    files = source_files(root, (t.front or {}).get("sources") or [])
    if not files:
        return [Violation(f"{name}.template.md", "sources", "T-SOURCES", "no source file matches")]
    vs: list[Violation] = []
    if name == "srs":
        vs += [Violation("docs/srs", "-", "SRS-VERIFY", line) for line in srs_check.verify(root)]
    referenced: set[str] = set()
    cache: dict[Path, str] = {}
    for path in files:
        rel = path.relative_to(root).as_posix()
        doc = parse(_read(path))
        vs += _check_diagrams(rel, doc)
        if name == "sds":
            vs += _check_links(root, path, rel, doc, cache)
            referenced |= _referenced(doc)
    if name == "sds":
        for fr in sorted({a.upper() for a in _srs_anchors(root) if _FR_RE.match(a)}):
            if fr not in referenced:
                vs.append(
                    Violation("docs/sds", fr, "S-COVER", f"{fr} is implemented by no SDS module")
                )
    return vs


def check_doc(root: Path, settings: dict, name: str) -> tuple[list[Violation], list[str]]:
    templates = load_templates(root / settings["templates"])
    t = templates.get(name)
    if t is None:
        return [
            Violation(
                f"{name}.template.md", "-", "T-MISSING", "template not found — run /flow-init"
            )
        ], []
    if name in CONVERT_ONLY:
        return _check_source_doc(root, name, t), []
    rel = doc_rel(settings, name)
    path = root / rel
    if not path.is_file():
        return [Violation(rel, "-", "S-MISSING", "document not written yet")], []
    doc = parse(_read(path))
    kinds = known_kinds(templates)
    vs = check_structure(root, rel, doc, t, templates)
    vs += _check_links(root, path, rel, doc, {})
    vs += _check_tokens(rel, doc, t, kinds, id_universe(root, settings, templates))
    if name == "architecture":
        for a in sorted(
            {a.upper() for a in _srs_anchors(root) if _FR_RE.match(a) or _NFR_ITEM_RE.match(a)}
        ):
            if a not in _referenced(doc):
                vs.append(Violation(rel, a, "S-COVER", f"{a} is mapped by no component"))
    vs += _check_inventory(rel, doc, t)
    cross, notes = _check_cross(root, settings, name, rel, doc)
    vs += cross
    vs += _check_sources(root, rel, doc)
    vs += _check_diagrams(rel, doc)
    return vs, notes


def main(argv: list[str] | None = None) -> int:
    force_utf8_io()
    parser = argparse.ArgumentParser(description="Check design-doc templates and documents.")
    parser.add_argument("--root", default=None, help="host root (default: project dir)")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--templates", action="store_true", help="check the host's templates")
    mode.add_argument("--doc", choices=DOCS, help="check one document")
    mode.add_argument(
        "--paths", action="store_true", help="print the resolved design_docs settings"
    )
    mode.add_argument(
        "--wiki-id",
        choices=WRITER_DOCS,
        help="print the wiki_id _check_front expects for <docs>/<doc>.md",
    )
    args = parser.parse_args(argv)
    root = Path(args.root) if args.root else host_root()
    settings = load_settings(root)
    if args.paths:
        for key in DEFAULTS:
            print(f"{key}\t{settings[key]}")
        return 0
    if args.wiki_id:
        try:
            print(expected_wiki_id(root, doc_rel(settings, args.wiki_id)))
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 1
        return 0
    if args.templates:
        vs, notes = check_templates(root / settings["templates"], root), []
    else:
        vs, notes = check_doc(root, settings, args.doc)
    for note in notes:
        print(f"note: {note}")
    for v in vs:
        print(v.format())
    print(f"{len(vs)} violation(s)")
    return 1 if vs else 0


if __name__ == "__main__":
    sys.exit(main())
