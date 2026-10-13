"""SPEC-0074 Perl witness probe and its mapping to the SPEC-0027 witness, with the real probe in real Perl processes.

Runs the host's Perl (any 5.14+ with core Test::More); the Perl 5.26.3 image runs are recorded in PLAN-0088.
"""
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest

from corsair.nodes.witness import PERL_PROBE_SHA256, PROBE_SHA256, Calibration, perl_probe_argv, witness_evidence
from corsair.ports.artifacts import ArtifactRef
from corsair.ports.test_runner import WitnessCapture, WitnessRequest
from corsair.reports.tap import parse_tap

PERL = shutil.which('perl')
pytestmark = pytest.mark.skipif(
    PERL is None or subprocess.run([PERL, '-MTest::More', '-MJSON::PP', '-e1'], capture_output=True).returncode != 0,
    reason='no Perl with core Test::More and JSON::PP on this host')

NONCE = 'nonce-1'
FILE = 't/case.t'
IDS = (f'{FILE}#test_control', f'{FILE}#test_security')
REQUEST = WitnessRequest('lib/Notes.pm', 'save', 'sentinel.txt')
CONTROL = Calibration(IDS[0], 'sentinel.txt')
NOTES = '''package Notes;
use strict;
use warnings;
use Exporter 'import';
our @EXPORT_OK = qw(save);
use Helper;

sub save {
    my ($dir, $name, $mode) = @_;
    die "refused\\n" if $mode eq 'check' && $name =~ /\\.\\./;
    return Helper::touch("$dir/$name") if $mode eq 'helper';
    open(my $fh, '>', "$dir/$name") or die "cannot write: $!\\n";
    print $fh "note";
    close $fh;
    return 1;
}

1;
'''
# Another file with a sub of the same name: never the target, though it opens the planned file.
HELPER = '''package Helper;
use strict;
use warnings;
sub touch { open(my $fh, '>', $_[0]) or die; close $fh; 1 }
sub save { open(my $fh, '>', $_[0]) or die; close $fh; 1 }
1;
'''
HEADER = '''use strict;
use warnings;
use Test::More;
use File::Temp qw(tempdir);
use Notes qw(save);
my $dir = tempdir(CLEANUP => 1);
mkdir "$dir/notes";
'''
CONTROL_TEST = '''subtest test_control => sub {
    ok(save($dir, 'sentinel.txt', 'check'), 'writes its own note');
};
'''


def run_probe(tmp_path, body, *, probed=True, record_path='witness.json'):
    (tmp_path / 'lib').mkdir(exist_ok=True)
    (tmp_path / 't').mkdir(exist_ok=True)
    (tmp_path / 'lib/Notes.pm').write_text(NOTES)
    (tmp_path / 'lib/Helper.pm').write_text(HELPER)
    (tmp_path / FILE).write_text(HEADER + CONTROL_TEST + body + 'done_testing;\n')
    command = (PERL, '-Ilib')
    argv = (perl_probe_argv(command, REQUEST, FILE, root=str(tmp_path), record_path=record_path, nonce=NONCE)
            if probed else command + (FILE,))
    done = subprocess.run(argv, cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, timeout=60,
                          env={'PATH': os.environ.get('PATH', ''), 'HOME': str(tmp_path)})
    record = (tmp_path / record_path).read_bytes() if probed and (tmp_path / record_path).exists() else b''
    return done, record


def capture(record, **changes):
    values = dict(status='captured', request=REQUEST, nonce=NONCE, probe_sha256=PERL_PROBE_SHA256, record=record,
                  artifact=ArtifactRef(sha256(record).hexdigest(), len(record)), detail='', receipt=None)
    return WitnessCapture(**(values | changes))


def mapped(tmp_path, body, **options):
    done, record = run_probe(tmp_path, body)
    assert record, done.stdout.decode()
    return witness_evidence(capture(record), REQUEST, IDS[1], **options), json.loads(record), done


def test_the_target_reached_through_an_imported_alias_records_the_planned_open(tmp_path):
    found, record, _ = mapped(tmp_path, '''subtest test_security => sub {
    ok(!eval { save("$dir/notes", '../sentinel.txt', 'none'); 1 }, 'traversal refused');
};
''')
    assert found.reason == 'admitted' and found.witness.effect == 'observed' and found.witness.path_reached
    security = record['tests'][IDS[1]]
    assert security['entered'] == 1 and security['exits'] == [None] and security['opens'][0]['planned']
    assert record['intact'] and record['tool_registered'] and record['plugin_sha256'] == PERL_PROBE_SHA256


def test_a_calibrated_refusal_is_the_planned_absence(tmp_path):
    body = '''subtest test_security => sub {
    ok(!eval { save("$dir/notes", '../sentinel.txt', 'check'); 1 }, 'traversal refused');
};
'''
    found, record, _ = mapped(tmp_path, body, planned_safe_behavior='no_file_open', control=CONTROL)
    assert found.witness.effect == 'absent' and found.witness.safe_behavior == 'no_file_open'
    assert record['tests'][IDS[1]]['exits'] == ['die']
    uncalibrated, *_ = mapped(tmp_path, body, planned_safe_behavior='no_file_open',
                              control=Calibration(IDS[0], 'other.txt'))
    assert uncalibrated.witness is None and 'not calibrated' in uncalibrated.reason


