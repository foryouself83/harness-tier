import pytest

from tests.flow_init._helpers import PLUGIN


def _is_type_checking(test) -> bool:
    """`if TYPE_CHECKING:` exactly — the one test whose body python never runs.

    A substring search over the dumped node also exempts `if not TYPE_CHECKING:` and
    `if x == "TYPE_CHECKING":`, whose bodies DO run.
    """
    import ast

    if isinstance(test, ast.Name) and test.id == "TYPE_CHECKING":
        return True
    return isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"


def _runtime_builtin_generics(source: str) -> list[int]:
    """Line numbers where a builtin generic is subscripted somewhere python evaluates it.

    Everything under an annotation is exempt (`from __future__ import annotations` makes those
    strings), and so is an `if TYPE_CHECKING:` body, which never runs. What is left — a type
    alias, a default argument, a class attribute, a `try:` body at module level, a call inside
    a function — is evaluated for real and needs python 3.9.
    """
    import ast

    tree = ast.parse(source)
    exempt: set[int] = set()
    for node in ast.walk(tree):
        deferred = [
            getattr(node, "annotation", None),
            getattr(node, "returns", None),
        ]
        if isinstance(node, ast.If) and _is_type_checking(node.test):
            deferred += node.body
        for sub in (d for d in deferred if d is not None):
            exempt.update(id(n) for n in ast.walk(sub))
    builtins_ = {"list", "dict", "set", "tuple", "frozenset", "type"}
    return sorted(
        node.lineno
        for node in ast.walk(tree)
        if isinstance(node, ast.Subscript)
        and isinstance(node.value, ast.Name)
        and node.value.id in builtins_
        and id(node) not in exempt
    )


def test_copied_scripts_carry_no_runtime_builtin_generic():
    """Every script the host runs has to import under python 3.8 (Invariant #1, Exception 1).

    A TypeError raised while importing one aborts whichever gate script imported it, and a gate
    that never runs blocks nothing — including the unclassified commit it exists to catch.
    """
    from scripts.flow_init_setup import COPY_FILES

    offenders = [
        f"{rel}:{line}"
        for rel in COPY_FILES
        if rel.endswith(".py")
        for line in _runtime_builtin_generics((PLUGIN / rel).read_text(encoding="utf-8"))
    ]
    assert offenders == []


@pytest.mark.parametrize(
    "source",
    [
        "Finding = tuple[str, int]\n",
        "try:\n    Finding = tuple[str, int]\nexcept TypeError:\n    pass\n",
        "class C:\n    Finding = tuple[str, int]\n",
        "def f(x=list[int]()):\n    pass\n",
        "def f():\n    return dict[str, int]()\n",
        "tuple[int]\n",
        "from typing import TYPE_CHECKING\nif not TYPE_CHECKING:\n    F = tuple[str]\n",
        'if x == "TYPE_CHECKING":\n    F = tuple[str]\n',
        "if TYPE_CHECKING_OFF:\n    F = tuple[str]\n",
    ],
)
def test_the_38_guard_sees_every_place_python_evaluates_one(source: str):
    # A guard that only reads module-level assignments passes five of these six.
    assert _runtime_builtin_generics(source)


@pytest.mark.parametrize(
    "source",
    [
        "def f(x: list[int]) -> dict[str, int]:\n    pass\n",
        "x: tuple[int, str]\n",
        "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    F = tuple[str, int]\n",
    ],
)
def test_the_38_guard_exempts_what_python_never_evaluates(source: str):
    assert _runtime_builtin_generics(source) == []
