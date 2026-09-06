import re
from pathlib import Path

import pytest

import scripts._harness_paths as vp
from tests.skills._helpers import (
    REPO,
    SHIPPED_RULES,
    SKILL_IDS,
    SKILLS,
    bash_rule_matches,
    frontmatter,
)


def issued_commands(skill: Path) -> list[str]:
    """Every shell command a skill can issue — the ground truth a rule is measured against.

    Three sources, because a skill issues commands in three shapes and a rule is dead if
    it matches none of them:

    * fenced ```bash blocks in the SKILL.md;
    * the same in its `references/`, which the skill loads and follows (performance's
      k6/lizard invocations live only there);
    * inline `` `touch ...` `` in prose (an argument required — a bare one-word token like
      `lizard` or `testDir` is a name, not a command, and counting names let a rule "match
      a command" that the skill only ever mentions) — flow records its gate markers this
      way, so a body-blocks-only scan reports its `touch` rules as dead when they are not.

    Compound commands are split on `&&`/`||`/`;`/`|`: the permission check sees each
    sub-command, so `mkdir -p X && touch Y` is two commands, not one.
    """
    text = "\n".join(
        p.read_text(encoding="utf-8")
        for p in [skill, *sorted(skill.parent.glob("references/*.md"))]
    )
    raw: list[str] = []
    for block in re.findall(r"```bash\n(.*?)```", text, re.DOTALL):
        raw += [ln for ln in block.splitlines() if ln.strip() and not ln.strip().startswith("#")]
    raw += re.findall(r"`([a-z][\w.-]* [^`\n]+)`", text)
    out = []
    for line in raw:
        for part in re.split(r"\s*(?:&&|\|\||;|\|)\s*", line.strip()):
            part = part.split("#")[0].strip()
            if part:
                out.append(part)
    return out


# Commands that must keep prompting. Each is a decision the skill's own prose routes
# through the user, and a permission grant would quietly step around that prose.
MUST_STILL_PROMPT = {
    "flow": ["git commit -m 'x'", "rm -rf .claude/harness-tier/.flow", "git switch -c feature/x"],
    "doc-sync": ["rm -rf .claude/harness-tier/.flow"],
    "performance": ["pip install lizard", "npx @grafana/openapi-to-k6 --version"],
    "integration": ["npx playwright install chromium", "npm install -D @playwright/test"],
}


def declared_rules(skill: Path) -> list[str]:
    entries = frontmatter(skill).get("allowed-tools", "")
    if not isinstance(entries, str):
        entries = " ".join(entries)
    return re.findall(r"Bash\([^)]*\)", entries)


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_every_allowed_tools_rule_matches_a_command_the_skill_issues(skill: Path):
    """A rule is only a grant if it matches something. Measured against the commands
    pulled out of the skill itself, not a list kept alongside the test — a hand-kept list
    lets a mistyped rule pass as long as some *other* rule covers the listed command, so
    the typo survives as a permission that never fires. That is the same silent nothing
    this file exists to catch, wearing a permission's clothes.
    """
    rules = declared_rules(skill)
    if not rules:
        return
    commands = issued_commands(skill)
    for rule in rules:
        assert any(bash_rule_matches(rule, c) for c in commands), (
            f"{skill.parent.name}: {rule} matches no command this skill issues, so it "
            f"grants nothing. Fix the pattern or drop the rule."
        )


def runner_prefilter() -> tuple[str, re.Pattern[str]]:
    """The runner's coarse pre-filter, read out of the shipped script.

    Read rather than copied: a copy keeps matching after the script's stops, and the gate is then
    silently off with the suite still green. Two parts, both required to spawn the gate — the
    literal the `case` demands, and the subcommand word. POSIX classes are the only translation.
    """
    src = (REPO / "scripts/precommit-runner.sh").read_text(encoding="utf-8")
    literal = re.search(r"^  \*(?P<lit>[a-z]+)\*\) ;;$", src, re.M)
    assert literal, "the pre-filter's `case` is gone from precommit-runner.sh"
    m = re.search(r"^_word_re='(?P<re>.+)'$", src, re.M)
    assert m, "_word_re is gone from precommit-runner.sh — the pre-filter moved"
    pattern = m.group("re").replace("[:space:]", r"\s").replace("[:alnum:]", "0-9A-Za-z")
    return literal.group("lit"), re.compile(pattern)


