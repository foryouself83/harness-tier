"""Quote removal read the way bash performs it, and the grammar searched without rescanning.

The quote-removed view is what joins a word split by quoting back into the word bash runs, so
every spelling below was checked against bash with a stub `git` that prints its arguments."""

import random
import re
import time

import pytest

import scripts._harness_paths as vp
import scripts.flow_gate_check as fgc

BS = chr(92)


@pytest.mark.parametrize(
    "text,value",
    [
        ("com''mit", "commit"),
        ('com""mit', "commit"),
        (f"c{BS}ommit", "commit"),
        (f"co{BS}\nmmit", "commit"),
        (f"co{BS}\r\nmmit", "commit"),
        # a backslash inside double quotes quotes only $ ` " \ and newline
        (f'"C:{BS}Git{BS}git.exe"', f"C:{BS}Git{BS}git.exe"),
        (f'"a{BS}$b{BS}"c{BS}{BS}d"', f'a$b"c{BS}d'),
        (f'"co{BS}\nmmit"', "commit"),
        # single quotes take every character literally
        (f"'C:{BS}Git'", f"C:{BS}Git"),
        # ANSI-C strings decode their escapes; $"…" reads as a double-quoted string
        (f"$'{BS}x63ommit'", "commit"),
        (f"$'{BS}143ommit'", "commit"),
        (f"$'{BS}u0063ommit'", "commit"),
        (f"$'{BS}U00000063ommit'", "commit"),
        (f"$'{BS}t{BS}n{BS}{BS}{BS}''", f"\t\n{BS}'"),
        (f"$'{BS}cA'", chr(1)),
        (f"$'{BS}q'", f"{BS}q"),
        (f"$'{BS}xZ'", f"{BS}xZ"),
        # a code point no character carries stays as written
        (f"$'{BS}U7FFFFFFF'", f"{BS}U7FFFFFFF"),
        (f"$'{BS}ud800'", f"{BS}ud800"),
        # the body ends at the first quote no backslash takes; `\c` never reaches past it
        (f"$'{BS}c' x", f"{BS}c x"),
        (f"$'a{BS}'b'", "a'b"),
        # a line continuation between `$` and its quote is gone before the quote is read
        (f"${BS}\n'{BS}x63ommit'", "commit"),
        ('$"commit"', "commit"),
        # an unterminated quote runs to the end
        ("'commit", "commit"),
        ('"commit', "commit"),
        (f"{BS}", BS),
    ],
)
def test_quote_removal_matches_bash(text: str, value: str):
    assert vp._remove_quotes(text) == value


@pytest.mark.parametrize(
    "text,words",
    [
        (f"git $'{BS}x63ommit' -m x", ["git", "commit", "-m", "x"]),
        (f"git $'it{BS}'s' x", ["git", "it's", "x"]),
        ('git $"commit"', ["git", "commit"]),
        # inside other quotes `$'` is text
        ("echo \"$'x'\"", ["echo", "$'x'"]),
        ("echo '$'x", ["echo", "$x"]),
        (
            f"git merge -m $'{BS}U7FFFFFFF' --no-ff dev",
            ["git", "merge", "-m", f"{BS}U7FFFFFFF", "--no-ff", "dev"],
        ),
    ],
)
def test_ansi_c_strings_reach_shlex_as_the_words_they_decode_to(text: str, words: list[str]):
    import shlex

    assert shlex.split(vp.requote_ansi_c(text)) == words


def _corpus(seed: int, count: int) -> list[str]:
    rng = random.Random(seed)
    pieces = [
        "git",
        "/usr/bin/git",
        "git.exe",
        "-C",
        "-",
        "-c",
        "x",
        "-a",
        "commit",
        "merge",
        ";",
        "&&",
        "|",
        "(",
        ")",
        "`",
        "a=b",
        "--no-ff",
        "mygit",
        "log",
        "\n",
        "'q'",
    ]
    return [
        "".join(rng.choice(pieces) + rng.choice([" ", "", "  "]) for _ in range(rng.randint(1, 14)))
        for _ in range(count)
    ]


@pytest.mark.parametrize("word", ["commit", "merge", "(?:switch|checkout)"])
def test_the_linear_search_finds_what_the_regex_finds(word: str):
    """Against the plain regex the search replaces, over generated commands: same spans, same
    option region, every start position included."""
    plain = re.compile(
        rf"(?:^|[\s;&|(`])(?:[^\s;&|()'\"`]*[/\\])?"
        rf"git(?:\.exe)?({vp._GIT_OPTIONS})\s+{word}(?=$|[\s;&|)`<>])"
    )
    grammar = vp.git_subcommand_re(word)
    for text in _corpus(7, 4000):
        want = [(m.span(), m.span(1)) for m in plain.finditer(text)]
        got = [(m.span(), m.span(1)) for m in grammar.finditer(text)]
        assert got == want, text
        for pos, end in ((1, len(text)), (0, len(text) // 2)):
            want = [(m.span(), m.span(1)) for m in plain.finditer(text, pos, end)]
            got = [(m.span(), m.span(1)) for m in grammar.finditer(text, pos, end)]
            assert got == want, (text, pos, end)


@pytest.mark.parametrize(
    "command",
    [
        "make " + "-a git " * 16000 + "; commit",
        "make " + "g''it -a " * 8000,
        "x " + "-a git " * 16000 + "-m commit",
    ],
    # The id becomes PYTEST_CURRENT_TEST, which Windows caps at 32767 characters.
    ids=["chain-then-separator", "split-git-chain", "chain-into-a-value"],
)
def test_a_chain_of_options_naming_git_does_not_stall_the_gate(command: str):
    """Each `git` in the chain must not restart a scan of the rest of it: past the hook timeout
    there is no verdict, and Invariant #1 turns that into a commit that passes ungated."""
    start = time.perf_counter()
    vp.is_invocation(command, "commit")
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"{len(command)} chars took {elapsed:.2f}s"


@pytest.mark.parametrize(
    "command",
    ["python x " + "`a" * 20000 + " commit", "git log " + "a`" * 20000],
    ids=["backtick-run-then-word", "backtick-run"],
)
def test_a_run_of_backticks_does_not_stall_the_gate(command: str):
    """A backtick opens a program position, and a path prefix that could run across the next
    one rescanned the whole run from each of them."""
    start = time.perf_counter()
    vp.is_invocation(command, "commit")
    elapsed = time.perf_counter() - start
    assert elapsed < 2.0, f"{len(command)} chars took {elapsed:.2f}s"


def test_many_merges_are_judged_without_rereading_the_command_per_merge():
    """Each merge asks for the switches before it, and the shell-split reading of the whole
    command runs the net over every stage: read per merge, it grows with their product."""
    command = "git merge --no-ff a/b; python x y; " * 400
    start = time.perf_counter()
    merges = fgc._merges(command)
    targets = [fgc._target_from_command(command, s) for s, _f, _s in merges]
    elapsed = time.perf_counter() - start
    assert len(targets) == 400
    assert elapsed < 5.0, f"{len(merges)} merges took {elapsed:.2f}s"


def test_a_merge_flag_beside_an_ansi_c_value_out_of_range_is_still_read():
    """Raising on the value would empty the merge's words, and an empty merge fails open."""
    command = f"git merge --no-ff -m $'{BS}U7FFFFFFF' dev"
    assert fgc.parse_merge_commands(command) == [({"--no-ff"}, "dev")]


def test_an_ansi_c_switch_operand_names_its_branch():
    assert fgc._target_from_command("git switch $'dev' && git merge --ff feature/x") == "dev"
