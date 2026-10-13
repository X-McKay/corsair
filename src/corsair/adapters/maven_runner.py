"""Native Maven Surefire runner for JUnit: fresh workspace, listed discovery, one execution, claims from Surefire XML.

The project's own build and test framework run unchanged. Discovery compiles the tests with the
project's Maven build, then lists the selected methods with an operator-pinned JUnit Platform console
launcher against the compiled classes, so it works for JUnit 4 and 5 whatever version the project pins
and runs no test body (class loading still runs static initialisers, as pytest collection imports).
"""
from dataclasses import dataclass
import re
from uuid import UUID, uuid5

from corsair.adapters.native_runner import NativeRunner, check_bounds, check_command, check_ids, check_root
from corsair.ports.test_runner import (ApprovedPatch, JavaTestId, PreparedWorkspace, WitnessRequest,
                                       approved_path)
from corsair.reports.junit import MAX_JUNIT_BYTES, JUnitError
from corsair.reports.junit_listing import listed
from corsair.reports.surefire import parse_surefire

# Fixed operator script run by absolute /bin/sh: Maven's console goes to stderr, stdout is exactly the
# one Surefire class report, exit status is Maven's. Paths and selectors arrive only as positional arguments.
WRAPPER = ('report="$1"; shift; rm -f -- "$report"; "$@" 1>&2; '
           'status=$?; cat -- "$report" 2>/dev/null; exit $status')
# Fixed discovery script: compile and write the test classpath with Maven (console to stderr), then list
# exactly the two selected methods. Every path, the Maven argv and both selectors are positional.
DISCOVER = ('cpfile="$1"; roots="$2"; java="$3"; jar="$4"; first="$5"; second="$6"; shift 6; '
            'rm -f -- "$cpfile"; "$@" 1>&2 || exit $?; '
            'exec "$java" -jar "$jar" discover --disable-banner --disable-ansi-colors --details=flat '
            '--class-path "$roots:$(cat -- "$cpfile")" "--select-method=$first" "--select-method=$second"')


@dataclass(frozen=True)
class MavenRunnerConfig:
    """Operator-owned goal-free Maven prefix (binary, `-B -o`, `--file=<root>/pom.xml`, repository), never agent input.

    Every token after the binary is an option, so no goal or phase can run a test outside the runner's
    selection; the runner appends `test-compile` for discovery and `test` for execution.

    `java` and `console_jar` are absolute image paths for the pinned JUnit Platform console launcher; the
    dependency plugin coordinate is pinned and must be in the offline closure. Directories are Maven's
    per-module defaults unless the admitted build changes them.
    """
    command: tuple[str, ...]
    workspace_root: str
    java: str
    console_jar: str
    dependency_plugin: str = 'org.apache.maven.plugins:maven-dependency-plugin:3.8.1'
    output_dir: str = 'target'
    reports_dir: str = 'target/surefire-reports'
    test_root: str = 'src/test/java'
    max_report_bytes: int = MAX_JUNIT_BYTES
    max_excerpt_chars: int = 4096

    def __post_init__(self):
        check_command(self.command)
        if any(token[0] != '-' for token in self.command[1:]):
            raise ValueError('Maven prefix must hold options only (`--file=...`, `-D...`), never a goal or phase')
        check_root(self.workspace_root)
        if any(type(v) is not str or not v.startswith('/') or '\0' in v for v in (self.java, self.console_jar)):
            raise ValueError('Java and console launcher must be absolute operator paths')
        if type(self.dependency_plugin) is not str or not re.fullmatch(r'[\w.-]+:[\w.-]+:[\w.-]+', self.dependency_plugin):
            raise ValueError('Dependency plugin must be a pinned group:artifact:version')
        for value in (self.output_dir, self.reports_dir, self.test_root):
            approved_path(value)
        check_bounds(self.max_report_bytes, self.max_excerpt_chars, MAX_JUNIT_BYTES)


def selection(ids: tuple[str, ...]) -> tuple[str, ...]:
    """Reactor and Surefire arguments selecting exactly these methods of one class.

    A module build also makes its reactor dependencies (`-am`), whose Surefire runs select nothing.
    """
    parsed = [JavaTestId.parse(i) for i in ids]
    module, class_name = parsed[0].module, parsed[0].class_name
    reactor = ('-pl', module, '-am', '-Dsurefire.failIfNoSpecifiedTests=false') if module else ()
    return reactor + (f'-Dtest={class_name}#{"+".join(item.method for item in parsed)}',)


