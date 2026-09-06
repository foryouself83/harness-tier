import re

import pytest
import yaml

import scripts.skill_sandbox as sandbox
from tests.evals._helpers import CASES, REPO, SKILLS

HAPPY_CASES = 5
NEGATIVE_CASES = 5


def frontmatter(name: str) -> dict:
    path = REPO / f"skills/{name}/SKILL.md"
    text = path.read_text(encoding="utf-8")
    block = re.match(r"^---\s*\n(.*?)\n---\s*\n", text, re.DOTALL)
    # A skill with no parseable frontmatter would otherwise surface as `NoneType has no
    # attribute 'group'` somewhere downstream, naming neither the skill nor the problem.
    assert block, f"{path} has no YAML frontmatter block"
    return yaml.safe_load(block.group(1))


def test_cases_cover_every_model_invoked_skill_and_nothing_else():
    """A skill with `disable-model-invocation` never puts its description in front of the
    model, so it cannot fail to be invoked — a case for it would report coverage that does
    not exist. The reverse gap is worse: a model-invoked skill with no cases is unmeasured
    while the suite is green."""
    invocable = {
        p.parent.name
        for p in REPO.glob("skills/*/SKILL.md")
        if not frontmatter(p.parent.name).get("disable-model-invocation")
    }
    assert set(SKILLS) == invocable, (
        f"cases.yaml covers {sorted(SKILLS)} but the model-invoked skills are {sorted(invocable)}"
    )


@pytest.mark.parametrize("name", SKILLS)
def test_each_skill_has_the_full_case_set(name: str):
    entry = CASES["skills"][name]
    assert len(entry["happy"]) == HAPPY_CASES, f"{name}: expected {HAPPY_CASES} happy cases"
    assert len(entry["negative"]) == NEGATIVE_CASES, (
        f"{name}: expected {NEGATIVE_CASES} negative cases"
    )


@pytest.mark.parametrize("name", SKILLS)
def test_case_fixtures_name_a_real_sandbox_scenario(name: str):
    """A typo'd fixture name would silently fall back to an empty directory and the run
    would still produce a number — a wrong one, indistinguishable from a real score."""
    entry = CASES["skills"][name]
    fixtures = {entry.get("fixture")}
    for case in entry["happy"] + entry["negative"]:
        if isinstance(case, dict):
            fixtures.add(case.get("fixture"))
    for f in fixtures - {None}:
        assert f in sandbox.BY_NAME, f"{name}: unknown fixture {f!r}"
