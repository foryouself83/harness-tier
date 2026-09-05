"""The prose gate: what --lint refuses, and what --verify proves a rewrite kept.

Two contracts, tested apart. --lint reads prose only — a banned word inside a fenced block or a
backtick span is data, and a rule that read it would make the rule file itself unlintable.
--verify is the other direction: it never judges prose, only that a rewrite dropped none of the
structure a reader navigates by (headings, fences, URLs, inline code) and none of the code under
a comment pass.
"""

import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from scripts.doc_style_check import (  # noqa: E402
    code_blocks,
    config_paths,
    git_head_text,
    in_scope,
    lint_text,
    main,
    markdown_prose,
    python_prose,
    shell_prose,
    strip_prose,
    verify,
)


def _codes(path: Path, text: str, severity: str = "error") -> list[str]:
    return [code for level, _, code, _ in lint_text(path, text) if level == severity]


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


# ---------- What --verify proves ----------


BEFORE_MD = """# Title

Some long explanatory paragraph that will be compressed.

- one
- two
- three

See https://example.com/spec and the `--verify` flag.

```bash
python3 scripts/doc_style_check.py --lint
```
"""


def test_a_faithful_rewrite_verifies_clean():
    after = BEFORE_MD.replace(
        "Some long explanatory paragraph that will be compressed.", "Compressed."
    )
    assert verify(Path("d.md"), BEFORE_MD, after) == []


def test_a_lost_heading_is_an_error():
    after = BEFORE_MD.replace("# Title\n", "")
    assert "HEADING" in [code for _, _, code, _ in verify(Path("d.md"), BEFORE_MD, after)]


def test_an_edited_code_block_is_an_error():
    after = BEFORE_MD.replace("--lint", "--lint --root .")
    assert "CODE" in [code for _, _, code, _ in verify(Path("d.md"), BEFORE_MD, after)]


def test_a_lost_url_is_an_error():
    after = BEFORE_MD.replace("https://example.com/spec", "the spec")
    assert "URL" in [code for _, _, code, _ in verify(Path("d.md"), BEFORE_MD, after)]


def test_a_lost_inline_code_span_is_an_error():
    after = BEFORE_MD.replace("`--verify`", "verify")
    assert "INLINE" in [code for _, _, code, _ in verify(Path("d.md"), BEFORE_MD, after)]


def test_dropped_bullets_warn():
    after = BEFORE_MD.replace("- two\n- three\n", "")
    findings = verify(Path("d.md"), BEFORE_MD, after)
    assert ("BULLET", "warning") in {(code, level) for level, _, code, _ in findings}
    assert not [f for f in findings if f[0] == "error" and f[2] == "BULLET"]


# ---------- Source: prose may move, code may not ----------


PY_BEFORE = '''"""Long docstring that used to explain the whole history."""

import os


def f(a, b=2):  # a comment nobody needs
    """Explains what the next line already says."""
    return os.path.join(str(a), str(b))
'''


def test_a_comment_only_rewrite_verifies_clean():
    after = '''"""One line."""

import os


def f(a, b=2):
    """Join a and b."""
    return os.path.join(str(a), str(b))
'''
    assert verify(Path("m.py"), PY_BEFORE, after) == []


def test_a_code_change_under_a_prose_rewrite_is_an_error():
    after = PY_BEFORE.replace("b=2", "b=3")
    assert "CODE" in [code for _, _, code, _ in verify(Path("m.py"), PY_BEFORE, after)]


def test_reindenting_prose_does_not_change_the_code_view():
    assert strip_prose(Path("m.py"), PY_BEFORE) == strip_prose(
        Path("m.py"), PY_BEFORE.replace("# a comment nobody needs", "")
    )


def test_shell_trailing_comment_is_prose_not_code():
    before = "set -e\nrun --now   # this used to be optional\n"
    after = "set -e\nrun --now\n"
    assert verify(Path("s.sh"), before, after) == []


def test_shell_hash_inside_quotes_is_code():
    # `# b` sits inside a quoted string: code, never a trailing comment. Assert on the
    # stripped code, since a non-empty verify() also holds with the quote handling gone —
    # the two files differ either way.
    before = "echo 'a # b'\n"
    assert strip_prose(Path("s.sh"), before) == "echo 'a # b'"
    assert verify(Path("s.sh"), before, "echo 'a'\n")


# ---------- CLI ----------


def test_lint_exits_1_on_an_error(tmp_path: Path, capsys):
    doc = tmp_path / "d.md"
    doc.write_text("It used to work.\n", encoding="utf-8")
    assert main(["--root", str(tmp_path), "--lint", str(doc)]) == 1
    assert "HIST" in capsys.readouterr().err


