"""Native Perl TAP runner (Test::More subtests): fresh workspace, listed discovery, one execution, claims from TAP.

The project's own test file runs unchanged under the image's Perl. TAP has no listing mode, so discovery
loads the file with Test::More's `subtest` replaced by a recorder: subtest names are listed and no subtest
body runs, while file-level code still runs, as pytest's collection imports a module (SPEC-0061).
Execution runs the file once with stdout and stderr merged, the stream Test::More writes its TAP and
diagnostics to; `reports/tap.py` admits it.
"""
from dataclasses import dataclass
import re
from uuid import uuid5

from corsair.adapters.native_runner import NativeRunner, check_bounds, check_command, check_root
from corsair.ports.test_runner import MAX_TEST_ID, ApprovedPatch, PerlTestId, WitnessRequest, approved_path
from corsair.reports.junit import MAX_JUNIT_BYTES
from corsair.reports.admission import failed_count
from corsair.reports.tap import RESULT, TapError, parse_tap

# Fixed operator scripts run by absolute /bin/sh; the root, the Perl argv and the file arrive only as positional
# arguments. Execution: stdout is the merged TAP stream, exit status is the test file's.
WRAPPER = 'cd -- "$1" || exit 125; shift; exec "$@" 2>&1'
# Fixed discovery program for `perl -e`: record top-level subtest names without running their bodies. `_exit`
# skips Test::Builder's end-of-file plan checks, which would fail because no assertion ran.
LISTER = ('use strict; use warnings; use Test::More (); use POSIX ();'
          ' my $file = shift @ARGV; $| = 1;'
          ' { no warnings "redefine"; *Test::More::subtest = sub { print "corsair-subtest\\t$_[0]\\n"; 1 }; }'
          ' $0 = $file; my $loaded = do "./$file";'
          ' if ($@) { print STDERR $@; POSIX::_exit(2) }'
          ' if (!defined $loaded && $!) { print STDERR "cannot read $file: $!\\n"; POSIX::_exit(2) }'
          ' POSIX::_exit(0);')
LISTED = re.compile(r'corsair-subtest\t(?P<name>[A-Za-z_][A-Za-z0-9_]*)')


@dataclass(frozen=True)
class TapRunnerConfig:
    """Operator-owned Perl interpreter, include directories and bounds, never agent input.

    `command` is the absolute interpreter followed by `-I<dir>` options only (relative to the workspace root, for
    a built `blib` or the project's `lib`), so nothing but the selected file can run.
    """
    command: tuple[str, ...]
    workspace_root: str
    max_report_bytes: int = MAX_JUNIT_BYTES
    max_excerpt_chars: int = 4096

    def __post_init__(self):
        check_command(self.command)
        if not self.command[0].startswith('/'):
            raise ValueError('Perl must be an absolute operator path')
        for token in self.command[1:]:
            if not token.startswith('-I'):
                raise ValueError('Perl prefix must hold `-I<dir>` options only')
            approved_path(token[2:])
        check_root(self.workspace_root)
        check_bounds(self.max_report_bytes, self.max_excerpt_chars, MAX_JUNIT_BYTES)


def listed(stdout: bytes) -> tuple[str, ...] | None:
    """Subtest names the lister recorded; a top-level TAP result means a test outside a subtest ran, not a listing."""
    try:
        lines = stdout.decode('utf-8').splitlines()
    except UnicodeError:
        return None
    if any(RESULT.fullmatch(line) for line in lines):
        return None
    return tuple(match['name'] for line in lines if (match := LISTED.fullmatch(line)))


class TapRunner(NativeRunner):
    exact_discovery = 'TAP discovery command must equal the operator\'s Perl prefix'
    tool, report_format = 'perl', 'TAP'

    @staticmethod
    def _exit_agrees(native_exit, cases):
        # Test::More exits with the number of failed subtests, or 255 when the file died; parse_tap also
        # checks the plan, which only the stream shows.
        if any(case.outcome == 'error' for case in cases):
            return native_exit == 255
        return native_exit == failed_count(cases)

    def _validate(self, patch: ApprovedPatch, ids: tuple[str, str], witness: WitnessRequest | None) -> None:
        if witness is not None and not isinstance(witness, WitnessRequest):
            raise ValueError('Witness capture needs a typed request')
        try:
            parsed = [PerlTestId.parse(i) for i in ids]
        except ValueError as error:
            raise ValueError('Two distinct `path/to/file.t#subtest` ids are required') from error
        paths = {item.path for item in patch.files}
        if len(set(ids)) != 2 or any(len(i) > MAX_TEST_ID or item.path not in paths for i, item in zip(ids, parsed)):
            raise ValueError('Two distinct test ids declared in patch files are required')
        # One TAP stream per file; both subtests in one file keep exactly one stream to admit.
        if len({item.path for item in parsed}) != 1:
            raise ValueError('Control and security tests must be subtests of one file')
        if any(path[0] == '-' for path in paths):
            raise ValueError('Patch paths conflict with runner arguments')

    def _discovery_argv(self, file: str) -> tuple[str, ...]:
        return ('/bin/sh', '-c', WRAPPER, 'corsair-tap-discover', self._config.workspace_root,
                *self._config.command, '-e', LISTER, file)

    def _stages(self, prepared, ids, discovery_command, paths, operation, witness):
        file = PerlTestId.parse(ids[0]).path
        read = lambda stdout: None if (names := listed(stdout)) is None else tuple(f'{file}#{name}' for name in names)
        discovery, stopped = self._discover(prepared.handle, self._discovery_argv(file), ids, operation, read)
        if stopped:
            return stopped
        execution, layer = self._run_once(prepared, ids, file, frozenset(paths), uuid5(operation, 'execution'))
        return discovery, execution, layer, execution.detail, self._no_witness(witness, operation, 'no Perl witness probe')

    def _run_once(self, prepared, ids, file, test_paths, operation):
        argv = ('/bin/sh', '-c', WRAPPER, 'corsair-tap', self._config.workspace_root, *self._config.command, file)
        receipt, problem = self._execute(prepared.handle, argv, operation)
        if problem:
            return self._failure(argv, receipt, 'execution', f'execution: {problem}')
        if receipt.native_exit == 125:
            return self._failure(argv, receipt, 'execution', 'execution: workspace root unavailable')
        report, stored = self._store_report(receipt.stdout)
        if stored:
            return self._failure(argv, receipt, 'report', f'report storage: {stored}')
        try:
            # The exit status is checked against the outcomes inside: Test::More's rule depends on how the file ended.
            cases = parse_tap(receipt.stdout, ids, exit_status=receipt.native_exit, test_paths=test_paths,
                              max_bytes=self._config.max_report_bytes)
        except TapError as error:
            return self._failure(argv, receipt, 'report', f'report: {error}', report, 'invalid_report')
        return self._completed(prepared, argv, receipt, cases, report, operation)
