"""Test-framework adapters: the only language-specific code the kernel runs.

An adapter owns five things for one framework: the structural guard on a submitted probe, the kernel-owned driver
files that turn the probe into two native test ids, the command and environment that run one payload alone under
coverage, the result files to collect, and how to read those files into a ``ProbeResult``. Everything else (build
replay, twin sandboxes, gates, verdict, fix verification) is generic and lives in ``corsair.kernel``.

Adding a language is one module here, one image under ``images/`` and one row in ``matrix.yaml``. Registration is
explicit; nothing is discovered.
"""
from __future__ import annotations

from collections.abc import Callable

from .base import Framework, ProbeResult

__all__ = ("FRAMEWORKS", "Framework", "ProbeResult", "framework")


def framework(name: str) -> Framework:
    """The adapter registered under ``name``; unknown names are an error, never a fallback."""
    try:
        return FRAMEWORKS[name]()
    except KeyError:
        raise ValueError(f"no framework adapter named {name!r}; known: {', '.join(sorted(FRAMEWORKS))}") from None


def _pytest() -> Framework:
    from .pytest_ import Pytest

    return Pytest()


def _node_test() -> Framework:
    from .node_test import NodeTest

    return NodeTest()


def _javac_java() -> Framework:
    from .javac_java import JavacJava

    return JavacJava()


def _perl_tap() -> Framework:
    from .perl_tap import PerlTap

    return PerlTap()


FRAMEWORKS: dict[str, Callable[[], Framework]] = {
    "pytest": _pytest,
    "node-test": _node_test,
    "javac-java": _javac_java,
    "perl-tap": _perl_tap,
}
