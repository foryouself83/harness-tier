"""`flow-tiers.yaml`'s `tiers.*.superpowers` is restated in docs alone, and no code reads it.

`/flow` and the operator read the policy and the docs instead, so a copy that disagrees
with `flow-tiers.yaml` sends a promotion through the whole design->plan->implement
pipeline over already-built work. Every copy goes stale together, so `doc-sync` sees no
drift to report.

Pinned here: both USAGE tables and risk-tiers Step 2 — the copy `flow-tiers.yaml` names as
the SSOT, and the one an agent reads, being the only rule injected at SessionStart. Left
unpinned: the prose restatements under that table and at `/flow`'s Docs and Dev headings,
which carry a tier per sentence rather than in a grid.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TWINS = ("USAGE.md", "USAGE.ko.md")
RULE = "rules/risk-tiers.md"
MARK = {"✓": True, "✗": False}


def _policy_superpowers() -> dict[str, bool]:
    policy = yaml.safe_load((ROOT / "flow-tiers.yaml").read_text(encoding="utf-8"))
    return {name: tier["superpowers"] for name, tier in policy["tiers"].items()}


def _table_superpowers(doc: str) -> dict[str, bool]:
    """The `superpowers` cell per tier row, read off the one table that carries the column."""
    found: dict[str, bool] = {}
    for line in (ROOT / doc).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*`([a-z]+)`\s*\|[^|]*\|\s*(.)\s*\|", line)
        if m and m.group(2) in MARK:
            found[m.group(1)] = MARK[m.group(2)]
    return found


def _rule_superpowers() -> dict[str, bool]:
    """Step 2's table — bold tier names and a worded cell, so it needs its own reader."""
    found: dict[str, bool] = {}
    for line in (ROOT / RULE).read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\|\s*\*\*([A-Za-z]+)\*\*\s*\|\s*(ON|OFF)\b", line)
        if m:
            found[m.group(1).lower()] = m.group(2) == "ON"
    return found


def test_every_tier_appears_in_each_copy():
    tiers = set(_policy_superpowers())
    for doc in TWINS:
        assert set(_table_superpowers(doc)) == tiers, doc
    assert set(_rule_superpowers()) == tiers, RULE


def test_every_copy_agrees_with_the_policy():
    policy = _policy_superpowers()
    for doc in TWINS:
        assert _table_superpowers(doc) == policy, doc
    assert _rule_superpowers() == policy, RULE
