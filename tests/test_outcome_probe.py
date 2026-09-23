import json
from pathlib import Path

import scripts.skill_sandbox as sandbox
from evals import outcome_probe
from evals.outcome_probe import golden_cases, parse_stream_tier, read_marker_tier


def _assistant(text: str) -> str:
    block = {"type": "text", "text": text}
    return json.dumps({"type": "assistant", "message": {"content": [block]}})


def test_parse_stream_tier_reads_last_classification():
    stream = "\n".join(
        [
            _assistant("thinking..."),
            _assistant("## Tier Classification\n- Tier: DEV\n- Reason: touches .py"),
        ]
    )
    assert parse_stream_tier(stream) == "dev"


def test_parse_stream_tier_picks_last_when_reclassified():
    stream = "\n".join(
        [
            _assistant("- Tier: Docs"),
            _assistant("- Tier: Dev"),
        ]
    )
    assert parse_stream_tier(stream) == "dev"


def test_parse_stream_tier_none_when_absent():
    assert parse_stream_tier(_assistant("no classification here")) is None


def test_read_marker_tier_reads_prefix(tmp_path):
    d = tmp_path / ".claude" / "harness-tier" / ".flow"
    d.mkdir(parents=True)
    (d / "tier").write_text("staging:feature/x", encoding="utf-8")
    assert read_marker_tier(tmp_path) == "staging"


def test_read_marker_tier_none_when_absent(tmp_path):
    assert read_marker_tier(tmp_path) is None


def test_golden_cases_are_the_labelled_flow_prompts():
    cases = golden_cases()
    tiers = sorted(g for _, g, _ in cases)
    # Every labelled flow prompt is `dev`: the promotion prompt sits in flow's negative set,
    # and a negative carries no golden_tier.
    assert tiers == ["dev"] * 5
    assert all(isinstance(p, str) and p for p, _, _ in cases)


def test_a_golden_case_carries_the_fixture_its_prompt_presumes():
    """The probe runs each case in its own directory. Dropping the fixture here would measure
    `commit these changes` against an empty tree — the state that made it unanswerable."""
    fixtures = {p: f for p, _, f in golden_cases()}
    assert fixtures["Commit these changes."] == "flow-pending-commit"
    assert sum(f is not None for f in fixtures.values()) == 1


def test_probe_reads_the_marker_from_the_directory_the_session_ran_in(monkeypatch, tmp_path):
    """A fixture-backed case runs inside <tmp>/<scenario>; reading <tmp> would report every
    one of them as "no marker" and sink the capture rate for a reason that is not the router."""
    from evals import run

    def fake_stream(prompt, fixture, workdir, config_dir, restricted):
        cwd = Path(workdir) / fixture if fixture else Path(workdir)
        marker = cwd / ".claude" / "harness-tier" / ".flow" / "tier"
        marker.parent.mkdir(parents=True, exist_ok=True)
        marker.write_text("dev:feature/x\n", encoding="utf-8")
        return _assistant("## Tier Classification\n- Tier: DEV"), ""

    monkeypatch.setattr(run, "_claude_stream", fake_stream)
    # The fake places the marker where build() places the fixture, so the probe's `wd / fixture`
    # is pinned to the real convention rather than to the fake's guess at it.
    assert sandbox.build(sandbox.BY_NAME["flow-pending-commit"], tmp_path) == (
        tmp_path / "flow-pending-commit"
    )
    row = outcome_probe._probe_one("p", "dev", "flow-pending-commit", Path("."))
    assert row["marker_tier"] == "dev"
    assert outcome_probe._probe_one("p", "dev", None, Path("."))["marker_tier"] == "dev"


def test_a_skill_level_fixture_reaches_a_labelled_case(monkeypatch, tmp_path):
    """run.cases_for falls back to the skill's own fixture; reading the case alone would run
    the probe in an empty directory while the scored arm builds one."""
    (tmp_path / "evals").mkdir()
    (tmp_path / "evals" / "cases.yaml").write_text(
        "skills:\n"
        "  flow:\n"
        "    fixture: flow-pending-commit\n"
        "    happy:\n"
        "      - prompt: p\n"
        "        golden_tier: dev\n"
        "      - prompt: own\n"
        "        golden_tier: dev\n"
        "        fixture: doc-sync-drift\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(outcome_probe, "REPO", tmp_path)
    assert golden_cases() == [
        ("p", "dev", "flow-pending-commit"),
        ("own", "dev", "doc-sync-drift"),
    ]
