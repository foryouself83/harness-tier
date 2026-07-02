from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path

try:
    import yaml  # PyYAML (repo dependency)
except Exception:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

# The encoding defense comes from the shared SSOT (_harness_paths) (no duplicate definitions).
# harness_scaffold runs from the plugin location, so sibling import is the default; package (test)
# imports use scripts._harness_paths.
try:
    from _harness_paths import force_utf8_io
except ImportError:
    from scripts._harness_paths import force_utf8_io

VENDOR_DIRS = {
    ".git",
    "node_modules",
    ".venv",
    "venv",
    "__pycache__",
    "dist",
    "build",
    ".next",
    "target",
    "vendor",
    ".mypy_cache",
    ".pytest_cache",
    ".idea",
    ".vscode",
}
SOURCE_EXTS = {
    ".py",
    ".js",
    ".ts",
    ".jsx",
    ".tsx",
    ".go",
    ".rs",
    ".java",
    ".kt",
    ".rb",
    ".php",
    ".cs",
    ".cpp",
    ".c",
    ".swift",
    ".scala",
    ".vue",
    ".svelte",
}
# dependency key → framework label
FRAMEWORK_SIGNATURES = {
    "next": "next.js",
    "react": "react",
    "vue": "vue",
    "nuxt": "nuxt",
    "svelte": "svelte",
    "@angular/core": "angular",
    "express": "express",
    "nestjs": "nestjs",
    "@nestjs/core": "nestjs",
    "fastapi": "fastapi",
    "django": "django",
    "flask": "flask",
}


def _walk_files(root: Path) -> Iterator[Path]:
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in VENDOR_DIRS]
        for fn in filenames:
            yield Path(dirpath) / fn


def detect_state(root: Path) -> str:
    for f in _walk_files(root):
        if f.suffix in SOURCE_EXTS:
            return "brownfield"
    return "greenfield"


def _norm_version(spec: str) -> str:
    # "==0.118.0", "^15.0.1", ">=2,<3" → extract only the first numeric version (else the original)
    m = re.search(r"\d+(?:\.\d+)*", spec or "")
    return m.group(0) if m else (spec or "").strip()


def detect_frameworks(root: Path) -> list[dict]:
    out: list[dict] = []

    pkg = root / "package.json"
    if pkg.is_file():
        try:
            data = json.loads(pkg.read_text(encoding="utf-8"))
            deps = {}
            deps.update(data.get("dependencies", {}) or {})
            deps.update(data.get("devDependencies", {}) or {})
            for dep, ver in deps.items():
                label = FRAMEWORK_SIGNATURES.get(dep)
                if label:
                    out.append(
                        {
                            "name": label,
                            "version": _norm_version(str(ver)),
                            "manifest": "package.json",
                        }
                    )
        except Exception:
            pass

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        try:
            text = pyproject.read_text(encoding="utf-8")
            for dep, label in FRAMEWORK_SIGNATURES.items():
                esc = re.escape(dep)
                # PEP 621: dependencies = ["fastapi==0.118.0"]  (name inside the quotes)
                m = re.search(rf"['\"]{esc}\s*([=<>!~^]*\s*[\d.]+)?['\"]", text)
                if not m:
                    # Poetry: `fastapi = "^0.118.0"` in [tool.poetry.dependencies] (name is the key)
                    m = re.search(rf"(?m)^\s*{esc}\s*=\s*['\"]([^'\"]*)['\"]", text)
                if m:
                    out.append(
                        {
                            "name": label,
                            "version": _norm_version(m.group(1) or ""),
                            "manifest": "pyproject.toml",
                        }
                    )
        except Exception:
            pass

    reqs = root / "requirements.txt"
    if reqs.is_file():
        try:
            text = reqs.read_text(encoding="utf-8")
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                name_m = re.match(r"([A-Za-z0-9_.\-]+)", stripped)
                if not name_m:
                    continue
                label = FRAMEWORK_SIGNATURES.get(name_m.group(1).lower())
                if label:
                    ver_m = re.search(r"==\s*([\d.]+)", stripped)
                    out.append(
                        {
                            "name": label,
                            "version": ver_m.group(1) if ver_m else "",
                            "manifest": "requirements.txt",
                        }
                    )
        except Exception:
            pass

    gomod = root / "go.mod"
    if gomod.is_file():
        out.append({"name": "go", "version": "", "manifest": "go.mod"})

    # If multiple dependencies point to the same framework, dedup by name (keep first occurrence)
    deduped: list[dict] = []
    seen: set[str] = set()
    for item in out:
        if item["name"] not in seen:
            seen.add(item["name"])
            deduped.append(item)
    return deduped


