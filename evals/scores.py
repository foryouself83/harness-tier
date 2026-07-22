"""The eval baseline and the predicate that guards it.

Split from `run.py` because the two halves have opposite costs: producing a score spends
hours of rate-limit budget across hundreds of real CLI sessions, while judging one needs a
JSON file and a hash. Only the cheap half belongs in `pytest`.

Cheap is not the same as pure, and this module has been described as pure more than once.
`check` and `may_write` are: they take dicts and return a Verdict, touching nothing. `load`
and `description_sha` read from disk — `scores.json` and every `skills/*/SKILL.md`. What the
split actually guarantees is that nothing here spawns a session or reaches the network, which
is the property `pytest` needs; a test calling `description_sha` still needs the repo on disk.
"""

import hashlib
import json
import math
import re
from pathlib import Path
from typing import NamedTuple

import yaml

REPO = Path(__file__).resolve().parent.parent
SCORES = REPO / "evals/scores.json"

# This one stays live and data-independent. Whatever the right firing rate turns out to be, a
# skill that grabs more than a fifth of the prompts meant for its neighbours is wrong at any
# calibration.
MAX_FALSE_FIRE = 0.20

# The family-wise false-alarm budget across the whole skill set, per confirmed regression. The
# ratchet's per-run per-skill threshold is derived from it in `alpha_single`.
#
# There is no `MIN_INVOKE` floor here any more, and no `RATCHET_DELTA`. A global invoke-rate
# floor was circular — the 0.25 it once held was chosen after seeing the very distribution it
# then judged — and wrong in principle: skills fire at different proper rates by design
# (harness-authoring's autonomous reach is minor; its primary path is harness-init invoking
# it), which is why a per-skill `exempt_floor` had to be bolted on. Both are replaced by a
# per-skill `expect_invoke` declaration in cases.yaml and an exact-binomial ratchet. A fixed
# absolute delta was the second defect: binomial noise scales with p, so a constant 0.10 width
# was 0.78-0.87 sigma across the five mid-range skills and cried wolf ~20% of the time per run.
ALPHA_FAMILY = 0.05

# The baseline describes exactly one model. "opus" (a floating CLI alias) held this slot for a
# while and defeated its own comment: when the alias retargets, every re-measure silently
# compares a new model's k/n against an old model's — the measured spread on one case was 0/4
# vs 4/4 across models. Pin the full ID, stamp it per entry, and fail freshness on a mismatch
# exactly like description_sha.
MODEL = "claude-opus-4-8"


def alpha_single(n_skills: int) -> float:
    """Per-run trip threshold. Sidak over the skill family, then square-rooted because a fail
    requires two consecutive trips (the confirmation re-measure): two independent trips at
    sqrt(a) compound to a. So the per-run alpha is loose (~0.085 at n=7) while the family-wise
    rate after confirmation is ALPHA_FAMILY."""
    return (1 - (1 - ALPHA_FAMILY) ** (1 / n_skills)) ** 0.5


def binom_cdf(k: int, n: int, p: float) -> float:
    """Lower tail P(X <= k) for X ~ Binomial(n, p). Exact, pure stdlib via math.comb."""
    return sum(math.comb(n, i) * p**i * (1 - p) ** (n - i) for i in range(k + 1))


def ratchet_trips(k_new: int, n_new: int, k_base: int, n_base: int, alpha: float) -> bool:
    """Did the new measurement fall significantly below the recorded baseline?"""
    # Jeffreys-shrunk reference: (k + 0.5) / (n + 1). Treating the recorded rate as exact
    # breaks at p=1.00, where any miss becomes infinitely significant — the baseline is itself
    # a noisy measurement, and the shrink concedes exactly that. At a 15/15 base the shrink
    # tolerates 14/15 and only trips at <= 13.
    p_ref = (k_base + 0.5) / (n_base + 1)
    return binom_cdf(k_new, n_new, p_ref) < alpha


class Verdict(NamedTuple):
    level: str  # "ok" | "warn" | "confirm" | "fail"
    message: str


def parse_frontmatter(path: Path) -> dict:
    """The one frontmatter grammar for this repo's eval/test layers — the same regex was
    copied into four modules and the copies had already drifted on failure behaviour.
    scripts/harness_scaffold.py keeps its own on purpose: it ships to consumer hosts and
    must run without evals/ on the path. tests/test_skills.py keeps an assert-flavoured
    wrapper whose message contract differs; both are documented, everything else calls this.
    """
    text = path.read_text(encoding="utf-8")
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    if m is None:
        # Without a guard this is an AttributeError on None, which reads like a bug in the
        # harness rather than what it is: a skill whose frontmatter stopped parsing.
        raise ValueError(f"{path} has no frontmatter block")
    return yaml.safe_load(m.group(1))


def description_sha(name: str) -> str:
    """Hash the description *only*. Invocation is decided by the description, so demanding
    a re-measurement after every body edit would make the freshness check pure noise — and
    a noisy gate is one people learn to skip."""
    front = parse_frontmatter(REPO / f"skills/{name}/SKILL.md")
    return hashlib.sha256(front["description"].encode("utf-8")).hexdigest()[:12]


def load(path: Path | None = None) -> dict:
    path = path or SCORES
    if not path.exists():
        return {"skills": {}}
    return json.loads(path.read_text(encoding="utf-8"))


