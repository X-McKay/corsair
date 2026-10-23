"""Validate native evidence once for every adapter; malformed evidence never becomes decisive."""
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
    result: Literal["PASS", "FAIL", "ERROR"]
    invariant_held: bool | None
    exception_type: str | None
    message: str | None


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


def read_junit(data: bytes | None, role: str) -> tuple[int, str | None, str | None]:
    """Exactly one named, non-skipped native test, with its failure/error kind and detail."""
    if not data:
        return 0, None, None
    root = ET.fromstring(data)
    if root.tag not in ("testsuites", "testsuite"):
        raise ValueError("invalid native report root")
    cases = list(root.iter("testcase"))
    if not cases:
        return 0, None, "the native test never ran (collection or import error)"
    if len(cases) != 1:
        raise ValueError(f"expected one native test, found {len(cases)}")
    case = cases[0]
    if case.get("name") != f"test_probe[{role}]":
        raise ValueError("native test identity does not match the requested payload")
    if case.find("skipped") is not None:
        raise ValueError("native test was skipped")
    problems = [node for node in case if node.tag in ("failure", "error")]
    if len(problems) > 1:
        raise ValueError("native test contains multiple failures or errors")
    if problems:
        node = problems[0]
        return 1, node.tag, f"{node.tag}: {(node.get('message') or node.text or '')[:500]}"
    return 1, None, None


def read_probe(files: Mapping[str, bytes | None], hypothesis, role: str, *,
               native_error_kind: Literal["failure", "error"] = "failure") -> ProbeResult:
    from ..kernel import RoleResult, role_result

    covered_target, covered_lines = read_coverage(files.get(f"{RESULT_DIR}/coverage.json"), hypothesis)
    count = 0
    invariant_held = None
    exception_type = message = None
    try:
        data = files.get(f"{RESULT_DIR}/result.json")
        if not data:
            return ProbeResult(RoleResult.NOT_RUN, None, None, "the driver never ran (collection or import error)",
                               0, covered_target, covered_lines)
        record = DriverRecord.model_validate_json(data)
        if record.role != role:
            raise ValueError("driver role does not match the requested payload")
        result = RoleResult(record.result)
        if result in (RoleResult.PASS, RoleResult.FAIL):
            if record.invariant_held is None:
                raise ValueError("a clean driver record requires a Boolean invariant")
            if record.exception_type is not None:
                raise ValueError("a clean driver record contains an exception")
            if result is not role_result(role, record.invariant_held):
                raise ValueError("driver result disagrees with the role's Boolean expectation")
        elif record.invariant_held is not None or not record.exception_type:
            raise ValueError("an error record requires an exception and no Boolean invariant")
        count, native_kind, native_message = read_junit(files.get(f"{RESULT_DIR}/junit.xml"), role)
        if count == 0:
            result, message = RoleResult.NOT_RUN, native_message or "the native report is missing"
        else:
            if (result is RoleResult.PASS) != (native_kind is None):
                raise ValueError(f"native report disagrees with the driver record: {native_message}")
            if result is RoleResult.FAIL and native_kind != "failure":
                raise ValueError("native error disagrees with a clean driver failure")
            # pytest/node:test use <failure> for call exceptions; Java/Perl emit <error>.
            if result is RoleResult.ERROR and native_kind != native_error_kind:
                raise ValueError("native exception kind disagrees with the driver error")
            invariant_held = record.invariant_held
            exception_type, message = record.exception_type, record.message
    except ValidationError as error:
        result = RoleResult.ERROR
        message = f"invalid probe evidence: {error.errors(include_input=False, include_url=False)}"
    except (ValueError, ET.ParseError) as error:
        result, message = RoleResult.ERROR, f"invalid probe evidence: {error}"
    return ProbeResult(result, invariant_held, exception_type, message[:2000] if message else None,
                       count, covered_target, covered_lines)
