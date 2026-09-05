#!/usr/bin/env python3
"""Prose gate: style lint over docs and code comments, plus a lossless rewrite check.

Two independent jobs, one file because both read the same prose:

- ``--lint`` flags prose that [rule-doc-style] bans (history narration, plan-record
  pointers, filler, Korean ``~다`` endings, over-long lines). Runs as a flow-gate stage
  and in CI.
- ``--verify`` proves a rewrite dropped nothing. Markdown keeps its headings, fenced
  blocks, URLs and inline code; source keeps its code byte-for-byte once comments and
  docstrings are stripped. Invoked by ``doc-sync`` after it rewrites a document.
"""

from __future__ import annotations

import argparse
import ast
import io
import os
import re
import subprocess
import sys
import tokenize
from collections import Counter
from functools import lru_cache
from pathlib import Path
from typing import TYPE_CHECKING

try:
    from _harness_paths import config_path, force_utf8_io, host_root  # direct (sibling)
except ImportError:
    from scripts._harness_paths import (  # package (test/dev)
        config_path,
        force_utf8_io,
        host_root,
    )

# Any indent, not CommonMark's 0-3: a fence inside a list item is indented past that, and
# reading its body as prose is how an indented code block turns into false lint errors.
# The indent is captured because it also decides what CLOSES the block — see _closes.
FENCE = re.compile(r"^(\s*)(`{3,}|~{3,})(.*)$")
HEADING = re.compile(r"^(#{1,6})\s+(.*)")
BULLET = re.compile(r"^\s*[-*+]\s+", re.MULTILINE)
URL = re.compile(r"https?://[^\s)>\]]+")
INLINE_CODE = re.compile(r"`[^`]+`")
LINK_TARGET = re.compile(r"\]\([^)]*\)")
PATH_LIKE = re.compile(r"(?:\./|\.\./|/|[A-Za-z]:\\)[\w\-/\\.]+|[\w\-.]+[/\\][\w\-/\\.]+")
# 7+ hex chars carrying BOTH a letter and a digit: a commit sha, never an English word
# (`deadbeef` has no digit) and never a plain number (`20240115`, a byte count).
SHA = re.compile(r"\b(?=[0-9a-f]*[a-f])(?=[0-9a-f]*[0-9])[0-9a-f]{7,40}\b")

MAX_LINE = 100

# Under TYPE_CHECKING, so nothing evaluates it: an alias on the right of `=` at module level
# IS evaluated at import, where annotations are deferred, and `tuple[...]` needs python 3.9.
# The gate's runtime floor is 3.8 (check-deps.sh), and a TypeError raised here takes
# flow_gate_check.py down with it — which fails OPEN, letting an unclassified commit through.
if TYPE_CHECKING:
    Finding = tuple[str, int, str, str]  # (severity, line number, rule code, message)


# ---------- Prose extraction ----------


def _closes(opener: re.Match, candidate: re.Match) -> bool:
    """Whether `candidate` ends the block `opener` began.

    Same char, at least as long, no info string — and indented no further than the opener,
    the part that matters once any indent may open a fence: a deeper ``` inside a block is
    content, and reading it as the closer both leaks that content into prose AND leaves an
    unclosed fence that swallows the rest of the document, hiding real violations.
    CommonMark allows the closer up to three spaces further in; keep that slack.
    """
    return (
        candidate.group(2)[0] == opener.group(2)[0]
        and len(candidate.group(2)) >= len(opener.group(2))
        and not candidate.group(3).strip()
        and len(candidate.group(1)) <= len(opener.group(1)) + 3
    )


def _mask(line: str, keep_link_targets: bool = False) -> str:
    """Blank out spans a prose rule must never read: code, URLs, and link targets.

    ``keep_link_targets`` serves PLAN alone: a backticked ``docs/superpowers/plans/`` NAMES
    the banned pattern, where a link to one IS the pointer the rule bans.
    """
    patterns = (INLINE_CODE, URL) if keep_link_targets else (INLINE_CODE, LINK_TARGET, URL)
    for pattern in patterns:
        line = pattern.sub(lambda m: " " * len(m.group(0)), line)
    return line


