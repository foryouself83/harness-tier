"""How the strategy verdict reads a merge whose words a redirection, a quote-split subcommand
or a program that parses them again (`eval`, `watch`, `ssh`) shapes."""

import pytest

import scripts.flow_gate_check as fgc
from tests.flow_gate.test_merge_check import _run_merge_check
from tests.flow_gate.test_merge_spellings import _policy


@pytest.mark.parametrize(
    "command,branch,blocked",
    [
        # a redirection and its target are no operands, and its `|` or `&` separates nothing
        ("git merge >|o.txt --no-ff fix/x", "dev", True),
        ("git merge >| o.txt --no-ff fix/x", "dev", True),
        ("git merge > o.txt --no-ff fix/x", "dev", True),
        ("git merge >o.txt --no-ff fix/x", "dev", True),
        ("git merge 2>&1 --no-ff fix/x", "dev", True),
        ("git merge &>o.txt --no-ff fix/x", "dev", True),
        ("git merge >&2 --no-ff fix/x", "dev", True),
        ("git merge <o.txt --no-ff fix/x", "dev", True),
        ("git merge --no-ff fix/x <<<hi", "dev", True),
        ("git merge feature/x >|o.txt --squash", "dev", False),
        ("git mer''ge >|o.txt --no-ff fix/x", "dev", True),
        ("git mer''ge 2>&1 --no-ff fix/x", "dev", True),
        # a quoted `>` is an argument, not a redirection
        ("git merge -m '>' --no-ff fix/x", "dev", True),
        # behind `eval` a quoted separator ends the merge before it
        ("eval git merge feature/a ';' git merge --squash feature/x", "dev", True),
        ("eval git merge feature/a \\; git merge --squash feature/x", "dev", True),
        ("eval git merge feature/a 'x;' git merge --squash feature/x", "dev", True),
        ("eval >|o git merge feature/a ';' git merge --squash feature/x", "dev", True),
        ("eval git mer''ge feature/a ';' git mer''ge --squash feature/x", "dev", True),
        ("eval git switch main ';' git merge stage", "dev", True),
        ("eval git switch main \\; git merge --no-ff stage", "dev", False),
        # without a program that parses it again, a quoted `;` stays an argument
        ("env git merge -m ';' --no-ff fix/x", "dev", True),
        ("watch -x git merge -m 'a;b' --no-ff fix/x", "dev", True),
        ("watch --exec git merge -m 'a;b' --no-ff fix/x", "dev", True),
        ("find . -name eval -exec git merge -m 'a;b' --no-ff fix/x \\;", "dev", True),
        ("sudo -u eval git merge -m 'a;b' --no-ff fix/x", "dev", True),
        ("timeout -s eval 5 git merge -m 'x;y' --no-ff fix/x", "dev", True),
        ("sudo eval git merge feature/a ';' git merge --squash feature/x", "dev", True),
        ("eval git merge -m 'a;b' --no-ff fix/x", "dev", False),
        # the second parse drops a redirection and ends at a comment as the first one does
        ("eval git merge '2>&1' --no-ff fix/x", "dev", True),
        ("eval git merge '&>o' --no-ff fix/x", "dev", True),
        ("eval git merge '>|o' --no-ff fix/x", "dev", True),
        ("ssh h git merge '2>&1' --no-ff fix/x", "dev", True),
        ("eval git switch main '2>&1' ';' git merge stage", "dev", True),
        ("eval git merge feature/x '#;' --squash", "dev", True),
        ("eval git merge feature/x '#' --squash", "dev", True),
        # the quote-split fallback reads the second parse the same way
        ("eval git mer''ge feature/x '#' --squash", "dev", True),
        ("eval git mer''ge '2>&1' --no-ff fix/x", "dev", True),
        ("watch -x git mer''ge -m 'a#' --no-ff fix/x", "dev", True),
        # a quote spanning two words, a second `eval`, and `builtin eval`
        ("eval git merge -m \"'a\" \"b'\" feature/x ';' --squash", "dev", True),
        ("eval eval git merge feature/x \"';'\" --squash", "dev", True),
        ("builtin eval git merge feature/x ';' --squash", "dev", True),
        ("watch eval git merge feature/x \"';'\" --squash", "dev", True),
        # the word after `ssh` is its host, whatever it is named
        ("ssh eval git merge -m \"'a;b'\" --no-ff fix/x", "dev", True),
    ],
)
def test_review_round_four_spellings(monkeypatch, tmp_path, command, branch, blocked):
    _policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, command, branch)
    assert (code == fgc.BLOCK_EXIT_CODE) is blocked, (command, code)


