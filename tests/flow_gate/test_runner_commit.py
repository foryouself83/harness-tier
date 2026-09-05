import json
from pathlib import Path

import pytest
import yaml

from tests.flow_gate._helpers import (
    _classify_worktree_module,
    _init_repo,
    _rg,
    _run_runner,
    requires_bash_git,
)


@requires_bash_git
def test_runner_gates_worktree_commit_via_git_dash_c(tmp_path: Path):
    # end-to-end: `git -C <wt> commit` must (1) pass the commit self-filter despite the `-C <dir>`
    # between `git` and `commit`, then (2) re-point ROOT=W so the module pre-check reads the
    # worktree's staged files. If either breaks, W's `echo LINT_RAN` would not appear (DRYRUN).
    main = tmp_path / "main"
    _init_repo(main)
    wt = tmp_path / "wt"
    _rg(["worktree", "add", "-b", "feature/x", str(wt)], main)
    _classify_worktree_module(wt)
    r = _run_runner(main, f"git -C {wt} commit -m x")
    assert "echo LINT_RAN" in (r.stdout + r.stderr)  # gate ran against W


@requires_bash_git
@pytest.mark.parametrize("quote", ['"', "'"])
def test_runner_gates_a_worktree_commit_whose_path_holds_a_space(tmp_path: Path, quote: str):
    # the same end-to-end path as the test above, with the one difference a Windows host makes
    # routine: a directory name with a space, which the command must quote. An option-argument
    # token that stops at whitespace ends the self-filter's scan inside the quotes, so the runner
    # reads the line as "not a commit" and every gate behind it is skipped in silence. Both quote
    # characters, because covering only one certifies the half of the grammar that works.
    main = tmp_path / "main"
    _init_repo(main)
    wt = tmp_path / "wt with space"
    _rg(["worktree", "add", "-b", "feature/x", str(wt)], main)
    _classify_worktree_module(wt)
    r = _run_runner(main, f"git -C {quote}{wt}{quote} commit -m x")
    assert "echo LINT_RAN" in (r.stdout + r.stderr)  # gate ran against W


@requires_bash_git
def test_runner_leaves_a_read_only_command_that_mentions_committing_alone(tmp_path: Path):
    # a token that crosses whitespace by pairing one string's closing quote with a later string's
    # opening quote turns `git log … && echo "… commit"` into a commit, and the tree below — dirty
    # and unclassified — is exactly where that gets denied. The gate blocking a read-only command
    # is the mirror image of the silent skip above, and as wrong.
    main = tmp_path / "main"
    _init_repo(main)
    (main / ".claude" / "harness-tier" / "config").mkdir(parents=True)
    (main / ".claude" / "harness-tier" / "config" / "flow-config.yaml").write_text(
        "modules: []\n", encoding="utf-8"
    )
    r = _run_runner(main, 'git -c user.email="a@b.c" log --oneline && echo "please commit"')
    assert r.returncode == 0, (r.returncode, r.stdout, r.stderr)


@requires_bash_git
def test_runner_gates_a_commit_whose_option_holds_an_unpaired_quote(tmp_path: Path):
    # A `"` inside a single-quoted option value is one literal character, not the start of a
    # quoted span. Read as one, the span swallows the subcommand, the command is not an
    # invocation, and every gate behind it is skipped in silence (Invariant #1). The grammar
    # is pinned on this spelling by the corpus in test_skills.py; what this adds is the whole
    # chain — pre-filter, --classify, ROOT, the flow gate — on a command that carries quotes.
    # The deny below is the proof it engaged: an unclassified commit is one of the three
    # things the gate does block.
    main = tmp_path / "main"
    _init_repo(main)
    (main / ".claude" / "harness-tier" / "config").mkdir(parents=True)
    (main / ".claude" / "harness-tier" / "config" / "flow-config.yaml").write_text(
        "modules: []\n", encoding="utf-8"
    )
    r = _run_runner(main, "git -c user.name='a\"b' commit -m x")
    assert r.returncode == 2, (r.returncode, r.stdout, r.stderr)


@requires_bash_git
def test_deny_json_survives_a_quote_bearing_command(tmp_path: Path):
    # deny() interpolates the failing command into the permissionDecisionReason JSON string.
    # The wiki gate's command is the first plugin-generated one that ALWAYS carries double
    # quotes and, on Windows, backslashes — raw, the `"` closes the string early and `\r`
    # is an invalid JSON escape, so the payload is malformed exactly when the gate blocks.
    # ESC stands in for the rest of the C0 range, which JSON forbids raw and which has no
    # short escape: the wiki gate quotes a git subject line into its reason, and a subject
    # holds whatever was pasted into it.
    main = tmp_path / "main"
    _init_repo(main)
    wt = tmp_path / "wt"
    _rg(["worktree", "add", "-b", "feature/x", str(wt)], main)
    _classify_worktree_module(wt)
    command = 'echo "C:\\repo" \x1b >/dev/null; exit 1'
    (wt / ".claude" / "harness-tier" / "config" / "flow-config.yaml").write_text(
        yaml.safe_dump(
            {"modules": [{"name": "api", "path": "services/api/", "checks": {"lint": command}}]},
            allow_unicode=True,
        ),
        encoding="utf-8",
    )
    r = _run_runner(main, f"git -C {wt} commit -m x", dryrun=False)
    assert r.returncode == 2
    payload = json.loads(r.stdout.strip())  # raises on an unescaped quote/backslash/control
    reason = payload["hookSpecificOutput"]["permissionDecisionReason"]
    assert 'echo "C:\\repo"' in reason  # …and the command survives the escaping intact
    assert "\x1b" not in reason  # the control character is dropped, not smuggled through


@requires_bash_git
def test_runner_ignores_commit_graph_subcommand(tmp_path: Path):
    # `git -C <wt> commit-graph write` is NOT a commit — the whole-word match must not fire,
    # else a non-commit git command would be gated (false block risk).
    main = tmp_path / "main"
    _init_repo(main)
    wt = tmp_path / "wt"
    _rg(["worktree", "add", "-b", "feature/x", str(wt)], main)
    _classify_worktree_module(wt)
    r = _run_runner(main, f"git -C {wt} commit-graph write")
    assert "echo LINT_RAN" not in (r.stdout + r.stderr)
    assert r.returncode == 0