def _parse_frontmatter(text: str) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if not m:
        return {}
    block = m.group(1)
    if yaml is not None:
        try:
            data = yaml.safe_load(block) or {}
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    # Fallback (yaml absent): parse name/description lines + collect block-scalar (>, |) multilines
    out: dict = {}
    lines = block.splitlines()
    i = 0
    while i < len(lines):
        mm = re.match(r"\s*(name|description)\s*:\s*(.*?)\s*$", lines[i])
        if not mm:
            i += 1
            continue
        key, val = mm.group(1), mm.group(2).strip()
        if val in (">", "|", ">-", "|-", ">+", "|+"):
            collected: list[str] = []
            i += 1
            while i < len(lines) and (not lines[i].strip() or lines[i][:1] in (" ", "\t")):
                collected.append(lines[i].strip())
                i += 1
            out[key] = " ".join(c for c in collected if c)
            continue
        out[key] = val.strip("'\"")
        i += 1
    return out


def _read_frontmatter(md_path: Path) -> dict:
    try:
        return _parse_frontmatter(md_path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _component_entry(md_path: Path) -> dict:
    fm = _read_frontmatter(md_path)
    return {
        "name": fm.get("name", ""),
        "description": fm.get("description", ""),
        "path": str(md_path),
    }


def scan_components(claude_dir: Path) -> dict:
    result: dict = {"skills": [], "commands": [], "agents": []}
    cmd_dir = claude_dir / "commands"
    if cmd_dir.is_dir():
        result["commands"] = [_component_entry(p) for p in sorted(cmd_dir.glob("*.md"))]
    agt_dir = claude_dir / "agents"
    if agt_dir.is_dir():
        result["agents"] = [_component_entry(p) for p in sorted(agt_dir.glob("*.md"))]
    skl_dir = claude_dir / "skills"
    if skl_dir.is_dir():
        result["skills"] = [_component_entry(p) for p in sorted(skl_dir.glob("*/SKILL.md"))]
    return result


def _marker_begin(marker_id: str) -> str:
    return f"<!-- {marker_id} BEGIN (managed by /harness-init — edits inside are overwritten) -->"


def _marker_end(marker_id: str) -> str:
    return f"<!-- {marker_id} END -->"


def upsert_marker_block(path: Path, marker_id: str, body: str) -> str:
    begin, end = _marker_begin(marker_id), _marker_end(marker_id)
    block = f"{begin}\n{body.rstrip()}\n{end}\n"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(block, encoding="utf-8")
        return "created"
    text = path.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(begin) + r".*?" + re.escape(end) + r"\n?", re.DOTALL)
    if pattern.search(text):
        new_text = pattern.sub(block, text, count=1)
        if new_text != text:
            path.write_text(new_text, encoding="utf-8")
        return "replaced"
    if begin in text:
        raise ValueError(
            f"corrupt managed block: '{marker_id}' has BEGIN without matching END in {path}"
        )
    sep = "" if text.endswith("\n") else "\n"
    path.write_text(text + sep + "\n" + block, encoding="utf-8")
    return "inserted"


