"""`gate_evidence.invalidate_on_edit`: the host's own answer, read line by line."""

from pathlib import Path

import pytest

from tests.invalidate_gate_markers._helpers import (
    BASH,
    MARKERS,
    NL,
    flow,
    payload,
    repo,
    run,
)

pytestmark = pytest.mark.skipif(BASH is None, reason="a repo-visible bash is required")


def _switch(project: Path, body: str) -> None:
    cfg = project / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "flow-config.yaml").write_text(body, encoding="utf-8")


def test_the_host_can_keep_its_markers_through_an_edit(project: Path):
    """This hook is registered by the PLUGIN, so a version bump alone arms it on every
    consumer - no `/flow-init` re-run, no step where anyone agreed to it. The team that is
    affected is the one that has to be able to say no."""
    _switch(project, "gate_evidence:" + chr(10) + "  invalidate_on_edit: false" + chr(10))
    run(project, payload(str(project / "src" / "a.py")))
    for name in MARKERS:
        assert (flow(project) / name).exists(), name


def test_the_switch_has_to_be_asked_for(project: Path):
    """Armed is the default, and `rules/risk-tiers.md` promises consumers that everything which
    is not the switch leaves it armed. Each shape below is a way someone reaches for it and
    misses: no config, the value spelled true, a line commented out mid-experiment, the YAML
    falses that are not this reader's word, a key whose name merely ends in the block's, and
    the switch written where `yaml.safe_load` would not read it as this setting either —
    under a nested key, inside a block scalar, overridden by a later duplicate, or missing
    one of the two spaces YAML needs to see a value and a comment at all. A header that
    carries a flow mapping or a block scalar opens no block, so nothing under it is read.
    Inferring "off" from a file that does not say so is the gate turning itself off in silence."""
    for body in (
        None,
        "gate_evidence:" + NL + "  invalidate_on_edit: true" + NL,
        "gate_evidence:" + NL + "  # invalidate_on_edit: false" + NL,
        "gate_evidence:" + NL + "  invalidate_on_edit: no" + NL,
        "gate_evidence:" + NL + "  invalidate_on_edit: off" + NL,
        "gate_evidence:" + NL + "  invalidate_on_edit: False" + NL,
        "invalidate_on_edit: false" + NL,
        "doc_sync:" + NL + "  invalidate_on_edit: false" + NL,
        "foo_gate_evidence:" + NL + "  invalidate_on_edit: false" + NL,
        "gate_evidence:" + NL + "  nested:" + NL + "    invalidate_on_edit: false" + NL,
        "gate_evidence:" + NL + "  note: |" + NL + "    invalidate_on_edit: false" + NL,
        "gate_evidence:"
        + NL
        + "  invalidate_on_edit: false"
        + NL
        + "  invalidate_on_edit: true"
        + NL,
        "gate_evidence:" + NL + "  invalidate_on_edit: false# keep" + NL,
        "gate_evidence:" + NL + "  invalidate_on_edit:false" + NL,
        "gate_evidence: |" + NL + "  invalidate_on_edit: false" + NL,
        "gate_evidence: {invalidate_on_edit: false}" + NL,
        "gate_evidence:"
        + NL
        + "  invalidate_on_edit: false"
        + NL
        + "gate_evidence:"
        + NL
        + "  other: 1"
        + NL,
        "gate_evidence:"
        + NL
        + "  invalidate_on_edit: true"
        + NL
        + "doc_sync:"
        + NL
        + "  invalidate_on_edit: false"
        + NL,
    ):
        for name in MARKERS:
            (flow(project) / name).touch()
        if body is not None:
            _switch(project, body)
        run(project, payload(str(project / "src" / "a.py")))
        for name in MARKERS:
            assert not (flow(project) / name).exists(), (body, name)


def test_the_switch_survives_the_shapes_a_real_config_has(project: Path):
    """The reader is line-based, so the shapes a hand-edited YAML file carries have to
    reach it: CRLF from a Windows editor, comments above and beside the key, a comment at
    column 0 that must not close the block it sits in, other blocks before and after, a
    later duplicate that wins the way YAML resolves one, and a file the YAML parser itself
    would reject — that last one is the point of reading lines at all, since a host whose
    config broke elsewhere still gets its answer."""
    bodies = (
        "gate_evidence:" + chr(13) + NL + "  invalidate_on_edit: false" + chr(13) + NL,
        "gate_evidence:"
        + NL
        + "  # keep them until the commit"
        + NL
        + "  invalidate_on_edit: false"
        + NL,
        "branches:"
        + NL
        + "  integration: dev"
        + NL
        + "gate_evidence:"
        + NL
        + "  invalidate_on_edit: false"
        + NL
        + "doc_sync:"
        + NL
        + "  index: CLAUDE.md"
        + NL,
        "branches: [oops" + NL + "gate_evidence:" + NL + "  invalidate_on_edit: false" + NL,
        "gate_evidence:" + NL + "# trying this out" + NL + "  invalidate_on_edit: false" + NL,
        "gate_evidence:" + NL + "  invalidate_on_edit: false  # keep them until the commit" + NL,
        "gate_evidence:"
        + NL
        + "  invalidate_on_edit: true"
        + NL
        + "  invalidate_on_edit: false"
        + NL,
    )
    for body in bodies:
        for name in MARKERS:
            (flow(project) / name).touch()
        _switch(project, body)
        run(project, payload(str(project / "src" / "a.py")))
        for name in MARKERS:
            assert (flow(project) / name).exists(), (body, name)


def test_each_block_sets_its_own_child_indent(project: Path):
    """The block's keys sit at the indent ITS OWN first key set, so a depth carried over
    from an earlier `gate_evidence:` cannot decide what counts as a key later. YAML resolves
    the duplicated block to the last one, which is the one holding the switch; carrying the
    first block's deeper indent forward would put that switch below the depth being looked
    at, and the host that asked to keep its markers would go on losing them."""
    body = (
        "gate_evidence:"
        + NL
        + "    unrelated: 1"
        + NL
        + "doc_sync:"
        + NL
        + "  index: CLAUDE.md"
        + NL
        + "gate_evidence:"
        + NL
        + "  invalidate_on_edit: false"
        + NL
    )
    _switch(project, body)
    run(project, payload(str(project / "src" / "a.py")))
    for name in MARKERS:
        assert (flow(project) / name).exists(), name


def test_one_repo_opting_out_does_not_speak_for_another(project: Path, tmp_path: Path):
    """The switch is the host answering for the evidence it pays to re-earn, so it is asked of
    each tree this edit outdated. A session in an opted-out project editing a file in a repo that
    never opted out would otherwise leave that repo's markers standing on the strength of a
    setting nobody there wrote."""
    other = repo(tmp_path / "other")
    _switch(project, "gate_evidence:" + NL + "  invalidate_on_edit: false" + NL)
    edited = other / "src" / "a.py"
    edited.parent.mkdir(parents=True, exist_ok=True)
    edited.write_text("x", encoding="utf-8")
    run(project, payload(str(edited)))
    for name in MARKERS:
        assert not (flow(other) / name).exists(), f"{name}: the edited repo kept it"
        assert (flow(project) / name).exists(), f"{name}: the opted-out project lost it"
