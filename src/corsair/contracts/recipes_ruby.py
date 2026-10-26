"""Canonical Ruby recipe contract; no vendor SDK types.

A second, concrete recipe for a non-Python runtime.  It mirrors
:class:`corsair.contracts.sources.PythonRecipe` field for field so the trusted Ruby
driver reads the same operator-owned secret-disclosure check: the investigator controls
only the value of ``payload_parameter``; the receiver constant, method, fixed keyword
arguments, public fixtures, expected benign value, and tolerated exception classes are
operator-fixed and not editable.  The private fixture's random content never appears in
an agent prompt or the driver job.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import Field, JsonValue, field_validator, model_validator

from .common import Contract, safe_path

_RUBY_CONSTANT = re.compile(r"[A-Z]\w*(::[A-Z]\w*)*")
_RUBY_METHOD = re.compile(r"[a-z_]\w*[?!]?")
_RUBY_KEYWORD = re.compile(r"[a-z_]\w*")
_RUBY_EXCEPTION = re.compile(r"[A-Z]\w*(::[A-Z]\w*)*")


class RubyRecipe(Contract):
    """Operator-owned secret-disclosure check at a Ruby module/class method's real API.

    The trusted driver calls ``receiver.public_send(function, **fixed_kwargs,
    payload_parameter: payload)`` on the pinned source module inside the offline
    ``corsair-ruby`` image and asserts that the returned value never contains the
    private fixture.
    """

    kind: Literal["ruby.secret_disclosure/1"] = "ruby.secret_disclosure/1"
    module_file: str
    receiver: str
    function: str
    payload_parameter: str
    fixed_kwargs: dict[str, JsonValue] = Field(default_factory=dict)
    public_files: dict[str, str] = Field(default_factory=lambda: {"hello.txt": "hello"})
    expected_control: JsonValue = "hello"
    allowed_exceptions: list[str] = Field(default_factory=lambda: ["ArgumentError"])

    _safe_module = field_validator("module_file")(safe_path)

    @field_validator("module_file")
    @classmethod
    def ruby_file(cls, value: str) -> str:
        if not value.endswith(".rb"):
            raise ValueError("the Ruby recipe supports Ruby source files only")
        return value

    @field_validator("receiver")
    @classmethod
    def ruby_constant(cls, value: str) -> str:
        if not _RUBY_CONSTANT.fullmatch(value):
            raise ValueError("expected a Ruby constant path (e.g. Attachments or A::B)")
        return value

    @field_validator("function")
    @classmethod
    def ruby_method(cls, value: str) -> str:
        if not _RUBY_METHOD.fullmatch(value) or value.startswith("_"):
            raise ValueError("expected a public Ruby method name")
        return value

    @field_validator("payload_parameter")
    @classmethod
    def ruby_keyword(cls, value: str) -> str:
        if not _RUBY_KEYWORD.fullmatch(value) or value.startswith("_"):
            raise ValueError("expected a public Ruby keyword-argument name")
        return value

    @field_validator("fixed_kwargs")
    @classmethod
    def keyword_arguments(cls, value: dict) -> dict:
        if len(value) > 16 or any(not _RUBY_KEYWORD.fullmatch(key) for key in value):
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
        if any(not _RUBY_EXCEPTION.fullmatch(item) for item in value):
            raise ValueError("exceptions must be Ruby class names")
        return value

    @model_validator(mode="after")
    def payload_not_fixed(self):
        if self.payload_parameter in self.fixed_kwargs:
            raise ValueError("payload_parameter may not override an operator-fixed argument")
        return self