REQUIRED_RULES = ("karpathy", "dry-constants", "version-pinning", "security", "reuse-first")
BASELINE_MARKER = "harness:baseline"
# Also recognize components in subdirectories (.+ — do not assume a single segment).
_SKILL_PATH_RE = re.compile(r"(?:^|/)\.claude/skills/.+/SKILL\.md$")
_AGENT_PATH_RE = re.compile(r"(?:^|/)\.claude/agents/.+\.md$")
# Inline markdown links only (exclude images ![..](..) — block '!' right before '[',
# allow title·whitespace padding).
_MD_LINK_RE = re.compile(
    r"(?<!!)\[[^\]]*\]\(\s*([^)\s#]+\.md)(?:#[^)\s]*)?(?:\s+[\"'][^\")]*[\"'])?\s*\)"
)
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`]+`")
_WIN_ABS_RE = re.compile(r"[a-zA-Z]:[\\/]")
OPS_ANCHOR_RE = re.compile(r"<!--\s*ops-conventions\s*-->")
OPS_MAX_LINES = 3


def _ops_directive_blocks(body: str) -> list[list[str]]:
    """Split the top-level list items (`- ...`) after the `<!-- ops-conventions -->` anchor.

    Each block = the `- ` line + the consecutive lines up to a blank line/next `- `/heading/next
    anchor. A heading or the next anchor is treated as the end of the section (input to the
    operations-directive line-count guard).
    """
    m = OPS_ANCHOR_RE.search(body)
    if not m:
        return []
    blocks: list[list[str]] = []
    cur: list[str] | None = None
    for line in body[m.end() :].splitlines():
        stripped = line.strip()
        if stripped.startswith("#") or OPS_ANCHOR_RE.search(line):
            break
        if line.startswith("- "):
            if cur is not None:
                blocks.append(cur)
            cur = [line]
        elif cur is not None:
            if stripped == "":
                blocks.append(cur)
                cur = None
            else:
                cur.append(line)
    if cur is not None:
        blocks.append(cur)
    return blocks


def _norm_rel(path: str) -> str:
    """Normalize a plan path to a POSIX canonical form (remove backslashes·dup separators·'./').

    Normalizing only one side makes path comparison mismatch, causing dead-link false
    positives·command-guard bypass.
    """
    if not path:
        return ""
    return os.path.normpath(path.replace("\\", "/")).replace("\\", "/")


def _is_component_path(rel: str) -> bool:
    return bool(_SKILL_PATH_RE.search(rel) or _AGENT_PATH_RE.search(rel))


def _has_rule_anchor(body: str, key: str) -> bool:
    """Detect a rule anchor, tolerant of HTML-comment whitespace variants (e.g. <!--rule:x-->)."""
    return re.search(rf"<!--\s*rule:{re.escape(key)}\s*-->", body) is not None


def _strip_frontmatter(text: str) -> str:
    """Return only the body with the frontmatter block removed (so link scans skip metadata)."""
    m = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
    return text[m.end() :] if m else text


def _strip_code(text: str) -> str:
    """Remove code fences·inline code (so link scans don't flag code examples as dead links)."""
    return _INLINE_CODE_RE.sub("", _CODE_FENCE_RE.sub("", text))


