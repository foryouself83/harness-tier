"""Guards for the plugin's own skills — the artefacts that *are* the product.

A `SKILL.md` edit changes what every consumer's agent does, yet until now nothing in
this suite read one. That gap is exactly how command-era frontmatter (`allowed-tools`
on 9 skills) and a hardcoded `./tests` search survived unnoticed: `uv run pytest`
stayed green the whole time because no test ever opened these files.

Two layers:

* **structural** — frontmatter parses and conforms to the official spec, links and
  section references resolve, no shipped command carries an un-runnable placeholder.
* **behavioural** — the case-discovery command is extracted *from the shipped skill*
  and run against real fixture projects. Testing the artefact rather than a copy is
  the point: a copy drifts, and drift is the bug class this file exists to catch.

Spec reference (verify against the docs, not model knowledge — see CLAUDE.md):
https://code.claude.com/docs/en/skills.md
"""

import re
import subprocess
from fnmatch import fnmatchcase
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
SKILLS = sorted(REPO.glob("skills/*/SKILL.md"))
SKILL_IDS = [p.parent.name for p in SKILLS]

# Every field the official SKILL.md frontmatter reference defines. Anything else is
# either a typo or a command-era leftover that silently does nothing.
SPEC_FIELDS = {
    "name",
    "description",
    "when_to_use",
    "argument-hint",
    "arguments",
    "disable-model-invocation",
    "user-invocable",
    "allowed-tools",
    "disallowed-tools",
    "model",
    "effort",
    "context",
    "agent",
    "hooks",
    "paths",
    "shell",
}

# Conservative budget for `description` + `when_to_use` in the skill listing. The official
# docs put the listing truncation at 1,536 chars; 1024 leaves headroom rather than tracking
# the platform constant exactly (a previous comment presented 1024 as the platform value —
# exactly the un-re-derived model knowledge the CLAUDE.md preamble warns about).
DESCRIPTION_CAP = 1024

# Korean is allowed only where it is *data* rather than prose: a verbatim quote of a
# script's real stdout, and the input tokens harness-insight parses. Translating either
# would desync the doc from the code or drop Korean input support.
KOREAN = re.compile(r"[가-힣]")
KOREAN_DATA_LITERAL_ALLOWLIST = {
    "skills/flow-init/SKILL.md": ["config 슬롯 점검"],
    "skills/harness-insight/SKILL.md": ["N일", "N주", "N개월", "오늘"],
}


def frontmatter(path: Path) -> dict:
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", path.read_text(encoding="utf-8"), re.DOTALL)
    assert m, f"{path.relative_to(REPO)}: no frontmatter block — the skill will not load"
    data = yaml.safe_load(m.group(1))
    assert isinstance(data, dict), f"{path.relative_to(REPO)}: frontmatter is not a mapping"
    return data


def body(path: Path) -> str:
    return re.sub(r"^---\s*\n.*?\n---\s*\n", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)


def bash_blocks(text: str) -> list[str]:
    return re.findall(r"```bash\n(.*?)```", text, re.DOTALL)


# --------------------------------------------------------------------------- structural


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_frontmatter_parses_and_only_uses_spec_fields(skill: Path):
    """A non-spec field is dead weight: Claude Code ignores it, so it reads as a
    working declaration while doing nothing. `allowed-tools`/`argument-hint` survived
    the command→skill migration exactly this way."""
    data = frontmatter(skill)
    unknown = set(data) - SPEC_FIELDS
    assert not unknown, f"{skill.parent.name}: fields absent from the official spec: {unknown}"


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_name_and_description_are_present_and_named_for_the_directory(skill: Path):
    data = frontmatter(skill)
    assert isinstance(data.get("description"), str) and data["description"].strip()
    assert data.get("name") == skill.parent.name, (
        f"name={data.get('name')!r} but the directory (and therefore the /command) "
        f"is {skill.parent.name!r}"
    )


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_description_fits_the_listing_cap(skill: Path):
    data = frontmatter(skill)
    combined = len(data["description"]) + len(str(data.get("when_to_use", "")))
    assert combined <= DESCRIPTION_CAP, f"{skill.parent.name}: {combined} chars > {DESCRIPTION_CAP}"


