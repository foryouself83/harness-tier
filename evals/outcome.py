"""The outcome arm: does a skill, once it fires, actually reach the right end-state?

Separate from run.py's invocation arm by design. The invocation arm asks whether a
description makes the skill fire; this asks whether the skill's *body*, executed for real,
produces the golden end-state — a different question, with a different freshness signal
(body + fixture + golden, not the description) and a different recipe (bypassPermissions +
--add-dir, so the session can actually edit files).

The pure half here (outcome_sha, outcome_check) is model-free like scores.py. run_outcome
and the CLI spend real sessions and are guarded by the suite's no_real_sessions fixture
through run._claude_stream.

    uv run python -m evals.outcome            # measure the outcome arm (reps 3)
    uv run python -m evals.outcome --dry-run  # session count + wall-clock, no model calls
    uv run python -m evals.outcome --skill wiki-init   # one skill; others keep their baseline
"""

import argparse
import hashlib
import json
import sys
import tempfile
from dataclasses import asdict
from datetime import date
from pathlib import Path

import evals.run as run
import evals.scores as scores
import evals.stream as stream
import scripts.skill_sandbox as sandbox

REPO = Path(__file__).resolve().parent.parent
OUTCOME_SCORES = REPO / "evals/outcome_scores.json"


# Scenario fields that describe the run for a human instead of shaping it: the sandbox's
# prose pass/fail criteria and the rationale behind them. Nothing build() or check_outcome
# touches, so rewording one must not cost a re-measurement. Everything else is fingerprinted,
# including fields added later — see outcome_sha.
SHA_EXEMPT = frozenset({"why", "expect", "reject"})


def _copied_file_sha(src: str) -> str:
    """Digest of one file `copy_from_repo` brings into the fixture.

    A path that does not resolve still fingerprints, under its own name: such a scenario is
    already broken and build() is where that gets said, while outcome_sha is walked
    field-by-field by the tests, so raising here would turn a fingerprint into a crash."""
    try:
        return hashlib.sha256((REPO / src).read_bytes()).hexdigest()
    except OSError:
        return "unreadable"


def outcome_sha(skill: str, scenario: sandbox.Scenario) -> str:
    """Freshness fingerprint for the outcome baseline.

    Covers everything the outcome claim depends on: the skill body that executes, the prompt
    that drives it, the fixture it runs against, and the golden it is scored by.
    description_sha covers none of these — it hashes the description only, because invocation is
    decided by the description while outcome is decided by the body.

    The scenario goes in whole, minus SHA_EXEMPT. Listing the fields to *include* is what
    let `copy_from_repo` and `git` ship outside the payload — the fixture could then change
    while every baseline still reported fresh, which is the one thing this exists to
    prevent. An allowlist cannot cover the field nobody remembered to add to it, so the
    default is now inclusion and each exemption has to argue for itself.

    `copy_from_repo` needs one thing more than its own value: the files it names are fixture
    content, and the mapping is identical whether or not they were edited. A gate script
    copied in by path can be rewritten under a baseline that keeps reporting fresh, so the
    digest of each source travels beside its path."""
    body = (REPO / f"skills/{skill}/SKILL.md").read_text(encoding="utf-8")
    fixture = {k: v for k, v in asdict(scenario).items() if k not in SHA_EXEMPT}
    fixture["copy_from_repo"] = {
        dest: [src, _copied_file_sha(src)] for dest, src in scenario.copy_from_repo.items()
    }
    payload = body + json.dumps(fixture, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:12]


