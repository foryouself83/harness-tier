import pytest

import scripts._harness_paths as vp


def test_dir_from_command_reads_past_a_comment_that_holds_an_apostrophe():
    # bash ends a `#` comment at the newline; treating the apostrophe inside it as an opening
    # quote masks the rest of the command, the invocation disappears, and a classified worktree
    # commit is rejected as unclassified. Invariant #6: never newly block.
    command = '# don\'t forget the worktree\ngit -C "/a b/wt" commit -m x'
    assert vp._dir_from_command(command) == "/a b/wt"


def test_dir_from_command_reads_the_rest_of_a_heredoc_introducer_line():
    # the body is literal, the line that opens it is not — its own quotes still have to be read,
    # or a quoted worktree path on that line stays unmasked and the option token cannot cross it.
    command = 'cat <<EOF | git -C "/a b/wt" commit -F -\nfix(x): y\nEOF'
    assert vp._dir_from_command(command) == "/a b/wt"


def test_dir_from_command_reads_ansi_c_quoting():
    # inside `$'…'` a backslash escapes, so the region ends at the LAST quote, not the escaped one.
    command = "echo $'don\\'t' && git -C \"/a b/wt\" commit -m x"
    assert vp._dir_from_command(command) == "/a b/wt"


def test_dir_from_command_reads_an_escaped_quote_inside_a_double_quoted_span():
    command = 'echo "a \\" b" && git -C /wt commit -m "c"'
    assert vp._dir_from_command(command) == "/wt"


def test_dir_from_command_masks_a_tab_indented_heredoc_body():
    # `<<-` strips leading TABS from the terminator; the body is still literal text.
    command = "\n".join(["cat <<-EOF | git -C /wt commit -F -", "run git -C /evil commit", "\tEOF"])
    assert vp._dir_from_command(command) == "/wt"


def test_dir_from_command_keeps_a_plain_heredoc_body_closed_to_the_exact_word():
    # plain `<<` needs the terminator line EXACTLY; an indented look-alike is body text, so
    # ending the region there hands the rest of the body to the parser as syntax.
    command = "\n".join(
        ["cat <<EOF | git -C /wt commit -F -", "  EOF", "run git -C /evil commit", "EOF"]
    )
    assert vp._dir_from_command(command) == "/wt"


def test_dir_from_command_masks_an_unterminated_heredoc_body():
    # bash consumes a body with no terminator to end of input. Reading it as syntax makes a tree
    # named only in a message the resolved directory.
    assert vp._dir_from_command("cat <<EOF\nrun git -C /evil commit\n") is None
    # …and with no trailing newline, which is the branch that must run to end of input rather
    # than report "no body" and hand the message back to the parser.
    assert vp._dir_from_command("cat <<EOF\nrun git -C /evil commit") is None


def test_dir_from_command_ignores_a_dash_c_inside_a_quoted_option_value():
    # the option region is scanned on the mask, so a `-C` inside a quoted VALUE is not an option.
    assert vp._dir_from_command('git -c user.name="x -C /evil" -C /wt commit -m y') == "/wt"


def test_dir_from_command_gives_up_when_only_one_invocation_names_a_directory():
    # two commits in two trees is the ambiguity Invariant #6 wants ended: answering with the one
    # that named a directory re-points ROOT away from the tree the other commit runs in.
    assert vp._dir_from_command("git commit -m x && git -C /y commit --amend") is None


def test_dir_from_command_reads_an_introducer_line_with_no_body_after_it():
    # `<<EOF` as the last line has no body, so nothing follows it to mask — blanking the rest of
    # the introducer instead swallows the invocation on that same line. bash runs this (with a
    # warning), so rejecting it is a new block Invariant #6 forbids.
    assert vp._dir_from_command('cat <<EOF | git -C "/a b" commit -F -') == "/a b"


def test_dir_from_command_keeps_a_here_string_operand_out_of_the_heredoc_grammar():
    # `<<<` is a here-string. Read as `<<` + word, its operand becomes a heredoc terminator that
    # never appears, so the body runs to end of input and masks the commit that follows.
    command = 'grep -q ok <<<"$status"\ngit -C /wt commit -m x'
    assert vp._dir_from_command(command) == "/wt"