@pytest.mark.parametrize(
    "command,branch,blocked",
    [
        # a quote-split merge keeps a quoted `;`, `>`, `|` or `(` as an argument
        ("git mer''ge -m ';' --no-ff fix/x", "dev", True),
        ("git mer''ge -m '>' --no-ff fix/x", "dev", True),
        ("git mer''ge -m 'a|b' --no-ff fix/x", "dev", True),
        ("git mer''ge -m '(' --no-ff fix/x", "dev", True),
        ("git mer''ge " + chr(92) + chr(10) + " --no-ff fix/x", "dev", True),
        # and reads a substitution as one word, judging a merge inside it
        ("git mer''ge feature/x $(true; false) --squash", "dev", False),
        ("echo $(git mer''ge --no-ff fix/x)", "dev", True),
        ("git mer''ge feature/x $(git mer''ge --no-ff fix/y) --squash", "dev", True),
        # a stage the mask shows one merge in may hold a quote-split one
        ("eval git merge --squash feature/x ';' git mer''ge --no-ff fix/x", "dev", True),
        ("git mer''ge --no-ff fix/x & git merge --squash feature/y", "dev", True),
        ("git mer''ge --squash feature/x & git merge --no-ff fix/y", "dev", True),
        # a named fd and a heredoc's operator go with their redirection
        ("git merge {fd}>o --no-ff fix/x", "dev", True),
        ("git merge <<EOF --no-ff fix/x\nx\nEOF\n", "dev", True),
        ("git merge <<-EOF --no-ff fix/x\nx\nEOF\n", "dev", True),
        ("git merge <<'E O' --no-ff fix/x\nx\nE O\n", "dev", True),
        ("git merge --no-ff fix/x <<EOF\ngit merge feature/y\nEOF\n", "dev", True),
        # past the options of `watch` and `ssh` and the host of `ssh`
        ("watch -n 1 eval git merge feature/x \"';'\" --squash", "dev", True),
        ("ssh h eval git merge feature/x \"';'\" --squash", "dev", True),
        ("ssh -p 22 user@h eval git merge feature/x \"';'\" --squash", "dev", True),
        ("ssh -o X=1 -p22 h eval git merge feature/x \"';'\" --squash", "dev", True),
        ("watch -x eval git merge feature/x ';' --squash", "dev", False),
    ],
)
def test_review_round_five_spellings(monkeypatch, tmp_path, command, branch, blocked):
    _policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, command, branch)
    assert (code == fgc.BLOCK_EXIT_CODE) is blocked, (command, code)


@pytest.mark.parametrize(
    "command,passes",
    [
        # one parse more, read by the mask reader alone
        ("eval " + "git merge --squash feature/x " * 50, 1),
        # two more, read by both readers since the stage holds quotes
        ("eval eval git merge --squash feature/x \"';'\" " * 50, 4),
        ("ssh -p 22 h eval git merge --squash feature/x \"';'\" " * 50, 4),
    ],
)
def test_a_chain_behind_eval_parses_each_word_again_once(monkeypatch, command, passes):
    """Parsed again for each merge, a chain of them cost the square of its length."""
    import scripts._harness_paths as hp

    calls = []
    real = hp._reread
    monkeypatch.setattr(hp, "_reread", lambda w: calls.append(w) or real(w))
    assert len(fgc._merges(command)) == 50
    assert len(calls) <= passes * len(command.split())