def reaches_the_gate(command: str) -> bool:
    """Whether `command` gets the gate spawned on it at all."""
    literal, word_re = runner_prefilter()
    return literal in command and bool(word_re.search(command))


def reads_as_an_invocation(command: str, word: str) -> bool:
    """Whether the gate's own grammar — the single authority — calls `command` a `git <word>`."""
    return vp.is_invocation(command, word)


def assert_git_commands_reach_the_gate(label: str, commands: list[str]) -> None:
    """Every `git commit` / `git merge` in `commands` must be readable by the gate.

    The hook is handed `tool_input.command` *before* the shell expands it, and the grammar needs
    the token after `git` to start with `-`, so a variable supplying the flag itself — `git
    ${WT:+-C "$WT"} commit` — is not read as an invocation. The runner then exits 0 as "not a
    commit" and everything behind it is skipped in silence: the unclassified-commit block, the
    evidence markers, the module pre-check, the in-process wiki gate, and worktree
    re-designation, which parses a literal `-C <dir>` out of that same string. Invariant #6.
    """
    for cmd in commands:
        if not re.match(r"git(\s|$)", cmd):
            continue
        for word in ("commit", "merge"):
            if re.search(rf"(?<![\w-]){word}(?![\w-])", cmd) and not reads_as_an_invocation(
                cmd, word
            ):
                raise AssertionError(
                    f"{label}: {cmd!r} never reaches the gate — it reads the command "
                    f"unexpanded and does not see a {word}. Spell the flags literally."
                )


def test_the_prefilter_states_no_opinion_about_quoting():
    """The pre-filter decides only WHETHER to spawn the gate; the gate decides what the command
    is. A pre-filter that reasons about quotes is a second grammar, and a second grammar has to
    agree with the first. So it may not mention a quote or an escape at all: over-matching costs
    one spawn, under-matching costs the whole gate."""
    src = (REPO / "scripts/precommit-runner.sh").read_text(encoding="utf-8")
    raw = re.search(r"^_word_re='(?P<re>.+)'$", src, re.M)
    assert raw, "_word_re is gone from precommit-runner.sh"
    assert not set(raw.group("re")) & set("\"'\\"), (
        "the pre-filter grew a quoting grammar again — it must stay coarse enough that it "
        "cannot be narrower than the gate's own."
    )


