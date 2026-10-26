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
from typing import Literal, Self

from pydantic import Field, JsonValue, field_validator, model_validator

from .common import Contract, safe_path

_PACKAGE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*(::[A-Za-z_][A-Za-z0-9_]*)*")
_SUB = re.compile(r"[A-Za-z][A-Za-z0-9_]*")
_DEFAULT_CONTROL = "<div class='comment'>hello</div>"


def _markup_chars(text: str) -> int:
    """Count ``<``/``>`` exactly as driver.pl's ``_markup_chars`` does."""
    return sum(char in "<>" for char in text)


class PerlRecipe(Contract):
    """HTML-injection check at a Perl sub's real API, observed in an offline container."""

    kind: Literal["perl.html_injection/1"] = "perl.html_injection/1"
    module_file: str
    package: str
    function: str
    # Operator-fixed leading positional arguments; the model payload is appended last.
    fixed_args: list[JsonValue] = Field(default_factory=list)
    expected_control: JsonValue = _DEFAULT_CONTROL
    # The count of markup characters (``<`` and ``>``) the fixed template contributes on
    # benign input; the control confirms it and the adversarial role rejects any excess.
    # When omitted it is derived from a string ``expected_control`` (and is required for any
    # other expected value). An explicit value for a string control must equal that count:
    # the driver requires both the exact benign return and this count, so any other value
    # would make every control INVALID.
    baseline_markup_chars: int = Field(default=_markup_chars(_DEFAULT_CONTROL), ge=0, le=4096)
    # Substrings of a Perl ``die`` message the adversarial role may treat as a handled
    # rejection rather than an observer error; empty means any die is an error.
    allowed_exceptions: list[str] = Field(default_factory=list)

    _safe_module = field_validator("module_file")(safe_path)

    @model_validator(mode="before")
    @classmethod
    def derive_baseline(cls, data: object) -> object:
        if isinstance(data, dict) and "baseline_markup_chars" not in data:
            control = data.get("expected_control", _DEFAULT_CONTROL)
            if not isinstance(control, str):
                raise ValueError(
                    "baseline_markup_chars is required when expected_control is not a string"
                )
            return {**data, "baseline_markup_chars": _markup_chars(control)}
        return data

    @model_validator(mode="after")
    def consistent_baseline(self) -> Self:
        control = self.expected_control
        if isinstance(control, str) and self.baseline_markup_chars != _markup_chars(control):
            raise ValueError(
                "baseline_markup_chars must equal the markup count of expected_control"
            )
        return self

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