def test_a_quoted_separator_parsed_again_is_an_argument():
    """At a command's start the mask unwraps a quoted word, which must not expose its `;`."""
    import scripts._harness_paths as hp

    assert hp._reread(("';'",)) == ((";",), False)
    assert hp._reread((";",)) == ((), True)


@pytest.mark.parametrize(
    "command,branch,blocked",
    [
        # parsed again, a quoted redirection takes the next word for its target
        ("eval git merge feature/x '>' --squash", "dev", True),
        ("eval eval git merge feature/x '>' --squash", "dev", True),
        ("eval git merge feature/x '2>' --squash", "dev", True),
        ("eval git merge feature/x '>>' --squash", "dev", True),
        ("eval git merge feature/x '<' --squash", "dev", True),
        ("eval git merge feature/x '>|' --squash", "dev", True),
        ("eval git merge feature/x '&>' --squash", "dev", True),
        ("eval git merge feature/x \\> --squash", "dev", True),
        ("eval git mer''ge feature/x '>' --squash", "dev", True),
        ("sudo eval git mer''ge feature/x '>' --squash", "dev", True),
        ("ssh h git mer''ge feature/x '>' --squash", "dev", True),
        ("watch -n1 eval git mer''ge feature/x '>' --squash", "dev", True),
        ("eval git merge feature/x '>o' --squash", "dev", False),
        # `<<<`, `<<` and `<<-` are one operator each, never a run of `<`
        ("eval eval git merge feature/x \"'<<<'\" --squash", "dev", True),
        ("eval git merge feature/x '<<<' --squash", "dev", True),
        ("eval git merge feature/x '<<' --squash", "dev", True),
        ("eval git merge feature/x '<<-' --squash", "dev", True),
        ("git merge feature/x <<<hi --squash", "dev", False),
        # a line continuation inside a word joins it
        ("git merge --no" + chr(92) + chr(10) + "-ff fix/x", "dev", True),
        ("git merge fi" + chr(92) + chr(10) + "x/x --no-ff", "dev", True),
        ("git mer" + chr(92) + chr(10) + "ge --no-ff fix/x", "dev", True),
        ("git switch ma" + chr(92) + chr(10) + "in && git merge stage", "dev", True),
        ("eval eval git merge -m 'a" + chr(92) + chr(10) + "b' --no-ff fix/x", "dev", True),
        ('eval eval git merge -m "a' + chr(92) + chr(10) + 'b" --no-ff fix/x', "dev", True),
        ("watch -n 1 eval git merge -m 'a" + chr(92) + chr(10) + "b' --no-ff fix/x", "dev", True),
        ('watch -n 1 eval git merge -m "a' + chr(92) + chr(10) + 'b" --no-ff fix/x', "dev", True),
        ("ssh h eval git merge -m 'a" + chr(92) + chr(10) + "b' --no-ff fix/x", "dev", True),
        ('ssh h eval git merge -m "a' + chr(92) + chr(10) + 'b" --no-ff fix/x', "dev", True),
        ("ssh -p 22 h eval git merge -m 'a" + chr(92) + chr(10) + "b' --no-ff fix/x", "dev", True),
        ('ssh -p 22 h eval git merge -m "a' + chr(92) + chr(10) + 'b" --no-ff fix/x', "dev", True),
        ('git merge -m "a' + chr(92) + chr(10) + 'b" --no-ff fix/x', "dev", True),
        ('git merge "fi' + chr(92) + chr(10) + 'x/x" --no-ff', "dev", True),
        ("git mer''ge \"fi" + chr(92) + chr(10) + 'x/x" --no-ff', "dev", True),
    ],
)
def test_review_round_six_spellings(monkeypatch, tmp_path, command, branch, blocked):
    _policy(tmp_path)
    code = _run_merge_check(monkeypatch, tmp_path, command, branch)
    assert (code == fgc.BLOCK_EXIT_CODE) is blocked, (command, code)
