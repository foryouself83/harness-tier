import scripts._harness_paths as vp
from tests.harness_paths._helpers import _Q3


def test_a_backtick_pair_balances():
    """A backtick is its own closer. Counted as another opening one the pair never balances
    and the scan swallows the rest of the command, so every region after it is wrong."""
    assert vp._matching(chr(96) + "abc" + chr(96) + "def", 1, chr(96), chr(96)) == 5


def test_an_element_that_runs_nothing_is_not_exempt():
    """The exemption is earned by a name. Read as satisfied by the absence of one, a
    fragment holding only a quoted script would be skipped for having no program in it."""
    assert not vp._reads_only("")
    assert not vp._reads_only("   ")
    assert vp._reads_only("grep -rn x .")


def test_the_subcommand_ends_at_the_backtick_that_closes_a_substitution():
    """The reading over the mask is the primary one and has to be right on its own. The
    inversion behind it happens to catch this too, so only a direct reading of the mask says
    whether the grammar ends the subcommand where a substitution does."""
    assert vp._GIT_COMMIT_RE.search(vp.mask_literals("echo " + chr(96) + "git commit" + chr(96)))


def test_a_quote_dense_command_is_classified_in_bounded_time():
    """Both quote predicates look back a fixed window, not to the start of the command. Read
    from the start they are quadratic, and at this size the hook timed out instead of
    answering — a verdict that never arrives is the gate off, not a slow gate."""
    import time

    command = " ".join(["echo " + chr(34) + "a b c" + chr(34)] * 2400)
    started = time.perf_counter()
    vp.is_invocation(command, "commit")
    assert time.perf_counter() - started < 1.5


def test_a_substitution_is_one_element_however_it_is_spelled():
    """The verdict for a backtick happens to survive being split — the closing backtick is the
    opening one, so it lands in the tail and withdraws the exemption there. `$( … )` has no
    such luck, and neither spelling should be split at all: what is written inside one
    substitution is one command's worth of programs."""
    for command in (
        "$(date; echo " + chr(34) + "x" + chr(34) + ")",
        chr(96) + "date; echo " + chr(34) + "x" + chr(34) + chr(96),
        "$(date" + chr(10) + "echo x)",
    ):
        assert len(vp._list_elements(command, vp.mask_literals(command))) == 1, command


def test_a_reserved_word_starts_the_command_after_it():
    """A reserved word is a token and the start of the command after it, and taken for the
    program itself the `grep` inside a `do` looked like a command with no program at all —
    every quoted mention in a loop body was denied. With nothing after it the word starts no
    command, and an element with no program of its own earns no exemption either way."""
    assert vp._programs(" then git commit -m x") == ["git"]
    assert vp._programs(" do grep -rn x .") == ["grep"]
    assert vp._programs("time grep -rn x .") == ["grep"]
    # A reserved word may also stand at a command position because another one stands in front
    # of it, which is what the lookback needs a whole word of room to see. Without it the
    # position reads as an argument and the program there is never asked about.
    assert vp._programs("cat f done then " + _Q3 + " commit") == ["cat", None]
    for element in sorted(vp._RESERVED_WORDS):
        assert vp._programs(element) == [], element
        assert vp._programs(element + " ; ") == [], element
        assert vp._reads_only(element) is False, element


def test_a_command_position_the_scan_cannot_name_is_not_a_reader():
    """The exemption is decided over the programs the walk reports, so one it cannot name has
    to be reported as that rather than left out. A program written quoted is blanked by the
    mask; one standing behind a `!`, a redirection or an assignment sits where a second scan
    looks for a name and finds punctuation."""
    for element in (
        "cat f | > /dev/null '\0\0\0' commit",
        "cat f | ! '\0\0\0' commit",
        "cat f | A=1 '\0\0\0' commit",
    ):
        assert None in vp._programs(element), element
        assert vp._reads_only(element) is False, element
    # A program BEHIND one of those is found, not stepped past — the half two scans disagreed
    # about, where the walk saw `env` and the name list did not.
    behind = "cat f | > /dev/null env '\0\0\0' commit"
    assert vp._programs(behind) == ["cat", "env"], vp._programs(behind)
    assert vp._reads_only(behind) is False
    for element in (
        "grep -rn x .",
        "grep -rn x . > out.txt",
        " do grep -q x f",
        "echo bash and then '\0\0\0'",
    ):
        assert None not in vp._programs(element), element
        assert vp._reads_only(element) is True, element


