"""Canonical Python recipe wire contracts; no vendor SDK types.

`PythonRecipe` is the initial secret-disclosure check; `PythonCommandSentinel` is the
command/code-execution check. Both bind one public Python callable and share the one
trusted driver (``adapters/sandboxing/drivers/python/driver.py``). Every member
constrains the model to one JSON payload value and keeps the assertion with the operator.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import Field, JsonValue, field_validator, model_validator

from ..common import Contract, safe_path


def _public_identifier(value: str) -> str:
    if not value.isidentifier() or value.startswith("_"):
        raise ValueError("expected a public Python identifier")
    return value


def _fixed_keyword_arguments(value: dict) -> dict:
    if len(value) > 16 or any(not key.isidentifier() for key in value):
        raise ValueError("invalid fixed keyword arguments")
    if len(json.dumps(value)) > 16000:
        raise ValueError("fixed arguments exceed the recipe limit")
    return value


def _bounded_public_files(value: dict[str, str]) -> dict[str, str]:
    if len(value) > 16 or sum(len(text.encode()) for text in value.values()) > 65536:
        raise ValueError("public fixtures exceed the recipe limit")
    for name in value:
        safe_path(name)
    return value


def _qualified_exceptions(value: list[str]) -> list[str]:
    if any(not re.fullmatch(r"[A-Za-z][\w]*(\.[A-Za-z][\w]*)+", item) for item in value):
        raise ValueError("exceptions must have fully qualified names")
    return value


class PythonRecipe(Contract):
    """Operator-owned secret-disclosure check at a Python callable's real API.

    The investigator controls ONLY the value of payload_parameter. Fixed keyword
    arguments, fixtures, expected benign value, and exception policy are not editable.
    The private fixture's actual random content never appears in an agent prompt.
    """

    kind: Literal["python.secret_disclosure/1"] = "python.secret_disclosure/1"
    module_file: str
    function: str
    payload_parameter: str
    fixed_kwargs: dict[str, JsonValue] = Field(default_factory=dict)
    public_files: dict[str, str] = Field(default_factory=lambda: {"hello.txt": "hello"})
    expected_control: JsonValue = "hello"
    allowed_exceptions: list[str] = Field(default_factory=lambda: ["builtins.ValueError"])

    _safe_module = field_validator("module_file")(safe_path)

    @field_validator("module_file")
    @classmethod
    def python_file(cls, value: str) -> str:
        if not value.endswith(".py"):
            raise ValueError("the initial recipe supports Python source files only")
        return value

    @field_validator("function", "payload_parameter")
    @classmethod
    def identifier(cls, value: str) -> str:
        if not value.isidentifier() or value.startswith("_"):
            raise ValueError("expected a public Python identifier")
        return value

    @field_validator("fixed_kwargs")
    @classmethod
    def keyword_arguments(cls, value: dict) -> dict:
        if len(value) > 16 or any(not key.isidentifier() for key in value):
            raise ValueError("invalid fixed keyword arguments")
        if len(json.dumps(value)) > 16000:
            raise ValueError("fixed arguments exceed the recipe limit")
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
        if any(not re.fullmatch(r"[A-Za-z][\w]*(\.[A-Za-z][\w]*)+", item) for item in value):
            raise ValueError("exceptions must have fully qualified names")
        return value

    @model_validator(mode="after")
    def payload_not_fixed(self):
        if self.payload_parameter in self.fixed_kwargs:
            raise ValueError("payload_parameter may not override an operator-fixed argument")
        return self


class PythonCommandSentinel(Contract):
    """Operator-owned command/code-execution check at a Python callable's real API.

    The property: invoking the callable with the benign ``control`` payload must NOT
    create the operator-chosen private sentinel file, while a payload that achieves
    command or code execution does. The investigator controls ONLY the value of
    ``payload_parameter``; the sentinel path, fixed keyword arguments, fixtures, and
    exception policy are not editable. No private fixture content is ever revealed;
    the trusted observer reports only whether the fixed sentinel path was created.
    """

    kind: Literal["python.command_sentinel/1"] = "python.command_sentinel/1"
    module_file: str
    function: str
    payload_parameter: str
    fixed_kwargs: dict[str, JsonValue] = Field(default_factory=dict)
    public_files: dict[str, str] = Field(default_factory=lambda: {"hello.txt": "hello"})
    # A writable tmpfs path inside the container that only successful code/command
    # execution can create. It is operator-fixed and disclosed to the model so it can
    # target it; a non-executing callable cannot write there.
    sentinel_path: str = "/work/corsair-sentinel"
    allowed_exceptions: list[str] = Field(default_factory=lambda: ["builtins.ValueError"])

    _safe_module = field_validator("module_file")(safe_path)

    @field_validator("module_file")
    @classmethod
    def python_file(cls, value: str) -> str:
        if not value.endswith(".py"):
            raise ValueError("the command-sentinel recipe supports Python source files only")
        return value

    @field_validator("function", "payload_parameter")
    @classmethod
    def identifier(cls, value: str) -> str:
        return _public_identifier(value)

    @field_validator("fixed_kwargs")
    @classmethod
    def keyword_arguments(cls, value: dict) -> dict:
        return _fixed_keyword_arguments(value)

    @field_validator("public_files")
    @classmethod
    def fixtures(cls, value: dict[str, str]) -> dict[str, str]:
        return _bounded_public_files(value)

    @field_validator("allowed_exceptions")
    @classmethod
    def exceptions(cls, value: list[str]) -> list[str]:
        return _qualified_exceptions(value)

    @field_validator("sentinel_path")
    @classmethod
    def writable_sentinel(cls, value: str) -> str:
        # The sentinel lives on the container's writable /work tmpfs, never under the
        # read-only source, fixtures, or input mounts. It must be an unambiguous
        # absolute path with a non-empty name component and no traversal.
        parts = value.split("/")
        if (
            not value.startswith("/work/")
            or len(value) > 200
            or "\\" in value
            or "\x00" in value
            or any(part in {"", ".", ".."} for part in parts[1:])
        ):
            raise ValueError("sentinel_path must be an absolute non-traversing path under /work/")
        return value

    @model_validator(mode="after")
    def payload_not_fixed(self):
        if self.payload_parameter in self.fixed_kwargs:
            raise ValueError("payload_parameter may not override an operator-fixed argument")
        return self
