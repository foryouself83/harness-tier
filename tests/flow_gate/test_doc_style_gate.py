import json
from pathlib import Path

import scripts.flow_gate_check as fgc
from scripts._harness_paths import RUNTIME_GATES
from scripts.flow_gate_check import missing_gates, module_commands
from tests.flow_gate._helpers import (
    _classify_worktree_module,
    _doc_style_host,
    _init_repo,
    _rg,
    _run_runner,
    requires_bash_git,
)


def test_doc_style_is_a_runtime_gate_needing_no_marker(tmp_path: Path):
    assert "doc-style" in RUNTIME_GATES
    flow = tmp_path / ".flow"
    flow.mkdir()
    assert "doc-style" not in missing_gates(flow, ["doc-style", "doc-sync"])


def test_doc_style_gate_reports_a_violation_in_a_changed_file(tmp_path: Path):
    root = _doc_style_host(tmp_path, "The runner used to spawn twice.\n")
    report = fgc.doc_style_gate(root, ["precommit", "doc-style"])
    assert report and "HIST" in report and "doc.md" in report


def test_doc_style_gate_is_silent_on_clean_prose(tmp_path: Path):
    root = _doc_style_host(tmp_path, "The gate blocks an unclassified commit.\n")
    assert fgc.doc_style_gate(root, ["doc-style"]) is None


def test_doc_style_gate_is_silent_when_the_config_is_off(tmp_path: Path):
    root = _doc_style_host(tmp_path, "The runner used to spawn twice.\n")
    (root / ".claude" / "harness-tier" / "config" / "flow-config.yaml").write_text(
        "doc_style:\n  enable: false\n", encoding="utf-8"
    )
    assert fgc.doc_style_gate(root, ["doc-style"]) is None


def test_doc_style_gate_is_silent_when_the_gate_is_not_listed(tmp_path: Path):
    # flow-tiers.yaml gates is the on/off switch, same as every other runtime gate.
    root = _doc_style_host(tmp_path, "The runner used to spawn twice.\n")
    assert fgc.doc_style_gate(root, ["precommit"]) is None
    assert fgc.doc_style_gate(root, None) is None


def test_doc_style_gate_internal_failure_is_fail_open(tmp_path: Path, monkeypatch):
    root = _doc_style_host(tmp_path, "The runner used to spawn twice.\n")
    monkeypatch.setattr(fgc, "lint_paths", lambda paths: 1 / 0)
    assert fgc.doc_style_gate(root, ["doc-style"]) is None


def test_doc_style_gate_opens_without_its_sibling(tmp_path: Path, monkeypatch):
    # A half-copied host can hold flow_gate_check.py without doc_style_check.py.
    root = _doc_style_host(tmp_path, "The runner used to spawn twice.\n")
    monkeypatch.setattr(fgc, "lint_paths", None)
    assert fgc.doc_style_gate(root, ["doc-style"]) is None


def test_doc_style_gate_is_not_a_module_command(tmp_path: Path):
    # Same contract as the wiki gate: down the module channel any nonzero exit reads as
    # "the check failed", which a warn-only gate can never honour. The config carries a
    # module WITH checks, so the empty answer is the routing's and not the early return
    # module_commands takes when there are no modules at all.
    root = _doc_style_host(
        tmp_path,
        "The runner used to spawn twice.\n",
        config=(
            "doc_style:\n  enable: true\n"
            "modules:\n  - name: api\n    path: services/api/\n"
            '    checks:\n      security: "echo SCAN"\n'
        ),
    )
    with_bucket, _ = module_commands(root, "staging", ["security-scan"])
    assert with_bucket, "the fixture must reach the routing, not the early return"
    assert module_commands(root, "staging", ["security-scan", "doc-style"])[0] == with_bucket
    assert module_commands(root, "staging", ["doc-style"]) == ([], [])
    assert module_commands(root, "docs", ["doc-sync", "doc-style"]) == ([], [])


@requires_bash_git
def test_doc_style_never_blocks_a_commit(tmp_path: Path):
    # The verdict belongs to doc-style.yml, which sees the whole tree. Here it only warns.
    main = tmp_path / "main"
    _init_repo(main)
    wt = tmp_path / "wt"
    _rg(["worktree", "add", "-b", "feature/x", str(wt)], main)
    _classify_worktree_module(wt)
    (wt / ".claude" / "harness-tier" / "config" / "flow-config.yaml").write_text(
        "doc_style:\n  enable: true\n", encoding="utf-8"
    )
    (wt / "doc.md").write_text("The runner used to spawn twice.\n", encoding="utf-8")
    _rg(["add", "doc.md"], wt)
    r = _run_runner(main, f"git -C {wt} commit -m x", dryrun=False)
    assert r.returncode == 0, f"stdout={r.stdout!r} stderr={r.stderr!r}"
    assert "HIST" in json.loads(r.stdout.strip())["systemMessage"]


def test_runtime_notices_carry_every_gate_in_one_payload(tmp_path: Path, monkeypatch, capsys):
    # precommit-runner.sh echoes this stdout verbatim; a second JSON object would not parse.
    monkeypatch.setattr(fgc, "_wiki_stage", lambda root, gates: "wiki note")
    monkeypatch.setattr(fgc, "doc_style_gate", lambda root, gates: "prose note")
    fgc._runtime_notices(tmp_path, ["wiki", "doc-style"])
    payload = json.loads(capsys.readouterr().out.strip())
    assert "wiki note" in payload["systemMessage"]
    assert "prose note" in payload["systemMessage"]


def test_runtime_notices_stay_quiet_when_every_gate_is_clean(tmp_path: Path, monkeypatch, capsys):
    monkeypatch.setattr(fgc, "_wiki_stage", lambda root, gates: None)
    monkeypatch.setattr(fgc, "doc_style_gate", lambda root, gates: None)
    fgc._runtime_notices(tmp_path, ["wiki", "doc-style"])
    assert capsys.readouterr().out == ""
