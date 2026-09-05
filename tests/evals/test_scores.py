import warnings

import pytest

import evals.scores as scores
from tests.evals._helpers import CASES, EXPECT, N_SKILLS, OK, REPO, SKILLS


def _entry(**overrides) -> dict:
    """A gate-passing entry with per-test overrides — the check() fixtures grew one key at a
    time (model, the count pairs) and inline dicts made every addition a sweep."""
    return {**OK, **overrides}


def test_alpha_single_is_a_family_bound_split_across_the_confirmation_re_measure():
    """Sidak over the 7-skill family gives a per-skill alpha; the square root splits it across
    the two consecutive trips a fail requires, so two independent trips at sqrt(a) compound
    back to the family a. Both fixed points were recomputed this session."""
    assert scores.alpha_single(7) == pytest.approx(0.08544, abs=1e-5)
    # Squaring undoes the sqrt, landing on the per-skill Sidak alpha the family bound implies.
    assert scores.alpha_single(7) ** 2 == pytest.approx(0.00730, abs=1e-5)


def test_binom_cdf_is_the_lower_tail():
    assert scores.binom_cdf(15, 15, 0.8) == pytest.approx(1.0)
    assert scores.binom_cdf(0, 15, 0.5) == pytest.approx(0.5**15)
    cdfs = [scores.binom_cdf(k, 15, 0.6) for k in range(16)]
    assert cdfs == sorted(cdfs), "binom_cdf must be non-decreasing in k"


@pytest.mark.parametrize(
    "k_base,trips_at_or_below,first_clear",
    [
        (10, 6, 7),
        (9, 5, 6),
        (8, 4, 5),
        # The Jeffreys boundary and the regression guard for the retracted claim: a perfect
        # baseline tolerates 14/15 and only trips at 13 — the recorded rate is itself noisy,
        # and treating 1.00 as exact would make any single miss infinitely significant.
        (15, 13, 14),
        (2, 0, 1),
    ],
)
def test_ratchet_trip_table(k_base: int, trips_at_or_below: int, first_clear: int):
    """Every boundary recomputed this session against the shipped binomial at n=15 and
    alpha=alpha_single(7). binom_cdf is monotone in k, so a trip at the boundary implies a
    trip at everything below it; the row asserts both the last trip and the first clear."""
    alpha = scores.alpha_single(7)
    for k_new in range(trips_at_or_below + 1):
        assert scores.ratchet_trips(k_new, 15, k_base, 15, alpha), (k_base, k_new)
    assert not scores.ratchet_trips(first_clear, 15, k_base, 15, alpha), (k_base, first_clear)


def test_a_rise_never_trips_the_low_tail_ratchet():
    """The test is one-sided: a measurement at or above the reference is never a regression."""
    alpha = scores.alpha_single(7)
    assert not scores.ratchet_trips(12, 15, 4, 15, alpha)
    assert not scores.ratchet_trips(15, 15, 10, 15, alpha)


def test_the_gate_ignores_per_skill_provenance_keys():
    """`measured_at`/`reps` moved onto each entry so an incremental run cannot claim its own
    sample size for six skills it never measured. The gate must stay indifferent to them —
    if `check` ever grew strict about the key set, moving provenance would break it."""
    assert scores.check(
        "integration", {**OK, "measured_at": "2026-07-19", "reps": 3}, "x", EXPECT, N_SKILLS
    ).level == ("ok")


def test_unmeasured_skill_warns_rather_than_failing():
    """Failing here would paint `uv run pytest` red from the day the harness lands, and a
    suite that is red by default stops being read as a signal at all. The same holds for
    every newly added skill."""
    assert scores.check("integration", None, "x", EXPECT, N_SKILLS).level == "warn"


def test_the_gate_surfaces_a_warning_rather_than_passing_in_silence():
    """A warn that prints nothing is a pass, and an unmeasured skill would look measured."""
    with pytest.warns(UserWarning, match="not measured"):
        gate("integration", None, "x", EXPECT, N_SKILLS)


def test_a_healthy_measurement_passes():
    assert scores.check("integration", OK, "x", EXPECT, N_SKILLS).level == "ok"


def test_a_stale_measurement_fails():
    """Without this the harness is decorative: edit the description, keep the old green
    number, merge. The score would no longer describe the skill it is attached to."""
    v = scores.check("integration", OK, "different-sha", EXPECT, N_SKILLS)
    assert v.level == "fail"
    assert "re-measure" in v.message


