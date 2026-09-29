"""Render a host's Claude Code instructions into one managed block of its root AGENTS.md.

Codex loads AGENTS.md only from the session's directory and its ancestors, never `.claude/rules/`
or a subdirectory's CLAUDE.md, so the root file carries the rules and points at the rest. Claude
Code reads AGENTS.md itself only when no root CLAUDE.md exists; there the rendered rules repeat
`.claude/rules/` for it, which is accepted. Runs in the host on the gate's Python floor (3.8).
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

TARGET = "AGENTS.md"
# harness.instructions.ROOT_FILES, restated for `_shared_source` (a test pins the two).
ROOT_SOURCES = ("CLAUDE.md", ".claude/CLAUDE.md")
OVERRIDE = "AGENTS.override.md"
_TAG = "<!-- harness-tier:codex-instructions"
# A source quoting a marker gets this visible escape, so the block never holds a marker line.
_TAG_ESCAPED = "<!- - harness-tier:codex-instructions"
_BEGIN_PREFIX = f"{_TAG} BEGIN"
BEGIN = f"{_BEGIN_PREFIX} — generated; edit CLAUDE.md or .claude/rules -->"
END = f"{_TAG} END -->"
# Codex's default `project_doc_max_bytes`; past it the file is truncated without a word.
MAX_BYTES = 32768


class MissingModule(Exception):
    """A module the renderer imports is not installed in this Python."""


def _import(sibling: str, packaged: str):
    """`sibling` as the host copy sees it, else the in-repo package path — and a module those
    two import that is itself missing (PyYAML) is named instead of the fallback's miss."""
    import importlib

    def own(name: str | None, path: str) -> bool:
        return name is not None and (path == name or path.startswith(name + "."))

    try:
        return importlib.import_module(sibling)
    except ModuleNotFoundError as exc:
        if not own(exc.name, sibling):
            raise MissingModule(exc.name) from exc
    try:
        return importlib.import_module(packaged)
    except ModuleNotFoundError as exc:
        if not own(exc.name, packaged):
            raise MissingModule(exc.name) from exc
        raise


def _missing(exc: MissingModule) -> str:
    name = "PyYAML" if exc.args[0] == "yaml" else exc.args[0]
    return f"{name} 가 이 python3 에 없습니다 — 설치한 뒤 다시 실행하세요"


def _model():
    return _import("harness.instructions", "scripts.harness.instructions")


def _collect(host: Path, keep: set):
    model = _model()
    try:
        return model.collect(host, keep_imports=keep)
    except ModuleNotFoundError as exc:
        raise MissingModule(exc.name) from exc


def _source_rels(host: Path) -> list[str]:
    """Every Claude source's repo-relative path, listed without reading or parsing any."""
    root = host.resolve()
    return [path.relative_to(root).as_posix() for _, path in _model().sources(root)]


def _rule_index(doc) -> str:
    if doc.paths:
        return f"Before editing files matching `{', '.join(doc.paths)}`, read `{doc.source}`."
    return f"Before editing any file, read `{doc.source}`."


def _rule_section(doc) -> str:
    applies = ", ".join(doc.paths) if doc.paths else "all files"
    head = f"### Rule: {doc.source}\nApplies to: {applies}"
    body = doc.body.strip("\n")
    return f"{head}\n\n{body}" if body else head


def _block(docs, rule_bodies: bool) -> str:
    rules = [d for d in docs if d.kind == "rule"]
    modules = [d for d in docs if d.kind == "module"]
    sections = [d.body.strip("\n") for d in docs if d.kind == "root"]
    if rule_bodies:
        sections.extend(_rule_section(d) for d in rules)
    elif rules:
        sections.append("### Rules\n" + "\n".join(_rule_index(d) for d in rules))
    if modules:
        lines = [f"Before working under `{d.scope_dir}/`, read `{d.source}`." for d in modules]
        sections.append("### Directory instructions\n" + "\n".join(lines))
    inner = "\n\n".join(s for s in sections if s).replace(_TAG, _TAG_ESCAPED)
    return "\n".join([BEGIN, inner, END])