# A skill that outgrows this stops being read and starts being skimmed — including by the
# agent running it. 500 is the practical ceiling; the longest here is flow-init at 349.
SKILL_LINE_CAP = 500


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_skill_stays_short_enough_to_be_read(skill: Path):
    lines = len(skill.read_text(encoding="utf-8").splitlines())
    assert lines <= SKILL_LINE_CAP, (
        f"{skill.parent.name}: {lines} lines exceeds {SKILL_LINE_CAP}. Disclose reference "
        f"material into references/ and link it rather than growing SKILL.md"
    )


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_model_invocable_descriptions_state_when_to_use(skill: Path):
    """A model-invocable description is the only thing in context deciding whether the
    skill fires, so it must lead with triggering conditions. `disable-model-invocation`
    skills are exempt: their description never reaches the model, and serves the
    human reading the `/` menu."""
    data = frontmatter(skill)
    if data.get("disable-model-invocation") is True:
        return
    desc = data["description"]
    # "Use for requests like <quoted phrases>" is the same job done with literal user
    # wording; "MANDATORY ... invoke BEFORE" is the discipline form.
    assert re.search(r"\bUse (when|for)\b", desc) or desc.startswith("MANDATORY"), (
        f"{skill.parent.name}: description says what the skill does but not when to "
        f"use it — agents cannot decide to load it. Got: {desc[:80]!r}"
    )


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_argument_hint_is_only_on_skills_that_read_arguments(skill: Path):
    """`argument-hint` is "Hint shown during autocomplete to indicate expected
    arguments" — a skill that never reads `$ARGUMENTS` has no hint to show, and `(none)`
    puts the literal string "(none)" in the menu."""
    hint = frontmatter(skill).get("argument-hint")
    if hint is None:
        return
    assert hint != "(none)", f"{skill.parent.name}: drop argument-hint instead of '(none)'"
    assert "$ARGUMENTS" in body(skill), (
        f"{skill.parent.name}: argument-hint promises arguments the body never reads"
    )


# Tools that never prompt, so pre-approving them grants nothing. Read-only tools are
# auto-allowed (permissions.md: "Read-only | File reads, Grep | Approval required: No"),
# and the rest never reach a permission check.
NEVER_PROMPTS = {"Read", "Grep", "Glob", "Skill", "Agent", "Task", "SendMessage", "AskUserQuestion"}

# Bare tool names that grant the whole tool. `Bash` is `Bash(*)`: every command.
BLANKET = {"Bash", "Write", "Edit", "WebFetch", "WebSearch", "NotebookEdit"}


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_allowed_tools_entries_are_scoped_and_do_something(skill: Path):
    """`allowed-tools` reads like a restriction and is the opposite: "It does not restrict
    which tools are available: every tool remains callable." Two ways to get it wrong, and
    this repo shipped both at once for nine skills — `Bash, Read, Grep, Glob, Write, Edit,
    AskUserQuestion, Agent`:

    * an entry for a tool that never prompts grants nothing and only implies a limit;
    * a bare `Bash` grants every command, the opposite of the documented
      `Bash(git add *)` form, and the docs warn that "a skill can grant itself broad
      tool access".
    """
    entries = frontmatter(skill).get("allowed-tools")
    if entries is None:
        return
    if isinstance(entries, str):
        entries = re.findall(r"\w+\([^)]*\)|[\w-]+", entries)
    for e in entries:
        assert e not in NEVER_PROMPTS, (
            f"{skill.parent.name}: '{e}' never asks for permission, so pre-approving it "
            f"changes nothing — it only makes the list read like a restriction"
        )
        assert e not in BLANKET, (
            f"{skill.parent.name}: bare '{e}' grants the whole tool. Scope it, e.g. "
            f"Bash(git add *), or drop it"
        )


def bash_rule_matches(rule: str, command: str) -> bool:
    """Claude Code's Bash rule semantics, per permissions.md.

    Patterns are globs over the command string. A trailing ` *` (or the equivalent `:*`)
    "enforces a word boundary, requiring the prefix to be followed by a space **or
    end-of-string**" — so `Bash(ls *)` matches `ls -la` *and* the bare `ls`, but not
    `lsof`. Without the space, `Bash(ls*)` matches `lsof` too. No wildcard means an
    exact match.
    """
    pattern = rule[len("Bash(") : -1]
    if pattern.endswith(":*"):
        pattern = pattern[:-2] + " *"
    if pattern.endswith(" *"):
        prefix = pattern[:-2]
        # followed by a space (has arguments) or end-of-string (bare command)
        return command == prefix or fnmatchcase(command, prefix + " *")
    return fnmatchcase(command, pattern) or command == pattern


