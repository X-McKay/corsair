"""Canonical recipe wire contracts: one module per runtime, one discriminated union.

Each ``<language>.py`` module holds the operator-owned recipe members for one runtime;
its trusted observer is ``adapters/sandboxing/drivers/<language>/``. This package owns
the cross-runtime pieces: the ``Recipe`` union and its ``kind`` discriminator, the
Python callable grouping, and the kinds whose driver executes a native binary.
"""

from __future__ import annotations

from typing import Annotated, Any

from pydantic import Discriminator, Tag

from .c import CRecipe as CRecipe
from .java import JavaRecipe as JavaRecipe
from .javascript import JavaScriptRecipe as JavaScriptRecipe
from .perl import PerlRecipe as PerlRecipe
from .python import PythonCommandSentinel as PythonCommandSentinel
from .python import PythonRecipe as PythonRecipe
from .ruby import RubyRecipe as RubyRecipe


def _recipe_kind(value: Any) -> str:
    """Discriminate recipe members by ``kind``.

    A request that predates the recipe union omits ``kind``; it is the original
    Python secret-disclosure recipe, so a missing tag resolves there. This keeps the
    frozen request fixtures (and their recorded digests) valid without a rewrite.
    """
    tag = value.get("kind") if isinstance(value, dict) else getattr(value, "kind", None)
    return tag if isinstance(tag, str) else "python.secret_disclosure/1"


# The Python callable recipes: both import one stdlib module directly and invoke one
# public function, so they share the Python-AST gates (target binding, line derivation)
# that other languages replace with their own run-time binding gates.
PythonCallableRecipe = PythonRecipe | PythonCommandSentinel
PYTHON_CALLABLE_RECIPES = (PythonRecipe, PythonCommandSentinel)


# The admitted recipe alternatives, discriminated on the stable ``kind`` tag following
# the native ProducerDecision pattern. Each member is one concrete, tested recipe with
# its own trusted observer and runtime image; adding a language adds a union member, not
# a generic adapter. Every member exposes ``module_file`` so the finding binds uniformly.
Recipe = Annotated[
    Annotated[PythonRecipe, Tag("python.secret_disclosure/1")]
    | Annotated[PythonCommandSentinel, Tag("python.command_sentinel/1")]
    | Annotated[JavaScriptRecipe, Tag("javascript.prototype_pollution/1")]
    | Annotated[RubyRecipe, Tag("ruby.secret_disclosure/1")]
    | Annotated[JavaRecipe, Tag("java.secret_disclosure/1")]
    | Annotated[PerlRecipe, Tag("perl.html_injection/1")]
    | Annotated[CRecipe, Tag("c.integer_overflow/1")],
    Discriminator(_recipe_kind),
]


# Deliberate, kind-scoped relaxation: recipe kinds whose trusted driver compiles and
# executes a native binary in /work. Only their /work tmpfs drops noexec (nosuid, nodev,
# size, mode and ownership stay); every interpreter recipe keeps /work noexec, /tmp is
# always noexec, and every other container control is unchanged.
NATIVE_EXEC_KINDS = frozenset({"c.integer_overflow/1"})


# Interim guard (round 4): the recipe kinds whose clean-negative path is qualified.
# A clean negative's only semantic check is the outcome-blind auditor's ACCEPT, and the
# auditor rubric is qualified for the Python kinds only, so a held pair of any other
# kind stays INCONCLUSIVE. Positives rest on trusted observations and are unaffected.
# A kind joins this set only with a qualified per-kind auditor cohort.
CLEAN_NEGATIVE_QUALIFIED_KINDS = frozenset(
    {"python.secret_disclosure/1", "python.command_sentinel/1"}
)
