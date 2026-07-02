from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Iterator
from pathlib import Path

try:
    import yaml  # PyYAML (repo 의존성)
except Exception:  # pragma: no cover
    yaml = None  # type: ignore[assignment]

# 인코딩 방어는 공용 SSOT(_vway_paths)에서 가져온다(중복 정의 금지). harness_scaffold 는
# 플러그인 위치에서 실행되므로 형제 import 가 기본이고, 패키지(테스트)에서는 scripts._vway_paths.
try:
    from _vway_paths import force_utf8_io
except ImportError:
    from scripts._vway_paths import force_utf8_io

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
# 의존성 키 → 프레임워크 라벨
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
    # "==0.118.0", "^15.0.1", ">=2,<3" → 첫 숫자 버전만 추출(없으면 원문)
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
                # PEP 621: dependencies = ["fastapi==0.118.0"]  (이름이 따옴표 안)
                m = re.search(rf"['\"]{esc}\s*([=<>!~^]*\s*[\d.]+)?['\"]", text)
                if not m:
                    # Poetry: [tool.poetry.dependencies] 의 `fastapi = "^0.118.0"` (이름이 키)
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

    # 같은 프레임워크를 가리키는 의존성이 둘 이상이면 name 기준 dedup(첫 등장 유지)
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
    # 폴백(yaml 부재): name/description 라인 파싱 + 블록 스칼라(>, |) 멀티라인 수집
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
# 하위 디렉터리 컴포넌트도 인식한다(.+ — 단일 세그먼트 가정 금지).
_SKILL_PATH_RE = re.compile(r"(?:^|/)\.claude/skills/.+/SKILL\.md$")
_AGENT_PATH_RE = re.compile(r"(?:^|/)\.claude/agents/.+\.md$")
# 인라인 마크다운 링크만(이미지 ![..](..) 제외 — '[' 직전 '!' 차단, 타이틀·공백 패딩 허용).
_MD_LINK_RE = re.compile(
    r"(?<!!)\[[^\]]*\]\(\s*([^)\s#]+\.md)(?:#[^)\s]*)?(?:\s+[\"'][^\")]*[\"'])?\s*\)"
)
_CODE_FENCE_RE = re.compile(r"```.*?```", re.DOTALL)
_INLINE_CODE_RE = re.compile(r"`[^`]+`")
_WIN_ABS_RE = re.compile(r"[a-zA-Z]:[\\/]")
OPS_ANCHOR_RE = re.compile(r"<!--\s*ops-conventions\s*-->")
OPS_MAX_LINES = 3


def _ops_directive_blocks(body: str) -> list[list[str]]:
    """`<!-- ops-conventions -->` 앵커 뒤의 최상위 리스트 항목(`- ...`)을 블록으로 나눈다.

    각 블록 = `- ` 줄 + 빈 줄/다음 `- `/헤딩/다음 앵커 전까지의 연속 줄. 헤딩이나 다음
    앵커를 만나면 절이 끝난 것으로 본다(운영 directive 라인 수 가드의 입력).
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
    """plan 경로를 POSIX 정규형으로 통일(백슬래시·중복 구분자·'./' 제거).

    한쪽만 정규화하면 경로 비교가 어긋나 dead-link 오탐·커맨드 가드 우회가 난다.
    """
    if not path:
        return ""
    return os.path.normpath(path.replace("\\", "/")).replace("\\", "/")


def _is_component_path(rel: str) -> bool:
    return bool(_SKILL_PATH_RE.search(rel) or _AGENT_PATH_RE.search(rel))


def _has_rule_anchor(body: str, key: str) -> bool:
    """룰 앵커 검출 — HTML 주석 공백 변형(<!--rule:x-->, <!-- rule:x  -->)에 관대."""
    return re.search(rf"<!--\s*rule:{re.escape(key)}\s*-->", body) is not None


def _strip_frontmatter(text: str) -> str:
    """frontmatter 블록을 제거한 본문만 반환(링크 스캔이 메타데이터를 건드리지 않게)."""
    m = re.match(r"^---\s*\n.*?\n---\s*\n", text, re.DOTALL)
    return text[m.end() :] if m else text


def _strip_code(text: str) -> str:
    """코드 펜스·인라인 코드를 제거(링크 스캔이 코드 예시를 dead-link 로 오탐하지 않게)."""
    return _INLINE_CODE_RE.sub("", _CODE_FENCE_RE.sub("", text))


def validate_plan(root: Path, plan: dict) -> dict:
    """생성 plan 의 결정적 구조 검증. 게이트가 아니라 진단(FAIL-OPEN)."""
    issues: list[dict] = []
    files = plan.get("files", [])
    # 경로는 비교 전 항상 정규화한다 — 한쪽만 정규화하면 매칭이 어긋난다.
    plan_paths = {_norm_rel(e.get("path", "")) for e in files}

    existing = scan_components(root / ".claude")
    existing_by_name: dict = {}  # name → 기존 파일의 root-상대 정규경로
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
    new_names: dict = {}  # name → plan 내 정규경로

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
            # name 은 비교·해싱 전 문자열로 보장(YAML 리스트/딕트면 위에서 이미 누락 처리).
            nm = name_val if isinstance(name_val, str) else ""
            if nm:
                # 같은 name 이 다른 경로면 진짜 중복. 같은 경로면 기존 파일 갱신이므로 허용.
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

        # 링크 스캔은 본문만(frontmatter·코드·이미지 제외, root 밖 경로는 검증 범위 밖).
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
            # plan content 에 마커 라인이 박혀 있으면(템플릿 통째 복사) apply 가 재래핑해 중첩된다.
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
                    # cp949 호스트의 기존 파일도 마커(ASCII)는 읽혀야 한다 → errors='replace'.
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
                report["conflicts"].append(rel)  # 덮어쓰기 금지
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(entry.get("content", ""), encoding="utf-8")
            report["created"].append(rel)
        else:
            report["skipped"].append(rel)
    return report


# 편입 완료된 중간 사본을 정리할 때 절대 지우지 않는 감사용 증거(호스트로 복사되지 않음).
CLEANUP_PRESERVE = ("plan.json", "manifest.json", "critic-report.json", "rationale.md")


def cleanup_harness(harness_dir: Path, root: Path | None = None) -> dict:
    """apply 후 docs로 편입된 중간 사본(research/)을 제거한다.

    링크 가드(FAIL-SAFE): root가 주어지면 docs/ 의 .md 를 스캔해 ".harness/research" 를
    참조하는 링크가 있으면 제거를 보류하고 link_warnings 에 기록한다(편입 누락으로 링크가
    깨질 상황 방지). 감사/재실행용 증거(CLEANUP_PRESERVE)는 항상 보존하고, research/ 와 보존
    목록 외의 파일은 보수적으로 건드리지 않는다.
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
                pass  # FAIL-OPEN: 정리는 부가작업, 실패해도 흐름을 막지 않는다
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
        return 0  # FAIL-OPEN: 진단이지 게이트가 아님
    if args.cmd == "cleanup":
        harness_dir = root / ".claude" / "vway-kit" / ".harness"
        print(json.dumps(cleanup_harness(harness_dir, root), ensure_ascii=False, indent=2))
        return 0
    return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
