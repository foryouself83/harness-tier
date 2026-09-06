from pathlib import Path

import pytest

from scripts import wiki_graph
from tests.wiki_graph._helpers import _EXAMPLES, _write_config


def test_derive_wiki_id_examples():
    for path, expected in _EXAMPLES.items():
        assert wiki_graph.derive_wiki_id(path) == expected, path


def test_derive_wiki_id_root_prefix_is_optional():
    # `--derive-id docs/a.md` and `--derive-id a.md --root docs/` are the same call.
    assert wiki_graph.derive_wiki_id("a.b.md", "docs") == "a-b"
    assert wiki_graph.derive_wiki_id("docs/a.b.md", "docs/") == "a-b"


def test_derive_wiki_id_root_prefix_matches_segment_boundary():
    # docs-old/ is not prefixed by the root docs (the same shape as Invariant 6's path-prefix
    # footgun).
    assert wiki_graph.derive_wiki_id("docs-old/a.md", "docs") == "docs-old.a"


def test_derive_wiki_id_windows_separators():
    assert wiki_graph.derive_wiki_id("docs\\sds\\README.md", "docs") == "sds.readme"


def test_derive_wiki_id_rejects_degenerate_segment():
    # A Hangul-only name has nothing left after sanitizing. Emitting one blocks commits on a
    # duplicate id from the second such document onward — the very symptom this feature exists
    # to remove — so it is refused at the source.
    with pytest.raises(ValueError, match="영문"):
        wiki_graph.derive_wiki_id("docs/온보딩.md", "docs")


def test_derive_wiki_id_rejects_root_itself_and_empty():
    with pytest.raises(ValueError):
        wiki_graph.derive_wiki_id("docs", "docs")
    with pytest.raises(ValueError):
        wiki_graph.derive_wiki_id("", "docs")


def test_wiki_root_hint_ignores_the_enable_gate(tmp_path: Path):
    # The root is honored even under enable: false, because /harness-init may run before
    # /wiki-init (harness-rules 8-2). Going through load_wiki_config returns None there and
    # derives against docs silently.
    _write_config(tmp_path, "wiki:\n  enable: false\n  root: documentation/\n")
    assert wiki_graph._wiki_root_hint(tmp_path) == "documentation"


def test_wiki_root_hint_fails_soft_to_docs(tmp_path: Path):
    assert wiki_graph._wiki_root_hint(tmp_path) == "docs"  # no config
    _write_config(tmp_path, "wiki: [broken\n")
    assert wiki_graph._wiki_root_hint(tmp_path) == "docs"  # unparsable


# ---------------------------------------------------------------- --derive-id CLI


def test_derive_id_cli_prints_tab_pairs(capsys):
    # path<TAB>id pairs, not a positional zip, so a partial failure cannot shift the lines and
    # silently mismatch them.
    rc = wiki_graph.main(["--derive-id", "docs/a/b.md", "docs/a.b.md", "--root", "docs"])
    assert rc == 0
    assert capsys.readouterr().out.splitlines() == ["docs/a/b.md\ta.b", "docs/a.b.md\ta-b"]


def test_derive_id_cli_partial_failure_names_the_path(capsys):
    rc = wiki_graph.main(["--derive-id", "docs/ok.md", "docs/온보딩.md", "--root", "docs"])
    assert rc == 1
    captured = capsys.readouterr()
    assert "docs/ok.md\tok" in captured.out  # the successes still go out
    assert "온보딩" in captured.err  # the failure names its path


def test_derive_id_cli_reads_config_root(tmp_path: Path, monkeypatch, capsys):
    _write_config(tmp_path, "wiki:\n  enable: false\n  root: documentation/\n")
    monkeypatch.setattr(wiki_graph, "host_root", lambda: tmp_path)
    rc = wiki_graph.main(["--derive-id", "documentation/api_spec.md"])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "documentation/api_spec.md\tapi-spec"


def test_derive_id_cli_respects_an_explicit_empty_root(tmp_path: Path, monkeypatch, capsys):
    # `--root ""` is an explicit choice the caller typed, not "no --root given". Branching
    # on truthiness would silently fall back to the config/default root instead — the same
    # footgun `main()` already guards against for `--neighbors ""` (`is not None` there too).
    # With no root to strip, "docs/a.md" derives as "docs.a", not the "a" a default root
    # of "docs" would produce — that difference is what proves the empty root was honored.
    monkeypatch.setattr(wiki_graph, "host_root", lambda: tmp_path)
    rc = wiki_graph.main(["--derive-id", "docs/a.md", "--root", ""])
    assert rc == 0
    assert capsys.readouterr().out.strip() == "docs/a.md\tdocs.a"


def test_derive_id_is_not_swallowed_by_fail_open(monkeypatch):
    # --derive-id is not a gate command. An internal exception failing open into exit 0 is a
    # "success with no output", and the caller falls back to deriving by hand — the failure mode
    # this command exists to remove.
    def _boom(paths, root_arg):
        raise RuntimeError("boom")

    monkeypatch.setattr(wiki_graph, "cmd_derive_id", _boom)
    with pytest.raises(RuntimeError):
        wiki_graph.main(["--derive-id", "docs/a.md"])