def test_the_skill_editing_rule_still_fires_on_skills():
    """`.claude/rules/skill-frontmatter.md` is path-scoped, which is the whole reason it
    costs nothing — and also how it dies silently. A glob that stops matching takes the
    rule out of context without failing anything, which is the same shape of quiet
    nothing this file exists to catch. Frontmatter is `paths`-only per authoring-spec.md.
    """
    rule = REPO / ".claude/rules/skill-frontmatter.md"
    assert rule.exists(), "the skill-editing rule is gone; CLAUDE.md still links it"
    m = re.match(r"^---\s*\n(.*?)\n---\s*\n", rule.read_text(encoding="utf-8"), re.DOTALL)
    assert m, "rule has no frontmatter, so it loads unconditionally into every session"
    data = yaml.safe_load(m.group(1))
    assert set(data) == {"paths"}, f"a rule takes only `paths`; got {sorted(data)}"
    targets = [p.relative_to(REPO).as_posix() for p in REPO.glob("skills/**/*.md")]
    for pattern in data["paths"]:
        assert any(fnmatchcase(t, pattern) for t in targets), (
            f"glob {pattern!r} matches no skill file — the rule would never load"
        )


def test_bash_rule_matcher_agrees_with_the_documented_examples():
    """This matcher is the yardstick the next test measures rules against, so it is only
    worth anything if it reproduces the examples in permissions.md verbatim."""
    for rule, command, expected in [
        ("Bash(ls *)", "ls -la", True),
        ("Bash(ls *)", "ls", True),  # word boundary is "space OR end-of-string" (permissions.md)
        ("Bash(ls *)", "lsof", False),
        ("Bash(ls:*)", "ls", True),  # :* is equivalent, so it too matches the bare command
        ("Bash(ls*)", "lsof", True),
        ("Bash(ls:*)", "ls -la", True),
        ("Bash(npm run build)", "npm run build", True),
        ("Bash(npm run build)", "npm run test", False),
        ("Bash(git add *)", "git add -A", True),
        ("Bash(* --version)", "python3 --version", True),
    ]:
        assert bash_rule_matches(rule, command) is expected, f"{rule} vs {command}"


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
# Everything not listed here is a command the skill text really carries, and the probe must
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
        # `/\*` anywhere, not just at the end: `…/.flow/*.done` is the same hole — the
        # fnmatch `*` crosses separators wherever it sits after a slash.
        assert not re.search(r"/\*", rule), (
            f"{skill.parent.name}: {rule} carries a path glob — enumerate exact paths"
        )


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_relative_links_resolve(skill: Path):
    for link in re.findall(r"\]\(([^)]+)\)", body(skill)):
        if link.startswith(("http://", "https://", "#")):
            continue
        target = (skill.parent / link.split("#")[0]).resolve()
        assert target.exists(), f"{skill.parent.name}: dead link → {link}"


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_intra_file_section_references_resolve(skill: Path):
    """`§3.1` pointing at a section that was renumbered away sends the agent nowhere.

    A `§` belonging to another file is that file's business, so a reference is only
    checked when neither its own line nor the one above names a `.md` — cross-file
    citations routinely wrap, putting the filename one line up from the `§`.
    """
    text = body(skill)
    headings = {h.rstrip(".") for h in re.findall(r"^#+\s+([\d.]+)", text, re.M)}
    if not headings:
        return
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if ".md" in line or (i and ".md" in lines[i - 1]):
            continue
        for ref in re.findall(r"§(\d+(?:\.\d+)?)", line):
            assert ref in headings, (
                f"{skill.parent.name}: §{ref} has no matching heading. Sections: {sorted(headings)}"
            )


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_cross_file_section_references_resolve(skill: Path):
    """`web-playwright.md (§10.7)` when that file stops at §6 sends the agent hunting.
    A citation is attributed to the single `.md` linked on its line or the one above —
    these wrap constantly, putting the filename a line up from the `§`."""
    lines = body(skill).splitlines()
    for i, line in enumerate(lines):
        window = (lines[i - 1] + "\n" + line) if i else line
        targets = {t for t in re.findall(r"\]\(([^)]+\.md)[^)]*\)", window)}
        refs = re.findall(r"§(\d+(?:\.\d+)?)", line)
        if len(targets) != 1 or not refs:
            continue
        target = (skill.parent / targets.pop()).resolve()
        if not target.exists():
            continue  # test_relative_links_resolve owns that failure
        headings = {
            h.rstrip(".")
            for h in re.findall(r"^#+\s+([\d.]+)", target.read_text(encoding="utf-8"), re.M)
        }
        for ref in refs:
            assert ref in headings, (
                f"{skill.parent.name}: cites {target.name} §{ref}, which has {sorted(headings)}"
            )


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_shipped_commands_have_no_unrunnable_placeholders(skill: Path):
    """A `<placeholder>` in command position is worse than a wrong default: run
    verbatim it fails into an empty result rather than an error, so the agent reads a
    silent zero as a real answer. Placeholders belong in assignments and paths that
    the surrounding prose tells the agent to fill."""
    for block in bash_blocks(body(skill)):
        for line in block.splitlines():
            stripped = line.strip()
            if stripped.startswith("#") or not stripped:
                continue
            m = re.match(r"(find|cat|ls|grep\s+-\w+)\s+[\"']?(<[^>]+>)", stripped)
            assert not m, f"{skill.parent.name}: command reads a placeholder literally → {stripped}"


