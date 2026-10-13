"""Shared native test runner orchestration: one fresh workspace, framework stages, release always runs.

Every framework (pytest, Maven Surefire, Perl TAP, ...) is a small adapter over this base. The adapter
supplies its id grammar (`_validate`), its listing command and reader, its run command and its report
reader; the base owns the workspace lifecycle, receipt completeness, the exact-listing check, report
storage, exit agreement, claims and the absent-witness answer, and never retries a command.
"""
from typing import Callable, Literal
from uuid import UUID, uuid5

from corsair.ports.artifacts import ArtifactRef, ArtifactStore
from corsair.ports.execution import ExecutionReceipt, SandboxExecution
from corsair.ports.sandbox import SandboxHandle
from corsair.nodes.witness import MAX_RECORD_BYTES
from corsair.ports.test_runner import (MAX_TEST_ID, ApprovedPatch, Discovery, Execution, NativeTestRun,
                                       PreparedWorkspace, TestCaseResult, TestWorkspace, WitnessCapture, WitnessRequest)
from corsair.reports.admission import failed_count
from corsair.reports.test_observations import AdmittedTestClaims, TestClaim, WorkloadTestReport

# Fixed read-back of a probe record after execution; the path arrives only as a positional argument.
WITNESS_READ = 'cat -- "$1"'
# Framework outcome to workload claim: an error (the test could not complete) is a failed claim.
CLAIM = {'passed': 'passed', 'failed': 'failed', 'error': 'failed', 'skipped': 'skipped'}


def error_text(error: BaseException) -> str:
    return f'{type(error).__name__}: {error}'[:2048]


def incomplete(receipt: ExecutionReceipt, operation: UUID, handle: SandboxHandle) -> str | None:
    if receipt.operation != str(operation) or receipt.handle != handle:
        return 'receipt identity does not match the requested execution'
    if (receipt.delivery != 'acknowledged' or receipt.completion != 'terminal_observed' or receipt.reason != 'terminal'
            or receipt.failure_layer is not None or receipt.storage_error is not None
            or receipt.worker_cleanup != 'confirmed' or type(receipt.native_exit) is not int):
        return (f'incomplete execution: delivery={receipt.delivery} completion={receipt.completion} '
                f'reason={receipt.reason} layer={receipt.failure_layer} cleanup={receipt.worker_cleanup}')
    return None


def check_command(command: tuple[str, ...], minimum: int = 1,
                  message: str = 'Runner command must be nonempty string tokens') -> None:
    if (type(command) is not tuple or len(command) < minimum
            or any(type(t) is not str or not t or '\0' in t for t in command)):
        raise ValueError(message)


def check_root(workspace_root: str) -> None:
    if type(workspace_root) is not str or not workspace_root.startswith('/') or '\0' in workspace_root:
        raise ValueError('Workspace root must be an absolute operator path')


def check_bounds(max_report_bytes: int, max_excerpt_chars: int, report_limit: int) -> None:
    if not (type(max_report_bytes) is int and 1 <= max_report_bytes <= report_limit
            and type(max_excerpt_chars) is int and 1 <= max_excerpt_chars <= 65536):
        raise ValueError('Runner bounds outside the admitted range')


def check_ids(patch: ApprovedPatch, ids: tuple[str, str], witness: WitnessRequest | None, parse, grammar: str, *,
              unit, together: str, file=lambda item: item.path) -> list:
    """The id rule every listed-discovery framework shares, checked before any workspace exists: a typed witness
    request, two distinct ids in the framework's grammar, each naming a file the patch itself carries, both in
    one report unit (file or class) so exactly one report is admitted, and no patch path that reads as an option.
    Returns the parsed ids."""
    if witness is not None and not isinstance(witness, WitnessRequest):
        raise ValueError('Witness capture needs a typed request')
    try:
        parsed = [parse(i) for i in ids]
    except ValueError as error:
        raise ValueError(f'Two distinct {grammar} ids are required') from error
    paths = {item.path for item in patch.files}
    if len(set(ids)) != 2 or any(len(i) > MAX_TEST_ID or file(item) not in paths for i, item in zip(ids, parsed)):
        raise ValueError('Two distinct test ids declared in patch files are required')
    if len({unit(item) for item in parsed}) != 1:
        raise ValueError(together)
    if any(path[0] == '-' for path in paths):
        raise ValueError('Patch paths conflict with runner arguments')
    return parsed