def _spans(text: str) -> list[tuple[int, int]]:
    """Every managed block, END's line break included, in file order.

    A BEGIN line is recognized by `_BEGIN_PREFIX`, not its full wording, so a block written under
    an earlier wording is still found and replaced rather than orphaned beside a new one.
    """
    pos, start, found = 0, None, []
    for line in text.split("\n"):
        nxt = min(pos + len(line) + 1, len(text))
        bare = line[:-1] if line.endswith("\r") else line
        if start is None and bare.startswith(_BEGIN_PREFIX):
            start = pos
        elif start is not None and bare == END:
            found.append((start, nxt))
            start = None
        pos = nxt
    if start is not None:
        raise ValueError(f"{TARGET} 에 Codex 지침 블록의 END 표식이 없습니다")
    return found


def _without(text: str, span: tuple[int, int], nl: str) -> str:
    before, after = text[: span[0]], text[span[1] :]
    if not after and before.endswith(nl * 2):
        before = before[: -len(nl)]
    return before + after


def _compose(existing: str, block: str | None) -> str:
    """`existing` with its first block replaced (or the block appended) and every further block
    dropped; with `block` None, every block dropped. Dropped last-first, so each one's
    separating blank line goes with it."""
    nl = "\r\n" if "\r\n" in existing else "\n"
    spans = _spans(existing)
    for span in reversed(spans if block is None else spans[1:]):
        existing = _without(existing, span, nl)
    if block is None:
        return existing
    rendered = block.replace("\n", nl) + nl
    if spans:
        return existing[: spans[0][0]] + rendered + existing[spans[0][1] :]
    if not existing:
        return rendered
    return existing + (nl if existing.endswith("\n") else nl * 2) + rendered


def _size(text: str) -> int:
    return len(text.encode("utf-8"))


def _collect_docs(host: Path):
    """Every Claude source, parsed. A source that cannot be read or decoded raises here, into the
    caller's one error boundary."""
    return _collect(host, {host / TARGET})


def _plan(host: Path, docs) -> tuple[str | None, str | None, list[str]]:
    """(current text, desired text, notes); None text means the file does not exist. `docs` is
    `_collect_docs(host)`."""
    path = host / TARGET
    current = path.read_bytes().decode("utf-8") if path.is_file() else None
    if not docs:
        if current is None or not _spans(current):
            return current, current, []
        desired = _compose(current, None)
        return current, (desired if desired.strip() else None), []
    desired = _compose(current or "", _block(docs, rule_bodies=True))
    if _size(desired) > MAX_BYTES:
        desired = _compose(current or "", _block(docs, rule_bodies=False))
    notes = []
    if _size(desired) > MAX_BYTES:
        notes.append(
            f"  [!] {TARGET} 가 {_size(desired)} bytes 로 Codex 한도 {MAX_BYTES} bytes 를 넘습니다"
            " — 넘친 부분은 Codex 가 읽지 않으니 CLAUDE.md 를 줄이세요"
        )
    if (host / OVERRIDE).is_file():
        notes.append(f"  [!] {OVERRIDE} 가 있어 Codex 는 {TARGET} 를 읽지 않습니다")
    return current, desired, notes


def _shared_source(host: Path) -> str | None:
    """The root source AGENTS.md is the same file as (a link either way, or a hard link), if any.
    Such a host already gives Codex the Claude text, and any write would land inside it."""
    path = host / TARGET
    target = os.path.normcase(os.path.realpath(path))
    for rel in ROOT_SOURCES:
        source = host / rel
        try:
            if os.path.normcase(os.path.realpath(source)) == target:
                return rel
            if path.exists() and source.exists() and os.path.samefile(path, source):
                return rel
        except OSError:
            continue
    return None


