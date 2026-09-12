"""The extraction is a move, not a rewrite: both module surfaces must agree.

`harness_scaffold` re-exports rather than redefines — a second definition would drift
the moment either copy is touched, and the drift is silent because both pass their own
tests.
"""

import scripts._md_anchors as ma
import scripts.harness_scaffold as hs


def test_harness_scaffold_reexports_the_moved_names():
    for name in ("_slugify", "_has_anchor", "_strip_frontmatter", "_strip_code"):
        assert getattr(hs, name) is getattr(ma, name), name


def test_module_defines_no_second_copy():
    src = (ma.__file__, hs.__file__)
    assert src[0] != src[1]
    body = open(hs.__file__, encoding="utf-8").read()
    for name in ("def _slugify", "def _has_anchor", "def _strip_frontmatter", "def _strip_code"):
        assert name not in body, f"{name} still defined in harness_scaffold"


def test_slugify_still_handles_the_hard_cases():
    assert ma._slugify("Step 1 — Classify the task") == "step-1--classify-the-task"
    assert ma._slugify("flow_gate_check") == "flow_gate_check"
    assert ma._slugify("Map<K,V>") == "mapkv"


def test_has_anchor_reads_an_explicit_id():
    assert ma._has_anchor('<a id="fr-payment-001"></a>**FR-PAYMENT-001**', "fr-payment-001")
    assert not ma._has_anchor("# Heading\n", "fr-payment-001")
