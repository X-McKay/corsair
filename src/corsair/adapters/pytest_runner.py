"""Native pytest runner: fresh workspace, exact discovery, one execution, claims from pytest's JUnit."""
from dataclasses import dataclass
from typing import Literal
from uuid import UUID, uuid5

from corsair.ports.artifacts import ArtifactStore
from corsair.ports.execution import ExecutionReceipt, SandboxExecution
from corsair.ports.sandbox import SandboxHandle
from corsair.ports.test_runner import (MAX_TEST_ID, TEST_ID, ApprovedPatch, Discovery, Execution, NativeTestRun,
                                       PreparedWorkspace, TestWorkspace)
from corsair.reports.junit import MAX_JUNIT_BYTES, JUnitError, parse_junit
from corsair.reports.test_observations import AdmittedTestClaims, TestClaim, WorkloadTestReport

# Fixed operator script: stdout is exactly the JUnit file, exit status is pytest's.
# Paths and test ids arrive only as positional arguments, never inside the script text.
WRAPPER = ('junit="$1"; shift; rm -f -- "$junit"; '
           '"$@" --junitxml "$junit" -o junit_logging=all -o junit_log_passing_tests=true >/dev/null 2>&1; '
           'status=$?; cat -- "$junit" 2>/dev/null; exit $status')
# Native tracebacks give parseable `File "...", line N, in function` frames for failure classification.
RUN_OPTIONS = ('--tb=native',)
CLAIM = {'passed': 'passed', 'failed': 'failed', 'error': 'failed', 'skipped': 'skipped'}


@dataclass(frozen=True)
class PytestRunnerConfig:
    """Operator-owned argv prefix (interpreter, plugin isolation, rootdir), workspace root and bounds; never agent input."""
    command: tuple[str, ...]
    junit_path: str
    workspace_root: str
    max_junit_bytes: int = MAX_JUNIT_BYTES
    max_excerpt_chars: int = 4096

    def __post_init__(self):
        if (type(self.command) is not tuple or not self.command
                or any(type(t) is not str or not t or '\0' in t for t in self.command)):
            raise ValueError('Runner command must be nonempty string tokens')
        if type(self.junit_path) is not str or not self.junit_path or '\0' in self.junit_path or self.junit_path[0] == '-':
            raise ValueError('JUnit path must be a plain operator path')
        if type(self.workspace_root) is not str or not self.workspace_root.startswith('/') or '\0' in self.workspace_root:
            raise ValueError('Workspace root must be an absolute operator path')
        if not (type(self.max_junit_bytes) is int and 1 <= self.max_junit_bytes <= MAX_JUNIT_BYTES
                and type(self.max_excerpt_chars) is int and 1 <= self.max_excerpt_chars <= 65536):
            raise ValueError('Runner bounds outside the admitted range')


def _error(error: BaseException) -> str:
    return f'{type(error).__name__}: {error}'[:2048]


def _incomplete(receipt: ExecutionReceipt, operation: UUID, handle: SandboxHandle) -> str | None:
    if receipt.operation != str(operation) or receipt.handle != handle:
        return 'receipt identity does not match the requested execution'
    if (receipt.delivery != 'acknowledged' or receipt.completion != 'terminal_observed' or receipt.reason != 'terminal'
            or receipt.failure_layer is not None or receipt.storage_error is not None
            or receipt.worker_cleanup != 'confirmed' or type(receipt.native_exit) is not int):
        return (f'incomplete execution: delivery={receipt.delivery} completion={receipt.completion} '
                f'reason={receipt.reason} layer={receipt.failure_layer} cleanup={receipt.worker_cleanup}')
    return None


def collected(stdout: bytes) -> tuple[str, ...] | None:
    """`--collect-only -q` lists node ids up to the first blank line; any other line is not exact discovery."""
    try:
        lines = stdout.decode('utf-8').splitlines()
    except UnicodeError:
        return None
    block = lines[:lines.index('')] if '' in lines else lines
    return tuple(block) if all(TEST_ID.fullmatch(line) for line in block) else None


