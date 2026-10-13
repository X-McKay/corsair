"""Vendor-free native test runner boundary; commands and limits are operator-owned.

The runner places an approved test patch next to captured baseline source in a
fresh workspace, runs native discovery, then executes once and reports native
JUnit results. JUnit and discovery output remain workload claims: they classify
observations, they never attest test semantics or a security disposition.
"""
from dataclasses import dataclass
import hashlib
import re
from pathlib import PurePosixPath
from typing import Literal, Protocol
from uuid import UUID

from corsair.ports.artifacts import ArtifactRef
from corsair.ports.execution import ExecutionReceipt
from corsair.ports.sandbox import SandboxHandle
from corsair.reports.test_observations import AdmittedTestClaims

MAX_PATCH_FILES = 4
MAX_PATCH_FILE_BYTES = 32768
MAX_TEST_ID = 128
TEST_ID = re.compile(r'^[A-Za-z0-9_./-]+\.py(::[A-Za-z_][A-Za-z0-9_]*){1,2}$')


def approved_path(value: str) -> str:
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or '..' in path.parts or '\\' in value or str(path) != value
            or any(ord(char) < 32 for char in value) or not re.fullmatch(r'[A-Za-z0-9_./-]+', value)):
        raise ValueError('Expected a canonical confined relative test path')
    return value


@dataclass(frozen=True)
class PatchFile:
    path: str
    content: bytes

    def __post_init__(self):
        approved_path(self.path)
        if type(self.content) is not bytes or len(self.content) > MAX_PATCH_FILE_BYTES:
            raise ValueError('Patch file content must be bounded bytes')


@dataclass(frozen=True)
class ApprovedPatch:
    """Test files only, each inside the operator's approved set; never application source."""
    files: tuple[PatchFile, ...]
    approved_paths: tuple[str, ...]

    def __post_init__(self):
        for path in self.approved_paths:
            approved_path(path)
        paths = [item.path for item in self.files]
        if not 1 <= len(paths) <= MAX_PATCH_FILES or len(set(paths)) != len(paths):
            raise ValueError('Patch needs one to four distinct files')
        if not set(paths) <= set(self.approved_paths):
            raise ValueError('Patch path outside the approved test paths')

    @property
    def sha256(self) -> str:
        """Order-independent digest over path and content; the same patch on every revision."""
        digest = hashlib.sha256()
        for item in sorted(self.files, key=lambda f: f.path):
            digest.update(item.path.encode() + b'\0' + str(len(item.content)).encode() + b'\0' + item.content)
        return digest.hexdigest()


@dataclass(frozen=True)
class PreparedWorkspace:
    """A fresh sandbox holding the captured baseline source plus exactly this patch."""
    handle: SandboxHandle
    source: ArtifactRef
    tests: ArtifactRef
    patch_sha256: str


class TestWorkspace(Protocol):
    """Fresh source copy plus approved test delivery; the gating node for live use."""
    __test__ = False

    def prepare(self, patch: ApprovedPatch, operation: UUID) -> PreparedWorkspace: ...
    def release(self, workspace: PreparedWorkspace, operation: UUID) -> Literal['confirmed', 'unconfirmed']: ...


@dataclass(frozen=True)
class FailureDetail:
    """Bounded native failure classification input; not semantic attestation."""
    kind: Literal['failure', 'error']
    type: str | None
    path: str | None
    function: str | None
    line: int | None
    message: str


@dataclass(frozen=True)
class TestCaseResult:
    __test__ = False
    test_id: str
    outcome: Literal['passed', 'failed', 'error', 'skipped']
    failure: FailureDetail | None
    captured_output: str


@dataclass(frozen=True)
class Discovery:
    status: Literal['discovered', 'collection_error', 'execution_failure']
    test_ids: tuple[str, ...]
    errors: str
    command: tuple[str, ...]
    receipt: ExecutionReceipt | None


@dataclass(frozen=True)
class Execution:
    status: Literal['completed', 'execution_failure', 'invalid_report']
    cases: tuple[TestCaseResult, ...]
    junit: ArtifactRef | None
    claims: AdmittedTestClaims | None
    detail: str
    command: tuple[str, ...]
    receipt: ExecutionReceipt | None


@dataclass(frozen=True)
class WitnessRequest:
    """Operator-derived from the admitted identification target; never model text or test output."""
    target_path: str
    target_symbol: str

    def __post_init__(self):
        approved_path(self.target_path)
        if (type(self.target_symbol) is not str
                or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*', self.target_symbol)
                or len(self.target_symbol) > 256):
            raise ValueError('Witness target needs a plain qualified symbol')


@dataclass(frozen=True)
class WitnessCapture:
    """The operator probe's record, read back by a separate fixed command after execution."""
    status: Literal['captured', 'unavailable']
    request: WitnessRequest
    nonce: str
    probe_sha256: str
    record: bytes
    artifact: ArtifactRef | None
    detail: str
    receipt: ExecutionReceipt | None


@dataclass(frozen=True)
class NativeTestRun:
    """One fresh workspace: discovery, then execution only if exactly the expected tests were found."""
    operation: str
    patch_sha256: str
    workspace: PreparedWorkspace | None
    discovery: Discovery | None
    execution: Execution | None
    cleanup: Literal['not_required', 'confirmed', 'unconfirmed']
    failure_layer: Literal['workspace', 'discovery', 'execution', 'report'] | None
    detail: str
    witness: WitnessCapture | None = None


class TestRunner(Protocol):
    __test__ = False

    def run(self, patch: ApprovedPatch, *, control_test_id: str, security_test_id: str,
            discovery_command: tuple[str, ...], operation: UUID,
            witness: WitnessRequest | None = None) -> NativeTestRun: ...
