"""Behavior spec for the shared helper _harness_paths — path SSOT, fallback helpers,
encoding defenses.

If this module breaks, path resolution in every gate script breaks along with it, so the
consolidated behavior is pinned here in one place (rather than each script carrying its own
host_root/force_utf8_io and tested it separately).
"""

import subprocess
from pathlib import Path

import pytest

import scripts._harness_paths as vp

_Q3 = chr(39) + chr(0) * 3 + chr(39)  # a quoted program, as the mask leaves it


def test_path_segment_constants():
    # the host write root and its subcategories are all gathered under
    # .claude/harness-tier/ (CLAUDE.md).
    assert vp.HARNESS_DIR == ".claude/harness-tier"
    assert vp.SCRIPTS_DIR == ".claude/harness-tier/scripts"
    assert vp.CONFIG_DIR == ".claude/harness-tier/config"
    assert vp.FLOW_DIR == ".claude/harness-tier/.flow"


def test_filename_constants():
    assert vp.CONFIG_FILENAME == "flow-config.yaml"
    assert vp.TIERS_FILENAME == "flow-tiers.yaml"


def test_gate_contract_constants():
    # Invariant #3: block = exit 2. Runtime gates and tier labels are byte-match targets
    # against yaml keys.
    assert vp.BLOCK_EXIT_CODE == 2
    assert "security-scan" in vp.RUNTIME_GATES
    assert vp.STAGING_TIER == "staging"
    assert vp.RELEASE_TIER == "release"


def test_path_helpers_compose_from_root(tmp_path: Path):
    assert vp.harness_dir(tmp_path) == tmp_path / ".claude" / "harness-tier"
    assert vp.config_dir(tmp_path) == tmp_path / ".claude" / "harness-tier" / "config"
    assert vp.flow_dir(tmp_path) == tmp_path / ".claude" / "harness-tier" / ".flow"
    assert vp.config_path(tmp_path) == (
        tmp_path / ".claude" / "harness-tier" / "config" / "flow-config.yaml"
    )


def test_host_root_prefers_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(tmp_path))
    assert vp.host_root() == tmp_path.resolve()


def test_host_root_fallback_no_crash(monkeypatch, tmp_path: Path):
    # env unset + git failure → cwd fallback when the marker (.claude) lookup fails
    # (no IndexError/crash).
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    monkeypatch.chdir(tmp_path)

    def boom(*_a, **_k):
        raise OSError("no git")

    monkeypatch.setattr(vp.subprocess, "run", boom)
    result = vp.host_root()
    assert isinstance(result, Path)  # path without marker → cwd fallback (no crash)


def test_plugin_root_prefers_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("CLAUDE_PLUGIN_ROOT", str(tmp_path))
    assert vp.plugin_root() == tmp_path


def test_plugin_root_fallback_is_scripts_parent(monkeypatch):
    monkeypatch.delenv("CLAUDE_PLUGIN_ROOT", raising=False)
    # _harness_paths.py lives in scripts/, so the fallback is its parent (the plugin root).
    assert vp.plugin_root() == Path(vp.__file__).resolve().parent.parent


def test_force_utf8_io_sets_pythonutf8(monkeypatch):
    # set PYTHONUTF8 so child python processes inherit the encoding (reinforces Invariant #2).
    monkeypatch.delenv("PYTHONUTF8", raising=False)
    vp.force_utf8_io()
    assert vp.os.environ.get("PYTHONUTF8") == "1"


# ── working_root: worktree-aware detection (branch-key ladder) ────────────────────
# The gate assumes "working tree = one CLAUDE_PROJECT_DIR". working_root detects the
# worktree where the commit runs, so git status/diff/tier-marker/module-lint
# all read that worktree. Non-worktree / uncertain → project_dir (FAIL-OPEN, Invariant #1).


def test_dir_from_command_dash_c():
    # ① `git -C <dir>` — the deterministic top-of-ladder signal (git overrides cwd).
    assert vp._dir_from_command('git -C /a/b commit -m "x"') == "/a/b"