def markdown_prose(text: str) -> list[tuple[int, str]]:
    """Numbered prose lines, fenced blocks and front matter removed. Masking is per rule."""
    lines = text.split("\n")
    out: list[tuple[int, str]] = []
    opener = None
    start = 0
    if lines and lines[0].strip() == "---":  # YAML front matter
        for i in range(1, len(lines)):
            if lines[i].strip() == "---":
                start = i + 1
                break
    for i in range(start, len(lines)):
        line = lines[i]
        m = FENCE.match(line)
        if opener is not None:
            if m and _closes(opener, m):
                opener = None
            continue
        if m:
            opener = m
            continue
        out.append((i + 1, line))
    return out


def python_prose(text: str) -> list[tuple[int, str]]:
    """Numbered prose lines from `#` comments and every docstring."""
    out: list[tuple[int, str]] = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type == tokenize.COMMENT and not tok.string.startswith("# type:"):
                out.append((tok.start[0], tok.string.lstrip("#").strip()))
    except (tokenize.TokenError, IndentationError, SyntaxError):
        pass
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return sorted(out)
    nodes = [tree] + [
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    ]
    for node in nodes:
        doc = ast.get_docstring(node, clean=False)
        if not doc:
            continue
        base = node.body[0].lineno  # the docstring expression itself
        for offset, line in enumerate(doc.split("\n")):
            out.append((base + offset, line))
    return sorted(out)


def shell_prose(text: str) -> list[tuple[int, str]]:
    """Numbered prose lines from `#` comments, minus shebang and tool directives."""
    out: list[tuple[int, str]] = []
    for i, line in enumerate(text.split("\n"), 1):
        stripped = line.strip()
        if not stripped.startswith("#") or stripped.startswith("#!"):
            continue
        body = stripped.lstrip("#").strip()
        if body.startswith(("shellcheck ", "noqa", "-*-")):
            continue
        out.append((i, body))
    return out


def prose_of(path: Path, text: str) -> list[tuple[int, str]]:
    if path.suffix == ".md":
        return markdown_prose(text)
    if path.suffix == ".py":
        return python_prose(text)
    if path.suffix in (".sh", ".bash"):
        return shell_prose(text)
    return []


# ---------- Style rules ----------

BANNED = (
    (
        "HIST",
        "error",
        re.compile(
            r"\b(previously|formerly|historically|in the past|back then|"
            r"at the time|for months|turned out|went wrong|has since)\b"
            # `used to` narrates; `is used to` is the passive of "use".
            r"|(?<!is )(?<!are )(?<!was )(?<!were )(?<!be )(?<!been )(?<!being )\bused to\b"
            r"|이전에는|예전에|원래는|과거에|였다가|바뀌었",
            re.IGNORECASE,
        ),
        "history narration — state the rule in force, not how it got there",
    ),
    (
        "SHA",
        "error",
        SHA,
        "commit sha in prose — a squash merge can make it unreachable",
    ),
    (
        "PLAN",
        "error",
        re.compile(r"docs/superpowers/(plans|specs)/|^\s*[-*]\s*\[[ xX]\]\s"),
        "implementation-plan record — shipped prose carries the fact, not a pointer to it",
    ),
    (
        "FILLER",
        "error",
        re.compile(
            r"\b(just|really|basically|actually|simply|essentially|obviously|"
            r"in order to|make sure to|be sure to|needless to say|"
            r"it is worth noting|keep in mind|of course)\b"
            # Connectives only where they join sentences: `however small` is a
            # concession, `However,` is filler.
            r"|\b(however|furthermore|moreover|additionally|in addition)\s*,",
            re.IGNORECASE,
        ),
        "filler — drop it, the sentence keeps its meaning",
    ),
    (
        "ENDING",
        "error",
        re.compile(r"[가-힣]다[.]|[가-힣]다\s*$"),
        "`~다` ending — use a nominal ending",
    ),
)

# The one rule that reads link targets (see :func:`_mask`).
READS_LINK_TARGETS = ("PLAN",)


