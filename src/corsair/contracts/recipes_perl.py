"""Operator-owned Perl HTML-injection recipe (CWE-79).

One concrete, narrow property: a public Perl sub renders a model-controlled value into
markup, and the rendered output must carry no more markup characters (``<``/``>``) than
the fixed template contributes.  An excess is an injected tag.  This mirrors the Python
secret-disclosure recipe's "the real secret must not appear in the rendered output"
shape; secret disclosure itself does not fit any Perl corpus row, so the ``kind`` is
named for the property the driver actually asserts.

The investigator controls ONLY the final positional payload.  Fixed leading arguments,
the expected benign return, the template markup budget, and the exception policy are not
editable, and a payload may not stand in for an operator-fixed argument.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import Field, JsonValue, field_validator

from .common import Contract, safe_path

_PACKAGE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(::[A-Za-z_][A-Za-z0-9_]*)*")
_SUB = re.compile(r"[A-Za-z][A-Za-z0-9_]*")


class PerlRecipe(Contract):
    """HTML-injection check at a Perl sub's real API, observed in an offline container."""

    kind: Literal["perl.html_injection/1"] = "perl.html_injection/1"
    module_file: str
    package: str
    function: str
    # Operator-fixed leading positional arguments; the model payload is appended last.
    fixed_args: list[JsonValue] = Field(default_factory=list)
    expected_control: JsonValue = "<div class='comment'>hello</div>"
    # The count of markup characters (``<`` and ``>``) the fixed template contributes on
    # benign input; the control confirms it and the adversarial role rejects any excess.
    baseline_markup_chars: int = Field(default=0, ge=0, le=4096)
    # Substrings of a Perl ``die`` message the adversarial role may treat as a handled
    # rejection rather than an observer error; empty means any die is an error.
    allowed_exceptions: list[str] = Field(default_factory=list)

    _safe_module = field_validator("module_file")(safe_path)

    @field_validator("module_file")
    @classmethod
    def perl_file(cls, value: str) -> str:
        if not value.endswith((".pm", ".pl")):
            raise ValueError("the Perl recipe supports .pm/.pl source files only")
        return value

    @field_validator("package")
    @classmethod
    def perl_package(cls, value: str) -> str:
        if not _PACKAGE.fullmatch(value):
            raise ValueError("expected a Perl package name")
        return value

    @field_validator("function")
    @classmethod
    def perl_sub(cls, value: str) -> str:
        if not _SUB.fullmatch(value):
            raise ValueError("expected a public Perl sub name")
        return value

    @field_validator("fixed_args")
    @classmethod
    def bounded_fixed_args(cls, value: list[JsonValue]) -> list[JsonValue]:
        if len(value) > 16 or len(json.dumps(value)) > 16000:
            raise ValueError("fixed arguments exceed the recipe limit")
        return value

    @field_validator("allowed_exceptions")
    @classmethod
    def bounded_exceptions(cls, value: list[str]) -> list[str]:
        if len(value) > 16 or any(not item or len(item) > 200 for item in value):
            raise ValueError("invalid allowed exception substrings")
        return value