def test_dir_from_command_dash_c_quoted():
    # a path with spaces is preserved via quote handling (conservative shell-lite parse).
    assert vp._dir_from_command('git -C "/a b/c" commit -m "x"') == "/a b/c"


def test_dir_from_command_cd_prefix():
    # ② leading `cd <dir> && … git commit`.
    assert vp._dir_from_command("cd /a/b && git commit -m 'x'") == "/a/b"


def test_dir_from_command_none_without_signal():
    assert vp._dir_from_command("git commit -m 'x'") is None
    assert vp._dir_from_command(None) is None


def test_dir_from_command_ignores_dash_c_inside_message():
    # `-C` inside the commit message (after the `commit` subcommand) must not be picked up
    # as a directory — only the global-options region before `commit` is scanned.
    assert vp._dir_from_command('git commit -m "use -C /wrong"') is None


def test_dir_from_command_survives_a_body_that_says_commit_before_the_git():
    # the commit skill builds its message in a quoted heredoc and pipes it, so the whole body
    # sits in the command string *ahead* of the git invocation. Ending the options region at the
    # first " commit" anywhere lands inside that body and loses the `-C` — the very signal the
    # skill tells the agent to write literally.
    command = "\n".join(
        [
            "msg=$(cat <<'EOF'",
            "fix(x): y",
            "",
            "- the runner takes the line for something that is not a commit",
            "EOF",
            ")",
            'printf %s "$msg" | git -C /a/b commit -F -',
        ]
    )
    assert vp._dir_from_command(command) == "/a/b"


def test_dir_from_command_ignores_a_git_commit_quoted_inside_the_message():
    # the message is an argument, so a `git -C <dir> commit` quoted inside it is text, not an
    # invocation. Reading it as the execution directory re-points ROOT at a tree the commit does
    # not run in — the gate then reads that tree's tier marker and staged files, which can both
    # newly block a classified commit and let an unclassified one through (Invariant #6).
    assert vp._dir_from_command('git -C /a commit -m "do not git -C /evil commit"') == "/a"
    assert vp._dir_from_command('git -C /a commit -m x && echo "git -C /b commit"') == "/a"
    assert vp._dir_from_command('echo "git -C /b commit" && git -C /a commit -m x') == "/a"


def test_dir_from_command_gives_up_on_two_real_invocations():
    # two unquoted `git … commit` in one command: which tree the gate should read is genuinely
    # ambiguous, and Invariant #6 answers ambiguity with the main repo, never a guess.
    assert vp._dir_from_command("git -C /a commit -m x && git -C /b commit -m y") is None


def test_dir_from_command_gives_up_without_taking_the_cd_prefix():
    # ambiguity has to end the read, not fall through to rung ②: the `cd` target is a third tree,
    # so answering with it re-points ROOT at a directory NEITHER commit runs in. A newly cd'd-into
    # worktree is usually clean, which makes the runner exit 0 and skip the gate in silence.
    assert vp._dir_from_command("cd /a && git -C /x commit -m 1 && git -C /y commit -m 2") is None


def test_dir_from_command_takes_two_invocations_that_agree():
    # commit-then-amend names one directory twice. Counting raw matches calls that ambiguous and
    # falls back to main, which rejects a correctly classified worktree commit — Invariant #6
    # forbids newly blocking. There is exactly one answer here, so it has to be given.
    assert vp._dir_from_command("git -C /a commit -m x && git -C /a commit --amend") == "/a"
    assert (
        vp._dir_from_command('git -C "/a b" commit -m x && git -C "/a b" commit --amend') == "/a b"
    )


def test_dir_from_command_dash_c_single_quoted():
    # `'…'` is the more idiomatic shell quoting for a path with a space, and the option-token
    # grammar has to read it exactly as it reads `"…"`.
    assert vp._dir_from_command("git -C '/a b/c' commit -m x") == "/a b/c"


def test_dir_from_command_reads_an_option_holding_a_lone_quote():
    # `-c user.name='a"b'` is one literal `"`, not the start of a span. The shell self-filter was
    # taught this; the resolver has to agree, or the gate engages and then reads the wrong tree.
    assert vp._dir_from_command("git -c user.name='a\"b' -C /wt commit -m x") == "/wt"


