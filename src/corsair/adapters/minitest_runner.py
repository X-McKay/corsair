"""Native Minitest runner: fresh workspace, listed discovery, one execution, claims from Minitest's own results.

The project's Bundler environment and Minitest version run unchanged. Minitest has no list-only mode and no
machine-readable report, so two fixed operator Ruby scripts use its public API: discovery loads the test
file with autorun disabled and lists the selected methods the class defines (class bodies run, as pytest
collection imports, but no test body); execution loads it the same way, keeps only the tests' class, adds a
recorder through Minitest's plugin hook after the project's own plugins, runs `Minitest.run` once with an
exact name filter and prints one JSON report. Every console byte goes to stderr; stdout is the report.
"""
from dataclasses import dataclass
from pathlib import PurePosixPath
from uuid import UUID, uuid5

from corsair.adapters.native_runner import NativeRunner, error_text
from corsair.ports.test_runner import (ApprovedPatch, Discovery, Execution, PreparedWorkspace, RubyTestId,
                                       WitnessCapture, WitnessRequest)
from corsair.reports.junit import MAX_JUNIT_BYTES, JUnitError
from corsair.reports.minitest import SCHEMA, parse_minitest
from corsair.reports.test_observations import AdmittedTestClaims, TestClaim, WorkloadTestReport

# Fixed shell step: run the operator's Ruby prefix in the workspace root. Root and argv are positional.
CHDIR = 'cd -- "$1" || exit 125; shift; exec "$@"'
# Shared prologue: keep the real stdout for the runner, send every other byte (Ruby, C extensions, children)
# to stderr, disable autorun so loading the file runs nothing, and resolve the class by its constant path.
PROLOGUE = '''file, name, *wanted = ARGV
out = $stdout.dup
$stdout.reopen($stderr)
require "minitest"
def Minitest.autorun; end
load File.expand_path(file)
klass = begin
  name.split("::").inject(Object) { |scope, part| scope.const_get(part, false) }
rescue NameError
  nil
end
abort "corsair: #{name} is not a Minitest test class in #{file}" unless klass.is_a?(Class) && klass < Minitest::Runnable
'''
# Minitest 5.16+ orders runnable methods with the run's seed, which only `Minitest.run` sets.
LIST = PROLOGUE + '''Minitest.seed ||= 0 if Minitest.respond_to?(:seed=)
(klass.runnable_methods & wanted).sort.each { |method| out.puts "#{name}##{method}" }
out.flush
'''
RUN = PROLOGUE + '''require "json"
results = []
recorder = Class.new(Minitest::AbstractReporter) { define_method(:record) { |result| results << result } }.new
Minitest.load_plugins unless ENV["MT_NO_PLUGINS"]
Minitest.extensions << "corsair"
Minitest.define_singleton_method(:plugin_corsair_init) { |_options| Minitest.reporter << recorder }
Minitest::Runnable.runnables.replace([klass])
passed = Minitest.run(["--seed", "0", "--name", "/\\\\A(?:#{wanted.map { |m| Regexp.escape(m) }.join("|")})\\\\z/"])
tests = results.map do |result|
  failure = result.failures.find { |item| !item.is_a?(Minitest::Skip) }
  error = failure.is_a?(Minitest::UnexpectedError)
  cause = error ? (failure.respond_to?(:error) ? failure.error : failure.exception) : failure
  outcome = result.skipped? ? "skipped" : error ? "error" : failure ? "failed" : "passed"
  detail = outcome == "skipped" || failure.nil? ? nil : {
    "kind" => error ? "error" : "failure", "type" => cause.class.name,
    "message" => (error ? "#{cause.message}" : failure.message).to_s[0, 2048],
    "backtrace" => Array(cause.backtrace).first(50).map(&:to_s)}
  {"class" => (result.respond_to?(:klass) ? result.klass : result.class.name).to_s, "name" => result.name.to_s,
   "outcome" => outcome, "failure" => detail}
end
out.write(JSON.generate({"schema" => "''' + SCHEMA + '''", "tests" => tests}))
out.flush
exit(passed ? 0 : 1)
'''
CLAIM = {'passed': 'passed', 'failed': 'failed', 'error': 'failed', 'skipped': 'skipped'}


