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
import os
import signal
import subprocess
import sys
import tempfile
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
from datetime import date
from pathlib import Path

import yaml

import evals.scores as scores
import evals.stream as stream
import scripts.skill_sandbox as sandbox

REPO = Path(__file__).resolve().parent.parent
CASES = REPO / "evals/cases.yaml"

# Measured under isolation, 5 happy samples of `integration`:
#   3 turns -> invoke_rate 0.2, truncated 0.80   (the score was measuring this constant)
#   6 turns -> invoke_rate 0.2, truncated 0.20   (budget adequate; the rate is real)
MAX_TURNS = 6

# The pinned model lives in scores.MODEL: the gate validates each entry's fingerprint
# against it, so the pin and the check cannot drift apart. It is a full model ID — the
# "opus" alias that held this slot retargeted with every Opus release, silently changing
# what the baseline described (measured spread on one case: 0/4 vs 4/4 across models).

# A hang guard, not a measurement bound. `MAX_TURNS` already ends a session; this only stops
# one that has stopped making progress from holding a worker forever.
#
# It was 30s for a while, chosen from a solo session where a firing landed 0.3-1.0s after the
# model started responding. That generalised across environments and should not have: under
# eight-way load the mean session runs 58s, not 45s, and at a 30s cap 75-100% of every miss
# turned out to be a session stopped before it could decide. The score was measuring this
# constant. Sessions now run to their natural end.
SESSION_TIMEOUT = 180
JOBS = 8

# Measured under eight-way load: 35 sessions finished in 252s. Solo they run ~45s — running
# eight at once stretches each one. This drives the estimate only; SESSION_TIMEOUT is a guard,
# and multiplying by it instead reported 92 minutes for a 30-minute run.
SECONDS_PER_SESSION = 58

# Observed ceiling on how late a firing arrives: across every capture, a skill that fires has
# fired by the third tool call. A session cut before that never got its chance and is genuinely
# ambiguous; one cut after five tool calls without firing had its chance and declined. Counting
# every cut session as ambiguous instead pinned the warning permanently on at 0.80 while
# `invoke_rate` sat unmoved at 0.20 across three timeouts — and a warning that always fires is
# not a signal.
FIRE_BY_TOOL_CALL = 3


def cut_early(obs: stream.Observation) -> bool:
    """Did the session stop before it had a real chance to reach for the skill?

    Two ways to be stopped — killed at SESSION_TIMEOUT (no result event, so `completed` is
    False) or spent at MAX_TURNS — and one rule for both: it is only ambiguous if it had not
    yet made FIRE_BY_TOOL_CALL tool calls. A 6-turn cap reached after four tool calls is a
    session that had its chance and declined, not a truncation."""
    return not (obs.completed and not obs.turns_exhausted) and obs.tool_calls < FIRE_BY_TOOL_CALL


def _tail(err: str, lines: int = 5) -> str:
    """The last of a dead session's stderr, for the SystemExit that reports it. Captured but
    never read is how the cause of an unusable session got thrown away."""
    kept = [ln for ln in err.strip().splitlines() if ln.strip()][-lines:]
    return "\n  stderr: " + "\n          ".join(kept) if kept else ""


class RateLimited(RuntimeError):
    """The five-hour window is exhausted. Overage is rejected on this account, so the CLI
    starts failing rather than billing — and a failed session recorded as "the skill did not
    fire" is a fabricated score. Everything measured before this point is already on disk."""


def cases_for(entry: dict, arm: str) -> list[tuple[str, str | None]]:
    """Normalise both `- "prompt"` and `- {prompt:, fixture:}` into (prompt, fixture)."""
    out = []
    for case in entry[arm]:
        if isinstance(case, dict):
            out.append((case["prompt"], case.get("fixture", entry.get("fixture"))))
        else:
            out.append((case, entry.get("fixture")))
    return out


