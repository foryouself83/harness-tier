"""Measure whether each model-invoked skill fires when it should.

Runs every case as a real headless `claude` session against the working tree
(`--plugin-dir`, so unreleased changes are measurable) and records the rate at which the
right skill fired.

Three things keep the number about *these descriptions* rather than about the machine that
produced them. An empty `CLAUDE_CONFIG_DIR` drops every installed plugin — this machine has
a second one shipping seven identically-named skills. The model is pinned, because an
inherited one moved `integration` between 0.0 and 1.0 across tiers. And the tool set is left
alone, because restricting it would remove the very choice being measured: whether the agent
reaches for the skill instead of doing the work itself.

    uv run python -m evals.run                 # only skills whose description changed
    uv run python -m evals.run --all           # the full calibration run (reps 3)
    uv run python -m evals.run --all --dry-run # session count + wall-clock, no model calls
    uv run python -m evals.run --skill doc-sync --accept --reason "traded for false_fire"
"""

import argparse
import json
import sys

import yaml

import evals.scores as scores
from evals.runner import capture, config, invocation, session
from scripts._harness_paths import force_utf8_io


def _main() -> int:
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n")[0])
    # Mutually exclusive because they answered the same question and one silently won:
    # `--all --skill flow` measured one skill while reading as a full run.
    scope = ap.add_mutually_exclusive_group()
    scope.add_argument("--all", action="store_true", help="re-measure every skill")
    scope.add_argument("--skill", help="measure one skill")
    # 3, matching the baseline in scores.json. It was 5 while the committed numbers were
    # measured at 3. Under the old rate-subtraction ratchet that mismatch was a real error —
    # re-measuring at 25 samples and comparing the rate to a 15-sample baseline treated two
    # different quantities as one. The exact-binomial ratchet removes that: it compares k/n to
    # k/n via `binom_cdf(k_new, n_new, p_ref)`, which is correct even when n_new != n_base. That
    # is why a per-skill `reps:` override in cases.yaml is safe — a low-rate skill can buy
    # sample size without distorting the comparison. The global default stays 3 for provenance
    # (the committed baseline's n) and predictable budget; rate-limit is no longer the driver —
    # at JOBS = 8 a full run is 245 sessions in ~30 min and 5 reps would be ~46 min, both fit.
    ap.add_argument("--reps", type=int, default=config.DEFAULT_REPS)
    ap.add_argument("--jobs", type=int, default=config.JOBS, help="sessions in flight at once")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    ap.add_argument("--accept", action="store_true", help="allow a score below the baseline")
    ap.add_argument("--reason", help="why the drop is acceptable (required with --accept)")
    ap.add_argument(
        "--capture-fixtures",
        action="store_true",
        help=(
            "save stream fixture candidates as <name>.jsonl.new (requires --skill: the "
            "committed fixtures name a specific skill, so another skill's session cannot "
            "replace them)"
        ),
    )
    args = ap.parse_args()

    if args.reps < 1:
        ap.error("--reps must be >= 1")
    if args.capture_fixtures and not args.skill:
        # The suite asserts on a named skill (`"integration" in obs.fired`), so a candidate
        # from another skill's session clears every structural condition and still fails the
        # tests it is meant to feed. The incremental default mode walks skills alphabetically,
        # which makes doc-sync — not the fixture's skill — the one that would win first.
        ap.error(
            "--capture-fixtures requires --skill: the committed fixtures name a specific "
            "skill, so a candidate captured from another skill's session cannot replace them"
        )
    if args.accept and not args.reason:
        ap.error(
            "--accept requires --reason: an unexplained drop is indistinguishable "
            "from an unnoticed one"
        )
    if args.accept and not args.skill:
        # Acceptance is a judgement about one description's drop, and `--reason` is the
        # record of that judgement. A run over several skills has only one `--reason` to
        # spend, so it stamped the same sentence onto every skill that dropped — a written
        # justification that was true of at most one of them. Scoping the flag is the honest
        # fix; the alternative (silently applying it only where a drop occurred) still
        # attributes one person's reasoning to skills they never looked at.
        ap.error(
            "--accept requires --skill: one --reason cannot honestly explain a drop in "
            "more than one description. Accept them one at a time."
        )

    # Disarmed on entry, unconditionally, before any branch or early return can skip it —
    # `--dry-run` and an unknown `--skill` both leave without reaching the arming call
    # below, and inheriting a previous in-process run's state there is the bug this pair
    # of calls exists to make impossible. Two calls, two jobs: disarm, then arm.
    capture._reset_capture_state()

    data = yaml.safe_load(config.CASES.read_text(encoding="utf-8"))
    # The family size the ratchet's per-run alpha is derived over (Sidak across the skills).
    n_skills = len(data["skills"])
    baseline = scores.load()
    old_skills = baseline.get("skills", {})

    # Assigned once, ahead of the branches, and unconditionally. Setting it inside the
    # `--skill` arm alone left a flagless `--all` inheriting the previous call's target within
    # a process — the constraint this feature is built on is "off unless asked", and a global
    # written on one path out of three does not hold it. `CAPTURED` resets with it so a second
    # run cannot report the first one's results.
    if args.skill:
        if args.skill not in data["skills"]:
            ap.error(f"unknown skill {args.skill!r}; cases.yaml has {sorted(data['skills'])}")
        targets = [args.skill]
    elif args.all:
        targets = sorted(data["skills"])
    else:
        # The default is incremental. A harness nobody can afford to run is one whose
        # freshness gate blocks every merge.
        targets = [
            n for n in sorted(data["skills"]) if invocation.is_stale(n, old_skills.get(n, {}))
        ]
        if not targets:
            print("every score is current — nothing to measure")
            return 0

    sessions = sum(
        (len(data["skills"][n]["happy"]) + len(data["skills"][n]["negative"]))
        * data["skills"][n].get("reps", args.reps)
        + len(data["skills"][n]["happy"])
        for n in targets
    )
    minutes = sessions / args.jobs * config.SECONDS_PER_SESSION / 60
    print(
        f"{len(targets)} skill(s), {sessions} sessions, {args.jobs} at a time, ~{minutes:.0f} min"
    )
    if args.dry_run:
        return 0

    # Armed here, past every exit that spawns no session, so that an unknown `--skill` or a
    # `--dry-run` cannot end with a capture report about sessions that never existed. Position
    # carries the guarantee; a pair of conditions would have to be remembered.
    capture._reset_capture_state(args.skill if args.capture_fixtures else None)

    def save() -> None:
        """Persist after every skill. Writing once at the end loses the whole run to a single
        rate-limit refusal.

        `measured_at` and `reps` live on each skill entry (see `measure`) — nothing file-level
        is written, because an incremental run only knows the provenance of what it measured."""
        baseline["skills"] = old_skills
        scores.SCORES.write_text(
            json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    with session.isolated_config_dir() as config_dir:
        measured = 0
        for name in targets:
            entry = data["skills"][name]
            # Forcing function: the gate operates on the per-skill declaration, not a global
            # constant, so refuse to record a baseline for a skill that has not declared one.
            if "expect_invoke" not in entry or not str(entry.get("expect_why", "")).strip():
                raise SystemExit(
                    f"{name}: declare expect_invoke and expect_why in cases.yaml before measuring"
                )
            # A low-rate skill can buy sample size with its own `reps:`; the ratchet compares
            # k/n against k/n, so a larger n for one skill does not distort the comparison.
            reps = entry.get("reps", args.reps)
            print(f"measuring {name}")
            try:
                result = invocation.measure(name, entry, reps, config_dir, args.jobs)
                verdict = scores.may_write(
                    name, result, old_skills.get(name), args.accept, n_skills=n_skills
                )
                print(f"  {result}")
                if verdict.level == "confirm":
                    # One reading cannot separate a real regression from binomial noise at this
                    # sample size. Rather than widening the tolerance until the ratchet never
                    # fires, spend a second measurement: two consecutive trips are what a fail
                    # requires, and alpha_single carries the sqrt that compounds them to
                    # ALPHA_FAMILY.
                    print(f"  {verdict.message}")
                    result = invocation.measure(name, entry, reps, config_dir, args.jobs)
                    print(f"  {result}")
                    verdict = scores.may_write(
                        name,
                        result,
                        old_skills.get(name),
                        args.accept,
                        confirmed=True,
                        n_skills=n_skills,
                    )
            except session.RateLimited as e:
                save()
                print(f"\n{e}", file=sys.stderr)
                # Name the remainder explicitly. "re-run without --all" was wrong advice
                # for an interrupted --all run: the remaining skills' old entries still
                # carry matching shas, so the incremental default would skip them and
                # report every score current.
                remaining = targets[targets.index(name) :]
                print(
                    f"{measured}/{len(targets)} skills measured and saved. When the window "
                    f"resets, finish one at a time:",
                    file=sys.stderr,
                )
                for n in remaining:
                    # Carry the capture flag into the resume line — without it a rate-limited
                    # run silently stops capturing, and the leftover `.new` from this run then
                    # suppresses the retry's candidates too.
                    flag = " --capture-fixtures" if capture.CAPTURE_FOR else ""
                    print(f"  uv run python -m evals.run --skill {n}{flag}", file=sys.stderr)
                capture.CAPTURE_PROVISIONAL = True
                return 1
            if verdict.level == "fail":
                print(verdict.message, file=sys.stderr)
                return 1
            # Only when the number went down. `--accept` is permission to write a lower
            # score, not an assertion that this run produced one — stamping `lowered_from` on
            # a run that came back level or higher would leave a permanent record of a
            # regression that never happened, indistinguishable from a real one.
            if args.accept and name in old_skills:
                if old_skills[name]["invoke_rate"] > result["invoke_rate"]:
                    result["lowered_from"] = old_skills[name]["invoke_rate"]
                    result["lowered_reason"] = args.reason
            old_skills[name] = result
            measured += 1
            save()

        print(f"wrote {scores.SCORES}")
        return 0


def main() -> int:
    """Thin wrapper so the capture report reaches EVERY exit.

    Reporting at the two obvious returns missed the likeliest non-clean ending of a capture
    run: a ratchet `fail` return, which the plan itself predicts (`integration` sits at 4/15
    and re-measuring re-baselines it). `measure`'s SystemExit guards were uncovered too. A
    `finally` costs one indirection and closes all of them."""
    force_utf8_io()
    try:
        return _main()
    finally:
        # A print that raises inside `finally` replaces the exception leaving this frame. The
        # report is a diagnostic; it must never become the thing that hides the real exit.
        try:
            capture.report_capture(provisional=capture.CAPTURE_PROVISIONAL)
        except Exception:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
