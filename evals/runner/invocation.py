"""The invocation arm: does a skill fire on the prompts it should, and stay quiet on the rest."""

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path

import evals.scores as scores
import evals.stream as stream
from evals.runner import config, diagnose, session


def cut_early(obs: stream.Observation) -> bool:
    """Did the session stop before it had a real chance to reach for the skill?

    Two ways to be stopped — killed at SESSION_TIMEOUT (no result event, so `completed` is
    False) or spent at MAX_TURNS — and one rule for both: it is only ambiguous if it had not
    yet made FIRE_BY_TOOL_CALL tool calls. A 6-turn cap reached after four tool calls is a
    session that had its chance and declined, not a truncation.

    At the current budget the turn-cap half is empty: turns cost tool calls at a rate of at
    least `num_turns - 1` (the closing turn can be text-only — `stream-quiet` captures exactly
    that, 4 turns to 3 calls), so spending MAX_TURNS=6 lands on 5 and clears
    FIRE_BY_TOOL_CALL=3 with room to spare.
    The branch stays because the rule is what is right, not the arithmetic — drop MAX_TURNS
    below FIRE_BY_TOOL_CALL and it comes alive. `test_a_spent_turn_cap_cannot_be_ambiguous_at_
    this_budget` pins that relationship so the emptiness is a checked fact, not a claim in a
    comment: the scenario table in tests/evals/ exercises this branch with a state the runner
    cannot currently produce."""
    return (
        not (obs.completed and not obs.turns_exhausted)
        and obs.tool_calls < config.FIRE_BY_TOOL_CALL
    )


def is_stale(name: str, recorded: dict) -> bool:
    """Whether the incremental run re-measures this skill. A recorded fixture_sha that no
    longer matches is as stale as a moved description; an entry that predates the key is left
    alone, so adding the key re-measured nothing."""
    fixture = scores.fixture_sha(name)
    return (
        recorded.get("description_sha") != scores.description_sha(name)
        or recorded.get("fixture_sha", fixture) != fixture
    )


def cases_for(entry: dict, arm: str) -> list[tuple[str, str | None]]:
    """Normalise both `- "prompt"` and `- {prompt:, fixture:}` into (prompt, fixture)."""
    out = []
    for case in entry[arm]:
        if isinstance(case, dict):
            out.append((case["prompt"], case.get("fixture", entry.get("fixture"))))
        else:
            out.append((case, entry.get("fixture")))
    return out