def test_an_all_zero_baseline_always_fails():
    """The one data-independent floor. A committed 0/15 must never be green: if the true rate
    is merely low, a re-measure will produce a nonzero and this failure forces exactly that
    re-measure. It bites with the declaration present and without it."""
    zero = {**OK, "invoke_rate": 0.0, "invoke_hits": 0, "invoke_n": 15}
    assert scores.check("integration", zero, "x", EXPECT, N_SKILLS).level == "fail"
    assert scores.check("integration", zero, "x", None, N_SKILLS).level == "fail"


def test_an_undeclared_skill_fails_rather_than_defaulting():
    """The gate refuses to operate on a skill with no `expect_invoke` rather than substituting
    a global constant — the declaration is the forcing function that replaced the floor."""
    v = scores.check("integration", OK, "x", None, N_SKILLS)
    assert v.level == "fail"
    assert "expect_invoke" in v.message


def test_a_measurement_far_below_its_declaration_warns_not_fails():
    """n=15 cannot support hard-failing an aspiration, and a suite red by default stops being
    read — so the declaration gap is a warn (information), not a fail. The ratchet is the
    enforcement. 4/15 against 0.70 is far enough below to warn; 8/15 clears it."""
    low = {**OK, "invoke_rate": 0.27, "invoke_hits": 4, "invoke_n": 15}
    assert scores.check("integration", low, "x", 0.70, N_SKILLS).level == "warn"
    ok = {**OK, "invoke_rate": 0.53, "invoke_hits": 8, "invoke_n": 15}
    assert scores.check("integration", ok, "x", 0.70, N_SKILLS).level == "ok"


@pytest.mark.parametrize("name", SKILLS)
def test_a_programmatic_reach_claim_names_a_real_caller(name: str):
    """`reached_programmatically` now grounds a low `expect_invoke` (harness-authoring's 0.10)
    rather than a floor exemption: the autonomous rate is only a liveness check because the
    primary path is another skill invoking it. If cases.yaml claims that path, some other
    shipped skill has to invoke it — otherwise the claim is stale."""
    if not CASES["skills"][name].get("reached_programmatically"):
        return
    callers = [
        p.parent.name
        for p in REPO.glob("skills/*/SKILL.md")
        if p.parent.name != name and f"Skill: {name}" in p.read_text(encoding="utf-8")
    ]
    assert callers, (
        f"{name}: cases.yaml declares reached_programmatically, but no shipped skill "
        f"invokes it. Either the claim is stale or the caller was removed."
    )


def test_the_false_fire_ceiling_fails():
    over = _entry(false_hits=4, false_n=15, false_fire=0.27)
    v = scores.check("integration", over, "x", EXPECT, N_SKILLS)
    assert v.level == "fail"
    assert "false_fire" in v.message


def test_false_fire_ceiling_reads_the_raw_counts_not_the_rounded_rate():
    """The derived two-decimal field can drift from the counts under a hand edit — the very
    threat the lowered_from check documents — and at a reps-raised n a true rate in
    (0.20, 0.205] rounds down to a passing 0.20."""
    lying = _entry(false_hits=5, false_n=15, false_fire=0.0)  # derived field says clean
    v = scores.check("integration", lying, "x", EXPECT, N_SKILLS)
    assert v.level == "fail"
    assert "false_fire" in v.message


def test_check_order_fails_an_undeclared_skill_even_when_unmeasured():
    """Spec §6: an undeclared skill makes the gate refuse to judge and FAIL — measured or
    not. Returning the not-measured warn first quietly bypassed the forcing function."""
    v = scores.check("ghost", None, "whatever", None, n_skills=N_SKILLS)
    assert v.level == "fail"
    assert "expect_invoke" in v.message


def test_check_fails_a_missing_count_key_with_a_verdict_not_a_keyerror():
    """The module's stated threat model is a hand-edited scores.json — a bare KeyError names
    neither the skill nor the fix."""
    trimmed = {"description_sha": "x", "invoke_rate": 0.5}
    v = scores.check("integration", trimmed, "x", EXPECT, N_SKILLS)
    assert v.level == "fail"
    assert "invoke_hits" in v.message


def test_a_model_mismatch_fails_like_a_stale_sha():
    """The baseline is a fact about one model (0/4 vs 4/4 on the same case, measured). A
    mismatched fingerprint is as stale as an old sha and forces the same re-measure."""
    v = scores.check("integration", _entry(model="claude-sonnet-5"), "x", EXPECT, N_SKILLS)
    assert v.level == "fail"
    assert "model" in v.message