def test_dir_from_command_reads_an_escaped_quote_the_way_a_shell_does():
    # `'\''` is the only way to put an apostrophe inside a single-quoted string, and it is what
    # the commit skill's own template produces. Counting quotes without honouring the escape
    # leaves an odd tally, so every later quote pairs one position off.
    command = "printf '%s' 'fix: don'\\''t break it' | git -C /wt commit -F -"
    assert vp._dir_from_command(command) == "/wt"


def test_dir_from_command_ignores_a_git_commit_inside_a_heredoc_body():
    # a `<<'EOF'` body is literal text to the shell, so a command quoted in a commit message is
    # not an invocation — but it is not a *quoted span* either, and this repo's own commit bodies
    # routinely spell `git -C <wt> commit`. Reading the body's directory re-points ROOT at a tree
    # the commit does not run in.
    command = "\n".join(
        [
            "msg=$(cat <<'EOF'",
            "fix(gate): stop re-pointing ROOT",
            "",
            "- a worktree commit issued as git -C /evil commit was gated against main",
            "EOF",
            ")",
            "printf %s \"$msg\" | git -C '/a b/wt' commit -F -",
        ]
    )
    assert vp._dir_from_command(command) == "/a b/wt"


def test_dir_from_command_requires_the_word_git():
    # `git` unanchored matches the tail of another program's name, and the directory that follows
    # belongs to a command the gate knows nothing about.
    assert vp._dir_from_command("mygit -C /evil commit -m x") is None
    assert vp._dir_from_command("legit -C /evil commit -m x") is None
    # A directory prefix names the same program, so requiring the word must not reject one.
    assert vp._dir_from_command("/usr/bin/mygit -C /evil commit -m x") is None


@pytest.mark.parametrize(
    "prefix", ["/usr/bin/", "/usr/local/bin/", "C:/Git/bin/", "C:\\Git\\bin\\", "./"]
)
def test_dir_from_command_reads_a_path_qualified_git(prefix: str):
    """`/usr/bin/git … commit` is the same invocation, and the runner's self-filter — which is
    unanchored — agrees. Only this half stops recognising it, and that disagreement is the gate
    silently off: the hook engages, resolves no worktree, leaves ROOT on the main repo, and a
    clean main exits 0 with the commit never classified. Invariant #6."""
    assert vp._dir_from_command(f"{prefix}git -C /a/wt commit -m x") == "/a/wt"


def test_parse_worktree_list_blocks_and_detached():
    text = (
        "worktree /main\nHEAD abc\nbranch refs/heads/main\n\n"
        "worktree /wt-feat\nHEAD def\nbranch refs/heads/feature/x\n\n"
        "worktree /wt-detached\nHEAD 123\ndetached\n"
    )
    entries = vp._parse_worktree_list(text)
    assert ("/main", "main") in entries
    assert ("/wt-feat", "feature/x") in entries
    assert ("/wt-detached", None) in entries  # detached → no branch


def _has_git() -> bool:
    try:
        subprocess.run(["git", "--version"], capture_output=True, timeout=5)
        return True
    except Exception:
        return False


requires_git = pytest.mark.skipif(not _has_git(), reason="git not available")


def test_git_survives_non_utf8_output(tmp_path: Path):
    # A single non-UTF-8 byte anywhere in git's output makes the decode raise and the whole
    # call return None — the gate then fails open silently for that entire repository.
    # errors="replace" keeps the value: a path carrying a replacement character fails
    # to match, so only that one entry falls open, which is far narrower.
    if not _has_git():
        pytest.skip("git not available")
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    sha = (
        subprocess.run(
            ["git", "hash-object", "-w", "--stdin"],
            cwd=tmp_path,
            input=b"caf\xe9 latin-1\n",
            capture_output=True,
            check=True,
        )
        .stdout.decode()
        .strip()
    )
    out = vp._git(["cat-file", "blob", sha], tmp_path)
    assert out is not None and "caf" in out


def _run_git(args: list[str], cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True)


