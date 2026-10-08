"""Commands the bash oracle runs, and the gaps the merge path knowingly leaves.

A row is a command, or (command, "flags") where a substitution prints into the merge's words
and only the flags can agree. A KNOWN_GAPS entry runs as a strict xfail: fixing the gap turns
it into a failure that asks for the entry to go."""

_BS = chr(92)
_NL = chr(10)

CORPUS: list = [
    "eval git merge feature/a ';' git merge --squash feature/x",
    "eval git merge feature/a " + _BS + "; git merge --squash feature/x",
    "eval git merge feature/a 'x;' git merge --squash feature/x",
    "eval >|o git merge feature/a ';' git merge --squash feature/x",
    "eval git mer''ge feature/a ';' git mer''ge --squash feature/x",
    "eval git switch main ';' git merge stage",
    "eval git switch main " + _BS + "; git merge --no-ff stage",
    "watch -x git merge -m 'a;b' --no-ff fix/x",
    "watch --exec git merge -m 'a;b' --no-ff fix/x",
    "eval git merge -m 'a;b' --no-ff fix/x",
    "eval git merge '2>&1' --no-ff fix/x",
    "eval git merge '&>o' --no-ff fix/x",
    "eval git merge '>|o' --no-ff fix/x",
    "ssh h git merge '2>&1' --no-ff fix/x",
    "eval git switch main '2>&1' ';' git merge stage",
    "eval git merge feature/x '#;' --squash",
    "eval git merge feature/x '#' --squash",
    "eval git mer''ge feature/x '#' --squash",
    "eval git mer''ge '2>&1' --no-ff fix/x",
    "watch -x git mer''ge -m 'a#' --no-ff fix/x",
    "eval git merge -m \"'a\" \"b'\" feature/x ';' --squash",
    "eval eval git merge feature/x \"';'\" --squash",
    "builtin eval git merge feature/x ';' --squash",
    "watch eval git merge feature/x \"';'\" --squash",
    "ssh eval git merge -m \"'a;b'\" --no-ff fix/x",
    "eval git merge --squash feature/x ';' git mer''ge --no-ff fix/x",
    "watch -n 1 eval git merge feature/x \"';'\" --squash",
    "ssh h eval git merge feature/x \"';'\" --squash",
    "ssh -p 22 user@h eval git merge feature/x \"';'\" --squash",
    "ssh -o X=1 -p22 h eval git merge feature/x \"';'\" --squash",
    "eval git merge feature/x '>' --squash",
    "eval eval git merge feature/x '>' --squash",
    "eval git merge feature/x '2>' --squash",
    "eval git merge feature/x '>>' --squash",
    "eval git merge feature/x '>|' --squash",
    "eval git merge feature/x '&>' --squash",
    "eval git merge feature/x " + _BS + "> --squash",
    "eval git mer''ge feature/x '>' --squash",
    "ssh h git mer''ge feature/x '>' --squash",
    "watch -n1 eval git mer''ge feature/x '>' --squash",
    "eval git merge feature/x '>o' --squash",
    "eval eval git merge feature/x \"'<<<'\" --squash",
    "eval git merge feature/x '<<<' --squash",
    "eval git merge feature/x '<<' --squash",
    "eval git merge feature/x '<<-' --squash",
    "eval eval git merge feature/x \"'$(git merge --no-ff fix/y)'\" --squash",
    "eval eval true ';' echo \"'" + _BS + "$(git merge --no-ff fix/y)'\"",
    "eval echo '#' '$(git switch stage)'; git merge feature/x",
    "eval echo \"'a\" '$(git switch stage)' \"'\"; git merge feature/x",
    "watch -n1 echo '#' '$(git switch stage)'; git merge feature/x",
    "eval echo '#' '$(git checkout stage)' && git merge feature/x",
    "ssh -o '$(git switch stage)' h true; git merge feature/x",
    "eval echo '#' '$(git merge --no-ff fix/y)'",
    "eval echo \"'" + _BS + "$(git merge --no-ff fix/y)'\"",
    "eval eval git merge -m 'a" + _BS + _NL + "b' --no-ff fix/x",
    'eval eval git merge -m "a' + _BS + _NL + 'b" --no-ff fix/x',
    "watch -n 1 eval git merge -m 'a" + _BS + _NL + "b' --no-ff fix/x",
    "ssh h eval git merge -m 'a" + _BS + _NL + "b' --no-ff fix/x",
    'ssh -p 22 h eval git merge -m "a' + _BS + _NL + 'b" --no-ff fix/x',
    "git switch dev && ssh h 'echo $(git switch main)' && git merge feature/x",
    "eval 'git switch dev; git merge --no-ff fix/x'",
    'eval "git -C /tmp merge x"',
    "eval echo $(git merge --no-ff fix/y)",
    "eval git merge feature/x # --squash",
    "eval echo 'git switch main;' git merge feature/x",
    "eval printf '%s' 'git switch main' ';' git merge feature/x",
    "cat > notes.md <<EOF"
    + _NL
    + "  eval git merge feature/x"
    + _NL
    + "EOF"
    + _NL
    + "git merge --squash feature/x",
    "git merge --no-ff fix/x; " + "eval " * 130 + "echo " + "x" * 400,
    "eval 'eval git merge --no-ff fix/x'",
    "bash -c 'eval git switch dev' && git merge feature/x",
    "env git switch dev; git merge feature/x",
]

