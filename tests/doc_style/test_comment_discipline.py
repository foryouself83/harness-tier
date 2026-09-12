"""ANCHOR, META and TRAP: the three rules this branch added, plus the fixes a re-review found
in them (a mutation gap in the TRAP blank-line check, two META discrimination holes, and a
TRAP key hidden by its own backticks)."""

from pathlib import Path

import pytest

from tests.doc_style._helpers import REPO, _codes, lint_text

# ---------- ANCHOR: a filename followed by a line number ----------


@pytest.mark.parametrize(
    "prose,code",
    [
        ("Same guard as `precommit-runner.sh:31`.", "ANCHOR"),
        ("See scripts/check-deps.sh:10 for the other half.", "ANCHOR"),
        ("The failure lands in flow_gate_check.py: 12.", "ANCHOR"),
    ],
)
def test_banned_anchor_prose_is_an_error(prose: str, code: str):
    assert code in _codes(Path("doc.md"), prose)


def test_a_url_port_is_not_a_line_anchor():
    """`ANCHOR` reads inline code, so the URL masking is the only thing keeping a port out."""
    assert _codes(Path("doc.md"), "Serve it at http://localhost:8000/openapi.json\n") == []


def test_a_github_line_link_target_is_not_a_line_anchor():
    """The target is a permalink; the claim would be in the link TEXT, which stays readable."""
    assert _codes(Path("doc.md"), "See [the guard](scripts/check-deps.sh#L10).\n") == []


def test_a_bare_filename_is_allowed():
    assert _codes(Path("doc.md"), "The guard lives in `precommit-runner.sh`.\n") == []


def test_a_yaml_mapping_example_is_not_a_line_anchor():
    """The leading zero and the seven-digit run are YAML's int coercion, not a line ref."""
    text = "Same YAML 1.1 trap as _TEXT_FIELDS: `src/a.py: 0123456` records int 42798,\n"
    assert _codes(Path("doc.md"), text) == []


def test_a_six_digit_anchor_is_still_caught():
    """The digit cap is a cap, not an off-by-one: six digits is the largest still allowed."""
    assert _codes(Path("doc.md"), "Same guard as `f.py:123456`.\n") == ["ANCHOR"]


@pytest.mark.parametrize(
    "prose",
    [
        "CHANGELOG.md: 12 entries landed this quarter.\n",
        "README.md: 3 sections need a rewrite.\n",
        "The ratio in config.yaml: 3 to 1.\n",
    ],
)
def test_a_word_after_the_number_makes_it_a_sentence(prose: str):
    """Release-note and documentation prose, not an anchor. Markdown is the only surface a
    consumer lints by default and its CI job fails the push, so a sentence of this shape took a
    consumer's build down with no remedy available but dropping the colon."""
    assert _codes(Path("doc.md"), prose) == []


@pytest.mark.parametrize(
    "prose",
    [
        "The failure lands in flow_gate_check.py: 12.\n",
        "Look at MAIN.PY:31 for it.\n",
        "The selector lives in app.vue:44.\n",
        "The bucket name is in main.tf:9.\n",
        "The rule sits in styles.scss:120.\n",
    ],
)
def test_an_anchor_survives_the_sentence_carve_out(prose: str):
    """The carve-out is the half that could switch the rule off. A colon with no space is an
    anchor whatever follows it, a spaced one still is when the number ends the clause, and the
    extension list is read without regard to case."""
    assert _codes(Path("doc.md"), prose) == ["ANCHOR"]


# ---------- META: a field label vs. a definitional clause ----------


@pytest.mark.parametrize(
    "prose,code",
    [
        ("@author jdoe", "META"),
        ("Author: J. Doe", "META"),
        ("Last updated: 2026-09-12", "META"),
        ("작성자: 홍길동", "META"),
        ("수정이력: 인코딩 가드 추가", "META"),
    ],
)
def test_banned_meta_prose_is_an_error(prose: str, code: str):
    assert code in _codes(Path("doc.md"), prose)


def test_a_bare_date_is_not_a_metadata_field():
    """A date can be a contract (a cutoff, a deprecation). Only a field label is banned."""
    assert _codes(Path("doc.md"), "The pin expires 2026-12-31.\n") == []