@pytest.mark.parametrize("skill", SKILLS, ids=SKILL_IDS)
def test_korean_only_survives_as_data_literals(skill: Path):
    """The skills ship in English. The exceptions are data, not prose: translating them
    would desync a doc from real script output, or drop Korean input support."""
    rel = skill.relative_to(REPO).as_posix()
    allowed = KOREAN_DATA_LITERAL_ALLOWLIST.get(rel, [])
    for i, line in enumerate(skill.read_text(encoding="utf-8").splitlines(), 1):
        if not KOREAN.search(line):
            continue
        assert any(a in line for a in allowed), (
            f"{rel}:{i}: untranslated Korean prose → {line.strip()}"
        )


def test_references_are_english():
    """Reference files load into the same context as the skill that points at them."""
    for ref in sorted(REPO.glob("skills/*/references/**/*.md")):
        offenders = [
            line for line in ref.read_text(encoding="utf-8").splitlines() if KOREAN.search(line)
        ]
        assert not offenders, f"{ref.relative_to(REPO)}: Korean prose → {offenders[0].strip()}"


def copy_files() -> list[str]:
    setup = (REPO / "scripts/flow_init_setup.py").read_text(encoding="utf-8")
    block = setup[setup.index("COPY_FILES") : setup.index("]", setup.index("COPY_FILES"))]
    return re.findall(r'"scripts/([\w.\-]+)"', block)


def test_scaffold_treats_a_ts_playwright_config_as_a_typescript_signal():
    """`@playwright/test` ships its own TypeScript, so a TS Playwright project routinely
    has no `tsconfig.json` and no `typescript` dependency — keying the language only on
    those two writes a `.js` spec into a `.ts` suite. Surfaced by the `empty-web`
    sandbox scenario, whose fixture is exactly that shape."""
    step = re.search(
        r"^## Step 2 — Detect testDir and Language$(.*?)^---$",
        body(REPO / "skills/playwright-scaffold/SKILL.md"),
        re.M | re.DOTALL,
    )
    assert step, "playwright-scaffold: the language-detection step was renamed"
    assert "playwright.config.ts" in step.group(1), (
        "playwright-scaffold decides .ts vs .js without counting playwright.config.ts as "
        "a TypeScript signal, so a TS project with no tsconfig gets a .js spec"
    )


def test_flow_init_does_not_enumerate_the_copy_list():
    """`COPY_FILES` is the only list that is true by construction. flow-init once
    enumerated five scripts while COPY_FILES held nine — and told the agent to relay
    that stale list to the user. Naming a script elsewhere (what depends on it, where
    the host copy lives) is fine; re-listing what gets copied is what drifts."""
    doc = (REPO / "skills/flow-init/SKILL.md").read_text(encoding="utf-8")
    bullet = re.search(r"^- \*\*Copies\*\*.*?(?=^- \*\*)", doc, re.M | re.DOTALL)
    assert bullet, "flow-init/SKILL.md: the **Copies** bullet is gone — did the report change?"
    listed = [name for name in copy_files() if name in bullet.group(0)]
    assert not listed, (
        f"the Copies bullet enumerates {listed}; that list drifts the moment a script is "
        f"added to COPY_FILES. Relay the script's own printed report instead."
    )


