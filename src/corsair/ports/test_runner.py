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
# JUnit on Maven: `[module/]fully.qualified.Class#method`. The optional module is the reactor directory
# relative to the repository root; top-level classes and plain ASCII identifiers only (no nested `$` classes).
JAVA_TEST_ID = re.compile(r'^(?:(?P<module>[A-Za-z0-9_][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*)*)/)?'
                          r'(?P<class_name>(?:[A-Za-z_][A-Za-z0-9_]*\.)*[A-Za-z_][A-Za-z0-9_]*)'
                          r'#(?P<method>[A-Za-z_][A-Za-z0-9_]*)$')

# Jest: `path/to/file.test.js::[suite::]name` for a top-level test or one in a top-level `describe`. Segments are
# plain identifiers, so Jest's full name (ancestor titles and title joined by a space) maps back to one id.
JS_TEST_ID = re.compile(r'^(?P<path>[A-Za-z0-9_./-]+\.(?:js|jsx|mjs|cjs))'
                        r'::(?:(?P<suite>[A-Za-z_][A-Za-z0-9_]*)::)?(?P<name>[A-Za-z_][A-Za-z0-9_]*)$')
# TAP on Perl: `path/to/file.t#subtest`, a repository-relative test file and one of its top-level Test::More subtests.
PERL_TEST_ID = re.compile(r'^(?P<path>[A-Za-z0-9_][A-Za-z0-9_.-]*(?:/[A-Za-z0-9_][A-Za-z0-9_.-]*)*\.t)'
                          r'#(?P<name>[A-Za-z_][A-Za-z0-9_]*)$')


def approved_path(value: str) -> str:
    path = PurePosixPath(value)
    if (not value or path.is_absolute() or '..' in path.parts or '\\' in value or str(path) != value
            or any(ord(char) < 32 for char in value) or not re.fullmatch(r'[A-Za-z0-9_./-]+', value)):
        raise ValueError('Expected a canonical confined relative test path')
    return value


@dataclass(frozen=True)
class JavaTestId:
    """A JUnit method in a Maven module; Surefire reports it as (class_name, method)."""
    module: str | None
    class_name: str
    method: str

    @classmethod
    def parse(cls, value: str) -> 'JavaTestId':
        match = JAVA_TEST_ID.fullmatch(value) if type(value) is str and len(value) <= MAX_TEST_ID else None
        if match is None:
            raise ValueError('Expected `[module/]package.Class#method`')
        return cls(match['module'], match['class_name'], match['method'])

    def source_path(self, test_root: str = 'src/test/java') -> str:
        """Maven's conventional location of the declaring class, relative to the repository root."""
        relative = f'{test_root}/{self.class_name.replace(".", "/")}.java'
        return f'{self.module}/{relative}' if self.module else relative

    def __str__(self) -> str:
        return f'{self.module + "/" if self.module else ""}{self.class_name}#{self.method}'


@dataclass(frozen=True)
class JsTestId:
    """A Jest test in one repository file; Jest's JSON report names it by (ancestorTitles, title)."""
    path: str
    suite: str | None
    name: str

    @classmethod
    def parse(cls, value: str) -> 'JsTestId':
        match = JS_TEST_ID.fullmatch(value) if type(value) is str and len(value) <= MAX_TEST_ID else None
        if match is None:
            raise ValueError('Expected `path/file.test.js::[suite::]name` with identifier segments')
        return cls(approved_path(match['path']), match['suite'], match['name'])

    @property
    def titles(self) -> tuple[tuple[str, ...], str]:
        return ((self.suite,) if self.suite else (), self.name)

    @property
    def full_name(self) -> str:
        """What Jest's `--testNamePattern` matches: ancestor titles and the title joined by one space."""
        return f'{self.suite} {self.name}' if self.suite else self.name

    def __str__(self) -> str:
        return f'{self.path}::{self.suite + "::" if self.suite else ""}{self.name}'


@dataclass(frozen=True)
class PerlTestId:
    """A top-level Test::More subtest of one `.t` file; TAP names it on its `# Subtest:` line."""
    path: str
    name: str

    @classmethod
    def parse(cls, value: str) -> 'PerlTestId':
        match = PERL_TEST_ID.fullmatch(value) if type(value) is str and len(value) <= MAX_TEST_ID else None
        if match is None or '..' in match['path'].split('/'):
            raise ValueError('Expected `path/to/file.t#subtest`')
        return cls(match['path'], match['name'])

    def __str__(self) -> str:
        return f'{self.path}#{self.name}'


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
    """An operator-approved envelope: the probed target and the file name its planned effect opens.

    Admitted only when it equals the identification target; never model text or test output.
    """
    target_path: str
    target_symbol: str
    effect_name: str

    def __post_init__(self):
        approved_path(self.target_path)
        if (type(self.target_symbol) is not str
                or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*(\.[A-Za-z_][A-Za-z0-9_]*)*', self.target_symbol)
                or len(self.target_symbol) > 256):
            raise ValueError('Witness target needs a plain qualified symbol')
        if (type(self.effect_name) is not str or not re.fullmatch(r'[A-Za-z0-9_.-]{1,128}', self.effect_name)
                or self.effect_name in ('.', '..')):
            raise ValueError('Witness effect needs a plain file name')


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
