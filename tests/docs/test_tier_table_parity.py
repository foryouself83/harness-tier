"""USAGE's tier table is the only thing enforcing `tiers.*.superpowers`.

No script and no other test reads that field — `/flow` and the operator read the policy
and the docs instead, so a twin that disagrees with `flow-tiers.yaml` sends a promotion
through the whole design->plan->implement pipeline over already-built work. Both twins
are equally stale when that happens, so `doc-sync` sees no drift to report.
"""

import re
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TWINS = ("USAGE.md", "USAGE.ko.md")
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


def test_every_tier_appears_in_both_twins():
    tiers = set(_policy_superpowers())
    for doc in TWINS:
        assert set(_table_superpowers(doc)) == tiers, doc


def test_twins_agree_with_the_policy():
    policy = _policy_superpowers()
    for doc in TWINS:
        assert _table_superpowers(doc) == policy, doc
