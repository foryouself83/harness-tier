import pytest

import evals.run as run
from tests.evals._helpers import _NoRealSessions


@pytest.fixture(autouse=True)
def no_real_sessions(monkeypatch):
    """Make the model-free guarantee structural rather than a convention.

    Every test in this package monkeypatches `run._one`, which is the only reason none of them
    spends a session — a guarantee that rests on each future test author remembering the same thing.
    A test that called `run_session` (or `_one` unpatched) would spawn real `claude`
    processes against a rate limit, in CI, silently and slowly. Patching the module object's
    `subprocess` reference rather than `subprocess.run` itself keeps the block scoped to
    `evals.run`, so the rest of the suite can still shell out."""
    monkeypatch.setattr(run, "subprocess", _NoRealSessions())


@pytest.fixture(autouse=True)
def reset_capture_state():
    """Capture state is module-level, so it leaks between tests without this — `CAPTURED` makes
    the second write skip and the failure reads as a broken implementation.

    Calls the production reset rather than listing the globals again. The earlier version
    listed them, and that is how the bug got in: this fixture reset three while the runner
    reset two, so the suite stayed green over a leak a real second run would hit."""
    run._reset_capture_state()
    yield
    run._reset_capture_state()