def test_one_long_unquoted_run_is_classified_in_bounded_time():
    """The quoted one below is only half the shape: the interpreter search restarted at every
    character a name cannot hold — `=`, `{`, `,`, `:` — and walked the rest of the run for a
    path separator. A real `aws … --metadata git-commit=…,k=v,…` at 70KB took twelve seconds."""
    import time

    command = "aws s3 cp b/ s3://b/ --metadata git-commit=abc," + "k0=v0," * 12000
    started = time.perf_counter()
    vp.is_invocation(command, "commit")
    vp.is_invocation(command, "merge")
    assert time.perf_counter() - started < 1.5


def test_one_long_quoted_token_is_classified_in_bounded_time():
    """The other three time tests are many SHORT quoted spans, and what costs is ONE long one:
    the interpreter search restarted at every character the mask had blanked and each attempt
    walked the rest of the run. 80KB took eighty seconds — and the runner asks about `commit`
    and `merge` both, so a long commit message alone paid it twice."""
    import time

    command = "echo '" + "a" * 80000 + "' | base64 -d"
    started = time.perf_counter()
    assert not vp.is_invocation(command, "merge")
    assert not vp.is_invocation(command, "commit")
    assert time.perf_counter() - started < 1.5


def test_a_redirection_dense_command_is_classified_in_bounded_time():
    """`{` both starts a command and may sit in a redirection target, so every one of them sent
    the walk over the prefixes to the end of the element: 48KB took 12 seconds, past the hook
    timeout, and a verdict that never arrives is the gate off rather than a slow gate."""
    import time

    command = "cat f | " + "{2>&1x" * 16000 + " 'git' commit -m x"
    started = time.perf_counter()
    assert vp.is_invocation(command, "commit")
    assert time.perf_counter() - started < 1.5


def test_a_reserved_word_dense_command_is_classified_in_bounded_time():
    """Whether a reserved word is at a command position was asked by searching back to the
    start of the element, which is quadratic: 60KB took 39 seconds, past the hook timeout, and
    a verdict that never arrives is the gate off rather than a slow gate. What may precede the
    word is a separator or one more reserved word, so the answer fits in a fixed window."""
    import time

    # Reading past a reserved word to the command it introduces costs one walk per
    # word unless each command is resolved once.
    command = "do " * 20000
    started = time.perf_counter()
    vp.is_invocation(command, "commit")
    assert time.perf_counter() - started < 1.5


def test_a_separator_dense_command_is_classified_in_bounded_time():
    """Each separator asked every substitution span whether it contained it, which is
    quadratic: 64KB took a minute, past the hook timeout, and a verdict that never arrives is
    the gate off rather than a slow gate."""
    import time

    command = (chr(96) + "; ") * 20000
    started = time.perf_counter()
    vp.is_invocation(command, "commit")
    assert time.perf_counter() - started < 1.5


def test_an_assignment_the_element_carries_is_not_the_program():
    """The exemption is earned by a NAME, and an assignment is neither that name nor one of
    its arguments — it reaches inside the program the list vouched for. `less` runs what
    `LESSOPEN` names, so an element carrying one is reported unnamed rather than read as a
    reader. The cost is a reader denied for an assignment that changes nothing, which the
    user sees; the other direction turned the gate off in silence."""
    assert vp._programs("LC_ALL=C grep x f") == [None]
    assert vp._reads_only("LC_ALL=C grep x f") is False
    assert vp._programs("A=1 time grep -rn x .") == [None]
    # …and the name is still read where nothing stands in front of it.
    assert vp._programs("grep x f") == ["grep"]
    assert vp._reads_only("grep x f") is True


def test_a_program_that_runs_what_its_environment_names_is_not_a_reader():
    """Most distributions set `LESSOPEN` in a login profile, so `less` runs a command nobody
    wrote in the command — the list's criterion is about arguments and missed it."""
    assert "less" not in vp._READS_ONLY
    assert "more" not in vp._READS_ONLY  # `more` is `less` on enough hosts
