import json

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
    tiers = sorted(g for _, g in cases)
    assert tiers == ["dev", "dev", "dev", "staging"]  # 4 labelled, unlabelled dropped
    assert all(isinstance(p, str) and p for p, _ in cases)
