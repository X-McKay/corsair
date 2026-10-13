"""Native Jest runner: fresh workspace, listed discovery, one execution, claims from Jest's own JSON report.

The project's own Jest and configuration run unchanged. Discovery runs the test file with a name
pattern that matches nothing, so Jest loads the file and reports every test as skipped by name without
running a test body or hook (module top-level code still runs, as pytest collection imports); execution
then selects exactly the two tests by their anchored full names.
"""
from dataclasses import dataclass
from uuid import UUID, uuid5

from corsair.adapters.native_runner import NativeRunner, error_text
from corsair.ports.test_runner import (MAX_TEST_ID, ApprovedPatch, Discovery, Execution, JsTestId,
                                       PreparedWorkspace, WitnessCapture, WitnessRequest)
from corsair.reports.jest import MAX_JEST_BYTES, JestError, listed, parse_jest
from corsair.reports.test_observations import AdmittedTestClaims, TestClaim, WorkloadTestReport

# Fixed operator script run by absolute /bin/sh: Jest's console goes to stderr, stdout is exactly Jest's
# JSON report, exit status is Jest's. The report path and all Jest arguments arrive only as positional arguments.
WRAPPER = ('report="$1"; shift; rm -f -- "$report"; "$@" --json "--outputFile=$report" 1>&2; '
           'status=$?; cat -- "$report" 2>/dev/null; exit $status')
# A JavaScript regular expression that matches no name: every test is filtered out and reported pending.
LIST_NOTHING = '(?!)'
CLAIM = {'passed': 'passed', 'failed': 'failed', 'skipped': 'skipped'}
# Selection, reporting and watch options belong to the runner; an operator prefix holding them could
# run or report other tests.
RESERVED = ('-t', '--testNamePattern', '--testPathPattern', '--runTestsByPath', '--listTests', '--json', '--outputFile',
            '-o', '--onlyChanged', '--changedSince', '--findRelatedTests', '--lastCommit', '--watch', '--watchAll',
            '--testRegex', '--testMatch', '--passWithNoTests', '--bail', '-b', '--retry', '--updateSnapshot', '-u')


@dataclass(frozen=True)
class JestRunnerConfig:
    """Operator-owned Jest prefix (Node binary, the project's Jest CLI script, options), never agent input.

    Every token after the script is an option and none selects tests or reports, so only the runner's
    `--runTestsByPath` and `--testNamePattern` decide what runs.
    """
    command: tuple[str, ...]
    workspace_root: str
    report_path: str
    max_report_bytes: int = MAX_JEST_BYTES
    max_excerpt_chars: int = 4096

    def __post_init__(self):
        if (type(self.command) is not tuple or len(self.command) < 2
                or any(type(t) is not str or not t or '\0' in t for t in self.command)):
            raise ValueError('Runner command must be a binary, the Jest script and options')
        if not self.command[0].startswith('/'):
            raise ValueError('Runner binary must be an absolute operator path')
        if any(token[0] != '-' or token.split('=', 1)[0] in RESERVED for token in self.command[2:]):
            raise ValueError('Jest prefix must hold non-selecting options only after the Jest script')
        if type(self.workspace_root) is not str or not self.workspace_root.startswith('/') or '\0' in self.workspace_root:
            raise ValueError('Workspace root must be an absolute operator path')
        if (type(self.report_path) is not str or not self.report_path.startswith('/') or '\0' in self.report_path
                or self.report_path.startswith(self.workspace_root.rstrip('/') + '/')):
            raise ValueError('Report path must be an absolute operator path outside the workspace')
        if not (type(self.max_report_bytes) is int and 1 <= self.max_report_bytes <= MAX_JEST_BYTES
                and type(self.max_excerpt_chars) is int and 1 <= self.max_excerpt_chars <= 65536):
            raise ValueError('Runner bounds outside the admitted range')


def selection(ids: tuple[str, ...]) -> tuple[str, ...]:
    """The file and an anchored name pattern selecting exactly these tests (identifier titles need no escaping)."""
    parsed = [JsTestId.parse(i) for i in ids]
    return ('--runTestsByPath', parsed[0].path,
            '--testNamePattern', '^(?:' + '|'.join(item.full_name for item in parsed) + ')$')


