"""Native Maven Surefire runner for JUnit: fresh workspace, dry-run discovery, one execution, claims from Surefire XML.

Discovery is the JUnit Platform's own dry run (`junit.platform.execution.dryRun.enabled`, Platform 1.13+):
Surefire reports every selected test as skipped without running its body. An older platform ignores the
property and runs the bodies; the report then shows real outcomes and discovery is refused, so the
operator must only configure this runner for an admitted closure with a dry-run capable platform.
"""
from dataclasses import dataclass
from uuid import UUID, uuid5

from corsair.adapters.native_runner import NativeRunner, error_text
from corsair.ports.test_runner import (MAX_TEST_ID, ApprovedPatch, Discovery, Execution, JavaTestId,
                                       PreparedWorkspace, WitnessCapture, WitnessRequest, approved_path)
from corsair.reports.junit import MAX_JUNIT_BYTES, JUnitError
from corsair.reports.surefire import parse_surefire
from corsair.reports.test_observations import AdmittedTestClaims, TestClaim, WorkloadTestReport

# Fixed operator script run by absolute /bin/sh: Maven's console goes to stderr, stdout is exactly the
# one Surefire class report, exit status is Maven's. Paths and selectors arrive only as positional arguments.
WRAPPER = ('report="$1"; shift; rm -f -- "$report"; "$@" 1>&2; '
           'status=$?; cat -- "$report" 2>/dev/null; exit $status')
DRY_RUN = '-Djunit.platform.execution.dryRun.enabled=true'
CLAIM = {'passed': 'passed', 'failed': 'failed', 'error': 'failed', 'skipped': 'skipped'}


@dataclass(frozen=True)
class MavenRunnerConfig:
    """Operator-owned Maven argv (binary, `-B -o`, `-f <root>/pom.xml`, repository and goal), never agent input.

    `reports_dir` and `test_root` are Maven's per-module defaults unless the admitted build changes them.
    """
    command: tuple[str, ...]
    workspace_root: str
    reports_dir: str = 'target/surefire-reports'
    test_root: str = 'src/test/java'
    max_report_bytes: int = MAX_JUNIT_BYTES
    max_excerpt_chars: int = 4096

    def __post_init__(self):
        if (type(self.command) is not tuple or not self.command
                or any(type(t) is not str or not t or '\0' in t for t in self.command)):
            raise ValueError('Runner command must be nonempty string tokens')
        if type(self.workspace_root) is not str or not self.workspace_root.startswith('/') or '\0' in self.workspace_root:
            raise ValueError('Workspace root must be an absolute operator path')
        for value in (self.reports_dir, self.test_root):
            approved_path(value)
        if not (type(self.max_report_bytes) is int and 1 <= self.max_report_bytes <= MAX_JUNIT_BYTES
                and type(self.max_excerpt_chars) is int and 1 <= self.max_excerpt_chars <= 65536):
            raise ValueError('Runner bounds outside the admitted range')


def selection(ids: tuple[str, ...]) -> tuple[str, ...]:
    """Reactor and Surefire arguments selecting exactly these methods of one class.

    A module build also makes its reactor dependencies (`-am`), whose Surefire runs select nothing.
    """
    parsed = [JavaTestId.parse(i) for i in ids]
    module, class_name = parsed[0].module, parsed[0].class_name
    reactor = ('-pl', module, '-am', '-Dsurefire.failIfNoSpecifiedTests=false') if module else ()
    return reactor + (f'-Dtest={class_name}#{"+".join(item.method for item in parsed)}',)


