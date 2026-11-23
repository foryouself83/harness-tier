"""FUTURE: planned work written into current prose — a warning a host opts into."""

from pathlib import Path

import pytest

from tests.doc_style._helpers import _scoped, lint_text, main

MARKED = [
    "추후 지원 예정임",
    "향후 Codex 도 지원함",
    "차후 플래그로 분리함",
    "TODO: wire the renderer",
    "FIXME the parser drops quotes",
    "Support for GitLab is on the roadmap.",
    "Windows paths are not yet supported.",
    "The flag is not yet implemented.",
    "A JSON reporter is coming soon.",
    "A second reporter is planned.",
    "Lands in a future release.",
]


def _warnings(path: Path, text: str, **kwargs) -> list[str]:
    return [code for level, _, code, _ in lint_text(path, text, **kwargs) if level == "warning"]


@pytest.mark.parametrize("prose", MARKED)
def test_a_marked_future_statement_warns_when_opted_in(prose: str):
    assert _warnings(Path("doc.md"), prose + "\n", future=True) == ["FUTURE"]


@pytest.mark.parametrize("prose", MARKED)
def test_the_rule_is_off_by_default(prose: str):
    assert "FUTURE" not in _warnings(Path("doc.md"), prose + "\n")


@pytest.mark.parametrize(
    "prose",
    [
        "The hook will block the commit.",
        "Shows what it will create, then writes on confirm.",
        "30 sessions planned per run, 10 of them negative.",
        "The `TODO` marker is what this rule reads.",
        "예정대로가 아니라 실제 값을 씀",
    ],
)
def test_present_behaviour_and_quoted_markers_stay_silent(prose: str):
    """`will` states what the code does now; a backticked marker names the rule."""
    assert "FUTURE" not in _warnings(Path("doc.md"), prose + "\n", future=True)


def test_a_code_comment_marker_warns():
    text = "x = 1  # TODO: read the bound from config\n"
    assert _warnings(Path("m.py"), text, future=True) == ["FUTURE"]


def test_it_never_errors():
    findings = lint_text(Path("doc.md"), "추후 지원 예정임\n", future=True)
    assert [level for level, _, code, _ in findings if code == "FUTURE"] == ["warning"]


def _run(tmp_path: Path, config: str, capsys) -> str:
    root = _scoped(tmp_path, config, [])
    doc = root / "doc.md"
    doc.write_text("Windows paths are not yet supported.\n", encoding="utf-8")
    assert main(["--root", str(root), "--lint", str(doc)]) == 0
    return capsys.readouterr().err


def test_the_cli_reads_the_opt_in_from_flow_config(tmp_path: Path, capsys):
    err = _run(tmp_path, "doc_style:\n  enable: true\n  future: true\n", capsys)
    assert "WARNING FUTURE" in err


@pytest.mark.parametrize(
    "config",
    [
        "doc_style:\n  enable: true\n",
        "doc_style:\n  enable: true\n  future: false\n",
        # Only the boolean opts in: a quoted "true" is a string, and reading it as on would
        # make `future: "false"` on as well.
        'doc_style:\n  enable: true\n  future: "true"\n',
        "doc_style: [not, a, mapping]\n",
    ],
)
def test_anything_but_a_boolean_true_leaves_it_off(tmp_path: Path, capsys, config: str):
    assert "FUTURE" not in _run(tmp_path, config, capsys)


def test_a_config_that_does_not_parse_leaves_it_off(tmp_path: Path, capsys):
    root = _scoped(tmp_path, "other: [unclosed\n", [])
    doc = root / "doc.md"
    doc.write_text("추후 지원 예정임\n", encoding="utf-8")
    assert main(["--root", str(root), "--lint", str(doc)]) == 0
    assert "FUTURE" not in capsys.readouterr().err