def _shared_note(rel: str) -> str:
    return (
        f"  [!] {TARGET} 가 {rel} 와 같은 파일입니다 — Codex 가 그 내용을 이미 읽으므로"
        " 렌더하지 않습니다"
    )


def _is_multiply_linked(path: Path) -> bool:
    """AGENTS.md is a symlink (even a dangling one — its target need not exist), or shares its
    inode with another directory entry (a hard link). `_shared_source` above only recognizes
    that other entry when it is one of `ROOT_SOURCES`; a rule file or a module `CLAUDE.md`
    linked in instead is caught here, without needing to know every Claude source by name."""
    if path.is_symlink():
        return True
    try:
        return path.stat().st_nlink > 1
    except OSError:
        return False


def _linked_note() -> str:
    return (
        f"  [!] {TARGET} 가 다른 파일과 연결되어 있습니다(symlink 또는 hard link) — Claude 산출물"
        "일 수 있어 그 파일을 통해 쓰지 않습니다"
    )


def _reverse_shared_source(host: Path, rels: list[str]) -> str | None:
    """Which of `rels` (a rule under `.claude/rules/`, a module `CLAUDE.md`, or a root file) is
    itself a link resolving to AGENTS.md — the reverse of `_shared_source`'s direction, where
    AGENTS.md is the one doing the linking. Writing AGENTS.md's own bytes would land inside that
    source too, since underneath they are the same file. `ROOT_SOURCES` already covers the two
    root files via `_shared_source`; this checks every collected source instead, since a rule
    file or a module `CLAUDE.md` can point at AGENTS.md exactly as easily. It compares file
    identity only, so `rels` comes from `_source_rels` — no source is read, and neither a missing
    PyYAML nor an undecodable source stops it.
    """
    path = host / TARGET
    target = os.path.normcase(os.path.realpath(path))
    for rel in rels:
        source = host / rel
        try:
            if os.path.normcase(os.path.realpath(source)) == target:
                return rel
            if path.exists() and source.exists() and os.path.samefile(path, source):
                return rel
        except OSError:
            continue
    return None


def _reverse_shared_note(rel: str) -> str:
    return (
        f"  [!] {rel} 가 {TARGET} 와 같은 파일입니다 — 쓰면 그 Claude 산출물도 함께 바뀌므로"
        " 렌더하지 않습니다"
    )


def render(host: Path) -> list[str]:
    path = host / TARGET
    shared = _shared_source(host)
    if shared:
        return [_shared_note(shared)]
    if _is_multiply_linked(path):
        return [_linked_note()]
    try:
        reverse = _reverse_shared_source(host, _source_rels(host))
        if reverse:
            return [_reverse_shared_note(reverse)]
        current, desired, notes = _plan(host, _collect_docs(host))
        if desired == current:
            return [f"  [=] {TARGET} Codex 지침 블록 최신", *notes]
        if desired is None:
            path.unlink()
            return [f"  [-] {TARGET} 삭제(렌더할 지침 없음)", *notes]
        path.write_bytes(desired.encode("utf-8"))
    except MissingModule as exc:
        return [f"  [!] {TARGET} 렌더 불가: {_missing(exc)}"]
    except (OSError, ValueError) as exc:
        return [f"  [!] {TARGET} 렌더 실패({exc}) — 수동 확인 필요"]
    return [f"  [+] {TARGET} Codex 지침 블록 갱신", *notes]


