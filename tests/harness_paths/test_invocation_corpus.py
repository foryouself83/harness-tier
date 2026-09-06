import pytest

import scripts._harness_paths as vp

# Commands a shell does run as a commit or a merge, each one a spelling a reading
# missed. Kept apart from NET_INVOCATIONS: these are not an interpreter being handed a
# script, they are places the mask or the grammar was wrong about what bash does.
RUNS_A_COMMIT = [
    # A reader that runs what its environment names, verified under a real bash with a
    # stub `git`: the assignment is neither the program nor its argument.
    ("LESSOPEN='|git commit -m x %s' less -f big.txt", "commit"),
    ("LESSCLOSE='git commit -m x %s %s' LESSOPEN='|cat %s' less -f big.txt", "commit"),
    ("cat f | LESSOPEN='|git commit -m x %s' less -f big.txt", "commit"),
    # a backtick inside a double-quoted span swallowed the rest of the command
    ('echo "`date`" && git commit -m x', "commit"),
    ('echo "`date`" && git merge --squash feature/x', "merge"),
    # an UNQUOTED delimiter leaves expansion on, so the body is code and not text — a
    # backtick opens one as much as a `$(`, and a backslash before one does not
    ("git log --oneline <<EOF\nnote $(git commit -am wip)\nEOF", "commit"),
    ("git log --oneline <<EOF\nnote `git commit -am wip`\nEOF", "commit"),
    ("git log --oneline <<EOF\na \\$(x) $(git commit -am wip)\nEOF", "commit"),
    # a substitution written as `$((` is one too — a reader in front of it does not
    # make the output it runs data
    ('cat $((echo "git commit -m x") )', "commit"),
    # `&` ends a command as well as carrying a redirection's fd, and the program of
    # the command after it is a program like any other
    ("cat f & xargs 'git' commit -m x", "commit"),
    # a reserved word standing behind a prefix introduces the command after it. Read
    # as the program itself it was dropped further on for being reserved, and the
    # quoted program behind it went unmentioned — the last two need the lookback to
    # see a whole reserved word behind the one it is asking about.
    ("cat f | A=1 time 'git' commit -m x", "commit"),
    ("cat f | 2>/dev/null time 'git' commit -m x", "commit"),
    ("cat f | > /dev/null time 'git' commit -m x", "commit"),
    ("cat f | > /dev/null time 'git' merge --no-ff dev", "merge"),
    ("! time 'git' commit -m x | cat f", "commit"),
    ("if true; then time 'git' commit -m x | cat f; fi", "commit"),
    ("for i in 1; do time 'git' commit -m x | cat f; done", "commit"),
    # a program the scan cannot NAME is one the exemption is decided without. Both ways
    # it goes unnamed run a commit a real bash was made to run here: the program is
    # written quoted, which the mask blanks, or it stands behind a `!`, a redirection or
    # an assignment, where the scan looks for a name and finds punctuation.
    ("time cat a.txt | > /dev/null 'git' commit -m x", "commit"),
    ("time grep -q x a.txt | >> out.txt 'git' commit -m x", "commit"),
    ('time echo hi | > /dev/null "git" commit -m x', "commit"),
    ("time cat a.txt | > /dev/null 'git' merge --no-ff dev", "merge"),
    ("time 'git' commit -m x | echo hi", "commit"),
    ("true | time 'git' commit -m x", "commit"),
    ("echo hi | time 'git' commit -m x | grep -q x a.txt", "commit"),
    ("sort a.txt | > /dev/null 'git' commit -m x", "commit"),
    ("for i in 1; do cat a.txt | > /dev/null 'git' commit -m x; done", "commit"),
    ("if true; then cat a.txt | > /dev/null 'git' commit -m x; fi", "commit"),
    ("while true; do echo hi | > /dev/null 'git' commit -m x; break; done", "commit"),
    ("LC_ALL=C cat f | > /dev/null 'git' commit -m x", "commit"),
    # a separator inside the SECOND substitution is no element boundary either: the
    # pointer has to walk to the span the separator sits in, not stop at the first one
    ('echo $(date); $(true; echo "git commit -m x")', "commit"),
    (
        'x=$(date) ; $(date > /dev/null; echo "git merge --no-ff dev")',
        "merge",
    ),
    # the subcommand's terminator has to admit everything that ends a word
    ("echo `git commit`", "commit"),
    ("git commit>log.txt", "commit"),
    ("git commit>>log", "commit"),
    ("git commit<msg.txt", "commit"),
    ("git merge>log", "merge"),
    # `(( … ))` is arithmetic wherever a command may start, not only after a separator —
    # every reserved word a command may follow, not only the two that open a block
    ("if (( 1 << 2 )); then\n  git commit -m x\nfi", "commit"),
    ("while true; do (( i << 1 )); git commit -m x; done", "commit"),
    ("until false; do (( 1 << 2 )); git commit -m x; done", "commit"),
    ("case x in y) (( 1 << 2 )); git commit -m x;; esac", "commit"),
    ("while (( i << 1 )); do\n  git merge --no-ff dev\ndone", "merge"),
    ("{ (( 1 << 2 )); git commit -m x; }", "commit"),
    # and every word a command may follow, which only a second line shows: on one line the
    # heredoc that left shift opens has no body to swallow the commit with
    ("if x; then (( 1 << 2 )); fi\ngit commit -m x", "commit"),
    ("until false; do (( 1 << 2 )); done\ngit commit -m x", "commit"),
    # a backslash inside a double-quoted span quotes the quote after it, so the span ends
    # where the shell ends it and the command after it is still a command
    ('echo "he said \\"hi\\""\ngit commit -m x', "commit"),
    ('echo "a \\" b" && git commit -m x', "commit"),
    # a global option's value is one token however it is quoted, or the options region never
    # reaches the subcommand
    ("git -c 'user.name=A B' commit -m x", "commit"),
    ('git -c "user.name=A B" commit -m x', "commit"),
    ("git -c 'user.email=a b' merge --squash feature/x", "merge"),
    # the subcommand word may be quoted or split, exactly as the program token may be
    ('git "commit" -m x', "commit"),
    ("git 'commit' -m x", "commit"),
    ("git 'merge' --no-ff dev", "merge"),
    # a searching or listing tool is exempt from the second reading, so one that can run a
    # command written in its own arguments may not be on that list
    ("awk 'BEGIN{system(\"git commit -m x\")}'", "commit"),
    ('awk \'BEGIN{print "x" | "git commit -m x"}\' a.txt', "commit"),
    ("sed '1e git merge --no-ff dev' a.txt", "merge"),
    ("find . -exec 'git' commit -m x ;", "commit"),
    ("find . -exec git 'commit' -m x ;", "commit"),
    ("ack --pager='git commit -m x' pattern .", "commit"),
    # a shell written over several lines puts a reserved word at the very start of an
    # element, where the scan has to find the program the word introduces without ever
    # claiming the word again — the corpus shapes with a blank after the separator do not
    # reach that
    ("time 'git' commit -m x", "commit"),
    ("if [ -f a ]; then git commit -m x; fi", "commit"),
    ("for f in a\ndo\ngit commit -m x\ndone", "commit"),
    # what a substitution prints is a command, so a heredoc it is handed is a script even
    # when the element names no interpreter of its own
    ("$(cat <<'EOT'\ngit commit -m x\nEOT\n)", "commit"),
    ('X=$(cat <<EOT\ngit commit -m x\nEOT\n); eval "$X"', "commit"),
    ("`head -1 <<'EOT'\ngit merge --no-ff dev\nEOT\n`", "merge"),
    # a separator inside a substitution ends nothing: split there, the tail is an element
    # whose only program reads and the exemption comes straight back
    ('$(date > /dev/null; echo "git commit -m x")', "commit"),
    ('$(\n  echo "git commit -m wip"\n)', "commit"),
    ('`true; echo "git merge --no-ff dev"`', "merge"),
    ('CMD=$(\n  echo "git commit -m x"\n)\neval "$CMD"', "commit"),
    # the host spells an interpreter with the path it has, with or without a blank after it
    ("bash.exe <<'EOF'\ngit commit -m x\nEOF", "commit"),
    ("bash<<'EOF'\ngit commit -m x\nEOF", "commit"),
    ("/bin/sh <<'EOF'\ngit commit -m x\nEOF", "commit"),
    # an interpreter is one wherever it is written. A reserved word, a prefix command, an
    # assignment and a redirection in front of it are all still the interpreter running,
    # and the heredoc it is handed is a script in every one of them
    ("if true; then bash <<'EOF'\ngit commit -m x\nEOF\nfi", "commit"),
    ("time bash <<'EOF'\ngit commit -m x\nEOF", "commit"),
    ("A=1 bash <<'EOF'\ngit commit -m x\nEOF", "commit"),
    ("2>/dev/null bash <<'EOF'\ngit commit -m x\nEOF", "commit"),
    # an element that expands a substitution runs what that prints, so the reader written
    # inside it is not the program the element runs — and where the substitution sits is
    # not the question: `!`, a redirection, an assignment and every prefix command stand
    # between it and the command position
    ('! $(echo "git commit -m x")', "commit"),
    ('> /dev/null $(echo "git commit -m x")', "commit"),
    ('if true; then ! $(echo "git commit -m x"); fi', "commit"),
    ('time env $(echo "git commit -m x")', "commit"),
    ('for i in 1; do ! `echo "git merge --no-ff dev"`; done', "merge"),
    ('$(echo "git commit -m x")', "commit"),
    ('`echo "git commit -m x"`', "commit"),
    ('$(echo "git merge --no-ff dev")', "merge"),
    # a program that runs its arguments as a command is not a reader, and the list is only
    # as good as a case that notices a name arriving on it. A name is compared whole, so a
    # reader's own name with anything appended to it is a different program
    ("env -S 'git commit -m x'", "commit"),
    ("cat.sh 'git commit -m x'", "commit"),
    # `$((` is a substitution holding a subshell as readily as it is arithmetic, and the
    # shell runs what the first one prints
    ('$((echo "git commit -m x") )', "commit"),
    ("ls | xargs 'git' commit -m x", "commit"),
    ('cat a.txt | xargs "git" merge --no-ff dev', "merge"),
    # text a builtin runs later, and text a variable holds for something else to run
    ("trap 'git commit -m x' EXIT; true", "commit"),
    ('C="git commit -m x"; eval "$C"', "commit"),
]


