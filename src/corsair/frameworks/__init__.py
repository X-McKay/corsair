"""One Python differential driver with explicit, native target-coverage collectors.

Project build systems belong in build.sh and skills, not in kernel conditionals.
Each collector keeps the same clean-build, twin-run and evidence contract.
"""
from __future__ import annotations

from collections.abc import Callable
from importlib import import_module

from .base import Framework, ProbeResult

__all__ = ("FRAMEWORKS", "Framework", "ProbeResult", "framework")


def _adapter(module: str, name: str) -> Callable[[], Framework]:
    return lambda: getattr(import_module(f".{module}", __name__), name)()


FRAMEWORKS: dict[str, Callable[[], Framework]] = {
    "pytest": _adapter("pytest_", "Pytest"),
    "node": _adapter("node", "Node"),
    "java": _adapter("jvm", "Java"),
    "ruby": _adapter("ruby", "Ruby"),
    "perl": _adapter("perl", "Perl"),
    "cpp": _adapter("native_cpp", "Cpp"),
}


def framework(name: str) -> Framework:
    """Unknown adapters are errors, never silently replaced by a different runtime."""
    try:
        factory = FRAMEWORKS[name]
    except KeyError:
        raise ValueError(f"no framework adapter named {name!r}; known: {', '.join(sorted(FRAMEWORKS))}") from None
    return factory()