class MavenRunner(NativeRunner):
    # A goal-bearing discovery command would run test bodies (possibly other tests) before the listing.
    # Maven also exits 1 for build failures; with a complete report that names a failure the two agree.
    tool, report_format = 'maven', 'Surefire'

    def _validate(self, patch: ApprovedPatch, ids: tuple[str, str], witness: WitnessRequest | None) -> None:
        # One Surefire report per class; both tests in one class keeps exactly one report to admit.
        check_ids(patch, ids, witness, JavaTestId.parse, '`[module/]package.Class#method`',
                  file=lambda item: item.source_path(self._config.test_root),
                  unit=lambda item: (item.module, item.class_name),
                  together='Control and security tests must be methods of one class')

    def _module_dir(self, ids: tuple[str, ...]) -> str:
        item = JavaTestId.parse(ids[0])
        return self._config.workspace_root.rstrip('/') + (f'/{item.module}' if item.module else '')

    def _report(self, ids: tuple[str, ...]) -> str:
        return f'{self._module_dir(ids)}/{self._config.reports_dir}/TEST-{JavaTestId.parse(ids[0]).class_name}.xml'

    def _discovery_argv(self, ids: tuple[str, ...]) -> tuple[str, ...]:
        config, module = self._config, self._module_dir(ids)
        cpfile = f'{module}/{config.output_dir}/corsair-test.classpath'
        roots = f'{module}/{config.output_dir}/test-classes:{module}/{config.output_dir}/classes'
        parsed = [JavaTestId.parse(i) for i in ids]
        reactor = selection(ids)[:-1]
        maven = (*config.command, *reactor, 'test-compile', f'{config.dependency_plugin}:build-classpath',
                 f'-Dmdep.outputFile={config.output_dir}/corsair-test.classpath', '-Dmdep.includeScope=test')
        return ('/bin/sh', '-c', DISCOVER, 'corsair-maven-discover', cpfile, roots, config.java, config.console_jar,
                *(f'{item.class_name}#{item.method}' for item in parsed), *maven)

    def _stages(self, prepared, ids, discovery_command, paths, operation, witness):
        module = JavaTestId.parse(ids[0]).module
        read = lambda stdout: None if (names := listed(stdout)) is None else tuple(
            f'{module + "/" if module else ""}{class_name}#{method}' for class_name, method in names)
        discovery, stopped = self._discover(prepared.handle, self._discovery_argv(ids), ids, operation, read)
        if stopped:
            return stopped
        execution, layer = self._run_once(prepared, ids, self._report(ids), selection(ids), frozenset(paths),
                                          uuid5(operation, 'execution'))
        # No JVM probe exists (SPEC-0039).
        return (discovery, execution, layer, execution.detail,
                self._no_witness(witness, operation, 'no Java witness probe; see SPEC-0039'))

    def _run_once(self, prepared: PreparedWorkspace, ids: tuple[str, str], report: str, selected: tuple[str, ...],
                  test_paths: frozenset[str], operation: UUID):
        argv = ('/bin/sh', '-c', WRAPPER, 'corsair-maven', report, *self._config.command, *selected, 'test')
        receipt, problem = self._execute(prepared.handle, argv, operation)
        failure = lambda *args: self._failure(argv, receipt, *args)
        if problem:
            return failure('execution', f'execution: {problem}')
        if not receipt.stdout:
            # Maven failed before Surefire wrote this class's report (build, dependency or fork failure).
            return failure('execution', f'execution: maven exit {receipt.native_exit} without a report')
        junit, stored = self._store_report(receipt.stdout)
        if stored:
            return failure('report', f'report storage: {stored}')
        if receipt.native_exit not in (0, 1):
            return failure('execution', f'execution: maven exit {receipt.native_exit}', junit)
        try:
            cases = parse_surefire(receipt.stdout, ids, test_paths=test_paths, test_root=self._config.test_root,
                                   max_bytes=self._config.max_report_bytes)
        except JUnitError as error:
            return failure('report', f'report: {error}', junit, 'invalid_report')
        return self._completed(prepared, argv, receipt, cases, junit, operation)