def _init_repo(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    _run_git(["init", "-b", "main"], path)
    _run_git(["config", "user.email", "t@e.st"], path)
    _run_git(["config", "user.name", "Test"], path)
    (path / "README.md").write_text("x", encoding="utf-8")
    _run_git(["add", "-A"], path)
    _run_git(["commit", "-m", "init"], path)


def _add_worktree(main: Path, wt: Path, branch: str) -> None:
    _run_git(["worktree", "add", "-b", branch, str(wt)], main)


@requires_git
def test_working_root_signal1_git_dash_c(tmp_path: Path):
    # ① `git -C <wt> commit` → W = that worktree's toplevel.
    main = tmp_path / "repo"
    _init_repo(main)
    wt = tmp_path / "repo-wt"
    _add_worktree(main, wt, "feature/x")
    got = vp.working_root(project_dir=main, hook_cwd=None, command=f'git -C {wt} commit -m "m"')
    assert got == wt.resolve()


@requires_git
def test_working_root_signal2_cd_prefix(tmp_path: Path):
    # ② `cd <wt> && git commit` → W = that worktree.
    main = tmp_path / "repo"
    _init_repo(main)
    wt = tmp_path / "repo-wt"
    _add_worktree(main, wt, "feature/x")
    got = vp.working_root(project_dir=main, hook_cwd=None, command=f"cd {wt} && git commit -m m")
    assert got == wt.resolve()


@requires_git
def test_working_root_signal3_cwd_bijection(tmp_path: Path):
    # ③ only hook cwd → learn branch B → the unique `git worktree list` entry with B.
    main = tmp_path / "repo"
    _init_repo(main)
    wt = tmp_path / "repo-wt"
    _add_worktree(main, wt, "feature/x")
    got = vp.working_root(project_dir=main, hook_cwd=str(wt), command=None)
    assert got == wt.resolve()


@requires_git
def test_working_root_signal4_fallback_main(tmp_path: Path):
    # ④ no directional signal → project_dir (current behavior).
    main = tmp_path / "repo"
    _init_repo(main)
    got = vp.working_root(project_dir=main, hook_cwd=None, command="git commit -m m")
    assert got == main.resolve()


@requires_git
def test_working_root_detached_returns_main(tmp_path: Path):
    # a detached-HEAD worktree has no branch → bijection fails → FAIL-OPEN to main.
    main = tmp_path / "repo"
    _init_repo(main)
    wt = tmp_path / "repo-wt"
    _add_worktree(main, wt, "feature/x")
    _run_git(["-C", str(wt), "checkout", "--detach"], main)
    got = vp.working_root(project_dir=main, hook_cwd=str(wt), command=None)
    assert got == main.resolve()


@requires_git
def test_working_root_different_repo_returns_main(tmp_path: Path):
    # `git -C <other-repo>` where other is a *different* repo → common-dir differs → main.
    main = tmp_path / "repo"
    _init_repo(main)
    other = tmp_path / "other"
    _init_repo(other)
    got = vp.working_root(project_dir=main, hook_cwd=None, command=f"git -C {other} commit -m m")
    assert got == main.resolve()


@requires_git
def test_working_root_sibling_prefix_same_repo(tmp_path: Path):
    # prefix trap: `…/kit` vs `…/kit-feature` (sibling, path prefix overlap) — a naive
    # startswith would (mis)judge, but common-dir equality correctly keeps same-repo.
    main = tmp_path / "kit"
    _init_repo(main)
    wt = tmp_path / "kit-feature"
    _add_worktree(main, wt, "feature/y")
    got = vp.working_root(project_dir=main, hook_cwd=None, command=f"git -C {wt} commit -m m")
    assert got == wt.resolve()


@requires_git
def test_working_root_sibling_prefix_different_repo(tmp_path: Path):
    # prefix trap, negative: `…/kit` vs `…/kit-other` share a prefix but are different repos —
    # common-dir equality correctly rejects (naive startswith would falsely accept).
    main = tmp_path / "kit"
    _init_repo(main)
    other = tmp_path / "kit-other"
    _init_repo(other)
    got = vp.working_root(project_dir=main, hook_cwd=None, command=f"git -C {other} commit -m m")
    assert got == main.resolve()


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