def test_the_tests_own_read_after_the_call_is_not_the_effect(tmp_path):
    found, record, _ = mapped(tmp_path, '''subtest test_security => sub {
    ok(!eval { save("$dir/notes", '../sentinel.txt', 'check'); 1 }, 'traversal refused');
    ok(open(my $fh, '<', "$dir/sentinel.txt"), 'control note still readable');
};
''')
    security = record['tests'][IDS[1]]
    assert security['body_planned'] == 1 and security['offstack_planned'] == 0 and found.witness.effect == 'absent'


def test_a_planned_open_by_another_module_off_the_target_is_unknown(tmp_path):
    found, record, _ = mapped(tmp_path, '''subtest test_security => sub {
    ok(!eval { save("$dir/notes", 'x.txt', 'check'); 1 }, 'saved');
    Helper::save("$dir/sentinel.txt");
};
''')
    assert record['tests'][IDS[1]]['offstack_planned'] == 1 and found.witness.effect == 'unknown'


def test_the_same_name_in_another_file_is_never_the_target(tmp_path):
    found, record, _ = mapped(tmp_path, '''subtest test_security => sub {
    ok(Helper::save("$dir/notes/x.txt"), 'helper');
};
''')
    assert record['tests'][IDS[1]]['entered'] == 0 and found.witness.path_reached is False


def test_a_failed_planned_open_on_the_target_stack_leaves_the_effect_unknown(tmp_path):
    found, record, _ = mapped(tmp_path, '''subtest test_security => sub {
    ok(!eval { save("$dir/missing", 'sentinel.txt', 'none'); 1 }, 'cannot write');
};
''')
    security = record['tests'][IDS[1]]
    assert security['os_errors'][0]['errno'] != 0 and security['exits'] == ['die'] and found.witness.effect == 'unknown'


def test_test_code_replacing_the_open_override_marks_the_record_not_intact(tmp_path):
    found, record, _ = mapped(tmp_path, '''subtest test_security => sub {
    no warnings 'redefine';
    *CORE::GLOBAL::open = sub { 1 };
    ok(1, 'replaced');
};
''')
    assert not record['intact'] and found.witness is None and 'not registered' in found.reason


def test_a_record_path_that_already_exists_fails_the_run_instead_of_being_replaced(tmp_path):
    (tmp_path / 'witness.json').write_text('{"forged": true}')
    done, record = run_probe(tmp_path, 'subtest test_security => sub { ok(1) };\n')
    assert done.returncode == 3 and json.loads(record) == {'forged': True}


def test_another_probe_or_run_is_refused(tmp_path):
    _, record = run_probe(tmp_path, 'subtest test_security => sub { ok(1) };\n')
    assert 'another target or probe' in witness_evidence(capture(record, probe_sha256='0' * 64), REQUEST, IDS[1]).reason
    for changes in ({'probe_sha256': PROBE_SHA256}, {'nonce': 'other'}):
        assert 'does not belong' in witness_evidence(capture(record, **changes), REQUEST, IDS[1]).reason


CAPTURES = Path(__file__).with_name('tap_reports') / 'runner'
EXITS = json.loads((CAPTURES / 'exits.json').read_text())


@pytest.mark.parametrize('name', sorted(EXITS))
def test_the_probe_leaves_the_tap_stream_and_exit_status_unchanged(tmp_path, name):
    """Every recorded runner case under the probe: same exit and TAP, Perl naming the file `./t/...` as `do` loads it."""
    path = f't/{name}.t'
    (tmp_path / 't').mkdir()
    (tmp_path / path).write_bytes((CAPTURES / f'{name}.t').read_bytes())
    command = (PERL,)
    env = {'PATH': os.environ.get('PATH', ''), 'HOME': str(tmp_path)}
    plain = subprocess.run(command + (path,), cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    argv = perl_probe_argv(command, WitnessRequest('lib/None.pm', 'none', 'x.txt'), path, root=str(tmp_path),
                           record_path='witness.json', nonce=NONCE)
    probed = subprocess.run(argv, cwd=tmp_path, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env)
    normalized = probed.stdout.replace(b'./' + path.encode(), path.encode())
    assert (probed.returncode, normalized) == (plain.returncode, plain.stdout)
    if name in ('pass', 'fail', 'die'):
        ids = (f'{path}#test_control', f'{path}#test_security')
        located = lambda stream, status: [
            (case.outcome, case.failure and (case.failure.kind, case.failure.path, case.failure.line))
            for case in parse_tap(stream, ids, exit_status=status, test_paths=frozenset({path}))]
        assert located(probed.stdout, probed.returncode) == located(plain.stdout, plain.returncode)
