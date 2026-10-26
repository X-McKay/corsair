"""Canonical C recipe wire contract; no vendor SDK types.

One narrow, operator-owned property: a length-controlled copy whose out-of-range
length triggers a heap/stack sanitizer error on a vulnerable revision. The
investigator controls ONLY the integer length (the submission's control and exploit
payloads). The callable name, source fill byte, expected benign length, and the
admitted sanitizer class are operator-fixed and not editable from a model payload.

The trusted driver (``adapters/sandboxing/drivers/c/driver.py``) compiles the admitted
C source plus a FIXED harness under AddressSanitizer with gcov coverage; the sole
basis for a VIOLATION is a machine-readable sanitizer report of ``sanitizer_class`` in
a frame naming the target file. A plain crash is ERROR, never VIOLATION.
"""

from __future__ import annotations

import re
from typing import Literal

from pydantic import Field, field_validator

from .common import Contract, safe_path

# AddressSanitizer / UndefinedBehaviorSanitizer error classes admitted as the trusted
# assertion for this recipe kind. Keep this narrow; a new class is a recipe change.
SANITIZER_CLASSES = frozenset(
    {"heap-buffer-overflow", "stack-buffer-overflow", "global-buffer-overflow"}
)


class CRecipe(Contract):
    """Operator-owned integer-overflow / out-of-bounds-length check at a C callable.

    The fixed harness calls ``char *function(const char *buf, unsigned short len)`` with
    ``len`` set from the model-controlled length payload and ``buf`` an operator-filled
    source of that length. The control length must reproduce the expected public
    behaviour (``expected_control_length`` bytes returned) with no sanitizer error.
    """

    kind: Literal["c.integer_overflow/1"] = "c.integer_overflow/1"
    module_file: str
    function: str
    length_parameter: str = "len"
    fill_byte: int = Field(default=65, ge=1, le=126)
    expected_control_length: int = Field(default=0, ge=0, le=0xFFFF)
    sanitizer_class: str = "heap-buffer-overflow"

    _safe_module = field_validator("module_file")(safe_path)

    @field_validator("module_file")
    @classmethod
    def c_file(cls, value: str) -> str:
        if not value.endswith(".c"):
            raise ValueError("the C recipe supports C source files only")
        return value

    @field_validator("function", "length_parameter")
    @classmethod
    def c_identifier(cls, value: str) -> str:
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", value) or value.startswith("_"):
            raise ValueError("expected a public C identifier")
        return value

    @field_validator("sanitizer_class")
    @classmethod
    def known_sanitizer_class(cls, value: str) -> str:
        if value not in SANITIZER_CLASSES:
            raise ValueError("sanitizer_class must be an admitted sanitizer error class")
        return value