def validate_plan(root: Path, plan: dict) -> dict:
    """Deterministic structural validation of the plan. Diagnostic, not a gate (FAIL-OPEN)."""
    issues: list[dict] = []
    files = plan.get("files", [])
    # Paths are always normalized before comparison — normalizing one side only would mismatch.
    plan_paths = {_norm_rel(e.get("path", "")) for e in files}

    existing = scan_components(root / ".claude")
    existing_by_name: dict = {}  # name → root-relative canonical path of the existing file
    for grp in existing.values():
        for c in grp:
            nm2 = c.get("name")
            if not nm2:
                continue
            try:
                rp = _norm_rel(os.path.relpath(c["path"], root))
            except Exception:
                rp = ""
            existing_by_name.setdefault(nm2, rp)
    new_names: dict = {}  # name → canonical path within the plan

    for e in files:
        rel = _norm_rel(e.get("path", ""))
        content = e.get("content", "")

        if rel.startswith(".claude/commands/") or "/.claude/commands/" in rel:
            issues.append(
                {
                    "severity": "high",
                    "kind": "command",
                    "path": rel,
                    "detail": "harness는 커맨드를 생성하지 않는다",
                }
            )

        if _is_component_path(rel):
            fm = _parse_frontmatter(content)
            name_val = fm.get("name")
            if not name_val or not isinstance(name_val, str):
                issues.append(
                    {
                        "severity": "high",
                        "kind": "frontmatter",
                        "path": rel,
                        "detail": "name 누락/빈값",
                    }
                )
            desc_val = fm.get("description")
            if not desc_val or not isinstance(desc_val, str):
                issues.append(
                    {
                        "severity": "high",
                        "kind": "frontmatter",
                        "path": rel,
                        "detail": "description 누락/빈값",
                    }
                )
            # Ensure name is a string before comparison·hashing (a YAML list/dict was already
            # handled as missing above).
            nm = name_val if isinstance(name_val, str) else ""
            if nm:
                # Same name at a different path is a real duplicate. Same path is an update of an
                # existing file, so allowed.
                if nm in existing_by_name and existing_by_name[nm] != rel:
                    issues.append(
                        {
                            "severity": "high",
                            "kind": "dedup",
                            "path": rel,
                            "detail": f"기존 컴포넌트와 name 충돌: {nm}",
                        }
                    )
                if nm in new_names and new_names[nm] != rel:
                    issues.append(
                        {
                            "severity": "high",
                            "kind": "dedup",
                            "path": rel,
                            "detail": f"plan 내 name 중복: {nm}",
                        }
                    )
                new_names.setdefault(nm, rel)

        # Link scanning covers only the body (excludes frontmatter·code·images; paths outside
        # root are out of scope).
        for link in _MD_LINK_RE.findall(_strip_code(_strip_frontmatter(content))):
            if link.startswith(("http://", "https://", "/")) or _WIN_ABS_RE.match(link):
                continue
            target = _norm_rel(str(Path(rel).parent / link))
            if target.startswith(".."):
                continue
            if target in plan_paths or (root / target).exists():
                continue
            issues.append(
                {
                    "severity": "warn",
                    "kind": "dead-link",
                    "path": rel,
                    "detail": f"링크 대상 없음: {link}",
                }
            )

        for blk in _ops_directive_blocks(content):
            non_empty = [ln for ln in blk if ln.strip()]
            if len(non_empty) > OPS_MAX_LINES:
                issues.append(
                    {
                        "severity": "high",
                        "kind": "ops-line-limit",
                        "path": rel,
                        "detail": (
                            f"운영 directive 가 {len(non_empty)}줄 — "
                            f"항목당 ≤{OPS_MAX_LINES}줄 (살은 docs/code-style 로)"
                        ),
                    }
                )

        if e.get("action") == "marker_upsert":
            mid = e.get("marker_id", "")
            # If a marker line is embedded in plan content (a whole-template copy), apply
            # re-wraps it and nests.
            if mid and (_marker_begin(mid) in content or _marker_end(mid) in content):
                issues.append(
                    {
                        "severity": "high",
                        "kind": "marker",
                        "path": rel,
                        "detail": "content 에 마커 BEGIN/END 포함 — body 만 넣어야 함(중첩 방지)",
                    }
                )
            target_file = root / rel
            if target_file.exists():
                try:
                    # Even an existing file on a cp949 host must have its marker (ASCII) read,
                    # hence errors='replace'.
                    txt = target_file.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    txt = ""
                if mid and _marker_begin(mid) in txt and _marker_end(mid) not in txt:
                    issues.append(
                        {
                            "severity": "high",
                            "kind": "marker",
                            "path": rel,
                            "detail": "BEGIN without END (corrupt)",
                        }
                    )

    baseline = next(
        (
            e
            for e in files
            if e.get("action") == "marker_upsert" and e.get("marker_id") == BASELINE_MARKER
        ),
        None,
    )
    if baseline is None:
        issues.append(
            {
                "severity": "high",
                "kind": "rule-load",
                "path": "CLAUDE.md",
                "detail": f"{BASELINE_MARKER} 마커블록 없음",
            }
        )
    else:
        body = baseline.get("content", "")
        for key in REQUIRED_RULES:
            if not _has_rule_anchor(body, key):
                issues.append(
                    {
                        "severity": "high",
                        "kind": "rule-load",
                        "path": baseline.get("path", "CLAUDE.md"),
                        "detail": f"필수 룰 anchor 누락: {key}",
                    }
                )

    return {"ok": not any(i["severity"] == "high" for i in issues), "issues": issues}


