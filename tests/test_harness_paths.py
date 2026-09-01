"""Behavior spec for the shared helper _harness_paths — path SSOT, fallback helpers,
encoding defenses.

If this module breaks, path resolution in every gate script breaks along with it, so the
consolidated behavior is pinned here in one place (previously each script carried its own
host_root/force_utf8_io and tested it separately).
"""

import subprocess
from pathlib import Path

import pytest

import scripts._harness_paths as vp


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
# worktree where the commit actually runs, so git status/diff/tier-marker/module-lint
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
    # so answering with it re-points ROOT at a directory NEITHER commit runs in. A just-cd'd-into
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
    # errors="replace" keeps the value: a path carrying a replacement character simply fails
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
    # the word-start test has to accept a newline, not just the start of the string.
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
    # is the shape this option actually carries and dropping them resolves nothing.
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