def check(host: Path) -> tuple[bool, str]:
    """(True, "") when AGENTS.md already holds what `render` would write; writes nothing.

    (True, note) when AGENTS.md is not this renderer's to manage at all — shared with a root
    Claude source (either link direction, or a hard link), or itself a symlink/hard link into
    something else. That is not drift `render` could ever fix, so it is not a failure either:
    `--check` still exits 0, and the CLI relays `note` (the render `[!]` line) on stderr instead
    of leaving the caller to poll a check that would otherwise fail on this file forever.
    """
    shared = _shared_source(host)
    if shared:
        return True, _shared_note(shared)
    if _is_multiply_linked(host / TARGET):
        return True, _linked_note()
    try:
        reverse = _reverse_shared_source(host, _source_rels(host))
        if reverse:
            return True, _reverse_shared_note(reverse)
        current, desired, _ = _plan(host, _collect_docs(host))
    except MissingModule as exc:
        return False, f"{TARGET} 점검 불가: {_missing(exc)}"
    except (OSError, ValueError) as exc:
        return False, f"{TARGET} 점검 실패({exc})"
    if desired == current:
        return True, ""
    return False, (
        f"{TARGET} 의 Codex 지침 블록이 CLAUDE.md·.claude/rules 와 다릅니다 — render 를 실행하세요"
    )


def remove(host: Path) -> str:
    path = host / TARGET
    if not path.is_file():
        return f"  [=] {TARGET} 없음"
    shared = _shared_source(host)
    if shared:
        return f"  [=] {TARGET} 가 {shared} 와 같은 파일 — 건드리지 않음 (skip)"
    if _is_multiply_linked(path):
        return f"  [=] {TARGET} 가 다른 파일과 연결되어 있어 건드리지 않음 (skip)"
    try:
        reverse = _reverse_shared_source(host, _source_rels(host))
        verified = True
    except (MissingModule, OSError, ValueError):
        # Removal reads only AGENTS.md's own bytes, so sources that cannot be listed do not
        # stop it. It does leave unknown whether a source links to AGENTS.md, so the file is
        # kept even when emptied: deleting it would dangle such a link.
        reverse, verified = None, False
    if reverse:
        return f"  [=] {reverse} 가 {TARGET} 와 같은 파일 — 건드리지 않음 (skip)"
    try:
        text = path.read_bytes().decode("utf-8")
        if not _spans(text):
            return f"  [=] {TARGET} 에 Codex 지침 블록 없음"
        remaining = _compose(text, None)
        if not remaining.strip() and verified:
            path.unlink()
            return f"  [-] {TARGET} 삭제(Codex 지침 블록만 있었음)"
        path.write_bytes(remaining.encode("utf-8"))
    except (OSError, ValueError) as exc:
        return f"  [!] {TARGET} 블록 제거 실패({exc}) — 수동 확인 필요"
    if not verified:
        return f"  [-] {TARGET} Codex 지침 블록 제거(원본을 다 읽지 못해 파일은 남김)"
    return f"  [-] {TARGET} Codex 지침 블록 제거"


def main(argv: list[str]) -> int:
    paths = _import("_harness_paths", "scripts._harness_paths")
    paths.force_utf8_io()
    parser = argparse.ArgumentParser(description="CLAUDE.md·.claude/rules → AGENTS.md (Codex)")
    sub = parser.add_subparsers(dest="cmd", required=True)
    render_cmd = sub.add_parser("render", help="블록 갱신")
    render_cmd.add_argument("--check", action="store_true", help="다르면 exit 1, 쓰지 않음")
    remove_cmd = sub.add_parser("remove", help="블록 삭제")
    for cmd in (render_cmd, remove_cmd):
        cmd.add_argument("--host", help="호스트 루트(기본: 현재 저장소)")
    args = parser.parse_args(argv)
    host = Path(args.host) if args.host else paths.host_root()
    if args.cmd == "remove":
        print(remove(host))
        return 0
    if args.check:
        ok, reason = check(host)
        if reason:
            # A real drift is reported on stdout (the CLI's one line of actionable output); a
            # not-managed note (`ok` already True — nothing this renderer could fix) goes to
            # stderr instead, so `--check` still exits 0 without staying silent about why.
            print(reason, file=sys.stderr if ok else sys.stdout)
        return 0 if ok else 1
    for line in render(host):
        print(line)
    return 0


if __name__ == "__main__":
    # Only here, never at import time: this file's own directory is sys.path[0], and the
    # harness package and _harness_paths sit two levels up.
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    raise SystemExit(main(sys.argv[1:]))