def outcome_check(
    skill: str, entry: dict | None, sha: str, scenario: sandbox.Scenario
) -> scores.Verdict:
    """Model-free gate for a committed outcome entry — freshness + a non-zero floor.

    Mirrors scores.check's shape without its ratchet: at reps=3 a skill has no history to
    ratchet against yet, so a 1.0 sliding to 0.33 passes. What it enforces is that a
    committed baseline cannot be a stale or all-zero lie riding a green suite.

    `scenario` is required although only the stale branch reads it: the gate has exactly one
    call site, and an optional one let that site drop the argument with the suite still
    green — the message is then vague again and nothing says so."""
    if entry is None:
        return scores.Verdict(
            "warn", f"{skill}: outcome not measured yet — run uv run python -m evals.outcome"
        )
    missing = [k for k in ("outcome_hits", "outcome_n", "outcome_sha", "model") if k not in entry]
    if missing:
        return scores.Verdict("fail", f"{skill}: outcome entry is missing {missing} — re-measure")
    if entry["outcome_sha"] != sha:
        # Every input is named by a file, because a `copy_from_repo` source belongs to a skill
        # its editor may never have opened. The scenario carries the prompt, the fixture files
        # and the golden, so it is listed by its own path — a bare name puts three more inputs
        # behind a label that claims to list them.
        inputs = [
            f"skills/{skill}/SKILL.md",
            f"{Path(sandbox.__file__).relative_to(REPO).as_posix()}:{scenario.name}",
            *sorted(scenario.copy_from_repo.values()),
        ]
        return scores.Verdict(
            "fail",
            f"{skill}: an outcome input changed since the score — re-measure with "
            f"`uv run python -m evals.outcome --skill {skill}`. Inputs: {', '.join(inputs)}",
        )
    if entry["model"] != scores.MODEL:
        return scores.Verdict(
            "fail",
            f"{skill}: outcome measured on model {entry['model']!r}, gate pinned to "
            f"{scores.MODEL!r} — re-measure",
        )
    if entry["outcome_hits"] == 0:
        return scores.Verdict(
            "fail", f"{skill}: outcome_pass_rate is 0 — never reached the end-state, re-measure"
        )
    return scores.Verdict("ok", f"{skill}: outcome ok")


OUTCOME_MAX_TURNS = 25
# Higher than run.SESSION_TIMEOUT (180): outcome sessions actually edit files and may route
# flow -> doc-sync, so they run longer than an invocation probe.
OUTCOME_TIMEOUT = 300
REPS = 3


def _outcome_targets(only: str | None = None) -> list[tuple[str, sandbox.Scenario]]:
    """(skill, scenario) for every sandbox scenario that declares a golden end-state.

    Driven by Scenario.outcome, not cases.yaml — the invocation arm's data stays untouched.

    `only` narrows to one skill (--skill), matching run.py. Re-measuring one skill must not
    spend the others' sessions or overwrite baselines that nothing changed. An unknown name
    exits rather than measuring nothing: an empty run still writes and prints "wrote", which
    reads as a completed measurement."""
    targets = [(s.skill, s) for s in sandbox.SCENARIOS if s.outcome]
    if only is None:
        return targets
    picked = [t for t in targets if t[0] == only]
    if not picked:
        raise SystemExit(
            f"unknown skill {only!r}; scenarios declaring a golden end-state: "
            f"{sorted({s for s, _ in targets})}"
        )
    return picked