class MavenRunner(NativeRunner):
    def _validate(self, patch: ApprovedPatch, ids: tuple[str, str], witness: WitnessRequest | None) -> None:
        if witness is not None and not isinstance(witness, WitnessRequest):
            raise ValueError('Witness capture needs a typed request')
        try:
            parsed = [JavaTestId.parse(i) for i in ids]
        except ValueError as error:
            raise ValueError('Two distinct `[module/]package.Class#method` ids are required') from error
        paths = {item.path for item in patch.files}
        if len(set(ids)) != 2 or any(len(i) > MAX_TEST_ID or item.source_path(self._config.test_root) not in paths
                                     for i, item in zip(ids, parsed)):
            raise ValueError('Two distinct test ids declared in patch files are required')
        # One Surefire report per class; both tests in one class keeps exactly one report to admit.
        if len({(item.module, item.class_name) for item in parsed}) != 1:
            raise ValueError('Control and security tests must be methods of one class')
        if any(path[0] == '-' for path in paths):
            raise ValueError('Patch paths conflict with runner arguments')

    def _report(self, ids: tuple[str, ...]) -> str:
        item = JavaTestId.parse(ids[0])
        module = f'{item.module}/' if item.module else ''
        return f'{self._config.workspace_root.rstrip("/")}/{module}{self._config.reports_dir}/TEST-{item.class_name}.xml'

    def _stages(self, prepared, ids, discovery_command, paths, operation, witness):
        handle = prepared.handle
        report, selected = self._report(ids), selection(ids)
        command = ('/bin/sh', '-c', WRAPPER, 'corsair-maven', report, *discovery_command, *selected, DRY_RUN)
        receipt, problem = self._execute(handle, command, uuid5(operation, 'discovery'))
        if problem:
            discovery = Discovery('execution_failure', (), self._excerpt(receipt), command, receipt)
            return discovery, None, 'discovery', f'discovery: {problem}', None
        try:
            found = tuple(case.test_id for case in parse_surefire(
                receipt.stdout, ids, test_paths=frozenset(paths), test_root=self._config.test_root,
                max_bytes=self._config.max_report_bytes, dry_run=True))
            refused = ''
        except JUnitError as error:
            found, refused = None, f', {error}'
        if receipt.native_exit != 0 or found is None:
            discovery = Discovery('collection_error', found or (), self._excerpt(receipt), command, receipt)
            return discovery, None, 'discovery', f'discovery: exit {receipt.native_exit}{refused}', None
        discovery = Discovery('discovered', found, '', command, receipt)
        execution, layer = self._run_once(prepared, ids, report, selected, frozenset(paths), uuid5(operation, 'execution'))
        captured = None
        if witness is not None:
            # No JVM probe exists (SPEC-0039); nothing is run, so the gates see an absent witness.
            captured = WitnessCapture('unavailable', witness, str(uuid5(operation, 'witness-nonce')), '', b'', None,
                                      'no Java witness probe; see SPEC-0039', None)
        return discovery, execution, layer, execution.detail, captured

    def _run_once(self, prepared: PreparedWorkspace, ids: tuple[str, str], report: str, selected: tuple[str, ...],
                  test_paths: frozenset[str], operation: UUID):
        argv = ('/bin/sh', '-c', WRAPPER, 'corsair-maven', report, *self._config.command, *selected)
        receipt, problem = self._execute(prepared.handle, argv, operation)
        failure = lambda layer, detail, junit=None, status='execution_failure': (
            Execution(status, (), junit, None, detail, argv, receipt), layer)
        if problem:
            return failure('execution', f'execution: {problem}')
        if not receipt.stdout:
            # Maven failed before Surefire wrote this class's report (build, dependency or fork failure).
            return failure('execution', f'execution: maven exit {receipt.native_exit} without a report')
        try:
            junit = self._store.put(receipt.stdout)
        except Exception as error:
            return failure('report', f'report storage: {error_text(error)}')
        if receipt.native_exit not in (0, 1):
            return failure('execution', f'execution: maven exit {receipt.native_exit}', junit)
        try:
            cases = parse_surefire(receipt.stdout, ids, test_paths=test_paths, test_root=self._config.test_root,
                                   max_bytes=self._config.max_report_bytes)
        except JUnitError as error:
            return failure('report', f'report: {error}', junit, 'invalid_report')
        # Maven also exits 1 for build failures; with a complete report that names a failure the two agree.
        if receipt.native_exit != int(any(case.outcome in ('failed', 'error') for case in cases)):
            return failure('report', f'report: maven exit {receipt.native_exit} conflicts with Surefire outcomes',
                           junit, 'invalid_report')
        control, security = (TestClaim(test_id=case.test_id, outcome=CLAIM[case.outcome]) for case in cases)
        claims_report = WorkloadTestReport(schema_version='test-observations-v1', operation=str(operation),
                                           source_sha256=prepared.source.sha256, tests_sha256=prepared.tests.sha256,
                                           control=control, security=security)
        claims = AdmittedTestClaims(str(operation), prepared.handle, prepared.source, prepared.tests, junit,
                                    receipt.native_exit, claims_report)
        return Execution('completed', cases, junit, claims, '', argv, receipt), None
