"""Which files are in scope, and what the CLI exits with."""

from pathlib import Path

import pytest

from tests.doc_style._helpers import (
    TREE,
    Q,
    S,
    _codes,
    _rels,
    _scoped,
    code_blocks,
    config_paths,
    in_scope,
    main,
)

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


def test_lint_config_is_silent_without_the_config(tmp_path: Path, capsys):
    assert main(["--root", str(tmp_path), "--lint-config"]) == 0
    assert capsys.readouterr().err == ""


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


def test_a_config_that_never_opted_in_stays_green_when_it_does_not_parse(tmp_path: Path):
    """A file YAML cannot load cannot say whether it holds a `doc_style` block, so the raw
    text is asked instead. Without one the repo never enabled this, and a feature nobody
    turned on may not turn the build red over a typo elsewhere in a file it does not own."""
    root = _scoped(tmp_path, "branches:\n  - [unbalanced\n", ["a.md"])
    assert config_paths(root) == []


def test_the_opt_in_is_recognised_however_the_key_is_quoted(tmp_path: Path):
    """YAML takes `doc_style:`, `"doc_style":` and `'doc_style':` as the same key, so a repo
    that wrote either quoted form asked for this as plainly as one that did not. Reading
    only the bare spelling would hand exactly that repo the silence the loud exit exists
    to prevent."""
    for n, key in enumerate((Q + "doc_style" + Q, S + "doc_style" + S)):
        root = _scoped(
            tmp_path / str(n),
            key
            + ":"
            + chr(10)
            + "  enable: true"
            + chr(10)
            + "b:"
            + chr(10)
            + "  - [oops"
            + chr(10),
            ["a.md"],
        )
        with pytest.raises(SystemExit):
            config_paths(root)


def test_a_config_that_did_opt_in_still_exits_loudly_when_it_does_not_parse(tmp_path: Path):
    """The other half. Silence here reads as "off" and takes the CI arm down with no red
    job to say so, which is why the loud exit was chosen in the first place."""
    root = _scoped(tmp_path, "doc_style:\n  enable: true\nbranches:\n  - [oops\n", ["a.md"])
    with pytest.raises(SystemExit):
        config_paths(root)


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