# The corpus IS the spec, in both directions, and it is fed to both halves rather than the two
# being compared to each other — which only proves they drift together. A real invocation must be
# read as one AND reach the gate, and a command that merely says the word must be read as
# neither: a positive list alone is satisfied by a grammar that matches everything.
REAL_INVOCATIONS = [
    ("git commit -m x", "commit"),
    ("git -C '/c/My Work/wt' commit -F -", "commit"),
    ('git -C "/c/My Work/wt" commit -F -', "commit"),
    (r"git -C /home/o\'b/wt commit -m x", "commit"),
    (r"""git -C '/a/o'\''b' commit -F -""", "commit"),
    (r'git -c user.name="a\"b" commit -m x', "commit"),
    ("git -c user.name='a\"b' commit -m x", "commit"),
    ("/usr/bin/git -C /a/wt commit -m x", "commit"),
    ("C:/Git/bin/git commit --amend --no-edit", "commit"),
    (r"git -C /tmp/My\ P/wt commit -m x", "commit"),
    ("git -C /c/wt \\\n  commit -m x", "commit"),
    ("git merge --no-ff stage", "merge"),
    ("git -C '/c/My Work/wt' merge --squash feature/x", "merge"),
    ("/usr/bin/git merge --no-ff origin/dev", "merge"),
    ("git switch dev && git merge --squash feature/x", "merge"),
    # Quoted text something RUNS. A mask that calls these literal loses a real commit, which
    # the substring match they replaced still caught — the one direction that must not
    # regress.
    ('bash -c "git commit -m x"', "commit"),
    ("bash -c 'git merge --squash feature/x'", "merge"),
    ('eval "git commit -m x"', "commit"),
    ('out="$(git commit -m x)"', "commit"),
    ("out=$(git commit -m x)", "commit"),
    ("out=`git commit -m x`", "commit"),
    ("((n = 1 << 2))\ngit commit -m x", "commit"),
    # The program token as the host spells it, and as a shell still accepts it.
    ("git.exe commit -m x", "commit"),
    ("C:/Git/bin/git.exe -C /a/wt commit -m x", "commit"),
    ("'git' commit -m x", "commit"),
    # Text handed to a program that RUNS it. The channel is not always the argument of a `-c`:
    # a here-string, a heredoc, and a pipeline all deliver a script, and each spelling closed
    # by name has been followed by one that was not. What they share is that the command
    # starts an interpreter, and that is what is matched.
    ("printf 'git commit -m x' | bash", "commit"),
    ('echo "git commit -m x" | sh', "commit"),
    ('bash -c -- "git commit -m x"', "commit"),
    ("eval $'git commit -m x'", "commit"),
    ("bash <<< 'git commit -m x'", "commit"),
    ("bash -s <<< 'git commit -m x'", "commit"),
    ("""perl -e 'system("git commit -m x")'""", "commit"),
    ("bash <<'EOF'\ngit commit -m x\nEOF", "commit"),
    ("printf 'git merge --no-ff dev' | bash", "merge"),
    ("bash -c 'git \"commit\" -m x'", "commit"),
    ("bash <<< 'git merge --squash feature/x'", "merge"),
]
NON_INVOCATIONS = [
    'git -c user.email="a@b.c" log --oneline && echo "please commit"',
    'git -C "/c/wt" log --oneline -5 && echo "now commit"',
    'git --no-pager log --format="%s" && echo "then merge"',
    "git commit-graph write",
    "git merge-base HEAD dev",
    "git log -1 --format=%s <<'EOF'\ngit -C /wt commit -m x\nEOF",
    "cat <<" + "\\" + "EOF\ngit -C /wt merge --no-ff dev\nEOF",
    'grep -rn "git commit" scripts/',
    "echo '''nothing to merge'''",
    "git -c commit.gpgsign=false log --oneline",
    # The net widens only a command that starts an interpreter. These start none, so the word
    # stays data — a read-only `git log` denied as an unclassified commit is the gate blocking
    # work it was never meant to see.
    'echo "run bash and then git commit -m x"',
    "cat script.sh | less",
]


@pytest.mark.parametrize("command,word", REAL_INVOCATIONS, ids=[c for c, _ in REAL_INVOCATIONS])
def test_every_real_invocation_is_read_as_one_and_reaches_the_gate(command: str, word: str):
    """Both directions, on the same corpus: the grammar must call it an invocation, and the
    pre-filter must let it through to be judged. Either one failing is the gate off — a spelling
    the pre-filter drops never spawns the hook, and one the grammar drops leaves ROOT on the main
    repo while the runner believes it engaged."""
    assert reads_as_an_invocation(command, word), (
        f"{command!r} is in the corpus as a real {word} but the grammar no longer reads it as "
        f"one. The corpus is the spec — widen the grammar, not the corpus."
    )
    assert reaches_the_gate(command), (
        f"{command!r} is a real invocation the runner's pre-filter drops: the hook exits 0 and "
        f"every gate behind it is skipped in silence."
    )


