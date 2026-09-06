"""What counts as prose, and which prose the rule bans."""

from pathlib import Path

import pytest

from tests.doc_style._helpers import (
    REPO,
    _codes,
    lint_text,
    markdown_prose,
    python_prose,
    shell_prose,
)

# ---------- What --lint refuses ----------


@pytest.mark.parametrize(
    "prose,code",
    [
        ("The runner used to spawn twice.", "HIST"),
        ("This previously lived in the hook.", "HIST"),
        ("이전에는 훅이 두 번 돌았다", "HIST"),
        ("Fixed in 51adb2cf.", "SHA"),
        ("See docs/superpowers/plans/2026-08-06-llm-wiki.md for the rest.", "PLAN"),
        ("- [ ] wire the renderer", "PLAN"),
        ("It is just a marker.", "FILLER"),
        ("However, the gate blocks it.", "FILLER"),
        ("In order to commit, classify first.", "FILLER"),
        ("게이트가 커밋을 차단한다.", "ENDING"),
        ("훅이 먼저 실행됩니다.", "ENDING"),
    ],
)
def test_banned_prose_is_an_error(prose: str, code: str):
    assert code in _codes(Path("doc.md"), prose)


def test_a_concessive_connective_is_not_filler():
    """`however small` concedes; `However,` joins sentences. Only the second is filler."""
    assert _codes(Path("doc.md"), "Any change to code, however small, is Dev.\n") == []


def test_a_passive_use_is_not_history():
    """`used to` narrates; `is used to` is the passive of "use"."""
    assert _codes(Path("doc.md"), "The marker is used to gate the commit.\n") == []


def test_clean_prose_passes():
    text = "# Gate\n\nThe gate blocks an unclassified commit. Evidence lives under `.flow/`.\n"
    assert lint_text(Path("doc.md"), text) == []


def test_long_line_warns_but_does_not_error():
    text = "x " * 60 + "end\n"
    findings = lint_text(Path("doc.md"), text)
    assert [code for level, _, code, _ in findings if level == "warning"] == ["LONG"]
    assert _codes(Path("doc.md"), text) == []


def test_table_rows_escape_the_length_cap():
    row = "| " + "cell | " * 30 + "\n"
    assert lint_text(Path("doc.md"), row) == []


# ---------- Quoting a banned word is not using it ----------


def test_fenced_block_is_not_prose():
    text = "# H\n\n```bash\n# it used to be simply this\n```\n"
    assert lint_text(Path("doc.md"), text) == []


def test_inline_code_is_not_prose():
    assert _codes(Path("doc.md"), "Ban `used to` and `just` in prose.\n") == []


def test_url_and_link_target_are_not_prose():
    text = "See [the note](docs/notes/it-used-to-work.md) and https://x/just/really.\n"
    assert _codes(Path("doc.md"), text) == []


def test_front_matter_is_not_prose():
    text = "---\nname: x\ndescription: it used to do this\n---\n\nBody.\n"
    assert _codes(Path("doc.md"), text) == []


def test_the_rule_file_lints_clean():
    """rules/doc-style.md names every banned pattern. Backticking them is the whole contract."""
    path = REPO / "rules" / "doc-style.md"
    assert _codes(path, path.read_text(encoding="utf-8")) == []


# ---------- Which lines count as prose ----------


def test_python_prose_is_comments_and_docstrings_only():
    src = '"""Module doc used to say more."""\n\nX = 1  # just a constant\nY = "used to"\n'
    lines = dict(python_prose(src))
    assert any("used to say more" in v for v in lines.values())
    assert any("a constant" in v for v in lines.values())
    assert not any(v.strip() == '"used to"' for v in lines.values())  # a string literal is code


def test_shell_prose_skips_shebang_and_directives():
    src = "#!/usr/bin/env bash\n# shellcheck disable=SC2086\n# it used to exit 0\necho hi\n"
    assert [text for _, text in shell_prose(src)] == ["it used to exit 0"]


def test_markdown_prose_keeps_line_numbers():
    text = "# H\n\n```\nfenced\n```\n\ntail\n"
    assert (7, "tail") in markdown_prose(text)


# ---------- The PLAN rule reads link targets ----------


def test_a_link_to_a_plan_record_is_the_pointer_plan_bans():
    """The shape the rule is written for. Masking link targets hid every one of them."""
    text = "See [the plan](docs/superpowers/plans/x.md) for the rest.\n"
    assert _codes(Path("doc.md"), text) == ["PLAN"]


def test_naming_the_plan_path_in_backticks_is_clean():
    # rules/doc-style.md has to name the banned pattern to document it, the same exemption
    # every other rule gets from a backtick span.
    assert _codes(Path("doc.md"), "Ban `docs/superpowers/plans/` here.\n") == []


@pytest.mark.parametrize("number", ["20240115", "1000000", "3141592"])
def test_a_plain_number_is_not_a_commit_sha(number):
    """SHA needs a letter as well as a digit — a date and a byte count are neither."""
    assert _codes(Path("doc.md"), f"Handled {number} rows.\n") == []


def test_a_real_sha_still_reports():
    assert _codes(Path("doc.md"), "See 6cddf51 for it.\n") == ["SHA"]


def test_a_fence_indented_inside_a_list_item_is_still_code():
    """CommonMark's 0-3 indent rule is for a top-level fence.

    A fenced block under a numbered list sits further in, and reading its body as prose reports
    banned words in code a consumer cannot rewrite.
    """
    text = "1. Step:\n\n   ```bash\n   run --just now   # it used to be simply this\n   ```\n"
    assert lint_text(Path("doc.md"), text) == []