@pytest.mark.parametrize("command,word", RUNS_A_COMMIT, ids=[c for c, _ in RUNS_A_COMMIT])
def test_a_command_a_shell_really_runs_is_read_as_one(command: str, word: str):
    assert vp.is_invocation(command, word)


# Read-only work. Denying one of these is the gate blocking work it was never meant to
# see, and the user cannot tell that deny apart from a real verdict.
RUNS_NO_COMMIT = [
    # the fd a redirection duplicates is written after `<` as well as after `>`, the
    # `&` between them belongs to the redirection, and `>>` is a redirection too
    "grep -rn 'git commit' . 0<&3",
    "cat f | 2>&1 grep 'git commit' .",
    "cat f | >> out.txt grep 'git commit'",
    # an interpreter's name has to END where the token does: `nodemon` is not `node`
    "nodemon <<EOF\ngit commit -m x\nEOF",
    "bashful <<EOF\ngit commit -m x\nEOF",
    # the `&` of a `2>&1` starts no command, and the fd after it is not a program:
    # counted as one it is on no reader's list and a piped-and-redirected grep was
    # denied
    "grep -rn 'git commit' . 2>&1 | head -20",
    "grep 'git commit' f 1>&2",
    "cat f 2>&1 | grep 'git commit'",
    # `!` is one of the things that may stand in front of a program, so the reader
    # behind it is still the program the exemption is decided over
    "! grep -q 'git commit' f",
    "! rg 'git commit' .",
    # a reader keeps its exemption however the host spells its path
    "/usr/bin/grep -rn 'git commit' .",
    "./grep -rn 'git commit' .",
    # the walk over what may stand in front of a program is what keeps these exempt:
    # a redirection ahead of the program, and a start that opens no command at all
    "cat f | > out.txt grep 'git commit'",
    "{ grep -q 'git commit' f; }",
    "grep -q 'git commit' f;",
    # a reserved word is reserved only where a command may start; read as one in an
    # argument, the quoted text after it is a program the scan cannot name and the
    # element stops being exempt — a denial nothing runs
    'echo bash and then "git commit -m x"',
    'echo "the time is now" | grep "git commit"',
    "cat notes | grep -n 'then git commit'",
    "grep -rn 'git commit' . > out.txt",
    "grep -q 'git commit' f && echo yes",
    "for f in *.md; do grep -c 'git commit' $f; done",
    # a count flag is not an interpreter's `-c`
    'grep -c "git commit" a.txt',
    'grep -rc "git commit" .',
    'rg -c "git commit" --glob *.md',
    'sort -c "git commit"',
    # a continued line is one command, not a new one, so its quoted argument stays data
    "grep -rn \\\n  'git commit' scripts/",
    "echo \\\n  'about to git commit'",
    "rg --hidden \\\n   'git merge --no-ff' docs/",
    # the host spells a reader with the suffix it has, and the exemption is by name
    'grep.exe -c "git commit" a.txt',
    'rg.exe -n "git commit" .',
    # a tool that runs a program by PATH rather than a shell string spells no command
    "sort --compress-program='git commit -m x' f",
    "rg --pre 'git commit' pattern .",
    # a reader inside a loop or a conditional is still the only program there, wherever the
    # reserved word sits — including at the very start, where a scan can wrongly claim the
    # word itself as the program and never reach the one it introduces
    ("time grep 'git commit' a.txt"),
    ("if grep -q 'git commit' a.txt; then echo hi; fi"),
    ("while grep -q 'git commit' a.txt; do echo hi; break; done"),
    ("until grep -q 'git commit' a.txt; do echo hi; break; done"),
    # a name that merely ENDS with an interpreter's is not one
    ("rebash <<EOF\ngit commit -m x\nEOF"),
    ("for f in *; do grep -n 'git commit' $f; done"),
    ("if true; then echo 'git commit'; fi"),
    ('while read l; do echo "git commit"; done < a.txt'),
    # a backslash before a `$(` leaves it text, and a heredoc body runs to its terminator
    # rather than to the first quote in it
    ("cat <<EOF\n\\$(git commit -am wip)\nEOF"),
    ('cat <<EOF\nsay "hi" then git commit -m x\nEOF'),
    # an escaped separator is a literal character, not the end of a command
    "echo a\\; 'git commit'",
]


@pytest.mark.parametrize("command", RUNS_NO_COMMIT)
def test_read_only_work_is_not_read_as_a_commit(command: str):
    for word in ("commit", "merge"):
        assert not vp.is_invocation(command, word), (command, word)