def test_dir_from_command_only_treats_a_word_start_hash_as_a_comment():
    # bash starts a comment only where a word does. `#` inside a word or an expansion is data.
    assert vp._dir_from_command("echo fix#123 ; git -C /wt commit -m x") == "/wt"
    assert vp._dir_from_command("echo ${a#b} && git -C /wt commit -m x") == "/wt"
    assert vp._dir_from_command("echo $# && git -C /wt commit -m x") == "/wt"


def test_dir_from_command_masks_a_comment_rather_than_only_skipping_it():
    # a `-C` written in a comment is not an option; leaving the text as syntax makes it one.
    command = "# run git -C /evil commit\ngit -C /wt commit -m x"
    assert vp._dir_from_command(command) == "/wt"


def test_dir_from_command_finds_a_comment_that_starts_after_a_newline():
    # the word-start test has to accept a newline, not only the start of the string.
    command = "echo a\n# don't run git -C /evil commit\ngit -C /wt commit -m x"
    assert vp._dir_from_command(command) == "/wt"


def test_dir_from_command_enters_a_heredoc_body_that_follows_a_redirect():
    # the introducer is not the end of its line, so the body is entered only after the line is
    # scanned. An apostrophe in the body is the everyday case that must not open a quote.
    command = "cat <<EOF >msg\ndon't touch\nEOF\ngit -C /wt commit -F msg"
    assert vp._dir_from_command(command) == "/wt"


def test_dir_from_command_strips_only_tabs_and_only_for_a_dash_heredoc():
    # `<<-` strips leading TABS from the terminator; plain `<<` strips nothing. Getting either
    # backwards ends the body early and hands the rest of a message to the parser.
    dashed = "cat <<-EOF >msg\n\trun git -C /evil commit\n\tEOF\ngit -C /wt commit -F msg"
    assert vp._dir_from_command(dashed) == "/wt"
    plain = "cat <<EOF >msg\n\tEOF\nrun git -C /evil commit\nEOF\ngit -C /wt commit -F msg"
    assert vp._dir_from_command(plain) == "/wt"


# ── one authority for what a shell word is ───────────────────────────────────────
# Each case below is reachable from a real command and resolves to the wrong tree — or to no
# tree, which leaves ROOT on main and so newly blocks a correctly-classified worktree commit.


def test_dir_from_command_reads_a_backslash_escaped_space_in_a_path():
    assert vp._dir_from_command(r"git -C /tmp/My\ P/wt commit -m x") == "/tmp/My P/wt"


def test_dir_from_command_keeps_a_windows_backslash_path_intact():
    # bash would drop these backslashes; the gate deliberately does not, because a Windows path
    # is the shape this option carries and dropping them resolves nothing.
    assert vp._dir_from_command(r"git -C C:\work\wt commit -m x") == r"C:\work\wt"


def test_dir_from_command_closes_a_heredoc_whose_delimiter_carries_a_cr():
    # A heredoc delimiter is one WORD, and a CR is an ordinary character in it: after `<<'EOF'`
    # the CR of a CRLF line joins the same word, so bash's delimiter is EOF+CR and the EOF+CR
    # line closes it. Reading the delimiter as EOF alone runs the body to end of input and
    # swallows the real invocation that follows — the commit skill's own template.
    tmpl = (
        "msg=$(cat <<'EOF'\nfix(gate): x\nEOF\n)\nprintf '%s\n' \"$msg\" | git -C /c/wt commit -F -"
    )
    assert vp._dir_from_command(tmpl) == "/c/wt"
    assert vp._dir_from_command(tmpl.replace("\n", "\r\n")) == "/c/wt"


def test_dir_from_command_masks_a_backslash_quoted_heredoc_body():
    # A backslash quotes the delimiter exactly as single quotes do. Left unrecognised, the body
    # is never masked at all and a commit the message merely quotes re-points ROOT.
    c = "cat <<" + "\\" + "EOF | mail\nsee git -C /evil/wt commit -m x\nEOF\n"
    assert vp._dir_from_command(c) is None


def test_dir_from_command_masks_the_second_of_two_heredocs_on_one_line():
    c = "cat <<A <<B\nplain\nA\ngit -C /evil/wt commit -m x\nB\n"
    assert vp._dir_from_command(c) is None


def test_dir_from_command_reads_a_delimiter_word_built_from_two_pieces():
    c = "cat <<'EO'F\ngit -C /evil/wt commit -m x\nEOF\ngit -C /c/wt commit -m y"
    assert vp._dir_from_command(c) == "/c/wt"