@dataclass(frozen=True)
class MinitestRunnerConfig:
    """Operator-owned Ruby prefix (Bundler environment, `bundle exec`, the ruby binary, `-I` options), never agent input.

    Every token after the ruby binary is an option, so nothing but the runner's own script can run; the
    runner appends `-e <script> -- <file> <class> <methods>`. The prefix runs in `workspace_root`.
    """
    command: tuple[str, ...]
    workspace_root: str
    max_report_bytes: int = MAX_JUNIT_BYTES
    max_excerpt_chars: int = 4096

    def __post_init__(self):
        if (type(self.command) is not tuple or not self.command
                or any(type(t) is not str or not t or '\0' in t for t in self.command)):
            raise ValueError('Runner command must be nonempty string tokens')
        rubies = [i for i, token in enumerate(self.command) if PurePosixPath(token).name == 'ruby']
        if not rubies or not self.command[rubies[0]].startswith('/'):
            raise ValueError('Ruby prefix must name the ruby binary by absolute path')
        options = self.command[rubies[0] + 1:]
        if any(token[0] != '-' or token in ('-e', '-E', '-x', '--') or token.startswith(('-e', '-x')) for token in options):
            raise ValueError('Ruby prefix must end in options only (`-I...`), never a script or program text')
        if type(self.workspace_root) is not str or not self.workspace_root.startswith('/') or '\0' in self.workspace_root:
            raise ValueError('Workspace root must be an absolute operator path')
        if not (type(self.max_report_bytes) is int and 1 <= self.max_report_bytes <= MAX_JUNIT_BYTES
                and type(self.max_excerpt_chars) is int and 1 <= self.max_excerpt_chars <= 65536):
            raise ValueError('Runner bounds outside the admitted range')


def listed(stdout: bytes) -> tuple[tuple[str, str], ...] | None:
    """`Class#test_method` per line from the listing script; any other line is not exact discovery."""
    try:
        lines = stdout.decode('utf-8').splitlines()
    except UnicodeError:
        return None
    found = []
    for line in lines:
        class_name, sep, method = line.rpartition('#')
        try:
            RubyTestId.parse(f'x.rb::{class_name}#{method}')
        except ValueError:
            return None
        found.append((class_name, method))
    return tuple(found)