@contextmanager
def isolated_config_dir() -> Iterator[Path]:
    """A config dir holding credentials and nothing else.

    Isolation is what makes the score about *these* descriptions. This machine has a second
    installed plugin shipping seven of the same skill names, and a twin winning the
    invocation reads as our skill not firing — a property of one developer's setup, not of
    the description, and not reproducible by anyone else.

    The credentials are the one thing that has to survive the isolation. An empty config dir
    still produces a well-formed `init` event and then answers "Not logged in", so every
    session would score 0.0 for a reason that has nothing to do with any skill. Measured: ten
    such sessions read invoke_rate 0.00 before this was found.

    The copy is a live credential sitting in a world-writable system temp dir for the length
    of the run, so it is written through `os.open` with 0o600 rather than `shutil.copy2`
    (which would carry the source mode in and leave the file briefly readable in between).
    Permissions are only half of it — on Windows they are largely advisory — so the credential
    is also unlinked in a `finally`, before the temp tree comes down. A context manager rather
    than a plain function so that cleanup lives next to the copy: the previous shape leaned on
    the caller's `TemporaryDirectory` alone, which meant the one file here worth worrying about
    outlived any exit that skipped the tree removal.

    `ignore_cleanup_errors` matches `_one`: on Windows a session's leftover child process can
    still hold a handle on the tree, and the two temp dirs disagreeing on that meant the config
    root could raise at exit over a directory the OS reclaims anyway.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
        cfg = Path(root) / "cfg"
        cfg.mkdir(exist_ok=True)
        src = Path.home() / ".claude" / ".credentials.json"
        if not src.exists():
            raise SystemExit(
                f"no credentials at {src} — isolated sessions cannot authenticate. "
                f"Keychain-stored logins (macOS) and API-key auth keep nothing there; this "
                f"runner currently requires a machine whose subscription login wrote "
                f".credentials.json (Windows/Linux)."
            )
        dst = cfg / src.name
        fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(src.read_bytes())
        try:
            yield cfg
        finally:
            dst.unlink(missing_ok=True)


def session_env(config_dir: Path) -> dict[str, str]:
    """Everything provider-shaped is stripped rather than whitelisting the world: the CLI
    needs an unknowable, platform-varying set of system variables (PATH, APPDATA, node's
    own), while the contamination surface is exactly the provider-prefixed names —
    ANTHROPIC_BASE_URL reroutes every session through a proxy, ANTHROPIC_API_KEY switches
    the auth path away from the copied credential, CLAUDE_CODE_* flips CLI behaviour. One
    developer's shell must not become a fact in the committed baseline."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not (k.startswith("ANTHROPIC_") or k.startswith("CLAUDE_"))
    }
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    return env


def run_session(
    prompt: str, fixture: str | None, workdir: Path, config_dir: Path, restricted: bool = False
) -> tuple[stream.Observation, str]:
    """Returns the observation plus the session's stderr.

    stderr is carried alongside rather than folded into the Observation because
    `stream.observe` answers questions about the transcript and knows nothing about the
    process that produced it. It is the only record of *why* a session produced no usable
    stream, and capturing it without ever reading it is how that cause got lost."""
    if fixture:
        # build() creates workdir/<scenario> and returns it — run *there*. Staying in the
        # parent would put the agent in a directory holding a single subdirectory, which is
        # the empty-cwd condition that makes it explore before it reaches for a skill, and
        # every fixture-backed skill would score low for a reason that is not its description.
        workdir = sandbox.build(sandbox.BY_NAME[fixture], workdir)
    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--max-turns",
        str(MAX_TURNS),
        "--model",
        scores.MODEL,
        "--plugin-dir",
        str(REPO),
    ]
    if restricted:
        # The diagnostic arm. With no other tool on offer the agent cannot quietly do the
        # work itself, so what is left is whether the prompt matches the description at all.
        # It answers a different question from the scored arms and is never gated.
        cmd += ["--allowedTools", "Skill"]
    proc = subprocess.Popen(
        cmd,
        cwd=workdir,
        env=session_env(config_dir),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        # POSIX: a fresh process group, so the timeout path below can kill the whole tree
        # with one killpg. Ignored on Windows, where taskkill /T walks the tree instead.
        start_new_session=os.name != "nt",
    )
    try:
        out, err = proc.communicate(timeout=SESSION_TIMEOUT)
    except subprocess.TimeoutExpired:
        # subprocess.run()'s timeout path kills only the direct child and then drains the
        # pipes with an UNBOUNDED communicate(); a surviving grandchild holding the
        # inherited write handles blocks that read forever — on this module's own Windows
        # evidence that children outlive the kill, the "hang guard" was itself the hang.
        # Kill the tree first, then drain: with every writer dead the pipes close.
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                proc.kill()  # the group is already gone; reap whatever is left
        out, err = proc.communicate()
    # The turn cap exits 1 with the stream fully written, and a timeout kill leaves no exit
    # code worth reading either. Parse, then judge.
    return (
        stream.observe(out.decode("utf-8", errors="replace")),
        err.decode("utf-8", errors="replace"),
    )


