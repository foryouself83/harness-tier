import re

import yaml as _yaml

from tests.flow_init._helpers import PLUGIN

# A `${{ }}` expression inside a `run:` block is substituted textually before the shell ever
# sees the script, so a value carrying shell metacharacters becomes code rather than data.
# `github.ref_name` is the live one: git only forbids whitespace and `~^:?*[\` in a ref, so
# `$(...)`, backticks and `;` are all legal branch names. Today every release template triggers
# on a fixed two-branch list, which is the only reason this is not already exploitable — the
# defence sits in the trigger, not in the code. Templates get edited (a tag push, a `release/**`
# glob) and the defence disappears with no diff to the step that consumes it. `env:` + `"$VAR"`
# moves the defence into the step itself, where the edit cannot reach it.
#
# An allow-list, deliberately, not a deny-list of the contexts known to be dangerous. `matrix.*`
# IS the command the host configured (unit-test renders flow-config `jobs[]` into it) and
# `steps.*` is, with one exception noted below, a literal the workflow itself echoed into
# `$GITHUB_OUTPUT`. Everything else fails here — including values that look inert, like
# `github.run_number`. Judging each context on whether it happens to be an integer today is
# precisely how five templates ended up split across two patterns while every individual file
# read as fine.
#
# The exception, recorded rather than special-cased: `steps.gitversion.outputs.semVer` in
# release.gitversion comes from a third-party action, not from this workflow's own echo, and
# GitVersion derives it from the branch name. It stays allowed because semver output is
# constrained to `[0-9A-Za-z.-]` and the step is an informational `continue-on-error` echo —
# but the blanket "steps.* is our own literal" claim is not true of it.
WORKFLOW_CONTEXTS = frozenset(
    {
        "github",
        "env",
        "vars",
        "job",
        "jobs",
        "steps",
        "runner",
        "secrets",
        "strategy",
        "matrix",
        "needs",
        "inputs",
    }
)
WORKFLOW_RUN_CONTEXTS_ALLOWED = frozenset({"matrix", "steps"})


def _disallowed_contexts(expr: str) -> set[str]:
    """Which contexts one `${{ }}` expression reaches for that must not touch a shell.

    Every reference in the expression, not the leading one. A prefix test answers "does this
    start with something allowed", which is a different question: `${{ steps.a.outputs.b ||
    github.event.head_commit.message }}` starts with `steps.` and carries a commit message.
    The `||` fallback is ordinary workflow idiom — this repo already writes
    `secrets.RELEASE_TOKEN || secrets.GITHUB_TOKEN` — so that shape arrives by normal editing
    rather than by anyone attacking the check.

    The rule is "an identifier with no dot in front of it", not "an identifier with a dot after
    it". Requiring the trailing dot missed every reference that is not a property dereference —
    `toJSON(github)`, `github['event']['message']` (index syntax is interchangeable with the dot
    form) and `GITHUB.actor` (the evaluator is case-insensitive). Leading-dot exclusion is also
    what keeps a *segment* from reading as a context, in both directions: `outputs` in
    `steps.x.outputs.y` is not the outputs context, and a step whose id is `env` is still a step.

    Known-list filtering means an unrecognised name passes, so a context GitHub adds later is
    fail-open here until this set is updated."""
    identifiers = {m.lower() for m in re.findall(r"(?<![.\w])([A-Za-z_][A-Za-z0-9_-]*)", expr)}
    return (identifiers & WORKFLOW_CONTEXTS) - WORKFLOW_RUN_CONTEXTS_ALLOWED