@pytest.mark.parametrize("command", NON_INVOCATIONS)
def test_a_command_that_only_says_the_word_is_read_as_neither(command: str):
    """The pre-filter may claim these — it is allowed to over-match, and the spawn it costs is
    the price of never being narrower than the grammar. The grammar may not: a read-only `git
    log` read as a commit is denied as unclassified, the gate blocking work it was never meant
    to see."""
    for word in ("commit", "merge"):
        assert not reads_as_an_invocation(command, word), (command, word)


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_git_commands_a_skill_issues_reach_the_flow_gate(skill: Path):
    assert_git_commands_reach_the_gate(skill.parent.name, issued_commands(skill))


@pytest.mark.parametrize("rule", SHIPPED_RULES, ids=[p.stem for p in SHIPPED_RULES])
def test_git_commands_a_rule_issues_reach_the_flow_gate(rule: Path):
    """The same guard for `rules/`, which reaches the agent the way a skill does.

    The SessionStart hook injects these files into every session, so a `git merge` spelled out
    in one is a command the agent runs — `risk-tiers.md` is where the merge strategy the
    promotions follow is written down. A guard over `skills/` alone leaves that unmeasured.
    """
    assert_git_commands_reach_the_gate(rule.name, issued_commands(rule))


@pytest.mark.parametrize("name", sorted(MUST_STILL_PROMPT), ids=sorted(MUST_STILL_PROMPT))
def test_allowed_tools_never_grants_a_command_the_user_should_decide(name: str):
    """The commit prompt is the mechanical backstop behind the tier gate; an install
    writes into the host's environment; `rm -rf` deletes the evidence. Each stays a
    question."""
    entries = frontmatter(REPO / f"skills/{name}/SKILL.md").get("allowed-tools", "")
    rules = re.findall(r"Bash\([^)]*\)", entries if isinstance(entries, str) else " ".join(entries))
    for command in MUST_STILL_PROMPT[name]:
        offender = next((r for r in rules if bash_rule_matches(r, command)), None)
        assert offender is None, f"{name}: {offender} pre-approves {command!r}, which must be asked"


# Probes guarding against a *future* rule matching a command the skill never issues (the
# skill's own text carries no such command, so the staleness check below cannot apply).
# Everything not listed here is a command the skill text does carry, and the probe must
# track its wording.
DEFENSIVE_ONLY = {("doc-sync", "rm -rf .claude/harness-tier/.flow")}


@pytest.mark.parametrize("name", sorted(MUST_STILL_PROMPT), ids=sorted(MUST_STILL_PROMPT))
def test_must_still_prompt_literals_track_the_skill_text(name: str):
    """A stale literal guards nothing: if the skill rewords the command, the old string keeps
    matching no rule while a new rule matching the new wording ships unseen. Each probe's
    first two tokens must still appear in a command the skill issues (or its references —
    that is where an install the skill routes through the user is spelled out)."""
    issued = issued_commands(REPO / f"skills/{name}/SKILL.md")
    for command in MUST_STILL_PROMPT[name]:
        if (name, command) in DEFENSIVE_ONLY:
            continue
        head = " ".join(command.split()[:2])
        assert any(c.startswith(head) for c in issued), (
            f"{name}: no issued command starts with {head!r} — the probe {command!r} is "
            f"stale; update MUST_STILL_PROMPT to the skill's current wording"
        )


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_no_allowed_tools_rule_ends_in_a_path_glob(skill: Path):
    """`Bash(touch dir/*)`'s star crosses path separators including `..` — it grants the
    command against every path on disk while reading as a directory scope. A space before
    `*` (`k6 run *`) is the prefix-boundary form and stays legal; marker sets are finite,
    so path rules are enumerated exactly."""
    for rule in declared_rules(skill):
        # `/\*` anywhere, not only at the end: `…/.flow/*.done` is the same hole — the
        # fnmatch `*` crosses separators wherever it sits after a slash.
        assert not re.search(r"/\*", rule), (
            f"{skill.parent.name}: {rule} carries a path glob — enumerate exact paths"
        )