class MinitestRunner(NativeRunner):
    def run(self, patch, *, control_test_id, security_test_id, discovery_command, operation, witness=None):
        # The admitted discovery command must be exactly the operator's prefix: a command that names a test
        # file or program would run test bodies before the listing.
        if discovery_command != self._config.command:
            raise ValueError('Minitest discovery command must equal the operator\'s Ruby prefix')
        return super().run(patch, control_test_id=control_test_id, security_test_id=security_test_id,
                           discovery_command=discovery_command, operation=operation, witness=witness)

    def _validate(self, patch: ApprovedPatch, ids: tuple[str, str], witness: WitnessRequest | None) -> None:
        if witness is not None and not isinstance(witness, WitnessRequest):
            raise ValueError('Witness capture needs a typed request')
        try:
            parsed = [RubyTestId.parse(i) for i in ids]
        except ValueError as error:
            raise ValueError('Two distinct `path.rb::Class#test_method` ids are required') from error
        paths = {item.path for item in patch.files}
        if len(set(ids)) != 2 or any(item.path not in paths for item in parsed):
            raise ValueError('Two distinct test ids declared in patch files are required')
        # One file and class: the runner loads one file and keeps only that class's tests.
        if len({(item.path, item.class_name) for item in parsed}) != 1:
            raise ValueError('Control and security tests must be methods of one class in one file')
        if any(path[0] == '-' for path in paths):
            raise ValueError('Patch paths conflict with runner arguments')

    def _argv(self, script: str, ids: tuple[str, ...]) -> tuple[str, ...]:
        parsed = [RubyTestId.parse(i) for i in ids]
        return ('/bin/sh', '-c', CHDIR, 'corsair-minitest', self._config.workspace_root, *self._config.command,
                '-e', script, '--', parsed[0].path, parsed[0].class_name, *(item.method for item in parsed))

    def _discovery_argv(self, ids: tuple[str, ...]) -> tuple[str, ...]:
        return self._argv(LIST, ids)

    def _execution_argv(self, ids: tuple[str, ...]) -> tuple[str, ...]:
        return self._argv(RUN, ids)

    def _stages(self, prepared, ids, discovery_command, paths, operation, witness):
        handle = prepared.handle
        command = self._discovery_argv(ids)
        receipt, problem = self._execute(handle, command, uuid5(operation, 'discovery'))
        if problem:
            discovery = Discovery('execution_failure', (), self._excerpt(receipt), command, receipt)
            return discovery, None, 'discovery', f'discovery: {problem}', None
        path = RubyTestId.parse(ids[0]).path
        names = listed(receipt.stdout)
        found = None if names is None else tuple(f'{path}::{class_name}#{method}' for class_name, method in names)
        if receipt.native_exit != 0 or found is None or len(found) != len(set(found)) or set(found) != set(ids):
            discovery = Discovery('collection_error', found or (), self._excerpt(receipt), command, receipt)
            return (discovery, None, 'discovery', f'discovery: exit {receipt.native_exit}, found {list(found or ())}',
                    None)
        discovery = Discovery('discovered', found, '', command, receipt)
        execution, layer = self._run_once(prepared, ids, frozenset(paths), uuid5(operation, 'execution'))
        captured = None
        if witness is not None:
            # No Ruby witness probe exists (SPEC-0059); nothing is run, so the gates see an absent witness.
            captured = WitnessCapture('unavailable', witness, str(uuid5(operation, 'witness-nonce')), '', b'', None,
                                      'no Ruby witness probe; see SPEC-0059', None)
        return discovery, execution, layer, execution.detail, captured

    def _run_once(self, prepared: PreparedWorkspace, ids: tuple[str, str], test_paths: frozenset[str], operation: UUID):
        argv = self._execution_argv(ids)
        receipt, problem = self._execute(prepared.handle, argv, operation)
        failure = lambda layer, detail, report=None, status='execution_failure': (
            Execution(status, (), report, None, detail, argv, receipt), layer)
        if problem:
            return failure('execution', f'execution: {problem}')
        if not receipt.stdout:
            # Ruby failed before the report was written (load, dependency or Bundler failure).
            return failure('execution', f'execution: ruby exit {receipt.native_exit} without a report')
        try:
            report = self._store.put(receipt.stdout)
        except Exception as error:
            return failure('report', f'report storage: {error_text(error)}')
        if receipt.native_exit not in (0, 1):
            return failure('execution', f'execution: ruby exit {receipt.native_exit}', report)
        try:
            cases = parse_minitest(receipt.stdout, ids, root=self._config.workspace_root, test_paths=test_paths,
                                   max_bytes=self._config.max_report_bytes)
        except JUnitError as error:
            return failure('report', f'report: {error}', report, 'invalid_report')
        if receipt.native_exit != int(any(case.outcome in ('failed', 'error') for case in cases)):
            return failure('report', f'report: ruby exit {receipt.native_exit} conflicts with Minitest outcomes',
                           report, 'invalid_report')
        control, security = (TestClaim(test_id=case.test_id, outcome=CLAIM[case.outcome]) for case in cases)
        claims_report = WorkloadTestReport(schema_version='test-observations-v1', operation=str(operation),
                                           source_sha256=prepared.source.sha256, tests_sha256=prepared.tests.sha256,
                                           control=control, security=security)
        claims = AdmittedTestClaims(str(operation), prepared.handle, prepared.source, prepared.tests, report,
                                    receipt.native_exit, claims_report)
        return Execution('completed', cases, report, claims, '', argv, receipt), None
