"""Admit bounded workload claims; execution integrity is not test semantics."""

from dataclasses import dataclass
import hashlib
import json
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from corsair.ports.artifacts import ArtifactRef, ArtifactStore
from corsair.ports.execution import ExecutionReceipt
from corsair.ports.sandbox import SandboxHandle

MAX_REPORT_BYTES = 4096


class TestClaim(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    test_id: str = Field(min_length=1, max_length=128, pattern=r'^[A-Za-z0-9_./:#-]+$')
    outcome: Literal['passed', 'failed', 'skipped']


class WorkloadTestReport(BaseModel):
    model_config = ConfigDict(extra='forbid', frozen=True, strict=True)
    schema_version: Literal['test-observations-v1']
    operation: str = Field(pattern=r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')
    source_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    tests_sha256: str = Field(pattern=r'^[0-9a-f]{64}$')
    control: TestClaim
    security: TestClaim

    @model_validator(mode='after')
    def distinct_tests(self):
        if self.control.test_id == self.security.test_id:
            raise ValueError('Control and security claims must identify distinct tests')
        return self


@dataclass(frozen=True)
class AdmittedTestClaims:
    """Host binding plus untrusted claims; intentionally no security disposition."""
    operation: str
    handle: SandboxHandle
    source: ArtifactRef
    tests: ArtifactRef
    report: ArtifactRef
    native_exit: int
    claims: WorkloadTestReport


def _unique_keys(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate JSON object key')
        result[key] = value
    return result


def consume_test_report(store: ArtifactStore, reference: ArtifactRef, *,
                        receipt: ExecutionReceipt, operation: UUID,
                        handle: SandboxHandle, source: ArtifactRef,
                        tests: ArtifactRef) -> AdmittedTestClaims:
    """Only operator-selected stdout bytes; never follows workload references."""
    if (not isinstance(operation, UUID) or receipt.operation != str(operation)
            or receipt.handle != handle):
        raise ValueError('Execution identity does not match operator selection')
    if (receipt.delivery != 'acknowledged' or receipt.completion != 'terminal_observed'
            or receipt.worker_cleanup != 'confirmed' or receipt.storage_error is not None
            or receipt.failure_layer is not None or receipt.reason != 'terminal'
            or type(receipt.native_exit) is not int or receipt.native_exit not in (0, 1)):
        raise ValueError('Complete retained native execution is required')
    if not isinstance(reference, ArtifactRef) or not 1 <= reference.size <= MAX_REPORT_BYTES:
        raise ValueError('Report exceeds admitted byte envelope')
    data = store.get(reference)
    if (type(data) is not bytes or len(data) != reference.size
            or hashlib.sha256(data).hexdigest() != reference.sha256 or data != receipt.stdout):
        raise ValueError('Report artifact does not match exact observed stdout')
    # Native Pydantic JSON parsing permits duplicate keys; reject ambiguity first.
    try:
        json.loads(data.decode('utf-8'), object_pairs_hook=_unique_keys)
    except (UnicodeError, RecursionError) as error:
        raise ValueError('Invalid bounded UTF8 JSON report') from error
    claims = WorkloadTestReport.model_validate_json(data)
    if (claims.operation != str(operation) or claims.source_sha256 != source.sha256
            or claims.tests_sha256 != tests.sha256):
        raise ValueError('Workload claims do not match operator input identities')
    outcomes = (claims.control.outcome, claims.security.outcome)
    if 'skipped' not in outcomes and receipt.native_exit != int('failed' in outcomes):
        raise ValueError('Native exit conflicts with reported test outcomes')
    return AdmittedTestClaims(str(operation), handle, source, tests, reference,
                              receipt.native_exit, claims)