def test_flow_init_setup_actually_reports_what_it_copied():
    """flow-init tells the agent to relay the script's report. That instruction is only
    real if the script prints one — otherwise the agent has nothing to relay and the
    delegation is a no-op dressed as a fix."""
    setup = (REPO / "scripts/flow_init_setup.py").read_text(encoding="utf-8")
    copy_fn = setup[setup.index("COPY_FILES") :]
    assert "report.append" in copy_fn and "Path(rel).name" in copy_fn, (
        "flow_init_setup.py no longer reports each copied file by name; flow-init's "
        "'relay the script's report' instruction now has nothing to relay."
    )


# -------------------------------------------------------------------------- behavioural
#
# The case-discovery command decides "does this project already have tests?". A wrong
# answer scaffolds a starter smoke over a suite that already exists. These tests run
# the command the skills actually ship.

CASE_DISCOVERY_FILES = [
    "skills/integration/SKILL.md",
    "skills/integration/references/web-playwright.md",
    "skills/playwright-scaffold/SKILL.md",
]


def case_discovery_command(rel: str) -> str:
    """Pull the shipped `testDir` resolution + guarded `find` out of a skill.

    All three lines must be identical everywhere: they decide which directory is
    searched, what counts as a case, and — via the `[ -d ]` guard — whether an empty
    result means "no cases" or "that directory is not there".
    """
    text = (REPO / rel).read_text(encoding="utf-8")
    resolve = re.search(r"^TESTDIR=\$\(grep .*$", text, re.M)
    default = re.search(r'^TESTDIR="\$\{TESTDIR:-.*$', text, re.M)
    search = re.search(r'^if \[ -d "\$TESTDIR" \]; then find .*fi$', text, re.M)
    assert resolve and default and search, f"{rel}: no guarded testDir discovery command found"
    # Strip only a trailing consumer. Splitting on "|" would cut the `(spec|test)`
    # alternation inside the regex and hand bash a syntax error.
    core = re.sub(r"\s*\|\s*(wc -l|head -\d+)\s*$", "", search.group(0))
    return "\n".join([resolve.group(0), default.group(0), core.strip()])


def make_project(root: Path, test_dir: str | None, cases: list[str] | None) -> None:
    """`cases=None` means the test directory itself is absent — the state the `[ -d ]`
    guard exists to tell apart from an empty one."""
    config = (
        f'export default {{ testDir: "{test_dir}" }};\n' if test_dir else "export default {};\n"
    )
    (root / "playwright.config.ts").write_text(config, encoding="utf-8", newline="")
    if cases is None:
        return
    target = root / (test_dir or "tests")
    target.mkdir(parents=True, exist_ok=True)
    for name in cases:
        (target / name).write_text("// case\n", encoding="utf-8", newline="")


def run_discovery(rel: str, cwd: Path) -> list[str]:
    """Run the skill's own command in a throwaway project and return the cases it found.

    Two Windows hazards, both of which corrupt the script before bash ever sees it and
    would otherwise be misread as a bug in the skill:

    * the script goes in on stdin (`bash -s`), not as a `-c` argument — CreateProcess
      escapes the embedded double quotes and Git Bash reads them back as literal
      backslashes;
    * it goes in as **bytes** — `text=True` wraps stdin in a TextIOWrapper whose default
      newline translation rewrites every ``\\n`` to ``\\r\\n``, and bash then treats the
      stray ``\\r`` as part of the command.
    """
    proc = subprocess.run(
        ["bash", "-s"],
        input=case_discovery_command(rel).encode("utf-8"),
        cwd=cwd,
        capture_output=True,
        check=False,
    )
    stderr = proc.stderr.decode("utf-8", "replace")
    assert proc.returncode == 0, f"{rel}: command failed (rc={proc.returncode}) → {stderr}"
    return [ln for ln in proc.stdout.decode("utf-8", "replace").splitlines() if ln.strip()]


def test_all_three_files_agree_on_the_discovery_command():
    """integration, its reference, and playwright-scaffold each decide what counts as
    an existing case. Disagreement means one of them scaffolds over a real suite."""
    commands = {rel: case_discovery_command(rel) for rel in CASE_DISCOVERY_FILES}
    assert len(set(commands.values())) == 1, f"discovery commands diverge: {commands}"


