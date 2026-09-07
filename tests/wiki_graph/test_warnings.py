from scripts.wiki_graph import _safe_int, build_graph, collect_warnings, undirected_adjacency
from tests.wiki_graph._helpers import _mk, _wiki


def test_adjacency_ignores_direction():
    nodes = [_mk("b.x", {"related": ["a.x"]}, "docs/b.md"), _mk("a.x", path="docs/a.md")]
    adj = undirected_adjacency(build_graph(nodes))
    assert "b.x" in adj["a.x"] and "a.x" in adj["b.x"]


def test_adjacency_drops_dangling_targets():
    # Carrying an id that does not exist into the adjacency makes two nodes pointing at the
    # same typo count as connected for orphan detection — a node unreachable from the index
    # then looks reachable.
    nodes = [
        _mk("a.x", {"related": ["ghost.id"]}, "docs/a.md"),
        _mk("b.x", {"related": ["ghost.id"]}, "docs/b.md"),
    ]
    adj = undirected_adjacency(build_graph(nodes))
    assert "ghost.id" not in adj
    assert adj["a.x"] == [] and adj["b.x"] == []


def test_orphan_warns():
    nodes = [
        _mk("index", path="docs/index.md"),
        _mk("lonely.x", path="docs/lonely.md"),
    ]
    warns = collect_warnings(_wiki(), nodes, build_graph(nodes))
    assert any("lonely.x" in w and "orphan" in w for w in warns)


def test_node_reachable_from_index_is_not_orphan():
    nodes = [
        _mk("index", {"related": ["a.x"]}, "docs/index.md"),
        _mk("a.x", {"related": ["index"]}, "docs/a.md"),
    ]
    assert collect_warnings(_wiki(), nodes, build_graph(nodes)) == []


def test_max_lines_warns():
    node = _mk("a.x", path="docs/a.md")
    node["line_count"] = 500
    nodes = [_mk("index", {"related": ["a.x"]}, "docs/index.md"), node]
    node["front"]["related"] = ["index"]
    warns = collect_warnings(_wiki(max_lines=400), nodes, build_graph(nodes))
    assert any("500" in w and "docs/a.md" in w for w in warns)


def test_max_lines_zero_disables_the_check():
    node = _mk("index", path="docs/index.md")
    node["line_count"] = 9999
    assert collect_warnings(_wiki(max_lines=0), [node], build_graph([node])) == []


def test_rule_promotion_threshold_warns():
    nodes = [_mk("index", path="docs/index.md")]
    for i in range(3):
        nodes.append(
            _mk(f"defect.d{i}", {"affects": ["index"], "tags": ["auth"]}, f"docs/defects/d{i}.md")
        )
    warns = collect_warnings(_wiki(), nodes, build_graph(nodes))
    assert any("auth" in w and "Rule" in w for w in warns)


def test_rule_promotion_silent_when_already_promoted():
    nodes = [_mk("index", path="docs/index.md")]
    for i in range(3):
        nodes.append(
            _mk(
                f"defect.d{i}",
                {
                    "affects": ["index"],
                    "tags": ["auth"],
                    "promoted_to_rule": "rules/x.md" if i == 0 else None,
                },
                f"docs/defects/d{i}.md",
            )
        )
    assert not any("Rule" in w for w in collect_warnings(_wiki(), nodes, build_graph(nodes)))


def test_safe_int_handles_non_numeral_strings():
    assert _safe_int("abc") == 0
    assert _safe_int("many") == 0
    assert _safe_int("42") == 42
    assert _safe_int(42) == 42
    assert _safe_int(0.0) == 0
    assert _safe_int("0") == 0
    assert _safe_int(None) == 0
    assert _safe_int("xyz", default=100) == 100


def test_index_not_a_node_skips_per_node_orphan_check():
    # With the index not resolving to a node there is no origin to compute reachability from,
    # so no individual node may be called an orphan.
    nodes = [
        _mk("a.x", path="docs/a.md"),
        _mk("b.x", path="docs/b.md"),
    ]
    warns = collect_warnings(_wiki(index="docs/missing.md"), nodes, build_graph(nodes))
    assert not any("'a.x'" in w or "'b.x'" in w for w in warns)


def test_index_not_a_node_warns_the_check_is_off():
    # With the wiki enabled and the index not resolving to a node, the operator has to learn
    # that orphan detection is switched off — as a warning, not a block.
    nodes = [_mk("a.x", path="docs/a.md")]
    warns = collect_warnings(_wiki(index="docs/missing.md"), nodes, build_graph(nodes))
    assert any("docs/missing.md" in w for w in warns)