def test_dir_from_command_does_not_read_an_arithmetic_shift_as_a_heredoc():
    c = "n=$((1 << 2))\necho $n\ngit -C /c/wt commit -m x"
    assert vp._dir_from_command(c) == "/c/wt"


def test_dir_from_command_reads_across_a_line_continuation():
    assert vp._dir_from_command("git -C /c/wt \\\n  commit -m x") == "/c/wt"


# ── quoted text the shell EXECUTES is not literal ────────────────────────────────
# The mask exists so a commit a message merely quotes is not read as one. But a quoted span is
# data only until something runs it: `$( )` and backticks are commands wherever they appear, and
# an interpreter's `-c` argument is the command it was handed. Read as literal text, a real
# commit disappears and the gate exits 0 on it — which is worse than the false block the mask
# was introduced to remove, and worse than the substring match it replaced.


@pytest.mark.parametrize(
    "command,word",
    [
        ('bash -c "git commit -m x"', "commit"),
        ("bash -c 'git commit -m x'", "commit"),
        ('sh -c "git merge --no-ff dev"', "merge"),
        ('zsh -c "git commit -m x"', "commit"),
        ('eval "git commit -m x"', "commit"),
        ("eval 'git merge --squash feature/x'", "merge"),
        ('out="$(git commit -m x)"', "commit"),
        ("out=$(git merge --no-ff dev)", "merge"),
        ("out=`git commit -m x`", "commit"),
        ('git submodule foreach "git commit -m x"', "commit"),
    ],
)
def test_a_command_the_shell_executes_is_read_even_when_quoted(command: str, word: str):
    assert vp.is_invocation(command, word), command


@pytest.mark.parametrize(
    "command",
    [
        'grep "git commit" -r .',
        'echo "run git commit now"',
        'echo "then merge it"',
        "git log --oneline && echo 'now commit'",
    ],
)
def test_quoted_text_nothing_runs_is_still_not_an_invocation(command: str):
    for word in ("commit", "merge"):
        assert not vp.is_invocation(command, word), (command, word)


def test_dir_from_command_reads_a_dash_c_inside_an_executed_argument():
    assert vp._dir_from_command('bash -c "git -C /c/wt commit -m x"') == "/c/wt"


def test_dir_from_command_still_ignores_a_dash_c_in_a_heredoc_body():
    # the body is data handed to git, not a command an interpreter runs
    c = "git commit -F - <<'EOF'\nsee git -C /evil/wt commit -m x\nEOF\n"
    assert vp._dir_from_command(c) is None


@pytest.mark.parametrize(
    "arith",
    ["((n = 1 << 2))", "$[1 << 2]", "let 'n = 1 << 2'"],
    ids=["bare", "dollar-bracket", "let"],
)
def test_arithmetic_left_shift_is_never_a_heredoc_introducer(arith: str):
    assert vp._dir_from_command(f"{arith}\ngit -C /c/wt commit -m x") == "/c/wt"


@pytest.mark.parametrize("prog", ["git.exe", "C:/Git/bin/git.exe", "/usr/bin/git"])
def test_the_program_token_may_carry_the_platform_suffix(prog: str):
    # `git.exe` is the native spelling on the host the gate runs on (Invariant #2).
    assert vp._dir_from_command(f"{prog} -C /a/wt commit -m x") == "/a/wt"


def test_a_quoted_program_name_is_still_the_program():
    # `'git' commit` runs a commit; the quotes are how the shell was told the name, not data.
    assert vp._dir_from_command("'git' -C /c/wt commit -m x") == "/c/wt"
    assert vp._dir_from_command('"git" -C /c/wt commit -m x') == "/c/wt"


@pytest.mark.parametrize("prog", ["mygit", "/usr/bin/mygit", "gitx.exe", "notgit.exe"])
def test_a_different_program_is_still_rejected(prog: str):
    assert vp._dir_from_command(f"{prog} -C /evil commit -m x") is None


def test_a_backslash_quoted_carriage_return_continues_a_line():
    # a CRLF-authored continuation: the backslash quotes the CR, and the newline still joins.
    assert vp._dir_from_command("git -C /c/wt \\\r\n  commit -m x") == "/c/wt"