def lint_text(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    for lineno, raw in prose_of(path, text):
        if not raw.strip():
            continue
        line = _mask(raw)
        with_links = _mask(raw, keep_link_targets=True)
        for code, severity, pattern, message in BANNED:
            m = pattern.search(with_links if code in READS_LINK_TARGETS else line)
            if m:
                hit = m.group(0).strip() or line.strip()
                findings.append((severity, lineno, code, f"{message} — {hit!r}"))
        if len(line) > MAX_LINE and "|" not in line:
            findings.append(
                ("warning", lineno, "LONG", f"prose line is {len(line)} chars (cap {MAX_LINE})")
            )
    return findings


def lint_paths(paths: list[Path]) -> list[tuple[Path, list[Finding]]]:
    out = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        findings = lint_text(path, text)
        if findings:
            out.append((path, findings))
    return out


# ---------- Lossless verify ----------


def headings(text: str) -> list[tuple[str, str]]:
    found = (HEADING.match(line) for line in text.split("\n"))
    return [(m.group(1), m.group(2).strip()) for m in found if m]


def code_blocks(text: str) -> list[str]:
    """Fenced blocks, closing fence matched per CommonMark. Unclosed fences are skipped."""
    blocks: list[str] = []
    lines = text.split("\n")
    i = 0
    while i < len(lines):
        m = FENCE.match(lines[i])
        if not m:
            i += 1
            continue
        block = [lines[i]]
        i += 1
        closed = False
        while i < len(lines):
            close = FENCE.match(lines[i])
            block.append(lines[i])
            i += 1
            if close and _closes(m, close):
                closed = True
                break
        if closed:
            blocks.append("\n".join(block))
    return blocks


def inline_codes(text: str) -> Counter[str]:
    body = text
    for block in code_blocks(text):
        body = body.replace(block, "")
    return Counter(m.group(0) for m in INLINE_CODE.finditer(body))


def _docstring_starts(text: str) -> set[tuple[int, int]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    starts = set()
    for node in [tree] + list(ast.walk(tree)):
        if not isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            continue
        if ast.get_docstring(node, clean=False) is not None:
            expr = node.body[0]
            starts.add((expr.lineno, expr.col_offset))
    return starts


SKIP_TOKENS = frozenset(
    {
        tokenize.COMMENT,
        tokenize.NL,
        tokenize.NEWLINE,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.ENDMARKER,
    }
)


def _shell_code(line: str) -> str:
    """The line minus a trailing comment, quotes respected."""
    quote = ""
    for i, ch in enumerate(line):
        if quote:
            if ch == quote:
                quote = ""
        elif ch in "'\"":
            quote = ch
        elif ch == "#" and (i == 0 or line[i - 1].isspace()):
            return line[:i]
    return line


def strip_prose(path: Path, text: str) -> str:
    """The file's code with comments and docstrings gone — what a prose rewrite must not touch."""
    if path.suffix == ".py":
        skip = _docstring_starts(text)
        try:
            kept = [
                f"{tok.type}:{tok.string}"
                for tok in tokenize.generate_tokens(io.StringIO(text).readline)
                if tok.type not in SKIP_TOKENS
                and not (tok.type == tokenize.STRING and tok.start in skip)
            ]
        except (tokenize.TokenError, IndentationError):
            return text
        return "\n".join(kept)
    kept_lines = []
    for line in text.split("\n"):
        if line.strip().startswith("#") and not line.strip().startswith("#!"):
            continue
        code = _shell_code(line).rstrip()
        if code:
            kept_lines.append(code)
    return "\n".join(kept_lines)


def verify_markdown(before: str, after: str) -> list[Finding]:
    findings: list[Finding] = []
    h1, h2 = headings(before), headings(after)
    if len(h1) != len(h2):
        findings.append(("error", 0, "HEADING", f"heading count {len(h1)} -> {len(h2)}"))
    elif h1 != h2:
        findings.append(("warning", 0, "HEADING", "heading text or order changed"))
    if code_blocks(before) != code_blocks(after):
        findings.append(("error", 0, "CODE", "fenced code blocks not preserved exactly"))
    lost_urls = set(URL.findall(before)) - set(URL.findall(after))
    if lost_urls:
        findings.append(("error", 0, "URL", f"URLs lost: {sorted(lost_urls)}"))
    c1, c2 = inline_codes(before), inline_codes(after)
    lost_code = {k: n - c2[k] for k, n in c1.items() if c2[k] < n}
    if lost_code:
        findings.append(("error", 0, "INLINE", f"inline code lost: {sorted(lost_code)}"))
    b1 = len(BULLET.findall(before))
    b2 = len(BULLET.findall(after))
    if b1 and abs(b1 - b2) / b1 > 0.15:
        findings.append(("warning", 0, "BULLET", f"bullet count {b1} -> {b2}"))
    lost_paths = set(PATH_LIKE.findall(before)) - set(PATH_LIKE.findall(after))
    if lost_paths:
        findings.append(("warning", 0, "PATH", f"paths lost: {sorted(lost_paths)[:10]}"))
    return findings


def verify(path: Path, before: str, after: str) -> list[Finding]:
    if path.suffix == ".md":
        return verify_markdown(before, after)
    if strip_prose(path, before) != strip_prose(path, after):
        return [("error", 0, "CODE", "code changed — a prose rewrite must leave it byte-identical")]
    return []


DEFAULT_GLOBS = ("**/*.md",)
# Directory NAMES, matched at any depth. A vendored tree is never the repo's own prose, and
# these hold whatever a consumer's `paths` says — a glob would need every one of them
# spelled `**/node_modules/**` to reach as far.
NEVER_LINTED = frozenset({".git", "node_modules", ".venv", "vendor"})


def _segment_re(seg: str) -> str:
    """One path segment of a glob as regex source. ``*`` and ``?`` stay inside the segment."""
    out = []
    i = 0
    while i < len(seg):
        char = seg[i]
        if char == "*":
            out.append("[^/]*")
        elif char == "?":
            out.append("[^/]")
        elif char == "[":
            end = seg.find("]", i + 1)
            if end == -1:
                out.append(re.escape(char))
            else:
                # A backslash or a `[` inside the class has to reach the regex escaped —
                # a bare `[` there is legal but warns about a nested set.
                body = seg[i + 1 : end].replace("\\", "\\\\").replace("[", "\\[")
                body = ("^" + body[1:]) if body.startswith("!") else body
                out.append("[" + body + "]")
                i = end
        else:
            out.append(re.escape(char))
        i += 1
    return "".join(out)


@lru_cache(maxsize=512)
def _glob_re(pattern: str) -> re.Pattern:
    """A ``paths``/``exclude`` glob compiled to a regex over a root-relative posix path.

    ``*``/``?`` stop at ``/``; a whole-segment ``**`` spans any number of directories,
    including none, so ``docs/**/*.md`` covers ``docs/a.md`` as well as ``docs/x/b.md``;
    a trailing ``**`` is the whole subtree.

    This is the ONLY reader of a glob in this module — :func:`config_paths` walks the tree
    and asks the same question rather than handing the pattern to ``Path.glob``. Two
    readers is how the hook and CI came to disagree about a consumer's own ``paths``, and
    ``Path.glob`` cannot be the second one anyway: what a trailing ``**`` matches changed
    in 3.13, and it is case-insensitive on Windows and not on the Linux runner.

    A pattern that cannot compile raises ``ValueError`` — the CLI turns that into an exit
    code, the hook fails open on it, exactly as for a config that does not parse.
    """
    parts = pattern.split("/")
    out = []
    for at, seg in enumerate(parts):
        if seg == "**":
            out.append(".*" if at == len(parts) - 1 else "(?:[^/]+/)*")
        else:
            out.append(_segment_re(seg) + ("/" if at < len(parts) - 1 else ""))
    try:
        return re.compile("".join(out) + r"\Z")
    except re.error as exc:
        raise ValueError(f"doc_style glob {pattern!r} is not usable: {exc}")


def _match(rel: str, pattern: str) -> bool:
    """Whether the root-relative posix path `rel` matches a `paths`/`exclude` glob."""
    return bool(_glob_re(pattern).match(rel))


def scope_rules(root: Path) -> tuple[tuple[str, ...], tuple[str, ...]] | None:
    """(paths, exclude) from flow-config's ``doc_style`` block. None when absent or off.

    Absent config is the common case in a repo that never opted in, so it reads as "nothing
    to lint" rather than an error — CI stays green there without a second guard. A config
    that is PRESENT and malformed is the opposite case and raises: read as "off", one typo
    would take layer 3 down with no red job to say so. It is a plain ``ValueError`` and not
    a ``SystemExit`` so that the hook's ``except Exception`` still catches it — the CLI is
    where it becomes an exit code, the commit gate has to FAIL OPEN (Invariant #1).
    """
    try:
        text = config_path(root).read_text(encoding="utf-8")
    except OSError:
        return None
    import yaml

    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ValueError(f"flow-config.yaml does not parse — doc-style cannot run: {exc}")
    cfg = data.get("doc_style") if isinstance(data, dict) else None
    if not isinstance(cfg, dict) or not cfg.get("enable"):
        return None
    return tuple(cfg.get("paths") or DEFAULT_GLOBS), tuple(cfg.get("exclude") or ())


def in_scope(root: Path, paths: list[Path], fail_open: bool = True) -> list[Path]:
    """The subset of ``paths`` the config puts in scope. [] when it is absent or off.

    Both arms of the gate read their scope here, so a ``paths``/``exclude`` written for CI
    cannot be ignored by the hook, and the hook cannot warn about a file CI would never look
    at. ``fail_open`` is what separates them: a config or glob that does not parse reads as
    no scope for the commit gate (Invariant #1) and raises for the CLI, where a red job is
    the whole point.
    """
    try:
        rules = scope_rules(root)
        if rules is None:
            return []
        globs, excluded = rules
        for pattern in tuple(globs) + tuple(excluded):
            _glob_re(pattern)  # compile every pattern before any path is judged
    except ValueError:
        if fail_open:
            return []
        raise
    root_resolved = root.resolve()
    out = []
    for path in paths:
        try:
            rel = path.resolve().relative_to(root_resolved)
        except (ValueError, OSError):
            continue
        if not NEVER_LINTED.isdisjoint(rel.parts):
            continue
        posix = rel.as_posix()
        if any(_match(posix, rule) for rule in excluded):
            continue
        if any(_match(posix, glob) for glob in globs):
            out.append(path)
    return out


def config_paths(root: Path) -> list[Path]:
    """Every file in the repo the ``doc_style`` block puts in scope — the CI arm.

    Walks the tree and hands every file to the same :func:`in_scope` the hook uses, so the
    two arms answer from one function over one matcher. Handing the globs to ``Path.glob``
    instead is what let them disagree: it reads a trailing ``**`` differently across python
    versions (3.12 yields directories only, and CI pins 3.12) and matches case-insensitively
    on Windows. A malformed config or glob becomes the exit code here, where red is the point.
    """
    try:
        if scope_rules(root) is None:
            return []
        found = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in NEVER_LINTED]
            found += [Path(dirpath) / name for name in filenames]
        return sorted(in_scope(root, found, fail_open=False))
    except ValueError as exc:
        raise SystemExit(str(exc))


def git_head_text(root: Path, path: Path) -> str | None:
    try:
        rel = path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None  # outside the repo — no HEAD side to compare against
    try:
        out = subprocess.run(
            ["git", "show", f"HEAD:{rel}"],
            cwd=root,
            capture_output=True,
            check=False,
        )
    except OSError:
        return None
    return out.stdout.decode("utf-8", "replace") if out.returncode == 0 else None


# ---------- Reporting ----------


def report(items: list[tuple[Path, list[Finding]]], root: Path) -> int:
    errors = 0
    for path, findings in items:
        try:
            name = path.resolve().relative_to(root.resolve()).as_posix()
        except ValueError:
            name = str(path)
        for severity, lineno, code, message in findings:
            errors += severity == "error"
            where = f"{name}:{lineno}" if lineno else name
            print(f"{where}: {severity.upper()} {code}: {message}", file=sys.stderr)
    return errors


def main(argv: list[str] | None = None) -> int:
    force_utf8_io()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--lint", nargs="*", metavar="PATH")
    parser.add_argument("--verify", nargs=2, metavar=("BEFORE", "AFTER"))
    parser.add_argument("--verify-git", nargs="+", metavar="PATH")
    parser.add_argument("--lint-config", action="store_true")
    parser.add_argument("--root", default=None)
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else host_root()

    if args.verify:
        before, after = (Path(p) for p in args.verify)
        findings = verify(
            after, before.read_text(encoding="utf-8"), after.read_text(encoding="utf-8")
        )
        return 1 if report([(after, findings)], root) else 0

    if args.verify_git:
        items = []
        for raw in args.verify_git:
            path = Path(raw)
            before = git_head_text(root, path)
            if before is None:
                continue  # new file — nothing to lose
            items.append((path, verify(path, before, path.read_text(encoding="utf-8"))))
        return 1 if report(items, root) else 0

    paths = config_paths(root) if args.lint_config else [Path(p) for p in (args.lint or [])]
    return 1 if report(lint_paths(paths), root) else 0


if __name__ == "__main__":
    sys.exit(main())