_OVER = "; the reader judges it (over-block)"
_SUB = "a substitution in the words eval, watch or ssh parse again is not read as it is there"
_QUOTED = "a quoted command ssh or watch runs is not read as a command"
_SPLIT = "the words eval parses again are not split as it splits them"
_ECHO = "a switch another program's argument names is read as moving HEAD"

KNOWN_GAPS: dict = {
    "eval git merge fix/x '$(case x in a) echo;; esac)' --no-ff": (
        "a case pattern's ) closes the substitution early on the mask"
    ),
    'git merge feature/x $(echo ")"; git merge --no-ff fix/y)': (
        "a quoted ) inside a substitution closes it on the mask"
    ),
    "eval 'git merge --no-ff fix/y; echo \"x'": "bash runs no part of a line that fails" + _OVER,
    "eval git merge '--no-f$(echo)f' fix/x": "a flag a substitution assembles is unknown",
    "find . -name eval -exec git merge -m 'a;b' --no-ff fix/x " + _BS + ";": (
        "find runs -exec only on a file it finds" + _OVER
    ),
    "timeout -s eval 5 git merge -m 'x;y' --no-ff fix/x": "timeout rejects the signal" + _OVER,
    "watch -x eval git merge feature/x ';' --squash": "watch -x cannot exec a builtin" + _OVER,
    "eval git merge feature/x '<' --squash": (
        "redirecting from a missing file runs nothing" + _OVER
    ),
    "eval git merge feature/x '<$(echo)' --squash": (
        "redirecting from a missing file runs nothing" + _OVER
    ),
    "eval git merge fix/x '$(echo)' --no-ff": _SUB,
    "eval git merge fix/x '$(echo a; echo b)' --no-ff": _SUB,
    "eval git merge fix/x '$(echo #c" + _NL + ")' --no-ff": _SUB,
    "eval git merge -m '$(echo)' --no-ff fix/x": _SUB,
    "eval git merge feature/x '$(echo)' '>' --squash": _SUB,
    "eval git merge feature/x '$((1+2))' --squash": _SUB,
    "eval git merge feature/x '$((1<<2))' --squash": _SUB,
    "eval git merge feature/x '$(echo a; echo b)' --squash": _SUB,
    "eval git merge feature/x '`echo a; echo b`' --squash": _SUB,
    "eval git merge feature/x '$(echo \"#\")' --squash": _SUB,
    "eval git merge feature/x '$(git merge --no-ff fix/y)' --squash": _SUB,
    "eval git merge feature/x '$(git mer''ge --no-ff fix/y)' --squash": _SUB,
    "eval git merge feature/x '<(git merge --no-ff fix/y)' --squash": _SUB,
    "eval git merge feature/x '`git merge --no-ff fix/y`' --squash": _SUB,
    "ssh h git merge feature/x '$(git merge --no-ff fix/y)' --squash": _SUB,
    "watch -n1 git merge feature/x '$(git merge --no-ff fix/y)' --squash": _SUB,
    "eval eval git merge feature/x \"'" + _BS + "$(git merge --no-ff fix/y)'\" --squash": _SUB,
    "eval eval git merge feature/x '$(git merge --no-ff fix/y)' --squash": _SUB,
    "ssh h eval git merge feature/x '$(git merge --no-ff fix/y)' --squash": _SUB,
    "eval ssh h git merge feature/x '$(git merge --no-ff fix/y)' --squash": _SUB,
    "eval eval echo '$(git merge --no-ff fix/y)'": _SUB,
    "eval true ';' eval echo \"'" + _BS + "$(git merge --no-ff fix/y)'\"": _SUB,
    "eval echo '$(git merge --no-ff fix/y)'": _SUB,
    "eval echo '$(git merge --squash feature/y)'": _SUB,
    "FOO=\"'\" eval git merge feature/x '$(git merge --no-ff fix/y)' --squash": _SUB,
    "ssh -o '#' h git merge feature/x '$(git merge --no-ff fix/y)' --squash": _SUB,
    "ssh h 'git merge --no-ff fix/x'": _QUOTED,
    "watch 'git merge --no-ff fix/x'": _QUOTED,
    "watch -n1 'git switch dev; git merge feature/x'": _QUOTED,
    "git switch dev && eval echo '$(git switch dev)' && git merge feature/x": _SUB,
    "eval " + "git merge --squash feature/x " * 3: _SPLIT,
    "eval FOO='$(git merge --no-ff fix/y)' true": _SUB,
    "eval $'git merge b" + _BS + "necho \"y'": _SPLIT,
    "echo git switch main; git merge feature/x": _ECHO,
    "eval 'true;' 'git merge --no-ff fix/x'": _SPLIT,
    "eval 'true |' 'git merge --no-ff fix/x'": _SPLIT,
    "eval 'git merge -m \"x;y\" --no-ff fix/x'": _SPLIT,
}
