import pytest

from scripts import bump_version
from scripts.bump_version import last_stable, main, next_version, parse_level, pending_rc

TAGS_PENDING = ["v1.0.0", "v1.1.0-rc.1", "v1.1.0-rc.2"]
TAGS_RELEASED = ["v1.0.0", "v1.1.0-rc.1", "v1.1.0-rc.2", "v1.1.0"]


def msg(level: str | None) -> str:
    body = "Merge dev: headline\n\n- item\n"
    return body if level is None else body + f"\nRelease-Level: {level}\n"


@pytest.mark.parametrize(
    "level, expected",
    [
        ("continue", "1.1.0-rc.3"),
        ("patch", "1.1.1-rc.1"),
        ("minor", "1.2.0-rc.1"),
        ("major", "2.0.0-rc.1"),
    ],
)
def test_re_promotion_computes_from_the_pending_rc_base(level, expected):
    assert next_version(msg(level), TAGS_PENDING) == expected


@pytest.mark.parametrize(
    "level, expected",
    [("patch", "1.1.1-rc.1"), ("minor", "1.2.0-rc.1"), ("major", "2.0.0-rc.1")],
)
def test_first_promotion_bumps_the_last_stable_tag(level, expected):
    assert next_version(msg(level), TAGS_RELEASED) == expected


def test_continue_without_a_pending_rc_fails():
    with pytest.raises(ValueError, match="no pending"):
        next_version(msg("continue"), TAGS_RELEASED)


@pytest.mark.parametrize("message", [msg(None), msg("auto")])
def test_auto_is_left_to_the_tool(message):
    assert next_version(message, TAGS_PENDING) == "auto"


@pytest.mark.parametrize("value", ["pach", "", "Minor", "patch minor"])
def test_an_invalid_trailer_value_fails(value):
    with pytest.raises(ValueError, match="Release-Level"):
        parse_level(msg(value))


def test_two_different_trailers_fail():
    with pytest.raises(ValueError, match="Release-Level"):
        parse_level(msg("patch") + "Release-Level: minor\n")


def test_a_released_rc_is_not_pending_even_when_it_is_the_newest_tag():
    # Staging's back-merge was skipped (FF refused): describe on staging still reaches the rc,
    # but the tag list carries its stable twin.
    assert pending_rc(["v1.1.0-rc.2", "v1.1.0"]) is None


def test_pending_rc_is_the_highest_unreleased_one():
    assert pending_rc(["v1.0.0-rc.1", "v1.0.0", "v1.1.0-rc.1", "v1.1.0-rc.10", "v1.1.0-rc.9"]) == (
        "1.1.0",
        10,
    )


def test_unrelated_tags_are_ignored():
    assert last_stable(["v1.0.0", "latest", "v2.0.0-beta.1", "nightly-3"]) == "1.0.0"
    assert last_stable([]) == "0.0.0"


def test_auto_level_turns_auto_into_continue_or_the_fallback_level():
    assert next_version(msg(None), TAGS_PENDING, auto_level="patch") == "1.1.0-rc.3"
    assert next_version(msg(None), TAGS_RELEASED, auto_level="patch") == "1.1.1-rc.1"


def test_a_hotfix_that_shipped_the_rc_base_moves_the_next_rc_past_it():
    # stage waits on 1.1.1-rc.1, a hotfix shipped 1.1.1 straight to production.
    tags = ["v1.1.0", "v1.1.1-rc.1", "v1.1.1"]
    assert pending_rc(tags) is None
    assert next_version(msg("patch"), tags) == "1.1.2-rc.1"
    with pytest.raises(ValueError, match="no pending"):
        next_version(msg("continue"), tags)


def test_cli_prints_the_version(capsys):
    assert main(["next", "--message", msg("minor"), "--tags", "\n".join(TAGS_PENDING)]) == 0
    assert capsys.readouterr().out.strip() == "1.2.0-rc.1"


def test_cli_exits_2_with_a_reason(capsys):
    assert main(["next", "--message", msg("pach"), "--tags", ""]) == 2
    assert "Release-Level" in capsys.readouterr().err


def test_finalize_tag_prints_the_pending_rc_base(capsys):
    assert main(["finalize-tag", "--tags", "\n".join(TAGS_PENDING)]) == 0
    assert capsys.readouterr().out.strip() == "1.1.0"


@pytest.mark.parametrize("tags", [TAGS_RELEASED, ["v1.0.0"], []])
def test_finalize_tag_exits_1_silently_without_a_pending_rc(tags, capsys):
    assert main(["finalize-tag", "--tags", "\n".join(tags)]) == 1
    assert capsys.readouterr().out == ""


def test_finalize_tag_reads_only_the_given_token(capsys):
    tags = "\n".join(["v1.0.0", "v1.1.0-beta.1"])
    assert main(["finalize-tag", "--tags", tags]) == 1
    capsys.readouterr()
    assert main(["finalize-tag", "--tags", tags, "--token", "beta"]) == 0
    assert capsys.readouterr().out.strip() == "1.1.0"


def test_finalize_tag_rc_prints_the_pending_rc_tag(capsys):
    assert main(["finalize-tag", "--rc", "--tags", "\n".join(TAGS_PENDING)]) == 0
    assert capsys.readouterr().out.strip() == "v1.1.0-rc.2"


def test_finalize_tag_rc_exits_1_silently_without_a_pending_rc(capsys):
    assert main(["finalize-tag", "--rc", "--tags", "\n".join(TAGS_RELEASED)]) == 1
    assert capsys.readouterr().out == ""


def test_an_rc_below_the_last_stable_tag_is_superseded_not_pending():
    # An orphan rc series left behind by later stable releases can never ship without a
    # downgrade, so `continue` must not resume it.
    tags = ["v0.2.3-rc.5", "v0.3.0", "v0.4.0"]
    assert pending_rc(tags) is None
    assert next_version(msg("patch"), tags) == "0.4.1-rc.1"
    with pytest.raises(ValueError, match="no pending"):
        next_version(msg("continue"), tags)


def test_a_lower_hotfix_leaves_the_rc_pending():
    assert pending_rc(["v1.1.0-rc.2", "v1.0.4"]) == ("1.1.0", 2)


def test_a_higher_hotfix_supersedes_the_rc():
    assert pending_rc(["v1.1.0-rc.2", "v1.1.1"]) is None


def test_finalize_tag_ignores_a_superseded_rc(capsys):
    assert main(["finalize-tag", "--rc", "--tags", "v0.2.3-rc.5\nv0.3.0\nv0.4.0"]) == 1
    assert capsys.readouterr().out == ""


def test_next_refuses_a_version_whose_tag_already_exists(monkeypatch, capsys):
    # No consistent tag list reaches this today; the check stops a future pending_rc defect
    # from re-cutting an existing rc instead of producing a duplicate tag.
    monkeypatch.setattr(bump_version, "pending_rc", lambda tags, token="rc": ("1.1.0", 1))
    tags = "\n".join(["v1.0.0", "v1.1.0-rc.1", "v1.1.0-rc.2"])
    assert main(["next", "--message", msg("continue"), "--tags", tags]) == 2
    err = capsys.readouterr().err
    assert "v1.1.0-rc.2" in err and "already exists" in err
