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
