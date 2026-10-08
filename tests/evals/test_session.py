import subprocess
from pathlib import Path

from evals.runner import session


class _Proc:
    pid = 0
    returncode = None

    def __init__(self, hang: bool):
        self.hang = hang

    def communicate(self, timeout=None):
        if self.hang and timeout is not None:
            raise subprocess.TimeoutExpired("claude", timeout)
        self.returncode = -9 if self.hang else 0
        return (b'{"type":"result"}', "중단\n".encode())


class _Subprocess:
    def __init__(self, hang: bool):
        self.hang = hang

    def Popen(self, cmd, **kwargs):
        return _Proc(self.hang)

    def run(self, cmd, **kwargs):
        return None

    def __getattr__(self, attr):
        return getattr(subprocess, attr)


def _run(monkeypatch, hang):
    monkeypatch.setattr(session, "subprocess", _Subprocess(hang))
    # The POSIX kill path must never reach a real process group.
    monkeypatch.setattr(session.os, "killpg", lambda *a: None, raising=False)
    return session._claude_stream("p", None, Path("."), Path("cfg"))


def test_a_finished_session_is_not_timed_out(monkeypatch):
    raw = _run(monkeypatch, hang=False)
    assert raw.timed_out is False
    assert raw.returncode == 0
    assert raw.text == '{"type":"result"}'
    assert raw.err == "중단\n"
    assert raw.elapsed >= 0


def test_a_killed_session_reports_the_timeout(monkeypatch):
    raw = _run(monkeypatch, hang=True)
    assert raw.timed_out is True
    assert raw.returncode == -9
    assert raw.text == '{"type":"result"}'