def _run_block_expressions(text: str) -> list[tuple[str, str]]:
    """Every `${{ }}` that lands inside a `run:` script, as (step label, expression).

    Takes the YAML text rather than a path so that generated workflows — which exist only as a
    Python string until a consumer renders them — go through the identical parse."""
    data = _yaml.safe_load(text)
    found = []
    for job_name, job in (data.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            # A step is a mapping; `uses:`-only steps carry no `run:` and are skipped by the
            # isinstance check below rather than by guessing at the schema.
            if not isinstance(step, dict) or not isinstance(step.get("run"), str):
                continue
            for expr in re.findall(r"\$\{\{(.*?)\}\}", step["run"], re.DOTALL):
                found.append((str(step.get("name", job_name)), expr.strip()))
    return found


def test_the_run_block_check_reads_every_context_in_an_expression_not_just_the_first():
    """Locks the hole a prefix test left: an allowed context in front, a forbidden one behind."""
    assert _disallowed_contexts("steps.a.outputs.b || github.event.head_commit.message") == {
        "github"
    }
    assert _disallowed_contexts("matrix.x && github.actor || ''") == {"github"}
    assert _disallowed_contexts("inputs.tag") == {"inputs"}
    # Allowed stays allowed, and `outputs` — a segment, not a context — is not mistaken for one.
    assert _disallowed_contexts("steps.sr.outputs.released") == set()
    assert _disallowed_contexts("matrix.setup") == set()


def test_the_run_block_check_reads_contexts_that_are_not_followed_by_a_dot():
    """A reference does not have to be `name.field`, and matching on the dot missed three shapes.

    `toJSON(github)` is the one that matters: dumping a whole context is the standard way people
    debug a workflow, so it arrives by ordinary editing rather than by anyone evading the check —
    and it inlines the entire `github` context, `event.head_commit.message` included, into the
    script. Index syntax is interchangeable with property dereference in GitHub expressions, and
    the expression evaluator is case-insensitive, so both of those are valid too."""
    assert _disallowed_contexts("toJSON(github)") == {"github"}
    assert _disallowed_contexts("fromJSON(inputs.config).name") == {"inputs"}
    assert _disallowed_contexts("github['event']['head_commit']['message']") == {"github"}
    assert _disallowed_contexts("GITHUB.actor") == {"github"}
    # The mirror of the same fix: only an identifier NOT preceded by a dot is a context, so a
    # step whose id happens to be `env` stays a step reference rather than reading as env.*.
    assert _disallowed_contexts("steps.env.outputs.x") == set()
    assert _disallowed_contexts("secrets.RELEASE_TOKEN || secrets.GITHUB_TOKEN") == {"secrets"}


def test_no_workflow_interpolates_a_context_value_into_a_run_block():
    """Covers the shipped templates and this repo's own workflows in one sweep.

    Both halves matter. The templates are what `/flow-init` renders into a consumer repo, so a
    bad pattern there is shipped; this repo's own `.github/workflows/` is where the good pattern
    was worked out first, and keeping both under one assertion is what stops the two from
    drifting apart again."""
    offenders = []
    for path in sorted(PLUGIN.glob("github/*.yml")) + sorted(
        PLUGIN.glob(".github/workflows/*.yml")
    ):
        for step, expr in _run_block_expressions(path.read_text(encoding="utf-8")):
            if _disallowed_contexts(expr):
                offenders.append(f"{path.name}: step {step!r} interpolates ${{{{ {expr} }}}}")
    assert not offenders, (
        "a run: block interpolates a context value directly into the shell — bind it to env: "
        'and read it as "$VAR" instead:\n  ' + "\n  ".join(offenders)
    )


def test_the_generated_deploy_orchestrator_keeps_contexts_out_of_its_run_block():
    """The sweep above globs files, and `deploy.yml` is not one — `_orchestrator_yaml` assembles
    it from Python string literals, so it stayed invisible to a check written in terms of paths
    while shipping to every consumer that runs `/harness-deployments`.

    It is also the worst place to leave the pattern. The release templates' `github.ref_name` is
    held safe by a fixed two-branch trigger; this workflow's `inputs.tag` is a `required: false,
    type: string` **workflow_dispatch** input, which GitHub does not constrain, and the jobs it
    feeds run with `secrets: inherit`. Nothing stands between that input and the shell."""
    from scripts.flow_init_setup import _orchestrator_yaml

    rendered = _orchestrator_yaml(
        [{"name": "pypi", "target": "pypi"}, {"name": "ghcr", "target": "ghcr"}], ["pypi", "ghcr"]
    )
    offenders = [
        f"step {step!r} interpolates ${{{{ {expr} }}}} ({', '.join(sorted(bad))})"
        for step, expr in _run_block_expressions(rendered)
        if (bad := _disallowed_contexts(expr))
    ]
    assert not offenders, (
        "the generated deploy.yml interpolates a context value into the shell:\n  "
        + "\n  ".join(offenders)
    )