class PytestRunner:
    def __init__(self, workspace: TestWorkspace, execution: SandboxExecution, store: ArtifactStore,
                 config: PytestRunnerConfig):
        self._workspace, self._execution, self._store, self._config = workspace, execution, store, config

    def run(self, patch: ApprovedPatch, *, control_test_id: str, security_test_id: str,
            discovery_command: tuple[str, ...], operation: UUID) -> NativeTestRun:
        if not isinstance(operation, UUID) or not isinstance(patch, ApprovedPatch):
            raise ValueError('Operator operation and approved patch required')
        ids = (control_test_id, security_test_id)
        paths = {item.path for item in patch.files}
        if (any(type(i) is not str or not TEST_ID.fullmatch(i) or len(i) > MAX_TEST_ID or i[0] == '-'
                or i.split('::')[0] not in paths for i in ids) or len(set(ids)) != 2):
            raise ValueError('Two distinct plain node ids inside the patch are required')
        if any(path[0] == '-' for path in paths) or self._config.junit_path in paths:
            raise ValueError('Patch paths conflict with runner arguments')
        if type(discovery_command) is not tuple or not discovery_command or any(type(t) is not str for t in discovery_command):
            raise ValueError('Discovery command must be string tokens')
        base = dict(operation=str(operation), patch_sha256=patch.sha256)
        try:
            prepared = self._workspace.prepare(patch, operation)
        except Exception as error:
            # Preparation may have created a sandbox before failing: never infer absence.
            return NativeTestRun(**base, workspace=None, discovery=None, execution=None, cleanup='unconfirmed',
                                 failure_layer='workspace', detail=f'prepare: {_error(error)}')
        cleanup: Literal['confirmed', 'unconfirmed'] = 'unconfirmed'
        released = ''
        try:
            if prepared.patch_sha256 != patch.sha256:
                discovery = execution = None
                layer, detail = 'workspace', 'prepared workspace does not hold this patch'
            else:
                discovery, execution, layer, detail = self._stages(prepared, ids, discovery_command, sorted(paths), operation)
        finally:
            try:
                cleanup = 'confirmed' if self._workspace.release(prepared, operation) == 'confirmed' else 'unconfirmed'
            except Exception as error:
                released = f'; release: {_error(error)}'
        return NativeTestRun(**base, workspace=prepared, discovery=discovery, execution=execution, cleanup=cleanup,
                             failure_layer=layer, detail=detail+released)

    def _execute(self, handle: SandboxHandle, argv: tuple[str, ...], operation: UUID) -> tuple[ExecutionReceipt | None, str | None]:
        try:
            receipt = self._execution.execute(handle, argv, operation)
        except Exception as error:
            # Never retried: delivery of the failed command may be unknown.
            return getattr(error, 'receipt', None), _error(error)
        return receipt, _incomplete(receipt, operation, handle)

    def _excerpt(self, receipt: ExecutionReceipt | None) -> str:
        if receipt is None:
            return ''
        limit = self._config.max_excerpt_chars
        return (f'exit={receipt.native_exit}\nstdout:\n{receipt.stdout[:limit*4].decode("utf-8", "replace")[:limit]}'
                f'\nstderr:\n{receipt.stderr[:limit*4].decode("utf-8", "replace")[:limit]}')

    def _stages(self, prepared, ids, discovery_command, paths, operation):
        handle = prepared.handle
        command = discovery_command + tuple(paths)
        receipt, problem = self._execute(handle, command, uuid5(operation, 'discovery'))
        if problem:
            discovery = Discovery('execution_failure', (), self._excerpt(receipt), command, receipt)
            return discovery, None, 'discovery', f'discovery: {problem}'
        found = collected(receipt.stdout)
        if receipt.native_exit != 0 or found is None or len(found) != len(set(found)) or set(found) != set(ids):
            discovery = Discovery('collection_error', found or (), self._excerpt(receipt), command, receipt)
            return discovery, None, 'discovery', f'discovery: exit {receipt.native_exit}, found {list(found or ())}'
        discovery = Discovery('discovered', found, '', command, receipt)
        execution, layer = self._run_once(prepared, ids, frozenset(paths), uuid5(operation, 'execution'))
        return discovery, execution, layer, execution.detail

    def _run_once(self, prepared: PreparedWorkspace, ids: tuple[str, str], test_paths: frozenset[str], operation: UUID):
        argv = ('sh', '-c', WRAPPER, 'corsair-pytest', self._config.junit_path, *self._config.command, *RUN_OPTIONS, *ids)
        receipt, problem = self._execute(prepared.handle, argv, operation)
        failure = lambda layer, detail, junit=None, status='execution_failure': (
            Execution(status, (), junit, None, detail, argv, receipt), layer)
        if problem:
            return failure('execution', f'execution: {problem}')
        try:
            junit = self._store.put(receipt.stdout)
        except Exception as error:
            # The command completed; only retention of its JUnit bytes failed.
            return failure('report', f'junit storage: {_error(error)}')
        if receipt.native_exit not in (0, 1):
            return failure('execution', f'execution: pytest exit {receipt.native_exit}', junit)
        try:
            cases = parse_junit(receipt.stdout, ids, root=self._config.workspace_root, test_paths=test_paths,
                                max_bytes=self._config.max_junit_bytes)
        except JUnitError as error:
            return failure('report', f'report: {error}', junit, 'invalid_report')
        if receipt.native_exit != int(any(case.outcome in ('failed', 'error') for case in cases)):
            return failure('report', f'report: pytest exit {receipt.native_exit} conflicts with JUnit outcomes',
                           junit, 'invalid_report')
        control, security = (TestClaim(test_id=case.test_id, outcome=CLAIM[case.outcome]) for case in cases)
        report = WorkloadTestReport(schema_version='test-observations-v1', operation=str(operation),
                                    source_sha256=prepared.source.sha256, tests_sha256=prepared.tests.sha256,
                                    control=control, security=security)
        claims = AdmittedTestClaims(str(operation), prepared.handle, prepared.source, prepared.tests, junit,
                                    receipt.native_exit, report)
        return Execution('completed', cases, junit, claims, '', argv, receipt), None