class NativeRunner:
    """Subclasses implement `_validate` (refuse before any workspace exists) and `_stages`.

    `tool` and `report_format` name the framework in the exit-agreement refusal.
    """
    tool, report_format = 'runner', 'report'

    def __init__(self, workspace: TestWorkspace, execution: SandboxExecution, store: ArtifactStore, config):
        self._workspace, self._execution, self._store, self._config = workspace, execution, store, config

    def _validate(self, patch: ApprovedPatch, ids: tuple[str, str], witness: WitnessRequest | None) -> None:
        raise NotImplementedError

    def _stages(self, prepared, ids, discovery_command, paths, operation, witness):
        raise NotImplementedError

    def run(self, patch: ApprovedPatch, *, control_test_id: str, security_test_id: str,
            discovery_command: tuple[str, ...], operation: UUID,
            witness: WitnessRequest | None = None) -> NativeTestRun:
        if not isinstance(operation, UUID) or not isinstance(patch, ApprovedPatch):
            raise ValueError('Operator operation and approved patch required')
        ids = (control_test_id, security_test_id)
        self._validate(patch, ids, witness)
        if type(discovery_command) is not tuple or not discovery_command or any(type(t) is not str for t in discovery_command):
            raise ValueError('Discovery command must be string tokens')
        paths = {item.path for item in patch.files}
        base = dict(operation=str(operation), patch_sha256=patch.sha256)
        try:
            prepared = self._workspace.prepare(patch, operation)
        except Exception as error:
            # Preparation may have created a sandbox before failing: never infer absence.
            return NativeTestRun(**base, workspace=None, discovery=None, execution=None, cleanup='unconfirmed',
                                 failure_layer='workspace', detail=f'prepare: {error_text(error)}')
        cleanup: Literal['confirmed', 'unconfirmed'] = 'unconfirmed'
        released, captured = '', None
        try:
            if prepared.patch_sha256 != patch.sha256:
                discovery = execution = None
                layer, detail = 'workspace', 'prepared workspace does not hold this patch'
            else:
                discovery, execution, layer, detail, captured = self._stages(
                    prepared, ids, discovery_command, sorted(paths), operation, witness)
        finally:
            try:
                cleanup = 'confirmed' if self._workspace.release(prepared, operation) == 'confirmed' else 'unconfirmed'
            except Exception as error:
                released = f'; release: {error_text(error)}'
        return NativeTestRun(**base, workspace=prepared, discovery=discovery, execution=execution, cleanup=cleanup,
                             failure_layer=layer, detail=detail+released, witness=captured)

    def _execute(self, handle: SandboxHandle, argv: tuple[str, ...], operation: UUID) -> tuple[ExecutionReceipt | None, str | None]:
        try:
            receipt = self._execution.execute(handle, argv, operation)
        except Exception as error:
            # Never retried: delivery of the failed command may be unknown.
            return getattr(error, 'receipt', None), error_text(error)
        return receipt, incomplete(receipt, operation, handle)

    def _excerpt(self, receipt: ExecutionReceipt | None) -> str:
        if receipt is None:
            return ''
        limit = self._config.max_excerpt_chars
        return (f'exit={receipt.native_exit}\nstdout:\n{receipt.stdout[:limit*4].decode("utf-8", "replace")[:limit]}'
                f'\nstderr:\n{receipt.stderr[:limit*4].decode("utf-8", "replace")[:limit]}')

    def _discover(self, handle: SandboxHandle, command: tuple[str, ...], ids: tuple[str, str], operation: UUID,
                  read: Callable[[bytes], tuple[str, ...] | None]):
        """Run the listing once; the run continues only when it lists exactly the two ids. Returns
        (discovery, stage result to return on failure or None)."""
        receipt, problem = self._execute(handle, command, uuid5(operation, 'discovery'))
        if problem:
            discovery = Discovery('execution_failure', (), self._excerpt(receipt), command, receipt)
            return discovery, (discovery, None, 'discovery', f'discovery: {problem}', None)
        found = read(receipt.stdout)
        if receipt.native_exit != 0 or found is None or len(found) != len(set(found)) or set(found) != set(ids):
            discovery = Discovery('collection_error', found or (), self._excerpt(receipt), command, receipt)
            return discovery, (discovery, None, 'discovery',
                               f'discovery: exit {receipt.native_exit}, found {list(found or ())}', None)
        return Discovery('discovered', found, '', command, receipt), None

    def _store_report(self, data: bytes) -> tuple[ArtifactRef | None, str | None]:
        """Retain the report bytes before admitting them; only retention can fail here."""
        try:
            return self._store.put(data), None
        except Exception as error:
            return None, error_text(error)

    @staticmethod
    def _failure(argv, receipt, layer, detail, report=None, status='execution_failure'):
        return Execution(status, (), report, None, detail, argv, receipt), layer

    @staticmethod
    def _exit_agrees(native_exit: int, cases: tuple[TestCaseResult, ...]) -> bool:
        """Default rule: exit 1 exactly when a test failed or errored, else 0."""
        return native_exit == int(failed_count(cases) > 0)

    def _completed(self, prepared: PreparedWorkspace, argv: tuple[str, ...], receipt: ExecutionReceipt,
                   cases: tuple[TestCaseResult, ...], report: ArtifactRef, operation: UUID):
        """Admitted outcomes become the control and security claims of this workspace, but only when the
        native exit status agrees with them; every runner passes through here, so none can skip the check."""
        if not self._exit_agrees(receipt.native_exit, cases):
            return self._failure(argv, receipt, 'report', f'report: {self.tool} exit {receipt.native_exit} '
                                 f'conflicts with {self.report_format} outcomes', report, 'invalid_report')
        control, security = (TestClaim(test_id=case.test_id, outcome=CLAIM[case.outcome]) for case in cases)
        claims_report = WorkloadTestReport(schema_version='test-observations-v1', operation=str(operation),
                                           source_sha256=prepared.source.sha256, tests_sha256=prepared.tests.sha256,
                                           control=control, security=security)
        claims = AdmittedTestClaims(str(operation), prepared.handle, prepared.source, prepared.tests, report,
                                    receipt.native_exit, claims_report)
        return Execution('completed', cases, report, claims, '', argv, receipt), None

    def _read_witness(self, prepared: PreparedWorkspace, request: WitnessRequest, nonce: str, operation: UUID,
                      record_path: str, probe_sha256: str) -> WitnessCapture:
        """One fixed read of the probe record; never retried, and a missing or oversized record is unavailable."""
        argv = ('/bin/sh', '-c', WITNESS_READ, 'corsair-witness', record_path)
        unavailable = lambda detail, receipt=None: WitnessCapture('unavailable', request, nonce, probe_sha256, b'',
                                                                  None, detail[:2048], receipt)
        receipt, problem = self._execute(prepared.handle, argv, operation)
        if problem:
            return unavailable(f'read: {problem}', receipt)
        if receipt.native_exit != 0 or not receipt.stdout or len(receipt.stdout) > MAX_RECORD_BYTES:
            return unavailable(f'read: exit {receipt.native_exit}, {len(receipt.stdout)} bytes', receipt)
        try:
            artifact = self._store.put(receipt.stdout)
        except Exception as error:
            return unavailable(f'record storage: {error_text(error)}', receipt)
        return WitnessCapture('captured', request, nonce, probe_sha256, receipt.stdout, artifact, '', receipt)

    @staticmethod
    def _no_witness(witness: WitnessRequest | None, operation: UUID, detail: str) -> WitnessCapture | None:
        """A framework without an operator probe runs nothing for a witness, so the gates see it absent."""
        if witness is None:
            return None
        return WitnessCapture('unavailable', witness, str(uuid5(operation, 'witness-nonce')), '', b'', None, detail, None)
