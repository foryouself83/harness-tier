import pytest

from evals.runner import capture, diagnose, session
from tests.evals._helpers import _NoRealSessions


@pytest.fixture(autouse=True)
def no_real_sessions(monkeypatch):
    """Make the model-free guarantee structural rather than a convention.

    Every test in this package monkeypatches `session._one`, which is the only reason none of them
    spends a session — a guarantee that rests on each future test author remembering the same thing.
    A test that called `run_session` (or `_one` unpatched) would spawn real `claude`
    processes against a rate limit, in CI, silently and slowly. Patching the module object's
    `subprocess` reference rather than `subprocess.run` itself keeps the block scoped to
    `evals.runner.session`, so the rest of the suite can still shell out."""
    monkeypatch.setattr(session, "subprocess", _NoRealSessions())


@pytest.fixture(autouse=True)
def reset_capture_state():
    """Capture state is module-level, so it leaks between tests without this — `CAPTURED` makes
    the second write skip and the failure reads as a broken implementation.

    Calls the production reset rather than listing the globals again. The earlier version
    listed them, and that is how the bug got in: this fixture reset three while the runner
    reset two, so the suite stayed green over a leak a real second run would hit."""
    capture._reset_capture_state()
    yield
    capture._reset_capture_state()


@pytest.fixture(autouse=True)
def runs_dir(monkeypatch, tmp_path):
    """`diagnose.record` writes beside the repo by default; a test must never leave one there."""
    monkeypatch.setattr(diagnose, "RUNS_DIR", tmp_path / "runs")
    return tmp_path / "runs"
