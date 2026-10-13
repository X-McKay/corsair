"""Native Jest runner: fresh workspace, listed discovery, one execution, claims from Jest's own JSON report.

The project's own Jest and configuration run unchanged. Discovery runs the test file with a name
pattern that matches nothing, so Jest loads the file and reports every test as skipped by name without
running a test body or hook (module top-level code still runs, as pytest collection imports); execution
then selects exactly the two tests by their anchored full names.
"""
from dataclasses import dataclass
from uuid import UUID, uuid5

from corsair.adapters.native_runner import NativeRunner, check_bounds, check_command, check_root
from corsair.ports.test_runner import MAX_TEST_ID, ApprovedPatch, JsTestId, PreparedWorkspace, WitnessRequest
from corsair.reports.jest import MAX_JEST_BYTES, JestError, listed, parse_jest

# Fixed operator script run by absolute /bin/sh: Jest's console goes to stderr, stdout is exactly Jest's
# JSON report, exit status is Jest's. The report path and all Jest arguments arrive only as positional arguments.
WRAPPER = ('report="$1"; shift; rm -f -- "$report"; "$@" --json "--outputFile=$report" 1>&2; '
           'status=$?; cat -- "$report" 2>/dev/null; exit $status')
# A JavaScript regular expression that matches no name: every test is filtered out and reported pending.
LIST_NOTHING = '(?!)'
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
        check_command(self.command, 2, 'Runner command must be a binary, the Jest script and options')
        if not self.command[0].startswith('/'):
            raise ValueError('Runner binary must be an absolute operator path')
        if any(token[0] != '-' or token.split('=', 1)[0] in RESERVED for token in self.command[2:]):
            raise ValueError('Jest prefix must hold non-selecting options only after the Jest script')
        check_root(self.workspace_root)
        if (type(self.report_path) is not str or not self.report_path.startswith('/') or '\0' in self.report_path
                or self.report_path.startswith(self.workspace_root.rstrip('/') + '/')):
            raise ValueError('Report path must be an absolute operator path outside the workspace')
        check_bounds(self.max_report_bytes, self.max_excerpt_chars, MAX_JEST_BYTES)


def selection(ids: tuple[str, ...]) -> tuple[str, ...]:
    """The file and an anchored name pattern selecting exactly these tests (identifier titles need no escaping)."""
    parsed = [JsTestId.parse(i) for i in ids]
    return ('--runTestsByPath', parsed[0].path,
            '--testNamePattern', '^(?:' + '|'.join(item.full_name for item in parsed) + ')$')


class JestRunner(NativeRunner):
    # The admitted discovery command must be exactly the operator's prefix: anything else could run tests.
    exact_discovery = 'Jest discovery command must equal the operator\'s Jest prefix'
    tool, report_format = 'jest', 'Jest'

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
        path = JsTestId.parse(ids[0]).path
        read = lambda stdout: listed(stdout, root=self._config.workspace_root, path=path,
                                     max_bytes=self._config.max_report_bytes)
        discovery, stopped = self._discover(prepared.handle, self._argv(ids, LIST_NOTHING), ids, operation, read)
        if stopped:
            return stopped
        execution, layer = self._run_once(prepared, ids, frozenset(paths), uuid5(operation, 'execution'))
        return (discovery, execution, layer, execution.detail,
                self._no_witness(witness, operation, 'no Node.js witness probe; see SPEC-0057'))

    def _run_once(self, prepared: PreparedWorkspace, ids: tuple[str, str], test_paths: frozenset[str], operation: UUID):
        argv = self._argv(ids)
        receipt, problem = self._execute(prepared.handle, argv, operation)
        failure = lambda *args: self._failure(argv, receipt, *args)
        if problem:
            return failure('execution', f'execution: {problem}')
        if not receipt.stdout:
            # Jest stopped before writing its report (configuration, transform or environment failure).
            return failure('execution', f'execution: jest exit {receipt.native_exit} without a report')
        report, stored = self._store_report(receipt.stdout)
        if stored:
            return failure('report', f'report storage: {stored}')
        if receipt.native_exit not in (0, 1):
            return failure('execution', f'execution: jest exit {receipt.native_exit}', report)
        try:
            cases = parse_jest(receipt.stdout, ids, root=self._config.workspace_root, test_paths=test_paths,
                               max_bytes=self._config.max_report_bytes)
        except JestError as error:
            return failure('report', f'report: {error}', report, 'invalid_report')
        return self._completed(prepared, argv, receipt, cases, report, operation)