def test_the_word_author_inside_a_sentence_is_not_a_field():
    assert _codes(Path("doc.md"), "The skill will author the workflow file.\n") == []


def test_a_korean_metadata_word_inside_a_sentence_is_not_a_field():
    """작성자 can appear in regular sentences; only a field label is banned."""
    assert _codes(Path("doc.md"), "Git blame으로 작성자를 확인하세요.\n") == []


@pytest.mark.parametrize(
    "prose",
    ["- Updated: 2026-09-12\n", "**Updated:** 2026-09-12\n", "> Updated: 2026-09-12\n"],
)
def test_a_revision_field_under_a_markdown_prefix_is_still_a_field(prose: str):
    """A bullet, a bold run and a quote marker are the shapes a document records revision
    metadata in, and a line-head anchor that cannot absorb them misses all three."""
    assert _codes(Path("doc.md"), prose) == ["META"]


@pytest.mark.parametrize(
    "prose",
    ["Changelog:\n", "Revision: 3\n", "Author: John Doe\n", "Author: jdoe smith\n"],
)
def test_a_bare_or_value_shaped_field_is_still_caught(prose: str):
    """A bare label with nothing after it, a numeric value, and a two-word name are all still
    field values — none of them contains the function word a clause needs to read as a
    sentence. `jdoe smith` is the hole a re-review found: an all-lowercase multi-word name is
    a value exactly as much as `J. Doe` or `John Doe` are, and the old heuristic (a lowercase
    first letter means a clause) let it through."""
    assert _codes(Path("doc.md"), prose) == ["META"]


@pytest.mark.parametrize(
    "prose",
    [
        "Modified: files are re-read from disk.\n",
        "Created: a new worktree per run.\n",
        "History: the gate is fail-closed.\n",
        "- Updated: the resolver now reads the worktree.\n",
        # The other two holes a re-review found: capitalizing the clause's first word, or
        # dropping the space after the colon, must not turn a clause into a field. Neither
        # changes what makes it a clause — the function word still glues its pieces together.
        "Created: A new worktree per run.\n",
        "History: The gate is fail-closed.\n",
        "Modified:files are re-read from disk.\n",
    ],
)
def test_a_definitional_label_is_not_a_revision_field(prose: str):
    """Each label doubles as an ordinary word. What separates the field from the definition is
    the value: a field carries a date, a version, a name or an identifier; a definition carries
    a clause, and English cannot state one without a function word joining its pieces."""
    assert _codes(Path("doc.md"), prose) == []


# ---------- TRAP: a CRITICAL TRAP marker needs its Trigger/Symptom keys ----------

TRAP_OK = (
    "# CRITICAL TRAP: the gate passes a commit it should block\n"
    "# Trigger: a cp949 host with a Korean reason string\n"
    "# Symptom: exit 0, empty stderr, the commit lands unreviewed\n"
    "x = 1\n"
)

TRAP_NO_KEYS = (
    "# CRITICAL TRAP: the gate passes a commit it should block\n"
    "# it happens when the host locale is cp949\n"
    "x = 1\n"
)

TRAP_SPLIT = (
    "# CRITICAL TRAP: the gate passes a commit it should block\n"
    "\n"
    "# Trigger: a cp949 host\n"
    "# Symptom: the commit lands unreviewed\n"
    "x = 1\n"
)


def test_a_complete_trap_box_passes():
    assert "TRAP" not in _codes(Path("m.py"), TRAP_OK)


def test_a_trap_box_without_its_keys_is_an_error():
    assert "TRAP" in _codes(Path("m.py"), TRAP_NO_KEYS)


def test_a_blank_line_ends_the_box():
    """A true blank source line leaves NO entry in `python_prose` at all, so this reaches
    `_blocks` through the numbering-gap check, never through its `if not raw.strip()` line —
    see `test_a_bare_comment_line_ends_the_box` for a case that reaches that line directly.
    """
    assert "TRAP" in _codes(Path("m.py"), TRAP_SPLIT)


TRAP_BARE_COMMENT_SPLIT = (
    "# CRITICAL TRAP: the gate passes a commit it should block\n"
    "#\n"
    "# Trigger: a cp949 host\n"
    "# Symptom: the commit lands unreviewed\n"
    "x = 1\n"
)