def run_outcome(skill: str, scenario: sandbox.Scenario, reps: int, config_dir: Path) -> dict:
    """Run one skill against its golden fixture `reps` times; score each by end-state.

    `fired_hits` is a diagnostic, never the score, and it is structurally 0 for a scenario
    whose prompt IS a slash command: a `disable-model-invocation` skill is entered by the
    user typing it, so no Skill tool_use is ever emitted for stream.observe to see. A 0
    beside another skill's 1.0 is that, not a regression — the end-state is the verdict.

    Each rep gets a throwaway fixture dir so bypassPermissions edits stay contained. Judged by
    the final end-state (chain-agnostic): whether the skill ran directly or via another's
    routing, the files it left behind are the outcome. `fired` is a diagnostic only.

    Aborts rather than recording a fabricated 0 when a session errored or never loaded the
    plugin — the same discipline run.measure applies to the invocation arm."""
    hits = fired_hits = 0
    for _ in range(reps):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            built = sandbox.build(scenario, Path(tmp))
            text, err = run._claude_stream(
                scenario.prompt,
                None,
                built,
                config_dir,
                permission_mode="bypassPermissions",
                # The verified recipe (spike 32-b): --add-dir REPO is what lets the session load
                # the plugin. The write boundary is cwd (the throwaway `built` fixture) plus the
                # fixture-scoped prompt, NOT --add-dir -- which also makes REPO writable. cwd and
                # the prompt are what keep edits inside the fixture; the recipe ran clean across
                # the spike and the seeding runs.
                add_dirs=(run.REPO,),
                max_turns=OUTCOME_MAX_TURNS,
                timeout=OUTCOME_TIMEOUT,
            )
            obs = stream.observe(text)
            if obs.rate_limited:
                raise run.RateLimited(f"{skill}: rate limit reached mid-outcome-measurement")
            # ASCII-only in these messages: a SystemExit propagating to a cp949 console must not
            # raise UnicodeEncodeError and bury the diagnostic (Invariant 2).
            if obs.errored or not obs.available:
                raise SystemExit(
                    f"{skill}: outcome session failed outright or never loaded the plugin -- "
                    f"refusing to record a 0 that is not about the end-state.{run._tail(err)}"
                )
            if skill not in obs.available:
                # Parity with run.measure: the plugin loaded but this skill was not offered
                # (frontmatter probably failed to parse). A recorded 0 here would be about the
                # missing skill, not the end-state -- abort rather than fabricate one.
                raise SystemExit(
                    f"{skill}: the plugin loaded but {skill} was not among its skills -- "
                    f"its frontmatter probably failed to parse."
                )
            passed, _failures = sandbox.check_outcome(scenario, built)
            hits += passed
            fired_hits += skill in obs.fired
    return {
        "outcome_sha": outcome_sha(skill, scenario),
        "model": scores.MODEL,
        "measured_at": date.today().isoformat(),
        "reps": reps,
        "outcome_hits": hits,
        "outcome_n": reps,
        "outcome_pass_rate": round(hits / reps, 2),
        # Diagnostic, never gated: did the target skill fire in the (possibly flow-routed)
        # chain? Attribution visibility without gating the score on it.
        "fired_hits": fired_hits,
        "fired_rate": round(fired_hits / reps, 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    ap.add_argument("--reps", type=int, default=REPS)
    ap.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    ap.add_argument("--skill", help="measure one skill (default: every skill with a golden)")
    args = ap.parse_args()
    if args.reps < 1:
        ap.error("--reps must be >= 1")

    targets = _outcome_targets(args.skill)
    sessions = len(targets) * args.reps
    minutes = sessions * run.SECONDS_PER_SESSION / 60
    print(f"{len(targets)} skill(s), {sessions} outcome sessions, ~{minutes:.0f} min")
    if args.dry_run:
        return 0

    baseline: dict = {}
    if OUTCOME_SCORES.exists():
        baseline = json.loads(OUTCOME_SCORES.read_text(encoding="utf-8"))
    interrupted = False
    with run.isolated_config_dir() as config_dir:
        for skill, scenario in targets:
            print(f"measuring outcome: {skill}")
            try:
                result = run_outcome(skill, scenario, args.reps, config_dir)
            except run.RateLimited as e:
                print(f"\n{e}", file=sys.stderr)
                interrupted = True
                break
            print(f"  {result}")
            baseline[skill] = result
            # Persist after each skill: a rate-limit stop keeps what was measured.
            OUTCOME_SCORES.write_text(
                json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
    if interrupted:
        # A rate-limited run is not a success: return non-zero and skip the "wrote" line so a
        # partial (or, when the first skill measured is the one that hit the limit, empty)
        # run is never read as a completed one.
        return 1
    print(f"wrote {OUTCOME_SCORES}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
