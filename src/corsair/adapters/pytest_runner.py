"""Native pytest runner: fresh workspace, exact discovery, one execution, claims from pytest's JUnit."""
from dataclasses import dataclass
from uuid import UUID, uuid5

from corsair.adapters.native_runner import NativeRunner, check_bounds, check_command, check_root
from corsair.nodes.witness import PROBE_SHA256, probe_argv
from corsair.ports.test_runner import (MAX_TEST_ID, TEST_ID, ApprovedPatch, PreparedWorkspace, WitnessCapture,
                                       WitnessRequest)
from corsair.reports.junit import MAX_JUNIT_BYTES, JUnitError, parse_junit

# Fixed operator script run by absolute /bin/sh (sandbox exec promises no PATH lookup): stdout is exactly
# the JUnit file, exit status is pytest's.
# Paths and test ids arrive only as positional arguments, never inside the script text.
WRAPPER = ('junit="$1"; shift; rm -f -- "$junit"; '
           '"$@" --junitxml "$junit" -o junit_logging=all -o junit_log_passing_tests=true >/dev/null 2>&1; '
           'status=$?; cat -- "$junit" 2>/dev/null; exit $status')
# Native tracebacks give parseable `File "...", line N, in function` frames for failure classification.
RUN_OPTIONS = ('--tb=native',)


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
        check_command(self.command)
        if type(self.junit_path) is not str or not self.junit_path or '\0' in self.junit_path or self.junit_path[0] == '-':
            raise ValueError('JUnit path must be a plain operator path')
        check_root(self.workspace_root)
        check_bounds(self.max_junit_bytes, self.max_excerpt_chars, MAX_JUNIT_BYTES)
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
    tool, report_format = 'pytest', 'JUnit'

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
        discovery, stopped = self._discover(prepared.handle, discovery_command + tuple(paths), ids, operation, collected)
        if stopped:
            return stopped
        nonce = str(uuid5(operation, 'witness-nonce')) if witness is not None else None
        execution, layer = self._run_once(prepared, ids, frozenset(paths), uuid5(operation, 'execution'), witness, nonce)
        captured = None
        if witness is not None:
            captured = (self._read_witness(prepared, witness, nonce, uuid5(operation, 'witness'),
                                           self._config.witness_record_path, PROBE_SHA256)
                        if execution.status == 'completed' else
                        WitnessCapture('unavailable', witness, nonce, PROBE_SHA256, b'', None,
                                       f'execution {execution.status}; record not read', None))
        return discovery, execution, layer, execution.detail, captured

    def _run_once(self, prepared: PreparedWorkspace, ids: tuple[str, str], test_paths: frozenset[str], operation: UUID,
                  witness: WitnessRequest | None = None, nonce: str | None = None):
        command = self._config.command
        if witness is not None:
            command = probe_argv(command, witness, root=self._config.workspace_root,
                                 record_path=self._config.witness_record_path, nonce=nonce)
        argv = ('/bin/sh', '-c', WRAPPER, 'corsair-pytest', self._config.junit_path, *command, *RUN_OPTIONS, *ids)
        receipt, problem = self._execute(prepared.handle, argv, operation)
        failure = lambda *args: self._failure(argv, receipt, *args)
        if problem:
            return failure('execution', f'execution: {problem}')
        junit, stored = self._store_report(receipt.stdout)
        if stored:
            # The command completed; only retention of its JUnit bytes failed.
            return failure('report', f'junit storage: {stored}')
        if receipt.native_exit not in (0, 1):
            return failure('execution', f'execution: pytest exit {receipt.native_exit}', junit)
        try:
            cases = parse_junit(receipt.stdout, ids, root=self._config.workspace_root, test_paths=test_paths,
                                max_bytes=self._config.max_junit_bytes)
        except JUnitError as error:
            return failure('report', f'report: {error}', junit, 'invalid_report')
        return self._completed(prepared, argv, receipt, cases, junit, operation)