def check(name: str, entry: dict | None, sha: str, expect: float | None, n_skills: int) -> Verdict:
    # No global constant to fall back on: the gate refuses to operate on a skill that has not
    # declared what it expects — measured or not. Checking the entry first returned "warn" for
    # an unmeasured-and-undeclared skill, quietly bypassing the forcing function that replaced
    # the floor (spec §6: an undeclared skill FAILS).
    if expect is None:
        return Verdict("fail", f"{name}: declare expect_invoke and expect_why in cases.yaml")
    if entry is None:
        return Verdict("warn", f"{name}: not measured yet — run python -m evals.run")
    # The threat model is a hand-edited scores.json (see the lowered_from note below). A
    # missing key must name the skill and the fix, not surface as a bare KeyError.
    missing = [k for k in ("invoke_hits", "invoke_n", "false_hits", "false_n") if k not in entry]
    if missing:
        return Verdict("fail", f"{name}: entry is missing {missing} — re-measure")
    if entry.get("description_sha") != sha:
        return Verdict("fail", f"{name}: description changed since the score — re-measure")
    # The freshness pair: the sha says the score measured this description, the model says it
    # measured it on the model the gate is pinned to. Model identity swings a skill's rate
    # 0.0<->1.0 on the same case (measured), so a mismatched fingerprint is as stale as an
    # old sha.
    if entry.get("model") != MODEL:
        return Verdict(
            "fail",
            f"{name}: measured on model {entry.get('model')!r}, gate pinned to {MODEL!r} "
            f"— re-measure",
        )
    # The one data-independent floor. A committed all-zero baseline must never be green: if the
    # true rate is merely low, a re-measure will produce a nonzero, and this failure forces
    # exactly that re-measure rather than freezing a zero into the ratchet's reference.
    # Keyed on the integer hits, not the rounded rate — at a large enough n a single hit
    # rounds to 0.00 while not being zero.
    if entry["invoke_hits"] == 0:
        return Verdict("fail", f"{name}: invoke_rate is 0 — description never fires, re-measure")
    # Counts, not the rounded derived rate: the derived field can drift from the counts under
    # a hand edit, and at a reps-raised n a true rate in (0.20, 0.205] rounds down to a
    # passing 0.20. Same reason the zero floor above reads the integer hits.
    if entry["false_hits"] > MAX_FALSE_FIRE * entry["false_n"]:
        return Verdict(
            "fail",
            f"{name}: false_fire {entry['false_hits']}/{entry['false_n']} > {MAX_FALSE_FIRE}",
        )
    # Not reachable through the CLI, and deliberately kept anyway. `run.py` writes the two
    # keys together and argparse refuses `--accept` without `--reason`, so no supported path
    # produces this state — which is exactly why it is worth checking. The state it catches is
    # a hand-edited `scores.json`: someone lowering a committed number and deleting the
    # justification, the one edit that turns the ratchet's audit trail back into a bare score.
    # Do not delete this as dead code; the CLI is not the only thing that writes this file.
    if "lowered_from" in entry and not entry.get("lowered_reason"):
        return Verdict("fail", f"{name}: lowered_from recorded with no lowered_reason")
    # A warn, not a fail: n=15 cannot support hard-failing an aspiration, and a suite red by
    # default stops being read. The declaration gap is information; the *ratchet* (may_write)
    # is the enforcement. `expect_invoke` is a design-intent claim, deliberately not tuned to
    # the baseline, so a significant shortfall means the description needs work.
    if binom_cdf(entry["invoke_hits"], entry["invoke_n"], expect) < alpha_single(n_skills):
        return Verdict(
            "warn",
            f"{name}: invoke_rate {entry['invoke_rate']:.2f} is significantly below its declared "
            f"expectation {expect:.2f} — the description needs work",
        )
    return Verdict("ok", f"{name}: ok")


def may_write(
    name: str,
    new: dict,
    old: dict | None,
    accepted: bool,
    confirmed: bool = False,
    *,
    n_skills: int,
) -> Verdict:
    """The ratchet, enforced where the comparison exists — at write time. Once a score has
    been reached it becomes the reference; falling significantly below it is a deliberate act
    that leaves a record in the diff.

    "Significantly" is an exact one-sided binomial test against the Jeffreys-shrunk baseline
    rate (see `ratchet_trips`), at `alpha_single(n_skills)` — noise scaling with p, not a fixed
    width. A rise never trips (the test is one-sided low-tail).

    A first drop returns `confirm`, not `fail`: the caller re-measures that one skill and calls
    again with `confirmed=True`. Two consecutive trips are what a fail requires, and
    `alpha_single` already carries the sqrt that makes them compound to the family bound.

    The escape hatch exists because a drop is not always a regression: narrowing a description
    to cut `false_fire` can cost a little `invoke_rate` and still be an improvement. A hard
    ratchet blocks that and ends with the gate disabled."""
    if old is None or accepted or old.get("model") != new.get("model"):
        # A model change makes old and new k/n incomparable — the exact binomial would
        # attribute model drift to the description. MODEL is a reviewed code constant, so
        # crossing it is a re-baseline, not an escape hatch.
        return Verdict("ok", f"{name}: writing")
    tripped = ratchet_trips(
        new["invoke_hits"],
        new["invoke_n"],
        old["invoke_hits"],
        old["invoke_n"],
        alpha_single(n_skills),
    )
    if not tripped:
        return Verdict("ok", f"{name}: writing")
    move = f"{old['invoke_rate']:.2f} -> {new['invoke_rate']:.2f}"
    if not confirmed:
        return Verdict("confirm", f"{name}: invoke_rate {move} tripped the ratchet — re-measuring")
    return Verdict(
        "fail",
        f"{name}: invoke_rate {move}, confirmed by a second measurement. Fix the "
        f"description, or accept it with --skill {name} --accept --reason '...'",
    )