class JestRunner(NativeRunner):
    def run(self, patch, *, control_test_id, security_test_id, discovery_command, operation, witness=None):
        # The admitted discovery command must be exactly the operator's prefix: anything else could run tests.
        if discovery_command != self._config.command:
            raise ValueError('Jest discovery command must equal the operator\'s Jest prefix')
        return super().run(patch, control_test_id=control_test_id, security_test_id=security_test_id,
                           discovery_command=discovery_command, operation=operation, witness=witness)

    def _validate(self, patch: ApprovedPatch, ids: tuple[str, str], witness: WitnessRequest | None) -> None:
        if witness is not None and not isinstance(witness, WitnessRequest):
            raise ValueError('Witness capture needs a typed request')
        try:
            parsed = [JsTestId.parse(i) for i in ids]
        except ValueError as error:
            raise ValueError('Two distinct `path/file.test.js::[suite::]name` ids are required') from error
        paths = {item.path for item in patch.files}
        if (len(set(ids)) != 2 or len({item.titles for item in parsed}) != 2
                or any(len(i) > MAX_TEST_ID or item.path not in paths for i, item in zip(ids, parsed))):
            raise ValueError('Two distinct test ids declared in patch files are required')
        # One Jest test result per file; both tests in one file keeps exactly one result to admit.
        if len({item.path for item in parsed}) != 1:
            raise ValueError('Control and security tests must be in one file')
        if any(path[0] == '-' for path in paths):
            raise ValueError('Patch paths conflict with runner arguments')

    def _argv(self, ids: tuple[str, ...], pattern: str | None = None) -> tuple[str, ...]:
        file, selected = selection(ids)[:2], selection(ids)[2:]
        names = ('--testNamePattern', pattern) if pattern is not None else selected
        return ('/bin/sh', '-c', WRAPPER, 'corsair-jest', self._config.report_path, *self._config.command, *file, *names)

    def _stages(self, prepared, ids, discovery_command, paths, operation, witness):
        handle = prepared.handle
        command = self._argv(ids, LIST_NOTHING)
        receipt, problem = self._execute(handle, command, uuid5(operation, 'discovery'))
        if problem:
            discovery = Discovery('execution_failure', (), self._excerpt(receipt), command, receipt)
            return discovery, None, 'discovery', f'discovery: {problem}', None
        path = JsTestId.parse(ids[0]).path
        found = listed(receipt.stdout, root=self._config.workspace_root, path=path,
                       max_bytes=self._config.max_report_bytes)
        if receipt.native_exit != 0 or found is None or len(found) != len(set(found)) or set(found) != set(ids):
            discovery = Discovery('collection_error', found or (), self._excerpt(receipt), command, receipt)
            return (discovery, None, 'discovery', f'discovery: exit {receipt.native_exit}, found {list(found or ())}',
                    None)
        discovery = Discovery('discovered', found, '', command, receipt)
        execution, layer = self._run_once(prepared, ids, frozenset(paths), uuid5(operation, 'execution'))
        captured = None
        if witness is not None:
            # No Node probe exists; nothing is run, so the gates see an absent witness.
            captured = WitnessCapture('unavailable', witness, str(uuid5(operation, 'witness-nonce')), '', b'', None,
                                      'no Node.js witness probe; see SPEC-0057', None)
        return discovery, execution, layer, execution.detail, captured

    def _run_once(self, prepared: PreparedWorkspace, ids: tuple[str, str], test_paths: frozenset[str], operation: UUID):
        argv = self._argv(ids)
        receipt, problem = self._execute(prepared.handle, argv, operation)
        failure = lambda layer, detail, report=None, status='execution_failure': (
            Execution(status, (), report, None, detail, argv, receipt), layer)
        if problem:
            return failure('execution', f'execution: {problem}')
        if not receipt.stdout:
            # Jest stopped before writing its report (configuration, transform or environment failure).
            return failure('execution', f'execution: jest exit {receipt.native_exit} without a report')
        try:
            report = self._store.put(receipt.stdout)
        except Exception as error:
            return failure('report', f'report storage: {error_text(error)}')
        if receipt.native_exit not in (0, 1):
            return failure('execution', f'execution: jest exit {receipt.native_exit}', report)
        try:
            cases = parse_jest(receipt.stdout, ids, root=self._config.workspace_root, test_paths=test_paths,
                               max_bytes=self._config.max_report_bytes)
        except JestError as error:
            return failure('report', f'report: {error}', report, 'invalid_report')
        if receipt.native_exit != int(any(case.outcome == 'failed' for case in cases)):
            return failure('report', f'report: jest exit {receipt.native_exit} conflicts with Jest outcomes',
                           report, 'invalid_report')
        control, security = (TestClaim(test_id=case.test_id, outcome=CLAIM[case.outcome]) for case in cases)
        claims_report = WorkloadTestReport(schema_version='test-observations-v1', operation=str(operation),
                                           source_sha256=prepared.source.sha256, tests_sha256=prepared.tests.sha256,
                                           control=control, security=security)
        claims = AdmittedTestClaims(str(operation), prepared.handle, prepared.source, prepared.tests, report,
                                    receipt.native_exit, claims_report)
        return Execution('completed', cases, report, claims, '', argv, receipt), None