def _keep(name: str, i: int, case: tuple, seen: tuple, reason: str) -> Path:
    """Record one session of `measure`'s plan under `diagnose`, at its plan index."""
    arm, prompt, fixture, _restricted = case
    obs, raw = seen
    return diagnose.record(
        raw,
        obs,
        skill=name,
        arm=arm,
        index=i,
        prompt=prompt,
        fixture=fixture,
        reason=reason,
        timeout=config.SESSION_TIMEOUT,
    )


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
            pool.submit(session._one, prompt, fixture, config_dir, restricted): i
            for i, (_arm, prompt, fixture, restricted) in enumerate(plan)
        }
        for done, fut in enumerate(as_completed(futures), 1):
            obs, _raw = seen[futures[fut]] = fut.result()
            print(f"\r  {name}: {done}/{len(plan)} sessions", end="", flush=True)
            if obs.rate_limited:
                # Stop the moment the window closes, not after the plan finishes. Every
                # session still queued would be refused the same way, so letting them run
                # spends the next window's budget producing nothing. Judged here rather than
                # in the aggregation loop below, where hitting the cap on session 1 of 35
                # still burned the other 34 before anyone was told.
                print()
                raise session.RateLimited(f"{name}: rate limit reached mid-measurement")
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
    for i, (case, (obs, raw)) in enumerate(zip(plan, seen)):
        arm = case[0]
        if obs.errored:
            path = _keep(name, i, case, (obs, raw), diagnose.ERRORED)
            raise SystemExit(
                f"{name}: a session failed outright rather than hitting the turn cap — most "
                f"likely the isolated config dir lost authentication. Refusing to record a "
                f"0.0 that is not about the description.{session._tail(raw.err)}"
                f"\n  record: {path}"
            )
        # Judged per session, not per run. A session that never reached the init event
        # produced no evidence about anything: `completed` is False and `tool_calls` 0, so it
        # would be tallied as a miss *and* as truncated. Checking only "did any session see
        # the plugin" let 14 of 15 dead sessions through and wrote their silence into the
        # score. A session killed at SESSION_TIMEOUT normally has long since passed init, so
        # this mostly catches a failed spawn; one stuck before init says so instead.
        if not obs.available and raw.timed_out:
            path = _keep(name, i, case, (obs, raw), diagnose.TIMEOUT)
            raise SystemExit(
                f"{name}: a session timed out at {config.SESSION_TIMEOUT}s before the init "
                f"event — unusable, not a miss.{session._tail(raw.err)}\n  record: {path}"
            )
        if not obs.available:
            path = _keep(name, i, case, (obs, raw), diagnose.NO_INIT)
            raise SystemExit(
                f"{name}: a session never reached the init event — unusable, not a miss. "
                f"--plugin-dir {config.REPO} may be wrong, or the process died before it "
                f"started.{session._tail(raw.err)}\n  record: {path}"
            )
        if name not in obs.available:
            path = _keep(name, i, case, (obs, raw), diagnose.MISSING_SKILL)
            raise SystemExit(
                f"{name}: the plugin loaded but this skill was not among its skills — "
                f"the frontmatter probably failed to parse.\n  record: {path}"
            )
        if raw.timed_out:
            # Scored below by the rule every cut session meets; the record says where it hung.
            path = _keep(name, i, case, (obs, raw), diagnose.TIMEOUT)
            print(
                f"  [!] {name} {arm}#{i}: timed out at {config.SESSION_TIMEOUT}s after "
                f"{obs.tool_calls} tool calls, last {diagnose.last_name(obs)} — {path}",
                flush=True,
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
        # The fixtures this run's prompts met. None records a run in no fixture, which check()
        # holds the skill to: gaining a fixture later stales the score.
        "fixture_sha": scores.fixture_sha(name),
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
        # `truncated` says how much of the verdict rests on a session being cut short, as a share
        # of the MISSES — only a miss can rest on it, since a session that fired already decided.
        # Over every sample instead it was bounded by `1 - invoke_rate`, which made the 0.20
        # warning below mean a different thing per skill: arithmetically unreachable for one
        # measuring 1.00 (two of the seven are) and easy to trip for one near the floor. 0.0 when
        # nothing was missed — no miss, nothing to explain.
        #
        # `restricted` is NOT comparable to `invoke_rate`, and reading it as "the rate if the
        # agent could not do the work itself" is wrong. `--allowedTools Skill` removes Read
        # and Bash, so it also removes the agent's ability to *see the fixture* that
        # run_session went to the trouble of building — the arm answers only "does the prompt
        # match the description on its own words". That is why a fixture-backed skill tends to
        # read `restricted <= invoke_rate` while fixture-less ones can read higher, and why
        # playwright-scaffold shows 1.00 free against 0.20 restricted. Second caveat: reps are
        # not applied to this arm, so it is n=5 however many reps the scored arms ran — two
        # decimals of a five-sample rate are three more than it can carry.
        "truncated": round(truncated / misses, 2) if misses else 0.0,
        "truncated_quiet": round(truncated_quiet / quiet, 2) if quiet else 0.0,
        "restricted": round(restricted_hits / restricted_total, 2),
        "lost_to": lost_to,
    }
    if lost_to:
        losses = ", ".join(f"{winner} x{n}" for winner, n in sorted(lost_to.items()))
        print(f"  [i] {name}: happy misses reached for {losses} instead", flush=True)
    # The recorded metric and this warning answer different questions, so they divide by
    # different things. `truncated` above asks "how much of the miss column is unexplained" —
    # a share of the misses. The warning asks "did truncation distort the score enough to be
    # worth re-measuring", and that is a share of the whole arm: one cut miss out of fifteen
    # moves invoke_rate by 0.067 no matter what fraction of the miss column it happens to be.
    # Dividing by misses here would fire at 100% on a 14/15 skill whose single miss timed out,
    # and a warning that fires on a 0.067 distortion is the "always on" failure this threshold
    # already survived once.
    for metric, cut, total, of in (
        ("invoke_rate", truncated, hits + misses, "happy"),
        ("false_fire", truncated_quiet, fires + quiet, "negative"),
    ):
        # Inclusive: at 15 samples a 3/15 truncation is exactly 0.20, and the ratchet trips at
        # 13/15 against a 15/15 baseline — so an exclusive bound leaves the one case where the
        # artifact alone can fail the gate with nothing printed to explain why.
        if total and cut / total >= 0.20:
            print(
                f"  [!] {name}: {cut}/{total} {of} samples were cut short — {metric} is "
                f"reporting SESSION_TIMEOUT or MAX_TURNS rather than the description",
                flush=True,
            )
    return result
