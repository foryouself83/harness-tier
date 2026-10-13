"""Which agent harnesses this plugin installs its gate into, and the package that does it for each."""  # noqa: E501

from __future__ import annotations

import importlib

KNOWN = ("claude", "codex", "antigravity")
SUPPORTED = ("claude", "codex")


def installer(name: str):
    if name not in KNOWN:
        raise ValueError(f"unknown harness: {name}")
    if name not in SUPPORTED:
        raise NotImplementedError(f"harness not supported yet: {name}")
    try:
        return importlib.import_module(f"harness.{name}.install")
    except ImportError:
        return importlib.import_module(f"scripts.harness.{name}.install")
