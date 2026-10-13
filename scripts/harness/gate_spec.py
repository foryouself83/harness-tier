"""The commit gate, said once. Each harness package renders its own hook entry from this."""

from __future__ import annotations

from dataclasses import dataclass

try:
    from _harness_paths import SCRIPTS_DIR
except ImportError:
    from scripts._harness_paths import SCRIPTS_DIR


@dataclass(frozen=True)
class GateSpec:
    runner_rel: str
    timeout: int
    status: str


GATE = GateSpec(
    runner_rel=f"{SCRIPTS_DIR}/precommit-runner.sh",
    timeout=600,
    status="harness-tier: flow 게이트 + 테스트 검사 중…",
)
