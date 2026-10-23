"""Validate native evidence once for every adapter; malformed evidence never becomes a decisive outcome."""
from __future__ import annotations

import posixpath
import xml.etree.ElementTree as ET
from collections.abc import Mapping
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from .base import RESULT_DIR, WORKDIR, ProbeResult


class DriverRecord(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)

    role: Literal["control", "exploit"]
    outcome: Literal["holds", "violated", "errored"]
    exception_type: str | None
    message: str | None
    invariant_failed: bool


class CoveredFile(BaseModel):
    model_config = ConfigDict(strict=True)
    executed_lines: list[int] = Field(default_factory=list)


class CoverageReport(BaseModel):
    model_config = ConfigDict(strict=True)
    files: dict[str, CoveredFile]


def read_coverage(data: bytes | None, hypothesis) -> tuple[bool | None, tuple[int, ...]]:
    """Normalized coverage.py-shaped JSON. Paths must equal the target relative to /work, never just a suffix."""
    if not data:
        return None, ()
    try:
        report = CoverageReport.model_validate_json(data)
    except ValidationError:
        return None, ()
    target = posixpath.normpath(hypothesis.target_file)
    executed: set[int] = set()
    for path, info in report.files.items():
        path = posixpath.normpath(path)
        if path in (target, f"{WORKDIR}/{target}"):
            executed.update(line for line in info.executed_lines if line > 0)
    return bool(executed), tuple(sorted(executed.intersection(hypothesis.target_lines)))


def read_junit(data: bytes | None, role: str) -> tuple[int, str | None]:
    """Exactly one named, non-skipped native test. Invalid reports raise; missing reports have no tests."""
    if not data:
        return 0, None
    root = ET.fromstring(data)
    cases = list(root.iter("testcase"))
    if not cases:
        return 0, "the native test never ran (collection or import error)"
    if len(cases) != 1:
        raise ValueError(f"expected one native test, found {len(cases)}")
    case = cases[0]
    if case.get("name") != f"test_probe[{role}]":
        raise ValueError("native test identity does not match the requested payload")
    if case.find("skipped") is not None:
        raise ValueError("native test was skipped")
    for kind in ("failure", "error"):
        node = case.find(kind)
        if node is not None:
            return 1, f"{kind}: {(node.get('message') or node.text or '')[:500]}"
    return 1, None


def read_probe(files: Mapping[str, bytes | None], hypothesis, role: str) -> ProbeResult:
    from ..kernel import Outcome

    covered_target, covered_lines = read_coverage(files.get(f"{RESULT_DIR}/coverage.json"), hypothesis)
    count = 0
    exception_type = message = None
    try:
        data = files.get(f"{RESULT_DIR}/result.json")
        if not data:
            return ProbeResult(Outcome.NOT_RUN, None, "the driver never ran (collection or import error)",
                               0, covered_target, covered_lines)
        count, native = read_junit(files.get(f"{RESULT_DIR}/junit.xml"), role)
        if count == 0:
            outcome, message = Outcome.NOT_RUN, native or "the driver record or native report is missing"
        else:
            record = DriverRecord.model_validate_json(data)
            outcome = Outcome(record.outcome)
            exception_type, message = record.exception_type, record.message
            if record.role != role:
                raise ValueError("driver role does not match the requested payload")
            if (outcome is Outcome.HOLDS) != (native is None):
                raise ValueError(f"native report disagrees with the driver record: {native}")
            if outcome is Outcome.HOLDS and exception_type is not None:
                raise ValueError("a passing driver record contains an exception")
            if outcome is Outcome.VIOLATED and (exception_type != "AssertionError" or not record.invariant_failed):
                raise ValueError("violation was not raised by the kernel-owned invariant check")
    except (ValueError, ET.ParseError) as error:
        outcome, message = Outcome.ERRORED, f"invalid probe evidence: {error}"
    return ProbeResult(outcome, exception_type, message[:2000] if message else None,
                       count, covered_target, covered_lines)