def test_lint_exits_0_on_warnings_only(tmp_path: Path):
    doc = tmp_path / "d.md"
    doc.write_text("word " * 40 + "\n", encoding="utf-8")
    assert main(["--root", str(tmp_path), "--lint", str(doc)]) == 0


def test_verify_git_compares_against_head(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.email", "t@t"], cwd=tmp_path, check=True)
    subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
    doc = tmp_path / "d.md"
    doc.write_text(BEFORE_MD, encoding="utf-8")
    subprocess.run(["git", "add", "d.md"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-qm", "seed"], cwd=tmp_path, check=True)

    doc.write_text(BEFORE_MD.replace("# Title\n", ""), encoding="utf-8")
    assert main(["--root", str(tmp_path), "--verify-git", str(doc)]) == 1


def test_verify_git_ignores_a_file_head_never_had(tmp_path: Path):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    doc = tmp_path / "new.md"
    doc.write_text("It used to work.\n", encoding="utf-8")
    assert main(["--root", str(tmp_path), "--verify-git", str(doc)]) == 0


def test_lint_config_is_silent_without_the_config(tmp_path: Path, capsys):
    assert main(["--root", str(tmp_path), "--lint-config"]) == 0
    assert capsys.readouterr().err == ""


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


# ---------- Config scope: one reader for both arms ----------


def _scoped(tmp_path: Path, config: str, rels: list[str]) -> Path:
    cfg = tmp_path / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-config.yaml").write_text(config, encoding="utf-8")
    for rel in rels:
        path = tmp_path / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("body\n", encoding="utf-8")
    return tmp_path


TREE = [
    "a.md",
    "docs/keep.md",
    "docs/legacy/old.md",
    "docs/legacy/sub/older.md",
    "node_modules/direct.md",
    "node_modules/pkg/deep/README.md",
    ".venv/lib/p/README.md",
    "vendor/x/y/z.md",
]


def _rels(root: Path, paths) -> list[str]:
    return sorted(p.relative_to(root).as_posix() for p in paths)


def test_exclude_reaches_past_a_directorys_direct_children(tmp_path: Path):
    """`Path.match` matched from the right, so even `docs/legacy/**` kept nested files in."""
    root = _scoped(
        tmp_path,
        "doc_style:\n  enable: true\n  paths: ['**/*.md']\n  exclude: ['docs/legacy/**']\n",
        TREE,
    )
    assert _rels(root, config_paths(root)) == ["a.md", "docs/keep.md"]


def test_a_single_star_exclude_stops_at_the_separator(tmp_path: Path):
    """`Path.glob` rules, not fnmatch's: `dir/*` is the direct children, `dir/**` the subtree.

    Letting `*` cross `/` here would make the hook's scope a superset of the one CI
    enumerates with `Path.glob`, which is the disagreement `in_scope` exists to prevent.
    """
    root = _scoped(
        tmp_path,
        "doc_style:\n  enable: true\n  paths: ['**/*.md']\n  exclude: ['docs/legacy/*']\n",
        TREE,
    )
    assert _rels(root, config_paths(root)) == [
        "a.md",
        "docs/keep.md",
        "docs/legacy/sub/older.md",
    ]


def test_never_linted_directories_are_out_at_any_depth(tmp_path: Path):
    root = _scoped(tmp_path, "doc_style:\n  enable: true\n", TREE)
    assert _rels(root, config_paths(root)) == [
        "a.md",
        "docs/keep.md",
        "docs/legacy/old.md",
        "docs/legacy/sub/older.md",
    ]


def test_both_arms_read_one_scope(tmp_path: Path):
    """The hook filters its changed files through in_scope; CI enumerates with the same rules.

    Disagreement means a consumer's `exclude` holds in one arm and not the other.
    """
    root = _scoped(
        tmp_path,
        "doc_style:\n  enable: true\n  paths: ['**/*.md']\n  exclude: ['docs/legacy/*']\n",
        TREE,
    )
    every = [root / rel for rel in TREE]
    assert _rels(root, in_scope(root, every)) == _rels(root, config_paths(root))


def test_scope_is_empty_without_the_config(tmp_path: Path):
    assert config_paths(tmp_path) == []
    assert in_scope(tmp_path, [tmp_path / "a.md"]) == []


def test_a_malformed_config_exits_loudly(tmp_path: Path):
    """Read as "off", one typo would take the CI arm down with no red job to say so."""
    root = _scoped(tmp_path, "doc_style: [\n", ["a.md"])
    with pytest.raises(SystemExit):
        config_paths(root)


def test_git_head_text_answers_none_outside_the_repo(tmp_path: Path):
    # doc-sync passes user-supplied paths to --verify-git; an outside one must not traceback.
    outside = tmp_path.parent / "not-in-this-repo.md"
    assert git_head_text(tmp_path, outside) is None


def test_a_fence_indented_inside_a_list_item_is_still_code():
    """CommonMark's 0-3 indent rule is for a top-level fence.

    A fenced block under a numbered list sits further in, and reading its body as prose reports
    banned words in code a consumer cannot rewrite.
    """
    text = "1. Step:\n\n   ```bash\n   run --just now   # it used to be simply this\n   ```\n"
    assert lint_text(Path("doc.md"), text) == []


@pytest.mark.parametrize(
    "glob,expected",
    [
        ("**/*.md", ["a.md", "docs/a.md", "docs/deep/nested.md", "docs/legacy/old.md"]),
        ("*.md", ["a.md"]),
        ("docs/*.md", ["docs/a.md"]),
        ("docs/**/*.md", ["docs/a.md", "docs/deep/nested.md", "docs/legacy/old.md"]),
        ("docs/**", ["docs/a.md", "docs/deep/nested.md", "docs/legacy/old.md"]),
        ("**/*.py", ["src/deep/y.py", "src/x.py"]),
        ("src/**/*.py", ["src/deep/y.py", "src/x.py"]),
        ("docs/?.md", ["docs/a.md"]),
        ("**/[ay].*", ["a.md", "docs/a.md", "src/deep/y.py"]),
    ],
)
def test_a_glob_means_the_same_thing_in_both_arms(tmp_path: Path, glob, expected):
    """CI walks the tree and the hook filters its changed files — one matcher answers both.

    Handing the pattern to `Path.glob` for the CI half is what let them disagree: a trailing
    `**` yields directories only before python 3.13 (CI pins 3.12), and it matches
    case-insensitively on Windows and not on the Linux runner.
    """
    rels = [
        "a.md",
        "docs/a.md",
        "docs/deep/nested.md",
        "docs/legacy/old.md",
        "src/x.py",
        "src/deep/y.py",
    ]
    root = _scoped(tmp_path, f"doc_style:\n  enable: true\n  paths: ['{glob}']\n", rels)
    assert _rels(root, in_scope(root, [root / rel for rel in rels])) == sorted(expected)
    # config_paths walks the whole tree, so it also finds the config file this fixture wrote.
    walked = [r for r in _rels(root, config_paths(root)) if not r.startswith(".claude/")]
    assert walked == sorted(expected)


def test_a_glob_that_cannot_compile_is_loud_in_ci_and_open_in_the_hook(tmp_path: Path):
    # Same split as a config that does not parse: red job, never a blocked commit.
    root = _scoped(tmp_path, "doc_style:\n  enable: true\n  paths: ['**/[z-a]']\n", ["a.md"])
    assert in_scope(root, [root / "a.md"]) == []
    with pytest.raises(SystemExit):
        config_paths(root)


def test_a_pattern_path_glob_would_reject_is_merely_a_non_match(tmp_path: Path):
    # `root.glob("/docs/*.md")` raises NotImplementedError and `root.glob("")` raises
    # ValueError. Walking the tree instead leaves them as patterns that match nothing.
    root = _scoped(tmp_path, "doc_style:\n  enable: true\n  paths: ['/docs/*.md', '']\n", ["a.md"])
    assert config_paths(root) == []


def test_a_deeper_fence_inside_a_block_does_not_close_it():
    """Allowing any indent to OPEN a fence made a deeper ``` inside one close it.

    The block's tail then leaked into prose, and the unclosed fence left behind swallowed the
    rest of the document — false positives and silent misses from the same edit.
    """
    text = "```text\ntree:\n        ```\n```\n\nIt used to be simply this.\n"
    assert len(code_blocks(text)) == 1
    assert _codes(Path("d.md"), text) == ["HIST", "FILLER"]


def test_a_closing_fence_may_be_indented_three_further():
    # CommonMark's slack for the closer; keeping it means the common case still closes.
    text = "```text\nbody used to be here\n  ```\n\nIt used to work.\n"
    assert _codes(Path("d.md"), text) == ["HIST"]


def test_a_malformed_config_fails_open_for_in_scope(tmp_path: Path):
    """The hook side of the same config. CI may be loud; the commit gate may not (Invariant #1).

    A `SystemExit` here would escape the gate's `except Exception` and abort the whole gate
    script, which is the fail-open the invariant forbids reaching by accident.
    """
    root = _scoped(tmp_path, "doc_style: [\n", ["a.md"])
    assert in_scope(root, [root / "a.md"]) == []