def test_may_write_skips_the_ratchet_across_a_model_change():
    """Ratcheting a new model's k/n against an old model's attributes model drift to the
    description. MODEL is a reviewed code constant, so crossing it re-baselines instead —
    not an escape hatch."""
    new = _entry(invoke_hits=0, invoke_n=15, invoke_rate=0.0)
    old = _entry(invoke_hits=15, invoke_n=15, invoke_rate=1.0, model="claude-sonnet-5")
    v = scores.may_write("integration", new, old, accepted=False, n_skills=N_SKILLS)
    assert v.level == "ok"


def test_an_accepted_drop_needs_a_recorded_reason():
    entry = {**OK, "lowered_from": 0.95}
    assert scores.check("integration", entry, "x", EXPECT, N_SKILLS).level == "fail"
    entry["lowered_reason"] = "traded for a lower false_fire"
    assert scores.check("integration", entry, "x", EXPECT, N_SKILLS).level == "ok"


# Base 10/15 (invoke_rate 0.67). By the trip table this trips at k_new <= 6 and clears at 7.
RATCHET_OLD = {"invoke_rate": 0.67, "invoke_hits": 10, "invoke_n": 15, "false_fire": 0.0}
RATCHET_TRIP = {"invoke_rate": 0.40, "invoke_hits": 6, "invoke_n": 15, "false_fire": 0.0}


def test_a_first_drop_asks_for_confirmation_rather_than_failing():
    """A single reading cannot separate a real regression from binomial noise at n=15, so the
    first trip asks for a re-measure rather than failing. alpha_single already carries the
    sqrt that makes the two consecutive trips a fail requires compound to the family bound."""
    assert (
        scores.may_write("integration", RATCHET_TRIP, RATCHET_OLD, accepted=False, n_skills=7).level
        == "confirm"
    )


def test_a_confirmed_drop_fails_and_acceptance_overrides_it():
    assert (
        scores.may_write(
            "integration", RATCHET_TRIP, RATCHET_OLD, accepted=False, confirmed=True, n_skills=7
        ).level
        == "fail"
    )
    assert (
        scores.may_write("integration", RATCHET_TRIP, RATCHET_OLD, accepted=True, n_skills=7).level
        == "ok"
    )


def test_the_ratchet_tolerates_noise_and_welcomes_a_rise():
    """A drop that does not clear the significance bar is written without a fuss (7/15 from a
    10/15 base clears the trip), and a rise is never a regression."""
    within = {"invoke_rate": 0.47, "invoke_hits": 7, "invoke_n": 15, "false_fire": 0.0}
    higher = {"invoke_rate": 1.0, "invoke_hits": 15, "invoke_n": 15, "false_fire": 0.0}
    assert scores.may_write("integration", within, RATCHET_OLD, False, n_skills=7).level == "ok"
    assert scores.may_write("integration", higher, RATCHET_OLD, False, n_skills=7).level == "ok"


def gate(name: str, entry: dict | None, sha: str, expect: float | None, n_skills: int) -> None:
    """Apply a verdict: fail loudly, warn visibly, pass quietly."""
    v = scores.check(name, entry, sha, expect, n_skills)
    if v.level == "fail":
        pytest.fail(v.message)
    if v.level == "warn":
        warnings.warn(v.message, stacklevel=2)


def test_every_skill_declares_its_expectation():
    """The declarations are the gate's forcing function — a skill with no `expect_invoke`
    fails the gate rather than falling back to a global constant, and `expect_why` is the
    design-intent prose that must accompany it."""
    for name in SKILLS:
        entry = CASES["skills"][name]
        expect = entry.get("expect_invoke")
        assert isinstance(expect, int | float) and 0 < expect <= 1, f"{name}: expect_invoke"
        assert isinstance(entry.get("expect_why"), str) and entry["expect_why"].strip(), (
            f"{name}: expect_why"
        )


def test_the_committed_baseline_passes_the_gate():
    """The gate itself, applied to the file that gets committed. Fail is the only hard
    state; warns surface through pytest's warning summary (integration and flow warn today —
    both measured significantly below their declared expectation). The warn set is
    deliberately NOT pinned: a ratchet-approved dip adds a warn, an improvement removes one,
    an --accept'ed drop still warns — and a suite that turns red on any of those teaches
    people to edit the test instead of reading the warning. Warn is information; the ratchet
    is the enforcement (spec §6)."""
    baseline = scores.load()
    for name in SKILLS:
        gate(
            name,
            baseline.get("skills", {}).get(name),
            scores.description_sha(name),
            CASES["skills"][name].get("expect_invoke"),
            len(SKILLS),
        )
