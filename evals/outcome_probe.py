"""Probe: can flow's classified tier be captured deterministically from a headless
session, and does it match the golden_tier? Standalone — the scored path never imports it."""

import argparse
import contextlib
import json
import re
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent

# The Phase-1 line /flow prints before any interactive gate (flow/SKILL.md, risk-tiers.md).
_TIER_RE = re.compile(r"(?im)^\s*-\s*Tier:\s*(\w+)")


def parse_stream_tier(text: str) -> str | None:
    """The tier from /flow's '## Tier Classification' block, lower-cased. Last match wins
    (a reclassification supersedes), None if the block never appeared."""
    chunks = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            event = json.loads(line)
        except json.JSONDecodeError:
            continue
        if event.get("type") == "assistant":
            for block in event.get("message", {}).get("content", []):
                if block.get("type") == "text":
                    chunks.append(block.get("text", ""))
    matches = _TIER_RE.findall("\n".join(chunks))
    return matches[-1].lower() if matches else None


def read_marker_tier(workdir: Path) -> str | None:
    """The tier from /flow's marker file (written only if Phase 2 completed), or None.
    `workdir` is the session's CWD: the temp dir for a fixture-less case, and the directory
    `build()` made inside it for a case that names one — the marker lands beneath whichever
    the session ran in."""
    marker = Path(workdir) / ".claude" / "harness-tier" / ".flow" / "tier"
    if not marker.exists():
        return None
    tier = marker.read_text(encoding="utf-8").strip().split(":", 1)[0].lower()
    return tier or None


def golden_cases() -> list[tuple[str, str, str | None]]:
    """flow's happy prompts carrying a golden_tier — (prompt, golden_tier, fixture).

    A prompt whose tier depends on an unspecified diff carries no golden and is skipped. The
    fixture travels with the case: measured without it, a prompt that presumes a state its
    directory does not have answers something else, which is not the router's classification."""
    data = yaml.safe_load((REPO / "evals/cases.yaml").read_text(encoding="utf-8"))
    entry = data["skills"]["flow"]
    out = []
    for case in entry["happy"]:
        if isinstance(case, dict) and case.get("golden_tier"):
            # Case first, then the skill-level default — the same order run.cases_for applies.
            # Read the case alone and a skill-level fixture would build for the scored run and
            # not for this one, measuring the router against a directory the score never saw.
            fixture = case.get("fixture") or entry.get("fixture")
            out.append((case["prompt"], case["golden_tier"], fixture))
    return out


def _probe_one(prompt: str, golden: str, fixture: str | None, config_dir: Path) -> dict:
    """One session; capture the tier two ways. Lazy import keeps run's subprocess machinery
    off the import path of the pure-function tests."""
    from evals import run, stream

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        wd = Path(tmp)
        text, _err = run._claude_stream(prompt, fixture, wd, config_dir, False)
        # _claude_stream builds a fixture into <tmp>/<scenario> and runs there, so the marker
        # lands one level down. Reading <tmp> instead would report every fixture-backed case
        # as "no marker", which is what a capture rate is for.
        wd = wd / fixture if fixture else wd
        return {
            "prompt": prompt,
            "golden": golden,
            "fired": "flow" in stream.observe(text).fired,
            "stream_tier": parse_stream_tier(text),
            "marker_tier": read_marker_tier(wd),  # read before the tempdir is cleaned
        }


def _report(rows: list[dict]) -> None:
    print(f"\n{'prompt':40} {'golden':8} {'fired':6} {'stream':8} {'marker':8} match")
    for r in rows:
        m = "-" if not r["fired"] else ("ok" if r["stream_tier"] == r["golden"] else "MISS")
        print(
            f"{r['prompt'][:40]:40} {r['golden']:8} {str(r['fired']):6} "
            f"{str(r['stream_tier']):8} {str(r['marker_tier']):8} {m}"
        )
    fired = [r for r in rows if r["fired"]]
    n = len(fired) or 1
    s_cap = sum(r["stream_tier"] is not None for r in fired)
    m_cap = sum(r["marker_tier"] is not None for r in fired)
    s_hit = sum(r["stream_tier"] == r["golden"] for r in fired)
    print(
        f"\nfired {len(fired)}/{len(rows)} | "
        f"stream capture {s_cap}/{n} match {s_hit}/{n} | marker capture {m_cap}/{n}"
    )


def main(reps: int = 3, jobs: int = 8) -> None:
    from evals import run

    plan = [(p, g, f) for p, g, f in golden_cases() for _ in range(reps)]
    rows: list[dict] = []
    with run.isolated_config_dir() as cfg:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [pool.submit(_probe_one, p, g, f, cfg) for p, g, f in plan]
            for done, fut in enumerate(as_completed(futures), 1):
                rows.append(fut.result())
                print(f"\r  {done}/{len(plan)} sessions", end="", flush=True)
    _report(rows)


if __name__ == "__main__":
    with contextlib.suppress(ImportError):  # a run by path has no `scripts` package on sys.path
        from scripts._harness_paths import force_utf8_io

        force_utf8_io()
    ap = argparse.ArgumentParser(description="Router outcome-capture probe (step a).")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true", help="list the cases; run nothing")
    args = ap.parse_args()
    if args.dry_run:
        cases = golden_cases()
        print(f"{len(cases)} case(s) x {args.reps} reps = {len(cases) * args.reps} sessions")
        for p, g, f in cases:
            print(f"  [{g:8}] {p}" + (f"  (fixture: {f})" if f else ""))
    else:
        main(reps=args.reps, jobs=args.jobs)
