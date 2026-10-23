"""Immutable hypotheses, submissions, evidence and verdicts; no infrastructure dependencies."""

from __future__ import annotations

import hashlib
import json
from enum import StrEnum
from typing import Literal

from pydantic import Field, field_validator

from corsair.domain.artifacts import ArtifactRef
from corsair.domain.case import Frozen, SafePath

TAIL = 4000

Role = Literal["control", "exploit"]
RevisionName = Literal["vulnerable", "fixed"]


class Hypothesis(Frozen):
    target_file: SafePath = Field(
        description="Path of the vulnerable source file, relative to the repository root"
    )
    target_symbol: str = Field(
        min_length=1, max_length=256, description="Function or method holding the flaw"
    )
    target_lines: tuple[int, ...] = Field(
        min_length=1, max_length=64, description="Lines that both payloads must execute"
    )
    root_cause: str = Field(
        min_length=1, max_length=2_000, description="The mechanism of the bug, one or two sentences"
    )
    expected_violation: str = Field(
        min_length=1,
        max_length=1_000,
        description="What the invariant assertion observes when EXPLOIT_PAYLOAD runs",
    )

    @field_validator("target_lines")
    @classmethod
    def _positive(cls, lines: tuple[int, ...]) -> tuple[int, ...]:
        if any(line < 1 for line in lines):
            raise ValueError("target lines are 1-based")
        return tuple(sorted(set(lines)))


class Submission(Frozen):
    hypothesis: Hypothesis
    build_script: str = Field(
        default="",
        max_length=16_000,
        description="bash run once in a clean container with network, from the repository "
        "root; empty when the project needs nothing installed",
    )
    probe: str = Field(
        min_length=1,
        max_length=32_000,
        description="One Python module defining CONTROL_PAYLOAD, EXPLOIT_PAYLOAD and "
        "run_target(payload) -> None, whose invariant assertion fails only when the "
        "reported condition occurs",
    )

    @property
    def sha256(self) -> str:
        return hashlib.sha256(json.dumps(self.model_dump(mode="json"), sort_keys=True).encode()).hexdigest()


class Gate(StrEnum):
    TARGET_BINDING = "target_binding"
    AST_GUARD = "ast_guard"
    BUILD_REPLAY = "build_replay"
    CONTROL_RUN = "control_run"
    CONTROL_COVERAGE = "control_coverage"
    EXPLOIT_RUN = "exploit_run"
    EXPLOIT_COVERAGE = "exploit_coverage"
    BLIND_AUDIT = "blind_audit"
    FIX_RUN = "fix_run"
    INFRA = "infra"
    VERIFIED = "verified"


class GateVerdict(Frozen):
    passed: bool
    stage: Gate
    reason: str = Field(max_length=4_000)
    stdout_tail: str = Field(default="", max_length=TAIL)
    stderr_tail: str = Field(default="", max_length=TAIL)


class Outcome(StrEnum):
    HOLDS = "holds"  # run_target returned: the invariant held
    VIOLATED = "violated"  # the probe's own assertion failed: the reported condition occurred
    ERRORED = "errored"  # another exception, or an assertion raised by application code
    NOT_RUN = "not_run"  # the test never ran (import or collection error, no test found)
    INFRA = "infra"  # timeout, container failure or unreadable results


class ProbeRun(Frozen):
    revision: RevisionName
    role: Role
    outcome: Outcome
    exception_type: str | None = None
    message: str | None = Field(default=None, max_length=2_000)
    exit_code: int | None
    junit_tests: int = Field(ge=0, description="Test cases the native JUnit report lists")
    covered_target: bool | None = Field(
        default=None, description="The target file executed at all; None unknown"
    )
    covered_lines: tuple[int, ...] = Field(default=(), description="Hypothesis lines the run executed")
    duration_s: float | None = None
    output: ArtifactRef | None = None
    junit: ArtifactRef | None = None
    reports: dict[str, ArtifactRef] = Field(default_factory=dict)
    cleanup_confirmed: bool | None = None


class AuditResult(Frozen):
    valid: bool
    reason: str = Field(max_length=2_000)


class Label(StrEnum):
    LIKELY_EXPLOITABLE = "LIKELY_EXPLOITABLE"
    LIKELY_NOT_EXPLOITABLE = "LIKELY_NOT_EXPLOITABLE"
    INCONCLUSIVE = "INCONCLUSIVE"
    UNABLE_TO_RUN = "UNABLE_TO_RUN"
    ERROR = "ERROR"


class Fix(StrEnum):
    VERIFIED = "verified"
    NOT_VERIFIED = "not_verified"
    NOT_APPLICABLE = "not_applicable"


class Verdict(Frozen):
    label: Label
    rule: str
    reason: str = Field(max_length=2_000)
    fix: Fix
    fix_reason: str = Field(default="", max_length=2_000)
    submission_sha256: str | None = None
    environment_image: str | None = None
    runs: tuple[ProbeRun, ...] = ()
    audit: AuditResult | None = None


class Evaluation(Frozen):
    """What one submission produced: the first failed gate, or ``verified`` with a verdict.

    One gate can fail while a verdict exists: ``fix_run``. The vulnerable-revision gates passed, so the label stands,
    but the exploit payload raised something other than the probe's assertion on the fixed revision, so the fix could
    not be verified and the producer may correct the probe within its budget.
    """

    submission: Submission
    submission_sha256: str
    gate: GateVerdict
    verdict: Verdict | None = None
    runs: tuple[ProbeRun, ...] = ()
    duration_s: float
    audit: AuditResult | None = None
    clean_negative: bool = Field(
        default=False,
        description="Control and exploit both held on the vulnerable revision "
        "with the target lines executed, and the audit (if any) "
        "accepted: counts toward K4",
    )
