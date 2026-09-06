from pathlib import Path

import yaml

import scripts.flow_gate_check as fgc


# ── per-check timing (_parse_check / _default_timing) ─────────────────────────────
def test_parse_check_plain_string_is_every_commit():
    assert fgc._parse_check("lint", "ruff .") == ("ruff .", "every-commit", None)


def test_parse_check_security_string_defaults_promotion():
    # back-compat: the reserved 'security' key stays promotion even as a plain string.
    assert fgc._parse_check("security", "bandit -r .") == ("bandit -r .", "promotion", None)


def test_parse_check_dict_when_promotion():
    assert fgc._parse_check("sbom", {"run": "syft .", "when": "promotion"}) == (
        "syft .",
        "promotion",
        None,
    )


def test_parse_check_dict_when_every_commit():
    assert fgc._parse_check("license", {"run": "make lic", "when": "every-commit"}) == (
        "make lic",
        "every-commit",
        None,
    )


def test_parse_check_dict_without_when_uses_key_default():
    # dict form without `when` → key-name default (security→promotion, else every-commit).
    assert fgc._parse_check("license", {"run": "make lic"}) == ("make lic", "every-commit", None)
    assert fgc._parse_check("security", {"run": "bandit ."}) == ("bandit .", "promotion", None)


def test_parse_check_unknown_when_failsafe_every_commit_with_warning():
    cmd, timing, warn = fgc._parse_check("license", {"run": "make lic", "when": "promo"})
    assert cmd == "make lic"
    assert timing == "every-commit"  # fail-safe: run more often, not less
    assert warn is not None and "license" in warn and "promo" in warn


def test_parse_check_dict_without_run_is_none():
    cmd, _timing, _warn = fgc._parse_check("license", {"when": "promotion"})
    assert cmd is None


def test_parse_check_empty_string_is_none():
    assert fgc._parse_check("lint", "")[0] is None


# ── per-check timing routing in module_commands ──────────────────────────────────
_CUSTOMCFG = (
    "branches:\n  production: main\n"
    "modules:\n"
    "  - name: api\n    path: services/api/\n"
    "    checks:\n"
    "      lint: 'ruff check services/api'\n"
    "      license:\n        run: 'make license'\n        when: every-commit\n"
    "      sbom:\n        run: 'syft services/api'\n        when: promotion\n"
    "      security: 'bandit -r services/api'\n"
)


def _write_customcfg(tmp_path: Path) -> None:
    cfg = tmp_path / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-config.yaml").write_text(_CUSTOMCFG, encoding="utf-8")


def test_custom_every_commit_runs_on_changed_precommit(tmp_path: Path, monkeypatch):
    _write_customcfg(tmp_path)
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/x.py"])
    cmds, report = fgc.module_commands(tmp_path, "dev", ["precommit", "review", "doc-sync"])
    # every-commit: lint + license (custom). promotion (sbom, security) excluded on dev.
    assert cmds == ["ruff check services/api", "make license"]
    assert report == []


def test_custom_promotion_runs_all_modules_on_release(tmp_path: Path, monkeypatch):
    _write_customcfg(tmp_path)
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/x.py"])
    cmds, _ = fgc.module_commands(
        tmp_path, "release", ["precommit", "review", "security-scan", "security"]
    )
    # precommit(changed): lint, license. security-scan(all): sbom + security (both promotion).
    assert cmds == [
        "ruff check services/api",
        "make license",
        "syft services/api",
        "bandit -r services/api",
    ]


def test_multiple_promotion_checks_one_module(tmp_path: Path, monkeypatch):
    # the pre-generalization limit (single `security` slot) is gone: sbom + security both emit.
    _write_customcfg(tmp_path)
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/x.py"])
    cmds, _ = fgc.module_commands(tmp_path, "staging", ["security-scan"])
    assert cmds == ["syft services/api", "bandit -r services/api"]


def test_unknown_when_warned_once_and_command_emitted(tmp_path: Path, monkeypatch):
    cfg = tmp_path / ".claude" / "harness-tier" / "config"
    cfg.mkdir(parents=True)
    (cfg / "flow-config.yaml").write_text(
        "modules:\n  - name: api\n    path: services/api/\n"
        "    checks:\n      lint:\n        run: 'ruff .'\n        when: bogus\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(fgc, "_changed_files", lambda _r: ["services/api/x.py"])
    # release runs both passes → the module is seen twice, but the warning is de-duped to one line.
    cmds, report = fgc.module_commands(tmp_path, "release", ["precommit", "security-scan"])
    assert cmds == ["ruff ."]  # fail-safe every-commit
    warn_lines = [ln for ln in report if "bogus" in ln]
    assert len(warn_lines) == 1


def test_shipped_example_config_custom_check_routing():
    # the shipped example must stay valid YAML and demonstrate a custom check (with `when`,
    # not the YAML-boolean-trap `on`); guards the example against drift.

    root = Path(__file__).resolve().parent.parent.parent
    data = yaml.safe_load((root / "flow-config.example.yaml").read_text(encoding="utf-8"))
    api = next(m for m in data["modules"] if m["name"] == "api")
    cmd, timing, warn = fgc._parse_check("license", api["checks"]["license"])
    assert warn is None  # `when` is a valid timing (proves it was not parsed as boolean True)
    assert timing in fgc._TIMINGS
    assert cmd  # non-empty command
