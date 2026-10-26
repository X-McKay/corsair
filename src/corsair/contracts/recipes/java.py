"""Canonical Java recipe contract; the second concrete recipe after PythonRecipe.

The Java secret-disclosure recipe mirrors :class:`PythonRecipe`: the investigator
controls ONLY the value of the single payload, a model-authored JSON string that the
trusted driver passes as the sole ``String`` argument of a fixed public callable.  The
operator fixes the entry class, method, compile roots, public fixtures, the expected
benign return, and the exception policy.  The private fixture's random content never
appears in an agent prompt, the job JSON, or any observation.  See
``docs/reference/corpus-java.md`` for the per-row survey that chose the qualified row.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, field_validator

from ..common import Contract, safe_path

_JAVA_IDENTIFIER = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*")
_JAVA_FQN = re.compile(r"[A-Za-z_$][A-Za-z0-9_$]*(\.[A-Za-z_$][A-Za-z0-9_$]*)*")


class JavaRecipe(Contract):
    """Operator-owned secret-disclosure check at one Java callable's real API.

    The fixed trusted driver compiles the admitted source with ``javac`` alone (no
    build tool, no dependency resolution), writes a fixed JUnit 5 test that invokes
    ``entry_class.method(payload)`` reflectively, runs it under the JaCoCo agent, and
    reports whether the private fixture value occurs in the rendered return.
    """

    kind: Literal["java.secret_disclosure/1"] = "java.secret_disclosure/1"
    module_file: str
    entry_class: str
    method: str
    source_roots: list[str] = Field(default_factory=lambda: ["src/main/java"])
    public_files: dict[str, str] = Field(default_factory=lambda: {"hello.txt": "hello"})
    expected_control: str = "hello"
    allowed_exceptions: list[str] = Field(default_factory=list)

    _safe_module = field_validator("module_file")(safe_path)

    @field_validator("module_file")
    @classmethod
    def java_file(cls, value: str) -> str:
        if not value.endswith(".java"):
            raise ValueError("the Java recipe supports Java source files only")
        return value

    @field_validator("entry_class")
    @classmethod
    def fully_qualified_class(cls, value: str) -> str:
        if not _JAVA_FQN.fullmatch(value):
            raise ValueError("entry_class must be a fully qualified Java class name")
        return value

    @field_validator("method")
    @classmethod
    def public_method(cls, value: str) -> str:
        if not _JAVA_IDENTIFIER.fullmatch(value) or value.startswith(("_", "$")):
            raise ValueError("expected a public Java method identifier")
        return value

    @field_validator("source_roots")
    @classmethod
    def compile_roots(cls, value: list[str]) -> list[str]:
        if not value or len(value) > 8:
            raise ValueError("source_roots must name between one and eight compile roots")
        for root in value:
            safe_path(root)
        return value

    @field_validator("public_files")
    @classmethod
    def fixtures(cls, value: dict[str, str]) -> dict[str, str]:
        if len(value) > 16 or sum(len(text.encode()) for text in value.values()) > 65536:
            raise ValueError("public fixtures exceed the recipe limit")
        for name in value:
            safe_path(name)
        return value

    @field_validator("allowed_exceptions")
    @classmethod
    def exceptions(cls, value: list[str]) -> list[str]:
        if len(value) > 16 or any(
            not _JAVA_FQN.fullmatch(item) or "." not in item for item in value
        ):
            raise ValueError("exceptions must be fully qualified Java class names")
        return value
