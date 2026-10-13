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

from corsair.adapters.native_runner import NativeRunner, check_bounds, check_command, check_ids, check_root
from corsair.ports.test_runner import ApprovedPatch, PreparedWorkspace, RubyTestId, WitnessRequest
from corsair.reports.junit import MAX_JUNIT_BYTES, JUnitError
from corsair.reports.minitest import SCHEMA, parse_minitest

# Fixed shell step: run the operator's Ruby prefix in the workspace root. Root and argv are positional.
CHDIR = 'cd -- "$1" || exit 125; shift; exec "$@"'
# Shared prologue: keep the real stdout for the runner, send every other byte (Ruby, C extensions, children)
# to stderr, disable autorun so loading the file runs nothing, and resolve the class by its constant path.
# Only methods whose definition is in the loaded patch file count: a patch that reopens a repository class
# must not let an inherited or helper-defined test stand in for the control or security test.
PROLOGUE = '''file, name, *wanted = ARGV
out = $stdout.dup
$stdout.reopen($stderr)
require "minitest"
def Minitest.autorun; end
path = File.expand_path(file)
load path
klass = begin
  name.split("::").inject(Object) { |scope, part| scope.const_get(part, false) }
rescue NameError
  nil
end
abort "corsair: #{name} is not a Minitest test class in #{file}" unless klass.is_a?(Class) && klass < Minitest::Runnable
wanted = wanted.select do |method|
  location = klass.public_method_defined?(method) && klass.instance_method(method).source_location
  location && File.expand_path(location[0]) == path
end
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
        check_command(self.command)
        rubies = [i for i, token in enumerate(self.command) if PurePosixPath(token).name == 'ruby']
        if not rubies or not self.command[rubies[0]].startswith('/'):
            raise ValueError('Ruby prefix must name the ruby binary by absolute path')
        options = self.command[rubies[0] + 1:]
        if any(token[0] != '-' or token in ('-e', '-E', '-x', '--') or token.startswith(('-e', '-x')) for token in options):
            raise ValueError('Ruby prefix must end in options only (`-I...`), never a script or program text')
        check_root(self.workspace_root)
        check_bounds(self.max_report_bytes, self.max_excerpt_chars, MAX_JUNIT_BYTES)


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
    # The admitted discovery command must be exactly the operator's prefix: a command that names a test
    # file or program would run test bodies before the listing.
    tool, report_format = 'ruby', 'Minitest'

    def _validate(self, patch: ApprovedPatch, ids: tuple[str, str], witness: WitnessRequest | None) -> None:
        # One file and class: the runner loads one file and keeps only that class's tests.
        check_ids(patch, ids, witness, RubyTestId.parse, '`path.rb::Class#test_method`',
                  unit=lambda item: (item.path, item.class_name),
                  together='Control and security tests must be methods of one class in one file')

    def _argv(self, script: str, ids: tuple[str, ...]) -> tuple[str, ...]:
        parsed = [RubyTestId.parse(i) for i in ids]
        return ('/bin/sh', '-c', CHDIR, 'corsair-minitest', self._config.workspace_root, *self._config.command,
                '-e', script, '--', parsed[0].path, parsed[0].class_name, *(item.method for item in parsed))

    def _discovery_argv(self, ids: tuple[str, ...]) -> tuple[str, ...]:
        return self._argv(LIST, ids)

    def _execution_argv(self, ids: tuple[str, ...]) -> tuple[str, ...]:
        return self._argv(RUN, ids)

    def _stages(self, prepared, ids, discovery_command, paths, operation, witness):
        path = RubyTestId.parse(ids[0]).path

        def read(stdout):
            names = listed(stdout)
            return None if names is None else tuple(f'{path}::{class_name}#{method}' for class_name, method in names)

        discovery, stopped = self._discover(prepared.handle, self._discovery_argv(ids), ids, operation, read)
        if stopped:
            return stopped
        execution, layer = self._run_once(prepared, ids, frozenset(paths), uuid5(operation, 'execution'))
        return (discovery, execution, layer, execution.detail,
                self._no_witness(witness, operation, 'no Ruby witness probe; see SPEC-0063'))

    def _run_once(self, prepared: PreparedWorkspace, ids: tuple[str, str], test_paths: frozenset[str], operation: UUID):
        argv = self._execution_argv(ids)
        receipt, problem = self._execute(prepared.handle, argv, operation)
        failure = lambda *args: self._failure(argv, receipt, *args)
        if problem:
            return failure('execution', f'execution: {problem}')
        if not receipt.stdout:
            # Ruby failed before the report was written (load, dependency or Bundler failure).
            return failure('execution', f'execution: ruby exit {receipt.native_exit} without a report')
        report, stored = self._store_report(receipt.stdout)
        if stored:
            return failure('report', f'report storage: {stored}')
        if receipt.native_exit not in (0, 1):
            return failure('execution', f'execution: ruby exit {receipt.native_exit}', report)
        try:
            cases = parse_minitest(receipt.stdout, ids, root=self._config.workspace_root, test_paths=test_paths,
                                   max_bytes=self._config.max_report_bytes)
        except JUnitError as error:
            return failure('report', f'report: {error}', report, 'invalid_report')
        return self._completed(prepared, argv, receipt, cases, report, operation)