def apply_plan(root: Path, plan: dict) -> dict:
    report = {"created": [], "skipped": [], "updated": [], "conflicts": []}
    for entry in plan.get("files", []):
        rel = entry["path"]
        target = root / rel
        action = entry.get("action", "create")
        if action == "marker_upsert":
            upsert_marker_block(target, entry["marker_id"], entry.get("content", ""))
            report["updated"].append(rel)
        elif action == "create":
            if target.exists():
                report["conflicts"].append(rel)  # no overwrite
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(entry.get("content", ""), encoding="utf-8")
            report["created"].append(rel)
        else:
            report["skipped"].append(rel)
    return report


# Audit evidence never deleted when cleaning up incorporated intermediate copies (host-excluded).
CLEANUP_PRESERVE = ("plan.json", "manifest.json", "critic-report.json", "rationale.md")


def cleanup_harness(harness_dir: Path, root: Path | None = None) -> dict:
    """After apply, remove the intermediate copies (research/) that were incorporated into docs.

    Link guard (FAIL-SAFE): if root is given, scan the .md files under docs/ and, if any link
    references ".harness/research", withhold removal and record it in link_warnings (to prevent
    broken links from missed incorporation). Audit/re-run evidence (CLEANUP_PRESERVE) is always
    preserved, and files other than research/ and the preserve list are left untouched.
    """
    report: dict = {"removed": [], "preserved": [], "link_warnings": []}
    research_dir = harness_dir / "research"

    if root is not None:
        docs_dir = root / "docs"
        if docs_dir.is_dir():
            for md in sorted(docs_dir.rglob("*.md")):
                try:
                    text = md.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                if ".harness/research" in text:
                    report["link_warnings"].append(str(md.relative_to(root)).replace("\\", "/"))

    if research_dir.is_dir() and not report["link_warnings"]:
        for f in sorted(research_dir.rglob("*"), reverse=True):
            try:
                if f.is_file():
                    f.unlink()
                    report["removed"].append(str(f.relative_to(harness_dir)).replace("\\", "/"))
                elif f.is_dir():
                    f.rmdir()
            except OSError:
                pass  # FAIL-OPEN: cleanup is auxiliary; failure must not block the flow
        try:
            research_dir.rmdir()
        except OSError:
            pass

    report["preserved"] = [n for n in CLEANUP_PRESERVE if (harness_dir / n).exists()]
    return report


def _detect_payload(root: Path) -> dict:
    return {
        "state": detect_state(root),
        "frameworks": detect_frameworks(root),
        "existing": scan_components(root / ".claude"),
    }


def main(argv: list[str]) -> int:
    force_utf8_io()
    parser = argparse.ArgumentParser(prog="harness_scaffold")
    sub = parser.add_subparsers(dest="cmd", required=True)
    d = sub.add_parser("detect")
    d.add_argument("--root", default=".")
    a = sub.add_parser("apply")
    a.add_argument("--root", default=".")
    a.add_argument("--plan", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--root", default=".")
    v.add_argument("--plan", required=True)
    c = sub.add_parser("cleanup")
    c.add_argument("--root", default=".")
    args = parser.parse_args(argv)
    root = Path(args.root)
    if args.cmd == "detect":
        print(json.dumps(_detect_payload(root), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "apply":
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        print(json.dumps(apply_plan(root, plan), ensure_ascii=False, indent=2))
        return 0
    if args.cmd == "validate":
        plan = json.loads(Path(args.plan).read_text(encoding="utf-8"))
        print(json.dumps(validate_plan(root, plan), ensure_ascii=False, indent=2))
        return 0  # FAIL-OPEN: diagnostic, not a gate
    if args.cmd == "cleanup":
        harness_dir = root / ".claude" / "harness-tier" / ".harness"
        print(json.dumps(cleanup_harness(harness_dir, root), ensure_ascii=False, indent=2))
        return 0
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