@pytest.mark.parametrize("rel", CASE_DISCOVERY_FILES, ids=lambda r: Path(r).parent.name)
def test_discovery_finds_cases_under_a_custom_testdir(rel: str, tmp_path: Path):
    """The regression this file was written for: a hardcoded `./tests` reported zero
    cases for a `testDir: './e2e'` project, so the agent scaffolded over the suite."""
    make_project(tmp_path, "./e2e", ["checkout.spec.ts", "auth.test.tsx"])
    assert len(run_discovery(rel, tmp_path)) == 2


@pytest.mark.parametrize("rel", CASE_DISCOVERY_FILES, ids=lambda r: Path(r).parent.name)
def test_discovery_falls_back_to_the_playwright_default(rel: str, tmp_path: Path):
    make_project(tmp_path, None, ["smoke.spec.js"])
    assert len(run_discovery(rel, tmp_path)) == 1


@pytest.mark.parametrize("rel", CASE_DISCOVERY_FILES, ids=lambda r: Path(r).parent.name)
def test_discovery_ignores_files_that_are_not_playwright_cases(rel: str, tmp_path: Path):
    """`testMatch` defaults to `**/*.@(spec|test).?(c|m)[jt]s?(x)` — a broader glob
    would count `notes.spec.md` and report a suite that does not exist."""
    make_project(tmp_path, "./e2e", ["notes.spec.md", "readme.test.txt"])
    assert run_discovery(rel, tmp_path) == []


def test_integration_does_not_read_an_empty_result_as_an_empty_directory():
    """An empty result means "no Playwright cases", never "this directory is empty" — a
    `tests/` full of pytest or vitest files produces exactly the same silence. The two
    diverge in any repo that keeps unit tests under the same roof (this one included:
    running the command here against `./tests` returns nothing beside 13 Python files).
    The scaffold action stays right either way; the *stated reason* is what misleads."""
    text = body(REPO / "skills/integration/SKILL.md")
    row = re.search(r"^\| nothing \| (.+?) \|", text, re.M)
    assert row, "integration: the discovery outcome table lost its empty-result row"
    meaning = row.group(1)
    assert "no Playwright cases" in meaning, (
        f"the empty-result row explains itself as {meaning!r}; it must say the directory "
        f"holds no Playwright cases, not that the directory is empty"
    )


@pytest.mark.parametrize("rel", CASE_DISCOVERY_FILES, ids=lambda r: Path(r).parent.name)
def test_discovery_reports_empty_for_a_genuinely_empty_project(rel: str, tmp_path: Path):
    """Zero must stay reachable — it is what legitimately triggers the starter smoke."""
    make_project(tmp_path, "./e2e", [])
    assert run_discovery(rel, tmp_path) == []


def test_discovery_sees_a_previous_runs_smoke_as_an_existing_case(tmp_path: Path):
    """playwright-scaffold is idempotent only if its own output counts as a case."""
    make_project(tmp_path, "./e2e", ["main.smoke.spec.ts"])
    assert len(run_discovery("skills/playwright-scaffold/SKILL.md", tmp_path)) == 1


@pytest.mark.parametrize("rel", CASE_DISCOVERY_FILES, ids=lambda r: Path(r).parent.name)
def test_discovery_distinguishes_a_missing_testdir_from_an_empty_one(rel: str, tmp_path: Path):
    """`find … 2>/dev/null` renders "that directory does not exist" as an empty result —
    identical to "the directory is there and holds no cases". The empty result is what
    authorises scaffolding, so a config pointing at a directory that is not there used to
    read as a licence to scaffold. The `[ -d ]` guard makes the two states nameable.

    A control agent on the pre-fix skill diagnosed this unprompted: "이 `0`은 케이스가
    없다는 뜻이 아닙니다 … `2>/dev/null`이 이를 '케이스 0건'으로 위장시켰습니다."
    """
    make_project(tmp_path, "./e2e", None)  # config says ./e2e; the directory is absent
    assert run_discovery(rel, tmp_path) == ["MISSING: ./e2e"]


@pytest.mark.parametrize("rel", CASE_DISCOVERY_FILES, ids=lambda r: Path(r).parent.name)
def test_discovery_names_the_default_when_a_fresh_project_has_no_test_dir(rel: str, tmp_path: Path):
    """No `testDir` in the config and no `./tests`: a project that never had tests. The
    output still names which directory was looked for, so the agent can tell this apart
    from a config that points somewhere wrong."""
    make_project(tmp_path, None, None)
    assert run_discovery(rel, tmp_path) == ["MISSING: ./tests"]