def test_a_bare_comment_line_ends_the_box():
    """A bare `#` IS a prose entry (empty body), unlike a true blank source line — this is
    the case that exercises `_blocks`'s `if not raw.strip(): continue` line.
    """
    assert "TRAP" in _codes(Path("m.py"), TRAP_BARE_COMMENT_SPLIT)


TRAP_INLINE_CODE_ONLY_LINE = (
    "# CRITICAL TRAP: the gate passes a commit it should block\n"
    "# `PYTHONUTF8=1`\n"
    "# Trigger: a cp949 host\n"
    "# Symptom: the commit lands unreviewed\n"
    "x = 1\n"
)


def test_an_inline_code_only_line_does_not_split_the_box():
    """`_blocks` judges blankness on the RAW line, never the masked one, on purpose: a line
    holding nothing but an inline-code span masks to all spaces, and ending the run there
    would split this box in two — the marker alone in one block, Trigger/Symptom orphaned in
    a second, marker-less one, both reported incomplete. A mutation from `raw` to `masked` in
    that one check passed the whole suite before this test existed.
    """
    assert "TRAP" not in _codes(Path("m.py"), TRAP_INLINE_CODE_ONLY_LINE)


def test_a_multi_line_comment_without_the_marker_is_not_checked():
    body = "# the locale is cp949 here\n# so the child python needs PYTHONUTF8\nx = 1\n"
    assert "TRAP" not in _codes(Path("m.py"), body)


TRAP_MISSING_SYMPTOM_ONLY = (
    "# CRITICAL TRAP: the gate passes a commit it should block\n# Trigger: a cp949 host\nx = 1\n"
)


def test_a_box_missing_one_key_names_only_that_key():
    """The single-item branch of `' and '.join(missing)` — a box short one key, not both."""
    findings = lint_text(Path("m.py"), TRAP_MISSING_SYMPTOM_ONLY)
    [message] = [msg for level, _, code, msg in findings if code == "TRAP"]
    assert "Symptom:" in message
    assert "Trigger:" not in message


# ---------- TRAP: two boxes can share one unbroken comment run ----------

TRAP_SECOND_BOX_INCOMPLETE = (
    "# CRITICAL TRAP: box A (complete)\n"
    "# Trigger: A\n"
    "# Symptom: A\n"
    "# CRITICAL TRAP: box B (missing both keys)\n"
    "x = 1\n"
)


def test_a_complete_box_does_not_cover_an_incomplete_one_after_it():
    """One `_blocks` run, two markers: box A's keys must not satisfy box B's, and the
    finding must land on box B's own line, not box A's."""
    findings = lint_text(Path("m.py"), TRAP_SECOND_BOX_INCOMPLETE)
    trap = [(lineno, message) for level, lineno, code, message in findings if code == "TRAP"]
    assert trap == [(4, "CRITICAL TRAP box is missing Trigger: and Symptom:")]


TRAP_TWO_COMPLETE_BOXES = (
    "# CRITICAL TRAP: box A\n"
    "# Trigger: A\n"
    "# Symptom: A\n"
    "# CRITICAL TRAP: box B\n"
    "# Trigger: B\n"
    "# Symptom: B\n"
    "x = 1\n"
)


def test_two_complete_boxes_back_to_back_have_no_finding():
    assert "TRAP" not in _codes(Path("m.py"), TRAP_TWO_COMPLETE_BOXES)


TRAP_KEYS_BELOW_NEXT_MARKER = (
    "# CRITICAL TRAP: box A (its keys never come before box B)\n"
    "# CRITICAL TRAP: box B\n"
    "# Trigger: B\n"
    "# Symptom: B\n"
    "x = 1\n"
)


def test_a_boxs_keys_below_the_next_marker_do_not_count_for_it():
    """Box B's Trigger/Symptom sit after box A in the same run — they are box B's, not box
    A's borrowed keys."""
    findings = lint_text(Path("m.py"), TRAP_KEYS_BELOW_NEXT_MARKER)
    trap = [(lineno, message) for level, lineno, code, message in findings if code == "TRAP"]
    assert trap == [(1, "CRITICAL TRAP box is missing Trigger: and Symptom:")]


# ---------- TRAP: the marker and its keys read the same line head every other rule does ----

