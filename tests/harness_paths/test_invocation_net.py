import pytest

import scripts._harness_paths as vp

# The interpreter net. The channels that carry text into a shell are unbounded and the programs
# that run it are a list, so the net asks whether the command STARTS one and, if it does, reads
# the same grammar over the command with its quoting rubbed out.
NET_INVOCATIONS = [
    ("printf 'git commit -m x' | bash", "commit"),
    ('echo "git commit -m x" | sh', "commit"),
    ("eval $'git commit -m x'", "commit"),
    ("bash <<< 'git commit -m x'", "commit"),
    ("bash -s <<< 'git commit -m x'", "commit"),
    ("""perl -e 'system("git commit -m x")'""", "commit"),
    ("bash <<'EOF'\ngit commit -m x\nEOF", "commit"),
    ("printf 'git merge --no-ff dev' | bash", "merge"),
    ("bash <<< 'git merge --squash feature/x'", "merge"),
    ("source /dev/stdin <<< 'git commit -m x'", "commit"),
    ("node -e \"require('child_process').execSync('git commit -m x')\"", "commit"),
    # A backslash-escaped quote is quoting too, so the net has to rub it out with the quote
    # it escapes — the script here is `git "commit" -m x`.
    ('bash -c "git \\"commit\\" -m x"', "commit"),
    ("{ bash <<< 'git commit -m x'; }", "commit"),
]


@pytest.mark.parametrize("command,word", NET_INVOCATIONS, ids=[c for c, _ in NET_INVOCATIONS])
def test_text_an_interpreter_runs_is_read_as_the_invocation_it_is(command: str, word: str):
    assert vp.is_invocation(command, word)


@pytest.mark.parametrize("command,word", NET_INVOCATIONS, ids=[c for c, _ in NET_INVOCATIONS])
def test_every_net_case_is_one_the_precise_reading_misses(command: str, word: str):
    """Otherwise the corpus grows entries that never exercise the net and it can be deleted
    with the suite still green."""
    assert not vp.git_subcommand_re(word).search(vp.mask_literals(command))


# Spelled out rather than read from the module: a list that generates its own cases cannot
# fail when a name leaves it, which is the shape that already let one slip through here.
RUNS_TEXT = [
    "sh",
    "bash",
    "zsh",
    "dash",
    "ksh",
    "ash",
    "busybox",
    "eval",
    "source",
    "perl",
    "python",
    "python2",
    "python3",
    "ruby",
    "node",
    "pwsh",
    "powershell",
    "cmd",
]


def test_the_program_list_is_the_one_the_code_carries():
    assert sorted(RUNS_TEXT) == sorted(vp._RUNS_TEXT)


@pytest.mark.parametrize("name", RUNS_TEXT)
def test_the_net_fires_for_every_program_that_runs_text(name: str):
    """Through a pipe, because an interpreter's own `-c` argument is code the FIRST reading
    already sees — a case scored there proves nothing about the net."""
    command = f"printf 'git commit -m x' | {name}"
    assert not vp.git_subcommand_re("commit").search(vp.mask_literals(command)), command
    assert vp.is_invocation(command, "commit"), command


NET_MUST_NOT_FIRE = [
    # No program that runs text, so the net never looks: the word sits in data and stays data.
    'grep -rn "git commit" scripts/',
    "git log -1 --format=%s <<'EOF'\ngit -C /wt commit -m x\nEOF",
    'git -C "/c/wt" log --oneline -5 && echo "now commit"',
    "git -c commit.gpgsign=false log --oneline",
    # An interpreter NAMED as an argument is not one the command runs. These are the shapes a
    # developer writes all day, and `sh` is two letters that turn up in an option value.
    'rg "git commit" --type sh',
    'rg -t sh "git commit"',
    'ls /bin/sh && echo "git commit -m x"',
    'which bash; echo "git commit -m x"',
    'echo bash and then "git commit -m x"',
    'shellcheck -s bash scripts/*.sh && grep -rn "git commit" .',
    # A comment is never code, whatever runs beside it.
    "bash x.sh  # remember to git commit -m x",
    # Backslashes that quote nothing are path separators, not quoting.
    "bash C:\\git\\commit\\run.sh",
    # A quoted string that LOOKS like a command list is still data. The program has to be
    # found on the mask; found in the second reading instead, every one of these fires.
    "echo \"; bash -c 'git commit -m x'\"",
    'echo "| bash" && grep -rn "git commit" .',
    "cat <<'EOF'\n; bash -c 'git commit -m x'\nEOF",
    # A command list is read one element at a time. An interpreter in ANOTHER element does
    # not make this one's quoted text a script — otherwise every read-only command run
    # beside a python or a bash is denied, which is most of them.
    'python3 scripts/wiki_graph.py --verify && rg "git commit" scripts/',
    'rg "git commit" scripts/ && python3 scripts/wiki_graph.py --verify',
    'bash -c "echo ok"; grep -rn "git commit" .',
    'bash -c "echo ok"\ngrep -rn "git commit" .',
    'bash -c "echo ok" || grep -rn "git commit" .',
    "git log -1 --format=%s <<'EOF'\ngit -C /wt commit -m x\nEOF\npython3 -V",
    # An interpreter with no invocation in it either.
    "bash -c 'echo hello'",
    "python3 -c 'import sys; print(sys.version)'",
]


@pytest.mark.parametrize("command", NET_MUST_NOT_FIRE)
def test_the_net_does_not_widen_a_command_that_runs_no_commit(command: str):
    for word in ("commit", "merge"):
        assert not vp.is_invocation(command, word), (command, word)
