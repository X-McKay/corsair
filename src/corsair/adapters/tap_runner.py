"""Native Perl TAP runner (Test::More subtests): fresh workspace, listed discovery, one execution, claims from TAP.

The project's own test file runs unchanged under the image's Perl. TAP has no listing mode, so discovery
loads the file with Test::More's `subtest` replaced by a recorder: subtest names are listed and no subtest
body runs, while file-level code still runs, as pytest's collection imports a module (SPEC-0061).
Execution runs the file once with stdout and stderr merged, the stream Test::More writes its TAP and
diagnostics to; `reports/tap.py` admits it. With a witness request the file runs through the operator Perl probe
(SPEC-0074), whose record is read back by one fixed command, as the pytest probe's is.
"""
from dataclasses import dataclass
from hashlib import sha256
import json
from pathlib import Path
import re
from uuid import uuid5

from corsair.adapters.native_runner import NativeRunner, check_bounds, check_command, check_ids, check_root
import corsair.nodes.witness
from corsair.ports.test_runner import ApprovedPatch, PerlTestId, WitnessCapture, WitnessRequest, approved_path
from corsair.reports.junit import MAX_JUNIT_BYTES
from corsair.reports.admission import failed_count
from corsair.reports.tap import RESULT, TapError, parse_tap

# The operator Perl probe (SPEC-0074), shipped beside the shared witness module that admits its record by digest.
PERL_PROBE_SOURCE = Path(corsair.nodes.witness.__file__).with_name('witness_probe.pl').read_text(encoding='utf-8')
PERL_PROBE_SHA256 = sha256(PERL_PROBE_SOURCE.encode('utf-8')).hexdigest()
# Fixed Perl bootstrap for `perl -e`: the probe, its JSON config and the test file are the first three arguments;
# the file then runs as `perl FILE` would, with `$0` set to it and a die rethrown for Test::More's exit status. The
# probe's END block is compiled before Test::More loads, so it runs last and sees the final exit status.
PERL_BOOTSTRAP = ('my ($source, $config, $file) = splice @ARGV, 0, 3; require Digest::SHA; require JSON::PP;'
                  ' eval "$source; END { Corsair::WitnessProbe::finish() } 1" or die $@;'
                  ' Corsair::WitnessProbe::start(Digest::SHA::sha256_hex($source), JSON::PP::decode_json($config), $file);'
                  ' $0 = $file; do "./$file"; die $@ if $@;')

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


def perl_probe_argv(command: tuple[str, ...], request: WitnessRequest, file: str, *, root: str, record_path: str,
                    nonce: str) -> tuple[str, ...]:
    """The operator Perl prefix running `file` through the probe bootstrap instead of directly."""
    config = json.dumps({'root': root, 'target_path': request.target_path, 'target_symbol': request.target_symbol,
                         'effect_name': request.effect_name, 'record_path': record_path, 'nonce': nonce,
                         'file': file}, sort_keys=True)
    return command + ('-e', PERL_BOOTSTRAP, PERL_PROBE_SOURCE, config, file)


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
    witness_record_path: str | None = None  # Where the operator Perl probe writes its record (SPEC-0074)

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
        record = self.witness_record_path
        if record is not None and (type(record) is not str or not record.startswith('/') or '\0' in record
                                   or record.startswith(self.workspace_root.rstrip('/') + '/')):
            raise ValueError('Witness record path must be an absolute operator path outside the workspace')


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
    # The environment's discovery command is accepted and not run: the listing is always built from the operator prefix.
    tool, report_format = 'perl', 'TAP'

    @staticmethod
    def _exit_agrees(native_exit, cases):
        # Test::More exits with the number of failed subtests, or 255 when the file died; parse_tap also
        # checks the plan, which only the stream shows.
        if any(case.outcome == 'error' for case in cases):
            return native_exit == 255
        return native_exit == failed_count(cases)

    def _validate(self, patch: ApprovedPatch, ids: tuple[str, str], witness: WitnessRequest | None) -> None:
        # One TAP stream per file; both subtests in one file keep exactly one stream to admit.
        check_ids(patch, ids, witness, PerlTestId.parse, '`path/to/file.t#subtest`', unit=lambda item: item.path,
                  together='Control and security tests must be subtests of one file')
        if witness is not None and self._config.witness_record_path is None:
            raise ValueError('Witness capture needs an operator record path')

    def _discovery_argv(self, file: str) -> tuple[str, ...]:
        return ('/bin/sh', '-c', WRAPPER, 'corsair-tap-discover', self._config.workspace_root,
                *self._config.command, '-e', LISTER, file)

    def _stages(self, prepared, ids, discovery_command, paths, operation, witness):
        file = PerlTestId.parse(ids[0]).path
        read = lambda stdout: None if (names := listed(stdout)) is None else tuple(f'{file}#{name}' for name in names)
        discovery, stopped = self._discover(prepared.handle, self._discovery_argv(file), ids, operation, read)
        if stopped:
            return stopped
        nonce = str(uuid5(operation, 'witness-nonce')) if witness is not None else None
        execution, layer = self._run_once(prepared, ids, file, frozenset(paths), uuid5(operation, 'execution'),
                                          witness, nonce)
        captured = None
        if witness is not None:
            record = self._config.witness_record_path
            captured = (self._read_witness(prepared, witness, nonce, uuid5(operation, 'witness'), record,
                                           PERL_PROBE_SHA256)
                        if execution.status == 'completed' else
                        WitnessCapture('unavailable', witness, nonce, PERL_PROBE_SHA256, b'', None,
                                       f'execution {execution.status}; record not read', None))
        return discovery, execution, layer, execution.detail, captured

    def _run_once(self, prepared, ids, file, test_paths, operation, witness=None, nonce=None):
        # With a witness the file runs through the probe bootstrap; its TAP stream and exit status are the file's.
        command = self._config.command if witness is None else perl_probe_argv(
            self._config.command, witness, file, root=self._config.workspace_root,
            record_path=self._config.witness_record_path, nonce=nonce)
        argv = ('/bin/sh', '-c', WRAPPER, 'corsair-tap', self._config.workspace_root, *command,
                *(() if witness is not None else (file,)))
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