def test_index_not_a_node_is_silent_when_there_are_no_nodes():
    # No nodes at all means nothing to check: an empty wiki gets no noise.
    warns = collect_warnings(_wiki(index="docs/missing.md"), [], build_graph([]))
    assert warns == []


def test_node_linked_to_but_not_from_is_not_orphan():
    nodes = [
        _mk("index", path="docs/index.md"),
        _mk("a.x", {"related": ["index"]}, "docs/a.md"),
    ]
    warns = collect_warnings(_wiki(), nodes, build_graph(nodes))
    assert not any("orphan" in w for w in warns)


def _sources_warns(nodes):
    """Only this warning. Matching on 'sds' alone would also catch the orphan line, which
    names the same path — every quiet assertion below would then pass on the wrong warning."""
    warns = collect_warnings(_wiki(), nodes, build_graph(nodes))
    return [w for w in warns if "sds 문서인데 sources 값이" in w]


def test_sds_node_without_sources_warns():
    nodes = [
        _mk("index", path="docs/index.md"),
        _mk("sds.readme", {"tags": ["sds"]}, "docs/sds/README.md"),
    ]
    assert any("docs/sds/README.md" in w for w in _sources_warns(nodes))


def test_sds_node_with_empty_sources_is_quiet():
    # `sources: {}` is the author saying "no code to map yet" — the shape a greenfield SDS
    # ships with. Warning on it would fire on every generated design doc, forever, with the
    # only remedy the doc-sync step explicitly forbids (inventing a path).
    node = _mk("sds.readme", {"tags": ["sds"], "sources": {}}, "docs/sds/README.md")
    assert _sources_warns([node]) == []


def test_sds_node_with_null_sources_warns():
    # `sources:` with nothing after it is YAML null — an edit someone stopped halfway, not
    # the empty-map statement. `validate_structure` lets None pass too, so reading it as
    # "declared" leaves the node invisible with nothing said anywhere.
    node = _mk("sds.readme", {"tags": ["sds"], "sources": None}, "docs/sds/README.md")
    assert any("docs/sds/README.md" in w for w in _sources_warns([node]))


def test_sds_node_with_list_sources_is_quiet():
    # A list is the wrong shape, but `validate_structure` already blocks it with its own
    # message, and `--nodes-for` does read a list — so this warning's text would be untrue
    # and the one mistake would be reported twice.
    node = _mk("sds.readme", {"tags": ["sds"], "sources": ["src/a.py"]}, "docs/sds/README.md")
    assert _sources_warns([node]) == []


def test_sds_tag_is_read_from_a_bare_string():
    # `tags: sds` (a scalar, not a list) is valid YAML a human writes. Without _as_list the
    # membership test runs against the string and "sds" in "sds" is coincidentally true —
    # but `tags: sdsx` would then match too. Pin the scalar path.
    node = _mk("sds.readme", {"tags": "sds"}, "docs/sds/README.md")
    assert any("docs/sds/README.md" in w for w in _sources_warns([node]))


def test_a_substring_tag_does_not_count_as_sds():
    # Scalar, not a list, and deliberately so: `_as_list("sdsx")` is `["sdsx"]`, which does
    # not contain "sds". Reading the raw value instead makes the membership test a SUBSTRING
    # test — `"sds" in "sdsx"` is true — and any tag containing the three letters warns.
    node = _mk("x.readme", {"tags": "sdsx"}, "docs/x/README.md")
    assert _sources_warns([node]) == []


def test_a_non_node_is_never_warned_about():
    # No wiki_id means not a wiki node. Its front matter is not the author's wiki claim, so
    # reporting it is the noise the marker suppression elsewhere exists to avoid.
    node = {"id": "", "path": "docs/sds/README.md", "line_count": 3, "front": {"tags": ["sds"]}}
    assert _sources_warns([node]) == []


def test_sds_node_with_sources_is_quiet():
    node = _mk("sds.readme", {"tags": ["sds"], "sources": {"src/a.py": None}}, "docs/sds/README.md")
    assert _sources_warns([node]) == []


def test_non_sds_node_without_sources_is_quiet():
    # The whole point of the tag narrowing: requirements and onboarding pages map to no code
    # path, and warning on them is the permanent noise that makes the block unread.
    node = _mk("srs.readme", {"tags": ["srs"]}, "docs/srs/README.md")
    assert _sources_warns([node]) == []