TRAP_MD_OK = (
    "- **CRITICAL TRAP:** the gate passes a commit it should block\n"
    "- Trigger: a cp949 host with a Korean reason string\n"
    "- Symptom: exit 0, and the commit lands unreviewed\n"
)

TRAP_MD_NO_KEYS = (
    "- **CRITICAL TRAP:** the gate passes a commit it should block\n"
    "- it reaches that state when the host locale is cp949\n"
)

TRAP_MD_INDENTED = (
    "Write it exactly like this:\n"
    "\n"
    "    # CRITICAL TRAP: the gate passes a commit it should block\n"
    "    # Trigger: a cp949 host with a Korean reason string\n"
    "    # Symptom: exit 0, and the commit lands unreviewed\n"
)

TRAP_SH_OK = (
    "#!/usr/bin/env bash\n"
    "# CRITICAL TRAP: the gate passes a commit it should block\n"
    "# Trigger: a cp949 host with a Korean reason string\n"
    "# Symptom: exit 0, and the commit lands unreviewed\n"
    "exit 0\n"
)

TRAP_SH_NO_KEYS = (
    "#!/usr/bin/env bash\n"
    "# CRITICAL TRAP: the gate passes a commit it should block\n"
    "# it reaches that state when the host locale is cp949\n"
    "exit 0\n"
)


def test_a_markdown_box_behind_a_list_prefix_is_complete():
    """The keys are on the next two lines. Reported missing, the finding states something that
    is not true, and the only edit that clears it is deleting a box the rule asked for."""
    assert "TRAP" not in _codes(Path("doc.md"), TRAP_MD_OK)


def test_a_markdown_box_without_its_keys_is_an_error():
    assert "TRAP" in _codes(Path("doc.md"), TRAP_MD_NO_KEYS)


def test_an_indented_code_block_box_is_read_through_its_comment_marks():
    """Only a fence leaves `markdown_prose`, so a box shown inside a numbered rule arrives with
    its `#` still on — the shape `rules/doc-style.md` writes its own model example in."""
    assert "TRAP" not in _codes(Path("doc.md"), TRAP_MD_INDENTED)


def test_a_shell_box_is_complete():
    assert "TRAP" not in _codes(Path("g.sh"), TRAP_SH_OK)


def test_a_shell_box_without_its_keys_is_an_error():
    assert "TRAP" in _codes(Path("g.sh"), TRAP_SH_NO_KEYS)


def test_naming_the_marker_in_backticks_is_not_a_box_in_markdown():
    """Every other rule exempts an inline-code span, and a document has to name the marker to
    document it. Reading the raw line left `CRITICAL TRAP:` unwritable in any shipped prose."""
    assert "TRAP" not in _codes(Path("doc.md"), "The marker is `CRITICAL TRAP:` exactly.\n")


def test_naming_the_marker_in_backticks_is_not_a_box_in_a_comment():
    assert "TRAP" not in _codes(Path("g.sh"), "# The marker is `CRITICAL TRAP:` exactly.\n")


# ---------- TRAP: a key styled as inline code is still the key ----------

TRAP_KEY_BACKTICKED = "# CRITICAL TRAP: x\n# `Trigger:` a cp949 host\n# Symptom: ...\n"


def test_a_backticked_key_still_counts_for_its_box():
    """The marker on line 1 is unbackticked and real, so the box already exists — a re-review
    found that styling the `Trigger:` key itself as inline code then hid it from the key
    search (which read the same default mask as the marker) and reported the box as missing
    Trigger:, even though the key is plainly there, just formatted. Reading the keys on the
    "code" mask instead keeps the key visible without reopening the marker's own exemption
    (naming `CRITICAL TRAP:` in backticks with no box around it still is not one — see
    test_naming_the_marker_in_backticks_is_not_a_box_in_a_comment)."""
    assert "TRAP" not in _codes(Path("m.py"), TRAP_KEY_BACKTICKED)


def test_the_rule_files_own_backtick_wrapped_marker_still_lints_clean():
    """`rules/doc-style.md` shows the marker inside a fenced code block, not backticked inline,
    so this is a regression guard on the file that documents the rule itself."""
    path = REPO / "rules" / "doc-style.md"
    assert "TRAP" not in _codes(path, path.read_text(encoding="utf-8"))
