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

from corsair.adapters.native_runner import NativeRunner, error_text
from corsair.ports.test_runner import (MAX_TEST_ID, ApprovedPatch, Discovery, Execution, PerlTestId,
                                       WitnessCapture, WitnessRequest, approved_path)
from corsair.reports.junit import MAX_JUNIT_BYTES
from corsair.reports.tap import RESULT, TapError, parse_tap
from corsair.reports.test_observations import AdmittedTestClaims, TestClaim, WorkloadTestReport

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
CLAIM = {'passed': 'passed', 'failed': 'failed', 'error': 'failed', 'skipped': 'skipped'}


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
        if (type(self.command) is not tuple or not self.command
                or any(type(t) is not str or not t or '\0' in t for t in self.command)):
            raise ValueError('Runner command must be nonempty string tokens')
        if not self.command[0].startswith('/'):
            raise ValueError('Perl must be an absolute operator path')
        for token in self.command[1:]:
            if not token.startswith('-I'):
                raise ValueError('Perl prefix must hold `-I<dir>` options only')
            approved_path(token[2:])
        if type(self.workspace_root) is not str or not self.workspace_root.startswith('/') or '\0' in self.workspace_root:
            raise ValueError('Workspace root must be an absolute operator path')
        if not (type(self.max_report_bytes) is int and 1 <= self.max_report_bytes <= MAX_JUNIT_BYTES
                and type(self.max_excerpt_chars) is int and 1 <= self.max_excerpt_chars <= 65536):
            raise ValueError('Runner bounds outside the admitted range')


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
    def run(self, patch, *, control_test_id, security_test_id, discovery_command, operation, witness=None):
        if discovery_command != self._config.command:
            raise ValueError('TAP discovery command must equal the operator\'s Perl prefix')
        return super().run(patch, control_test_id=control_test_id, security_test_id=security_test_id,
                           discovery_command=discovery_command, operation=operation, witness=witness)

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
        command = self._discovery_argv(file)
        receipt, problem = self._execute(prepared.handle, command, uuid5(operation, 'discovery'))
        if problem:
            discovery = Discovery('execution_failure', (), self._excerpt(receipt), command, receipt)
            return discovery, None, 'discovery', f'discovery: {problem}', None
        names = listed(receipt.stdout)
        found = None if names is None else tuple(f'{file}#{name}' for name in names)
        if receipt.native_exit != 0 or found is None or len(found) != len(set(found)) or set(found) != set(ids):
            discovery = Discovery('collection_error', found or (), self._excerpt(receipt), command, receipt)
            return (discovery, None, 'discovery', f'discovery: exit {receipt.native_exit}, found {list(found or ())}',
                    None)
        discovery = Discovery('discovered', found, '', command, receipt)
        execution, layer = self._run_once(prepared, ids, file, frozenset(paths), uuid5(operation, 'execution'))
        captured = None
        if witness is not None:
            # No Perl probe exists; nothing is run, so the gates see an absent witness.
            captured = WitnessCapture('unavailable', witness, str(uuid5(operation, 'witness-nonce')), '', b'', None,
                                      'no Perl witness probe', None)
        return discovery, execution, layer, execution.detail, captured

    def _run_once(self, prepared, ids, file, test_paths, operation):
        argv = ('/bin/sh', '-c', WRAPPER, 'corsair-tap', self._config.workspace_root, *self._config.command, file)
        receipt, problem = self._execute(prepared.handle, argv, operation)
        failure = lambda layer, detail, report=None, status='execution_failure': (
            Execution(status, (), report, None, detail, argv, receipt), layer)
        if problem:
            return failure('execution', f'execution: {problem}')
        if receipt.native_exit == 125:
            return failure('execution', 'execution: workspace root unavailable')
        try:
            report = self._store.put(receipt.stdout)
        except Exception as error:
            return failure('report', f'report storage: {error_text(error)}')
        try:
            cases = parse_tap(receipt.stdout, ids, exit_status=receipt.native_exit, test_paths=test_paths,
                              max_bytes=self._config.max_report_bytes)
        except TapError as error:
            return failure('report', f'report: {error}', report, 'invalid_report')
        control, security = (TestClaim(test_id=case.test_id, outcome=CLAIM[case.outcome]) for case in cases)
        claims_report = WorkloadTestReport(schema_version='test-observations-v1', operation=str(operation),
                                           source_sha256=prepared.source.sha256, tests_sha256=prepared.tests.sha256,
                                           control=control, security=security)
        claims = AdmittedTestClaims(str(operation), prepared.handle, prepared.source, prepared.tests, report,
                                    receipt.native_exit, claims_report)
        return Execution('completed', cases, report, claims, '', argv, receipt), None
