"""Native pytest runner: fresh workspace, exact discovery, one execution, claims from pytest's JUnit."""
from dataclasses import dataclass
from uuid import UUID, uuid5

from corsair.adapters.native_runner import NativeRunner, error_text
from corsair.nodes.witness import MAX_RECORD_BYTES, PROBE_SHA256, probe_argv
from corsair.ports.test_runner import (MAX_TEST_ID, TEST_ID, ApprovedPatch, Discovery, Execution, PreparedWorkspace,
                                       WitnessCapture, WitnessRequest)
from corsair.reports.junit import MAX_JUNIT_BYTES, JUnitError, parse_junit
from corsair.reports.test_observations import AdmittedTestClaims, TestClaim, WorkloadTestReport

# Fixed operator script run by absolute /bin/sh (sandbox exec promises no PATH lookup): stdout is exactly
# the JUnit file, exit status is pytest's.
# Paths and test ids arrive only as positional arguments, never inside the script text.
WRAPPER = ('junit="$1"; shift; rm -f -- "$junit"; '
           '"$@" --junitxml "$junit" -o junit_logging=all -o junit_log_passing_tests=true >/dev/null 2>&1; '
           'status=$?; cat -- "$junit" 2>/dev/null; exit $status')
# Native tracebacks give parseable `File "...", line N, in function` frames for failure classification.
RUN_OPTIONS = ('--tb=native',)
CLAIM = {'passed': 'passed', 'failed': 'failed', 'error': 'failed', 'skipped': 'skipped'}
# Fixed read-back of the probe record after execution; the path arrives only as a positional argument.
WITNESS_READ = 'cat -- "$1"'


@dataclass(frozen=True)
class PytestRunnerConfig:
    """Operator-owned argv prefix (interpreter, plugin isolation, rootdir), workspace root and bounds; never agent input."""
    command: tuple[str, ...]
    junit_path: str
    workspace_root: str
    max_junit_bytes: int = MAX_JUNIT_BYTES
    max_excerpt_chars: int = 4096
    witness_record_path: str | None = None

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
        record = self.witness_record_path
        if record is not None and (type(record) is not str or not record or '\0' in record or record[0] == '-'
                                   or record == self.junit_path):
            raise ValueError('Witness record path must be a plain operator path distinct from the JUnit path')


def collected(stdout: bytes) -> tuple[str, ...] | None:
    """`--collect-only -q` lists node ids up to the first blank line; any other line is not exact discovery."""
    try:
        lines = stdout.decode('utf-8').splitlines()
    except UnicodeError:
        return None
    block = lines[:lines.index('')] if '' in lines else lines
    return tuple(block) if all(TEST_ID.fullmatch(line) for line in block) else None


class PytestRunner(NativeRunner):
    def _validate(self, patch: ApprovedPatch, ids: tuple[str, str], witness: WitnessRequest | None) -> None:
        if witness is not None and (not isinstance(witness, WitnessRequest) or self._config.witness_record_path is None):
            raise ValueError('Witness capture needs a typed request and an operator record path')
        paths = {item.path for item in patch.files}
        if (any(type(i) is not str or not TEST_ID.fullmatch(i) or len(i) > MAX_TEST_ID or i[0] == '-'
                or i.split('::')[0] not in paths for i in ids) or len(set(ids)) != 2):
            raise ValueError('Two distinct plain node ids inside the patch are required')
        if (any(path[0] == '-' for path in paths) or self._config.junit_path in paths
                or self._config.witness_record_path in paths):
            raise ValueError('Patch paths conflict with runner arguments')

    def _stages(self, prepared, ids, discovery_command, paths, operation, witness):
        handle = prepared.handle
        command = discovery_command + tuple(paths)
        receipt, problem = self._execute(handle, command, uuid5(operation, 'discovery'))
        if problem:
            discovery = Discovery('execution_failure', (), self._excerpt(receipt), command, receipt)
            return discovery, None, 'discovery', f'discovery: {problem}', None
        found = collected(receipt.stdout)
        if receipt.native_exit != 0 or found is None or len(found) != len(set(found)) or set(found) != set(ids):
            discovery = Discovery('collection_error', found or (), self._excerpt(receipt), command, receipt)
            return (discovery, None, 'discovery', f'discovery: exit {receipt.native_exit}, found {list(found or ())}',
                    None)
        discovery = Discovery('discovered', found, '', command, receipt)
        nonce = str(uuid5(operation, 'witness-nonce')) if witness is not None else None
        execution, layer = self._run_once(prepared, ids, frozenset(paths), uuid5(operation, 'execution'), witness, nonce)
        captured = None
        if witness is not None:
            captured = (self._read_witness(prepared, witness, nonce, uuid5(operation, 'witness'))
                        if execution.status == 'completed' else
                        WitnessCapture('unavailable', witness, nonce, PROBE_SHA256, b'', None,
                                       f'execution {execution.status}; record not read', None))
        return discovery, execution, layer, execution.detail, captured

    def _read_witness(self, prepared: PreparedWorkspace, request: WitnessRequest, nonce: str,
                      operation: UUID) -> WitnessCapture:
        """One fixed read of the probe record; never retried, and a missing or oversized record is unavailable."""
        argv = ('/bin/sh', '-c', WITNESS_READ, 'corsair-witness', self._config.witness_record_path)
        unavailable = lambda detail, receipt=None: WitnessCapture('unavailable', request, nonce, PROBE_SHA256, b'',
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
        return WitnessCapture('captured', request, nonce, PROBE_SHA256, receipt.stdout, artifact, '', receipt)

    def _run_once(self, prepared: PreparedWorkspace, ids: tuple[str, str], test_paths: frozenset[str], operation: UUID,
                  witness: WitnessRequest | None = None, nonce: str | None = None):
        command = self._config.command
        if witness is not None:
            command = probe_argv(command, witness, root=self._config.workspace_root,
                                 record_path=self._config.witness_record_path, nonce=nonce)
        argv = ('/bin/sh', '-c', WRAPPER, 'corsair-pytest', self._config.junit_path, *command, *RUN_OPTIONS, *ids)
        receipt, problem = self._execute(prepared.handle, argv, operation)
        failure = lambda layer, detail, junit=None, status='execution_failure': (
            Execution(status, (), junit, None, detail, argv, receipt), layer)
        if problem:
            return failure('execution', f'execution: {problem}')
        try:
            junit = self._store.put(receipt.stdout)
        except Exception as error:
            # The command completed; only retention of its JUnit bytes failed.
            return failure('report', f'junit storage: {error_text(error)}')
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
