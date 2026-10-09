"""Spawn one headless `claude -p` session, isolated from this machine's config."""

import os
import signal
import subprocess
import tempfile
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path

import evals.scores as scores
import evals.stream as stream
import scripts.skill_sandbox as sandbox
from evals.runner import capture, config


def _tail(err: str, lines: int = 5) -> str:
    """The last of a dead session's stderr, for the SystemExit that reports it. Captured but
    never read is how the cause of an unusable session got thrown away."""
    kept = [ln for ln in err.strip().splitlines() if ln.strip()][-lines:]
    return "\n  stderr: " + "\n          ".join(kept) if kept else ""


@dataclass
class Raw:
    """What the process did, beside what its transcript says: `stream.observe` reads `text`,
    and a session killed on the timeout leaves a transcript that cannot say it was killed."""

    text: str
    err: str
    timed_out: bool = False
    elapsed: float = 0.0
    returncode: int | None = None


class RateLimited(RuntimeError):
    """The five-hour window is exhausted. Overage is rejected on this account, so the CLI
    starts failing rather than billing — and a failed session recorded as "the skill did not
    fire" is a fabricated score. Everything measured before this point is already on disk."""


@contextmanager
def isolated_config_dir() -> Iterator[Path]:
    """A config dir holding credentials and nothing else.

    Isolation is what makes the score about *these* descriptions. This machine has a second
    installed plugin shipping seven of the same skill names, and a twin winning the
    invocation reads as our skill not firing — a property of one developer's setup, not of
    the description, and not reproducible by anyone else.

    The credentials are the one thing that has to survive the isolation. An empty config dir
    still produces a well-formed `init` event and then answers "Not logged in", so every
    session would score 0.0 for a reason that has nothing to do with any skill. Measured: ten
    such sessions read invoke_rate 0.00 before this was found.

    The copy is a live credential sitting in a world-writable system temp dir for the length
    of the run, so it is written through `os.open` with 0o600 rather than `shutil.copy2`
    (which would carry the source mode in and leave the file briefly readable in between).
    Permissions are only half of it — on Windows they are largely advisory — so the credential
    is also unlinked in a `finally`, before the temp tree comes down. A context manager rather
    than a plain function so that cleanup lives next to the copy: the previous shape leaned on
    the caller's `TemporaryDirectory` alone, which meant the one file here worth worrying about
    outlived any exit that skipped the tree removal.

    `ignore_cleanup_errors` matches `_one`: on Windows a session's leftover child process can
    still hold a handle on the tree, and the two temp dirs disagreeing on that meant the config
    root could raise at exit over a directory the OS reclaims anyway.
    """
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as root:
        cfg = Path(root) / "cfg"
        cfg.mkdir(exist_ok=True)
        src = Path.home() / ".claude" / ".credentials.json"
        if not src.exists():
            raise SystemExit(
                f"no credentials at {src} — isolated sessions cannot authenticate. "
                f"Keychain-stored logins (macOS) and API-key auth keep nothing there; this "
                f"runner currently requires a machine whose subscription login wrote "
                f".credentials.json (Windows/Linux)."
            )
        dst = cfg / src.name
        fd = os.open(dst, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "wb") as out:
            out.write(src.read_bytes())
        try:
            yield cfg
        finally:
            dst.unlink(missing_ok=True)


def session_env(config_dir: Path) -> dict[str, str]:
    """Everything provider-shaped is stripped rather than whitelisting the world: the CLI
    needs an unknowable, platform-varying set of system variables (PATH, APPDATA, node's
    own), while the contamination surface is exactly the provider-prefixed names —
    ANTHROPIC_BASE_URL reroutes every session through a proxy, ANTHROPIC_API_KEY switches
    the auth path away from the copied credential, CLAUDE_CODE_* flips CLI behaviour. One
    developer's shell must not become a fact in the committed baseline."""
    env = {
        k: v
        for k, v in os.environ.items()
        if not (k.startswith("ANTHROPIC_") or k.startswith("CLAUDE_"))
    }
    env["CLAUDE_CONFIG_DIR"] = str(config_dir)
    return env


