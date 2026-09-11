"""Child environments for the host CLAUDE.md Invariant #2 describes: python I/O that is not UTF-8.

Pinned by variables rather than by the platform, so each one reproduces on the CI runner too.
"""

import os


def cp949_stdio_env(**extra: str) -> dict[str, str]:
    """stdin/stdout/stderr in cp949, the Windows hook host's codec.

    PYTHONIOENCODING outranks even UTF-8 mode, so a caller may pass PYTHONUTF8="1" to stand
    where the commit-gate runner does.
    """
    env = {k: v for k, v in os.environ.items() if k != "PYTHONUTF8"}
    env["PYTHONIOENCODING"] = "cp949"
    env.update(extra)
    return env


def ansi_locale_env(**extra: str) -> dict[str, str]:
    """No UTF-8 mode, so a text-mode pipe decodes with the locale codec.

    That is the ANSI code page on Windows, and ASCII under POSIX's C locale — with coercion off,
    or C.UTF-8 would stand in for it.
    """
    env = {k: v for k, v in os.environ.items() if k != "PYTHONIOENCODING"}
    env.update(PYTHONUTF8="0", LC_ALL="C", PYTHONCOERCECLOCALE="0")
    env.update(extra)
    return env
