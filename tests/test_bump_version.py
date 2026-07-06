from pathlib import Path

import pytest

from scripts.bump_version import bump, finalize, main, rewrite_file


def test_bump_patch():
    assert bump("1.2.3", "patch") == "1.2.4"


def test_bump_minor_resets_patch():
    assert bump("1.2.3", "minor") == "1.3.0"


def test_bump_major_resets_minor_and_patch():
    assert bump("1.2.3", "major") == "2.0.0"


def test_bump_with_prerelease_suffix():
    assert bump("1.2.3", "patch", prerelease="rc.1") == "1.2.4-rc.1"


def test_bump_from_existing_prerelease_current():
    assert bump("1.2.3-rc.4", "patch") == "1.2.4"


def test_bump_continuing_a_prerelease_train_holds_the_base():
    # Regression: a second push to the prerelease branch must NOT re-bump patch on top of the
    # already-bumped base from the first rc — only the prerelease token advances.
    first = bump("1.2.3", "patch", prerelease="rc.1")
    assert first == "1.2.4-rc.1"
    second = bump(first, "patch", prerelease="rc.2")
    assert second == "1.2.4-rc.2"  # NOT 1.2.5-rc.2
    third = bump(second, "patch", prerelease="rc.3")
    assert third == "1.2.4-rc.3"


def test_bump_rejects_non_semver():
    with pytest.raises(ValueError):
        bump("not-a-version", "patch")


def test_bump_rejects_unknown_level():
    with pytest.raises(ValueError):
        bump("1.2.3", "epic")


def test_finalize_strips_prerelease():
    assert finalize("1.2.3-rc.4") == "1.2.3"


def test_finalize_noop_on_stable():
    assert finalize("1.2.3") is None


def test_rewrite_file_replaces_capture_group(tmp_path: Path):
    f = tmp_path / "Cargo.toml"
    f.write_text('[package]\nname = "x"\nversion = "1.2.3"\n', encoding="utf-8")
    rewrite_file(f, r'^version\s*=\s*"([^"]+)"', "1.2.4")
    assert 'version = "1.2.4"' in f.read_text(encoding="utf-8")


def test_rewrite_file_raises_when_pattern_absent(tmp_path: Path):
    f = tmp_path / "Cargo.toml"
    f.write_text('[package]\nname = "x"\n', encoding="utf-8")
    with pytest.raises(ValueError):
        rewrite_file(f, r'^version\s*=\s*"([^"]+)"', "1.2.4")


def test_main_bump_prints_version(capsys):
    assert main(["bump", "--current", "1.2.3", "--level", "minor"]) == 0
    assert capsys.readouterr().out.strip() == "1.3.0"


def test_main_finalize_exit_1_when_not_prerelease(capsys):
    assert main(["finalize", "--current", "1.2.3"]) == 1


def test_main_bump_rewrites_file(tmp_path: Path, capsys):
    f = tmp_path / "version.txt"
    f.write_text('version := "1.2.3"\n', encoding="utf-8")
    rc = main(
        [
            "bump",
            "--current",
            "1.2.3",
            "--level",
            "patch",
            "--file",
            str(f),
            "--pattern",
            r'version := "([^"]+)"',
        ]
    )
    assert rc == 0
    assert capsys.readouterr().out.strip() == "1.2.4"
    assert 'version := "1.2.4"' in f.read_text(encoding="utf-8")
