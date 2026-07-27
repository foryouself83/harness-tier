"""Probe: can flow's classified tier be captured deterministically from a headless
session, and does it match the golden_tier? Standalone — the scored path never imports it.
See docs/superpowers/specs/2026-07-24-router-outcome-probe-design.md."""

import argparse
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
    flow's fixture is null, so <workdir> is the session CWD and the marker lands beneath it."""
    marker = Path(workdir) / ".claude" / "harness-tier" / ".flow" / "tier"
    if not marker.exists():
        return None
    tier = marker.read_text(encoding="utf-8").strip().split(":", 1)[0].lower()
    return tier or None


def golden_cases() -> list[tuple[str, str]]:
    """flow's happy prompts carrying a golden_tier — (prompt, golden_tier). The unlabelled
    'Commit these changes' (tier depends on the diff) is skipped."""
    data = yaml.safe_load((REPO / "evals/cases.yaml").read_text(encoding="utf-8"))
    out = []
    for case in data["skills"]["flow"]["happy"]:
        if isinstance(case, dict) and case.get("golden_tier"):
            out.append((case["prompt"], case["golden_tier"]))
    return out


def _probe_one(prompt: str, golden: str, config_dir: Path) -> dict:
    """One session; capture the tier two ways. Lazy import keeps run's subprocess machinery
    off the import path of the pure-function tests."""
    from evals import run, stream

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        wd = Path(tmp)
        text, _err = run._claude_stream(prompt, None, wd, config_dir, False)
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

    plan = [(p, g) for p, g in golden_cases() for _ in range(reps)]
    rows: list[dict] = []
    with run.isolated_config_dir() as cfg:
        with ThreadPoolExecutor(max_workers=jobs) as pool:
            futures = [pool.submit(_probe_one, p, g, cfg) for p, g in plan]
            for done, fut in enumerate(as_completed(futures), 1):
                rows.append(fut.result())
                print(f"\r  {done}/{len(plan)} sessions", end="", flush=True)
    _report(rows)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Router outcome-capture probe (step a).")
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=8)
    ap.add_argument("--dry-run", action="store_true", help="list the cases; run nothing")
    args = ap.parse_args()
    if args.dry_run:
        cases = golden_cases()
        print(f"{len(cases)} case(s) x {args.reps} reps = {len(cases) * args.reps} sessions")
        for p, g in cases:
            print(f"  [{g:8}] {p}")
    else:
        main(reps=args.reps, jobs=args.jobs)
