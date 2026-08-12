"""LLM Wiki graph builder / verifier (harness-tier).

Parses front matter mechanically into a knowledge graph and validates it. No embeddings,
no LLM, and PyYAML is the only dependency. `--build` is called by doc-sync, `--verify` by
the flow gate.

With no wiki installed (no config / enable:false / missing root directory) every
subcommand passes silently.

User-facing output is Korean, matching the other gate scripts; comments and docstrings are
English, same as scripts/_harness_paths.py and scripts/flow_gate_check.py.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path, PurePosixPath

try:
    from _harness_paths import _git, config_path, force_utf8_io, host_root
except ImportError:
    from scripts._harness_paths import _git, config_path, force_utf8_io, host_root

# Default SSOT for flow-config.wiki — slots the host leaves unset are filled from here.
_DEFAULTS: dict = {"max_lines": 400, "context_lines": 2000, "defect_rule_threshold": 3}


def _norm_rel(value) -> str:
    """Normalize a configured path to a repo-relative posix path (`./docs/` → `docs`).

    Node paths always come from `path.relative_to(root).as_posix()`, so leaving a configured
    value as raw text means `wiki.index` can never equal any node path — which switches
    orphan detection off across the whole repo, silently. Making both sides of that
    comparison the same shape is this function's only job.
    """
    text = str(value).replace("\\", "/").strip()
    if not text:
        return ""
    return PurePosixPath(text).as_posix().rstrip("/")


def load_wiki_config(root: Path) -> dict | None:
    """Read flow-config.wiki into a defaults-filled dict, or None when there is no wiki.

    None means "there is no wiki to check" and the caller must pass silently. A broken
    config is also None (Invariant #1 FAIL-OPEN — a config we cannot parse never blocks a
    commit).
    """
    cfg = config_path(root)
    if not cfg.is_file():
        return None
    try:
        import yaml

        data = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        wiki = data.get("wiki")
    except Exception:
        return None
    if not isinstance(wiki, dict) or not wiki.get("enable"):
        return None
    wiki_root = _norm_rel(wiki.get("root") or "docs/") or "docs"
    if not (root / wiki_root).is_dir():
        # `enable: true` pointing at a directory that is not there is a typo, not a repo without
        # a wiki, but both would silently switch the whole gate off — and /wiki-init Step 8 reads
        # `--build` + `--verify` succeeding on empty output as proof the wiki is enforced. Say so.
        # Still None: a broken config must not block a commit (Invariant #1).
        print(
            f"wiki.enable 는 true 인데 wiki.root '{wiki_root}' 디렉터리가 없습니다 — "
            f"검증이 통째로 꺼진 상태입니다 (flow-config.yaml 의 root 를 확인하세요)",
            file=sys.stderr,
        )
        return None
    out = dict(_DEFAULTS)
    out.update({k: v for k, v in wiki.items() if v is not None})
    out["root"] = wiki_root
    # Absent/empty → the root's default entry point. Normalize whichever branch we take: the
    # index is string-compared against node paths, and the DERIVED default needs it as much as a
    # configured one — with root ".", `f"{wiki_root}/index.md"` is "./index.md" while node paths
    # are "index.md", which matches nothing and silently switches orphan detection off.
    out["index"] = _norm_rel(out.get("index") or f"{wiki_root}/index.md")
    return out


_FM_DELIM = "---"


def _front_matter_block(text: str) -> str | None:
    """The text between the opening `---` and the closing one, or None when there is no block.

    Both readers below share this so the delimiter rule — including the `end + 1` boundary —
    lives in one place. A copy would let one of them drift.
    """
    if not text.startswith(_FM_DELIM):
        return None
    end = text.find(f"\n{_FM_DELIM}", len(_FM_DELIM))
    if end < 0:
        return None
    return text[len(_FM_DELIM) : end + 1]


def parse_front_matter(text: str) -> dict | None:
    """Parse the leading `---` block as YAML. None when it is absent or broken.

    None covers both "not a wiki node" and "the front matter is malformed" — this function
    alone cannot tell them apart, and does not try to. The caller decides what None means:
    `collect_nodes` only treats it as "not a node" after it separately asks
    `_broken_front_matter` whether the raw text carries a `wiki_id:` line, which is what
    decides whether a broken block is surfaced as a block (marker present) or a warning (no
    marker) rather than silently dropped.
    """
    block = _front_matter_block(text)
    if block is None:
        return None
    try:
        import yaml

        front = yaml.safe_load(block)
    except Exception:
        return None
    return front if isinstance(front, dict) else None


# Read from the RAW front-matter text, because a block that failed to parse has no YAML to
# ask. Whether the author wrote a `wiki_id:` line is still visible, and that is what separates
# "an intended node that broke" (block) from "someone else's metadata that broke" (warn).
_MARKER_LINE_RE = re.compile(r"^wiki_id\s*:", re.MULTILINE)


def _broken_front_matter(text: str) -> tuple[str, bool] | None:
    """(reason, marker_seen) when a `---` block exists but does not parse as a map, else None.

    `parse_front_matter` returns None for three different situations and only one of them is a
    broken document, so its return value cannot drive a warning:

    - no leading `---` at all — an ordinary markdown file, silent
    - a leading `---` with no closing one — not front matter either. A horizontal rule or a
      setext underline on the first line is common, and counting those as broken turns the
      warning into noise
    - an opened AND closed block that raises or yields a non-None non-map — the broken
      document. `None` (an empty block, or one holding only comments) is excluded: Jekyll
      writes `---\n---\n` by convention, and that is not broken, just not a node.

    Re-parsing costs one extra parse per broken file, which is rarer than changing
    parse_front_matter's signature is disruptive (three tests call it directly).
    """
    block = _front_matter_block(text)
    if block is None:
        return None
    try:
        import yaml

        front = yaml.safe_load(block)
    except Exception as exc:
        # One line: this rides a hook deny message, and PyYAML's mark spans three.
        reason = " ".join(str(exc).split())
    else:
        # `front is None` covers an EMPTY block (`---\n---`), which Jekyll writes by
        # convention and which is not broken — it is simply not a node. Reporting it would
        # put the warning back on ordinary documentation, which is what this task avoids.
        if front is None or isinstance(front, dict):
            return None
        reason = f"front matter 가 map 이 아닙니다 (YAML 이 {type(front).__name__} 로 읽었습니다)"
    return reason, bool(_MARKER_LINE_RE.search(block))


def _candidate_files(root: Path, wiki: dict) -> tuple[list[Path], bool]:
    """The .md files that make up the wiki, path-sorted, and whether that set is authoritative.

    Taken from git's index, not the filesystem. The graph is committed, so it must describe
    what the repository contains: a file the filesystem shows but git does not is invisible to
    everyone else, and putting it in the graph makes the committed graph.yaml unreproducible.
    Two concrete failures that caused, both blocking every commit repo-wide:

    - A gitignored tree under the wiki root — a Docusaurus/MkDocs build output, node_modules —
      carries front matter and counts as nodes that no teammate will ever have.
    - An untracked scratch draft puts a node in the graph its author commits; the teammate who
      pulls rebuilds a graph WITHOUT it, is blocked, rebuilds, and blocks the author in turn.

    Index contents mean `git add` is what admits a document to the wiki, which also makes the
    inverse true: build AFTER staging new documents, or the freshly staged file shows up as
    drift on the next verify.

    Falls back to walking the filesystem when git cannot answer, because `--build` has to work
    outside a repository too. The second return value says whether the result can be *gated*
    on, which is not the same question:

    - Outside a repository (or with no git at all) the filesystem IS the record — authoritative,
      and there is no commit to gate anyway.
    - Inside one, a failed `ls-files` (timeout, index lock, nonzero exit) is an internal error,
      and the fallback silently re-admits the gitignored and untracked files above. Gating on
      that would report drift nobody else has and deny every commit in the repo, while the
      remedy it prints (`--build`) would commit the poisoned graph. Not authoritative —
      `cmd_verify` fails open instead (Invariant #1), and `cmd_build` refuses to write.
    """
    base = root / wiki["root"]
    # -z is mandatory, not a nicety: with the default core.quotePath, `git ls-files` returns a
    # non-ASCII path as a quoted C-escape ("docs/\355\225\234\352\270\200.md"), which resolves to
    # no file on disk. A Korean-named document would drop out of the graph without a word and
    # block every commit as drift — the exact failure this function exists to prevent.
    listing = _git(["ls-files", "--cached", "-z", "--", f"{wiki['root']}/"], root)
    if listing is None:
        # "Is this a repository" must NOT be a second git call: it would share the first
        # call's failure mode, so the very load spike that timed out ls-files would time it
        # out too and misread "repo under load" as "not a repo" — reinstating the false
        # block this flag exists to prevent. The filesystem cannot time out. `.git` is a
        # directory in a normal repo and a file in a worktree or submodule; exists() covers
        # both, and the gate only ever runs with root at the (work)tree toplevel.
        inside_repo = (root / ".git").exists()
        return sorted(base.rglob("*.md")), not inside_repo
    out: list[Path] = []
    for rel in listing.split("\0"):
        if not rel.endswith(".md"):
            continue
        path = root / rel
        if path.is_file():
            out.append(path)
    return sorted(out), True


def collect_nodes(root: Path, wiki: dict, paths: list[Path] | None = None) -> list[dict]:
    """Collect every wiki .md that carries front matter, path-sorted.

    `paths` overrides the file set, for a caller that already ran `_candidate_files` and
    needs its index/filesystem flag as well.
    """
    nodes: list[dict] = []
    for path in _candidate_files(root, wiki)[0] if paths is None else paths:
        try:
            # utf-8-sig strips a leading BOM if present (Windows editors add one) and reads
            # plain UTF-8 unchanged otherwise. Plain "utf-8" would keep the BOM glued to the
            # opening "---", so parse_front_matter's startswith check fails silently and the
            # node vanishes from the graph with no warning (Invariant #2 — wrong only on
            # Windows, wrong in the permissive direction).
            text = path.read_text(encoding="utf-8-sig")
        except (OSError, UnicodeDecodeError):
            continue
        front = parse_front_matter(text)
        if front is None:
            broken = _broken_front_matter(text)
            if broken is None:
                continue  # no front matter at all — an ordinary markdown file
            reason, marker_seen = broken
            # `front` stays an EMPTY DICT, never None: every consumer already skips on a falsy
            # id, and a None here would turn each `node["front"].get(...)` into a crash.
            nodes.append(
                {
                    "id": None,
                    "path": path.relative_to(root).as_posix(),
                    "line_count": len(text.splitlines()),
                    "front": {},
                    "broken": reason,
                    "marker_seen": marker_seen,
                }
            )
            continue
        raw_id = front.get("wiki_id")
        nodes.append(
            {
                "id": str(raw_id) if raw_id else None,
                "path": path.relative_to(root).as_posix(),
                "line_count": len(text.splitlines()),
                "front": front,
            }
        )
    return nodes


GRAPH_HEADER = "# GENERATED by wiki_graph.py --build. Do not edit by hand.\n"
# Manually written edges mapped to the reverse edges derived from them. Writing a reverse
# edge by hand would give the graph two sources of truth, so validation blocks on it.
# EDGE_KEYS carries its own ORDER (the --neighbors budget priority) and so is not derived
# from the two above; tests/test_wiki_graph.py enforces that the three stay in sync.
DERIVED_EDGES = {"depends_on": "used_by", "affects": "defects"}
MANUAL_EDGES = ("depends_on", "related", "affects")
EDGE_KEYS = ("depends_on", "used_by", "affects", "defects", "related")
# Front-matter fields carried onto a node (scalar or list). `sources` is handled separately
# because it converts from a map to a list.
_NODE_FIELDS = ("title", "tags", "aliases", "commit", "regression_test", "promoted_to_rule")


def _as_list(val) -> list[str]:
    """Normalize a scalar / list / None into a list of strings."""
    if val is None:
        return []
    if isinstance(val, (list, tuple)):
        return [str(v) for v in val if v is not None]
    return [str(val)]


def build_graph(nodes: list[dict]) -> dict:
    """Build the graph dict from a node list. Reverse edges are generated only here."""
    out_nodes: dict[str, dict] = {}
    edges: dict[str, dict[str, list[str]]] = {k: {} for k in EDGE_KEYS}
    for node in nodes:
        nid = node["id"]
        if not nid:
            continue
        front = node["front"]
        entry: dict = {"path": node["path"]}
        for field in _NODE_FIELDS:
            val = front.get(field)
            if isinstance(val, (list, tuple)):
                val = [str(v) for v in val if v is not None]
            if val:
                entry[field] = val
        sources = front.get("sources")
        if isinstance(sources, dict) and sources:
            entry["sources"] = sorted(str(k) for k in sources)
        elif sources:
            entry["sources"] = sorted(_as_list(sources))
        out_nodes[nid] = entry
        for kind in MANUAL_EDGES:
            targets = sorted(set(_as_list(front.get(kind))))
            if targets:
                edges[kind][nid] = targets
    for kind, derived in DERIVED_EDGES.items():
        for src, targets in edges[kind].items():
            for target in targets:
                edges[derived].setdefault(target, []).append(src)
    for derived in DERIVED_EDGES.values():
        edges[derived] = {k: sorted(set(v)) for k, v in edges[derived].items()}
    return {"version": 1, "nodes": out_nodes, "edges": edges}


def dump_graph(graph: dict) -> str:
    """Deterministic YAML serialization. Fixed key ordering is what makes drift comparable."""
    import yaml

    body = yaml.safe_dump(
        graph, sort_keys=True, allow_unicode=True, default_flow_style=False, width=100
    )
    return GRAPH_HEADER + body


def graph_path(root: Path, wiki: dict) -> Path:
    """Where graph.yaml lives — <wiki.root>/graph/graph.yaml."""
    return root / wiki["root"] / "graph" / "graph.yaml"


# Defect-node discriminator — identified by an id prefix alone, with no separate flag field.
DEFECT_PREFIX = "defect."
DEFECT_FIELDS = ("affects", "commit", "regression_test", "promoted_to_rule")
_SHA_RE = re.compile(r"^[0-9a-f]{7,40}$")

WIKI_ID_RE = re.compile(r"^[a-z0-9-]+(\.[a-z0-9-]+)*$")

# Front-matter fields that must be text. PyYAML resolves YAML 1.1 scalars, so an unquoted value
# can arrive as something the author never typed: `commit: 0123456` is octal → int 42798, and
# `title: no` is a bool → False. Both then fail downstream in a way that names a value nobody
# wrote ("commit '42798' is not hex") or contradicts the file ("title missing" on a doc that has
# one). Reporting the type mismatch itself is the only message that leads to the fix.
# `wiki_id` is in the list because it decides whether the file is a node at all:
# `wiki_id: no` → False → the document drops out of the graph and is reported as having no
# marker, and `wiki_id: 0123456` → 42798 becomes a valid-looking id for a node nobody wrote.
_TEXT_FIELDS = ("wiki_id", "title", "commit", "regression_test", "promoted_to_rule")


def _wrong_type(path: str, field: str, val) -> str:
    return (
        f"{path}: {field} 가 문자열이 아닙니다 — YAML 이 {type(val).__name__} 로 읽었습니다"
        f" (값 {val!r}). 따옴표로 감싸세요"
    )


def _text_type_problems(path: str, front: dict) -> list[str]:
    """Report front-matter values that YAML resolved to a non-string. Absent fields are fine."""
    out = []
    for field in _TEXT_FIELDS:
        val = front.get(field)
        if val is None or isinstance(val, str):
            continue
        out.append(_wrong_type(path, field, val))
    for field in MANUAL_EDGES:
        val = front.get(field)
        # Edge targets are ids, so they are text too. `depends_on: no` becomes the string
        # "False" through _as_list and surfaces as "points at a missing id 'False'".
        for item in val if isinstance(val, (list, tuple)) else [val]:
            if item is None or isinstance(item, str):
                continue
            out.append(_wrong_type(path, f"{field}[]", item))
    return out


def _find_cycle(adjacency: dict[str, list[str]]) -> list[str] | None:
    """Return one cycle in the depends_on graph as a path, or None.

    Iterative DFS, so there is no recursion-depth limit.
    """
    color: dict[str, int] = {}  # 0 = in progress, 1 = done
    for start in sorted(adjacency):
        if color.get(start) == 1:
            continue
        stack = [(start, iter(adjacency.get(start, ())))]
        path = [start]
        color[start] = 0
        while stack:
            node, it = stack[-1]
            nxt = next(it, None)
            if nxt is None:
                color[node] = 1
                stack.pop()
                path.pop()
                continue
            if color.get(nxt) == 0:
                return path[path.index(nxt) :] + [nxt]
            if color.get(nxt) != 1:
                color[nxt] = 0
                path.append(nxt)
                stack.append((nxt, iter(adjacency.get(nxt, ()))))
    return None


def validate_defects(root: Path, nodes: list[dict]) -> list[str]:
    """Collect Defect Memory rule violations.

    `commit` is checked for shape only. Proving it exists would need `git cat-file`, which
    breaks the principle that verification stays read-only and structural.
    """
    problems: list[str] = []
    for node in nodes:
        nid, path = node["id"], node["path"]
        front = node["front"]
        if not nid:
            continue
        if not nid.startswith(DEFECT_PREFIX):
            used = [f for f in DEFECT_FIELDS if front.get(f)]
            if used:
                problems.append(
                    f"{path}: {used} 는 defect 노드 전용 필드입니다 — "
                    f"id 를 '{DEFECT_PREFIX}' 로 시작하거나 필드를 지우세요"
                )
            continue
        if not front.get("affects"):
            problems.append(f"{path}: defect 노드에는 affects 가 필요합니다")
        commit = front.get("commit")
        if commit and not _SHA_RE.match(str(commit)):
            problems.append(f"{path}: commit '{commit}' 은 hex 7~40자가 아닙니다")
        # A missing path here blocks, while a missing `sources` path only warns
        # (collect_warnings). The asymmetry is deliberate: `sources` may legitimately name a
        # file that is not on disk — generated, gitignored, present only on another branch —
        # so there is no edit that makes it exist and blocking would freeze the repo with no
        # remedy. These two name a tracked repository artifact and assert it exists ("this
        # defect has a regression test"), so an absent path means the claim is false; the
        # commonest cause is the template's placeholder left uncommented, and both the fix
        # (correct the path) and the escape hatch (delete the line) are one edit away.
        for field in ("regression_test", "promoted_to_rule"):
            val = front.get(field)
            if not val:
                continue
            rel = str(val).split("::", 1)[0]
            if not (root / rel).exists():
                problems.append(f"{path}: {field} 경로 '{rel}' 가 없습니다")
    return problems


def validate_structure(root: Path, wiki: dict, nodes: list[dict], graph: dict) -> list[str]:
    """Collect structural violations (block reasons). An empty list means pass.

    Most violations require correctly parsed front matter, but one is checked first and
    does not: a `---` block that failed to parse while its raw text still carries a
    `wiki_id:` line is blocked below too (the `node.get("broken")` branch) — that is the
    only fail-closed path this module adds, because a marker line makes the author's intent
    unambiguous. `collect_nodes` only drops a file silently when there is no front matter at
    all, or a broken block with no marker seen; neither of those reaches this function.

    A dedicated `wiki_id` is what marks a wiki node. `id` is NOT used: it is a documented
    first-class front-matter field in Docusaurus and Jekyll, and a wiki root is very often
    the same `docs/` tree they own — reading it as a node id made someone else's
    `id: Getting_Started` a format violation that blocked every commit in the repository,
    with no remedy `--build` or doc-sync could apply. A document with no `wiki_id` is not a
    node and is skipped; collect_warnings surfaces the ones that look like they meant to be.
    """
    problems: list[str] = []
    seen: dict[str, str] = {}
    for node in nodes:
        if node.get("broken"):
            if node.get("marker_seen"):
                problems.append(
                    f"{node['path']}: wiki_id 가 있는데 front matter 를 읽지 못했습니다 — "
                    f"{node['broken']}"
                )
            continue
        nid, path = node["id"], node["path"]
        front = node["front"]
        raw_id = front.get("wiki_id")
        if raw_id is not None and not isinstance(raw_id, str):
            # Checked before the not-a-node skip below: `wiki_id: no` resolves to False, which
            # makes nid None, so the document would otherwise be reported as having no marker.
            problems.append(_wrong_type(path, "wiki_id", raw_id))
            continue
        if not nid:
            continue
        if not WIKI_ID_RE.match(nid):
            problems.append(f"{path}: wiki_id '{nid}' 형식 위반 (허용: {WIKI_ID_RE.pattern})")
        if nid in seen:
            problems.append(f"{path}: wiki_id '{nid}' 중복 — 이미 {seen[nid]} 가 사용 중")
        else:
            seen[nid] = path
        problems.extend(_text_type_problems(path, front))
        # `is None`, not truthiness: `title: no` parses to False, and reporting a document that
        # visibly has a title as missing one leaves the author with nowhere to go.
        # _text_type_problems above already names the real cause for that case.
        title = front.get("title")
        if title is None or (isinstance(title, str) and not title.strip()):
            problems.append(f"{path}: 필수 필드 title 이 없습니다")
        for derived in DERIVED_EDGES.values():
            if front.get(derived):
                problems.append(
                    f"{path}: '{derived}' 는 생성 필드입니다 — 손으로 쓰지 마세요 "
                    f"(역 edge 는 build 가 만듭니다)"
                )
        sources = front.get("sources")
        if sources is not None and not isinstance(sources, dict):
            # The shape the design (§2) explicitly rejects (a list) — and the easiest one
            # to write by hand. cmd_stale silently skips anything that is not a map, so
            # without this block the node would be invisible to staleness forever.
            problems.append(f"{path}: sources 는 map 이어야 합니다 (경로→sha) — 리스트/값 아님")
        elif isinstance(sources, dict):
            for key in sorted(sources, key=str):
                src = str(key)
                sha = sources[key]
                if sha is not None and not isinstance(sha, str):
                    # Same YAML 1.1 trap as _TEXT_FIELDS: `src/a.py: 0123456` records int 42798,
                    # so the node compares against a sha nobody wrote and reports stale forever.
                    problems.append(
                        f"{path}: sources['{src}'] 의 sha 가 문자열이 아닙니다 — YAML 이 "
                        f"{type(sha).__name__} 로 읽었습니다 (값 {sha!r}). 따옴표로 감싸세요"
                    )
    known = set(graph["nodes"])
    id_to_path = {nid: graph["nodes"][nid]["path"] for nid in graph["nodes"]}
    for kind in MANUAL_EDGES:
        for src, targets in sorted(graph["edges"][kind].items()):
            for target in targets:
                if target not in known:
                    src_path = id_to_path.get(src, src)
                    problems.append(
                        f"{src_path}: {kind} 가 가리키는 id '{target}' 인 노드가 없습니다 "
                        f"— 대상 문서의 wiki_id 를 확인하거나 이 항목을 고치세요"
                    )
    cycle = _find_cycle(graph["edges"]["depends_on"])
    if cycle:
        cycle_paths = [id_to_path.get(nid, nid) for nid in cycle]
        problems.append("depends_on 순환: " + " → ".join(cycle_paths))
    return problems + validate_defects(root, nodes)


def _safe_int(val, default: int = 0) -> int:
    """Convert a hand-written YAML value to an int, falling back to a default (Invariant #1)."""
    try:
        return int(val) if val is not None else default
    except (ValueError, TypeError):
        return default


def undirected_adjacency(graph: dict) -> dict[str, list[str]]:
    """Adjacency over every edge with direction ignored.

    Shared by orphan detection and --neighbors. Neighbours come out in EDGE_KEYS order
    (depends_on → used_by → affects → defects → related): within one hop that lets a
    structural dependency claim budget before a loose association. Reachability does not
    care about order, so one function serves both callers.

    Ids that do not exist (dangling edge targets) are carried neither as keys nor as
    values — carrying them would let two nodes pointing at the same typo count as
    connected during orphan detection.
    """
    known = set(graph["nodes"])
    adj: dict[str, list[str]] = {nid: [] for nid in known}
    for kind in EDGE_KEYS:
        for src, targets in graph["edges"][kind].items():
            if src not in known:
                continue
            for target in targets:
                if target not in known:
                    continue
                adj[src].append(target)
                adj[target].append(src)
    out: dict[str, list[str]] = {}
    for nid, targets in adj.items():
        seen: set[str] = set()
        out[nid] = [t for t in targets if not (t in seen or seen.add(t))]
    return out


def _index_id(wiki: dict, graph: dict) -> str | None:
    """The node id whose path is the configured wiki.index."""
    index_path = str(wiki.get("index") or "")
    for nid, entry in graph["nodes"].items():
        if entry["path"] == index_path:
            return nid
    return None


# Fields only a wiki node carries. `tags` is deliberately NOT here: Jekyll and Docusaurus use
# it too, so it cannot tell "meant to be a node" from "someone else's metadata".
WIKI_ONLY_FIELDS = ("related", "depends_on", "affects", "sources")


def _wiki_fields_present(front: dict) -> list[str]:
    """Wiki-only fields this document carries. Non-empty means the author meant it as a node."""
    return [f for f in WIKI_ONLY_FIELDS if front.get(f) is not None]


WARN_CAP = 3

# Warnings are a sample; structural problems are a work list. Capping them at WARN_CAP would
# make an author with 20 violations run --verify seven times to see them all, while ten lines
# still read as a deny message.
PROBLEM_CAP = 10


def _capped(warns: list[str], lines: list[str], label: str) -> None:
    """Append at most WARN_CAP lines plus a count. Every warning list obeys this.

    These print on every commit and, when the gate blocks for some other reason, are carried
    into one deny message. A repo mid-migration has hundreds of orphans; uncapped, that is
    hundreds of lines per commit and a deny reason nobody can read.
    """
    warns.extend(lines[:WARN_CAP])
    if len(lines) > WARN_CAP:
        warns.append(f"  ... 외 {len(lines) - WARN_CAP}건 ({label})")


def collect_warnings(
    wiki: dict, nodes: list[dict], graph: dict, root: Path | None = None
) -> list[str]:
    """Collect non-blocking quality warnings (orphans, file size, missing sources, promotion).

    ``root`` enables the sources-path check; omit it to skip that one.
    """
    warns: list[str] = []
    start = _index_id(wiki, graph)
    if start:
        adj = undirected_adjacency(graph)
        seen = {start}
        queue = [start]
        while queue:
            cur = queue.pop()
            for nxt in adj.get(cur, ()):
                if nxt not in seen:
                    seen.add(nxt)
                    queue.append(nxt)
        _capped(
            warns,
            [
                f"orphan: '{nid}' 는 index 에서 도달할 수 없습니다 ({graph['nodes'][nid]['path']})"
                for nid in sorted(set(graph["nodes"]) - seen)
            ],
            "orphan",
        )
    elif graph["nodes"]:
        # With the wiki enabled, an index that resolves to no node needs a signal (unlike a
        # missing config): it means orphan detection is entirely off. With no nodes at all
        # there is nothing to check, so stay quiet.
        idx_path = wiki.get("index") or ""
        warns.append(
            f"wiki.index 경로 '{idx_path}' 에 대응하는 wiki 노드가 없어 orphan 검사를 "
            f"생략합니다 — 해당 문서에 wiki_id 가 있는지, 경로가 맞는지 확인하세요"
        )
    _capped(
        warns,
        [
            f"{node['path']}: front matter 를 읽지 못해 wiki 노드로 보지 않습니다 — "
            f"{node['broken']}"
            for node in nodes
            if node.get("broken") and not node.get("marker_seen")
        ],
        "읽지 못한 front matter",
    )
    # A missing marker is the NORMAL state once the key is dedicated — a Docusaurus tree under
    # the wiki root has hundreds of such files, and warning on all of them is permanent noise
    # on every commit. Wiki-only fields are the one signal that separates a forgotten marker
    # from someone else's metadata.
    _capped(
        warns,
        [
            f"{node['path']}: {', '.join(_wiki_fields_present(node['front']))} 가 있는데 "
            f"wiki_id 가 없어 wiki 노드로 보지 않습니다"
            for node in nodes
            if not node["id"] and not node.get("broken") and _wiki_fields_present(node["front"])
        ],
        "wiki_id 없는 wiki 필드",
    )
    if root is not None:
        # A sources path that is not on disk. NOT a block: a doc legitimately documents a
        # generated or gitignored file (a built API client), or a file that exists only on
        # another branch — and blocking on that freezes every commit, including code-only ones,
        # with no remedy `--build` can apply. `--stale` carries the same fact to doc-sync as
        # `missing: true`, which is where the repair belongs.
        _capped(
            warns,
            [
                f"{node['path']}: sources 경로 '{src}' 가 없습니다 — 파일이 옮겨졌거나 지워졌다면 "
                f"sha 를 찍지 말고 경로를 고치거나 항목을 지우세요"
                for node in nodes
                if node["id"] and isinstance(node["front"].get("sources"), dict)
                for src in sorted(str(k) for k in node["front"]["sources"])
                if not (root / src).exists()
            ],
            "없는 sources 경로",
        )
    cap = _safe_int(wiki.get("max_lines"))
    if cap > 0:
        _capped(
            warns,
            [
                f"{node['path']}: {node['line_count']}줄 (> max_lines {cap}) — "
                f"한 파일 한 개념으로 쪼개세요"
                for node in nodes
                if node["id"] and node["line_count"] > cap
            ],
            "max_lines 초과",
        )
    threshold = _safe_int(wiki.get("defect_rule_threshold"))
    if threshold > 0:
        by_tag: dict[str, list[str]] = {}
        promoted: set[str] = set()
        for node in nodes:
            nid = node["id"]
            if not nid or not nid.startswith(DEFECT_PREFIX):
                continue
            for tag in _as_list(node["front"].get("tags")):
                by_tag.setdefault(tag, []).append(nid)
                if node["front"].get("promoted_to_rule"):
                    promoted.add(tag)
        _capped(
            warns,
            [
                f"Rule 승격 검토: tag '{tag}' 로 defect 가 {len(by_tag[tag])}건인데 "
                f"promoted_to_rule 이 없습니다"
                for tag in sorted(by_tag)
                if len(by_tag[tag]) >= threshold and tag not in promoted
            ],
            "Rule 승격 후보",
        )
    return warns


def _last_commit(root: Path, rel: str) -> str:
    """One-line summary of the file's last commit, or "" when the lookup fails.

    The person who created the drift and the person it blocks can be different (design §4), so
    the failure message names the commit behind it rather than reading as a bug in the gate.
    """
    return _git(["log", "-1", "--format=%h %an %s", "--", rel], root) or ""


def _parse_graph(text: str | None) -> dict | None:
    """Parse on-disk graph.yaml text into a dict. None if unreadable or not a map.

    Never raises.
    """
    if text is None:
        return None
    try:
        import yaml

        loaded = yaml.safe_load(text)
    except Exception:
        return None
    return loaded if isinstance(loaded, dict) else None


def _drifted_paths(graph: dict, disk: dict | None) -> list[str]:
    """File paths of the nodes where the on-disk graph and a fresh rebuild disagree.

    Sorted and deduplicated. Since the person who created the drift and the person it
    blocks can differ, the failure message has to say WHICH document drifted, not merely
    that something did. When that cannot be determined (no file, parse failure, YAML that
    parses but is not a map, or nodes/edges that are not maps) the result is an empty
    list — this function never raises. A rename can leave two ids pointing at one path, so
    paths are deduplicated too.
    """
    if disk is None:
        return []
    disk_nodes = disk.get("nodes")
    if not isinstance(disk_nodes, dict):
        disk_nodes = {}
    live_nodes = graph.get("nodes") or {}
    changed = {
        nid
        for nid in set(disk_nodes) | set(live_nodes)
        if disk_nodes.get(nid) != live_nodes.get(nid)
    }
    disk_edges = disk.get("edges")
    if not isinstance(disk_edges, dict):
        disk_edges = {}
    for kind in EDGE_KEYS:
        on_disk = disk_edges.get(kind)
        if not isinstance(on_disk, dict):
            on_disk = {}
        live = graph["edges"][kind]
        for nid in set(on_disk) | set(live):
            if on_disk.get(nid) != live.get(nid):
                changed.add(nid)
    paths: list[str] = []
    seen: set[str] = set()
    for nid in sorted(changed):
        entry = live_nodes.get(nid) or disk_nodes.get(nid) or {}
        if not isinstance(entry, dict):
            entry = {}
        path = entry.get("path")
        if path and path not in seen:
            seen.add(path)
            paths.append(path)
    return paths


def _load(root: Path):
    """(wiki, nodes, graph, authoritative), or (None, [], {}, False) when there is no wiki.

    `authoritative` is False only when the node set is known to be untrustworthy — see
    `_candidate_files`. `cmd_verify` fails open on it; `cmd_build` refuses to write from it.
    """
    wiki = load_wiki_config(root)
    if wiki is None:
        return None, [], {}, False
    paths, authoritative = _candidate_files(root, wiki)
    nodes = collect_nodes(root, wiki, paths)
    return wiki, nodes, build_graph(nodes), authoritative


def neighbors(
    graph: dict, nodes: list[dict], start: str, budget: int
) -> tuple[list[str], int, int]:
    """BFS out from the entry point, collecting file paths that fit a line budget.

    There is no depth limit — the budget is the only brake, and the visited set handles
    cycles. The entry point itself is always included even if it alone exceeds the budget,
    so the result is never empty.
    """
    if start not in graph["nodes"]:
        return [], 0, 0
    lines = {n["id"]: n["line_count"] for n in nodes if n["id"]}
    adj = undirected_adjacency(graph)
    paths = [graph["nodes"][start]["path"]]
    total = lines.get(start, 0)
    seen = {start}
    queue = [start]
    cut = 0
    while queue:
        cur = queue.pop(0)
        for nxt in adj.get(cur, ()):
            if nxt in seen:
                continue
            seen.add(nxt)
            # No "is this a real node" check needed: undirected_adjacency already drops ids
            # that are not in graph["nodes"], so every neighbour reached here exists.
            cost = lines.get(nxt, 0)
            if total + cost > budget:
                cut += 1
                continue
            total += cost
            paths.append(graph["nodes"][nxt]["path"])
            queue.append(nxt)
    return paths, total, cut


def cmd_neighbors(root: Path, start: str, budget: int | None) -> int:
    """Print neighbouring document paths to stdout. The gate never calls this (lookup only).

    An unknown id exits 1: exit 0 with empty stdout is indistinguishable from "this node
    has no neighbours", so the caller reads a failed lookup as "nothing to harmonize" and
    moves on.
    """
    wiki, nodes, graph, _authoritative = _load(root)
    if wiki is None:
        return 0
    limit = budget if budget is not None else _safe_int(wiki.get("context_lines"))
    paths, total, cut = neighbors(graph, nodes, start, limit)
    if not paths:
        print(f"알 수 없는 id: '{start}'", file=sys.stderr)
        return 1
    for path in paths:
        print(path)
    print(f"# {len(paths)}개 문서 {total}줄 / 예산 {limit}줄, 잘림 {cut}개", file=sys.stderr)
    return 0


def cmd_build(root: Path) -> int:
    """Write graph.yaml. doc-sync only — the gate never calls this."""
    wiki, _nodes, graph, authoritative = _load(root)
    if wiki is None:
        return 0
    if not authoritative:
        # Inside a repository whose ls-files failed, the fallback node set holds the
        # gitignored and untracked files the index deliberately excludes — writing it IS the
        # poisoned graph.yaml that cmd_verify refuses to gate on, and a doc-sync that commits
        # it hands the drift to every teammate. Verify fails open here because blocking is
        # the harm; build refuses here because writing is. One re-run is the whole remedy.
        # (Outside a repository the filesystem set is authoritative, so --build still works.)
        print(
            "graph.yaml 생성 중단: git 인덱스를 읽지 못했습니다 — --build 를 다시 실행하세요",
            file=sys.stderr,
        )
        return 1
    target = graph_path(root, wiki)
    # Serialize BEFORE opening the file. `open("w")` truncates immediately, so computing the
    # content as the write argument means a dump_graph failure leaves a 0-byte graph.yaml behind
    # while main()'s FAIL-OPEN reports exit 0 — --verify then blocks every commit on a file the
    # build claimed to have written.
    text = dump_graph(graph)
    target.parent.mkdir(parents=True, exist_ok=True)
    # newline="" keeps LF on Windows so the committed graph.yaml is byte-identical whoever
    # built it. Written through Path.open, NOT Path.write_text(newline=…): that keyword only
    # exists on Python 3.10+, while the gate's floor is 3.8 (check-deps.sh / precommit-runner.sh).
    # On a 3.9 host it would raise TypeError, main()'s FAIL-OPEN would swallow it into exit 0,
    # and --build would silently write nothing — leaving --verify to block every commit forever
    # with no working remedy.
    with target.open("w", encoding="utf-8", newline="") as fh:
        fh.write(text)
    print(f"graph.yaml 생성: {target.relative_to(root).as_posix()} (노드 {len(graph['nodes'])}개)")
    return 0


def cmd_verify(root: Path) -> int:
    """Read-only verification. Returns 1 on any violation or drift."""
    wiki, nodes, graph, authoritative = _load(root)
    if wiki is None:
        return 0
    if not authoritative:
        # git could not list its own index, so the node set came from walking the filesystem
        # (see _candidate_files) — it holds the gitignored and untracked files the index
        # deliberately excludes. Verifying that set reports drift nobody else has, and the
        # remedy it prints (`--build`) would commit the poisoned graph and block the whole
        # team. A git that cannot answer is an internal error: fail open (Invariant #1).
        print(
            "wiki 검증 생략: git 인덱스를 읽지 못했습니다 — 다음 커밋에서 다시 검사합니다",
            file=sys.stderr,
        )
        return 0
    problems = validate_structure(root, wiki, nodes, graph)
    structural = len(problems)  # count before drift reasons — picks which remedy hint to print
    target = graph_path(root, wiki)
    actual: str | None = None
    unreadable = False
    if target.is_file():
        try:
            actual = target.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            # A graph.yaml we cannot read is not evidence of being current — treat it as
            # drift and block. (Invariant #1 lists an unreadable file as a fail-open cause,
            # but this is not "verification failed": it is "the thing being verified cannot
            # be shown to be current", which is a different claim.)
            unreadable = True
    # Compare parsed content, not bytes. PyYAML's emitter differs subtly between versions in
    # line width and quoting style, and a byte comparison reads that difference as drift — A
    # commits, B is blocked, B rebuilds, A is blocked, forever. Same meaning, same graph.
    disk = _parse_graph(actual)
    drift = unreadable or disk != graph
    if drift:
        if unreadable:
            rel = target.relative_to(root).as_posix()
            problems.append(f"graph.yaml 을 읽을 수 없습니다: {rel}")
        else:
            detail = "없습니다" if actual is None else "front matter 와 어긋납니다"
            problems.append(f"graph.yaml 이 {detail}")
        drifted = _drifted_paths(graph, disk)
        for path in drifted[:3]:
            info = _last_commit(root, path)
            problems.append(f"  어긋난 노드: {path}" + (f" — 최근 변경 {info}" if info else ""))
        if len(drifted) > 3:
            problems.append(f"  ... 외 {len(drifted) - 3}건")
    for warn in collect_warnings(wiki, nodes, graph, root):
        print(warn, file=sys.stderr)
    if problems:
        print("wiki graph 검증 실패:", file=sys.stderr)
        # Cap the STRUCTURAL section only. The drift reasons appended after it carry the other
        # remedy, and letting ten structural violations push them off the message would leave
        # half the failures with no way out. `structural` already marks that boundary.
        for line in problems[:structural][:PROBLEM_CAP]:
            print(f"  - {line}", file=sys.stderr)
        if structural > PROBLEM_CAP:
            print(f"  - ... 외 {structural - PROBLEM_CAP}건 (구조 위반)", file=sys.stderr)
        for line in problems[structural:]:
            print(f"  - {line}", file=sys.stderr)
        # The remedy differs by cause. --build only makes the graph match the front matter,
        # so it does nothing for a structural violation (id format/duplicate, missing title,
        # dangling reference, cycle) — there the document is what needs fixing. Printing
        # only one hint sends half the failures down a path that cannot work.
        if structural:
            print("해소(구조 위반): 위에 지목된 문서의 front matter 를 고치세요.", file=sys.stderr)
        if drift:
            print(
                "해소(그래프 불일치): doc-sync 스킬을 실행하거나 "
                "python3 .claude/harness-tier/scripts/wiki_graph.py --build "
                "— 만든 graph.yaml 을 문서와 함께 스테이징해야 합니다.",
                file=sys.stderr,
            )
        return 1
    return 0


def cmd_stale(root: Path) -> int:
    """Compare each recorded `sources` sha against the file's last commit, as JSON. Always 0.

    A lookup, so it never blocks — the gate does not call it; only doc-sync consumes it.
    """
    wiki = load_wiki_config(root)
    if wiki is None:
        print(json.dumps([], ensure_ascii=False))
        return 0
    out: list[dict] = []
    # Several nodes legitimately list the same code path, and a process spawn is the most
    # expensive syscall on the Windows host this plugin targets — ask git once per path.
    head_cache: dict[str, str] = {}
    for node in collect_nodes(root, wiki):
        if not node["id"]:
            continue
        sources = node["front"].get("sources")
        if not isinstance(sources, dict):
            continue
        for key in sorted(sources, key=str):
            src = str(key)
            # Only a non-empty string is a recorded sha. `src/a.py: ""` would otherwise make
            # `current.startswith("")` unconditionally true and the node would report fresh
            # forever; a YAML-coerced int (octal sha) is not a sha the author wrote either.
            raw = sources[key]
            recorded = raw if isinstance(raw, str) and raw else None
            if not (root / src).exists():
                # The file moved or was deleted. git log still answers for a deleted path, so
                # without this the entry reads as an ordinary sha drift and doc-sync stamps the
                # new sha — leaving --verify's "sources 경로 … 가 없습니다" block in place.
                out.append(
                    {
                        "id": node["id"],
                        "path": node["path"],
                        "source": src,
                        "recorded": recorded,
                        "current": None,
                        "missing": True,
                    }
                )
                continue
            if src not in head_cache:
                head_cache[src] = _git(["log", "-1", "--format=%H", "--", src], root) or ""
            current = head_cache[src]
            if not current:
                continue  # a failed git lookup is not staleness (FAIL-OPEN)
            if recorded is not None and current.startswith(recorded):
                continue
            out.append(
                {
                    "id": node["id"],
                    "path": node["path"],
                    "source": src,
                    "recorded": recorded,
                    "current": current,
                    "missing": False,
                }
            )
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point. Every exception raised here fails open.

    The exit code is the gate's verdict, and wiki is none of Invariant #1's three
    fail-closed exceptions (missing-dependency, unclassified-commit, merge-strategy). An
    argparse usage error is a `SystemExit`, which passes straight through
    `except Exception` and keeps exit 2 — the gate builds this command itself, so a
    mistyped flag cannot happen at runtime.
    """
    force_utf8_io()
    try:
        parser = argparse.ArgumentParser(prog="wiki_graph.py", description="LLM Wiki graph tool")
        group = parser.add_mutually_exclusive_group(required=True)
        group.add_argument("--build", action="store_true", help="graph.yaml 생성 (doc-sync 전용)")
        group.add_argument("--verify", action="store_true", help="읽기 전용 검증 (flow gate 전용)")
        group.add_argument("--stale", action="store_true", help="코드 stale 목록 (JSON)")
        group.add_argument("--neighbors", metavar="ID", help="예산 내 이웃 문서 경로")
        parser.add_argument("--budget", type=int, default=None, help="줄 예산 (기본값: config)")
        args = parser.parse_args(argv)
        root = host_root()
        if args.build:
            return cmd_build(root)
        if args.stale:
            return cmd_stale(root)
        # `is not None` — an empty string is still a --neighbors request. Branching on
        # truthiness let `--neighbors ""` fall silently through to cmd_verify: the caller
        # read an empty lookup result while a graph verification was actually running,
        # returning 1 on drift.
        if args.neighbors is not None:
            return cmd_neighbors(root, args.neighbors, args.budget)
        return cmd_verify(root)
    except Exception as exc:  # FAIL-OPEN: a broken wiki_graph.py never holds the repo hostage
        print(f"wiki graph 확인 중 내부 오류, 통과 처리합니다: {exc}", file=sys.stderr)
        return 0


if __name__ == "__main__":
    sys.exit(main())