def _one(prompt: str, fixture: str | None, config_dir: Path, restricted: bool):
    # On Windows, killing `claude` on the timeout does not necessarily kill every process it
    # spawned, so the temp dir can still be held open a moment after the session returns.
    # ignore_cleanup_errors keeps that race from crashing the whole run over one leaked
    # directory that the OS will reclaim regardless.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        return run_session(prompt, fixture, Path(tmp), config_dir, restricted)


def measure(name: str, entry: dict, reps: int, config_dir: Path, jobs: int) -> dict:
    happy = cases_for(entry, "happy")
    negative = cases_for(entry, "negative")

    plan = [("happy", p, f, False) for p, f in happy for _ in range(reps)]
    plan += [("negative", p, f, False) for p, f in negative for _ in range(reps)]
    plan += [("restricted", p, f, True) for p, f in happy]

    # Sessions share nothing — each gets its own temp dir and prompt, and the config dir is
    # read-only to them. Serial was an unexamined default; 8 at a time measured 8 sessions
    # per ~30s against 45s each on their own.
    seen: list = [None] * len(plan)
    pool = ThreadPoolExecutor(max_workers=jobs)
    try:
        futures = {
            pool.submit(_one, prompt, fixture, config_dir, restricted): i
            for i, (_arm, prompt, fixture, restricted) in enumerate(plan)
        }
        for done, fut in enumerate(as_completed(futures), 1):
            obs, _err = seen[futures[fut]] = fut.result()
            print(f"\r  {name}: {done}/{len(plan)} sessions", end="", flush=True)
            if obs.rate_limited:
                # Stop the moment the window closes, not after the plan finishes. Every
                # session still queued would be refused the same way, so letting them run
                # spends the next window's budget producing nothing. Judged here rather than
                # in the aggregation loop below, where hitting the cap on session 1 of 35
                # still burned the other 34 before anyone was told.
                print()
                raise RateLimited(f"{name}: rate limit reached mid-measurement")
        print()
    finally:
        # A plain `ThreadPoolExecutor(...)` rather than `with`, because the `with` form's exit
        # is `shutdown(wait=True)` — on a rate-limit stop that blocks for up to
        # SESSION_TIMEOUT on the <= `jobs` sessions already in flight. Those are already spent
        # and their results are discarded, so waiting on them only delays `main`'s save of
        # every skill measured before the window closed, which is the one thing a rate-limit
        # stop exists to protect. cancel_futures drops everything not yet started; the
        # interpreter still joins the surviving threads at exit, so nothing is orphaned.
        pool.shutdown(wait=False, cancel_futures=True)

    hits = misses = fires = quiet = truncated = truncated_quiet = 0
    restricted_hits = restricted_total = 0
    # Which *other* harness-tier skill took a happy prompt this one was meant to win. A bare
    # rate says a description is losing; this says what it is losing to, which is the whole
    # reason for measuring descriptions against each other. Diagnostic only — `scores.check`
    # never reads it, so a shift here can never pass or fail the gate.
    #
    # Bounded by what `obs.fired` can see: `stream._local` keeps only `harness-tier:*` names,
    # so a prompt lost to a built-in or to plain Bash reads as an empty `lost_to`, not as a
    # named winner. Under an isolated config dir there are no other plugins to lose to, which
    # is what makes sibling-only close to complete here rather than merely convenient.
    lost_to: dict[str, int] = {}
    for (arm, _p, _f, _r), (obs, err) in zip(plan, seen):
        if obs.errored:
            raise SystemExit(
                f"{name}: a session failed outright rather than hitting the turn cap — most "
                f"likely the isolated config dir lost authentication. Refusing to record a "
                f"0.0 that is not about the description.{_tail(err)}"
            )
        # Judged per session, not per run. A session that never reached the init event
        # produced no evidence about anything: `completed` is False and `tool_calls` 0, so it
        # would be tallied as a miss *and* as truncated. Checking only "did any session see
        # the plugin" let 14 of 15 dead sessions through and wrote their silence into the
        # score. A session killed at SESSION_TIMEOUT has long since passed init, so this
        # catches a failed spawn rather than a slow run.
        if not obs.available:
            raise SystemExit(
                f"{name}: a session never reached the init event — unusable, not a miss. "
                f"--plugin-dir {REPO} may be wrong, or the process died before it "
                f"started.{_tail(err)}"
            )
        if name not in obs.available:
            raise SystemExit(
                f"{name}: the plugin loaded but this skill was not among its skills — "
                f"the frontmatter probably failed to parse."
            )
        fired = name in obs.fired
        # The one outcome this design cannot tell from a deliberate miss: the session stopped
        # before it had a real chance to reach for the skill. Both arms apply the same rule.
        # A spent turn cap is *not* automatically ambiguous — by FIRE_BY_TOOL_CALL's own
        # rationale a session that made three or more tool calls without firing had its
        # chance and declined, and a 6-turn cap always makes at least that many. Counting
        # every cap as ambiguous flagged the skill closest to the floor for a truncation that
        # had not happened.
        ambiguous = cut_early(obs)
        if arm == "restricted":
            restricted_hits += fired
            restricted_total += 1
        elif arm == "happy":
            hits += fired
            misses += not fired
            truncated += ambiguous and not fired
            if not fired:
                # dict.fromkeys, not the raw list: a session that reached for the same
                # neighbour twice is one lost prompt, not two.
                for winner in dict.fromkeys(obs.fired):
                    lost_to[winner] = lost_to.get(winner, 0) + 1
        else:
            fires += fired
            quiet += not fired
            # The same cut flatters `false_fire` exactly as it depresses `invoke_rate`: a
            # negative sample stopped before the agent could over-fire is recorded as
            # correctly quiet. Tracking it on only one arm would leave the ceiling passing
            # on evidence nobody checked.
            truncated_quiet += ambiguous and not fired

    result = {
        "description_sha": scores.description_sha(name),
        # The second fingerprint, written by the same hand that ran the sessions. Without it
        # every future entry fails check()'s model gate (and "re-measure" cannot fix what
        # re-measuring reproduces), while may_write's model-boundary skip reads the missing
        # key as a model change and never ratchets again.
        "model": scores.MODEL,
        # Provenance per skill, not per file. The default mode is incremental, so the normal
        # run measures one skill and rewrites the whole file; a file-level `reps` would then
        # claim this run's sample size for six skills it never touched.
        "measured_at": date.today().isoformat(),
        "reps": reps,
        # The raw counts are what the gate and ratchet read — the exact binomial needs k and n,
        # not a two-decimal rate. `invoke_rate`/`false_fire` are kept as derived, human-readable
        # fields. Recording n alongside the rate is also what lets a per-skill `reps` override
        # raise sample size for a low-rate skill without the ratchet mixing sample sizes.
        "invoke_hits": hits,
        "invoke_n": hits + misses,
        "invoke_rate": round(hits / (hits + misses), 2),
        # Gated at MAX_FALSE_FIRE, but do not read a green `false_fire` as "the description is
        # precise". All seven skills measure 0.00 across 105 negative sessions, and at 15
        # samples failing needs 4/15 — while the overall firing base rate is low (happy mean
        # ~0.60). A skill that reaches for itself three times in five is not one that will grab
        # its neighbour's prompt four times in fifteen, so near-zero here is mostly explained
        # by how rarely anything fires at all. The ceiling stays because it costs nothing and
        # would catch a genuinely greedy description; it is not evidence that the descriptions
        # are well separated. Raising `invoke_rate` is what would make this metric informative.
        "false_hits": fires,
        "false_n": fires + quiet,
        "false_fire": round(fires / (fires + quiet), 2),
        # Both diagnostics, never gated.
        #
        # `truncated` says how much of the verdict rests on a session being cut short.
        #
        # `restricted` is NOT comparable to `invoke_rate`, and reading it as "the rate if the
        # agent could not do the work itself" is wrong. `--allowedTools Skill` removes Read
        # and Bash, so it also removes the agent's ability to *see the fixture* that
        # run_session went to the trouble of building — the arm answers only "does the prompt
        # match the description on its own words". That is why all four fixture-backed skills
        # read `restricted <= invoke_rate` while fixture-less ones can read higher, and why
        # playwright-scaffold shows 1.00 free against 0.20 restricted. Second caveat: reps are
        # not applied to this arm, so it is n=5 however many reps the scored arms ran — two
        # decimals of a five-sample rate are three more than it can carry.
        "truncated": round(truncated / (hits + misses), 2),
        "truncated_quiet": round(truncated_quiet / (fires + quiet), 2),
        "restricted": round(restricted_hits / restricted_total, 2),
        "lost_to": lost_to,
    }
    if lost_to:
        losses = ", ".join(f"{winner} x{n}" for winner, n in sorted(lost_to.items()))
        print(f"  [i] {name}: happy misses reached for {losses} instead", flush=True)
    for metric, share, of in (
        ("invoke_rate", result["truncated"], "happy"),
        ("false_fire", result["truncated_quiet"], "negative"),
    ):
        if share > 0.20:
            print(
                f"  [!] {name}: {share:.0%} of {of} samples were cut short — {metric} is "
                f"reporting SESSION_TIMEOUT or MAX_TURNS rather than the description",
                flush=True,
            )
    return result


