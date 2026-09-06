import re
from pathlib import Path

import yaml as _yaml

from scripts.flow_init_setup import (
    copy_artifacts,
    load_unit_test_config,
    render_unit_test_workflow,
    run_setup,
)
from tests.flow_init._helpers import PLUGIN

# ── unit_test workflow rendering ────────────────────────────────────────────────


def _write_unit_test_config(host: Path, unit_test: dict) -> None:
    cfg_dir = host / ".claude" / "harness-tier" / "config"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    (cfg_dir / "flow-config.yaml").write_text(
        _yaml.safe_dump({"unit_test": unit_test}, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )


_UNIT_TEST_SAMPLE = {
    "enable": True,
    "branches": ["dev", "stage", "main"],
    "timeout_minutes": 25,
    "jobs": [
        {
            "name": "api",
            "language": "python",
            "version": "3.12",
            "setup": "pip install uv && uv sync",
            "test": "uv run pytest",
        },
        {
            "name": "web",
            "language": "node",
            "version": "20",
            "setup": "npm ci",
            "test": "npm test",
        },
    ],
}


def test_render_unit_test_creates_and_substitutes(tmp_path: Path):
    _write_unit_test_config(tmp_path, _UNIT_TEST_SAMPLE)
    out = render_unit_test_workflow(tmp_path, PLUGIN)
    assert any("생성" in line for line in out)
    dest = tmp_path / ".github" / "workflows" / "unit-test.yml"
    text = dest.read_text(encoding="utf-8")
    # all tokens substituted
    assert "__HARNESS_" not in text
    # config-driven timeout applied to the job
    assert "timeout-minutes: 25" in text
    # branch substitution
    assert "branches: [dev, stage, main]" in text
    # the whole rendered document is valid YAML, and the variable-length jobs[] became a valid
    # matrix.include list of mappings (this is the "matrix include valid YAML" guard).
    data = _yaml.safe_load(text)
    include = data["jobs"]["unit-test"]["strategy"]["matrix"]["include"]
    assert [j["name"] for j in include] == ["api", "web"]
    assert data["jobs"]["unit-test"]["timeout-minutes"] == 25
    # every declared field survives the flow-style round-trip
    api = include[0]
    assert api["language"] == "python" and api["version"] == "3.12"
    assert api["setup"] == "pip install uv && uv sync" and api["test"] == "uv run pytest"


def test_supported_setup_languages_matches_the_template_gates():
    # One fact in three places: the template's `if: matrix.language == '<lang>'` steps, the
    # constant that copies them, and the list flow-config.example advertises to hosts. A copy
    # drifts silently — adding a setup-* step without the constant makes that language warn as a
    # typo, dropping one lets the real typo through, and a stale example teaches the wrong value.
    # Read all three back out of their files so none can diverge unnoticed.
    from scripts.flow_init_setup import (
        EXAMPLE_CONFIG,
        SUPPORTED_SETUP_LANGUAGES,
        UNIT_TEST_TEMPLATE,
    )

    template = (PLUGIN / UNIT_TEST_TEMPLATE).read_text(encoding="utf-8")
    gates = set(re.findall(r"matrix\.language == '([^']+)'", template))
    assert gates == set(SUPPORTED_SETUP_LANGUAGES)

    # Split on the bare pipe and strip, so respacing the list is a formatting edit rather than a
    # failure that reads like a real divergence. Both asserts carry a message for the same reason.
    example = (PLUGIN / EXAMPLE_CONFIG).read_text(encoding="utf-8")
    documented = re.search(r"#\s+language:\s+([a-z |]+?)\s+→", example)
    assert documented, "flow-config.example's `language:` slot line moved or was rewrapped"
    listed = {word.strip() for word in documented.group(1).split("|")}
    assert listed == set(SUPPORTED_SETUP_LANGUAGES), f"example documents {sorted(listed)}"


def test_unit_test_language_warnings_flags_case_variant_only():
    # only a case variant of a supported language (near-certain typo) warns; an exact match and a
    # genuinely custom language (the escape hatch flow-config.example documents) do not, and a job
    # without `language` is ignored.
    from scripts.flow_init_setup import _unit_test_language_warnings

    warnings = _unit_test_language_warnings(
        [
            {"name": "api", "language": "Python"},  # case variant → warn
            {"name": "web", "language": "node"},  # exact supported → no warn
            {"name": "edge", "language": "deno"},  # custom runtime → escape hatch, no warn
            {"name": "nolang"},  # no language key → no warn
        ]
    )
    assert len(warnings) == 1
    assert "'api'" in warnings[0] and "'Python'" in warnings[0]


def test_render_unit_test_surfaces_language_warning(tmp_path: Path):
    # the case-variant warning must reach the render log, and rendering still succeeds (non-fatal).
    _write_unit_test_config(
        tmp_path,
        {"enable": True, "jobs": [{"name": "api", "language": "GO", "test": "go test ./..."}]},
    )
    out = render_unit_test_workflow(tmp_path, PLUGIN)
    assert any("'GO'" in line and "매칭" in line for line in out)
    assert any("생성" in line for line in out)


def test_render_unit_test_default_timeout(tmp_path: Path):
    # timeout_minutes omitted → falls back to UNIT_TEST_DEFAULT_TIMEOUT (10). Locks the default so
    # a drift between the constant and the docs that quote it is caught.
    from scripts.flow_init_setup import UNIT_TEST_DEFAULT_TIMEOUT

    _write_unit_test_config(
        tmp_path,
        {"enable": True, "jobs": [{"name": "api", "language": "python", "test": "pytest"}]},
    )
    render_unit_test_workflow(tmp_path, PLUGIN)
    text = (tmp_path / ".github" / "workflows" / "unit-test.yml").read_text(encoding="utf-8")
    assert f"timeout-minutes: {UNIT_TEST_DEFAULT_TIMEOUT}" in text
    assert UNIT_TEST_DEFAULT_TIMEOUT == 10


def test_render_unit_test_null_timeout_falls_back(tmp_path: Path):
    # timeout_minutes present but blank (null) must fall back to the default, NOT render
    # `timeout-minutes: None` (yaml.safe_load accepts the string so a naive check misses it,
    # but GitHub Actions rejects a non-integer cap → CLAUDE.md "every job caps timeout" broken).
    from scripts.flow_init_setup import UNIT_TEST_DEFAULT_TIMEOUT

    _write_unit_test_config(
        tmp_path,
        {"enable": True, "timeout_minutes": None, "jobs": [{"name": "api", "test": "pytest"}]},
    )
    render_unit_test_workflow(tmp_path, PLUGIN)
    text = (tmp_path / ".github" / "workflows" / "unit-test.yml").read_text(encoding="utf-8")
    assert "timeout-minutes: None" not in text
    assert f"timeout-minutes: {UNIT_TEST_DEFAULT_TIMEOUT}" in text


def test_render_unit_test_disabled(tmp_path: Path):
    _write_unit_test_config(tmp_path, {"enable": False, "jobs": [{"name": "x", "test": "t"}]})
    out = render_unit_test_workflow(tmp_path, PLUGIN)
    assert any("enable=false" in line for line in out)
    cfg = {"enable": False, "jobs": [{"name": "x", "test": "t"}]}
    assert load_unit_test_config(tmp_path) == cfg
    assert not (tmp_path / ".github" / "workflows" / "unit-test.yml").exists()


def test_render_unit_test_absent_section(tmp_path: Path):
    # flow-config absent → unconfigured → skip (FAIL-OPEN, non-destructive)
    out = render_unit_test_workflow(tmp_path, PLUGIN)
    assert any("미설정" in line for line in out)
    assert load_unit_test_config(tmp_path) is None
    assert not (tmp_path / ".github" / "workflows" / "unit-test.yml").exists()


def test_render_unit_test_empty_jobs_skips(tmp_path: Path):
    # enabled but no jobs → nothing to render → skip (do not emit an empty matrix)
    _write_unit_test_config(tmp_path, {"enable": True, "jobs": []})
    out = render_unit_test_workflow(tmp_path, PLUGIN)
    assert any("jobs" in line for line in out)
    assert not (tmp_path / ".github" / "workflows" / "unit-test.yml").exists()


def test_render_unit_test_idempotent_reports_only(tmp_path: Path):
    _write_unit_test_config(tmp_path, _UNIT_TEST_SAMPLE)
    render_unit_test_workflow(tmp_path, PLUGIN)  # first render (create)
    dest = tmp_path / ".github" / "workflows" / "unit-test.yml"
    sentinel = dest.read_text(encoding="utf-8") + "\n# user edit\n"
    dest.write_text(sentinel, encoding="utf-8")  # simulate a user edit
    out = render_unit_test_workflow(tmp_path, PLUGIN)  # second render — report only
    assert any("이미 있어" in line for line in out)
    assert dest.read_text(encoding="utf-8") == sentinel  # not overwritten


def test_run_setup_renders_unit_test(tmp_path: Path, capsys):
    _write_unit_test_config(tmp_path, _UNIT_TEST_SAMPLE)
    run_setup(tmp_path, PLUGIN)
    captured = capsys.readouterr().out
    assert "유닛 테스트" in captured
    assert (tmp_path / ".github" / "workflows" / "unit-test.yml").is_file()


def test_all_github_workflow_templates_have_timeout():
    # every rendered/copied workflow template must cap wall-clock via timeout-minutes (a hung
    # runner otherwise burns the full 6h default). Guards against a new template omitting it.
    templates = sorted(PLUGIN.glob("github/*.workflow.example.yml"))
    assert templates, "no workflow templates found"
    missing = [t.name for t in templates if "timeout-minutes" not in t.read_text(encoding="utf-8")]
    assert not missing, f"templates missing timeout-minutes: {missing}"


def test_release_workflows_do_not_pin_the_checkout_ref():
    # Covers the shipped templates and this repo's own release workflow in one sweep, for the
    # reason the run-block sweep above gives: keeping both halves under one assertion is what
    # stops them drifting apart. A release triggers on push, where actions/checkout already
    # attaches HEAD to the triggering branch (`git checkout --force -B <branch>
    # refs/remotes/origin/<branch>`, the remote ref fetched at the event's sha). Pinning `ref:`
    # re-resolves the branch *tip*, so a commit that landed after the trigger is released without
    # having been tested. Deploy templates are excluded on purpose: they are workflow_call'd with
    # an explicit tag, and a tag cannot move under them.
    offenders = []
    for t in sorted(PLUGIN.glob("github/release.*.workflow.example.yml")) + [
        PLUGIN / ".github" / "workflows" / "release.yml"
    ]:
        data = _yaml.safe_load(t.read_text(encoding="utf-8")) or {}
        for job in (data.get("jobs") or {}).values():
            for step in (job or {}).get("steps") or []:
                if str(step.get("uses", "")).startswith("actions/checkout"):
                    ref = (step.get("with") or {}).get("ref")
                    if ref is not None:
                        offenders.append(f"{t.name}: ref: {ref}")
    assert not offenders, f"a push-triggered release checkout must not pin ref: {offenders}"


def test_all_github_workflow_templates_are_valid_yaml():
    # the SOURCE templates are YAML files tracked in this repo, so check-yaml (pre-commit) parses
    # them. A __HARNESS_*__ token placed at a spot that breaks the *pre-render* parse (e.g. a bare
    # scalar at column 0) would fail CI even though the rendered output is fine. Every token must
    # sit at a valid scalar / list-item position so the template parses before substitution.
    for t in sorted(PLUGIN.glob("github/*.workflow.example.yml")):
        _yaml.safe_load(t.read_text(encoding="utf-8"))  # raises on malformed YAML


def test_merge_strategy_policy_reaches_host(tmp_path: Path):
    """copy_artifacts must carry the merge_strategy policy into the host config dir."""
    import yaml

    plugin = Path(__file__).resolve().parent.parents[1]
    host = tmp_path / "host"
    host.mkdir()
    copy_artifacts(plugin, host)
    dest = host / ".claude" / "harness-tier" / "config" / "flow-tiers.yaml"
    data = yaml.safe_load(dest.read_text(encoding="utf-8"))
    assert isinstance(data.get("merge_strategy"), list)
    assert any(r.get("require") == "--squash" for r in data["merge_strategy"])
