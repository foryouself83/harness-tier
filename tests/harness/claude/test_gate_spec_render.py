"""The Claude entry rendered from the gate IR is the entry every existing host already carries."""

import scripts.flow_init_setup as fis
from scripts.harness.claude import install
from scripts.harness.gate_spec import GATE

EXISTING_ENTRY = {
    "matcher": "Bash",
    "hooks": [
        {
            "type": "command",
            "shell": "bash",
            "command": 'bash "${CLAUDE_PROJECT_DIR:-.}/.claude/harness-tier/scripts/precommit-runner.sh"',  # noqa: E501
            "timeout": 600,
            "statusMessage": "harness-tier: flow 게이트 + 테스트 검사 중…",
        }
    ],
}


def test_rendered_claude_entry_is_byte_identical_to_the_shipped_one():
    assert install.GATE_ENTRY == EXISTING_ENTRY


def test_flow_init_setup_reexports_the_same_objects():
    assert fis.GATE_ENTRY is install.GATE_ENTRY
    assert fis.register_gate is install.register
    assert fis._is_gate_hook is install.is_gate_hook


def test_ir_holds_the_values_both_harnesses_render_from():
    assert GATE.runner_rel == ".claude/harness-tier/scripts/precommit-runner.sh"
    assert GATE.timeout == 600
