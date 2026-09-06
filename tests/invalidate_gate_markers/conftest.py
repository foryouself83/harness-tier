"""The project fixture every module here builds on."""

from pathlib import Path

import pytest

from tests.invalidate_gate_markers._helpers import KEPT, flow, repo


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = repo(tmp_path / "project")
    for name in KEPT:
        (flow(root) / name).touch()
    return root