def main() -> int:
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
    ap.add_argument("--reps", type=int, default=3)
    ap.add_argument("--jobs", type=int, default=JOBS, help="sessions in flight at once")
    ap.add_argument("--dry-run", action="store_true", help="print the plan, run nothing")
    ap.add_argument("--accept", action="store_true", help="allow a score below the baseline")
    ap.add_argument("--reason", help="why the drop is acceptable (required with --accept)")
    args = ap.parse_args()

    if args.reps < 1:
        ap.error("--reps must be >= 1")
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

    data = yaml.safe_load(CASES.read_text(encoding="utf-8"))
    # The family size the ratchet's per-run alpha is derived over (Sidak across the skills).
    n_skills = len(data["skills"])
    baseline = scores.load()
    old_skills = baseline.get("skills", {})

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
            n
            for n in sorted(data["skills"])
            if old_skills.get(n, {}).get("description_sha") != scores.description_sha(n)
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
    minutes = sessions / args.jobs * SECONDS_PER_SESSION / 60
    print(
        f"{len(targets)} skill(s), {sessions} sessions, {args.jobs} at a time, ~{minutes:.0f} min"
    )
    if args.dry_run:
        return 0

    def save() -> None:
        """Persist after every skill. Writing once at the end loses the whole run to a single
        rate-limit refusal.

        `measured_at` and `reps` live on each skill entry (see `measure`) — nothing file-level
        is written, because an incremental run only knows the provenance of what it measured."""
        baseline["skills"] = old_skills
        scores.SCORES.write_text(
            json.dumps(baseline, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )

    with isolated_config_dir() as config_dir:
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
                result = measure(name, entry, reps, config_dir, args.jobs)
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
                    result = measure(name, entry, reps, config_dir, args.jobs)
                    print(f"  {result}")
                    verdict = scores.may_write(
                        name,
                        result,
                        old_skills.get(name),
                        args.accept,
                        confirmed=True,
                        n_skills=n_skills,
                    )
            except RateLimited as e:
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
                    print(f"  uv run python -m evals.run --skill {n}", file=sys.stderr)
                return 1
            if verdict.level == "fail":
                print(verdict.message, file=sys.stderr)
                return 1
            # Only when the number actually went down. `--accept` is permission to write a
            # lower score, not an assertion that this run produced one: re-running an
            # accepted skill that then came back level or higher used to stamp `lowered_from`
            # on the improvement, leaving a permanent record of a regression that never
            # happened and that no later reader could tell from a real one.
            if args.accept and name in old_skills:
                if old_skills[name]["invoke_rate"] > result["invoke_rate"]:
                    result["lowered_from"] = old_skills[name]["invoke_rate"]
                    result["lowered_reason"] = args.reason
            old_skills[name] = result
            measured += 1
            save()

        print(f"wrote {scores.SCORES}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
