"""Canonical JavaScript recipe contract; no vendor SDK types.

The first JavaScript recipe checks one narrow operator-owned property -- that a
model-controlled JSON value, merged by a fixed public callable into an operator-fixed
target, does not pollute ``Object.prototype`` (CWE-1321). It is the JavaScript analogue
of ``PythonRecipe``: the investigator controls only the final positional argument (the
merge source); the callable, the module file and the leading fixed arguments are not
editable. Support is deliberately CommonJS, dependency-free ``.js`` modules with one
exported function, observed by Node's built-in test runner and V8 line coverage.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import Field, JsonValue, field_validator

from .common import Contract, safe_path

# A conservative public JavaScript identifier (ASCII; `$` permitted, no leading digit).
_JS_IDENTIFIER = re.compile(r"[A-Za-z$][A-Za-z0-9_$]*")


def _default_fixed_arguments() -> list[JsonValue]:
    """One fixed leading argument: an empty merge target the payload is merged into."""
    return [{}]


class JavaScriptRecipe(Contract):
    """Operator-owned prototype-pollution check at a CommonJS callable's real API.

    The investigator controls ONLY the model payload, which the trusted driver passes
    as the final positional argument to ``function(*fixed_arguments, payload)``. The
    module file, the callable and the fixed leading arguments are not editable. No
    private fixture or secret is involved: the observed property is whether invoking the
    callable adds any enumerable property to ``Object.prototype``.
    """

    kind: Literal["javascript.prototype_pollution/1"] = "javascript.prototype_pollution/1"
    module_file: str
    function: str
    # Operator-fixed leading positional arguments; the model payload is appended last.
    fixed_arguments: list[JsonValue] = Field(default_factory=_default_fixed_arguments)

    _safe_module = field_validator("module_file")(safe_path)

    @field_validator("module_file")
    @classmethod
    def javascript_file(cls, value: str) -> str:
        if not value.endswith(".js"):
            raise ValueError("the JavaScript recipe supports CommonJS .js source files only")
        return value

    @field_validator("function")
    @classmethod
    def identifier(cls, value: str) -> str:
        if not _JS_IDENTIFIER.fullmatch(value):
            raise ValueError("expected a public JavaScript identifier")
        return value

    @field_validator("fixed_arguments")
    @classmethod
    def arguments(cls, value: list[JsonValue]) -> list[JsonValue]:
        if len(value) > 16:
            raise ValueError("too many fixed arguments")
        if len(json.dumps(value)) > 16000:
            raise ValueError("fixed arguments exceed the recipe limit")
        return value