def _claude_stream(
    prompt: str,
    fixture: str | None,
    workdir: Path,
    config_dir: Path,
    restricted: bool = False,
    *,
    permission_mode: str | None = None,
    add_dirs: tuple[Path, ...] = (),
    max_turns: int = config.MAX_TURNS,
    timeout: int = config.SESSION_TIMEOUT,
) -> Raw:
    """Run one headless `claude -p` session; return its `Raw`, stdout and stderr as utf-8.

    Extracted from run_session so a caller that needs the raw stream (the outcome arm) can
    reuse the subprocess + timeout-kill + decode logic without duplicating it. run_session
    observes the returned text itself.

    The keyword-only tail exists for the outcome arm and defaults to reproduce the scored
    command byte-for-byte: run_session passes none of them, so the invocation measurement is
    unchanged. outcome.run_outcome passes `permission_mode="bypassPermissions"`,
    `add_dirs=(REPO,)`, a higher `max_turns`, and a longer `timeout` so the session can
    edit files and run to a natural end."""
    if fixture:
        # build() creates workdir/<scenario> and returns it — run *there*. Staying in the
        # parent would put the agent in a directory holding a single subdirectory, which is
        # the empty-cwd condition that makes it explore before it reaches for a skill, and
        # every fixture-backed skill would score low for a reason that is not its description.
        workdir = sandbox.build(sandbox.BY_NAME[fixture], workdir)
    cmd = [
        "claude",
        "-p",
        prompt,
        "--output-format",
        "stream-json",
        "--verbose",
        "--max-turns",
        str(max_turns),
        "--model",
        scores.MODEL,
        "--plugin-dir",
        str(config.REPO),
    ]
    if restricted:
        # The diagnostic arm. With no other tool on offer the agent cannot quietly do the
        # work itself, so what is left is whether the prompt matches the description at all.
        # It answers a different question from the scored arms and is never gated.
        cmd += ["--allowedTools", "Skill"]
    # Outcome arm only — the defaults above leave the scored command byte-identical.
    if permission_mode:
        cmd += ["--permission-mode", permission_mode]
    for d in add_dirs:
        cmd += ["--add-dir", str(d)]
    proc = subprocess.Popen(
        cmd,
        cwd=workdir,
        env=session_env(config_dir),
        stdin=subprocess.DEVNULL,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        # POSIX: a fresh process group, so the timeout path below can kill the whole tree
        # with one killpg. Ignored on Windows, where taskkill /T walks the tree instead.
        start_new_session=os.name != "nt",
    )
    start = time.monotonic()
    timed_out = False
    try:
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
        # subprocess.run()'s timeout path kills only the direct child and then drains the
        # pipes with an UNBOUNDED communicate(); a surviving grandchild holding the
        # inherited write handles blocks that read forever — on this module's own Windows
        # evidence that children outlive the kill, the "hang guard" was itself the hang.
        # Kill the tree first, then drain: with every writer dead the pipes close.
        if os.name == "nt":
            subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(proc.pid)],
                capture_output=True,
                check=False,
            )
        else:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                proc.kill()  # the group is already gone; reap whatever is left
        out, err = proc.communicate()
    return Raw(
        out.decode("utf-8", errors="replace"),
        err.decode("utf-8", errors="replace"),
        timed_out=timed_out,
        elapsed=round(time.monotonic() - start, 1),
        returncode=proc.returncode,
    )


def run_session(
    prompt: str, fixture: str | None, workdir: Path, config_dir: Path, restricted: bool = False
) -> tuple[stream.Observation, Raw]:
    """Returns the observation plus the `Raw` it was read from.

    The `Raw` is carried alongside rather than folded into the Observation because
    `stream.observe` answers questions about the transcript and knows nothing about the
    process that produced it. Its stderr and timeout flag are the only record of *why* a
    session produced no usable stream, and capturing them without ever reading them is how
    that cause got lost."""
    # The turn cap exits 1 with the stream fully written, and a timeout kill leaves no exit
    # code worth reading either. Parse, then judge.
    raw = _claude_stream(prompt, fixture, workdir, config_dir, restricted)
    obs = stream.observe(raw.text)
    # Riding along with a real run is the whole point: a re-capture on its own would have to
    # spend sessions hunting for a turn-capped firing, while measuring one skill already runs
    # 35 and the conditions fall out of them.
    capture.maybe_capture(obs, raw.text)
    return obs, raw


def _one(prompt: str, fixture: str | None, config_dir: Path, restricted: bool):
    # On Windows, killing `claude` on the timeout does not necessarily kill every process it
    # spawned, so the temp dir can still be held open a moment after the session returns.
    # ignore_cleanup_errors keeps that race from crashing the whole run over one leaked
    # directory that the OS will reclaim regardless.
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        return run_session(prompt, fixture, Path(tmp), config_dir, restricted)
